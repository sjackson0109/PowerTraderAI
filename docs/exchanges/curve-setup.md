# Curve Finance Integration Setup Guide

## Overview
Curve Finance is the leading decentralized exchange (DEX) specialized in stablecoin and similar asset trading. Built on Ethereum and multiple other chains, Curve offers the most efficient swaps for correlated assets with minimal slippage and provides substantial yield opportunities through liquidity provision.

## Features
- **Stablecoin Specialist**: Optimized for low-slippage stablecoin swaps
- **Multi-Chain Support**: Ethereum, Polygon, Arbitrum, Optimism, Avalanche, Fantom
- **High Yields**: Competitive APY through liquidity provision and CRV rewards
- **Low Slippage**: Efficient AMM algorithm for similar assets
- **Governance Token**: CRV token with voting power and fee sharing
- **Gauge System**: Incentivized liquidity pools with boosted rewards

## Prerequisites
- Web3 wallet (MetaMask, WalletConnect, etc.)
- ETH or native tokens for transaction fees
- Supported tokens for trading/liquidity provision
- Understanding of DeFi and impermanent loss risks

## Technical Setup

### 1. Web3 Wallet Configuration

```python
from web3 import Web3
from eth_account import Account
import json

# Initialize Web3 connection
w3 = Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/YOUR_INFURA_KEY'))

# Load wallet from private key (secure method recommended)
private_key = os.getenv('WALLET_PRIVATE_KEY')
account = Account.from_key(private_key)
wallet_address = account.address

print(f"Wallet Address: {wallet_address}")
print(f"ETH Balance: {w3.eth.get_balance(wallet_address) / 10**18:.4f} ETH")
```

### 2. Contract Addresses & ABIs

```python
# Curve Protocol Addresses (Ethereum Mainnet)
CURVE_CONTRACTS = {
    # Core Contracts
    'registry': '0x90E00ACe148ca3b23Ac1bC8C240C2a7Dd9c2d7f5',
    'pool_registry': '0xB9fC157394Af804a3578134A6585C0dc9cc990d4',
    'gauge_controller': '0x2F50D538606Fa9EDD2B11E2446BEb18C9D5846bB',
    'minter': '0xd061D61a4d941c39E5453435B6345Dc261C2fcE0',
    'voting_escrow': '0x5f3b5DfEb7B28CDbD7FAba78963EE202a494e2A2',

    # Token Contracts
    'crv_token': '0xD533a949740bb3306d119CC777fa900bA034cd52',
    'cvx_token': '0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B',

    # Major Pools
    '3pool': '0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7',  # DAI/USDC/USDT
    'steth': '0xDC24316b9AE028F1497c275EB9192a3Ea0f67022',  # ETH/stETH
    'frax': '0xd632f22692FaC7611d2AA1C0D552930D43CAEd3B',   # FRAX/3CRV
    'mim': '0x5a6A4D54456819380173272A5E8E9B9904BdF41B',    # MIM/3CRV
    'tricrypto': '0x80466c64868E1ab14a1Ddf27A676C3fcBE638Fe5'  # USDT/WBTC/WETH
}

# Load contract ABIs (store in separate files)
def load_abi(contract_name):
    with open(f'abis/{contract_name}.json', 'r') as f:
        return json.load(f)

# Initialize contract instances
pool_registry = w3.eth.contract(
    address=CURVE_CONTRACTS['pool_registry'],
    abi=load_abi('pool_registry')
)
```

### 3. Configure PowerTraderAI+

Add Curve configuration to your environment:

```bash
# Curve DeFi Configuration
CURVE_WALLET_ADDRESS=0xYourWalletAddress
CURVE_PRIVATE_KEY=your_private_key_here
CURVE_INFURA_KEY=your_infura_project_id
CURVE_CHAIN_IDS=1,137,42161,10  # Ethereum, Polygon, Arbitrum, Optimism
CURVE_SLIPPAGE_TOLERANCE=0.005  # 0.5%
CURVE_GAS_LIMIT_MULTIPLIER=1.2
```

## Configuration in PowerTraderAI+

### 1. Exchange Configuration
```python
from pt_exchanges import CurveExchange

# Initialize Curve exchange
curve = CurveExchange({
    'wallet_address': 'your_wallet_address',
    'private_key': 'your_private_key',
    'infura_key': 'your_infura_key',
    'chain_ids': [1, 137, 42161, 10],  # Multi-chain support
    'slippage_tolerance': 0.005,  # 0.5% slippage
    'gas_limit_multiplier': 1.2,
    'max_gas_price': 100  # Max 100 gwei
})
```

### 2. Trading Configuration
```python
# Configure DeFi trading parameters
curve_config = {
    'preferred_pools': ['3pool', 'steth', 'tricrypto'],
    'min_liquidity_usd': 1000000,  # $1M minimum pool liquidity
    'max_slippage': 0.01,  # 1% maximum slippage
    'auto_compound': True,  # Auto-compound CRV rewards
    'gauge_staking': True,  # Auto-stake LP tokens in gauges
    'boost_optimization': True  # Optimize veCRV boost
}
```

## Trading Features

### Available Pools & Assets

```python
# Get all available Curve pools
def get_curve_pools():
    pools = curve.get_all_pools()

    print("Major Curve Pools:")
    for pool in pools[:10]:  # Show top 10 by TVL
        print(f"Pool: {pool['name']}")
        print(f"  Assets: {', '.join(pool['coins'])}")
        print(f"  TVL: ${pool['tvl']:,.0f}")
        print(f"  APY: {pool['apy']:.2f}%")
        print(f"  Volume 24h: ${pool['volume_24h']:,.0f}")
        print()

# Major stablecoin pools
stablecoin_pools = [
    '3pool',      # DAI/USDC/USDT
    'frax',       # FRAX/3CRV
    'mim',        # MIM/3CRV
    'lusd',       # LUSD/3CRV
    'susd',       # sUSD/DAI/USDC/USDT
]

# ETH derivative pools
eth_pools = [
    'steth',      # ETH/stETH
    'reth',       # ETH/rETH
    'seth',       # ETH/sETH
    'ankreth',    # ETH/ankrETH
]

# BTC pools
btc_pools = [
    'ren',        # renBTC/WBTC/sBTC
    'sbtc',       # sBTC/renBTC/WBTC
    'bbtc',       # bBTC/sbtc
]
```

### Swap Operations

```python
# Execute token swaps with optimal routing
def execute_curve_swap(from_token, to_token, amount, min_amount_out=None):
    """
    Execute swap on Curve with best route finding
    """
    # Find best pool and route
    route = curve.find_best_route(from_token, to_token, amount)

    print(f"Best route found:")
    print(f"  Route: {' -> '.join(route['path'])}")
    print(f"  Expected output: {route['expected_amount']:.6f} {to_token}")
    print(f"  Price impact: {route['price_impact']:.3f}%")
    print(f"  Estimated gas: {route['gas_estimate']:,}")

    # Set minimum amount if not provided (with slippage tolerance)
    if min_amount_out is None:
        min_amount_out = route['expected_amount'] * (1 - curve_config['max_slippage'])

    # Execute swap
    tx_hash = curve.swap(
        from_token=from_token,
        to_token=to_token,
        amount=amount,
        min_amount_out=min_amount_out,
        route=route['path']
    )

    print(f"Swap executed: {tx_hash}")
    return tx_hash

# Example: Swap 1000 USDC for USDT
swap_tx = execute_curve_swap('USDC', 'USDT', 1000)
```

### Liquidity Provision

```python
# Provide liquidity to earn fees and CRV rewards
def add_liquidity_to_pool(pool_name, amounts, min_mint_amount=None):
    """
    Add liquidity to a Curve pool
    """
    pool_info = curve.get_pool_info(pool_name)

    # Calculate expected LP tokens
    expected_lp_tokens = curve.calc_token_amount(pool_name, amounts, True)

    if min_mint_amount is None:
        min_mint_amount = expected_lp_tokens * 0.995  # 0.5% slippage

    print(f"Adding liquidity to {pool_name}:")
    print(f"  Amounts: {amounts}")
    print(f"  Expected LP tokens: {expected_lp_tokens:.6f}")
    print(f"  Minimum LP tokens: {min_mint_amount:.6f}")

    # Add liquidity
    tx_hash = curve.add_liquidity(
        pool_name=pool_name,
        amounts=amounts,
        min_mint_amount=min_mint_amount
    )

    print(f"Liquidity added: {tx_hash}")

    # Auto-stake in gauge if enabled
    if curve_config['gauge_staking']:
        stake_tx = curve.stake_in_gauge(pool_name, expected_lp_tokens)
        print(f"Staked in gauge: {stake_tx}")

    return tx_hash

# Example: Add balanced liquidity to 3pool
add_liquidity_tx = add_liquidity_to_pool('3pool', [1000, 1000, 1000])
```

### Yield Farming & Rewards

```python
# Comprehensive yield farming strategy
def curve_yield_farming():
    """
    Automated yield farming across Curve pools
    """
    # Get pool APYs
    pools_with_apy = curve.get_pools_by_apy()

    print("Top Yield Opportunities:")
    for pool in pools_with_apy[:5]:
        base_apy = pool['base_apy']
        crv_apy = pool['crv_apy']
        total_apy = base_apy + crv_apy

        print(f"{pool['name']}:")
        print(f"  Base APY: {base_apy:.2f}%")
        print(f"  CRV APY: {crv_apy:.2f}%")
        print(f"  Total APY: {total_apy:.2f}%")
        print(f"  Risk Level: {pool['risk_level']}")
        print()

    # Auto-select best pools based on risk-adjusted returns
    selected_pools = curve.select_optimal_pools(
        max_pools=3,
        min_apy=10,
        max_risk=5,
        diversification_factor=0.7
    )

    return selected_pools

# Get CRV rewards and compound
def manage_crv_rewards():
    """
    Claim and compound CRV rewards
    """
    # Check claimable rewards
    claimable = curve.get_claimable_rewards()

    total_claimable_usd = 0
    for token, amount in claimable.items():
        usd_value = curve.get_token_usd_price(token) * amount
        total_claimable_usd += usd_value
        print(f"Claimable {token}: {amount:.6f} (${usd_value:.2f})")

    # Claim if worthwhile (considering gas costs)
    if total_claimable_usd > 50:  # $50 minimum
        claim_tx = curve.claim_all_rewards()
        print(f"Claimed rewards: {claim_tx}")

        # Auto-compound if enabled
        if curve_config['auto_compound']:
            compound_tx = curve.compound_rewards()
            print(f"Compounded rewards: {compound_tx}")
    else:
        print("Rewards too small to claim (gas costs)")
```

## veCRV & Boost Optimization

### Vote-Escrowed CRV

```python
# Optimize veCRV holdings for maximum boost
def optimize_vecrv_boost():
    """
    Manage veCRV position for optimal boost across pools
    """
    current_vecrv = curve.get_vecrv_balance()
    current_boost = curve.get_current_boost()

    print(f"Current veCRV: {current_vecrv:.2f}")
    print(f"Current boost: {current_boost:.2f}x")

    # Calculate optimal CRV lock amount
    positions = curve.get_lp_positions()
    optimal_crv = curve.calculate_optimal_crv_lock(positions)

    print(f"Optimal CRV to lock: {optimal_crv:.2f}")

    if optimal_crv > 0:
        # Lock CRV for veCRV
        lock_time = 4 * 365 * 24 * 3600  # 4 years max lock
        lock_tx = curve.create_lock(optimal_crv, lock_time)
        print(f"Locked CRV: {lock_tx}")

    return optimal_crv

# Vote on gauge weights
def vote_on_gauges():
    """
    Vote on gauge weights to maximize returns
    """
    voting_power = curve.get_voting_power()

    if voting_power > 0:
        # Get recommended gauge votes
        recommendations = curve.get_gauge_vote_recommendations()

        # Execute votes
        for gauge, weight in recommendations.items():
            vote_tx = curve.vote_for_gauge(gauge, weight)
            print(f"Voted {weight}% for {gauge}: {vote_tx}")
```

## Cross-Chain Strategies

### Multi-Chain Arbitrage

```python
# Cross-chain arbitrage opportunities
def cross_chain_arbitrage():
    """
    Find and execute arbitrage across Curve deployments
    """
    chains = ['ethereum', 'polygon', 'arbitrum', 'optimism']

    arbitrage_opportunities = []

    for chain1 in chains:
        for chain2 in chains:
            if chain1 != chain2:
                # Compare prices for same assets
                price_diff = curve.compare_cross_chain_prices(
                    'USDC', chain1, chain2
                )

                if abs(price_diff) > 0.002:  # 0.2% minimum
                    arbitrage_opportunities.append({
                        'asset': 'USDC',
                        'buy_chain': chain2 if price_diff > 0 else chain1,
                        'sell_chain': chain1 if price_diff > 0 else chain2,
                        'profit_percentage': abs(price_diff),
                        'estimated_profit': abs(price_diff) * 10000  # For $10K trade
                    })

    # Sort by profitability
    arbitrage_opportunities.sort(key=lambda x: x['profit_percentage'], reverse=True)

    return arbitrage_opportunities[:5]  # Top 5 opportunities
```

## Risk Management

### Pool Risk Assessment

```python
# Comprehensive risk management for Curve positions
def assess_pool_risks(pool_name):
    """
    Analyze risks for a specific Curve pool
    """
    pool_info = curve.get_pool_info(pool_name)

    risks = {
        'smart_contract_risk': curve.assess_contract_risk(pool_name),
        'liquidity_risk': pool_info['tvl'] < 10000000,  # < $10M TVL
        'impermanent_loss_risk': curve.calculate_il_risk(pool_name),
        'depeg_risk': curve.assess_depeg_risk(pool_name),
        'admin_risk': curve.get_admin_risk_score(pool_name)
    }

    # Calculate overall risk score
    risk_weights = {
        'smart_contract_risk': 0.3,
        'liquidity_risk': 0.2,
        'impermanent_loss_risk': 0.2,
        'depeg_risk': 0.2,
        'admin_risk': 0.1
    }

    overall_risk = sum(
        risks[risk] * weight
        for risk, weight in risk_weights.items()
    )

    return {
        'risks': risks,
        'overall_score': overall_risk,
        'risk_level': 'Low' if overall_risk < 0.3 else 'Medium' if overall_risk < 0.6 else 'High'
    }

# Position size management
def calculate_position_size(pool_name, portfolio_value):
    """
    Calculate appropriate position size based on risk
    """
    risk_assessment = assess_pool_risks(pool_name)

    # Risk-based position sizing
    risk_multipliers = {
        'Low': 0.15,     # Max 15% for low risk
        'Medium': 0.10,  # Max 10% for medium risk
        'High': 0.05     # Max 5% for high risk
    }

    max_position = portfolio_value * risk_multipliers[risk_assessment['risk_level']]

    return {
        'max_position_usd': max_position,
        'risk_level': risk_assessment['risk_level'],
        'recommended_allocation': max_position
    }
```

## Integration Examples

### Complete DeFi Strategy

```python
import os
from pt_exchanges import CurveExchange

# Initialize Curve integration
curve = CurveExchange({
    'wallet_address': os.getenv('CURVE_WALLET_ADDRESS'),
    'private_key': os.getenv('CURVE_PRIVATE_KEY'),
    'infura_key': os.getenv('CURVE_INFURA_KEY')
})

# Automated Curve strategy
def automated_curve_strategy():
    print("🌀 Curve Finance Automated Strategy")
    print("=" * 40)

    # 1. Assess current portfolio
    portfolio = curve.get_portfolio_overview()
    print(f"Portfolio Value: ${portfolio['total_usd']:,.2f}")
    print(f"LP Positions: {len(portfolio['positions'])}")
    print(f"Claimable Rewards: ${portfolio['claimable_usd']:.2f}")

    # 2. Claim rewards if worthwhile
    if portfolio['claimable_usd'] > 50:
        curve.claim_all_rewards()
        curve.compound_rewards()
        print("✅ Rewards claimed and compounded")

    # 3. Rebalance positions
    optimal_allocation = curve.get_optimal_allocation(
        portfolio['total_usd'],
        target_apy=15,
        max_risk=6
    )

    print("\nOptimal Allocation:")
    for pool, allocation in optimal_allocation.items():
        print(f"  {pool}: ${allocation['amount']:,.0f} ({allocation['percentage']:.1f}%)")

    # 4. Execute rebalancing
    rebalance_trades = curve.generate_rebalancing_trades(
        current_positions=portfolio['positions'],
        target_allocation=optimal_allocation
    )

    for trade in rebalance_trades:
        if trade['action'] == 'add_liquidity':
            curve.add_liquidity(trade['pool'], trade['amounts'])
        elif trade['action'] == 'remove_liquidity':
            curve.remove_liquidity(trade['pool'], trade['lp_amount'])
        elif trade['action'] == 'swap':
            curve.swap(trade['from_token'], trade['to_token'], trade['amount'])

        print(f"✅ Executed: {trade['action']} on {trade['pool']}")

    # 5. Update veCRV position if needed
    if curve.should_update_vecrv():
        optimal_crv = curve.calculate_optimal_crv_lock()
        if optimal_crv > 0:
            curve.create_lock(optimal_crv, 4 * 365 * 24 * 3600)
            print("✅ Updated veCRV position")

    print("\n🎯 Strategy execution completed!")

# Run the strategy
automated_curve_strategy()
```

This completes the Curve Finance integration setup. The protocol's focus on efficient stablecoin trading and high-yield opportunities provides excellent DeFi integration for PowerTraderAI+'s multi-exchange framework.
