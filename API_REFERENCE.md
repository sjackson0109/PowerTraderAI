# PowerTraderAI+ - API Reference Documentation

## Overview

PowerTraderAI+ provides comprehensive APIs for exchange integration, trading operations, and system management. This reference covers all public interfaces for developers and advanced users.

## 📦 Core Modules

### `pt_exchange_abstraction.py`

#### AbstractExchange Class
Base class for all exchange implementations.

```python
from pt_exchange_abstraction import AbstractExchange, MarketData, OrderResult

class AbstractExchange:
    """Base class for all cryptocurrency exchange implementations."""
    
    async def initialize(self) -> bool:
        """Initialize exchange connection and authentication."""
        
    async def get_market_data(self, symbol: str) -> MarketData:
        """Get current market data for a trading pair."""
        
    async def place_order(self, order_request: OrderRequest) -> OrderResult:
        """Place a trading order on the exchange."""
        
    async def get_balance(self, asset: str = None) -> Dict[str, float]:
        """Get account balance for specific asset or all assets."""
        
    def get_supported_regions(self) -> List[str]:
        """Return list of supported geographic regions."""
        
    def normalize_symbol(self, symbol: str) -> str:
        """Convert symbol to exchange-specific format."""
```

#### Data Classes

**MarketData**
```python
@dataclass
class MarketData:
    symbol: str           # Trading pair symbol
    price: float         # Current price
    bid: float           # Best bid price
    ask: float           # Best ask price
    volume: float        # 24h trading volume
    timestamp: datetime  # Data timestamp
    exchange: str        # Source exchange name
```

**OrderRequest**
```python
@dataclass
class OrderRequest:
    symbol: str          # Trading pair
    side: str           # 'buy' or 'sell'
    amount: float       # Order quantity
    order_type: str     # 'market', 'limit', 'stop'
    price: float = None # Limit price (if applicable)
    time_in_force: str = "GTC"  # Order duration
```

**OrderResult**
```python
@dataclass
class OrderResult:
    order_id: str        # Exchange order ID
    status: str          # Order status
    filled_amount: float # Executed quantity
    remaining_amount: float # Unfilled quantity
    average_price: float # Average execution price
    fees: Dict[str, float] # Trading fees
    timestamp: datetime  # Execution timestamp
```

#### ExchangeType Enum
```python
from enum import Enum

class ExchangeType(Enum):
    ROBINHOOD = "robinhood"
    KRAKEN = "kraken"
    BINANCE = "binance"
    COINBASE = "coinbase"
    KUCOIN = "kucoin"
    BITSTAMP = "bitstamp"
    BYBIT = "bybit"
    OKX = "okx"
```

#### ExchangeFactory
```python
class ExchangeFactory:
    """Factory for creating exchange instances."""
    
    @staticmethod
    def create_exchange(exchange_type: str, config: Dict = None) -> AbstractExchange:
        """Create exchange instance by type."""
        
    @staticmethod
    def get_available_exchanges() -> List[str]:
        """Get list of all available exchange types."""
        
    @staticmethod
    def register_exchange(name: str, exchange_class: type):
        """Register custom exchange implementation."""
```

### `pt_multi_exchange.py`

#### MultiExchangeManager Class
High-level manager for multi-exchange operations.

```python
from pt_multi_exchange import MultiExchangeManager

class MultiExchangeManager:
    """Manages multiple exchanges and provides unified interface."""
    
    def __init__(self, config_manager: ExchangeConfigManager = None):
        """Initialize with optional configuration manager."""
        
    def get_available_exchanges(self) -> List[str]:
        """Get list of exchanges available for current region."""
        
    async def get_market_data(self, symbol: str, exchange: str = None) -> MarketData:
        """Get market data from specific or best exchange."""
        
    async def compare_prices(self, symbol: str) -> Dict[str, MarketData]:
        """Compare prices across all available exchanges."""
        
    async def get_best_price(self, symbol: str, side: str = "buy") -> MarketData:
        """Find best price across all exchanges."""
        
    async def place_order(self, order_request: OrderRequest, exchange: str = None) -> OrderResult:
        """Place order on specific or optimal exchange."""
        
    def get_exchange_status(self) -> Dict[str, Dict]:
        """Get connection status for all exchanges."""
        
    async def get_balances(self, exchange: str = None) -> Dict[str, Dict[str, float]]:
        """Get balances from specific exchange or all exchanges."""
```

#### ExchangeConfigManager Class
Configuration and credential management.

```python
from pt_multi_exchange import ExchangeConfigManager

class ExchangeConfigManager:
    """Manages exchange configurations and credentials."""
    
    def __init__(self, config_dir: str = "credentials"):
        """Initialize with configuration directory."""
        
    def load_exchange_config(self, exchange_name: str) -> Dict:
        """Load configuration for specific exchange."""
        
    def save_exchange_config(self, exchange_name: str, config: Dict):
        """Save configuration for specific exchange."""
        
    def validate_config(self, exchange_name: str) -> bool:
        """Validate exchange configuration."""
        
    def get_configured_exchanges(self) -> List[str]:
        """Get list of exchanges with valid configurations."""
        
    def delete_exchange_config(self, exchange_name: str):
        """Remove configuration for specific exchange."""
```

### `pt_exchanges.py`

#### Exchange-Specific Implementations

**RobinhoodExchange**
```python
from pt_exchanges import RobinhoodExchange

class RobinhoodExchange(AbstractExchange):
    """Robinhood exchange implementation."""
    
    def __init__(self, config: Dict = None):
        """Initialize with username/password configuration."""
        
    def get_supported_regions(self) -> List[str]:
        """Returns ['us'] - US only."""
        
    async def initialize(self) -> bool:
        """Login with username/password, handle 2FA."""
        
    async def get_market_data(self, symbol: str) -> MarketData:
        """Get crypto price data from Robinhood API."""
```

**KrakenExchange**
```python
from pt_exchanges import KrakenExchange

class KrakenExchange(AbstractExchange):
    """Kraken exchange implementation."""
    
    def __init__(self, config: Dict = None):
        """Initialize with API key/secret configuration."""
        
    def get_supported_regions(self) -> List[str]:
        """Returns ['us', 'eu', 'global'] - Worldwide."""
        
    async def get_market_data(self, symbol: str) -> MarketData:
        """Get market data from Kraken REST API."""
        
    async def place_order(self, order_request: OrderRequest) -> OrderResult:
        """Place order using Kraken trading API."""
```

**BinanceExchange**
```python
from pt_exchanges import BinanceExchange

class BinanceExchange(AbstractExchange):
    """Binance exchange implementation."""
    
    def normalize_symbol(self, symbol: str) -> str:
        """Convert to Binance format (e.g., BTC-USD -> BTCUSDT)."""
        
    async def get_market_data(self, symbol: str) -> MarketData:
        """Get ticker data from Binance API."""
        
    def get_supported_regions(self) -> List[str]:
        """Returns ['eu', 'global'] - Excludes US."""
```

## 🔧 Configuration APIs

### Settings Management
```python
from pt_hub import PowerTraderHub

# Access settings from GUI application
hub = PowerTraderHub()
settings = hub.settings

# Exchange settings
primary_exchange = settings.get("primary_exchange", "robinhood")
region = settings.get("region", "us")
price_comparison = settings.get("price_comparison_enabled", True)

# Trading settings  
coins = settings.get("coins", ["BTC", "ETH"])
trade_start_level = settings.get("trade_start_level", 3)
start_allocation_pct = settings.get("start_allocation_pct", 5.0)
```

### Credential Loading Priority
```python
"""
Credential loading order (first found wins):
1. Environment variables (CI/CD deployments)
2. Encrypted credential files (desktop use)
3. Plain JSON files (development/testing)
"""

# Environment variables format
os.environ["KRAKEN_API_KEY"] = "your_key"
os.environ["KRAKEN_API_SECRET"] = "your_secret"

# File-based credentials
# credentials/kraken_config.json
{
    "api_key": "your_key",
    "api_secret": "your_secret"
}
```

## 📊 Trading APIs

### Market Data Access
```python
import asyncio
from pt_multi_exchange import MultiExchangeManager

async def get_crypto_prices():
    manager = MultiExchangeManager()
    
    # Single exchange
    btc_data = await manager.get_market_data("BTC-USD", "kraken")
    print(f"BTC: ${btc_data.price}")
    
    # Compare across exchanges
    eth_prices = await manager.compare_prices("ETH-USD")
    for exchange, data in eth_prices.items():
        print(f"{exchange}: ${data.price}")
    
    # Best price discovery
    best_btc = await manager.get_best_price("BTC-USD", "buy")
    print(f"Best buy price: ${best_btc.price} on {best_btc.exchange}")

# Run async function
asyncio.run(get_crypto_prices())
```

### Order Placement
```python
from pt_exchange_abstraction import OrderRequest
from pt_multi_exchange import MultiExchangeManager

async def place_crypto_order():
    manager = MultiExchangeManager()
    
    # Create order request
    order = OrderRequest(
        symbol="BTC-USD",
        side="buy",
        amount=0.001,
        order_type="market"
    )
    
    # Place on specific exchange
    result = await manager.place_order(order, exchange="kraken")
    print(f"Order {result.order_id}: {result.status}")
    
    # Place on best price exchange
    result = await manager.place_order(order)  # Auto-selects best exchange
    print(f"Executed at ${result.average_price} on best exchange")

asyncio.run(place_crypto_order())
```

### Balance Management
```python
async def check_balances():
    manager = MultiExchangeManager()
    
    # Get balances from all exchanges
    all_balances = await manager.get_balances()
    for exchange, balances in all_balances.items():
        print(f"\n{exchange.upper()} Balances:")
        for asset, amount in balances.items():
            if amount > 0:
                print(f"  {asset}: {amount}")
    
    # Get specific exchange balance
    kraken_balances = await manager.get_balances("kraken")
    btc_balance = kraken_balances.get("kraken", {}).get("BTC", 0)
    print(f"Kraken BTC balance: {btc_balance}")

asyncio.run(check_balances())
```

## 🔍 Monitoring APIs

### Exchange Health Monitoring
```python
from pt_multi_exchange import MultiExchangeManager

def monitor_exchanges():
    manager = MultiExchangeManager()
    
    # Get overall system status
    status = manager.get_system_status()
    print(f"System Status: {status['overall']}")
    print(f"Available Exchanges: {status['available_count']}/{status['total_count']}")
    
    # Detailed exchange status
    exchange_status = manager.get_exchange_status()
    for exchange, info in exchange_status.items():
        print(f"{exchange}: {info['status']} ({info['latency']}ms)")
        if info.get('last_error'):
            print(f"  Error: {info['last_error']}")

# Run monitoring
monitor_exchanges()
```

### Real-time Price Streaming
```python
from pt_multi_exchange import MultiExchangeManager
import asyncio

async def price_stream():
    manager = MultiExchangeManager()
    
    def on_price_update(exchange, symbol, price_data):
        print(f"[{exchange}] {symbol}: ${price_data.price}")
    
    def on_connection_change(exchange, connected):
        status = "Connected" if connected else "Disconnected"
        print(f"[{exchange}] {status}")
    
    # Subscribe to events
    manager.subscribe_to_price_updates(on_price_update)
    manager.subscribe_to_connection_events(on_connection_change)
    
    # Start monitoring
    await manager.start_price_monitoring(["BTC-USD", "ETH-USD"])
    
    # Keep running
    while True:
        await asyncio.sleep(1)

asyncio.run(price_stream())
```

## 🛡️ Error Handling APIs

### Exception Classes
```python
from pt_exchange_abstraction import (
    ExchangeConnectionError,
    ExchangeAuthenticationError,
    ExchangeRateLimitError,
    ExchangeOrderError
)

try:
    await exchange.place_order(order_request)
except ExchangeConnectionError as e:
    print(f"Connection failed: {e}")
    # Try backup exchange
except ExchangeAuthenticationError as e:
    print(f"Auth failed: {e}")
    # Check credentials
except ExchangeRateLimitError as e:
    print(f"Rate limited: {e}")
    # Wait and retry
except ExchangeOrderError as e:
    print(f"Order failed: {e}")
    # Check order parameters
```

### Retry and Fallback
```python
from pt_multi_exchange import MultiExchangeManager
import asyncio

async def robust_trading():
    manager = MultiExchangeManager()
    
    # Automatic retry with exponential backoff
    async def place_order_with_retry(order_request, max_retries=3):
        for attempt in range(max_retries):
            try:
                result = await manager.place_order(order_request)
                return result
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = 2 ** attempt
                print(f"Retry {attempt + 1} in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
    
    # Exchange fallback
    async def place_order_with_fallback(order_request):
        exchanges = ["kraken", "coinbase", "binance"]
        for exchange in exchanges:
            try:
                return await manager.place_order(order_request, exchange)
            except Exception as e:
                print(f"Failed on {exchange}: {e}")
        raise Exception("All exchanges failed")

# Usage
order = OrderRequest(symbol="BTC-USD", side="buy", amount=0.001, order_type="market")
result = await place_order_with_fallback(order)
```

## 🔌 Custom Exchange Integration

### Creating Custom Exchange
```python
from pt_exchange_abstraction import AbstractExchange, MarketData, OrderResult
from typing import List, Dict
import aiohttp

class CustomExchange(AbstractExchange):
    """Custom exchange implementation template."""
    
    def __init__(self, config: Dict = None):
        super().__init__()
        self.config = config or {}
        self.session = None
        
    def get_supported_regions(self) -> List[str]:
        return ["us", "eu", "global"]  # Specify supported regions
        
    async def initialize(self) -> bool:
        """Initialize API connection."""
        try:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
            # Test API connection
            await self._test_connection()
            return True
        except Exception as e:
            print(f"Custom exchange init failed: {e}")
            return False
            
    async def get_market_data(self, symbol: str) -> MarketData:
        """Implement market data retrieval."""
        normalized_symbol = self.normalize_symbol(symbol)
        
        async with self.session.get(
            f"https://api.customexchange.com/ticker/{normalized_symbol}"
        ) as response:
            data = await response.json()
            
            return MarketData(
                symbol=symbol,
                price=float(data['price']),
                bid=float(data['bid']),
                ask=float(data['ask']),
                volume=float(data['volume']),
                timestamp=datetime.now(),
                exchange="custom"
            )
            
    async def place_order(self, order_request: OrderRequest) -> OrderResult:
        """Implement order placement."""
        # Build order payload
        payload = {
            "symbol": self.normalize_symbol(order_request.symbol),
            "side": order_request.side,
            "type": order_request.order_type,
            "quantity": order_request.amount
        }
        
        if order_request.order_type == "limit":
            payload["price"] = order_request.price
            
        # Submit order
        async with self.session.post(
            "https://api.customexchange.com/order",
            json=payload,
            headers=self._get_auth_headers()
        ) as response:
            result = await response.json()
            
            return OrderResult(
                order_id=result['order_id'],
                status=result['status'],
                filled_amount=float(result.get('filled_qty', 0)),
                remaining_amount=float(result.get('remaining_qty', 0)),
                average_price=float(result.get('avg_price', 0)),
                fees=result.get('fees', {}),
                timestamp=datetime.now()
            )
            
    def normalize_symbol(self, symbol: str) -> str:
        """Convert symbol to exchange format."""
        # Example: BTC-USD -> BTCUSD
        return symbol.replace("-", "").upper()
        
    def _get_auth_headers(self) -> Dict[str, str]:
        """Generate authentication headers."""
        return {
            "X-API-Key": self.config.get("api_key", ""),
            "X-API-Secret": self.config.get("api_secret", "")
        }
        
    async def _test_connection(self):
        """Test API connectivity."""
        async with self.session.get(
            "https://api.customexchange.com/ping"
        ) as response:
            if response.status != 200:
                raise Exception(f"Connection test failed: {response.status}")

# Register custom exchange
from pt_exchange_abstraction import ExchangeFactory
ExchangeFactory.register_exchange("custom", CustomExchange)
```

### Using Custom Exchange
```python
from pt_multi_exchange import MultiExchangeManager, ExchangeConfigManager

# Configure custom exchange
config_manager = ExchangeConfigManager()
config_manager.save_exchange_config("custom", {
    "api_key": "your_custom_api_key",
    "api_secret": "your_custom_api_secret"
})

# Use with multi-exchange manager
manager = MultiExchangeManager(config_manager)
data = await manager.get_market_data("BTC-USD", "custom")
print(f"Custom exchange price: ${data.price}")
```

## 📋 Utility Functions

### Symbol Conversion
```python
from pt_exchanges import symbol_utils

# Convert between different exchange symbol formats
binance_symbol = symbol_utils.to_binance_format("BTC-USD")  # "BTCUSDT"
kraken_symbol = symbol_utils.to_kraken_format("BTC-USD")    # "XBTUSD"
coinbase_symbol = symbol_utils.to_coinbase_format("BTC-USD") # "BTC-USD"

# Normalize to standard format
standard_symbol = symbol_utils.normalize_symbol("BTCUSDT", "binance")  # "BTC-USD"
```

### Configuration Helpers
```python
from pt_multi_exchange import config_utils

# Validate exchange configuration
is_valid = config_utils.validate_exchange_config("kraken", {
    "api_key": "your_key",
    "api_secret": "your_secret"
})

# Get regional exchange recommendations
exchanges = config_utils.get_recommended_exchanges("us")
print(f"US exchanges: {exchanges}")

# Test exchange connectivity
is_connected = await config_utils.test_exchange_connection("kraken")
print(f"Kraken connected: {is_connected}")
```

---

**PowerTraderAI+ API Reference** - Complete developer documentation for multi-exchange cryptocurrency trading.