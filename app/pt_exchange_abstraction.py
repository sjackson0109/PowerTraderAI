"""
Multi-Exchange Trading Platform Abstraction Layer
Supports all major cryptocurrency exchanges with unified interface
"""

import abc
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

import pt_secrets
from market_data.resample import build_candles, build_from
from market_data.timeframes import candle_timeframe_seconds

logger = logging.getLogger("pt_exchange_abstraction")

# Constructor arguments that carry credentials (see pt_secrets.secret_fields).
_CREDENTIAL_KWARGS = ("api_key", "api_secret", "passphrase", "private_key")


class MarketNotFound(RuntimeError):
    """The exchange has no market for the symbol (e.g. Coinbase and XMR).

    Unlike a network error, retrying cannot help, so callers can skip the coin
    instead of retrying for ever."""


def usable_minimum(value: Any) -> Optional[float]:
    """``value`` as a minimum order value: a positive, finite number, else None (a
    connector may answer anything)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if 0.0 < value < float("inf") else None


_DOLLARS = ("USDT", "USDC", "USD")


def dollar_symbol(symbol: str) -> str:
    """``symbol`` in the form the connectors take, ``COIN-USD``. A bare coin
    (``BTC``) and the USDT / USDC forms (``BTCUSDT``, ``BTC-USDT``, ``BTC/USDC``)
    all become ``BTC-USD``: USD, USDT and USDC count as the same dollar (FDS-MX-001
    decision D3). Other quotes are kept (``ETH-BTC``)."""
    text = str(symbol).strip().upper().replace("/", "-").replace("_", "-")
    if "-" in text:
        base, quote = text.split("-", 1)
    else:
        for candidate in _DOLLARS:
            if text.endswith(candidate) and len(text) > len(candidate):
                base, quote = text[: -len(candidate)], candidate
                break
        else:
            return f"{text}-USD"
    return f"{base}-USD" if quote in _DOLLARS else f"{base}-{quote}"


class MarketDataUnavailable(RuntimeError):
    """No connected exchange could give the market data asked for. The message says
    what each exchange answered."""


@dataclass
class MarketStatus:
    """Whether an exchange's market for a coin is trading (``market_status``)."""

    listed: bool  # False: the exchange has no market for the coin
    trading: Optional[bool]  # None when the exchange's answer is not clear
    status: str  # the exchange's own word: TRADING, online, cancel_only, ...
    reason: str = ""


@dataclass
class PriceQuote:
    """Best bid and ask, with the exchange's own time for them where it gives one."""

    bid: float
    ask: float
    quote_ts: Optional[float]  # epoch seconds (UTC) by the exchange's clock, or None


@dataclass
class Sourced:
    """A market-data answer from the exchange layer, and where it came from."""

    value: Any
    exchange: str  # ExchangeType value, e.g. "coinbase"
    pair: str  # that exchange's market, e.g. "BTC-USD"
    primary: bool  # True when the primary exchange answered
    built_from: str = ""  # candles only: the size they were built from, e.g. "1h"


class ExchangeType(Enum):
    """Supported exchange types"""

    # Tier 1 - Existing + Major Additions
    ROBINHOOD = "robinhood"
    KRAKEN = "kraken"
    BINANCE = "binance"
    COINBASE = "coinbase"
    BITSTAMP = "bitstamp"
    BITPANDA = "bitpanda"
    KUCOIN = "kucoin"
    GEMINI = "gemini"
    BYBIT = "bybit"
    OKX = "okx"
    HUOBI = "huobi"
    GATE = "gate"
    BITGET = "bitget"
    MEXC = "mexc"
    BITFINEX = "bitfinex"

    # Major Platform Additions
    CRYPTO_COM = "crypto_com"
    ETORO = "etoro"

    # Asian Market Leaders
    UPBIT = "upbit"
    COINCHECK = "coincheck"

    # Regional Exchanges
    COINDCX = "coindcx"
    WAZIRX = "wazirx"
    LUNO = "luno"
    MERCADO_BITCOIN = "mercado_bitcoin"

    # Derivatives Specialists
    PHEMEX = "phemex"
    BINGX = "bingx"

    # DeFi Protocols
    ONEINCH = "oneinch"
    UNISWAP = "uniswap"
    DYDX = "dydx"
    CURVE = "curve"
    PANCAKESWAP = "pancakeswap"
    JUPITER = "jupiter"
    SUSHISWAP = "sushiswap"
    BALANCER = "balancer"
    PERPETUAL_PROTOCOL = "perpetual_protocol"

    # Institutional/OTC
    CUMBERLAND = "cumberland"
    GENESIS = "genesis"
    B2C2 = "b2c2"

    # Traditional Finance
    INTERACTIVE_BROKERS = "interactive_brokers"
    PLUS500 = "plus500"
    REVOLUT = "revolut"

    # Latin America
    BITSO = "bitso"
    RIPIO = "ripio"
    SATOSHITANGO = "satoshitango"

    # Middle East & Africa
    RAIN = "rain"
    YELLOW_CARD = "yellow_card"
    QUIDAX = "quidax"
    VALR = "valr"

    # Eastern Europe & CIS
    COINSBIT = "coinsbit"
    EXMO = "exmo"
    CEX_IO = "cex_io"

    # Turkey
    BTCTURK = "btcturk"
    PARIBU = "paribu"

    # DeFi Lending & Borrowing
    AAVE = "aave"
    COMPOUND = "compound"
    MAKERDAO = "makerdao"

    # Yield Aggregation
    YEARN_FINANCE = "yearn_finance"
    CONVEX_FINANCE = "convex_finance"
    BEEFY_FINANCE = "beefy_finance"

    # Layer 2 DEXs
    QUICKSWAP = "quickswap"
    SPOOKYSWAP = "spookyswap"
    TRADERJOE = "traderjoe"
    RAYDIUM = "raydium"

    # Derivatives Specialists
    DERIBIT = "deribit"
    LYRA_FINANCE = "lyra_finance"
    DOPEX = "dopex"
    PERP_PROTOCOL = "perp_protocol"
    GMX = "gmx"
    GAINS_NETWORK = "gains_network"

    # Cross-Chain Infrastructure
    HOP_PROTOCOL = "hop_protocol"
    ACROSS_PROTOCOL = "across_protocol"
    SYNAPSE = "synapse"
    LI_FI = "li_fi"
    RANGO = "rango"
    SOCKET = "socket"

    # Specialized Platforms
    POLYMARKET = "polymarket"
    AUGUR = "augur"
    PAXFUL = "paxful"
    LOCALCOINSWAP = "localcoinswap"
    BISQ = "bisq"

    # Staking Platforms
    LIDO_FINANCE = "lido_finance"
    ROCKET_POOL = "rocket_pool"
    MARINADE_FINANCE = "marinade_finance"


@dataclass
class MarketData:
    """Standardized market data structure"""

    symbol: str
    price: float
    bid: float
    ask: float
    volume: float
    timestamp: float
    exchange: str


@dataclass
class OrderResult:
    """Standardized order result structure"""

    order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    amount: float
    price: float
    status: str
    exchange: str
    timestamp: float
    # Why an order was rejected (e.g. "PRICE_UNAVAILABLE"); "" otherwise.
    reason: str = ""
    # Price provenance, set by exchanges that simulate fills (paper):
    # "live" | "stale" | "simulated" | "n/a"; "" when not tracked.
    price_source: str = ""
    quote_ts: Optional[float] = None  # exchange timestamp of the quote (epoch s, UTC)
    age_s: Optional[float] = None  # fetched_ts - quote_ts


class ConnectionStatus(str, Enum):
    """Outcome of a read-only connection test (see ``check_connection``)."""

    OK = "ok"
    # Credentials are malformed; detected locally, nothing was sent.
    INVALID_CREDENTIALS = "invalid_credentials"
    # The exchange rejected the credentials (HTTP 401).
    AUTH_FAILED = "auth_failed"
    # The credentials were accepted but may not do what we need (HTTP 403, or
    # the key lacks view permission).
    PERMISSION_DENIED = "permission_denied"
    # Could not reach the exchange: DNS, TLS, timeout, connection refused.
    NETWORK_ERROR = "network_error"
    # Reached something that did not behave like the exchange API: 404, 429,
    # 5xx, a redirect or an unparseable body.
    ENDPOINT_ERROR = "endpoint_error"
    # No read-only check is implemented for this exchange.
    UNSUPPORTED = "unsupported"


@dataclass
class ConnectionTestResult:
    """Result of ``AbstractExchange.check_connection``. ``message`` is
    user-readable and never contains credentials or tokens."""

    exchange: str
    status: ConnectionStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status is ConnectionStatus.OK


class ExchangeRegion(Enum):
    """Exchange regional availability"""

    US_ONLY = ["robinhood", "gemini"]
    EU_UK = ["kraken", "bitstamp", "bitpanda"]
    GLOBAL = ["binance", "kucoin", "bybit", "okx"]
    US_EU_UK = ["coinbase"]


class AbstractExchange(abc.ABC):
    """Abstract base class for all exchange implementations"""

    # True only for connectors that really read balances and place orders. Most
    # connectors raise NotImplementedError for both and can serve prices only.
    SUPPORTS_LIVE_ORDERS = False

    def __init__(self, api_key: str = "", api_secret: str = "", **kwargs):
        self.api_key = api_key
        self.api_secret = api_secret
        self.exchange_name = self.get_exchange_name()

    def min_order_usd(self, symbol: str) -> Optional[float]:
        """The exchange's minimum order value for ``symbol``, in its quote currency
        (USD or a USD stablecoin), or None when this connector does not know it.
        Connectors that can read it from their exchange override this."""
        return None

    # --- public market data (FDS-MX-001 section 5.1) ------------------------------
    # Optional: a connector that leaves these as they are answers "not supported",
    # and the exchange layer asks the next exchange.

    def market_symbol(self, symbol: str) -> str:
        """This exchange's market for ``symbol`` (``BTC-USD`` is ``BTCUSDT`` on
        Binance)."""
        convert = getattr(self, "_convert_symbol", None)
        return convert(symbol) if callable(convert) else symbol

    def candle_timeframes(self) -> FrozenSet[str]:
        """The candle sizes the exchange serves itself (``1h``, ``1d``, ...); empty
        when this connector reads no candles."""
        return frozenset()

    def max_history_bars(self, tf: str) -> Optional[int]:
        """How many of its most recent ``tf`` bars the exchange serves; None when it
        serves its whole history."""
        return None

    def candles(self, symbol: str, tf: str, start_ms: int, end_ms: int) -> List[list]:
        """``tf`` bars of ``symbol`` opening from ``start_ms`` to ``end_ms``
        (inclusive), oldest first, as ``[open_time_ms, open, high, low, close,
        volume]``. ``tf`` is one of ``candle_timeframes()``. The still-forming bar
        may be included (the exchange layer drops it). Raises MarketNotFound when the
        exchange has no market for the coin."""
        raise NotImplementedError(f"{self.get_exchange_name()} reads no candles")

    def market_status(self, symbol: str) -> Optional[MarketStatus]:
        """Whether the exchange's market for ``symbol`` is trading; None when this
        connector cannot say, or the exchange could not be asked."""
        return None

    def quote(self, symbol: str) -> Optional[PriceQuote]:
        """Best bid and ask for ``symbol``; None when this connector cannot give
        one."""
        return None

    @abc.abstractmethod
    def get_exchange_name(self) -> str:
        """Return the exchange name"""
        pass

    @abc.abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """Get current market price for symbol"""
        pass

    @abc.abstractmethod
    def get_market_data(self, symbol: str) -> MarketData:
        """Get comprehensive market data"""
        pass

    @abc.abstractmethod
    def place_order(
        self, symbol: str, side: str, amount: float, price: Optional[float] = None
    ) -> OrderResult:
        """Place a trading order"""
        pass

    @abc.abstractmethod
    def get_balance(self) -> Dict[str, float]:
        """Get account balances"""
        pass

    @abc.abstractmethod
    def get_order_status(self, order_id: str) -> OrderResult:
        """Get order status"""
        pass

    @abc.abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        pass

    @abc.abstractmethod
    def is_available_in_region(self, region: str) -> bool:
        """Check if exchange is available in region"""
        pass

    def check_connection(self, timeout: float = 10.0) -> ConnectionTestResult:
        """Verify the credentials with ONE read-only authenticated call.

        Implementations must never place, preview or cancel an order. The
        default reports that no check exists rather than claiming success.
        """
        return ConnectionTestResult(
            exchange=self.get_exchange_name(),
            status=ConnectionStatus.UNSUPPORTED,
            message=(
                f"A read-only connection test is not implemented for "
                f"{self.get_exchange_name().title()} yet, so these credentials "
                "were not checked."
            ),
        )


class ExchangeFactory:
    """Factory for creating exchange instances"""

    _exchanges = {}
    _credentials = {}

    @classmethod
    def register_exchange(cls, exchange_type: ExchangeType, exchange_class: type):
        """Register an exchange implementation"""
        cls._exchanges[exchange_type] = exchange_class

    @classmethod
    def _registered(cls) -> dict:
        """The registry, with the connectors loaded. They register themselves when
        pt_exchanges is imported; until something had imported it, the factory
        knew no exchange at all, so its answers depended on import order."""
        if not cls._exchanges:
            try:
                import pt_exchanges  # noqa: F401  (registers the connectors)
            except ImportError:  # e.g. requests missing: no connectors
                pass
        return cls._exchanges

    @classmethod
    def get_exchange_class(cls, exchange_type: ExchangeType) -> Optional[type]:
        """The registered implementation class, or None. Unlike ``get_exchange``
        this does not look up any stored credentials."""
        return cls._registered().get(exchange_type)

    @classmethod
    def load_credentials(cls, config_path: str = None):
        """Load per-exchange constructor options (e.g. ``sandbox``) from
        ``exchange_config.json``. Credentials are NOT read from it: they come
        from ``pt_secrets`` only. Credential fields found in the file are
        ignored with a warning."""
        if config_path is None:
            import pt_paths

            config_path = pt_paths.exchange_config_file()

        if not os.path.exists(config_path):
            return
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        options = {}
        for exchange, settings in (data.items() if isinstance(data, dict) else ()):
            if not isinstance(settings, dict):
                continue
            kept = {}
            for key, value in settings.items():
                if pt_secrets.is_secret_key(key):
                    if value:
                        logger.warning(
                            "%s holds a credential field (%s.%s); it is ignored. "
                            "Credentials are read from environment variables or the OS "
                            "keyring only (run pt_migrate.py to move it).",
                            os.path.basename(config_path),
                            exchange,
                            key,
                        )
                    continue
                kept[key] = value
            options[exchange] = kept
        cls._credentials = options

    @classmethod
    def get_exchange(cls, exchange_type: ExchangeType, **kwargs) -> AbstractExchange:
        """Create an exchange instance.

        Credentials passed in ``kwargs`` (``api_key``, ``api_secret``, ...) are
        used as given. Otherwise they come from ``pt_secrets`` (environment
        variables, then the OS keyring). The two are never combined, so a
        credential supplied in two places can no longer raise "multiple values
        for keyword argument" and silently drop the exchange.
        """
        if exchange_type not in cls._registered():
            raise ValueError(f"Exchange {exchange_type.value} not registered")

        options = dict(cls._credentials.get(exchange_type.value, {}))
        if any(key in kwargs for key in _CREDENTIAL_KWARGS):
            creds = {}
        else:
            creds = cls._get_credentials(exchange_type)
            # Allow public access for market data feeds (no credentials needed)
            if not creds:
                print(
                    f"Using public access for {exchange_type.value} (market data only)"
                )
                creds = {}

        exchange_class = cls._exchanges[exchange_type]
        return exchange_class(**{**options, **creds, **kwargs})

    @classmethod
    def _get_credentials(cls, exchange_type: ExchangeType) -> Optional[Dict[str, str]]:
        """Credentials from ``pt_secrets``: environment variables first, then
        the OS keyring. ``exchange_config.json`` never supplies credentials."""
        try:
            return pt_secrets.get_credentials(exchange_type.value)
        except pt_secrets.SecretsError:
            return None

    @classmethod
    def get_available_exchanges(cls, region: str = None) -> List[ExchangeType]:
        """Get list of available exchanges for region"""
        available = []
        registered = cls._registered()
        for exchange_type in ExchangeType:
            if exchange_type in registered:
                if region is None:
                    available.append(exchange_type)
                else:
                    # Check regional availability
                    if (
                        region.upper() in ["US", "USA"]
                        and exchange_type.value
                        in ExchangeRegion.US_ONLY.value
                        + ExchangeRegion.US_EU_UK.value
                        + ExchangeRegion.GLOBAL.value
                    ):
                        available.append(exchange_type)
                    elif (
                        region.upper() in ["EU", "UK", "EUROPE"]
                        and exchange_type.value
                        in ExchangeRegion.EU_UK.value
                        + ExchangeRegion.US_EU_UK.value
                        + ExchangeRegion.GLOBAL.value
                    ):
                        available.append(exchange_type)
                    elif region.upper() == "GLOBAL":
                        available.append(exchange_type)
        return available


class ExchangeManager:
    """Manages multiple exchange connections"""

    def __init__(self):
        self.exchanges: Dict[ExchangeType, AbstractExchange] = {}
        self.primary_exchange: Optional[ExchangeType] = None

    def add_exchange(self, exchange_type: ExchangeType, **kwargs):
        """Add an exchange connection"""
        try:
            exchange = ExchangeFactory.get_exchange(exchange_type, **kwargs)
            self.exchanges[exchange_type] = exchange

            # Set as primary if first exchange
            if self.primary_exchange is None:
                self.primary_exchange = exchange_type

            return True
        except Exception as e:
            print(f"Failed to add {exchange_type.value}: {e}")
            return False

    def set_primary_exchange(self, exchange_type: ExchangeType):
        """Set primary exchange for trading"""
        if exchange_type in self.exchanges:
            self.primary_exchange = exchange_type
        else:
            raise ValueError(f"Exchange {exchange_type.value} not connected")

    def get_primary_exchange(self) -> Optional[AbstractExchange]:
        """Get primary exchange instance"""
        if self.primary_exchange and self.primary_exchange in self.exchanges:
            return self.exchanges[self.primary_exchange]
        return None

    def get_current_price(
        self, symbol: str, exchange_type: ExchangeType = None
    ) -> float:
        """Get current price from specified exchange or primary"""
        if exchange_type is None:
            exchange_type = self.primary_exchange

        if exchange_type not in self.exchanges:
            raise ValueError(f"Exchange {exchange_type.value} not connected")

        return self.exchanges[exchange_type].get_current_price(symbol)

    def _ordered(self) -> List[Tuple[ExchangeType, AbstractExchange]]:
        """The connected exchanges, primary first, then the others in the order they
        were connected (the Settings order)."""
        return sorted(
            self.exchanges.items(), key=lambda item: item[0] != self.primary_exchange
        )

    def _sourced(self, value, exchange_type, exchange, symbol, built_from=""):
        return Sourced(
            value=value,
            exchange=exchange_type.value,
            pair=exchange.market_symbol(symbol),
            primary=exchange_type == self.primary_exchange,
            built_from=built_from,
        )

    def min_order_usd(self, symbol: str) -> Optional[float]:
        """The minimum order value for ``symbol``: the primary exchange's; when it does
        not state one, the first other connected exchange's that does (in the order
        they were connected). None when no exchange states one."""
        symbol = dollar_symbol(symbol)
        for exchange_type, exchange in self._ordered():
            try:
                minimum = usable_minimum(exchange.min_order_usd(symbol))
            except Exception as exc:
                logger.debug(f"No minimum order from {exchange_type.value}: {exc}")
                continue
            if minimum is not None:
                return minimum
        return None

    def candles(
        self,
        symbol: str,
        tf: str,
        start_ms: int,
        end_ms: int,
        now_ms: Optional[int] = None,
    ) -> Sourced:
        """Closed ``tf`` bars of ``symbol`` opening from ``start_ms`` to ``end_ms``
        (inclusive), oldest first, as ``[open_time_ms, open, high, low, close,
        volume]``, with the exchange and pair that served them.

        The primary exchange is asked first, then the others in order. An exchange
        is passed over when it serves no ``tf`` candles (and none to build them
        from), when it cannot reach back to ``start_ms``, when it has no market for
        the coin, or when it fails. One exchange serves the whole series: bars from
        two exchanges are never mixed. A size the exchange does not serve is built
        from a smaller one it does (``Sourced.built_from``).

        Raises MarketNotFound when every exchange asked has no market for the coin,
        otherwise MarketDataUnavailable with each exchange's answer."""
        symbol = dollar_symbol(symbol)
        now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        step_ms = candle_timeframe_seconds(tf) * 1000
        reasons: List[str] = []
        not_found = 0
        for exchange_type, exchange in self._ordered():
            name = exchange_type.value
            native = exchange.candle_timeframes()
            fetch_tf = tf if tf in native else build_from(tf, native)
            if fetch_tf is None:
                reasons.append(f"{name}: no {tf} candles")
                continue
            fetch_step_ms = candle_timeframe_seconds(fetch_tf) * 1000
            limit = exchange.max_history_bars(fetch_tf)
            if limit is not None:
                earliest = (now_ms // fetch_step_ms - limit + 1) * fetch_step_ms
                if start_ms < earliest:
                    reasons.append(
                        f"{name}: serves only its latest {limit} {fetch_tf} bars"
                    )
                    continue
            # the last tf bar wanted, and every smaller bar it is built from
            fetch_end = end_ms + step_ms - fetch_step_ms
            try:
                rows = exchange.candles(symbol, fetch_tf, start_ms, fetch_end)
            except MarketNotFound as exc:
                not_found += 1
                reasons.append(f"{name}: {exc}")
                continue
            except Exception as exc:
                reasons.append(f"{name}: {type(exc).__name__}: {exc}")
                continue
            if fetch_tf != tf:
                rows = build_candles(rows, fetch_tf, tf)
            bars = {
                int(r[0]): r
                for r in rows
                if start_ms <= int(r[0]) <= end_ms and int(r[0]) + step_ms <= now_ms
            }
            series = [bars[t] for t in sorted(bars)]
            built = fetch_tf if fetch_tf != tf else ""
            return self._sourced(series, exchange_type, exchange, symbol, built)
        if reasons and not_found == len(reasons):
            raise MarketNotFound(
                f"No exchange has a market for {symbol}: " + "; ".join(reasons)
            )
        raise MarketDataUnavailable(
            f"No exchange gave {tf} candles for {symbol}: "
            + ("; ".join(reasons) or "no exchange connected")
        )

    def market_status(self, symbol: str) -> Optional[Sourced]:
        """Whether ``symbol``'s market is trading, from the primary exchange; when the
        primary does not list the coin or cannot say, from the next exchange that
        lists it. An exchange that does not list the coin is the answer only when
        no exchange lists it. None when no exchange could say."""
        symbol = dollar_symbol(symbol)
        not_listed: Optional[Sourced] = None
        for exchange_type, exchange in self._ordered():
            try:
                status = exchange.market_status(symbol)
            except Exception as exc:
                logger.debug(f"No market status from {exchange_type.value}: {exc}")
                continue
            if status is None:
                continue
            answer = self._sourced(status, exchange_type, exchange, symbol)
            if status.listed:
                return answer
            not_listed = not_listed or answer
        return not_listed

    def quote(self, symbol: str) -> Optional[Sourced]:
        """Best bid and ask for ``symbol`` (a PriceQuote), from the primary exchange,
        else the next that gives one. None when none does."""
        symbol = dollar_symbol(symbol)
        for exchange_type, exchange in self._ordered():
            try:
                quote = exchange.quote(symbol)
            except Exception as exc:
                logger.debug(f"No quote from {exchange_type.value}: {exc}")
                continue
            if quote is not None and quote.bid > 0 and quote.ask > 0:
                return self._sourced(quote, exchange_type, exchange, symbol)
        return None

    def get_best_price(
        self, symbol: str, side: str = "buy"
    ) -> Tuple[float, ExchangeType]:
        """Get best price across all connected exchanges"""
        prices = []

        for exchange_type, exchange in self.exchanges.items():
            try:
                market_data = exchange.get_market_data(symbol)
                price = market_data.ask if side == "buy" else market_data.bid
                prices.append((price, exchange_type))
            except Exception:
                continue

        if not prices:
            raise ValueError(f"No price data available for {symbol}")

        if side == "buy":
            return min(prices)  # Best ask (lowest price to buy)
        else:
            return max(prices)  # Best bid (highest price to sell)

    def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        exchange_type: ExchangeType = None,
    ) -> OrderResult:
        """Place order on specified exchange or primary"""
        if exchange_type is None:
            exchange_type = self.primary_exchange

        if exchange_type not in self.exchanges:
            raise ValueError(f"Exchange {exchange_type.value} not connected")

        return self.exchanges[exchange_type].place_order(symbol, side, amount, price)

    def get_total_balance(self) -> Dict[str, float]:
        """Get combined balances across all exchanges"""
        total_balances = {}

        for exchange_type, exchange in self.exchanges.items():
            try:
                balances = exchange.get_balance()
                for currency, amount in balances.items():
                    if currency in total_balances:
                        total_balances[currency] += amount
                    else:
                        total_balances[currency] = amount
            except Exception as e:
                print(f"Failed to get balance from {exchange_type.value}: {e}")

        return total_balances
