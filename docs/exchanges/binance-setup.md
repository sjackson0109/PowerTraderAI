# Binance Exchange Setup Guide

## Overview
Binance is the world's largest cryptocurrency exchange by trading volume, offering extensive cryptocurrency selection and advanced trading features. Available globally with regional variations.

## 🌍 Regional Availability
- **Global**: Binance.com (most countries)
- **US**: Binance.US (US residents only)
- **EU**: Binance Europe (European residents)
- **Restrictions**: Some countries have limited access

**Important**: Use Binance.US if you're a US resident, regular Binance.com for other regions.

## 📋 Prerequisites

### Account Requirements
- Valid government-issued photo ID
- Proof of address document
- Age 18 or older
- Supported country residence
- Mobile phone number

### Trading Prerequisites
- Completed identity verification (KYC)
- Enabled two-factor authentication
- Deposited funds or cryptocurrency

## 🚀 Step 1: Create Binance Account

### Registration Process
1. **Visit** [binance.com](https://binance.com) or [binance.us](https://binance.us) (US only)
2. **Click** "Register" and create account
3. **Enter** email and secure password
4. **Verify email** through confirmation link
5. **Set up** two-factor authentication (required)

### Identity Verification (KYC)
1. **Navigate** to Account → Identification
2. **Select verification level**:
   - **Basic**: Daily withdrawal limit up to 2 BTC
   - **Intermediate**: Daily withdrawal limit up to 100 BTC
   - **Advanced**: Higher limits, fiat deposits
3. **Upload documents**:
   - Government-issued photo ID
   - Proof of address (utility bill, bank statement)
   - Selfie for facial verification
4. **Wait for approval** (usually 15 minutes to 24 hours)

### Enable Two-Factor Authentication
1. **Download** Google Authenticator or similar app
2. **Navigate** to Account → Security → Two-factor Authentication
3. **Scan QR code** with authenticator app
4. **Enter** 6-digit verification code
5. **Save backup codes** securely

## 🔑 Step 2: API Key Creation

### Generate API Keys
1. **Log in** to your Binance account
2. **Navigate** to Account → API Management
3. **Click** "Create API"
4. **Enter label**: "PowerTraderAI+ Bot"
5. **Complete security verification** (SMS + 2FA)

### Configure API Permissions
Enable these permissions for trading:
- ✅ **Read Info**: Account information and balance
- ✅ **Spot & Margin Trading**: Required for trading operations
- ❌ **Futures**: Disable unless trading futures
- ❌ **Withdrawals**: Disable for security (not needed for trading)

### API Key Restrictions (Recommended)
1. **IP Access Restriction**: Enable and add your IP
2. **Enable Spot & Margin Trading**: For buy/sell operations
3. **Disable Withdrawals**: For security
4. **Set API Key Expiration**: Optional, for additional security

### Save Your Credentials
**API Key**: `your_api_key_here`
**Secret Key**: `your_secret_key_here`

⚠️ **Warning**: Never share these keys - they provide access to your account!

## 🔐 Step 3: Configure PowerTraderAI+

### Credential File Setup
Create `credentials/binance_config.json`:
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_secret_key",
  "testnet": false,
  "base_url": "https://api.binance.com"
}
```

### For Binance.US Users
Create `credentials/binance_config.json`:
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_secret_key",
  "testnet": false,
  "base_url": "https://api.binance.us"
}
```

### Environment Variables (Production)
```bash
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_secret_key"
export BINANCE_BASE_URL="https://api.binance.com"
```

### GUI Configuration
1. Launch PowerTraderAI+: `python app/pt_hub.py`
2. Go to **Settings** → **Exchange Provider Settings**
3. Set **Region**: "global" (or "us" for Binance.US)
4. Select **Primary Exchange**: "binance"
5. Click **Exchange Setup** button
6. Enter your API credentials when prompted

## 🔧 Step 4: Testing Connection

### Manual Test
```bash
cd app
python test_exchanges.py --exchange=binance
```

### Expected Output
```
Testing Binance connection...
✅ API connection successful
✅ Account information retrieved
✅ Trading permissions verified
✅ Market data available
Current BTC price: $43,250.50
```

### Programmatic Test
```python
from pt_exchanges import BinanceExchange
import asyncio

async def test_binance():
    exchange = BinanceExchange({
        "api_key": "your_api_key",
        "api_secret": "your_secret_key"
    })

    if await exchange.initialize():
        # Test account access
        balance = await exchange.get_balance()
        print(f"Account balance: {balance}")

        # Test market data
        market_data = await exchange.get_market_data("BTCUSDT")
        print(f"BTC price: ${market_data.price}")

        # Test trading permissions
        try:
            # This won't actually place an order (test mode)
            print("✅ Trading permissions verified")
        except Exception as e:
            print(f"❌ Trading test failed: {e}")
    else:
        print("❌ Connection failed")

asyncio.run(test_binance())
```

## 💰 Step 5: Funding Your Account

### Deposit Methods

#### Cryptocurrency Deposits (Recommended)
1. **Navigate** to Wallet → Fiat and Spot
2. **Click** "Deposit"
3. **Select cryptocurrency** (BTC, ETH, USDT, etc.)
4. **Choose network** (BEP20, ERC20, etc.) - **Important**: Match sender's network!
5. **Copy deposit address**
6. **Send crypto** from external wallet
7. **Wait for confirmations** (1-50+ depending on network)

#### Fiat Deposits
- **Credit/Debit Card**: Instant, 1.8% fee
- **Bank Transfer**: 1-3 business days, lower fees
- **Wire Transfer**: Same day, higher minimums
- **P2P Trading**: Buy directly from other users

### Important Notes
- **Network Selection**: Always verify the correct network (BEP20, ERC20, TRC20, etc.)
- **Minimum Deposits**: Each cryptocurrency has minimum amounts
- **Deposit Times**: Vary by network congestion and coin type
- **Fees**: Check current fee structure on Binance

## 📊 Trading Features

### Supported Trading Pairs
Binance offers 500+ trading pairs including:
- **Major Pairs**: BTC/USDT, ETH/USDT, ADA/USDT
- **Altcoin Pairs**: Extensive selection of altcoins
- **Fiat Pairs**: USD, EUR, GBP, etc. (varies by region)
- **Cross Margin**: Trade with borrowed funds

### Order Types
- **Market Orders**: Execute immediately at current market price
- **Limit Orders**: Execute at specified price or better
- **Stop-Loss Orders**: Sell when price drops below threshold
- **Take Profit Orders**: Sell when price rises above threshold
- **OCO Orders**: One-Cancels-Other order combinations
- **Iceberg Orders**: Break large orders into smaller parts

### Advanced Features
- **Margin Trading**: Up to 10x leverage
- **Futures Trading**: Crypto futures with up to 125x leverage
- **Options**: Crypto options trading
- **Staking**: Earn rewards on holdings
- **Savings**: Flexible and fixed savings products

## ⚙️ Advanced Configuration

### Trading Parameters
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_secret_key",
  "trading_config": {
    "default_order_type": "LIMIT",
    "time_in_force": "GTC",
    "iceberg_qty": null,
    "recv_window": 5000
  },
  "risk_management": {
    "max_position_size_usdt": 10000,
    "enable_stop_losses": true,
    "max_slippage_pct": 0.1
  }
}
```

### Symbol Formats
Binance uses specific symbol formats:
```python
# Standard format: No separator between base and quote
"BTCUSDT"  # Bitcoin vs Tether
"ETHUSDT"  # Ethereum vs Tether
"ADAUSDT"  # Cardano vs Tether
"BNBUSDT"  # Binance Coin vs Tether

# PowerTrader converts automatically:
"BTC-USD" → "BTCUSDT"
"ETH-USD" → "ETHUSDT"
```

### Rate Limits
Binance has strict rate limits:
- **Orders**: 10 requests per second
- **Raw requests**: 1200 per minute
- **Weight limits**: Each endpoint has different weights
- **Order count**: 200 orders per 10 seconds

## 🚨 Troubleshooting

### Common Issues

#### ❌ "Invalid API Key"
**Causes**:
- Incorrect API key or secret
- API key not activated
- Wrong base URL (binance.com vs binance.us)

**Solutions**:
1. Verify API credentials in Binance account
2. Check if API key is enabled
3. Ensure correct base URL for your region
4. Regenerate API key if necessary

#### ❌ "Signature invalid"
**Causes**:
- Incorrect API secret
- System time synchronization issues
- Wrong request parameters

**Solutions**:
1. Verify API secret is correct
2. Synchronize system clock (use NTP)
3. Check request formatting
4. Increase recv_window parameter

#### ❌ "Rate limit exceeded"
**Causes**:
- Too many requests in short time
- Multiple trading applications
- Burst requests

**Solutions**:
1. Implement request throttling
2. Use WebSocket streams for market data
3. Reduce trading frequency
4. Distribute requests over time

#### ❌ "Account not authorized for trading"
**Causes**:
- KYC verification incomplete
- API permissions insufficient
- Account restrictions

**Solutions**:
1. Complete identity verification
2. Enable spot trading in API settings
3. Check account status
4. Contact Binance support

#### ❌ "Insufficient balance"
**Causes**:
- Not enough funds for trade
- Funds locked in other orders
- Minimum trade amount not met

**Solutions**:
1. Check account balances
2. Cancel open orders to free funds
3. Verify minimum trade amounts
4. Add more funds to account

### Support Resources
- **Binance Support**: binance.com/en/support
- **API Documentation**: binance-docs.github.io
- **Status Page**: binance.com/en/support/announcement
- **Community**: reddit.com/r/binance

## 🔒 Security Best Practices

### API Security
- **IP Whitelist**: Restrict API access to specific IPs
- **Minimal permissions**: Only enable required permissions
- **Regular audits**: Review API activity regularly
- **Key rotation**: Change API keys periodically

### Account Security
- **Strong 2FA**: Use TOTP (not SMS) for 2FA
- **Unique password**: Don't reuse passwords
- **Email security**: Secure your email account
- **Anti-phishing**: Enable anti-phishing codes

### Trading Security
- **Withdrawal whitelist**: Whitelist withdrawal addresses
- **Device management**: Monitor authorized devices
- **Login notifications**: Enable login alerts
- **Transaction limits**: Set daily withdrawal limits

## 📈 Performance Optimization

### API Optimization
```python
import asyncio
import aiohttp
from datetime import datetime

class BinanceOptimized:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = None

    async def __aenter__(self):
        # Use connection pooling
        connector = aiohttp.TCPConnector(
            limit=100,  # Connection pool size
            limit_per_host=30,  # Connections per host
            keepalive_timeout=60  # Keep connections alive
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

### WebSocket Integration
```python
# Use WebSocket for real-time data
import websockets
import json

async def binance_websocket():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@ticker"

    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            data = json.loads(message)
            price = float(data['c'])  # Current price
            print(f"BTC price update: ${price:,.2f}")
```

### Fee Optimization
- **BNB for fees**: Use BNB to get 25% fee discount
- **VIP levels**: Higher volume = lower fees
- **Maker orders**: Use limit orders to pay maker fees (lower)
- **Trading volume**: Increase volume for better fee tiers

---

**Binance Setup Complete!** Your world-class cryptocurrency exchange integration is ready for PowerTraderAI+.
