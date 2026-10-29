"""Settings > Check Exchanges: the checks (exchange_check), the window
(exchange_check_gui) and the Settings button.

No network: the connectors are fakes. Everything runs under the isolation guard.
"""

import gc
import json
import os
import sys
import time
import tkinter as tk
from tkinter import ttk

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(__file__))

import exchange_check  # noqa: E402
import pt_hub  # noqa: E402
from exchange_check import NO_CONNECTOR, Result  # noqa: E402
from exchange_check_gui import ExchangeCheckWindow  # noqa: E402
from pt_exchange_abstraction import MarketStatus, PriceQuote  # noqa: E402
from pt_multi_exchange import ExchangeConfigManager  # noqa: E402

HOUR_MS = 3_600_000


class FakeExchange:
    """BTC and ETH listed, a fresh quote, a full day of hourly candles."""

    def __init__(self, listed=("BTC", "ETH"), fail_quote=()):
        self.listed = set(listed)
        self.fail_quote = set(fail_quote)

    def candle_timeframes(self):
        return ["1h"]

    def market_status(self, symbol):
        coin = symbol.split("-")[0]
        if coin not in self.listed:
            return MarketStatus(False, None, "", "no market")
        return MarketStatus(True, True, "online", "online")

    def quote(self, symbol):
        if symbol.split("-")[0] in self.fail_quote:
            raise ConnectionError("reset by peer")
        return PriceQuote(99.0, 100.0, time.time() - 0.5)

    def candles(self, symbol, tf, start, end):
        rows, t = [], start
        while t <= end:
            rows.append([t, 10.0, 12.0, 9.0, 11.0, 1.0])
            t += HOUR_MS
        return rows

    def min_order_usd(self, symbol):
        return 1.0


@pytest.fixture
def fakes(monkeypatch):
    made = {}

    def connector(name):
        made[name] = made.get(name) or FakeExchange()
        return made[name]

    monkeypatch.setattr(exchange_check, "connector", connector)
    return made


# --- the checks ----------------------------------------------------------------------------


def test_every_check_is_reported_as_it_arrives_in_exchange_order(fakes):
    seen = []
    results = exchange_check.check(["kraken", "coinbase"], ["BTC"], report=seen.append)
    assert seen == results
    assert [(r.exchange, r.check, r.ok) for r in results] == [
        ("kraken", "BTC status", True),
        ("kraken", "BTC quote", True),
        ("kraken", "candles", True),
        ("kraken", "min order", True),
        ("coinbase", "BTC status", True),
        ("coinbase", "BTC quote", True),
        ("coinbase", "candles", True),
        ("coinbase", "min order", True),
    ]


def test_an_unlisted_coin_does_not_apply_and_a_failing_quote_fails_that_coin_only(
    fakes,
):
    fakes["kraken"] = FakeExchange(listed=("BTC", "ETH"), fail_quote=("ETH",))
    results = exchange_check.check(["kraken"], ["DASH", "ETH", "BTC"])
    by_check = {r.check: r for r in results}
    assert by_check["DASH status"].ok is None
    assert by_check["ETH quote"].ok is False
    assert "reset by peer" in by_check["ETH quote"].detail
    assert by_check["BTC quote"].ok is True  # the next coin is still checked


def test_an_exchange_without_a_connector_or_unknown_name_fails_without_a_request(
    fakes,
):
    results = exchange_check.check(["bitstamp", "nosuch"], ["BTC"])
    assert [(r.exchange, r.ok, r.detail) for r in results] == [
        ("bitstamp", False, NO_CONNECTOR),
        ("nosuch", False, "not an exchange"),
    ]
    assert fakes == {}


def test_stopping_ends_the_run_before_the_next_exchange(fakes):
    asked = []

    def stopped():
        asked.append(1)
        return len(asked) > 1

    results = exchange_check.check(["kraken", "coinbase"], ["BTC"], stopped=stopped)
    assert {r.exchange for r in results} == {"kraken"}


def test_the_key_check_runs_only_when_asked(fakes, monkeypatch):
    monkeypatch.setattr(
        exchange_check, "check_api_key", lambda name: Result(name, "API key", True, "")
    )
    assert "API key" not in [r.check for r in exchange_check.check(["kraken"], [])]
    assert "API key" in [
        r.check for r in exchange_check.check(["kraken"], [], auth=True)
    ]


def _config(tmp_path, primary, enabled):
    folder = tmp_path / "config"
    folder.mkdir()
    exchanges = [
        {"exchange_type": name, "enabled": name in enabled, "region_preference": i + 1}
        for i, name in enumerate(["binance", "kraken", "kucoin", "coinbase"])
    ]
    data = {
        "user_region": "GLOBAL",
        "primary_exchange": primary,
        "exchanges": exchanges,
    }
    (folder / "trading_config.json").write_text(json.dumps(data), encoding="utf-8")
    return ExchangeConfigManager(str(folder))


def test_the_enabled_exchanges_come_primary_first_then_in_settings_order(tmp_path):
    manager = _config(tmp_path, "coinbase", {"kraken", "kucoin", "coinbase"})
    assert exchange_check.enabled_exchanges(manager) == (
        ["coinbase", "kraken", "kucoin"],
        "coinbase",
    )


def test_the_primary_is_listed_first_even_when_its_entry_is_disabled(tmp_path):
    # the exchange layer always connects the primary, so it is checked too
    manager = _config(tmp_path, "binance", {"kraken"})
    assert exchange_check.enabled_exchanges(manager) == (
        ["binance", "kraken"],
        "binance",
    )


# --- the window ------------------------------------------------------------------------------


@pytest.fixture
def root():
    gc.collect()  # leftover Tk variables die on the main thread
    try:
        r = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    r.withdraw()
    yield r
    r.destroy()


class FakeRunner:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def __call__(self, names, coins, auth=False, report=None, stopped=None):
        self.calls.append((list(names), list(coins), auth))
        for r in self.results:
            report(r)
        return self.results


def run_to_end(win):
    win.run()
    win._worker.join(5)
    assert win.drain() is True


def test_the_window_lists_the_choices_and_labels_the_primary(root):
    win = ExchangeCheckWindow(
        root, ["coinbase", "kraken"], ["BTC", "ETH"], primary="coinbase"
    )
    texts = [
        str(w.cget("text"))
        for frame in win.winfo_children()[0].winfo_children()
        for w in frame.winfo_children()
        if isinstance(w, ttk.Checkbutton)
    ]
    assert texts[:4] == ["coinbase (primary)", "kraken", "BTC", "ETH"]
    assert win.title() == "Check Exchanges"
    win.destroy()


def test_a_run_checks_only_the_ticked_choices_and_shows_every_result(root):
    runner = FakeRunner(
        [
            Result("coinbase", "BTC quote", True, "bid 1 ask 2, 0.3 s old"),
            Result("coinbase", "DASH status", None, "not listed (no market)"),
            Result("coinbase", "candles", False, "3 of 24 bars"),
        ]
    )
    win = ExchangeCheckWindow(
        root, ["coinbase", "kraken"], ["BTC", "DASH"], primary="coinbase", runner=runner
    )
    win.exchange_vars["kraken"].set(False)
    win.auth_var.set(True)
    run_to_end(win)
    assert runner.calls == [(["coinbase"], ["BTC", "DASH"], True)]
    rows = [win.tree.item(i, "values") for i in win.tree.get_children()]
    assert [row[2] for row in rows] == ["PASS", "n/a", "FAIL"]
    assert win.status_var.get() == "1 passed, 1 failed, 1 not applicable"
    assert str(win.run_button.cget("state")) == "normal"
    win.destroy()


def test_a_run_with_no_exchange_ticked_asks_for_one(root):
    runner = FakeRunner([])
    win = ExchangeCheckWindow(root, ["kraken"], ["BTC"], runner=runner)
    win.exchange_vars["kraken"].set(False)
    win.run()
    assert runner.calls == []
    assert win.status_var.get() == "Choose at least one exchange."
    win.destroy()


def test_an_error_in_the_run_is_shown_not_lost(root):
    def broken(*args, **kwargs):
        raise RuntimeError("no network")

    win = ExchangeCheckWindow(root, ["kraken"], ["BTC"], runner=broken)
    run_to_end(win)
    assert [r.detail for r in win.results] == ["stopped: no network"]
    assert win.status_var.get() == "0 passed, 1 failed"
    win.destroy()


# --- the Settings button ---------------------------------------------------------------------


@pytest.fixture
def root_hub(monkeypatch):
    import helpers_trainer as ht

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    yield hub
    ht.close_hub(hub)


def test_settings_has_a_check_exchanges_button_that_opens_the_window(
    root_hub, monkeypatch
):
    from test_trainer_launch import open_settings, press, widgets

    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    monkeypatch.setattr(
        exchange_check, "enabled_exchanges", lambda: (["kucoin", "kraken"], "kucoin")
    )
    hub = root_hub
    win = open_settings(hub)
    labels = [str(w.cget("text")) for w in widgets(win) if isinstance(w, ttk.Button)]
    assert "Check Exchanges..." in labels

    press(win, "Check Exchanges...")
    (dlg,) = [w for w in win.winfo_children() if isinstance(w, ExchangeCheckWindow)]
    assert list(dlg.exchange_vars) == ["kucoin", "kraken"]
    assert list(dlg.coin_vars) == [str(c).upper() for c in hub.coins]
    assert hub.open_exchange_check(win) is dlg  # a second press raises the same window
    dlg.destroy()
    win.destroy()
