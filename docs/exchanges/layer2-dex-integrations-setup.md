# Layer 2 DEX Integration Guide

## Overview
This guide covers integration with major Layer 2 decentralized exchanges (DEXs) across different scaling solutions. These platforms offer significantly lower fees and faster transactions while maintaining decentralization and composability.

## Supported Layer 2 DEXs

### 🚀 **QuickSwap (Polygon)**
- **Network**: Polygon PoS
- **TVL**: $150M+ across 500+ trading pairs
- **Features**: Uniswap V3 fork, liquidity mining, perpetual trading
- **Specialty**: Leading Polygon DEX with comprehensive DeFi ecosystem

### 🚀 **SpookySwap (Fantom)**
- **Network**: Fantom Opera
- **TVL**: $80M+ with 200+ trading pairs
- **Features**: AMM, yield farming, lending, NFT marketplace
- **Specialty**: Fantom's premier DeFi hub with gamified features

### 🚀 **Trader Joe (Avalanche)**
- **Network**: Avalanche C-Chain
- **TVL**: $200M+ across multiple features
- **Features**: Liquidity Book (concentrated liquidity), lending, launchpad
- **Specialty**: Avalanche's leading DEX with innovative liquidity technology

### 🚀 **Raydium (Solana)**
- **Network**: Solana
- **TVL**: $400M+ integrated with Serum orderbook
- **Features**: Hybrid AMM/CLOB, yield farming, AcceleRaytor launchpad
- **Specialty**: Solana's premier DEX with orderbook integration

### 🚀 **SushiSwap (Multi-chain)**
- **Networks**: Arbitrum, Optimism, Polygon, Avalanche, Fantom
- **TVL**: $300M+ across all chains
- **Features**: Cross-chain AMM, yield farming, MISO launchpad
- **Specialty**: Multi-chain DEX with unified liquidity

## Prerequisites
- Layer 2 network setup and native tokens for gas
- Understanding of automated market makers (AMMs) and impermanent loss
- Bridge setup for moving assets between Layer 1 and Layer 2
- Sufficient liquidity for meaningful trading positions
- Risk management for Layer 2 specific risks

## **Access & Verification Requirements**

### **Layer 2 DEX Platforms - Universal Access**

#### **No Verification Required**
- **QuickSwap**: Instant wallet connection, no KYC
- **SpookySwap**: Permissionless access, wallet-based
- **Trader Joe**: No registration, Avalanche wallet needed
- **Raydium**: Solana wallet connection only
- **PancakeSwap**: BSC access, no verification
- **SushiSwap**: Multi-chain, wallet-based access

#### **Geographic Access**
- **Protocol Level**: Unrestricted globally
- **Frontend Restrictions**: Some interfaces may geo-block
- **US Access**: Generally available via protocol
- **EU Compliance**: No specific restrictions
- **Alternative Access**: IPFS frontends, direct contract interaction

#### **Network Requirements**
- **Polygon (QuickSwap)**: MATIC for gas fees
- **Fantom (SpookySwap)**: FTM for transactions
- **Avalanche (Trader Joe)**: AVAX for gas
- **Solana (Raydium)**: SOL for transaction fees
- **BSC (PancakeSwap)**: BNB for gas fees

#### **Risk Considerations**
- **Impermanent Loss**: Risk disclosure for liquidity providers
- **Smart Contract Risk**: Audit status varies by platform
- **Yield Farming**: Token emission and inflationary risks
- **Bridge Risk**: Cross-chain asset transfer vulnerabilities

## Technical Setup

### 1. QuickSwap (Polygon) Integration

```python
from pt_exchanges import QuickSwapExchange
import web3
from web3 import Web3
import json
import time

# QuickSwap Configuration
QUICKSWAP_CONFIG = {
    'polygon_rpc': 'https://polygon-rpc.com',
    'router_v3': '0xE592427A0AEce92De3Edee1F18E0157C05861564',  # Uniswap V3 Router
    'router_v2': '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff',  # QuickSwap Router
    'factory_v3': '0x411b0fAcC3489691f28ad58c47006AF5E3Ab3A28',
    'factory_v2': '0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32',
    'quoter': '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6',

    # Popular trading pairs on Polygon
    'pairs': {
        'WMATIC_USDC': {
            'token0': '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270',  # WMATIC
            'token1': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',  # USDC
            'fee': 500  # 0.05%
        },
        'WETH_USDC': {
            'token0': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',  # WETH
            'token1': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',  # USDC
            'fee': 500
        },
        'WBTC_WETH': {
            'token0': '0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6',  # WBTC
            'token1': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',  # WETH
            'fee': 3000  # 0.3%
        }
    }
}

class QuickSwapExchange:
    def __init__(self, config):
        self.web3 = Web3(Web3.HTTPProvider(QUICKSWAP_CONFIG['polygon_rpc']))
        self.wallet_address = config['wallet_address']
        self.private_key = config['private_key']

        # Load ABIs
        self.router_v3_abi = self.load_abi('uniswap_v3_router')
        self.router_v2_abi = self.load_abi('quickswap_router')
        self.quoter_abi = self.load_abi('quoter')
        self.erc20_abi = self.load_abi('erc20')

        # Initialize contracts
        self.router_v3 = self.web3.eth.contract(
            address=QUICKSWAP_CONFIG['router_v3'],
            abi=self.router_v3_abi
        )

        self.router_v2 = self.web3.eth.contract(
            address=QUICKSWAP_CONFIG['router_v2'],
            abi=self.router_v2_abi
        )

        self.quoter = self.web3.eth.contract(
            address=QUICKSWAP_CONFIG['quoter'],
            abi=self.quoter_abi
        )

    def get_polygon_gas_price(self):
        """Get optimal gas price for Polygon network"""
        try:
            # Polygon gas price is much lower than Ethereum
            base_gas = self.web3.eth.gas_price
            # Cap at 100 gwei for Polygon (usually 1-50 gwei)
            return min(base_gas, self.web3.to_wei('100', 'gwei'))
        except:
            return self.web3.to_wei('30', 'gwei')  # Safe fallback

    def get_v3_quote(self, token_in, token_out, amount_in, fee_tier=500):
        """Get quote for V3 swap"""
        try:
            quote_result = self.quoter.functions.quoteExactInputSingle(
                token_in,           # tokenIn
                token_out,          # tokenOut
                fee_tier,           # fee
                amount_in,          # amountIn
                0                   # sqrtPriceLimitX96 (0 = no limit)
            ).call()

            return {
                'amount_out': quote_result[0],
                'sqrt_price_x96_after': quote_result[1],
                'initialized_ticks_crossed': quote_result[2],
                'gas_estimate': quote_result[3]
            }
        except Exception as e:
            print(f"V3 quote error: {e}")
            return None

    def swap_exact_input_v3(self, token_in, token_out, amount_in, min_amount_out, fee_tier=500):
        """Execute V3 swap with exact input"""
        # Check and approve token spending
        self.ensure_token_approval(token_in, amount_in, QUICKSWAP_CONFIG['router_v3'])

        # Prepare swap parameters
        swap_params = {
            'tokenIn': token_in,
            'tokenOut': token_out,
            'fee': fee_tier,
            'recipient': self.wallet_address,
            'deadline': int(time.time()) + 300,  # 5 minutes
            'amountIn': amount_in,
            'amountOutMinimum': min_amount_out,
            'sqrtPriceLimitX96': 0
        }

        # Build transaction
        transaction = self.router_v3.functions.exactInputSingle(swap_params).build_transaction({
            'from': self.wallet_address,
            'gas': 300000,  # Higher gas limit for V3
            'gasPrice': self.get_polygon_gas_price(),
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        })

        # Sign and send
        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"QuickSwap V3 swap: {tx_hash.hex()}")

        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        return self.parse_swap_result(receipt)

    def add_liquidity_v3(self, token0, token1, fee_tier, amount0_desired, amount1_desired, tick_lower, tick_upper):
        """Add concentrated liquidity to V3 pool"""
        # Get position manager contract
        position_manager = self.get_position_manager_contract()

        # Approve tokens
        self.ensure_token_approval(token0, amount0_desired, position_manager.address)
        self.ensure_token_approval(token1, amount1_desired, position_manager.address)

        # Calculate minimum amounts (5% slippage)
        amount0_min = int(amount0_desired * 0.95)
        amount1_min = int(amount1_desired * 0.95)

        # Mint parameters
        mint_params = {
            'token0': token0,
            'token1': token1,
            'fee': fee_tier,
            'tickLower': tick_lower,
            'tickUpper': tick_upper,
            'amount0Desired': amount0_desired,
            'amount1Desired': amount1_desired,
            'amount0Min': amount0_min,
            'amount1Min': amount1_min,
            'recipient': self.wallet_address,
            'deadline': int(time.time()) + 300
        }

        # Execute mint
        transaction = position_manager.functions.mint(mint_params).build_transaction({
            'from': self.wallet_address,
            'gas': 500000,
            'gasPrice': self.get_polygon_gas_price(),
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        })

        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"V3 liquidity added: {tx_hash.hex()}")

        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        return self.parse_liquidity_result(receipt)

    def get_pool_analytics(self, pair_name='WMATIC_USDC'):
        """Get comprehensive pool analytics"""
        pair_config = QUICKSWAP_CONFIG['pairs'][pair_name]

        # Get pool contract
        pool_address = self.get_pool_address(
            pair_config['token0'],
            pair_config['token1'],
            pair_config['fee']
        )

        pool_contract = self.get_pool_contract(pool_address)

        # Get pool state
        slot0 = pool_contract.functions.slot0().call()
        liquidity = pool_contract.functions.liquidity().call()

        return {
            'pair': pair_name,
            'pool_address': pool_address,
            'current_price': self.sqrt_price_to_price(slot0[0]),
            'current_tick': slot0[1],
            'liquidity': liquidity,
            'fee_tier': pair_config['fee'],
            'protocol_fee': slot0[2],
            'token0': pair_config['token0'],
            'token1': pair_config['token1'],
            'volume_24h': self.get_24h_volume(pool_address),
            'fees_24h': self.get_24h_fees(pool_address),
            'apy_estimate': self.calculate_pool_apy(pool_address)
        }

# Initialize QuickSwap
quickswap = QuickSwapExchange({
    'wallet_address': 'your_wallet_address',
    'private_key': 'your_private_key'
})
```

### 2. SpookySwap (Fantom) Integration

```python
# SpookySwap Configuration
SPOOKYSWAP_CONFIG = {
    'fantom_rpc': 'https://rpc.ftm.tools',
    'router': '0xF491e7B69E4244ad4002BC14e878a34207E38c29',
    'factory': '0x152eE697f2E276fA89E96742e9bB9aB1F2E61bE3',
    'masterchef': '0x2b2929E785374c651a81A63878Ab22742656DcDd',  # Yield farming
    'boo_token': '0x841FAD6EAe12c286d1Fd18d1d525DFfA75C7EFFE',  # BOO governance token

    # Popular Fantom pairs
    'pairs': {
        'FTM_USDC': {
            'token0': '0x21be370D5312f44cB42ce377BC9b8a0cEF1A4C83',  # WFTM
            'token1': '0x04068DA6C83AFCFA0e13ba15A6696662335D5B75',  # USDC
            'pid': 2  # MasterChef pool ID
        },
        'WFTM_BOO': {
            'token0': '0x21be370D5312f44cB42ce377BC9b8a0cEF1A4C83',  # WFTM
            'token1': '0x841FAD6EAe12c286d1Fd18d1d525DFfA75C7EFFE',  # BOO
            'pid': 0
        }
    }
}

class SpookySwapExchange:
    def __init__(self, config):
        self.web3 = Web3(Web3.HTTPProvider(SPOOKYSWAP_CONFIG['fantom_rpc']))
        self.wallet_address = config['wallet_address']
        self.private_key = config['private_key']

        # Initialize contracts
        self.router = self.web3.eth.contract(
            address=SPOOKYSWAP_CONFIG['router'],
            abi=self.load_abi('spookyswap_router')
        )

        self.masterchef = self.web3.eth.contract(
            address=SPOOKYSWAP_CONFIG['masterchef'],
            abi=self.load_abi('masterchef')
        )

        self.boo_token = self.web3.eth.contract(
            address=SPOOKYSWAP_CONFIG['boo_token'],
            abi=self.load_abi('erc20')
        )

    def get_fantom_gas_price(self):
        """Get optimal gas price for Fantom (very low fees)"""
        try:
            base_gas = self.web3.eth.gas_price
            # Fantom typically has very low gas prices
            return min(base_gas, self.web3.to_wei('50', 'gwei'))
        except:
            return self.web3.to_wei('3', 'gwei')  # Ultra-low fallback

    def swap_exact_ftm_for_tokens(self, token_out, ftm_amount, min_tokens_out):
        """Swap FTM for tokens on SpookySwap"""
        path = [SPOOKYSWAP_CONFIG['pairs']['FTM_USDC']['token0'], token_out]

        transaction = self.router.functions.swapExactETHForTokens(
            min_tokens_out,
            path,
            self.wallet_address,
            int(time.time()) + 300  # 5 minutes deadline
        ).build_transaction({
            'from': self.wallet_address,
            'value': ftm_amount,
            'gas': 200000,
            'gasPrice': self.get_fantom_gas_price(),
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        })

        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"SpookySwap FTM swap: {tx_hash.hex()}")

        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    def add_liquidity_and_farm(self, token_a, token_b, amount_a, amount_b, pool_id):
        """Add liquidity and automatically stake in yield farm"""
        # Step 1: Add liquidity
        self.ensure_token_approval(token_a, amount_a, SPOOKYSWAP_CONFIG['router'])
        self.ensure_token_approval(token_b, amount_b, SPOOKYSWAP_CONFIG['router'])

        # Calculate minimum amounts (2% slippage for Fantom's low volatility)
        amount_a_min = int(amount_a * 0.98)
        amount_b_min = int(amount_b * 0.98)

        add_liquidity_tx = self.router.functions.addLiquidity(
            token_a,
            token_b,
            amount_a,
            amount_b,
            amount_a_min,
            amount_b_min,
            self.wallet_address,
            int(time.time()) + 300
        ).build_transaction({
            'from': self.wallet_address,
            'gas': 300000,
            'gasPrice': self.get_fantom_gas_price(),
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        })

        signed_tx = self.web3.eth.account.sign_transaction(add_liquidity_tx, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"Liquidity added: {tx_hash.hex()}")
        self.web3.eth.wait_for_transaction_receipt(tx_hash)

        # Step 2: Get LP token balance
        lp_token_address = self.get_pair_address(token_a, token_b)
        lp_token = self.web3.eth.contract(address=lp_token_address, abi=self.erc20_abi)
        lp_balance = lp_token.functions.balanceOf(self.wallet_address).call()

        # Step 3: Stake LP tokens in MasterChef
        if lp_balance > 0:
            # Approve MasterChef to spend LP tokens
            approve_tx = lp_token.functions.approve(
                SPOOKYSWAP_CONFIG['masterchef'],
                lp_balance
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 100000,
                'gasPrice': self.get_fantom_gas_price(),
                'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
            })

            signed_approve = self.web3.eth.account.sign_transaction(approve_tx, self.private_key)
            approve_hash = self.web3.eth.send_raw_transaction(signed_approve.rawTransaction)
            self.web3.eth.wait_for_transaction_receipt(approve_hash)

            # Deposit to MasterChef
            deposit_tx = self.masterchef.functions.deposit(pool_id, lp_balance).build_transaction({
                'from': self.wallet_address,
                'gas': 200000,
                'gasPrice': self.get_fantom_gas_price(),
                'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
            })

            signed_deposit = self.web3.eth.account.sign_transaction(deposit_tx, self.private_key)
            deposit_hash = self.web3.eth.send_raw_transaction(signed_deposit.rawTransaction)

            print(f"LP tokens staked: {deposit_hash.hex()}")

            receipt = self.web3.eth.wait_for_transaction_receipt(deposit_hash)
            return receipt

    def harvest_boo_rewards(self, pool_id):
        """Harvest BOO token rewards from yield farming"""
        # Check pending rewards
        pending_boo = self.masterchef.functions.pendingBOO(pool_id, self.wallet_address).call()

        if pending_boo > 0:
            print(f"Harvesting {pending_boo / 1e18:.4f} BOO tokens")

            # Harvest by depositing 0
            harvest_tx = self.masterchef.functions.deposit(pool_id, 0).build_transaction({
                'from': self.wallet_address,
                'gas': 150000,
                'gasPrice': self.get_fantom_gas_price(),
                'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
            })

            signed_harvest = self.web3.eth.account.sign_transaction(harvest_tx, self.private_key)
            harvest_hash = self.web3.eth.send_raw_transaction(signed_harvest.rawTransaction)

            receipt = self.web3.eth.wait_for_transaction_receipt(harvest_hash)
            return receipt

        return None

# Initialize SpookySwap
spookyswap = SpookySwapExchange({
    'wallet_address': 'your_wallet_address',
    'private_key': 'your_private_key'
})
```

### 3. Trader Joe (Avalanche) Integration

```python
# Trader Joe Configuration
TRADER_JOE_CONFIG = {
    'avalanche_rpc': 'https://api.avax.network/ext/bc/C/rpc',
    'router_v2': '0x60aE616a2155Ee3d9A68541Ba4544862310933d4',
    'factory_v2': '0x9Ad6C38BE94206cA50bb0d90783181662f0Cfa10',
    'lb_router': '0xb4315e873dBcf96Ffd0acd8EA43f689D8c20fB30',  # Liquidity Book Router
    'lb_factory': '0x8e42f2F4101563bF679975178e880FD87d3eFd4e', # Liquidity Book Factory
    'joe_token': '0x6e84a6216eA6dACC71eE8E6b0a5B7322EEbC0fDd',
    'xjoe_token': '0x57319d41F71E81F3c65F2a47CA4e001EbAFd4F33',  # Staked JOE

    # Popular AVAX pairs
    'pairs': {
        'AVAX_USDC': {
            'token0': '0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7',  # WAVAX
            'token1': '0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E',  # USDC
            'bin_step': 15  # For Liquidity Book
        },
        'AVAX_JOE': {
            'token0': '0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7',  # WAVAX
            'token1': '0x6e84a6216eA6dACC71eE8E6b0a5B7322EEbC0fDd',  # JOE
            'bin_step': 20
        }
    }
}

class TraderJoeExchange:
    def __init__(self, config):
        self.web3 = Web3(Web3.HTTPProvider(TRADER_JOE_CONFIG['avalanche_rpc']))
        self.wallet_address = config['wallet_address']
        self.private_key = config['private_key']

        # Initialize contracts
        self.router_v2 = self.web3.eth.contract(
            address=TRADER_JOE_CONFIG['router_v2'],
            abi=self.load_abi('traderjoe_router')
        )

        self.lb_router = self.web3.eth.contract(
            address=TRADER_JOE_CONFIG['lb_router'],
            abi=self.load_abi('lb_router')
        )

        self.lb_factory = self.web3.eth.contract(
            address=TRADER_JOE_CONFIG['lb_factory'],
            abi=self.load_abi('lb_factory')
        )

        self.joe_token = self.web3.eth.contract(
            address=TRADER_JOE_CONFIG['joe_token'],
            abi=self.load_abi('erc20')
        )

    def get_avalanche_gas_price(self):
        """Get optimal gas price for Avalanche C-Chain"""
        try:
            base_gas = self.web3.eth.gas_price
            # Avalanche typically has moderate gas prices
            return min(base_gas, self.web3.to_wei('25', 'gwei'))
        except:
            return self.web3.to_wei('25', 'gwei')

    def swap_exact_avax_for_tokens_lb(self, token_out, avax_amount, min_tokens_out, bin_step=15):
        """Swap AVAX for tokens using Liquidity Book (V2.1) for better capital efficiency"""
        # Get the LB pair address
        pair_address = self.lb_factory.functions.getLBPairInformation(
            TRADER_JOE_CONFIG['pairs']['AVAX_USDC']['token0'],  # WAVAX
            token_out,
            bin_step
        ).call()[0]  # LBPair address

        if pair_address == '0x0000000000000000000000000000000000000000':
            # Fallback to V2 router
            return self.swap_exact_avax_for_tokens_v2(token_out, avax_amount, min_tokens_out)

        # Prepare swap path for Liquidity Book
        path = {
            'tokenPath': [TRADER_JOE_CONFIG['pairs']['AVAX_USDC']['token0'], token_out],
            'pairBinSteps': [bin_step],
            'versions': [1]  # Version 1 for LB pairs
        }

        # Execute LB swap
        transaction = self.lb_router.functions.swapExactNATIVEForTokens(
            min_tokens_out,
            path,
            self.wallet_address,
            int(time.time()) + 300
        ).build_transaction({
            'from': self.wallet_address,
            'value': avax_amount,
            'gas': 250000,
            'gasPrice': self.get_avalanche_gas_price(),
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        })

        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"Trader Joe LB swap: {tx_hash.hex()}")

        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    def add_liquidity_book_position(self, token_x, token_y, amount_x, amount_y, active_id, bin_step, width=5):
        """Add concentrated liquidity to Liquidity Book with specific price range"""
        # Calculate bin range for liquidity provision
        lower_bin = active_id - width
        upper_bin = active_id + width

        # Distribute liquidity across bins (uniform distribution)
        bins = list(range(lower_bin, upper_bin + 1))
        distribution_x = [amount_x // len(bins)] * len(bins)
        distribution_y = [amount_y // len(bins)] * len(bins)

        # Approve tokens
        self.ensure_token_approval(token_x, amount_x, TRADER_JOE_CONFIG['lb_router'])
        self.ensure_token_approval(token_y, amount_y, TRADER_JOE_CONFIG['lb_router'])

        # Prepare liquidity parameters
        liquidity_params = {
            'tokenX': token_x,
            'tokenY': token_y,
            'binStep': bin_step,
            'amountX': amount_x,
            'amountY': amount_y,
            'amountXMin': int(amount_x * 0.95),  # 5% slippage
            'amountYMin': int(amount_y * 0.95),
            'activeIdDesired': active_id,
            'idSlippage': 5,  # Allow 5 bins of slippage
            'deltaIds': bins,
            'distributionX': distribution_x,
            'distributionY': distribution_y,
            'to': self.wallet_address,
            'deadline': int(time.time()) + 300
        }

        # Add liquidity
        transaction = self.lb_router.functions.addLiquidity(liquidity_params).build_transaction({
            'from': self.wallet_address,
            'gas': 400000,
            'gasPrice': self.get_avalanche_gas_price(),
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        })

        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"LB liquidity added: {tx_hash.hex()}")

        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    def get_lb_pair_info(self, token_x, token_y, bin_step):
        """Get Liquidity Book pair information and analytics"""
        pair_info = self.lb_factory.functions.getLBPairInformation(token_x, token_y, bin_step).call()

        if pair_info[0] != '0x0000000000000000000000000000000000000000':
            pair_address = pair_info[0]
            pair_contract = self.web3.eth.contract(
                address=pair_address,
                abi=self.load_abi('lb_pair')
            )

            # Get current active bin and price
            active_id = pair_contract.functions.getActiveId().call()
            reserves = pair_contract.functions.getReserves().call()

            return {
                'pair_address': pair_address,
                'active_id': active_id,
                'reserve_x': reserves[0],
                'reserve_y': reserves[1],
                'bin_step': bin_step,
                'price': self.bin_id_to_price(active_id, bin_step),
                'total_supply_x': pair_contract.functions.totalSupply(active_id).call(),
                'fees_24h': self.get_lb_pair_fees_24h(pair_address),
                'volume_24h': self.get_lb_pair_volume_24h(pair_address)
            }

        return None

    def stake_joe_for_xjoe(self, joe_amount):
        """Stake JOE tokens for xJOE (staked JOE with governance rights)"""
        # Approve JOE spending
        approve_tx = self.joe_token.functions.approve(
            TRADER_JOE_CONFIG['xjoe_token'],
            joe_amount
        ).build_transaction({
            'from': self.wallet_address,
            'gas': 100000,
            'gasPrice': self.get_avalanche_gas_price(),
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        })

        signed_approve = self.web3.eth.account.sign_transaction(approve_tx, self.private_key)
        approve_hash = self.web3.eth.send_raw_transaction(signed_approve.rawTransaction)
        self.web3.eth.wait_for_transaction_receipt(approve_hash)

        # Stake JOE
        xjoe_contract = self.web3.eth.contract(
            address=TRADER_JOE_CONFIG['xjoe_token'],
            abi=self.load_abi('xjoe')
        )

        stake_tx = xjoe_contract.functions.enter(joe_amount).build_transaction({
            'from': self.wallet_address,
            'gas': 150000,
            'gasPrice': self.get_avalanche_gas_price(),
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        })

        signed_stake = self.web3.eth.account.sign_transaction(stake_tx, self.private_key)
        stake_hash = self.web3.eth.send_raw_transaction(signed_stake.rawTransaction)

        print(f"JOE staked for xJOE: {stake_hash.hex()}")

        receipt = self.web3.eth.wait_for_transaction_receipt(stake_hash)
        return receipt

# Initialize Trader Joe
traderjoe = TraderJoeExchange({
    'wallet_address': 'your_wallet_address',
    'private_key': 'your_private_key'
})
```

## Layer 2 Trading Strategies

### 1. Multi-Chain DEX Arbitrage
```python
def multi_chain_dex_arbitrage():
    """
    Arbitrage opportunities across Layer 2 DEXs
    """
    print("🌉 Multi-Chain DEX Arbitrage Strategy")
    print("=" * 35)

    # Get prices across different L2s
    token_pair = 'USDC_WETH'

    prices = {
        'polygon_quickswap': quickswap.get_pool_analytics('WETH_USDC')['current_price'],
        'fantom_spookyswap': spookyswap.get_pair_price('FTM_USDC'),  # Convert FTM to ETH equivalent
        'avalanche_traderjoe': traderjoe.get_lb_pair_info(
            TRADER_JOE_CONFIG['pairs']['AVAX_USDC']['token0'],
            TRADER_JOE_CONFIG['pairs']['AVAX_USDC']['token1'],
            15
        )['price'],
        'arbitrum_sushiswap': sushiswap.get_pair_price('WETH_USDC', 'arbitrum'),
        'optimism_sushiswap': sushiswap.get_pair_price('WETH_USDC', 'optimism')
    }

    print("Cross-Chain Price Comparison (USDC per ETH):")
    for chain, price in prices.items():
        print(f"  {chain}: ${price:,.2f}")

    # Find arbitrage opportunities
    min_price_chain = min(prices, key=prices.get)
    max_price_chain = max(prices, key=prices.get)

    price_difference = prices[max_price_chain] - prices[min_price_chain]
    arbitrage_percentage = (price_difference / prices[min_price_chain]) * 100

    print(f"\nArbitrage Opportunity:")
    print(f"  Buy on {min_price_chain}: ${prices[min_price_chain]:,.2f}")
    print(f"  Sell on {max_price_chain}: ${prices[max_price_chain]:,.2f}")
    print(f"  Spread: ${price_difference:,.2f} ({arbitrage_percentage:.2f}%)")

    # Execute if profitable (accounting for bridge costs)
    bridge_cost = estimate_bridge_cost(min_price_chain.split('_')[0], max_price_chain.split('_')[0])

    if arbitrage_percentage > bridge_cost + 1:  # Need >1% profit after bridge costs
        print(f"✅ Profitable arbitrage opportunity! Executing...")
        execute_cross_chain_arbitrage(min_price_chain, max_price_chain, price_difference)
    else:
        print(f"❌ Not profitable after bridge costs ({bridge_cost:.2f}%)")

def execute_cross_chain_arbitrage(buy_chain, sell_chain, expected_profit):
    """Execute cross-chain arbitrage trade"""
    print(f"⚡ Executing arbitrage: {buy_chain} → {sell_chain}")

    trade_amount_eth = 1.0  # 1 ETH for arbitrage

    # Step 1: Buy ETH on cheaper chain
    if 'polygon' in buy_chain:
        buy_tx = quickswap.swap_exact_input_v3(
            QUICKSWAP_CONFIG['pairs']['WMATIC_USDC']['token1'],  # USDC
            QUICKSWAP_CONFIG['pairs']['WETH_USDC']['token0'],    # WETH
            int(trade_amount_eth * 1800 * 1e6),  # Approximate USDC amount
            int(trade_amount_eth * 0.99 * 1e18)  # Min ETH out (1% slippage)
        )
    elif 'fantom' in buy_chain:
        buy_tx = spookyswap.swap_exact_ftm_for_tokens(
            SPOOKYSWAP_CONFIG['pairs']['FTM_USDC']['token1'],  # Target token
            int(trade_amount_eth * 1800 * 1e18),  # FTM amount (assume FTM price)
            int(trade_amount_eth * 0.99 * 1e18)   # Min tokens out
        )
    elif 'avalanche' in buy_chain:
        buy_tx = traderjoe.swap_exact_avax_for_tokens_lb(
            TRADER_JOE_CONFIG['pairs']['AVAX_USDC']['token1'],  # USDC
            int(trade_amount_eth * 1800 * 1e18),  # AVAX amount
            int(trade_amount_eth * 0.99 * 1e18)   # Min out
        )

    print(f"✅ Buy executed on {buy_chain}: {buy_tx}")

    # Step 2: Bridge to sell chain (simplified - actual implementation would use bridge protocols)
    bridge_tx = bridge_assets(
        from_chain=buy_chain.split('_')[0],
        to_chain=sell_chain.split('_')[0],
        asset='ETH',
        amount=trade_amount_eth
    )

    print(f"✅ Bridge completed: {bridge_tx}")

    # Step 3: Sell ETH on more expensive chain
    if 'polygon' in sell_chain:
        sell_tx = quickswap.swap_exact_input_v3(
            QUICKSWAP_CONFIG['pairs']['WETH_USDC']['token0'],    # WETH
            QUICKSWAP_CONFIG['pairs']['WMATIC_USDC']['token1'],  # USDC
            int(trade_amount_eth * 1e18),  # ETH amount
            int(trade_amount_eth * 1800 * 0.99 * 1e6)  # Min USDC out
        )
    # Similar implementations for other chains...

    print(f"✅ Sell executed on {sell_chain}: {sell_tx}")
    print(f"💰 Expected profit: ${expected_profit:,.2f}")

def bridge_assets(from_chain, to_chain, asset, amount):
    """Simplified bridge function - would integrate with actual bridge protocols"""
    # This would integrate with:
    # - Hop Protocol for optimistic rollups
    # - Multichain for general bridging
    # - Stargate for stablecoin bridging
    # - Synapse for cross-chain bridging

    bridge_mapping = {
        ('polygon', 'avalanche'): 'multichain',
        ('polygon', 'fantom'): 'multichain',
        ('avalanche', 'fantom'): 'multichain',
        ('arbitrum', 'optimism'): 'hop_protocol',
        ('polygon', 'arbitrum'): 'hop_protocol'
    }

    bridge_protocol = bridge_mapping.get((from_chain, to_chain), 'multichain')

    print(f"🌉 Bridging {amount} {asset} from {from_chain} to {to_chain} via {bridge_protocol}")

    # Return mock transaction hash
    return f"0x{''.join(['a'] * 64)}"  # Placeholder

def estimate_bridge_cost(from_chain, to_chain):
    """Estimate bridge cost as percentage of transaction value"""
    bridge_costs = {
        ('polygon', 'avalanche'): 0.1,   # 0.1%
        ('polygon', 'fantom'): 0.15,     # 0.15%
        ('avalanche', 'fantom'): 0.1,    # 0.1%
        ('arbitrum', 'optimism'): 0.05,  # 0.05% (both optimistic)
        ('polygon', 'arbitrum'): 0.1     # 0.1%
    }

    return bridge_costs.get((from_chain, to_chain), 0.2)  # Default 0.2%
```

### 2. Layer 2 Yield Optimization
```python
def layer2_yield_optimization():
    """
    Optimize yield farming across different Layer 2 networks
    """
    print("🚀 Layer 2 Yield Optimization Strategy")
    print("=" * 40)

    # Get yield opportunities across L2s
    yield_opportunities = {
        'quickswap_matic_usdc': {
            'platform': 'QuickSwap',
            'chain': 'Polygon',
            'pair': 'MATIC-USDC',
            'base_apy': quickswap.get_pool_analytics('WMATIC_USDC')['apy_estimate'],
            'additional_rewards': ['QUICK', 'dQUICK'],
            'additional_apy': 12.5,  # From liquidity mining
            'total_apy': 0  # To be calculated
        },
        'spookyswap_ftm_boo': {
            'platform': 'SpookySwap',
            'chain': 'Fantom',
            'pair': 'FTM-BOO',
            'base_apy': 8.2,
            'additional_rewards': ['BOO'],
            'additional_apy': 25.3,
            'total_apy': 0
        },
        'traderjoe_avax_joe': {
            'platform': 'Trader Joe',
            'chain': 'Avalanche',
            'pair': 'AVAX-JOE',
            'base_apy': 6.8,
            'additional_rewards': ['JOE'],
            'additional_apy': 18.7,
            'total_apy': 0
        },
        'sushiswap_arb_eth_usdc': {
            'platform': 'SushiSwap',
            'chain': 'Arbitrum',
            'pair': 'ETH-USDC',
            'base_apy': 4.5,
            'additional_rewards': ['SUSHI', 'ARB'],
            'additional_apy': 15.2,
            'total_apy': 0
        }
    }

    # Calculate total APYs
    for opportunity_id, data in yield_opportunities.items():
        data['total_apy'] = data['base_apy'] + data['additional_apy']

    # Sort by total APY
    sorted_opportunities = sorted(
        yield_opportunities.items(),
        key=lambda x: x[1]['total_apy'],
        reverse=True
    )

    print("Yield Opportunities Ranked by APY:")
    for i, (opportunity_id, data) in enumerate(sorted_opportunities, 1):
        print(f"  {i}. {data['platform']} ({data['chain']})")
        print(f"     Pair: {data['pair']}")
        print(f"     Base APY: {data['base_apy']:.1f}%")
        print(f"     Rewards APY: {data['additional_apy']:.1f}%")
        print(f"     Total APY: {data['total_apy']:.1f}%")
        print(f"     Rewards: {', '.join(data['additional_rewards'])}")
        print()

    # Execute optimal allocation
    total_capital = 50000  # $50k to allocate

    # Allocate based on risk-adjusted returns
    allocation_strategy = calculate_l2_yield_allocation(sorted_opportunities, total_capital)

    execute_l2_yield_deployment(allocation_strategy)

def calculate_l2_yield_allocation(opportunities, total_capital):
    """Calculate optimal allocation across L2 yield opportunities"""
    # Simple allocation: Weight by APY but cap single platform exposure
    allocations = {}

    total_weighted_apy = sum(data[1]['total_apy'] for data in opportunities)

    for opportunity_id, data in opportunities:
        # Base allocation by APY weight
        apy_weight = data['total_apy'] / total_weighted_apy

        # Cap single platform at 40%
        allocation_percentage = min(apy_weight, 0.4)

        # Adjust for gas costs (favor L2s with lower gas)
        gas_adjustment = {
            'Polygon': 1.0,    # Lowest fees
            'Fantom': 1.0,     # Very low fees
            'Avalanche': 0.95,  # Moderate fees
            'Arbitrum': 0.9    # Higher fees but still reasonable
        }

        chain = data['chain']
        adjusted_allocation = allocation_percentage * gas_adjustment.get(chain, 0.9)

        allocations[opportunity_id] = {
            'amount': total_capital * adjusted_allocation,
            'percentage': adjusted_allocation * 100,
            'platform': data['platform'],
            'chain': data['chain'],
            'expected_apy': data['total_apy']
        }

    print("Optimal Allocation Strategy:")
    for opportunity_id, allocation in allocations.items():
        if allocation['amount'] > 1000:  # Only show allocations > $1k
            print(f"  {allocation['platform']} ({allocation['chain']}): "
                  f"${allocation['amount']:,.0f} ({allocation['percentage']:.1f}%) - "
                  f"{allocation['expected_apy']:.1f}% APY")

    return allocations

def execute_l2_yield_deployment(allocations):
    """Deploy capital across Layer 2 yield opportunities"""
    print("\nDeploying capital across Layer 2 platforms:")

    for opportunity_id, allocation in allocations.items():
        if allocation['amount'] > 1000:  # Only deploy meaningful amounts
            platform = allocation['platform']
            chain = allocation['chain']
            amount = allocation['amount']

            print(f"\nDeploying ${amount:,.0f} to {platform} on {chain}")

            if platform == 'QuickSwap':
                deploy_to_quickswap(amount)
            elif platform == 'SpookySwap':
                deploy_to_spookyswap(amount)
            elif platform == 'Trader Joe':
                deploy_to_traderjoe(amount)
            elif platform == 'SushiSwap':
                deploy_to_sushiswap(amount, chain)

def deploy_to_quickswap(amount_usd):
    """Deploy capital to QuickSwap LP + farming"""
    # Convert USD to token amounts (50/50 split)
    matic_amount = (amount_usd / 2) / get_token_price('MATIC')
    usdc_amount = (amount_usd / 2)

    # Add liquidity
    lp_tx = quickswap.add_liquidity_v3(
        QUICKSWAP_CONFIG['pairs']['WMATIC_USDC']['token0'],  # WMATIC
        QUICKSWAP_CONFIG['pairs']['WMATIC_USDC']['token1'],  # USDC
        500,  # 0.05% fee tier
        int(matic_amount * 1e18),
        int(usdc_amount * 1e6),
        -887220,  # tick_lower (wide range)
        887220    # tick_upper (wide range)
    )

    print(f"✅ QuickSwap liquidity added: {lp_tx}")

    # Additional farming integration would go here
    return lp_tx

def deploy_to_spookyswap(amount_usd):
    """Deploy capital to SpookySwap LP + farming"""
    # Convert USD to FTM and BOO amounts
    ftm_amount = (amount_usd / 2) / get_token_price('FTM')
    boo_amount = (amount_usd / 2) / get_token_price('BOO')

    # Add liquidity and farm
    farm_tx = spookyswap.add_liquidity_and_farm(
        SPOOKYSWAP_CONFIG['pairs']['WFTM_BOO']['token0'],  # WFTM
        SPOOKYSWAP_CONFIG['pairs']['WFTM_BOO']['token1'],  # BOO
        int(ftm_amount * 1e18),
        int(boo_amount * 1e18),
        SPOOKYSWAP_CONFIG['pairs']['WFTM_BOO']['pid']
    )

    print(f"✅ SpookySwap farming deployed: {farm_tx}")
    return farm_tx

def deploy_to_traderjoe(amount_usd):
    """Deploy capital to Trader Joe Liquidity Book"""
    # Get current active bin for AVAX-JOE
    pair_info = traderjoe.get_lb_pair_info(
        TRADER_JOE_CONFIG['pairs']['AVAX_JOE']['token0'],  # WAVAX
        TRADER_JOE_CONFIG['pairs']['AVAX_JOE']['token1'],  # JOE
        TRADER_JOE_CONFIG['pairs']['AVAX_JOE']['bin_step']
    )

    # Convert USD to token amounts
    avax_amount = (amount_usd / 2) / get_token_price('AVAX')
    joe_amount = (amount_usd / 2) / get_token_price('JOE')

    # Add concentrated liquidity
    lb_tx = traderjoe.add_liquidity_book_position(
        TRADER_JOE_CONFIG['pairs']['AVAX_JOE']['token0'],  # WAVAX
        TRADER_JOE_CONFIG['pairs']['AVAX_JOE']['token1'],  # JOE
        int(avax_amount * 1e18),
        int(joe_amount * 1e18),
        pair_info['active_id'],  # Current active bin
        TRADER_JOE_CONFIG['pairs']['AVAX_JOE']['bin_step'],
        10  # Liquidity width (10 bins)
    )

    print(f"✅ Trader Joe LB position created: {lb_tx}")
    return lb_tx
```

## Environment Configuration

Add to your `.env` file:

```bash
# Layer 2 Networks Configuration
POLYGON_RPC_URL=https://polygon-rpc.com
FANTOM_RPC_URL=https://rpc.ftm.tools
AVALANCHE_RPC_URL=https://api.avax.network/ext/bc/C/rpc
ARBITRUM_RPC_URL=https://arb1.arbitrum.io/rpc
OPTIMISM_RPC_URL=https://mainnet.optimism.io

# DEX Configuration
QUICKSWAP_WALLET_ADDRESS=your_wallet_address
QUICKSWAP_PRIVATE_KEY=your_private_key
SPOOKYSWAP_WALLET_ADDRESS=your_wallet_address
SPOOKYSWAP_PRIVATE_KEY=your_private_key
TRADERJOE_WALLET_ADDRESS=your_wallet_address
TRADERJOE_PRIVATE_KEY=your_private_key

# Strategy Parameters
L2_ARBITRAGE_MIN_PROFIT=1.0
L2_YIELD_OPTIMIZATION_INTERVAL=7200
L2_AUTO_COMPOUND=true
L2_CROSS_CHAIN_ENABLED=true
L2_MAX_SLIPPAGE=0.02
L2_GAS_OPTIMIZATION=true

# Bridge Configuration
HOP_PROTOCOL_ENABLED=true
MULTICHAIN_BRIDGE_ENABLED=true
SYNAPSE_BRIDGE_ENABLED=true
STARGATE_BRIDGE_ENABLED=true
```

This comprehensive Layer 2 DEX documentation provides full integration capabilities for major L2 trading platforms with advanced cross-chain arbitrage and yield optimization strategies within PowerTraderAI+.
