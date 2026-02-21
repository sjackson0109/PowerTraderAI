# PowerTraderAI+ - Quick Reference Guide

## New Multi-Exchange Features Overview

PowerTraderAI+ now supports **global cryptocurrency trading** across 10+ major exchanges with unified management and intelligent routing.

## 📖 Documentation Library

| Document | Purpose | Audience |
|----------|---------|----------|
| **[EXCHANGE_DOCUMENTATION.md](EXCHANGE_DOCUMENTATION.md)** | Complete multi-exchange system guide | All users |
| **[GUI_USER_GUIDE.md](GUI_USER_GUIDE.md)** | Desktop application manual | GUI users |
| **[API_REFERENCE.md](API_REFERENCE.md)** | Developer API documentation | Developers |

## Supported Exchanges

### By Region

| Region | Exchanges | Notes |
|--------|-----------|-------|
| 🇺🇸 **US** | Robinhood, Coinbase, Kraken, Binance.US, KuCoin | Compliance-checked |
| 🇪🇺 **EU/UK** | Kraken, Coinbase, Binance, Bitstamp, KuCoin | EU-regulated |
| 🌐 **Global** | Binance, Kraken, KuCoin, Coinbase, Bybit, OKX | Worldwide access |

### Exchange Capabilities

| Exchange | Regions | API Trading | 2FA Support | Crypto Variety |
|----------|---------|-------------|-------------|----------------|
| **Robinhood** | US | Yes | Yes | Basic |
| **Kraken** | Global | Yes | Yes | High |
| **Binance** | Global¹ | Yes | Yes | Very High |
| **Coinbase** | US/EU | Yes | Yes | High |
| **KuCoin** | Global | Yes | Yes | Very High |
| **Bitstamp** | EU | Yes | Yes | Medium |
| **Bybit** | Global² | Yes | Yes | High |
| **OKX** | Global² | Yes | Yes | Very High |

¹ Binance.US for US users
² Check local regulations

## Desktop GUI Quick Start

### 1. Launch Application
```bash
cd app
python pt_hub.py
```

### 2. Configure Exchange
1. **Settings** menu → **Open Settings Dialog**
2. Scroll to **Exchange Provider Settings**
3. Select your **region** and **primary exchange**
4. Click **Exchange Setup** for credentials
5. **Save** settings

### 3. Monitor Status
- Check **Exchange: Connected EXCHANGE_NAME** status indicator
- Connected = Connected | Limited = Limited | Failed = Failed

## Command Line Setup

### Interactive Setup Wizard
```bash
python exchange_setup.py
```

### Quick Test
```bash
python test_exchanges.py
```

## 💼 API Quick Examples

### Basic Market Data
```python
from pt_multi_exchange import MultiExchangeManager

manager = MultiExchangeManager()

# Get price from specific exchange
btc_price = await manager.get_market_data("BTC-USD", "kraken")
print(f"BTC: ${btc_price.price}")

# Compare prices across all exchanges
prices = await manager.compare_prices("ETH-USD")
for exchange, data in prices.items():
    print(f"{exchange}: ${data.price}")
```

### Order Placement
```python
from pt_exchange_abstraction import OrderRequest

# Create order
order = OrderRequest(
    symbol="BTC-USD",
    side="buy",
    amount=0.001,
    order_type="market"
)

# Place on best exchange
result = await manager.place_order(order)
print(f"Executed: {result.order_id}")
```

## 🔐 Credential Setup

### File-Based (Desktop)
Create `credentials/exchange_config.json`:
```json
{
  "kraken": {
    "api_key": "your_api_key",
    "api_secret": "your_api_secret"
  },
  "coinbase": {
    "api_key": "your_key",
    "api_secret": "your_secret",
    "passphrase": "your_passphrase"
  }
}
```

### Environment Variables (CI/CD)
```bash
export KRAKEN_API_KEY="your_key"
export KRAKEN_API_SECRET="your_secret"
export COINBASE_API_KEY="your_key"
export COINBASE_API_SECRET="your_secret"
export COINBASE_PASSPHRASE="your_passphrase"
```

## Key Features

### 💱 Price Optimization
- **Cross-Exchange Comparison**: Real-time price comparison
- **Best Price Discovery**: Automatic best price finding
- **Smart Order Routing**: Route orders to optimal exchanges

### Automatic Failover
- **Connection Monitoring**: Continuous health checks
- **Backup Exchanges**: Automatic switching on failures
- **Rate Limit Management**: Intelligent request distribution

### Security & Compliance
- **Regional Filtering**: Only show compliant exchanges
- **Credential Encryption**: Secure storage of API keys
- **Permission Validation**: Verify API key permissions

### Real-Time Monitoring
- **Exchange Status**: Live connection indicators
- **Price Feeds**: Real-time market data
- **Trade Execution**: Order status tracking

## 🚨 Common Issues & Solutions

### ❌ "Exchange not available"
**Solution**: Check region settings and exchange support
```python
from pt_multi_exchange import MultiExchangeManager
manager = MultiExchangeManager()
print("Available:", manager.get_available_exchanges())
```

### ❌ "Authentication failed"
**Solutions**:
1. Verify API keys in credentials folder
2. Check key permissions on exchange
3. Ensure 2FA is properly configured
4. Validate IP whitelist settings

### ❌ "Rate limit exceeded"
**Solutions**:
1. Enable automatic exchange rotation
2. Reduce trading frequency
3. Use multiple API keys
4. Check exchange-specific limits

## 🔍 Debug & Testing

### Enable Debug Mode
```bash
export PT_DEBUG=1
python pt_hub.py
```

### Test All Exchanges
```bash
python test_exchanges.py --all
```

### Validate Configuration
```python
from pt_multi_exchange import ExchangeConfigManager
config = ExchangeConfigManager()
print("Valid configs:", config.get_configured_exchanges())
```

## Integration Examples

### Portfolio Monitoring
```python
# Get balances across all exchanges
balances = await manager.get_balances()
total_btc = sum(
    exchange_balances.get("BTC", 0)
    for exchange_balances in balances.values()
)
print(f"Total BTC across all exchanges: {total_btc}")
```

### Arbitrage Detection
```python
# Find price differences
prices = await manager.compare_prices("BTC-USD")
sorted_prices = sorted(prices.items(), key=lambda x: x[1].price)
cheapest = sorted_prices[0]
most_expensive = sorted_prices[-1]
spread = most_expensive[1].price - cheapest[1].price
print(f"Arbitrage opportunity: ${spread}")
```

### Risk Management
```python
# Distribute trades across exchanges
total_amount = 1.0  # 1 BTC to buy
exchanges = manager.get_available_exchanges()
amount_per_exchange = total_amount / len(exchanges)

for exchange in exchanges:
    order = OrderRequest(
        symbol="BTC-USD",
        side="buy",
        amount=amount_per_exchange,
        order_type="market"
    )
    await manager.place_order(order, exchange)
```

## Best Practices

### Security
- Yes Use environment variables for production
- Yes Rotate API keys regularly
- Yes Enable IP restrictions on exchanges
- Yes Use separate keys for trading vs. monitoring

### Trading
- Yes Start with small amounts for testing
- Yes Monitor all exchanges initially
- Yes Set up proper alerts for failures
- Yes Test failover scenarios

### Performance
- Yes Enable price comparison for better execution
- Yes Use connection pooling for high-frequency trading
- Yes Cache market data appropriately
- Yes Monitor API rate limits

---

**PowerTraderAI+ Multi-Exchange System** - Your gateway to global cryptocurrency trading with intelligent automation and enterprise-grade reliability.
