# Bitso Exchange Setup Guide

## Overview
Bitso is Latin America's leading cryptocurrency exchange, serving over 3 million users across Mexico, Argentina, Brazil, and Colombia. Founded in 2014, Bitso offers a comprehensive platform for cryptocurrency trading, remittances, and digital payments with strong regulatory compliance and innovative financial services.

## Features
- **Largest LATAM Exchange**: Market leader across Latin America
- **Remittance Network**: Cross-border payments via cryptocurrency
- **Multiple Fiat Currencies**: MXN, ARS, BRL, COP support
- **Mobile-First Platform**: Full-featured mobile app
- **Bitso+ Program**: VIP benefits and reduced fees
- **Bitso Alpha**: Advanced trading features

## Prerequisites
- Bitso account with verified identity
- Valid ID from Mexico, Argentina, Brazil, or Colombia
- API access enabled in account settings
- Bank account in supported country

## API Setup

### 1. Enable API Access

1. **Login to Bitso**:
   - Navigate to https://bitso.com/
   - Log into your verified account

2. **Access API Settings**:
   - Go to "Configuración" → "API Keys"
   - Click "Crear Nueva Clave API"

3. **Configure API Permissions**:
   - **Trading**: Order placement ✓
   - **Funding**: Deposits/withdrawals (optional)
   - **View**: Account and market data ✓

### 2. API Credentials
Generate your API credentials:
- **Key**: Your public API identifier
- **Secret**: Your private API secret
- **Passphrase**: Additional security phrase
- **Base URL**: https://api.bitso.com/v3/

### 3. Configure PowerTraderAI+

Add Bitso credentials to your environment:

```bash
# Bitso API Configuration
BITSO_API_KEY=your_api_key_here
BITSO_SECRET_KEY=your_secret_key_here
BITSO_PASSPHRASE=your_passphrase_here
BITSO_API_URL=https://api.bitso.com/v3/
BITSO_RATE_LIMIT=60  # Requests per minute
```

## Configuration in PowerTraderAI+

### 1. Exchange Configuration
```python
from pt_exchanges import BitsoExchange

# Initialize Bitso exchange
bitso = BitsoExchange({
    'api_key': 'your_api_key',
    'secret_key': 'your_secret_key',
    'passphrase': 'your_passphrase',
    'api_url': 'https://api.bitso.com/v3/',
    'rate_limit': 60,  # Max 60 requests per minute
    'timeout': 30
})
```

### 2. Trading Configuration
```python
# Configure Latin American trading parameters
bitso_config = {
    'base_currencies': ['MXN', 'ARS', 'BRL', 'COP'],  # Local fiat
    'preferred_pairs': ['btc_mxn', 'eth_mxn', 'xrp_mxn'],
    'max_position_size': 0.1,  # Max 10% portfolio per trade
    'min_order_mxn': 100,  # Minimum 100 MXN order
    'use_remittance_features': True
}
```

## Trading Features

### Available Markets

#### Mexican Peso (MXN) Markets
```python
mxn_markets = [
    'btc_mxn',    # Bitcoin
    'eth_mxn',    # Ethereum
    'xrp_mxn',    # Ripple
    'ltc_mxn',    # Litecoin
    'bch_mxn',    # Bitcoin Cash
    'tusd_mxn',   # TrueUSD
    'dai_mxn',    # Dai
    'usdc_mxn',   # USD Coin
    'bat_mxn',    # Basic Attention Token
    'mana_mxn'    # Decentraland
]

# Get MXN market prices
for pair in mxn_markets:
    ticker = bitso.get_ticker(pair)
    print(f"{pair.upper()}: ${ticker['last']:,.2f} MXN")
```

#### Multi-Currency Support
- **Mexican Peso (MXN)**: Primary market with most liquidity
- **Argentine Peso (ARS)**: Selected major cryptocurrencies
- **Brazilian Real (BRL)**: Limited pairs available
- **Colombian Peso (COP)**: Major cryptocurrencies

### Advanced Trading Features

#### Smart Order Routing
```python
# Bitso's intelligent order routing
def execute_smart_order(symbol, side, amount, order_type='smart'):
    """
    Execute order with Bitso's smart routing
    Automatically finds best execution across order book
    """
    order = bitso.place_order({
        'book': symbol,
        'side': side,  # 'buy' or 'sell'
        'type': order_type,  # 'smart', 'limit', 'market'
        'amount': amount,
        'time_in_force': 'goodtillcancelled'
    })

    print(f"Smart order placed: {order['oid']}")
    return order

# Example: Buy 0.1 BTC with smart routing
smart_order = execute_smart_order('btc_mxn', 'buy', 0.1)
```

#### Bitso+ VIP Features
```python
# Access VIP features for high-volume traders
def check_bitso_plus_status():
    """
    Check Bitso+ membership status and benefits
    """
    account = bitso.get_account_status()

    if account['client_id']:
        plus_info = bitso.get_bitso_plus_info()

        print(f"Bitso+ Status: {plus_info['tier']}")
        print(f"Trading Fee Discount: {plus_info['fee_discount']}%")
        print(f"30-day Volume: ${plus_info['volume_30d']:,.2f} MXN")
        print(f"Next Tier Requirement: ${plus_info['next_tier_volume']:,.2f} MXN")

        return plus_info

    return None

# Optimize trading based on VIP status
plus_status = check_bitso_plus_status()
if plus_status and plus_status['tier'] in ['Gold', 'Platinum']:
    # Use advanced features for VIP members
    enable_algorithmic_trading()
```

## Cross-Border Remittance Integration

### Cryptocurrency Remittances
```python
# Leverage Bitso's remittance network
def crypto_remittance_opportunity():
    """
    Find arbitrage opportunities in Bitso's remittance corridors
    """
    # Major remittance corridors
    corridors = [
        {'from': 'US', 'to': 'MX', 'currency': 'MXN'},
        {'from': 'US', 'to': 'AR', 'currency': 'ARS'},
        {'from': 'MX', 'to': 'BR', 'currency': 'BRL'},
        {'from': 'MX', 'to': 'CO', 'currency': 'COP'}
    ]

    opportunities = []

    for corridor in corridors:
        # Get traditional remittance rate
        traditional_rate = get_traditional_remittance_rate(corridor)

        # Calculate crypto remittance rate via Bitso
        crypto_rate = calculate_crypto_remittance_rate(corridor)

        # Calculate savings
        savings_percentage = ((traditional_rate - crypto_rate) / traditional_rate) * 100

        if savings_percentage > 5:  # 5% minimum savings
            opportunities.append({
                'corridor': f"{corridor['from']} → {corridor['to']}",
                'savings': savings_percentage,
                'traditional_fee': traditional_rate,
                'crypto_fee': crypto_rate,
                'currency': corridor['currency']
            })

    return sorted(opportunities, key=lambda x: x['savings'], reverse=True)

def calculate_crypto_remittance_rate(corridor):
    """
    Calculate effective rate for crypto-based remittance
    """
    # Simplified calculation - implement actual API calls
    base_conversion_fee = 0.5  # 0.5% conversion fee
    trading_fee = 0.1  # 0.1% trading fee
    network_fee = 2.0  # $2 network fee

    return base_conversion_fee + trading_fee + network_fee

# Find current remittance opportunities
remittance_opps = crypto_remittance_opportunity()
for opp in remittance_opps:
    print(f"💰 Remittance Opportunity: {opp['corridor']}")
    print(f"  Savings: {opp['savings']:.1f}%")
    print(f"  Traditional: {opp['traditional_fee']:.2f}%")
    print(f"  Crypto: {opp['crypto_fee']:.2f}%")
```

## Latin American Market Strategies

### Peso Devaluation Hedge
```python
# Hedge against peso devaluation
def peso_devaluation_strategy():
    """
    Automated strategy to hedge against peso devaluation
    Popular strategy in Latin America
    """
    # Monitor USD/MXN exchange rate
    usd_mxn_rate = get_usd_mxn_rate()
    historical_average = get_historical_average_rate(days=90)

    # Calculate devaluation percentage
    devaluation = (usd_mxn_rate - historical_average) / historical_average

    print(f"Current USD/MXN: {usd_mxn_rate:.2f}")
    print(f"90-day Average: {historical_average:.2f}")
    print(f"Devaluation: {devaluation:.2%}")

    if devaluation > 0.05:  # 5% devaluation threshold
        # Increase cryptocurrency allocation
        account_balance_mxn = bitso.get_balance()['mxn']['available']
        hedge_amount = account_balance_mxn * 0.2  # Hedge 20% of MXN

        # Buy stable cryptocurrencies
        stable_allocation = {
            'btc_mxn': hedge_amount * 0.4,   # 40% Bitcoin
            'eth_mxn': hedge_amount * 0.3,   # 30% Ethereum
            'usdc_mxn': hedge_amount * 0.3   # 30% USDC
        }

        for pair, amount in stable_allocation.items():
            if amount >= 100:  # Minimum order size
                order = bitso.place_order({
                    'book': pair,
                    'side': 'buy',
                    'type': 'market',
                    'minor': amount  # Amount in MXN
                })
                print(f"Hedge order: {pair} for ${amount:,.2f} MXN")

# Run peso hedge strategy
peso_devaluation_strategy()
```

### Dollar Cost Averaging for LATAM
```python
# Localized DCA strategy for Latin American users
def latam_dca_strategy():
    """
    Dollar Cost Averaging strategy adapted for Latin American markets
    Accounts for local salary cycles and currency volatility
    """
    # Salary-aligned DCA (bi-weekly for most LATAM countries)
    dca_config = {
        'btc_mxn': {'amount': 1000, 'frequency': 'bi-weekly'},   # $1000 MXN bi-weekly
        'eth_mxn': {'amount': 500, 'frequency': 'bi-weekly'},    # $500 MXN bi-weekly
        'usdc_mxn': {'amount': 500, 'frequency': 'weekly'}       # $500 MXN weekly (stability)
    }

    for pair, config in dca_config.items():
        try:
            # Check if it's the right time to execute
            if is_dca_time(config['frequency']):

                # Get current price and calculate amount
                ticker = bitso.get_ticker(pair)
                current_price = ticker['ask']

                # Place market order
                order = bitso.place_order({
                    'book': pair,
                    'side': 'buy',
                    'type': 'market',
                    'minor': config['amount']  # Amount in local currency
                })

                print(f"DCA executed: {pair} ${config['amount']} MXN")

                # Log for tracking
                log_dca_transaction(pair, config['amount'], current_price)

        except Exception as e:
            print(f"DCA failed for {pair}: {e}")

def is_dca_time(frequency):
    """Check if it's time to execute DCA based on frequency"""
    # Implement calendar logic for bi-weekly/weekly execution
    # Account for Mexican payroll cycles (typically 15th and 30th)
    import datetime
    today = datetime.date.today()

    if frequency == 'bi-weekly':
        return today.day in [15, 30] or (today.day == 31 and today.month in [1,3,5,7,8,10,12])
    elif frequency == 'weekly':
        return today.weekday() == 4  # Friday (end of work week)

    return False
```

## Fee Structure & Optimization

### Dynamic Fee Structure
```python
# Optimize trading based on Bitso's fee structure
def calculate_optimal_order_size(pair, total_amount):
    """
    Calculate optimal order size considering Bitso's fee tiers
    """
    account = bitso.get_account_status()
    volume_30d = account.get('volume_30d', 0)

    # Bitso fee tiers (example - check current rates)
    fee_tiers = [
        {'min_volume': 0, 'maker_fee': 0.5, 'taker_fee': 0.65},
        {'min_volume': 50000, 'maker_fee': 0.45, 'taker_fee': 0.6},
        {'min_volume': 250000, 'maker_fee': 0.4, 'taker_fee': 0.55},
        {'min_volume': 1000000, 'maker_fee': 0.35, 'taker_fee': 0.5},
        {'min_volume': 5000000, 'maker_fee': 0.3, 'taker_fee': 0.45}
    ]

    # Find current fee tier
    current_tier = None
    for tier in reversed(fee_tiers):
        if volume_30d >= tier['min_volume']:
            current_tier = tier
            break

    # Calculate fees for different order strategies
    strategies = {
        'single_order': {
            'orders': 1,
            'size': total_amount,
            'fee': total_amount * (current_tier['taker_fee'] / 100)
        },
        'split_orders': {
            'orders': 3,
            'size': total_amount / 3,
            'fee': total_amount * (current_tier['maker_fee'] / 100)  # Assume maker orders
        },
        'gradual_orders': {
            'orders': 5,
            'size': total_amount / 5,
            'fee': total_amount * (current_tier['maker_fee'] / 100) * 0.8  # Volume discount
        }
    }

    # Return most cost-effective strategy
    optimal_strategy = min(strategies.items(), key=lambda x: x[1]['fee'])

    print(f"Optimal Strategy: {optimal_strategy[0]}")
    print(f"Total Fee: ${optimal_strategy[1]['fee']:.2f} MXN")

    return optimal_strategy
```

## Integration Examples

### Complete LATAM Trading Setup
```python
import os
from pt_exchanges import BitsoExchange

# Initialize Bitso exchange
bitso = BitsoExchange({
    'api_key': os.getenv('BITSO_API_KEY'),
    'secret_key': os.getenv('BITSO_SECRET_KEY'),
    'passphrase': os.getenv('BITSO_PASSPHRASE')
})

# Comprehensive Latin American strategy
def bitso_latam_strategy():
    print("🌎 Bitso Latin American Trading Strategy")
    print("=" * 45)

    # 1. Account overview
    account = bitso.get_account_status()
    balances = bitso.get_balance()

    print(f"Account Tier: {account.get('tier', 'Basic')}")
    print(f"30-day Volume: ${account.get('volume_30d', 0):,.2f} MXN")

    # Show balances
    print("\n💰 Account Balances:")
    for currency, balance in balances.items():
        if float(balance['available']) > 0:
            print(f"  {currency.upper()}: {balance['available']}")

    # 2. Market analysis
    print("\n📊 Mexican Market Analysis:")
    major_pairs = ['btc_mxn', 'eth_mxn', 'xrp_mxn']

    for pair in major_pairs:
        ticker = bitso.get_ticker(pair)
        volume_24h = ticker.get('volume', 0)
        change_24h = ticker.get('change_24', 0)

        print(f"  {pair.upper()}: ${ticker['last']:,.2f} MXN")
        print(f"    24h Volume: ${float(volume_24h) * float(ticker['last']):,.0f} MXN")
        print(f"    24h Change: {float(change_24h):.2%}")

    # 3. Execute peso hedge if needed
    print("\n🛡️ Peso Devaluation Check:")
    peso_devaluation_strategy()

    # 4. DCA execution
    print("\n📈 DCA Strategy Check:")
    latam_dca_strategy()

    # 5. Remittance opportunities
    print("\n💸 Remittance Opportunities:")
    remittance_opportunities = crypto_remittance_opportunity()
    for opp in remittance_opportunities[:3]:
        print(f"  {opp['corridor']}: {opp['savings']:.1f}% savings")

    print("\n✅ LATAM strategy execution completed!")

# Run the comprehensive strategy
bitso_latam_strategy()
```

This completes the Bitso integration setup, providing comprehensive Latin American market access with specialized features for peso hedging, remittances, and region-specific trading strategies within PowerTraderAI+'s framework.
