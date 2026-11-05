"""The hub's Market Data tab (real_time_market_data_gui): the coins in Settings
subscribed by default, symbol boxes that offer them and take any other, every pair
in the connected exchange's own format and every exchange by its proper name, and no
timer or feed left running once the tab is gone.

A real Tk window (alpha 0) under the isolation guard (app/conftest.py); the exchange
layer holds fake connectors: no network.
"""

import os
import re
import sys
import tkinter as tk
from tkinter import ttk

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import real_time_market_data as rtmd  # noqa: E402
import real_time_market_data_gui as gui_mod  # noqa: E402
import ui_table  # noqa: E402
from pt_exchange_abstraction import (  # noqa: E402
    ExchangeManager,
    ExchangeType,
    MarketNotFound,
    OrderBookSnapshot,
    Ticker,
)

FORMATS = {  # each exchange's own name for a coin's dollar market
    "coinbase": "{coin}-USD",
    "binance": "{coin}USDT",
    "kraken": "{coin}USD",
}


class Connector:
    """An exchange: its pair format, a ticker for every coin it lists, and candles
    of every size the chart offers, with ``volume`` (0: the exchange gives none)."""

    def __init__(self, name, unlisted=()):
        self.name = name
        self.unlisted = set(unlisted)
        self.asked = []
        self.volume = 7.0
        self.candle_error = None

    def market_symbol(self, symbol):
        return FORMATS[self.name].format(coin=symbol.split("-")[0])

    def order_book(self, symbol, depth=20):
        coin = symbol.split("-")[0]
        self.asked.append(("book", coin, depth))
        if coin in self.unlisted:
            raise MarketNotFound(f"{self.name} has no market {symbol}")
        return OrderBookSnapshot(
            [(100.0 - i, 1.0 + i) for i in range(depth)],
            [(101.0 + i, 0.5 * (i + 1)) for i in range(depth)],
            1_800_000_000.0,
        )

    def candle_timeframes(self):
        return frozenset(gui_mod.CHART_TIMEFRAMES)

    def max_history_bars(self, tf):
        return None

    def candles(self, symbol, tf, start_ms, end_ms):
        from market_data.timeframes import candle_timeframe_seconds

        self.asked.append(("candles", tf))
        if self.candle_error:
            raise self.candle_error
        step = candle_timeframe_seconds(tf) * 1000
        first = -(-int(start_ms) // step) * step
        return [
            [t, 100.0, 103.0, 98.0, 101.0 if (t // step) % 2 else 99.0, self.volume]
            for t in range(first, int(end_ms) + 1, step)
        ]

    def ticker(self, symbol):
        coin = symbol.split("-")[0]
        self.asked.append(coin)
        if coin in self.unlisted:
            raise MarketNotFound(f"{self.name} has no market {symbol}")
        return Ticker(
            101.0,
            100.0,
            102.0,
            volume_24h=8913.3,
            high_24h=105.0,
            low_24h=95.0,
            change_24h=2.5,
            change_24h_pct=2.54,
        )


def layer(*names, unlisted=None):
    manager = ExchangeManager()
    for name in names:
        manager.exchanges[ExchangeType(name)] = Connector(
            name, (unlisted or {}).get(name, ())
        )
    manager.primary_exchange = ExchangeType(names[0])
    return manager


class Box:
    """Stands in for tkinter.messagebox."""

    def __init__(self):
        self.shown = []

    def __getattr__(self, name):
        if name.startswith("show"):
            return lambda title, text, **kw: self.shown.append((name, text))
        raise AttributeError(name)


@pytest.fixture
def root(tmp_path, monkeypatch):
    import ui_theme
    import ui_tokens

    monkeypatch.setattr(ui_table, "LAYOUT_PATH", str(tmp_path / "table_layout.json"))
    ui_table.forget_layouts()
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
    ui_table.forget_layouts()


@pytest.fixture
def build(root, tmp_path):
    made = []

    def make(coins=("ETH", "SOL", "DOGE"), exchanges=("coinbase",), **kw):
        manager = rtmd.MarketDataManager(db_path=str(tmp_path / f"md{len(made)}.db"))
        manager.aggregator._layer = layer(*exchanges, unlisted=kw.pop("unlisted", None))
        manager.aggregator.poll_seconds = 3600  # the test polls by hand
        settings = list(coins)
        frame = ttk.Frame(root)
        frame.pack(fill="both", expand=True)
        gui = gui_mod.MarketDataGUI(
            frame,
            coins=lambda: settings,
            manager=manager,
            messagebox=Box(),
            refresh_ms=kw.pop("refresh_ms", 0),
        )
        gui.settings = settings
        made.append(gui)
        root.update_idletasks()
        return gui

    yield make
    for gui in made:
        gui.cleanup()
        for thread in gui.market_manager.aggregator.feed_threads.values():
            thread.join(timeout=10)


def poll(gui, *exchanges):
    for name in exchanges or gui.exchange_names():
        gui.market_manager.aggregator.poll_once(name)
    gui.process_updates()
    gui.data_table.settle()


def rows(gui):
    tree = gui.data_tree
    return [tuple(str(v) for v in tree.item(i, "values")) for i in tree.get_children()]


# --- the coins in Settings --------------------------------------------------------------


def test_the_default_subscriptions_are_the_coins_in_settings(build):
    gui = build(coins=("ETH", "sol", "DOGE"))
    assert set(gui.subscribed()) == {"ETH", "SOL", "DOGE"}
    assert all(names == ["coinbase"] for names in gui.subscribed().values())
    assert gui.subscriptions_count_label.cget("text") == "3"


def test_no_hard_coded_symbol_or_coin_is_left():
    with open(
        os.path.join(APP_DIR, "real_time_market_data_gui.py"), encoding="utf-8"
    ) as f:
        source = f.read()
    assert "BTCUSDT" not in source
    assert not re.search(r"[\"']ADA[\"']", source)


def test_every_symbol_box_offers_the_coins_in_settings_and_takes_any_other(build):
    gui = build(coins=("ETH", "SOL", "DOGE"))
    for var in (gui.symbol_var, gui.chart_symbol_var, gui.ob_symbol_var):
        assert var.get() == "ETH-USD"  # the first coin in Settings
    assert isinstance(gui.symbol_box, ttk.Combobox)
    assert str(gui.symbol_box.cget("state")) != "readonly"  # free entry
    assert list(gui.symbol_box.cget("values")) == ["ETH-USD", "SOL-USD", "DOGE-USD"]
    for typed, coin in (("ethusdt", "ETH"), ("SOL-USD", "SOL"), ("link", "LINK")):
        assert gui.coin_from(typed) == coin
    gui.symbol_var.set("link")
    gui.subscribe_symbol()
    assert gui.subscribed()["LINK"] == ["coinbase"]
    assert gui._box.shown[-1] == ("showinfo", "Subscribed to LINK-USD on Coinbase")


def test_the_coins_added_or_removed_in_settings_are_followed(build):
    gui = build(coins=("ETH", "SOL"))
    gui.settings[:] = ["ETH", "XRP"]
    gui._follow_settings_coins()
    assert set(gui.subscribed()) == {"ETH", "XRP"}
    assert gui.subscriptions_count_label.cget("text") == "2"


# --- one pair format, the exchanges by name ---------------------------------------------


@pytest.mark.parametrize(
    "exchanges, pair, shown",
    [(("coinbase",), "ETH-USD", "Coinbase"), (("binance",), "ETHUSDT", "Binance")],
)
def test_pairs_are_shown_as_the_connected_exchange_writes_them(
    build, exchanges, pair, shown
):
    gui = build(coins=("ETH",), exchanges=exchanges)
    poll(gui)
    ((symbol, exchange, price, change, pct, volume, *_),) = rows(gui)
    assert (symbol, exchange) == (pair, shown)
    assert (price, change, pct, volume) == ("101.00", "+2.50", "+2.54%", "8,913.30")
    assert gui.symbol_var.get() == pair
    assert list(gui.symbol_box.cget("values")) == [pair]


def test_one_format_even_for_a_coin_another_exchange_serves(build):
    """XMR is not on the primary: Kraken serves it, and it is still shown in the
    primary's format, like every other pair."""
    gui = build(
        coins=("BTC", "XMR"),
        exchanges=("coinbase", "kraken"),
        unlisted={"coinbase": {"XMR"}},
    )
    poll(gui, "coinbase")  # Coinbase has no XMR market: it moves to Kraken
    assert gui.subscribed()["XMR"] == ["kraken"]
    poll(gui, "kraken")
    assert sorted((r[0], r[1]) for r in rows(gui)) == [
        ("BTC-USD", "Coinbase"),
        ("XMR-USD", "Kraken"),
    ]
    assert list(gui.exchange_choices()) == ["Coinbase", "Kraken"]


def test_unsubscribing_removes_the_coins_rows(build):
    gui = build(coins=("ETH", "SOL"))
    poll(gui)
    gui.symbol_var.set("SOL-USD")
    gui.unsubscribe_symbol()
    assert [r[0] for r in rows(gui)] == ["ETH-USD"]
    assert set(gui.subscribed()) == {"ETH"}


# --- Price Charts -----------------------------------------------------------------------


def chart(gui, tf, symbol=None):
    if symbol is not None:
        gui.chart_symbol_var.set(symbol)
    gui.timeframe_var.set(tf)
    gui.update_chart()
    gui.chart_jobs.drain()


def span_days(gui):
    lo, hi = gui.price_ax.get_xlim()
    return hi - lo


def test_the_timeframe_sets_the_charts_time_span(build):
    """The chart is CHART_BARS candles of the chosen timeframe from the candle cache
    (it was the last 100 polled quotes, whatever the timeframe said)."""
    gui = build(coins=("ETH",))
    chart(gui, "1h")
    hourly = span_days(gui)
    assert hourly == pytest.approx((gui_mod.CHART_BARS + 0.4) / 24, rel=0.02)
    assert len(gui.price_ax.patches) == gui_mod.CHART_BARS
    assert gui.price_ax.get_title() == "ETH-USD · 1h · Coinbase"
    chart(gui, "1d")
    assert span_days(gui) / hourly == pytest.approx(24, rel=0.02)
    assert gui.price_ax.get_title() == "ETH-USD · 1d · Coinbase"
    connector = gui.market_manager.aggregator.layer().exchanges[ExchangeType.COINBASE]
    assert ("candles", "1h") in connector.asked and ("candles", "1d") in connector.asked
    # the cache: the same chart again asks the exchange for no older bar
    before = len(connector.asked)
    chart(gui, "1d")
    assert len([a for a in connector.asked[before:] if a[0] == "candles"]) <= 1


def test_the_volume_panel_shows_the_candles_volume_and_hides_without(build):
    gui = build(coins=("ETH", "SOL"))
    chart(gui, "1h", "ETH-USD")
    assert gui.volume_ax is not None
    assert [p.get_height() for p in gui.volume_ax.patches] == [7.0] * gui_mod.CHART_BARS
    connector = gui.market_manager.aggregator.layer().exchanges[ExchangeType.COINBASE]
    connector.volume = 0.0  # an exchange that gives no volume
    chart(gui, "4h", "SOL-USD")
    assert gui.volume_ax is None and gui.figure.axes == [gui.price_ax]
    assert len(gui.price_ax.patches) == gui_mod.CHART_BARS


def test_the_chart_is_drawn_when_its_tab_is_first_shown(build, root):
    gui = build(coins=("ETH",))
    assert len(gui.price_ax.patches) == 0  # nothing read while the tab is hidden
    gui.notebook.select(gui.charts_tab)
    root.update()
    gui.chart_jobs.drain()
    assert len(gui.price_ax.patches) == gui_mod.CHART_BARS


def test_a_coin_with_no_candles_says_so(build):
    gui = build(coins=("ETH",))
    connector = gui.market_manager.aggregator.layer().exchanges[ExchangeType.COINBASE]
    connector.candle_error = MarketNotFound("Coinbase has no market ETH-USD")
    chart(gui, "1h")
    assert [t.get_text() for t in gui.price_ax.texts] == ["ETH-USD (1h): no candles"]


# --- Order Books ------------------------------------------------------------------------


def book_rows(tree):
    return [tuple(str(v) for v in tree.item(i, "values")) for i in tree.get_children()]


def test_the_order_book_shows_both_sides_with_their_cumulative_quantity(build, root):
    gui = build(coins=("ETH",), exchanges=("coinbase", "kraken"))
    gui.ob_exchange_var.set("Kraken")
    gui.ob_depth_var.set("10")
    gui.load_orderbook()
    gui.book_jobs.drain()
    kraken = gui.market_manager.aggregator.layer().exchanges[ExchangeType.KRAKEN]
    assert ("book", "ETH", 10) in kraken.asked
    asks, bids = book_rows(gui.asks_tree), book_rows(gui.bids_tree)
    assert len(asks) == len(bids) == 10
    assert asks[:3] == [
        ("101.00", "0.5000", "0.5000"),
        ("102.00", "1.0000", "1.5000"),
        ("103.00", "1.5000", "3.0000"),
    ]  # the lowest ask first, the quantity up to each price
    assert bids[:2] == [("100.00", "1.0000", "1.0000"), ("99.00", "2.0000", "3.0000")]
    status = gui.ob_status_var.get()
    assert status.startswith("ETH-USD on Kraken")
    assert "Spread 1.00 (0.990%)" in status and "Mid price 100.50" in status
    headings = [
        gui.asks_tree.heading(c, "text") for c in ("price", "quantity", "total")
    ]
    assert headings == ["Price", "Quantity", "Cumulative Quantity"]


def test_the_order_book_refreshes_on_the_feed_interval_while_shown(build, root):
    gui = build(coins=("ETH",))
    gui.market_manager.aggregator.poll_seconds = 5.0
    gui.load_orderbook()
    gui.book_jobs.drain()
    assert "book" in gui._afters and gui._book_interval_ms() == 5000
    coinbase = gui.market_manager.aggregator.layer().exchanges[ExchangeType.COINBASE]
    asked = len([a for a in coinbase.asked if a[0] == "book"])
    gui._refresh_book()  # hidden (the Overview is the tab shown): not asked
    gui.book_jobs.drain()
    assert len([a for a in coinbase.asked if a[0] == "book"]) == asked
    gui.notebook.select(gui.orderbook_tab)
    root.update()
    gui._refresh_book()
    gui.book_jobs.drain()
    assert len([a for a in coinbase.asked if a[0] == "book"]) == asked + 1


def test_a_coin_the_exchange_does_not_list_says_so(build):
    gui = build(coins=("XMR",), unlisted={"coinbase": {"XMR"}})
    gui.load_orderbook()
    gui.book_jobs.drain()
    assert gui.ob_status_var.get() == "Coinbase has no market for XMR-USD"
    assert "book" not in gui._afters  # not asked again until loaded again
    assert book_rows(gui.asks_tree) == []


def test_no_not_yet_implemented_message_is_left():
    with open(
        os.path.join(APP_DIR, "real_time_market_data_gui.py"), encoding="utf-8"
    ) as f:
        assert "not yet implemented" not in f.read().lower()


# --- no Arbitrage Monitor ---------------------------------------------------------------


def test_there_is_no_arbitrage_monitor(build):
    """It compared the subscribed exchanges only (nothing, with one exchange) and
    left out trading fees, withdrawal fees and transfer time."""
    gui = build(coins=("ETH",), exchanges=("coinbase", "kraken"))
    names = [
        gui.notebook.tab(t, "text").replace("\n", " ") for t in gui.notebook.tabs()
    ]
    assert names == ["Market Overview", "Price Charts", "Order Books", "Data Feeds"]
    for module in ("real_time_market_data_gui.py", "real_time_market_data.py"):
        with open(os.path.join(APP_DIR, module), encoding="utf-8") as f:
            source = f.read()
        assert (
            "arbitrage_opportunities" not in source and "scan_arbitrage" not in source
        )
    poll(gui)
    assert (
        "arbitrage_opportunities"
        not in gui.market_manager.get_market_summary("ETH")["spread_analysis"]
    )


# --- Data Feeds -------------------------------------------------------------------------


def stats_rows(gui):
    tree = gui.stats_tree
    return {
        str(iid): tuple(str(v) for v in tree.item(iid, "values"))
        for iid in tree.get_children()
    }


def test_data_feeds_shows_green_with_live_statistics_and_the_overview_connected(
    build,
):
    import ui_tokens

    gui = build(coins=("ETH", "SOL"), exchanges=("coinbase", "kraken"))
    poll(gui, "coinbase")
    gui.update_feed_view()
    assert gui.feed_indicators["coinbase"].cget("foreground") == (
        ui_tokens.STATUS["good"]
    )
    assert gui.feed_indicators["kraken"].cget("foreground") == ui_tokens.STATUS["bad"]
    rows = stats_rows(gui)
    exchange, status, messages, last, uptime, errors, last_error = rows["coinbase"]
    assert (exchange, status, errors, last_error) == ("Coinbase", "Connected", "0", "")
    assert int(messages) >= 2 and re.fullmatch(r"\d\d:\d\d:\d\d", last)
    assert re.fullmatch(r"\d+s", uptime)
    assert rows["kraken"][:3] == ("Kraken", "Stopped", "0")  # no coin on it
    assert rows["kraken"][3:5] == ("n/a", "n/a")
    assert gui.feed_status_label.cget("text") == "Connected"
    assert str(gui.feed_status_label.cget("style")) == "Good.TLabel"


def test_the_overview_and_data_feeds_follow_one_state(build):
    """Stale and failing feeds: amber, red, and the Overview's label in step."""
    from datetime import datetime, timedelta

    import ui_tokens

    gui = build(coins=("ETH",))
    poll(gui)
    later = datetime.now() + timedelta(hours=3)  # no ticker for six poll intervals
    gui.market_manager.aggregator.poll_seconds = 5.0
    gui.update_feed_view(later)
    assert (
        gui.feed_indicators["coinbase"].cget("foreground") == ui_tokens.STATUS["warn"]
    )
    assert (
        stats_rows(gui)["coinbase"][1]
        == gui.feed_status_label.cget("text")
        == ("Stale")
    )

    class Down:
        def market_symbol(self, symbol):
            return symbol

        def ticker(self, symbol):
            raise ConnectionError("no route to host")

    gui.market_manager.aggregator.layer().exchanges[ExchangeType.COINBASE] = Down()
    poll(gui)
    gui.update_feed_view()
    row = stats_rows(gui)["coinbase"]
    assert row[1] == gui.feed_status_label.cget("text") == "Error"
    assert gui.feed_indicators["coinbase"].cget("foreground") == ui_tokens.STATUS["bad"]
    assert int(row[5]) >= 1 and row[6].endswith(
        "ETH-USD: ConnectionError: no route to host"
    )
    gui.market_manager.stop()
    gui.update_feed_view()
    assert (
        stats_rows(gui)["coinbase"][1]
        == gui.feed_status_label.cget("text")
        == ("Stopped")
    )


# --- nothing left running ---------------------------------------------------------------


def test_the_timers_and_feeds_stop_when_the_tab_is_destroyed(build, root):
    gui = build(coins=("ETH",), refresh_ms=20)
    assert set(gui._afters) == {"refresh", "coins"}
    threads = list(gui.market_manager.aggregator.feed_threads.values())
    assert threads and all(t.is_alive() for t in threads)
    gui.main_frame.master.destroy()
    root.update()
    assert gui.alive is False and gui._afters == {}
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
