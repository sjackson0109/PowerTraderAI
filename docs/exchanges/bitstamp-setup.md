# Bitstamp Exchange Setup Guide

## Overview
Bitstamp is one of Europe's oldest and most trusted cryptocurrency exchanges, founded in 2011. Known for strong regulatory compliance, security, and reliability, particularly popular in European markets.

## 🌍 Regional Availability
- **EU**: Fully licensed across European Union
- **UK**: FCA authorized and regulated
- **US**: Available in most US states
- **Global**: 50+ countries supported worldwide

## 📋 Prerequisites

### Account Requirements
- Valid government-issued photo ID
- Proof of address (utility bill, bank statement)
- Age 18 or older
- Supported country residence
- Bank account for fiat deposits

### Trading Prerequisites
- Completed identity verification (KYC)
- Enabled two-factor authentication
- Deposited funds (fiat or cryptocurrency)

## 🚀 Step 1: Create Bitstamp Account

### Registration Process
1. **Visit** [bitstamp.net](https://bitstamp.net)
2. **Click** "Register" and create account
3. **Enter** email, password, and country
4. **Verify email** through confirmation link
5. **Complete** basic profile information

### Identity Verification (KYC)
Bitstamp requires thorough verification:

#### Personal Information
1. **Full name** as it appears on ID
2. **Date of birth** and nationality
3. **Residential address** with postal code
4. **Phone number** with country code

#### Document Upload
1. **Government ID**:
   - Passport (preferred for international users)
   - Driver's license
   - National ID card
2. **Proof of Address** (dated within 3 months):
   - Utility bill (electricity, gas, water)
   - Bank statement
   - Government correspondence
3. **Selfie verification**: Hold ID next to face

#### Additional Information
- **Source of funds**: Employment, savings, investment, etc.
- **Trading experience**: Previous crypto trading history
- **Expected trading volume**: Monthly trading estimates

**Verification time**: Usually 1-3 business days

## 🔑 Step 2: API Key Creation

### Access API Settings
1. **Log in** to your Bitstamp account
2. **Navigate** to Account → Security → API Access
3. **Click** "New API Key"
4. **Complete 2FA verification**

### Configure API Permissions
Enable required permissions for trading:
- ✅ **Account balance**: View account balances
- ✅ **User transactions**: View transaction history
- ✅ **Open orders**: View and manage orders
- ✅ **Buy order**: Place buy orders
- ✅ **Sell order**: Place sell orders
- ❌ **Withdrawal requests**: Disable for security
- ❌ **Crypto withdrawal**: Disable for security

### API Key Configuration
```
API Key Description: PowerTraderAI+ Bot
Permissions:
  ✅ Account balance
  ✅ User transactions
  ✅ Open orders
  ✅ Buy order
  ✅ Sell order
  ❌ Withdrawal requests
  ❌ Crypto withdrawal

IP Restriction: [Your IP Address] (highly recommended)
```

### Save Your Credentials
You'll receive:
- **API Key**: `your_api_key_here`
- **API Secret**: `your_api_secret_here`

⚠️ **Important**: Store these securely - Bitstamp won't show them again!

## 🔐 Step 3: Configure PowerTraderAI+

### Credential File Setup
Create `credentials/bitstamp_config.json`:
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_api_secret",
  "customer_id": "your_customer_id",
  "api_version": "v2"
}
```

### Find Your Customer ID
1. **Log in** to Bitstamp account
2. **Go to** Account → Account Information
3. **Copy** Customer ID number

### Environment Variables (Production)
```bash
export BITSTAMP_API_KEY="your_api_key"
export BITSTAMP_API_SECRET="your_api_secret"
export BITSTAMP_CUSTOMER_ID="your_customer_id"
```

### GUI Configuration
1. Launch PowerTraderAI+: `python app/pt_hub.py`
2. Go to **Settings** → **Exchange Provider Settings**
3. Set **Region**: "eu" (or "global")
4. Select **Primary Exchange**: "bitstamp"
5. Click **Exchange Setup** button
6. Enter API credentials when prompted

## 🔧 Step 4: Testing Connection

### Manual Test
```bash
cd app
python test_exchanges.py --exchange=bitstamp
```

### Expected Output
```
Testing Bitstamp connection...
✅ API authentication successful
✅ Account balance retrieved
✅ Trading permissions verified
✅ Market data available
Current BTC price: €39,750.25
```

### Programmatic Test
```python
from pt_exchanges import BitstampExchange
import asyncio

async def test_bitstamp():
    exchange = BitstampExchange({
        "api_key": "your_api_key",
        "api_secret": "your_api_secret",
        "customer_id": "your_customer_id"
    })

    if await exchange.initialize():
        # Test account access
        balance = await exchange.get_balance()
        print(f"Account balance: {balance}")

        # Test market data
        market_data = await exchange.get_market_data("btceur")
        print(f"BTC price: €{market_data.price}")

        print("✅ Bitstamp connection successful")
    else:
        print("❌ Connection failed")

asyncio.run(test_bitstamp())
```

## 💰 Step 5: Funding Your Account

### Deposit Methods

#### SEPA Bank Transfer (EU) - Recommended
1. **Navigate** to Deposit → EUR
2. **Select** "SEPA bank transfer"
3. **Copy** Bitstamp bank details
4. **Initiate transfer** from your bank
5. **Include reference number** in transfer description
6. **Processing time**: Same day to 1 business day
7. **No fees** for SEPA transfers

#### International Wire Transfer
1. **Select** "International wire transfer"
2. **Get wire instructions** for your currency
3. **Initiate wire** from your bank
4. **Include all required references**
5. **Processing time**: 1-5 business days
6. **Fees**: €7.50 + correspondent bank fees

#### Credit/Debit Card (Instant)
1. **Navigate** to Deposit → Card
2. **Enter** card details and amount
3. **Complete 3D Secure** verification
4. **Instant processing** (usually)
5. **Fees**: 5% fee + potential card fees
6. **Limits**: €1,000 daily, €10,000 monthly

#### Cryptocurrency Deposits
1. **Select cryptocurrency** to deposit
2. **Generate** deposit address
3. **Send crypto** from external wallet
4. **Wait for confirmations**:
   - Bitcoin: 1 confirmation
   - Ethereum: 12 confirmations
   - Other coins: varies

## 📊 Trading Features

### Supported Trading Pairs
Bitstamp focuses on major cryptocurrencies:
- **Bitcoin**: BTC/EUR, BTC/USD, BTC/GBP
- **Ethereum**: ETH/EUR, ETH/USD, ETH/BTC
- **Litecoin**: LTC/EUR, LTC/USD, LTC/BTC
- **XRP**: XRP/EUR, XRP/USD, XRP/BTC
- **Bitcoin Cash**: BCH/EUR, BCH/USD, BCH/BTC
- **Chainlink**: LINK/EUR, LINK/USD
- **Others**: ADA, DOT, UNI, AAVE, etc.

### Order Types
- **Market Orders**: Execute immediately at current price
- **Limit Orders**: Execute at specified price or better
- **Stop Orders**: Market order triggered at stop price
- **Stop-Limit Orders**: Limit order triggered at stop price
- **Trailing Stop**: Dynamic stop that follows price

### Fee Structure
**Trading Fees** (based on 30-day volume):
- **0-20,000 EUR**: 0.50% maker, 0.50% taker
- **20,000-100,000 EUR**: 0.25% maker, 0.25% taker
- **100,000+ EUR**: Lower fees with volume tiers

**Other Fees**:
- **Deposits**: Free (SEPA), varies for others
- **Withdrawals**: €3 (SEPA), varies for crypto

## ⚙️ Advanced Configuration

### Trading Parameters
```json
{
  "api_key": "your_api_key",
  "api_secret": "your_api_secret",
  "customer_id": "your_customer_id",
  "trading_config": {
    "default_currency": "eur",
    "precision": 2,
    "timeout": 30
  },
  "risk_management": {
    "max_position_size_eur": 10000,
    "enable_stop_losses": true,
    "max_slippage_pct": 0.2
  }
}
```

### Symbol Formats
Bitstamp uses lowercase concatenated symbols:
```python
# Bitstamp format
"btceur"    # Bitcoin vs Euro
"btcusd"    # Bitcoin vs US Dollar
"etheur"    # Ethereum vs Euro
"ethusd"    # Ethereum vs US Dollar

# PowerTrader conversion:
"BTC-EUR" → "btceur"
"ETH-USD" → "ethusd"
```

## 🚨 Troubleshooting

### Common Issues

#### ❌ "API key does not exist"
**Causes**:
- Incorrect API key
- API key deleted or expired
- Wrong API version

**Solutions**:
1. Verify API key in Bitstamp account
2. Check if API key is still active
3. Regenerate API key if necessary
4. Ensure using correct API version (v2)

#### ❌ "Signature mismatch"
**Causes**:
- Incorrect API secret
- Wrong nonce generation
- Clock synchronization issues

**Solutions**:
1. Verify API secret is correct
2. Ensure nonce is incrementing properly
3. Synchronize system clock
4. Check signature generation algorithm

#### ❌ "Insufficient permissions"
**Causes**:
- API key missing trading permissions
- Account verification incomplete
- IP address not whitelisted

**Solutions**:
1. Enable required API permissions
2. Complete full account verification
3. Add your IP to API whitelist
4. Check account status

#### ❌ "Invalid trading pair"
**Causes**:
- Unsupported trading pair
- Incorrect symbol format
- Trading pair suspended

**Solutions**:
1. Use only supported pairs (btceur, ethusd, etc.)
2. Check correct symbol format (lowercase)
3. Verify pair is actively trading
4. Check Bitstamp pair listings

### Support Resources
- **Bitstamp Support**: bitstamp.net/contact
- **API Documentation**: bitstamp.net/api
- **Status Page**: bitstamp.net (main site for status)
- **Community**: reddit.com/r/Bitstamp

## 🔒 Security Best Practices

### API Security
- **IP Restrictions**: Always whitelist specific IPs
- **Minimal permissions**: Only enable trading permissions
- **Regular monitoring**: Check API activity logs
- **Key hygiene**: Rotate keys periodically

### Account Security
- **Two-Factor Authentication**: Enable TOTP with authenticator app
- **Strong passwords**: Use unique, complex passwords
- **Email security**: Secure your email account
- **Login monitoring**: Enable login notifications

### Trading Security
- **Start small**: Test with minimal amounts
- **Monitor trades**: Watch for unexpected activity
- **Withdrawal limits**: Set conservative daily limits
- **Cold storage**: Keep majority of funds offline

## 📈 Performance Optimization

### API Rate Limits
Bitstamp has generous rate limits:
- **Public endpoints**: 600 requests per 10 minutes
- **Private endpoints**: 600 requests per 10 minutes
- **Trading endpoints**: 600 requests per 10 minutes

### Connection Optimization
```python
import aiohttp
import asyncio
import hashlib
import hmac
import time

class BitstampOptimized:
    def __init__(self, api_key, api_secret, customer_id):
        self.api_key = api_key
        self.api_secret = api_secret
        self.customer_id = customer_id
        self.session = None
        self.nonce = int(time.time() * 1000000)

    def get_nonce(self):
        self.nonce += 1
        return str(self.nonce)

    def get_signature(self, nonce, customer_id, api_key):
        message = nonce + customer_id + api_key
        return hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest().upper()
```

### European Market Optimization
- **SEPA deposits**: Use for lowest cost funding
- **EUR trading**: Trade in EUR to avoid conversion fees
- **Market hours**: EU market hours for better liquidity
- **Volume tiers**: Build volume for better fee rates

---

**Bitstamp Setup Complete!** Your trusted European cryptocurrency exchange integration is ready for PowerTraderAI+.
