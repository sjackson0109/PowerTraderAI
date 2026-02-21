"""
Multi-Exchange Trading Platform Abstraction Layer
Supports all major cryptocurrency exchanges with unified interface
"""
import abc
import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


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


class ExchangeRegion(Enum):
    """Exchange regional availability"""

    US_ONLY = ["robinhood", "gemini"]
    EU_UK = ["kraken", "bitstamp", "bitpanda"]
    GLOBAL = ["binance", "kucoin", "bybit", "okx"]
    US_EU_UK = ["coinbase"]


class AbstractExchange(abc.ABC):
    """Abstract base class for all exchange implementations"""

    def __init__(self, api_key: str, api_secret: str, **kwargs):
        self.api_key = api_key
        self.api_secret = api_secret
        self.exchange_name = self.get_exchange_name()

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


class ExchangeFactory:
    """Factory for creating exchange instances"""

    _exchanges = {}
    _credentials = {}

    @classmethod
    def register_exchange(cls, exchange_type: ExchangeType, exchange_class: type):
        """Register an exchange implementation"""
        cls._exchanges[exchange_type] = exchange_class

    @classmethod
    def load_credentials(cls, config_path: str = None):
        """Load credentials for all exchanges from config"""
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(__file__), "exchange_config.json"
            )

        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                cls._credentials = json.load(f)

    @classmethod
    def get_exchange(cls, exchange_type: ExchangeType, **kwargs) -> AbstractExchange:
        """Create exchange instance with credentials"""
        if exchange_type not in cls._exchanges:
            raise ValueError(f"Exchange {exchange_type.value} not registered")

        # Get credentials from config or environment
        creds = cls._get_credentials(exchange_type)
        if not creds:
            raise ValueError(f"No credentials found for {exchange_type.value}")

        exchange_class = cls._exchanges[exchange_type]
        return exchange_class(**creds, **kwargs)

    @classmethod
    def _get_credentials(cls, exchange_type: ExchangeType) -> Optional[Dict[str, str]]:
        """Get credentials for exchange from config or environment"""
        exchange_name = exchange_type.value.upper()

        # Try environment variables first
        api_key = os.environ.get(f"POWERTRADER_{exchange_name}_API_KEY")
        api_secret = os.environ.get(f"POWERTRADER_{exchange_name}_API_SECRET")

        if api_key and api_secret:
            return {"api_key": api_key, "api_secret": api_secret}

        # Try config file
        if exchange_type.value in cls._credentials:
            return cls._credentials[exchange_type.value]

        return None

    @classmethod
    def get_available_exchanges(cls, region: str = None) -> List[ExchangeType]:
        """Get list of available exchanges for region"""
        available = []
        for exchange_type in ExchangeType:
            if exchange_type in cls._exchanges:
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
