# Deribit Exchange Setup Guide

## Overview
Deribit is the world's largest Bitcoin and Ethereum options exchange, handling over 80% of all cryptocurrency options volume globally. Founded in 2016, Deribit specializes in derivatives trading with advanced options, futures, and perpetual contracts, offering institutional-grade features with deep liquidity.

## Features
- **Options Market Leader**: 80%+ global crypto options market share
- **Advanced Greeks**: Real-time options Greeks and analytics
- **Portfolio Margining**: Cross-margining across all positions
- **Deep Liquidity**: Tight spreads and large order book depth
- **Institutional Features**: Block trading, RFQ system, prime brokerage
- **Settlement**: Physical delivery for futures, cash settlement for options

## Prerequisites
- Deribit account with verified identity
- Understanding of options trading and Greeks
- Minimum deposit: 0.001 BTC or 0.01 ETH
- API access enabled for trading

## API Setup

### 1. Enable API Access

1. **Login to Deribit**:
   - Navigate to https://www.deribit.com/
   - Log into your verified account

2. **Access API Settings**:
   - Go to "Account" → "API"
   - Click "Create New Key"

3. **Configure API Permissions**:
   - **Trading**: Order placement and management ✓
   - **Wallet**: Account balance access ✓
   - **Read**: Market data access ✓

### 2. API Credentials
Generate your API credentials:
- **Client ID**: Your public API identifier
- **Client Secret**: Your private API secret
- **Base URL**: https://www.deribit.com/api/v2/
- **Testnet URL**: https://test.deribit.com/api/v2/

### 3. Configure PowerTraderAI+

Add Deribit credentials to your environment:

```bash
# Deribit API Configuration
DERIBIT_CLIENT_ID=your_client_id_here
DERIBIT_CLIENT_SECRET=your_client_secret_here
DERIBIT_API_URL=https://www.deribit.com/api/v2/
DERIBIT_TESTNET=false  # Set to true for testing
DERIBIT_RATE_LIMIT=20  # Requests per second
```

## Configuration in PowerTraderAI+

### 1. Exchange Configuration
```python
from pt_exchanges import DeribitExchange

# Initialize Deribit exchange
deribit = DeribitExchange({
    'client_id': 'your_client_id',
    'client_secret': 'your_client_secret',
    'api_url': 'https://www.deribit.com/api/v2/',
    'testnet': False,  # Use testnet for testing
    'rate_limit': 20,  # Max 20 requests per second
    'timeout': 30
})
```

### 2. Options Trading Configuration
```python
# Configure options trading parameters
deribit_config = {
    'base_currencies': ['BTC', 'ETH'],
    'preferred_expiries': ['1W', '1M', '3M'],  # Weekly, monthly, quarterly
    'max_position_delta': 5.0,  # Maximum portfolio delta
    'iv_range': [0.4, 1.2],  # Implied volatility range 40%-120%
    'liquidity_threshold': 100,  # Minimum $100k open interest
    'auto_hedge_delta': True,  # Auto-hedge delta exposure
    'max_gamma_exposure': 10.0  # Maximum gamma exposure
}
```

## Options Trading Features

### Available Instruments

#### Bitcoin Options
```python
# Get all available BTC options
btc_options = deribit.get_instruments('option', 'BTC')

print("📈 Available BTC Options:")
for option in btc_options[:10]:  # Show first 10
    print(f"  {option['instrument_name']}")
    print(f"    Strike: ${option['strike']:,.0f}")
    print(f"    Expiry: {option['expiration_timestamp']}")
    print(f"    Type: {option['option_type']}")
    print()

# Popular BTC option strikes
btc_price = deribit.get_current_price('BTC-PERPETUAL')
popular_strikes = [
    btc_price * 0.8,   # 20% OTM put
    btc_price * 0.9,   # 10% OTM put
    btc_price,         # ATM
    btc_price * 1.1,   # 10% OTM call
    btc_price * 1.2    # 20% OTM call
]
```

#### Ethereum Options
```python
# Get ETH options chain
eth_options = deribit.get_options_chain('ETH')

# Filter by expiry and liquidity
liquid_options = []
for option in eth_options:
    if (option['open_interest'] > 100 and  # Min open interest
        option['volume_24h'] > 10):        # Min daily volume
        liquid_options.append(option)

print(f"Found {len(liquid_options)} liquid ETH options")
```

### Options Greeks & Analytics

```python
# Comprehensive options analytics
def analyze_options_greeks(instrument_name):
    """
    Analyze options Greeks and risk metrics
    """
    option_data = deribit.get_option_details(instrument_name)
    greeks = deribit.get_greeks(instrument_name)

    print(f"📊 Options Analysis: {instrument_name}")
    print("=" * 50)

    # Basic option info
    print(f"Underlying: {option_data['underlying']}")
    print(f"Strike: ${option_data['strike']:,.0f}")
    print(f"Expiry: {option_data['expiry_date']}")
    print(f"Type: {option_data['option_type']}")
    print(f"DTE: {option_data['days_to_expiry']}")

    # Greeks
    print(f"\n🏛️ Greeks:")
    print(f"  Delta: {greeks['delta']:.4f}")
    print(f"  Gamma: {greeks['gamma']:.4f}")
    print(f"  Theta: {greeks['theta']:.4f}")
    print(f"  Vega: {greeks['vega']:.4f}")
    print(f"  Rho: {greeks['rho']:.4f}")

    # Risk metrics
    print(f"\n📈 Risk Metrics:")
    print(f"  Implied Volatility: {greeks['iv']:.2%}")
    print(f"  Moneyness: {option_data['moneyness']:.2%}")
    print(f"  Open Interest: {option_data['open_interest']:,.0f}")
    print(f"  Volume 24h: {option_data['volume_24h']:,.0f}")

    return greeks

# Example: Analyze BTC weekly call
btc_weekly_call = "BTC-29MAR24-70000-C"  # Example instrument
greeks_analysis = analyze_options_greeks(btc_weekly_call)
```

### Advanced Options Strategies

#### Covered Call Strategy
```python
# Implement covered call strategy
def covered_call_strategy(underlying_amount=1.0, target_yield=0.05):
    """
    Automated covered call strategy
    """
    underlying = 'BTC'
    current_price = deribit.get_current_price(f'{underlying}-PERPETUAL')

    print(f"🛡️ Covered Call Strategy - {underlying}")
    print(f"Current Price: ${current_price:,.0f}")
    print(f"Position Size: {underlying_amount} {underlying}")
    print(f"Target Monthly Yield: {target_yield:.1%}")

    # Find optimal call to sell
    options_chain = deribit.get_options_chain(underlying, option_type='call')

    # Filter for monthly expiries (25-35 days)
    monthly_options = [
        opt for opt in options_chain
        if 25 <= opt['days_to_expiry'] <= 35
    ]

    # Find calls with target delta (0.2-0.3 for covered calls)
    optimal_calls = []
    for option in monthly_options:
        greeks = deribit.get_greeks(option['instrument_name'])

        if (0.15 <= abs(greeks['delta']) <= 0.35 and  # Target delta range
            greeks['iv'] > 0.3):  # Minimum IV for premium

            # Calculate potential yield
            premium = deribit.get_bid_price(option['instrument_name'])
            monthly_yield = premium / current_price

            optimal_calls.append({
                'instrument': option['instrument_name'],
                'strike': option['strike'],
                'premium': premium,
                'delta': greeks['delta'],
                'iv': greeks['iv'],
                'monthly_yield': monthly_yield
            })

    # Sort by yield
    optimal_calls.sort(key=lambda x: x['monthly_yield'], reverse=True)

    if optimal_calls:
        best_call = optimal_calls[0]

        if best_call['monthly_yield'] >= target_yield:
            print(f"\n✅ Optimal Call Found:")
            print(f"  Instrument: {best_call['instrument']}")
            print(f"  Strike: ${best_call['strike']:,.0f}")
            print(f"  Premium: {best_call['premium']:.4f} {underlying}")
            print(f"  Delta: {best_call['delta']:.3f}")
            print(f"  IV: {best_call['iv']:.1%}")
            print(f"  Monthly Yield: {best_call['monthly_yield']:.2%}")

            # Execute covered call
            sell_call_order = deribit.place_order({
                'instrument_name': best_call['instrument'],
                'amount': underlying_amount,
                'type': 'limit',
                'direction': 'sell',
                'price': best_call['premium'],
                'post_only': True
            })

            print(f"\n📋 Covered call order placed: {sell_call_order['order_id']}")
            return sell_call_order

    print("❌ No suitable covered call opportunities found")
    return None

# Execute covered call strategy
covered_call_order = covered_call_strategy(underlying_amount=0.1, target_yield=0.03)
```

#### Protective Put Strategy
```python
# Implement protective put strategy
def protective_put_strategy(underlying_amount=1.0, protection_level=0.9):
    """
    Automated protective put strategy for downside protection
    """
    underlying = 'BTC'
    current_price = deribit.get_current_price(f'{underlying}-PERPETUAL')
    target_strike = current_price * protection_level

    print(f"🛡️ Protective Put Strategy - {underlying}")
    print(f"Current Price: ${current_price:,.0f}")
    print(f"Protection Level: {protection_level:.1%}")
    print(f"Target Strike: ${target_strike:,.0f}")

    # Find suitable puts
    puts_chain = deribit.get_options_chain(underlying, option_type='put')

    # Filter for quarterly expiries (80-100 days) for longer protection
    quarterly_puts = [
        opt for opt in puts_chain
        if 80 <= opt['days_to_expiry'] <= 100 and
           abs(opt['strike'] - target_strike) < current_price * 0.05  # Within 5% of target
    ]

    if not quarterly_puts:
        print("❌ No suitable protective puts found")
        return None

    # Find most liquid put near target strike
    best_put = min(quarterly_puts,
                   key=lambda x: abs(x['strike'] - target_strike))

    # Get put details
    put_premium = deribit.get_ask_price(best_put['instrument_name'])
    greeks = deribit.get_greeks(best_put['instrument_name'])

    # Calculate protection cost
    protection_cost = put_premium / current_price
    max_loss = (current_price - best_put['strike']) / current_price

    print(f"\n✅ Protective Put Selected:")
    print(f"  Instrument: {best_put['instrument_name']}")
    print(f"  Strike: ${best_put['strike']:,.0f}")
    print(f"  Premium: {put_premium:.4f} {underlying}")
    print(f"  Protection Cost: {protection_cost:.2%}")
    print(f"  Max Loss (excluding premium): {max_loss:.2%}")
    print(f"  Delta: {greeks['delta']:.3f}")
    print(f"  Days to Expiry: {best_put['days_to_expiry']}")

    # Execute protective put purchase
    buy_put_order = deribit.place_order({
        'instrument_name': best_put['instrument_name'],
        'amount': underlying_amount,
        'type': 'limit',
        'direction': 'buy',
        'price': put_premium * 1.01,  # Slightly above ask for execution
        'post_only': False
    })

    print(f"\n📋 Protective put order placed: {buy_put_order['order_id']}")
    return buy_put_order

# Execute protective put strategy
protective_put_order = protective_put_strategy(underlying_amount=0.1)
```

### Volatility Trading

#### Volatility Surface Analysis
```python
# Analyze implied volatility surface
def analyze_volatility_surface(underlying='BTC'):
    """
    Analyze the implied volatility surface for trading opportunities
    """
    options_data = deribit.get_all_options(underlying)

    print(f"📊 {underlying} Volatility Surface Analysis")
    print("=" * 60)

    # Group by expiry
    expiry_groups = {}
    for option in options_data:
        expiry = option['expiry_date']
        if expiry not in expiry_groups:
            expiry_groups[expiry] = []
        expiry_groups[expiry].append(option)

    current_price = deribit.get_current_price(f'{underlying}-PERPETUAL')

    print(f"Current {underlying} Price: ${current_price:,.0f}")
    print(f"\n{'Expiry':<12} {'DTE':<5} {'ATM IV':<8} {'25D Put':<8} {'25D Call':<8} {'Skew':<6}")
    print("-" * 60)

    vol_opportunities = []

    for expiry, options in expiry_groups.items():
        if not options:
            continue

        # Find ATM option
        atm_option = min(options, key=lambda x: abs(x['strike'] - current_price))

        # Find 25 delta options (approximate)
        call_25d = None
        put_25d = None

        for option in options:
            greeks = deribit.get_greeks(option['instrument_name'])
            if option['option_type'] == 'call' and 0.2 <= greeks['delta'] <= 0.3:
                call_25d = option
            elif option['option_type'] == 'put' and -0.3 <= greeks['delta'] <= -0.2:
                put_25d = option

        # Calculate metrics
        atm_greeks = deribit.get_greeks(atm_option['instrument_name'])
        atm_iv = atm_greeks['iv']

        call_25d_iv = deribit.get_greeks(call_25d['instrument_name'])['iv'] if call_25d else 0
        put_25d_iv = deribit.get_greeks(put_25d['instrument_name'])['iv'] if put_25d else 0

        # Volatility skew
        skew = call_25d_iv - put_25d_iv if call_25d and put_25d else 0

        print(f"{expiry:<12} {atm_option['days_to_expiry']:<5} {atm_iv:<7.1%} {put_25d_iv:<7.1%} {call_25d_iv:<7.1%} {skew:<5.1%}")

        # Identify opportunities
        if skew > 0.05:  # High call skew
            vol_opportunities.append({
                'type': 'sell_call_skew',
                'expiry': expiry,
                'skew': skew,
                'action': f'Sell {call_25d["instrument_name"] if call_25d else "N/A"}'
            })
        elif skew < -0.05:  # High put skew
            vol_opportunities.append({
                'type': 'sell_put_skew',
                'expiry': expiry,
                'skew': skew,
                'action': f'Sell {put_25d["instrument_name"] if put_25d else "N/A"}'
            })

    # Show opportunities
    if vol_opportunities:
        print(f"\n🎯 Volatility Trading Opportunities:")
        for opp in vol_opportunities:
            print(f"  {opp['type']}: {opp['action']} (Skew: {opp['skew']:.1%})")

    return vol_opportunities

# Analyze volatility surface
btc_vol_opportunities = analyze_volatility_surface('BTC')
```

## Risk Management

### Portfolio Greeks Management

```python
# Comprehensive portfolio Greeks management
def manage_portfolio_greeks():
    """
    Monitor and manage portfolio-level Greeks exposure
    """
    positions = deribit.get_all_positions()

    # Calculate portfolio Greeks
    portfolio_greeks = {
        'delta': 0,
        'gamma': 0,
        'theta': 0,
        'vega': 0,
        'rho': 0
    }

    print("⚖️ Portfolio Greeks Management")
    print("=" * 50)

    position_details = []

    for position in positions:
        if position['size'] != 0:
            instrument = position['instrument_name']
            size = position['size']

            # Get Greeks for this position
            greeks = deribit.get_greeks(instrument)

            # Calculate position Greeks
            position_greeks = {
                'delta': greeks['delta'] * size,
                'gamma': greeks['gamma'] * size,
                'theta': greeks['theta'] * size,
                'vega': greeks['vega'] * size,
                'rho': greeks['rho'] * size
            }

            # Add to portfolio totals
            for greek in portfolio_greeks:
                portfolio_greeks[greek] += position_greeks[greek]

            position_details.append({
                'instrument': instrument,
                'size': size,
                'greeks': position_greeks
            })

    # Display portfolio Greeks
    print(f"Portfolio Delta: {portfolio_greeks['delta']:.3f}")
    print(f"Portfolio Gamma: {portfolio_greeks['gamma']:.3f}")
    print(f"Portfolio Theta: {portfolio_greeks['theta']:.3f}")
    print(f"Portfolio Vega: {portfolio_greeks['vega']:.3f}")
    print(f"Portfolio Rho: {portfolio_greeks['rho']:.3f}")

    # Risk assessment
    risk_alerts = []

    if abs(portfolio_greeks['delta']) > deribit_config['max_position_delta']:
        risk_alerts.append({
            'type': 'delta_limit',
            'current': portfolio_greeks['delta'],
            'limit': deribit_config['max_position_delta'],
            'action': 'hedge_delta'
        })

    if abs(portfolio_greeks['gamma']) > deribit_config['max_gamma_exposure']:
        risk_alerts.append({
            'type': 'gamma_limit',
            'current': portfolio_greeks['gamma'],
            'limit': deribit_config['max_gamma_exposure'],
            'action': 'reduce_gamma'
        })

    # Execute risk management actions
    if risk_alerts:
        print(f"\n⚠️ Risk Management Alerts:")
        for alert in risk_alerts:
            print(f"  {alert['type']}: {alert['current']:.3f} (Limit: {alert['limit']:.3f})")

            if alert['action'] == 'hedge_delta':
                hedge_portfolio_delta(portfolio_greeks['delta'])
            elif alert['action'] == 'reduce_gamma':
                reduce_gamma_exposure(portfolio_greeks['gamma'])

    return portfolio_greeks, risk_alerts

def hedge_portfolio_delta(current_delta):
    """
    Hedge portfolio delta using perpetual futures
    """
    hedge_amount = -current_delta  # Opposite direction

    if abs(hedge_amount) > 0.01:  # Minimum hedge size
        underlying = 'BTC' if 'BTC' in str(current_delta) else 'ETH'
        perp_instrument = f'{underlying}-PERPETUAL'

        hedge_order = deribit.place_order({
            'instrument_name': perp_instrument,
            'amount': abs(hedge_amount),
            'type': 'market',
            'direction': 'buy' if hedge_amount > 0 else 'sell'
        })

        print(f"🛡️ Delta hedge executed: {hedge_order['order_id']}")
        return hedge_order

    return None
```

## Integration Examples

### Complete Options Strategy

```python
import os
from pt_exchanges import DeribitExchange

# Initialize Deribit exchange
deribit = DeribitExchange({
    'client_id': os.getenv('DERIBIT_CLIENT_ID'),
    'client_secret': os.getenv('DERIBIT_CLIENT_SECRET'),
    'testnet': False
})

# Comprehensive options trading strategy
def deribit_options_strategy():
    print("⚖️ Deribit Options Trading Strategy")
    print("=" * 40)

    # 1. Account overview
    account = deribit.get_account_summary()
    print(f"Account Equity: {account['equity']:.4f} BTC")
    print(f"Available Funds: {account['available_funds']:.4f} BTC")
    print(f"Maintenance Margin: {account['maintenance_margin']:.4f} BTC")

    # 2. Market analysis
    print("\n📊 Market Analysis:")
    btc_price = deribit.get_current_price('BTC-PERPETUAL')
    eth_price = deribit.get_current_price('ETH-PERPETUAL')

    print(f"BTC Price: ${btc_price:,.0f}")
    print(f"ETH Price: ${eth_price:,.0f}")

    # 3. Volatility analysis
    print("\n📈 Volatility Analysis:")
    btc_vol_opps = analyze_volatility_surface('BTC')
    eth_vol_opps = analyze_volatility_surface('ETH')

    # 4. Execute strategies based on market conditions
    account_btc = account['equity']

    # Conservative allocation: 20% for options strategies
    options_allocation = account_btc * 0.2

    if options_allocation > 0.01:  # Minimum 0.01 BTC
        # Strategy 1: Covered calls if we have underlying
        btc_balance = deribit.get_balance('BTC')
        if btc_balance > 0.1:
            print("\n🛡️ Executing Covered Call Strategy:")
            covered_call_strategy(underlying_amount=min(btc_balance, 0.5))

        # Strategy 2: Protective puts for large holdings
        if btc_balance > 1.0:
            print("\n🛡️ Executing Protective Put Strategy:")
            protective_put_strategy(underlying_amount=btc_balance * 0.5)

        # Strategy 3: Volatility trading
        if btc_vol_opps:
            print("\n🎯 Executing Volatility Strategies:")
            for opp in btc_vol_opps[:2]:  # Max 2 vol trades
                execute_volatility_strategy(opp)

    # 5. Portfolio risk management
    print("\n⚖️ Portfolio Risk Check:")
    portfolio_greeks, alerts = manage_portfolio_greeks()

    if not alerts:
        print("✅ Portfolio Greeks within limits")

    # 6. Performance monitoring
    daily_pnl = deribit.get_daily_pnl()
    print(f"\n📈 Daily P&L: {daily_pnl['total_pnl']:.4f} BTC ({daily_pnl['percentage']:.2%})")

    print("\n✅ Options strategy execution completed!")

def execute_volatility_strategy(opportunity):
    """Execute volatility trading opportunity"""
    if opportunity['type'] == 'sell_call_skew':
        print(f"  Selling call skew: {opportunity['action']}")
        # Implement call selling logic
    elif opportunity['type'] == 'sell_put_skew':
        print(f"  Selling put skew: {opportunity['action']}")
        # Implement put selling logic

# Run the comprehensive options strategy
deribit_options_strategy()
```

This completes the Deribit integration setup, providing comprehensive options trading capabilities with advanced Greeks management, volatility analysis, and automated strategy execution within PowerTraderAI+'s framework.
