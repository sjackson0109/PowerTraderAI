"""The bottom panel's Trade History and Long-term Holdings tabs (owner, 2026-11-04).

Trade History: the trade history as a table (Time, Side, Source, Pair, Quantity,
Price, Value, Fees, Realised PnL, PnL %), newest first, sorted by a heading click;
filters for the coin, side, source and period and a search through every column;
a summary of the rows shown. The rows are trade_history.jsonl's, read as before.

Long-term Holdings: holdings.db's entries, with the share of the holdings only, a
subtitle saying they are apart from the trading account, and nothing linking them.

Real Tk widgets (hidden, or a transparent window where sizes matter) and a real
hub, under the isolation guard (app/conftest.py).
"""

import json
import os
import sys
import time

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import trade_history_view as thv  # noqa: E402
import ui_table  # noqa: E402

NOW = time.mktime((2026, 11, 4, 12, 0, 0, 0, 0, -1))
HOUR = 3600.0
DAY = 24 * HOUR


def row(age_h, side, tag, symbol, qty, price, **extra):
    r = {
        "ts": NOW - age_h * HOUR,
        "side": side,
        "tag": tag,
        "symbol": symbol,
        "qty": qty,
        "price": price,
        "fees_usd": 0.1,
        "realized_profit_usd": None,
        "pnl_pct": None,
    }
    r.update(extra)
    return r


ROWS = [  # oldest first, as the trader appends them
    row(24 * 40, "buy", None, "BTC-USD", 0.001, 60000.0),
    row(24 * 10, "buy", "DCA", "BTC-USD", 0.001, 57000.0, pnl_pct=-5.0),
    row(
        30,
        "sell",
        "TRAIL_SELL",
        "BTC-USD",
        0.002,
        61000.0,
        fees_usd=0.2,
        realized_profit_usd=1.5,
        pnl_pct=3.2,
    ),
    row(20, "buy", "ENTRY", "ETH-USD", 0.5, 3000.0),
    row(
        5,
        "sell",
        "EXIT:OVL-PLOCK",
        "ETH-USD",
        0.5,
        2990.0,
        fees_usd=None,
        realized_profit_usd=-0.5,
        pnl_pct=-0.3,
    ),
    row(1, "buy", "MANUAL", "SOL-USD", 2.0, 150.0),
    {"ts": NOW, "side": "deposit", "symbol": "USD"},  # not a trade: not shown
]


@pytest.fixture
def tk_root(tmp_path, monkeypatch):
    import tkinter as tk
    from tkinter import ttk

    import ui_theme
    import ui_tokens

    monkeypatch.setattr(ui_table, "LAYOUT_PATH", str(tmp_path / "layout.json"))
    ui_table.forget_layouts()
    root, error = None, None
    for _ in range(10):
        try:
            root = tk.Tk()
            break
        except tk.TclError as exc:
            error = exc
    if root is None:
        pytest.skip(f"Tk not available: {error}")
    root.withdraw()
    ui_theme.apply_theme(root, ttk.Style(root), ui_tokens.DARK)
    yield root
    ui_table.forget_layouts()
    try:
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def view(tk_root):
    v = thv.TradeHistoryView(tk_root, now=lambda: NOW)
    v.pack(fill="both", expand=True)
    v.load(ROWS)
    return v


def shown(v, column):
    i = thv.COLUMNS.index(column)
    v.table.settle()
    return [str(v.tree.item(iid, "values")[i]) for iid in v.tree.get_children()]


def test_the_table_has_the_ten_columns_and_one_row_per_trade(view):
    titles = [view.table._titles[c] for c in thv.COLUMNS]
    assert titles == [
        "Time",
        "Side",
        "Source",
        "Pair",
        "Quantity",
        "Price",
        "Value",
        "Fees",
        "Realised PnL",
        "PnL %",
    ]
    assert len(view.tree.get_children()) == 6  # the deposit row is not a trade
    sell = [t for t in view.trades if t.source == "Neural" and t.side == "Sell"][0]
    cells = dict(zip(thv.COLUMNS, view.cells(sell)))
    assert cells["side"] == "Sell" and cells["pair"] == "BTC-USD"
    assert cells["qty"] == "0.002"
    assert cells["value"] == "$122.00"  # quantity x price
    assert cells["fees"] == "$0.20"
    assert cells["realised"] == "+$1.50"
    assert cells["pnl_pct"] == "+3.20%"
    assert cells["time"] == time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(NOW - 30 * HOUR)
    )


@pytest.mark.parametrize(
    "tag, side, source, text",
    [
        (None, "buy", "Neural", "Neural"),
        ("TRAIL_SELL", "sell", "Neural", "Neural"),
        ("DCA", "buy", "DCA", "DCA"),
        ("ENTRY", "buy", "Strategy", "Strategy"),
        ("EXIT:strategy", "sell", "Strategy", "Strategy"),
        ("EXIT:OVL-PLOCK", "sell", "Strategy", "Strategy (Profit lock stages)"),
        ("EXIT:stop:OVL-ATR", "sell", "Strategy", "Strategy (ATR trailing stop)"),
        ("MANUAL", "buy", "Manual", "Manual"),
        ("SOMETHING_NEW", "buy", "SOMETHING_NEW", "SOMETHING_NEW"),
    ],
)
def test_the_source_is_what_the_row_records(tag, side, source, text):
    trade = thv.trade_of({"side": side, "tag": tag, "symbol": "BTC-USD"})
    assert (trade.source, trade.source_text) == (source, text)


def test_realised_pnl_is_a_sells_and_pnl_pct_a_sells_or_dca_buys():
    buy = thv.trade_of(row(1, "buy", None, "BTC-USD", 1, 2, pnl_pct=4.0))
    dca = thv.trade_of(row(1, "buy", "DCA", "BTC-USD", 1, 2, pnl_pct=-4.0))
    assert buy.pnl_pct is None and buy.realised is None
    assert dca.pnl_pct == -4.0 and dca.realised is None


def test_newest_first_until_a_heading_is_clicked(view):
    times = shown(view, "time")
    assert times == sorted(times, reverse=True)
    assert view.table.sort_order == ("time", True)
    view.table.sort_by("price")
    prices = [ui_table.number_in(p) for p in shown(view, "price")]
    assert prices == sorted(prices)


def test_filters_and_sort_work_together_and_the_summary_follows(view):
    assert view.summary.cget("text").startswith("6 trades, fees $")
    view.coin_var.set("BTC")
    assert shown(view, "pair") == ["BTC-USD"] * 3
    assert view.summary.cget("text") == ("3 trades, fees $0.40, realised PnL +$1.50")
    view.table.sort_by("price", descending=True)
    assert shown(view, "price") == ["$61,000", "$60,000", "$57,000"]
    view.side_var.set("Buy")  # the sort holds through a new filter
    assert shown(view, "price") == ["$60,000", "$57,000"]
    assert view.summary.cget("text").startswith("2 trades, fees $0.20")
    view.source_var.set("DCA")
    assert shown(view, "source") == ["DCA"]
    assert view.summary.cget("text") == "1 trade, fees $0.10, realised PnL +$0.00"
    view.clear_filters()
    assert len(view.tree.get_children()) == 6
    assert view.table.sort_order == ("price", True)  # clearing filters keeps the sort


def test_a_fee_not_recorded_is_unknown_not_zero(view):
    view.coin_var.set("ETH")
    assert "N/A" in shown(view, "fees")
    assert view.summary.cget("text") == (
        "2 trades, fees $0.10, realised PnL -$0.50 (1 with no fee recorded)"
    )


def test_the_period_and_a_custom_range(view):
    view.period_var.set("Last 24 hours")
    assert sorted(shown(view, "pair")) == ["ETH-USD", "ETH-USD", "SOL-USD"]
    view.period_var.set("Last 30 days")
    assert len(view.tree.get_children()) == 5
    view.period_var.set(thv.CUSTOM)
    assert str(view.from_entry.cget("state")) == "normal"
    ten_days_ago = time.strftime("%Y-%m-%d", time.localtime(NOW - 10 * DAY))
    view.from_var.set(ten_days_ago)
    view.to_var.set(ten_days_ago)  # one day, inclusive
    assert shown(view, "source") == ["DCA"]
    view.to_var.set("10/11/2026")
    assert "To: write the date as YYYY-MM-DD" in view.summary.cget("text")
    view.period_var.set("All time")
    assert str(view.from_entry.cget("state")) == "disabled"
    assert len(view.tree.get_children()) == 6


def test_the_search_looks_in_every_column(view):
    view.search_var.set("profit lock")
    view._search_now()
    assert shown(view, "pair") == ["ETH-USD"]
    view.search_var.set("btc-usd sell")
    view._search_now()
    assert shown(view, "source") == ["Neural"]
    view.search_var.set("n/a")
    view._search_now()
    assert shown(view, "fees") == ["N/A"]


def test_no_trades_and_no_match_say_so(tk_root):
    v = thv.TradeHistoryView(tk_root, now=lambda: NOW)
    v.pack(fill="both", expand=True)
    v.load([])
    v.table.settle()
    assert v.table.empty.cget("text") == "No trades yet" and v.table.is_empty_shown()
    assert v.summary.cget("text") == "0 trades, fees $0.00, realised PnL +$0.00"
    v.load(ROWS)
    v.coin_var.set("BTC")
    v.side_var.set("Sell")
    v.source_var.set("Manual")
    v.table.settle()
    assert v.table.empty.cget("text") == "No trades match these filters"
    assert v.table.is_empty_shown()


# ---- in the hub ----


@pytest.fixture
def hub(monkeypatch):
    import helpers_trainer as ht

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    yield hub
    ht.close_hub(hub)


def test_the_hub_shows_every_trade_of_the_history_file(hub):
    os.makedirs(os.path.dirname(hub.trade_history_path), exist_ok=True)
    with open(hub.trade_history_path, "w", encoding="utf-8") as f:
        for n in range(300):  # the list view showed the last 250 lines only
            f.write(json.dumps(row(n, "buy", "DCA", "BTC-USD", 0.001, 50000.0)) + "\n")
    hub._refresh_trade_history()
    view = hub.trade_history_view
    assert len(view.trades) == 300 and len(view.tree.get_children()) == 300
    assert view.summary.cget("text").startswith("300 trades")
    assert hub.hist_filter_var is view.search_var


def test_long_term_holdings_are_holdings_db_entries_apart_from_the_account(hub):
    import pt_hub
    import pt_paths
    from long_term_holdings import Holding, HoldingsDatabase

    tab = hub.bottom_notebook.tabs()[1]
    texts = [
        w.cget("text")
        for w in hub.nametowidget(tab).winfo_children()
        if w.winfo_class() == "TLabel"
    ]
    assert texts == [pt_hub.LONG_TERM_HOLDINGS_SUBTITLE]
    assert pt_hub.LONG_TERM_HOLDINGS_SUBTITLE == (
        "Manual HODL positions, tracked separately from the trading account. "
        "Not included in Value, Buying Power or % in Trade."
    )
    assert hub.lth_tree.heading("allocation", "text") == "% of Holdings"

    path = pt_paths.data_file("holdings.db")
    hub._refresh_long_term_holdings()  # no holdings.db: nothing shown, none made
    hub.lth_table.settle()
    assert not os.path.exists(path) and hub.lth_table.is_empty_shown()
    assert hub.lth_table.empty.cget("text") == "No holdings yet"

    account = [
        hub.lbl_acct_total_value.cget("text"),
        hub.lbl_acct_buying_power.cget("text"),
        hub.lbl_acct_percent_in_trade.cget("text"),
    ]
    db = HoldingsDatabase(path)
    db.add_holding(
        Holding(symbol="BTC", quantity=0.5, average_cost=40000.0, current_price=60000.0)
    )
    db.add_holding(
        Holding(symbol="DOT", quantity=100, average_cost=5.0, current_price=10.0)
    )
    hub._refresh_long_term_holdings()
    rows = {
        hub.lth_tree.item(i, "values")[0]: hub.lth_tree.item(i, "values")
        for i in hub.lth_tree.get_children()
    }
    assert set(rows) == {"BTC", "DOT"}
    # the share of the holdings' own value: 30,000 and 1,000 of 31,000
    assert rows["BTC"][7] == "96.77%" and rows["DOT"][7] == "3.23%"
    assert rows["BTC"][5] == "+$10,000.00"
    # the account's figures are untouched
    assert account == [
        hub.lbl_acct_total_value.cget("text"),
        hub.lbl_acct_buying_power.cget("text"),
        hub.lbl_acct_percent_in_trade.cget("text"),
    ]
