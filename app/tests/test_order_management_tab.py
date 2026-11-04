"""The Order Management tab (order_management_view; owner, 2026-11-04).

* A toolbar (Create Order, Refresh, Cancel Selected, a status filter and a search)
  over the orders, in the shared table (ui_table.DataTable): one border, no title
  repeating the tab's, scrollbars only while the rows overflow, newest first, and
  the filter, search and sort working together.
* Create Order opens a dialog that starts on the coin shown in the chart, as the
  symbol of the exchange the order is for, with prices from that exchange's bid and
  ask; it refuses a buy above Buying Power and confirms every order, naming the
  paper account or the live exchange.
* The Order Notifications under a splitter, newest first, with Mark all read.

A real Tk window, shown fully transparent, under the isolation guard
(app/conftest.py); a temporary order database; exchanges answer from stubs (the
real connectors give the symbols, no request is sent).
"""

import os
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

pytest.importorskip("sqlalchemy")

import order_management_view as omv  # noqa: E402
import ui_table  # noqa: E402

# bid, ask per market
PRICES = {"BTC-USD": (67000.5, 67001.25), "ETH-USD": (3500.1, 3500.4)}


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
    win.geometry("900x420+0+0")
    ui_theme.apply_theme(win, ttk.Style(win), ui_tokens.DARK)
    yield win
    try:
        win.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def manager(tmp_path, monkeypatch):
    """An OrderManager on its own temporary database (not the process's shared one)."""
    import order_management_integration
    from order_management_db import OrderManagementDB

    monkeypatch.setattr(
        order_management_integration,
        "get_order_db",
        lambda url=None: OrderManagementDB(url),
    )
    m = order_management_integration.OrderManager(f"sqlite:///{tmp_path / 'orders.db'}")
    assert m.is_available
    yield m
    m.stop_monitoring()
    m.db.close()


@pytest.fixture
def dialogs(monkeypatch):
    """The message boxes, recorded; askyesno answers ``dialogs.answer``."""
    seen = SimpleNamespace(calls=[], answer=True)

    def record(name):
        def box(title, message, **kw):
            seen.calls.append((name, title, message, kw))
            return seen.answer if name == "askyesno" else "ok"

        return box

    for name in ("showerror", "showinfo", "showwarning", "askyesno"):
        monkeypatch.setattr(omv.messagebox, name, record(name))
    return seen


def connector(name, prices=PRICES, fees=None):
    """The real connector for ``name`` (its own symbols), answering quotes from
    ``prices`` instead of the exchange."""
    import pt_exchanges  # noqa: F401  (registers the connectors)
    from pt_exchange_abstraction import ExchangeFactory, ExchangeType, PriceQuote

    ex = ExchangeFactory.get_exchange(ExchangeType(name), api_key="", api_secret="")

    def quote(symbol):
        if prices is None or symbol not in prices:
            return None
        bid, ask = prices[symbol]
        return PriceQuote(bid=bid, ask=ask, quote_ts=None)

    ex.quote = quote
    if fees is not None:
        ex.trading_fees = lambda: fees
    return ex


def layer(*connectors, primary=None):
    """An exchange layer (pt_exchange_abstraction.ExchangeManager) holding
    ``connectors`` in that order, ``primary`` first."""
    from pt_exchange_abstraction import ExchangeManager, ExchangeType

    em = ExchangeManager()
    for name, ex in connectors:
        em.exchanges[ExchangeType(name)] = ex
    em.primary_exchange = ExchangeType(primary or connectors[0][0])
    return SimpleNamespace(exchange_manager=em, quote=em.quote)


def market(*connectors, primary=None):
    lay = layer(*connectors, primary=primary)
    return omv.ExchangeMarket(layer=lambda: lay)


def trading(mode="paper", broker=None, testnet=False, preview=False):
    from trading_mode import TradingMode, TradingSettings

    return TradingSettings(
        mode=TradingMode.LIVE if mode == "live" else TradingMode.PAPER,
        active_broker=broker,
        testnet=testnet,
        preview=preview,
    )


def view(
    root,
    manager,
    *,
    chart_coin="ETH",
    coins=("BTC", "ETH"),
    settings=None,
    buying_power=1000.0,
    mkt=None,
):
    v = omv.OrderManagementView(
        root,
        manager,
        coins=lambda: list(coins),
        chart_coin=lambda: chart_coin,
        trading=lambda: settings or trading(),
        buying_power=lambda: buying_power,
        market=mkt or market(("coinbase", connector("coinbase"))),
        refresh_ms=None,
    )
    v.pack(fill="both", expand=True)
    settle(root, v)
    return v


def settle(root, v):
    for _ in range(3):
        root.update()
        v.orders_table.settle()
        v.notes_table.settle()
    root.update()


def open_dialog(v, root):
    dlg = v.open_dialog(background=False)
    dlg.attributes("-alpha", 0.0)
    root.update()
    return dlg


def column(v, name):
    i = omv.ORDER_COLUMNS.index(name)
    tree = v.orders_tree
    return [str(tree.item(iid, "values")[i]) for iid in tree.get_children()]


def orders_in_db(manager):
    return omv.load_orders(manager.db)


def set_created(manager, order_id, when):
    from order_management_models import Order

    with manager.db.get_session() as s:
        s.query(Order).filter(
            Order.id == uuid.UUID(str(order_id))
        ).one().created_at = when


# ---- acceptance: one border, no repeated title, no scrollbar while it fits ----


def test_the_tab_has_one_border_and_no_title_repeating_its_name(root, manager):
    from tkinter import ttk

    v = view(root, manager)
    widgets, stack = [], [v]
    while stack:
        w = stack.pop()
        widgets.append(w)
        stack.extend(w.winfo_children())
    trees = [w for w in widgets if isinstance(w, ttk.Treeview)]
    assert set(trees) == {v.orders_tree, v.notes_tree}
    assert all(str(t.cget("style")) == ui_table.STYLE for t in trees)
    assert not [w for w in widgets if isinstance(w, ttk.Labelframe)]
    texts = [str(w.cget("text")) for w in widgets if isinstance(w, ttk.Label)]
    assert not [t for t in texts if "Order Management" in t or "Active Orders" in t]
    assert omv.NOTES_TITLE in texts and "Recent Notifications" not in texts
    # the table style draws no border: only its rows' area
    style = ttk.Style(root)
    assert "border" not in str(style.layout(ui_table.STYLE)).lower()


def test_no_scrollbar_while_the_orders_and_notifications_fit(root, manager):
    for coin in ("BTC-USD", "ETH-USD"):
        manager.create_take_profit_order(coin, Decimal("0.1"), Decimal("70000"))
    v = view(root, manager)
    assert len(v.orders_tree.get_children()) == 2
    assert v.orders_table.scrollbars_shown() == {"x": False, "y": False}
    assert v.notes_table.scrollbars_shown() == {"x": False, "y": False}


def test_many_orders_scroll_along_the_whole_table(root, manager):
    for n in range(40):
        manager.create_take_profit_order("BTC-USD", Decimal("0.1"), Decimal(70000 + n))
    v = view(root, manager)
    root.geometry("420x420")
    settle(root, v)
    t = v.orders_table
    assert t.scrollbars_shown() == {"x": True, "y": True}
    assert t.ysb.winfo_height() == t.tree.winfo_height()
    assert t.xsb.winfo_width() == t.tree.winfo_width()
    assert t.xsb.winfo_y() == t.tree.winfo_y() + t.tree.winfo_height()


# ---- acceptance: the dialog starts on a valid symbol and price ----


def test_the_dialog_starts_on_the_chart_coin_as_the_exchange_symbol(root, manager):
    v = view(root, manager, chart_coin="ETH")
    dlg = open_dialog(v, root)
    assert dlg.coin_var.get() == "ETH"
    assert dlg.type_var.get() == omv.MARKET  # the default order type
    assert dlg.quote.exchange == "coinbase" and dlg.quote.pair == "ETH-USD"
    assert str(dlg.symbol_label.cget("text")) == "ETH-USD on Coinbase"
    assert str(dlg.market_price_label.cget("text")) == "$3,500.4 (the ask)"
    # a stop starts at the bid, never at a fixed number
    dlg.type_var.set(omv.STOP_LOSS)
    assert dlg.stop_var.get() == "3500.1"
    dlg.type_var.set(omv.STOP_LIMIT)
    assert (dlg.stop_var.get(), dlg.limit_var.get()) == ("3500.1", "3500.1")
    assert dlg.side_var.get() == "Sell"
    # another coin: its own symbol and prices
    dlg.coin_var.set("BTC")
    root.update()
    assert dlg.quote.pair == "BTC-USD" and dlg.stop_var.get() == "67000.5"
    # a condition's price: a buy's from the ask, a sell's from the bid
    dlg.type_var.set(omv.CONDITIONAL)
    dlg.side_var.set("Buy")
    assert dlg.cond_value_var.get() == "67001.25"
    dlg.side_var.set("Sell")
    assert dlg.cond_value_var.get() == "67000.5"


def test_the_symbol_is_the_live_exchanges_own(root, manager):
    """Live on Binance: BTCUSDT, Binance's own market, from Binance's prices."""
    mkt = market(
        ("coinbase", connector("coinbase")),
        ("binance", connector("binance", {"BTC-USD": (66990.0, 66991.0)})),
    )
    v = view(
        root,
        manager,
        chart_coin="BTC",
        settings=trading("live", "binance"),
        mkt=mkt,
    )
    dlg = open_dialog(v, root)
    assert str(dlg.symbol_label.cget("text")) == "BTCUSDT on Binance"
    assert (dlg.quote.bid, dlg.quote.ask) == (66990.0, 66991.0)


def test_in_paper_mode_the_primary_exchange_answers_first(root, manager):
    """Kraken is primary but has no price: the next exchange in Settings answers,
    with its own symbol."""
    mkt = market(
        ("kraken", connector("kraken", prices=None)),
        ("coinbase", connector("coinbase")),
        primary="kraken",
    )
    dlg = open_dialog(view(root, manager, chart_coin="BTC", mkt=mkt), root)
    assert str(dlg.symbol_label.cget("text")) == "BTC-USD on Coinbase"
    assert dlg.quote.ask == 67001.25


def test_with_the_account_chart_shown_the_dialog_starts_on_the_first_coin(
    root, manager
):
    dlg = open_dialog(view(root, manager, chart_coin="ACCOUNT"), root)
    assert dlg.coin_var.get() == "BTC" and dlg.quote.pair == "BTC-USD"


def test_the_market_is_looked_up_in_the_background(root, manager):
    import time

    v = view(root, manager, chart_coin="BTC")
    dlg = v.open_dialog()  # background=True: the hub's way
    dlg.attributes("-alpha", 0.0)
    end = time.time() + 10
    while dlg.quote is None and time.time() < end:
        root.update()
        time.sleep(0.01)
    assert dlg.quote is not None and dlg.quote.pair == "BTC-USD"


def test_the_fee_comes_from_the_connectors_trading_fees(root, manager):
    mkt = market(("coinbase", connector("coinbase", fees={"taker": 0.006})))
    dlg = open_dialog(view(root, manager, mkt=mkt), root)
    dlg.qty_var.set("1")
    root.update()
    assert str(dlg.value_label.cget("text")) == "$3,500.40"
    assert str(dlg.fee_label.cget("text")) == "$21.00 (0.60%)"


def test_with_no_trading_fees_the_fee_is_not_known(root, manager):
    dlg = open_dialog(view(root, manager), root)
    dlg.qty_var.set("1")
    root.update()
    assert str(dlg.fee_label.cget("text")) == "not known"


# ---- acceptance: a buy above Buying Power is refused ----


def test_a_buy_above_buying_power_is_refused(root, manager, dialogs):
    dlg = open_dialog(view(root, manager, buying_power=100.0), root)
    dlg.qty_var.set("1")  # 1 ETH at the ask: $3,500.40
    root.update()
    assert str(dlg.warning_label.cget("text")) == "More than Buying Power"
    assert dlg.create() is None
    name, title, message, _kw = dialogs.calls[-1]
    assert name == "showerror" and title == "Order refused"
    assert "$3,500.40" in message and "more than Buying Power, $100.00" in message
    assert not [c for c in dialogs.calls if c[0] == "askyesno"]  # not offered
    assert orders_in_db(manager) == [] and dlg.winfo_exists()


def test_the_fee_counts_towards_buying_power(root, manager, dialogs):
    mkt = market(("coinbase", connector("coinbase", fees={"taker": 0.01})))
    dlg = open_dialog(view(root, manager, buying_power=3510.0, mkt=mkt), root)
    dlg.qty_var.set("1")  # $3,500.40 + $35.00 fee
    assert dlg.create() is None and orders_in_db(manager) == []


def test_a_buy_is_refused_while_buying_power_is_not_known(root, manager, dialogs):
    dlg = open_dialog(view(root, manager, buying_power=None), root)
    dlg.qty_var.set("0.01")
    assert dlg.create() is None
    assert "Buying Power is not known" in dialogs.calls[-1][2]
    assert orders_in_db(manager) == []


def test_a_buy_within_buying_power_is_confirmed_then_created(root, manager, dialogs):
    v = view(root, manager, buying_power=100.0)
    dlg = open_dialog(v, root)
    dlg.qty_var.set("0.01")  # $35.00
    order_id = dlg.create()
    assert order_id
    name, title, message, kw = dialogs.calls[-1]
    assert name == "askyesno" and title == "Confirm order"
    assert "Account: Paper account" in message
    assert "Buy 0.01 ETH-USD on Coinbase" in message and "Type: Market" in message
    (row,) = orders_in_db(manager)
    assert (row.symbol, row.kind, row.side, row.status) == (
        "ETH-USD",
        "Market",
        "Buy",
        "pending",
    )
    settle(root, v)
    assert column(v, "symbol") == ["ETH-USD"]  # the table refreshed


def test_answering_no_creates_nothing(root, manager, dialogs):
    dialogs.answer = False
    dlg = open_dialog(view(root, manager), root)
    dlg.qty_var.set("0.01")
    assert dlg.create() is None and orders_in_db(manager) == []


def test_a_sell_is_not_checked_against_buying_power(root, manager, dialogs):
    """A stop-loss sells a holding: it spends no Buying Power."""
    dlg = open_dialog(view(root, manager, buying_power=100.0), root)
    dlg.type_var.set(omv.STOP_LOSS)
    dlg.qty_var.set("10")  # $35,001 at the stop
    assert dlg.create()
    (row,) = orders_in_db(manager)
    assert (row.kind, row.side, row.stop) == ("Stop Loss", "Sell", 3500.1)
    assert row.conditions == "Price ≤ 3,500.1"


def test_a_live_order_names_the_exchange_and_is_confirmed_as_live(
    root, manager, dialogs
):
    mkt = market(("binance", connector("binance", {"ETH-USD": (3500.0, 3501.0)})))
    v = view(root, manager, settings=trading("live", "binance"), mkt=mkt)
    dlg = open_dialog(v, root)
    assert str(dlg.account_label.cget("text")) == "Account: Binance, live (real money)"
    dlg.qty_var.set("0.01")
    assert dlg.create()
    name, title, message, kw = dialogs.calls[-1]
    assert title == "Confirm live order"
    assert kw["icon"] == "warning" and kw["default"] == "no"
    assert "Account: Binance, live (real money)" in message
    assert orders_in_db(manager)[0].symbol == "ETHUSDT"


def test_live_mode_with_no_exchange_chosen_refuses_the_order(root, manager, dialogs):
    v = view(root, manager, settings=trading("live", None))
    dlg = open_dialog(v, root)
    assert "no exchange chosen" in str(dlg.account_label.cget("text"))
    dlg.qty_var.set("0.01")
    assert dlg.create() is None and orders_in_db(manager) == []


@pytest.mark.parametrize(
    "settings, text",
    [
        (trading("live", "coinbase", preview=True), "preview orders"),
        (trading("live", "binance", testnet=True), "Binance testnet"),
    ],
)
def test_preview_and_testnet_accounts_say_so(settings, text):
    assert text in omv.account_text(settings)[0]


# ---- the order types ----


def test_each_order_type_is_created_and_shown(root, manager, dialogs):
    v = view(root, manager, buying_power=10_000.0)
    for kind, fill in (
        (omv.STOP_LIMIT, {}),
        (omv.TAKE_PROFIT, {}),
        (omv.DCA, {"level_var": "6"}),
        (omv.CONDITIONAL, {}),
    ):
        dlg = open_dialog(v, root)
        dlg.type_var.set(kind)
        dlg.qty_var.set("0.5")
        for var, value in fill.items():
            getattr(dlg, var).set(value)
        assert dlg.create(), kind
    v.status_var.set("All")
    settle(root, v)
    assert sorted(column(v, "type")) == [
        "Conditional",
        "DCA (stage 1)",
        "Stop-Limit",
        "Take Profit",
    ]
    conditions = dict(zip(column(v, "type"), column(v, "conditions")))
    assert conditions["Conditional"] == "Price ≥ 3,500.4"  # a buy: from the ask
    assert conditions["DCA (stage 1)"] == "Neural level ≥ 6"


def test_a_stop_loss_without_a_limit_price_is_created(manager):
    """OrderType has no STOP_LOSS: create_stop_loss_order raised on it, so a stop
    with no limit price was never created. It is a STOP order now."""
    order_id = manager.create_stop_loss_order(
        "BTC-USD", Decimal("0.1"), Decimal("60000")
    )
    assert order_id is not None
    (row,) = orders_in_db(manager)
    assert (row.kind, row.side, row.stop, row.price) == (
        "Stop Loss",
        "Sell",
        60000.0,
        None,
    )


# ---- acceptance: filter, search and sort together ----


def test_status_filter_search_and_sort_work_together(root, manager, dialogs):
    from order_management_models import OrderStatus

    ids = {}
    for coin, qty in (("BTC-USD", "0.2"), ("ETH-USD", "3"), ("ETH-USD", "1")):
        ids[(coin, qty)] = manager.create_take_profit_order(
            coin, Decimal(qty), Decimal("70000")
        )
    base = datetime(2026, 11, 4, 9, 0, 0)
    for n, oid in enumerate(ids.values()):
        set_created(manager, oid, base + timedelta(minutes=n))
    manager.db.update_order_status(ids[("ETH-USD", "1")], OrderStatus.FILLED)

    v = view(root, manager)
    # newest first, open orders only
    assert column(v, "quantity") == ["3", "0.2"]
    v.status_var.set("Filled")
    settle(root, v)
    assert column(v, "quantity") == ["1"]
    v.status_var.set("All")
    settle(root, v)
    assert column(v, "quantity") == ["1", "3", "0.2"]
    v.search_var.set("eth")
    v._search_now()
    settle(root, v)
    assert column(v, "quantity") == ["1", "3"]
    v.orders_table.sort_by("quantity")
    assert column(v, "quantity") == ["1", "3"]
    v.orders_table.sort_by("quantity")  # again: descending
    assert column(v, "quantity") == ["3", "1"]
    v.search_var.set("")
    v._search_now()
    settle(root, v)
    assert column(v, "quantity") == ["3", "1", "0.2"]  # the sort holds
    v.search_var.set("nothing like this")
    v._search_now()
    settle(root, v)
    assert v.orders_table.is_empty_shown()
    assert str(v.orders_table.empty.cget("text")) == omv.NO_MATCH


def test_widths_and_sort_are_kept_between_sessions(root, manager):
    v = view(root, manager)
    v.orders_table.sort_by("symbol")
    assert ui_table.saved_layout("order_management")["sort"] == ["symbol", False]
    again = view(root, manager)
    assert again.orders_table.sort_order == ("symbol", False)


# ---- the toolbar ----


def test_cancel_selected_cancels_the_open_orders_chosen(root, manager, dialogs):
    from order_management_models import OrderStatus

    a = manager.create_take_profit_order("BTC-USD", Decimal("1"), Decimal("70000"))
    b = manager.create_take_profit_order("ETH-USD", Decimal("2"), Decimal("4000"))
    c = manager.create_take_profit_order("ETH-USD", Decimal("3"), Decimal("4000"))
    manager.db.update_order_status(c, OrderStatus.FILLED)
    v = view(root, manager)
    v.status_var.set("All")
    settle(root, v)
    v.orders_tree.selection_set([str(a), str(b), str(c)])
    assert v.cancel_selected() == 2
    name, title, message, _kw = [x for x in dialogs.calls if x[0] == "askyesno"][-1]
    assert "Cancel 2 orders?" in message and "not open" in message
    status = {r.id: r.status for r in orders_in_db(manager)}
    assert status == {
        str(a): "cancelled",
        str(b): "cancelled",
        str(c): "filled",
    }


def test_a_refresh_keeps_the_selection(root, manager):
    a = manager.create_take_profit_order("BTC-USD", Decimal("1"), Decimal("70000"))
    v = view(root, manager)
    v.orders_tree.selection_set([str(a)])
    manager.create_take_profit_order("ETH-USD", Decimal("2"), Decimal("4000"))
    v.refresh()
    settle(root, v)
    assert len(v.orders_tree.get_children()) == 2
    assert v.orders_tree.selection() == (str(a),)


# ---- the notifications ----


def test_notifications_newest_first_and_mark_all_read(root, manager):
    from order_management_models import Notification

    manager.create_take_profit_order("BTC-USD", Decimal("1"), Decimal("70000"))
    manager.create_take_profit_order("ETH-USD", Decimal("2"), Decimal("4000"))
    with manager.db.get_session() as s:
        notes = s.query(Notification).all()
        for n, note in enumerate(sorted(notes, key=lambda x: x.title)):
            note.created_at = datetime(2026, 11, 4, 9, 0, 0) + timedelta(minutes=n)
    v = view(root, manager)
    tree = v.notes_tree
    events = [str(tree.item(i, "values")[1]) for i in tree.get_children()]
    assert events == ["Order Created: SELL ETH-USD", "Order Created: SELL BTC-USD"]
    assert all("unread" in tree.item(i, "tags") for i in tree.get_children())
    assert str(v.mark_read_button.cget("state")) == "normal"

    v.mark_all_read()
    settle(root, v)
    assert manager.get_unread_notifications() == []
    assert not any(tree.item(i, "tags") for i in tree.get_children())
    assert len(tree.get_children()) == 2  # still shown, as read
    assert str(v.mark_read_button.cget("state")) == "disabled"


def test_the_splitter_keeps_both_panes_at_their_minimum_height(root, manager):
    v = view(root, manager)
    total = v.paned.winfo_height()
    pos = int(v.paned.sashpos(0))
    assert total - pos >= omv.MIN_NOTES_PX and pos >= omv.MIN_ORDERS_PX
    assert total - pos <= total // 2  # the orders have most of the height
    v.paned.sashpos(0, 5)
    v.clamp_sash()
    assert int(v.paned.sashpos(0)) >= omv.MIN_ORDERS_PX
    v.paned.sashpos(0, total - 5)
    v.clamp_sash()
    assert total - int(v.paned.sashpos(0)) >= omv.MIN_NOTES_PX


# ---- in the hub ----


def test_the_hub_tab_uses_the_chart_coin_and_buying_power(monkeypatch, manager):
    from helpers_trainer import build_real_hub, close_hub

    import pt_hub

    hub = build_real_hub(monkeypatch)
    try:
        monkeypatch.setattr(pt_hub, "get_global_order_manager", lambda: manager)
        hub._create_order_management_tab()
        view_ = hub.order_view
        assert isinstance(view_, omv.OrderManagementView)
        assert hub.orders_tree is view_.orders_tree
        tabs = [hub.bottom_notebook.tab(t, "text") for t in hub.bottom_notebook.tabs()]
        assert "Order\nManagement" in tabs
        view_.market = market(("coinbase", connector("coinbase")))
        coin = hub.coins[-1] if "ETH" not in hub.coins else "ETH"
        hub._current_chart_page = coin
        hub._last_buying_power = 1234.5
        dlg = view_.open_dialog(background=False)
        dlg.attributes("-alpha", 0.0)
        assert dlg.coin_var.get() == coin
        assert dlg.buying_power == 1234.5
        assert str(dlg.power_label.cget("text")) == "$1,234.50"
        dlg.destroy()
    finally:
        manager.stop_monitoring()
        close_hub(hub)
