# Aave Protocol Integration Setup Guide

## Overview
Aave is the leading decentralized lending protocol with over $6 billion in total value locked (TVL). Built on Ethereum and multiple other chains, Aave allows users to lend and borrow cryptocurrencies in a trustless manner while earning yield on deposits and accessing innovative features like flash loans and rate switching.

## Features
- **Multi-Chain Support**: Ethereum, Polygon, Arbitrum, Optimism, Avalanche, Fantom
- **Lending & Borrowing**: 30+ cryptocurrencies supported
- **Flexible Interest Rates**: Stable and variable rate options
- **Flash Loans**: Uncollateralized loans for arbitrage and liquidations
- **aTokens**: Interest-bearing tokens representing deposits
- **Governance**: AAVE token voting on protocol upgrades

## Prerequisites
- Web3 wallet (MetaMask, WalletConnect, etc.)
- ETH or native tokens for transaction fees
- Supported tokens for lending/borrowing
- Understanding of DeFi risks (smart contract, liquidation)

## Technical Setup

### 1. Web3 Wallet Configuration

```python
from web3 import Web3
from eth_account import Account
import json

# Initialize Web3 connection
w3 = Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/YOUR_INFURA_KEY'))

# Load wallet from private key
private_key = os.getenv('WALLET_PRIVATE_KEY')
account = Account.from_key(private_key)
wallet_address = account.address

print(f"Wallet Address: {wallet_address}")
print(f"ETH Balance: {w3.eth.get_balance(wallet_address) / 10**18:.4f} ETH")
```

### 2. Aave Contract Addresses & ABIs

```python
# Aave Protocol Addresses (Ethereum Mainnet)
AAVE_CONTRACTS = {
    # Core Contracts
    'pool': '0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2',
    'pool_data_provider': '0x7B4EB56E7CD4b454BA8ff71E4518426369a138a3',
    'price_oracle': '0x54586bE62E3c3580375aE3723C145253060Ca0C2',
    'aave_oracle': '0x54586bE62E3c3580375aE3723C145253060Ca0C2',
    'rewards_controller': '0x8164Cc65827dcFe994AB23944CBC90e0aa80bFcb',

    # Token Contracts
    'aave_token': '0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9',
    'staked_aave': '0x4da27a545c0c5B758a6BA100e3a049001de870f5',

    # aTokens (Interest-bearing)
    'aUSDC': '0xBcca60bB61934080951369a648Fb03DF4F96263C',
    'aUSDT': '0x3Ed3B47Dd13EC9a98b44e6204A523E766B225811',
    'aDAI': '0x018008bfb33d285247A21d44E50697654f754e63',
    'aWETH': '0x4d5F47FA6A74757f35C14fD3a6Ef8E3C9BC514E8',
    'aWBTC': '0x5Ee5bf7ae06D1Be5997A1A72006FE6C607eC6DE8',

    # Debt Tokens
    'variableDebtUSDC': '0x72E95b8931767C79bA4EeE721354d6E99a61D004',
    'stableDebtUSDC': '0xDC6a3Ab17299D9C2A412B0294d3a27c56Dd01203'
}

# Load contract ABIs
def load_aave_abi(contract_name):
    with open(f'abis/aave_{contract_name}.json', 'r') as f:
        return json.load(f)

# Initialize Aave Pool contract
aave_pool = w3.eth.contract(
    address=AAVE_CONTRACTS['pool'],
    abi=load_aave_abi('pool')
)
```

### 3. Configure PowerTraderAI+

Add Aave configuration to your environment:

```bash
# Aave DeFi Configuration
AAVE_WALLET_ADDRESS=0xYourWalletAddress
AAVE_PRIVATE_KEY=your_private_key_here
AAVE_INFURA_KEY=your_infura_project_id
AAVE_CHAIN_IDS=1,137,42161,10  # Ethereum, Polygon, Arbitrum, Optimism
AAVE_SLIPPAGE_TOLERANCE=0.01   # 1%
AAVE_GAS_LIMIT_MULTIPLIER=1.3
AAVE_HEALTH_FACTOR_MIN=2.0     # Minimum health factor
```

## Configuration in PowerTraderAI+

### 1. Exchange Configuration
```python
from pt_exchanges import AaveExchange

# Initialize Aave exchange
aave = AaveExchange({
    'wallet_address': 'your_wallet_address',
    'private_key': 'your_private_key',
    'infura_key': 'your_infura_key',
    'chain_ids': [1, 137, 42161, 10],  # Multi-chain support
    'health_factor_min': 2.0,  # Conservative health factor
    'gas_limit_multiplier': 1.3,
    'max_gas_price': 80  # Max 80 gwei
})
```

### 2. Lending Configuration
```python
# Configure DeFi lending parameters
aave_config = {
    'preferred_lending_assets': ['USDC', 'USDT', 'DAI', 'WETH'],
    'preferred_borrowing_assets': ['USDC', 'WETH'],
    'max_ltv_ratio': 0.7,  # Maximum 70% loan-to-value
    'target_health_factor': 2.5,  # Target health factor
    'auto_compound': True,  # Auto-compound rewards
    'use_emode': True,  # Use efficiency mode when applicable
    'rate_switching': True  # Auto-switch between stable/variable rates
}
```

## Lending & Borrowing Features

### Available Assets & Rates

```python
# Get all available Aave markets
def get_aave_markets():
    """
    Fetch all available lending markets with current rates
    """
    markets = aave.get_all_reserves_data()

    print("📊 Aave Lending Markets:")
    print("=" * 60)
    print(f"{'Asset':<8} {'Supply APY':<12} {'Borrow APY':<12} {'Utilization':<12} {'Total Supply':<15}")
    print("-" * 60)

    for asset, data in markets.items():
        supply_apy = data['supply_apy']
        borrow_apy = data['variable_borrow_apy']
        utilization = data['utilization_rate']
        total_supply = data['total_liquidity']

        print(f"{asset:<8} {supply_apy:<11.2%} {borrow_apy:<11.2%} {utilization:<11.2%} ${total_supply:<14,.0f}")

# Major lending assets with current APYs
lending_assets = {
    'USDC': {'apy_range': '1-8%', 'risk_level': 'Low', 'liquidity': 'High'},
    'USDT': {'apy_range': '1-7%', 'risk_level': 'Low', 'liquidity': 'High'},
    'DAI': {'apy_range': '2-9%', 'risk_level': 'Low', 'liquidity': 'High'},
    'WETH': {'apy_range': '0.5-4%', 'risk_level': 'Medium', 'liquidity': 'High'},
    'WBTC': {'apy_range': '0.2-3%', 'risk_level': 'Medium', 'liquidity': 'Medium'},
    'AAVE': {'apy_range': '0.5-6%', 'risk_level': 'Medium', 'liquidity': 'Medium'}
}
```

### Lending Operations

```python
# Execute lending operations
def supply_to_aave(asset, amount):
    """
    Supply assets to Aave for lending
    """
    print(f"Supplying {amount} {asset} to Aave...")

    # Check current rates
    reserve_data = aave.get_reserve_data(asset)
    current_apy = reserve_data['supply_apy']

    print(f"Current {asset} lending APY: {current_apy:.2%}")

    # Execute supply transaction
    tx_hash = aave.supply(
        asset=asset,
        amount=amount,
        on_behalf_of=aave.wallet_address,
        referral_code=0
    )

    print(f"Supply transaction: {tx_hash}")

    # Monitor for aToken receipt
    atoken_balance = aave.get_atoken_balance(asset)
    print(f"aToken balance: {atoken_balance:.6f} a{asset}")

    return tx_hash

# Withdraw from Aave
def withdraw_from_aave(asset, amount=None):
    """
    Withdraw supplied assets from Aave
    """
    if amount is None:
        # Withdraw maximum available
        atoken_balance = aave.get_atoken_balance(asset)
        amount = atoken_balance

    print(f"Withdrawing {amount} {asset} from Aave...")

    # Execute withdrawal
    tx_hash = aave.withdraw(
        asset=asset,
        amount=amount,
        to=aave.wallet_address
    )

    print(f"Withdrawal transaction: {tx_hash}")
    return tx_hash

# Example: Supply 1000 USDC to Aave
supply_tx = supply_to_aave('USDC', 1000)
```

### Borrowing Operations

```python
# Execute borrowing operations
def borrow_from_aave(asset, amount, interest_rate_mode='variable'):
    """
    Borrow assets from Aave using supplied collateral
    """
    # Check borrowing power
    account_data = aave.get_user_account_data()
    available_borrow_usd = account_data['available_borrows_usd']

    # Get asset price
    asset_price = aave.get_asset_price(asset)
    max_borrow_amount = available_borrow_usd / asset_price

    print(f"Available borrowing power: ${available_borrow_usd:,.2f}")
    print(f"Max {asset} borrow amount: {max_borrow_amount:.6f}")

    if amount > max_borrow_amount:
        print("⚠️ Borrow amount exceeds available credit")
        return None

    # Check health factor impact
    projected_hf = aave.calculate_health_factor_after_borrow(asset, amount)

    if projected_hf < aave_config['target_health_factor']:
        print(f"⚠️ Health factor would drop to {projected_hf:.2f}")
        return None

    # Execute borrow
    rate_mode = 1 if interest_rate_mode == 'stable' else 2  # 1=stable, 2=variable

    tx_hash = aave.borrow(
        asset=asset,
        amount=amount,
        interest_rate_mode=rate_mode,
        referral_code=0,
        on_behalf_of=aave.wallet_address
    )

    print(f"Borrow transaction: {tx_hash}")
    print(f"New health factor: {aave.get_health_factor():.2f}")

    return tx_hash

# Repay borrowed assets
def repay_to_aave(asset, amount=None, rate_mode='variable'):
    """
    Repay borrowed assets to Aave
    """
    if amount is None:
        # Repay full debt
        debt_balance = aave.get_debt_token_balance(asset, rate_mode)
        amount = debt_balance

    print(f"Repaying {amount} {asset} to Aave...")

    rate_mode_code = 1 if rate_mode == 'stable' else 2

    tx_hash = aave.repay(
        asset=asset,
        amount=amount,
        rate_mode=rate_mode_code,
        on_behalf_of=aave.wallet_address
    )

    print(f"Repay transaction: {tx_hash}")
    return tx_hash
```

## Advanced DeFi Strategies

### Yield Farming with Leverage

```python
# Leveraged yield farming strategy
def leveraged_yield_farming():
    """
    Leverage supplied assets to multiply yield exposure
    Popular strategy with stablecoins and ETH
    """
    # Initial supply: 10,000 USDC
    initial_supply = 10000
    leverage_multiplier = 3  # 3x leverage
    target_asset = 'USDC'

    print(f"🚜 Leveraged Yield Farming: {leverage_multiplier}x {target_asset}")

    # Step 1: Supply initial USDC
    supply_to_aave('USDC', initial_supply)

    # Step 2: Borrow USDC against USDC (efficiency mode)
    max_ltv = 0.92  # USDC has 92% LTV in efficiency mode
    borrow_amount = initial_supply * max_ltv

    cycles = []
    total_supplied = initial_supply

    for cycle in range(int(leverage_multiplier)):
        if cycle > 0:
            # Supply borrowed amount
            supply_to_aave('USDC', borrow_amount)
            total_supplied += borrow_amount

            # Calculate next borrow amount
            borrow_amount = borrow_amount * max_ltv

        # Borrow for next cycle
        if cycle < leverage_multiplier - 1:
            borrow_tx = borrow_from_aave('USDC', borrow_amount)

            cycles.append({
                'cycle': cycle + 1,
                'supplied': borrow_amount if cycle > 0 else initial_supply,
                'borrowed': borrow_amount,
                'total_supplied': total_supplied
            })

    # Calculate effective yield
    base_apy = aave.get_reserve_data('USDC')['supply_apy']
    borrow_apy = aave.get_reserve_data('USDC')['variable_borrow_apy']

    net_apy = (base_apy * total_supplied) - (borrow_apy * (total_supplied - initial_supply))
    effective_apy = net_apy / initial_supply

    print(f"💰 Strategy Results:")
    print(f"  Initial Supply: ${initial_supply:,.2f}")
    print(f"  Total Supplied: ${total_supplied:,.2f}")
    print(f"  Effective Leverage: {total_supplied/initial_supply:.1f}x")
    print(f"  Base APY: {base_apy:.2%}")
    print(f"  Effective APY: {effective_apy:.2%}")

    return cycles

# Execute leveraged farming
leverage_cycles = leveraged_yield_farming()
```

### Flash Loan Arbitrage

```python
# Flash loan arbitrage implementation
def flash_loan_arbitrage():
    """
    Use Aave flash loans for arbitrage opportunities
    Borrow large amounts without collateral for single transaction
    """
    # Find arbitrage opportunity
    arbitrage_opportunity = find_arbitrage_opportunity()

    if not arbitrage_opportunity:
        print("No arbitrage opportunities found")
        return

    flash_loan_amount = arbitrage_opportunity['amount']
    asset = arbitrage_opportunity['asset']
    expected_profit = arbitrage_opportunity['profit']

    print(f"⚡ Flash Loan Arbitrage Opportunity:")
    print(f"  Asset: {asset}")
    print(f"  Amount: {flash_loan_amount:,.2f}")
    print(f"  Expected Profit: ${expected_profit:.2f}")

    # Flash loan fee (0.09% on Aave)
    flash_loan_fee = flash_loan_amount * 0.0009
    net_profit = expected_profit - flash_loan_fee

    if net_profit > 10:  # Minimum $10 profit
        print(f"  Flash Loan Fee: ${flash_loan_fee:.2f}")
        print(f"  Net Profit: ${net_profit:.2f}")

        # Execute flash loan
        flash_loan_params = {
            'receiver_address': aave.wallet_address,
            'assets': [aave.get_asset_address(asset)],
            'amounts': [int(flash_loan_amount * 10**18)],  # Convert to wei
            'modes': [0],  # 0 = no debt, repay in same transaction
            'on_behalf_of': aave.wallet_address,
            'params': encode_arbitrage_params(arbitrage_opportunity),
            'referral_code': 0
        }

        tx_hash = aave.flash_loan(**flash_loan_params)
        print(f"Flash loan executed: {tx_hash}")

        return tx_hash
    else:
        print("Arbitrage not profitable after fees")
        return None

def find_arbitrage_opportunity():
    """
    Scan for arbitrage opportunities across DEXs
    """
    # Simplified - implement actual DEX price comparison
    return {
        'asset': 'USDC',
        'amount': 100000,
        'profit': 50,
        'dex1': 'Uniswap',
        'dex2': 'SushiSwap'
    }
```

## Rate Optimization

### Dynamic Rate Switching

```python
# Automatic rate switching for optimal borrowing costs
def optimize_borrow_rates():
    """
    Automatically switch between stable and variable rates
    based on market conditions and rate projections
    """
    borrowed_assets = aave.get_user_debt_positions()

    for position in borrowed_assets:
        asset = position['asset']
        current_rate_mode = position['rate_mode']  # 'stable' or 'variable'
        current_rate = position['current_rate']

        # Get current rates for both modes
        reserve_data = aave.get_reserve_data(asset)
        stable_rate = reserve_data['stable_borrow_apy']
        variable_rate = reserve_data['variable_borrow_apy']

        print(f"📊 Rate Analysis for {asset}:")
        print(f"  Current Mode: {current_rate_mode}")
        print(f"  Current Rate: {current_rate:.2%}")
        print(f"  Stable Rate: {stable_rate:.2%}")
        print(f"  Variable Rate: {variable_rate:.2%}")

        # Rate switching logic
        should_switch = False
        new_rate_mode = current_rate_mode

        if current_rate_mode == 'stable' and variable_rate < stable_rate - 0.005:  # 0.5% threshold
            should_switch = True
            new_rate_mode = 'variable'
            savings = (stable_rate - variable_rate) * position['amount']

        elif current_rate_mode == 'variable' and stable_rate < variable_rate - 0.005:
            should_switch = True
            new_rate_mode = 'stable'
            savings = (variable_rate - stable_rate) * position['amount']

        if should_switch:
            print(f"SWITCHING: Switching {asset} from {current_rate_mode} to {new_rate_mode}")
            print(f"  Annual Savings: ${savings:.2f}")

            # Execute rate switch
            new_mode_code = 1 if new_rate_mode == 'stable' else 2
            tx_hash = aave.swap_borrow_rate_mode(
                asset=asset,
                rate_mode=new_mode_code
            )

            print(f"  Rate switch transaction: {tx_hash}")
        else:
            print(f"  ✅ Current rate is optimal")

# Run rate optimization
optimize_borrow_rates()
```

## Risk Management

### Health Factor Monitoring

```python
# Comprehensive risk management system
def monitor_health_factor():
    """
    Monitor and maintain safe health factor levels
    """
    account_data = aave.get_user_account_data()
    health_factor = account_data['health_factor']

    print(f"🏥 Health Factor: {health_factor:.2f}")

    # Risk levels
    if health_factor > 3.0:
        risk_level = "Low"
        action = "Safe to borrow more"
    elif health_factor > 2.0:
        risk_level = "Medium"
        action = "Monitor closely"
    elif health_factor > 1.5:
        risk_level = "High"
        action = "Consider reducing debt"
    elif health_factor > 1.1:
        risk_level = "Critical"
        action = "Reduce debt immediately"
    else:
        risk_level = "Liquidation Risk"
        action = "Emergency action required"

    print(f"Risk Level: {risk_level}")
    print(f"Recommended Action: {action}")

    # Auto-protect against liquidation
    if health_factor < 1.5:
        auto_protect_position(health_factor)

    return health_factor

def auto_protect_position(current_hf):
    """
    Automatically protect position from liquidation
    """
    print("🛡️ Auto-protecting position...")

    target_hf = 2.0  # Target health factor
    account_data = aave.get_user_account_data()

    # Calculate required repayment to reach target HF
    debt_positions = aave.get_user_debt_positions()

    for position in debt_positions:
        asset = position['asset']
        debt_amount = position['amount']

        # Calculate repayment needed
        required_repayment = calculate_repayment_for_hf(asset, debt_amount, target_hf)

        if required_repayment > 0:
            # Check if we have enough balance
            wallet_balance = aave.get_wallet_balance(asset)

            if wallet_balance >= required_repayment:
                print(f"Repaying {required_repayment:.6f} {asset}")
                repay_to_aave(asset, required_repayment)
            else:
                # Swap other assets to get repayment currency
                print(f"Need to swap assets to repay {asset}")
                swap_for_repayment(asset, required_repayment)

def calculate_repayment_for_hf(asset, debt_amount, target_hf):
    """Calculate required repayment to achieve target health factor"""
    # Simplified calculation - implement actual math based on Aave formulas
    current_hf = aave.get_health_factor()
    if current_hf >= target_hf:
        return 0

    # Estimate repayment needed (this is simplified)
    repayment_percentage = (target_hf - current_hf) / target_hf
    return debt_amount * repayment_percentage
```

## Integration Examples

### Complete DeFi Strategy

```python
import os
from pt_exchanges import AaveExchange

# Initialize Aave integration
aave = AaveExchange({
    'wallet_address': os.getenv('AAVE_WALLET_ADDRESS'),
    'private_key': os.getenv('AAVE_PRIVATE_KEY'),
    'infura_key': os.getenv('AAVE_INFURA_KEY')
})

# Automated Aave strategy
def automated_aave_strategy():
    print("🌊 Aave DeFi Automated Strategy")
    print("=" * 35)

    # 1. Account overview
    account_data = aave.get_user_account_data()
    health_factor = account_data['health_factor']

    print(f"Health Factor: {health_factor:.2f}")
    print(f"Total Collateral: ${account_data['total_collateral_usd']:,.2f}")
    print(f"Total Debt: ${account_data['total_debt_usd']:,.2f}")
    print(f"Available to Borrow: ${account_data['available_borrows_usd']:,.2f}")

    # 2. Monitor and protect health factor
    if health_factor < 2.0:
        print("⚠️ Health factor below target - protecting position")
        auto_protect_position(health_factor)

    # 3. Optimize borrowing rates
    print("\nOPTIMIZING: Optimizing Borrowing Rates:")
    optimize_borrow_rates()

    # 4. Compound rewards
    rewards_balance = aave.get_rewards_balance()
    if rewards_balance > 0:
        print(f"\n💰 Claiming {rewards_balance:.6f} AAVE rewards")
        aave.claim_all_rewards()

    # 5. Yield optimization
    print("\n📈 Yield Optimization Analysis:")
    markets = aave.get_all_reserves_data()

    # Find best lending opportunities
    best_lending = max(markets.items(), key=lambda x: x[1]['supply_apy'])
    print(f"Best Lending APY: {best_lending[0]} at {best_lending[1]['supply_apy']:.2%}")

    # Find cheapest borrowing
    borrowable = {k: v for k, v in markets.items() if v['borrowing_enabled']}
    cheapest_borrow = min(borrowable.items(), key=lambda x: x[1]['variable_borrow_apy'])
    print(f"Cheapest Borrowing: {cheapest_borrow[0]} at {cheapest_borrow[1]['variable_borrow_apy']:.2%}")

    # 6. Flash loan opportunities
    arbitrage_opp = find_arbitrage_opportunity()
    if arbitrage_opp and arbitrage_opp['profit'] > 10:
        print(f"\n⚡ Flash Loan Opportunity: ${arbitrage_opp['profit']:.2f} profit")
        flash_loan_arbitrage()

    print("\n✅ Aave strategy execution completed!")

# Run the automated strategy
automated_aave_strategy()
```

This completes the Aave Protocol integration setup, providing comprehensive DeFi lending and borrowing capabilities with advanced features like flash loans, leveraged yield farming, and automatic risk management within PowerTraderAI+'s framework.
