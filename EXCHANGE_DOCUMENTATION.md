# PowerTraderAI+ - Multi-Exchange Trading System

## Overview

PowerTraderAI+ now supports **global multi-exchange trading** with unified management across 10+ major cryptocurrency exchanges. This system provides price comparison, automatic failover, regional compliance, and seamless credential management.

## Supported Exchanges

### Regional Availability

#### **United States**
- **Robinhood** - Commission-free crypto trading
- **Coinbase** - Largest US crypto exchange
- **Kraken** - Professional trading platform
- **Binance.US** - US version of global exchange
- **KuCoin** - Global exchange (US accessible)

#### **Europe/UK**
- **Kraken** - EU-regulated exchange
- **Coinbase** - Available in 100+ countries
- **Binance** - Global platform
- **Bitstamp** - EU-licensed exchange
- **KuCoin** - Global exchange

#### **Global**
- **Binance** - World's largest crypto exchange
- **KuCoin** - Wide altcoin selection
- **Bybit** - Derivatives specialist
- **OKX** - Comprehensive trading platform
- **Kraken** - Global availability

## Quick Start Guide

### 1. Launch Desktop GUI
```bash
cd app
python pt_hub.py
```

### 2. Configure Exchange Settings
1. Click **Settings** menu
2. Scroll to **Exchange Provider Settings**
3. Select your **region** (US/EU-UK/Global)
4. Choose **primary exchange** from filtered list
5. Enable **price comparison** (optional)
6. Click **Exchange Setup** to configure credentials
7. **Save** settings

### 3. Exchange Status Monitoring
- Check **Exchange:** status indicator in main GUI
- Connected = Connected and working
- Limited = Connected but limited data
- Failed = Connection failed

## Exchange Setup & Credentials

### Setup Wizard
Run the interactive setup wizard:
```bash
python exchange_setup.py
```

### Manual Configuration

#### 1. Create Credentials Directory
```bash
mkdir credentials
```

#### 2. Create Exchange-Specific Config Files

**Robinhood** (`credentials/robinhood_config.json`):
```json
{
  "username": "your_username",
  "password": "your_password",
  "mfa_code": "optional_2fa_device_id"
}
```

**Kraken** (`credentials/kraken_config.json`):
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_api_secret"
}
```

**Binance** (`credentials/binance_config.json`):
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_api_secret"
}
```

**Coinbase** (`credentials/coinbase_config.json`):
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_api_secret",
  "passphrase": "your_passphrase"
}
```

**KuCoin** (`credentials/kucoin_config.json`):
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_api_secret",
  "passphrase": "your_passphrase"
}
```

### 3. Environment Variables (CI/CD)
For automated deployments, use environment variables:
```bash
export ROBINHOOD_USERNAME="username"
export ROBINHOOD_PASSWORD="password"
export KRAKEN_API_KEY="key"
export KRAKEN_API_SECRET="secret"
# ... etc for other exchanges
```

## Configuration Options

### Desktop GUI Settings

#### Primary Exchange Selection
- **Purpose**: Main exchange for trading operations
- **Auto-filtering**: Based on your selected region
- **Validation**: Checks exchange availability for your region

#### Price Comparison
- **Enable**: Compare prices across multiple exchanges
- **Benefits**: Find best execution prices
- **Performance**: Minimal impact with caching

#### Auto Best Price
- **Enable**: Automatically route to best price exchange
- **Caution**: May split orders across exchanges
- **Recommendation**: Test with small amounts first

### Advanced Configuration

#### Exchange Priorities (`pt_multi_exchange.py`)
```python
# Customize exchange priority order
EXCHANGE_PRIORITIES = {
    "us": ["robinhood", "coinbase", "kraken"],
    "eu": ["kraken", "bitstamp", "coinbase"],
    "global": ["binance", "kucoin", "kraken"]
}
```

#### Connection Timeouts
```python
# In exchange implementation files
CONNECTION_TIMEOUT = 30  # seconds
REQUEST_TIMEOUT = 10     # seconds
RETRY_ATTEMPTS = 3       # number of retries
```

## Trading Features

### Multi-Exchange Price Discovery
```python
from pt_multi_exchange import MultiExchangeManager

manager = MultiExchangeManager()

# Get best price across all exchanges
best_price = manager.get_best_price("BTC-USD")
print(f"Best price: ${best_price.price} on {best_price.exchange}")

# Compare prices across exchanges
prices = manager.compare_prices("ETH-USD")
for exchange, price_info in prices.items():
    print(f"{exchange}: ${price_info.price}")
```

### Automatic Failover
- **Primary Exchange Down**: Automatically switches to backup
- **Rate Limiting**: Rotates between exchanges
- **Network Issues**: Intelligent retry with different endpoints

### Order Routing
```python
# Route order to best exchange
order_result = manager.place_order(
    symbol="BTC-USD",
    side="buy",
    amount=0.001,
    order_type="market",
    use_best_price=True  # Finds best execution
)
```

## Security & Compliance

### Credential Protection
- **Encryption**: All stored credentials encrypted at rest
- **File Permissions**: Restrictive access (600)
- **Environment Variables**: Secure CI/CD deployment
- **Never Logged**: API keys never appear in logs

### Regional Compliance
- **US**: Only US-licensed exchanges recommended
- **EU**: GDPR-compliant and MiCA-regulated exchanges
- **KYC/AML**: All exchanges support required compliance

### Rate Limiting
- **Automatic**: Built-in rate limiting per exchange
- **Adaptive**: Adjusts to exchange-specific limits
- **Fallback**: Switches exchanges when limits hit

## Monitoring & Diagnostics

### Exchange Status Dashboard
Access via GUI or programmatically:
```python
from pt_multi_exchange import MultiExchangeManager

manager = MultiExchangeManager()
status = manager.get_exchange_status()

for exchange, info in status.items():
    print(f"{exchange}: {info['status']} - {info['latency']}ms")
```

### Health Checks
- **Connectivity**: Tests API endpoints
- **Market Data**: Validates price feeds
- **Trading**: Checks order placement capabilities
- **Balances**: Verifies account access

### Logging
```python
import logging

# Enable exchange-specific logging
logging.getLogger('pt_exchanges').setLevel(logging.DEBUG)
logging.getLogger('pt_multi_exchange').setLevel(logging.INFO)
```

## Troubleshooting

### Common Issues

#### ERROR: "Exchange not available"
**Solution**: Check region settings and exchange support
```python
# Verify exchange availability
manager = MultiExchangeManager()
available = manager.get_available_exchanges()
print("Available exchanges:", available)
```

#### ERROR: "Authentication failed"
**Solutions**:
1. Verify credentials in `credentials/` directory
2. Check API key permissions
3. Ensure 2FA is properly configured
4. Validate IP whitelist settings

#### ERROR: "Rate limit exceeded"
**Solutions**:
1. Enable automatic exchange rotation
2. Reduce request frequency
3. Check exchange-specific limits
4. Use multiple API keys (if supported)

#### ERROR: "Connection timeout"
**Solutions**:
1. Check internet connectivity
2. Verify exchange is operational
3. Try different exchanges
4. Increase timeout values

### Debug Mode
Enable detailed logging:
```bash
export PT_DEBUG=1
python pt_hub.py
```

### Test Exchange Connections
```bash
python test_exchanges.py
```

## Developer API

### Basic Usage
```python
from pt_exchange_abstraction import ExchangeFactory
from pt_multi_exchange import MultiExchangeManager

# Initialize exchange
exchange = ExchangeFactory.create_exchange("kraken")
await exchange.initialize()

# Get market data
market_data = await exchange.get_market_data("BTC-USD")
print(f"Price: ${market_data.price}")

# Multi-exchange manager
manager = MultiExchangeManager()
best_prices = manager.compare_prices("ETH-USD")
```

### Custom Exchange Integration
```python
from pt_exchange_abstraction import AbstractExchange, MarketData

class CustomExchange(AbstractExchange):
    def get_supported_regions(self) -> List[str]:
        return ["us", "global"]

    async def get_market_data(self, symbol: str) -> MarketData:
        # Implement custom exchange API calls
        pass

    async def place_order(self, order_request) -> OrderResult:
        # Implement custom order placement
        pass

# Register custom exchange
ExchangeFactory.register_exchange("custom", CustomExchange)
```

### Event Handling
```python
from pt_multi_exchange import MultiExchangeManager

def on_price_update(exchange, symbol, price):
    print(f"Price update: {symbol} = ${price} on {exchange}")

def on_connection_lost(exchange, error):
    print(f"Lost connection to {exchange}: {error}")

manager = MultiExchangeManager()
manager.subscribe_to_price_updates(on_price_update)
manager.subscribe_to_connection_events(on_connection_lost)
```

## Performance Optimization

### Connection Pooling
```python
# Configure connection limits
EXCHANGE_CONFIG = {
    "max_connections": 10,
    "connection_timeout": 30,
    "read_timeout": 10,
    "pool_recycle": 3600
}
```

### Caching Strategy
```python
# Price data caching
CACHE_CONFIG = {
    "price_cache_ttl": 1,      # 1 second for prices
    "balance_cache_ttl": 30,   # 30 seconds for balances
    "status_cache_ttl": 60     # 60 seconds for status
}
```

### Async Operations
```python
import asyncio
from pt_exchanges import KrakenExchange, BinanceExchange

async def get_multiple_prices():
    kraken = KrakenExchange()
    binance = BinanceExchange()

    # Fetch prices concurrently
    tasks = [
        kraken.get_market_data("BTC-USD"),
        binance.get_market_data("BTC-USDT")
    ]

    results = await asyncio.gather(*tasks)
    return results
```

## Update & Maintenance

### Exchange Support Updates
```bash
# Pull latest exchange integrations
git pull origin main

# Update dependencies
pip install -r requirements.txt

# Test new exchanges
python test_exchanges.py --exchange=new_exchange
```

### Credential Rotation
```python
from pt_multi_exchange import ExchangeConfigManager

config_manager = ExchangeConfigManager()

# Update API credentials
config_manager.update_exchange_config("kraken", {
    "api_key": "new_api_key",
    "api_secret": "new_api_secret"
})

# Reinitialize exchange
manager.refresh_exchange("kraken")
```

## Support

### Getting Help
1. **GUI Issues**: Check the exchange status indicator
2. **API Errors**: Enable debug logging
3. **Credential Problems**: Verify file permissions and formats
4. **Regional Issues**: Confirm exchange availability in your region

### Useful Commands
```bash
# Test all exchanges
python test_exchanges.py

# Interactive setup
python exchange_setup.py

# Check credentials
python -c "from pt_multi_exchange import ExchangeConfigManager; print(ExchangeConfigManager().validate_all_configs())"

# Exchange status
python -c "from pt_multi_exchange import MultiExchangeManager; print(MultiExchangeManager().get_system_status())"
```

---

**PowerTraderAI+ Multi-Exchange System** - Trade globally with confidence and compliance.
