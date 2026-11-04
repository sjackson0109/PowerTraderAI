"""The Long-term Holdings tab (long_term_holdings_gui; owner, 2026-11-04).

* One holdings tab, Long-term Holdings, in its old place: a subtitle over four
  sub-tabs (Holdings, Portfolio Overview, Rebalancing, Analytics). The separate
  Holdings Management tab and the read-only table are gone.
* A holding added in the dialog shows in Holdings and in Portfolio Overview; the
  dialog offers the hub's coins and shows the coin's market in the exchange layer's
  format (primary exchange first); holdings.db keeps the coin as before.
* With no data every sub-tab says so: no empty axes, no blank panel.
* Holdings and Rebalancing use the shared table: one border, scrollbars only while
  the rows or columns overflow, sortable, with a search through every column.
* holdings.db and its data stay as they are; nothing links the holdings to the
  trading account.

Real Tk widgets (a transparent window where sizes matter) and a real hub, under
the isolation guard (app/conftest.py); every holdings.db is a temporary one (the
test's own folder, or the guard's POWERTRADER_HOME); the exchange layer is built
from the real connectors (their own symbols) and sends no request.
"""

import os
import sqlite3
import sys
from types import SimpleNamespace

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import long_term_holdings as lth  # noqa: E402
import long_term_holdings_gui as ltg  # noqa: E402
import ui_table  # noqa: E402

SUBTITLE = (
    "Manual HODL positions, tracked separately from the trading account. "
    "Not included in Value, Buying Power or % in Trade."
)


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
    win.geometry("1100x420+0+0")
    ui_theme.apply_theme(win, ttk.Style(win), ui_tokens.DARK)
    yield win
    try:
        win.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def manager(tmp_path):
    """A HoldingsManager on its own temporary holdings.db."""
    return lth.HoldingsManager(str(tmp_path / "holdings.db"))


@pytest.fixture
def dialogs(monkeypatch):
    """The message boxes, recorded; askyesno answers ``dialogs.answer``."""
    seen = SimpleNamespace(calls=[], answer=True)

    def record(name):
        def box(title, message, **kw):
            seen.calls.append((name, title, message))
            return seen.answer if name == "askyesno" else "ok"

        return box

    for name in ("showerror", "showinfo", "showwarning", "askyesno"):
        monkeypatch.setattr(ltg.messagebox, name, record(name))
    return seen


def layer(*names, primary=None):
    """An exchange layer holding the real connectors for ``names`` (their own
    symbols), in that order, ``primary`` first."""
    import pt_exchanges  # noqa: F401  (registers the connectors)
    from pt_exchange_abstraction import ExchangeFactory, ExchangeManager, ExchangeType

    em = ExchangeManager()
    for name in names:
        em.exchanges[ExchangeType(name)] = ExchangeFactory.get_exchange(
            ExchangeType(name), api_key="", api_secret=""
        )
    if names:
        em.primary_exchange = ExchangeType(primary or names[0])
    return SimpleNamespace(exchange_manager=em)


def symbols(*names, primary=None):
    lay = layer(*names, primary=primary)
    return ltg.ExchangeSymbols(layer=lambda: lay)


def settle(win, g):
    for _ in range(3):
        win.update()
        g.holdings_table.settle()
        g.suggestions_table.settle()
    win.update()


def gui(win, manager, coins=("BTC", "ETH", "SOL"), syms=None):
    from tkinter import ttk

    frame = ttk.Frame(win)
    frame.pack(fill="both", expand=True)
    g = ltg.HoldingsManagementGUI(
        frame,
        coins=lambda: list(coins),
        manager=manager,
        symbols=syms or symbols("coinbase", "binance"),
    )
    settle(win, g)
    return g


def holding(symbol, qty, cost, price, **kw):
    return lth.Holding(
        symbol=symbol, quantity=qty, average_cost=cost, current_price=price, **kw
    )


def add(g, win, coin, qty, cost, price="", exchange="", target=""):
    """A holding added through the Add Holding dialog."""
    dlg = g.add_holding_dialog()
    dlg.attributes("-alpha", 0.0)
    dlg.coin_var.set(coin)
    dlg.exchange_var.set(exchange)
    dlg.quantity_var.set(str(qty))
    dlg.cost_var.set(str(cost))
    dlg.price_var.set(str(price))
    dlg.target_var.set(str(target))
    saved = dlg.save()
    assert saved is not None
    settle(win, g)
    return saved


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


def shown(widget, win, g=None, tab=None):
    """``widget`` is on screen, with its sub-tab selected."""
    if tab is not None:
        g.notebook.select(tab)
        win.update()
    return bool(widget.winfo_manager()) and bool(widget.winfo_ismapped())


# ---- the real hub ----


@pytest.fixture
def hub(monkeypatch, layout_file):
    """The real hub with its Long-term Holdings window (the other heavy features
    off), on the guard's temporary holdings.db."""
    import helpers_trainer as ht

    import pt_hub

    if not pt_hub.HOLDINGS_MANAGEMENT_AVAILABLE:
        pytest.skip("long_term_holdings_gui did not import")
    monkeypatch.setattr(lth, "_holdings_manager", None)  # this test's holdings.db
    monkeypatch.setattr(
        ht,
        "HEAVY_FLAGS",
        tuple(f for f in ht.HEAVY_FLAGS if f != "HOLDINGS_MANAGEMENT_AVAILABLE"),
    )
    hub = ht.build_real_hub(monkeypatch)
    hub.holdings_gui.symbols = symbols("coinbase", "binance")
    yield hub
    ht.close_hub(hub)


def holdings_tab(hub):
    """The Long-term Holdings tab, found by its name (the hub sets the tab order,
    pt_hub.MODULE_TAB_ORDER)."""
    import pt_hub

    nb = hub.bottom_notebook
    return next(
        t
        for t in nb.tabs()
        if pt_hub.module_tab_name(nb.tab(t, "text")) == "Long-term Holdings"
    )


def show_hub(hub, geometry="1500x950+0+0"):
    hub.attributes("-alpha", 0.0)
    hub.geometry(geometry)
    hub.deiconify()
    nb = hub.bottom_notebook
    nb.select(holdings_tab(hub))
    for _ in range(6):
        hub.update()
        hub.holdings_gui.holdings_table.settle()
        hub.holdings_gui.suggestions_table.settle()


# ---- acceptance: one holdings tab, four sub-tabs ----


def test_one_holdings_tab_named_long_term_holdings_with_four_sub_tabs(hub):
    import pt_hub
    import pt_paths

    nb = hub.bottom_notebook
    names = [nb.tab(t, "text").replace("\n", " ") for t in nb.tabs()]
    assert "Long-term Holdings" in names
    assert [n for n in names if "Holdings" in n] == ["Long-term Holdings"]

    g = hub.holdings_gui
    assert isinstance(g, ltg.HoldingsManagementGUI)
    tab = hub.nametowidget(holdings_tab(hub))
    assert g.main_frame in list(walk(tab))
    assert [g.notebook.tab(t, "text") for t in g.notebook.tabs()] == [
        "Holdings",
        "Portfolio Overview",
        "Rebalancing",
        "Analytics",
    ]
    # one subtitle line over the four sub-tabs
    labels = [w for w in tab.winfo_children() if w.winfo_class() == "TLabel"]
    assert [w.cget("text") for w in labels] == [pt_hub.LONG_TERM_HOLDINGS_SUBTITLE]
    assert pt_hub.LONG_TERM_HOLDINGS_SUBTITLE == SUBTITLE
    # the read-only table and the second tab are gone
    for name in ("lth_table", "lth_tree"):
        assert not hasattr(hub, name)
    for name in ("_refresh_long_term_holdings", "_create_holdings_management_tab"):
        assert not hasattr(pt_hub.PowerTraderHub, name)
    # the guard's temporary holdings.db, in the user data folder as before
    path = os.path.abspath(g.holdings_manager.db.db_path)
    assert path == os.path.abspath(pt_paths.data_file("holdings.db"))
    assert path.startswith(os.path.abspath(os.environ["POWERTRADER_HOME"]))


def test_without_the_holdings_window_the_tab_says_so(monkeypatch, layout_file):
    """The other hub tests switch the window off: the tab stays, with its subtitle."""
    import helpers_trainer as ht

    import pt_hub

    hub = ht.build_real_hub(monkeypatch)
    try:
        nb = hub.bottom_notebook
        names = [nb.tab(t, "text").replace("\n", " ") for t in nb.tabs()]
        assert [n for n in names if "Holdings" in n] == ["Long-term Holdings"]
        assert hub.holdings_gui is None
        texts = [
            str(w.cget("text"))
            for w in walk(hub.nametowidget(holdings_tab(hub)))
            if w.winfo_class() == "TLabel"
        ]
        assert texts == [
            pt_hub.LONG_TERM_HOLDINGS_SUBTITLE,
            "The holdings could not be loaded.",
        ]
    finally:
        ht.close_hub(hub)


# ---- acceptance: a holding added shows in Holdings and Portfolio Overview ----


def test_adding_a_holding_shows_it_in_holdings_and_portfolio_overview(hub):
    import pt_paths

    g = hub.holdings_gui
    account = [
        hub.lbl_acct_total_value.cget("text"),
        hub.lbl_acct_buying_power.cget("text"),
        hub.lbl_acct_percent_in_trade.cget("text"),
    ]
    assert g.overview_empty.winfo_manager() and not g.overview_body.winfo_manager()

    coin = hub.coins[0]
    dlg = g.add_holding_dialog()
    dlg.attributes("-alpha", 0.0)
    assert list(dlg.coin_box["values"]) == list(hub.coins)  # the coins in Settings
    assert dlg.coin_var.get() == coin
    dlg.quantity_var.set("0.5")
    dlg.cost_var.set("40000")
    dlg.price_var.set("60000")
    assert dlg.save() is not None
    assert not dlg.winfo_exists()
    hub.update()

    # Holdings: the row, with the share of the holdings
    (row,) = rows(g.holdings_tree)
    assert row[0] == coin and row[1] == "0.5"
    assert row[5] == "$30,000.00" and row[6] == "+$10,000.00" and row[7] == "+50.00%"
    assert row[8] == "100.00%"
    assert g.holdings_tree.heading("share", "text") == "% of Holdings"
    # Portfolio Overview: the totals and one wedge, no message
    assert g.overview_body.winfo_manager() and not g.overview_empty.winfo_manager()
    assert g.summary_labels["holdings_count"].cget("text") == "1"
    assert g.summary_labels["total_value"].cget("text") == "$30,000.00"
    (ax,) = g.portfolio_fig.axes
    assert len(ax.patches) == 1 and coin in [t.get_text() for t in ax.texts]
    # holdings.db keeps the coin, as before
    (saved,) = lth.HoldingsDatabase(
        pt_paths.data_file("holdings.db")
    ).get_all_holdings()
    assert (saved.symbol, saved.quantity, saved.average_cost) == (coin, 0.5, 40000.0)
    # nothing links the holdings to the trading account
    assert account == [
        hub.lbl_acct_total_value.cget("text"),
        hub.lbl_acct_buying_power.cget("text"),
        hub.lbl_acct_percent_in_trade.cget("text"),
    ]


def test_holdings_and_rebalancing_share_the_holdings_value(root, manager, dialogs):
    for h in (
        holding("BTC", 0.5, 40000.0, 60000.0, target_percentage=50.0),
        holding("DOT", 100, 5.0, 10.0, target_percentage=50.0),
    ):
        manager.add_holding(h)
    g = gui(root, manager)
    shares = {r[0]: r[8] for r in rows(g.holdings_tree)}
    # 30,000 and 1,000 of 31,000: the holdings' own value, not the account's
    assert shares == {"BTC": "96.77%", "DOT": "3.23%"}
    assert g.suggestions_tree.heading("current_pct", "text") == "% of Holdings"
    suggestions = {r[0]: r for r in rows(g.suggestions_tree)}
    assert suggestions["BTC"][1:3] == ("Sell", "96.77%")
    assert suggestions["DOT"][1:3] == ("Buy", "3.23%")
    headings = [g.holdings_tree.heading(c, "text") for c in ltg.HOLDINGS_COLUMNS]
    headings += [g.suggestions_tree.heading(c, "text") for c in ltg.REBALANCE_COLUMNS]
    assert not [h for h in headings if "Portfolio" in h]


# ---- acceptance: no empty axes or blank panels ----


def test_with_no_holdings_every_sub_tab_says_so_without_empty_axes(root, manager):
    g = gui(root, manager)
    tabs = g.notebook.tabs()

    assert shown(g.holdings_table.empty, root, g, tabs[0])
    assert g.holdings_table.empty.cget("text") == "No holdings yet"

    assert shown(g.overview_empty, root, g, tabs[1])
    assert g.overview_empty.cget("text") == "No holdings to display"
    assert not g.overview_body.winfo_manager()
    assert g.portfolio_fig.axes == []  # no 0-1 axes behind the message

    assert shown(g.suggestions_table.empty, root, g, tabs[2])
    assert g.suggestions_table.empty.cget("text") == "No holdings yet"

    assert shown(g.analytics_empty, root, g, tabs[3])
    assert g.analytics_empty.cget("text") == "No data yet"
    assert not g.analytics_widget.winfo_manager()
    assert g.analytics_fig.axes == []


def test_holdings_with_no_current_price_say_so(root, manager):
    manager.add_holding(holding("BTC", 0.5, 40000.0, 0.0, target_percentage=50.0))
    g = gui(root, manager)
    tabs = g.notebook.tabs()
    # the totals show; the chart's place says why there is no chart
    assert g.overview_body.winfo_manager()
    assert shown(g.chart_note, root, g, tabs[1])
    assert g.chart_note.cget("text") == ltg.NO_PRICES
    assert not g.portfolio_widget.winfo_manager() and g.portfolio_fig.axes == []
    assert shown(g.suggestions_table.empty, root, g, tabs[2])
    assert g.suggestions_table.empty.cget("text") == ltg.NO_PRICES
    assert shown(g.analytics_empty, root, g, tabs[3])
    assert g.analytics_empty.cget("text") == ltg.NO_PRICES
    assert g.analytics_fig.axes == []


def test_rebalancing_says_why_it_lists_nothing(root, manager):
    manager.add_holding(holding("BTC", 1, 100.0, 100.0))
    g = gui(root, manager)
    assert g.suggestions_table.is_empty_shown()
    assert g.suggestions_table.empty.cget("text") == ltg.NO_TARGETS
    h = manager.holdings[0]
    h.target_percentage = 100.0
    manager.update_holding(h)
    g.refresh_holdings_display()
    settle(root, g)
    assert g.suggestions_table.empty.cget("text") == ltg.IN_BALANCE


def test_analytics_charts_the_pnl_and_the_recorded_prices(root, manager):
    manager.add_holding(holding("BTC", 0.5, 40000.0, 60000.0))
    manager.add_holding(holding("ETH", 2, 3000.0, 2700.0))
    g = gui(root, manager)
    assert not g.analytics_empty.winfo_manager() and g.analytics_widget.winfo_manager()
    assert g.analytics_pnl == [("BTC", 50.0), ("ETH", pytest.approx(-10.0))]
    (ax,) = g.analytics_fig.axes
    assert ax.get_title() == ltg.PNL_TITLE
    assert [round(p.get_height(), 6) for p in ax.patches] == [50.0, -10.0]
    assert [t.get_text() for t in ax.get_xticklabels()] == ["BTC", "ETH"]

    # prices entered with Update Prices: the change since the first one
    manager.db.update_price("BTC", 50000.0)
    manager.db.update_price("BTC", 55000.0)
    manager.db.update_price("SOL", 150.0)  # not held: not charted
    manager.db.update_price("SOL", 160.0)
    g.refresh_holdings_display()
    root.update()
    assert g.analytics_prices == {"BTC": [0.0, pytest.approx(10.0)]}
    titles = [a.get_title() for a in g.analytics_fig.axes]
    assert titles == [ltg.PNL_TITLE, ltg.PRICES_TITLE]
    (line,) = g.analytics_fig.axes[1].get_lines()[:1]
    assert line.get_label() == "BTC"
    # the P&L follows the price recorded last
    assert g.analytics_pnl[0] == ("BTC", pytest.approx(37.5))


# ---- acceptance: one border, scrollbars only when needed ----


def test_one_border_and_scrollbars_only_while_the_rows_overflow(hub):
    from tkinter import ttk

    g = hub.holdings_gui
    tab = hub.nametowidget(holdings_tab(hub))
    assert str(g.notebook.cget("style")) == "Inner.TNotebook"
    widgets = list(walk(tab))
    assert not [
        w
        for w in widgets
        if w.winfo_class() == "TLabelframe"
        and str(w.cget("style")) != "Flat.TLabelframe"
    ]
    trees = [w for w in widgets if isinstance(w, ttk.Treeview)]
    assert set(trees) == {g.holdings_tree, g.suggestions_tree}
    for t in trees:
        assert isinstance(t.master, ui_table.DataTable)
        assert str(t.cget("style")) == ui_table.STYLE
    for table, sub_tab in (
        (g.holdings_table, g.holdings_tab),
        (g.suggestions_table, g.rebalancing_tab),
    ):
        assert table.master is sub_tab  # straight in its sub-tab, no frame round it
        assert str(table.pack_info()["fill"]) == "both"
        assert str(table.pack_info()["expand"]) in ("1", "True")

    m = g.holdings_manager
    for coin, qty in (("BTC", 0.5), ("ETH", 2.0)):
        m.add_holding(holding(coin, qty, 100.0, 120.0, target_percentage=10.0))
    g.refresh_holdings_display()
    show_hub(hub)
    for table, sub_tab in ((g.holdings_table, 0), (g.suggestions_table, 2)):
        g.notebook.select(g.notebook.tabs()[sub_tab])
        show_hub(hub)
        assert len(table.tree.get_children()) == 2
        assert table.scrollbars_shown() == {"x": False, "y": False}
        tree = table.tree
        # the table runs the sub-tab's full width
        assert tree.winfo_width() >= table.winfo_width() - 2

    # more rows than fit, and a long exchange name: wider than the panel too
    where = "Hardware wallet kept in the safe deposit box at the bank, second key"
    for n in range(40):
        m.add_holding(
            holding(
                f"C{n:02d}", n + 1, 100.0, 120.0, exchange=where, target_percentage=1
            )
        )
    g.refresh_holdings_display()
    g.notebook.select(g.notebook.tabs()[0])
    show_hub(hub, "1400x950+0+0")  # the hub's narrowest
    t = g.holdings_table
    assert t.scrollbars_shown() == {"x": True, "y": True}
    assert t.ysb.winfo_height() == t.tree.winfo_height()
    assert t.xsb.winfo_width() == t.tree.winfo_width()
    assert t.xsb.winfo_y() == t.tree.winfo_y() + t.tree.winfo_height()
    assert t.ysb.winfo_x() == t.tree.winfo_x() + t.tree.winfo_width()


# ---- the search and the sort ----


def test_the_search_looks_through_every_column_and_keeps_the_sort(
    root, manager, dialogs
):
    for h in (
        holding("BTC", 0.5, 40000.0, 60000.0, exchange="Ledger"),
        holding("ETH", 3, 3000.0, 3000.0, exchange="Coinbase"),
        holding("SOL", 10, 150.0, 150.0, exchange="Coinbase"),
    ):
        manager.add_holding(h)
    g = gui(root, manager)
    search = g.holdings_search
    assert rows(g.holdings_tree, 0) == ["BTC", "ETH", "SOL"]

    g.search_var.set("coinbase")
    search.now()
    settle(root, g)
    assert rows(g.holdings_tree, 0) == ["ETH", "SOL"]
    g.holdings_table.sort_by("quantity", descending=True)
    assert rows(g.holdings_tree, 0) == ["SOL", "ETH"]
    g.search_var.set("ETH 3")  # every word, in any column
    search.now()
    settle(root, g)
    assert rows(g.holdings_tree, 0) == ["ETH"]
    g.search_var.set("")
    search.now()
    settle(root, g)
    assert rows(g.holdings_tree, 0) == ["SOL", "ETH", "BTC"]  # the sort holds
    g.search_var.set("nothing like this")
    search.now()
    settle(root, g)
    assert g.holdings_table.is_empty_shown()
    assert g.holdings_table.empty.cget("text") == ltg.NO_HOLDINGS_MATCH


def test_the_search_waits_for_the_typing_to_stop(root, manager):
    manager.add_holding(holding("BTC", 1, 1.0, 1.0))
    manager.add_holding(holding("ETH", 1, 1.0, 1.0))
    g = gui(root, manager)
    g.search_var.set("eth")
    root.update()
    assert rows(g.holdings_tree, 0) == ["BTC", "ETH"]  # not yet
    root.after(ui_table.SEARCH_DELAY_MS + 100, root.quit)
    root.mainloop()
    settle(root, g)
    assert rows(g.holdings_tree, 0) == ["ETH"]


def test_rebalancing_is_searched_and_exported_as_shown(
    root, manager, dialogs, tmp_path
):
    for h in (
        holding("BTC", 0.5, 40000.0, 60000.0, target_percentage=50.0),
        holding("ETH", 3, 3000.0, 3000.0, target_percentage=50.0),
    ):
        manager.add_holding(h)
    g = gui(root, manager)
    assert sorted(rows(g.suggestions_tree, 1)) == ["Buy", "Sell"]
    g.suggestions_search.var.set("buy")
    g.suggestions_search.now()
    settle(root, g)
    assert rows(g.suggestions_tree, 0) == ["ETH"]
    out = tmp_path / "suggestions.csv"
    assert g.export_suggestions(str(out))
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Coin,Action,% of Holdings,Target %,Deviation %,Amount"
    assert len(lines) == 2 and lines[1].startswith("ETH,Buy,")


def test_widths_and_sort_are_kept_between_sessions(root, manager):
    g = gui(root, manager)
    g.holdings_table.sort_by("current_value", descending=True)
    saved = ui_table.saved_layout("holdings_management.holdings")
    assert saved["sort"] == ["current_value", True]
    again = gui(root, manager)
    assert again.holdings_table.sort_order == ("current_value", True)


# ---- the dialog: coins from Settings, symbols from the exchange layer ----


def test_the_dialog_offers_the_hubs_coins_and_the_exchanges_market(
    root, manager, dialogs
):
    g = gui(root, manager, coins=("btc", "ETH"))
    dlg = g.add_holding_dialog()
    dlg.attributes("-alpha", 0.0)
    assert list(dlg.coin_box["values"]) == ["BTC", "ETH"]
    assert str(dlg.coin_box.cget("state")) == "readonly"
    # the exchanges in Settings, primary first, by name; any other may be typed
    assert list(dlg.exchange_box["values"]) == ["Coinbase", "Binance"]
    assert str(dlg.exchange_box.cget("state")) != "readonly"
    assert dlg.market_label.cget("text") == "BTC-USD on Coinbase"
    dlg.exchange_var.set("Binance")
    assert dlg.market_label.cget("text") == "BTCUSDT on Binance"
    dlg.coin_var.set("ETH")
    assert dlg.market_label.cget("text") == "ETHUSDT on Binance"
    dlg.exchange_var.set("Ledger")  # a wallet: the primary exchange's market
    assert dlg.market_label.cget("text") == "ETH-USD on Coinbase"
    dlg.quantity_var.set("2")
    dlg.cost_var.set("3000")
    saved = dlg.save()
    assert (saved.symbol, saved.exchange) == ("ETH", "Ledger")
    (row,) = manager.db.get_all_holdings()
    assert (row.symbol, row.exchange, row.current_price) == ("ETH", "Ledger", 0.0)


def test_the_primary_exchange_comes_first(root, manager):
    g = gui(root, manager, syms=symbols("coinbase", "binance", primary="binance"))
    dlg = g.add_holding_dialog()
    dlg.attributes("-alpha", 0.0)
    assert list(dlg.exchange_box["values"]) == ["Binance", "Coinbase"]
    assert dlg.market_label.cget("text") == "BTCUSDT on Binance"
    dlg.destroy()

    none = ltg.ExchangeSymbols(layer=lambda: layer())
    assert none.exchanges() == [] and none.market("BTC") == ("BTC-USD", "")


def test_editing_keeps_a_coin_no_longer_in_settings(root, manager, dialogs):
    manager.add_holding(holding("DOT", 100, 5.0, 10.0, exchange="Kraken", notes="x"))
    g = gui(root, manager, coins=("BTC",))
    (iid,) = g.holdings_tree.get_children()
    g.holdings_tree.selection_set(iid)
    root.update()
    assert g.selected_holding is not None and g.selected_holding.symbol == "DOT"
    dlg = g.edit_holding_dialog()
    dlg.attributes("-alpha", 0.0)
    assert dlg.title() == "Edit Holding"
    assert list(dlg.coin_box["values"]) == ["BTC", "DOT"]
    assert dlg.coin_var.get() == "DOT" and dlg.quantity_var.get() == "100"
    assert dlg.exchange_var.get() == "Kraken"
    dlg.quantity_var.set("150")
    assert dlg.save() is not None
    settle(root, g)
    (row,) = manager.db.get_all_holdings()
    assert (row.id, row.symbol, row.quantity, row.notes) == (int(iid), "DOT", 150, "x")
    assert g.holdings_tree.selection() == (iid,)


def test_add_needs_a_coin_in_settings(root, manager, dialogs):
    g = gui(root, manager, coins=())
    assert g.add_holding_dialog() is None
    assert dialogs.calls[-1][:3] == (
        "showinfo",
        "Add Holding",
        "Add a coin in Settings first.",
    )


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("quantity_var", "abc", "Enter numbers in the number fields."),
        ("quantity_var", "nan", "Enter numbers in the number fields."),
        ("quantity_var", "0", "Quantity must be greater than 0."),
        ("cost_var", "", "Average cost must be greater than 0."),
        ("price_var", "-1", "Current price cannot be negative."),
        ("target_var", "120", "Target % must be between 0 and 100."),
    ],
)
def test_the_dialog_refuses_what_is_not_a_holding(
    root, manager, dialogs, field, value, message
):
    g = gui(root, manager)
    dlg = g.add_holding_dialog()
    dlg.attributes("-alpha", 0.0)
    dlg.quantity_var.set("1")
    dlg.cost_var.set("100")
    getattr(dlg, field).set(value)
    assert dlg.save() is None
    assert dialogs.calls[-1][0] == "showerror" and dialogs.calls[-1][2] == message
    assert dlg.winfo_exists() and manager.db.get_all_holdings() == []
    dlg.destroy()


def test_delete_asks_first(root, manager, dialogs):
    manager.add_holding(holding("BTC", 0.5, 40000.0, 60000.0, exchange="Ledger"))
    g = gui(root, manager)
    assert not g.delete_holding()
    assert dialogs.calls[-1][0] == "showwarning"
    g.holdings_tree.selection_set(g.holdings_tree.get_children()[0])
    root.update()
    dialogs.answer = False
    assert not g.delete_holding()
    assert "0.5 BTC on Ledger" in dialogs.calls[-1][2]
    assert len(manager.db.get_all_holdings()) == 1
    dialogs.answer = True
    assert g.delete_holding()
    settle(root, g)
    assert manager.db.get_all_holdings() == [] and g.holdings_table.is_empty_shown()
    assert g.overview_empty.winfo_manager()


# ---- holdings.db stays as it is ----


def _dump(path):
    conn = sqlite3.connect(path)
    try:
        schema = conn.execute(
            "SELECT name, sql FROM sqlite_master ORDER BY name"
        ).fetchall()
        tables = {
            name: conn.execute(f"SELECT * FROM {name} ORDER BY id").fetchall()
            for name in ("holdings", "price_history", "rebalance_history")
        }
    finally:
        conn.close()
    return schema, tables


def test_an_existing_holdings_db_is_read_and_left_as_it_is(root, tmp_path):
    path = str(tmp_path / "holdings.db")
    db = lth.HoldingsDatabase(path)
    db.add_holding(holding("BTC", 0.5, 40000.0, 60000.0, exchange="binance"))
    db.add_holding(holding("ETH-USD", 2, 3000.0, 3200.0, notes="cold wallet"))
    db.update_price("BTC", 61000.0)
    before = _dump(path)

    g = gui(root, lth.HoldingsManager(path))
    for n in range(3):  # every sub-tab, read again
        g.notebook.select(g.notebook.tabs()[n])
        g.refresh_holdings_display()
        settle(root, g)
    assert rows(g.holdings_tree, 0) == ["BTC", "ETH-USD"]
    assert rows(g.holdings_tree, 10) == ["binance", ""]
    assert _dump(path) == before


# ---- tags in holdings.db ----

# holdings.db as the app made it before the tags (2026-11-04)
OLD_SCHEMA = (
    """CREATE TABLE holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        quantity REAL NOT NULL,
        average_cost REAL NOT NULL,
        current_price REAL DEFAULT 0.0,
        exchange TEXT DEFAULT '',
        purchase_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        target_percentage REAL DEFAULT 0.0,
        rebalance_threshold REAL DEFAULT 5.0,
        last_updated TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        price REAL NOT NULL,
        timestamp TEXT NOT NULL,
        source TEXT DEFAULT 'manual'
    )""",
    """CREATE TABLE rebalance_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        portfolio_value REAL NOT NULL,
        rebalance_data TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        notes TEXT DEFAULT ''
    )""",
)


def _old_holdings_db(path):
    conn = sqlite3.connect(path)
    try:
        for sql in OLD_SCHEMA:
            conn.execute(sql)
        conn.executemany(
            "INSERT INTO holdings (symbol, quantity, average_cost, current_price,"
            " exchange, purchase_date, notes, target_percentage, rebalance_threshold,"
            " last_updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("BTC", 0.5, 40000.0, 60000.0, "binance", "2021-03-01", "", 50, 5, ""),
                ("ETH", 2.0, 3000.0, 3200.0, "", "last spring", "cold", 0, 5, "x"),
            ],
        )
        conn.execute(
            "INSERT INTO price_history (symbol, price, timestamp) VALUES (?, ?, ?)",
            ("BTC", 61000.0, "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO rebalance_history (portfolio_value, rebalance_data,"
            " timestamp) VALUES (?, ?, ?)",
            (36400.0, "{}", "2026-01-02T00:00:00"),
        )
        conn.commit()
    finally:
        conn.close()


def test_an_old_holdings_db_keeps_its_holdings_unchanged_and_untagged(tmp_path):
    path = str(tmp_path / "holdings.db")
    _old_holdings_db(path)
    schema, tables = _dump(path)

    for _ in range(2):  # opened twice: the second time changes nothing more
        m = lth.HoldingsManager(path)
        new_schema, new_tables = _dump(path)
        # every table and row from before, exactly; one new, empty table
        assert new_tables == tables
        # (and the index of its key)
        assert [s for s in new_schema if "holding_tags" not in s[0]] == schema
        assert "holding_tags" in [name for name, _sql in new_schema]
        conn = sqlite3.connect(path)
        try:
            assert conn.execute("SELECT COUNT(*) FROM holding_tags").fetchone() == (0,)
        finally:
            conn.close()
        assert [(h.symbol, h.tags) for h in m.holdings] == [("BTC", []), ("ETH", [])]
        assert m.all_tags() == []
        assert [h.symbol for h in m.filter_by_tags([lth.UNTAGGED])] == ["BTC", "ETH"]
        assert m.filter_by_tags(["Steve"]) == []

    # tagged afterwards: the tag is kept, the row otherwise as it was
    btc = m.holdings[0]
    btc.tags = ["Steve"]
    assert m.update_holding(btc)
    again, eth = lth.HoldingsManager(path).holdings
    assert again.tags == ["Steve"] and eth.tags == []
    assert (again.purchase_date, eth.purchase_date) == ("2021-03-01", "last spring")


def test_tags_are_kept_cleaned_and_removed_with_their_holding(manager):
    h = holding("BTC", 1, 100.0, 100.0, tags=[" Steve ", "pension", "steve", "a,  b"])
    assert manager.add_holding(h)
    (saved,) = manager.db.get_all_holdings()
    # trimmed, split at commas, once whatever the case, in alphabetical order
    assert saved.tags == ["a", "b", "pension", "Steve"]
    assert lth.tags_text(saved.tags) == "a, b, pension, Steve"

    saved.tags = ["Pension"]
    assert manager.update_holding(saved)
    (saved,) = manager.db.get_all_holdings()
    assert saved.tags == ["Pension"]

    assert manager.add_holding(holding("ETH", 1, 1.0, 1.0))  # no tags
    assert manager.all_tags() == ["Pension"]
    assert manager.delete_holding(saved.id)
    gone = holding("BTC", 1, 1.0, 1.0, tags=["Ghost"])
    gone.id = saved.id
    manager.db.update_holding(gone)  # a holding no longer there gains no tags
    conn = sqlite3.connect(manager.db.db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM holding_tags").fetchone() == (0,)
    finally:
        conn.close()
    assert manager.all_tags() == []


def test_a_tag_selection_keeps_the_holdings_with_any_of_its_tags(manager):
    for coin, tags in (
        ("BTC", ["Steve"]),
        ("ETH", ["Steve", "Pension"]),
        ("SOL", ["Pension"]),
        ("DOT", []),
    ):
        manager.add_holding(holding(coin, 1, 1.0, 1.0, tags=tags))

    def kept(*selection):
        return sorted(h.symbol for h in manager.filter_by_tags(selection))

    assert kept() == ["BTC", "DOT", "ETH", "SOL"]  # All
    assert kept("Steve") == ["BTC", "ETH"]
    assert kept("Pension") == ["ETH", "SOL"]  # ETH under either tag
    assert kept("steve") == ["BTC", "ETH"]  # in any case
    assert kept(" Steve ") == ["BTC", "ETH"]
    assert kept("Steve", "Pension") == ["BTC", "ETH", "SOL"]
    assert kept(lth.UNTAGGED) == ["DOT"]
    assert kept(lth.UNTAGGED, "Pension") == ["DOT", "ETH", "SOL"]
    assert kept("Nobody") == []
    assert manager.all_tags() == ["Pension", "Steve"]


def test_a_parent_that_is_not_a_widget_is_refused_at_once(monkeypatch):
    """A mock parent's masters never end: the window refuses it before it reads
    holdings.db or makes a Tk variable (test_suite.py builds one so)."""
    from unittest.mock import MagicMock

    monkeypatch.setattr(lth, "_holdings_manager", None)
    with pytest.raises(TypeError):
        ltg.HoldingsManagementGUI(MagicMock())
    assert lth._holdings_manager is None
