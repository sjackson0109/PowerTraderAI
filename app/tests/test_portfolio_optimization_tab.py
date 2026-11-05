"""Portfolio Analytics and Portfolio Optimization (owner, 2026-11-05).

* Portfolio Analytics is gone: no tab, no entry in the tab order, its two modules in
  archive/legacy/.
* Portfolio Optimization runs on the coins in Settings with no file and nothing
  typed: their daily closes come from the candle cache (the exchanges in Settings,
  primary first) over a window; a price file (CSV) stays an optional source, and the
  sample data and the typed returns are gone. The current portfolio is Long-term
  Holdings', as its tag filter keeps it.

Real Tk widgets and a real hub, under the isolation guard (app/conftest.py); the
exchanges are fakes behind a real ExchangeManager, so no request is sent; every
holdings.db is a temporary one. Jobs run off the Tk thread, and every test waits
for its own: none is left running.
"""

import gc
import os
import sys
import threading
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_DIR = os.path.dirname(APP_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import long_term_holdings as lth  # noqa: E402
import long_term_holdings_gui as ltg  # noqa: E402
import portfolio_optimizer as po  # noqa: E402
import portfolio_optimizer_gui as pog  # noqa: E402
import ui_table  # noqa: E402

DAY_MS = 86_400_000
COINS = ("BTC", "ETH", "SOL", "XRP")


# ---- daily candles: synthetic, correlated, ending at the last closed day ----


def today():
    return pd.Timestamp.now(tz="UTC").floor("D")


def daily_frames(coins=COINS, days=800, seed=7, end=None):
    """{coin: candle frame} of ``days`` daily bars ending the day before ``end``
    (default: today, UTC): correlated random walks (a common factor plus each
    coin's own moves), each coin with its own drift and volatility."""
    end = today() if end is None else end
    rng = np.random.default_rng(seed)
    common = rng.normal(0.0, 0.025, days)
    frames = {}
    for i, coin in enumerate(coins):
        own = rng.normal(0.0004 * (i + 1), 0.01 + 0.01 * i, days)
        closes = 100.0 * (i + 1) * np.cumprod(1.0 + 0.8 * common + own)
        opens = np.concatenate([[closes[0]], closes[:-1]])
        frames[coin] = pd.DataFrame(
            {
                "open_time": pd.date_range(
                    end=end - pd.Timedelta(days=1), periods=days, freq="D"
                ),
                "open": opens,
                "high": np.maximum(opens, closes) * 1.01,
                "low": np.minimum(opens, closes) * 0.99,
                "close": closes,
                "volume": 1.0,
            }
        )
    return frames


def fake_candles(frames, exchange="coinbase", missing=()):
    """Stands in for exchange_candles: the bars of ``frames`` with start <=
    open_time < end; a coin in ``missing`` (or not in ``frames``) has no market."""
    from pt_exchange_abstraction import MarketNotFound

    asked = []

    def candles(coin, tf, start, end, closed_only=True):
        asked.append((coin, tf))
        assert tf == "1d" and closed_only
        if coin in missing or coin not in frames:
            raise MarketNotFound(f"no market for {coin}")
        df = frames[coin]
        df = df[(df["open_time"] >= start) & (df["open_time"] < end)].reset_index(
            drop=True
        )
        df.attrs["exchange"] = exchange
        return df

    candles.asked = asked
    return candles


def loader(frames, **kw):
    """load_candle_data reading ``frames`` (fake_candles)."""
    candles = fake_candles(frames, **kw)

    def load(coins, days, **options):
        return po.load_candle_data(coins, days, candles=candles, **options)

    load.candles = candles
    return load


class DailyExchange:
    """A connector serving the daily bars of ``frames`` (its own symbols
    ``<COIN>-USD``); a coin not in them has no market."""

    def __init__(self, frames):
        self.frames = frames

    def market_symbol(self, symbol):
        return f"{str(symbol).split('-')[0].upper()}-USD"

    def candle_timeframes(self):
        return frozenset({"1h", "1d"})

    def max_history_bars(self, tf):
        return None

    def candles(self, symbol, tf, start_ms, end_ms):
        from pt_exchange_abstraction import MarketNotFound

        coin = str(symbol).split("-")[0].upper()
        if coin not in self.frames:
            raise MarketNotFound(f"no market for {symbol}")
        df = self.frames[coin]
        epoch = pd.Timestamp("1970-01-01", tz="UTC")
        ms = (df["open_time"] - epoch) // pd.Timedelta(milliseconds=1)
        keep = (ms >= start_ms) & (ms <= end_ms)
        return [
            [int(t), float(o), float(h), float(lo), float(c), float(v)]
            for t, o, h, lo, c, v in zip(
                ms[keep],
                df["open"][keep],
                df["high"][keep],
                df["low"][keep],
                df["close"][keep],
                df["volume"][keep],
            )
        ]


# ---- Tk ----


@pytest.fixture
def layout_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_table, "LAYOUT_PATH", str(tmp_path / "table_layout.json"))
    ui_table.forget_layouts()
    yield
    ui_table.forget_layouts()


@pytest.fixture
def root(layout_file):
    import tkinter as tk
    from tkinter import ttk

    import ui_theme
    import ui_tokens

    win, error = None, None
    for _ in range(10):  # Tk sometimes fails to read init.tcl on the first try
        try:
            win = tk.Tk()
            break
        except tk.TclError as exc:
            error = exc
    if win is None:
        pytest.skip(f"Tk not available: {error}")
    win.attributes("-alpha", 0.0)
    win.geometry("1200x700+0+0")
    ui_theme.apply_theme(win, ttk.Style(win), ui_tokens.DARK)
    yield win
    try:
        win.destroy()
    except tk.TclError:
        pass
    # free this test's Tk objects here, on the Tk thread: collected later in a job's
    # thread, they would leak their interpreter
    gc.collect()
    assert not optimizer_threads(), "a job was left running"


@pytest.fixture
def manager(tmp_path):
    """A HoldingsManager on its own temporary holdings.db."""
    return lth.HoldingsManager(str(tmp_path / "holdings.db"))


@pytest.fixture
def dialogs(monkeypatch):
    """The message boxes of both windows, recorded; askyesno answers
    ``dialogs.answer``; a file dialog fails the test."""
    seen = SimpleNamespace(calls=[], answer=True)

    def record(name):
        def box(title, message, **kw):
            seen.calls.append((name, title, message))
            return seen.answer if name == "askyesno" else "ok"

        return box

    for module in (ltg, pog):
        for name in ("showerror", "showinfo", "showwarning", "askyesno"):
            monkeypatch.setattr(module.messagebox, name, record(name))

    def no_file(*a, **k):
        raise AssertionError("a file dialog was opened")

    monkeypatch.setattr(pog.filedialog, "askopenfilename", no_file)
    return seen


def optimizer_threads():
    return [
        t
        for t in threading.enumerate()
        if t.name.startswith("Portfolio Optimization") and t.is_alive()
    ]


def holding(symbol, qty, cost, price, **kw):
    return lth.Holding(
        symbol=symbol, quantity=qty, average_cost=cost, current_price=price, **kw
    )


def holdings_gui(win, manager):
    from tkinter import ttk

    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True)
    return ltg.HoldingsManagementGUI(frame, coins=lambda: list(COINS), manager=manager)


def optimizer_gui(win, frames=None, coins=COINS, holdings=None, **kw):
    from tkinter import ttk

    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True)
    g = pog.PortfolioOptimizerGUI(
        frame,
        coins=lambda: list(coins),
        holdings=holdings,
        load_candles=loader(daily_frames() if frames is None else frames, **kw),
    )
    win.update()
    return g


def rows(tree, column=None):
    values = [
        tuple(str(v) for v in tree.item(i, "values")) for i in tree.get_children()
    ]
    if column is None:
        return values
    return [v[column] for v in values]


def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)


def texts(widget):
    """The text of every label and button under ``widget``."""
    out = []
    for w in walk(widget):
        try:
            out.append(str(w.cget("text")))
        except Exception:
            pass
    return out


# ---- acceptance: no Portfolio Analytics tab remains ----


def test_no_portfolio_analytics_tab_remains(monkeypatch):
    import helpers_trainer as ht

    import pt_hub

    hub = ht.build_real_hub(monkeypatch)
    try:
        nb = hub.bottom_notebook
        names = [pt_hub.module_tab_name(nb.tab(t, "text")) for t in nb.tabs()]
        assert "Portfolio Optimization" in names
        assert not [n for n in names if "Analytics" in n]
    finally:
        ht.close_hub(hub)
    assert "Portfolio Analytics" not in pt_hub.MODULE_TAB_ORDER
    assert not hasattr(pt_hub, "PORTFOLIO_ANALYTICS_AVAILABLE")
    assert not hasattr(pt_hub.PowerTraderHub, "_create_portfolio_analytics_tab")
    # the modules: in archive/legacy/, no longer in app/
    for name in ("portfolio_analytics.py", "portfolio_analytics_gui.py"):
        assert not os.path.exists(os.path.join(APP_DIR, name))
        assert os.path.isfile(os.path.join(REPO_DIR, "archive", "legacy", name))


# ---- the data: daily candles of the coins in Settings ----


def test_the_closes_come_from_the_candle_cache_primary_exchange_first(monkeypatch):
    """Through the real exchange_candles: BTC from the primary, ETH (which the
    primary does not list) from the next exchange, DOGE from none; every series is
    cached per exchange."""
    from market_data import candles
    from pt_exchange_abstraction import ExchangeManager, ExchangeType

    frames = daily_frames(("BTC", "ETH"), days=400)
    manager = ExchangeManager()
    manager.exchanges[ExchangeType("coinbase")] = DailyExchange({"BTC": frames["BTC"]})
    manager.exchanges[ExchangeType("kraken")] = DailyExchange(frames)
    manager.primary_exchange = ExchangeType("coinbase")
    monkeypatch.setattr(candles, "_exchange_manager", lambda: manager)

    data = po.load_candle_data(["BTC", "ETH", "DOGE"], 365)
    assert data.source == po.SOURCE_CANDLES and data.window_days == 365
    assert data.coins == ["BTC", "ETH"]
    assert data.exchanges == {"BTC": "coinbase", "ETH": "kraken"}
    assert data.left_out == {"DOGE": "no exchange in Settings has a market for it"}
    # the window's closed daily bars, to yesterday, on the same days for both
    assert len(data.prices) == 365 and data.bars == {"BTC": 365, "ETH": 365}
    assert data.last_day == today() - pd.Timedelta(days=1)
    assert not data.prices.isna().any().any()
    # the candle cache, one folder per exchange
    for exchange, pair in (("coinbase", "BTC-USD"), ("kraken", "ETH-USD")):
        assert os.path.isfile(candles.cache_path(pair, "1d", exchange=exchange))


def test_returns_line_up_by_day_and_are_annualised_over_365_days():
    frames = daily_frames(("BTC", "ETH"), days=200)
    frames["ETH"] = frames["ETH"].drop(index=[50, 51]).reset_index(drop=True)
    data = po.load_candle_data(["BTC", "ETH"], 365, candles=fake_candles(frames))
    # ETH has no close on two days: both coins lose them, so each row of returns is
    # the two coins' moves on that same day
    assert len(data.prices) == 198 and data.bars == {"BTC": 200, "ETH": 198}
    daily = data.prices.pct_change().iloc[1:]
    pd.testing.assert_frame_equal(data.returns, daily)
    assert po.DAYS_PER_YEAR == 365
    np.testing.assert_allclose(data.expected_returns(), daily.mean() * 365)
    np.testing.assert_allclose(data.covariance(), daily.cov() * 365)
    np.testing.assert_allclose(data.volatilities(), daily.std() * np.sqrt(365))


def test_a_coin_listed_late_is_left_out_rather_than_shorten_the_others():
    frames = daily_frames(("BTC", "ETH", "NEW"), days=400)
    frames["NEW"] = frames["NEW"].iloc[-100:].reset_index(drop=True)
    data = po.load_candle_data(["BTC", "ETH", "NEW"], 365, candles=fake_candles(frames))
    assert data.coins == ["BTC", "ETH"] and len(data.prices) == 365
    assert data.left_out == {"NEW": "closes on 100 of the 365 days"}


def test_the_windows_are_90_days_1_year_and_3_years():
    assert [label for label, _days in po.WINDOWS] == ["90 days", "1 year", "3 years"]
    assert po.window_days("3 years") == 1095 and po.DEFAULT_WINDOW == "1 year"


# ---- acceptance: optimization runs on the global coins, no file or typing ----


def test_optimization_runs_on_the_settings_coins_with_no_file_or_typed_input(
    root, dialogs
):
    g = optimizer_gui(root)
    # nothing to type returns into, no sample data
    shown = texts(g.main_frame)
    for gone in ("Load Sample", "Add Asset", "Remove", "Expected Return (%):"):
        assert gone not in shown
    for name in ("load_sample_data", "add_asset", "update_manual_data"):
        assert not hasattr(g, name)
    assert g.source_var.get() == po.SOURCE_CANDLES
    assert g.window_var.get() == "1 year"

    assert g.optimize_portfolio()  # loads the data first
    g.wait()
    assert not [c for c in dialogs.calls if c[0] == "showerror"]
    data = g.market_data
    assert data.coins == list(COINS) and len(data.prices) == 365
    result = g.optimization_result
    assert result["success"] and set(result["weights"]) == set(COINS)
    assert sum(result["weights"].values()) == pytest.approx(1.0)
    assert all(0.01 - 1e-6 <= w <= 0.40 + 1e-6 for w in result["weights"].values())
    assert g.frontier_data is not None and len(g.frontier_data) > 5
    # the Data table: each coin's days and annual figures
    table = {r[0]: r for r in rows(g.data_tree)}
    assert set(table) == set(COINS)
    assert table["BTC"][1] == "365"
    assert table["BTC"][3] == f"{data.expected_returns()['BTC'] * 100:.2f}%"
    # the Optimization table: the optimised weights
    assert {r[0]: r[2] for r in rows(g.results_tree)} == {
        c: f"{w * 100:.2f}%" for c, w in result["weights"].items()
    }
    assert g.metric_labels[("optimised", "volatility")].cget("text") == (
        f"{result['volatility'] * 100:.2f}%"
    )
    assert "4 coins, 365 days of daily candles" in g.status_label.cget("text")


def test_the_data_is_loaded_again_when_the_window_or_the_coins_change(root, dialogs):
    coins = ["BTC", "ETH"]
    g = optimizer_gui(root)
    g._coins = lambda: list(coins)
    asked = g._load_candles.candles.asked
    g.optimize_portfolio()
    g.wait()
    g.optimize_portfolio()  # the same request: the data loaded is used
    g.wait()
    assert [c for c, _tf in asked] == ["BTC", "ETH"]
    g.window_var.set("90 days")
    g.optimize_portfolio()
    g.wait()
    assert len(g.market_data.prices) == 90
    coins.append("SOL")
    g.optimize_portfolio()
    g.wait()
    assert g.market_data.coins == ["BTC", "ETH", "SOL"]
    assert len(asked) == 7


def test_coins_with_no_market_are_left_out_and_named(root, dialogs):
    g = optimizer_gui(root, missing=("XRP",))
    g.load_data()
    g.wait()
    assert g.market_data.coins == ["BTC", "ETH", "SOL"]
    assert g.left_out_label.cget("text") == (
        "Left out: XRP (no exchange in Settings has a market for it)"
    )


def test_one_coin_is_not_enough_to_optimise(root, dialogs):
    g = optimizer_gui(root, coins=("BTC",))
    g.optimize_portfolio()
    g.wait()
    assert g.optimization_result is None
    assert dialogs.calls[-1] == (
        "showerror",
        "Portfolio Optimization",
        "Optimization needs daily closes for at least two coins.",
    )


def test_weight_limits_no_portfolio_can_keep_to_are_refused(root, dialogs):
    g = optimizer_gui(root, coins=("BTC", "ETH"))
    g.optimize_portfolio()  # at most 40% each of two coins
    g.wait()
    assert g.optimization_result is None
    assert dialogs.calls[-1][2] == (
        "With 2 coins the max weight per coin must be at least 50.0%."
    )
    g.max_weight_var.set("70")
    g.optimize_portfolio()
    g.wait()
    assert g.optimization_result["success"]


def test_a_price_file_stays_an_optional_source(root, dialogs, tmp_path):
    frames = daily_frames(("BTC", "ETH", "SOL"), days=120)
    prices = pd.DataFrame(
        {c: f["close"].values for c, f in frames.items()},
        index=frames["BTC"]["open_time"].dt.tz_localize(None),
    )
    path = tmp_path / "prices.csv"
    prices.to_csv(path)
    g = optimizer_gui(root, frames={})  # no candles at all
    g.source_var.set(po.SOURCE_FILE)
    g.file_path_var.set(str(path))
    g.optimize_portfolio()
    g.wait()
    assert g.market_data.source == po.SOURCE_FILE
    assert g.market_data.coins == ["BTC", "ETH", "SOL"]
    assert g.optimization_result["success"]
    assert g._load_candles.candles.asked == []


# ---- the current portfolio: Long-term Holdings, as its tag filter keeps it ----


def test_the_current_portfolio_follows_the_holdings_tag_filter(root, manager, dialogs):
    for h in (
        holding("BTC", 1, 30000.0, 30000.0, tags=["Pension"]),
        holding("ETH", 10, 2000.0, 2000.0, tags=["Pension"]),
        holding("ETH", 5, 2000.0, 2000.0, tags=["Steve"]),
        holding("DOGE", 10000, 0.1, 0.5, tags=["Steve"]),
    ):
        manager.add_holding(h)
    lt = holdings_gui(root, manager)
    g = optimizer_gui(root, holdings=lt)
    # before any data: every coin held, BTC 30,000, ETH 30,000, DOGE 5,000
    assert g.current.weights == pytest.approx(
        {"BTC": 30 / 65, "ETH": 30 / 65, "DOGE": 5 / 65}
    )
    g.optimize_portfolio()
    g.wait()
    # in the coins with data: DOGE has none, and is named
    assert g.current.weights == pytest.approx({"BTC": 0.5, "ETH": 0.5})
    assert g.current.value == pytest.approx(60000.0)
    assert g.current.outside == pytest.approx({"DOGE": 5 / 65})
    line = g.current_label.cget("text")
    assert line.startswith("Current portfolio: Long-term Holdings, tags All: 2 coins")
    assert "DOGE (7.7% of the holdings' value)" in line
    held = {r[0]: r[1] for r in rows(g.results_tree)}
    assert held["BTC"] == "50.00%" and held["SOL"] == ""
    assert g.metric_labels[("current", "volatility")].cget("text").endswith("%")

    # the tag filter, chosen in Long-term Holdings
    lt.set_tag_selection(["Pension"])
    assert g.current.weights == pytest.approx({"BTC": 0.6, "ETH": 0.4})
    assert "tags Pension" in g.current_label.cget("text")
    assert {r[0]: r[5] for r in rows(g.data_tree)}["BTC"] == "60.00%"
    lt.set_tag_selection(["Steve"])
    assert g.current.weights == pytest.approx({"ETH": 1.0})
    assert g.current.outside == pytest.approx({"DOGE": 5 / 15})


def test_without_long_term_holdings_there_is_no_current_portfolio(root, dialogs):
    g = optimizer_gui(root)
    assert g.current.weights == {}
    assert g.current_label.cget("text") == (
        "Current portfolio: Long-term Holdings is not available."
    )


# ---- jobs off the Tk thread ----


def test_a_job_still_running_stops_when_the_window_is_destroyed(root, dialogs):
    started = threading.Event()

    def slow(coins, days, should_stop, progress):
        started.set()
        while not should_stop():
            threading.Event().wait(0.01)
        raise po.Stopped()

    g = optimizer_gui(root)
    g._load_candles = slow
    assert g.load_data()
    assert started.wait(5) and optimizer_threads()
    assert not g.load_data()  # one job at a time
    g.main_frame.master.destroy()
    assert not optimizer_threads()
    assert g.job is None


# ---- the hub ----


@pytest.fixture
def hub(monkeypatch, layout_file):
    """The real hub with its Long-term Holdings and Portfolio Optimization windows
    (the other heavy features off), on the guard's temporary holdings.db."""
    import helpers_trainer as ht

    import pt_hub

    if not (
        pt_hub.HOLDINGS_MANAGEMENT_AVAILABLE and pt_hub.PORTFOLIO_OPTIMIZER_AVAILABLE
    ):
        pytest.skip("the holdings or the optimizer window did not import")
    monkeypatch.setattr(lth, "_holdings_manager", None)  # this test's holdings.db
    on = ("HOLDINGS_MANAGEMENT_AVAILABLE", "PORTFOLIO_OPTIMIZER_AVAILABLE")
    monkeypatch.setattr(
        ht, "HEAVY_FLAGS", tuple(f for f in ht.HEAVY_FLAGS if f not in on)
    )
    hub = ht.build_real_hub(monkeypatch)
    yield hub
    ht.close_hub(hub)
    assert not optimizer_threads()


def test_the_hub_gives_the_tab_the_settings_coins_and_long_term_holdings(hub):
    import pt_hub

    g = hub.portfolio_optimizer_gui
    assert isinstance(g, pog.PortfolioOptimizerGUI)
    assert g.holdings is hub.holdings_gui
    assert g._coin_list() == [c.upper() for c in hub.coins]
    assert g.job is None and not optimizer_threads()  # nothing runs until asked
    nb = hub.bottom_notebook
    tab = next(
        t
        for t in nb.tabs()
        if pt_hub.module_tab_name(nb.tab(t, "text")) == "Portfolio Optimization"
    )
    assert g.main_frame in list(walk(hub.nametowidget(tab)))
