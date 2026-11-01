"""Settings > Paper trading: which coins paper trading opens new trades in.

The owner's choice (2026-10-31): either inherit the coins from the main settings (the
default) or override them with a chosen set, and never a BTC-only default. Before
this, the strategy traded ``strategy.symbols``, which had no Settings control and
defaulted to BTC, so a nine-coin hub paper-traded BTC alone.

No network: candles come from a scripted feed and quotes from fakes.
"""

import copy
import json
import os
import sys
import types
from tkinter import ttk
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(__file__))

import paper_coins  # noqa: E402
import pt_paths  # noqa: E402
import trading_mode as tm  # noqa: E402
from helpers import Feed, PaperTraderCase, make_candles  # noqa: E402
from pt_validation import InputValidator  # noqa: E402
from signal_engine import SignalEngine  # noqa: E402
from test_signal_engine import PAPER, expected_actions, trend_series  # noqa: E402

# -- the rule -----------------------------------------------------------------------


def test_paper_trading_inherits_the_coins_in_settings_by_default():
    assert paper_coins.entry_coins({}, ["btc", "ETH ", "SOL"]) == ["BTC", "ETH", "SOL"]
    assert paper_coins.entry_coins(None, ["BTC", "ETH"]) == ["BTC", "ETH"]
    # a chosen list is kept for later but not used while inheriting
    saved = {"paper_coins_mode": "inherit", "paper_coins": ["ETH"]}
    assert paper_coins.entry_coins(saved, ["BTC", "ETH"]) == ["BTC", "ETH"]


def test_an_override_trades_the_chosen_coins_in_settings_order():
    saved = {"paper_coins_mode": "override", "paper_coins": ["sol", "BTC", "DOGE"]}
    # DOGE is not in Settings: the trader has no prices for it
    assert paper_coins.entry_coins(saved, ["BTC", "ETH", "SOL"]) == ["BTC", "SOL"]


def test_an_unknown_choice_inherits_and_a_bad_list_chooses_nothing():
    assert paper_coins.mode({"paper_coins_mode": "magic"}) == paper_coins.INHERIT
    assert paper_coins.chosen({"paper_coins": "BTC"}) == []
    saved = {"paper_coins_mode": "OVERRIDE", "paper_coins": None}
    assert paper_coins.entry_coins(saved, ["BTC"]) == []


def test_the_trader_reads_both_keys_from_the_settings_file():
    validated = InputValidator.validate_config_data(
        {
            "coins": ["BTC", "ETH"],
            "paper_coins_mode": "Override",
            "paper_coins": ["eth", "not a coin!", 5],
        }
    )
    assert validated["paper_coins_mode"] == "override"
    assert validated["paper_coins"] == ["ETH"]
    assert (
        InputValidator.validate_config_data({"paper_coins_mode": "x"})[
            "paper_coins_mode"
        ]
        == "inherit"
    )


# -- the trader ---------------------------------------------------------------------


class PaperCoinTraderTests(PaperTraderCase):
    def setUp(self):
        super().setUp()
        self.frame = make_candles(trend_series())
        self.feed = Feed(self.frame)
        self.gui = {}
        for patch in (
            mock.patch.object(self.pt_trader.time, "sleep"),
            mock.patch.object(self.pt_trader, "crypto_symbols", ["BTC", "ETH"]),
            mock.patch.object(
                self.pt_trader, "_load_gui_settings", lambda: dict(self.gui)
            ),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def trader(self):
        settings = copy.deepcopy(PAPER)
        engine = SignalEngine(settings, self.feed.provider, self.feed.clock)
        self.feed.set_after_bar(150)
        t = self.pt_trader.CryptoAPITrading(
            settings_source=settings, signal_engine=engine
        )
        t._order_poll_seconds = 0.0
        return t

    def orders(self):
        return [
            (o.symbol, o.side.value)
            for o in tm.get_paper_exchange().account.orders.values()
        ]

    def run_bars(self, trader, bars):
        for k in bars:
            self.feed.set_after_bar(k)
            trader.manage_trades()

    def test_every_coin_in_settings_is_traded_when_inheriting(self):
        (enter_bar, _), (exit_bar, _) = expected_actions(self.frame)
        trader = self.trader()
        self.run_bars(trader, range(150, exit_bar + 1))
        self.assertEqual(
            sorted(self.orders()),
            [("BTC", "buy"), ("BTC", "sell"), ("ETH", "buy"), ("ETH", "sell")],
        )

    def test_an_override_opens_trades_only_in_the_chosen_coins(self):
        self.gui = {"paper_coins_mode": "override", "paper_coins": ["ETH"]}
        (enter_bar, _), (exit_bar, _) = expected_actions(self.frame)
        trader = self.trader()
        self.run_bars(trader, range(150, exit_bar + 1))
        self.assertEqual(self.orders(), [("ETH", "buy"), ("ETH", "sell")])

    def test_a_coin_taken_off_the_list_is_still_sold_by_its_exit(self):
        (enter_bar, _), (exit_bar, _) = expected_actions(self.frame)
        trader = self.trader()
        self.run_bars(trader, range(150, enter_bar + 1))
        self.assertEqual(sorted(self.orders()), [("BTC", "buy"), ("ETH", "buy")])
        self.gui = {"paper_coins_mode": "override", "paper_coins": ["ETH"]}
        self.run_bars(trader, range(enter_bar + 1, exit_bar + 1))
        self.assertIn(("BTC", "sell"), self.orders())
        self.assertIn(("ETH", "sell"), self.orders())

    def test_live_trading_uses_the_coins_in_settings(self):
        self.gui = {"paper_coins_mode": "override", "paper_coins": ["ETH"]}
        trader = self.trader()
        self.assertEqual(trader._entry_coins(), ["ETH"])
        trader._settings = types.SimpleNamespace(is_live=True)
        self.assertEqual(trader._entry_coins(), ["BTC", "ETH"])


# -- the Settings window ------------------------------------------------------------


@pytest.fixture
def root_hub(monkeypatch):
    import helpers_trainer as ht

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    yield hub
    ht.close_hub(hub)


def _widgets(win, kind, text=None):
    from test_trainer_launch import widgets

    return [
        w
        for w in widgets(win)
        if isinstance(w, kind) and (text is None or str(w.cget("text")) == text)
    ]


def _coin_boxes(win):
    """The paper-trading coin tick boxes, by coin."""
    (override,) = _widgets(win, ttk.Radiobutton, "Override paper-trading coins:")
    frame = override.master
    return {
        str(w.cget("text")): w
        for w in _widgets(frame, ttk.Checkbutton)
        if str(w.cget("text")).isalnum()
    }


def _saved_file():
    with open(pt_paths.gui_settings_file(), encoding="utf-8") as f:
        return json.load(f)


def test_the_settings_window_inherits_by_default_and_saves_an_override(root_hub):
    from test_trainer_launch import open_settings, press

    hub = root_hub
    hub.settings["coins"] = ["BTC", "ETH", "SOL"]
    win = open_settings(hub)
    (inherit,) = _widgets(win, ttk.Radiobutton, "Inherit coins from main settings")
    (override,) = _widgets(win, ttk.Radiobutton, "Override paper-trading coins:")
    boxes = _coin_boxes(win)
    assert list(boxes) == ["BTC", "ETH", "SOL"]
    # inheriting: every coin is ticked and none can be changed
    assert all(b.instate(["selected", "disabled"]) for b in boxes.values())

    override.invoke()
    boxes = _coin_boxes(win)
    assert not any(b.instate(["disabled"]) for b in boxes.values())
    boxes["ETH"].invoke()  # untick ETH
    press(win, "Save")

    assert hub.settings["paper_coins_mode"] == "override"
    assert hub.settings["paper_coins"] == ["BTC", "SOL"]
    saved = _saved_file()
    assert (saved["paper_coins_mode"], saved["paper_coins"]) == (
        "override",
        ["BTC", "SOL"],
    )
    assert paper_coins.entry_coins(saved, saved["coins"]) == ["BTC", "SOL"]


def test_an_override_with_no_coin_ticked_is_refused_and_changes_nothing(root_hub):
    from test_trainer_launch import open_settings, press

    hub = root_hub
    hub.settings["coins"] = ["BTC", "ETH"]
    before = copy.deepcopy(hub.settings)
    win = open_settings(hub)
    _widgets(win, ttk.Radiobutton, "Override paper-trading coins:")[0].invoke()
    for box in _coin_boxes(win).values():
        box.invoke()  # untick every coin
    press(win, "Save")
    assert ("showerror", ("Paper trading",)) == (
        hub.test_dialogs[-1][0],
        hub.test_dialogs[-1][1][:1],
    )
    assert hub.settings == before
    assert win.winfo_exists()  # the window stays open to fix it


def test_a_coin_typed_into_the_coins_field_gets_a_tick_box(root_hub):
    from test_trainer_launch import open_settings, type_into

    hub = root_hub
    hub.settings["coins"] = ["BTC"]
    hub.settings["paper_coins_mode"] = "override"
    hub.settings["paper_coins"] = ["BTC"]
    win = open_settings(hub)
    type_into(win, "Coins (comma):", "BTC,ETH")
    boxes = _coin_boxes(win)
    assert list(boxes) == ["BTC", "ETH"]
    # a saved override keeps its choice: a new coin starts unticked
    assert boxes["BTC"].instate(["selected"])
    assert not boxes["ETH"].instate(["selected"])
