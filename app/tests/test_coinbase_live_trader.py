"""FDS-LIVE-001 phase C: live trading on Coinbase through the real trader.

Coinbase is a fake behind recorded HTTP (helpers_coinbase): accounts, products, the
public ticker, orders and order status answer as Coinbase's Advanced Trade reference
shows, and nothing can leave the machine. The fake fills at its own prices and fees,
different from the ticker's, so the tests show the trader records Coinbase's numbers
and not its own estimate.

Also here: the one-time move of the live books into live/<broker>/, the key check,
the client order id and the Trading Mode window's additions.
"""

import copy
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(__file__))

import trading_mode as tm  # noqa: E402
from helpers_coinbase import make_response, recorded_http  # noqa: E402
from pt_exchange_abstraction import (  # noqa: E402
    ConnectionStatus,
    ConnectionTestResult,
    OrderResult,
)
from test_coinbase_paper_gate import LIVE_COINBASE, CoinbaseGateBase  # noqa: E402

BROKERAGE = "https://api.coinbase.com/api/v3/brokerage"
PUBLIC = "https://api.exchange.coinbase.com/products/BTC-USD"
REAL = {"trading": {**LIVE_COINBASE["trading"], "coinbase_preview": False}}
FEE_RATE = 0.006  # the fake's fee: 0.6% of the filled value


class FakeCoinbase:
    """A Coinbase account behind recorded HTTP. Buys fill at 101.5, sells at 98.5
    (the ticker says bid 99 / ask 101). ``partial`` fills half of each order and
    cancels the rest, as a market IOC order can end."""

    def __init__(self, rec, usd=10000.0, can_trade=True, can_transfer=False):
        self.rec = rec
        self.balances = {"USD": usd, "BTC": 0.0}
        self.permissions = {
            "can_view": True,
            "can_trade": can_trade,
            "can_transfer": can_transfer,
        }
        self.orders = {}
        self.posted = []
        self.partial = False
        self.unknown = []
        rec.respond(self.answer)

    def answer(self, method, url):
        method = method.upper()  # requests.get sends "get"
        if method == "GET":
            if url == f"{BROKERAGE}/key_permissions":
                return make_response(200, self.permissions)
            if url == f"{BROKERAGE}/accounts":
                return make_response(
                    200, {"accounts": self.accounts(), "has_next": False}
                )
            if url == f"{BROKERAGE}/products/BTC-USD":
                return make_response(200, PRODUCT)
            if url == f"{PUBLIC}/ticker":
                return make_response(
                    200, {"bid": "99", "ask": "101", "price": "100", "volume": "5"}
                )
            if url == PUBLIC:
                return make_response(200, {"min_market_funds": "1", "status": "online"})
            if url.startswith(f"{BROKERAGE}/orders/historical/"):
                return make_response(200, {"order": self.orders[url.rsplit("/", 1)[1]]})
        if method == "POST" and url == f"{BROKERAGE}/orders":
            return make_response(200, self.create(self.rec.calls[-1][2]))
        if method == "POST" and url == f"{BROKERAGE}/orders/preview":
            body = json.loads(self.rec.calls[-1][2]["data"])
            self.posted.append(("preview", body))
            return make_response(
                200,
                {
                    "errs": [],
                    "quote_size": "50.00",
                    "base_size": "0.49261083",
                    "commission_total": "0.30",
                    "order_total": "50.30",
                    "est_average_filled_price": "101.5",
                    "preview_id": "p-1",
                },
            )
        self.unknown.append((method, url))
        return make_response(404, {"message": "NotFound"})

    def accounts(self):
        return [
            {"currency": c, "available_balance": {"value": str(v), "currency": c}}
            for c, v in self.balances.items()
        ]

    def create(self, kwargs):
        body = json.loads(kwargs["data"])
        self.posted.append(("order", body))
        for made in self.orders.values():
            if made["client_order_id"] == body["client_order_id"]:
                # a repeated client order id gets the order Coinbase already made
                return {
                    "success": True,
                    "success_response": {"order_id": made["order_id"]},
                }
        size = body["order_configuration"]["market_market_ioc"]
        order_id = f"cb-{len(self.orders) + 1}"
        share = 0.5 if self.partial else 1.0
        if body["side"] == "BUY":
            value = float(size["quote_size"]) * share
            price = 101.5
            filled = value / price
            fee = value * FEE_RATE
            self.balances["USD"] -= value + fee
            self.balances["BTC"] += filled
        else:
            filled = float(size["base_size"]) * share
            price = 98.5
            value = filled * price
            fee = value * FEE_RATE
            self.balances["USD"] += value - fee
            self.balances["BTC"] -= filled
        self.orders[order_id] = {
            "order_id": order_id,
            "client_order_id": body["client_order_id"],
            "product_id": "BTC-USD",
            "side": body["side"],
            "status": "CANCELLED" if self.partial else "FILLED",
            "filled_size": repr(filled),
            "average_filled_price": repr(price),
            "filled_value": repr(value),
            "total_fees": repr(fee),
            "completion_percentage": "50" if self.partial else "100",
            "order_configuration": body["order_configuration"],
        }
        return {"success": True, "success_response": {"order_id": order_id}}

    def order_calls(self):
        return [b for kind, b in self.posted if kind == "order"]


PRODUCT = {
    "product_id": "BTC-USD",
    "price": "100",
    "base_increment": "0.00000001",
    "quote_increment": "0.01",
    "base_min_size": "0.00000001",
    "quote_min_size": "1",
}


def rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class LiveTraderTests(CoinbaseGateBase):
    def setUp(self):
        super().setUp()
        sleep = mock.patch("pt_trader.time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def books(self, *parts):
        return os.path.join(self.tmp.name, "live", "coinbase", *parts)

    def test_a_buy_and_a_sell_are_recorded_with_coinbases_own_numbers(self):
        with recorded_http() as rec:
            cb = FakeCoinbase(rec)
            trader = self.trader(copy.deepcopy(REAL))
            buy = trader.place_buy_order("client-buy", "buy", "market", "BTC-USD", 50.0)
            held = cb.balances["BTC"]
            sell = trader.place_sell_order(
                "client-sell", "sell", "market", "BTC-USD", held
            )
        self.assertEqual(cb.unknown, [])
        self.assertEqual(buy["state"], "filled")
        self.assertEqual(sell["state"], "filled")

        # the trader's client order ids reached Coinbase
        orders = cb.order_calls()
        self.assertEqual(
            [o["client_order_id"] for o in orders], ["client-buy", "client-sell"]
        )
        self.assertEqual([o["side"] for o in orders], ["BUY", "SELL"])

        history = rows(self.books("trade_history.jsonl"))
        self.assertEqual([r["side"] for r in history], ["buy", "sell"])
        placed = list(cb.orders.values())
        for row, order in zip(history, placed):
            self.assertAlmostEqual(row["qty"], float(order["filled_size"]))
            self.assertAlmostEqual(row["price"], float(order["average_filled_price"]))
            self.assertAlmostEqual(row["fees_usd"], float(order["total_fees"]))
            self.assertEqual(row["order_id"], order["order_id"])

        bought, sold = placed
        cost = float(bought["filled_value"]) + float(bought["total_fees"])
        proceeds = float(sold["filled_value"]) - float(sold["total_fees"])
        self.assertAlmostEqual(history[0]["position_cost_after_usd"], cost)
        # the sell was rounded down to Coinbase's 0.00000001 BTC step, so the cost is
        # charged for the share that was sold
        share = float(sold["filled_size"]) / float(bought["filled_size"])
        self.assertLess(share, 1.0)
        realized = proceeds - cost * share
        self.assertAlmostEqual(history[1]["realized_profit_usd"], realized)
        with open(self.books("pnl_ledger.json"), encoding="utf-8") as f:
            ledger = json.load(f)
        self.assertAlmostEqual(ledger["total_realized_profit_usd"], realized)
        self.assertEqual(ledger["pending_orders"], {})
        # nothing was written to the hub folder itself
        self.assertFalse(
            os.path.exists(os.path.join(self.tmp.name, "trade_history.jsonl"))
        )

    def test_an_order_that_filled_in_part_is_recorded_at_the_part_that_filled(self):
        with recorded_http() as rec:
            cb = FakeCoinbase(rec)
            cb.partial = True
            trader = self.trader(copy.deepcopy(REAL))
            result = trader.place_buy_order("c-1", "buy", "market", "BTC-USD", 50.0)
        (order,) = cb.orders.values()
        self.assertEqual(result["quantity"], float(order["filled_size"]))
        (row,) = rows(self.books("trade_history.jsonl"))
        self.assertAlmostEqual(row["qty"], float(order["filled_size"]))
        self.assertAlmostEqual(
            row["position_cost_after_usd"],
            float(order["filled_value"]) + float(order["total_fees"]),
        )

    def test_an_order_coinbase_already_made_is_not_recorded_twice(self):
        with recorded_http() as rec:
            cb = FakeCoinbase(rec)
            trader = self.trader(copy.deepcopy(REAL))
            first = trader.place_buy_order("same", "buy", "market", "BTC-USD", 50.0)
            again = trader.place_buy_order("same", "buy", "market", "BTC-USD", 50.0)
        self.assertEqual(first["state"], "filled")
        self.assertIsNone(again)
        self.assertEqual(len(cb.order_calls()), 2)  # both reached Coinbase...
        self.assertEqual(list(cb.orders), ["cb-1"])  # ...which made one order
        (row,) = rows(self.books("trade_history.jsonl"))
        self.assertEqual(row["order_id"], "cb-1")
        self.assertEqual(trader._pnl_ledger.get("pending_orders", {}), {})

    def test_preview_mode_places_nothing_records_nothing_and_does_not_repeat(self):
        with recorded_http() as rec:
            cb = FakeCoinbase(rec, can_trade=False)  # a view-only key is enough
            trader = self.trader(copy.deepcopy(LIVE_COINBASE))
            with mock.patch("builtins.print") as printed:
                first = trader.place_buy_order("c-1", "buy", "market", "BTC-USD", 50.0)
                again = trader.place_buy_order("c-2", "buy", "market", "BTC-USD", 50.0)
        self.assertIsNone(first)
        self.assertIsNone(again)
        self.assertEqual(cb.order_calls(), [])  # no POST /orders at all
        self.assertEqual([kind for kind, _ in cb.posted], ["preview"])  # once
        self.assertTrue(
            any(
                "ORDER PREVIEW" in str(c) and "would buy" in str(c)
                for c in printed.call_args_list
            )
        )
        self.assertFalse(os.path.exists(self.books("preview", "trade_history.jsonl")))
        self.assertEqual(trader._pnl_ledger.get("pending_orders", {}), {})

    def test_a_key_that_can_transfer_is_allowed_with_a_warning(self):
        with recorded_http() as rec:
            FakeCoinbase(rec, can_transfer=True)
            with mock.patch("builtins.print") as printed:
                trader = self.trader(copy.deepcopy(REAL))
        self.assertFalse(trader._target.preview)
        self.assertTrue(
            any(tm.KEY_CAN_TRANSFER in str(c) for c in printed.call_args_list)
        )


class BookMoveTests(CoinbaseGateBase):
    def write(self, folder, name, text):
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(text)

    def test_books_in_the_hub_folder_move_once_into_live_broker_after_a_backup(self):
        hub = self.tmp.name
        self.write(hub, "trade_history.jsonl", '{"side": "buy"}\n')
        self.write(hub, "pnl_ledger.json", '{"total_realized_profit_usd": 1.5}')
        self.write(hub, "runner_ready.json", "{}")  # not a book: stays
        moved = tm.move_root_live_books(hub, "binance")
        self.assertEqual(moved, os.path.join(hub, "live", "binance"))
        self.assertEqual(
            sorted(os.listdir(moved)), ["pnl_ledger.json", "trade_history.jsonl"]
        )
        self.assertFalse(os.path.exists(os.path.join(hub, "trade_history.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(hub, "runner_ready.json")))
        (backup,) = [n for n in os.listdir(hub) if n.startswith("live_books_backup_")]
        with open(os.path.join(hub, backup, "pnl_ledger.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["total_realized_profit_usd"], 1.5)
        self.assertIsNone(tm.move_root_live_books(hub, "binance"))  # once

    def test_books_are_never_merged_into_a_broker_folder_that_has_books(self):
        hub = self.tmp.name
        self.write(hub, "trade_history.jsonl", "old\n")
        self.write(os.path.join(hub, "live", "binance"), "trade_history.jsonl", "new\n")
        self.assertIsNone(tm.move_root_live_books(hub, "binance"))
        with open(os.path.join(hub, "trade_history.jsonl"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "old\n")

    def test_a_move_that_stopped_part_way_is_finished_next_time(self):
        hub = self.tmp.name
        self.write(hub, "trade_history.jsonl", '{"side": "buy"}\n')
        self.write(hub, "pnl_ledger.json", '{"total_realized_profit_usd": 1.5}')
        dest = os.path.join(hub, "live", "binance")
        real_replace = os.replace

        def ledger_in_use(source, target):
            if os.path.basename(source) == "pnl_ledger.json":
                raise PermissionError("in use")
            return real_replace(source, target)

        with mock.patch("trading_mode.os.replace", side_effect=ledger_in_use):
            with self.assertRaises(OSError):
                tm.move_root_live_books(hub, "binance")
        # stopped half way: the history moved, the ledger did not
        self.assertTrue(os.path.exists(os.path.join(dest, "trade_history.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(hub, "pnl_ledger.json")))

        self.assertEqual(tm.move_root_live_books(hub, "binance"), dest)  # finished
        self.assertEqual(
            sorted(os.listdir(dest)), ["pnl_ledger.json", "trade_history.jsonl"]
        )
        self.assertFalse(os.path.exists(os.path.join(hub, "pnl_ledger.json")))
        backups = [n for n in os.listdir(hub) if n.startswith("live_books_backup_")]
        self.assertEqual(len(backups), 1)
        self.assertIsNone(tm.move_root_live_books(hub, "binance"))

    def test_the_trader_does_not_start_on_books_it_could_not_move(self):
        self.write(
            self.tmp.name, "pnl_ledger.json", '{"total_realized_profit_usd": 2.0}'
        )
        real_replace = os.replace

        def ledger_in_use(source, target):
            if os.path.basename(source) in tm.LIVE_BOOK_FILES:
                raise PermissionError("in use")
            return real_replace(source, target)

        with recorded_http() as rec, mock.patch("pt_trader.time.sleep"):
            FakeCoinbase(rec)
            with mock.patch("trading_mode.os.replace", side_effect=ledger_in_use):
                with self.assertRaises(tm.LiveTradingRefused) as caught:
                    self.trader(copy.deepcopy(REAL))
        self.assertIn("live books could not be moved", str(caught.exception))

    def test_the_trader_moves_them_when_it_starts_live(self):
        self.write(
            self.tmp.name, "pnl_ledger.json", '{"total_realized_profit_usd": 2.0}'
        )
        with recorded_http() as rec, mock.patch("pt_trader.time.sleep"):
            FakeCoinbase(rec)
            trader = self.trader(copy.deepcopy(REAL))
        self.assertEqual(trader._pnl_ledger["total_realized_profit_usd"], 2.0)
        self.assertTrue(
            os.path.exists(
                os.path.join(self.tmp.name, "live", "coinbase", "pnl_ledger.json")
            )
        )


class ApiBooksTests(unittest.TestCase):
    def setUp(self):
        try:
            import pt_api_server
        except ImportError as exc:  # flask is optional
            self.skipTest(f"pt_api_server not importable: {exc}")
        self.api = pt_api_server
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_the_api_serves_the_books_of_the_trading_mode_in_use(self):
        hub = self.tmp.name
        books = self.api.books_dir_for(hub, copy.deepcopy(REAL))
        self.assertEqual(books, os.path.join(hub, "live", "coinbase"))
        self.assertEqual(
            self.api.books_dir_for(hub, copy.deepcopy(LIVE_COINBASE)),
            os.path.join(hub, "live", "coinbase", "preview"),
        )
        os.makedirs(books)
        with open(os.path.join(books, "trader_status.json"), "w") as f:
            json.dump({"account_value_usd": 123.0, "positions": []}, f)
        with open(os.path.join(books, "trade_history.jsonl"), "w") as f:
            f.write(json.dumps({"symbol": "BTC-USD", "side": "buy"}) + "\n")
        client = self.api.create_api_server(hub, books_dir=books).app.test_client()
        self.assertEqual(client.get("/api/status").get_json()["total_value"], 123.0)
        history = client.get("/api/history").get_json()
        self.assertEqual([t["side"] for t in history], ["buy"])

    def test_the_hub_gives_the_api_the_books_it_shows(self):
        import pt_hub

        hub = object.__new__(pt_hub.PowerTraderHub)
        hub.hub_dir, hub._books_dir = "hub", os.path.join("hub", "paper")
        hub._api_server_port, hub._api_server_host = 8080, "127.0.0.1"
        hub._api_server_enabled = False
        with mock.patch.object(
            pt_hub, "create_api_server", create=True
        ) as create, mock.patch.object(pt_hub, "API_SERVER_AVAILABLE", True):
            pt_hub.PowerTraderHub._init_api_server(hub)
        create.assert_called_once_with(
            hub_data_dir="hub",
            port=8080,
            host="127.0.0.1",
            books_dir=os.path.join("hub", "paper"),
        )


class KeyCheckTests(unittest.TestCase):
    def check(self, status, preview=False, **details):
        exchange = mock.Mock()
        exchange.check_connection.return_value = ConnectionTestResult(
            "coinbase", status, "the check's message", details
        )
        return tm.check_live_key(exchange, preview)

    def test_the_key_check_decides_who_may_trade(self):
        ok = ConnectionStatus.OK
        self.assertTrue(self.check(ok, can_trade=True).ok)
        refused = self.check(ok, can_trade=False)
        self.assertFalse(refused.ok)
        self.assertIn(tm.KEY_CANNOT_TRADE, refused.message)
        self.assertTrue(self.check(ok, preview=True, can_trade=False).ok)
        warned = self.check(ok, can_trade=True, can_transfer=True)
        self.assertTrue(warned.ok)
        self.assertEqual(warned.warning, tm.KEY_CAN_TRANSFER)
        for failed in (
            ConnectionStatus.AUTH_FAILED,
            ConnectionStatus.NETWORK_ERROR,
            ConnectionStatus.INVALID_CREDENTIALS,
        ):
            self.assertFalse(self.check(failed).ok, failed)
        # a connector with no key check (most of them) is not refused for it
        self.assertTrue(self.check(ConnectionStatus.UNSUPPORTED).ok)


class ClientOrderIdTests(unittest.TestCase):
    def target(self, exchange):
        return tm.OrderTarget(tm.TradingMode.LIVE, "x", exchange, "live:x")

    def test_the_id_goes_to_a_connector_that_takes_one_and_not_to_one_that_does_not(
        self,
    ):
        seen = []
        done = OrderResult("1", "BTC-USD", "buy", 1.0, 1.0, "filled", "x", 0.0)

        class Takes:
            def place_order(
                self, symbol, side, amount, price=None, *, client_order_id=None
            ):
                seen.append(client_order_id)
                return done

        class Ignores:
            def place_order(self, symbol, side, amount, price=None):
                seen.append("no id")
                return done

        self.target(Takes()).place_order("BTC-USD", "buy", 1.0, client_order_id="abc")
        # an empty id is passed on unchanged (the connector refuses it), not dropped
        self.target(Takes()).place_order("BTC-USD", "buy", 1.0, client_order_id="")
        self.target(Takes()).place_order("BTC-USD", "buy", 1.0)
        self.target(Ignores()).place_order("BTC-USD", "buy", 1.0, client_order_id="abc")
        self.assertEqual(seen, ["abc", "", None, "no id"])


class TradingModeWindowTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk

        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display available")
        self.addCleanup(self.root.destroy)
        self.root.withdraw()

    def dialog(self, key_check, applied):
        from trading_mode_ui import TradingModeDialog

        def apply(mode, broker=None, testnet=None, live_confirmed=False, **options):
            applied.append((mode, broker, options))
            return tm.read_trading_settings(LIVE_COINBASE)

        dialog = TradingModeDialog(
            self.root,
            current=tm.read_trading_settings({"trading": {"mode": "paper"}}),
            brokers=["binance", "coinbase"],
            on_applied=lambda s: None,
            apply_fn=apply,
            key_check_fn=key_check,
        )
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        dialog.mode_var.set("live")
        dialog.broker_var.set("coinbase")
        dialog.confirm_var.set(True)
        dialog._refresh()
        return dialog

    def test_coinbase_previews_by_default_and_says_it_has_no_test_network(self):
        applied = []
        dialog = self.dialog(
            lambda b, p: tm.KeyCheck(True, "view: yes, trade: no"), applied
        )
        self.assertTrue(dialog.preview_var.get())
        self.assertEqual(str(dialog.preview_cb.cget("state")), "normal")
        self.assertEqual(str(dialog.testnet_cb.cget("state")), "disabled")
        self.assertIn("nothing is bought or sold", dialog.note_var.get())
        dialog.preview_var.set(False)
        dialog._refresh()
        self.assertIn(
            "Coinbase has no test network: live orders use real money",
            dialog.note_var.get(),
        )
        dialog.check_key()
        self.assertEqual(dialog.key_var.get(), "view: yes, trade: no")

    def test_apply_is_refused_when_the_key_check_refuses_the_key(self):
        applied = []
        dialog = self.dialog(
            lambda b, p: tm.KeyCheck(False, tm.KEY_CANNOT_TRADE), applied
        )
        dialog.preview_var.set(False)
        with mock.patch("trading_mode_ui.messagebox") as box:
            dialog._apply()
        box.showerror.assert_called_once()
        self.assertIn(tm.KEY_CANNOT_TRADE, box.showerror.call_args[0][1])
        self.assertEqual(applied, [])

    def test_apply_saves_the_preview_choice(self):
        applied = []
        checks = []

        def key_check(broker, preview):
            checks.append((broker, preview))
            return tm.KeyCheck(True, "ok", tm.KEY_CAN_TRANSFER)

        dialog = self.dialog(key_check, applied)
        with mock.patch("trading_mode_ui.messagebox") as box:
            dialog._apply()
        box.showwarning.assert_called_once()  # the Transfer warning, then applied
        self.assertEqual(checks, [("coinbase", True)])
        self.assertEqual(applied, [("live", "coinbase", {"preview": True})])


if __name__ == "__main__":
    unittest.main()
