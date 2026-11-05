"""Portfolio Analytics and Portfolio Optimization (owner, 2026-11-05).

* Portfolio Analytics is gone: no tab, no entry in the tab order, its two modules in
  archive/legacy/.
* Portfolio Optimization runs on the coins in Settings with no file and nothing
  typed: their daily closes come from the candle cache (the exchanges in Settings,
  primary first) over a window; a price file (CSV) stays an optional source, and the
  sample data and the typed returns are gone. The current portfolio is Long-term
  Holdings', as its tag filter keeps it.
* One Rebalancing: Long-term Holdings'. Apply as Targets writes an optimisation's
  weights to the holdings' target %, after a confirmation with the old and new
  targets, and Long-term Holdings' Rebalancing shows the drift from them, each
  trade with its fee at the exchange layer's taker rate (0.6% when it gives none).
* Analysis: the efficient frontier, the composition and the risk-return scatter
  come from that data, and the frontier marks the current portfolio.
* Monte Carlo: 5,000 paths of 30 days by default, drawn by resampling the window's
  days (the default) or as correlated normal draws, the same draws for the current
  and optimised portfolios; the fan chart's percentiles, the expected final value,
  the Value at Risk at 95% and the chance of a drawdown reaching the emergency stop
  % (Settings); a fixed seed draws the same paths again; labelled as a model based
  on past data, not a forecast.

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


def holdings_gui(win, manager, fees=lambda symbol: (0.005, True)):
    """Long-term Holdings' window on ``manager``; ``fees`` stands in for the
    exchange layer's taker rate (0.5% by default)."""
    from tkinter import ttk

    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True)
    return ltg.HoldingsManagementGUI(
        frame, coins=lambda: list(COINS), manager=manager, fees=fees
    )


def optimizer_gui(
    win, frames=None, coins=COINS, holdings=None, drawdown_pct=None, **kw
):
    from tkinter import ttk

    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True)
    g = pog.PortfolioOptimizerGUI(
        frame,
        coins=lambda: list(coins),
        holdings=holdings,
        load_candles=loader(daily_frames() if frames is None else frames, **kw),
        drawdown_pct=drawdown_pct,
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


def test_a_target_return_is_met_or_refused_with_the_reachable_range(root, dialogs):
    g = optimizer_gui(root)
    g.opt_type_var.set("Target return")
    g.on_opt_type_change()
    g.load_data()
    g.wait()
    low, high = po.reachable_returns(
        g.market_data.expected_returns(), {"min_weight": 0.01, "max_weight": 0.4}
    )
    g.target_return_var.set(f"{(high + 0.05) * 100:.2f}")
    g.optimize_portfolio()
    g.wait()
    assert g.optimization_result is None
    assert dialogs.calls[-1][2] == (
        "With these weight limits the target return must be from "
        f"{low * 100:.2f}% to {high * 100:.2f}%."
    )
    target = (low + high) / 2
    g.target_return_var.set(f"{target * 100:.4f}")
    g.optimize_portfolio()
    g.wait()
    result = g.optimization_result
    assert result["success"] and result["method"] == "target_return"
    assert result["expected_return"] == pytest.approx(target, abs=1e-5)


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


# ---- acceptance: one Rebalancing, and Apply as Targets feeds it ----


def test_no_duplicate_rebalancing_remains(root, manager, dialogs):
    lt = holdings_gui(root, manager)
    g = optimizer_gui(root, holdings=lt)
    assert [g.notebook.tab(t, "text") for t in g.notebook.tabs()] == [
        "Data",
        "Optimization",
        "Analysis",
    ]
    assert not [t for t in texts(g.main_frame) if "Rebalanc" in t]
    for name in (
        "setup_rebalancing_tab",
        "analyze_rebalancing",
        "use_last_optimization",
        "parse_weights",
    ):
        assert not hasattr(g, name)
    assert not hasattr(po.PortfolioOptimizer, "suggest_rebalancing")
    # the one left: Long-term Holdings'
    assert "Rebalancing" in [lt.notebook.tab(t, "text") for t in lt.notebook.tabs()]


def pension_holdings(manager):
    """Four Pension holdings (BTC 30,000, ETH 20,000 on Coinbase and 10,000 on
    Kraken, SOL with no current price) and a Steve one."""
    for h in (
        holding("BTC", 1, 30000.0, 30000.0, target_percentage=50.0, tags=["Pension"]),
        holding(
            "ETH",
            10,
            2000.0,
            2000.0,
            exchange="Coinbase",
            target_percentage=25.0,
            tags=["Pension"],
        ),
        holding(
            "ETH",
            5,
            2000.0,
            2000.0,
            exchange="Kraken",
            target_percentage=25.0,
            tags=["Pension"],
        ),
        holding("SOL", 100, 100.0, 0.0, tags=["Pension"]),
        holding("DOGE", 10000, 0.1, 0.5, target_percentage=100.0, tags=["Steve"]),
    ):
        manager.add_holding(h)


def saved_holdings(manager):
    """holdings.db's holdings, by (coin, exchange)."""
    return {(h.symbol, h.exchange): h for h in manager.db.get_all_holdings()}


def test_applying_a_result_updates_the_targets_and_rebalancing_reflects_them(
    root, manager, dialogs
):
    pension_holdings(manager)
    lt = holdings_gui(root, manager)
    lt.set_tag_selection(["Pension"])
    g = optimizer_gui(root, holdings=lt)
    g.optimize_portfolio()
    g.wait()
    weights = g.optimization_result["weights"]
    # the targets now, beside the weights
    targets = {r[0]: r[3] for r in rows(g.results_tree)}
    assert (targets["BTC"], targets["ETH"], targets["XRP"]) == ("50.00%", "50.00%", "")

    # the confirmation: each old and new target; No changes nothing
    dialogs.answer = False
    assert not g.apply_as_targets()
    ((_box, title, message),) = [c for c in dialogs.calls if c[0] == "askyesno"]
    assert title == "Apply as Targets"
    lines = message.splitlines()
    assert lines[0] == (
        "Set the target % of 4 holdings (tags: Pension) to the optimised weights?"
    )
    btc, eth, sol = (weights[c] * 100 for c in ("BTC", "ETH", "SOL"))
    assert f"BTC: 50.00% → {btc:.2f}%" in lines
    # ETH's weight shared by value: 20,000 on Coinbase, 10,000 on Kraken
    assert f"ETH (Coinbase): 25.00% → {eth * 2 / 3:.2f}%" in lines
    assert f"ETH (Kraken): 25.00% → {eth / 3:.2f}%" in lines
    assert f"SOL: 0.00% → {sol:.2f}%" in lines  # the one SOL holding
    assert lines[-1] == f"Not set, no holding: XRP {weights['XRP'] * 100:.2f}%"
    assert saved_holdings(manager)[("BTC", "")].target_percentage == 50.0

    dialogs.answer = True
    assert g.apply_as_targets()
    saved = saved_holdings(manager)
    new = {
        ("BTC", ""): round(btc, 2),
        ("ETH", "Coinbase"): round(eth * 2 / 3, 2),
        ("ETH", "Kraken"): round(eth / 3, 2),
        ("SOL", ""): round(sol, 2),
        ("DOGE", ""): 100.0,  # outside the tag filter: as it was
    }
    assert {k: h.target_percentage for k, h in saved.items()} == pytest.approx(new)
    assert saved[("BTC", "")].tags == ["Pension"]  # the tags kept
    # Long-term Holdings shows them at once: Holdings, and Rebalancing's drift
    assert {r[0]: r[9] for r in rows(lt.holdings_tree)}[
        "BTC"
    ] == f"{new['BTC', '']:.1f}%"
    expected = manager.get_rebalancing_suggestions(
        lt.filtered_holdings(), fee_rate=lt.fee_rate
    )
    # BTC is 50% of the Pension holdings' value, its target at most 40% now
    assert ("BTC", "SELL") in [(s["symbol"], s["action"]) for s in expected]
    assert rows(lt.suggestions_tree) == [lt.suggestion_cells(s) for s in expected]
    shown_targets = {r[0]: r[3] for r in rows(lt.suggestions_tree)}
    assert shown_targets["BTC"] == f"{new['BTC', '']:.2f}%"
    # and the Optimization table, the targets now
    targets = {r[0]: r[3] for r in rows(g.results_tree)}
    assert targets["BTC"] == f"{new['BTC', '']:.2f}%"
    assert targets["ETH"] == f"{new['ETH', 'Coinbase'] + new['ETH', 'Kraken']:.2f}%"
    assert g.status_label.cget("text") == "Targets set on 4 holdings."


def test_coins_held_optimises_over_the_coins_held_only(root, manager, dialogs):
    pension_holdings(manager)
    lt = holdings_gui(root, manager)
    lt.set_tag_selection(["Pension"])
    g = optimizer_gui(root, holdings=lt)
    g.universe_var.set("Coins held")
    g.optimize_portfolio()
    g.wait()
    assert set(g.optimization_result["weights"]) == {"BTC", "ETH", "SOL"}
    assert g.market_data.coins == list(COINS)  # the data: the coins in Settings
    assert g.apply_as_targets()
    message = [c for c in dialogs.calls if c[0] == "askyesno"][-1][2]
    assert "Not set" not in message
    pension = [h for h in manager.db.get_all_holdings() if "Pension" in h.tags]
    assert sum(h.target_percentage for h in pension) == pytest.approx(100.0, abs=0.05)

    lt.set_tag_selection(["Steve"])  # DOGE only, and DOGE has no data
    g.optimize_portfolio()
    g.wait()
    assert dialogs.calls[-1][2] == (
        "Of the coins held: optimization needs daily closes for at least two coins."
    )


def test_apply_as_targets_needs_a_result_and_holdings(root, manager, dialogs):
    lt = holdings_gui(root, manager)
    g = optimizer_gui(root, holdings=lt)
    assert not g.apply_as_targets()
    assert dialogs.calls[-1][2] == "Optimize the portfolio first."
    g.optimize_portfolio()
    g.wait()
    assert not g.apply_as_targets()
    assert dialogs.calls[-1][2] == "No holdings to set targets on (tags: All)."
    alone = optimizer_gui(root)
    alone.optimize_portfolio()
    alone.wait()
    assert not alone.apply_as_targets()
    assert dialogs.calls[-1][2] == "Long-term Holdings is not available."


def test_a_coins_weight_is_shared_by_its_holdings_value():
    eth = [holding("ETH", 2, 1.0, 100.0), holding("ETH", 1, 1.0, 100.0)]
    ada = [holding("ADA", 10, 1.0, 0.0), holding("ADA", 5, 1.0, 0.0)]  # no value
    doge = holding("DOGE", 1, 1.0, 1.0, target_percentage=30.0)
    changes, unheld = po.targets_from_weights(
        eth + ada + [doge], {"ETH": 0.6, "ADA": 0.3, "BTC": 0.1}
    )
    assert [(c.old, c.new) for c in changes] == [
        (0.0, 40.0),
        (0.0, 20.0),
        (0.0, 15.0),  # equal shares when none has a value
        (0.0, 15.0),
        (30.0, 0.0),  # no weight: no target
    ]
    assert unheld == {"BTC": 0.1}


# ---- fees: the exchange layer's taker rate, else 0.6% ----


def test_the_fee_rate_comes_from_the_exchange_layer_else_the_default_0_6_percent():
    asked = []

    def trading_fees(symbol):
        asked.append(symbol)
        return {"maker": 0.004, "taker": 0.0025}

    on_layer = SimpleNamespace(trading_fees=trading_fees)
    assert lth.trading_fee_rate("BTC", layer=lambda: on_layer) == (0.0025, True)
    on_manager = SimpleNamespace(
        exchange_manager=SimpleNamespace(trading_fees=trading_fees)
    )
    assert lth.trading_fee_rate("ETH", layer=lambda: on_manager) == (0.0025, True)
    assert asked == ["BTC", "ETH"]
    assert lth.DEFAULT_TAKER_FEE_RATE == 0.006
    for layer in (
        SimpleNamespace(exchange_manager=SimpleNamespace()),  # no trading_fees()
        SimpleNamespace(trading_fees=lambda s: {"maker": 0.004}),  # no taker rate
        SimpleNamespace(trading_fees=lambda s: {"taker": 0.6}),  # a percent
        SimpleNamespace(trading_fees=lambda s: 1 / 0),  # it fails
    ):
        assert lth.trading_fee_rate("BTC", layer=lambda: layer) == (0.006, False)


def test_the_fee_rate_reads_the_exchange_managers_answer():
    """The exchange layer's managers answer trading_fees() with a Sourced whose value
    is a TradingFees, primary exchange first."""
    from pt_exchange_abstraction import ExchangeManager, ExchangeType, TradingFees

    class Connector:
        def market_symbol(self, market):
            return market

        def trading_fees(self, symbol):
            return TradingFees(0.004, 0.0025, "kraken", "exchange")

    manager = ExchangeManager()
    manager.exchanges[ExchangeType.KRAKEN] = Connector()
    on_manager = SimpleNamespace(exchange_manager=manager)
    assert lth.trading_fee_rate("BTC", layer=lambda: on_manager) == (0.0025, True)
    assert lth.trading_fee_rate("BTC", layer=lambda: manager) == (0.0025, True)


def two_holdings_to_rebalance(manager):
    """BTC 30,000 and ETH 10,000, both with a 50% target: BTC sells 10,000 and ETH
    buys 10,000."""
    for h in (
        holding("BTC", 0.5, 40000.0, 60000.0, target_percentage=50.0),
        holding("ETH", 10, 1000.0, 1000.0, target_percentage=50.0),
    ):
        manager.add_holding(h)


def trade_totals(lt):
    return {k: label.cget("text") for k, label in lt.trade_labels.items()}


def test_rebalancing_shows_each_trade_with_its_fee_and_the_totals(
    root, manager, dialogs
):
    two_holdings_to_rebalance(manager)
    asked = []

    def fees(symbol):
        asked.append(symbol)
        return 0.005, True

    lt = holdings_gui(root, manager, fees=fees)
    cells = {r[0]: r for r in rows(lt.suggestions_tree)}
    assert cells["BTC"][1] == "Sell"
    assert cells["BTC"][5:] == ("$10,000.00", "$50.00", "$9,950.00")
    assert cells["ETH"][1] == "Buy"
    assert cells["ETH"][5:] == ("$10,000.00", "$50.00", "$10,050.00")
    assert [lt.suggestions_tree.heading(c, "text") for c in ("fee", "net")] == [
        "Fee",
        "Net Amount",
    ]
    assert trade_totals(lt) == {
        "count": "2",
        "amount": "$20,000.00",
        "fees": "$100.00",
        "rate": "0.50%",
    }
    # each coin's rate is read once, until Refresh
    lt.refresh_holdings_display()
    assert sorted(asked) == ["BTC", "ETH"]
    lt.refresh()
    assert sorted(asked) == ["BTC", "BTC", "ETH", "ETH"]


def test_with_no_rate_from_the_exchange_layer_fees_are_at_the_default_rate(
    root, manager, dialogs
):
    two_holdings_to_rebalance(manager)
    no_rate = SimpleNamespace(exchange_manager=SimpleNamespace())
    lt = holdings_gui(
        root, manager, fees=lambda s: lth.trading_fee_rate(s, layer=lambda: no_rate)
    )
    cells = {r[0]: r for r in rows(lt.suggestions_tree)}
    assert cells["BTC"][5:] == ("$10,000.00", "$60.00", "$9,940.00")
    assert trade_totals(lt)["rate"] == "0.60% (default rate)"


# ---- the Analysis sub-tab: the real data, the current portfolio marked ----


def chart_lines(g):
    (ax,) = g.analysis_fig.axes
    return {line.get_label(): line for line in ax.get_lines()}


def test_the_frontier_is_the_data_s_and_marks_the_current_portfolio(
    root, manager, dialogs
):
    import matplotlib.pyplot as plt

    figures = len(plt.get_fignums())
    pension_holdings(manager)
    manager.add_holding(holding("ETH", 2, 2000.0, 2000.0, tags=["Steve"]))
    lt = holdings_gui(root, manager)
    lt.set_tag_selection(["Pension"])
    g = optimizer_gui(root, holdings=lt)
    g.notebook.select(g.analysis_tab)
    assert g.view_var.get() == "Efficient Frontier"
    assert g.chart_note.winfo_manager() and not g.analysis_widget.winfo_manager()
    assert g.chart_note.cget("text") == "Optimize the portfolio first"

    g.optimize_portfolio()
    g.wait()
    root.update()
    assert g.analysis_widget.winfo_manager() and not g.chart_note.winfo_manager()
    lines = chart_lines(g)
    assert list(lines) == [
        "Efficient frontier",
        "Max Sharpe ratio",
        "Optimised",
        "Current portfolio",
    ]
    frontier = g.frontier_data
    np.testing.assert_allclose(
        lines["Efficient frontier"].get_xdata(), frontier["Volatility"] * 100
    )
    np.testing.assert_allclose(
        lines["Efficient frontier"].get_ydata(), frontier["Return"] * 100
    )
    # the current portfolio: BTC and ETH, half each, over the same data
    ret, vol, _sharpe = g.portfolio_figures({"BTC": 0.5, "ETH": 0.5})
    data = g.result_data
    w = np.array([0.5, 0.5, 0.0, 0.0])
    assert ret == pytest.approx(float(data.expected_returns().values @ w))
    assert vol == pytest.approx(float(np.sqrt(w @ data.covariance().values @ w)))
    current = lines["Current portfolio"]
    assert (current.get_xdata()[0], current.get_ydata()[0]) == pytest.approx(
        (vol * 100, ret * 100)
    )
    result = g.optimization_result
    assert g.analysis_points["Optimised"] == pytest.approx(
        (result["volatility"], result["expected_return"])
    )
    # it follows the tag filter: of Steve's holdings, only ETH's coin has data
    lt.set_tag_selection(["Steve"])
    eth = (data.volatilities()["ETH"], data.expected_returns()["ETH"])
    assert g.analysis_points["Current portfolio"] == pytest.approx(eth)
    assert len(plt.get_fignums()) == figures  # one figure, not one per drawing


def test_the_composition_and_the_risk_return_scatter_use_the_data(
    root, manager, dialogs
):
    pension_holdings(manager)
    lt = holdings_gui(root, manager)
    lt.set_tag_selection(["Pension"])
    g = optimizer_gui(root, holdings=lt)
    g.view_var.set("Risk-Return Scatter")
    g.draw_analysis()
    assert g.chart_note.cget("text") == "Load the data first"
    g.optimize_portfolio()
    g.wait()

    (ax,) = g.analysis_fig.axes  # the scatter: each coin, and both portfolios
    data = g.result_data
    (coins,) = ax.collections
    np.testing.assert_allclose(
        coins.get_offsets(),
        np.column_stack([data.volatilities() * 100, data.expected_returns() * 100]),
    )
    assert [t.get_text() for t in ax.texts] == list(COINS)
    assert set(chart_lines(g)) == {"Optimised", "Current portfolio"}

    g.view_var.set("Portfolio Composition")
    g.draw_analysis()
    assert g.analysis_weights == {
        "Optimised": g.optimization_result["weights"],
        "Current portfolio": pytest.approx({"BTC": 0.5, "ETH": 0.5}),
    }
    (ax,) = g.analysis_fig.axes
    assert len(ax.patches) == 2 * len(COINS)  # two bars a coin
    widths = sorted(p.get_width() for p in ax.patches)
    assert widths[-1] == pytest.approx(50.0)  # BTC and ETH: 50% of the current


# ---- Monte Carlo ----


def fat_tailed_returns(days=500, seed=3):
    """Daily returns of two correlated coins with fat tails (Student's t, 3
    degrees of freedom)."""
    rng = np.random.default_rng(seed)
    common = rng.standard_t(3, days) * 0.02
    return pd.DataFrame(
        {
            "BTC": common + rng.normal(0.0, 0.01, days),
            "ETH": 1.3 * common + rng.normal(0.0, 0.015, days),
        },
        index=pd.date_range("2025-01-01", periods=days, freq="D", tz="UTC"),
    )


def one_day(returns, method, paths=20000, seed=1):
    """The simulated one-day returns of each coin held alone, path by path."""
    sim = po.simulate_portfolios(
        returns,
        {c: {c: 1.0} for c in returns.columns},
        start_value=1.0,
        days=1,
        paths=paths,
        method=method,
        seed=seed,
    )
    return np.column_stack([sim.portfolios[c].finals - 1.0 for c in returns.columns])


def test_the_simulation_defaults_to_5000_paths_of_30_days_by_historical_bootstrap():
    import inspect

    assert (po.DEFAULT_MC_PATHS, po.DEFAULT_MC_DAYS) == (5000, 30)
    assert po.MC_METHODS == (
        ("Historical bootstrap", po.MC_BOOTSTRAP),
        ("Normal", po.MC_NORMAL),
    )
    defaults = inspect.signature(po.simulate_portfolios).parameters
    assert defaults["method"].default == po.MC_BOOTSTRAP
    assert (defaults["paths"].default, defaults["days"].default) == (5000, 30)


def test_the_bootstrap_resamples_whole_days_so_the_coins_move_together():
    returns = fat_tailed_returns()
    drawn = one_day(returns, po.MC_BOOTSTRAP, paths=2000)
    # every simulated day is a day of the window: both coins' returns from it
    gaps = np.abs(drawn[:, None, :] - returns.values[None, :, :]).max(axis=2)
    assert gaps.min(axis=1).max() < 1e-6
    assert len({tuple(np.round(d, 5)) for d in drawn}) > 400  # many days drawn


def test_normal_draws_are_correlated_with_the_window_s_mean_and_covariance():
    returns = fat_tailed_returns()
    drawn = one_day(returns, po.MC_NORMAL, paths=100000)
    np.testing.assert_allclose(
        np.cov(drawn, rowvar=False), np.cov(returns.values, rowvar=False), rtol=0.03
    )
    assert np.corrcoef(drawn, rowvar=False)[0, 1] == pytest.approx(
        returns.corr().iloc[0, 1], abs=0.01
    )
    error = 4 * returns.std().max() / np.sqrt(len(drawn))  # four standard errors
    np.testing.assert_allclose(drawn.mean(axis=0), returns.mean(), atol=error)
    # the window's fat tails: its worst days are worse than normal draws give
    resampled = one_day(returns, po.MC_BOOTSTRAP, paths=100000)
    assert np.percentile(resampled[:, 1], 0.5) < np.percentile(drawn[:, 1], 0.5)


def test_a_fixed_seed_draws_the_same_paths_and_both_portfolios_share_them():
    returns = fat_tailed_returns()
    same = {"BTC": 0.5, "ETH": 0.5}

    def run(seed, method=po.MC_BOOTSTRAP):
        return po.simulate_portfolios(
            returns,
            {"a": same, "b": dict(same), "btc": {"BTC": 1.0}},
            start_value=1000.0,
            seed=seed,
            method=method,
        )

    for method in (po.MC_BOOTSTRAP, po.MC_NORMAL):
        first, again, other = run(7, method), run(7, method), run(8, method)
        a = first.portfolios["a"].finals
        np.testing.assert_array_equal(a, again.portfolios["a"].finals)
        assert not np.array_equal(a, other.portfolios["a"].finals)
        # the same draws for every portfolio: equal weights, equal paths
        np.testing.assert_array_equal(a, first.portfolios["b"].finals)
        assert first.seed == 7 and first.paths == 5000 and first.days == 30


def test_the_fan_the_expected_value_and_the_value_at_risk_come_from_the_paths():
    returns = fat_tailed_returns()
    sim = po.simulate_portfolios(
        returns, {"p": {"BTC": 0.7, "ETH": 0.3}}, start_value=10000.0, seed=3
    )
    stats = sim.portfolios["p"]
    p = stats.percentiles
    assert sorted(p) == [5, 25, 50, 75, 95]
    assert all(len(p[k]) == 31 and p[k][0] == pytest.approx(10000.0) for k in p)
    assert np.all(p[5] <= p[25]) and np.all(p[25] <= p[50])
    assert np.all(p[50] <= p[75]) and np.all(p[75] <= p[95])
    assert stats.expected_final == pytest.approx(stats.finals.mean())
    # Value at Risk at 95%: the start less the 5th percentile of the final value
    assert stats.var_95 == pytest.approx(10000.0 - np.percentile(stats.finals, 5))
    assert stats.var_95 == pytest.approx(10000.0 - p[5][-1], rel=1e-5)
    assert (sim.first_day, sim.last_day) == (returns.index[0], returns.index[-1])


def test_the_drawdown_is_the_fall_from_the_highest_value_before():
    paths = np.array(
        [
            [100.0, 120.0, 108.0, 115.0],  # 10% under its 120 peak, above the start
            [100.0, 95.0, 97.0, 99.0],  # 5%
            [100.0, 101.0, 102.0, 103.0],  # none
        ]
    )
    np.testing.assert_allclose(po.max_drawdowns(paths), [0.10, 0.05, 0.0])


def test_the_drawdown_probability_counts_the_paths_reaching_the_emergency_stop():
    index = pd.date_range("2025-01-01", periods=50, freq="D", tz="UTC")

    def chance(daily, days):
        returns = pd.DataFrame({"BTC": daily, "ETH": daily}, index=index)
        sim = po.simulate_portfolios(
            returns,
            {"p": {"BTC": 0.5, "ETH": 0.5}},
            start_value=1000.0,
            days=days,
            paths=200,
            drawdown_limit=0.08,
        )
        return sim.portfolios["p"].drawdown_probability

    assert chance(-0.01, 8) == 0.0  # 1 - 0.99^8: 7.7%
    assert chance(-0.01, 9) == 1.0  # 8.6%
    assert chance(0.01, 30) == 0.0
    # up or down 2% a day: some paths fall 8% from a peak within 30 days, some not
    halves = np.where(np.arange(50) % 2 == 0, 0.02, -0.02)
    assert 0.0 < chance(halves, 30) < 1.0


def test_paths_days_and_seed_are_checked(root, dialogs):
    g = optimizer_gui(root)
    g.load_data()
    g.wait()
    for paths, days, message in (
        ("50", "30", "The paths must be from 100 to 100,000."),
        ("5000", "2000", "The horizon must be from 1 to 1095 days."),
        ("100000", "1000", "Paths times days can be at most 10,000,000."),
        ("5.5", "30", "Enter whole numbers for the paths, days and seed."),
    ):
        g.mc_paths_var.set(paths)
        g.mc_days_var.set(days)
        assert not g.run_simulation()
        assert dialogs.calls[-1][2] == message
    assert g.job is None


def test_monte_carlo_compares_the_current_and_optimised_portfolios(
    root, manager, dialogs
):
    pension_holdings(manager)
    lt = holdings_gui(root, manager)
    lt.set_tag_selection(["Pension"])
    g = optimizer_gui(root, holdings=lt, drawdown_pct=lambda: 12.0)
    assert g.mc_method_var.get() == "Historical bootstrap"
    assert (g.mc_paths_var.get(), g.mc_days_var.get()) == ("5000", "30")
    assert not g.mc_fixed_seed_var.get()
    g.optimize_portfolio()
    g.wait()
    assert g.run_simulation()
    g.wait()
    sim = g.simulation
    assert set(sim.portfolios) == {"current", "optimised"}
    assert (sim.method, sim.paths, sim.days) == (po.MC_BOOTSTRAP, 5000, 30)
    assert sim.drawdown_limit == pytest.approx(0.12)
    # the starting value: the Pension holdings' value in the coins with data
    assert sim.portfolios["current"].start_value == pytest.approx(60000.0)
    assert g.view_var.get() == "Monte Carlo"

    # the fan charts, labelled as a model
    axes = g.analysis_fig.axes
    assert [ax.get_title() for ax in axes] == ["Current portfolio", "Optimised"]
    assert g.analysis_fig.get_suptitle() == (
        "A model based on past data, not a forecast"
    )
    median = next(line for line in axes[1].get_lines() if line.get_label() == "Median")
    np.testing.assert_allclose(
        median.get_ydata(), sim.portfolios["optimised"].percentiles[50]
    )
    data = g.result_data
    assert g.mc_note.winfo_manager()
    assert g.mc_note.cget("text") == (
        "A model based on past data, not a forecast: 5,000 paths of 30 days, days "
        f"resampled from the daily returns of {data.returns.index[0]:%Y-%m-%d} to "
        f"{data.returns.index[-1]:%Y-%m-%d}; seed {sim.seed}."
    )
    # the figures, for both
    assert g.mc_row_titles["drawdown"].cget("text") == (
        "Drawdown reaches 12% (emergency stop)"
    )
    for name in ("current", "optimised"):
        stats = sim.portfolios[name]
        change = stats.expected_final / 60000.0 - 1.0
        assert g.mc_labels[(name, "expected")].cget("text") == (
            f"${stats.expected_final:,.2f} ({change:+.1%})"
        )
        loss = max(0.0, stats.var_95)
        assert g.mc_labels[(name, "var")].cget("text") == (
            f"${loss:,.2f} ({loss / 60000.0:.1%})"
        )
        assert g.mc_labels[(name, "drawdown")].cget("text") == (
            f"{stats.drawdown_probability:.1%}"
        )
    # another chart: the simulation's parts go
    g.view_var.set("Efficient Frontier")
    g.draw_analysis()
    assert not g.mc_note.winfo_manager() and not g.mc_stats.winfo_manager()

    # the seed shown draws the same paths again
    g.mc_fixed_seed_var.set(True)
    g.mc_seed_var.set(str(sim.seed))
    g.run_simulation()
    g.wait()
    np.testing.assert_array_equal(
        g.simulation.portfolios["optimised"].finals,
        sim.portfolios["optimised"].finals,
    )
    # the normal method
    g.mc_method_var.set("Normal")
    g.run_simulation()
    g.wait()
    assert g.simulation.method == po.MC_NORMAL
    assert "correlated normal draws fitted to" in g.mc_note.cget("text")


def test_without_holdings_the_optimised_portfolio_alone_starts_at_10000(root, dialogs):
    g = optimizer_gui(root)
    assert not g.run_simulation()
    assert dialogs.calls[-1][2] == "Load the data first."
    g.optimize_portfolio()
    g.wait()
    g.mc_days_var.set("10")
    assert g.run_simulation()
    g.wait()
    assert set(g.simulation.portfolios) == {"optimised"}
    assert g.simulation.portfolios["optimised"].start_value == 10000.0
    assert [ax.get_title() for ax in g.analysis_fig.axes] == ["Optimised"]
    assert g.mc_labels[("current", "expected")].cget("text") == ""


def test_the_emergency_stop_comes_from_the_risk_settings(monkeypatch):
    import trading_mode

    assert pog._emergency_drawdown_pct() == 8.0  # no settings: the default
    monkeypatch.setattr(trading_mode, "read_emergency_drawdown_pct", lambda: 15.0)
    assert pog._emergency_drawdown_pct() == 15.0


def test_a_simulation_still_running_stops_when_the_window_is_destroyed(root, dialogs):
    g = optimizer_gui(root)
    g.load_data()
    g.wait()
    g.mc_paths_var.set("100000")
    g.mc_days_var.set("100")
    g.optimize_portfolio()
    g.wait()
    assert g.run_simulation()
    assert optimizer_threads()
    g.main_frame.master.destroy()
    assert not optimizer_threads()


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
