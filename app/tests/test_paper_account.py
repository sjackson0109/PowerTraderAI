"""Settings > Paper Account: the window that sets the paper trader's book
(starting balance, cash, positions), and its wiring into the hub.

Every test writes into its own temporary hub folder; message boxes are mocks.
"""

import gc
import json
import os
import sys
import tempfile
import time
import tkinter as tk
import types
import unittest
from tkinter import ttk
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(__file__))

import paper_account_ui  # noqa: E402
import pt_hub  # noqa: E402
import trading_mode as tm  # noqa: E402
from paper_account_ui import PaperAccountDialog  # noqa: E402


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


class TestPaperAccountDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk not available: {exc}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        gc.collect()  # leftover Tk variables die on the main thread
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.hub = tmp.name
        self.book = tm.paper_book_path(self.hub)
        self.ledger = tm.paper_ledger_path(self.hub)
        self.box = mock.MagicMock()
        self.box.askyesno.return_value = True
        self.running = None  # the reason the trader blocks saving, if any

    def open(self, known_coins=("BTC", "ETH")):
        dlg = PaperAccountDialog(
            self.root,
            hub_dir=self.hub,
            trader_running=lambda: self.running,
            known_coins=known_coins,
            messagebox=self.box,
        )
        self.addCleanup(gc.collect)
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        dlg.withdraw()
        return dlg

    def add(self, dlg, symbol, qty, price):
        dlg.symbol_var.set(symbol)
        dlg.qty_var.set(qty)
        dlg.price_var.set(price)
        return dlg.add_position()

    def test_a_new_account_shows_the_defaults(self):
        dlg = self.open()
        self.assertEqual(
            (dlg.initial_var.get(), dlg.cash_var.get()), ("10000", "10000")
        )
        self.assertEqual(dlg.positions, {})
        self.assertIn("No saved paper account yet", dlg.status_var.get())
        self.assertEqual(
            dlg.book_path, os.path.join(self.hub, "paper", "paper_account.json")
        )

    def test_saving_writes_the_book_and_the_ledger_cost_basis(self):
        dlg = self.open()
        dlg.initial_var.set("50")
        dlg.cash_var.set("40")
        self.assertTrue(self.add(dlg, "btc", "0.0001", "60000"))
        self.assertEqual(dlg.tree.get_children(), ("BTC",))
        self.assertTrue(dlg.save())
        self.assertEqual(
            read_json(self.book),
            {
                "initial_balance": "50",
                "cash_balance": "40",
                "positions": {"BTC": {"quantity": "0.0001", "average_price": "60000"}},
            },
        )
        ledger = read_json(self.ledger)
        self.assertEqual(
            ledger["open_positions"], {"BTC": {"usd_cost": 6.0, "qty": 0.0001}}
        )
        self.assertEqual(ledger["total_realized_profit_usd"], 0.0)
        self.box.showinfo.assert_called_once()
        self.assertFalse(dlg.winfo_exists())
        # and it is exactly what the trader will load
        ex = tm.PaperExchange(price_feed=None, state_path=self.book)
        self.assertEqual(ex.account.cash_balance, tm.Decimal("40"))

    def test_saving_is_refused_while_the_trader_runs(self):
        dlg = self.open()
        dlg.cash_var.set("50")
        self.running = "The trader is running."
        self.assertFalse(dlg.save())
        title, message = self.box.showerror.call_args[0]
        self.assertEqual(
            (title, message),
            (paper_account_ui.STOP_THE_TRADER, "The trader is running."),
        )
        self.assertFalse(os.path.exists(self.book))
        self.assertTrue(dlg.winfo_exists())

    def test_invalid_values_are_refused_and_nothing_is_written(self):
        for initial, cash in (("0", "50"), ("50", "-1"), ("fifty", "50")):
            with self.subTest(initial=initial, cash=cash):
                self.box.reset_mock()
                dlg = self.open()
                dlg.initial_var.set(initial)
                dlg.cash_var.set(cash)
                self.assertFalse(dlg.save())
                self.box.showerror.assert_called_once()
                self.assertFalse(os.path.exists(self.book))

    def test_add_position_checks_input_and_updates_an_existing_coin(self):
        dlg = self.open()
        self.assertFalse(self.add(dlg, "USD", "1", "1"))
        self.assertFalse(self.add(dlg, "BTC", "0", "1"))
        self.assertEqual(dlg.positions, {})
        self.assertTrue(self.add(dlg, "ETH", "2", "3000"))
        self.assertTrue(self.add(dlg, "eth", "3", "2500"))
        self.assertEqual(dlg.positions, {"ETH": ("3", "2500")})
        dlg.tree.selection_set("ETH")
        dlg.remove_position()
        self.assertEqual(dlg.positions, {})

    def test_the_saved_book_is_shown(self):
        tm.write_paper_book(
            self.book, tm.validate_paper_book("50", "25", {"ETH": ("0.01", "2500")})
        )
        dlg = self.open()
        self.assertEqual((dlg.initial_var.get(), dlg.cash_var.get()), ("50", "25"))
        self.assertEqual(dlg.positions, {"ETH": ("0.01", "2500")})
        self.assertEqual(dlg.tree.item("ETH")["values"][3], "25.00")
        self.assertIn("saved paper account", dlg.status_var.get())

    def test_an_unreadable_book_is_reported_and_replaced_on_save(self):
        os.makedirs(os.path.dirname(self.book))
        with open(self.book, "w", encoding="utf-8") as f:
            f.write("{ not json")
        dlg = self.open()
        self.assertIn("could not be read", dlg.status_var.get())
        self.assertIn("cannot use it either", dlg.status_var.get())
        self.assertEqual(
            (dlg.initial_var.get(), dlg.cash_var.get()), ("10000", "10000")
        )
        dlg.cash_var.set("50")
        dlg.initial_var.set("50")
        self.assertTrue(dlg.save())
        self.assertEqual(read_json(self.book)["cash_balance"], "50")

    def test_an_invalid_book_shows_what_the_trader_uses_and_is_fixed_on_save(self):
        # the user's own hand edit: the trader loads it as written (cash 50)
        os.makedirs(os.path.dirname(self.book))
        with open(self.book, "w", encoding="utf-8") as f:
            f.write('{"initial_balance": "0", "cash_balance": "50"}')
        dlg = self.open()
        self.assertIn("starting balance must be more than 0", dlg.status_var.get())
        self.assertIn("still loads these values as written", dlg.status_var.get())
        self.assertNotIn("$10,000", dlg.status_var.get())
        # the form shows what the file says (cash 50), so only the bad value changes
        self.assertEqual((dlg.initial_var.get(), dlg.cash_var.get()), ("0", "50"))
        dlg.initial_var.set("50")
        self.assertTrue(dlg.save())
        self.assertEqual(
            read_json(self.book),
            {"initial_balance": "50", "cash_balance": "50", "positions": {}},
        )

    def test_reset_backs_up_the_history_and_starts_profit_from_zero(self):
        tm.write_paper_book(
            self.book, tm.validate_paper_book("50", "10", {"BTC": ("1", "40")})
        )
        write_json(
            self.ledger, {"total_realized_profit_usd": 7.5, "open_positions": {}}
        )
        history = os.path.join(self.hub, "paper", "trade_history.jsonl")
        with open(history, "w", encoding="utf-8") as f:
            f.write('{"side": "buy"}\n')
        dlg = self.open()
        self.assertTrue(dlg.reset())
        self.assertEqual((dlg.cash_var.get(), dlg.positions), ("50", {}))
        self.assertTrue(dlg.save())
        self.assertEqual(
            read_json(self.book),
            {"initial_balance": "50", "cash_balance": "50", "positions": {}},
        )
        self.assertEqual(read_json(self.ledger)["total_realized_profit_usd"], 0.0)
        self.assertFalse(os.path.exists(history))
        backups = sorted(os.listdir(os.path.join(self.hub, "paper")))
        self.assertTrue(any(n.startswith("trade_history.jsonl.bak-") for n in backups))
        self.assertTrue(any(n.startswith("pnl_ledger.json.bak-") for n in backups))

    def test_reset_can_be_cancelled(self):
        dlg = self.open()
        dlg.cash_var.set("5")
        self.box.askyesno.return_value = False
        self.assertFalse(dlg.reset())
        self.assertEqual(dlg.cash_var.get(), "5")

    def test_a_coin_outside_the_coin_list_asks_before_saving(self):
        dlg = self.open(known_coins=("BTC",))
        self.assertTrue(self.add(dlg, "SOL", "1", "100"))
        self.box.askyesno.return_value = False
        self.assertFalse(dlg.save())
        self.assertIn("SOL is not in your coin list", self.box.askyesno.call_args[0][1])
        self.assertFalse(os.path.exists(self.book))

    def test_a_position_typed_but_not_added_is_saved_too(self):
        dlg = self.open()
        dlg.symbol_var.set("BTC")
        dlg.qty_var.set("0.5")
        dlg.price_var.set("60000")
        self.assertTrue(dlg.save())
        self.assertEqual(
            read_json(self.book)["positions"],
            {"BTC": {"quantity": "0.5", "average_price": "60000"}},
        )
        self.assertIn("BTC 0.5 @ $60000", self.box.showinfo.call_args[0][1])

    def test_a_bad_typed_position_stops_the_save(self):
        dlg = self.open()
        dlg.symbol_var.set("BTC")
        dlg.qty_var.set("0,5")  # a decimal comma: refused, never read as 5
        dlg.price_var.set("60000")
        self.assertFalse(dlg.save())
        self.assertIn("use a dot for decimals", self.box.showerror.call_args[0][1])
        self.assertFalse(os.path.exists(self.book))

    def test_remove_acts_on_the_typed_coin_over_the_selection(self):
        dlg = self.open()
        self.add(dlg, "BTC", "1", "100")
        self.add(dlg, "ETH", "2", "50")
        dlg.tree.selection_set("BTC")
        dlg.symbol_var.set("eth")
        dlg.remove_position()
        self.assertEqual(sorted(dlg.positions), ["BTC"])

    def test_a_cash_only_edit_keeps_each_positions_ledger_cost(self):
        tm.write_paper_book(
            self.book, tm.validate_paper_book("100", "50", {"BTC": ("0.5", "100")})
        )
        write_json(
            self.ledger, {"open_positions": {"BTC": {"usd_cost": 50.05, "qty": 0.5}}}
        )
        dlg = self.open()
        dlg.cash_var.set("75")
        self.assertTrue(dlg.save())
        self.assertEqual(
            read_json(self.ledger)["open_positions"]["BTC"]["usd_cost"], 50.05
        )

    def test_odd_keys_in_a_hand_edited_file_do_not_break_the_window(self):
        os.makedirs(os.path.dirname(self.book))
        with open(self.book, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "initial_balance": "0",
                    "cash_balance": "50",
                    "positions": {
                        "btc": {"quantity": "1", "average_price": "1"},
                        "BTC": {"quantity": "2", "average_price": "2"},
                    },
                },
                f,
            )
        dlg = self.open()  # no crash, nothing merged: the defaults are shown
        self.assertEqual(dlg.positions, {})

    def test_the_window_warns_at_once_when_the_trader_runs_or_mode_is_live(self):
        self.running = "The trader is running."
        dlg = self.open()
        self.assertIn("The trader is running.", dlg.status_var.get())
        live = PaperAccountDialog(
            self.root,
            hub_dir=self.hub,
            trader_running=lambda: None,
            messagebox=self.box,
            live=True,
        )
        self.addCleanup(live.destroy)
        self.assertIn("Trading Mode is live", live.status_var.get())

    def test_on_saved_is_called_after_a_save(self):
        saved = mock.Mock()
        dlg = PaperAccountDialog(
            self.root,
            hub_dir=self.hub,
            trader_running=lambda: None,
            messagebox=self.box,
            on_saved=saved,
        )
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        self.assertTrue(dlg.save())
        saved.assert_called_once_with()


class TestHubWiring(unittest.TestCase):
    """The hub's 'trader running' check, asked at the moment of saving."""

    def reason(self, **attrs):
        hub = types.SimpleNamespace(**attrs)
        return pt_hub.PowerTraderHub._paper_trader_running_reason(hub)

    def test_a_running_or_starting_trader_blocks_saving(self):
        with tempfile.TemporaryDirectory() as hub_dir:
            running = types.SimpleNamespace(
                proc=mock.Mock(**{"poll.return_value": None})
            )
            stopped = types.SimpleNamespace(proc=mock.Mock(**{"poll.return_value": 0}))
            self.assertIn(
                "Stop trader", self.reason(proc_trader=running, hub_dir=hub_dir)
            )
            self.assertIsNone(self.reason(proc_trader=stopped, hub_dir=hub_dir))
            self.assertIn(
                "about to start",
                self.reason(
                    proc_trader=stopped,
                    _auto_start_trader_pending=True,
                    hub_dir=hub_dir,
                ),
            )

    def test_a_fresh_status_from_a_trader_started_elsewhere_blocks_saving(self):
        with tempfile.TemporaryDirectory() as hub_dir:
            status = os.path.join(hub_dir, "paper", "trader_status.json")
            never = types.SimpleNamespace(proc=None)
            self.assertIsNone(self.reason(proc_trader=never, hub_dir=hub_dir))
            write_json(status, {"timestamp": time.time()})
            self.assertIn("2 minutes", self.reason(proc_trader=never, hub_dir=hub_dir))
            write_json(status, {"timestamp": time.time() - 600})
            self.assertIsNone(self.reason(proc_trader=never, hub_dir=hub_dir))
            # a trader this hub started and stopped: its own state decides
            stopped = types.SimpleNamespace(proc=mock.Mock(**{"poll.return_value": 0}))
            write_json(status, {"timestamp": time.time()})
            self.assertIsNone(self.reason(proc_trader=stopped, hub_dir=hub_dir))
            # a status file that is valid JSON but not an object does not crash
            write_json(status, [1, 2, 3])
            self.assertIsNone(self.reason(proc_trader=never, hub_dir=hub_dir))


class TestAccountPanelShowsTheBook(unittest.TestCase):
    """After a save, the hub's Account panel shows the saved book until the trader
    reports again (it used to keep the trader's last, stale figures)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.hub_dir = tmp.name
        hub = types.SimpleNamespace(
            hub_dir=self.hub_dir,
            trader_status_path=os.path.join(
                self.hub_dir, "paper", "trader_status.json"
            ),
            trade_history_path=os.path.join(
                self.hub_dir, "paper", "trade_history.jsonl"
            ),
            settings={},
            coins=["BTC"],
            trades_tree=mock.Mock(**{"get_children.return_value": []}),
        )
        for name in (
            "lbl_acct_total_value",
            "lbl_acct_holdings_value",
            "lbl_acct_buying_power",
            "lbl_acct_percent_in_trade",
            "lbl_acct_dca_spread",
            "lbl_acct_dca_single",
        ):
            setattr(hub, name, mock.Mock())
        hub._shown_paper_book_path = (
            lambda: pt_hub.PowerTraderHub._shown_paper_book_path(hub)
        )
        hub._paper_book_status = pt_hub.PowerTraderHub._paper_book_status
        hub._show_profit_figures = (
            lambda data: pt_hub.PowerTraderHub._show_profit_figures(hub, data)
        )
        self.hub = hub

    def refresh(self):
        pt_hub.PowerTraderHub._refresh_trader_status(self.hub)
        return self.hub.lbl_acct_total_value.config.call_args[1]["text"]

    def test_a_newer_book_replaces_the_traders_stale_figures(self):
        write_json(
            self.hub.trader_status_path,
            {
                "timestamp": 1.0,
                "account": {"total_account_value": 10000.0, "buying_power": 10000.0},
            },
        )
        os.utime(self.hub.trader_status_path, (1_000_000, 1_000_000))
        self.assertIn("$10,000.00", self.refresh())
        tm.write_paper_book(
            tm.paper_book_path(self.hub_dir),
            tm.validate_paper_book("50", "40", {"BTC": ("0.0001", "100000")}),
        )
        text = self.refresh()
        self.assertIn("$50.00", text)
        self.assertIn("saved paper account", text)
        buying = self.hub.lbl_acct_buying_power.config.call_args[1]["text"]
        self.assertIn("$40.00", buying)
        # the trader reports again (newer than the book): its figures are shown
        write_json(
            self.hub.trader_status_path,
            {
                "timestamp": 2.0,
                "account": {"total_account_value": 51.0, "buying_power": 41.0},
            },
        )
        book_time = os.path.getmtime(tm.paper_book_path(self.hub_dir))
        os.utime(self.hub.trader_status_path, (book_time + 5, book_time + 5))
        text = self.refresh()
        self.assertIn("$51.00", text)
        self.assertNotIn("saved paper account", text)

    def test_the_book_is_not_shown_for_live_books(self):
        self.hub.trader_status_path = os.path.join(self.hub_dir, "trader_status.json")
        self.assertIsNone(pt_hub.PowerTraderHub._shown_paper_book_path(self.hub))


@pytest.fixture
def root_hub(monkeypatch):
    import helpers_trainer as ht

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    yield hub
    ht.close_hub(hub)


def test_settings_has_a_paper_account_button_that_opens_the_window(
    root_hub, monkeypatch
):
    from test_trainer_launch import open_settings, press, widgets

    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    hub = root_hub
    win = open_settings(hub)
    labels = [str(w.cget("text")) for w in widgets(win) if isinstance(w, ttk.Button)]
    assert "Paper Account..." in labels

    press(win, "Paper Account...")
    (dlg,) = [w for w in win.winfo_children() if isinstance(w, PaperAccountDialog)]
    assert dlg.book_path == os.path.join(hub.hub_dir, "paper", "paper_account.json")
    assert dlg.title() == "Paper Account"
    dlg.destroy()
    win.destroy()


from helpers import PaperTraderCase  # noqa: E402


class TestTraderUsesTheSavedBook(PaperTraderCase):
    """Through the real trader start-up (pt_trader.CryptoAPITrading)."""

    def test_a_fresh_trader_saves_its_book_at_start_up(self):
        self.trader()
        book = os.path.join(self.tmp.name, "paper", "paper_account.json")
        self.assertEqual(
            read_json(book),
            {"initial_balance": "10000", "cash_balance": "10000", "positions": {}},
        )
        self.assertEqual(book, tm.paper_book_path(self.tmp.name))

    def test_a_trader_starts_from_the_book_and_cost_basis_the_window_saved(self):
        book = tm.validate_paper_book("50", "40", {"BTC": ("0.0001", "60000")})
        tm.write_paper_book(tm.paper_book_path(self.tmp.name), book)
        tm.write_paper_ledger_positions(tm.paper_ledger_path(self.tmp.name), book)
        trader = self.trader()
        balance = tm.get_paper_exchange().get_balance()
        self.assertEqual((balance["USD"], balance["BTC"]), (40.0, 0.0001))
        self.assertAlmostEqual(trader.cost_basis["BTC"], 60000.0)
        self.assertEqual(trader.get_account(), {"buying_power": 40.0})
