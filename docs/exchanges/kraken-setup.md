# Kraken Exchange Setup Guide

## Overview
Kraken is one of the largest and most established cryptocurrency exchanges, known for its security, reliability, and professional trading features. Available globally with strong regulatory compliance.

## 🌍 Regional Availability
- **Global**: Available in 190+ countries
- **US**: Kraken Pro available to US residents
- **EU**: Fully licensed and regulated in European Union
- **UK**: FCA authorized and regulated

## 📋 Prerequisites

### Account Requirements
- Valid government-issued photo ID
- Proof of address (utility bill, bank statement)
- Age 18 or older
- Supported country residence

### Trading Prerequisites
- Completed identity verification (KYC)
- Bank account or payment method linked
- Funding deposited (fiat or crypto)

## 🚀 Step 1: Create Kraken Account

### Registration Process
1. **Visit** [kraken.com](https://kraken.com)
2. **Sign up** with email and secure password
3. **Verify email** through confirmation link
4. **Complete basic verification**:
   - Full name and date of birth
   - Phone number verification
   - Country of residence

### Identity Verification (KYC)
1. **Navigate** to Account → Get Verified
2. **Choose verification level**:
   - **Starter**: $1,000 monthly limit
   - **Intermediate**: $5,000 monthly limit
   - **Pro**: $200,000+ monthly limits
3. **Upload documents**:
   - Government photo ID (passport, driver's license)
   - Proof of address (recent utility bill or bank statement)
4. **Wait for approval** (usually 1-3 business days)

## 🔑 Step 2: API Key Creation

### Generate API Keys
1. **Log in** to your Kraken account
2. **Navigate** to Settings → API
3. **Click** "Generate New Key"
4. **Configure permissions**:
   - ✅ **Query Funds**: Required for balance checking
   - ✅ **Query Open Orders**: Required for order status
   - ✅ **Query Closed Orders**: Required for trade history
   - ✅ **Query Ledger Entries**: Required for transaction history
   - ✅ **Place & Cancel Orders**: Required for trading
   - ⚠️ **Withdraw Funds**: Optional (not recommended for bots)

### API Key Settings
```
Key Description: PowerTraderAI+ Bot
Query Funds: ✅ Enabled
Query Open Orders: ✅ Enabled
Query Closed Orders: ✅ Enabled
Query Ledger Entries: ✅ Enabled
Place & Cancel Orders: ✅ Enabled
Withdraw Funds: ❌ Disabled (recommended)
```

### Save Your Credentials
**API Key**: `your_public_api_key_here`
**Private Key**: `your_private_api_key_here`

⚠️ **Important**: Store these securely - they provide access to your account!

## 🔐 Step 3: Configure PowerTraderAI+

### Credential File Setup
Create `credentials/kraken_config.json`:
```json
{
  "api_key": "your_public_api_key",
  "api_secret": "your_private_api_key",
  "api_version": "0",
  "timeout": 30
}
```

### Environment Variables (Production)
```bash
export KRAKEN_API_KEY="your_public_api_key"
export KRAKEN_API_SECRET="your_private_api_key"
```

### GUI Configuration
1. Launch PowerTraderAI+: `python app/pt_hub.py`
2. Go to **Settings** → **Exchange Provider Settings**
3. Set **Region**: "us", "eu", or "global"
4. Select **Primary Exchange**: "kraken"
5. Click **Exchange Setup** button
6. Enter your API credentials when prompted

## 🔧 Step 4: Testing Connection

In PowerTrader, open **Settings → Check Exchanges...**:

1. Tick **kraken** and the coins to check. The list shows the exchanges enabled in Settings, your primary exchange first.
2. Tick **Also check the saved API keys (read-only)** to test the keys you entered.
3. Press **Run check**.

Each row is one check: each coin's market status and best bid and ask (a price older than 30 seconds fails), the last day of hourly BTC candles, the minimum order and, when ticked, the API key. Nothing is ordered.
## 💰 Step 5: Funding Your Account

### Deposit Methods

#### Fiat Currency Deposits
- **Wire Transfer**: Fastest, higher limits
- **ACH Transfer**: US only, 1-3 business days
- **SEPA Transfer**: EU only, same day
- **Debit Card**: Instant, higher fees
- **Bank Transfer**: Various regions

#### Cryptocurrency Deposits
1. **Navigate** to Funding → Deposit
2. **Select cryptocurrency** (BTC, ETH, etc.)
3. **Copy deposit address**
4. **Send crypto** from external wallet
5. **Wait for confirmations** (varies by coin)

### Minimum Deposits
- **Fiat**: Usually $10-50 minimum
- **Crypto**: Varies by cryptocurrency
- **Wire Transfer**: $500-1000 minimum

## 📊 Trading Features

### Supported Trading Pairs
- **Major Pairs**: BTC/USD, ETH/USD, ADA/USD
- **Crypto Pairs**: BTC/ETH, ETH/ADA, etc.
- **Fiat Pairs**: USD, EUR, GBP, CAD, JPY
- **Stablecoins**: USDT, USDC, DAI

### Order Types
- **Market Orders**: Execute immediately at current price
- **Limit Orders**: Execute at specific price or better
- **Stop-Loss Orders**: Trigger sale when price drops
- **Take-Profit Orders**: Trigger sale when price rises
- **Post-Only Orders**: Only add liquidity to order book

### Advanced Features
- **Margin Trading**: Up to 5x leverage on select pairs
- **Futures Trading**: Crypto futures contracts
- **Dark Pool**: Large order execution
- **API Rate Limits**: 1 request per second for most calls

## ⚙️ Advanced Configuration

### Trading Parameters
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_api_secret",
  "trading_config": {
    "default_order_type": "limit",
    "max_slippage_pct": 0.5,
    "post_only": false,
    "reduce_only": false
  },
  "risk_management": {
    "max_position_size_usd": 10000,
    "max_daily_volume_usd": 50000,
    "enable_stop_losses": true
  }
}
```

### Symbol Mapping
Kraken uses unique symbol names:
```python
SYMBOL_MAP = {
    "BTC-USD": "XBTUSD",
    "ETH-USD": "ETHUSD",
    "ADA-USD": "ADAUSD",
    "DOT-USD": "DOTUSD",
    "LINK-USD": "LINKUSD"
}
```

## 🚨 Troubleshooting

### Common Issues

#### ❌ "Invalid API Key"
**Causes**:
- Incorrect API key or secret
- API key not activated
- Wrong API version

**Solutions**:
1. Verify API credentials in Kraken account
2. Ensure API key is enabled
3. Check API permissions are correct
4. Regenerate API key if necessary

#### ❌ "Insufficient permissions"
**Causes**:
- API key missing required permissions
- Account verification incomplete
- Trading restrictions

**Solutions**:
1. Enable all required API permissions
2. Complete account verification
3. Check account status and limits
4. Contact Kraken support if needed

#### ❌ "Rate limit exceeded"
**Causes**:
- Too many API requests
- Multiple trading bots
- Burst requests

**Solutions**:
1. Reduce request frequency
2. Implement request queuing
3. Use websocket feeds for market data
4. Respect rate limits (1 req/sec)

#### ❌ "Order rejected"
**Causes**:
- Insufficient balance
- Invalid trading pair
- Price out of range
- Market closed

**Solutions**:
1. Check account balance
2. Verify symbol format (XBTUSD vs BTC-USD)
3. Check price against current market
4. Ensure market is trading

### Support Resources
- **Kraken Support**: support.kraken.com
- **API Documentation**: docs.kraken.com/rest
- **Status Page**: status.kraken.com
- **Community**: reddit.com/r/Kraken

## 🔒 Security Best Practices

### API Security
- **Whitelist IPs**: Restrict API access to specific IPs
- **Minimal permissions**: Only enable required permissions
- **Regular rotation**: Change API keys periodically
- **Secure storage**: Never store keys in code

### Account Security
- **Two-Factor Authentication**: Enable TOTP (Google Authenticator)
- **Master Key**: Set up for additional security
- **Global Settings Lock**: Prevent unauthorized changes
- **Email notifications**: Enable for all activities

### Trading Security
- **Start small**: Test with small amounts first
- **Monitor trades**: Watch for unexpected activity
- **Set limits**: Use position and volume limits
- **Backup access**: Keep recovery codes safe

## 📈 Performance Optimization

### API Optimization
- **WebSocket feeds**: Use for real-time data
- **Batch requests**: Combine multiple queries
- **Caching**: Cache static data (symbols, limits)
- **Connection pooling**: Reuse HTTP connections

### Trading Optimization
- **Post-only orders**: Avoid taker fees when possible
- **Volume discounts**: Higher volume = lower fees
- **Staking rewards**: Earn rewards on holdings
- **Fee optimization**: Choose optimal order types

### Monitoring
```python
# Example monitoring code
import time
import logging

logger = logging.getLogger(__name__)

class KrakenMonitor:
    def __init__(self, exchange):
        self.exchange = exchange
        self.last_request_time = 0

    async def rate_limited_request(self, func, *args, **kwargs):
        # Respect 1 req/sec rate limit
        now = time.time()
        time_since_last = now - self.last_request_time

        if time_since_last < 1.0:
            await asyncio.sleep(1.0 - time_since_last)

        try:
            result = await func(*args, **kwargs)
            self.last_request_time = time.time()
            return result
        except Exception as e:
            logger.error(f"Kraken request failed: {e}")
            raise
```

---

**Kraken Setup Complete!** Your professional-grade cryptocurrency exchange integration is ready for PowerTraderAI+.
