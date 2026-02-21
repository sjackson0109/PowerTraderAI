# Phemex Exchange Setup Guide

## Overview
Phemex is a leading cryptocurrency derivatives exchange offering both spot and contract trading. Known for its zero-fee spot trading, advanced futures products, and high performance trading engine, Phemex serves both retail and institutional traders with competitive features and robust security.

## Features
- **Zero-Fee Spot Trading**: No fees on spot trading pairs
- **Advanced Derivatives**: Perpetual contracts with up to 100x leverage
- **High Performance**: Ultra-low latency trading engine
- **Copy Trading**: Follow successful traders automatically
- **Launchpad**: Early access to new token launches
- **Savings Products**: Earn yield on crypto holdings

## Prerequisites
- Phemex account with verified identity
- API access enabled in account settings
- Minimum deposit: $10 equivalent
- 2FA authentication enabled

## API Setup

### 1. Enable API Access

1. **Login to Phemex**:
   - Navigate to https://phemex.com/
   - Log into your verified account

2. **Access API Settings**:
   - Go to "Account" → "API Management"
   - Click "Create New API"

3. **Configure API Permissions**:
   - **Trade**: Order placement and management ✓
   - **Read**: Account and market data access ✓
   - **Transfer**: Internal transfers (optional)
   - **Withdraw**: Withdrawal permissions (optional)

### 2. API Credentials
Generate your API credentials:
- **API Key**: Your public API identifier
- **Secret Key**: Your private API secret
- **Passphrase**: Additional security phrase
- **Base URL**: https://api.phemex.com/

### 3. Configure PowerTraderAI+

Add Phemex credentials to your environment:

```bash
# Phemex API Configuration
PHEMEX_API_KEY=your_api_key_here
PHEMEX_SECRET_KEY=your_secret_key_here
PHEMEX_PASSPHRASE=your_passphrase_here
PHEMEX_API_URL=https://api.phemex.com/
PHEMEX_TESTNET=false  # Set to true for testing
PHEMEX_RATE_LIMIT=10  # Requests per second
```

## Configuration in PowerTraderAI+

### 1. Exchange Configuration
```python
from pt_exchanges import PhemexExchange

# Initialize Phemex exchange
phemex = PhemexExchange({
    'api_key': 'your_api_key',
    'secret_key': 'your_secret_key',
    'passphrase': 'your_passphrase',
    'api_url': 'https://api.phemex.com/',
    'testnet': False,  # Use testnet for testing
    'rate_limit': 10,  # Max 10 requests per second
    'timeout': 30
})
```

### 2. Trading Configuration
```python
# Configure trading parameters
phemex_config = {
    'default_leverage': 10,  # Default leverage for futures
    'max_leverage': 100,     # Maximum allowed leverage
    'risk_percentage': 0.02, # 2% risk per trade
    'use_spot_zero_fees': True,  # Prioritize zero-fee spot trading
    'auto_margin_mode': 'cross',  # 'cross' or 'isolated'
    'preferred_contracts': ['BTCUSD', 'ETHUSD', 'XRPUSD']
}
```

## Trading Features

### Spot Trading (Zero Fees)

```python
# Zero-fee spot trading pairs
zero_fee_pairs = [
    'BTCUSDT', 'ETHUSDT', 'XRPUSDT', 'ADAUSDT', 'DOTUSDT',
    'LINKUSDT', 'LTCUSDT', 'BCHUSDT', 'EOSUSDT', 'TRXUSDT',
    'XLMUSDT', 'XMRUSDT', 'DASHUSDT', 'ETCUSDT', 'ZECUSDT'
]

# Execute zero-fee spot trades
def execute_spot_trade(symbol, side, quantity, price=None):
    """
    Execute spot trade with zero fees
    """
    # Verify zero-fee eligibility
    if symbol not in zero_fee_pairs:
        print(f"Warning: {symbol} may have trading fees")

    # Place spot order
    if price is None:
        # Market order
        order = phemex.place_order({
            'symbol': symbol,
            'side': side,  # 'Buy' or 'Sell'
            'orderQtyRq': quantity,
            'ordType': 'Market'
        })
    else:
        # Limit order
        order = phemex.place_order({
            'symbol': symbol,
            'side': side,
            'orderQtyRq': quantity,
            'priceRp': price,
            'ordType': 'Limit'
        })

    print(f"Spot order placed: {order['orderID']}")
    return order
```

### Futures Trading

```python
# Advanced futures trading with leverage
def trade_futures_contract(symbol, side, size, leverage=10, order_type='Market'):
    """
    Trade perpetual futures contracts
    """
    # Set leverage for the contract
    phemex.set_leverage(symbol, leverage)

    # Calculate position size based on risk
    account_balance = phemex.get_account_balance()
    risk_amount = account_balance * phemex_config['risk_percentage']

    # Get current price for risk calculation
    ticker = phemex.get_ticker(symbol)
    current_price = ticker['markPrice']

    # Calculate position size
    if 'USD' in symbol:
        # USD-settled contracts (size in USD)
        position_size = min(size, risk_amount * leverage)
    else:
        # Coin-settled contracts (size in contracts)
        position_size = min(size, (risk_amount * leverage) / current_price)

    # Place futures order
    order = phemex.place_order({
        'symbol': symbol,
        'side': side,
        'orderQtyRq': position_size,
        'ordType': order_type,
        'reduceOnly': False,
        'closeOnTrigger': False
    })

    print(f"Futures order placed: {symbol} {side} {position_size}")
    return order

# Major perpetual contracts
perpetual_contracts = [
    'BTCUSD',   # Bitcoin USD-settled
    'ETHUSD',   # Ethereum USD-settled
    'XRPUSD',   # XRP USD-settled
    'ADAUSD',   # Cardano USD-settled
    'DOTUSD',   # Polkadot USD-settled
    'LINKUSD',  # Chainlink USD-settled
    'LTCUSD',   # Litecoin USD-settled
    'BCHUSD',   # Bitcoin Cash USD-settled
]
```

### Copy Trading Integration

```python
# Phemex copy trading features
def setup_copy_trading():
    """
    Configure and manage copy trading
    """
    # Find top traders to copy
    top_traders = phemex.get_top_traders({
        'timespan': '30d',
        'min_roi': 10,  # Minimum 10% return
        'min_followers': 100,
        'max_risk_score': 7
    })

    print("Top Copy Trading Candidates:")
    for trader in top_traders[:5]:
        print(f"Trader: {trader['nickname']}")
        print(f"  30d ROI: {trader['roi_30d']:.2f}%")
        print(f"  Followers: {trader['followers']:,}")
        print(f"  Risk Score: {trader['risk_score']}")
        print(f"  Win Rate: {trader['win_rate']:.1f}%")
        print()

    # Copy selected trader
    selected_trader = top_traders[0]
    copy_settings = {
        'trader_id': selected_trader['id'],
        'copy_amount': 1000,  # $1000 allocation
        'leverage_multiplier': 0.5,  # Use 50% of trader's leverage
        'copy_mode': 'proportion',  # Proportional copying
        'stop_loss': -20,  # Stop copying if -20% loss
        'max_positions': 10  # Maximum 10 concurrent positions
    }

    copy_result = phemex.start_copy_trading(copy_settings)
    print(f"Started copying trader: {copy_result['trader_id']}")

    return copy_result
```

## Advanced Features

### Strategy Trading

```python
# Automated trading strategies
def grid_trading_strategy(symbol, grid_size=0.5, num_grids=20):
    """
    Implement grid trading strategy
    """
    ticker = phemex.get_ticker(symbol)
    current_price = ticker['lastPrice']

    # Calculate grid levels
    grid_step = current_price * (grid_size / 100)

    # Place buy orders below current price
    buy_orders = []
    for i in range(1, num_grids // 2 + 1):
        buy_price = current_price - (grid_step * i)
        buy_quantity = 100 / buy_price  # $100 per grid

        order = phemex.place_order({
            'symbol': symbol,
            'side': 'Buy',
            'orderQtyRq': buy_quantity,
            'priceRp': buy_price,
            'ordType': 'Limit',
            'timeInForce': 'GoodTillCancel'
        })
        buy_orders.append(order)

    # Place sell orders above current price
    sell_orders = []
    for i in range(1, num_grids // 2 + 1):
        sell_price = current_price + (grid_step * i)
        sell_quantity = 100 / current_price  # $100 worth at current price

        order = phemex.place_order({
            'symbol': symbol,
            'side': 'Sell',
            'orderQtyRq': sell_quantity,
            'priceRp': sell_price,
            'ordType': 'Limit',
            'timeInForce': 'GoodTillCancel'
        })
        sell_orders.append(order)

    print(f"Grid trading setup: {len(buy_orders)} buy orders, {len(sell_orders)} sell orders")
    return {'buy_orders': buy_orders, 'sell_orders': sell_orders}

# DCA (Dollar Cost Averaging) strategy
def dca_strategy(symbol, amount_per_order=100, frequency_hours=24):
    """
    Implement automated DCA strategy
    """
    import time
    import threading

    def place_dca_order():
        try:
            ticker = phemex.get_ticker(symbol)
            current_price = ticker['lastPrice']
            quantity = amount_per_order / current_price

            order = phemex.place_order({
                'symbol': symbol,
                'side': 'Buy',
                'orderQtyRq': quantity,
                'ordType': 'Market'
            })

            print(f"DCA order placed: {symbol} ${amount_per_order} at {current_price}")

        except Exception as e:
            print(f"DCA order failed: {e}")

    # Schedule recurring orders
    def schedule_dca():
        while True:
            place_dca_order()
            time.sleep(frequency_hours * 3600)  # Wait for next interval

    # Start DCA in background thread
    dca_thread = threading.Thread(target=schedule_dca, daemon=True)
    dca_thread.start()

    print(f"DCA strategy started: {symbol} ${amount_per_order} every {frequency_hours}h")
```

### Launchpad Participation

```python
# Participate in Phemex Launchpad
def participate_in_launchpad():
    """
    Automatically participate in Phemex Launchpad events
    """
    # Get current launchpad projects
    projects = phemex.get_launchpad_projects()

    for project in projects:
        if project['status'] == 'open':
            print(f"Launchpad Project: {project['name']}")
            print(f"  Token: {project['token']}")
            print(f"  Price: ${project['price']}")
            print(f"  Max Allocation: ${project['max_allocation']}")
            print(f"  End Time: {project['end_time']}")

            # Check eligibility
            eligibility = phemex.check_launchpad_eligibility(project['id'])

            if eligibility['eligible']:
                # Calculate participation amount
                available_balance = phemex.get_spot_balance('USDT')
                max_participate = min(
                    project['max_allocation'],
                    available_balance * 0.1  # Use max 10% of balance
                )

                # Participate in launchpad
                participation = phemex.participate_launchpad(
                    project_id=project['id'],
                    amount=max_participate
                )

                print(f"Participated in {project['name']}: ${max_participate}")
```

## Risk Management

### Position Management

```python
# Comprehensive risk management
def manage_position_risk():
    """
    Monitor and manage all positions with automated risk controls
    """
    positions = phemex.get_all_positions()

    for position in positions:
        if position['size'] > 0:  # Active position
            symbol = position['symbol']
            side = position['side']
            size = position['size']
            entry_price = position['avgPx']
            current_price = position['markPrice']
            pnl_percentage = position['unrealizedPnlPcnt']

            print(f"Position: {symbol} {side} {size}")
            print(f"  Entry: ${entry_price}, Current: ${current_price}")
            print(f"  Unrealized PnL: {pnl_percentage:.2f}%")

            # Risk management rules
            if pnl_percentage <= -5:  # 5% stop loss
                print(f"  🛑 Stop loss triggered for {symbol}")
                close_order = phemex.place_order({
                    'symbol': symbol,
                    'side': 'Sell' if side == 'Buy' else 'Buy',
                    'orderQtyRq': size,
                    'ordType': 'Market',
                    'reduceOnly': True
                })
                print(f"  Position closed: {close_order['orderID']}")

            elif pnl_percentage >= 20:  # 20% take profit
                print(f"  💰 Take profit triggered for {symbol}")
                partial_close_size = size * 0.5  # Close 50%
                close_order = phemex.place_order({
                    'symbol': symbol,
                    'side': 'Sell' if side == 'Buy' else 'Buy',
                    'orderQtyRq': partial_close_size,
                    'ordType': 'Market',
                    'reduceOnly': True
                })
                print(f"  50% position closed: {close_order['orderID']}")

            # Trailing stop management
            elif pnl_percentage >= 10:  # Enable trailing stop at 10% profit
                trailing_stop_price = calculate_trailing_stop(
                    current_price, side, trailing_percentage=5
                )

                # Update or create stop order
                stop_order = phemex.place_conditional_order({
                    'symbol': symbol,
                    'side': 'Sell' if side == 'Buy' else 'Buy',
                    'orderQtyRq': size,
                    'ordType': 'Stop',
                    'stopPxRp': trailing_stop_price,
                    'reduceOnly': True
                })
                print(f"  📈 Trailing stop set at ${trailing_stop_price}")

def calculate_trailing_stop(current_price, side, trailing_percentage):
    """Calculate trailing stop price"""
    if side == 'Buy':
        return current_price * (1 - trailing_percentage / 100)
    else:
        return current_price * (1 + trailing_percentage / 100)
```

### Account Protection

```python
# Account-level risk protection
def account_risk_protection():
    """
    Monitor account-level risk metrics
    """
    account = phemex.get_account_info()

    # Calculate key risk metrics
    total_equity = account['totalEquityValueRv']
    used_margin = account['totalUsedBalanceRv']
    available_margin = account['totalAvailableBalanceRv']
    margin_ratio = used_margin / total_equity if total_equity > 0 else 0

    print(f"Account Risk Metrics:")
    print(f"  Total Equity: ${total_equity:,.2f}")
    print(f"  Used Margin: ${used_margin:,.2f}")
    print(f"  Margin Ratio: {margin_ratio:.2%}")
    print(f"  Available Margin: ${available_margin:,.2f}")

    # Risk alerts
    if margin_ratio > 0.8:  # 80% margin usage
        print("⚠️ HIGH RISK: Margin usage above 80%")

        # Reduce positions or add margin
        reduce_risk_exposure()

    elif margin_ratio > 0.6:  # 60% margin usage
        print("⚠️ MEDIUM RISK: Margin usage above 60%")

    # Daily loss limit check
    daily_pnl = phemex.get_daily_pnl()
    max_daily_loss = total_equity * 0.05  # 5% daily loss limit

    if daily_pnl < -max_daily_loss:
        print("🛑 DAILY LOSS LIMIT REACHED")
        close_all_positions()

def reduce_risk_exposure():
    """Reduce risk when margin usage is too high"""
    positions = phemex.get_all_positions()

    # Close smallest positions first
    sorted_positions = sorted(positions, key=lambda x: x['size'])

    for position in sorted_positions:
        if position['size'] > 0:
            # Close position
            phemex.place_order({
                'symbol': position['symbol'],
                'side': 'Sell' if position['side'] == 'Buy' else 'Buy',
                'orderQtyRq': position['size'],
                'ordType': 'Market',
                'reduceOnly': True
            })
            print(f"Risk reduction: Closed {position['symbol']}")
            break
```

## Integration Examples

### Complete Trading Setup

```python
import os
from pt_exchanges import PhemexExchange

# Initialize Phemex exchange
phemex = PhemexExchange({
    'api_key': os.getenv('PHEMEX_API_KEY'),
    'secret_key': os.getenv('PHEMEX_SECRET_KEY'),
    'passphrase': os.getenv('PHEMEX_PASSPHRASE'),
    'testnet': False
})

# Comprehensive trading strategy
def phemex_trading_strategy():
    print("⚡ Phemex Automated Trading Strategy")
    print("=" * 40)

    # 1. Account overview
    account = phemex.get_account_info()
    print(f"Account Balance: ${account['totalEquityValueRv']:,.2f}")
    print(f"Available Balance: ${account['totalAvailableBalanceRv']:,.2f}")

    # 2. Zero-fee spot trading opportunities
    spot_opportunities = phemex.find_spot_arbitrage()
    if spot_opportunities:
        print(f"\n💰 Found {len(spot_opportunities)} spot arbitrage opportunities")
        for opp in spot_opportunities[:3]:  # Top 3 opportunities
            print(f"  {opp['symbol']}: {opp['profit_percentage']:.3f}% profit")

            # Execute if profitable
            if opp['profit_percentage'] > 0.1:  # 0.1% minimum
                execute_spot_trade(
                    opp['symbol'],
                    opp['side'],
                    opp['quantity']
                )

    # 3. Futures trading signals
    futures_signals = phemex.get_trading_signals(['BTCUSD', 'ETHUSD'])
    for signal in futures_signals:
        if signal['confidence'] > 0.7:  # High confidence signals only
            print(f"\n📈 Trading Signal: {signal['symbol']}")
            print(f"  Direction: {signal['direction']}")
            print(f"  Confidence: {signal['confidence']:.1%}")
            print(f"  Entry: ${signal['entry_price']:,.2f}")
            print(f"  Target: ${signal['target_price']:,.2f}")
            print(f"  Stop Loss: ${signal['stop_loss']:,.2f}")

            # Execute trade
            trade_futures_contract(
                symbol=signal['symbol'],
                side=signal['direction'],
                size=signal['position_size'],
                leverage=10
            )

    # 4. Risk management check
    manage_position_risk()
    account_risk_protection()

    # 5. Copy trading management
    copy_positions = phemex.get_copy_trading_positions()
    if copy_positions:
        print(f"\n👥 Copy Trading: {len(copy_positions)} active copies")
        for copy_pos in copy_positions:
            if copy_pos['pnl_percentage'] < -10:  # Stop copying if -10%
                phemex.stop_copy_trading(copy_pos['trader_id'])
                print(f"  Stopped copying {copy_pos['trader_name']} (Loss: {copy_pos['pnl_percentage']:.1f}%)")

    print("\n✅ Strategy execution completed!")

# Run the automated strategy
phemex_trading_strategy()
```

### Zero-Fee Arbitrage Bot

```python
# Specialized zero-fee arbitrage bot
def zero_fee_arbitrage_bot():
    """
    Automated arbitrage bot leveraging Phemex zero-fee spot trading
    """
    print("🤖 Zero-Fee Arbitrage Bot Started")

    while True:
        try:
            # Find arbitrage opportunities
            arbitrage_opps = []

            for pair in zero_fee_pairs:
                # Compare Phemex price with other exchanges
                phemex_price = phemex.get_ticker(pair)['lastPrice']

                # Get price from Binance for comparison
                binance_pair = pair.replace('USDT', 'USDT')
                binance_price = get_binance_price(binance_pair)  # Implement this

                # Calculate arbitrage opportunity
                price_diff = (phemex_price - binance_price) / binance_price

                if abs(price_diff) > 0.002:  # 0.2% minimum opportunity
                    arbitrage_opps.append({
                        'pair': pair,
                        'price_diff': price_diff,
                        'phemex_price': phemex_price,
                        'binance_price': binance_price,
                        'direction': 'buy_phemex' if price_diff < 0 else 'sell_phemex'
                    })

            # Execute profitable arbitrage
            for opp in sorted(arbitrage_opps, key=lambda x: abs(x['price_diff']), reverse=True):
                if abs(opp['price_diff']) > 0.005:  # 0.5% minimum for execution

                    trade_amount = 1000  # $1000 per arbitrage trade
                    quantity = trade_amount / opp['phemex_price']

                    if opp['direction'] == 'buy_phemex':
                        # Buy on Phemex (cheaper), sell on Binance
                        phemex_order = execute_spot_trade(opp['pair'], 'Buy', quantity)
                        print(f"Arbitrage: Bought {quantity:.6f} {opp['pair']} on Phemex")

                    else:
                        # Sell on Phemex (higher price), buy on Binance
                        phemex_order = execute_spot_trade(opp['pair'], 'Sell', quantity)
                        print(f"Arbitrage: Sold {quantity:.6f} {opp['pair']} on Phemex")

                    estimated_profit = trade_amount * abs(opp['price_diff'])
                    print(f"Estimated profit: ${estimated_profit:.2f}")

            # Wait before next scan
            time.sleep(30)  # 30-second intervals

        except Exception as e:
            print(f"Arbitrage bot error: {e}")
            time.sleep(60)  # Wait longer on error

# Start the arbitrage bot
# zero_fee_arbitrage_bot()  # Uncomment to run
```

This completes the Phemex integration setup. The exchange's zero-fee spot trading and advanced derivatives capabilities provide excellent opportunities for both conservative and aggressive trading strategies within PowerTraderAI+'s framework.
