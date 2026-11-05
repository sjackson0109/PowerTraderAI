"""Order Management's orders, carried out (owner, 2026-11-05).

The Create Order dialog makes one of six kinds of order: Market, Limit, Stop-Limit,
Trailing Stop, OCO and Bracket. ``OrderExecutor.create`` writes it to the order
management database and ``OrderExecutor`` carries it out, on the account it was made
for and through the exchange layer:

* Paper: the paper account (``trading_mode.PaperExchange`` on the saved book, the
  one the paper trader uses), at the live quotes of the exchanges in Settings,
  primary first, paying the fees ``trading_fees()`` gives. A market order fills at
  once; every other kind is managed by PowerTrader: the app watches the quote and
  fills the paper account when the order's price is reached.
* Live: the broker chosen in Trading Mode, through the trading-mode gate
  (``resolve_order_target``). A kind the broker's connector places as the
  exchange's own order (``native_order_kinds``) is placed there and followed until
  it is done; any other is managed by PowerTrader, which places a market order when
  its price is reached.

How each kind works:

* Limit: fills at its price or better. One the market has already reached when it
  is made fills at once, at the market (as on an exchange); a paper limit reached
  later fills at its own price, at the maker rate.
* Stop-Limit: when the price reaches the stop (falls to it for a sell, rises to it
  for a buy), its limit order works.
* Trailing Stop: follows the best price since it was made (the highest bid for a
  sell, the lowest ask for a buy) at a distance: a percent of that price, or a
  multiple of the coin's average true range (``ATR_LENGTH`` bars of ``ATR_TF``
  candles) when it was made. When the price comes back to it, it is a market order.
* OCO: a take-profit limit and a stop (a market order once reached); when one fills,
  the other is cancelled.
* Bracket: an entry (market or limit) with a take-profit and a stop attached, which
  work as an OCO order once the entry has filled.

A fill is recorded on the order (Active Orders), as a notification, and in the
account's trade history (``trade_history.jsonl``, tag MANUAL, with its fee and how
the fee was worked out), which the Trade History tab shows. No order is created or
carried out while trading is halted (Settings > Risk). The orders the app manages
need it running: ``check`` goes over them every few seconds (the Order Management
tab's monitor). They are kept in the database, so it carries on with them when the
app starts again.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

try:  # SQLAlchemy: without it the hub shows Order Management as not available
    from order_management_models import (
        ManagedOrder,
        NotificationType,
        Order,
        OrderExecution,
        OrderSide,
        OrderStatus,
        OrderType,
        create_notification,
    )
except ImportError:  # the kinds, OrderSpec and the checks below still work
    ManagedOrder = NotificationType = Order = OrderExecution = None
    OrderSide = OrderStatus = OrderType = create_notification = None

# ---- the kinds of order (the dialog's names are in order_management_view) ----

MARKET = "market"
LIMIT = "limit"
STOP_LIMIT = "stop_limit"
TRAILING_STOP = "trailing_stop"
OCO = "oco"
BRACKET = "bracket"
KINDS = (MARKET, LIMIT, STOP_LIMIT, TRAILING_STOP, OCO, BRACKET)

PERCENT = "percent"
ATR = "atr"
ATR_LENGTH = 14  # bars in the average true range of a trailing stop's ATR multiple
ATR_TF = "1h"  # of these candles
ATR_TF_TEXT = "1-hour"
ATR_HISTORY_BARS = 5 * ATR_LENGTH  # Wilder smoothing needs room to settle

# How an order is carried out (ManagedOrder.handling)
BY_EXCHANGE = "exchange"
BY_POWERTRADER = "powertrader"
MANAGED_TEXT = "managed by PowerTrader, requires the app to be running"

TAG = "MANUAL"  # the trade history's tag for these fills (Trade History: Manual)
# A new order not sent within this many seconds (the app stopped first) is not sent
# later: a market order from hours ago would fill at a price nobody chose
SEND_WITHIN_S = 120.0

SIDES = ("buy", "sell")
# an exchange's words for an order that will not fill any more
_ENDED = {
    "cancelled": OrderStatus.CANCELLED,
    "canceled": OrderStatus.CANCELLED,
    "expired": OrderStatus.EXPIRED,
    "expired_in_match": OrderStatus.EXPIRED,
    "rejected": OrderStatus.REJECTED,
    "failed": OrderStatus.REJECTED,
}


def _utcnow() -> datetime:
    """Now in UTC without a zone, as the order database keeps its times."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def other_side(side: str) -> str:
    return "sell" if side == "buy" else "buy"


def _f(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError, ArithmeticError):
        return None


def _d(value: Any) -> Optional[Decimal]:
    return None if value is None else Decimal(str(value))


def _plain(value: Any) -> str:
    number = _f(value)
    if number is None:
        return ""
    return f"{number:,.8f}".rstrip("0").rstrip(".")


# ---- an order as the dialog makes it ----


@dataclass(frozen=True)
class OrderSpec:
    """One order from the Create Order dialog.

    ``coin`` and ``quantity`` (coins); ``side`` "buy" or "sell" (a Bracket order's
    entry side: its exits are the other side); ``exchange`` and ``pair`` the
    exchange whose market it is and that exchange's symbol. ``price``: a limit
    order's price, a stop-limit's limit, a Bracket's entry limit (None: a market
    entry). ``stop_price``: a stop-limit's, OCO's or Bracket's stop.
    ``take_profit``: an OCO's or Bracket's take-profit. A trailing stop has
    ``trail_mode`` ("percent" or "atr") and ``trail_value`` (the percent, or the
    multiple of ``atr``). ``reference`` is the price the dialog showed (the ask for
    a buy, the bid for a sell)."""

    kind: str
    coin: str
    side: str
    quantity: Decimal
    exchange: str = ""
    pair: str = ""
    price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    trail_mode: Optional[str] = None
    trail_value: Optional[Decimal] = None
    atr: Optional[float] = None
    reference: Optional[float] = None

    def trail_pct(self, price: Optional[float] = None) -> Optional[float]:
        """The trail as a percent of ``price`` (the reference price by default)."""
        value = _f(self.trail_value)
        if value is None:
            return None
        if self.trail_mode == PERCENT:
            return value
        base = price if price else self.reference
        if self.atr and base:
            return value * float(self.atr) / float(base) * 100.0
        return None


def problem_with(spec: OrderSpec, bid: Optional[float], ask: Optional[float]) -> str:
    """Why the order cannot be made as it is, against the current ``bid`` and
    ``ask`` ("" when it can). A stop already reached would fill at once, and an OCO
    or Bracket order's take-profit and stop must be on either side of the price."""
    if spec.kind not in KINDS:
        return f"Unknown order type {spec.kind!r}."
    if spec.side not in SIDES:
        return "The side must be Buy or Sell."
    if not spec.quantity or spec.quantity <= 0:
        return "Enter a quantity above 0."
    sell = spec.side == "sell"
    if spec.kind in (LIMIT, STOP_LIMIT) and not spec.price:
        return "Enter the limit price, above 0."
    if spec.kind in (STOP_LIMIT, OCO, BRACKET) and not spec.stop_price:
        return "Enter the stop price, above 0."
    if spec.kind in (OCO, BRACKET) and not spec.take_profit:
        return "Enter the take-profit price, above 0."
    if spec.kind == TRAILING_STOP:
        value = _f(spec.trail_value)
        if spec.trail_mode not in (PERCENT, ATR) or not value or value <= 0:
            return "Enter the trail distance, above 0."
        if spec.trail_mode == PERCENT and value >= 100:
            return "A trail in percent must be below 100."
        if spec.trail_mode == ATR and not spec.atr:
            return "The coin's ATR is not known yet, so the trail has no distance."
    if spec.kind == STOP_LIMIT and bid and ask:
        stop = float(spec.stop_price)
        if sell and stop >= bid:
            return (
                f"A sell's stop must be below the bid ({_plain(bid)}): this one would "
                "be reached at once."
            )
        if not sell and stop <= ask:
            return (
                f"A buy's stop must be above the ask ({_plain(ask)}): this one would "
                "be reached at once."
            )
    if spec.kind == OCO and bid and ask:
        tp, stop = float(spec.take_profit), float(spec.stop_price)
        if sell and not stop < bid < tp:
            return (
                f"A sell's take-profit must be above the bid ({_plain(bid)}) and its "
                "stop below it."
            )
        if not sell and not tp < ask < stop:
            return (
                f"A buy's take-profit must be below the ask ({_plain(ask)}) and its "
                "stop above it."
            )
    if spec.kind == BRACKET:
        entry = float(spec.price) if spec.price else (bid if sell else ask)
        if entry:
            tp, stop = float(spec.take_profit), float(spec.stop_price)
            if not sell and not stop < entry < tp:
                return (
                    f"A buy's take-profit must be above its entry ({_plain(entry)}) "
                    "and its stop below it."
                )
            if sell and not tp < entry < stop:
                return (
                    f"A sell's take-profit must be below its entry ({_plain(entry)}) "
                    "and its stop above it."
                )
    return ""


def _request(spec: OrderSpec, kind: str, side: str, price=None, stop=None, trail=None):
    from pt_exchange_abstraction import OrderRequest, dollar_symbol

    return OrderRequest(
        kind=kind,
        symbol=dollar_symbol(spec.coin),
        side=side,
        amount=float(spec.quantity),
        price=_f(price),
        stop_price=_f(stop),
        trail_pct=trail,
    )


def handling(spec: OrderSpec, live: bool, connector: Any) -> Dict[str, str]:
    """How each part of ``spec`` is carried out: {"order"} for a single order,
    {"group", "entry", "exits"} for a Bracket, {"group"} for an OCO, each "exchange"
    or "powertrader". Paper orders are all PowerTrader's (a market order fills at
    once); a live one is the exchange's when ``connector`` places that kind as its
    own order (``supports_native_order``). A Bracket's exits are attached by
    PowerTrader once its entry fills, so the Bracket itself is PowerTrader's."""

    def native(request) -> str:
        if not live or connector is None:
            return BY_POWERTRADER
        try:
            return (
                BY_EXCHANGE
                if connector.supports_native_order(request)
                else BY_POWERTRADER
            )
        except Exception:
            return BY_POWERTRADER

    if spec.kind == MARKET:
        return {"order": BY_EXCHANGE if live else BY_POWERTRADER}
    if spec.kind in (LIMIT, STOP_LIMIT):
        return {
            "order": native(
                _request(spec, spec.kind, spec.side, spec.price, spec.stop_price)
            )
        }
    if spec.kind == TRAILING_STOP:
        trail = spec.trail_pct() if spec.trail_mode == PERCENT else None
        return {
            "order": (
                native(_request(spec, TRAILING_STOP, spec.side, trail=trail))
                if trail is not None
                else BY_POWERTRADER
            )
        }
    if spec.kind == OCO:
        return {
            "group": native(
                _request(spec, OCO, spec.side, spec.take_profit, spec.stop_price)
            )
        }
    entry = (
        native(_request(spec, LIMIT, spec.side, spec.price))
        if spec.price
        else (BY_EXCHANGE if live else BY_POWERTRADER)
    )
    exits = native(
        _request(spec, OCO, other_side(spec.side), spec.take_profit, spec.stop_price)
    )
    return {"group": BY_POWERTRADER, "entry": entry, "exits": exits}


def handling_text(spec: OrderSpec, live: bool, connector: Any, exchange: str) -> str:
    """What the dialog says of how the order is carried out."""
    parts = handling(spec, live, connector)
    if not live:
        if spec.kind == MARKET:
            return "Fills at once in the paper account, at the market."
        return f"Paper account: {MANAGED_TEXT}."
    if spec.kind == BRACKET:
        where = (
            f"; its take-profit and stop are placed on {exchange} as one order "
            "once the entry fills"
            if parts["exits"] == BY_EXCHANGE
            else ""
        )
        return f"Placed on {exchange}; {MANAGED_TEXT}{where}."
    mine = parts.get("order") or parts.get("group")
    if mine == BY_EXCHANGE:
        return f"Placed on {exchange} as its own order."
    return f"On {exchange}: {MANAGED_TEXT}."


# ---- what the monitor reads of an order ----


@dataclass
class Item:
    """One order (or a group or leg) with how it is carried out, read in a session
    and used outside it (network calls never hold the database)."""

    id: Any
    parent_id: Any
    client_id: str
    exchange_order_id: str
    order_type: str
    side: str
    quantity: float
    price: Optional[float]
    stop: Optional[float]
    status: str
    filled: float
    created: Optional[datetime]
    account: str
    books: str
    exchange: str
    pair: str
    coin: str
    kind: str
    role: str
    handling: str
    state: str
    trail_mode: Optional[str]
    trail_value: Optional[float]
    atr: Optional[float]
    best_price: Optional[float]
    note: str
    updated: Optional[datetime] = None  # its ManagedOrder's last change
    legs: List["Item"] = field(default_factory=list)

    @property
    def is_open(self) -> bool:
        return self.status in ("pending", "submitted", "partial")

    def leg(self, role: str) -> Optional["Item"]:
        for leg in self.legs:
            if leg.role == role:
                return leg
        return None


def _item(order: Order, m: ManagedOrder) -> Item:
    return Item(
        id=order.id,
        parent_id=order.parent_order_id,
        client_id=str(order.client_order_id or ""),
        exchange_order_id=str(order.exchange_order_id or ""),
        order_type=order.order_type.value,
        side=order.side.value,
        quantity=float(order.quantity),
        price=_f(order.price),
        stop=_f(order.stop_price),
        status=order.status.value,
        filled=float(order.filled_quantity or 0),
        created=order.created_at,
        account=m.account,
        books=m.books,
        exchange=m.exchange or "",
        pair=m.pair or "",
        coin=m.coin,
        kind=m.kind,
        role=m.role,
        handling=m.handling,
        state=m.state,
        trail_mode=m.trail_mode,
        trail_value=_f(m.trail_value),
        atr=_f(m.atr),
        best_price=_f(m.best_price),
        note=str(m.note or ""),
        updated=m.updated_at,
    )


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    exchange: str = ""


class Skip(Exception):
    """The order waits this time (no live price, trading halted, ...): the message
    is its note."""


# ---- the executor ----


class OrderExecutor:
    """Creates Order Management's orders and carries them out (module docstring).

    ``db`` is the OrderManagementDB; ``hub_dir`` the hub folder (or a callable that
    gives it); ``trading()`` the hub's current trading settings
    (trading_mode.TradingSettings). The rest are for tests: ``paper(book_path)``
    makes the paper account, ``live(settings)`` the live order target,
    ``quote(settings, coin)`` a Quote, ``halt(books_dir)`` why trading is halted
    ("" when it is not), and ``atr(coin, exchange)`` a coin's ATR."""

    def __init__(
        self,
        db: Any,
        *,
        hub_dir: Any,
        trading: Callable[[], Any],
        paper: Optional[Callable[[str], Any]] = None,
        live: Optional[Callable[[Any], Any]] = None,
        quote: Optional[Callable[[Any, str], Optional[Quote]]] = None,
        halt: Optional[Callable[[str], str]] = None,
        atr: Optional[Callable[[str, str], Optional[float]]] = None,
        clock: Callable[[], float] = time.time,
    ):
        self.db = db
        self._hub_dir = hub_dir
        self._trading = trading
        self._make_paper = paper
        self._make_live = live
        self._quote_fn = quote
        self._halt_fn = halt
        self._atr_fn = atr
        self._clock = clock
        self._paper: Dict[str, Any] = {}
        self._targets: Dict[str, Any] = {}
        self._connectors: Dict[str, Any] = {}

    # ---- the account an order is for ----

    def hub_dir(self) -> str:
        return self._hub_dir() if callable(self._hub_dir) else str(self._hub_dir)

    def books_dir(self, books: str) -> str:
        return os.path.join(self.hub_dir(), books)

    def settings(self) -> Any:
        return self._trading()

    def halt_reason(self, books: str) -> str:
        """Why trading is halted for the account whose books are in ``books`` (""
        when it is not): Settings > Risk's emergency stop."""
        if self._halt_fn is not None:
            return self._halt_fn(self.books_dir(books)) or ""
        import risk_state

        view = risk_state.current(self.books_dir(books))
        if not view.halted:
            return ""
        return view.halt_reason or "Emergency stop"

    def refusal(self, settings: Any) -> str:
        """Why no order can be made for ``settings`` now ("" when one can)."""
        if settings is None:
            return "The trading mode is not known."
        if settings.is_live and not settings.active_broker:
            return "Live mode has no exchange chosen, so the order has no account."
        if settings.uses_preview:
            return (
                "Live trading is set to preview orders, so nothing is placed: turn "
                "off Preview orders only in File > Trading Mode to place orders."
            )
        reason = self.halt_reason(settings.data_subdir)
        if reason:
            return (
                f"Trading is halted ({reason}). Resume trading is in Settings > Risk."
            )
        return ""

    def connector(self, broker: str) -> Any:
        """``broker``'s connector without credentials: what its exchange can hold
        (``native_order_kinds``), with no request sent."""
        if broker not in self._connectors:
            import pt_exchanges  # noqa: F401  (registers the connectors)
            from pt_exchange_abstraction import ExchangeFactory, ExchangeType

            self._connectors[broker] = ExchangeFactory.get_exchange(
                ExchangeType(broker), api_key="", api_secret=""
            )
        return self._connectors[broker]

    def paper_account(self) -> Any:
        """The paper account on the saved book, the one the paper trader uses
        (``<hub>/paper/paper_account.json``). Raises RuntimeError when the saved book
        cannot be read, so that it is never overwritten."""
        import trading_mode as tm

        path = tm.paper_book_path(self.hub_dir())
        try:
            tm.read_paper_book(path)
        except tm.PaperBookUnreadable as exc:
            raise RuntimeError(
                f"{exc} Fix it in Settings > Paper Account; until then no paper order "
                "is filled."
            ) from None
        except tm.PaperBookInvalid:
            pass  # the trader loads it as written: so does this account
        if path not in self._paper:
            if self._make_paper is not None:
                self._paper[path] = self._make_paper(path)
            else:
                self._paper[path] = tm.PaperExchange(
                    initial_balance=tm.DEFAULT_PAPER_BALANCE,
                    price_feed=tm.fetch_public_quote,
                    fee_feed=tm.fetch_trading_fees,
                    state_path=path,
                )
        return self._paper[path]

    def live_target(self, settings: Any) -> Any:
        """The trading-mode gate's target for ``settings`` (built once per key)."""
        key = settings.key
        if key not in self._targets:
            if self._make_live is not None:
                self._targets[key] = self._make_live(settings)
            else:
                from trading_mode import resolve_order_target

                target = resolve_order_target()
                if target.key != key:
                    raise RuntimeError(
                        "The trading mode changed while the order was being sent."
                    )
                self._targets[key] = target
        return self._targets[key]

    def quote(self, settings: Any, coin: str) -> Quote:
        """The bid and ask an order of ``coin`` is checked against: the paper
        account's live quote (the exchanges in Settings, primary first), or the live
        broker's. Raises Skip when there is none, or it is not live."""
        if self._quote_fn is not None:
            answer = self._quote_fn(settings, coin)
            if answer is None:
                raise Skip(f"No price for {coin}")
            return answer
        if settings.is_live:
            from pt_exchange_abstraction import dollar_symbol

            q = self.live_target(settings).exchange.quote(dollar_symbol(coin))
            if q is None or not (q.bid > 0 and q.ask > 0):
                raise Skip(f"No price for {coin} from the exchange")
            return Quote(float(q.bid), float(q.ask), settings.active_broker)
        import trading_mode as tm

        q = tm.fetch_public_quote(coin)
        source = tm.classify_quote(
            q, tm.read_paper_settings().max_quote_age_s, time.time()
        )
        if source != "live":
            raise Skip(f"No live price for {coin} (the price is {source})")
        return Quote(q.bid, q.ask, q.exchange)

    def atr(self, coin: str, exchange: str = "") -> Optional[float]:
        """``coin``'s average true range: ATR_LENGTH bars of ATR_TF candles from the
        exchange layer (``exchange`` first when given), the latest closed bar's."""
        if self._atr_fn is not None:
            return self._atr_fn(coin, exchange)
        return candle_atr(coin, exchange)

    # ---- making an order ----

    def create(self, spec: OrderSpec) -> str:
        """Write ``spec`` to the database for the account trading now and return its
        id (a group's for an OCO or Bracket order). Sends nothing: ``submit`` does.
        Raises ValueError with the reason when it cannot be made."""
        settings = self.settings()
        refused = self.refusal(settings)
        if refused:
            raise ValueError(refused)
        problem = problem_with(spec, None, None)
        if problem:
            raise ValueError(problem)
        live = bool(settings.is_live)
        exchange = settings.active_broker if live else spec.exchange
        connector = self.connector(settings.active_broker) if live else None
        how = handling(spec, live, connector)
        context = dict(
            account=settings.key,
            books=settings.data_subdir,
            exchange=exchange or "",
            pair=spec.pair,
            coin=spec.coin,
            kind=spec.kind,
        )
        side = spec.side
        qty = spec.quantity
        db = self.db
        sides = {"buy": OrderSide.BUY, "sell": OrderSide.SELL}
        types = {
            MARKET: OrderType.MARKET,
            LIMIT: OrderType.LIMIT,
            STOP_LIMIT: OrderType.STOP_LIMIT,
            TRAILING_STOP: OrderType.TRAILING_STOP,
        }

        def order(order_type, side_, price=None, stop=None, parent=None, notify=False):
            return db.create_order(
                symbol=spec.pair or spec.coin,
                order_type=order_type,
                side=sides[side_],
                quantity=qty,
                price=price,
                stop_price=stop,
                tag=TAG,
                parent_order_id=parent,
                notify=notify,
            ).id

        def managed(order_id, role, handled, state="new", **extra):
            with db.get_session() as s:
                s.add(
                    ManagedOrder(
                        order_id=order_id,
                        role=role,
                        handling=handled,
                        state=state,
                        **context,
                        **extra,
                    )
                )

        if spec.kind in (MARKET, LIMIT, STOP_LIMIT, TRAILING_STOP):
            price = spec.price if spec.kind in (LIMIT, STOP_LIMIT) else None
            stop = spec.stop_price if spec.kind == STOP_LIMIT else None
            oid = order(types[spec.kind], side, price, stop, notify=True)
            extra = {}
            if spec.kind == TRAILING_STOP:
                extra = dict(
                    trail_mode=spec.trail_mode,
                    trail_value=spec.trail_value,
                    atr=_d(spec.atr),
                )
            managed(oid, "order", how["order"], **extra)
            return str(oid)
        if spec.kind == OCO:
            group = order(
                OrderType.OCO, side, spec.take_profit, spec.stop_price, notify=True
            )
            managed(group, "group", how["group"])
            tp = order(OrderType.LIMIT, side, spec.take_profit, parent=group)
            managed(tp, "take_profit", how["group"])
            sl = order(OrderType.STOP, side, None, spec.stop_price, parent=group)
            managed(sl, "stop", how["group"])
            return str(group)
        # a Bracket: the entry, then its exits on the other side
        group = order(OrderType.BRACKET, side, spec.price, spec.stop_price, notify=True)
        managed(group, "group", how["group"])
        entry_type = OrderType.LIMIT if spec.price else OrderType.MARKET
        entry = order(entry_type, side, spec.price, parent=group)
        managed(entry, "entry", how["entry"])
        exit_side = other_side(side)
        tp = order(OrderType.LIMIT, exit_side, spec.take_profit, parent=group)
        managed(tp, "take_profit", how["exits"], state="waiting")
        sl = order(OrderType.STOP, exit_side, None, spec.stop_price, parent=group)
        managed(sl, "stop", how["exits"], state="waiting")
        return str(group)

    # ---- reading the database ----

    def _items(self, account: Optional[str] = None, ids=None) -> List[Item]:
        """The open orders this executor carries out (of ``account``; or ``ids``),
        each group with its legs (the legs are not listed on their own)."""
        with self.db.get_session() as s:
            q = s.query(Order, ManagedOrder).join(
                ManagedOrder, ManagedOrder.order_id == Order.id
            )
            if ids is not None:
                q = q.filter(Order.id.in_(list(ids)))
            else:
                q = q.filter(
                    Order.status.in_(
                        [
                            OrderStatus.PENDING,
                            OrderStatus.SUBMITTED,
                            OrderStatus.PARTIAL,
                        ]
                    )
                )
                if account is not None:
                    q = q.filter(ManagedOrder.account == account)
            rows = [_item(o, m) for o, m in q.order_by(Order.created_at).all()]
            by_id = {r.id: r for r in rows}
            parents = {r.parent_id for r in rows if r.parent_id is not None}
            missing = [p for p in parents if p not in by_id]
            if missing:
                for o, m in (
                    s.query(Order, ManagedOrder)
                    .join(ManagedOrder, ManagedOrder.order_id == Order.id)
                    .filter(Order.id.in_(missing))
                    .all()
                ):
                    by_id[o.id] = _item(o, m)
            legs_wanted = [r.id for r in by_id.values() if r.role == "group"]
            if legs_wanted:
                for o, m in (
                    s.query(Order, ManagedOrder)
                    .join(ManagedOrder, ManagedOrder.order_id == Order.id)
                    .filter(Order.parent_order_id.in_(legs_wanted))
                    .order_by(Order.created_at)
                    .all()
                ):
                    by_id.setdefault(o.id, _item(o, m))
        tops = [r for r in by_id.values() if r.parent_id is None]
        for r in by_id.values():
            if r.parent_id is not None and r.parent_id in by_id:
                parent = by_id[r.parent_id]
                if all(leg.id != r.id for leg in parent.legs):
                    parent.legs.append(r)
        return sorted(tops, key=lambda r: r.created or datetime.min)

    def item(self, order_id) -> Optional[Item]:
        """The order (with its legs, for a group), whatever its status."""
        oid = (
            uuid.UUID(str(order_id))
            if not isinstance(order_id, uuid.UUID)
            else order_id
        )
        ids = self.db.order_group(oid)
        if not ids:
            return None
        tops = self._items(ids=ids)
        return tops[0] if tops else None

    def _update(self, item: Item, *, note: Optional[str] = None, **fields) -> None:
        """Change an order (``status``, ``price``, ``stop_price``,
        ``exchange_order_id``) and its ManagedOrder (``state``, ``best_price``,
        ``note``, ...) in one session."""
        order_fields = {
            k: fields.pop(k)
            for k in list(fields)
            if k in ("status", "price", "stop_price", "exchange_order_id", "quantity")
        }
        with self.db.get_session() as s:
            order = s.query(Order).filter(Order.id == item.id).one()
            m = s.query(ManagedOrder).filter(ManagedOrder.order_id == item.id).one()
            for key, value in order_fields.items():
                setattr(order, key, value)
                if key == "status" and value is OrderStatus.SUBMITTED:
                    order.submitted_at = order.submitted_at or _utcnow()
                if key == "status" and value in (
                    OrderStatus.CANCELLED,
                    OrderStatus.REJECTED,
                    OrderStatus.EXPIRED,
                ):
                    m.state = "done"
            for key, value in fields.items():
                setattr(m, key, value)
            if note is not None:
                m.note = note or None
            order.updated_at = _utcnow()
        for key in ("status",):
            if key in order_fields:
                item.status = order_fields[key].value
        if "state" in fields:
            item.state = fields["state"]
        if note is not None:
            item.note = note

    def _notify(self, item: Item, kind: NotificationType, title: str, text: str):
        with self.db.get_session() as s:
            create_notification(s, item.id, kind, title, text)

    def _end(self, item: Item, status: OrderStatus, why: str, notify=True) -> None:
        """The order will not fill: cancelled, rejected or expired, with why."""
        self._update(item, status=status, state="done", note=why)
        if notify:
            word = status.value.title()
            self._notify(
                item,
                {OrderStatus.EXPIRED: NotificationType.ORDER_EXPIRED}.get(
                    status, NotificationType.ORDER_CANCELLED
                ),
                f"Order {word}: {item.pair or item.coin}",
                f"{self.describe(item)}: {why}" if why else self.describe(item),
            )

    @staticmethod
    def describe(item: Item) -> str:
        return (
            f"{item.side.capitalize()} {_plain(item.quantity)} {item.pair or item.coin}"
        )

    # ---- sending a new order ----

    def submit(self, order_id) -> str:
        """Send a new order (a market order fills or is placed now; an order the
        exchange holds is placed; one PowerTrader manages starts working). Returns
        what happened ("" when nothing stopped it). Network: run it off the Tk
        thread."""
        item = self.item(order_id)
        if item is None or not item.is_open:
            return ""
        try:
            return self._run(item, self.settings(), first=True)
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}"
            self._update(item, note=text)
            return text

    # ---- the monitor ----

    def check(self) -> int:
        """One look at every open order of the account trading now: sends new ones,
        follows the ones an exchange holds, and carries out the ones PowerTrader
        manages whose price was reached. Returns how many were looked at."""
        settings = self.settings()
        if settings is None or (settings.is_live and not settings.active_broker):
            return 0
        tops = self._items(account=settings.key)
        quotes: Dict[str, Any] = {}
        for item in tops:
            if not item.is_open:
                continue  # a leg's group that is done
            try:
                self._run(item, settings, quotes=quotes)
            except Exception as exc:  # one order's trouble never stops the others
                text = f"{type(exc).__name__}: {exc}"
                if item.note != text:
                    self._update(item, note=text)
        return len(tops)

    def _run(self, item: Item, settings, first=False, quotes=None) -> str:
        """``_advance``; an order that cannot be carried out at all is rejected
        (a group with all its legs), and one that waits notes why."""
        try:
            return self._advance(item, settings, first=first, quotes=quotes)
        except _Refused as why:
            self._end_group(item, OrderStatus.REJECTED, str(why))
            return str(why)
        except Skip as why:
            if item.note != str(why):
                self._update(item, note=str(why))
            return str(why)

    def _price(self, settings, coin, quotes) -> Quote:
        if quotes is None:
            return self.quote(settings, coin)
        if coin not in quotes:
            try:
                quotes[coin] = self.quote(settings, coin)
            except Skip as why:
                quotes[coin] = why
        answer = quotes[coin]
        if isinstance(answer, Skip):
            raise answer
        return answer

    def _advance(self, item: Item, settings, first=False, quotes=None) -> str:
        """Carry ``item`` on as far as it goes now."""
        if item.account != settings.key:
            raise Skip("Waits: made for another account than the one trading now")
        halt = self.halt_reason(item.books)
        if halt:
            raise Skip(f"Not carried out while trading is halted ({halt})")
        if item.state == "new" and not first:
            made = item.updated or item.created or _utcnow()
            if _utcnow() - made > timedelta(seconds=SEND_WITHIN_S):
                self._end_group(
                    item,
                    OrderStatus.EXPIRED,
                    "Not sent: the app stopped before it was sent",
                )
                return "expired"
        if item.role == "group" and item.kind == OCO:
            return self._oco(item, settings, quotes)
        if item.role == "group" and item.kind == BRACKET:
            return self._bracket(item, settings, quotes)
        return self._single(item, settings, quotes)

    def _end_group(self, item: Item, status: OrderStatus, why: str) -> None:
        self._end(item, status, why)
        for leg in item.legs:
            if leg.is_open:
                self._end(leg, status, why, notify=False)

    # ---- one order ----

    def _single(self, item: Item, settings, quotes) -> str:
        """A market, limit, stop-limit or trailing-stop order (or a Bracket's
        entry, or an exit)."""
        _not_in_doubt(item)
        if item.handling == BY_EXCHANGE or item.state == "placed":
            if item.state == "new":
                return self._place_native(item, settings)
            return self._follow(item, settings)
        try:
            q = self._price(settings, item.coin, quotes)
        except Skip as why:
            if item.order_type == "market" and item.state == "new":
                raise _Refused(f"{why}: a market order is not kept for later")
            raise
        if item.state == "new":
            self._update(item, status=OrderStatus.SUBMITTED, state="working")
            item.state = "working"
            if item.order_type == "market":
                return self._fill_now(item, settings, q)
            if item.order_type == "limit" and self._limit_reached(item, q):
                return self._fill_now(item, settings, q)  # marketable: a taker
        kind = item.order_type
        if kind == "limit":
            if self._limit_reached(item, q):
                return self._fill_at(item, settings, q, item.price)
            return ""
        if kind == "stop_limit":
            if item.state == "working" and self._stop_reached(item, q):
                self._update(
                    item, state="triggered", note="Stop reached: the limit works"
                )
                item.state = "triggered"
                if self._limit_reached(item, q):
                    return self._fill_now(item, settings, q)
                return "triggered"
            if item.state == "triggered" and self._limit_reached(item, q):
                return self._fill_at(item, settings, q, item.price)
            return ""
        if kind == "stop":
            if self._stop_reached(item, q):
                return self._fill_now(item, settings, q)
            return ""
        if kind == "trailing_stop":
            return self._trail(item, settings, q)
        if kind == "market":
            return ""  # a market order fills when it is sent
        raise Skip(f"Not carried out: {kind} orders are not made here")

    @staticmethod
    def _limit_reached(item: Item, q: Quote) -> bool:
        if item.price is None:
            return False
        return q.ask <= item.price if item.side == "buy" else q.bid >= item.price

    @staticmethod
    def _stop_reached(item: Item, q: Quote) -> bool:
        if item.stop is None:
            return False
        return q.ask >= item.stop if item.side == "buy" else q.bid <= item.stop

    def _trail(self, item: Item, settings, q: Quote) -> str:
        """Move a trailing stop with the best price; a market order at the stop."""
        sell = item.side == "sell"
        now = q.bid if sell else q.ask
        best = item.best_price or now
        best = max(best, now) if sell else min(best, now)
        if item.trail_mode == PERCENT:
            distance = best * float(item.trail_value or 0) / 100.0
        else:
            distance = float(item.trail_value or 0) * float(item.atr or 0)
        if distance <= 0:
            raise Skip("The trail has no distance")
        stop = best - distance if sell else best + distance
        if (
            best != item.best_price
            or item.stop is None
            or abs(stop - item.stop) > 1e-12
        ):
            self._update(
                item, best_price=_d(best), stop_price=_d(round(stop, 8)), note=""
            )
            item.best_price, item.stop = best, stop
        if (now <= stop) if sell else (now >= stop):
            return self._fill_now(item, settings, q)
        return ""

    # ---- filling ----

    def _fill_now(self, item: Item, settings, q: Quote) -> str:
        """A market order for ``item``: the paper account fills it at the market; a
        live one is placed on the exchange and followed."""
        if not settings.is_live:
            paper = self._paper_for(item)
            self._check_paper_funds(paper, item, q.ask if item.side == "buy" else q.bid)
            from pt_exchange_abstraction import dollar_symbol

            result = paper.place_order(
                dollar_symbol(item.coin), item.side, item.quantity
            )
            return self._paper_result(item, paper, result)
        target = self.live_target(settings)
        from pt_exchange_abstraction import dollar_symbol

        result = self._send(
            [item],
            lambda: target.place_order(
                dollar_symbol(item.coin),
                item.side,
                item.quantity,
                client_order_id=self._client_id(item, "m"),
            ),
        )
        return self._placed(item, settings, result, follow_state="placed")

    def _send(self, items: List[Item], call: Callable[[], Any]) -> Any:
        """``call()``, an order sent to the exchange, with ``items`` marked
        "placing" while it is out. An error leaves them so: whether the exchange
        placed the order is not known, and it is never sent a second time."""
        for it in items:
            self._update(it, state="placing")
        try:
            return call()
        except Exception as exc:
            where = _exchange_name(items[0].exchange)
            raise Skip(
                f"Not known whether {where} placed this order "
                f"({type(exc).__name__}: {exc}): check it there"
            ) from exc

    def _paper_for(self, item: Item) -> Any:
        """The paper account; while its saved book cannot be read a market order is
        rejected (it would fill at a later price) and any other waits."""
        try:
            return self.paper_account()
        except RuntimeError as exc:
            if item.order_type == "market" and item.role in ("order", "entry"):
                raise _Refused(str(exc)) from None
            raise Skip(str(exc)) from None

    def _fill_at(self, item: Item, settings, q: Quote, price: float) -> str:
        """A limit reached: the paper account fills it at its own price (the maker
        rate); live, PowerTrader places a market order."""
        if settings.is_live:
            return self._fill_now(item, settings, q)
        paper = self._paper_for(item)
        self._check_paper_funds(paper, item, price)
        from pt_exchange_abstraction import dollar_symbol

        result = paper.fill_limit_order(
            dollar_symbol(item.coin), item.side, item.quantity, price
        )
        return self._paper_result(item, paper, result)

    def _check_paper_funds(self, paper, item: Item, price: float) -> None:
        balances = paper.get_balance()
        if item.side == "buy":
            fees = paper.trading_fees(item.coin)
            needed = item.quantity * price * (1 + max(fees.maker, fees.taker))
            cash = float(balances.get("USD", 0.0))
            if cash + 1e-9 < needed:
                raise _Refused(
                    f"The paper account has ${cash:,.2f}, less than the "
                    f"${needed:,.2f} this buy needs"
                )
        else:
            held = float(balances.get(item.coin, 0.0))
            if held + 1e-12 < item.quantity:
                raise _Refused(
                    f"The paper account holds {_plain(held)} {item.coin}, less than "
                    f"the {_plain(item.quantity)} this sell needs"
                )

    def _paper_result(self, item: Item, paper, result) -> str:
        status = str(result.status).lower()
        if status == "filled":
            pnl = None
            if item.side == "sell":
                for trade in reversed(paper.account.trade_history):
                    if trade.order_id == result.order_id:
                        pnl = float(trade.pnl) - float(result.fee or 0.0)
                        break
            closes = item.side == "sell" and item.coin not in paper.account.positions
            self._record_fill(
                item,
                qty=float(result.amount),
                price=float(result.price),
                fee=result.fee,
                result=result,
                realized=pnl,
                closes=closes,
            )
            return "filled"
        if result.reason == "PRICE_UNAVAILABLE":
            if item.order_type == "market":  # filled now or not at all
                raise _Refused(f"No live price for {item.coin}")
            raise Skip(f"No live price for {item.coin}: it waits")
        raise _Refused(result.reason or "The paper account refused the order")

    def _client_id(self, item: Item, suffix: str = "") -> str:
        text = item.client_id[:30]
        return f"{text}-{suffix}" if suffix else text

    def _place_native(self, item: Item, settings) -> str:
        """Place ``item`` as the exchange's own order (a market order too)."""
        target = self.live_target(settings)
        from pt_exchange_abstraction import OrderRequest, dollar_symbol

        symbol = dollar_symbol(item.coin)
        if item.order_type == "market":
            result = self._send(
                [item],
                lambda: target.place_order(
                    symbol,
                    item.side,
                    item.quantity,
                    client_order_id=self._client_id(item),
                ),
            )
            return self._placed(item, settings, result, follow_state="working")
        request = OrderRequest(
            kind=item.order_type,
            symbol=symbol,
            side=item.side,
            amount=item.quantity,
            price=item.price,
            stop_price=item.stop if item.order_type == "stop_limit" else None,
            trail_pct=item.trail_value if item.order_type == "trailing_stop" else None,
            client_order_id=self._client_id(item),
        )
        result = self._send([item], lambda: target.exchange.place_native_order(request))
        return self._placed(item, settings, result, follow_state="working")

    def _placed(self, item: Item, settings, result, follow_state: str) -> str:
        status = str(result.status).lower()
        if status == "preview":
            raise _Refused("Preview orders: nothing was placed")
        if status in ("rejected", "failed") or not result.order_id:
            raise _Refused(result.reason or "The exchange refused the order")
        self._update(
            item,
            status=OrderStatus.SUBMITTED,
            exchange_order_id=str(result.order_id),
            state=follow_state,
            note="",
        )
        item.exchange_order_id = str(result.order_id)
        item.state = follow_state
        return self._follow(item, settings)

    def _follow(self, item: Item, settings) -> str:
        """Read an exchange order's state; record its fill when it has filled."""
        if not item.exchange_order_id:
            raise Skip("Not placed on the exchange yet")
        target = self.live_target(settings)
        result = target.exchange.native_order_status(item.exchange_order_id)
        status = str(result.status).lower()
        if status == "filled":
            qty = float(result.amount or 0.0) or item.quantity
            price = float(result.price or 0.0)
            if not price and result.filled_value and qty:
                price = float(result.filled_value) / qty
            self._record_fill(item, qty=qty, price=price, fee=result.fee, result=result)
            return "filled"
        if status in _ENDED:
            self._end(
                item, _ENDED[status], result.reason or f"The exchange says {status}"
            )
            return status
        if status == "partially_filled" and item.status != "partial":
            self._update(item, status=OrderStatus.PARTIAL)
        return ""

    # ---- groups ----

    def _oco(self, group: Item, settings, quotes) -> str:
        """An OCO order: its take-profit and stop; when one fills the other is
        cancelled and the group is filled."""
        tp, sl = group.leg("take_profit"), group.leg("stop")
        if tp is None or sl is None:
            raise Skip("An OCO order needs its take-profit and stop")
        return self._exits(group, tp, sl, settings, quotes)

    def _exits(self, group: Item, tp: Item, sl: Item, settings, quotes) -> str:
        for x in (group, tp, sl):
            _not_in_doubt(x)
        if tp.handling == BY_EXCHANGE:
            if tp.state in ("new", "waiting"):
                return self._place_oco(group, tp, sl, settings)
            return self._follow_oco(group, tp, sl, settings)
        if group.state == "new":
            self._update(group, status=OrderStatus.SUBMITTED, state="working")
            group.state = "working"
        for leg in (tp, sl):
            if leg.state in ("new", "waiting"):
                self._update(leg, status=OrderStatus.SUBMITTED, state="working")
                leg.state = "working"
        pairs = ((sl, tp), (tp, sl))
        sent = [p for p in pairs if p[0].state == "placed"]
        for leg, other in sent or pairs:  # a market order sent: only it is followed
            if not leg.is_open:
                continue
            outcome = self._single(leg, settings, quotes)
            if outcome == "filled" or leg.status == "filled":
                self._close_group(group, leg, other, settings)
                return "filled"
            if leg.status in ("cancelled", "rejected", "expired"):
                self._end_group(group, OrderStatus.REJECTED, leg.note)
                return leg.status
            if leg.state == "placed":
                return ""  # its market order is out: the other waits for it
        return ""

    def _place_oco(self, group, tp, sl, settings) -> str:
        from pt_exchange_abstraction import OCO_ORDER, OrderRequest, dollar_symbol

        target = self.live_target(settings)
        request = OrderRequest(
            kind=OCO_ORDER,
            symbol=dollar_symbol(tp.coin),
            side=tp.side,
            amount=tp.quantity,
            price=tp.price,
            stop_price=sl.stop,
            client_order_id=self._client_id(
                group, "x" if group.kind == BRACKET else ""
            ),
        )
        result = self._send(
            [group, tp, sl], lambda: target.exchange.place_native_order(request)
        )
        status = str(result.status).lower()
        if status in ("rejected", "failed") or not result.order_id:
            raise _Refused(result.reason or "The exchange refused the order")
        self._update(
            group,
            status=OrderStatus.SUBMITTED,
            exchange_order_id=str(result.order_id),
            state="working",
            note="",
        )
        group.exchange_order_id = str(result.order_id)
        for role, leg in (("take_profit", tp), ("stop", sl)):
            self._update(
                leg,
                status=OrderStatus.SUBMITTED,
                exchange_order_id=str(result.legs.get(role, "")) or None,
                state="working",
                note="",
            )
            leg.exchange_order_id = str(result.legs.get(role, ""))
            leg.state = "working"
        return "placed"

    def _follow_oco(self, group, tp, sl, settings) -> str:
        """An exchange's OCO order: each of its orders when the exchange gives them
        apart; else the one order, whose fill price says which side filled."""
        target = self.live_target(settings)
        if tp.exchange_order_id and sl.exchange_order_id:
            results = {
                leg.role: target.exchange.native_order_status(leg.exchange_order_id)
                for leg in (tp, sl)
            }
            for leg, other in ((tp, sl), (sl, tp)):
                result = results[leg.role]
                if str(result.status).lower() == "filled":
                    self._native_fill(leg, result)
                    self._close_group(group, leg, other, settings, exchange_done=True)
                    return "filled"
            ended = [str(results[leg.role].status).lower() for leg in (tp, sl)]
            if all(s in _ENDED for s in ended):
                self._end_group(group, _ENDED[ended[0]], "The exchange ended the order")
                return ended[0]
            return ""
        if not group.exchange_order_id:
            raise Skip("Not placed on the exchange yet")
        result = target.exchange.native_order_status(group.exchange_order_id)
        status = str(result.status).lower()
        if status == "filled":
            price = float(result.price or 0.0)
            leg = tp
            if price and tp.price and sl.stop:
                leg = tp if abs(price - tp.price) <= abs(price - sl.stop) else sl
            other = sl if leg is tp else tp
            self._native_fill(leg, result)
            self._close_group(group, leg, other, settings, exchange_done=True)
            return "filled"
        if status in _ENDED:
            self._end_group(
                group, _ENDED[status], result.reason or "The exchange ended it"
            )
            return status
        return ""

    def _native_fill(self, leg: Item, result) -> None:
        qty = float(result.amount or 0.0) or leg.quantity
        price = float(result.price or 0.0)
        if not price and result.filled_value and qty:
            price = float(result.filled_value) / qty
        self._record_fill(leg, qty=qty, price=price, fee=result.fee, result=result)

    def _close_group(self, group, filled_leg, other, settings, exchange_done=False):
        """One exit filled: the other is cancelled (on the exchange too, when it
        holds it on its own) and the group is filled."""
        if other.is_open:
            if (
                not exchange_done
                and other.handling == BY_EXCHANGE
                and other.exchange_order_id
            ):
                try:
                    self.live_target(settings).exchange.cancel_native_order(
                        other.exchange_order_id
                    )
                except Exception:
                    pass  # the exchange's own OCO cancels it
            self._end(
                other, OrderStatus.CANCELLED, "The other side filled", notify=False
            )
        self._update(group, status=OrderStatus.FILLED, state="done", note="")
        with self.db.get_session() as s:
            order = s.query(Order).filter(Order.id == group.id).one()
            order.filled_quantity = _d(filled_leg.quantity)
            order.filled_at = _utcnow()

    def _bracket(self, group: Item, settings, quotes) -> str:
        """A Bracket order: its entry first; once it fills, its exits as an OCO."""
        entry = group.leg("entry")
        tp, sl = group.leg("take_profit"), group.leg("stop")
        if entry is None or tp is None or sl is None:
            raise Skip("A Bracket order needs its entry, take-profit and stop")
        if group.state == "new":
            self._update(group, status=OrderStatus.SUBMITTED, state="working")
            group.state = "working"
        if entry.is_open:
            try:
                outcome = self._single(entry, settings, quotes)
            except _Refused as why:
                self._end_group(group, OrderStatus.REJECTED, f"The entry: {why}")
                return "rejected"
            if outcome != "filled" and entry.status != "filled":
                if entry.status in ("cancelled", "rejected", "expired"):
                    self._end_group(group, OrderStatus.CANCELLED, "The entry ended")
                return outcome
        if entry.status != "filled":
            self._end_group(group, OrderStatus.CANCELLED, "The entry did not fill")
            return "cancelled"
        if tp.state == "waiting" and 0 < entry.filled < tp.quantity:
            for leg in (tp, sl):  # the exits sell what the entry bought
                self._update(leg, quantity=_d(entry.filled))
                leg.quantity = entry.filled
        if tp.state == "waiting" and tp.handling != BY_EXCHANGE:
            for leg in (tp, sl):
                self._update(
                    leg, status=OrderStatus.SUBMITTED, state="working", note=""
                )
                leg.state = "working"
        return self._exits(group, tp, sl, settings, quotes)

    # ---- recording a fill ----

    def _record_fill(
        self,
        item: Item,
        *,
        qty: float,
        price: float,
        fee: Optional[float],
        result: Any,
        realized: Optional[float] = None,
        closes: bool = False,
    ) -> None:
        """The fill on the order, its notification and its trade history row."""
        settings = self.settings()
        value = float(getattr(result, "filled_value", None) or qty * price)
        detail = self._fee_detail(item, result, value)
        if fee is None and detail.get("fee_rate") is not None:
            fee = value * float(detail["fee_rate"])
        exchange = (
            getattr(result, "price_exchange", "")
            or getattr(result, "fee_exchange", "")
            or item.exchange
        )
        with self.db.get_session() as s:
            order = s.query(Order).filter(Order.id == item.id).one()
            m = s.query(ManagedOrder).filter(ManagedOrder.order_id == item.id).one()
            s.add(
                OrderExecution(
                    order_id=order.id,
                    quantity=_d(qty),
                    price=_d(price),
                    commission=_d(fee or 0.0),
                    exchange_execution_id=str(getattr(result, "order_id", "") or "")
                    or None,
                    exchange_name=exchange or None,
                )
            )
            order.filled_quantity = _d(qty)
            order.average_fill_price = _d(price)
            order.commission = _d(fee or 0.0)
            order.total_cost = _d(value + (fee or 0.0))
            order.status = OrderStatus.FILLED
            order.filled_at = _utcnow()
            m.state = "done"
            m.note = None
            verb = "Bought" if item.side == "buy" else "Sold"
            fee_text = f", fee ${float(fee):,.2f}" if fee is not None else ""
            create_notification(
                s,
                order.id,
                NotificationType.ORDER_FILLED,
                f"Order Filled: {item.side.upper()} {item.pair or item.coin}",
                f"{verb} {_plain(qty)} {item.pair or item.coin} at ${_plain(price)}"
                + fee_text,
            )
        item.status = "filled"
        item.state = "done"
        item.filled = float(qty)
        self._append_trade(
            item,
            settings,
            qty=qty,
            price=price,
            fee=fee,
            detail=detail,
            result=result,
            realized=realized,
            closes=closes,
        )

    def _fee_detail(self, item: Item, result, value: float) -> dict:
        """How the fill's fee was worked out: the exchange's own figures when it
        gives them (the paper account does), else its rate from ``trading_fees()``."""
        detail = {
            "fee_currency": getattr(result, "fee_currency", "") or "",
            "fee_rate": getattr(result, "fee_rate", None),
            "fee_type": getattr(result, "fee_type", "") or "",
            "fee_exchange": getattr(result, "fee_exchange", "") or "",
            "fee_source": getattr(result, "fee_source", "") or "",
        }
        if detail["fee_rate"] is None and getattr(result, "fee", None) is None:
            fees = self._live_fees(item)
            if fees is not None:
                maker = item.order_type == "limit" and item.handling == BY_EXCHANGE
                kind, rate = fees.for_order("limit" if maker else "market")
                detail.update(
                    fee_rate=rate,
                    fee_type=kind,
                    fee_exchange=fees.exchange,
                    fee_source=fees.source,
                    fee_currency=detail["fee_currency"] or "USD",
                )
        elif getattr(result, "fee", None) is not None and value:
            detail["fee_rate"] = detail["fee_rate"] or float(result.fee) / value
            detail["fee_exchange"] = detail["fee_exchange"] or item.exchange
            detail["fee_source"] = detail["fee_source"] or "exchange"
        return {
            k: v
            for k, v in detail.items()
            if isinstance(v, (str, int, float)) and v != ""
        }

    def _live_fees(self, item: Item):
        from pt_exchange_abstraction import dollar_symbol, usable_fees

        try:
            settings = self.settings()
            exchange = self.live_target(settings).exchange
            return usable_fees(exchange.trading_fees(dollar_symbol(item.coin)))
        except Exception:
            return None

    def _append_trade(
        self, item, settings, *, qty, price, fee, detail, result, realized, closes
    ) -> None:
        """One row in the account's trade history, as the trader writes them."""
        from pt_exchange_abstraction import dollar_symbol

        entry = {
            "ts": self._clock(),
            "side": item.side,
            "tag": TAG,
            "symbol": dollar_symbol(item.coin),
            "qty": float(qty),
            "price": float(price),
            "avg_cost_basis": None,
            "pnl_pct": None,
            "fees_usd": float(fee) if fee is not None else None,
            "realized_profit_usd": realized,
            "order_id": str(getattr(result, "order_id", "") or item.client_id),
            "buying_power_before": None,
            "buying_power_after": None,
            "buying_power_delta": None,
            "position_cost_used_usd": None,
            "position_cost_after_usd": None,
            "order_management_id": str(item.id),
        }
        entry.update(detail)
        if not settings.is_live:
            entry["price_source"] = getattr(result, "price_source", "") or "unknown"
            entry["quote_ts"] = getattr(result, "quote_ts", None)
            entry["age_s"] = getattr(result, "age_s", None)
            entry["price_exchange"] = getattr(result, "price_exchange", "") or ""
        if item.side == "sell":
            entry["closes_position"] = bool(closes)
        path = os.path.join(self.books_dir(item.books), "trade_history.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # ---- cancel and modify ----

    def cancel(self, order_id) -> Tuple[bool, str]:
        """Cancel the order and, for an OCO or Bracket order (or one of its legs),
        all of its legs: on the exchange first, where the exchange holds them.
        (cancelled, why not)."""
        item = self.item(order_id)
        if item is None:
            ok = bool(self.db.cancel_order(order_id))
            return ok, "" if ok else "No such order"
        if not item.is_open and not any(l.is_open for l in item.legs):
            return False, "It is not open"
        settings = self.settings()
        problems = []
        held = [
            x
            for x in [item] + item.legs
            if x.is_open and x.exchange_order_id and x.state != "done"
        ]
        # an OCO list is cancelled by its id: its legs go with it
        list_id = item.exchange_order_id if item.role == "group" else ""
        for x in held:
            if list_id and x is not item and x.role in ("take_profit", "stop"):
                continue
            if item.account != settings.key:
                problems.append(
                    "it is on another account than the one trading now: cancel it "
                    f"on {_exchange_name(item.exchange)}"
                )
                break
            try:
                done = self.live_target(settings).exchange.cancel_native_order(
                    x.exchange_order_id
                )
            except Exception as exc:
                done, why = False, f"{type(exc).__name__}: {exc}"
            else:
                why = "" if done else "the exchange did not cancel it"
            if not done:
                problems.append(why)
        if problems:
            # it may have filled meanwhile: the monitor records what the exchange says
            return False, "; ".join(problems)
        ok = bool(self.db.cancel_order(item.id))
        with self.db.get_session() as s:
            ids = [item.id] + [l.id for l in item.legs]
            for m in s.query(ManagedOrder).filter(ManagedOrder.order_id.in_(ids)):
                m.state = "done"
        return ok, "" if ok else "It is not open"

    def modify(
        self,
        order_id,
        *,
        quantity: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        trail_value: Optional[Decimal] = None,
    ) -> str:
        """Change an open order's quantity or prices ("" when changed, else why
        not). An order PowerTrader manages changes in place; one the exchange holds
        is cancelled there and placed again with the new values. Nothing of an
        order that has started to fill changes, and a Bracket's quantity stays once
        its entry has filled."""
        item = self.item(order_id)
        if item is None:
            return "No such order"
        if not item.is_open:
            return "Only an open order can be changed"
        if item.filled > 0 or item.status == "partial":
            return "The order has started to fill"
        if item.kind == MARKET:
            return "A market order fills when it is sent: it cannot be changed"
        settings = self.settings()
        refused = (
            self.refusal(settings)
            if item.account == settings.key
            else ("It is on another account than the one trading now")
        )
        if refused:
            return refused
        spec = self.spec_of(item)
        entry = item.leg("entry")
        entered = entry is not None and entry.status == "filled"
        if entered and quantity is not None and float(quantity) != item.quantity:
            return "The entry has filled: its quantity cannot change"
        changes = dict(
            quantity=quantity if quantity is not None else spec.quantity,
            price=price if price is not None else spec.price,
            stop_price=stop_price if stop_price is not None else spec.stop_price,
            take_profit=take_profit if take_profit is not None else spec.take_profit,
            trail_value=trail_value if trail_value is not None else spec.trail_value,
        )
        new = OrderSpec(**{**spec.__dict__, **changes})
        if entered:
            new = OrderSpec(**{**new.__dict__, "price": None})  # checked on the exits
        try:
            q = self.quote(settings, item.coin)
            bid, ask = q.bid, q.ask
        except Exception:
            bid = ask = None  # checked against the market when there is a price
        working = item.kind == STOP_LIMIT and item.state == "triggered"
        problem = problem_with(new, None if working else bid, None if working else ask)
        if problem:
            return problem
        on_exchange = [
            x
            for x in [item] + item.legs
            if x.is_open and x.exchange_order_id and x.handling == BY_EXCHANGE
        ]
        if on_exchange:
            ok, why = self._cancel_on_exchange(item, settings)
            if not ok:
                return f"Not changed: {why}"
        self._apply(item, new, resend=bool(on_exchange))
        return ""

    def _cancel_on_exchange(self, item: Item, settings) -> Tuple[bool, str]:
        exchange = self.live_target(settings).exchange
        list_id = item.exchange_order_id if item.role == "group" else ""
        targets = (
            [list_id]
            if list_id
            else [
                x.exchange_order_id
                for x in [item] + item.legs
                if x.is_open and x.exchange_order_id
            ]
        )
        for oid in targets:
            try:
                if not exchange.cancel_native_order(oid):
                    return False, "the exchange did not cancel it (it may have filled)"
            except Exception as exc:
                return False, f"{type(exc).__name__}: {exc}"
        return True, ""

    def _apply(self, item: Item, new: OrderSpec, resend: bool) -> None:
        """Write ``new``'s values to the order and its legs; an order cancelled on
        the exchange is sent again (state "new")."""
        qty = new.quantity
        with self.db.get_session() as s:
            ids = [item.id] + [l.id for l in item.legs]
            orders = {o.id: o for o in s.query(Order).filter(Order.id.in_(ids))}
            managed = {
                m.order_id: m
                for m in s.query(ManagedOrder).filter(ManagedOrder.order_id.in_(ids))
            }
            for x in [item] + item.legs:
                o, m = orders[x.id], managed[x.id]
                if o.status in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                    continue
                o.quantity = qty
                limited = x.order_type in ("limit", "stop_limit")
                if x.role in ("order", "entry") and limited and new.price:
                    o.price = new.price
                if x.role == "order" and x.order_type == "stop_limit":
                    o.stop_price = new.stop_price
                if x.role == "take_profit":
                    o.price = new.take_profit
                if x.role == "stop":
                    o.stop_price = new.stop_price
                if x.role == "group":
                    if x.kind == OCO:
                        o.price = new.take_profit
                    elif new.price:
                        o.price = new.price
                    o.stop_price = new.stop_price
                if x.order_type == "trailing_stop":
                    m.trail_value = new.trail_value
                    m.best_price = None  # it trails again from the price now
                    o.stop_price = None
                if resend and (o.exchange_order_id or x.role == "group"):
                    # cancelled on the exchange: sent again by the monitor
                    o.exchange_order_id = None
                    exits = x.kind == BRACKET and x.role in ("take_profit", "stop")
                    m.state = "waiting" if exits else "new"
                    o.status = OrderStatus.PENDING
                m.note = "Changed"
                m.updated_at = _utcnow()
                o.updated_at = _utcnow()
            create_notification(
                s,
                item.id,
                NotificationType.ORDER_FILLED,
                f"Order Changed: {item.side.upper()} {item.pair or item.coin}",
                f"{self.describe(item)}: now {_plain(qty)}",
            )

    def spec_of(self, item: Item) -> OrderSpec:
        """The OrderSpec an order was made from (its current values)."""
        tp = item.leg("take_profit")
        sl = item.leg("stop")
        entry = item.leg("entry")
        if item.kind == OCO:
            price, stop, take = (
                None,
                sl.stop if sl else item.stop,
                tp.price if tp else item.price,
            )
        elif item.kind == BRACKET:
            price = entry.price if entry else item.price
            stop = sl.stop if sl else item.stop
            take = tp.price if tp else None
        else:
            price, stop, take = item.price, item.stop, None
        return OrderSpec(
            kind=item.kind,
            coin=item.coin,
            side=item.side,
            quantity=Decimal(str(item.quantity)),
            exchange=item.exchange,
            pair=item.pair,
            price=_d(price),
            stop_price=_d(stop) if item.kind != TRAILING_STOP else None,
            take_profit=_d(take),
            trail_mode=item.trail_mode,
            trail_value=_d(item.trail_value),
            atr=item.atr,
        )


class _Refused(Skip):
    """The order cannot be carried out at all (not enough cash, refused by the
    exchange): it is rejected, with this reason."""


def _not_in_doubt(item: Item) -> None:
    """An order being sent when the app stopped, or whose sending failed, is not
    sent again: whether the exchange has it is not known (Skip)."""
    if item.state == "placing" and not item.exchange_order_id:
        where = _exchange_name(item.exchange)
        raise Skip(f"Not known whether {where} placed this order: check it there")


def _exchange_name(exchange: str) -> str:
    from pt_exchange_abstraction import exchange_name

    return exchange_name(exchange) or "the exchange"


def candle_atr(
    coin: str, exchange: str = "", now: Optional[float] = None
) -> Optional[float]:
    """``coin``'s ATR(ATR_LENGTH) of closed ATR_TF candles from the exchange layer
    (``exchange`` first when given, then the others, primary first): the indicator
    the strategies' ATR stop uses (strategies.indicators.atr). None when there are
    too few candles."""
    import math

    import pandas as pd
    from market_data.candles import exchange_candles
    from market_data.timeframes import candle_timeframe_seconds
    from strategies.indicators import atr

    now = time.time() if now is None else float(now)
    step = candle_timeframe_seconds(ATR_TF)
    start = pd.Timestamp(now - step * (ATR_HISTORY_BARS + 2), unit="s", tz="UTC")
    end = pd.Timestamp(now, unit="s", tz="UTC")
    names = None
    if exchange:
        from pt_multi_exchange import market_exchanges

        others = market_exchanges().exchange_manager.exchange_names()
        names = [exchange] + [n for n in others if n != exchange]
    bars = exchange_candles(coin, ATR_TF, start, end, exchanges=names)
    if len(bars) < ATR_LENGTH + 1:
        return None
    value = float(atr(bars["high"], bars["low"], bars["close"], ATR_LENGTH).iloc[-1])
    return None if math.isnan(value) or value <= 0 else value
