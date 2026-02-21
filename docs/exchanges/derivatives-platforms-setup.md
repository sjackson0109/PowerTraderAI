# DeFi Derivatives Platforms Integration Guide

## Overview
This guide covers integration with advanced DeFi derivatives trading platforms including options, perpetuals, and structured products. These platforms enable sophisticated trading strategies with on-chain settlement and automated execution.

## Supported Derivatives Platforms

### ⚡ **Lyra Finance (Options)**
- **Network**: Optimism, Arbitrum
- **TVL**: $150M+ in options liquidity
- **Features**: Automated market maker for options, dynamic pricing, Greeks management
- **Specialty**: Next-generation options trading with optimized pricing models

### ⚡ **Dopex (Options)**
- **Network**: Arbitrum, Ethereum
- **TVL**: $80M+ across options vaults
- **Features**: Single staking options vaults (SSOVs), Atlantic options
- **Specialty**: Decentralized options trading with innovative vault structures

### ⚡ **GMX (Perpetuals)**
- **Network**: Arbitrum, Avalanche
- **TVL**: $600M+ in GLP pools
- **Features**: Perpetual swaps, up to 50x leverage, zero-slippage trades
- **Specialty**: Multi-asset pool model for leveraged trading

### ⚡ **PerpProtocol (Perpetuals)**
- **Network**: Optimism, previously Arbitrum
- **TVL**: $200M+ in vAMM
- **Features**: Virtual AMM, funding rates, insurance fund
- **Specialty**: Virtual automated market maker for perpetual contracts

### ⚡ **Gains Network (Leveraged Trading)**
- **Network**: Polygon, Arbitrum
- **TVL**: $100M+ in collateral
- **Features**: Synthetic leveraged trading, crypto/forex/stocks
- **Specialty**: Decentralized leveraged trading across multiple asset classes

## Prerequisites
- Layer 2 network setup (Optimism, Arbitrum, Polygon)
- Understanding of derivatives trading and risk management
- Sufficient collateral for margin requirements
- Knowledge of Greeks for options trading
- Advanced risk management protocols

## **Access & Verification Requirements**

### **Centralized Derivatives Platforms**

#### **Deribit (Professional Options/Futures)**
- **KYC Level 1**: Email + Phone | €2,000 daily withdrawal
- **KYC Level 2**: Government ID + Address proof | €100,000 daily
- **KYC Level 3**: Source of funds verification | Unlimited
- **Geographic**: Global except US, Canada, restricted jurisdictions
- **Professional**: Enhanced suitability assessment required
- **Compliance**: EU MiFID II, Dutch AFM regulated

### **Decentralized Derivatives Protocols**

#### **Lyra Finance (Options)**
- **Access**: Permissionless, wallet connection only
- **KYC**: None required
- **Geographic**: Protocol unrestricted, frontend may block jurisdictions
- **Network**: Optimism mainnet
- **Minimum**: Gas fees + option premiums only

#### **GMX (Perpetuals)**
- **Verification**: None - instant wallet access
- **Geographic**: Unrestricted at protocol level
- **Frontend Restrictions**: May block US, sanctioned countries
- **Alternative Access**: Multiple interfaces, IPFS deployment
- **Networks**: Arbitrum, Avalanche

#### **PerpProtocol (Perpetuals)**
- **Access Type**: Decentralized, no registration
- **Verification**: Wallet connection only
- **Trading Limits**: Based on available liquidity
- **Network**: Optimism
- **Compliance**: No protocol-level geographic restrictions

### **Regulatory Framework by Region**

#### **United States**
- **Offshore Platforms**: Most restricted for US residents
- **DeFi Access**: Technically available but regulatory uncertainty
- **CFTC Oversight**: Derivatives trading regulation
- **Accredited Investor**: May provide exemptions for professional trading

#### **European Union**
- **MiFID II**: Professional vs retail classification
- **Leverage Limits**: 30:1 maximum for retail accounts
- **Risk Protection**: Negative balance protection mandatory
- **Professional**: Higher leverage, reduced regulatory protection

#### **Professional Requirements**
- **Capital**: €500,000+ investable assets
- **Experience**: 1+ year derivatives trading history
- **Assessment**: Risk suitability questionnaire
- **Verification**: Source of wealth declaration

## Technical Setup

### 1. Lyra Finance Integration

```python
from pt_exchanges import LyraFinanceExchange
import web3
from web3 import Web3
import json
import time
from datetime import datetime, timedelta
import numpy as np

# Lyra Protocol Configuration
LYRA_CONFIG = {
    'optimism_rpc': 'https://mainnet.optimism.io',
    'arbitrum_rpc': 'https://arb1.arbitrum.io/rpc',

    # Optimism contracts
    'lyra_registry': '0x35bC24Be34f10f97a8F065F95fCBF7B9a9E307C7',
    'option_market_wrapper': '0x8A5D7e91a36F5b5Fe89c8B50C2e8CC5C5d618b35',
    'short_collateral': '0x27b4615CC27Ff9e38eFcfA54B0A5CaBeBE4Aa3B5',
    'option_token': '0x8e9E4e2e1eB4b0F3c5f5A0A5B5D5C5E5F5G5H5I5',

    # Available markets (ETH options on Optimism)
    'markets': {
        'sETH': {
            'market_address': '0x919E5e0C096002cb8a21397D724C4e3EbE77bC15',
            'base_asset': 'sETH',
            'quote_asset': 'sUSD',
            'strike_asset': 'sUSD'
        }
    }
}

class LyraFinanceExchange:
    def __init__(self, config):
        self.web3 = Web3(Web3.HTTPProvider(LYRA_CONFIG['optimism_rpc']))
        self.wallet_address = config['wallet_address']
        self.private_key = config['private_key']

        # Load ABIs
        self.option_market_abi = self.load_abi('lyra_option_market')
        self.option_token_abi = self.load_abi('lyra_option_token')
        self.wrapper_abi = self.load_abi('lyra_wrapper')

        # Initialize contracts
        self.registry = self.web3.eth.contract(
            address=LYRA_CONFIG['lyra_registry'],
            abi=self.load_abi('lyra_registry')
        )

        self.wrapper = self.web3.eth.contract(
            address=LYRA_CONFIG['option_market_wrapper'],
            abi=self.wrapper_abi
        )

        # Get market contracts
        self.markets = {}
        for market_name, config in LYRA_CONFIG['markets'].items():
            self.markets[market_name] = self.web3.eth.contract(
                address=config['market_address'],
                abi=self.option_market_abi
            )

    def get_live_boards(self, market='sETH'):
        """Get all live option boards (expiry dates) for a market"""
        market_contract = self.markets[market]

        live_boards = market_contract.functions.getLiveBoards().call()

        boards_info = []
        for board_id in live_boards:
            board = market_contract.functions.getBoard(board_id).call()

            boards_info.append({
                'board_id': board_id,
                'expiry': datetime.fromtimestamp(board[0]),  # expiry timestamp
                'base_iv': board[1] / 1e18,  # base implied volatility
                'strike_ids': board[2],  # list of strike IDs
                'frozen': board[3],  # is trading frozen
                'days_to_expiry': (datetime.fromtimestamp(board[0]) - datetime.now()).days
            })

        return boards_info

    def get_strikes_for_board(self, market='sETH', board_id=1):
        """Get all strikes for a specific board"""
        market_contract = self.markets[market]

        board = market_contract.functions.getBoard(board_id).call()
        strike_ids = board[2]

        strikes_info = []
        for strike_id in strike_ids:
            strike = market_contract.functions.getStrike(strike_id).call()

            strikes_info.append({
                'strike_id': strike_id,
                'strike_price': strike[0] / 1e18,  # Strike price in USD
                'skew': strike[1] / 1e18,  # IV skew
                'long_call': {
                    'price': strike[2][0] / 1e18,
                    'delta': strike[2][1] / 1e18,
                    'vega': strike[2][2] / 1e18
                },
                'short_call_base': {
                    'price': strike[3][0] / 1e18,
                    'delta': strike[3][1] / 1e18,
                    'vega': strike[3][2] / 1e18
                },
                'long_put': {
                    'price': strike[4][0] / 1e18,
                    'delta': strike[4][1] / 1e18,
                    'vega': strike[4][2] / 1e18
                },
                'short_put_quote': {
                    'price': strike[5][0] / 1e18,
                    'delta': strike[5][1] / 1e18,
                    'vega': strike[5][2] / 1e18
                }
            })

        return strikes_info

    def open_position(self, market='sETH', board_id=1, strike_id=1, option_type='LONG_CALL', amount=1.0, max_premium=None):
        """Open an options position on Lyra"""

        # Convert option type to Lyra enum
        option_type_mapping = {
            'LONG_CALL': 0,
            'SHORT_CALL_BASE': 1,
            'SHORT_CALL_QUOTE': 2,
            'LONG_PUT': 3,
            'SHORT_PUT_QUOTE': 4,
            'SHORT_PUT_BASE': 5
        }

        position_type = option_type_mapping[option_type]

        # Get quote for the trade
        quote = self.get_quote(market, board_id, strike_id, option_type, amount)

        if max_premium and quote['total_premium'] > max_premium:
            raise ValueError(f"Premium {quote['total_premium']} exceeds maximum {max_premium}")

        # Prepare trade parameters
        trade_params = {
            'strikeId': strike_id,
            'positionId': 0,  # 0 for new position
            'amount': int(amount * 1e18),
            'setCollateralTo': 0,  # For long positions
            'iterations': 3,  # Greeks calculation iterations
            'minTotalCost': 0,  # Minimum cost (for shorts)
            'maxTotalCost': int(quote['total_premium'] * 1.05 * 1e18),  # 5% slippage
            'optionType': position_type,
            'referrer': '0x0000000000000000000000000000000000000000'
        }

        # Execute trade through wrapper
        transaction = self.wrapper.functions.openPosition(trade_params).build_transaction({
            'from': self.wallet_address,
            'gas': 500000,
            'gasPrice': self.web3.eth.gas_price,
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address),
            'value': int(quote['total_premium'] * 1e18) if option_type.startswith('LONG') else 0
        })

        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"Lyra position opened: {tx_hash.hex()}")

        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        return self.parse_position_result(receipt)

    def get_quote(self, market, board_id, strike_id, option_type, amount):
        """Get a detailed quote for an options trade"""
        market_contract = self.markets[market]

        # Get current spot price and strike info
        spot_price = market_contract.functions.getSpotPrice().call() / 1e18
        strike_info = market_contract.functions.getStrike(strike_id).call()
        strike_price = strike_info[0] / 1e18

        # Calculate basic metrics
        days_to_expiry = self.get_days_to_expiry(board_id)
        moneyness = spot_price / strike_price

        option_type_mapping = {
            'LONG_CALL': 0, 'SHORT_CALL_BASE': 1, 'LONG_PUT': 3, 'SHORT_PUT_QUOTE': 4
        }

        # Get quote from contract
        quote_result = market_contract.functions.getOptionQuote(
            strike_id,
            option_type_mapping[option_type],
            int(amount * 1e18)
        ).call()

        return {
            'strike_price': strike_price,
            'spot_price': spot_price,
            'moneyness': moneyness,
            'days_to_expiry': days_to_expiry,
            'premium_per_option': quote_result[0] / 1e18,
            'total_premium': quote_result[0] * amount / 1e18,
            'delta': quote_result[1] / 1e18,
            'vega': quote_result[2] / 1e18,
            'theta': quote_result[3] / 1e18,
            'gamma': quote_result[4] / 1e18,
            'implied_volatility': quote_result[5] / 1e18,
            'break_even_price': self.calculate_break_even(strike_price, quote_result[0] / 1e18, option_type)
        }

    def get_portfolio_greeks(self):
        """Get portfolio-level Greeks for all positions"""
        positions = self.get_active_positions()

        total_delta = 0
        total_gamma = 0
        total_vega = 0
        total_theta = 0
        total_rho = 0

        for position in positions:
            # Weight Greeks by position size
            size_multiplier = position['amount']

            total_delta += position['delta'] * size_multiplier
            total_gamma += position['gamma'] * size_multiplier
            total_vega += position['vega'] * size_multiplier
            total_theta += position['theta'] * size_multiplier
            total_rho += position.get('rho', 0) * size_multiplier

        return {
            'portfolio_delta': total_delta,
            'portfolio_gamma': total_gamma,
            'portfolio_vega': total_vega,
            'portfolio_theta': total_theta,
            'portfolio_rho': total_rho,
            'position_count': len(positions),
            'risk_metrics': self.calculate_portfolio_risk_metrics(positions)
        }

    def delta_hedge_portfolio(self, target_delta=0.0):
        """Automatically delta hedge the portfolio"""
        portfolio_greeks = self.get_portfolio_greeks()
        current_delta = portfolio_greeks['portfolio_delta']

        delta_adjustment_needed = target_delta - current_delta

        print(f"Current Portfolio Delta: {current_delta:.4f}")
        print(f"Target Delta: {target_delta:.4f}")
        print(f"Adjustment Needed: {delta_adjustment_needed:.4f}")

        if abs(delta_adjustment_needed) > 0.05:  # Only hedge if delta > 0.05
            # Calculate ETH amount needed for hedge
            eth_amount = abs(delta_adjustment_needed)  # Simplified: 1 delta ≈ 1 ETH

            if delta_adjustment_needed > 0:
                # Need to buy ETH to increase delta
                print(f"Buying {eth_amount:.4f} ETH to increase delta")
                hedge_tx = self.buy_eth_for_hedge(eth_amount)
            else:
                # Need to sell ETH to decrease delta
                print(f"Selling {eth_amount:.4f} ETH to decrease delta")
                hedge_tx = self.sell_eth_for_hedge(eth_amount)

            return hedge_tx
        else:
            print("Portfolio delta within acceptable range, no hedging needed")
            return None

# Initialize Lyra Finance
lyra = LyraFinanceExchange({
    'wallet_address': 'your_wallet_address',
    'private_key': 'your_private_key'
})
```

### 2. GMX Integration

```python
# GMX Protocol Configuration
GMX_CONFIG = {
    'arbitrum_rpc': 'https://arb1.arbitrum.io/rpc',
    'avalanche_rpc': 'https://api.avax.network/ext/bc/C/rpc',

    # Arbitrum contracts
    'vault': '0x489ee077994B6658eAfA855C308275EAd8097C4A',
    'router': '0xaBBc5F99639c9B6bCb58544ddf04EFA6802F4064',
    'position_router': '0xb87a436B93fFE9D75c5cFA7bAcFff96430b09868',
    'reader': '0x22199a49A999c351eF7927602CFB187ec3cae489',
    'glp_manager': '0x3963FfC9dff443c2A94f21b129D429891E32ec18',
    'glp_token': '0x1aDDD80E6039594eE970E5872D247bf0414C8903',  # fsGLP

    # Supported tokens
    'tokens': {
        'ETH': '0x82aF49447D8a07e3bd95BD0d56f35241523fBab1',
        'BTC': '0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f',
        'USDC': '0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8',
        'USDT': '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9',
        'DAI': '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1'
    }
}

class GMXExchange:
    def __init__(self, config):
        self.web3 = Web3(Web3.HTTPProvider(GMX_CONFIG['arbitrum_rpc']))
        self.wallet_address = config['wallet_address']
        self.private_key = config['private_key']

        # Load contracts
        self.vault = self.web3.eth.contract(
            address=GMX_CONFIG['vault'],
            abi=self.load_abi('gmx_vault')
        )

        self.router = self.web3.eth.contract(
            address=GMX_CONFIG['router'],
            abi=self.load_abi('gmx_router')
        )

        self.position_router = self.web3.eth.contract(
            address=GMX_CONFIG['position_router'],
            abi=self.load_abi('gmx_position_router')
        )

        self.reader = self.web3.eth.contract(
            address=GMX_CONFIG['reader'],
            abi=self.load_abi('gmx_reader')
        )

        self.glp_manager = self.web3.eth.contract(
            address=GMX_CONFIG['glp_manager'],
            abi=self.load_abi('gmx_glp_manager')
        )

    def get_position_info(self, account, collateral_token, index_token, is_long):
        """Get detailed information about a position"""
        position = self.vault.functions.getPosition(
            account,
            collateral_token,
            index_token,
            is_long
        ).call()

        if position[0] == 0:  # No position
            return None

        # Calculate position metrics
        size_usd = position[0] / 1e30  # Position size in USD
        collateral_usd = position[1] / 1e30  # Collateral in USD
        avg_price = position[2] / 1e30  # Average entry price
        entry_funding_rate = position[3] / 1e30
        reserve_amount = position[4] / 1e18
        realized_pnl = position[5] / 1e30
        last_increased_time = position[6]

        # Get current price for P&L calculation
        current_price = self.vault.functions.getMaxPrice(index_token).call() / 1e30

        if is_long:
            pnl_usd = (current_price - avg_price) * (size_usd / avg_price)
        else:
            pnl_usd = (avg_price - current_price) * (size_usd / avg_price)

        leverage = size_usd / collateral_usd if collateral_usd > 0 else 0

        return {
            'size_usd': size_usd,
            'collateral_usd': collateral_usd,
            'avg_price': avg_price,
            'current_price': current_price,
            'pnl_usd': pnl_usd,
            'pnl_percentage': (pnl_usd / collateral_usd) * 100 if collateral_usd > 0 else 0,
            'leverage': leverage,
            'is_long': is_long,
            'liquidation_price': self.calculate_liquidation_price(position, is_long),
            'funding_fee': self.get_funding_fee(account, collateral_token, index_token, is_long)
        }

    def increase_position(self, path, index_token, amount_in, min_out, size_delta, is_long, price):
        """Increase a leveraged position"""
        # Approve token spending if not ETH
        if path[0] != '0x0000000000000000000000000000000000000000':  # Not ETH
            self.ensure_token_approval(path[0], amount_in, GMX_CONFIG['router'])

        # Calculate execution fee
        execution_fee = self.position_router.functions.minExecutionFee().call()

        # Create increase position request
        transaction = self.position_router.functions.createIncreasePosition(
            path,                    # path for token swap
            index_token,             # token to long/short
            amount_in,               # collateral amount
            min_out,                 # minimum tokens out from swap
            size_delta,              # USD size to increase position by
            is_long,                 # direction (long/short)
            price,                   # acceptable price
            execution_fee,           # execution fee
            '0x0000000000000000000000000000000000000000',  # referral code
            '0x0000000000000000000000000000000000000000'   # callback contract
        ).build_transaction({
            'from': self.wallet_address,
            'value': execution_fee + (amount_in if path[0] == '0x0000000000000000000000000000000000000000' else 0),
            'gas': 2000000,
            'gasPrice': self.web3.eth.gas_price,
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        })

        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"GMX position increase request: {tx_hash.hex()}")

        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    def decrease_position(self, collateral_token, index_token, collateral_delta, size_delta, is_long, receiver, price):
        """Decrease or close a leveraged position"""
        execution_fee = self.position_router.functions.minExecutionFee().call()

        transaction = self.position_router.functions.createDecreasePosition(
            [collateral_token],      # path (single token for decrease)
            index_token,             # index token
            collateral_delta,        # collateral to withdraw
            size_delta,              # size to decrease
            is_long,                 # direction
            receiver,                # receiver of withdrawn collateral
            price,                   # acceptable price
            0,                       # min out (for decrease)
            execution_fee,           # execution fee
            False,                   # withdraw ETH
            '0x0000000000000000000000000000000000000000'  # callback
        ).build_transaction({
            'from': self.wallet_address,
            'value': execution_fee,
            'gas': 2000000,
            'gasPrice': self.web3.eth.gas_price,
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        })

        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"GMX position decrease request: {tx_hash.hex()}")

        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    def buy_glp(self, token, amount, min_usdg_out, min_glp_out):
        """Buy GLP with tokens to earn fees from trading activity"""
        # Approve token spending
        self.ensure_token_approval(token, amount, GMX_CONFIG['glp_manager'])

        # Buy GLP
        transaction = self.glp_manager.functions.addLiquidity(
            token,           # token to deposit
            amount,          # amount of tokens
            min_usdg_out,    # minimum USDG out
            min_glp_out      # minimum GLP out
        ).build_transaction({
            'from': self.wallet_address,
            'gas': 500000,
            'gasPrice': self.web3.eth.gas_price,
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        })

        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"GLP purchased: {tx_hash.hex()}")

        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    def get_glp_analytics(self):
        """Get comprehensive GLP analytics"""
        total_supply = self.glp_manager.functions.glp().call()
        aum = self.glp_manager.functions.getAum(True).call()  # Assets under management

        # Get individual token weights and utilization
        vault_info = {}
        total_weight = 0

        for token_name, token_address in GMX_CONFIG['tokens'].items():
            token_weight = self.vault.functions.tokenWeights(token_address).call()
            pool_amount = self.vault.functions.poolAmounts(token_address).call()
            reserved_amount = self.vault.functions.reservedAmounts(token_address).call()

            utilization = (reserved_amount / pool_amount) if pool_amount > 0 else 0

            vault_info[token_name] = {
                'weight': token_weight / 1e4,  # Convert to percentage
                'pool_amount': pool_amount,
                'reserved_amount': reserved_amount,
                'utilization': utilization * 100,
                'target_weight': token_weight / 1e4
            }

            total_weight += token_weight

        # Calculate GLP metrics
        glp_price = aum / total_supply if total_supply > 0 else 0

        return {
            'glp_price': glp_price / 1e30,
            'total_supply': total_supply / 1e18,
            'aum_usd': aum / 1e30,
            'vault_composition': vault_info,
            'avg_utilization': np.mean([v['utilization'] for v in vault_info.values()]),
            'fee_basis_points': self.vault.functions.mintBurnFeeBasisPoints().call(),
            'tax_basis_points': self.vault.functions.taxBasisPoints().call()
        }

# Initialize GMX
gmx = GMXExchange({
    'wallet_address': 'your_wallet_address',
    'private_key': 'your_private_key'
})
```

## Advanced Derivatives Strategies

### 1. Options Strategy: Covered Call
```python
def covered_call_strategy():
    """
    Implement covered call strategy on Lyra Finance
    """
    print("🎯 Covered Call Strategy on Lyra Finance")
    print("=" * 40)

    # Step 1: Ensure we hold underlying ETH
    eth_balance = lyra.web3.eth.get_balance(lyra.wallet_address) / 1e18

    if eth_balance < 1.0:  # Need at least 1 ETH for covered call
        print("❌ Insufficient ETH balance for covered call")
        return None

    # Step 2: Get current ETH price and available options
    live_boards = lyra.get_live_boards('sETH')

    # Find board with 2-4 weeks to expiry
    target_board = None
    for board in live_boards:
        if 14 <= board['days_to_expiry'] <= 28:
            target_board = board
            break

    if not target_board:
        print("❌ No suitable expiry found")
        return None

    print(f"Selected expiry: {target_board['expiry']} ({target_board['days_to_expiry']} days)")

    # Step 3: Get strikes for the board
    strikes = lyra.get_strikes_for_board('sETH', target_board['board_id'])

    # Find optimal strike (slightly out of the money)
    current_price = strikes[0]['strike_price'] if strikes else 2000  # Fallback price

    optimal_strike = None
    for strike in strikes:
        # Look for strike 5-10% above current price
        if 1.05 <= strike['strike_price'] / current_price <= 1.10:
            optimal_strike = strike
            break

    if not optimal_strike:
        # Fallback to closest OTM strike
        otm_strikes = [s for s in strikes if s['strike_price'] > current_price]
        optimal_strike = min(otm_strikes, key=lambda x: x['strike_price']) if otm_strikes else strikes[0]

    print(f"Selected strike: ${optimal_strike['strike_price']:,.2f}")
    print(f"Call premium: ${optimal_strike['short_call_base']['price']:.4f} ETH")

    # Step 4: Sell call option
    try:
        position_tx = lyra.open_position(
            market='sETH',
            board_id=target_board['board_id'],
            strike_id=optimal_strike['strike_id'],
            option_type='SHORT_CALL_BASE',
            amount=1.0,  # 1 ETH worth of options
            max_premium=None
        )

        print(f"✅ Covered call position opened: {position_tx}")

        # Step 5: Set up monitoring
        monitor_covered_call_position(target_board['board_id'], optimal_strike['strike_id'])

        return position_tx

    except Exception as e:
        print(f"❌ Error opening covered call: {e}")
        return None

def monitor_covered_call_position(board_id, strike_id):
    """Monitor covered call position and manage risk"""
    print("🔍 Monitoring covered call position...")

    while True:
        # Get current position status
        try:
            current_quote = lyra.get_quote('sETH', board_id, strike_id, 'SHORT_CALL_BASE', 1.0)

            # Check if we should close early
            profit_target = 0.5  # 50% profit target
            loss_limit = 2.0     # 200% loss limit (premium received)

            current_cost_to_close = current_quote['total_premium']

            # Assuming we received premium when opening (would track this in real implementation)
            original_premium = 0.05  # Example: received 0.05 ETH

            if current_cost_to_close <= original_premium * profit_target:
                print(f"🎯 Profit target reached! Closing position...")
                close_covered_call_position(board_id, strike_id)
                break
            elif current_cost_to_close >= original_premium * loss_limit:
                print(f"⚠️ Loss limit reached! Closing position...")
                close_covered_call_position(board_id, strike_id)
                break

            # Check days to expiry
            if current_quote['days_to_expiry'] <= 3:
                print(f"📅 Close to expiry ({current_quote['days_to_expiry']} days). Consider closing...")

                # If deep ITM near expiry, close to avoid assignment
                if current_quote['moneyness'] > 1.05:  # 5% ITM
                    print(f"💰 Option is deep ITM, closing to avoid assignment...")
                    close_covered_call_position(board_id, strike_id)
                    break

            # Wait before next check
            time.sleep(3600)  # Check every hour

        except Exception as e:
            print(f"Error monitoring position: {e}")
            time.sleep(1800)  # Wait 30 minutes before retry

def close_covered_call_position(board_id, strike_id):
    """Close the covered call position"""
    try:
        close_tx = lyra.open_position(
            market='sETH',
            board_id=board_id,
            strike_id=strike_id,
            option_type='LONG_CALL',  # Buy back the call
            amount=1.0
        )

        print(f"✅ Covered call position closed: {close_tx}")
        return close_tx
    except Exception as e:
        print(f"❌ Error closing position: {e}")
        return None
```

### 2. Perpetual Strategy: Trend Following
```python
def trend_following_strategy():
    """
    Implement trend following strategy on GMX
    """
    print("📈 Trend Following Strategy on GMX")
    print("=" * 30)

    # Step 1: Analyze trend using multiple timeframes
    token = 'ETH'
    token_address = GMX_CONFIG['tokens'][token]

    # Get current price
    current_price = gmx.vault.functions.getMaxPrice(token_address).call() / 1e30

    # Get price history (simplified - would use external oracle/API)
    price_history = get_price_history(token, days=30)  # 30 days of data

    # Calculate technical indicators
    sma_20 = np.mean(price_history[-20:])  # 20-day moving average
    sma_50 = np.mean(price_history[-50:]) if len(price_history) >= 50 else sma_20

    # Calculate RSI
    rsi = calculate_rsi(price_history, 14)

    # Determine trend direction
    trend_direction = None
    trend_strength = 0

    if current_price > sma_20 > sma_50 and rsi < 70:
        trend_direction = 'BULLISH'
        trend_strength = min((current_price - sma_20) / sma_20 * 10, 5)  # Max 5
    elif current_price < sma_20 < sma_50 and rsi > 30:
        trend_direction = 'BEARISH'
        trend_strength = min((sma_20 - current_price) / sma_20 * 10, 5)  # Max 5

    print(f"Current Price: ${current_price:,.2f}")
    print(f"SMA 20: ${sma_20:,.2f}")
    print(f"SMA 50: ${sma_50:,.2f}")
    print(f"RSI: {rsi:.2f}")
    print(f"Trend: {trend_direction or 'NEUTRAL'}")
    print(f"Strength: {trend_strength:.2f}/5")

    if trend_direction and trend_strength >= 2:
        # Execute trend following trade
        execute_trend_trade(token, trend_direction, trend_strength, current_price)
    else:
        print("No clear trend detected, staying out of market")

def execute_trend_trade(token, direction, strength, entry_price):
    """Execute trend following trade on GMX"""
    token_address = GMX_CONFIG['tokens'][token]
    usdc_address = GMX_CONFIG['tokens']['USDC']

    # Calculate position size based on trend strength
    base_collateral = 1000  # $1000 base collateral
    collateral_usd = base_collateral * min(strength, 3)  # Max 3x for safety

    # Calculate leverage based on trend strength
    leverage = min(2 + strength, 8)  # Max 8x leverage

    position_size_usd = collateral_usd * leverage

    print(f"Opening {direction} position:")
    print(f"  Collateral: ${collateral_usd:,.2f}")
    print(f"  Leverage: {leverage:.1f}x")
    print(f"  Position Size: ${position_size_usd:,.2f}")

    # Prepare trade parameters
    is_long = direction == 'BULLISH'

    # Set acceptable price (2% slippage)
    if is_long:
        acceptable_price = int(entry_price * 1.02 * 1e30)
    else:
        acceptable_price = int(entry_price * 0.98 * 1e30)

    try:
        # Open position
        increase_tx = gmx.increase_position(
            path=[usdc_address],  # Using USDC as collateral
            index_token=token_address,
            amount_in=int(collateral_usd * 1e6),  # USDC has 6 decimals
            min_out=0,
            size_delta=int(position_size_usd * 1e30),
            is_long=is_long,
            price=acceptable_price
        )

        print(f"✅ Trend following position opened: {increase_tx}")

        # Set up position monitoring
        monitor_trend_position(token_address, usdc_address, is_long, entry_price, strength)

        return increase_tx

    except Exception as e:
        print(f"❌ Error opening position: {e}")
        return None

def monitor_trend_position(index_token, collateral_token, is_long, entry_price, trend_strength):
    """Monitor trend following position"""
    print("🔍 Monitoring trend following position...")

    while True:
        try:
            # Get current position
            position = gmx.get_position_info(
                gmx.wallet_address,
                collateral_token,
                index_token,
                is_long
            )

            if not position:
                print("Position closed or not found")
                break

            current_price = position['current_price']
            pnl_percentage = position['pnl_percentage']

            print(f"Position P&L: {pnl_percentage:.2f}%")
            print(f"Current Price: ${current_price:,.2f}")
            print(f"Entry Price: ${entry_price:,.2f}")

            # Risk management rules

            # 1. Profit taking based on trend strength
            profit_targets = {
                2: 15,  # 15% profit for weak trend
                3: 25,  # 25% profit for medium trend
                4: 40,  # 40% profit for strong trend
                5: 60   # 60% profit for very strong trend
            }

            profit_target = profit_targets.get(int(trend_strength), 20)

            if pnl_percentage >= profit_target:
                print(f"🎯 Profit target ({profit_target}%) reached!")
                close_trend_position(collateral_token, index_token, position, is_long)
                break

            # 2. Stop loss
            stop_loss = -10  # 10% stop loss
            if pnl_percentage <= stop_loss:
                print(f"🛑 Stop loss ({stop_loss}%) triggered!")
                close_trend_position(collateral_token, index_token, position, is_long)
                break

            # 3. Trend reversal check
            if check_trend_reversal(index_token, entry_price, is_long):
                print(f"REVERSAL: Trend reversal detected, closing position")
                close_trend_position(collateral_token, index_token, position, is_long)
                break

            # 4. Liquidation risk check
            if position['leverage'] > 15:  # High leverage warning
                print(f"⚠️ High leverage detected: {position['leverage']:.1f}x")

            liquidation_distance = abs(current_price - position['liquidation_price']) / current_price
            if liquidation_distance < 0.05:  # Within 5% of liquidation
                print(f"🚨 Near liquidation! Distance: {liquidation_distance:.2%}")
                # Reduce position size
                reduce_position_size(collateral_token, index_token, position, is_long, 0.5)

            time.sleep(900)  # Check every 15 minutes

        except Exception as e:
            print(f"Error monitoring position: {e}")
            time.sleep(600)  # Wait 10 minutes before retry

def close_trend_position(collateral_token, index_token, position, is_long):
    """Close the entire trend following position"""
    try:
        # Close entire position
        close_tx = gmx.decrease_position(
            collateral_token=collateral_token,
            index_token=index_token,
            collateral_delta=int(position['collateral_usd'] * 1e30),  # Withdraw all collateral
            size_delta=int(position['size_usd'] * 1e30),  # Close entire position
            is_long=is_long,
            receiver=gmx.wallet_address,
            price=int(position['current_price'] * (0.95 if is_long else 1.05) * 1e30)  # 5% slippage
        )

        print(f"✅ Position closed: {close_tx}")
        return close_tx
    except Exception as e:
        print(f"❌ Error closing position: {e}")
        return None
```

### 3. Delta-Neutral Strategy
```python
def delta_neutral_yield_strategy():
    """
    Implement delta-neutral strategy combining options and perpetuals
    """
    print("Delta-Neutral Yield Strategy")
    print("=" * 30)

    # Step 1: Buy GLP for base yield
    glp_investment = 10000  # $10,000 in GLP

    glp_analytics = gmx.get_glp_analytics()
    current_glp_price = glp_analytics['glp_price']

    print(f"GLP Price: ${current_glp_price:.4f}")
    print(f"Investing ${glp_investment:,.2f} in GLP")

    # Buy GLP with USDC
    usdc_amount = int(glp_investment * 1e6)  # Convert to USDC amount
    min_glp_out = int((glp_investment / current_glp_price) * 0.98 * 1e18)  # 2% slippage

    glp_tx = gmx.buy_glp(
        token=GMX_CONFIG['tokens']['USDC'],
        amount=usdc_amount,
        min_usdg_out=int(glp_investment * 0.98 * 1e18),
        min_glp_out=min_glp_out
    )

    print(f"GLP purchased: {glp_tx}")

    # Step 2: Create delta hedge with options
    # Estimate GLP's ETH exposure (typically ~20-25%)
    glp_eth_exposure = glp_investment * 0.22  # 22% ETH exposure
    eth_price = gmx.vault.functions.getMaxPrice(GMX_CONFIG['tokens']['ETH']).call() / 1e30
    eth_amount_exposed = glp_eth_exposure / eth_price

    print(f"GLP ETH exposure: ${glp_eth_exposure:,.2f} (~{eth_amount_exposed:.4f} ETH)")

    # Buy put options to hedge ETH downside
    live_boards = lyra.get_live_boards('sETH')
    near_term_board = min(live_boards, key=lambda x: x['days_to_expiry'])

    strikes = lyra.get_strikes_for_board('sETH', near_term_board['board_id'])
    # Find ATM or slightly OTM puts
    atm_strike = min(strikes, key=lambda x: abs(x['strike_price'] - eth_price))

    put_position_tx = lyra.open_position(
        market='sETH',
        board_id=near_term_board['board_id'],
        strike_id=atm_strike['strike_id'],
        option_type='LONG_PUT',
        amount=eth_amount_exposed,
        max_premium=glp_eth_exposure * 0.05  # Max 5% of exposure as premium
    )

    print(f"✅ Put hedge position: {put_position_tx}")

    # Step 3: Monitor and rebalance
    monitor_delta_neutral_strategy(glp_investment, eth_amount_exposed, near_term_board['board_id'], atm_strike['strike_id'])

def monitor_delta_neutral_strategy(glp_investment, hedged_eth_amount, board_id, strike_id):
    """Monitor delta-neutral strategy performance"""
    print("🔍 Monitoring delta-neutral strategy...")

    initial_portfolio_value = glp_investment

    while True:
        try:
            # 1. Check GLP performance
            current_glp_analytics = gmx.get_glp_analytics()
            current_glp_price = current_glp_analytics['glp_price']

            glp_balance = gmx.glp_manager.functions.balanceOf(gmx.wallet_address).call() / 1e18
            current_glp_value = glp_balance * current_glp_price

            # 2. Check put option value
            current_put_quote = lyra.get_quote('sETH', board_id, strike_id, 'LONG_PUT', hedged_eth_amount)
            put_value = current_put_quote['total_premium'] * hedged_eth_amount

            # 3. Calculate total portfolio value
            total_portfolio_value = current_glp_value + put_value
            portfolio_return = (total_portfolio_value - initial_portfolio_value) / initial_portfolio_value

            print(f"\n📊 Delta-Neutral Strategy Performance:")
            print(f"  GLP Value: ${current_glp_value:,.2f}")
            print(f"  Put Value: ${put_value:,.2f}")
            print(f"  Total Value: ${total_portfolio_value:,.2f}")
            print(f"  Return: {portfolio_return:.2%}")

            # 4. Check if rebalancing is needed
            days_to_expiry = current_put_quote['days_to_expiry']

            if days_to_expiry <= 7:
                print("ROLLING: Options near expiry, rolling positions...")
                roll_put_positions(board_id, strike_id, hedged_eth_amount)

            # 5. Check GLP composition changes
            current_eth_exposure = current_glp_value * 0.22  # Estimate current ETH exposure
            exposure_drift = abs(current_eth_exposure - (hedged_eth_amount * current_put_quote['spot_price'])) / current_glp_value

            if exposure_drift > 0.05:  # 5% drift threshold
                print(f"🎯 Exposure drift detected: {exposure_drift:.2%}")
                rebalance_hedge(current_eth_exposure, hedged_eth_amount)

            time.sleep(21600)  # Check every 6 hours

        except Exception as e:
            print(f"Error monitoring strategy: {e}")
            time.sleep(3600)

def roll_put_positions(current_board_id, current_strike_id, eth_amount):
    """Roll expiring put positions to next expiry"""
    try:
        # Close current put position
        close_put_tx = lyra.open_position(
            market='sETH',
            board_id=current_board_id,
            strike_id=current_strike_id,
            option_type='SHORT_PUT_QUOTE',  # Sell back the put
            amount=eth_amount
        )

        print(f"✅ Current put closed: {close_put_tx}")

        # Open new put position in next expiry
        live_boards = lyra.get_live_boards('sETH')
        next_board = min([b for b in live_boards if b['days_to_expiry'] > 14], key=lambda x: x['days_to_expiry'])

        next_strikes = lyra.get_strikes_for_board('sETH', next_board['board_id'])
        current_eth_price = lyra.vault.functions.getMaxPrice(GMX_CONFIG['tokens']['ETH']).call() / 1e30
        next_atm_strike = min(next_strikes, key=lambda x: abs(x['strike_price'] - current_eth_price))

        new_put_tx = lyra.open_position(
            market='sETH',
            board_id=next_board['board_id'],
            strike_id=next_atm_strike['strike_id'],
            option_type='LONG_PUT',
            amount=eth_amount
        )

        print(f"✅ New put opened: {new_put_tx}")

        return next_board['board_id'], next_atm_strike['strike_id']

    except Exception as e:
        print(f"❌ Error rolling positions: {e}")
        return current_board_id, current_strike_id
```

## Environment Configuration

```bash
# Derivatives Trading Configuration
LYRA_OPTIMISM_RPC=https://mainnet.optimism.io
LYRA_ARBITRUM_RPC=https://arb1.arbitrum.io/rpc
LYRA_WALLET_ADDRESS=your_wallet_address
LYRA_PRIVATE_KEY=your_private_key

GMX_ARBITRUM_RPC=https://arb1.arbitrum.io/rpc
GMX_AVALANCHE_RPC=https://api.avax.network/ext/bc/C/rpc
GMX_WALLET_ADDRESS=your_wallet_address
GMX_PRIVATE_KEY=your_private_key

# Risk Management
DERIVATIVES_MAX_LEVERAGE=10.0
DERIVATIVES_MAX_POSITION_SIZE=50000
DERIVATIVES_STOP_LOSS_PERCENTAGE=10.0
DERIVATIVES_PROFIT_TARGET_PERCENTAGE=25.0
DERIVATIVES_AUTO_HEDGE_DELTA=0.1

# Strategy Parameters
OPTIONS_MIN_TIME_TO_EXPIRY=7
OPTIONS_MAX_IMPLIED_VOLATILITY=100
OPTIONS_PREFERRED_DELTA_RANGE=0.2,0.8
PERPETUALS_TREND_CONFIRMATION_PERIODS=3
PERPETUALS_MIN_TREND_STRENGTH=2.0
```

This comprehensive derivatives documentation provides full integration capabilities for major DeFi derivatives platforms with advanced strategies including options trading, perpetual contracts, and delta-neutral yield farming within PowerTraderAI+.
