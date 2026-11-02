"""
Trading-mode gate (issue #96).

Every order PowerTrader places must pass through ``resolve_order_target``.
It is the single chokepoint that decides where an order may go:

* ``trading.mode`` is anything other than ``"live"``  -> the paper account.
  A live venue is never touched and no credentials are needed.
* ``trading.mode == "live"`` and no active broker      -> refused
  (``LiveTradingRefused``); nothing is sent anywhere.
* ``trading.mode == "live"`` and a broker is set       -> a live exchange built
  with ``ExchangeFactory.get_exchange(ExchangeType(active_broker))``.

The gate fails closed: a missing, unreadable or malformed settings file, or a
mode value it does not recognise, resolves to paper - never to live.

``PaperExchange`` adapts ``PaperTradingAccount`` to the ``AbstractExchange``
call shape so the trader talks to one interface whichever target it gets.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple

from pt_exchange_abstraction import (
    AbstractExchange,
    ConnectionStatus,
    ExchangeFactory,
    ExchangeType,
    MarketData,
    OrderResult,
)
from pt_paper_trading import (
    MarketDataSimulator,
    OrderSide,
    OrderType,
    PaperTradingAccount,
    Position,
)
from pt_logging import get_logger
from pt_settings_manager import (
    DEFAULT_EMERGENCY_DRAWDOWN_PCT,
    DEFAULT_MAX_QUOTE_AGE_S,
    DEFAULT_PRICE_FALLBACK_POLICY,
    EMERGENCY_DRAWDOWN_KEY,
    EMERGENCY_DRAWDOWN_RANGE,
    MAX_QUOTE_AGE_RANGE,
    PAPER_MAX_QUOTE_AGE_KEY,
    PAPER_POLICY_KEY,
    PRICE_FALLBACK_POLICIES,
    SETTINGS_FILE,
    TRADING_ACTIVE_BROKER_KEY,
    TRADING_MODE_KEY,
    trading_preview_key,
    trading_testnet_key,
)

logger = get_logger("trading_mode")

PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"

# Brokers whose exchange class accepts a ``testnet`` constructor flag. The
# ``trading.<broker>_testnet`` setting is only forwarded to these.
TESTNET_BROKERS = frozenset({ExchangeType.BINANCE.value})

# Each live broker's books are in <hub>/live/<broker>/ (TradingSettings.data_subdir)
LIVE_DATA_SUBDIR = "live"
# The trader's books for one mode: the files the one-time move takes out of the hub
# folder, where every live broker shared them before
LIVE_BOOK_FILES = (
    "trade_history.jsonl",
    "pnl_ledger.json",
    "account_value_history.jsonl",
    "trader_status.json",
    "strategy_state.json",
)
# Written in live/<broker>/ while that move runs; lists the files still to move
LIVE_BOOKS_MOVE_MARKER = "moving_live_books.json"

PAPER_BALANCE_ASSET = "USD"


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class TradingModeError(RuntimeError):
    """An order was blocked by the trading-mode gate."""


class LiveTradingRefused(TradingModeError):
    """Live mode is selected but cannot be used (no/invalid broker, broker build failed)."""


# --- Settings ----------------------------------------------------------------


def default_settings_path() -> str:
    """``pt_config.json`` in the user config folder (see pt_paths)."""
    import pt_paths

    return os.path.join(pt_paths.config_dir(), SETTINGS_FILE)


def _lookup(settings: Any, dotted_key: str, default: Any = None) -> Any:
    """Read ``trading.mode``-style keys from a nested dict, a flat dict keyed by
    the dotted name, or any object with a ``get(key, default)`` (SettingsManager)."""
    if settings is None:
        return default
    if isinstance(settings, Mapping):
        if dotted_key in settings:
            return settings[dotted_key]
        current: Any = settings
        for part in dotted_key.split("."):
            if isinstance(current, Mapping) and part in current:
                current = current[part]
            else:
                return default
        return current
    getter = getattr(settings, "get", None)
    if callable(getter):
        try:
            return getter(dotted_key, default)
        except Exception:
            return default
    return default


def _read_settings_file(path: str) -> Dict[str, Any]:
    """Raw read of the settings file. Any problem yields {} (=> paper)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "on"):
            return True
        if v in ("false", "0", "no", "off"):
            return False
    return default


def _valid_broker(raw: Any) -> Optional[str]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return ExchangeType(raw.strip().lower()).value
    except ValueError:
        return None


@dataclass(frozen=True)
class TradingSettings:
    mode: TradingMode
    active_broker: Optional[str]  # validated ExchangeType value, or None
    testnet: bool
    # "Preview orders only": the broker can preview orders and the setting is on
    # (read_trading_settings resolves both); a testnet run is never a preview
    preview: bool = False

    @property
    def is_live(self) -> bool:
        return self.mode is TradingMode.LIVE

    @property
    def uses_testnet(self) -> bool:
        return self.is_live and self.active_broker in TESTNET_BROKERS and self.testnet

    @property
    def uses_preview(self) -> bool:
        """Live orders are previewed by the broker and nothing is placed."""
        return (
            self.is_live
            and self.active_broker is not None
            and not self.uses_testnet
            and self.preview
        )

    @property
    def label(self) -> str:
        """Text for the always-visible hub indicator."""
        if not self.is_live:
            return "MODE: PAPER"
        if self.active_broker is None:
            return "MODE: LIVE — NO BROKER (orders blocked)"
        suffix = (
            " (testnet)"
            if self.uses_testnet
            else " (preview orders)" if self.uses_preview else ""
        )
        return f"MODE: LIVE — {self.active_broker}{suffix}"

    @property
    def key(self) -> str:
        """Stable identity of where orders would go; used to detect mode changes."""
        if not self.is_live:
            return "paper"
        if self.active_broker is None:
            return "live:blocked"
        suffix = (
            ":testnet" if self.uses_testnet else ":preview" if self.uses_preview else ""
        )
        return f"live:{self.active_broker}{suffix}"

    @property
    def data_subdir(self) -> str:
        """Sub-directory of the hub data dir holding this mode's ledger/history, so
        paper, testnet and preview runs never mix into the live books, and one live
        broker's order ids are never looked up on another: ``live/<broker>``."""
        if self.is_live and self.active_broker is not None:
            if self.uses_testnet:
                return "testnet"
            live = os.path.join(LIVE_DATA_SUBDIR, self.active_broker)
            return os.path.join(live, "preview") if self.uses_preview else live
        return "paper"


def read_trading_settings(settings: Any = None) -> TradingSettings:
    """
    Parse the trading section of ``settings``.

    ``settings`` may be None (read the settings file fresh from disk), a path to
    a settings file, a nested/flat dict, or a SettingsManager. Only the exact
    string "live" (case/whitespace-insensitive) selects live mode.
    """
    if settings is None:
        settings = _read_settings_file(default_settings_path())
    elif isinstance(settings, (str, os.PathLike)):
        settings = _read_settings_file(os.fspath(settings))

    raw_mode = _lookup(settings, TRADING_MODE_KEY)
    mode = (
        TradingMode.LIVE
        if isinstance(raw_mode, str) and raw_mode.strip().lower() == "live"
        else TradingMode.PAPER
    )
    broker = _valid_broker(_lookup(settings, TRADING_ACTIVE_BROKER_KEY))
    testnet = (
        _coerce_bool(_lookup(settings, trading_testnet_key(broker)), True)
        if broker
        else True
    )
    # defaults to on, like testnet: a broker that can preview starts by placing nothing
    preview = bool(broker) and broker_previews_orders(broker)
    if preview:
        preview = _coerce_bool(_lookup(settings, trading_preview_key(broker)), True)
    return TradingSettings(
        mode=mode, active_broker=broker, testnet=testnet, preview=preview
    )


# --- Paper price-integrity settings (FDS-096b) -------------------------------


@dataclass(frozen=True)
class PaperSettings:
    price_fallback_policy: str  # "pause" | "simulate_and_flag"
    max_quote_age_s: float


def _in_range(value: Any, bounds: Tuple[float, float]) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value
        and bounds[0] <= value <= bounds[1]
    )


def _settings_mapping(settings: Any) -> Any:
    if settings is None:
        return _read_settings_file(default_settings_path())
    if isinstance(settings, (str, os.PathLike)):
        return _read_settings_file(os.fspath(settings))
    return settings


# Public names for other modules that read the same settings source.
lookup_setting = _lookup
settings_mapping = _settings_mapping


def read_paper_settings(settings: Any = None) -> PaperSettings:
    """Fail closed: an unknown policy is "pause"; a bad max age is the default."""
    settings = _settings_mapping(settings)
    policy = _lookup(settings, PAPER_POLICY_KEY)
    if policy not in PRICE_FALLBACK_POLICIES:
        if policy is not None:
            logger.warning(
                f"Invalid {PAPER_POLICY_KEY}={policy!r}; using "
                f"'{DEFAULT_PRICE_FALLBACK_POLICY}'"
            )
        policy = DEFAULT_PRICE_FALLBACK_POLICY
    max_age = _lookup(settings, PAPER_MAX_QUOTE_AGE_KEY)
    if not _in_range(max_age, MAX_QUOTE_AGE_RANGE):
        if max_age is not None:
            logger.warning(
                f"Invalid {PAPER_MAX_QUOTE_AGE_KEY}={max_age!r}; using "
                f"{DEFAULT_MAX_QUOTE_AGE_S}"
            )
        max_age = DEFAULT_MAX_QUOTE_AGE_S
    return PaperSettings(price_fallback_policy=policy, max_quote_age_s=float(max_age))


def read_emergency_drawdown_pct(settings: Any = None) -> float:
    """``risk.emergency_drawdown_pct`` (1-50); anything invalid is 8.0, logged."""
    value = _lookup(_settings_mapping(settings), EMERGENCY_DRAWDOWN_KEY)
    if _in_range(value, EMERGENCY_DRAWDOWN_RANGE):
        return float(value)
    if value is not None:
        logger.warning(
            f"Invalid {EMERGENCY_DRAWDOWN_KEY}={value!r} (valid "
            f"{EMERGENCY_DRAWDOWN_RANGE[0]:g}-{EMERGENCY_DRAWDOWN_RANGE[1]:g}); using "
            f"{DEFAULT_EMERGENCY_DRAWDOWN_PCT}"
        )
    return DEFAULT_EMERGENCY_DRAWDOWN_PCT


# --- Quotes with provenance --------------------------------------------------


@dataclass(frozen=True)
class Quote:
    """A raw bid/ask as received from a price feed."""

    bid: float
    ask: float
    quote_ts: Optional[float]  # exchange timestamp (epoch s, UTC); None if unknown
    fetched_ts: float  # local time the quote was fetched (epoch s, UTC)
    exchange: str = ""  # the exchange that gave it (e.g. "coinbase"); "" if unknown
    pair: str = ""  # that exchange's market (e.g. "BTC-USD")

    @property
    def age_s(self) -> Optional[float]:
        return None if self.quote_ts is None else self.fetched_ts - self.quote_ts


@dataclass(frozen=True)
class PricedQuote:
    """A quote plus where it came from: live | stale | simulated."""

    bid: float
    ask: float
    price_source: str
    quote_ts: Optional[float]
    fetched_ts: float
    age_s: Optional[float]
    exchange: str = ""  # the exchange whose quote it is; "" when simulated


class PriceUnavailable(RuntimeError):
    """No live price and the policy is ``pause``."""

    reason = PRICE_UNAVAILABLE


def classify_quote(quote: Optional[Quote], max_age_s: float, now: float) -> str:
    """ "live" if fresh; "stale" if older than ``max_age_s`` (or its age is
    unknown, which is treated as stale); "simulated" if there is no quote."""
    if quote is None:
        return "simulated"
    age = quote.age_s
    if age is None or age > max_age_s or (now - quote.fetched_ts) > max_age_s:
        return "stale"
    return "live"


# --- Public quote feed (paper pricing only; never an order call) -------------

_QUOTE_TTL_SECONDS = 2.0
_quote_cache: Dict[str, Quote] = {}


def _layer_quote(base: str):
    """The exchange layer's best bid and ask for ``base``: a ``Sourced``
    ``PriceQuote`` from the exchanges in Settings, primary first, or None."""
    from pt_multi_exchange import market_exchanges

    return market_exchanges().quote(base)


def fetch_public_quote(base: str) -> Optional[Quote]:
    """
    The best bid and ask for ``base`` from the exchanges in Settings: the primary
    exchange first, then the other enabled exchanges (FDS-MX-001 phase B). None when
    no exchange gives one. Public market data only: no credentials.

    ``quote_ts`` is the exchange's own time for the quote (its timestamp, or the
    Date of its answer); a quote without one is treated as stale. ``exchange`` and
    ``pair`` say which exchange and market gave it. A quote is reused for 2 s.
    """
    now = time.time()
    cached = _quote_cache.get(base)
    if cached and now - cached.fetched_ts < _QUOTE_TTL_SECONDS:
        return cached
    try:
        answer = _layer_quote(base)
    except Exception as exc:
        logger.debug(f"No quote for {base} from the exchange layer: {exc}")
        return None
    if answer is None:
        return None
    quote = Quote(
        bid=float(answer.value.bid),
        ask=float(answer.value.ask),
        quote_ts=answer.value.quote_ts,
        fetched_ts=time.time(),
        exchange=answer.exchange,
        pair=answer.pair,
    )
    _quote_cache[base] = quote
    return quote


# --- Paper adapter -----------------------------------------------------------


class _AnchoredSimulator(MarketDataSimulator):
    """Fills at the quote the adapter last anchored; random walk only when offline."""

    def __init__(self) -> None:
        super().__init__()
        self.anchors: Dict[str, Decimal] = {}

    def get_current_price(self, symbol: str) -> Decimal:
        price = self.anchors.get(symbol)
        if price is None:
            return super().get_current_price(symbol)
        self.current_prices[symbol] = price
        self._record_price_history(symbol, price)
        return price


def _base_asset(symbol: str) -> str:
    return str(symbol).upper().strip().split("-")[0].split("/")[0]


class PaperExchange(AbstractExchange):
    """``PaperTradingAccount`` behind the ``AbstractExchange`` interface.

    Needs no credentials. ``price_feed(base) -> Quote | None`` supplies real
    prices. Every price used is classified ``live`` / ``stale`` / ``simulated``
    (see ``classify_quote``) and, per ``paper.price_fallback_policy``:

    * ``pause`` (default): a market order on a stale/simulated price is
      rejected with reason ``PRICE_UNAVAILABLE`` and price reads raise
      ``PriceUnavailable`` - nothing is faked.
    * ``simulate_and_flag``: the order fills (at the stale quote, or at the
      account's own simulator price when there is no quote), and the fill is
      marked with its ``price_source`` and logged at WARNING.

    ``settings_source`` is where the policy and max quote age are read from
    (None = the settings file, re-read on every use).
    """

    # Offline fallback spread around the simulator price.
    _SIM_HALF_SPREAD = 0.0005

    def __init__(
        self,
        account: Optional[PaperTradingAccount] = None,
        initial_balance: Decimal = Decimal("10000"),
        price_feed: Optional[Callable[[str], Optional[Quote]]] = None,
        state_path: Optional[str] = None,
        settings_source: Any = None,
        clock: Callable[[], float] = time.time,
        **kwargs: Any,
    ) -> None:
        super().__init__("", "", **kwargs)
        self.account = account or PaperTradingAccount(initial_balance=initial_balance)
        self._simulator = _AnchoredSimulator()
        self.account.market_simulator = self._simulator
        self._price_feed = price_feed
        self._state_path = state_path
        self.settings_source = settings_source
        self._clock = clock
        self._lock = threading.RLock()
        self._rejections: Dict[str, OrderResult] = {}
        self.last_quotes: Dict[str, PricedQuote] = {}
        # False when there is no saved book or it could not be read
        self.state_loaded = bool(state_path) and self.load_state(state_path)

    def get_exchange_name(self) -> str:
        return "paper"

    def is_available_in_region(self, region: str) -> bool:
        return True

    # -- quotes --

    def _priced_quote(self, base: str) -> PricedQuote:
        """The best available price for ``base`` with its provenance, per policy.
        Raises ``PriceUnavailable`` when it is not live and the policy is pause."""
        paper = read_paper_settings(self.settings_source)
        now = self._clock()
        quote = self._price_feed(base) if self._price_feed else None
        source = classify_quote(quote, paper.max_quote_age_s, now)

        if source == "live":
            priced = PricedQuote(
                quote.bid,
                quote.ask,
                "live",
                quote.quote_ts,
                quote.fetched_ts,
                quote.age_s,
                quote.exchange,
            )
        elif paper.price_fallback_policy != "simulate_and_flag":
            logger.warning(
                f"Paper price for {base} is {source} (policy=pause): "
                f"{PRICE_UNAVAILABLE}; no fill"
            )
            raise PriceUnavailable(f"{PRICE_UNAVAILABLE}: {base} price is {source}")
        elif source == "stale":
            logger.warning(
                f"Paper price for {base} is stale (age_s={quote.age_s}, max "
                f"{paper.max_quote_age_s:g}); filling on it and flagging (policy="
                "simulate_and_flag)"
            )
            priced = PricedQuote(
                quote.bid,
                quote.ask,
                "stale",
                quote.quote_ts,
                quote.fetched_ts,
                quote.age_s,
                quote.exchange,
            )
        else:
            mid = float(MarketDataSimulator.get_current_price(self._simulator, base))
            logger.warning(
                f"No live price for {base}; SIMULATED price {mid:.8g} (policy="
                "simulate_and_flag)"
            )
            priced = PricedQuote(
                mid * (1 - self._SIM_HALF_SPREAD),
                mid * (1 + self._SIM_HALF_SPREAD),
                "simulated",
                None,
                now,
                None,
            )
        self.last_quotes[base] = priced
        return priced

    def get_quote(self, symbol: str) -> PricedQuote:
        """Price with provenance for ``symbol`` (may raise ``PriceUnavailable``)."""
        return self._priced_quote(_base_asset(symbol))

    def get_current_price(self, symbol: str) -> float:
        return self.get_quote(symbol).ask

    def get_market_data(self, symbol: str) -> MarketData:
        priced = self.get_quote(symbol)
        return MarketData(
            symbol=symbol,
            price=(priced.bid + priced.ask) / 2,
            bid=priced.bid,
            ask=priced.ask,
            volume=0.0,
            timestamp=(
                priced.quote_ts if priced.quote_ts is not None else priced.fetched_ts
            ),
            exchange="paper",
        )

    # -- orders --

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        side_l = str(side).lower().strip()
        if side_l not in ("buy", "sell"):
            raise ValueError(f"Invalid order side: {side!r}")
        order_side = OrderSide.BUY if side_l == "buy" else OrderSide.SELL
        base = _base_asset(symbol)

        with self._lock:
            priced: Optional[PricedQuote] = None
            if price is None:
                # Market order: fill at the ask when buying, the bid when selling.
                try:
                    priced = self._priced_quote(base)
                except PriceUnavailable:
                    return self._reject(symbol, side_l, amount, PRICE_UNAVAILABLE)
                self._simulator.anchors[base] = Decimal(
                    str(priced.ask if order_side is OrderSide.BUY else priced.bid)
                )
                order_id = self.account.place_order(
                    symbol=base,
                    order_type=OrderType.MARKET,
                    side=order_side,
                    quantity=Decimal(str(amount)),
                )
            else:
                # Limit order: the price is the caller's, no feed involved.
                order_id = self.account.place_order(
                    symbol=base,
                    order_type=OrderType.LIMIT,
                    side=order_side,
                    quantity=Decimal(str(amount)),
                    price=Decimal(str(price)),
                )
            self._stamp_provenance(order_id, priced)
            self._save_state()
            return self._order_result(order_id)

    def _reject(
        self, symbol: str, side: str, amount: float, reason: str
    ) -> OrderResult:
        result = OrderResult(
            order_id=f"rejected-{uuid.uuid4().hex[:12]}",
            symbol=f"{_base_asset(symbol)}-USD",
            side=side,
            amount=0.0,
            price=0.0,
            status="rejected",
            exchange="paper",
            timestamp=time.time(),
            reason=reason,
            price_source="n/a",
        )
        self._rejections[result.order_id] = result
        return result

    def _stamp_provenance(self, order_id: str, priced: Optional[PricedQuote]) -> None:
        """Record where a fill's price came from on the order (and its trade)."""
        order = self.account.orders[order_id]
        if priced is None:
            order.price_source = "n/a"  # limit order: caller-supplied price
        else:
            order.price_source = priced.price_source
            order.quote_ts = priced.quote_ts
            order.age_s = priced.age_s
            order.price_exchange = priced.exchange
        for trade in reversed(self.account.trade_history):
            if trade.order_id == order_id:
                trade.price_source = order.price_source
                trade.quote_ts = order.quote_ts
                trade.age_s = order.age_s
                trade.price_exchange = order.price_exchange
                break

    def get_balance(self) -> Dict[str, float]:
        with self._lock:
            balances = {PAPER_BALANCE_ASSET: float(self.account.cash_balance)}
            for symbol, position in self.account.positions.items():
                if position.quantity > 0:
                    balances[symbol] = float(position.quantity)
            return balances

    def get_order_status(self, order_id: str) -> OrderResult:
        if order_id in self._rejections:
            return self._rejections[order_id]
        if order_id not in self.account.orders:
            raise LookupError(f"Unknown paper order id: {order_id}")
        return self._order_result(order_id)

    def cancel_order(self, order_id: str) -> bool:
        with self._lock:
            return bool(self.account.cancel_order(order_id))

    def _order_result(self, order_id: str) -> OrderResult:
        order = self.account.orders[order_id]
        return OrderResult(
            order_id=order_id,
            symbol=f"{order.symbol}-USD",
            side=order.side.value,
            amount=float(order.filled_quantity),
            price=float(order.filled_price or order.price),
            status=order.status.value,
            exchange="paper",
            timestamp=time.time(),
            price_source=order.price_source,
            quote_ts=order.quote_ts,
            age_s=order.age_s,
            price_exchange=order.price_exchange,
        )

    # -- persistence (so the paper book survives a trader restart) --

    def _save_state(self) -> None:
        if not self._state_path:
            return
        state = {
            "initial_balance": str(self.account.initial_balance),
            "cash_balance": str(self.account.cash_balance),
            "positions": {
                sym: {
                    "quantity": str(pos.quantity),
                    "average_price": str(pos.average_price),
                }
                for sym, pos in self.account.positions.items()
            },
        }
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            tmp = f"{self._state_path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, self._state_path)
        except OSError:
            pass

    def load_state(self, path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            cash = Decimal(state["cash_balance"])
            positions = {
                sym: Position(
                    symbol=sym,
                    quantity=Decimal(p["quantity"]),
                    average_price=Decimal(p["average_price"]),
                    current_price=Decimal(p["average_price"]),
                )
                for sym, p in (state.get("positions") or {}).items()
            }
            initial = Decimal(
                state.get("initial_balance", self.account.initial_balance)
            )
        except FileNotFoundError:
            return False
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            ArithmeticError,
        ) as exc:
            # A bad hand edit must not crash start-up; say so instead of silently
            # trading the default balance.
            logger.warning(
                "Paper account %s could not be read (%s); starting from the "
                "default balance. Fix it in Settings > Paper Account.",
                path,
                type(exc).__name__,
            )
            return False
        self.account.cash_balance = cash
        self.account.positions = positions
        self.account.initial_balance = initial
        return True


# -- the paper book on disk (the Settings window edits it; the trader loads it) --

PAPER_DATA_SUBDIR = "paper"  # TradingSettings.data_subdir in paper mode
PAPER_BOOK_FILE = "paper_account.json"
PAPER_LEDGER_FILE = "pnl_ledger.json"
DEFAULT_PAPER_BALANCE = Decimal("10000")
_PAPER_SYMBOL_RE = re.compile(r"^[A-Z]{2,10}$")  # the trader's holdings filter
_PAPER_CASH_SYMBOLS = frozenset({"USD", "ZUSD", "USDT", "USDC", "BUSD"})  # cash
_PAPER_MAX_QUANTITY = Decimal("1e9")
# Files in <hub>/paper that a reset backs up so P&L and history start again too.
PAPER_HISTORY_FILES = (
    PAPER_LEDGER_FILE,
    "trade_history.jsonl",
    "account_value_history.jsonl",
    "strategy_state.json",
    "trader_status.json",
)


class PaperBookError(ValueError):
    """The paper book cannot be read or is not valid. The message is safe to show."""


class PaperBookUnreadable(PaperBookError):
    """The file cannot be parsed the way the trader parses it (bad JSON, a missing
    or malformed field, a number written with commas): the trader ignores it and
    starts from the default balance."""


class PaperBookInvalid(PaperBookError):
    """The file parses but a value breaks a rule (e.g. a starting balance of 0).
    The trader still loads it as written; the Paper Account window will not save
    it until it is fixed."""


@dataclass
class PaperBook:
    """What ``paper_account.json`` holds: ``positions`` maps a base asset (``BTC``)
    to ``(quantity, average_price)``."""

    initial_balance: Decimal
    cash_balance: Decimal
    positions: Dict[str, Tuple[Decimal, Decimal]]


def paper_book_path(hub_dir: str) -> str:
    """The book the paper trader loads at start-up (``<hub>/paper/paper_account.json``)."""
    return os.path.join(hub_dir, PAPER_DATA_SUBDIR, PAPER_BOOK_FILE)


def paper_ledger_path(hub_dir: str) -> str:
    """The paper P&L ledger (cost basis per open position, realized profit)."""
    return os.path.join(hub_dir, PAPER_DATA_SUBDIR, PAPER_LEDGER_FILE)


_THOUSANDS_RE = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")


def _decimal(value: Any, what: str, grouping: bool = True) -> Decimal:
    """A finite Decimal. With ``grouping`` (form input) a comma is accepted only as a
    thousands separator (``10,000.5``); ``0,5`` is refused, never read as 5."""
    text = str(value).strip()
    if "," in text:
        if not (grouping and _THOUSANDS_RE.match(text)):
            raise PaperBookInvalid(
                f"{what}: use a dot for decimals (e.g. 0.5) and no other commas."
            )
        text = text.replace(",", "")
    try:
        number = Decimal(text)
    except (ArithmeticError, ValueError, TypeError):
        raise PaperBookInvalid(f"{what} must be a number.") from None
    if not number.is_finite():
        raise PaperBookInvalid(f"{what} must be a number.")
    return number


def validate_paper_book(
    initial_balance: Any,
    cash_balance: Any,
    positions: Mapping[str, Tuple[Any, Any]],
    grouping: bool = True,
) -> PaperBook:
    """A checked ``PaperBook`` from raw values (strings from a form are fine).

    The starting balance must be above 0 (the return % is measured from it), cash
    0 or more; each symbol a base asset of 2-10 letters (upper-cased), with a
    quantity and an average price above 0, and no symbol twice. Raises
    PaperBookInvalid."""
    initial = _decimal(initial_balance, "The starting balance", grouping)
    if initial <= 0:
        raise PaperBookInvalid("The starting balance must be more than 0.")
    cash = _decimal(cash_balance, "The cash balance", grouping)
    if cash < 0:
        raise PaperBookInvalid("The cash balance cannot be negative.")
    checked: Dict[str, Tuple[Decimal, Decimal]] = {}
    for raw_symbol, (raw_qty, raw_price) in positions.items():
        symbol = str(raw_symbol).strip().upper()
        if not _PAPER_SYMBOL_RE.match(symbol):
            raise PaperBookInvalid(
                f"'{raw_symbol}' is not a coin symbol (2-10 letters, e.g. BTC)."
            )
        if symbol in _PAPER_CASH_SYMBOLS:
            raise PaperBookInvalid(
                f"{symbol} is cash, not a coin: put it in the cash balance."
            )
        if symbol in checked:
            raise PaperBookInvalid(f"{symbol} is listed twice.")
        qty = _decimal(raw_qty, f"The quantity of {symbol}", grouping)
        price = _decimal(raw_price, f"The average price of {symbol}", grouping)
        if qty <= 0:
            raise PaperBookInvalid(f"The quantity of {symbol} must be more than 0.")
        if qty > _PAPER_MAX_QUANTITY:
            raise PaperBookInvalid(f"The quantity of {symbol} is too large.")
        if price <= 0:
            raise PaperBookInvalid(
                f"The average price of {symbol} must be more than 0."
            )
        checked[symbol] = (qty, price)
    return PaperBook(initial, cash, checked)


def read_paper_book(path: str) -> Optional[PaperBook]:
    """The saved book, or None when there is none.

    Raises PaperBookUnreadable when the trader could not parse the file either
    (it then starts from the default balance), and PaperBookInvalid when the
    trader loads it as written but a value breaks a rule. Numbers are parsed
    exactly as the trader parses them (no commas)."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        raw_positions = state.get("positions") or {}
        positions = {
            sym: (p["quantity"], p["average_price"]) for sym, p in raw_positions.items()
        }
        initial = state.get("initial_balance", DEFAULT_PAPER_BALANCE)
        cash = state["cash_balance"]
        # what PaperExchange.load_state does: a value Decimal() refuses makes the
        # trader ignore the whole file
        for value in [initial, cash] + [v for pair in positions.values() for v in pair]:
            Decimal(value)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        ArithmeticError,
    ) as exc:
        raise PaperBookUnreadable(
            f"The saved paper account could not be read ({type(exc).__name__})."
        ) from None
    return validate_paper_book(initial, cash, positions, grouping=False)


def _atomic_write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def write_paper_book(path: str, book: PaperBook) -> None:
    """Save ``book`` in the format ``PaperExchange.load_state`` reads (atomic)."""
    _atomic_write_json(
        path,
        {
            "initial_balance": str(book.initial_balance),
            "cash_balance": str(book.cash_balance),
            "positions": {
                sym: {"quantity": str(qty), "average_price": str(price)}
                for sym, (qty, price) in book.positions.items()
            },
        },
    )


def write_paper_ledger_positions(
    path: str,
    book: PaperBook,
    reset_realized: bool = False,
    keep_cost: Iterable[str] = (),
) -> None:
    """Make the paper P&L ledger's open positions match ``book``.

    The trader takes each position's cost basis (for take-profit and DCA) from
    the ledger, not from the book, so a new or changed position gets
    ``usd_cost = quantity x average price``. A position in ``keep_cost`` (left as
    it was) keeps the ledger's own cost, which includes the buy commission, when
    the ledger holds the same quantity. Pending orders belong to the old book and
    are dropped; realized profit is kept unless ``reset_realized``. Other fields
    are kept as they are."""
    ledger: Dict[str, Any] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            ledger = loaded
    except (OSError, ValueError):
        pass
    ledger.setdefault("total_realized_profit_usd", 0.0)
    if reset_realized:
        ledger["total_realized_profit_usd"] = 0.0
    old = ledger.get("open_positions")
    old = old if isinstance(old, dict) else {}
    keep = set(keep_cost)
    positions: Dict[str, Any] = {}
    for sym, (qty, price) in book.positions.items():
        prior = old.get(sym)
        try:
            same_qty = (
                sym in keep
                and isinstance(prior, dict)
                and abs(float(prior.get("qty", 0.0)) - float(qty)) < 1e-12
                and float(prior.get("usd_cost", 0.0)) > 0.0
            )
        except (TypeError, ValueError):
            same_qty = False
        positions[sym] = (
            dict(prior)
            if same_qty
            else {"usd_cost": float(qty * price), "qty": float(qty)}
        )
    ledger["open_positions"] = positions
    ledger["pending_orders"] = {}
    ledger["last_updated_ts"] = time.time()
    _atomic_write_json(path, ledger)


def backup_paper_history(hub_dir: str, stamp: Optional[str] = None) -> list:
    """Rename the paper ledger, trade and account-value history, strategy state
    and trader status in ``<hub>/paper`` to ``<name>.bak-<stamp>``, so a reset
    account starts its P&L and history from zero. Nothing is deleted. Returns the
    new paths."""
    folder = os.path.join(hub_dir, PAPER_DATA_SUBDIR)
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    moved = []
    for name in PAPER_HISTORY_FILES:
        src = os.path.join(folder, name)
        if os.path.isfile(src):
            dst = f"{src}.bak-{stamp}"
            os.replace(src, dst)
            moved.append(dst)
    return moved


_paper_exchange: Optional[PaperExchange] = None
_paper_lock = threading.Lock()


def configure_paper_exchange(
    state_path: Optional[str] = None,
    initial_balance: Decimal = DEFAULT_PAPER_BALANCE,
    price_feed: Optional[Callable[[str], Optional[Quote]]] = fetch_public_quote,
    settings_source: Any = None,
) -> PaperExchange:
    """(Re)create the process-wide paper exchange. Call once at trader start-up.

    With ``state_path`` the saved book is loaded. When there is no file yet, the
    new book is saved at once, so it exists (and can be edited in Settings) before
    the first order. A file the trader cannot read is renamed to
    ``paper_account.json.bad-<date-time>`` (kept, never overwritten by the next
    order) and a fresh book is saved in its place."""
    global _paper_exchange
    with _paper_lock:
        _paper_exchange = PaperExchange(
            initial_balance=initial_balance,
            price_feed=price_feed,
            state_path=state_path,
            settings_source=settings_source,
        )
        if state_path:
            if os.path.exists(state_path) and not _paper_exchange.state_loaded:
                kept = f"{state_path}.bad-{time.strftime('%Y%m%d-%H%M%S')}"
                try:
                    os.replace(state_path, kept)
                    logger.warning(
                        "Unreadable paper account kept as %s; starting a fresh book.",
                        kept,
                    )
                except OSError:
                    pass
            if not os.path.exists(state_path):
                _paper_exchange._save_state()
        return _paper_exchange


def get_paper_exchange() -> PaperExchange:
    """The process-wide paper exchange (one account, shared by every paper order)."""
    global _paper_exchange
    with _paper_lock:
        if _paper_exchange is None:
            _paper_exchange = PaperExchange(price_feed=fetch_public_quote)
        return _paper_exchange


def reset_paper_exchange() -> None:
    global _paper_exchange
    with _paper_lock:
        _paper_exchange = None


# --- Changing the mode (used by the hub; enforced here, not only in the UI) ---

LIVE_CONFIRM_TEXT = "Yes, I understand real money is at risk"


def can_apply(mode: str, broker: Optional[str], live_confirmed: bool) -> bool:
    """Whether a mode change may be applied. Paper always can; live needs a
    valid broker AND the explicit confirmation."""
    if str(mode).strip().lower() != "live":
        return True
    return _valid_broker(broker) is not None and bool(live_confirmed)


def apply_trading_mode(
    mode: str,
    broker: Optional[str] = None,
    testnet: Optional[bool] = None,
    live_confirmed: bool = False,
    manager: Any = None,
    preview: Optional[bool] = None,
) -> TradingSettings:
    """
    Persist a mode change through the settings manager and return the new
    effective settings. Raises TradingModeError (and changes nothing) when
    switching to live without a broker, on a broker this version cannot place
    orders on, or without the explicit confirmation.
    """
    from pt_settings_manager import SettingsManager

    mode_l = str(mode).strip().lower()
    if mode_l not in ("paper", "live"):
        raise TradingModeError(f"Unknown trading mode: {mode!r}")
    broker_id = _valid_broker(broker)
    if broker and broker_id is None:
        raise TradingModeError(f"Unknown broker: {broker!r}")
    if mode_l == "live":
        if broker_id is None:
            raise TradingModeError("Select a broker before switching to live trading.")
        if not broker_places_orders(broker_id):
            raise TradingModeError(
                f"This version cannot place orders on '{broker_id}'. Choose another "
                "broker, or stay in paper mode."
            )
        if not live_confirmed:
            raise TradingModeError(
                f"Live trading needs explicit confirmation: '{LIVE_CONFIRM_TEXT}'."
            )

    manager = manager if manager is not None else SettingsManager()
    if not manager.set_trading_mode(mode_l, broker=broker_id, persist=False):
        raise TradingModeError("Could not apply the trading mode.")
    if testnet is not None and broker_id is not None:
        if not manager.set_testnet(broker_id, bool(testnet), persist=False):
            raise TradingModeError("Could not apply the testnet setting.")
    if preview is not None and broker_id is not None:
        if not manager.set_preview(broker_id, bool(preview), persist=False):
            raise TradingModeError("Could not apply the preview setting.")
    if not manager.save_settings():
        raise TradingModeError("Could not save the trading mode to disk.")
    return read_trading_settings(manager)


# --- The gate ----------------------------------------------------------------


@dataclass(frozen=True)
class OrderTarget:
    """Where an order is allowed to go. Obtained only from ``resolve_order_target``."""

    mode: TradingMode
    broker: Optional[str]  # None for paper
    exchange: AbstractExchange
    key: str  # TradingSettings.key at resolution time
    # orders are previewed by the broker (``preview_order``) and none is placed
    preview: bool = False

    @property
    def is_live(self) -> bool:
        return self.mode is TradingMode.LIVE

    # The AbstractExchange calls the trader uses, delegated.
    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        *,
        client_order_id: Optional[str] = None,
    ) -> OrderResult:
        """The order, or in preview mode the broker's preview of it (an OrderResult
        with status "preview"). ``client_order_id`` goes unchanged to a connector
        that takes one (it makes the order idempotent); one that does not still
        works."""
        if self.preview:
            return self.exchange.preview_order(symbol, side, amount)
        if client_order_id is not None and _takes_client_order_id(
            self.exchange.place_order
        ):
            return self.exchange.place_order(
                symbol, side, amount, price, client_order_id=client_order_id
            )
        return self.exchange.place_order(symbol, side, amount, price)

    def get_balance(self) -> Dict[str, float]:
        return self.exchange.get_balance()

    def get_order_status(self, order_id: str) -> OrderResult:
        return self.exchange.get_order_status(order_id)

    def cancel_order(self, order_id: str) -> bool:
        return self.exchange.cancel_order(order_id)

    def get_market_data(self, symbol: str) -> MarketData:
        return self.exchange.get_market_data(symbol)


def broker_places_orders(broker: Optional[str]) -> bool:
    """True when this version can read balances and place live orders on
    ``broker`` (its connector's ``SUPPORTS_LIVE_ORDERS``). Looks up no credentials."""
    try:
        exchange_class = ExchangeFactory.get_exchange_class(ExchangeType(broker))
    except (TypeError, ValueError):
        return False
    return bool(getattr(exchange_class, "SUPPORTS_LIVE_ORDERS", False))


def broker_previews_orders(broker: Optional[str]) -> bool:
    """True when ``broker``'s connector can preview an order without placing it
    (``SUPPORTS_ORDER_PREVIEW``). Looks up no credentials."""
    try:
        exchange_class = ExchangeFactory.get_exchange_class(ExchangeType(broker))
    except (TypeError, ValueError):
        return False
    return bool(getattr(exchange_class, "SUPPORTS_ORDER_PREVIEW", False))


def _takes_client_order_id(place_order: Callable) -> bool:
    """The connector's ``place_order`` names a ``client_order_id`` parameter."""
    try:
        return "client_order_id" in inspect.signature(place_order).parameters
    except (TypeError, ValueError):
        return False


KEY_CANNOT_TRADE = (
    "This API key cannot place orders. Create a key with Trade permission, then save "
    "it in Configure Exchange APIs."
)
KEY_CAN_TRANSFER = (
    "This API key can also transfer funds out of the account. PowerTrader does not "
    "need Transfer: a key without it is safer."
)


@dataclass(frozen=True)
class KeyCheck:
    """What the broker's read-only key check said about live trading."""

    ok: bool  # False: live trading is refused with this key
    message: str  # the check's own answer (permissions, or why it failed)
    warning: str = ""  # allowed, but the user should know (e.g. Transfer)


def check_live_key(exchange: Any, preview: bool = False) -> KeyCheck:
    """The broker's read-only key check (``check_connection``) before live trading.

    A key the broker rejects, or that cannot trade, is refused (a preview needs no
    Trade permission). A key that can transfer funds is allowed with a warning. A
    connector without a key check is allowed: there is nothing to check."""
    try:
        result = exchange.check_connection()
    except Exception as exc:
        return KeyCheck(False, f"The API key could not be checked: {exc}")
    if result.status is ConnectionStatus.UNSUPPORTED:
        return KeyCheck(True, result.message)
    if result.status is not ConnectionStatus.OK:
        return KeyCheck(False, result.message)
    details = result.details or {}
    if not preview and details.get("can_trade") is False:
        return KeyCheck(False, f"{result.message} {KEY_CANNOT_TRADE}")
    warning = KEY_CAN_TRANSFER if details.get("can_transfer") else ""
    return KeyCheck(True, result.message, warning)


def check_broker_key(broker: str, preview: bool = False) -> KeyCheck:
    """``check_live_key`` for ``broker`` with its saved key (Trading Mode window)."""
    settings = TradingSettings(TradingMode.LIVE, _valid_broker(broker), False, preview)
    if settings.active_broker is None:
        return KeyCheck(False, f"Unknown broker: {broker!r}")
    try:
        exchange = _build_live_exchange(settings)
    except LiveTradingRefused as exc:
        return KeyCheck(False, str(exc))
    return check_live_key(exchange, preview)


def move_root_live_books(hub_dir: str, broker: Optional[str]) -> Optional[str]:
    """Once: move live books kept in the hub folder itself (where every live broker
    shared them) into ``live/<broker>/``, after copying them to a backup folder.

    Returns the folder they moved to, or None when nothing moved. Books are never
    merged: when ``live/<broker>/`` already has books, nothing moves.

    The files to move are written to a marker in ``live/<broker>/`` first, so a
    move that stopped part-way is finished on the next call before any book is
    read. Raises OSError while it cannot be finished; the trader does not start
    on a half-moved set of books."""
    if not broker:
        return None
    dest = os.path.join(hub_dir, LIVE_DATA_SUBDIR, broker)
    marker = os.path.join(dest, LIVE_BOOKS_MOVE_MARKER)
    if os.path.isfile(marker):
        with open(marker, encoding="utf-8") as f:
            started = json.load(f)
        present = [n for n in started.get("files", []) if n in LIVE_BOOK_FILES]
        backup = str(started.get("backup", ""))
        logger.warning(f"Finishing the move of the live books {present} to {dest}")
    else:
        present = [
            n for n in LIVE_BOOK_FILES if os.path.isfile(os.path.join(hub_dir, n))
        ]
        if not present:
            return None
        if any(os.path.exists(os.path.join(dest, n)) for n in LIVE_BOOK_FILES):
            logger.warning(
                f"Live books found in {hub_dir} and in {dest}; left as they are "
                "(books are never merged)"
            )
            return None
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = os.path.join(hub_dir, f"live_books_backup_{stamp}")
        os.makedirs(backup, exist_ok=True)
        for name in present:
            shutil.copy2(os.path.join(hub_dir, name), os.path.join(backup, name))
        os.makedirs(dest, exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            json.dump({"files": present, "backup": backup}, f)
    for name in present:
        source, target = os.path.join(hub_dir, name), os.path.join(dest, name)
        if os.path.isfile(source) and os.path.exists(target):
            raise OSError(
                f"Live book {name} is in both {hub_dir} and {dest}; the move was not "
                f"finished (a copy from before the move is in {backup})"
            )
        if os.path.isfile(source):
            os.replace(source, target)
        elif not os.path.exists(target):
            raise OSError(
                f"Live book {name} is in neither {hub_dir} nor {dest}; the move was "
                f"not finished (a copy from before the move is in {backup})"
            )
    os.remove(marker)
    logger.info(f"Moved the live books {present} to {dest} (backup in {backup})")
    return dest


def _build_live_exchange(ts: TradingSettings) -> AbstractExchange:
    assert ts.active_broker is not None
    try:
        import pt_exchanges  # noqa: F401  (registers exchange classes with the factory)
    except ImportError:
        # Nothing registered -> the factory below raises "not registered", which
        # is reported as a refusal. Don't mask an already-registered broker.
        pass

    try:
        ExchangeFactory.load_credentials()
        kwargs: Dict[str, Any] = {}
        if ts.active_broker in TESTNET_BROKERS:
            kwargs["testnet"] = ts.testnet
        return ExchangeFactory.get_exchange(ExchangeType(ts.active_broker), **kwargs)
    except Exception as exc:
        raise LiveTradingRefused(
            f"Live trading refused: could not set up broker "
            f"'{ts.active_broker}': {exc}"
        ) from exc


def resolve_order_target(settings: Any = None) -> OrderTarget:
    """
    The single chokepoint every order must pass through.

    Returns the target an order may be sent to, or raises ``LiveTradingRefused``
    when live trading is selected but unusable. Never returns a live exchange
    unless ``trading.mode`` is "live" and an active broker is configured.
    """
    ts = read_trading_settings(settings)

    if not ts.is_live:
        paper = get_paper_exchange()
        paper.settings_source = settings  # price policy follows the same settings
        return OrderTarget(
            mode=TradingMode.PAPER,
            broker=None,
            exchange=paper,
            key=ts.key,
        )

    if ts.active_broker is None:
        raise LiveTradingRefused(
            "Live trading refused: trading.mode is 'live' but no active broker "
            "is selected. Choose a broker in the hub, or switch back to paper mode."
        )

    exchange = _build_live_exchange(ts)
    if not getattr(exchange, "SUPPORTS_LIVE_ORDERS", False):
        raise LiveTradingRefused(
            f"Live trading refused: this version cannot place orders on "
            f"'{ts.active_broker}'. Choose another broker in File > Trading Mode, or "
            "switch back to paper mode."
        )
    if ts.uses_preview and not callable(getattr(exchange, "preview_order", None)):
        raise LiveTradingRefused(
            f"Live trading refused: '{ts.active_broker}' cannot preview orders"
        )
    return OrderTarget(
        mode=TradingMode.LIVE,
        broker=ts.active_broker,
        exchange=exchange,
        key=ts.key,
        preview=ts.uses_preview,
    )
