# Coinbase Exchange Setup Guide

## Overview
Coinbase is one of the most user-friendly and trusted cryptocurrency exchanges, especially popular in the United States and Europe. Known for strong regulatory compliance and security.

## 🌍 Regional Availability
- **US**: Coinbase Pro/Advanced Trade (all US states except Hawaii)
- **EU**: Available in 40+ European countries
- **UK**: Fully licensed and regulated by FCA
- **Global**: 100+ countries supported

## 📋 Prerequisites

### Account Requirements
- Valid government-issued photo ID
- Proof of address document
- Age 18 or older (21 in some US states)
- Supported country residence
- Bank account for fiat deposits

### Trading Prerequisites
- Completed identity verification
- Linked and verified payment method
- Two-factor authentication enabled

## 🚀 Step 1: Create Coinbase Account

### Registration Process
1. **Visit** [coinbase.com](https://coinbase.com) or [pro.coinbase.com](https://pro.coinbase.com)
2. **Click** "Sign up" and enter details
3. **Verify email** through confirmation link
4. **Complete phone verification**
5. **Add personal information** (name, DOB, address)

### Identity Verification
1. **Navigate** to Settings → Identity Verification
2. **Upload photo ID**:
   - Driver's license (preferred)
   - Passport
   - State ID card
3. **Verify address** with utility bill or bank statement
4. **Complete facial recognition** verification
5. **Wait for approval** (usually instant to 24 hours)

### Enable Two-Factor Authentication
1. **Go to** Settings → Security
2. **Enable 2FA** with authenticator app (Google Authenticator, Authy)
3. **Save backup codes** in secure location
4. **Test 2FA** with test login

## 🔑 Step 2: API Key Creation

### Access API Settings
1. **Log in** to Coinbase Pro/Advanced Trade
2. **Navigate** to Settings → API
3. **Click** "Create New API Key"
4. **Complete security verification** (2FA required)

### Configure API Permissions
Select appropriate permissions:
- ✅ **View**: Required for account info and balances
- ✅ **Trade**: Required for placing and managing orders
- ❌ **Transfer**: Not needed for trading (disable for security)

### API Key Configuration
```
Nickname: PowerTraderAI+ Bot
Permissions:
  ✅ View (accounts, orders, fills, payment methods)
  ✅ Trade (buy, sell, cancel orders)
  ❌ Transfer (send, receive crypto)

IP Whitelist: [Your IP Address] (recommended)
```

### Save Your Credentials
You'll receive three pieces of information:
- **API Key**: `your_api_key_here`
- **API Secret**: `your_api_secret_here`
- **Passphrase**: `your_passphrase_here`

⚠️ **Important**: Store all three securely - you cannot retrieve them again!

## 🔐 Step 3: Configure PowerTraderAI+

### Credential File Setup
Create `credentials/coinbase_config.json`:
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_api_secret",
  "passphrase": "your_passphrase",
  "sandbox": false,
  "api_url": "https://api.exchange.coinbase.com"
}
```

### Environment Variables (Production)
```bash
export COINBASE_API_KEY="your_api_key"
export COINBASE_API_SECRET="your_api_secret"
export COINBASE_PASSPHRASE="your_passphrase"
```

### GUI Configuration
1. Launch PowerTraderAI+: `python app/pt_hub.py`
2. Go to **Settings** → **Exchange Provider Settings**
3. Set **Region**: "us" or "eu"
4. Select **Primary Exchange**: "coinbase"
5. Click **Exchange Setup** button
6. Enter all three credentials when prompted

## 🔧 Step 4: Testing Connection

### Manual Test
```bash
cd app
python test_exchanges.py --exchange=coinbase
```

### Expected Output
```
Testing Coinbase connection...
✅ API authentication successful
✅ Account access verified
✅ Trading permissions confirmed
✅ Market data retrieved
Current BTC price: $43,250.50
```

### Programmatic Test
```python
from pt_exchanges import CoinbaseExchange
import asyncio

async def test_coinbase():
    exchange = CoinbaseExchange({
        "api_key": "your_api_key",
        "api_secret": "your_api_secret",
        "passphrase": "your_passphrase"
    })

    if await exchange.initialize():
        # Test account access
        accounts = await exchange.get_balance()
        print(f"Accounts: {accounts}")

        # Test market data
        market_data = await exchange.get_market_data("BTC-USD")
        print(f"BTC price: ${market_data.price}")

        print("✅ Coinbase connection successful")
    else:
        print("❌ Connection failed")

asyncio.run(test_coinbase())
```

## 💰 Step 5: Funding Your Account

### Deposit Methods

#### Bank Transfer (ACH) - US Only
1. **Navigate** to Portfolio → Deposit
2. **Select** "US Dollar" or your local currency
3. **Choose** "Bank transfer (ACH)"
4. **Link bank account** (micro-deposit verification)
5. **Initiate transfer** (1-3 business days)
6. **No fees** for ACH transfers

#### Wire Transfer
1. **Select** "Wire transfer" option
2. **Get wire instructions** from Coinbase
3. **Initiate wire** from your bank
4. **Same day processing** (usually)
5. **$10 fee** for wire transfers

#### Debit Card
1. **Select** "Debit card" option
2. **Enter card details** and verify
3. **Instant deposit** (up to $1,000/day initially)
4. **3.99% fee** for debit card deposits

#### Cryptocurrency Deposits
1. **Select cryptocurrency** to deposit
2. **Copy deposit address**
3. **Send crypto** from external wallet
4. **Wait for confirmations**:
   - Bitcoin: 3 confirmations
   - Ethereum: 35 confirmations
   - Others: varies by coin

## 📊 Trading Features

### Supported Trading Pairs
Major cryptocurrencies available:
- **Bitcoin**: BTC-USD, BTC-EUR
- **Ethereum**: ETH-USD, ETH-EUR
- **Altcoins**: ADA-USD, DOT-USD, LINK-USD, etc.
- **Stablecoins**: USDC-USD (1:1 conversion)

### Order Types
- **Market Orders**: Execute immediately at current price
- **Limit Orders**: Execute at specified price or better
- **Stop Orders**: Trigger market order when price reached
- **Stop-Limit Orders**: Trigger limit order when price reached

### Fee Structure
**Coinbase Pro/Advanced Trade Fees**:
- **Maker**: 0.00% to 0.60% (based on volume)
- **Taker**: 0.05% to 0.60% (based on volume)
- **Volume tiers**: Higher volume = lower fees

**Regular Coinbase** (not recommended for trading):
- **Buy/Sell spread**: ~0.50%
- **Coinbase fee**: 1.49% to 3.99%

## ⚙️ Advanced Configuration

### Trading Parameters
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_api_secret",
  "passphrase": "your_passphrase",
  "trading_config": {
    "default_order_type": "limit",
    "time_in_force": "GTC",
    "post_only": false,
    "stp": "dc"
  },
  "risk_management": {
    "max_position_size_usd": 10000,
    "enable_stop_losses": true,
    "max_slippage_pct": 0.1
  }
}
```

### Symbol Formats
Coinbase uses dash-separated symbols:
```python
# Coinbase format
"BTC-USD"   # Bitcoin vs US Dollar
"ETH-USD"   # Ethereum vs US Dollar
"ADA-USD"   # Cardano vs US Dollar
"DOT-USD"   # Polkadot vs US Dollar

# These work directly with PowerTraderAI+
symbols = ["BTC-USD", "ETH-USD", "ADA-USD"]
```

### Rate Limits
- **Private endpoints**: 10 requests per second
- **Public endpoints**: 10 requests per second
- **Orders**: 5 orders per second
- **Bursts**: Short bursts allowed up to limits

## 🚨 Troubleshooting

### Common Issues

#### ❌ "Invalid API Key"
**Causes**:
- Incorrect API credentials
- API key not activated
- Wrong passphrase

**Solutions**:
1. Verify all three credentials (key, secret, passphrase)
2. Check API key is enabled in Coinbase Pro
3. Regenerate API key if necessary
4. Ensure you're using Pro/Advanced Trade (not regular Coinbase)

#### ❌ "Insufficient permissions"
**Causes**:
- API missing Trade permissions
- Account verification incomplete
- Region restrictions

**Solutions**:
1. Enable Trade permissions for API key
2. Complete full account verification
3. Check if your region supports Pro trading
4. Verify account is in good standing

#### ❌ "Rate limit exceeded"
**Causes**:
- Too many requests per second
- Multiple applications using same API
- Burst of requests

**Solutions**:
1. Implement request throttling (max 10/sec)
2. Use WebSocket feed for market data
3. Space out API calls
4. Check for other applications using API

#### ❌ "Product not found"
**Causes**:
- Invalid trading pair symbol
- Trading pair not available in your region
- Symbol format incorrect

**Solutions**:
1. Verify symbol format (BTC-USD not BTCUSD)
2. Check available products for your region
3. Use only supported trading pairs
4. Check Coinbase Pro product list

### Support Resources
- **Coinbase Support**: help.coinbase.com
- **API Documentation**: docs.cloud.coinbase.com
- **Status Page**: status.coinbase.com
- **Community**: reddit.com/r/CoinbaseSupport

## 🔒 Security Best Practices

### API Security
- **IP Restrictions**: Whitelist your IP addresses only
- **Minimal permissions**: Only enable View and Trade
- **Regular monitoring**: Review API activity logs
- **Key rotation**: Change API keys periodically

### Account Security
- **Strong 2FA**: Use app-based TOTP (not SMS)
- **Unique passwords**: Don't reuse passwords
- **Vault storage**: Use Coinbase Vault for long-term storage
- **Device security**: Keep devices secure and updated

### Trading Security
- **Start small**: Test with minimal amounts
- **Monitor closely**: Watch for unexpected activity
- **Withdrawal security**: Set up withdrawal whitelisting
- **Backup access**: Store recovery information safely

## 📈 Performance Optimization

### WebSocket Integration
```python
import asyncio
import json
import websockets

async def coinbase_websocket():
    uri = "wss://ws-feed.exchange.coinbase.com"

    subscribe_msg = {
        "type": "subscribe",
        "product_ids": ["BTC-USD", "ETH-USD"],
        "channels": ["ticker"]
    }

    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps(subscribe_msg))

        async for message in websocket:
            data = json.loads(message)
            if data.get('type') == 'ticker':
                symbol = data['product_id']
                price = float(data['price'])
                print(f"{symbol}: ${price:,.2f}")
```

### Connection Optimization
```python
import aiohttp
import asyncio

class CoinbaseOptimized:
    def __init__(self, api_key, api_secret, passphrase):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.session = None

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=20,
            ttl_dns_cache=300,
            use_dns_cache=True
        )

        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
```

### Fee Optimization
- **Use Pro/Advanced**: Much lower fees than regular Coinbase
- **Maker orders**: Use limit orders to pay maker fees
- **Volume tiers**: Increase trading volume for better rates
- **USDC trading**: No fees for USD ↔ USDC conversion

---

**Coinbase Setup Complete!** Your trusted and regulated cryptocurrency exchange integration is ready for PowerTraderAI+.
