# OKX Exchange Setup Guide

## Overview
OKX (formerly OKEx) is a leading global cryptocurrency exchange offering comprehensive trading services including spot, futures, options, and DeFi products. Known for innovation, deep liquidity, and competitive fees.

## 🌍 Regional Availability
- **Global**: Available in 180+ countries
- **Restrictions**: Not available in US, Singapore (residents), and some restricted regions
- **Popular regions**: Europe, Asia, Latin America, Middle East, Africa

⚠️ **Important**: Verify local regulations and compliance before using OKX in your jurisdiction.

## 📋 Prerequisites

### Account Requirements
- Valid government-issued photo ID
- Proof of address (for higher verification levels)
- Age 18 or older
- Non-restricted country residence
- Mobile phone number

### Trading Prerequisites
- Completed identity verification (KYC)
- Two-factor authentication enabled
- Deposited cryptocurrency (OKX is primarily crypto-focused)

## 🚀 Step 1: Create OKX Account

### Registration Process
1. **Visit** [okx.com](https://okx.com)
2. **Click** "Sign up"
3. **Choose registration method**:
   - Email address (recommended)
   - Mobile phone number
4. **Enter details** and create strong password
5. **Complete verification** via email/SMS
6. **Accept terms** and complete registration

### Identity Verification (KYC)
OKX offers progressive verification levels:

#### Level 0 (Basic)
- **No verification required**
- **Withdrawal limit**: 10 BTC per day
- **Deposit limit**: Unlimited
- **Features**: Basic trading

#### Level 1 (Individual Verification)
- **Government ID required**
- **Withdrawal limit**: 500 BTC per day
- **Additional features**: Higher limits, advanced trading

#### Level 2 (Advanced Verification)
- **Proof of address required**
- **Withdrawal limit**: 2000+ BTC per day
- **Features**: Maximum limits, institutional features

**Verification Steps**:
1. **Navigate** to Profile → Verification
2. **Select** verification level
3. **Upload documents**:
   - Government-issued photo ID
   - Proof of address (utility bill, bank statement)
4. **Complete facial recognition**
5. **Wait for approval** (usually 1-24 hours)

## 🔑 Step 2: API Key Creation

### Access API Management
1. **Log in** to your OKX account
2. **Navigate** to Profile → API
3. **Click** "Create API Key"
4. **Complete security verification** (2FA + email confirmation)

### Configure API Permissions
Select appropriate permissions for trading:
- ✅ **Read**: View account information and balances
- ✅ **Trade**: Place and cancel orders
- ✅ **Withdraw**: Only if needed (not recommended for bots)

### API Key Settings
```
API Key Name: PowerTraderAI+ Bot
Permissions:
  ✅ Read (Account info, balances, orders)
  ✅ Trade (Buy, sell, cancel orders)
  ❌ Withdraw (Disabled for security)

IP Whitelist: [Your IP Address] (mandatory for withdrawal permission)
Passphrase: [Your secure passphrase]
```

### Save Your Credentials
You'll receive:
- **API Key**: `your_api_key_here`
- **Secret Key**: `your_secret_key_here`
- **Passphrase**: `your_passphrase_here`

⚠️ **Critical**: Store all three credentials securely - you cannot retrieve them later!

## 🔐 Step 3: Configure PowerTraderAI+

### Credential File Setup
Create `credentials/okx_config.json`:
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_secret_key",
  "passphrase": "your_passphrase",
  "sandbox": false,
  "base_url": "https://www.okx.com"
}
```

### Environment Variables (Production)
```bash
export OKX_API_KEY="your_api_key"
export OKX_API_SECRET="your_secret_key"
export OKX_PASSPHRASE="your_passphrase"
```

### GUI Configuration
1. Launch PowerTraderAI+: `python app/pt_hub.py`
2. Go to **Settings** → **Exchange Provider Settings**
3. Set **Region**: "global"
4. Select **Primary Exchange**: "okx"
5. Click **Exchange Setup** button
6. Enter all three credentials when prompted

## 🔧 Step 4: Testing Connection

### Manual Test
```bash
cd app
python test_exchanges.py --exchange=okx
```

### Expected Output
```
Testing OKX connection...
✅ API authentication successful
✅ Account access verified
✅ Trading permissions confirmed
✅ Market data retrieved
Current BTC price: $43,250.50
```

### Programmatic Test
```python
from pt_exchanges import OKXExchange
import asyncio

async def test_okx():
    exchange = OKXExchange({
        "api_key": "your_api_key",
        "api_secret": "your_secret_key",
        "passphrase": "your_passphrase"
    })

    if await exchange.initialize():
        # Test account access
        balance = await exchange.get_balance()
        print(f"Account balance: {balance}")

        # Test market data
        market_data = await exchange.get_market_data("BTC-USDT")
        print(f"BTC price: ${market_data.price}")

        print("✅ OKX connection successful")
    else:
        print("❌ Connection failed")

asyncio.run(test_okx())
```

## 💰 Step 5: Funding Your Account

### Cryptocurrency Deposits (Primary Method)
OKX primarily uses cryptocurrency funding:

#### Deposit Process
1. **Navigate** to Assets → Deposit
2. **Select cryptocurrency** (USDT, BTC, ETH, etc.)
3. **Choose blockchain network**:
   - **ERC-20**: Ethereum (higher fees, more secure)
   - **TRC-20**: Tron (lower fees, faster)
   - **BSC (BEP-20)**: Binance Smart Chain
   - **Polygon**: Low-cost Ethereum layer 2
   - **Others**: 20+ blockchain networks supported
4. **Copy deposit address**
5. **Send crypto** from external wallet
6. **Wait for confirmations**

⚠️ **Network Warning**: Always double-check the network! Wrong network = permanent loss.

#### Popular Deposit Cryptocurrencies
- **USDT**: Most liquid for trading (multiple networks)
- **USDC**: USD-backed stablecoin
- **BTC**: Bitcoin (slower but secure)
- **ETH**: Ethereum (versatile)
- **OKB**: OKX native token (fee discounts)

### Alternative Funding Methods
- **P2P Trading**: Buy crypto directly from other users
- **Credit/Debit Card**: Instant purchase (higher fees)
- **Bank Transfer**: Available in select regions

### Confirmation Times
- **USDT (TRC-20)**: ~2-5 minutes
- **USDT (ERC-20)**: ~10-30 minutes
- **BTC**: ~30-60 minutes
- **ETH**: ~5-15 minutes
- **BSC tokens**: ~3-10 minutes

## 📊 Trading Features

### Supported Markets

#### Spot Trading
- **Major pairs**: BTC/USDT, ETH/USDT, ADA/USDT
- **Altcoins**: 400+ trading pairs
- **Cross trading**: Crypto-to-crypto pairs
- **Margin trading**: Up to 10x leverage

#### Derivatives Trading
- **Perpetual Swaps**: BTC, ETH, altcoins
- **Quarterly Futures**: Expiring contracts
- **Options**: European and American style
- **Leveraged tokens**: Simplified leverage exposure

#### DeFi and Innovation
- **Earn products**: Staking and lending
- **NFT marketplace**: Digital collectibles
- **DeFi hub**: Decentralized finance protocols
- **Web3 integration**: Blockchain ecosystem tools

### Order Types
- **Market Orders**: Execute at current market price
- **Limit Orders**: Execute at specific price or better
- **Post-only Orders**: Only add liquidity (maker orders)
- **Fill-or-Kill (FOK)**: Execute completely or cancel
- **Immediate-or-Cancel (IOC)**: Execute partial and cancel remainder
- **Iceberg Orders**: Hide large order quantities
- **TWAP Orders**: Time-weighted average price
- **Algo Orders**: Various algorithmic order types

## ⚙️ Advanced Configuration

### Trading Parameters
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_secret_key",
  "passphrase": "your_passphrase",
  "trading_config": {
    "default_order_type": "limit",
    "default_tif": "GTC",
    "margin_mode": "isolated",
    "position_side": "net"
  },
  "risk_management": {
    "max_position_size_usdt": 10000,
    "enable_stop_losses": true,
    "max_leverage": 5
  }
}
```

### Symbol Formats
OKX uses dash-separated symbols:
```python
# Spot trading symbols
"BTC-USDT"   # Bitcoin vs USDT (spot)
"ETH-USDT"   # Ethereum vs USDT (spot)
"ADA-USDT"   # Cardano vs USDT (spot)

# Perpetual swap symbols
"BTC-USD-SWAP"   # Bitcoin perpetual (USD)
"ETH-USD-SWAP"   # Ethereum perpetual (USD)

# Futures symbols
"BTC-USD-240329"  # Bitcoin future expiring March 29, 2024
```

## 🚨 Troubleshooting

### Common Issues

#### ❌ "Invalid API key"
**Causes**:
- Incorrect API credentials
- API key not activated
- Wrong passphrase

**Solutions**:
1. Verify all three credentials (key, secret, passphrase)
2. Check API key status in OKX account
3. Ensure passphrase matches exactly
4. Regenerate API key if necessary

#### ❌ "Request timestamp expired"
**Causes**:
- System clock not synchronized
- High network latency
- Wrong timezone settings

**Solutions**:
1. Synchronize system clock (use NTP)
2. Check internet connection stability
3. Increase timestamp tolerance in code
4. Verify timezone settings

#### ❌ "Insufficient permissions"
**Causes**:
- API missing required permissions
- Account verification incomplete
- Trading restrictions

**Solutions**:
1. Enable Read and Trade permissions
2. Complete identity verification
3. Check account status and restrictions
4. Contact OKX support if needed

#### ❌ "Rate limit exceeded"
**Causes**:
- Too many requests per second
- Multiple trading applications
- Burst requests

**Solutions**:
1. Implement request throttling (20 requests/2 seconds)
2. Use WebSocket feeds for market data
3. Space out API calls appropriately
4. Monitor rate limit headers

### Support Resources
- **OKX Support**: okx.com/support/hc
- **API Documentation**: okx.com/docs-v5
- **Status Page**: status.okx.com
- **Community**: t.me/OKXOfficial_English

## 🔒 Security Best Practices

### API Security
- **Passphrase strength**: Use complex, unique passphrase
- **IP restrictions**: Whitelist specific IP addresses
- **Permission minimization**: Only enable required permissions
- **Regular audits**: Monitor API activity logs

### Account Security
- **Two-Factor Authentication**: Use TOTP authenticator (not SMS)
- **Anti-phishing code**: Set up unique anti-phishing identifier
- **Email security**: Secure your registered email account
- **Login monitoring**: Enable login notifications

### Trading Security
- **Start conservative**: Begin with small position sizes
- **Risk management**: Always use stop-losses
- **Position monitoring**: Check positions regularly
- **Withdrawal security**: Use address whitelisting

## 📈 Performance Optimization

### API Rate Limits
OKX rate limits per IP:
- **REST API**: 20 requests per 2 seconds
- **WebSocket**: 240 connections per minute
- **Order placement**: 60 orders per 2 seconds

### WebSocket Integration
```python
import asyncio
import websockets
import json

async def okx_websocket():
    uri = "wss://ws.okx.com:8443/ws/v5/public"

    subscribe_msg = {
        "op": "subscribe",
        "args": [
            {"channel": "tickers", "instId": "BTC-USDT"}
        ]
    }

    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps(subscribe_msg))

        async for message in websocket:
            data = json.loads(message)
            if data.get('arg', {}).get('channel') == 'tickers':
                ticker_data = data['data'][0]
                price = float(ticker_data['last'])
                print(f"BTC price: ${price:,.2f}")
```

### Fee Optimization
- **OKB holdings**: Hold OKB tokens for fee discounts
- **VIP levels**: Higher trading volume = lower fees
- **Maker orders**: Use limit orders for maker rebates
- **Trading competitions**: Participate for additional rewards

### Advanced Trading Features
```python
# Example: OKX algo order setup
algo_order = {
    "instId": "BTC-USDT",
    "tdMode": "cash",  # Trading mode
    "side": "buy",
    "ordType": "conditional",  # Conditional order
    "sz": "0.01",             # Order size
    "triggerPx": "40000",     # Trigger price
    "orderPx": "39900",       # Order price
    "triggerPxType": "last",  # Trigger price type
    "timeInForce": "GTC"      # Time in force
}
```

### Multi-Asset Portfolio Management
```python
# Monitor multiple assets
portfolio_config = {
    "assets": ["BTC-USDT", "ETH-USDT", "ADA-USDT"],
    "allocation": {
        "BTC-USDT": 0.4,  # 40% allocation
        "ETH-USDT": 0.3,  # 30% allocation
        "ADA-USDT": 0.3   # 30% allocation
    },
    "rebalance_threshold": 0.05  # Rebalance at 5% drift
}
```

---

**OKX Setup Complete!** Your comprehensive cryptocurrency trading integration is ready for PowerTraderAI+ with access to spot, derivatives, and DeFi markets.
