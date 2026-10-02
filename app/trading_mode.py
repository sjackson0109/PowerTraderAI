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

import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from decimal import Decimal
from email.utils import parsedate_to_datetime
from enum import Enum
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from pt_exchange_abstraction import (
    AbstractExchange,
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
    trading_testnet_key,
)

logger = get_logger("trading_mode")

PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"

# Brokers whose exchange class accepts a ``testnet`` constructor flag. The
# ``trading.<broker>_testnet`` setting is only forwarded to these.
TESTNET_BROKERS = frozenset({ExchangeType.BINANCE.value})

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

    @property
    def is_live(self) -> bool:
        return self.mode is TradingMode.LIVE

    @property
    def uses_testnet(self) -> bool:
        return (
            self.is_live
            and self.active_broker in TESTNET_BROKERS
            and self.testnet
        )

    @property
    def label(self) -> str:
        """Text for the always-visible hub indicator."""
        if not self.is_live:
            return "MODE: PAPER"
        if self.active_broker is None:
            return "MODE: LIVE — NO BROKER (orders blocked)"
        suffix = " (testnet)" if self.uses_testnet else ""
        return f"MODE: LIVE — {self.active_broker}{suffix}"

    @property
    def key(self) -> str:
        """Stable identity of where orders would go; used to detect mode changes."""
        if not self.is_live:
            return "paper"
        if self.active_broker is None:
            return "live:blocked"
        return f"live:{self.active_broker}" + (":testnet" if self.uses_testnet else "")

    @property
    def data_subdir(self) -> str:
        """Sub-directory of the hub data dir holding this mode's ledger/history,
        so paper and testnet fills never mix into the live books."""
        if self.is_live and self.active_broker is not None:
            return "testnet" if self.uses_testnet else ""
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
    return TradingSettings(mode=mode, active_broker=broker, testnet=testnet)


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


class PriceUnavailable(RuntimeError):
    """No live price and the policy is ``pause``."""

    reason = PRICE_UNAVAILABLE


def classify_quote(quote: Optional[Quote], max_age_s: float, now: float) -> str:
    """"live" if fresh; "stale" if older than ``max_age_s`` (or its age is
    unknown, which is treated as stale); "simulated" if there is no quote."""
    if quote is None:
        return "simulated"
    age = quote.age_s
    if age is None or age > max_age_s or (now - quote.fetched_ts) > max_age_s:
        return "stale"
    return "live"


# --- Public quote feed (paper pricing only; never an order call) -------------

_QUOTE_URL = "https://api.binance.com/api/v3/ticker/bookTicker?symbol={symbol}"
_QUOTE_TTL_SECONDS = 2.0
_quote_cache: Dict[str, Quote] = {}


def fetch_public_quote(base: str, timeout: float = 3.0) -> Optional[Quote]:
    """
    Binance public book ticker for ``base``/USDT, or None if unreachable.

    The book ticker carries no timestamp of its own, so ``quote_ts`` is the
    server time of the response (HTTP ``Date`` header, 1 s resolution). A
    response without a usable Date header has ``quote_ts=None`` and is treated
    as stale.
    """
    now = time.time()
    cached = _quote_cache.get(base)
    if cached and now - cached.fetched_ts < _QUOTE_TTL_SECONDS:
        return cached
    try:
        url = _QUOTE_URL.format(symbol=f"{base}USDT")
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            date_header = resp.headers.get("Date") if resp.headers else None
        bid, ask = float(payload["bidPrice"]), float(payload["askPrice"])
    except (urllib.error.URLError, ValueError, KeyError, TypeError, OSError):
        return None
    if bid <= 0 or ask <= 0:
        return None
    quote_ts: Optional[float] = None
    if date_header:
        try:
            quote_ts = parsedate_to_datetime(date_header).timestamp()
        except (TypeError, ValueError):
            quote_ts = None
    quote = Quote(bid=bid, ask=ask, quote_ts=quote_ts, fetched_ts=time.time())
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
        if state_path:
            self.load_state(state_path)

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
                quote.bid, quote.ask, "live", quote.quote_ts, quote.fetched_ts, quote.age_s
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
                quote.bid, quote.ask, "stale", quote.quote_ts, quote.fetched_ts, quote.age_s
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
            timestamp=priced.quote_ts if priced.quote_ts is not None else priced.fetched_ts,
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

    def _reject(self, symbol: str, side: str, amount: float, reason: str) -> OrderResult:
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
        for trade in reversed(self.account.trade_history):
            if trade.order_id == order_id:
                trade.price_source = order.price_source
                trade.quote_ts = order.quote_ts
                trade.age_s = order.age_s
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
                for sym, p in state.get("positions", {}).items()
            }
            initial = Decimal(state.get("initial_balance", self.account.initial_balance))
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError):
            return False
        self.account.cash_balance = cash
        self.account.positions = positions
        self.account.initial_balance = initial
        return True


_paper_exchange: Optional[PaperExchange] = None
_paper_lock = threading.Lock()


def configure_paper_exchange(
    state_path: Optional[str] = None,
    initial_balance: Decimal = Decimal("10000"),
    price_feed: Optional[Callable[[str], Optional[Quote]]] = fetch_public_quote,
    settings_source: Any = None,
) -> PaperExchange:
    """(Re)create the process-wide paper exchange. Call once at trader start-up."""
    global _paper_exchange
    with _paper_lock:
        _paper_exchange = PaperExchange(
            initial_balance=initial_balance,
            price_feed=price_feed,
            state_path=state_path,
            settings_source=settings_source,
        )
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
) -> TradingSettings:
    """
    Persist a mode change through the settings manager and return the new
    effective settings. Raises TradingModeError (and changes nothing) when
    switching to live without a broker or without the explicit confirmation.
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

    @property
    def is_live(self) -> bool:
        return self.mode is TradingMode.LIVE

    # The AbstractExchange calls the trader uses, delegated.
    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        return self.exchange.place_order(symbol, side, amount, price)

    def get_balance(self) -> Dict[str, float]:
        return self.exchange.get_balance()

    def get_order_status(self, order_id: str) -> OrderResult:
        return self.exchange.get_order_status(order_id)

    def cancel_order(self, order_id: str) -> bool:
        return self.exchange.cancel_order(order_id)

    def get_market_data(self, symbol: str) -> MarketData:
        return self.exchange.get_market_data(symbol)


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

    return OrderTarget(
        mode=TradingMode.LIVE,
        broker=ts.active_broker,
        exchange=_build_live_exchange(ts),
        key=ts.key,
    )
