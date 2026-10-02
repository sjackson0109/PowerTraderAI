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
from dataclasses import dataclass
from decimal import Decimal
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
from pt_settings_manager import (
    SETTINGS_FILE,
    TRADING_ACTIVE_BROKER_KEY,
    TRADING_MODE_KEY,
    trading_testnet_key,
)

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
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILE)


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


# --- Public quote feed (paper pricing only; never an order call) -------------

_QUOTE_URL = "https://api.binance.com/api/v3/ticker/bookTicker?symbol={symbol}"
_QUOTE_TTL_SECONDS = 2.0
_quote_cache: Dict[str, Tuple[float, Tuple[float, float]]] = {}


def fetch_public_quote(base: str, timeout: float = 3.0) -> Optional[Tuple[float, float]]:
    """(bid, ask) for ``base``/USDT from Binance's public book ticker, or None."""
    now = time.time()
    cached = _quote_cache.get(base)
    if cached and now - cached[0] < _QUOTE_TTL_SECONDS:
        return cached[1]
    try:
        url = _QUOTE_URL.format(symbol=f"{base}USDT")
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        quote = (float(payload["bidPrice"]), float(payload["askPrice"]))
    except (urllib.error.URLError, ValueError, KeyError, TypeError, OSError):
        return None
    if quote[0] <= 0 or quote[1] <= 0:
        return None
    _quote_cache[base] = (now, quote)
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

    Needs no credentials. ``price_feed(base) -> (bid, ask) | None`` supplies
    real prices; without one (or when it returns None) the account's own market
    simulator prices the fills.
    """

    # Offline fallback spread around the simulator price.
    _SIM_HALF_SPREAD = 0.0005

    def __init__(
        self,
        account: Optional[PaperTradingAccount] = None,
        initial_balance: Decimal = Decimal("10000"),
        price_feed: Optional[Callable[[str], Optional[Tuple[float, float]]]] = None,
        state_path: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("", "", **kwargs)
        self.account = account or PaperTradingAccount(initial_balance=initial_balance)
        self._simulator = _AnchoredSimulator()
        self.account.market_simulator = self._simulator
        self._price_feed = price_feed
        self._state_path = state_path
        self._lock = threading.RLock()
        if state_path:
            self.load_state(state_path)

    def get_exchange_name(self) -> str:
        return "paper"

    def is_available_in_region(self, region: str) -> bool:
        return True

    # -- quotes --

    def _quote(self, base: str) -> Tuple[float, float]:
        quote = self._price_feed(base) if self._price_feed else None
        if quote:
            return float(quote[0]), float(quote[1])
        mid = float(self._simulator.get_current_price(base))
        return mid * (1 - self._SIM_HALF_SPREAD), mid * (1 + self._SIM_HALF_SPREAD)

    def get_current_price(self, symbol: str) -> float:
        return self._quote(_base_asset(symbol))[1]

    def get_market_data(self, symbol: str) -> MarketData:
        base = _base_asset(symbol)
        bid, ask = self._quote(base)
        return MarketData(
            symbol=symbol,
            price=(bid + ask) / 2,
            bid=bid,
            ask=ask,
            volume=0.0,
            timestamp=time.time(),
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
            if price is None:
                # Market order: fill at the ask when buying, the bid when selling.
                bid, ask = self._quote(base)
                self._simulator.anchors[base] = Decimal(
                    str(ask if order_side is OrderSide.BUY else bid)
                )
                order_id = self.account.place_order(
                    symbol=base,
                    order_type=OrderType.MARKET,
                    side=order_side,
                    quantity=Decimal(str(amount)),
                )
            else:
                order_id = self.account.place_order(
                    symbol=base,
                    order_type=OrderType.LIMIT,
                    side=order_side,
                    quantity=Decimal(str(amount)),
                    price=Decimal(str(price)),
                )
            self._save_state()
            return self._order_result(order_id)

    def get_balance(self) -> Dict[str, float]:
        with self._lock:
            balances = {PAPER_BALANCE_ASSET: float(self.account.cash_balance)}
            for symbol, position in self.account.positions.items():
                if position.quantity > 0:
                    balances[symbol] = float(position.quantity)
            return balances

    def get_order_status(self, order_id: str) -> OrderResult:
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
    price_feed: Optional[Callable[[str], Optional[Tuple[float, float]]]] = fetch_public_quote,
) -> PaperExchange:
    """(Re)create the process-wide paper exchange. Call once at trader start-up."""
    global _paper_exchange
    with _paper_lock:
        _paper_exchange = PaperExchange(
            initial_balance=initial_balance,
            price_feed=price_feed,
            state_path=state_path,
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
        return OrderTarget(
            mode=TradingMode.PAPER,
            broker=None,
            exchange=get_paper_exchange(),
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
