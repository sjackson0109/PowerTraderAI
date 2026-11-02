"""FDS-LIVE-001 phase B: Coinbase orders, previews and cancels.

Recorded HTTP only (helpers_coinbase): every request is captured and nothing can
leave the machine. Shapes follow Coinbase's Advanced Trade reference (create
order, preview order, batch cancel). Coinbase's documentation asks for a market
buy in dollars (quote_size) and a market sell in coins (base_size); the trader
always sizes in coins, so the connector converts a buy (decision D2).
"""

import base64
import json
import os
import sys
import unittest

import requests

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(__file__))

from helpers_coinbase import (  # noqa: E402
    KEY_NAME,
    make_ec_pem,
    make_ed25519_secret,
    make_response,
    recorded_http,
)
from pt_exchanges import CoinbaseExchange  # noqa: E402

BROKERAGE = "https://api.coinbase.com/api/v3/brokerage"
TICKER = "https://api.exchange.coinbase.com/products/BTC-USD/ticker"

PRODUCT = {
    "product_id": "BTC-USD",
    "price": "70000",
    "base_increment": "0.00000001",
    "quote_increment": "0.01",
    "base_min_size": "0.00000001",
    "quote_min_size": "1",
    "trading_disabled": False,
    "is_disabled": False,
    "cancel_only": False,
    "limit_only": False,
}
TICKER_BODY = {
    "bid": "69990",
    "ask": "70010",
    "price": "70000",
    "time": "2026-10-31T10:00:00Z",
}
CREATED = {
    "success": True,
    "success_response": {
        "order_id": "cb-order-1",
        "product_id": "BTC-USD",
        "side": "BUY",
        "client_order_id": "trader-uuid-1",
    },
}


class Coinbase:
    """A recorded Coinbase: the product, the public ticker and one answer for each
    POST path (a Response, a dict for HTTP 200, or an exception to raise)."""

    def __init__(self, rec, product=None, posts=None):
        self.rec = rec
        self.product = product or PRODUCT
        self.posts = posts or {}
        self.ticker_reads = 0
        rec.respond(self.answer)

    def answer(self, method, url):
        method = method.upper()  # requests.get sends "get"
        if method == "GET" and url == TICKER:
            self.ticker_reads += 1
            return make_response(200, TICKER_BODY)
        if method == "GET" and url == f"{BROKERAGE}/products/BTC-USD":
            return make_response(200, self.product)
        if method == "POST":
            answer = self.posts[url[len(BROKERAGE) :]]
            if isinstance(answer, Exception):
                raise answer
            return (
                answer
                if isinstance(answer, requests.Response)
                else make_response(200, answer)
            )
        raise AssertionError(f"unexpected request {method} {url}")

    def posted(self):
        return [
            (u[len(BROKERAGE) :], json.loads(k["data"]))
            for m, u, k in self.rec.calls
            if m == "POST"
        ]

    def claims(self):
        out = []
        for m, u, k in self.rec.calls:
            if m == "POST":
                token = k["headers"]["Authorization"].split(" ", 1)[1].split(".")[1]
                out.append(
                    json.loads(
                        base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
                    )["uri"]
                )
        return out


def connector(secret=None):
    return CoinbaseExchange(
        api_key=KEY_NAME, api_secret=secret or make_ed25519_secret()
    )


class PlaceOrderTests(unittest.TestCase):
    def test_a_buy_is_sent_in_dollars_with_the_traders_client_order_id(self):
        with recorded_http() as rec:
            cb = Coinbase(rec, posts={"/orders": CREATED})
            result = connector().place_order(
                "BTC-USD", "buy", 0.01, client_order_id="trader-uuid-1"
            )
        ((path, body),) = cb.posted()
        self.assertEqual(path, "/orders")
        self.assertEqual(
            body,
            {
                "client_order_id": "trader-uuid-1",
                "product_id": "BTC-USD",
                "side": "BUY",
                # 0.01 BTC x the 70010 ask (not the 70000 last price), to the cent
                "order_configuration": {"market_market_ioc": {"quote_size": "700.10"}},
            },
        )
        self.assertEqual(cb.ticker_reads, 1)
        self.assertEqual(cb.claims(), ["POST api.coinbase.com/api/v3/brokerage/orders"])
        self.assertEqual(
            (result.status, result.order_id, result.side, result.exchange),
            ("pending", "cb-order-1", "buy", "coinbase"),
        )

    def test_a_minimum_sized_buy_is_not_rounded_below_the_minimum(self):
        # the trader sizes a $1 entry as round(1 / ask, 8) coins
        coins = round(1.0 / 70010, 8)
        with recorded_http() as rec:
            cb = Coinbase(rec, posts={"/orders": CREATED})
            self.assertEqual(
                connector().place_order("BTC-USD", "buy", coins).status, "pending"
            )
        size = cb.posted()[0][1]["order_configuration"]["market_market_ioc"]
        self.assertEqual(size, {"quote_size": "1.00"})

    def test_a_sell_is_sent_in_coins_rounded_down_to_the_increment(self):
        with recorded_http() as rec:
            cb = Coinbase(rec, posts={"/orders": CREATED})
            connector().place_order("BTC-USD", "sell", 0.000142857999)
        body = cb.posted()[0][1]
        self.assertEqual(body["side"], "SELL")
        self.assertEqual(
            body["order_configuration"],
            {"market_market_ioc": {"base_size": "0.00014285"}},
        )
        self.assertTrue(body["client_order_id"])  # a new one when none is given

    def test_an_order_below_the_minimum_sends_nothing(self):
        cases = [
            ("sell", 0.000000001, {}),  # below base_min_size
            ("buy", 0.00001, {}),  # 0.70 at the ask: below quote_min_size
            ("buy", 0.01, {"trading_disabled": True}),
            ("sell", 0.01, {"cancel_only": True}),
        ]
        for side, coins, flags in cases:
            with recorded_http() as rec:
                cb = Coinbase(rec, product={**PRODUCT, **flags})
                result = connector().place_order("BTC-USD", side, coins)
            self.assertEqual(cb.posted(), [], (side, coins, flags))
            self.assertEqual(result.status, "rejected")
            self.assertTrue(result.reason, (side, coins, flags))

    def test_a_refusal_by_coinbase_returns_its_reason(self):
        refused = {
            "success": False,
            "error_response": {
                "error": "INSUFFICIENT_FUND",
                "message": "Insufficient balance in source account",
                "new_order_failure_reason": "INSUFFICIENT_FUND",
            },
        }
        with recorded_http() as rec:
            Coinbase(rec, posts={"/orders": refused})
            result = connector().place_order("BTC-USD", "buy", 0.001)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(
            result.reason, "INSUFFICIENT_FUND: Insufficient balance in source account"
        )

    def test_a_repeated_client_order_id_gets_the_order_coinbase_already_made(self):
        # Coinbase's reference: "If the ID provided is not unique, the order will not
        # be created ... the order corresponding with that ID will be returned"
        with recorded_http() as rec:
            cb = Coinbase(rec, posts={"/orders": CREATED})
            first = connector().place_order(
                "BTC-USD", "buy", 0.001, client_order_id="same"
            )
            again = connector().place_order(
                "BTC-USD", "buy", 0.001, client_order_id="same"
            )
        self.assertEqual(first.order_id, again.order_id)
        self.assertEqual(
            [b["client_order_id"] for _, b in cb.posted()], ["same", "same"]
        )
        # and the failure reason Coinbase also lists is reported, not raised
        duplicate = {
            "success": False,
            "error_response": {"new_order_failure_reason": "DUPLICATE_CLIENT_ORDER_ID"},
        }
        with recorded_http() as rec:
            Coinbase(rec, posts={"/orders": duplicate})
            result = connector().place_order(
                "BTC-USD", "buy", 0.001, client_order_id="same"
            )
        self.assertEqual(
            (result.status, result.reason), ("rejected", "DUPLICATE_CLIENT_ORDER_ID")
        )

    def test_a_network_error_during_an_order_is_raised_and_not_retried(self):
        for failure in (
            requests.exceptions.ConnectionError("reset"),
            make_response(429, {"message": "rate limited"}),
            make_response(500, {"message": "oops"}),
        ):
            with recorded_http() as rec:
                cb = Coinbase(rec, posts={"/orders": failure})
                with self.assertRaises(Exception):
                    connector().place_order("BTC-USD", "buy", 0.001)
            self.assertEqual(len(cb.posted()), 1, failure)

    def test_a_limit_price_is_refused(self):
        with recorded_http() as rec:
            with self.assertRaises(ValueError):
                connector().place_order("BTC-USD", "buy", 0.001, price=60000.0)
        self.assertEqual(rec.calls, [])

    def test_an_empty_client_order_id_is_refused_not_replaced(self):
        # The caller's id is never swapped for a new one: a blank id raises
        # before any request, and only a missing (None) id gets a new one.
        with recorded_http() as rec:
            for blank in ("", "   "):
                with self.assertRaises(ValueError):
                    connector().place_order(
                        "BTC-USD", "buy", 0.001, client_order_id=blank
                    )
        self.assertEqual(rec.calls, [])

    def test_an_ed25519_key_refused_for_an_order_names_the_key_type_coinbase_asks_for(
        self,
    ):
        for secret, hinted in ((make_ed25519_secret(), True), (make_ec_pem(), False)):
            with recorded_http() as rec:
                Coinbase(
                    rec,
                    posts={"/orders": make_response(401, {"message": "Unauthorized"})},
                )
                with self.assertRaises(RuntimeError) as caught:
                    connector(secret).place_order("BTC-USD", "buy", 0.001)
            self.assertEqual("ECDSA (ES256)" in str(caught.exception), hinted)


class PreviewTests(unittest.TestCase):
    PREVIEW = {
        "order_total": "14.08",
        "commission_total": "0.08",
        "errs": [],
        "warning": [],
        "quote_size": "14.00",
        "base_size": "0.00019997",
        "best_bid": "69990",
        "best_ask": "70010",
        "is_max": False,
        "est_average_filled_price": "70010.2",
        "preview_id": "preview-1",
    }

    def test_a_preview_reports_what_coinbase_would_do_and_places_nothing(self):
        with recorded_http() as rec:
            cb = Coinbase(rec, posts={"/orders/preview": self.PREVIEW})
            result = connector().preview_order("BTC-USD", "buy", 0.0002)
        ((path, body),) = cb.posted()
        self.assertEqual(path, "/orders/preview")
        self.assertNotIn("client_order_id", body)
        self.assertEqual(
            body["order_configuration"], {"market_market_ioc": {"quote_size": "14.00"}}
        )
        self.assertEqual(result.status, "preview")
        self.assertEqual(
            result.reason,
            "would buy 0.00019997 BTC, for $14.00, at about $70,010.20, fee $0.08, total $14.08",
        )
        self.assertEqual(
            (result.amount, result.price, result.fee, result.filled_value),
            (0.00019997, 70010.2, 0.08, 14.0),
        )

    def test_a_preview_coinbase_would_refuse_says_why(self):
        with recorded_http() as rec:
            Coinbase(
                rec,
                posts={
                    "/orders/preview": {
                        **self.PREVIEW,
                        "errs": ["PREVIEW_INSUFFICIENT_FUND"],
                    }
                },
            )
            result = connector().preview_order("BTC-USD", "sell", 0.01)
        self.assertEqual(
            (result.status, result.reason),
            ("rejected", "PREVIEW: PREVIEW_INSUFFICIENT_FUND"),
        )


class CancelTests(unittest.TestCase):
    def test_cancel_sends_one_order_id_and_reads_its_result(self):
        for success in (True, False):
            with recorded_http() as rec:
                cb = Coinbase(
                    rec,
                    posts={
                        "/orders/batch_cancel": {
                            "results": [{"success": success, "order_id": "cb-order-1"}]
                        }
                    },
                )
                self.assertIs(connector().cancel_order("cb-order-1"), success)
            self.assertEqual(
                cb.posted(), [("/orders/batch_cancel", {"order_ids": ["cb-order-1"]})]
            )


class LiveTests(unittest.TestCase):
    def test_the_connector_is_offered_for_live_trading_and_previews(self):
        # set in phase C, with the gate, the key check and the trader's books
        self.assertTrue(CoinbaseExchange.SUPPORTS_LIVE_ORDERS)
        self.assertTrue(CoinbaseExchange.SUPPORTS_ORDER_PREVIEW)


if __name__ == "__main__":
    unittest.main()
