"""The hub's Order Management tab (owner, 2026-11-04).

A toolbar (Create Order, Refresh, Cancel Selected, a status filter and a search)
over the orders table, and the Order Notifications under it, with a splitter
between them. Orders and notifications are read from the order management database
(order_management_db) and orders are created and cancelled through its OrderManager,
as before; nothing here changes how they are stored or executed.

Create Order opens ``OrderDialog``:

* the coin shown in the chart (the first coin while the chart shows the account),
  as the symbol of the exchange the order is for: the live exchange in live mode,
  otherwise the exchange layer's, primary exchange first (``BTC-USD`` on Coinbase,
  ``BTCUSDT`` on Binance);
* that exchange's current bid and ask, which fill the price fields (a buy's from
  the ask, a sell's from the bid);
* the order's estimated value, and its fee from the connector's ``trading_fees()``
  where it has one;
* the account it is for (paper, or the live exchange), and a confirmation before it
  is created. A buy worth more than Buying Power is refused.
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

OPEN_STATUSES = ("pending", "submitted", "partial")
STATUS_FILTERS: Tuple[Tuple[str, Optional[Tuple[str, ...]]], ...] = (
    ("Open", OPEN_STATUSES),
    ("Filled", ("filled",)),
    ("Cancelled", ("cancelled",)),
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
STOP_LOSS = "Stop Loss"
STOP_LIMIT = "Stop-Limit"
TAKE_PROFIT = "Take Profit"
DCA = "DCA"
CONDITIONAL = "Conditional"
ORDER_TYPES = (MARKET, STOP_LOSS, STOP_LIMIT, TAKE_PROFIT, DCA, CONDITIONAL)
FIXED_SIDE = {STOP_LOSS: "Sell", STOP_LIMIT: "Sell", TAKE_PROFIT: "Sell", DCA: "Buy"}
TYPE_ROWS = 2  # the most rows an order type's own fields take (Stop-Limit, DCA)
SIDES = ("Buy", "Sell")

TYPE_NAMES = {
    "market": MARKET,
    "limit": "Limit",
    "stop": STOP_LOSS,
    "stop_limit": STOP_LIMIT,
    "conditional": CONDITIONAL,
    "bracket": "Bracket",
    "oco": "OCO",
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
CONDITIONS = ("Price", "Neural level", "Volume")
OPERATORS = ("≥", "≤", ">", "<", "=")


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
    """An order's type as the table shows it: its tag tells a take-profit from a
    plain limit order, and a DCA stage from a plain conditional order."""
    kind = _value(order_type)
    tag = str(tag or "").upper()
    if kind == "limit" and tag == "TAKE_PROFIT":
        return TAKE_PROFIT
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

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


def order_row(order: Any) -> OrderRow:
    """The OrderRow of an ``Order`` read in an open session."""
    conditions = "; ".join(
        condition_text(c.condition_type, c.operator, c.target_value, bool(c.is_met))
        for c in (order.conditions or [])
    )
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
        conditions=conditions,
    )


def load_orders(db: Any, limit: int = ORDER_LIMIT) -> List[OrderRow]:
    """The newest ``limit`` orders of the database, newest first (read only)."""
    from order_management_models import Order

    with db.get_session() as session:
        orders = session.query(Order).order_by(Order.created_at.desc()).limit(limit)
        return [order_row(o) for o in orders.all()]


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
    fee_rate: Optional[float] = None  # the taker fee, as a fraction (0.006 = 0.6%)
    problem: str = ""  # why there is no bid and ask, when there are none


def fee_rate(connector: Any) -> Optional[float]:
    """The taker fee rate (a fraction) from the connector's ``trading_fees()``: a
    mapping with "taker" (and "maker") rates as fractions. None when the connector
    has no ``trading_fees()`` or it gives no taker rate."""
    fees = getattr(connector, "trading_fees", None)
    if not callable(fees):
        return None
    try:
        answer = fees()
    except Exception:
        return None
    taker = answer.get("taker") if isinstance(answer, dict) else None
    rate = _float(taker)
    return rate if rate is not None and 0.0 <= rate < 1.0 else None


class ExchangeMarket:
    """Symbols, bid and ask, and fees for the order dialog. A live order's come from
    the live exchange; otherwise from the exchanges in Settings, the primary first
    (``pt_multi_exchange.market_exchanges``, public market data: no credentials)."""

    def __init__(self, layer: Optional[Callable[[], Any]] = None):
        self._layer = layer
        self._connectors: Dict[str, Any] = {}

    def _manager(self):
        if self._layer is not None:
            return self._layer()
        from pt_multi_exchange import market_exchanges

        return market_exchanges()

    def _connector(self, exchange: str):
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

    def lookup(self, coin: str, broker: Optional[str] = None) -> MarketQuote:
        """``coin``'s market on the exchange an order is for: ``broker`` (the live
        exchange) when given, otherwise the layer's, primary first."""
        from pt_exchange_abstraction import ExchangeType, dollar_symbol, exchange_name

        symbol = dollar_symbol(coin)
        if broker:
            connector = self._connector(broker)
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
                broker, pair, quote.bid, quote.ask, fee_rate(connector), ""
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
            first = manager.exchange_manager.exchanges[ExchangeType(names[0])]
            return MarketQuote(
                names[0],
                first.market_symbol(symbol),
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
            fee_rate(connector),
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
    known); ``market`` an ExchangeMarket; ``manager`` the OrderManager the order is
    created through; ``on_created(order_id)`` is called once it is.
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
        manager: Any,
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
        self.manager = manager
        self.on_created = on_created
        self._money, self._price = money, price
        self._background = background
        self.quote: Optional[MarketQuote] = None
        self.created_id: Optional[str] = None
        self._results: "queue.Queue[Tuple[str, MarketQuote]]" = queue.Queue()
        self._account, self._banner = account_text(trading)

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
        self.stop_var = tk.StringVar()
        self.limit_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.stage_var = tk.StringVar(value="1")
        self.level_var = tk.StringVar()
        self.cond_type_var = tk.StringVar(value=CONDITIONS[0])
        self.cond_op_var = tk.StringVar(value=OPERATORS[0])
        self.cond_value_var = tk.StringVar()

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
        row += TYPE_ROWS

        ttk.Separator(body).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(gap + 2, 0)
        )
        row += 1
        self.value_label = ttk.Label(body, text="")
        field("Estimated value", self.value_label)
        self.fee_label = ttk.Label(body, text="")
        field("Fee", self.fee_label)
        self.power_label = ttk.Label(body, text="")
        field("Buying Power", self.power_label)
        self.warning_label = ttk.Label(body, text="", style="Bad.TLabel")
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
        for var in (
            self.qty_var,
            self.stop_var,
            self.limit_var,
            self.target_var,
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

    def _coin_changed(self) -> None:
        coin = self.coin_var.get()
        self.quote = None
        self.symbol_label.configure(text=f"{coin} (looking up the market...)")
        self.quote_label.configure(text="")
        self.update_estimate()
        if not coin:
            return
        if not self._background:
            self._show_quote(coin, self._lookup(coin))
            return
        threading.Thread(
            target=lambda: self._results.put((coin, self._lookup(coin))), daemon=True
        ).start()
        self.after(50, self._poll)

    def _lookup(self, coin: str) -> MarketQuote:
        try:
            return self.market.lookup(coin, self.broker())
        except Exception as exc:
            return MarketQuote("", "", problem=f"{type(exc).__name__}: {exc}")

    def _poll(self) -> None:
        try:
            coin, quote = self._results.get_nowait()
        except queue.Empty:
            try:
                self.after(50, self._poll)
            except tk.TclError:
                pass  # closed
            return
        self._show_quote(coin, quote)

    def _show_quote(self, coin: str, quote: MarketQuote) -> None:
        from pt_exchange_abstraction import exchange_name

        if coin != self.coin_var.get():
            return  # an older coin's answer
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        self.quote = quote
        where = f" on {exchange_name(quote.exchange)}" if quote.exchange else ""
        self.symbol_label.configure(text=f"{quote.pair or coin}{where}")
        if quote.bid and quote.ask:
            self.quote_label.configure(
                text=f"{self._price(quote.bid)} / {self._price(quote.ask)}"
            )
        else:
            self.quote_label.configure(text=quote.problem or "No price")
        self.fill_prices()
        self.update_estimate()

    def fill_prices(self) -> None:
        """The price fields from the current bid and ask: a buy's from the ask, a
        sell's from the bid."""
        q = self.quote
        if q is None or not (q.bid and q.ask):
            return
        for var in (self.stop_var, self.limit_var, self.target_var):
            var.set(plain_number(q.bid))  # stops and take-profits sell
        self.cond_value_var.set(
            plain_number(q.ask if self.side_var.get() == "Buy" else q.bid)
        )

    def _side_changed(self) -> None:
        """A condition value still at the bid or ask follows the side."""
        q = self.quote
        if q is not None and q.bid and q.ask:
            prefilled = {plain_number(q.bid), plain_number(q.ask)}
            if self.cond_value_var.get() in prefilled:
                self.cond_value_var.set(
                    plain_number(q.ask if self.side_var.get() == "Buy" else q.bid)
                )
        self.update_estimate()

    # ---- the order type ----

    def _type_changed(self) -> None:
        kind = self.type_var.get()
        fixed = FIXED_SIDE.get(kind)
        if fixed:
            self.side_var.set(fixed)
        self.side_box.configure(state="disabled" if fixed else "readonly")
        for widget in self._type_widgets:
            widget.destroy()
        self._type_widgets = []
        gap = ui_tokens.SPACE["sm"]
        body = self._body
        row = self._fields_row

        def field(label: str, widget: tk.Widget) -> None:
            nonlocal row
            name = ttk.Label(body, text=label)
            name.grid(row=row, column=0, sticky="w", padx=(0, gap), pady=(gap, 0))
            widget.grid(row=row, column=1, sticky="ew", pady=(gap, 0))
            self._type_widgets += [name, widget]
            row += 1

        def entry(var: tk.StringVar) -> ttk.Entry:
            return ttk.Entry(body, textvariable=var, width=16)

        if kind == MARKET:
            self.market_price_label = ttk.Label(body, text="")
            field("Price", self.market_price_label)
        elif kind == STOP_LOSS:
            field("Stop price", entry(self.stop_var))
        elif kind == STOP_LIMIT:
            field("Stop price", entry(self.stop_var))
            field("Limit price", entry(self.limit_var))
        elif kind == TAKE_PROFIT:
            field("Target price", entry(self.target_var))
        elif kind == DCA:
            field("DCA stage", entry(self.stage_var))
            field("Neural level ≥", entry(self.level_var))
        elif kind == CONDITIONAL:
            line = ttk.Frame(body)
            ttk.Combobox(
                line,
                textvariable=self.cond_type_var,
                values=CONDITIONS,
                state="readonly",
                width=12,
            ).pack(side="left")
            ttk.Combobox(
                line,
                textvariable=self.cond_op_var,
                values=OPERATORS,
                state="readonly",
                width=3,
            ).pack(side="left", padx=(gap, 0))
            ttk.Entry(line, textvariable=self.cond_value_var, width=14).pack(
                side="left", padx=(gap, 0), fill="x", expand=True
            )
            field("When", line)
        self.update_estimate()

    # ---- the estimate ----

    def market_price(self) -> Optional[float]:
        """The current price for the side: the ask for a buy, the bid for a sell."""
        q = self.quote
        if q is None or not (q.bid and q.ask):
            return None
        return q.ask if self.side_var.get() == "Buy" else q.bid

    def order_price(self) -> Optional[float]:
        """The price the order's value is estimated at."""
        kind = self.type_var.get()
        typed = {
            STOP_LOSS: self.stop_var,
            STOP_LIMIT: self.limit_var,
            TAKE_PROFIT: self.target_var,
        }.get(kind)
        if typed is not None:
            number = parse_amount(typed.get())
            return float(number) if number is not None else None
        return self.market_price()  # Market, DCA and Conditional fill at the market

    def estimate(self) -> Tuple[Optional[float], Optional[float]]:
        """(estimated value, estimated fee); None where it can't be worked out."""
        qty = parse_amount(self.qty_var.get())
        price = self.order_price()
        if qty is None or price is None:
            return None, None
        value = float(qty) * price
        rate = self.quote.fee_rate if self.quote else None
        return value, (value * rate if rate is not None else None)

    def over_buying_power(self) -> bool:
        value, fee = self.estimate()
        if self.side_var.get() != "Buy" or value is None:
            return False
        return self.buying_power is not None and value + (fee or 0.0) > float(
            self.buying_power
        )

    def update_estimate(self) -> None:
        if not hasattr(self, "warning_label"):
            return  # still being built
        if self.type_var.get() == MARKET and hasattr(self, "market_price_label"):
            price = self.market_price()
            word = "ask" if self.side_var.get() == "Buy" else "bid"
            try:
                self.market_price_label.configure(
                    text=f"{self._price(price)} (the {word})" if price else "N/A"
                )
            except tk.TclError:
                pass
        value, fee = self.estimate()
        self.value_label.configure(text=self._money(value) if value else "N/A")
        rate = self.quote.fee_rate if self.quote else None
        self.fee_label.configure(
            text=(
                f"{self._money(fee)} ({rate * 100:.2f}%)"
                if fee is not None
                else "not known"
            )
        )
        self.power_label.configure(
            text=(
                self._money(self.buying_power)
                if self.buying_power is not None
                else "N/A"
            )
        )
        if self._banner == "blocked":
            warning = "No live exchange is chosen"
        elif self.over_buying_power():
            warning = "More than Buying Power"
        else:
            warning = ""
        self.warning_label.configure(text=warning)

    # ---- creating the order ----

    def _refuse(self, message: str) -> None:
        messagebox.showerror("Order refused", message, parent=self)

    def create(self) -> Optional[str]:
        """Check the order, confirm it, and create it; its id, or None."""
        kind, side = self.type_var.get(), self.side_var.get()
        q = self.quote
        if self._banner == "blocked":
            self._refuse(
                "Live mode has no exchange chosen, so the order has no account."
            )
            return None
        if q is None or not q.pair:
            self._refuse("The coin's market is not known yet.")
            return None
        qty = parse_amount(self.qty_var.get())
        if qty is None:
            self._refuse("Enter a quantity above 0.")
            return None
        prices: Dict[str, Decimal] = {}
        needed = {
            STOP_LOSS: (("stop", self.stop_var, "stop price"),),
            STOP_LIMIT: (
                ("stop", self.stop_var, "stop price"),
                ("limit", self.limit_var, "limit price"),
            ),
            TAKE_PROFIT: (("target", self.target_var, "target price"),),
            CONDITIONAL: (("value", self.cond_value_var, "condition value"),),
        }.get(kind, ())
        for key, var, name in needed:
            number = parse_amount(var.get())
            if number is None:
                self._refuse(f"Enter the {name}, above 0.")
                return None
            prices[key] = number
        stage = level = 0
        if kind == DCA:
            try:
                stage, level = int(self.stage_var.get()), int(self.level_var.get())
            except ValueError:
                stage = level = -1
            if stage < 1 or level < 0:
                self._refuse("Enter the DCA stage (1 or more) and the neural level.")
                return None

        value, fee = self.estimate()
        if side == "Buy":
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

        if not self.confirm(kind, side, qty, value, fee):
            return None
        try:
            order_id = self.place(kind, side, q.pair, qty, prices, stage, level)
        except Exception as exc:
            order_id = None
            detail = f"\n\n{type(exc).__name__}: {exc}"
        else:
            detail = ""
        if not order_id:
            messagebox.showerror(
                "Order not created",
                "The order could not be created." + detail,
                parent=self,
            )
            return None
        self.created_id = str(order_id)
        self.on_created(self.created_id)
        self.destroy()
        return self.created_id

    def confirm(self, kind, side, qty, value, fee) -> bool:
        from pt_exchange_abstraction import exchange_name

        q = self.quote
        lines = [
            f"Account: {self._account}",
            f"{side} {plain_number(qty)} {q.pair} on {exchange_name(q.exchange)}",
            f"Type: {kind}",
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

    def place(self, kind, side, symbol, qty, prices, stage, level) -> Optional[str]:
        """Create the order through the OrderManager (the order management
        database), as the tab's form did."""
        from order_management_models import (
            ConditionOperator,
            ConditionType,
            OrderSide,
            OrderType,
        )

        m = self.manager
        order_side = OrderSide.BUY if side == "Buy" else OrderSide.SELL
        if kind == MARKET:
            order = m.db.create_order(
                symbol=symbol,
                order_type=OrderType.MARKET,
                side=order_side,
                quantity=qty,
            )
            return str(order.id)
        if kind == STOP_LOSS:
            return m.create_stop_loss_order(symbol, qty, prices["stop"])
        if kind == STOP_LIMIT:
            return m.create_stop_loss_order(
                symbol, qty, prices["stop"], prices["limit"]
            )
        if kind == TAKE_PROFIT:
            return m.create_take_profit_order(symbol, qty, prices["target"])
        if kind == DCA:
            return m.create_dca_order(symbol, qty, stage, level)
        if kind == CONDITIONAL:
            condition = {
                "Price": ConditionType.PRICE,
                "Neural level": ConditionType.NEURAL_LEVEL,
                "Volume": ConditionType.VOLUME,
            }[self.cond_type_var.get()]
            operator = {
                "≥": ConditionOperator.GTE,
                "≤": ConditionOperator.LTE,
                ">": ConditionOperator.GT,
                "<": ConditionOperator.LT,
                "=": ConditionOperator.EQ,
            }[self.cond_op_var.get()]
            order = m.db.create_order(
                symbol=symbol,
                order_type=OrderType.CONDITIONAL,
                side=order_side,
                quantity=qty,
            )
            m.db.add_condition_to_order(
                order.id, condition, operator, prices["value"], symbol=symbol
            )
            return str(order.id)
        return None


class OrderManagementView(ttk.Frame):
    """The tab: toolbar and orders over the Order Notifications; see the module
    docstring. The callables give the hub's current coins, the coin shown in the
    chart, the trading settings and Buying Power when an order is created.
    ``refresh_ms=None`` reads the database only when asked (tests)."""

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
        money: Callable[[float], str] = _plain_money,
        price: Callable[[float], str] = _plain_price,
        refresh_ms: Optional[int] = REFRESH_MS,
    ):
        super().__init__(parent)
        self.manager = manager
        self._coins, self._chart_coin = coins, chart_coin
        self._trading, self._buying_power = trading, buying_power
        self.market = market if market is not None else ExchangeMarket()
        self._money, self._price = money, price
        self._refresh_ms = refresh_ms
        self.orders: List[OrderRow] = []
        self.shown: List[OrderRow] = []
        self.notes: List[NoteRow] = []
        self.dialog: Optional[OrderDialog] = None
        self._search_after: Optional[str] = None
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
        )
        self.orders_table.pack(side="top", fill="both", expand=True)
        self.orders_tree = self.orders_table.tree

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

        self.refresh()
        if refresh_ms:
            self.after(refresh_ms, self._tick)

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

    # ---- reading the database ----

    def _tick(self) -> None:
        try:
            self.refresh()
            self.after(self._refresh_ms, self._tick)
        except tk.TclError:
            pass  # the tab is gone

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

    def matches(self) -> List[OrderRow]:
        """The orders the status filter and the search keep."""
        statuses = dict(STATUS_FILTERS).get(self.status_var.get())
        words = self.search_var.get().casefold().split()
        kept = []
        for r in self.orders:
            if statuses is not None and r.status not in statuses:
                continue
            if words:
                text = " ".join(self.cells(r)).casefold()
                if not all(w in text for w in words):
                    continue
            kept.append(r)
        return kept

    def apply_filters(self) -> None:
        tree = self.orders_tree
        selected = set(tree.selection())
        top = tree.yview()[0]
        kept = self.matches()
        self.shown = kept
        tree.delete(*tree.get_children())
        for r in kept:
            tree.insert("", "end", iid=r.id, values=self.cells(r))
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
        coins = [str(c).upper() for c in (self._coins() or ())]
        shown = str(self._chart_coin() or "").upper()
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
            manager=self.manager,
            on_created=lambda _id: self.refresh(),
            money=self._money,
            price=self._price,
            background=background,
        )
        return self.dialog

    def cancel_selected(self) -> int:
        """Cancel the selected open orders, after a confirmation; how many were."""
        selected = set(self.orders_tree.selection())
        if not selected:
            messagebox.showinfo(
                "Cancel orders", "Select the orders to cancel first.", parent=self
            )
            return 0
        rows = [r for r in self.orders if r.id in selected and r.is_open]
        if not rows:
            messagebox.showinfo(
                "Cancel orders", "Only open orders can be cancelled.", parent=self
            )
            return 0
        lines = [
            f"{r.side} {plain_number(r.quantity)} {r.symbol}, {r.kind}"
            for r in rows[:10]
        ]
        if len(rows) > 10:
            lines.append(f"... and {len(rows) - 10} more")
        skipped = len(selected) - len(rows)
        if skipped:
            lines.append(f"({skipped} selected order(s) not open: left as they are)")
        n = len(rows)
        if not messagebox.askyesno(
            "Cancel orders",
            f"Cancel {n} order{'' if n == 1 else 's'}?\n\n" + "\n".join(lines),
            parent=self,
        ):
            return 0
        failed = [r for r in rows if not self.manager.cancel_order(uuid.UUID(r.id))]
        self.refresh()
        if failed:
            messagebox.showerror(
                "Cancel orders",
                f"{len(failed)} order(s) could not be cancelled: "
                + ", ".join(r.client_id for r in failed),
                parent=self,
            )
        return n - len(failed)
