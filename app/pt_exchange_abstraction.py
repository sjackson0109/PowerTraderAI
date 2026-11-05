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
from market_data.timeframes import bar_open_floor, candle_timeframe_seconds

logger = logging.getLogger("pt_exchange_abstraction")

# Constructor arguments that carry credentials (see pt_secrets.secret_fields).
_CREDENTIAL_KWARGS = ("api_key", "api_secret", "passphrase", "private_key")

# A ticker without the 24-hour change gets it from this size of bar, the one open
# 24 hours ago (ExchangeManager.ticker): the price then, to within its length.
DAY_AGO_TF = "5m"
DAY_SECONDS = 86400


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
class Ticker:
    """An exchange's ticker for one market: the last trade price, the best bid and
    ask, and the last 24 hours' volume (in the coin), high, low and change (in the
    quote currency, and in percent of the price 24 hours ago). A field the exchange
    does not give is None, never 0."""

    last: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    volume_24h: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    change_24h: Optional[float] = None
    change_24h_pct: Optional[float] = None
    ticker_ts: Optional[float] = None  # epoch seconds (UTC) by the exchange's clock

    @property
    def price(self) -> Optional[float]:
        """The last trade price; with none, the middle of the bid and ask."""
        if self.last is not None and self.last > 0:
            return self.last
        if self.bid and self.ask and self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return None

    def set_change_from(self, reference: Optional[float]) -> None:
        """The 24-hour change: the price now against ``reference``, the price 24
        hours ago (left None without both)."""
        price = self.price
        if price is None or not reference or reference <= 0:
            return
        self.change_24h = price - reference
        self.change_24h_pct = (price - reference) / reference * 100.0


@dataclass
class OrderBookSnapshot:
    """An exchange's order book for one market, as (price, quantity) levels: bids
    from the highest price down, asks from the lowest up."""

    bids: List[Tuple[float, float]]
    asks: List[Tuple[float, float]]
    book_ts: Optional[float] = None  # epoch seconds (UTC) by the exchange's clock


def book_levels(rows, depth: int, descending: bool) -> List[Tuple[float, float]]:
    """(price, quantity) levels from an exchange's rows (``[price, quantity, ...]``
    lists, or ``{"price", "size"}`` objects): positive quantities only, best price
    first, at most ``depth``."""
    levels = []
    for row in rows or ():
        try:
            if isinstance(row, dict):
                price, quantity = float(row["price"]), float(row["size"])
            else:
                price, quantity = float(row[0]), float(row[1])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if price > 0 and quantity > 0:
            levels.append((price, quantity))
    levels.sort(key=lambda level: level[0], reverse=descending)
    return levels[: max(0, int(depth))]


@dataclass
class Sourced:
    """A market-data answer from the exchange layer, and where it came from."""

    value: Any
    exchange: str  # ExchangeType value, e.g. "coinbase"
    pair: str  # that exchange's market, e.g. "BTC-USD"
    primary: bool  # True when the primary exchange answered
    built_from: str = ""  # candles only: the size they were built from, e.g. "1h"


@dataclass(frozen=True)
class TradingFees:
    """An exchange's trading fee rates for one market, as fractions of an order's
    value (0.006 is 0.6%). A maker order adds to the order book and a taker order takes
    from it: a market order pays the taker rate, and a limit order is counted as a
    maker order. ``exchange`` is whose rates they are (an ExchangeType value; "" when
    no exchange is known) and ``source`` where they came from: "exchange" (read from
    the exchange), "default" (its published standard rates, DEFAULT_TRADING_FEES) or
    "paper" (the paper account's own rate, when no exchange gave any)."""

    maker: float
    taker: float
    exchange: str
    source: str

    def for_order(self, order_type: str = "market") -> Tuple[str, float]:
        """("maker", rate) for a limit order; ("taker", rate) for a market order and
        any other."""
        if str(order_type).strip().lower() == "limit":
            return "maker", self.maker
        return "taker", self.taker


def usable_fees(value: Any) -> Optional[TradingFees]:
    """``value`` as trading fees: a TradingFees whose two rates are numbers from 0 up
    to (not including) 1, else None (a connector may answer anything)."""
    if not isinstance(value, TradingFees):
        return None
    for rate in (value.maker, value.taker):
        if isinstance(rate, bool) or not isinstance(rate, (int, float)):
            return None
        if not 0.0 <= rate < 1.0:
            return None
    return value


# Each exchange's published standard-tier rates (maker, taker): the tier of an account
# with no 30-day trading volume. Used when its own rates cannot be read from it (no API
# key, or no answer), with a warning. Sources, spot trading:
#   coinbase: help.coinbase.com, "Coinbase Advanced trading fees", $0-1K tier
#   kraken:   kraken.com/features/fee-schedule, Kraken Pro, $0-10K tier
#   binance:  binance.com/en/fee/schedule, Regular User (VIP 0)
#   kucoin:   kucoin.com/vip/privilege, LV 0, class A coins
DEFAULT_TRADING_FEES: Dict[str, Tuple[float, float]] = {
    "coinbase": (0.0060, 0.0120),
    "kraken": (0.0025, 0.0040),
    "binance": (0.0010, 0.0010),
    "kucoin": (0.0010, 0.0010),
}
# The warning that standard rates are used is logged once an hour per exchange
DEFAULT_FEES_WARNING_SECONDS = 3600.0
_default_fees_warned: Dict[str, float] = {}


def default_trading_fees(exchange: Any) -> Optional[TradingFees]:
    """``exchange``'s published standard rates (DEFAULT_TRADING_FEES) as TradingFees
    with source "default", or None when none are stored. Logs a warning that they are
    used in place of the exchange's own rates (once an hour per exchange)."""
    key = str(getattr(exchange, "value", exchange) or "").strip().lower()
    rates = DEFAULT_TRADING_FEES.get(key)
    if rates is None:
        return None
    now = time.time()
    if now - _default_fees_warned.get(key, 0.0) >= DEFAULT_FEES_WARNING_SECONDS:
        _default_fees_warned[key] = now
        logger.warning(
            f"{exchange_name(key)} trading fees could not be read from the exchange; "
            f"using its standard rates: maker {rates[0]:.2%}, taker {rates[1]:.2%}"
        )
    return TradingFees(maker=rates[0], taker=rates[1], exchange=key, source="default")


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


# The name an exchange goes by on screen, where it is not its id with each word
# capitalised ("yellow_card" -> "Yellow Card"): the setup guides' spelling
EXCHANGE_NAMES: Dict[str, str] = {
    "bingx": "BingX",
    "btcturk": "BtcTurk",
    "cex_io": "CEX.IO",
    "coindcx": "CoinDCX",
    "crypto_com": "Crypto.com",
    "dydx": "dYdX",
    "etoro": "eToro",
    "exmo": "EXMO",
    "gate": "Gate.io",
    "gmx": "GMX",
    "kucoin": "KuCoin",
    "li_fi": "LI.FI",
    "localcoinswap": "LocalCoinSwap",
    "makerdao": "MakerDAO",
    "mexc": "MEXC",
    "okx": "OKX",
    "oneinch": "1inch",
    "pancakeswap": "PancakeSwap",
    "quickswap": "QuickSwap",
    "satoshitango": "SatoshiTango",
    "spookyswap": "SpookySwap",
    "sushiswap": "SushiSwap",
    "traderjoe": "Trader Joe",
    "valr": "VALR",
    "wazirx": "WazirX",
}


def exchange_name(exchange: Any) -> str:
    """The name an exchange goes by on screen ("kucoin" -> "KuCoin"), from its id
    or its ``ExchangeType``; "" for none."""
    key = str(getattr(exchange, "value", exchange) or "").strip().lower()
    return EXCHANGE_NAMES.get(key) or key.replace("_", " ").title()


def exchange_id(name: str) -> str:
    """The id behind a name ``exchange_name`` gives ("KuCoin" -> "kucoin"); an id
    comes back as it is."""
    text = str(name or "").strip().lower()
    for key, shown in EXCHANGE_NAMES.items():
        if shown.lower() == text:
            return key
    return text.replace(" ", "_")


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
    price_exchange: str = ""  # the exchange whose quote priced the fill (paper)
    # The exchange's own numbers for a fill, in the quote currency, when it reports
    # them (None otherwise): the fee charged and the value filled before fees.
    fee: Optional[float] = None
    filled_value: Optional[float] = None
    # True when a "filled" order stopped part-way (a market IOC order can): only
    # ``amount`` filled and the rest of the order was cancelled.
    partial: bool = False
    # How the fee was worked out, where the exchange says (paper fills do): its
    # currency, the rate charged (a fraction of ``filled_value``), "maker" or
    # "taker", and whose rates they were and from where (TradingFees.exchange and
    # .source).
    fee_currency: str = ""
    fee_rate: Optional[float] = None
    fee_type: str = ""
    fee_exchange: str = ""
    fee_source: str = ""
    # An OCO order's own orders on the exchange: "take_profit" and "stop" -> the
    # exchange's id for each (empty for any other order)
    legs: Dict[str, str] = field(default_factory=dict)


# Order kinds beyond a market order. A connector places the ones its exchange has as
# the exchange's own orders (AbstractExchange.native_order_kinds); Order Management
# watches the price itself for the others.
LIMIT_ORDER = "limit"
STOP_LIMIT_ORDER = "stop_limit"
TRAILING_STOP_ORDER = "trailing_stop"
OCO_ORDER = "oco"
ORDER_KINDS = (LIMIT_ORDER, STOP_LIMIT_ORDER, TRAILING_STOP_ORDER, OCO_ORDER)


@dataclass(frozen=True)
class OrderRequest:
    """An order beyond a market order, for ``AbstractExchange.place_native_order``.

    ``kind`` is one of ORDER_KINDS, ``symbol`` the ``COIN-USD`` form the connectors
    take, ``side`` "buy" or "sell" and ``amount`` in coins. A limit order has
    ``price``. A stop-limit order has ``stop_price``, the price that places it, and
    ``price``, its limit. A trailing stop has ``trail_pct``: it follows the best
    price since it was placed (the highest for a sell, the lowest for a buy) at that
    distance, in percent, and becomes a market order when the price comes back to
    it. An OCO order has ``price``, its take-profit limit, and ``stop_price``, its
    stop (a market order once reached): when one fills the other is cancelled."""

    kind: str
    symbol: str
    side: str
    amount: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    trail_pct: Optional[float] = None
    client_order_id: Optional[str] = None


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

    # Requests a second the exchange allows from one IP address, from its own
    # documentation. Every PowerTrader process on the computer counts against it
    # (``rate_limits``); trading_config.json can set another figure per exchange
    # (Configure Exchange APIs). This default is for an exchange whose connector
    # gives no figure.
    requests_per_second: float = 5.0

    def __init__(self, api_key: str = "", api_secret: str = "", **kwargs):
        self.api_key = api_key
        self.api_secret = api_secret
        self.exchange_name = self.get_exchange_name()

    def wait_for_request_slot(self) -> None:
        """Return once one more request to this exchange keeps every PowerTrader
        process on this computer within the exchange's limit."""
        import rate_limits

        rate_limits.wait(self.get_exchange_name(), self.requests_per_second)

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

    # --- trading fees ----------------------------------------------------------------

    def trading_fees(self, symbol: str) -> Optional[TradingFees]:
        """The maker and taker fee rates an order on ``symbol`` pays (TradingFees).
        Here: the exchange's published standard rates (``default_trading_fees``, which
        logs a warning), or None when none are stored. A connector that can read its
        exchange's rates overrides this, and falls back to it when they cannot be
        read."""
        return default_trading_fees(self.get_exchange_name())

    def market_status(self, symbol: str) -> Optional[MarketStatus]:
        """Whether the exchange's market for ``symbol`` is trading; None when this
        connector cannot say, or the exchange could not be asked."""
        return None

    def quote(self, symbol: str) -> Optional[PriceQuote]:
        """Best bid and ask for ``symbol``; None when this connector cannot give
        one."""
        return None

    def ticker(self, symbol: str) -> Optional[Ticker]:
        """The last price, best bid and ask, and the last 24 hours' volume, high, low
        and change for ``symbol``, from the exchange's own 24-hour ticker. This
        default has only the bid and ask of ``quote`` (the exchange layer adds the
        change from the candle cache); None when there is no quote either. Raises
        MarketNotFound when the exchange has no market for the coin, and passes on
        any other error, which the market data feed counts."""
        quote = self.quote(symbol)
        if quote is None:
            return None
        return Ticker(None, quote.bid, quote.ask, ticker_ts=quote.quote_ts)

    def order_book(self, symbol: str, depth: int = 20) -> Optional[OrderBookSnapshot]:
        """The ``depth`` best bids and asks of ``symbol``'s order book, from the
        exchange's public order book; None when this connector reads none. Raises
        MarketNotFound when the exchange has no market for the coin, and passes on
        any other error."""
        return None

    # --- orders beyond market orders -------------------------------------------------
    # Optional: a connector that leaves these as they are places market orders only,
    # and Order Management watches the price for the other kinds.

    def native_order_kinds(self) -> FrozenSet[str]:
        """The ORDER_KINDS this connector places as its exchange's own orders."""
        return frozenset()

    def supports_native_order(self, request: OrderRequest) -> bool:
        """Whether ``request`` can be placed as the exchange's own order: a kind the
        exchange has, with values it takes."""
        return request.kind in self.native_order_kinds()

    def place_native_order(self, request: OrderRequest) -> OrderResult:
        """Place ``request`` as the exchange's own order. The OrderResult has the
        exchange's order id (an OCO order's two orders in ``legs``), or status
        "rejected" and the reason when it was not created. Raises
        NotImplementedError for a kind this connector does not place."""
        raise NotImplementedError(
            f"{exchange_name(self.get_exchange_name())} places no {request.kind} orders"
        )

    def native_order_status(self, order_id: str) -> OrderResult:
        """The state of an order ``place_native_order`` placed (or of one of an OCO
        order's ``legs``)."""
        return self.get_order_status(order_id)

    def cancel_native_order(self, order_id: str) -> bool:
        """Cancel an order ``place_native_order`` placed; for an OCO order, its id
        cancels both of its orders. True when the exchange cancelled it."""
        return self.cancel_order(order_id)

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
    def market_data_exchanges(cls) -> List[str]:
        """The exchanges whose connector reads public market data (prices and
        candles), in alphabetical order: the ones that can be the primary exchange."""
        names = [
            exchange_type.value
            for exchange_type, exchange_class in cls._registered().items()
            if exchange_class.candle_timeframes
            is not AbstractExchange.candle_timeframes
        ]
        return sorted(names)

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
        # (exchange, market) -> (bar open, its open price): the price 24 hours ago
        self._day_ago: Dict[Tuple[str, str], Tuple[int, Optional[float]]] = {}

    def add_exchange(self, exchange_type: ExchangeType, **kwargs):
        """Add an exchange connection"""
        try:
            exchange = ExchangeFactory.get_exchange(exchange_type, **kwargs)
            self.exchanges[exchange_type] = exchange

            # The first exchange is the primary until one is chosen. A chosen primary
            # that cannot connect is not replaced by another: MultiExchangeManager
            # then leaves the primary unset (the others serve, in Settings order).
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
        """Current price from ``exchange_type``, else the primary exchange; with no
        primary connected, from the first connected exchange in Settings order."""
        if exchange_type is None:
            exchange_type = self.primary_exchange
        if exchange_type is None:
            ordered = self._ordered()
            if not ordered:
                raise ValueError("No exchange connected")
            exchange_type = ordered[0][0]

        if exchange_type not in self.exchanges:
            raise ValueError(f"Exchange {exchange_type.value} not connected")

        return self.exchanges[exchange_type].get_current_price(symbol)

    def _ordered(self) -> List[Tuple[ExchangeType, AbstractExchange]]:
        """The connected exchanges, primary first, then the others in the order they
        were connected (the Settings order)."""
        return sorted(
            self.exchanges.items(), key=lambda item: item[0] != self.primary_exchange
        )

    def exchange_names(self) -> List[str]:
        """The connected exchanges' names, primary first, then the Settings order."""
        return [exchange_type.value for exchange_type, _ in self._ordered()]

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
        only: Optional[str] = None,
        closed_only: bool = True,
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

        ``only`` asks that one exchange and no other (a cached series is topped up
        from the exchange it came from). ``closed_only=False`` keeps the bar still
        forming too, where the exchange serves that size itself (a chart shows it; a
        built size has no forming bar, as its group is not complete).

        Raises MarketNotFound when every exchange asked has no market for the coin,
        otherwise MarketDataUnavailable with each exchange's answer."""
        symbol = dollar_symbol(symbol)
        now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        step_ms = candle_timeframe_seconds(tf) * 1000
        reasons: List[str] = []
        not_found = 0
        for exchange_type, exchange in self._ordered():
            name = exchange_type.value
            if only is not None and name != only:
                continue
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
            last_open = now_ms - step_ms if closed_only else now_ms
            bars = {
                int(r[0]): r
                for r in rows
                if start_ms <= int(r[0]) <= min(end_ms, last_open)
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

    def trading_fees(
        self, symbol: str, only: Optional[str] = None
    ) -> Optional[Sourced]:
        """The maker and taker fee rates for ``symbol`` (a TradingFees), from the primary
        exchange, else the next that gives them; ``only`` asks that one exchange (the
        one whose quote priced a fill, say). Each exchange answers with the rates it
        reads from the exchange, else its published standard rates
        (``TradingFees.source`` says which). None when no exchange has either."""
        symbol = dollar_symbol(symbol)
        for exchange_type, exchange in self._ordered():
            name = exchange_type.value
            if only is not None and name != only:
                continue
            try:
                fees = usable_fees(exchange.trading_fees(symbol))
            except Exception as exc:
                logger.debug(f"No trading fees from {name}: {exc}")
                fees = None
            fees = fees or default_trading_fees(name)
            if fees is not None:
                return self._sourced(fees, exchange_type, exchange, symbol)
        return None

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

    def ticker(
        self, symbol: str, only: Optional[str] = None, now: Optional[float] = None
    ) -> Sourced:
        """A Ticker for ``symbol``, from the primary exchange, else the next that
        gives one; ``only`` asks that one exchange and no other. A ticker without the
        24-hour change (an exchange with no 24-hour ticker, or one whose day opens at
        midnight) gets it from the candle cache: the price now against the open of
        that exchange's ``DAY_AGO_TF`` bar holding the moment 24 hours before ``now``
        (default: the clock).

        Raises MarketNotFound when no exchange asked has a market for the coin,
        otherwise MarketDataUnavailable with each exchange's answer."""
        symbol = dollar_symbol(symbol)
        now = time.time() if now is None else float(now)
        reasons: List[str] = []
        not_found = 0
        for exchange_type, exchange in self._ordered():
            name = exchange_type.value
            if only is not None and name != only:
                continue
            try:
                ticker = exchange.ticker(symbol)
            except MarketNotFound as exc:
                not_found += 1
                reasons.append(f"{name}: {exc}")
                continue
            except Exception as exc:
                reasons.append(f"{name}: {type(exc).__name__}: {exc}")
                continue
            if ticker is None or ticker.price is None:
                reasons.append(f"{name}: no ticker")
                continue
            if ticker.change_24h is None:
                ticker.set_change_from(self._price_a_day_ago(name, symbol, now))
            return self._sourced(ticker, exchange_type, exchange, symbol)
        if reasons and not_found == len(reasons):
            raise MarketNotFound(
                f"No exchange has a market for {symbol}: " + "; ".join(reasons)
            )
        raise MarketDataUnavailable(
            f"No exchange gave a ticker for {symbol}: "
            + ("; ".join(reasons) or "no exchange connected")
        )

    def _price_a_day_ago(self, name: str, symbol: str, now: float) -> Optional[float]:
        """The open of ``name``'s ``DAY_AGO_TF`` bar holding the moment 24 hours
        before ``now``, read through the candle cache (that exchange's own); None
        when neither has it. Asked once per bar and market."""
        opened = bar_open_floor(int(now) - DAY_SECONDS, DAY_AGO_TF)
        memo = self._day_ago.get((name, symbol))
        if memo is not None and memo[0] == opened:
            return memo[1]
        price = None
        try:
            import pandas as pd
            from market_data.candles import exchange_candles

            step = candle_timeframe_seconds(DAY_AGO_TF)
            bars = exchange_candles(
                symbol,
                DAY_AGO_TF,
                pd.Timestamp(opened, unit="s", tz="UTC"),
                pd.Timestamp(opened + step, unit="s", tz="UTC"),
                now=pd.Timestamp(now, unit="s", tz="UTC"),
                manager=self,
                exchanges=[name],
            )
            if len(bars):
                price = float(bars["open"].iloc[0])
        except Exception as exc:
            logger.debug(f"No {DAY_AGO_TF} bar a day ago from {name}: {exc}")
        self._day_ago[(name, symbol)] = (opened, price)
        return price

    def order_book(
        self, symbol: str, depth: int = 20, only: Optional[str] = None
    ) -> Sourced:
        """The ``depth`` best bids and asks of ``symbol`` (an OrderBookSnapshot), from
        the primary exchange, else the next that gives them; ``only`` asks that one
        exchange and no other.

        Raises MarketNotFound when no exchange asked has a market for the coin,
        otherwise MarketDataUnavailable with each exchange's answer."""
        symbol = dollar_symbol(symbol)
        reasons: List[str] = []
        not_found = 0
        for exchange_type, exchange in self._ordered():
            name = exchange_type.value
            if only is not None and name != only:
                continue
            try:
                book = exchange.order_book(symbol, depth)
            except MarketNotFound as exc:
                not_found += 1
                reasons.append(f"{name}: {exc}")
                continue
            except Exception as exc:
                reasons.append(f"{name}: {type(exc).__name__}: {exc}")
                continue
            if book is None:
                reasons.append(f"{name}: reads no order book")
                continue
            return self._sourced(book, exchange_type, exchange, symbol)
        if reasons and not_found == len(reasons):
            raise MarketNotFound(
                f"No exchange has a market for {symbol}: " + "; ".join(reasons)
            )
        raise MarketDataUnavailable(
            f"No exchange gave an order book for {symbol}: "
            + ("; ".join(reasons) or "no exchange connected")
        )

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

    # No place_order here: every order goes through the trading-mode gate
    # (trading_mode.resolve_order_target) to the broker chosen in Trading Mode.

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
