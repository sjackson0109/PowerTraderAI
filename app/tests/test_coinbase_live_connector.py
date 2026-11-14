"""FDS-LIVE-001 phase A: the Coinbase connector's read-only calls.

Balances, product rules and order status, through recorded HTTP (helpers_coinbase):
every request is captured and nothing can leave the machine. The response shapes
follow Coinbase's Advanced Trade reference (accounts, products, get order). No test
here sends an order.
"""

import base64
import json
import os
import sys
import unittest
from decimal import Decimal
from unittest import mock

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(__file__))

import pt_exchanges  # noqa: E402
from helpers_coinbase import (  # noqa: E402
    KEY_NAME,
    make_ed25519_secret,
    make_response,
    recorded_http,
)
from pt_exchanges import CoinbaseExchange  # noqa: E402

BROKERAGE = "https://api.coinbase.com/api/v3/brokerage"


def connector():
    return CoinbaseExchange(api_key=KEY_NAME, api_secret=make_ed25519_secret())


def claim(call) -> str:
    """The ``uri`` claim of the JWT a recorded request carried."""
    token = call[2]["headers"]["Authorization"].split(" ", 1)[1]
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["uri"]


def account(currency, available, hold="0"):
    return {
        "uuid": f"uuid-{currency}",
        "name": f"{currency} Wallet",
        "currency": currency,
        "available_balance": {"value": available, "currency": currency},
        "hold": {"value": hold, "currency": currency},
        "type": "ACCOUNT_TYPE_CRYPTO",
        "ready": True,
        "active": True,
    }


def order(status, **fields):
    body = {
        "order_id": "0000-1111",
        "product_id": "BTC-USD",
        "side": "BUY",
        "client_order_id": "client-1",
        "status": status,
        "created_time": "2026-10-31T10:00:00.000000Z",
        "filled_size": "0",
        "average_filled_price": "0",
        "filled_value": "0",
        "total_fees": "0",
        "order_configuration": {"market_market_ioc": {"base_size": "0.0002"}},
    }
    body.update(fields)
    return {"order": body}


class ConstructionTests(unittest.TestCase):
    def test_it_builds_without_keys_and_reads_nothing_that_needs_one(self):
        exchange = CoinbaseExchange()
        self.assertEqual((exchange.api_key, exchange.api_secret), ("", ""))
        with recorded_http() as rec:
            with self.assertRaises(RuntimeError) as caught:
                exchange.get_balance()
        self.assertIn("Configure Exchange APIs", str(caught.exception))
        self.assertEqual(rec.calls, [])


class BalanceTests(unittest.TestCase):
    def test_every_page_is_read_and_only_available_funds_count(self):
        pages = {
            None: {
                "accounts": [account("USD", "12.50", hold="5"), account("BTC", "0")],
                "has_next": True,
                "cursor": "page-2",
            },
            "page-2": {
                "accounts": [account("ETH", "0.75"), account("USDC", "3")],
                "has_next": False,
                "cursor": "",
            },
        }
        with recorded_http() as rec:
            rec.respond(
                lambda m, u: make_response(
                    200, pages[rec.calls[-1][2]["params"].get("cursor")]
                )
            )
            balances = connector().get_balance()
        self.assertEqual(balances, {"USD": 12.5, "ETH": 0.75, "USDC": 3.0})
        self.assertEqual(rec.methods, ["GET", "GET"])
        self.assertEqual(rec.urls, [f"{BROKERAGE}/accounts"] * 2)
        self.assertEqual(
            [c[2]["params"] for c in rec.calls],
            [{"limit": 250}, {"limit": 250, "cursor": "page-2"}],
        )
        # the query travels in the request, never in the signed claim
        for call in rec.calls:
            self.assertEqual(
                claim(call), "GET api.coinbase.com/api/v3/brokerage/accounts"
            )

    def test_the_drawdown_stops_balances_add_the_funds_on_hold(self):
        # ``hold`` is in the account shape Coinbase's reference shows; that it holds
        # a resting order's funds is not verified on a live account (phase 0)
        page = {
            "accounts": [
                account("USD", "5100", hold="900"),
                account("BTC", "0.04"),
                account("ETH", "0", hold="0.5"),
                account("SOL", "0", hold="0"),
            ],
            "has_next": False,
        }
        with recorded_http() as rec:
            rec.respond_with(200, page)
            balances = connector().get_balance_with_holds()
            available = connector().get_balance()
        self.assertEqual(balances, {"USD": 6000.0, "BTC": 0.04, "ETH": 0.5})
        self.assertEqual(available, {"USD": 5100.0, "BTC": 0.04})  # unchanged
        self.assertEqual(rec.urls, [f"{BROKERAGE}/accounts"] * 2)

    def test_a_rate_limited_read_waits_and_is_tried_again(self):
        answers = [
            make_response(429, {"message": "slow down"}),
            make_response(200, {"accounts": []}),
        ]
        with recorded_http() as rec, mock.patch.object(
            pt_exchanges.time, "sleep"
        ) as sleep:
            rec.respond(lambda m, u: answers.pop(0))
            self.assertEqual(connector().get_balance(), {})
        self.assertEqual(len(rec.calls), 2)
        sleep.assert_called_once_with(CoinbaseExchange.BACKOFF_SECONDS[0])

    def test_an_http_error_is_raised_with_coinbases_message(self):
        with recorded_http() as rec:
            rec.respond_with(401, {"message": "Unauthorized"})
            with self.assertRaises(RuntimeError) as caught:
                connector().get_balance()
        text = str(caught.exception)
        self.assertIn("HTTP 401", text)
        self.assertIn("Unauthorized", text)
        self.assertIn("Configure Exchange APIs", text)


PRODUCT = {
    "product_id": "BTC-USD",
    "price": "70000.12",
    "base_increment": "0.00000001",
    "quote_increment": "0.01",
    "base_min_size": "0.00000001",
    "quote_min_size": "1",
    "trading_disabled": False,
    "is_disabled": False,
    "cancel_only": False,
    "limit_only": False,
}


class ProductRuleTests(unittest.TestCase):
    def test_rules_are_read_once_an_hour(self):
        exchange = connector()
        with recorded_http() as rec, mock.patch.object(
            pt_exchanges.time, "time"
        ) as now:
            now.return_value = 1000.0
            rec.respond_with(200, PRODUCT)
            first = exchange.product_rules("BTC-USD")
            exchange.product_rules("BTC-USDT")
            now.return_value = 1000.0 + CoinbaseExchange.PRODUCT_RULES_SECONDS + 1
            exchange.product_rules("BTCUSDT")
        self.assertEqual(rec.urls, [f"{BROKERAGE}/products/BTC-USD"] * 2)
        self.assertEqual(first["quote_min_size"], Decimal("1"))
        self.assertEqual(first["base_increment"], Decimal("0.00000001"))
        self.assertEqual(first["price"], 70000.12)
        self.assertIsNone(CoinbaseExchange.market_order_refusal(first))

    def test_a_product_that_takes_no_market_orders_says_why(self):
        for flag in ("trading_disabled", "is_disabled", "cancel_only", "limit_only"):
            with recorded_http() as rec:
                rec.respond_with(200, {**PRODUCT, flag: True})
                rules = connector().product_rules("BTC-USD")
            reason = CoinbaseExchange.market_order_refusal(rules)
            self.assertTrue(reason.startswith(flag.upper() + ":"), reason)


class OrderStatusTests(unittest.TestCase):
    def status(self, body):
        with recorded_http() as rec:
            rec.respond_with(200, body)
            result = connector().get_order_status("0000-1111")
        self.assertEqual(rec.methods, ["GET"])
        self.assertEqual(rec.urls, [f"{BROKERAGE}/orders/historical/0000-1111"])
        return result

    def test_every_coinbase_state_maps_to_a_trader_state(self):
        expected = {
            "FILLED": "filled",
            "CANCELLED": "cancelled",
            "EXPIRED": "expired",
            "FAILED": "failed",
            "PENDING": "pending",
            "OPEN": "pending",
            "QUEUED": "pending",
            "CANCEL_QUEUED": "pending",
            "EDIT_QUEUED": "pending",
            "UNKNOWN_ORDER_STATUS": "pending",
        }
        self.assertEqual(CoinbaseExchange.ORDER_STATES, expected)
        for state, mapped in expected.items():
            self.assertEqual(self.status(order(state)).status, mapped, state)

    def test_a_fill_carries_coinbases_quantity_price_value_and_fee(self):
        result = self.status(
            order(
                "FILLED",
                filled_size="0.0002",
                average_filled_price="70010.5",
                filled_value="14.0021",
                total_fees="0.0840126",
            )
        )
        self.assertEqual(
            (
                result.status,
                result.amount,
                result.price,
                result.filled_value,
                result.fee,
            ),
            ("filled", 0.0002, 70010.5, 14.0021, 0.0840126),
        )
        self.assertEqual(
            (result.order_id, result.side, result.exchange),
            ("0000-1111", "buy", "coinbase"),
        )

    def test_an_order_that_stopped_part_way_counts_the_part_that_filled(self):
        for state in ("CANCELLED", "EXPIRED"):
            result = self.status(order(state, filled_size="0.0001", filled_value="7"))
            self.assertEqual(result.status, "filled", state)
            self.assertEqual(result.amount, 0.0001)
            self.assertEqual(result.reason, "partly filled: 0.0001 of 0.0002")

    def test_a_failed_or_cancelled_order_says_why(self):
        self.assertEqual(
            self.status(order("FAILED", reject_message="Insufficient funds")).reason,
            "Insufficient funds",
        )
        self.assertEqual(
            self.status(order("CANCELLED", cancel_message="User requested")).reason,
            "User requested",
        )


if __name__ == "__main__":
    unittest.main()
