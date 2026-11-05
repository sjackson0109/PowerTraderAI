"""The exchange layer's orders beyond market orders, and the shared paper book
(owner, 2026-11-05).

* Binance and Coinbase place the order kinds their exchanges have
  (``place_native_order``) as their documented APIs describe them: Binance's LIMIT,
  STOP_LOSS_LIMIT, STOP_LOSS with ``trailingDelta`` and OCO order lists, Coinbase's
  ``limit_limit_gtc``, ``stop_limit_stop_limit_gtc`` and ``trigger_bracket_gtc``.
  Recorded requests: nothing is sent, and none of them was checked against the
  live exchanges.
* The paper account fills a limit order the market reached at its own price, at
  the maker rate.
* The paper book is shared: an account sees what another process saved.
"""

import json
import os
import sys
import time
from decimal import Decimal

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import trading_mode as tm  # noqa: E402
from pt_exchange_abstraction import TradingFees  # noqa: E402

FEES = TradingFees(maker=0.004, taker=0.006, exchange="coinbase", source="exchange")


class Prices:
    """One bid and ask per coin, as the paper account's price feed."""

    def __init__(self, **coins):
        self.coins = {c: tuple(v) for c, v in coins.items()}

    def feed(self, base):
        if base not in self.coins:
            return None
        bid, ask = self.coins[base]
        now = time.time()
        return tm.Quote(bid, ask, now, now, exchange="coinbase", pair=f"{base}-USD")


# ---- the connectors' own orders (recorded requests) ----


def test_binance_places_each_kind_as_its_documented_order(monkeypatch):
    from pt_exchange_abstraction import OrderRequest
    from pt_exchanges import BinanceExchange

    ex = BinanceExchange(api_key="k", api_secret="s")
    sent = []
    ex._symbol_filters["BTCUSDT"] = {
        "stepSize": Decimal("0.00001"),
        "tickSize": Decimal("0.01"),
        "minQty": Decimal("0"),
        "minNotional": Decimal("0"),
    }

    def signed(method, path, params=None, **_kw):
        sent.append((method, path, dict(params or {})))
        if path == "/api/v3/orderList/oco":
            return {
                "orderListId": 7,
                "listOrderStatus": "EXECUTING",
                "orderReports": [
                    {"orderId": 11, "type": "STOP_LOSS"},
                    {"orderId": 12, "type": "LIMIT_MAKER"},
                ],
            }
        if path == "/api/v3/orderList":
            return {"listOrderStatus": "ALL_DONE"}
        return {"orderId": 5, "status": "NEW", "executedQty": "0", "price": "0"}

    monkeypatch.setattr(ex, "_signed_request", signed)
    req = lambda kind, **kw: OrderRequest(
        kind=kind,
        symbol="BTC-USD",
        side="sell",
        amount=0.1,
        client_order_id="PT_1",
        **kw,
    )
    ex.place_native_order(req("limit", price=62000))
    ex.place_native_order(req("stop_limit", price=57900, stop_price=58000))
    assert ex.supports_native_order(req("trailing_stop", trail_pct=2.5))
    assert not ex.supports_native_order(req("trailing_stop", trail_pct=25))
    ex.place_native_order(req("trailing_stop", trail_pct=2.5))
    result = ex.place_native_order(req("oco", price=62000, stop_price=58000))
    limit, stop_limit, trailing, oco = [p for _m, _path, p in sent]
    assert (limit["type"], limit["price"], limit["timeInForce"]) == (
        "LIMIT",
        "62000",
        "GTC",
    )
    assert (stop_limit["type"], stop_limit["stopPrice"], stop_limit["price"]) == (
        "STOP_LOSS_LIMIT",
        "58000",
        "57900",
    )
    assert (trailing["type"], trailing["trailingDelta"]) == ("STOP_LOSS", 250)
    assert "stopPrice" not in trailing
    assert (
        oco["aboveType"],
        oco["abovePrice"],
        oco["belowType"],
        oco["belowStopPrice"],
    ) == (
        "LIMIT_MAKER",
        "62000",
        "STOP_LOSS",
        "58000",
    )
    assert result.order_id == "BTCUSDT:LIST:7"
    assert result.legs == {"take_profit": "BTCUSDT:12", "stop": "BTCUSDT:11"}
    assert ex.cancel_native_order(result.order_id) is True
    assert sent[-1][:2] == ("DELETE", "/api/v3/orderList")
    assert sent[-1][2]["orderListId"] == 7


def test_binance_order_status_gives_the_average_fill_price(monkeypatch):
    from pt_exchanges import BinanceExchange

    ex = BinanceExchange(api_key="k", api_secret="s")
    monkeypatch.setattr(
        ex,
        "_signed_request",
        lambda *a, **k: {
            "status": "FILLED",
            "side": "SELL",
            "executedQty": "0.2",
            "cummulativeQuoteQty": "12000",
            "price": "0",
        },
    )
    result = ex.native_order_status("BTCUSDT:5")
    assert (result.status, result.amount, result.price, result.filled_value) == (
        "filled",
        0.2,
        60000.0,
        12000.0,
    )


def test_coinbase_sends_limit_stop_limit_and_bracket_orders():
    sys.path.insert(0, os.path.dirname(__file__))
    from helpers_coinbase import (
        KEY_NAME,
        make_ed25519_secret,
        make_response,
        recorded_http,
    )
    from pt_exchange_abstraction import OrderRequest
    from pt_exchanges import CoinbaseExchange

    product = {
        "product_id": "BTC-USD",
        "price": "60000",
        "base_increment": "0.00000001",
        "quote_increment": "0.01",
        "price_increment": "0.01",
        "base_min_size": "0.00000001",
        "quote_min_size": "1",
    }
    created = {"success": True, "success_response": {"order_id": "cb-1"}}
    ex = CoinbaseExchange(api_key=KEY_NAME, api_secret=make_ed25519_secret())
    with recorded_http() as rec:
        rec.respond(
            lambda m, u: make_response(200, product if m.upper() == "GET" else created)
        )
        req = lambda kind, side="sell", **kw: OrderRequest(
            kind=kind,
            symbol="BTC-USD",
            side=side,
            amount=0.1,
            client_order_id="PT_1",
            **kw,
        )
        assert (
            ex.place_native_order(req("limit", side="buy", price=59000)).order_id
            == "cb-1"
        )
        ex.place_native_order(req("stop_limit", price=57900, stop_price=58000))
        ex.place_native_order(req("oco", price=62000, stop_price=58000))
        bodies = [json.loads(k["data"]) for m, u, k in rec.calls if m.upper() == "POST"]
    assert [b["client_order_id"] for b in bodies] == ["PT_1"] * 3
    assert bodies[0]["side"] == "BUY" and bodies[0]["order_configuration"] == {
        "limit_limit_gtc": {
            "base_size": "0.1",
            "limit_price": "59000",
            "post_only": False,
        }
    }
    assert bodies[1]["order_configuration"] == {
        "stop_limit_stop_limit_gtc": {
            "base_size": "0.1",
            "limit_price": "57900",
            "stop_price": "58000",
            "stop_direction": "STOP_DIRECTION_STOP_DOWN",
        }
    }
    assert bodies[2]["order_configuration"] == {
        "trigger_bracket_gtc": {
            "base_size": "0.1",
            "limit_price": "62000",
            "stop_trigger_price": "58000",
        }
    }
    assert not ex.supports_native_order(req("oco", side="buy", price=1, stop_price=2))
    assert not ex.supports_native_order(req("trailing_stop", trail_pct=2))


# ---- the shared paper book ----


def test_two_paper_accounts_on_one_book_see_each_others_fills(tmp_path):
    prices = Prices(BTC=(60000.0, 60010.0))
    path = str(tmp_path / "paper" / "paper_account.json")
    make = lambda: tm.PaperExchange(
        state_path=path,
        price_feed=prices.feed,
        fee_feed=lambda b, e: FEES,
        settings_source={},
    )
    trader, hub = make(), make()
    trader.place_order("BTC-USD", "buy", 0.05)
    assert hub.get_balance()["BTC"] == pytest.approx(0.05)  # read again from the file
    hub.place_order("BTC-USD", "buy", 0.05)
    assert trader.get_balance()["BTC"] == pytest.approx(0.1)
    trader.place_order("BTC-USD", "sell", 0.1)
    assert tm.read_paper_book(path).positions == {}
    assert hub.get_balance().get("BTC") is None


def test_a_paper_limit_fill_is_at_its_price_and_pays_the_maker_rate(tmp_path):
    prices = Prices(BTC=(58000.0, 58010.0))
    paper = tm.PaperExchange(
        price_feed=prices.feed, fee_feed=lambda b, e: FEES, settings_source={}
    )
    result = paper.fill_limit_order("BTC-USD", "buy", 0.1, 59000)
    assert (result.status, result.price, result.fee_type) == (
        "filled",
        59000.0,
        "maker",
    )
    assert result.fee == pytest.approx(5900 * 0.004)
    assert result.price_exchange == "coinbase" and result.price_source == "live"
