"""The Account panel's profit figures (Realized, Unrealized, Since start, each
explained on hover) and the Account chart's trade dots and timeframe (owner,
2026-11-04: "the chart shows we are slowly making a profit, but the account
section doesn't reflect that")."""

import json
import os
import tkinter as tk
from tkinter import ttk

import pytest
from matplotlib.colors import to_hex

import pt_hub
import trading_mode as tm

HOUR = 3600
T0 = 1_700_000_000 - 1_700_000_000 % HOUR


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def write_lines(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


# --- the figures -----------------------------------------------------------------


@pytest.mark.parametrize(
    "value, text, style",
    [
        (0.104, "+$0.10", "Good.TLabel"),
        (-1234.5, "-$1,234.50", "Bad.TLabel"),
        (0.004, "$0.00", "TLabel"),  # rounds to nothing: neither green nor red
        (-0.004, "$0.00", "TLabel"),
        (None, "N/A", "TLabel"),
        (float("nan"), "N/A", "TLabel"),
        ("1.5", "+$1.50", "Good.TLabel"),  # as a JSON file may hold it
    ],
)
def test_a_profit_is_signed_and_coloured(value, text, style):
    assert pt_hub._fmt_profit(value) == (text, style)


def position(qty, cost, bid, ask=None):
    return {
        "quantity": qty,
        "avg_cost_basis": cost,
        "current_sell_price": bid,
        "current_buy_price": bid if ask is None else ask,
    }


def test_unrealized_is_what_the_coins_held_would_sell_for_minus_their_cost():
    positions = {
        "BTC": position(0.001, 60000.0, 61000.0, ask=61500.0),  # +1.00 at the bid
        "ETH": position(0.5, 3000.0, 2990.0),  # -5.00
        "SOL": position(0.0, 0.0, 0.0),  # not held
    }
    assert pt_hub.unrealized_profit(positions) == pytest.approx(-4.0)
    assert pt_hub.unrealized_profit({}) == 0.0
    # a coin held without a cost or a bid: the figure is not known
    no_cost = dict(positions, XRP=position(10.0, 0.0, 0.5))
    no_bid = dict(positions, XRP=position(10.0, 0.4, 0.0))
    for broken in (no_cost, no_bid, {"BTC": "junk"}, []):
        assert pt_hub.unrealized_profit(broken) is None


def test_the_starting_balance_comes_from_the_saved_paper_book(tmp_path):
    path = tm.paper_book_path(str(tmp_path))
    assert pt_hub.paper_starting_balance(path) is None  # no book yet
    assert pt_hub.paper_starting_balance(None) is None
    tm.write_paper_book(
        path, tm.validate_paper_book("50", "34", {"BTC": ("0.0001", "80000")})
    )
    assert pt_hub.paper_starting_balance(path) == 50.0
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json")
    assert pt_hub.paper_starting_balance(path) is None


# --- the Account panel ---------------------------------------------------------


@pytest.fixture
def hub(monkeypatch):
    import helpers_trainer as ht

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    yield hub
    ht.close_hub(hub)


# $50 start, two coins bought for $8.00 each, both now worth $8.05 at the bid
STATUS = {
    "timestamp": T0,
    "trading_mode": "paper",
    "account": {
        "total_account_value": 50.10,
        "buying_power": 34.00,
        "holdings_sell_value": 16.10,
        "percent_in_trade": 32.14,
    },
    "positions": {
        "BTC": position(0.0001, 80000.0, 80500.0, ask=80510.0),
        "ETH": position(0.004, 2000.0, 2012.5, ask=2013.0),
    },
}


def show(hub, status, start="50", realized=0.0):
    write_json(hub.trader_status_path, status)
    book = tm.paper_book_path(hub.hub_dir)
    if start is not None:
        tm.write_paper_book(book, tm.validate_paper_book(start, "34", {}))
        # the book is older than the trader's report, so the report is shown
        t = os.path.getmtime(hub.trader_status_path) - 10
        os.utime(book, (t, t))
    write_json(hub.pnl_ledger_path, {"total_realized_profit_usd": realized})
    hub._last_trader_status_mtime = None
    hub._last_pnl_mtime = object()
    hub._refresh_trader_status()
    hub._refresh_pnl()


def figure(label):
    return str(label.cget("text")), str(label.cget("style"))


def test_the_panel_shows_the_profit_on_coins_still_held(hub):
    show(hub, STATUS)
    assert figure(hub.lbl_pnl) == ("$0.00", "TLabel")  # nothing sold yet
    assert figure(hub.lbl_acct_unrealized) == ("+$0.10", "Good.TLabel")
    assert figure(hub.lbl_acct_since_start) == ("+$0.10 (+0.20%)", "Good.TLabel")
    # a sale: its profit moves to Realized
    sold = dict(STATUS, positions={"ETH": STATUS["positions"]["ETH"]})
    show(hub, sold, realized=0.05)
    assert figure(hub.lbl_pnl) == ("+$0.05", "Good.TLabel")
    assert figure(hub.lbl_acct_unrealized) == ("+$0.05", "Good.TLabel")
    # a loss is red
    falling = dict(STATUS, account=dict(STATUS["account"], total_account_value=49.0))
    falling["positions"] = {"BTC": position(0.0001, 80000.0, 70000.0)}
    show(hub, falling, realized=-2.5)
    assert figure(hub.lbl_pnl) == ("-$2.50", "Bad.TLabel")
    assert figure(hub.lbl_acct_unrealized) == ("-$1.00", "Bad.TLabel")
    assert figure(hub.lbl_acct_since_start) == ("-$1.00 (-2.00%)", "Bad.TLabel")


def test_the_figures_say_not_known_rather_than_guess(hub):
    no_cost = dict(STATUS, positions={"BTC": position(0.0001, 0.0, 80500.0)})
    show(hub, no_cost, start=None)
    assert figure(hub.lbl_acct_unrealized)[0] == "N/A"
    assert figure(hub.lbl_acct_since_start)[0] == "N/A"  # no starting balance saved
    # no report from the trader at all
    os.remove(hub.trader_status_path)
    hub._last_trader_status_mtime = None
    hub._refresh_trader_status()
    assert figure(hub.lbl_acct_unrealized)[0] == "N/A"
    assert figure(hub.lbl_acct_since_start)[0] == "N/A"


def test_the_saved_paper_book_has_no_prices_so_unrealized_is_not_known(hub):
    book = tm.paper_book_path(hub.hub_dir)
    tm.write_paper_book(
        book, tm.validate_paper_book("50", "34", {"BTC": ("0.0002", "80000")})
    )
    hub._last_trader_status_mtime = None
    hub._refresh_trader_status()  # no report from the trader: the book is shown
    assert "saved paper account" in str(hub.lbl_acct_total_value.cget("text"))
    assert figure(hub.lbl_acct_unrealized)[0] == "N/A"
    assert figure(hub.lbl_acct_since_start) == ("$0.00 (0.00%)", "TLabel")


def test_since_start_is_shown_for_the_paper_account_only(hub):
    key, value = hub.lbl_acct_since_start_key, hub.lbl_acct_since_start
    show(hub, STATUS)
    assert key.winfo_manager() == value.winfo_manager() == "grid"
    paper_status = hub.trader_status_path
    # a live account has no starting balance to measure from
    hub.trader_status_path = os.path.join(hub.hub_dir, "live", "trader_status.json")
    show(hub, STATUS, start=None)
    assert key.winfo_manager() == value.winfo_manager() == ""
    assert figure(hub.lbl_acct_unrealized) == ("+$0.10", "Good.TLabel")
    hub.trader_status_path = paper_status
    show(hub, STATUS)
    assert key.winfo_manager() == value.winfo_manager() == "grid"
    assert int(key.grid_info()["row"]) == 5 and int(value.grid_info()["column"]) == 1


def account_widgets(hub):
    (box,) = [
        w
        for w in all_widgets(hub)
        if isinstance(w, ttk.LabelFrame) and str(w.cget("text")) == "Account"
    ]
    return all_widgets(box)


def all_widgets(parent):
    out = []
    for child in parent.winfo_children():
        out.append(child)
        out.extend(all_widgets(child))
    return out


def hover_text(widget):
    widget.event_generate("<Enter>")
    try:
        (tip,) = [w for w in widget.winfo_children() if isinstance(w, tk.Toplevel)]
        return str(tip.winfo_children()[0].cget("text"))
    finally:
        widget.event_generate("<Leave>")


def test_hovering_a_profit_figure_explains_it(hub):
    widgets = account_widgets(hub)
    names = {
        str(w.cget("text")): w
        for w in widgets
        if isinstance(w, ttk.Label)
        and str(w.cget("text")) in ("Realized", "Unrealized", "Since start")
    }
    assert set(names) == {"Realized", "Unrealized", "Since start"}
    for name, value, tip in (
        ("Realized", hub.lbl_pnl, pt_hub.REALIZED_TIP),
        ("Unrealized", hub.lbl_acct_unrealized, pt_hub.UNREALIZED_TIP),
        ("Since start", hub.lbl_acct_since_start, pt_hub.SINCE_START_TIP),
    ):
        assert hover_text(names[name]) == tip  # the word
        assert hover_text(value) == tip  # and its figure
        assert tip.startswith(name + ": ")
    # the two words people mix up, told apart
    assert "already sold" in pt_hub.REALIZED_TIP
    assert "still held" in pt_hub.UNREALIZED_TIP
    # Unrealized sits beside Realized, Since start on the row under them
    assert hub.lbl_acct_unrealized.grid_info()["row"] == hub.lbl_pnl.grid_info()["row"]


# --- the Account chart ---------------------------------------------------------


@pytest.fixture
def root():
    win, error = None, None
    for _ in range(10):  # Tk sometimes fails to read init.tcl on Windows
        try:
            win = tk.Tk()
            break
        except tk.TclError as exc:
            error = exc
    if win is None:
        pytest.skip(f"Tk cannot start: {error}")
    win.withdraw()
    yield win
    win.destroy()


def dots(chart):
    """(label, colour) of each trade dot, in the order drawn."""
    colours = [to_hex(c.get_facecolor()[0]) for c in chart.ax.collections]
    return list(zip([t.get_text() for t in chart.ax.texts], colours))


def points_shown(chart):
    return len(chart.ax.lines[0].get_xdata())


def hourly_history(path, hours):
    write_lines(
        path,
        [
            {"ts": T0 + k * HOUR, "total_account_value": 50.0 + k * 0.01}
            for k in range(hours)
        ],
    )


def test_the_account_chart_draws_sells_as_well_as_buys(root, tmp_path):
    history, trades = tmp_path / "history.jsonl", tmp_path / "trades.jsonl"
    hourly_history(history, 48)
    write_lines(
        trades,
        [
            {"ts": T0 + 2 * HOUR, "side": "buy", "tag": "ENTRY", "symbol": "BTC-USD"},
            {"ts": T0 + 5 * HOUR, "side": "buy", "tag": "DCA", "symbol": "BTC-USD"},
            {
                "ts": T0 + 9 * HOUR,
                "side": "sell",
                "tag": None,
                "symbol": "BTC-USD",
                "closes_position": True,
            },
            {"ts": T0 + 10 * HOUR, "side": "SELL", "symbol": "ETH-USD"},
        ],
    )
    chart = pt_hub.AccountValueChart(root, str(history), str(trades))
    chart.refresh()
    m = {k: to_hex(v) for k, v in pt_hub.MARKERS.items()}
    assert dots(chart) == [
        ("BTC BUY", m["buy"]),
        ("BTC DCA", m["dca"]),
        ("BTC SELL", m["sell"]),
        ("ETH SELL", m["sell"]),
    ]
    assert m["sell"] != m["buy"]


def test_the_timeframe_sets_the_period_shown(root, tmp_path):
    history, trades = tmp_path / "history.jsonl", tmp_path / "trades.jsonl"
    hourly_history(history, 240)  # ten days, a value each hour
    newest = T0 + 239 * HOUR
    write_lines(
        trades,
        [
            {"ts": T0 + 24 * HOUR, "side": "buy", "symbol": "BTC-USD"},  # day 2
            {"ts": newest - 2 * HOUR, "side": "sell", "symbol": "BTC-USD"},
        ],
    )
    chart = pt_hub.AccountValueChart(
        root, str(history), str(trades), timeframe="1hour", bars=lambda: 120
    )
    chart.refresh()
    # 120 one-hour bars back from the newest value, as a coin chart on 1hour shows
    assert points_shown(chart) == 121
    assert [label for label, _ in dots(chart)] == ["BTC SELL"]
    assert chart.ax.lines[0].get_ydata()[-1] == pytest.approx(50.0 + 2.39)
    chart.set_timeframe("1day")  # redraws at once, though no file changed
    assert points_shown(chart) == 240
    assert [label for label, _ in dots(chart)] == ["BTC BUY", "BTC SELL"]
    chart.set_timeframe("1min")  # two hours: the sell is on the first value shown
    assert points_shown(chart) == 3
    assert [label for label, _ in dots(chart)] == ["BTC SELL"]


def test_the_number_of_bars_follows_the_candles_limit(root, tmp_path):
    history = tmp_path / "history.jsonl"
    hourly_history(history, 240)
    limit = {"bars": 24}
    chart = pt_hub.AccountValueChart(
        root,
        str(history),
        str(tmp_path / "none.jsonl"),
        timeframe="1hour",
        bars=lambda: limit["bars"],
    )
    chart.refresh()
    assert points_shown(chart) == 25
    assert chart.period_seconds() == 24 * HOUR
    limit["bars"] = 48
    chart.refresh()  # the period changed, so it redraws
    assert points_shown(chart) == 49
    chart.timeframe_var.set("not a timeframe")
    chart.refresh()
    assert points_shown(chart) == 240  # the whole history


def test_the_hub_gives_the_account_chart_the_default_timeframe_and_keeps_it(hub):
    chart = hub.account_chart
    assert chart.timeframe_var.get() == hub.settings["default_timeframe"]
    hub.settings["candles_limit"] = 24
    assert chart.period_seconds() == 24 * HOUR  # 1hour by default
    chart.set_timeframe("1day")
    hub._rebuild_coin_chart_tabs()  # e.g. after the coin list changed
    assert hub.account_chart is not chart
    assert hub.account_chart.timeframe_var.get() == "1day"
    assert hub.chart_tf_combo.get() == "1day"  # the hub opens on ACCOUNT
