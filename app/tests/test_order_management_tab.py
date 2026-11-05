"""The Order Management tab (order_management_view; owner, 2026-11-04 and
2026-11-05).

* A toolbar (Create Order, Refresh, Cancel Selected, Modify Selected, a status
  filter and a search) over Active Orders, in the shared table
  (ui_table.DataTable): one border, no title repeating the tab's, scrollbars only
  while the rows overflow, newest first, and the filter, search and sort working
  together. An OCO or Bracket order's legs are under it, and one Cancel cancels
  them all.
* Create Order opens a dialog that starts on the coin shown in the chart, as the
  symbol of the exchange the order is for, with prices from that exchange's bid and
  ask. Its types are Market, Limit, Stop-Limit, Trailing Stop, OCO and Bracket, each
  showing only its own fields and saying how it is carried out; it refuses a buy
  above Buying Power and any order while trading is halted, and confirms every
  order, naming the paper account or the live exchange.
* In paper mode every type fills the paper account and the trade history.
* The Order Notifications under a splitter, newest first, with Mark all read.

A real Tk window, shown fully transparent, under the isolation guard
(app/conftest.py); a temporary order database and hub folder; exchanges answer from
stubs (the real connectors give the symbols, no request is sent).
"""

import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

pytest.importorskip("sqlalchemy")

import order_management_execution as ome  # noqa: E402
import order_management_view as omv  # noqa: E402
import trading_mode as tm  # noqa: E402
import ui_table  # noqa: E402
from pt_exchange_abstraction import OrderResult, TradingFees  # noqa: E402

# bid, ask per market
PRICES = {"BTC-USD": (67000.5, 67001.25), "ETH-USD": (3500.1, 3500.4)}
FEES = TradingFees(maker=0.004, taker=0.006, exchange="coinbase", source="exchange")


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
    ``prices`` and fees from ``fees`` instead of the exchange."""
    import pt_exchanges  # noqa: F401  (registers the connectors)
    from pt_exchange_abstraction import ExchangeFactory, ExchangeType, PriceQuote

    ex = ExchangeFactory.get_exchange(ExchangeType(name), api_key="", api_secret="")

    def quote(symbol):
        if prices is None or symbol not in prices:
            return None
        bid, ask = prices[symbol]
        return PriceQuote(bid=bid, ask=ask, quote_ts=None)

    ex.quote = quote
    ex.trading_fees = lambda symbol: fees
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


def market(*connectors, primary=None, atr=120.0):
    lay = layer(*connectors, primary=primary)
    return omv.ExchangeMarket(layer=lambda: lay, atr=lambda coin, exchange: atr)


def trading(mode="paper", broker=None, testnet=False, preview=False):
    return tm.TradingSettings(
        mode=tm.TradingMode.LIVE if mode == "live" else tm.TradingMode.PAPER,
        active_broker=broker,
        testnet=testnet,
        preview=preview,
    )


class Market:
    """The prices the paper account fills at and the executor checks against."""

    def __init__(self):
        self.coins = {k.split("-")[0]: v for k, v in PRICES.items()}

    def set(self, coin, bid, ask):
        self.coins[coin] = (bid, ask)

    def feed(self, base):
        bid, ask = self.coins[base]
        now = time.time()
        return tm.Quote(bid, ask, now, now, exchange="coinbase", pair=f"{base}-USD")

    def quote(self, settings, coin):
        bid, ask = self.coins[coin]
        return ome.Quote(bid, ask, "coinbase")


class FakeTarget:
    """A live order target: market orders are recorded and fill at once."""

    def __init__(self, exchange):
        self.exchange = exchange
        self.orders = []

    def place_order(self, symbol, side, amount, price=None, *, client_order_id=None):
        self.orders.append((symbol, side, amount))
        return OrderResult("live-1", symbol, side, 0.0, 0.0, "pending", "binance", 0)


@pytest.fixture
def world(tmp_path):
    """The hub folder (with a paper book), the market, the trading settings and a
    halt, for an OrderExecutor."""
    hub = str(tmp_path / "hub")
    tm.write_paper_book(
        tm.paper_book_path(hub),
        tm.PaperBook(
            Decimal("10000"), Decimal("10000"), {"ETH": (Decimal("4"), Decimal("3000"))}
        ),
    )
    return SimpleNamespace(
        hub=hub, prices=Market(), settings=trading(), halted="", target=None
    )


def executor_for(manager, world):
    def paper(path):
        return tm.PaperExchange(
            state_path=path,
            price_feed=world.prices.feed,
            fee_feed=lambda base, exchange: FEES,
            settings_source={},
        )

    return ome.OrderExecutor(
        manager.db,
        hub_dir=world.hub,
        trading=lambda: world.settings,
        paper=paper,
        live=lambda settings: world.target,
        quote=world.prices.quote,
        halt=lambda folder: world.halted,
        atr=lambda coin, exchange: 120.0,
    )


def view(
    root,
    manager,
    world,
    *,
    chart_coin="ETH",
    coins=("BTC", "ETH"),
    settings=None,
    buying_power=1000.0,
    mkt=None,
):
    if settings is not None:
        world.settings = settings
    v = omv.OrderManagementView(
        root,
        manager,
        coins=lambda: list(coins),
        chart_coin=lambda: chart_coin,
        trading=lambda: world.settings,
        buying_power=lambda: buying_power,
        market=mkt or market(("coinbase", connector("coinbase", fees=FEES))),
        executor=executor_for(manager, world),
        refresh_ms=None,
        sync=True,
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


def column(v, name, parent=""):
    i = omv.ORDER_COLUMNS.index(name)
    tree = v.orders_tree
    return [str(tree.item(iid, "values")[i]) for iid in tree.get_children(parent)]


def orders_in_db(manager):
    return omv.load_orders(manager.db)


def tops_in_db(manager):
    return [r for r in orders_in_db(manager) if not r.parent]


def set_created(manager, order_id, when):
    from order_management_models import Order

    with manager.db.get_session() as s:
        s.query(Order).filter(
            Order.id == uuid.UUID(str(order_id))
        ).one().created_at = when


def history(world, books="paper"):
    path = os.path.join(world.hub, books, "trade_history.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def fill(dlg, root, kind, side="Buy", qty="0.5", **fields):
    """Set the dialog to ``kind`` and its fields (variable name -> text)."""
    dlg.type_var.set(kind)
    dlg.side_var.set(side)
    dlg.qty_var.set(qty)
    for var, value in fields.items():
        getattr(dlg, var).set(value)
    root.update()


# ---- acceptance: one border, no repeated title, no scrollbar while it fits ----


def test_the_tab_has_one_border_and_no_title_repeating_its_name(root, manager, world):
    from tkinter import ttk

    v = view(root, manager, world)
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
    buttons = [str(w.cget("text")) for w in widgets if isinstance(w, ttk.Button)]
    for name in ("Create Order", "Refresh", "Cancel Selected", "Modify Selected"):
        assert name in buttons
    # the table style draws no border: only its rows' area
    style = ttk.Style(root)
    assert "border" not in str(style.layout(ui_table.STYLE)).lower()


def test_no_scrollbar_while_the_orders_and_notifications_fit(root, manager, world):
    for coin in ("BTC-USD", "ETH-USD"):
        manager.create_take_profit_order(coin, Decimal("0.1"), Decimal("70000"))
    root.geometry("960x420")  # the Leg column (an order's legs) takes 42 px more
    v = view(root, manager, world)
    assert len(v.orders_tree.get_children()) == 2
    assert v.orders_table.scrollbars_shown() == {"x": False, "y": False}
    assert v.notes_table.scrollbars_shown() == {"x": False, "y": False}


def test_many_orders_scroll_along_the_whole_table(root, manager, world):
    for n in range(40):
        manager.create_take_profit_order("BTC-USD", Decimal("0.1"), Decimal(70000 + n))
    v = view(root, manager, world)
    root.geometry("420x420")
    settle(root, v)
    t = v.orders_table
    assert t.scrollbars_shown() == {"x": True, "y": True}
    assert t.ysb.winfo_height() == t.tree.winfo_height()
    assert t.xsb.winfo_width() == t.tree.winfo_width()
    assert t.xsb.winfo_y() == t.tree.winfo_y() + t.tree.winfo_height()


# ---- acceptance: the dialog starts on a valid symbol and price ----


def test_the_dialog_starts_on_the_chart_coin_as_the_exchange_symbol(
    root, manager, world
):
    v = view(root, manager, world, chart_coin="ETH")
    dlg = open_dialog(v, root)
    assert dlg.coin_var.get() == "ETH"
    assert dlg.type_var.get() == omv.MARKET  # the default order type
    assert dlg.quote.exchange == "coinbase" and dlg.quote.pair == "ETH-USD"
    assert str(dlg.symbol_label.cget("text")) == "ETH-USD on Coinbase"
    assert str(dlg.market_price_label.cget("text")) == "$3,500.4 (the ask)"
    # the prices start at the market price for the side, never at a fixed number
    dlg.type_var.set(omv.STOP_LIMIT)
    assert (dlg.stop_var.get(), dlg.limit_var.get()) == ("3500.4", "3500.4")
    dlg.side_var.set("Sell")
    assert (dlg.stop_var.get(), dlg.limit_var.get()) == ("3500.1", "3500.1")
    dlg.limit_var.set("3400")  # typed in: it stays
    dlg.side_var.set("Buy")
    assert (dlg.stop_var.get(), dlg.limit_var.get()) == ("3500.4", "3400")
    # another coin: its own symbol and prices
    dlg.coin_var.set("BTC")
    root.update()
    assert dlg.quote.pair == "BTC-USD" and dlg.stop_var.get() == "67001.25"


def test_the_symbol_is_the_live_exchanges_own(root, manager, world):
    """Live on Binance: BTCUSDT, Binance's own market, from Binance's prices."""
    mkt = market(
        ("coinbase", connector("coinbase")),
        ("binance", connector("binance", {"BTC-USD": (66990.0, 66991.0)})),
    )
    v = view(
        root,
        manager,
        world,
        chart_coin="BTC",
        settings=trading("live", "binance"),
        mkt=mkt,
    )
    dlg = open_dialog(v, root)
    assert str(dlg.symbol_label.cget("text")) == "BTCUSDT on Binance"
    assert (dlg.quote.bid, dlg.quote.ask) == (66990.0, 66991.0)


def test_in_paper_mode_the_primary_exchange_answers_first(root, manager, world):
    """Kraken is primary but has no price: the next exchange in Settings answers,
    with its own symbol."""
    mkt = market(
        ("kraken", connector("kraken", prices=None)),
        ("coinbase", connector("coinbase")),
        primary="kraken",
    )
    dlg = open_dialog(view(root, manager, world, chart_coin="BTC", mkt=mkt), root)
    assert str(dlg.symbol_label.cget("text")) == "BTC-USD on Coinbase"
    assert dlg.quote.ask == 67001.25


def test_with_no_price_the_symbol_is_the_primary_exchanges(root, manager, world):
    mkt = market(
        ("binance", connector("binance", prices=None)),
        ("coinbase", connector("coinbase", prices=None)),
    )
    dlg = open_dialog(view(root, manager, world, chart_coin="BTC", mkt=mkt), root)
    assert dlg.quote.pair == "BTCUSDT" and "No price for BTC" in dlg.quote.problem


def test_with_the_account_chart_shown_the_dialog_starts_on_the_first_coin(
    root, manager, world
):
    dlg = open_dialog(view(root, manager, world, chart_coin="ACCOUNT"), root)
    assert dlg.coin_var.get() == "BTC" and dlg.quote.pair == "BTC-USD"


def test_the_coins_are_the_settings_coins_as_coins(root, manager, world):
    v = view(root, manager, world, coins=("btc", "ETH-USD", "BTCUSDT"))
    dlg = open_dialog(v, root)
    assert dlg.coins == ["BTC", "ETH"]


def test_the_market_is_looked_up_in_the_background(root, manager, world):
    v = view(root, manager, world, chart_coin="BTC")
    dlg = v.open_dialog()  # background=True: the hub's way
    dlg.attributes("-alpha", 0.0)
    end = time.time() + 10
    while dlg.quote is None and time.time() < end:
        root.update()
        time.sleep(0.01)
    assert dlg.quote is not None and dlg.quote.pair == "BTC-USD"


def test_the_fee_comes_from_the_exchanges_trading_fees(root, manager, world):
    dlg = open_dialog(view(root, manager, world), root)
    dlg.qty_var.set("1")
    root.update()
    assert str(dlg.value_label.cget("text")) == "$3,500.40"
    assert str(dlg.fee_label.cget("text")) == "$21.00 (0.60%, taker)"
    fill(dlg, root, omv.LIMIT, qty="1", limit_var="3000")
    assert str(dlg.fee_label.cget("text")) == "$12.00 (0.40%, maker)"


def test_with_no_trading_fees_the_fee_is_not_known(root, manager, world):
    mkt = market(("coinbase", connector("coinbase", fees=None)))
    dlg = open_dialog(view(root, manager, world, mkt=mkt), root)
    dlg.qty_var.set("1")
    root.update()
    assert str(dlg.fee_label.cget("text")) == "not known"


# ---- the order types: only their own fields ----


def test_each_type_shows_only_the_fields_it_needs(root, manager, world):
    dlg = open_dialog(view(root, manager, world), root)
    expected = {
        omv.MARKET: ["Price"],
        omv.LIMIT: ["Limit price"],
        omv.STOP_LIMIT: ["Stop price", "Limit price"],
        omv.TRAILING_STOP: ["Trail", "Trail distance"],
        omv.OCO: ["Take-profit price", "Stop price"],
        omv.BRACKET: ["Entry", "Take-profit price", "Stop price"],
    }
    assert tuple(expected) == omv.ORDER_TYPES == tuple(dlg.type_box.cget("values"))
    for kind, labels in expected.items():
        dlg.type_var.set(kind)
        root.update()
        assert list(dlg.fields) == labels, kind
        shown = [
            str(w.cget("text"))
            for w in dlg._body.grid_slaves(column=0)
            if w.winfo_class() == "TLabel"
        ]
        for other in {"Limit price", "Stop price", "Take-profit price", "Trail"}:
            assert (other in shown) == (other in labels), (kind, other)


def test_no_iceberg_twap_or_vwap():
    names = " ".join(omv.ORDER_TYPES + tuple(ome.KINDS)).lower()
    for gone in ("iceberg", "twap", "vwap"):
        assert gone not in names


def test_the_dialog_says_which_orders_powertrader_manages(root, manager, world):
    dlg = open_dialog(view(root, manager, world), root)
    assert str(dlg.how_label.cget("text")) == (
        "Fills at once in the paper account, at the market."
    )
    for kind in (omv.LIMIT, omv.STOP_LIMIT, omv.TRAILING_STOP, omv.OCO, omv.BRACKET):
        dlg.type_var.set(kind)
        root.update()
        text = str(dlg.how_label.cget("text"))
        assert "managed by PowerTrader, requires the app to be running" in text, kind


def test_live_on_binance_its_own_order_types_are_placed_there(root, manager, world):
    mkt = market(("binance", connector("binance", {"ETH-USD": (3500.0, 3501.0)})))
    v = view(root, manager, world, settings=trading("live", "binance"), mkt=mkt)
    dlg = open_dialog(v, root)
    for kind in (omv.LIMIT, omv.STOP_LIMIT, omv.OCO):
        dlg.type_var.set(kind)
        root.update()
        assert str(dlg.how_label.cget("text")) == "Placed on Binance as its own order."
    fill(dlg, root, omv.TRAILING_STOP, trail_mode_var=omv.TRAIL_PERCENT, trail_var="2")
    assert str(dlg.how_label.cget("text")) == "Placed on Binance as its own order."
    fill(dlg, root, omv.TRAILING_STOP, trail_mode_var=omv.TRAIL_ATR, trail_var="1.5")
    assert "managed by PowerTrader" in str(dlg.how_label.cget("text"))


def test_a_trailing_stop_shows_its_distance(root, manager, world):
    dlg = open_dialog(view(root, manager, world), root)
    fill(dlg, root, omv.TRAILING_STOP, side="Sell", trail_var="2")
    assert str(dlg.trail_label.cget("text")) == "$70.002 (2% of $3,500.1)"
    dlg.trail_mode_var.set(omv.TRAIL_ATR)
    dlg.trail_var.set("1.5")
    root.update()
    assert dlg.atr == 120.0
    assert str(dlg.trail_label.cget("text")).startswith("$180 (1.5 × ATR(14)")


# ---- acceptance: a buy above Buying Power is refused ----


def test_a_buy_above_buying_power_is_refused(root, manager, world, dialogs):
    dlg = open_dialog(view(root, manager, world, buying_power=100.0), root)
    dlg.qty_var.set("1")  # 1 ETH at the ask: $3,500.40
    root.update()
    assert str(dlg.warning_label.cget("text")) == "More than Buying Power"
    assert dlg.create() is None
    name, title, message, _kw = dialogs.calls[-1]
    assert name == "showerror" and title == "Order refused"
    assert "$3,521.40" in message and "more than Buying Power, $100.00" in message
    assert not [c for c in dialogs.calls if c[0] == "askyesno"]  # not offered
    assert orders_in_db(manager) == [] and dlg.winfo_exists()


def test_the_fee_counts_towards_buying_power(root, manager, world, dialogs):
    dlg = open_dialog(view(root, manager, world, buying_power=3510.0), root)
    dlg.qty_var.set("1")  # $3,500.40 + $21.00 fee
    assert dlg.create() is None and orders_in_db(manager) == []


def test_a_buy_is_refused_while_buying_power_is_not_known(
    root, manager, world, dialogs
):
    dlg = open_dialog(view(root, manager, world, buying_power=None), root)
    dlg.qty_var.set("0.01")
    assert dlg.create() is None
    assert "Buying Power is not known" in dialogs.calls[-1][2]
    assert orders_in_db(manager) == []


def test_a_market_buy_is_confirmed_then_fills_the_paper_account(
    root, manager, world, dialogs
):
    v = view(root, manager, world, buying_power=100.0)
    dlg = open_dialog(v, root)
    dlg.qty_var.set("0.01")  # $35.00
    order_id = dlg.create()
    assert order_id
    name, title, message, kw = [c for c in dialogs.calls if c[0] == "askyesno"][-1]
    assert title == "Confirm order"
    assert "Account: Paper account" in message
    assert "Buy 0.01 ETH-USD on Coinbase" in message and "Type: Market" in message
    (row,) = orders_in_db(manager)
    assert (row.symbol, row.kind, row.side, row.status) == (
        "ETH-USD",
        "Market",
        "Buy",
        "filled",
    )
    settle(root, v)
    v.status_var.set("All")
    settle(root, v)
    assert column(v, "symbol") == ["ETH-USD"]  # the table refreshed
    assert tm.read_paper_book(tm.paper_book_path(world.hub)).positions["ETH"][
        0
    ] == Decimal("4.01")
    (trade,) = history(world)
    assert (trade["tag"], trade["qty"], trade["price"]) == ("MANUAL", 0.01, 3500.4)
    assert trade["fees_usd"] == pytest.approx(0.01 * 3500.4 * 0.006)


def test_answering_no_creates_nothing(root, manager, world, dialogs):
    dialogs.answer = False
    dlg = open_dialog(view(root, manager, world), root)
    dlg.qty_var.set("0.01")
    assert dlg.create() is None and orders_in_db(manager) == []


def test_a_sell_is_not_checked_against_buying_power(root, manager, world, dialogs):
    """A stop-limit sell sells a holding: it spends no Buying Power."""
    dlg = open_dialog(view(root, manager, world, buying_power=100.0), root)
    fill(
        dlg,
        root,
        omv.STOP_LIMIT,
        side="Sell",
        qty="3",
        stop_var="3400",
        limit_var="3390",
    )
    assert dlg.create()
    (row,) = orders_in_db(manager)
    assert (row.kind, row.side, row.stop, row.price, row.status) == (
        "Stop-Limit",
        "Sell",
        3400.0,
        3390.0,
        "submitted",
    )
    assert "Managed by PowerTrader" in row.conditions


def test_a_stop_the_market_has_passed_is_refused(root, manager, world, dialogs):
    dlg = open_dialog(view(root, manager, world), root)
    fill(dlg, root, omv.STOP_LIMIT, side="Sell", stop_var="3600", limit_var="3590")
    assert dlg.create() is None
    assert "below the bid" in dialogs.calls[-1][2]


def test_a_live_order_names_the_exchange_and_is_confirmed_as_live(
    root, manager, world, dialogs
):
    mkt = market(("binance", connector("binance", {"ETH-USD": (3500.0, 3501.0)})))
    world.target = FakeTarget(mkt.connector("binance"))
    v = view(root, manager, world, settings=trading("live", "binance"), mkt=mkt)
    dlg = open_dialog(v, root)
    assert str(dlg.account_label.cget("text")) == "Account: Binance, live (real money)"
    dlg.qty_var.set("0.01")
    assert dlg.create()
    name, title, message, kw = [c for c in dialogs.calls if c[0] == "askyesno"][-1]
    assert title == "Confirm live order"
    assert kw["icon"] == "warning" and kw["default"] == "no"
    assert "Account: Binance, live (real money)" in message
    assert orders_in_db(manager)[0].symbol == "ETHUSDT"
    assert world.target.orders == [("ETH-USD", "buy", 0.01)]


def test_live_mode_with_no_exchange_chosen_refuses_the_order(
    root, manager, world, dialogs
):
    v = view(root, manager, world, settings=trading("live", None))
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


# ---- acceptance: a halt stops manual orders too ----


def test_no_order_is_created_while_trading_is_halted(root, manager, world, dialogs):
    world.halted = "Account drawdown 25%"
    dlg = open_dialog(view(root, manager, world), root)
    dlg.qty_var.set("0.01")
    root.update()
    assert "Trading is halted" in str(dlg.warning_label.cget("text"))
    assert dlg.create() is None
    name, title, message, _kw = dialogs.calls[-1]
    assert title == "Order refused" and "Account drawdown 25%" in message
    assert "Settings > Risk" in message
    assert orders_in_db(manager) == []


# ---- acceptance: each type in paper mode, in Active Orders, filled ----


def test_each_order_type_is_placed_shown_and_filled_in_paper_mode(
    root, manager, world, dialogs
):
    v = view(root, manager, world, buying_power=100_000.0)
    made = {}
    for kind, side, fields in (
        (omv.MARKET, "Buy", {}),
        (omv.LIMIT, "Buy", {"limit_var": "3400"}),
        (omv.STOP_LIMIT, "Sell", {"stop_var": "3450", "limit_var": "3440"}),
        (omv.TRAILING_STOP, "Sell", {"trail_var": "1"}),
        (omv.OCO, "Sell", {"tp_var": "3600", "stop_var": "3300"}),
        (omv.BRACKET, "Buy", {"tp_var": "3700", "stop_var": "3420"}),
    ):
        dlg = open_dialog(v, root)
        fill(dlg, root, kind, side=side, qty="0.5", **fields)
        made[kind] = dlg.create()
        assert made[kind], kind
    v.status_var.set("All")
    settle(root, v)
    assert sorted(column(v, "type")) == sorted(omv.ORDER_TYPES)
    # an OCO or Bracket order's legs are under it, named in the Leg column
    oco = made[omv.OCO]
    assert [v.orders_tree.item(i, "text") for i in v.orders_tree.get_children(oco)] == [
        "Take-profit",
        "Stop",
    ]
    assert column(v, "type", oco) == ["Limit", "Stop"]
    # the Leg column fits its names, one indent in
    from tkinter import font as tkfont

    body = tkfont.nametofont("TkDefaultFont")
    leg_width = int(v.orders_tree.column("#0", "width"))
    assert leg_width >= body.measure("Take-profit") + ui_table.TREE_INDENT
    bracket = made[omv.BRACKET]
    assert [
        v.orders_tree.item(i, "text") for i in v.orders_tree.get_children(bracket)
    ] == ["Entry", "Take-profit", "Stop"]

    # the market falls through every stop and the limit, then rises past the
    # take-profits
    for bid, ask in ((3395.0, 3396.0), (3380.0, 3381.0), (3290.0, 3291.0)):
        world.prices.set("ETH", bid, ask)
        v.executor.check()
    world.prices.set("ETH", 3800.0, 3801.0)
    v.executor.check()
    v.refresh()
    settle(root, v)
    status = {r.id: r.status for r in orders_in_db(manager)}
    for kind in omv.ORDER_TYPES:
        assert status[made[kind]] == "filled", kind
    trades = history(world)
    assert len(trades) == 7  # one fill each; the Bracket's entry and one exit
    assert {t["tag"] for t in trades} == {"MANUAL"}
    assert all(t["fees_usd"] and t["fee_rate"] in (0.004, 0.006) for t in trades)
    book = tm.read_paper_book(tm.paper_book_path(world.hub))
    # 4 ETH held, +0.5 market, +0.5 limit, -0.5 stop-limit, -0.5 trail, -0.5 OCO,
    # +0.5 -0.5 bracket
    assert book.positions["ETH"][0] == Decimal("3.5")
    fees = sum(t["fees_usd"] for t in trades)
    flows = sum(
        (-1 if t["side"] == "buy" else 1) * t["qty"] * t["price"] for t in trades
    )
    assert float(book.cash_balance) == pytest.approx(10000 + flows - fees)


# ---- acceptance: one Cancel cancels an OCO or Bracket order's legs ----


@pytest.mark.parametrize("pick", ["parent", "leg"])
def test_cancel_selected_cancels_every_leg_of_an_oco(
    root, manager, world, dialogs, pick
):
    v = view(root, manager, world)
    dlg = open_dialog(v, root)
    fill(dlg, root, omv.OCO, side="Sell", qty="1", tp_var="3600", stop_var="3300")
    oco = dlg.create()
    settle(root, v)
    legs = v.orders_tree.get_children(oco)
    v.orders_tree.selection_set([oco] if pick == "parent" else [legs[1]])
    assert v.cancel_selected() == 1
    message = [c for c in dialogs.calls if c[0] == "askyesno"][-1][2]
    assert "Cancel 1 order?" in message and "with its 2 legs" in message
    assert {r.status for r in orders_in_db(manager)} == {"cancelled"}


def test_cancel_selected_cancels_a_bracket_with_its_legs(root, manager, world, dialogs):
    v = view(root, manager, world, buying_power=100_000.0)
    dlg = open_dialog(v, root)
    fill(
        dlg,
        root,
        omv.BRACKET,
        qty="1",
        entry_var=omv.LIMIT,
        limit_var="3400",
        tp_var="3700",
        stop_var="3300",
    )
    bracket = dlg.create()
    settle(root, v)
    v.orders_tree.selection_set([bracket])
    assert v.cancel_selected() == 1
    rows = orders_in_db(manager)
    assert len(rows) == 4 and {r.status for r in rows} == {"cancelled"}


# ---- Modify Selected ----


def test_modify_selected_changes_an_orders_prices(root, manager, world, dialogs):
    v = view(root, manager, world)
    dlg = open_dialog(v, root)
    fill(dlg, root, omv.LIMIT, qty="0.1", limit_var="3400")
    order_id = dlg.create()
    settle(root, v)
    v.orders_tree.selection_set([order_id])
    m = v.modify_selected()
    m.attributes("-alpha", 0.0)
    assert set(m.vars) == {"quantity", "price"}
    m.vars["price"].set("3300")
    m.vars["quantity"].set("0.2")
    m.save()
    root.update()
    (row,) = orders_in_db(manager)
    assert (row.price, row.quantity) == (3300.0, 0.2)
    assert not m.winfo_exists()


def test_modify_says_why_a_change_is_refused(root, manager, world, dialogs):
    v = view(root, manager, world)
    dlg = open_dialog(v, root)
    fill(dlg, root, omv.OCO, side="Sell", qty="1", tp_var="3600", stop_var="3300")
    oco = dlg.create()
    settle(root, v)
    v.orders_tree.selection_set([oco])
    m = v.modify_selected()
    assert set(m.vars) == {"quantity", "stop_price", "take_profit"}
    m.vars["stop_price"].set("3550")  # above the bid
    m.save()
    root.update()
    assert "stop below it" in str(m.message.cget("text")) and m.winfo_exists()


def test_modify_needs_one_open_order(root, manager, world, dialogs):
    v = view(root, manager, world)
    assert v.modify_selected() is None
    assert "Select one open order" in dialogs.calls[-1][2]


# ---- acceptance: no "coming soon" in Order Management ----


def test_no_coming_soon_anywhere_in_order_management():
    for name in os.listdir(APP_DIR):
        if name.startswith("order_management") and name.endswith(".py"):
            with open(os.path.join(APP_DIR, name), encoding="utf-8") as f:
                text = f.read()
            assert not re.search(
                r"coming\s+soon|not\s+implemented\s+yet", text, re.I
            ), name


# ---- acceptance: filter, search and sort together ----


def test_status_filter_search_and_sort_work_together(root, manager, world, dialogs):
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

    v = view(root, manager, world)
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


def test_a_group_is_kept_by_the_filter_when_one_of_its_legs_is(
    root, manager, world, dialogs
):
    v = view(root, manager, world)
    dlg = open_dialog(v, root)
    fill(dlg, root, omv.OCO, side="Sell", qty="1", tp_var="3600", stop_var="3300")
    oco = dlg.create()
    world.prices.set("ETH", 3610.0, 3611.0)
    v.executor.check()
    v.refresh()
    v.status_var.set("Cancelled")  # only its stop leg was cancelled
    settle(root, v)
    assert list(v.orders_tree.get_children()) == [oco]
    assert len(v.orders_tree.get_children(oco)) == 2
    v.status_var.set("Rejected")
    settle(root, v)
    assert v.orders_table.is_empty_shown()
    v.status_var.set("All")
    v.search_var.set("take-profit")  # the leg's name
    v._search_now()
    settle(root, v)
    assert list(v.orders_tree.get_children()) == [oco]


def test_widths_and_sort_are_kept_between_sessions(root, manager, world):
    v = view(root, manager, world)
    v.orders_table.sort_by("symbol")
    assert ui_table.saved_layout("order_management")["sort"] == ["symbol", False]
    again = view(root, manager, world)
    assert again.orders_table.sort_order == ("symbol", False)


# ---- the toolbar ----


def test_cancel_selected_cancels_the_open_orders_chosen(root, manager, world, dialogs):
    from order_management_models import OrderStatus

    a = manager.create_take_profit_order("BTC-USD", Decimal("1"), Decimal("70000"))
    b = manager.create_take_profit_order("ETH-USD", Decimal("2"), Decimal("4000"))
    c = manager.create_take_profit_order("ETH-USD", Decimal("3"), Decimal("4000"))
    manager.db.update_order_status(c, OrderStatus.FILLED)
    v = view(root, manager, world)
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


def test_a_refresh_keeps_the_selection(root, manager, world):
    a = manager.create_take_profit_order("BTC-USD", Decimal("1"), Decimal("70000"))
    v = view(root, manager, world)
    v.orders_tree.selection_set([str(a)])
    manager.create_take_profit_order("ETH-USD", Decimal("2"), Decimal("4000"))
    v.refresh()
    settle(root, v)
    assert len(v.orders_tree.get_children()) == 2
    assert v.orders_tree.selection() == (str(a),)


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


# ---- the monitor ----


def test_the_monitor_works_on_a_thread_that_stops_with_the_tab(
    root, manager, world, dialogs
):
    v = omv.OrderManagementView(
        root,
        manager,
        coins=lambda: ["ETH"],
        chart_coin=lambda: "ETH",
        trading=lambda: world.settings,
        buying_power=lambda: 1000.0,
        market=market(("coinbase", connector("coinbase", fees=FEES))),
        executor=executor_for(manager, world),
        refresh_ms=50,
    )
    v.pack(fill="both", expand=True)
    order_id = v.executor.create(
        ome.OrderSpec(
            kind=ome.LIMIT,
            coin="ETH",
            side="buy",
            quantity=Decimal("0.1"),
            exchange="coinbase",
            pair="ETH-USD",
            price=Decimal("3400"),
        )
    )
    v.order_created(order_id)
    world.prices.set("ETH", 3390.0, 3391.0)
    end = time.time() + 10
    while time.time() < end:
        root.update()
        row = next((r for r in v.orders if r.id == order_id), None)
        if row is not None and row.status == "filled":
            break
        time.sleep(0.02)
    assert row is not None and row.status == "filled"
    thread = v.jobs.thread
    assert thread is not None and thread.is_alive()
    v.destroy()
    thread.join(timeout=5)
    assert not thread.is_alive()


# ---- the notifications ----


def test_notifications_newest_first_and_mark_all_read(root, manager, world):
    from order_management_models import Notification

    manager.create_take_profit_order("BTC-USD", Decimal("1"), Decimal("70000"))
    manager.create_take_profit_order("ETH-USD", Decimal("2"), Decimal("4000"))
    with manager.db.get_session() as s:
        notes = s.query(Notification).all()
        for n, note in enumerate(sorted(notes, key=lambda x: x.title)):
            note.created_at = datetime(2026, 11, 4, 9, 0, 0) + timedelta(minutes=n)
    v = view(root, manager, world)
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


def test_the_splitter_keeps_both_panes_at_their_minimum_height(root, manager, world):
    v = view(root, manager, world)
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
        names = [
            pt_hub.module_tab_name(hub.bottom_notebook.tab(t, "text"))
            for t in hub.bottom_notebook.tabs()
        ]
        assert "Order Management" in names and "Advanced Orders" not in names
        # the executor carries out the hub's orders on the hub's books
        assert isinstance(view_.executor, ome.OrderExecutor)
        assert view_.executor.hub_dir() == hub.hub_dir
        assert view_.executor.settings() is hub._trading
        assert manager.condition_check_thread is None  # no idle monitoring thread
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
