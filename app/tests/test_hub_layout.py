"""The compact Controls pane: Account grid with the trader row, the coin table
(training status and the runner's long/short counts), the Controls/Live Output
split and coloured logs.

Runs under the isolation guard (app/conftest.py); the real-hub test uses a hidden
window and processes no events.
"""

import os
import queue
import sys
import types
from tkinter import ttk
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_hub  # noqa: E402

Hub = pt_hub.PowerTraderHub


@pytest.mark.parametrize(
    "line, tag",
    [
        ('[RUNNER] EXCEPTION IN (LINE 12 "x"): boom', "log_error"),
        ("[RUNNER] Error in main loop: boom", "log_error"),
        ("[BTC] [process exited, code 2]", "log_error"),
        ("[RUNNER] [process exited, code 0]", "log_state"),
        (
            "[RUNNER] [training BTC: the runner skips BTC until its new model is saved]",
            "log_state",
        ),
        ("[RUNNER] [stopped with the ■ button]", "log_state"),
        (
            "[RUNNER] Initialization complete. Starting main processing loop...",
            "log_state",
        ),
        ("[RUNNER] ZEC  (NOT TRAINED / OUTDATED - run trainer)", "log_warn"),
        (
            "[RUNNER] BTC  (TRAINING - no signals until the new model is saved)",
            "log_warn",
        ),
        ("[RUNNER] XRP  (WAITING FOR PRICE DATA - CoinDataError: x)", "log_warn"),
        ("[RUNNER] LONG on 1hour timeframe. 0.5 Low Boundary: 1", "log_long"),
        ("[RUNNER] SHORT on 4hour timeframe. -0.2 High Boundary: 2", "log_short"),
        ("[RUNNER] WITHIN on 1day timeframe.", "log_dim"),
        ("[RUNNER] Processing BTC...", "log_dim"),
        ("[RUNNER] Completed iteration 4, sleeping...", "log_dim"),
        ("[RUNNER] =========================================", "log_dim"),
        ("[RUNNER] === BTC ===", "log_dim"),
        ("[TRADER] Paper trader started", None),
        # a stop the hub asked for is not a crash
        ("[RUNNER] [process exited, code 1 - stopped from the hub]", "log_state"),
        (
            "[X] [process exited - log lost, the process may still be running]",
            "log_warn",
        ),
        # the trader's most serious lines
        ("[TRADER] EMERGENCY STOP: Account drawdown 21.0% exceeds 20%", "log_error"),
        ("[TRADER] Trading halted until manual intervention", "log_error"),
        ("[TRADER] RISK HALT: daily loss limit reached", "log_error"),
        ("[TRADER] ORDER FAILED (BTC buy): insufficient funds", "log_error"),
        ("[TRADER] ORDER REFUSED: live trading is not enabled", "log_error"),
        ("[TRADER] RISK BLOCK: position limit", "log_warn"),
        ("[TRADER] ORDER REJECTED (min notional)", "log_warn"),
        ("[RUNNER] Error getting price from coinbase: timeout", "log_error"),
        ("[RUNNER] INACTIVE (training data issue) on 1hour timeframe.", "log_warn"),
        ("[RUNNER] Skipping XMR: Coinbase has no market XMR-USD", "log_warn"),
        ("[TRADER] No holdings found. Skipping DCA levels initialization.", None),
    ],
)
def test_log_lines_are_tagged_by_kind(line, tag):
    assert pt_hub._log_line_tag(line) == tag


class FakeText:
    def __init__(self, at_bottom, height=200):
        self.bottom, self.inserted, self.seen = at_bottom, [], 0
        self.height = height

    def winfo_height(self):
        return self.height

    def yview(self):
        return (0.5, 1.0 if self.bottom else 0.6)

    def insert(self, index, text, tags=()):
        self.inserted.append((text, tags))

    def index(self, _):
        return f"{len(self.inserted) + 1}.0"

    def delete(self, *_):
        pass

    def see(self, _):
        self.seen += 1


@pytest.mark.parametrize(
    "at_bottom, height, follows",
    [
        (True, 200, 1),
        (False, 200, 0),  # the user is reading older lines
        (False, 1, 1),  # a tab never opened yet: still follows, opens on new lines
    ],
)
def test_the_log_follows_new_lines_only_when_scrolled_to_the_bottom(
    at_bottom, height, follows
):
    q = queue.Queue()
    q.put("[RUNNER] LONG on 1hour timeframe.")
    q.put("[RUNNER] plain line")
    txt = FakeText(at_bottom, height)
    Hub._drain_queue_to_text(types.SimpleNamespace(), q, txt)
    assert txt.inserted == [
        ("[RUNNER] LONG on 1hour timeframe.\n", ("log_long",)),
        ("[RUNNER] plain line\n", ()),
    ]
    assert txt.seen == follows


@pytest.mark.parametrize(
    "requested, total, target",
    [
        (300, 900, 302),  # Controls gets what it asks for
        (100, 900, 160),  # never less than 160
        (800, 900, 450),  # at most half, or 450 when that is more
        (800, 1400, 700),  # half of a tall window
        (800, 500, 380),  # Live Output keeps at least 120
    ],
)
def test_the_controls_split_fits_its_content_within_limits(requested, total, target):
    assert pt_hub._left_split_target(requested, total) == target


class FakeLabel:
    def __init__(self):
        self.calls = []

    def configure(self, **kw):
        self.calls.append(kw)


def test_training_cells_are_updated_in_place_and_only_when_changed():
    cells = {c: tuple(FakeLabel() for _ in range(5)) for c in ("ZEC", "BTC")}
    hub = types.SimpleNamespace(
        coins=["ZEC", "BTC"],
        _training_table_coins=("ZEC", "BTC"),
        _training_cells=cells,
        _training_cell_state={},
        _build_training_table=mock.Mock(),
        _get_training_hours=lambda coin: "1.5h",
    )
    hub._get_status_border_color = (
        lambda status, coin=None: Hub._get_status_border_color(hub, status, coin)
    )
    Hub._update_training_table(hub, {"ZEC": "●", "BTC": "✅"})
    _, zec_dot, _, zec_age, _ = cells["ZEC"]
    _, btc_dot, _, btc_age, _ = cells["BTC"]
    assert zec_dot.calls == [{"text": "●", "fg": pt_hub.STATUS_AMBER}]
    assert zec_age.calls == [{"text": "training"}]
    assert btc_dot.calls == [{"text": "●", "fg": pt_hub.STATUS_GREEN}]
    assert btc_age.calls == [{"text": "1.5h"}]
    Hub._update_training_table(hub, {"ZEC": "●", "BTC": "✅"})
    assert len(zec_dot.calls) == 1 and len(btc_age.calls) == 1  # nothing changed
    Hub._update_training_table(hub, {"ZEC": "○", "BTC": "✅"})  # the training blink
    assert zec_dot.calls[-1] == {"text": "○", "fg": pt_hub.STATUS_AMBER}
    hub._build_training_table.assert_not_called()


def test_a_changed_coin_list_rebuilds_the_training_table():
    hub = types.SimpleNamespace(
        coins=["ZEC", "BTC", "ETH"],
        _training_table_coins=("ZEC", "BTC"),
        _training_cells={},
        _training_cell_state={},
    )
    hub._build_training_table = mock.Mock()
    Hub._update_training_table(hub, {})
    hub._build_training_table.assert_called_once()


@pytest.fixture
def hub(monkeypatch):
    import helpers_trainer as ht

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    yield hub
    ht.close_hub(hub)


def all_widgets(parent):
    out = []
    for child in parent.winfo_children():
        out.append(child)
        out.extend(all_widgets(child))
    return out


def test_the_controls_pane_is_compact(hub):
    frames = [w for w in all_widgets(hub) if isinstance(w, ttk.LabelFrame)]
    titles = [str(w.cget("text")) for w in frames]
    assert "Trading (Exchanges)" not in titles  # folded into the Account box
    assert "Thinking (Signals)" not in titles  # its counts are in the coin table
    assert {"Account", "Coins"} <= set(titles)
    (account,) = [w for w in frames if str(w.cget("text")) == "Account"]
    inside = all_widgets(account)
    for name in (
        "lbl_trader",
        "lbl_exchange",
        "btn_start_trader",
        "btn_stop_trader",
        "lbl_acct_total_value",
        "lbl_acct_buying_power",
        "lbl_acct_holdings_value",
        "lbl_acct_percent_in_trade",
        "lbl_acct_dca_single",
        "lbl_acct_dca_spread",
        "lbl_pnl",
    ):
        assert getattr(hub, name) in inside, name
    keys = [str(w.cget("text")) for w in inside if isinstance(w, ttk.Label)]
    assert {"Value", "Buying Power", "Holdings", "% in Trade", "DCA Single"} <= set(
        keys
    )
    assert list(hub._training_cells) == list(hub.coins)  # one cell per coin
    (coins,) = [w for w in frames if str(w.cget("text")) == "Coins"]
    for name in ("lbl_neural", "btn_start_neural", "btn_stop_neural"):
        assert getattr(hub, name) in all_widgets(coins), name
    hub._tick()  # the refresh loop runs with the new widgets
    assert str(hub.lbl_trader.cget("text")) == "stopped"


class SigLabel:
    def __init__(self):
        self.text, self.fg, self.calls = None, None, 0

    def configure(self, text, fg):
        self.text, self.fg, self.calls = text, fg, self.calls + 1


@pytest.mark.parametrize(
    "longs, shorts, age, level, text, colour",
    [
        (None, None, None, 3, "–", "MUTED"),  # no signal file
        (4, 0, 10, 3, "L4 S0", pt_hub.STATUS_GREEN),
        (3, 0, 10, 3, "L3 S0", pt_hub.STATUS_GREEN),  # the trader starts at 3
        (2, 0, 10, 3, "L2 S0", "FG"),  # below the start level: no trade
        (1, 0, 10, 1, "L1 S0", pt_hub.STATUS_GREEN),
        (4, 2, 10, 3, "L4 S2", pt_hub.LOG_SHORT),
        (0, 0, 10, 3, "L0 S0", "FG"),
        (4, 0, 16 * 60, 3, "L4 S0", "MUTED"),  # the trader ignores it now
    ],
)
def test_a_cell_shows_the_signal_counts(longs, shorts, age, level, text, colour):
    """A palette key (FG, MUTED) is the active palette's colour: dark or paper."""
    import time

    import ui_theme

    colour = ui_theme.active_palette().get(colour, colour)
    hub = types.SimpleNamespace(_training_signal_state={})
    label = SigLabel()
    mtime = None if age is None else time.time() - age
    Hub._show_signal_counts(hub, "BTC", label, longs, shorts, mtime, level)
    assert (label.text, label.fg) == (text, colour)
    Hub._show_signal_counts(hub, "BTC", label, longs, shorts, mtime, level)
    assert label.calls == 1  # unchanged: not touched again


def test_the_counts_are_read_from_each_coins_signal_files(tmp_path):
    btc, eth = tmp_path / "btc", tmp_path / "eth"
    btc.mkdir()
    eth.mkdir()
    (btc / "long_dca_signal.txt").write_text("5")
    (btc / "short_dca_signal.txt").write_text("0")
    labels = {c: SigLabel() for c in ("BTC", "ETH", "ZEC")}
    hub = types.SimpleNamespace(
        settings={"main_neural_dir": ""},
        coins=["BTC", "ETH", "ZEC"],
        _coin_folders_sig=("", ("BTC", "ETH", "ZEC")),  # keep these folders
        coin_folders={"BTC": str(btc), "ETH": str(eth), "ZEC": str(tmp_path / "none")},
        _training_cells={c: (None, None, None, None, labels[c]) for c in labels},
        _training_signal_state={},
        _neural_overview_cache={},
    )
    hub._show_signal_counts = lambda *a: Hub._show_signal_counts(hub, *a)
    Hub._refresh_neural_overview(hub)
    assert labels["BTC"].text == "L5 S0"
    assert labels["ETH"].text == "–"  # folder but no signal files yet
    assert labels["ZEC"].text == "–"  # no folder


def tooltip_hub(
    status="✅", signal=(3, 0, None, 3), engine="catalogue", trained_at=None, gate=None
):
    import time

    hub = types.SimpleNamespace(
        _training_status={"ZEC": status},
        last_training_times={"ZEC": trained_at or time.time() - 2 * 3600},
        settings={"training_auto_enabled": True, "training_auto_interval_hours": 6},
        _training_signal_info={"ZEC": signal},
        _signals_engine=engine,
        _gate_record=lambda coin: gate,
    )
    hub._gate_tooltip_line = lambda coin: Hub._gate_tooltip_line(hub, coin)
    return hub


def test_the_status_dot_explains_each_colour():
    tip = Hub._coin_tooltip(tooltip_hub("✅"), "ZEC", "status")
    assert "trained (green dot)" in tip and "less than 14 days" in tip
    tip = Hub._coin_tooltip(tooltip_hub("●"), "ZEC", "status")
    assert "training now (amber dot)" in tip and "skips ZEC" in tip
    tip = Hub._coin_tooltip(tooltip_hub("❌"), "ZEC", "status")
    assert "not trained (grey dot)" in tip and "no signals" in tip


def test_the_status_dot_gives_the_last_training_runs_entry_gate_result():
    from test_settings_tabs import gate_record

    def record(published, kept=None):
        return dict(gate_record(published, kept), coin="ZEC")

    tip = Hub._coin_tooltip(tooltip_hub(gate=record(True)), "ZEC", "status")
    assert (
        "Return after fees vs random: +2.00% vs -2.00% (99th percentile); passed the "
        "entry gate." in tip
    )
    kept = record(False, kept="ZEC-20251201T0000Z-aaaaaaaaaaaa")
    tip = Hub._coin_tooltip(tooltip_hub(gate=kept), "ZEC", "status")
    assert "less than 14 days old, so the neural runner uses it" in tip
    assert (
        "the new model did not pass the entry gate, so the model in use "
        "(ZEC-20251201T0000Z-aaaaaaaaaaaa) is kept" in tip
    )
    tip = Hub._coin_tooltip(tooltip_hub(gate=record(False)), "ZEC", "status")
    assert "none did before, so the neural runner gives ZEC no signals" in tip


def test_the_trained_for_time_says_when_and_how_long_it_lasts():
    tip = Hub._coin_tooltip(tooltip_hub("✅"), "ZEC", "age")
    assert "2.0 h ago, at " in tip
    assert "trained for 14 days" in tip
    assert "Auto-retrain: about every 6 h" in tip
    tip = Hub._coin_tooltip(tooltip_hub("❌"), "ZEC", "age")
    assert "never been trained" in tip


def test_the_signal_counts_explain_l_s_the_start_level_and_who_uses_them():
    import time

    tip = Hub._coin_tooltip(
        tooltip_hub(signal=(2, 0, time.time() - 30, 3)), "ZEC", "signal"
    )
    assert "L2 S0" in tip
    assert "price below their predicted low (long)" in tip
    assert "above their predicted high (short)" in tip
    assert "trade start level (3, Settings)" in tip
    assert "Updated 30 s ago." in tip
    assert "engine is catalogue, which does not use these counts" in tip
    tip = Hub._coin_tooltip(
        tooltip_hub(signal=(4, 0, time.time() - 20 * 60, 3), engine="legacy_neural"),
        "ZEC",
        "signal",
    )
    assert "Updated 20 min ago. Older than 15 minutes: the trader ignores it" in tip
    assert "these counts decide its new trades" in tip
    tip = Hub._coin_tooltip(tooltip_hub(signal=(None, None, None, 3)), "ZEC", "signal")
    assert "none yet" in tip and "two full sweeps" in tip


def test_each_coin_field_has_its_own_tooltip(hub):
    cell, dot, sym, age, sig = hub._training_cells[hub.coins[0]]
    for widget in (dot, sym, age, sig):
        assert widget.bind("<Enter>"), "no tooltip on a coin field"
    assert not cell.bind("<Enter>")  # not a second tooltip on the frame itself


# --- the bottom panel's module tabs (owner, 2026-11-04) -------------------------------


def test_the_module_tabs_follow_the_one_order_list(hub):
    """The tabs under the charts sit as MODULE_TAB_ORDER lists them, whatever order
    they were built in, and Current Trades is the one shown at start-up."""
    nb = hub.bottom_notebook
    names = [pt_hub.module_tab_name(nb.tab(t, "text")) for t in nb.tabs()]
    assert set(names) <= set(pt_hub.MODULE_TAB_ORDER)  # every tab is in the list
    assert names == [n for n in pt_hub.MODULE_TAB_ORDER if n in names]
    assert names[:2] == ["Current Trades", "Trade History"]
    assert nb.select() == nb.tabs()[0]
    order = list(pt_hub.MODULE_TAB_ORDER)
    assert order.index("Holdings Management") == order.index("Long-term Holdings") + 1
    # Order Management has the order types; there is no Advanced Orders tab (owner,
    # 2026-11-05)
    assert "Advanced Orders" not in order and "Advanced Orders" not in names


def test_the_tab_order_skips_missing_tabs_and_keeps_unlisted_ones_last(hub):
    """Built in any order, with a listed tab missing and one the list does not name:
    the listed ones come first in the list's order, the other keeps its place after."""
    nb = ttk.Notebook(hub)
    try:
        built = ["LLM Research", "Spare", "Market Data", "Current Trades"]
        for name in built:
            nb.add(ttk.Frame(nb), text=name.replace(" ", "\n", 1))
        real = hub.bottom_notebook
        hub.bottom_notebook = nb
        try:
            hub._order_module_tabs()
        finally:
            hub.bottom_notebook = real
        names = [pt_hub.module_tab_name(nb.tab(t, "text")) for t in nb.tabs()]
        assert names == ["Current Trades", "Market Data", "LLM Research", "Spare"]
    finally:
        nb.destroy()


# --- the chart tab row (owner, 2026-10-14) -------------------------------------------


def placed_on(hub) -> object:
    """The widget the Timeframe box and cog are placed on, or None."""
    overlay = hub._chart_overlay
    return overlay.place_info().get("in") if overlay.winfo_manager() else None


def test_the_timeframe_box_and_cog_sit_on_the_chart_top_right(hub):
    """Owner, 2026-11-04: the cog on the chart's top right corner, anchored to the
    chart, and the Timeframe box butted up against its left; the tab row keeps only
    the buttons and the status lines."""
    overlay, box, cog = hub._chart_overlay, hub._chart_tf_box, hub.chart_settings_button
    assert isinstance(hub.chart_tabs_bar, pt_hub.ScrollingRow)
    assert all(
        b.master is hub.chart_tabs_bar.inner for b in hub._chart_tab_buttons.values()
    )
    assert box.master is overlay and cog.master is overlay
    assert overlay.pack_slaves() == [box, cog]  # the box, then the cog at the right
    for widget in (box, cog):
        assert widget.pack_info()["padx"] in (0, (0, 0))  # no gap between them
    assert overlay not in hub._chart_tabs_row.winfo_children()
    for page in (hub.coins[0], "ACCOUNT"):
        hub._show_chart_page(page)
        chart = hub._chart_named(page)
        info = overlay.place_info()
        assert info["in"] is chart.canvas.get_tk_widget()  # the chart, not its page
        assert info["anchor"] == "ne"
        assert (float(info["relx"]), float(info["rely"])) == (1.0, 0.0)
        assert (int(info["x"]), int(info["y"])) == (0, 0)


def test_the_plot_starts_below_the_timeframe_box_and_cog(hub):
    """The chart shown gets the overlay's height, and its plot is fitted to start
    below it."""
    from matplotlib.figure import Figure

    for page in (hub.coins[0], "ACCOUNT"):
        hub._show_chart_page(page)
        chart = hub._chart_named(page)
        assert chart.overlay_px == hub._chart_overlay_px
    hub.update_idletasks()
    assert hub._chart_overlay_px() == hub._chart_overlay.winfo_reqheight() > 1
    fig = Figure(figsize=(6, 4), dpi=100)
    ax = fig.add_subplot(111)
    fig.canvas.draw()
    pt_hub._fit_axes(fig)
    height = fig.bbox.height
    assert pt_hub._top_below(fig, ax, 0, 1.0) == 1.0  # nothing to keep clear of
    reserve = height - ax.get_window_extent().y1 + 20
    top = pt_hub._top_below(fig, ax, reserve, 1.0)
    pt_hub._fit_axes(fig, 1.0, top)
    assert abs(ax.get_window_extent().y1 - (height - reserve)) <= 1
    assert pt_hub._top_below(fig, ax, reserve, top) == top  # clear already


def test_the_timeframe_box_and_cog_come_back_after_the_coins_change(hub):
    """The tab row and the pages are rebuilt when the coins change; the overlay is
    rebuilt with them and placed on the chart shown."""
    hub._show_chart_page(hub.coins[0])
    old = hub._chart_overlay
    hub._rebuild_coin_chart_tabs()
    assert not old.winfo_exists()
    page = hub._current_chart_page
    assert placed_on(hub) is hub._chart_named(page).canvas.get_tk_widget()
    assert hub._chart_overlay.pack_slaves() == [
        hub._chart_tf_box,
        hub.chart_settings_button,
    ]


def test_the_account_chart_fills_its_page_like_a_coin_chart(hub):
    """Owner, 2026-11-04: no "Account value" name and no "Last:" time above the
    account chart; its plot fills the page under the coin buttons."""
    chart = hub.account_chart
    assert chart.pack_slaves() == [chart.canvas.get_tk_widget()]
    info = chart.canvas.get_tk_widget().pack_info()
    assert info["fill"] == "both" and int(info["expand"])
    assert chart.pack_info()["fill"] == "both" and int(chart.pack_info()["expand"])
    texts = [
        str(w.cget("text")) for w in all_widgets(chart) if isinstance(w, ttk.Label)
    ]
    assert texts == []
    assert not hasattr(chart, "last_update_label")


def test_the_timeframe_box_follows_the_selected_chart(hub):
    box, combo = hub._chart_tf_box, hub.chart_tf_combo
    coin = hub.coins[0]
    chart = hub.charts[coin]
    other = [tf for tf in combo.cget("values") if tf != chart.timeframe_var.get()][0]
    hub._show_chart_page(coin)
    assert (
        box.winfo_manager() == "pack" and placed_on(hub) is chart.canvas.get_tk_widget()
    )
    assert combo.get() == chart.timeframe_var.get()
    combo.set(other)
    hub._on_chart_timeframe_selected()
    assert chart.timeframe_var.get() == other
    assert hub.charts[hub.coins[1]].timeframe_var.get() != other or len(hub.coins) < 2
    # the account chart (owner, 2026-11-04) has a timeframe of its own in the box
    account = hub.account_chart.timeframe_var
    hub._show_chart_page("ACCOUNT")
    assert placed_on(hub) is hub.account_chart.canvas.get_tk_widget()
    assert combo.get() == account.get() == hub.settings["default_timeframe"]
    combo.set("1day")
    hub._on_chart_timeframe_selected()
    assert account.get() == "1day" and chart.timeframe_var.get() == other
    hub._show_chart_page(coin)
    assert combo.get() == other


def test_the_coin_chart_toolbar_names_no_coin_and_has_no_timeframe_box(hub):
    chart = hub.charts[hub.coins[0]]
    widgets = all_widgets(chart)
    assert not any(isinstance(w, ttk.Combobox) for w in widgets)
    texts = [str(w.cget("text")) for w in widgets if isinstance(w, ttk.Label)]
    assert not any(t.endswith(" chart") or t == "Timeframe:" for t in texts)


def test_the_tab_row_scrolls_only_while_its_buttons_do_not_fit():
    import tkinter as tk

    root, error = None, None
    for _ in range(10):  # Tk sometimes fails to read init.tcl on the first try
        try:
            root = tk.Tk()
            break
        except tk.TclError as exc:
            error = exc
    if root is None:
        pytest.skip(f"Tk not available: {error}")
    root.withdraw()
    try:
        row = pt_hub.ScrollingRow(root)
        row.pack(fill="x")
        for k in range(10):
            row.add(ttk.Button(row.inner, text=f"COIN{k}"), padx=(0, 6))
        root.update_idletasks()
        # resizing the row or its buttons runs the fit
        assert row._canvas.bind("<Configure>") and row.inner.bind("<Configure>")
        # a hidden window gives every widget a width of 1, so the row's visible
        # width is set here
        visible = {"px": 300}
        row._canvas.winfo_width = lambda: visible["px"]
        needed = row.inner.winfo_reqwidth()
        assert needed > 300
        assert int(row._canvas.cget("width")) == needed  # it asks for all of it
        row._fit()
        assert row.scrolls
        visible["px"] = needed + 50
        row._fit()
        assert not row.scrolls  # wide enough: the scrollbar goes away
        visible["px"] = 300
        row._fit()
        assert row.scrolls
    finally:
        root.destroy()


def test_the_chart_tab_buttons_are_sized_to_their_text(hub):
    """Owner, 2026-10-14: 10 px from the text to each edge of the button."""
    import tkinter.font as tkfont

    style = ttk.Style(hub)
    font = tkfont.nametofont(
        style.lookup("ChartTab.TButton", "font") or "TkDefaultFont"
    )
    hub.update_idletasks()
    for text, button in hub._chart_tab_buttons.items():
        assert abs(button.winfo_reqwidth() - (font.measure(text) + 20)) <= 1, text
        assert abs(button.winfo_reqheight() - (font.metrics("linespace") + 20)) <= 1


def test_the_chart_settings_cog_opens_chart_settings_on_every_chart(hub):
    """Owner, 2026-10-14: the cog right of the Timeframe box; on the chart since
    2026-11-04, the account chart's too."""
    cog = hub.chart_settings_button
    assert str(cog.cget("text")) == "\u2699" and cog.master is hub._chart_overlay
    hub._show_chart_page(hub.coins[0])
    assert hub._chart_overlay.pack_slaves()[-1] is cog
    hub._show_chart_page("ACCOUNT")
    assert placed_on(hub) is hub.account_chart.canvas.get_tk_widget()  # it stays
    before = set(hub.winfo_children())
    cog.invoke()
    opened = [w for w in hub.winfo_children() if w not in before]
    assert len(opened) == 1  # the Chart settings window
    opened[0].destroy()


def test_the_charts_sit_5px_from_the_panel_edges(hub):
    """Owner, 2026-10-14: 5 px left, right and bottom."""
    info = hub.chart_pages_container.pack_info()
    assert info["padx"] in (5, (5, 5)) and info["pady"] == (0, 5)
    assert hub._chart_tabs_row.pack_info()["padx"] in (5, (5, 5))


def test_the_left_pane_starts_394px_wide(hub):
    """Owner: the divider 36 px further left (438 -> 402) on 2026-11-02, then 8 px
    more (394) on 2026-11-03, closing the strip right of the coin table. The window
    is never shown: the pane's width is stood in and the sash position the hub sets
    is recorded."""
    import time

    outer = hub._pw_outer
    placed = []
    read = outer.sashpos

    def sashpos(index, pos=None):
        if pos is None:  # the hub also reads it back
            return read(index)
        placed.append((index, pos))

    outer.winfo_width = lambda: 1500
    outer.sashpos = sashpos
    deadline = time.monotonic() + 5.0
    while not getattr(hub, "_did_init_outer_sash", False):
        assert time.monotonic() < deadline, "the divider was never placed"
        hub.update()
        time.sleep(0.01)
    assert placed == [(0, 394)]


def test_the_account_row_has_the_exchange_left_and_the_trader_by_its_buttons(hub):
    """Owner, 2026-11-02: Exchange first, its key grey like "Trading:" (owner,
    2026-11-03: "Trading" like the Training, Thinking and Trading tabs); the
    trader's state right-aligned beside its start and stop buttons."""
    row = hub.lbl_trader.master
    slaves = row.pack_slaves()
    trader_key = slaves[3]
    assert slaves == [
        hub.btn_stop_trader,
        hub.btn_start_trader,
        hub.lbl_trader,
        trader_key,
        hub.lbl_exchange_key,
        hub.lbl_exchange,
    ]
    assert str(trader_key.cget("text")) == "Trading:"
    for widget in slaves[:4]:
        assert widget.pack_info()["side"] == "right"
    for widget in slaves[4:]:
        assert widget.pack_info()["side"] == "left"
    assert str(hub.lbl_exchange_key.cget("text")) == "Exchange:"
    grey = str(trader_key.cget("foreground"))
    assert str(hub.lbl_exchange_key.cget("foreground")) == grey


def test_the_exchange_line_shows_its_state_by_colour_not_an_icon(hub):
    import ui_theme
    import ui_tokens

    p = ui_theme.active_palette()
    for status, tone, colour in (
        ("Coinbase", "ok", p["ACCENT2"]),
        ("Coinbase (no prices)", "warn", ui_tokens.STATUS["warn"]),
        ("Kraken (no live orders)", "bad", ui_tokens.STATUS["bad"]),
    ):
        hub._exchange_status = {"status": status, "details": "d", "tone": tone}
        hub._update_exchange_status_display()
        assert str(hub.lbl_exchange.cget("text")) == status
        assert str(hub.lbl_exchange.cget("foreground")).lower() == colour.lower()


def test_the_coin_table_fits_three_columns_with_no_gap_after_the_last(hub):
    """Owner, 2026-10-14: the left pane is 32 px narrower (438 px), so the column
    rule counts the 8 px gap between columns only, not after the last one."""
    hub.update_idletasks()  # measure the cells
    cells = hub._training_cells
    cell = max(c[0].winfo_reqwidth() for c in cells.values())
    assert cell > 50
    for width, cols in ((3 * cell + 2 * 8, 3), (3 * cell + 2 * 8 - 1, 2)):
        hub.training_status_frame.winfo_width = lambda w=width: w
        hub._training_table_cols = 0  # lay out again
        hub._layout_training_table()
        assert hub._training_table_cols == cols, width
    rows = -(-len(cells) // 2)  # the last layout: two columns
    for i, coin in enumerate(hub._training_table_coins):
        padx = cells[coin][0].grid_info()["padx"]
        if i // rows == 0:
            assert padx == (0, 8)
        else:
            assert padx in (0, (0, 0))  # no gap after the last column


def test_the_chart_settings_cog_has_no_visible_border(hub):
    """Owner, 2026-10-14: no border round the cog. Its border is painted in its own
    background colour, idle and while hovered, so it keeps the tab buttons' height."""
    cog = hub.chart_settings_button
    style = ttk.Style(hub)
    name = str(cog.cget("style"))
    assert name == "ChartCog.TButton"
    # idle it takes the chart's background, which it sits on, in either mode
    # (paper mode recolours the frames blue, not the chart); so do the overlay's
    # frames and its Timeframe label
    chart_bg = pt_hub.CHART["figure"]
    assert style.lookup(name, "background") == chart_bg
    for widget in [hub._chart_overlay] + all_widgets(hub._chart_overlay):
        if isinstance(widget, (ttk.Frame, ttk.Label)):
            assert style.lookup(str(widget.cget("style")), "background") == chart_bg
    for state in ([], ["active"], ["pressed"]):
        bg = style.lookup(name, "background", state)
        for edge in ("bordercolor", "lightcolor", "darkcolor", "focuscolor"):
            assert style.lookup(name, edge, state) == bg, (state, edge)
    hub.update_idletasks()
    tab = hub._chart_tab_buttons["ACCOUNT"]
    assert cog.winfo_reqheight() == tab.winfo_reqheight()


def test_coin_charts_learn_whether_the_trader_is_running(hub, monkeypatch):
    """ASK/BID are drawn dotted while the trader is stopped, so every coin-chart
    refresh says whether it runs, by the same rule as the "Trading:" label."""
    import time

    assert hub._trader_is_running() is False  # no trader started in tests
    coin = hub.coins[0]
    seen = []
    monkeypatch.setattr(hub.charts[coin], "refresh", lambda *a, **k: seen.append(k))
    hub._show_chart_page(coin)  # refreshes the shown chart on the next tick
    deadline = time.time() + 2
    while not seen and time.time() < deadline:
        hub.update()
    assert seen and seen[-1].get("trader_running") is False


def test_the_status_line_sits_in_the_tab_row_after_the_buttons(hub):
    """Owner, 2026-10-14: the selected coin chart's status line (neural readout,
    pattern count) sits right of the coin buttons, outside their scroll area, and
    the chart has no status row above its plot any more. Since 2026-11-04 it is two
    lines, the neural readout above the pattern count, out to the row's right edge."""
    row, slot, bar = hub._chart_tabs_row, hub._chart_status_slot, hub.chart_tabs_bar
    coin, other = hub.coins[0], hub.coins[1]
    hub._show_chart_page(coin)
    strip = hub._chart_tabs_strip
    assert row.pack_slaves() == [strip]
    assert strip.grid_slaves(column=0) == [bar] and strip.grid_slaves(column=1) == [
        slot
    ]
    assert slot.grid_info()["sticky"] == "new"
    chart = hub.charts[coin]
    assert chart.status_frame.master is slot and chart.neural_status_label.master is (
        chart.status_frame
    )
    assert slot.pack_slaves() == [chart.status_frame]
    assert chart.status_frame.pack_info()["fill"] == "x"
    lines = [chart.neural_status_label, chart.patterns_status_label]
    assert chart.status_frame.pack_slaves() == lines
    for label in lines:
        info = label.pack_info()
        assert (info["side"], info["anchor"]) == ("top", "w")
        assert info["padx"] in (0, (0, 0))
    assert hub.charts[other].status_frame.winfo_manager() == ""
    assert chart.pack_slaves()[0] is chart.canvas.get_tk_widget()  # plot at the top
    hub._show_chart_page(other)
    assert slot.pack_slaves() == [hub.charts[other].status_frame]
    hub._show_chart_page("ACCOUNT")
    assert slot.pack_slaves() == []


def test_a_destroyed_chart_takes_its_status_line_with_it(hub):
    """The status line is a child of the tab row, so destroying one chart on its own
    left it packed in the row, next to the next chart's."""
    coin = hub.coins[0]
    hub._show_chart_page(coin)
    chart = hub.charts[coin]
    frame = chart.status_frame
    assert hub._chart_status_slot.pack_slaves() == [frame]
    chart.destroy()
    assert not frame.winfo_exists()
    assert hub._chart_status_slot.pack_slaves() == []


def test_the_buttons_shrink_before_the_status_line(hub, monkeypatch):
    """Tk sizes the row: the buttons and the status lines share a strip as wide as
    the row. With room to spare the status column has the weight, so it reaches the
    right edge (owner, 2026-11-04); short of room the buttons' column has it, so it
    narrows first (to MIN_TAB_BUTTONS_W) and the buttons scroll while the status
    keeps its width. (A hidden window lays nothing out, so the strip's width is
    stood in and this checks the layout's settings, not pixels.)"""
    hub._show_chart_page(hub.coins[0])
    hub.update_idletasks()
    row, strip, bar = hub._chart_tabs_row, hub._chart_tabs_strip, hub.chart_tabs_bar
    assert row.pack_slaves() == [strip]
    assert strip.pack_info()["fill"] == "x" and int(strip.pack_info()["expand"])
    for event in (strip, hub._chart_status_slot, bar.inner):
        assert event.bind("<Configure>")  # a change of either width balances again
    need = (
        bar.inner.winfo_reqwidth()
        + hub._chart_status_slot.winfo_reqwidth()
        + pt_hub.SPACE["sm"]
    )
    for width, weights in ((need + 200, (0, 1)), (need, (0, 1)), (need - 1, (1, 0))):
        monkeypatch.setattr(strip, "winfo_width", lambda w=width: w)
        hub._balance_chart_tab_strip()
        buttons, status = strip.grid_columnconfigure(0), strip.grid_columnconfigure(1)
        assert (buttons["weight"], status["weight"]) == weights, width
        assert buttons["minsize"] == pt_hub.MIN_TAB_BUTTONS_W
    assert "e" in bar.grid_info()["sticky"] and "w" in bar.grid_info()["sticky"]
    # the bar asks for all its buttons
    assert int(bar._canvas.cget("width")) == bar.inner.winfo_reqwidth()


def test_the_chart_sits_4px_under_the_buttons_and_the_divider_moves_up(hub):
    """Owner, 2026-10-14: 4 px from the buttons to the chart; the divider under the
    charts starts higher by the height the status row used to take, so the chart
    keeps its height and the panel below gains it."""
    for button in hub._chart_tab_buttons.values():
        assert button.pack_info()["pady"] == (0, 4)
    assert hub._chart_status_slot.grid_info()["pady"] == (0, 4)
    label = next(iter(hub.charts.values())).neural_status_label
    # the old status row (label and its pads) plus what the gap under the buttons
    # shrank by, measured from the buttons as packed
    gap = hub._chart_tab_buttons["ACCOUNT"].pack_info()["pady"][1]
    row = label.winfo_reqheight() + 2 * pt_hub.CHART_STATUS_ROW_PADY
    assert hub._moved_status_row_px() == row + pt_hub.FORMER_TAB_BUTTON_GAP - gap
    assert (pt_hub.CHART_STATUS_ROW_PADY, pt_hub.FORMER_TAB_BUTTON_GAP) == (6, 6)
    # a chart on its own still has that row
    alone = pt_hub.CandleChart(
        hub, hub.fetcher, "BTC", hub._settings_getter, hub.trade_history_path
    )
    try:
        assert alone.status_frame.pack_info()["pady"] == pt_hub.CHART_STATUS_ROW_PADY
    finally:
        alone.destroy()


# --- the paper header (owner, 2026-10-23) ---------------------------------------------


def test_the_paper_header_is_one_row_with_no_live_btc_price(hub):
    """PAPER TRADING where MODE: PAPER was, the price and signal notes after it, and
    Run sample trade at the right. The Live BTC price is gone."""
    banner, strip = hub._paper_banner, hub._mode_indicator
    assert hub.pack_slaves()[0] is banner  # the top of the window
    assert strip not in hub.pack_slaves()  # not a row of its own
    assert strip.pack_info()["in"] is banner
    texts = [str(w.cget("text")) for w in banner.pack_slaves() if "text" in w.keys()]
    assert texts[0] == "PAPER TRADING"
    assert "Run sample trade" in texts
    assert not [t for t in texts if "MODE" in t or "Live BTC" in t]
    assert not hasattr(banner, "set_price")


def test_switching_to_live_and_back_moves_the_mode_strip(hub):
    import trading_mode as tm

    strip = hub._mode_indicator
    hub._on_trading_mode_applied(
        tm.read_trading_settings(
            {"trading": {"mode": "live", "active_broker": "kraken"}}
        )
    )
    assert hub._paper_banner is None
    assert hub.pack_slaves()[0] is strip
    assert str(strip.cget("text")).startswith("MODE: LIVE — Kraken")
    hub._on_trading_mode_applied(
        tm.read_trading_settings({"trading": {"mode": "paper"}})
    )
    banner = hub._paper_banner
    assert hub.pack_slaves()[0] is banner and strip.pack_info()["in"] is banner
    children = hub.winfo_children()  # in stacking order, lowest first
    assert children.index(strip) > children.index(banner)  # drawn above its banner


def test_the_charts_frame_is_titled_charts_alone(hub):
    """The overlays can all be switched off (Chart settings), so the frame names
    none of them."""
    assert str(hub._charts_frame.cget("text")) == "Charts"
