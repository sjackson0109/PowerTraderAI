# Bybit Exchange Setup Guide

## Overview
Bybit is a leading cryptocurrency derivatives exchange known for its advanced trading features, high liquidity, and competitive fees. Popular among professional traders and institutions worldwide.

## 🌍 Regional Availability
- **Global**: Available in 160+ countries
- **Restrictions**: Not available in US, UK (residents), and some restricted regions
- **Popular regions**: Asia, Europe, Middle East, Africa, Latin America

⚠️ **Important**: Check local regulations before using Bybit. Some countries restrict derivatives trading.

## 📋 Prerequisites

### Account Requirements
- Valid government-issued photo ID
- Proof of address document (for higher limits)
- Age 18 or older
- Non-restricted country residence
- Mobile phone number

### Trading Prerequisites
- Completed identity verification (KYC)
- Two-factor authentication enabled
- Deposited cryptocurrency (Bybit is crypto-only)

## 🚀 Step 1: Create Bybit Account

### Registration Process
1. **Visit** [bybit.com](https://bybit.com)
2. **Click** "Sign Up"
3. **Choose registration method**:
   - Email + password (recommended)
   - Phone number + SMS
4. **Complete email/SMS verification**
5. **Set strong password** with required complexity

### Identity Verification (KYC)
Bybit offers multiple verification levels:

#### Level 0 (No KYC)
- **Withdrawal limit**: 2 BTC per day
- **Deposit limit**: Unlimited
- **Features**: Basic trading

#### Level 1 (Basic KYC)
- **Upload government ID**
- **Withdrawal limit**: 50 BTC per day
- **Additional features**: Higher limits

#### Level 2 (Advanced KYC)
- **Proof of address required**
- **Withdrawal limit**: 100+ BTC per day
- **Features**: Maximum limits, special features

**Verification Process**:
1. **Navigate** to Account → Verification
2. **Select** verification level
3. **Upload documents**:
   - Government-issued photo ID
   - Proof of address (for Level 2)
4. **Complete facial verification**
5. **Wait for approval** (usually 1-24 hours)

## 🔑 Step 2: API Key Creation

### Access API Management
1. **Log in** to your Bybit account
2. **Navigate** to Account → API Management
3. **Click** "Create New Key"
4. **Choose API type**: "System-generated API Keys"

### Configure API Permissions
Enable necessary permissions for trading:
- ✅ **Read-Write**: Required for trading operations
- ✅ **Contract**: For futures/derivatives trading
- ✅ **Spot**: For spot trading
- ✅ **Wallet**: For balance information
- ✅ **Options**: For options trading (optional)
- ❌ **Withdraw**: Disable for security

### API Key Settings
```
API Key Name: PowerTraderAI+ Bot
Permissions:
  ✅ Read-Write
  ✅ Contract (Futures/Derivatives)
  ✅ Spot (Spot Trading)
  ✅ Wallet (Balance/Transfer)
  ❌ Withdraw (Disabled for security)

IP Restriction: [Your IP Address] (highly recommended)
Read-Only: ❌ (Need Read-Write for trading)
```

### Save Your Credentials
You'll receive:
- **API Key**: `your_api_key_here`
- **Secret Key**: `your_secret_key_here`

⚠️ **Security**: Store these securely and never share them!

## 🔐 Step 3: Configure PowerTraderAI+

### Credential File Setup
Create `credentials/bybit_config.json`:
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_secret_key",
  "testnet": false,
  "base_url": "https://api.bybit.com"
}
```

### Testnet Configuration (Optional)
For testing without real funds:
```json
{
  "api_key": "your_testnet_api_key",
  "api_secret": "your_testnet_secret",
  "testnet": true,
  "base_url": "https://api-testnet.bybit.com"
}
```

### Environment Variables (Production)
```bash
export BYBIT_API_KEY="your_api_key"
export BYBIT_API_SECRET="your_secret_key"
export BYBIT_TESTNET="false"
```

### GUI Configuration
1. Launch PowerTraderAI+: `python app/pt_hub.py`
2. Go to **Settings** → **Exchange Provider Settings**
3. Set **Region**: "global"
4. Select **Primary Exchange**: "bybit"
5. Click **Exchange Setup** button
6. Enter API credentials when prompted

## 🔧 Step 4: Testing Connection

### Manual Test
```bash
cd app
python test_exchanges.py --exchange=bybit
```

### Expected Output
```
Testing Bybit connection...
✅ API authentication successful
✅ Account balance retrieved
✅ Trading permissions verified
✅ Market data available
Current BTC price: $43,250.50
```

### Programmatic Test
```python
from pt_exchanges import BybitExchange
import asyncio

async def test_bybit():
    exchange = BybitExchange({
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

        print("✅ Bybit connection successful")
    else:
        print("❌ Connection failed")

asyncio.run(test_bybit())
```

## 💰 Step 5: Funding Your Account

### Cryptocurrency Deposits (Only Option)
Bybit is crypto-only - no fiat deposits:

#### Deposit Process
1. **Navigate** to Assets → Deposit
2. **Select cryptocurrency** (USDT, BTC, ETH, etc.)
3. **Choose network**:
   - **ERC20**: Ethereum network (higher fees)
   - **TRC20**: Tron network (lower fees)
   - **BEP20**: Binance Smart Chain
   - **Others**: Various blockchain networks
4. **Copy deposit address**
5. **Send crypto** from external wallet
6. **Wait for confirmations**

⚠️ **Critical**: Always verify the correct network! Sending to wrong network = lost funds.

#### Supported Deposit Cryptocurrencies
- **USDT**: Tether (most popular for trading)
- **USDC**: USD Coin
- **BTC**: Bitcoin
- **ETH**: Ethereum
- **BNB**: Binance Coin
- **And 100+ other cryptocurrencies**

### Deposit Times & Confirmations
- **USDT (TRC20)**: ~2-5 minutes, 19 confirmations
- **USDT (ERC20)**: ~10-30 minutes, 12 confirmations
- **BTC**: ~30-60 minutes, 2 confirmations
- **ETH**: ~5-15 minutes, 12 confirmations

## 📊 Trading Features

### Supported Markets
Bybit specializes in derivatives but also offers spot:

#### Spot Trading
- **Major pairs**: BTC/USDT, ETH/USDT, etc.
- **Altcoins**: 200+ trading pairs
- **Stablecoins**: USDT, USDC pairs

#### Derivatives (Primary Focus)
- **Perpetual Futures**: BTC, ETH, altcoins
- **Quarterly Futures**: Expiring contracts
- **Options**: European-style options
- **Leveraged Tokens**: Leveraged exposure without margin

### Order Types
- **Market Orders**: Execute immediately
- **Limit Orders**: Execute at specific price
- **Conditional Orders**: Trigger when conditions met
- **Stop Loss**: Risk management orders
- **Take Profit**: Profit-taking orders
- **Iceberg Orders**: Hide large order quantities

### Advanced Features
- **Leverage**: Up to 100x on perpetual futures
- **Cross Margin**: Share margin across positions
- **Isolated Margin**: Separate margin per position
- **Copy Trading**: Follow successful traders
- **Grid Trading**: Automated grid strategies

## ⚙️ Advanced Configuration

### Trading Parameters
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_secret_key",
  "trading_config": {
    "default_leverage": 1,
    "margin_mode": "isolated",
    "order_type": "limit",
    "time_in_force": "GTC"
  },
  "risk_management": {
    "max_position_size_usdt": 10000,
    "enable_stop_losses": true,
    "max_leverage": 10
  }
}
```

### Symbol Formats
Bybit uses specific symbol conventions:
```python
# Spot trading symbols
"BTCUSDT"   # Bitcoin vs USDT (spot)
"ETHUSDT"   # Ethereum vs USDT (spot)

# Perpetual futures symbols
"BTCUSD"    # Bitcoin perpetual (USD)
"ETHUSD"    # Ethereum perpetual (USD)
"BTCUSDT"   # Bitcoin perpetual (USDT)

# PowerTrader conversion handles this automatically
```

## 🚨 Troubleshooting

### Common Issues

#### ❌ "Forbidden, request ip is not in api whitelist"
**Causes**:
- IP address not whitelisted
- Dynamic IP changed
- VPN usage

**Solutions**:
1. Add your current IP to API whitelist
2. Use static IP or update whitelist regularly
3. Disable VPN if using
4. Check current IP: whatismyipaddress.com

#### ❌ "Invalid API key"
**Causes**:
- Incorrect API credentials
- API key not activated
- Wrong environment (testnet vs mainnet)

**Solutions**:
1. Verify API key and secret
2. Check API key is enabled
3. Ensure using correct environment
4. Regenerate API key if necessary

#### ❌ "Insufficient balance"
**Causes**:
- Not enough funds for trade
- Funds locked in other positions
- Wrong wallet (spot vs contract)

**Solutions**:
1. Check account balances
2. Close unnecessary positions
3. Transfer between wallets if needed
4. Deposit more cryptocurrency

#### ❌ "Rate limit exceeded"
**Causes**:
- Too many requests per second
- Multiple trading applications
- Burst of requests

**Solutions**:
1. Implement request throttling
2. Use WebSocket for real-time data
3. Space out API calls
4. Check rate limit documentation

### Support Resources
- **Bybit Support**: bybit.com/en-US/help-center
- **API Documentation**: bybit-exchange.github.io/docs
- **Status Page**: bybit.statuspage.io
- **Community**: t.me/bybitEnglish

## 🔒 Security Best Practices

### API Security
- **IP Whitelisting**: Always restrict to specific IPs
- **Minimal permissions**: Only enable required permissions
- **Regular monitoring**: Check API activity logs
- **Key rotation**: Change API keys monthly

### Account Security
- **2FA Authentication**: Enable Google Authenticator
- **Strong passwords**: Use unique, complex passwords
- **Anti-phishing**: Enable anti-phishing codes
- **Login notifications**: Monitor login activity

### Trading Security
- **Start conservative**: Use low leverage initially
- **Risk management**: Set stop losses and position limits
- **Monitor positions**: Check positions regularly
- **Withdrawal security**: Use withdrawal whitelist

## 📈 Performance Optimization

### API Rate Limits
Bybit has generous rate limits:
- **Spot trading**: 120 requests per minute
- **Derivatives**: 120 requests per minute
- **WebSocket**: 500 connections per IP

### WebSocket Integration
```python
import asyncio
import websockets
import json

async def bybit_websocket():
    uri = "wss://stream.bybit.com/v5/public/spot"

    subscribe_msg = {
        "op": "subscribe",
        "args": ["tickers.BTCUSDT"]
    }

    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps(subscribe_msg))

        async for message in websocket:
            data = json.loads(message)
            if data.get('topic') == 'tickers.BTCUSDT':
                price = float(data['data']['lastPrice'])
                print(f"BTC price update: ${price:,.2f}")
```

### Trading Optimization
- **TRC20 USDT**: Use for lowest deposit fees
- **Maker orders**: Use limit orders for better fees
- **Volume discounts**: Higher volume = lower fees
- **VIP program**: Exclusive benefits for large traders

### Derivatives Strategies
```python
# Example: Simple futures trading setup
futures_config = {
    "leverage": 5,              # Conservative leverage
    "margin_mode": "isolated",  # Risk isolation
    "position_size_pct": 10,    # 10% of balance per trade
    "stop_loss_pct": 2,         # 2% stop loss
    "take_profit_pct": 6        # 6% take profit
}
```

---

**Bybit Setup Complete!** Your professional derivatives trading integration is ready for PowerTraderAI+.
