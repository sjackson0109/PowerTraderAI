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
mode value it does not recognise, resolves to paper - never to live. A file that
exists but cannot be read is a problem in the strategy settings as well
(``settings_problem``), so the trader places no orders at all until it can be.

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
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from enum import Enum
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple

from pt_exchange_abstraction import (
    AbstractExchange,
    ConnectionStatus,
    ExchangeFactory,
    ExchangeType,
    MarketData,
    OrderResult,
    TradingFees,
    default_trading_fees,
    exchange_name,
    usable_fees,
    usable_minimum,
)
from pt_paper_trading import (
    MarketDataSimulator,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperTradingAccount,
    Position,
)
from pt_logging import get_logger
from pt_settings_manager import (
    DEFAULT_DRAWDOWN_CRITICAL_PCT,
    DEFAULT_DRAWDOWN_WARNING_PCT,
    DEFAULT_EMERGENCY_DRAWDOWN_PCT,
    DEFAULT_MAX_QUOTE_AGE_S,
    DEFAULT_PRICE_FALLBACK_POLICY,
    DRAWDOWN_CRITICAL_KEY,
    DRAWDOWN_LEVEL_RANGE,
    DRAWDOWN_WARNING_KEY,
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
# The reason a paper order is refused for its size, as live connectors give it
# (e.g. CoinbaseExchange._market_order)
BELOW_MINIMUM = "BELOW_MINIMUM"

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


class UnreadableSettings(dict):
    """No settings, for a settings file that exists but cannot be read: every setting
    reads as its default (the mode as paper), and ``problem`` says why. The strategy
    settings report it as a problem, so no orders are placed while it lasts."""

    def __init__(self, problem: str = ""):
        super().__init__()
        self.problem = problem


def _read_settings_file(path: str) -> Dict[str, Any]:
    """Raw read of the settings file. A missing file (a fresh install) yields {}
    (=> paper, every setting its default). One that exists but cannot be read, or
    is not a JSON object, yields an UnreadableSettings: the same, with why."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        return UnreadableSettings(
            f"the settings file {path} cannot be read ({type(exc).__name__}: {exc})"
        )
    if not isinstance(data, dict):
        return UnreadableSettings(
            f"the settings file {path} cannot be read (it is not a JSON object)"
        )
    return data


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
        return f"MODE: LIVE — {exchange_name(self.active_broker)}{suffix}"

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


def settings_problem(settings: Any = None) -> Optional[str]:
    """Why the settings file behind ``settings`` (anything ``settings_mapping``
    takes) cannot be read, or None: None too for a missing file, and for settings
    that are not a file."""
    mapping = _settings_mapping(settings)
    return mapping.problem if isinstance(mapping, UnreadableSettings) else None


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


def save_paper_settings(
    policy: str, max_quote_age_s: float, manager: Any = None
) -> bool:
    """Write both paper-fill rules (Settings > Paper trading). False, and nothing
    written, for a policy or an age out of range."""
    from pt_settings_manager import SettingsManager

    if policy not in PRICE_FALLBACK_POLICIES or not _in_range(
        max_quote_age_s, MAX_QUOTE_AGE_RANGE
    ):
        return False
    manager = manager if manager is not None else SettingsManager()
    if not manager.set(PAPER_MAX_QUOTE_AGE_KEY, float(max_quote_age_s)):
        return False
    if not manager.set_price_fallback_policy(policy, persist=False):
        return False
    return bool(manager.save_settings())


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


@dataclass(frozen=True)
class DrawdownLevels:
    """Account drawdown levels in percent of the peak (Settings > Risk)."""

    warning_pct: float
    critical_pct: float
    emergency_pct: float


# problems already logged, so a bad file is reported once, not on every check
_drawdown_logged: set = set()


def _log_drawdown_once(message: str) -> None:
    if message not in _drawdown_logged:
        _drawdown_logged.add(message)
        logger.warning(message)


def read_drawdown_levels(settings: Any = None) -> DrawdownLevels:
    """``risk.drawdown_warning_pct`` and ``risk.drawdown_critical_pct`` (each
    0.5-50) with the emergency stop (``read_emergency_drawdown_pct``). A level out
    of range, or a pair not in order (warning < critical < emergency), reads as the
    defaults for the warning and critical levels, logged; they never change the
    stop."""
    settings = _settings_mapping(settings)
    emergency = read_emergency_drawdown_pct(settings)
    warning = _lookup(settings, DRAWDOWN_WARNING_KEY, DEFAULT_DRAWDOWN_WARNING_PCT)
    critical = _lookup(settings, DRAWDOWN_CRITICAL_KEY, DEFAULT_DRAWDOWN_CRITICAL_PCT)
    if not (
        _in_range(warning, DRAWDOWN_LEVEL_RANGE)
        and _in_range(critical, DRAWDOWN_LEVEL_RANGE)
        and warning < critical < emergency
    ):
        _log_drawdown_once(
            f"Invalid {DRAWDOWN_WARNING_KEY}={warning!r} / {DRAWDOWN_CRITICAL_KEY}="
            f"{critical!r} (each {DRAWDOWN_LEVEL_RANGE[0]:g}-"
            f"{DRAWDOWN_LEVEL_RANGE[1]:g}, below the {emergency:g}% stop); using "
            f"{DEFAULT_DRAWDOWN_WARNING_PCT:g} and {DEFAULT_DRAWDOWN_CRITICAL_PCT:g}"
        )
        warning, critical = DEFAULT_DRAWDOWN_WARNING_PCT, DEFAULT_DRAWDOWN_CRITICAL_PCT
    return DrawdownLevels(float(warning), float(critical), float(emergency))


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


# --- Trading fees for paper fills (the exchange layer; never an order call) --


def _layer_fees(base: str, exchange: str = ""):
    """The exchange layer's maker and taker fees for ``base``: a ``Sourced``
    ``TradingFees`` from ``exchange``, or from the exchanges in Settings, primary
    first, when ``exchange`` is ""; None when none gives them."""
    from pt_multi_exchange import market_exchanges

    return market_exchanges().trading_fees(base, only=exchange or None)


def fetch_trading_fees(base: str, exchange: str = "") -> Optional[TradingFees]:
    """
    The fee rates a paper fill of ``base`` pays: those of ``exchange`` (the exchange
    whose quote priced it), else of the exchanges in Settings, primary first. The
    exchange layer reads each exchange's own rates where it can and gives its
    published standard rates otherwise (``TradingFees.source``). When the layer
    cannot be asked, ``exchange``'s standard rates; None when there are none.
    """
    try:
        answer = _layer_fees(base, exchange)
    except Exception as exc:
        logger.debug(f"No trading fees for {base} from the exchange layer: {exc}")
        answer = None
    if answer is not None:
        return answer.value
    return default_trading_fees(exchange) if exchange else None


# --- Sell step and minimum order for paper fills (the exchange layer) ---------


@dataclass(frozen=True)
class VenueRules:
    """What the exchanges in Settings state for orders in a coin: the step a sell's
    quantity is rounded down to, in coins (Coinbase's ``base_increment``), and the
    smallest order, in USD. None for either when no exchange states it."""

    sell_step: Optional[float] = None
    minimum_usd: Optional[float] = None


def _layer_venue_rules(base: str) -> VenueRules:
    """The exchange layer's sell step and minimum order for ``base``: the exchanges in
    Settings, primary first, from public product data. The paper trader's minimum
    order (its entry size and dust) and the strategy lab's venue rules, which the
    replay's costs use, come from the same two calls."""
    from pt_multi_exchange import market_exchanges

    manager = market_exchanges()
    symbol = f"{base}-USD"
    return VenueRules(manager.lot_increment(symbol), manager.min_order_usd(symbol))


def _usable_venue_rules(value: Any) -> VenueRules:
    """``value`` with any figure that is not a positive, finite number left out (a
    connector may answer anything)."""
    if not isinstance(value, VenueRules):
        return VenueRules()
    return VenueRules(
        usable_minimum(value.sell_step), usable_minimum(value.minimum_usd)
    )


def fetch_venue_rules(base: str) -> VenueRules:
    """
    The sell step and minimum order a paper fill of ``base`` follows: those the
    exchanges in Settings state, primary first. Either is None when no exchange
    states it, or the exchange layer cannot be asked (offline). Public product data
    only: no credentials.
    """
    try:
        return _usable_venue_rules(_layer_venue_rules(base))
    except Exception as exc:
        logger.debug(f"No sell step or minimum order for {base}: {exc}")
        return VenueRules()


def _plain(value: Any) -> str:
    """A quantity or price as written, without trailing zeros (``4.0`` is ``4``)."""
    return format(Decimal(str(value)).normalize(), "f")


def _worth(value: Decimal) -> str:
    """An order's value in dollars, for a refusal's reason."""
    return f"about ${value:,.2f}" if value >= Decimal("0.01") else "less than $0.01"


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

    Every fill pays a fee, in USD from the paper cash: the taker rate for a market
    order, the maker rate for a limit order, of the exchange whose quote priced it
    (``fee_feed(base, exchange) -> TradingFees | None``, the exchange layer's
    ``trading_fees``; "" for the exchanges in Settings, primary first). With no
    rates from the feed, that exchange's stored standard rates; with none at all,
    the paper account's own rate, logged at WARNING.

    Every order follows the exchange's sell step and minimum order, as live orders
    do (``venue_feed(base) -> VenueRules``, the exchange layer's ``lot_increment``
    and ``min_order_usd``: the exchanges in Settings, primary first). A sell is
    rounded down to the step and what is left stays in the book; a buy is not
    rounded (Coinbase sizes a market buy in dollars). A sell smaller than one step,
    or an order worth less than the minimum at its fill price, is rejected with
    reason ``BELOW_MINIMUM: ...`` and changes nothing. Where no exchange states a
    step or a minimum (or there is no feed), nothing is rounded or refused.

    With ``state_path`` the book is shared: the trader and the hub's Order
    Management each have an account on the same file. Every order and balance read
    takes the book's lock file and first reads the book again when another process
    saved it since this account last read or wrote it (``_book``).
    """

    # Offline fallback spread around the simulator price.
    _SIM_HALF_SPREAD = 0.0005
    # How long fee rates are reused before they are asked for again.
    _FEES_TTL_SECONDS = 3600.0
    # How long a coin's sell step and minimum order are reused (the trader keeps the
    # minimum it tells dust by as long: pt_trader.DUST_MINIMUM_SECONDS).
    _VENUE_TTL_SECONDS = 3600.0

    def __init__(
        self,
        account: Optional[PaperTradingAccount] = None,
        initial_balance: Decimal = Decimal("10000"),
        price_feed: Optional[Callable[[str], Optional[Quote]]] = None,
        state_path: Optional[str] = None,
        settings_source: Any = None,
        clock: Callable[[], float] = time.time,
        fee_feed: Optional[Callable[[str, str], Optional[TradingFees]]] = None,
        venue_feed: Optional[Callable[[str], Optional[VenueRules]]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("", "", **kwargs)
        self.account = account or PaperTradingAccount(initial_balance=initial_balance)
        self._simulator = _AnchoredSimulator()
        self.account.market_simulator = self._simulator
        self._price_feed = price_feed
        self._fee_feed = fee_feed
        self._venue_feed = venue_feed
        # base -> (when read, its sell step and minimum order)
        self._venue: Dict[str, Tuple[float, VenueRules]] = {}
        self._state_path = state_path
        self.settings_source = settings_source
        self._clock = clock
        self._lock = threading.RLock()
        self._rejections: Dict[str, OrderResult] = {}
        self.last_quotes: Dict[str, PricedQuote] = {}
        # (exchange, base) -> (when read, the fee rates a fill pays)
        self._fees: Dict[Tuple[str, str], Tuple[float, TradingFees]] = {}
        # the saved book as this account last read or wrote it (None: not read). Its
        # contents, not its time: a file time can repeat within a clock tick
        self._book_seen: Optional[bytes] = None
        # False when there is no saved book or it could not be read
        self.state_loaded = bool(state_path) and self.load_state(state_path)
        if self.state_loaded:
            self._book_seen = self._book_bytes()

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

    # -- fees --

    def _fees_for(self, base: str, exchange: str) -> TradingFees:
        """The fee rates a fill of ``base`` priced by ``exchange`` pays ("" when no
        exchange priced it), reused for ``_FEES_TTL_SECONDS``."""
        key = (exchange, base)
        now = self._clock()
        cached = self._fees.get(key)
        if cached is not None and now - cached[0] < self._FEES_TTL_SECONDS:
            return cached[1]
        fees = None
        if self._fee_feed is not None:
            try:
                fees = usable_fees(self._fee_feed(base, exchange))
            except Exception as exc:
                logger.debug(f"No trading fees for {base} from the fee feed: {exc}")
        if fees is None and exchange:
            fees = default_trading_fees(exchange)
        if fees is None:
            rate = float(self.account.commission_rate)
            logger.warning(
                f"No trading fees for {base} from the exchanges in Settings; paper "
                f"fills pay {rate:.2%}"
            )
            fees = TradingFees(rate, rate, exchange, "paper")
        self._fees[key] = (now, fees)
        return fees

    def trading_fees(self, symbol: str) -> TradingFees:
        """The fee rates the next fill of ``symbol`` pays: those of the exchange whose
        quote last priced it (the exchanges in Settings, primary first, before any
        quote)."""
        base = _base_asset(symbol)
        last = self.last_quotes.get(base)
        return self._fees_for(base, last.exchange if last is not None else "")

    def _stamp_fees(self, order_id: str, fees: TradingFees, fee_type: str) -> None:
        """Record on the order which rate its fill pays and where it came from."""
        order = self.account.orders[order_id]
        order.fee_type = fee_type
        order.fee_exchange = fees.exchange
        order.fee_source = fees.source

    # -- the exchange's sell step and minimum order --

    def _venue_for(self, base: str) -> VenueRules:
        """The sell step and minimum order the exchanges in Settings state for
        ``base``, reused for ``_VENUE_TTL_SECONDS``; neither without a venue feed."""
        if self._venue_feed is None:
            return VenueRules()
        now = self._clock()
        cached = self._venue.get(base)
        if cached is not None and now - cached[0] < self._VENUE_TTL_SECONDS:
            return cached[1]
        try:
            rules = _usable_venue_rules(self._venue_feed(base))
        except Exception as exc:
            logger.debug(f"No sell step or minimum order for {base}: {exc}")
            rules = VenueRules()
        self._venue[base] = (now, rules)
        return rules

    def _venue_size(
        self, base: str, side: OrderSide, amount: Any, price: Any
    ) -> Tuple[Decimal, str]:
        """(the quantity of ``base`` the exchange takes for an order of ``amount``,
        why it would refuse the order: "" when it would not), as a live connector
        works it out before sending (``CoinbaseExchange._market_order``). A sell is
        rounded down to the sell step; a buy is not rounded. A sell left with nothing,
        or an order worth less than the minimum at ``price``, is refused. With no
        step or minimum stated, ``amount`` is taken as it is (as before)."""
        rules = self._venue_for(base)
        asked = Decimal(str(amount))
        quantity = asked
        if side is OrderSide.SELL and rules.sell_step is not None:
            step = Decimal(str(rules.sell_step))
            quantity = (asked / step).to_integral_value(rounding=ROUND_DOWN) * step
            if quantity <= 0:
                return quantity, (
                    f"{BELOW_MINIMUM}: {_plain(asked)} {base} is less than the "
                    f"exchange's sell step of {_plain(step)} {base}"
                )
        if rules.minimum_usd is not None:
            value = quantity * Decimal(str(price))
            minimum = Decimal(str(rules.minimum_usd))
            if value < minimum:
                return quantity, (
                    f"{BELOW_MINIMUM}: {_plain(quantity)} {base} is worth "
                    f"{_worth(value)}, below the exchange's minimum order of "
                    f"${_plain(minimum)} for {base}-USD"
                )
        if quantity != asked:
            logger.info(
                f"Paper sell of {_plain(asked)} {base} rounded down to "
                f"{_plain(quantity)}: the exchange's sell step is "
                f"{_plain(rules.sell_step)} {base}"
            )
        return quantity, ""

    # -- orders --

    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        side_l = str(side).lower().strip()
        if side_l not in ("buy", "sell"):
            raise ValueError(f"Invalid order side: {side!r}")
        order_side = OrderSide.BUY if side_l == "buy" else OrderSide.SELL
        base = _base_asset(symbol)

        with self._book():
            priced: Optional[PricedQuote] = None
            if price is None:
                # Market order: fill at the ask when buying, the bid when selling,
                # paying the taker rate of the exchange whose quote it is.
                try:
                    priced = self._priced_quote(base)
                except PriceUnavailable:
                    return self._reject(symbol, side_l, amount, PRICE_UNAVAILABLE)
                fill = priced.ask if order_side is OrderSide.BUY else priced.bid
                quantity, refusal = self._venue_size(base, order_side, amount, fill)
                if refusal:
                    return self._reject(symbol, side_l, amount, refusal)
                self._simulator.anchors[base] = Decimal(str(fill))
                fees = self._fees_for(base, priced.exchange)
                fee_type, rate = fees.for_order("market")
                order_id = self.account.place_order(
                    symbol=base,
                    order_type=OrderType.MARKET,
                    side=order_side,
                    quantity=quantity,
                    commission_rate=Decimal(str(rate)),
                )
            else:
                # Limit order: the price is the caller's, no feed involved; it pays
                # the maker rate.
                quantity, refusal = self._venue_size(base, order_side, amount, price)
                if refusal:
                    return self._reject(symbol, side_l, amount, refusal)
                fees = self.trading_fees(base)
                fee_type, rate = fees.for_order("limit")
                order_id = self.account.place_order(
                    symbol=base,
                    order_type=OrderType.LIMIT,
                    side=order_side,
                    quantity=quantity,
                    price=Decimal(str(price)),
                    commission_rate=Decimal(str(rate)),
                )
            self._stamp_provenance(order_id, priced)
            self._stamp_fees(order_id, fees, fee_type)
            self._save_state()
            return self._order_result(order_id)

    def fill_limit_order(
        self, symbol: str, side: str, amount: float, price: float
    ) -> OrderResult:
        """A limit order the market has reached (Order Management watches it): it
        fills at its own limit ``price`` and pays the maker rate of the exchange
        whose quote reached it. That quote is the one a market order would use now,
        so it must be live as for a market order (else rejected with
        PRICE_UNAVAILABLE under the pause policy)."""
        side_l = str(side).lower().strip()
        if side_l not in ("buy", "sell"):
            raise ValueError(f"Invalid order side: {side!r}")
        order_side = OrderSide.BUY if side_l == "buy" else OrderSide.SELL
        base = _base_asset(symbol)
        with self._book():
            try:
                priced = self._priced_quote(base)
            except PriceUnavailable:
                return self._reject(symbol, side_l, amount, PRICE_UNAVAILABLE)
            limit = Decimal(str(price))
            quantity, refusal = self._venue_size(base, order_side, amount, limit)
            if refusal:
                return self._reject(symbol, side_l, amount, refusal)
            self._simulator.anchors[base] = limit
            fees = self._fees_for(base, priced.exchange)
            fee_type, rate = fees.for_order("limit")
            order_id = self.account.place_order(
                symbol=base,
                order_type=OrderType.LIMIT,
                side=order_side,
                quantity=quantity,
                price=limit,
                commission_rate=Decimal(str(rate)),
            )
            if self.account.orders[order_id].status is OrderStatus.PENDING:
                self.account._execute_order(order_id)  # at its limit price
            self._stamp_provenance(order_id, priced)
            self._stamp_fees(order_id, fees, fee_type)
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
        with self._book():
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
        # A fill reports its value and fee (USD, from the paper cash), as an
        # exchange does: the trader's books take them as they are
        filled = order.status is OrderStatus.FILLED
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
            fee=float(order.commission) if filled else None,
            filled_value=(
                float(order.filled_quantity * order.filled_price) if filled else None
            ),
            fee_currency=PAPER_BALANCE_ASSET if filled else "",
            fee_rate=(
                float(order.commission_rate)
                if order.commission_rate is not None
                else None
            ),
            fee_type=order.fee_type,
            fee_exchange=order.fee_exchange,
            fee_source=order.fee_source,
        )

    # -- persistence (so the paper book survives a trader restart) --

    def _book_bytes(self) -> Optional[bytes]:
        try:
            with open(self._state_path, "rb") as f:
                return f.read()
        except (OSError, TypeError):
            return None

    @contextmanager
    def _book(self):
        """One read or change of the book. With a saved book, its lock file is held
        (every process takes it, so two never change the book at once) and the book
        is read again first when it was saved since this account last read or wrote
        it. A book that cannot be read then is left as this account has it (logged
        by ``load_state``). When the lock cannot be had in a few seconds, the order
        goes ahead without it (logged)."""
        with self._lock:
            if not self._state_path:
                yield
                return
            # the cross-process lock the request pacing uses (one byte of a file)
            from rate_limits import _Locked

            held = _Locked(f"{self._state_path}.lock", self._clock)
            try:
                held.__enter__()
            except OSError as exc:
                logger.warning(f"Paper book lock not taken ({exc}); going ahead")
                held = None
            try:
                seen = self._book_bytes()
                if seen is not None and seen != self._book_seen:
                    self.load_state(self._state_path)
                    self._book_seen = seen
                yield
            finally:
                if held is not None:
                    held.__exit__(None, None, None)

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
        else:
            self._book_seen = self._book_bytes()  # this account's own write

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
    fee_feed: Optional[
        Callable[[str, str], Optional[TradingFees]]
    ] = fetch_trading_fees,
    venue_feed: Optional[Callable[[str], Optional[VenueRules]]] = fetch_venue_rules,
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
            fee_feed=fee_feed,
            venue_feed=venue_feed,
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
            _paper_exchange = PaperExchange(
                price_feed=fetch_public_quote,
                fee_feed=fetch_trading_fees,
                venue_feed=fetch_venue_rules,
            )
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
                f"This version cannot place orders on {exchange_name(broker_id)}. "
                "Choose another broker, or stay in paper mode."
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

    def get_balance_with_holds(self) -> Dict[str, float]:
        """Every balance with the funds held for open orders included, for the
        drawdown stop. A connector that cannot say what is on hold (the paper
        account holds nothing) gives ``get_balance``."""
        read = getattr(self.exchange, "get_balance_with_holds", None)
        return read() if callable(read) else self.exchange.get_balance()

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

    The files to move are written to a marker in ``live/<broker>/`` first. A move
    that stopped part-way is finished on the next call, into the broker folder it
    started for (whichever broker is chosen now), before anything else moves or
    any book is read. Raises OSError (ValueError for an unreadable marker) while
    it cannot be finished; the trader does not start on a half-moved set of books."""
    if not broker:
        return None
    dest = os.path.join(hub_dir, LIVE_DATA_SUBDIR, broker)
    finished = None
    for folder in _unfinished_live_book_moves(hub_dir):
        logger.warning(f"Finishing an earlier move of the live books into {folder}")
        done = _finish_live_books_move(hub_dir, folder)
        if os.path.normcase(folder) == os.path.normcase(dest):
            finished = done
    if finished is not None:
        return finished
    present = [n for n in LIVE_BOOK_FILES if os.path.isfile(os.path.join(hub_dir, n))]
    if not present:
        return None
    if any(os.path.exists(os.path.join(dest, n)) for n in LIVE_BOOK_FILES):
        logger.warning(
            f"Live books found in {hub_dir} and in {dest}; left as they are (books "
            "are never merged)"
        )
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(hub_dir, f"live_books_backup_{stamp}")
    os.makedirs(backup, exist_ok=True)
    for name in present:
        shutil.copy2(os.path.join(hub_dir, name), os.path.join(backup, name))
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, LIVE_BOOKS_MOVE_MARKER), "w", encoding="utf-8") as f:
        json.dump({"files": present, "backup": backup}, f)
    return _finish_live_books_move(hub_dir, dest)


def _unfinished_live_book_moves(hub_dir: str) -> list:
    """The ``live/<broker>/`` folders whose move from the hub folder has a marker."""
    live = os.path.join(hub_dir, LIVE_DATA_SUBDIR)
    try:
        names = sorted(os.listdir(live))
    except OSError:
        return []
    return [
        os.path.join(live, n)
        for n in names
        if os.path.isfile(os.path.join(live, n, LIVE_BOOKS_MOVE_MARKER))
    ]


def _finish_live_books_move(hub_dir: str, dest: str) -> str:
    """Move the books the marker in ``dest`` lists from the hub folder into
    ``dest``, then remove the marker. A book already in ``dest`` was moved."""
    marker = os.path.join(dest, LIVE_BOOKS_MOVE_MARKER)
    with open(marker, encoding="utf-8") as f:
        started = json.load(f)
    present = [n for n in started.get("files", []) if n in LIVE_BOOK_FILES]
    backup = str(started.get("backup", ""))
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
            f"{exchange_name(ts.active_broker)}: {exc}"
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
