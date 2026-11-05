"""The hub's Order Management tab (owner, 2026-11-04; order types 2026-11-05).

A toolbar (Create Order, Refresh, Cancel Selected, Modify Selected, a status filter
and a search) over the Active Orders table, and the Order Notifications under it,
with a splitter between them. Orders and notifications are read from the order
management database (order_management_db). An OCO or Bracket order is one row with
its legs under it; cancelling it, or any of its legs, cancels them all.

Create Order opens ``OrderDialog``. Its order types are Market, Limit, Stop-Limit,
Trailing Stop, OCO and Bracket, each with only the fields it needs:

* the coin shown in the chart (the first coin while the chart shows the account),
  from the coins in Settings, as the symbol of the exchange the order is for: the
  live exchange in live mode, otherwise the exchange layer's, primary exchange
  first (``BTC-USD`` on Coinbase, ``BTCUSDT`` on Binance);
* that exchange's current bid and ask, which fill the price fields (a buy's from
  the ask, a sell's from the bid);
* how the order is carried out: placed on the exchange as its own order where the
  exchange has that kind, else managed by PowerTrader (order_management_execution);
* the order's estimated value, and its fee from ``trading_fees()``;
* the account it is for (paper, or the live exchange), and a confirmation before it
  is created. A buy worth more than Buying Power is refused, and so is every order
  while trading is halted (Settings > Risk).

The tab's monitor (``refresh_ms``) reads the database again and lets the
OrderExecutor carry the open orders on (``OrderExecutor.check``), on a worker thread
that stops with the tab.
"""

import queue
import threading
import tkinter as tk
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import order_management_execution as ome
import ui_jobs
import ui_table
import ui_tokens

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
ORDER_LIMIT = 500  # the newest orders the table reads
NOTE_LIMIT = 200  # the newest notifications the pane reads
REFRESH_MS = 5000

# ---- the orders table ----

ORDER_COLUMNS = (
    "created",
    "symbol",
    "type",
    "side",
    "quantity",
    "price",
    "stop",
    "status",
    "conditions",
    "order_id",
)
ORDER_HEADINGS = {
    "created": "Created",
    "symbol": "Symbol",
    "type": "Type",
    "side": "Side",
    "quantity": "Quantity",
    "price": "Price",
    "stop": "Stop Price",
    "status": "Status",
    "conditions": "Conditions",
    "order_id": "Order ID",
}
ORDER_NUMERIC = ("quantity", "price", "stop")
LEG_HEADING = "Leg"  # the tree column: an OCO or Bracket order's legs are named there
LEG_NAMES = {"entry": "Entry", "take_profit": "Take-profit", "stop": "Stop"}
LEG_ORDER = {name: n for n, name in enumerate(LEG_NAMES.values())}

OPEN_STATUSES = ("pending", "submitted", "partial")
STATUS_FILTERS: Tuple[Tuple[str, Optional[Tuple[str, ...]]], ...] = (
    ("Open", OPEN_STATUSES),
    ("Filled", ("filled",)),
    ("Cancelled", ("cancelled",)),
    ("Rejected", ("rejected", "expired")),
    ("All", None),
)
NO_ORDERS = "No orders yet"
NO_MATCH = "No orders match these filters"

NOTE_COLUMNS = ("time", "event", "details")
NOTE_HEADINGS = {"time": "Time", "event": "Event", "details": "Details"}
NO_NOTES = "No notifications yet"
NOTES_TITLE = "Order Notifications"

MIN_ORDERS_PX = 110  # the orders pane: the toolbar and a few rows
MIN_NOTES_PX = 90  # the notifications pane: its title row and a few rows

# ---- order types (the dialog's names; the table shows the same) ----

MARKET = "Market"
LIMIT = "Limit"
STOP_LIMIT = "Stop-Limit"
TRAILING_STOP = "Trailing Stop"
OCO = "OCO"
BRACKET = "Bracket"
ORDER_TYPES = (MARKET, LIMIT, STOP_LIMIT, TRAILING_STOP, OCO, BRACKET)
KIND_OF = {
    MARKET: ome.MARKET,
    LIMIT: ome.LIMIT,
    STOP_LIMIT: ome.STOP_LIMIT,
    TRAILING_STOP: ome.TRAILING_STOP,
    OCO: ome.OCO,
    BRACKET: ome.BRACKET,
}
NAME_OF = {kind: name for name, kind in KIND_OF.items()}
TYPE_ROWS = 3  # the most rows an order type's own fields take (Bracket)
SIDES = ("Buy", "Sell")
TRAIL_PERCENT = "Percent"
TRAIL_ATR = "ATR multiple"
TRAIL_MODES = (TRAIL_PERCENT, TRAIL_ATR)
ENTRY_TYPES = (MARKET, LIMIT)

# The names of orders made before these types (their rows are still shown)
STOP_LOSS = "Stop Loss"
TAKE_PROFIT = "Take Profit"
DCA = "DCA"
CONDITIONAL = "Conditional"

TYPE_NAMES = {
    "market": MARKET,
    "limit": LIMIT,
    "stop": "Stop",
    "stop_limit": STOP_LIMIT,
    "trailing_stop": TRAILING_STOP,
    "conditional": CONDITIONAL,
    "bracket": BRACKET,
    "oco": OCO,
}
CONDITION_NAMES = {
    "price": "Price",
    "neural_level": "Neural level",
    "volume": "Volume",
    "time": "Time",
    "indicator": "Indicator",
    "portfolio_pct": "Portfolio %",
}
OPERATOR_SIGNS = {"gt": ">", "lt": "<", "gte": "≥", "lte": "≤", "eq": "=", "ne": "≠"}


def _value(enum_or_text: Any) -> str:
    return str(getattr(enum_or_text, "value", enum_or_text) or "")


def _float(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError, ArithmeticError):
        return None


def plain_number(value: Any) -> str:
    """A quantity or price as typed: no grouping, no trailing zeros."""
    number = _float(value)
    if number is None:
        return ""
    return f"{number:.8f}".rstrip("0").rstrip(".") or "0"


def _plain_money(value: float) -> str:
    return f"${value:,.2f}"


def _plain_price(value: float) -> str:
    return "$" + f"{value:,.8f}".rstrip("0").rstrip(".")


def local_time(when: Optional[datetime]) -> str:
    """The order database's times (UTC, without a zone) in local time."""
    if when is None:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone().strftime(TIME_FORMAT)


def type_name(order_type: Any, tag: Optional[str]) -> str:
    """An order's type as the table shows it: an older order's tag tells a
    take-profit or stop-loss from a plain limit or stop order, and a DCA stage from
    a plain conditional order."""
    kind = _value(order_type)
    tag = str(tag or "").upper()
    if kind == "limit" and tag == "TAKE_PROFIT":
        return TAKE_PROFIT
    if kind == "stop" and tag in ("STOP_LOSS", ""):
        return STOP_LOSS
    if kind == "conditional" and tag.startswith("DCA_STAGE_"):
        return f"DCA (stage {tag[len('DCA_STAGE_'):]})"
    return TYPE_NAMES.get(kind) or kind.replace("_", " ").title()


def condition_text(condition_type: Any, operator: Any, target: Any, met=False) -> str:
    name = CONDITION_NAMES.get(_value(condition_type), _value(condition_type))
    sign = OPERATOR_SIGNS.get(_value(operator), _value(operator))
    number = _float(target)
    shown = (
        f"{number:,.8f}".rstrip("0").rstrip(".") if number is not None else str(target)
    )
    return f"{name} {sign} {shown}" + (" (met)" if met else "")


def _grouped(number: Any) -> str:
    value = _float(number)
    return "" if value is None else f"{value:,.8f}".rstrip("0").rstrip(".")


def how_text(order: Any, m: Any) -> str:
    """What the Conditions column says of how an order is carried out: its trail,
    where it is, and what last held it up."""
    if m is None:
        return ""
    parts = []
    if m.trail_mode == ome.PERCENT and m.trail_value is not None:
        parts.append(f"Trail {_grouped(m.trail_value)}%")
    elif m.trail_mode == ome.ATR and m.trail_value is not None:
        parts.append(f"Trail {_grouped(m.trail_value)} × ATR {_grouped(m.atr)}")
    if m.best_price is not None:
        parts.append(f"best {_grouped(m.best_price)}")
    if m.state == "waiting":
        parts.append("Waits for the entry to fill")
    elif m.state == "triggered":
        parts.append("Stop reached: the limit works")
    open_ = _value(order.status) in OPEN_STATUSES
    if open_ and m.role in ("order", "group"):
        if m.handling == ome.BY_EXCHANGE:
            from pt_exchange_abstraction import exchange_name

            parts.append(f"On {exchange_name(m.exchange)}")
        elif _value(order.order_type) != "market":
            parts.append("Managed by PowerTrader")
    if m.note:
        parts.append(str(m.note))
    return "; ".join(parts)


@dataclass(frozen=True)
class OrderRow:
    """One order of the order management database, as the table shows it."""

    id: str
    client_id: str
    created: Optional[datetime]
    symbol: str
    kind: str
    side: str  # "Buy" | "Sell"
    quantity: Optional[float]
    price: Optional[float]
    stop: Optional[float]
    status: str  # OrderStatus value: pending, submitted, partial, filled, ...
    conditions: str
    parent: str = ""  # an OCO or Bracket order's id, for its legs
    leg: str = ""  # the leg's name: Entry, Take-profit, Stop

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


def order_row(order: Any, m: Any = None) -> OrderRow:
    """The OrderRow of an ``Order`` (and its ManagedOrder, when Order Management
    carries it out) read in an open session."""
    conditions = [
        condition_text(c.condition_type, c.operator, c.target_value, bool(c.is_met))
        for c in (order.conditions or [])
    ]
    how = how_text(order, m)
    if how:
        conditions.append(how)
    return OrderRow(
        id=str(order.id),
        client_id=str(order.client_order_id or ""),
        created=order.created_at,
        symbol=str(order.symbol or ""),
        kind=type_name(order.order_type, order.tag),
        side=_value(order.side).capitalize(),
        quantity=_float(order.quantity),
        price=_float(order.price),
        stop=_float(order.stop_price),
        status=_value(order.status),
        conditions="; ".join(conditions),
        parent=str(order.parent_order_id or ""),
        leg=LEG_NAMES.get(getattr(m, "role", ""), ""),
    )


def load_orders(db: Any, limit: int = ORDER_LIMIT) -> List[OrderRow]:
    """The newest ``limit`` orders of the database, newest first, with the legs of
    any OCO or Bracket order among them (read only)."""
    from order_management_models import ManagedOrder, Order

    with db.get_session() as session:
        rows = (
            session.query(Order, ManagedOrder)
            .outerjoin(ManagedOrder, ManagedOrder.order_id == Order.id)
            .order_by(Order.created_at.desc())
            .limit(limit)
            .all()
        )
        out = [order_row(o, m) for o, m in rows]
        have = {r.id for r in out}
        groups = [o.id for o, m in rows if m is not None and m.role == "group"]
        if groups:
            legs = (
                session.query(Order, ManagedOrder)
                .outerjoin(ManagedOrder, ManagedOrder.order_id == Order.id)
                .filter(Order.parent_order_id.in_(groups))
                .all()
            )
            out += [order_row(o, m) for o, m in legs if str(o.id) not in have]
        return out


@dataclass(frozen=True)
class NoteRow:
    """One notification of the order management database."""

    id: str
    created: Optional[datetime]
    title: str
    message: str
    unread: bool


def load_notifications(db: Any, limit: int = NOTE_LIMIT) -> List[NoteRow]:
    """The newest ``limit`` notifications, read or not, newest first (read only)."""
    from order_management_models import Notification

    with db.get_session() as session:
        notes = (
            session.query(Notification)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        return [
            NoteRow(
                id=str(n.id),
                created=n.created_at,
                title=str(n.title or ""),
                message=str(n.message or ""),
                unread=not n.is_read,
            )
            for n in notes.all()
        ]


# ---- the account an order is for ----


def account_text(trading: Any) -> Tuple[str, str]:
    """(the account an order is for, its banner: "paper", "live", "testnet" or
    "blocked"), from the hub's trading settings (trading_mode.TradingSettings)."""
    from pt_exchange_abstraction import exchange_name

    if trading is None or not getattr(trading, "is_live", False):
        return "Paper account", "paper"
    broker = getattr(trading, "active_broker", None)
    if not broker:
        return "Live, with no exchange chosen", "blocked"
    name = exchange_name(broker)
    if getattr(trading, "uses_testnet", False):
        return f"{name} testnet", "testnet"
    if getattr(trading, "uses_preview", False):
        return f"{name}, live (preview orders: nothing is placed)", "live"
    return f"{name}, live (real money)", "live"


# ---- symbols, prices and fees, through the exchange layer ----


@dataclass(frozen=True)
class MarketQuote:
    """What the dialog shows of the exchange an order is for."""

    exchange: str  # ExchangeType value, e.g. "coinbase"
    pair: str  # that exchange's own market, e.g. "BTC-USD"
    bid: Optional[float] = None
    ask: Optional[float] = None
    fees: Any = None  # TradingFees (maker and taker rates, as fractions), or None
    problem: str = ""  # why there is no bid and ask, when there are none

    @property
    def fee_rate(self) -> Optional[float]:
        """The taker rate: a market order's."""
        return self.fees.taker if self.fees is not None else None


def trading_fees_of(connector: Any, symbol: str) -> Any:
    """The connector's ``trading_fees(symbol)`` (a TradingFees), or None when it has
    none or gives no usable rates."""
    from pt_exchange_abstraction import usable_fees

    fees = getattr(connector, "trading_fees", None)
    if not callable(fees):
        return None
    try:
        return usable_fees(fees(symbol))
    except Exception:
        return None


class ExchangeMarket:
    """Symbols, bid and ask, fees and a coin's ATR for the order dialog. A live
    order's come from the live exchange; otherwise from the exchanges in Settings,
    the primary first (``pt_multi_exchange.market_exchanges``, public market data:
    no credentials). ``atr(coin, exchange)`` is for tests (default:
    ``order_management_execution.candle_atr``)."""

    def __init__(
        self,
        layer: Optional[Callable[[], Any]] = None,
        atr: Optional[Callable[[str, str], Optional[float]]] = None,
    ):
        self._layer = layer
        self._atr = atr
        self._connectors: Dict[str, Any] = {}

    def _manager(self):
        if self._layer is not None:
            return self._layer()
        from pt_multi_exchange import market_exchanges

        return market_exchanges()

    def connector(self, exchange: str):
        """The exchange's connector: the layer's when it is connected there, else
        one built without credentials (as the hub's Exchange line does)."""
        import pt_exchanges  # noqa: F401  (registers the connectors)
        from pt_exchange_abstraction import ExchangeFactory, ExchangeType

        kind = ExchangeType(exchange)
        try:
            connected = self._manager().exchange_manager.exchanges.get(kind)
        except Exception:
            connected = None
        if connected is not None:
            return connected
        if exchange not in self._connectors:
            self._connectors[exchange] = ExchangeFactory.get_exchange(
                kind, api_key="", api_secret=""
            )
        return self._connectors[exchange]

    def atr(self, coin: str, exchange: str = "") -> Optional[float]:
        if self._atr is not None:
            return self._atr(coin, exchange)
        return ome.candle_atr(coin, exchange)

    def lookup(self, coin: str, broker: Optional[str] = None) -> MarketQuote:
        """``coin``'s market on the exchange an order is for: ``broker`` (the live
        exchange) when given, otherwise the layer's, primary first."""
        from pt_exchange_abstraction import ExchangeType, dollar_symbol, exchange_name

        symbol = dollar_symbol(coin)
        if broker:
            connector = self.connector(broker)
            pair = connector.market_symbol(symbol)
            try:
                quote = connector.quote(symbol)
            except Exception as exc:
                quote, problem = None, f"{exchange_name(broker)}: {exc}"
            else:
                problem = "" if quote else f"No price from {exchange_name(broker)}"
            if quote is None or not (quote.bid > 0 and quote.ask > 0):
                return MarketQuote(broker, pair, problem=problem or "No price")
            return MarketQuote(
                broker, pair, quote.bid, quote.ask, trading_fees_of(connector, symbol)
            )
        try:
            manager = self._manager()
            names = manager.exchange_manager.exchange_names()
        except Exception:
            names = []
        if not names:
            return MarketQuote("", symbol, problem="No exchange is connected")
        try:
            answer = manager.quote(symbol)
        except Exception:
            answer = None
        if answer is None:
            from exchange_symbols import market_pair

            pair = market_pair(coin, lambda: manager)
            return MarketQuote(
                pair.exchange or names[0],
                pair.pair,
                problem=f"No price for {coin} from "
                + ", ".join(exchange_name(n) for n in names),
            )
        connector = manager.exchange_manager.exchanges.get(
            ExchangeType(answer.exchange)
        )
        return MarketQuote(
            answer.exchange,
            answer.pair,
            float(answer.value.bid),
            float(answer.value.ask),
            trading_fees_of(connector, symbol),
        )


def parse_amount(text: str) -> Optional[Decimal]:
    """A positive number typed in a field, or None."""
    try:
        number = Decimal(str(text).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number > 0 else None


class OrderDialog(tk.Toplevel):
    """The Create Order dialog; see the module docstring.

    ``coins`` are the hub's coins and ``coin`` the one to start with; ``trading``
    the hub's trading settings; ``buying_power`` the account's (None when not
    known); ``market`` an ExchangeMarket; ``executor`` the OrderExecutor the order
    is created through; ``on_created(order_id)`` is called once it is.
    ``background=False`` looks the market up at once (tests)."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        coins: Sequence[str],
        coin: str,
        trading: Any,
        buying_power: Optional[float],
        market: Any,
        executor: Any,
        on_created: Callable[[str], None] = lambda _id: None,
        money: Callable[[float], str] = _plain_money,
        price: Callable[[float], str] = _plain_price,
        background: bool = True,
    ):
        super().__init__(parent)
        self.title("Create Order")
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.coins = [str(c).upper() for c in coins if str(c).strip()]
        self.trading = trading
        self.buying_power = buying_power
        self.market = market
        self.executor = executor
        self.on_created = on_created
        self._money, self._price = money, price
        self._background = background
        self.quote: Optional[MarketQuote] = None
        self.atr: Optional[float] = None
        self.created_id: Optional[str] = None
        self._results: "queue.Queue[Tuple[str, str, Any]]" = queue.Queue()
        self._account, self._banner = account_text(trading)
        self._prefilled: Dict[str, str] = {}

        gap = ui_tokens.SPACE["sm"]
        body = ttk.Frame(self, padding=ui_tokens.SPACE["lg"])
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        bg, fg = ui_tokens.BANNER.get(
            "live" if self._banner == "blocked" else self._banner,
            ui_tokens.BANNER["paper"],
        )
        self.account_label = tk.Label(
            body,
            text=f"Account: {self._account}",
            bg=bg,
            fg=fg,
            font=ui_tokens.font("body", "bold"),
            anchor="w",
            padx=gap,
            pady=4,
        )
        self.account_label.grid(row=0, column=0, columnspan=2, sticky="ew")

        self.coin_var = tk.StringVar(value=str(coin or "").upper())
        self.type_var = tk.StringVar(value=MARKET)
        self.side_var = tk.StringVar(value="Buy")
        self.qty_var = tk.StringVar()
        self.limit_var = tk.StringVar()  # a limit's, a stop-limit's, a bracket entry's
        self.stop_var = tk.StringVar()
        self.tp_var = tk.StringVar()
        self.trail_mode_var = tk.StringVar(value=TRAIL_PERCENT)
        self.trail_var = tk.StringVar(value="2")
        self.entry_var = tk.StringVar(value=MARKET)

        row = 1

        def field(label: str, widget: tk.Widget) -> None:
            nonlocal row
            ttk.Label(body, text=label).grid(
                row=row, column=0, sticky="w", padx=(0, gap), pady=(gap, 0)
            )
            widget.grid(row=row, column=1, sticky="ew", pady=(gap, 0))
            row += 1

        self.coin_box = ttk.Combobox(
            body,
            textvariable=self.coin_var,
            values=self.coins,
            state="readonly",
            width=10,
        )
        field("Coin", self.coin_box)
        self.symbol_label = ttk.Label(body, text="")
        field("Symbol", self.symbol_label)
        self.quote_label = ttk.Label(body, text="", style="Muted.TLabel")
        field("Bid / Ask", self.quote_label)
        self.type_box = ttk.Combobox(
            body,
            textvariable=self.type_var,
            values=ORDER_TYPES,
            state="readonly",
            width=14,
        )
        field("Order type", self.type_box)
        self.side_box = ttk.Combobox(
            body, textvariable=self.side_var, values=SIDES, state="readonly", width=6
        )
        field("Side", self.side_box)
        self.qty_entry = ttk.Entry(body, textvariable=self.qty_var, width=16)
        field("Quantity", self.qty_entry)

        # the order type's own fields take these rows of the form (_type_changed),
        # so they line up with the others
        self._body = body
        self._fields_row = row
        self._type_widgets: List[tk.Widget] = []
        self.fields: Dict[str, tk.Widget] = {}  # label -> the shown field (tests)
        row += TYPE_ROWS

        ttk.Separator(body).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(gap + 2, 0)
        )
        row += 1
        self.how_label = ttk.Label(body, text="", wraplength=340, justify="left")
        field("Execution", self.how_label)
        self.value_label = ttk.Label(body, text="")
        field("Estimated value", self.value_label)
        self.fee_label = ttk.Label(body, text="")
        field("Fee", self.fee_label)
        self.power_label = ttk.Label(body, text="")
        field("Buying Power", self.power_label)
        self.warning_label = ttk.Label(
            body, text="", style="Bad.TLabel", wraplength=420, justify="left"
        )
        self.warning_label.grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(gap, 0)
        )
        row += 1

        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=2, sticky="e", pady=(gap * 2, 0))
        self.create_button = ttk.Button(
            buttons, text="Create Order", command=self.create
        )
        self.create_button.pack(side="left", padx=(0, gap))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left")

        self.coin_var.trace_add("write", lambda *_: self._coin_changed())
        self.type_var.trace_add("write", lambda *_: self._type_changed())
        self.side_var.trace_add("write", lambda *_: self._side_changed())
        self.trail_mode_var.trace_add("write", lambda *_: self._trail_mode_changed())
        self.entry_var.trace_add("write", lambda *_: self._type_changed())
        for var in (
            self.qty_var,
            self.stop_var,
            self.limit_var,
            self.tp_var,
            self.trail_var,
        ):
            var.trace_add("write", lambda *_: self.update_estimate())
        self.bind("<Escape>", lambda _e: self.destroy())

        self._type_changed()
        self._coin_changed()
        self.qty_entry.focus_set()
        try:
            self.grab_set()
        except tk.TclError:
            pass  # not viewable yet (a hidden test window)

    # ---- the market ----

    def broker(self) -> Optional[str]:
        """The live exchange the order is for; None in paper mode."""
        if getattr(self.trading, "is_live", False):
            return getattr(self.trading, "active_broker", None) or None
        return None

    def _run(self, what: str, coin: str, job: Callable[[], Any]) -> None:
        """``job`` (a lookup) now, or on a thread whose answer ``_poll`` shows."""
        if not self._background:
            self._show(what, coin, job())
            return
        threading.Thread(
            target=lambda: self._results.put((what, coin, job())), daemon=True
        ).start()
        self.after(50, self._poll)

    def _coin_changed(self) -> None:
        coin = self.coin_var.get()
        self.quote = None
        self.atr = None
        self.symbol_label.configure(text=f"{coin} (looking up the market...)")
        self.quote_label.configure(text="")
        self.update_estimate()
        if not coin:
            return
        self._run("quote", coin, lambda: self._lookup(coin))

    def _lookup(self, coin: str) -> MarketQuote:
        try:
            return self.market.lookup(coin, self.broker())
        except Exception as exc:
            return MarketQuote("", "", problem=f"{type(exc).__name__}: {exc}")

    def _look_up_atr(self) -> None:
        coin = self.coin_var.get()
        exchange = self.quote.exchange if self.quote else ""

        def job():
            try:
                return self.market.atr(coin, exchange)
            except Exception:
                return None

        self._run("atr", coin, job)

    def _poll(self) -> None:
        try:
            what, coin, answer = self._results.get_nowait()
        except queue.Empty:
            try:
                self.after(50, self._poll)
            except tk.TclError:
                pass  # closed
            return
        self._show(what, coin, answer)

    def _show(self, what: str, coin: str, answer: Any) -> None:
        if coin != self.coin_var.get():
            return  # an older coin's answer
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if what == "atr":
            self.atr = answer
            self.update_estimate()
            return
        self._show_quote(answer)

    def _show_quote(self, quote: MarketQuote) -> None:
        from pt_exchange_abstraction import exchange_name

        self.quote = quote
        where = f" on {exchange_name(quote.exchange)}" if quote.exchange else ""
        self.symbol_label.configure(text=f"{quote.pair or self.coin_var.get()}{where}")
        if quote.bid and quote.ask:
            self.quote_label.configure(
                text=f"{self._price(quote.bid)} / {self._price(quote.ask)}"
            )
        else:
            self.quote_label.configure(text=quote.problem or "No price")
        self.fill_prices()
        if self.trail_mode_var.get() == TRAIL_ATR:
            self._look_up_atr()
        self.update_estimate()

    def fill_prices(self, only_prefilled: bool = False) -> None:
        """The price fields from the market price for the side: the ask for a buy,
        the bid for a sell. ``only_prefilled``: only fields not typed in since."""
        price = self.market_price()
        if price is None:
            return
        text = plain_number(price)
        for name, var in (
            ("limit", self.limit_var),
            ("stop", self.stop_var),
            ("tp", self.tp_var),
        ):
            if only_prefilled and var.get() != self._prefilled.get(name):
                continue
            var.set(text)
            self._prefilled[name] = text

    def _side_changed(self) -> None:
        """Prices still at the market price follow the side."""
        self.fill_prices(only_prefilled=True)
        self.update_estimate()

    # ---- the order type ----

    def kind(self) -> str:
        return KIND_OF.get(self.type_var.get(), ome.MARKET)

    def _type_changed(self) -> None:
        for widget in self._type_widgets:
            widget.destroy()
        self._type_widgets = []
        self.fields = {}
        gap = ui_tokens.SPACE["sm"]
        body = self._body
        row = self._fields_row

        def field(label: str, widget: tk.Widget) -> None:
            nonlocal row
            name = ttk.Label(body, text=label)
            name.grid(row=row, column=0, sticky="w", padx=(0, gap), pady=(gap, 0))
            widget.grid(row=row, column=1, sticky="ew", pady=(gap, 0))
            self._type_widgets += [name, widget]
            self.fields[label] = widget
            row += 1

        def entry(var: tk.StringVar, parent=None) -> ttk.Entry:
            return ttk.Entry(parent or body, textvariable=var, width=16)

        kind = self.type_var.get()
        if kind == MARKET:
            self.market_price_label = ttk.Label(body, text="")
            field("Price", self.market_price_label)
        elif kind == LIMIT:
            field("Limit price", entry(self.limit_var))
        elif kind == STOP_LIMIT:
            field("Stop price", entry(self.stop_var))
            field("Limit price", entry(self.limit_var))
        elif kind == TRAILING_STOP:
            line = ttk.Frame(body)
            ttk.Combobox(
                line,
                textvariable=self.trail_mode_var,
                values=TRAIL_MODES,
                state="readonly",
                width=13,
            ).pack(side="left")
            entry(self.trail_var, line).pack(
                side="left", padx=(gap, 0), fill="x", expand=True
            )
            field("Trail", line)
            self.trail_label = ttk.Label(body, text="", style="Muted.TLabel")
            field("Trail distance", self.trail_label)
        elif kind == OCO:
            field("Take-profit price", entry(self.tp_var))
            field("Stop price", entry(self.stop_var))
        elif kind == BRACKET:
            line = ttk.Frame(body)
            ttk.Combobox(
                line,
                textvariable=self.entry_var,
                values=ENTRY_TYPES,
                state="readonly",
                width=8,
            ).pack(side="left")
            limit = entry(self.limit_var, line)
            limit.pack(side="left", padx=(gap, 0), fill="x", expand=True)
            if self.entry_var.get() != LIMIT:
                limit.state(["disabled"])
            field("Entry", line)
            field("Take-profit price", entry(self.tp_var))
            field("Stop price", entry(self.stop_var))
        self.update_estimate()

    def _trail_mode_changed(self) -> None:
        if self.trail_mode_var.get() == TRAIL_ATR:
            self.trail_var.set("2")
            if self.atr is None and self.quote is not None:
                self._look_up_atr()
        else:
            self.trail_var.set("2")
        self.update_estimate()

    # ---- the order ----

    def market_price(self) -> Optional[float]:
        """The current price for the side: the ask for a buy, the bid for a sell."""
        q = self.quote
        if q is None or not (q.bid and q.ask):
            return None
        return q.ask if self.side_var.get() == "Buy" else q.bid

    def spec(self) -> Optional[ome.OrderSpec]:
        """The order the fields describe (None without a quantity); prices that are
        not filled in are None."""
        qty = parse_amount(self.qty_var.get())
        if qty is None:
            return None
        kind = self.kind()
        q = self.quote
        mode = ome.PERCENT if self.trail_mode_var.get() == TRAIL_PERCENT else ome.ATR
        limit = parse_amount(self.limit_var.get())
        if kind == ome.BRACKET and self.entry_var.get() != LIMIT:
            limit = None
        return ome.OrderSpec(
            kind=kind,
            coin=self.coin_var.get(),
            side=self.side_var.get().lower(),
            quantity=qty,
            exchange=q.exchange if q else "",
            pair=q.pair if q else "",
            price=limit if kind in (ome.LIMIT, ome.STOP_LIMIT, ome.BRACKET) else None,
            stop_price=(
                parse_amount(self.stop_var.get())
                if kind in (ome.STOP_LIMIT, ome.OCO, ome.BRACKET)
                else None
            ),
            take_profit=(
                parse_amount(self.tp_var.get())
                if kind in (ome.OCO, ome.BRACKET)
                else None
            ),
            trail_mode=mode if kind == ome.TRAILING_STOP else None,
            trail_value=(
                parse_amount(self.trail_var.get())
                if kind == ome.TRAILING_STOP
                else None
            ),
            atr=self.atr if kind == ome.TRAILING_STOP and mode == ome.ATR else None,
            reference=self.market_price(),
        )

    def order_price(self) -> Optional[float]:
        """The price the order's value is estimated at: its limit (a limit,
        stop-limit or bracket limit entry), the higher of an OCO buy's prices or an
        OCO sell's take-profit, else the market price."""
        kind = self.kind()
        if kind in (ome.LIMIT, ome.STOP_LIMIT) or (
            kind == ome.BRACKET and self.entry_var.get() == LIMIT
        ):
            number = parse_amount(self.limit_var.get())
            return float(number) if number is not None else None
        if kind == ome.OCO:
            tp, stop = parse_amount(self.tp_var.get()), parse_amount(
                self.stop_var.get()
            )
            if tp is None or stop is None:
                return None
            buy = self.side_var.get() == "Buy"
            return float(max(tp, stop)) if buy else float(tp)
        return self.market_price()

    def fee_kind(self) -> str:
        """ "limit" (the maker rate) for an order that rests in the book, else
        "market" (the taker rate)."""
        kind = self.kind()
        if kind == ome.LIMIT or (kind == ome.BRACKET and self.entry_var.get() == LIMIT):
            return "limit"
        return "market"

    def estimate(self) -> Tuple[Optional[float], Optional[float]]:
        """(estimated value, estimated fee); None where it can't be worked out."""
        qty = parse_amount(self.qty_var.get())
        price = self.order_price()
        if qty is None or price is None:
            return None, None
        value = float(qty) * price
        fees = self.quote.fees if self.quote else None
        if fees is None:
            return value, None
        _name, rate = fees.for_order(self.fee_kind())
        return value, value * rate

    def over_buying_power(self) -> bool:
        value, fee = self.estimate()
        if self.side_var.get() != "Buy" or value is None:
            return False
        return self.buying_power is not None and value + (fee or 0.0) > float(
            self.buying_power
        )

    def how_text(self) -> str:
        """How the order is carried out (order_management_execution.handling_text)."""
        from pt_exchange_abstraction import exchange_name

        spec = self.spec() or ome.OrderSpec(
            kind=self.kind(),
            coin=self.coin_var.get(),
            side=self.side_var.get().lower(),
            quantity=Decimal("1"),
            price=parse_amount(self.limit_var.get()),
            trail_mode=ome.PERCENT,
            trail_value=parse_amount(self.trail_var.get()),
        )
        broker = self.broker()
        connector = None
        if broker:
            try:
                connector = self.market.connector(broker)
            except Exception:
                connector = None
        return ome.handling_text(
            spec, bool(broker), connector, exchange_name(broker or "")
        )

    def update_estimate(self) -> None:
        if not hasattr(self, "warning_label"):
            return  # still being built
        kind = self.type_var.get()
        price = self.market_price()
        word = "ask" if self.side_var.get() == "Buy" else "bid"
        if kind == MARKET and hasattr(self, "market_price_label"):
            try:
                self.market_price_label.configure(
                    text=f"{self._price(price)} (the {word})" if price else "N/A"
                )
            except tk.TclError:
                pass
        if kind == TRAILING_STOP and hasattr(self, "trail_label"):
            try:
                self.trail_label.configure(text=self.trail_text(price))
            except tk.TclError:
                pass
        value, fee = self.estimate()
        self.value_label.configure(text=self._money(value) if value else "N/A")
        fees = self.quote.fees if self.quote else None
        if fee is not None and fees is not None:
            name, rate = fees.for_order(self.fee_kind())
            self.fee_label.configure(
                text=f"{self._money(fee)} ({rate * 100:.2f}%, {name})"
            )
        else:
            self.fee_label.configure(text="not known")
        self.power_label.configure(
            text=(
                self._money(self.buying_power)
                if self.buying_power is not None
                else "N/A"
            )
        )
        try:
            self.how_label.configure(text=self.how_text())
        except Exception:
            self.how_label.configure(text="")
        refused = self._refusal()
        if refused:
            warning = refused
        elif self.over_buying_power():
            warning = "More than Buying Power"
        else:
            warning = ""
        self.warning_label.configure(text=warning)

    def trail_text(self, price: Optional[float]) -> str:
        """The trail's distance now: a percent of the price, or the ATR multiple."""
        value = parse_amount(self.trail_var.get())
        if value is None:
            return "Enter the trail"
        if self.trail_mode_var.get() == TRAIL_PERCENT:
            if price is None:
                return f"{plain_number(value)}% of the price"
            return (
                f"{self._price(price * float(value) / 100.0)} "
                f"({plain_number(value)}% of {self._price(price)})"
            )
        if self.atr is None:
            return f"ATR({ome.ATR_LENGTH}) of {ome.ATR_TF_TEXT} candles: looking up..."
        return (
            f"{self._price(float(value) * self.atr)} ({plain_number(value)} × "
            f"ATR({ome.ATR_LENGTH}) of {ome.ATR_TF_TEXT} candles, {self._price(self.atr)})"
        )

    def _refusal(self) -> str:
        if self._banner == "blocked":
            return "No live exchange is chosen"
        try:
            return self.executor.refusal(self.trading) if self.executor else ""
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"

    # ---- creating the order ----

    def _refuse(self, message: str) -> None:
        messagebox.showerror("Order refused", message, parent=self)

    def create(self) -> Optional[str]:
        """Check the order, confirm it, and create it; its id, or None."""
        q = self.quote
        if self._banner == "blocked":
            self._refuse(
                "Live mode has no exchange chosen, so the order has no account."
            )
            return None
        refused = self._refusal()
        if refused:
            self._refuse(refused)
            return None
        if q is None or not q.pair:
            self._refuse("The coin's market is not known yet.")
            return None
        spec = self.spec()
        if spec is None:
            self._refuse("Enter a quantity above 0.")
            return None
        problem = ome.problem_with(spec, q.bid, q.ask)
        if problem:
            self._refuse(problem)
            return None

        value, fee = self.estimate()
        if spec.side == "buy":
            if value is None:
                self._refuse(
                    f"There is no price for {q.pair}, so the order's value can't be "
                    "checked against Buying Power."
                )
                return None
            if self.buying_power is None:
                self._refuse(
                    "Buying Power is not known yet, so the order can't be checked "
                    "against it."
                )
                return None
            if self.over_buying_power():
                total = value + (fee or 0.0)
                self._refuse(
                    f"This order's value, {self._money(total)}, is more than Buying "
                    f"Power, {self._money(float(self.buying_power))}."
                )
                return None

        if not self.confirm(spec, value, fee):
            return None
        try:
            order_id = self.executor.create(spec)
        except ValueError as exc:
            self._refuse(str(exc))
            return None
        except Exception as exc:
            messagebox.showerror(
                "Order not created",
                f"The order could not be created.\n\n{type(exc).__name__}: {exc}",
                parent=self,
            )
            return None
        self.created_id = str(order_id)
        self.on_created(self.created_id)
        self.destroy()
        return self.created_id

    def price_lines(self, spec: ome.OrderSpec) -> List[str]:
        p = self._price
        if spec.kind == ome.LIMIT:
            return [f"Limit price: {p(float(spec.price))}"]
        if spec.kind == ome.STOP_LIMIT:
            return [
                f"Stop price: {p(float(spec.stop_price))}",
                f"Limit price: {p(float(spec.price))}",
            ]
        if spec.kind == ome.TRAILING_STOP:
            return [f"Trail: {self.trail_text(self.market_price())}"]
        if spec.kind in (ome.OCO, ome.BRACKET):
            lines = []
            if spec.kind == ome.BRACKET:
                entry = f"limit {p(float(spec.price))}" if spec.price else "market"
                lines.append(f"Entry: {entry}")
            return lines + [
                f"Take-profit: {p(float(spec.take_profit))}",
                f"Stop: {p(float(spec.stop_price))}",
            ]
        return []

    def confirm(self, spec: ome.OrderSpec, value, fee) -> bool:
        from pt_exchange_abstraction import exchange_name

        q = self.quote
        lines = [
            f"Account: {self._account}",
            f"{spec.side.capitalize()} {plain_number(spec.quantity)} {q.pair} on "
            f"{exchange_name(q.exchange)}",
            f"Type: {NAME_OF.get(spec.kind, spec.kind)}",
            *self.price_lines(spec),
            f"Execution: {self.how_text()}",
            f"Estimated value: {self._money(value) if value else 'N/A'}",
            f"Fee: {self._money(fee) if fee is not None else 'not known'}",
            "",
            "Create this order?",
        ]
        live = self._banner == "live"
        return bool(
            messagebox.askyesno(
                "Confirm live order" if live else "Confirm order",
                "\n".join(lines),
                icon="warning" if live else "question",
                default="no" if live else "yes",
                parent=self,
            )
        )


class ModifyDialog(tk.Toplevel):
    """Modify Selected: an open order's quantity and the prices its type has (a
    trailing stop's trail). ``save(changes)`` changes the order and returns ""
    or why it could not (OrderExecutor.modify)."""

    def __init__(
        self,
        parent: tk.Misc,
        item: Any,
        save: Callable[[Dict[str, Decimal]], None],
    ):
        super().__init__(parent)
        self.title("Modify Order")
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.item = item
        self._save = save
        gap = ui_tokens.SPACE["sm"]
        body = ttk.Frame(self, padding=ui_tokens.SPACE["lg"])
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        name = NAME_OF.get(item.kind, item.kind)
        ttk.Label(
            body,
            text=f"{name}: {item.side.capitalize()} {item.pair or item.coin}",
            font=ui_tokens.font("body", "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        self.vars: Dict[str, tk.StringVar] = {}
        row = 1

        def field(key: str, label: str, value: Any) -> None:
            nonlocal row
            var = tk.StringVar(value=plain_number(value))
            self.vars[key] = var
            ttk.Label(body, text=label).grid(
                row=row, column=0, sticky="w", padx=(0, gap), pady=(gap, 0)
            )
            ttk.Entry(body, textvariable=var, width=16).grid(
                row=row, column=1, sticky="ew", pady=(gap, 0)
            )
            row += 1

        spec = item.spec
        entry = item.leg("entry")
        entered = entry is not None and entry.status == "filled"
        if not entered:
            field("quantity", "Quantity", spec.quantity)
        if spec.kind in (ome.LIMIT, ome.STOP_LIMIT) or (
            spec.kind == ome.BRACKET and spec.price and not entered
        ):
            field("price", "Limit price", spec.price)
        if spec.kind in (ome.STOP_LIMIT, ome.OCO, ome.BRACKET):
            field("stop_price", "Stop price", spec.stop_price)
        if spec.kind in (ome.OCO, ome.BRACKET):
            field("take_profit", "Take-profit price", spec.take_profit)
        if spec.kind == ome.TRAILING_STOP:
            label = "Trail (%)" if spec.trail_mode == ome.PERCENT else "Trail (× ATR)"
            field("trail_value", label, spec.trail_value)
        self.message = ttk.Label(body, text="", style="Bad.TLabel", wraplength=320)
        self.message.grid(row=row, column=0, columnspan=2, sticky="w", pady=(gap, 0))
        row += 1
        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=2, sticky="e", pady=(gap * 2, 0))
        ttk.Button(buttons, text="Save", command=self.save).pack(
            side="left", padx=(0, gap)
        )
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left")
        self.bind("<Escape>", lambda _e: self.destroy())

    def changes(self) -> Optional[Dict[str, Decimal]]:
        out = {}
        for key, var in self.vars.items():
            number = parse_amount(var.get())
            if number is None:
                self.message.configure(text="Enter every value, above 0.")
                return None
            out[key] = number
        return out

    def save(self) -> None:
        changes = self.changes()
        if changes is not None:
            self._save(changes)


class OrderManagementView(ttk.Frame):
    """The tab: toolbar and Active Orders over the Order Notifications; see the
    module docstring. The callables give the hub's current coins, the coin shown in
    the chart, the trading settings and Buying Power when an order is created.
    ``executor`` is the OrderExecutor (one on ``manager``'s database by default).
    ``refresh_ms=None`` reads the database and carries the orders on only when asked
    (tests); ``sync=True`` runs the executor's work at once instead of on a worker
    thread (tests)."""

    def __init__(
        self,
        parent: tk.Misc,
        manager: Any,
        *,
        coins: Callable[[], Sequence[str]] = lambda: (),
        chart_coin: Callable[[], str] = lambda: "",
        trading: Callable[[], Any] = lambda: None,
        buying_power: Callable[[], Optional[float]] = lambda: None,
        market: Any = None,
        executor: Any = None,
        money: Callable[[float], str] = _plain_money,
        price: Callable[[float], str] = _plain_price,
        refresh_ms: Optional[int] = REFRESH_MS,
        sync: bool = False,
    ):
        super().__init__(parent)
        self.manager = manager
        self._coins, self._chart_coin = coins, chart_coin
        self._trading, self._buying_power = trading, buying_power
        self.market = market if market is not None else ExchangeMarket()
        self.executor = executor
        if self.executor is None and getattr(manager, "db", None) is not None:
            import pt_paths

            self.executor = ome.OrderExecutor(
                manager.db, hub_dir=lambda: pt_paths.hub_dir_for(None), trading=trading
            )
        self._money, self._price = money, price
        self._refresh_ms = refresh_ms
        self._sync = sync
        self.jobs = ui_jobs.BackgroundJobs(self, name="order-management")
        self.orders: List[OrderRow] = []
        self.shown: List[OrderRow] = []
        self.notes: List[NoteRow] = []
        self.dialog: Optional[OrderDialog] = None
        self.modify_dialog: Optional[ModifyDialog] = None
        self._search_after: Optional[str] = None
        self._tick_after: Optional[str] = None
        self._sash_placed = False
        gap = ui_tokens.SPACE["sm"]

        self.paned = ttk.Panedwindow(self, orient="vertical")
        self.paned.pack(fill="both", expand=True)

        # ---- orders: the toolbar over the table ----
        top = ttk.Frame(self.paned)
        bar = ttk.Frame(top)
        bar.pack(side="top", fill="x", padx=gap, pady=(gap, gap))
        ttk.Button(bar, text="Create Order", command=self.open_dialog).pack(
            side="left", padx=(0, gap)
        )
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(
            side="left", padx=(0, gap)
        )
        ttk.Button(bar, text="Cancel Selected", command=self.cancel_selected).pack(
            side="left", padx=(0, gap)
        )
        ttk.Button(bar, text="Modify Selected", command=self.modify_selected).pack(
            side="left", padx=(0, gap + 4)
        )
        self.status_var = tk.StringVar(value=STATUS_FILTERS[0][0])
        ttk.Label(bar, text="Status").pack(side="left", padx=(0, 4))
        self.status_box = ttk.Combobox(
            bar,
            textvariable=self.status_var,
            values=[name for name, _ in STATUS_FILTERS],
            state="readonly",
            width=10,
        )
        self.status_box.pack(side="left", padx=(0, gap + 4))
        self.search_var = tk.StringVar()
        ttk.Label(bar, text="Search").pack(side="left", padx=(0, 4))
        self.search_entry = ttk.Entry(bar, textvariable=self.search_var, width=16)
        self.search_entry.pack(side="left", fill="x", expand=True)

        self.orders_table = ui_table.DataTable(
            top,
            ORDER_COLUMNS,
            ORDER_HEADINGS,
            key="order_management",
            numeric=ORDER_NUMERIC,
            sort=("created", True),
            empty_text=NO_ORDERS,
            show="tree headings",  # an OCO or Bracket order's legs under it
        )
        self.orders_table.pack(side="top", fill="both", expand=True)
        self.orders_tree = self.orders_table.tree
        self.orders_tree.heading(ui_table.TREE, text=LEG_HEADING)

        # ---- the notifications ----
        bottom = ttk.Frame(self.paned)
        head = ttk.Frame(bottom)
        head.pack(side="top", fill="x", padx=gap, pady=(gap, 2))
        ttk.Label(head, text=NOTES_TITLE, style=ui_table.SECTION_STYLE).pack(
            side="left"
        )
        self.mark_read_button = ttk.Button(
            head, text="Mark all read", command=self.mark_all_read
        )
        self.mark_read_button.pack(side="right")
        self.notes_table = ui_table.DataTable(
            bottom,
            NOTE_COLUMNS,
            NOTE_HEADINGS,
            key="order_notifications",
            sort=("time", True),
            empty_text=NO_NOTES,
            height=4,
        )
        self.notes_table.pack(side="top", fill="both", expand=True)
        self.notes_tree = self.notes_table.tree
        body = ttk.Style(self).lookup(ui_table.STYLE, "font") or "TkDefaultFont"
        self._unread_font = tkfont.Font(root=self, font=body)  # the rows' font, bold
        self._unread_font.configure(weight="bold")
        self.notes_tree.tag_configure("unread", font=self._unread_font)

        self.paned.add(top, weight=3)
        self.paned.add(bottom, weight=1)
        self.paned.bind("<Configure>", lambda _e: self._place_sash(), add="+")
        self.paned.bind("<B1-Motion>", lambda _e: self.clamp_sash(), add="+")
        self.paned.bind("<ButtonRelease-1>", lambda _e: self.clamp_sash(), add="+")

        self.status_var.trace_add("write", lambda *_: self.apply_filters())
        self.search_var.trace_add("write", lambda *_: self._search_changed())
        self.bind("<Destroy>", self._on_destroy, add="+")

        self.refresh()
        if refresh_ms:
            self._tick_after = self.after(refresh_ms, self._tick)

    # ---- the splitter ----

    def _place_sash(self) -> None:
        """The first layout puts about a third of the height under the splitter;
        after that the splitter stays where it is, kept off the minimum heights."""
        if not self._sash_placed:
            total = self.paned.winfo_height()
            if total <= 1:
                return
            self._sash_placed = True
            notes = max(MIN_NOTES_PX, total // 3)
            try:
                self.paned.sashpos(0, max(MIN_ORDERS_PX, total - notes))
            except tk.TclError:
                return
        self.clamp_sash()

    def clamp_sash(self) -> None:
        """Keep each pane at least its minimum height (ttk panes have no minsize)."""
        try:
            total = self.paned.winfo_height()
            pos = int(self.paned.sashpos(0))
        except (tk.TclError, ValueError):
            return
        if total <= MIN_ORDERS_PX + MIN_NOTES_PX:
            return
        clamped = max(MIN_ORDERS_PX, min(total - MIN_NOTES_PX, pos))
        if clamped != pos:
            self.paned.sashpos(0, clamped)

    # ---- the monitor ----

    def _on_destroy(self, event) -> None:
        if event.widget is not self:
            return
        for after in (self._tick_after, self._search_after):
            if after is not None:
                try:
                    self.after_cancel(after)
                except tk.TclError:
                    pass
        self._tick_after = self._search_after = None

    def _tick(self) -> None:
        """Every ``refresh_ms``: read the database, and let the executor carry the
        open orders on (on the worker, one pass at a time)."""
        self._tick_after = None
        try:
            self.refresh()
            self.check_orders()
            self._tick_after = self.after(self._refresh_ms, self._tick)
        except tk.TclError:
            pass  # the tab is gone

    def has_work(self) -> bool:
        """Whether any order read is open (the executor carries on the ones it
        made)."""
        return any(r.is_open for r in self.orders)

    def check_orders(self) -> None:
        """One pass of ``OrderExecutor.check`` when there is an open order (no
        worker thread starts while there is none)."""
        if self.executor is None or self.jobs.busy or not self.has_work():
            return
        self._background(self.executor.check, lambda _n: self.refresh())

    def _background(self, job: Callable[[], Any], on_done: Callable[[Any], None]):
        """``job`` on the worker thread, then ``on_done(result)`` on the Tk thread
        (at once with ``sync``)."""
        if self._sync:
            on_done(job())
            return

        def failed(exc: BaseException) -> None:
            print(f"Order Management: {type(exc).__name__}: {exc}")
            self.refresh()

        self.jobs.submit(job, on_done=on_done, on_error=failed)

    # ---- reading the database ----

    def refresh(self) -> None:
        """Read the orders and notifications again; the tables change only when
        they did (so a selection and the scroll position stay)."""
        db = getattr(self.manager, "db", None)
        if db is None:
            return
        try:
            orders = load_orders(db)
            notes = load_notifications(db)
        except Exception as exc:
            print(f"Error reading the order management database: {exc}")
            return
        if orders != self.orders:
            self.orders = orders
            self.apply_filters()
        if notes != self.notes:
            self.notes = notes
            self._show_notes()

    # ---- the orders table ----

    def cells(self, r: OrderRow) -> Tuple[str, ...]:
        qty = "" if r.quantity is None else plain_number(r.quantity)
        return (
            local_time(r.created),
            r.symbol,
            r.kind,
            r.side,
            qty,
            "" if r.price is None else self._price(r.price),
            "" if r.stop is None else self._price(r.stop),
            r.status.capitalize(),
            r.conditions,
            r.client_id,
        )

    def _search_changed(self) -> None:
        if self._search_after is not None:
            try:
                self.after_cancel(self._search_after)
            except tk.TclError:
                pass
        self._search_after = self.after(150, self._search_now)

    def _search_now(self) -> None:
        self._search_after = None
        self.apply_filters()

    def groups(self) -> List[Tuple[OrderRow, List[OrderRow]]]:
        """Each order with its legs (an OCO or Bracket order's), newest first."""
        legs: Dict[str, List[OrderRow]] = {}
        ids = {r.id for r in self.orders}
        for r in self.orders:
            if r.parent and r.parent in ids:
                legs.setdefault(r.parent, []).append(r)
        out = []
        for r in self.orders:
            if r.parent and r.parent in ids:
                continue
            kids = sorted(
                legs.get(r.id, []),
                key=lambda x: (LEG_ORDER.get(x.leg, 9), x.created or datetime.min),
            )
            out.append((r, kids))
        return out

    def matches(self) -> List[OrderRow]:
        """The orders the status filter and the search keep: an order with legs is
        kept, with all of them, when it or one of them is."""
        statuses = dict(STATUS_FILTERS).get(self.status_var.get())
        words = self.search_var.get().casefold().split()

        def kept(r: OrderRow) -> bool:
            if statuses is not None and r.status not in statuses:
                return False
            if words:
                text = " ".join(self.cells(r) + (r.leg,)).casefold()
                return all(w in text for w in words)
            return True

        out = []
        for top, legs in self.groups():
            if kept(top) or any(kept(x) for x in legs):
                out.append(top)
                out.extend(legs)
        return out

    def apply_filters(self) -> None:
        tree = self.orders_tree
        selected = set(tree.selection())
        top = tree.yview()[0]
        kept = self.matches()
        self.shown = kept
        tree.delete(*tree.get_children())
        ids = {r.id for r in kept}
        for r in kept:
            parent = r.parent if r.parent in ids else ""
            tree.insert(
                parent,
                "end",
                iid=r.id,
                text=r.leg,
                values=self.cells(r),
                open=True,
            )
        keep = [r.id for r in kept if r.id in selected]
        if keep:
            tree.selection_set(keep)
        self.orders_table.empty.configure(text=NO_MATCH if self.orders else NO_ORDERS)
        self.orders_table.settle()
        if top > 0:
            tree.yview_moveto(top)

    # ---- the notifications ----

    def _show_notes(self) -> None:
        tree = self.notes_tree
        tree.delete(*tree.get_children())
        for n in self.notes:
            tree.insert(
                "",
                "end",
                iid=n.id,
                values=(local_time(n.created), n.title, n.message),
                tags=("unread",) if n.unread else (),
            )
        unread = any(n.unread for n in self.notes)
        self.mark_read_button.configure(state="normal" if unread else "disabled")

    def mark_all_read(self) -> None:
        for n in self.notes:
            if n.unread:
                self.manager.mark_notification_read(uuid.UUID(n.id))
        self.refresh()

    # ---- the toolbar ----

    def _start_coin(self) -> Tuple[List[str], str]:
        """The coins in Settings (each as its coin, ``exchange_symbols.coin_of``) and
        the one the chart shows, or the first."""
        from exchange_symbols import coin_of

        coins: List[str] = []
        for c in self._coins() or ():
            coin = coin_of(c)
            if coin and coin not in coins:
                coins.append(coin)
        shown = coin_of(self._chart_coin() or "")
        return coins, (shown if shown in coins else (coins[0] if coins else ""))

    def open_dialog(self, background: bool = True) -> Optional[OrderDialog]:
        if self.dialog is not None:
            try:
                if self.dialog.winfo_exists():
                    self.dialog.lift()
                    return self.dialog
            except tk.TclError:
                pass
        coins, coin = self._start_coin()
        if not coins:
            messagebox.showinfo(
                "Create Order", "Add a coin in Settings first.", parent=self
            )
            return None
        self.dialog = OrderDialog(
            self,
            coins=coins,
            coin=coin,
            trading=self._trading(),
            buying_power=self._buying_power(),
            market=self.market,
            executor=self.executor,
            on_created=self.order_created,
            money=self._money,
            price=self._price,
            background=background,
        )
        return self.dialog

    def order_created(self, order_id: str) -> None:
        """Send the new order (a market order fills or is placed at once), then show
        it; a market order that was refused says why."""
        self.refresh()

        def done(_result) -> None:
            self.refresh()
            row = next((r for r in self.orders if r.id == str(order_id)), None)
            if row is not None and row.status in ("rejected", "expired"):
                messagebox.showerror(
                    "Order not carried out",
                    f"{row.side} {plain_number(row.quantity)} {row.symbol}, "
                    f"{row.kind}: {row.conditions or row.status}",
                    parent=self,
                )

        if self.executor is not None:
            self._background(lambda: self.executor.submit(order_id), done)

    def _selected_tops(self) -> List[OrderRow]:
        """The orders selected: a leg stands for its OCO or Bracket order."""
        by_id = {r.id: r for r in self.orders}
        out: List[OrderRow] = []
        for iid in self.orders_tree.selection():
            r = by_id.get(str(iid))
            if r is None:
                continue
            if r.parent and r.parent in by_id:
                r = by_id[r.parent]
            if r not in out:
                out.append(r)
        return out

    def _legs_of(self, r: OrderRow) -> List[OrderRow]:
        return [x for x in self.orders if x.parent == r.id]

    def _is_open(self, r: OrderRow) -> bool:
        return r.is_open or any(x.is_open for x in self._legs_of(r))

    def cancel_selected(self) -> int:
        """Cancel the selected open orders, after a confirmation; how many were. An
        OCO or Bracket order (or any of its legs) is cancelled with all its legs."""
        if not self.orders_tree.selection():
            messagebox.showinfo(
                "Cancel orders", "Select the orders to cancel first.", parent=self
            )
            return 0
        chosen = self._selected_tops()
        rows = [r for r in chosen if self._is_open(r)]
        if not rows:
            messagebox.showinfo(
                "Cancel orders", "Only open orders can be cancelled.", parent=self
            )
            return 0
        lines = []
        for r in rows[:10]:
            legs = self._legs_of(r)
            extra = f", with its {len(legs)} legs" if legs else ""
            lines.append(
                f"{r.side} {plain_number(r.quantity)} {r.symbol}, {r.kind}{extra}"
            )
        if len(rows) > 10:
            lines.append(f"... and {len(rows) - 10} more")
        skipped = len(chosen) - len(rows)
        if skipped:
            lines.append(f"({skipped} selected order(s) not open: left as they are)")
        n = len(rows)
        if not messagebox.askyesno(
            "Cancel orders",
            f"Cancel {n} order{'' if n == 1 else 's'}?\n\n" + "\n".join(lines),
            parent=self,
        ):
            return 0

        def job():
            failed = []
            for r in rows:
                if self.executor is not None:
                    ok, why = self.executor.cancel(uuid.UUID(r.id))
                else:
                    ok, why = bool(self.manager.cancel_order(uuid.UUID(r.id))), ""
                if not ok:
                    failed.append((r, why))
            return failed

        def done(failed) -> None:
            self.refresh()
            if failed:
                messagebox.showerror(
                    "Cancel orders",
                    f"{len(failed)} order(s) could not be cancelled:\n"
                    + "\n".join(
                        f"{r.client_id}: {why}" if why else r.client_id
                        for r, why in failed
                    ),
                    parent=self,
                )

        result: List[Any] = []
        self._background(job, lambda failed: (result.append(failed), done(failed)))
        if self._sync and result:
            return n - len(result[0])
        return n

    def modify_selected(self) -> Optional[ModifyDialog]:
        """Modify Selected: the selected open order's quantity and prices."""
        rows = [r for r in self._selected_tops() if self._is_open(r)]
        if len(rows) != 1:
            messagebox.showinfo(
                "Modify order",
                (
                    "Select one open order to change."
                    if not rows
                    else "Select one order at a time to change."
                ),
                parent=self,
            )
            return None
        item = self.executor.item(uuid.UUID(rows[0].id)) if self.executor else None
        if item is None:
            messagebox.showinfo(
                "Modify order",
                "This order was made before these order types: cancel it and create "
                "it again to change it.",
                parent=self,
            )
            return None
        if item.kind == ome.MARKET:
            messagebox.showinfo(
                "Modify order",
                "A market order fills when it is sent: it cannot be changed.",
                parent=self,
            )
            return None
        item.spec = self.executor.spec_of(item)

        def save(changes: Dict[str, Decimal]) -> None:
            def done(problem: str) -> None:
                self.refresh()
                try:
                    if problem:
                        dialog.message.configure(text=problem)
                    else:
                        dialog.destroy()
                except tk.TclError:
                    pass

            self._background(
                lambda: self.executor.modify(uuid.UUID(rows[0].id), **changes), done
            )

        dialog = ModifyDialog(self, item, save)
        self.modify_dialog = dialog
        return dialog
