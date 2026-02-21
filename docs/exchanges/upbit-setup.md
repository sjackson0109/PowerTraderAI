# Upbit Exchange Setup Guide

## Overview
Upbit is South Korea's largest cryptocurrency exchange by trading volume, operated by Dunamu Inc. With over 8 million users, Upbit offers one of the most comprehensive selections of cryptocurrencies and is known for its high security standards and regulatory compliance in South Korea.

## Features
- **Largest Korean Exchange**: 70%+ market share in South Korea
- **Wide Cryptocurrency Selection**: 250+ trading pairs
- **High Security Standards**: Multiple security certifications
- **KRW Trading Pairs**: Direct won trading for major cryptocurrencies
- **Professional Trading Tools**: Advanced charting and analysis
- **Mobile App**: Full-featured trading app

## Prerequisites
- Upbit account with verified identity (Korean residents only for full features)
- API access enabled in account settings
- KYC verification completed
- Minimum deposit: 5,000 KRW

## API Setup

### 1. Enable API Access

1. **Login to Upbit**:
   - Navigate to https://upbit.com/
   - Log into your verified account

2. **Access API Settings**:
   - Go to "My Page" → "API Management"
   - Click "Create API Key"

3. **Configure API Permissions**:
   - **View**: Market data access ✓
   - **Trade**: Order placement ✓
   - **Withdraw**: Withdrawal permissions (optional)

### 2. API Credentials
Generate your API credentials:
- **Access Key**: Your public API identifier
- **Secret Key**: Your private API secret
- **Base URL**: https://api.upbit.com/

### 3. Configure PowerTraderAI+

Add Upbit credentials to your environment:

```bash
# Upbit API Configuration
UPBIT_ACCESS_KEY=your_access_key_here
UPBIT_SECRET_KEY=your_secret_key_here
UPBIT_API_URL=https://api.upbit.com/
UPBIT_RATE_LIMIT=10  # Requests per second
```

## Configuration in PowerTraderAI+

### 1. Exchange Configuration
```python
from pt_exchanges import UpbitExchange

# Initialize Upbit exchange
upbit = UpbitExchange({
    'access_key': 'your_access_key',
    'secret_key': 'your_secret_key',
    'api_url': 'https://api.upbit.com/',
    'rate_limit': 10,  # Max 10 requests per second
    'timeout': 30
})
```

### 2. Trading Configuration
```python
# Configure trading parameters
upbit_config = {
    'base_currency': 'KRW',  # Korean Won as base
    'max_position_size': 0.1,  # Max 10% portfolio per trade
    'min_order_size': 5000,  # Minimum 5,000 KRW order
    'preferred_pairs': ['KRW-BTC', 'KRW-ETH', 'BTC-ETH'],
    'use_market_orders': True
}
```

## Trading Features

### Available Markets
- **KRW Markets**: 200+ cryptocurrencies paired with Korean Won
- **BTC Markets**: 100+ altcoins paired with Bitcoin
- **USDT Markets**: 50+ pairs with Tether
- **Major Cryptocurrencies**: BTC, ETH, XRP, ADA, DOT, LINK, etc.
- **Korean Projects**: Strong support for Korean blockchain projects

### Popular Trading Pairs
```python
# Major KRW pairs
major_krw_pairs = [
    'KRW-BTC',    # Bitcoin
    'KRW-ETH',    # Ethereum
    'KRW-XRP',    # Ripple
    'KRW-ADA',    # Cardano
    'KRW-DOT',    # Polkadot
    'KRW-LINK',   # Chainlink
    'KRW-BCH',    # Bitcoin Cash
    'KRW-LTC',    # Litecoin
    'KRW-EOS',    # EOS
    'KRW-TRX'     # Tron
]

# Get current prices
prices = upbit.get_ticker(major_krw_pairs)
for pair, price in prices.items():
    print(f"{pair}: ₩{price['trade_price']:,}")
```

### Order Types
- **Market Orders**: Immediate execution at best available price
- **Limit Orders**: Execute at specific price or better
- **Stop Orders**: Not directly available (implement via API logic)

### Market Data Access
```python
# Get real-time ticker data
ticker = upbit.get_ticker('KRW-BTC')
print(f"Bitcoin Price: ₩{ticker['trade_price']:,}")
print(f"24h Change: {ticker['signed_change_rate']:.2%}")
print(f"Volume: ₩{ticker['acc_trade_price_24h']:,}")

# Get order book
orderbook = upbit.get_orderbook('KRW-BTC')
print(f"Best Bid: ₩{orderbook['bids'][0]['price']:,}")
print(f"Best Ask: ₩{orderbook['asks'][0]['price']:,}")

# Get recent trades
trades = upbit.get_trades('KRW-BTC')
for trade in trades[:5]:
    print(f"Price: ₩{trade['trade_price']:,}, Volume: {trade['trade_volume']}")
```

## Fee Structure

### Trading Fees
- **Maker Fee**: 0.05% (adds liquidity to order book)
- **Taker Fee**: 0.05% (removes liquidity from order book)
- **Volume Discounts**: Up to 50% reduction for high-volume traders

### Fee Calculation
```python
# Calculate trading fees
def calculate_upbit_fees(trade_volume_krw, is_maker=False):
    base_fee = 0.0005  # 0.05%

    # Volume-based discounts
    if trade_volume_krw >= 1000000000:  # 1B KRW
        discount = 0.5  # 50% discount
    elif trade_volume_krw >= 500000000:  # 500M KRW
        discount = 0.4  # 40% discount
    elif trade_volume_krw >= 100000000:  # 100M KRW
        discount = 0.3  # 30% discount
    elif trade_volume_krw >= 50000000:   # 50M KRW
        discount = 0.2  # 20% discount
    else:
        discount = 0

    return base_fee * (1 - discount)
```

### Other Fees
- **Deposit Fee**: Free for cryptocurrencies
- **Withdrawal Fees**: Varies by cryptocurrency
- **KRW Withdrawal**: 1,000 KRW flat fee
- **Bank Transfer**: Free for major Korean banks

## Security Features

### Account Security
- **Two-Factor Authentication**: SMS and OTP app support
- **Wallet Security**: Multi-signature cold storage
- **Real-time Monitoring**: 24/7 security monitoring
- **ISMS-P Certification**: Korean security standard
- **Insurance Coverage**: Digital asset insurance

### API Security
- **JWT Authentication**: Secure token-based authentication
- **Request Signing**: HMAC-SHA512 signatures
- **IP Whitelisting**: Restrict API access by IP address
- **Rate Limiting**: 10 requests per second limit
- **Secure Webhooks**: Real-time order updates

### Implementation Example
```python
import time
import uuid
import hashlib
import hmac
import jwt

def create_upbit_auth_header(access_key, secret_key, query_params=None):
    """Create authentication header for Upbit API"""
    payload = {
        'access_key': access_key,
        'nonce': str(uuid.uuid4()),
        'timestamp': round(time.time() * 1000)
    }

    if query_params:
        query_hash = hashlib.sha512()
        query_hash.update(query_params.encode())
        payload['query_hash'] = query_hash.hexdigest()
        payload['query_hash_alg'] = 'SHA512'

    # Create JWT token
    jwt_token = jwt.encode(payload, secret_key, algorithm='HS256')
    return f'Bearer {jwt_token}'
```

## Risk Management

### Trading Limits
- **Daily Trading Limit**: ₩200,000,000 for verified accounts
- **Withdrawal Limits**: ₩50,000,000 per day
- **Position Limits**: No specific limits, use own risk management
- **Price Deviation**: Orders outside 10% range may be rejected

### PowerTraderAI+ Integration
```python
# Risk management configuration
risk_config = {
    'max_daily_loss_krw': 1000000,  # 1M KRW daily loss limit
    'max_position_size': 0.1,  # 10% max position size
    'max_open_positions': 15,  # Maximum open positions
    'volatility_limit': 0.3,  # Max position volatility
    'correlation_limit': 0.7,  # Max correlation between positions
}

upbit.configure_risk_management(risk_config)
```

## Market Data & Analysis

### Korean Market Insights
```python
# Analyze Korean market trends
def analyze_korean_market():
    # Get top KRW pairs by volume
    markets = upbit.get_markets()
    krw_markets = [m for m in markets if m['market'].startswith('KRW-')]

    # Get 24h statistics
    stats = upbit.get_ticker([m['market'] for m in krw_markets])

    # Sort by volume
    sorted_by_volume = sorted(stats.items(),
                            key=lambda x: x[1]['acc_trade_price_24h'],
                            reverse=True)

    print("Top 10 KRW Markets by Volume:")
    for i, (pair, data) in enumerate(sorted_by_volume[:10], 1):
        volume_krw = data['acc_trade_price_24h']
        change = data['signed_change_rate'] * 100
        print(f"{i:2d}. {pair}: ₩{volume_krw:,.0f} ({change:+.2f}%)")

# Run market analysis
analyze_korean_market()
```

### Technical Analysis Integration
```python
# Get candlestick data for technical analysis
def get_candles(symbol, interval='minutes', count=200):
    """Get candlestick data from Upbit"""
    candles = upbit.get_candles(
        market=symbol,
        interval=interval,
        count=count
    )

    # Convert to PowerTraderAI+ format
    formatted_candles = []
    for candle in candles:
        formatted_candles.append({
            'timestamp': candle['candle_date_time_utc'],
            'open': candle['opening_price'],
            'high': candle['high_price'],
            'low': candle['low_price'],
            'close': candle['trade_price'],
            'volume': candle['candle_acc_trade_volume']
        })

    return formatted_candles

# Use with technical indicators
btc_candles = get_candles('KRW-BTC', interval='days', count=30)
# Apply your technical analysis here
```

## Korean Market Considerations

### Regulatory Environment
- **Strict KYC Requirements**: Real-name verification mandatory
- **Bank Partnerships**: Limited to major Korean banks
- **Regulatory Compliance**: Full compliance with Korean Financial Services Commission
- **Tax Implications**: 20% capital gains tax on crypto profits

### Market Characteristics
- **High Retail Participation**: Strong retail investor presence
- **Korean Won Pairs**: Unique KRW trading pairs not available elsewhere
- **Price Premiums**: Occasional "Kimchi Premium" for Korean markets
- **Local Projects**: Strong support for Korean blockchain projects

### Trading Strategies
```python
# Kimchi premium arbitrage detection
def detect_kimchi_premium(symbol_base='BTC'):
    upbit_price = upbit.get_ticker(f'KRW-{symbol_base}')['trade_price']

    # Get USD price from another exchange (e.g., Binance)
    binance_usd_price = binance.get_ticker(f'{symbol_base}USDT')['price']

    # Get current KRW/USD rate
    krw_usd_rate = get_krw_usd_rate()  # Implement this function

    # Calculate premium
    upbit_usd_equivalent = upbit_price / krw_usd_rate
    premium = (upbit_usd_equivalent / binance_usd_price - 1) * 100

    print(f"{symbol_base} Kimchi Premium: {premium:.2f}%")
    return premium
```

## Troubleshooting

### Common Issues

#### API Rate Limiting
```
Error: "Rate limit exceeded"
Solution: Implement exponential backoff, max 10 requests/second
```

#### Order Rejection
```
Error: "Order price outside acceptable range"
Solution: Check current market price, orders must be within ±10%
```

#### Insufficient Funds
```
Error: "Insufficient balance"
Solution: Check account balance and required fees
```

### Support Resources
- **Upbit Help Center**: https://upbit.com/service_center
- **API Documentation**: https://docs.upbit.com/
- **Developer Community**: Korean language support forums
- **Status Page**: https://upbit.com/service_center/notice

### Contact Information
- **Customer Support**: 1588-1455 (Korea)
- **Email Support**: help@upbit.com
- **Business Hours**: 9:00 - 18:00 KST (Weekdays)
- **API Support**: Developer documentation and forums

## Integration Examples

### Basic Trading Setup
```python
import os
from pt_exchanges import UpbitExchange

# Initialize exchange
upbit = UpbitExchange({
    'access_key': os.getenv('UPBIT_ACCESS_KEY'),
    'secret_key': os.getenv('UPBIT_SECRET_KEY')
})

# Get account info
account = upbit.get_accounts()
print("Account Balances:")
for balance in account:
    if float(balance['balance']) > 0:
        currency = balance['currency']
        amount = float(balance['balance'])
        print(f"{currency}: {amount:,.8f}")

# Place a limit order
order = upbit.place_order({
    'market': 'KRW-BTC',
    'side': 'bid',  # 'bid' for buy, 'ask' for sell
    'volume': None,  # Will be calculated from price
    'price': 45000000,  # 45M KRW per BTC
    'ord_type': 'limit'
})

print(f"Order placed: {order['uuid']}")

# Monitor order status
import time
while True:
    order_info = upbit.get_order(order['uuid'])
    if order_info['state'] == 'done':
        print("Order completed!")
        break
    elif order_info['state'] == 'cancel':
        print("Order cancelled!")
        break
    else:
        print(f"Order status: {order_info['state']}")
        time.sleep(5)
```

### Korean Market Analysis
```python
# Daily Korean market summary
def korean_market_summary():
    print("🇰🇷 Korean Cryptocurrency Market Summary")
    print("=" * 50)

    # Get all KRW markets
    markets = upbit.get_markets()
    krw_markets = [m for m in markets if m['market'].startswith('KRW-')]

    # Get tickers for all KRW pairs
    tickers = upbit.get_ticker([m['market'] for m in krw_markets])

    # Calculate total market stats
    total_volume = sum(ticker['acc_trade_price_24h'] for ticker in tickers.values())
    winners = [t for t in tickers.values() if t['signed_change_rate'] > 0]
    losers = [t for t in tickers.values() if t['signed_change_rate'] < 0]

    print(f"VOLUME: Total 24h Volume: ₩{total_volume:,.0f}")
    print(f"📈 Winners: {len(winners)} | Losers: {len(losers)}")

    # Top gainers
    top_gainers = sorted(tickers.items(),
                        key=lambda x: x[1]['signed_change_rate'],
                        reverse=True)[:5]

    print("\n🚀 Top Gainers:")
    for pair, data in top_gainers:
        change = data['signed_change_rate'] * 100
        price = data['trade_price']
        print(f"  {pair}: ₩{price:,} (+{change:.2f}%)")

    # Top volume
    top_volume = sorted(tickers.items(),
                       key=lambda x: x[1]['acc_trade_price_24h'],
                       reverse=True)[:5]

    print("\nTOP: Highest Volume:")
    for pair, data in top_volume:
        volume = data['acc_trade_price_24h']
        print(f"  {pair}: ₩{volume:,.0f}")

# Run daily summary
korean_market_summary()
```

This completes the Upbit integration setup. The exchange's dominance in the Korean market and unique KRW pairs provide excellent opportunities for regional trading strategies and arbitrage opportunities through PowerTraderAI+'s framework.
