# DeFi Lending Platforms Integration Guide

## Overview
This guide covers integration with major DeFi lending protocols including Compound, MakerDAO, and other lending platforms. These protocols enable automated borrowing, lending, and yield farming strategies with algorithmic interest rates and collateralized positions.

## Supported DeFi Lending Protocols

### 🏛️ **Compound Protocol**
- **Network**: Ethereum, Polygon
- **Features**: Algorithmic interest rates, cToken system, governance
- **TVL**: $3.2B+ across all markets
- **Specialty**: Blue-chip lending with battle-tested architecture

### 🏛️ **MakerDAO**
- **Network**: Ethereum (expanding to L2s)
- **Features**: DAI stablecoin minting, CDP system, decentralized governance
- **TVL**: $8.1B+ in collateral locked
- **Specialty**: Collateralized debt positions (CDPs) and DAI stability

### 🏛️ **Euler Finance**
- **Network**: Ethereum
- **Features**: Permission-less listing, reactive interest rates, MEV protection
- **TVL**: $200M+ across 100+ assets
- **Specialty**: Long-tail asset lending with advanced risk management

### 🏛️ **Frax Finance**
- **Network**: Ethereum, Polygon, Arbitrum, Avalanche
- **Features**: Algorithmic stablecoin, liquid staking, yield optimization
- **TVL**: $1.2B+ across protocols
- **Specialty**: Hybrid algorithmic/collateralized stablecoin system

## Prerequisites
- Web3 wallet with ETH for gas fees
- Understanding of DeFi lending mechanics and liquidation risks
- Basic knowledge of smart contracts and transaction costs
- Risk tolerance for smart contract vulnerabilities
- Sufficient collateral for borrowing positions

## **Access & Compliance Requirements**

### **Protocol-Level Access (Decentralized)**
- **KYC Required**: None - permissionless protocols
- **Geographic Restrictions**: None at protocol level
- **Age Verification**: None required
- **Identity Verification**: None required
- **Minimum Investment**: Only gas fees for transactions
- **Account Creation**: Wallet connection only

### **Frontend Interface Compliance**
- **Aave.com**: Geo-blocking for US, sanctioned countries
- **Compound.finance**: Restricted US access for certain features
- **Euler.finance**: Unrestricted global access
- **MakerDAO**: Multiple interfaces, mostly unrestricted
- **Alternative Access**: VPN usage common, multiple frontend options

### **Institutional DeFi Access**
- **Aave Arc**: Permissioned version with KYC/AML compliance
- **Compound Treasury**: Institutional gateway with verification
- **Fireblocks Integration**: Institutional custody solutions
- **Requirements**: Enhanced KYC, source of funds verification, institutional wallet custody

### **Regulatory Considerations**
- **Tax Reporting**: User responsibility for DeFi activity reporting
- **AML/CTF**: No protocol-level compliance mechanisms
- **Smart Contract Risk**: Users assume full protocol risk
- **Regulatory Evolution**: Compliance requirements may change by jurisdiction

## Technical Setup

### 1. Compound Protocol Integration

```python
from pt_exchanges import CompoundExchange
import web3
from web3 import Web3
import json
import time

# Compound Protocol Configuration
COMPOUND_CONFIG = {
    'comptroller': '0x3d9819210A31b4961b30EF54bE2aeD79B9c9Cd3B',  # Mainnet
    'price_oracle': '0x046728da7cb8272284238bD3e47909823d63A58D',
    'compound_lens': '0xd513d22422a3062Bd342Ae374b4b9c20E0a9a074',

    # cToken contracts
    'ceth': '0x4Ddc2D193948926D02f9B1fE9e1daa0718270ED5',      # cEther
    'cusdc': '0x39AA39c021dfbaE8faC545936693aC917d5E7563',     # cUSDC
    'cdai': '0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643',      # cDAI
    'cusdt': '0xf650C3d88D12dB855b8bf7D11Be6C55A4e07dCC9',     # cUSDT
    'cwbtc': '0xC11b1268C1A384e55C48c2391d8d480264A3A7F4',     # cWBTC
    'ccomp': '0x70e36f6BF80a52b3B46b3aF8e106CC0ed743E8e4',     # cCOMP

    # Underlying tokens
    'usdc': '0xA0b86a33E6441E6C9CD9F00Da6F75e2BB4fc4400',
    'dai': '0x6B175474E89094C44Da98b954EedeAC495271d0F',
    'usdt': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
    'wbtc': '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599',
    'comp': '0xc00e94Cb662C3520282E6f5717214004A7f26888'
}

class CompoundExchange:
    def __init__(self, config):
        self.web3 = Web3(Web3.HTTPProvider(config['rpc_url']))
        self.wallet_address = config['wallet_address']
        self.private_key = config['private_key']

        # Load ABIs
        self.comptroller_abi = self.load_abi('comptroller')
        self.ctoken_abi = self.load_abi('ctoken')
        self.erc20_abi = self.load_abi('erc20')

        # Initialize contracts
        self.comptroller = self.web3.eth.contract(
            address=COMPOUND_CONFIG['comptroller'],
            abi=self.comptroller_abi
        )

        self.ctoken_contracts = {}
        for name, address in COMPOUND_CONFIG.items():
            if name.startswith('c') and len(address) == 42:
                self.ctoken_contracts[name] = self.web3.eth.contract(
                    address=address,
                    abi=self.ctoken_abi
                )

    def get_market_info(self, ctoken_symbol='cusdc'):
        """Get comprehensive market information for a cToken"""
        ctoken = self.ctoken_contracts[ctoken_symbol]

        # Get basic market data
        supply_rate = ctoken.functions.supplyRatePerBlock().call()
        borrow_rate = ctoken.functions.borrowRatePerBlock().call()
        cash = ctoken.functions.getCash().call()
        total_borrows = ctoken.functions.totalBorrows().call()
        total_reserves = ctoken.functions.totalReserves().call()
        total_supply = ctoken.functions.totalSupply().call()
        exchange_rate = ctoken.functions.exchangeRateStored().call()

        # Convert to APY (blocks per year ~= 2,102,400)
        blocks_per_year = 2102400
        supply_apy = ((supply_rate / 1e18) * blocks_per_year) * 100
        borrow_apy = ((borrow_rate / 1e18) * blocks_per_year) * 100

        # Get collateral factor
        market_info = self.comptroller.functions.markets(ctoken.address).call()
        collateral_factor = market_info[1] / 1e18  # Convert from mantissa

        return {
            'symbol': ctoken_symbol,
            'supply_apy': supply_apy,
            'borrow_apy': borrow_apy,
            'utilization_rate': (total_borrows / (cash + total_borrows)) * 100 if (cash + total_borrows) > 0 else 0,
            'total_supply_usd': self.convert_to_usd(total_supply, ctoken_symbol),
            'total_borrows_usd': self.convert_to_usd(total_borrows, ctoken_symbol),
            'cash_usd': self.convert_to_usd(cash, ctoken_symbol),
            'collateral_factor': collateral_factor,
            'exchange_rate': exchange_rate / 1e28,  # Convert to readable format
            'last_updated': int(time.time())
        }

    def supply_asset(self, token_symbol, amount):
        """Supply assets to Compound for lending"""
        ctoken_symbol = f'c{token_symbol.lower()}'

        if ctoken_symbol not in self.ctoken_contracts:
            raise ValueError(f"Unsupported token: {token_symbol}")

        ctoken = self.ctoken_contracts[ctoken_symbol]

        if token_symbol.upper() == 'ETH':
            # Supply ETH directly
            tx_data = {
                'from': self.wallet_address,
                'value': self.web3.to_wei(amount, 'ether'),
                'gas': 200000,
                'gasPrice': self.web3.to_wei('20', 'gwei')
            }

            transaction = ctoken.functions.mint().build_transaction(tx_data)
        else:
            # Supply ERC20 token
            token_address = COMPOUND_CONFIG[token_symbol.lower()]
            token_contract = self.web3.eth.contract(
                address=token_address,
                abi=self.erc20_abi
            )

            # Check allowance
            allowance = token_contract.functions.allowance(
                self.wallet_address,
                ctoken.address
            ).call()

            token_amount = int(amount * 10**18)  # Assume 18 decimals for simplicity

            if allowance < token_amount:
                # Approve spending
                approve_tx = token_contract.functions.approve(
                    ctoken.address,
                    token_amount
                ).build_transaction({
                    'from': self.wallet_address,
                    'gas': 100000,
                    'gasPrice': self.web3.to_wei('20', 'gwei'),
                    'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
                })

                signed_approve = self.web3.eth.account.sign_transaction(approve_tx, self.private_key)
                approve_hash = self.web3.eth.send_raw_transaction(signed_approve.rawTransaction)

                print(f"Approval transaction: {approve_hash.hex()}")

                # Wait for approval confirmation
                self.web3.eth.wait_for_transaction_receipt(approve_hash)

            # Supply tokens
            transaction = ctoken.functions.mint(token_amount).build_transaction({
                'from': self.wallet_address,
                'gas': 200000,
                'gasPrice': self.web3.to_wei('20', 'gwei'),
                'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
            })

        # Sign and send transaction
        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"Supply transaction: {tx_hash.hex()}")

        # Wait for confirmation and return receipt
        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    def borrow_asset(self, token_symbol, amount):
        """Borrow assets from Compound"""
        ctoken_symbol = f'c{token_symbol.lower()}'

        if ctoken_symbol not in self.ctoken_contracts:
            raise ValueError(f"Unsupported token: {token_symbol}")

        ctoken = self.ctoken_contracts[ctoken_symbol]

        # Check borrowing capacity
        account_liquidity = self.get_account_liquidity()

        if account_liquidity['shortfall'] > 0:
            raise ValueError("Account has shortfall, cannot borrow")

        borrow_amount = int(amount * 10**18)  # Assume 18 decimals

        # Check if amount is within borrowing capacity
        token_price = self.get_token_price(token_symbol)
        borrow_value_usd = amount * token_price

        if borrow_value_usd > account_liquidity['liquidity']:
            raise ValueError(f"Borrow amount exceeds liquidity: {borrow_value_usd} > {account_liquidity['liquidity']}")

        # Execute borrow
        transaction = ctoken.functions.borrow(borrow_amount).build_transaction({
            'from': self.wallet_address,
            'gas': 200000,
            'gasPrice': self.web3.to_wei('20', 'gwei'),
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        })

        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"Borrow transaction: {tx_hash.hex()}")

        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    def get_account_liquidity(self):
        """Get account liquidity and borrowing capacity"""
        error, liquidity, shortfall = self.comptroller.functions.getAccountLiquidity(
            self.wallet_address
        ).call()

        if error != 0:
            raise ValueError(f"Error getting account liquidity: {error}")

        return {
            'liquidity': liquidity / 1e18,  # USD value of borrowing capacity
            'shortfall': shortfall / 1e18,  # USD value of shortfall
            'health_factor': float('inf') if shortfall == 0 else liquidity / shortfall if shortfall > 0 else float('inf')
        }

    def enable_collateral(self, ctoken_symbol):
        """Enable a cToken as collateral"""
        ctoken_address = COMPOUND_CONFIG[ctoken_symbol]

        # Check if already enabled
        assets_in = self.comptroller.functions.getAssetsIn(self.wallet_address).call()

        if ctoken_address not in assets_in:
            # Enable as collateral
            transaction = self.comptroller.functions.enterMarkets([ctoken_address]).build_transaction({
                'from': self.wallet_address,
                'gas': 150000,
                'gasPrice': self.web3.to_wei('20', 'gwei'),
                'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
            })

            signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

            print(f"Collateral enabled: {tx_hash.hex()}")

            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)
            return receipt

        print(f"{ctoken_symbol} already enabled as collateral")
        return None

# Initialize Compound
compound = CompoundExchange({
    'rpc_url': 'https://mainnet.infura.io/v3/YOUR_INFURA_KEY',
    'wallet_address': 'your_wallet_address',
    'private_key': 'your_private_key'
})
```

### 2. MakerDAO Integration

```python
# MakerDAO Configuration
MAKER_CONFIG = {
    'mcd_cat': '0xa5679C04fc3d9d8b0AaB1F0ab83555b301cA70Ea',     # Liquidation
    'mcd_vat': '0x35D1b3F3D7966A1DFe207aa4514C12a259A0492B',     # Core CDP engine
    'mcd_dai': '0x6B175474E89094C44Da98b954EedeAC495271d0F',     # DAI token
    'mcd_pot': '0x197E90f9FAD81970bA7976f33CbD77088E5D7cf7',     # DAI savings rate
    'mcd_join_dai': '0x9759A6Ac90977b93B58547b4A71c78317f391A28', # DAI join
    'mcd_jug': '0x19c0976f590D67707E62397C87829d896Dc0f1F1',     # Stability fees

    # Collateral joins
    'mcd_join_eth_a': '0x2F0b23f53734252Bda2277357e97e1517d6B042A',
    'mcd_join_wbtc_a': '0xBF72Da2Bd84c5170618Fbe5914B0ECA9638d5eb5',
    'mcd_join_usdc_a': '0xA191e578a6736167326d05c119CE0c90849E84B7',

    # Proxy actions
    'proxy_actions': '0x82ecD135Dce65Fbc6DbdD0e4237E0AF93FFD5038',
    'proxy_registry': '0x4678f0a6958e4D2Bc4F1BAF7Bc52E8F3564f3fE4'
}

class MakerDAOExchange:
    def __init__(self, config):
        self.web3 = Web3(Web3.HTTPProvider(config['rpc_url']))
        self.wallet_address = config['wallet_address']
        self.private_key = config['private_key']

        # Load ABIs
        self.vat_abi = self.load_abi('vat')
        self.dai_abi = self.load_abi('dai')
        self.pot_abi = self.load_abi('pot')
        self.proxy_actions_abi = self.load_abi('proxy_actions')

        # Initialize core contracts
        self.vat = self.web3.eth.contract(
            address=MAKER_CONFIG['mcd_vat'],
            abi=self.vat_abi
        )

        self.dai = self.web3.eth.contract(
            address=MAKER_CONFIG['mcd_dai'],
            abi=self.dai_abi
        )

        self.pot = self.web3.eth.contract(
            address=MAKER_CONFIG['mcd_pot'],
            abi=self.pot_abi
        )

        # Get or create DS-Proxy
        self.proxy_address = self.get_or_create_proxy()

    def get_vault_info(self, vault_id):
        """Get detailed information about a specific vault"""
        vault_data = self.vat.functions.urns(
            b'ETH-A',  # ilk (collateral type)
            self.proxy_address
        ).call()

        ink = vault_data[0] / 1e18  # Collateral amount
        art = vault_data[1] / 1e18  # Debt amount

        # Get collateralization ratio
        eth_price = self.get_eth_price()
        collateral_value = ink * eth_price
        collateralization_ratio = (collateral_value / art) if art > 0 else float('inf')

        # Get liquidation price
        liquidation_ratio = self.get_liquidation_ratio('ETH-A')
        liquidation_price = (art * liquidation_ratio) / ink if ink > 0 else 0

        return {
            'vault_id': vault_id,
            'collateral_eth': ink,
            'debt_dai': art,
            'collateral_value_usd': collateral_value,
            'collateralization_ratio': collateralization_ratio,
            'liquidation_price': liquidation_price,
            'liquidation_ratio': liquidation_ratio,
            'is_safe': collateralization_ratio > liquidation_ratio if art > 0 else True
        }

    def open_vault_and_draw_dai(self, eth_amount, dai_amount):
        """Open a new vault and draw DAI"""
        # Use DS-Proxy for complex transaction
        proxy_actions = self.web3.eth.contract(
            address=MAKER_CONFIG['proxy_actions'],
            abi=self.proxy_actions_abi
        )

        # Encode the openLockETHAndDraw call
        call_data = proxy_actions.encodeABI(
            fn_name='openLockETHAndDraw',
            args=[
                MAKER_CONFIG['mcd_join_eth_a'],  # ETH join adapter
                MAKER_CONFIG['mcd_join_dai'],    # DAI join adapter
                b'ETH-A',                        # Collateral type
                int(dai_amount * 1e18)           # DAI to draw (in wei)
            ]
        )

        # Execute through DS-Proxy
        transaction = {
            'from': self.wallet_address,
            'to': self.proxy_address,
            'value': self.web3.to_wei(eth_amount, 'ether'),
            'data': call_data,
            'gas': 500000,
            'gasPrice': self.web3.to_wei('30', 'gwei'),
            'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
        }

        signed_tx = self.web3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)

        print(f"Vault creation transaction: {tx_hash.hex()}")

        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash)

        # Parse events to get vault ID
        vault_id = self.parse_vault_id_from_receipt(receipt)

        return {
            'vault_id': vault_id,
            'transaction_hash': tx_hash.hex(),
            'collateral_deposited': eth_amount,
            'dai_drawn': dai_amount
        }

    def manage_vault_safety(self, vault_id, target_ratio=2.5):
        """Automatically manage vault safety by maintaining target collateralization ratio"""
        vault_info = self.get_vault_info(vault_id)

        current_ratio = vault_info['collateralization_ratio']
        liquidation_ratio = vault_info['liquidation_ratio']

        print(f"Current ratio: {current_ratio:.2f}")
        print(f"Target ratio: {target_ratio}")
        print(f"Liquidation ratio: {liquidation_ratio:.2f}")

        if current_ratio < target_ratio * 1.1:  # 10% buffer above target
            # Need to improve ratio
            if current_ratio < liquidation_ratio * 1.2:  # Danger zone
                print("🚨 URGENT: Vault near liquidation!")
                self.emergency_vault_protection(vault_id, vault_info)
            else:
                print("⚠️ Vault ratio below target, rebalancing...")
                self.rebalance_vault(vault_id, vault_info, target_ratio)

        elif current_ratio > target_ratio * 1.5:  # Much higher than target
            print("💰 Vault over-collateralized, optimizing...")
            self.optimize_vault_efficiency(vault_id, vault_info, target_ratio)

    def emergency_vault_protection(self, vault_id, vault_info):
        """Emergency protection for vaults near liquidation"""
        # Option 1: Add more ETH collateral
        additional_eth_needed = self.calculate_additional_collateral_needed(
            vault_info, target_ratio=2.0  # Safety target
        )

        eth_balance = self.web3.eth.get_balance(self.wallet_address) / 1e18

        if eth_balance >= additional_eth_needed:
            print(f"Adding {additional_eth_needed:.4f} ETH collateral")
            self.add_collateral(vault_id, additional_eth_needed)
        else:
            # Option 2: Repay some DAI debt
            dai_balance = self.dai.functions.balanceOf(self.wallet_address).call() / 1e18

            if dai_balance > 0:
                repay_amount = min(dai_balance, vault_info['debt_dai'] * 0.2)  # Repay up to 20%
                print(f"Repaying {repay_amount:.2f} DAI debt")
                self.repay_dai(vault_id, repay_amount)
            else:
                print("🚨 No ETH or DAI available for emergency protection!")
                # Consider liquidating other positions or external funding

    def stake_dai_in_dsr(self, dai_amount):
        """Stake DAI in the DAI Savings Rate (DSR)"""
        current_dsr = self.pot.functions.dsr().call()
        dsr_apy = ((current_dsr / 1e27) - 1) * (365 * 24 * 3600) / (365 * 24 * 3600) * 100

        print(f"Current DSR: {dsr_apy:.2f}% APY")

        if dsr_apy > 0.5:  # Only stake if DSR > 0.5%
            # Approve DAI spending
            approve_tx = self.dai.functions.approve(
                MAKER_CONFIG['mcd_pot'],
                int(dai_amount * 1e18)
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 100000,
                'gasPrice': self.web3.to_wei('20', 'gwei'),
                'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
            })

            signed_approve = self.web3.eth.account.sign_transaction(approve_tx, self.private_key)
            approve_hash = self.web3.eth.send_raw_transaction(signed_approve.rawTransaction)
            self.web3.eth.wait_for_transaction_receipt(approve_hash)

            # Join DSR
            join_tx = self.pot.functions.join(int(dai_amount * 1e18)).build_transaction({
                'from': self.wallet_address,
                'gas': 200000,
                'gasPrice': self.web3.to_wei('20', 'gwei'),
                'nonce': self.web3.eth.get_transaction_count(self.wallet_address)
            })

            signed_join = self.web3.eth.account.sign_transaction(join_tx, self.private_key)
            join_hash = self.web3.eth.send_raw_transaction(signed_join.rawTransaction)

            print(f"DAI staked in DSR: {join_hash.hex()}")

            receipt = self.web3.eth.wait_for_transaction_receipt(join_hash)
            return receipt

        print("DSR rate too low, not staking")
        return None

# Initialize MakerDAO
maker = MakerDAOExchange({
    'rpc_url': 'https://mainnet.infura.io/v3/YOUR_INFURA_KEY',
    'wallet_address': 'your_wallet_address',
    'private_key': 'your_private_key'
})
```

## Advanced DeFi Lending Strategies

### 1. Yield Optimization Strategy
```python
def defi_yield_optimization_strategy():
    """
    Automatically optimize yield across multiple DeFi lending platforms
    """
    print("📈 DeFi Yield Optimization Strategy")
    print("=" * 40)

    # Get current rates across platforms
    platforms = {
        'compound_usdc': compound.get_market_info('cusdc')['supply_apy'],
        'aave_usdc': aave.get_reserve_data('USDC')['supply_apy'],  # From previous Aave integration
        'maker_dsr': maker.get_current_dsr_rate(),
        'euler_usdc': euler.get_market_info('USDC')['supply_apy']
    }

    print("Current Yield Rates:")
    for platform, apy in platforms.items():
        print(f"  {platform}: {apy:.2f}% APY")

    # Find best yield opportunity
    best_platform = max(platforms, key=platforms.get)
    best_rate = platforms[best_platform]

    print(f"\n🏆 Best rate: {best_platform} at {best_rate:.2f}% APY")

    # Get current allocations
    current_allocations = get_current_defi_allocations()
    total_capital = sum(current_allocations.values())

    if total_capital > 1000:  # Minimum $1000 for optimization
        # Calculate optimal allocation
        optimal_allocation = calculate_optimal_yield_allocation(platforms, total_capital)

        # Execute rebalancing
        execute_yield_rebalancing(current_allocations, optimal_allocation)

def calculate_optimal_yield_allocation(rates, total_capital):
    """
    Calculate optimal capital allocation across lending platforms
    """
    # Simple allocation: 70% to best rate, 30% to second best (diversification)
    sorted_platforms = sorted(rates.items(), key=lambda x: x[1], reverse=True)

    allocation = {}
    allocation[sorted_platforms[0][0]] = total_capital * 0.7  # 70% to best
    allocation[sorted_platforms[1][0]] = total_capital * 0.3  # 30% to second best

    print(f"\nOptimal Allocation:")
    for platform, amount in allocation.items():
        percentage = (amount / total_capital) * 100
        print(f"  {platform}: ${amount:,.2f} ({percentage:.0f}%)")

    return allocation

def execute_yield_rebalancing(current, optimal):
    """
    Execute rebalancing between lending platforms
    """
    print("\nREBALANCING: Executing Yield Rebalancing:")

    for platform, target_amount in optimal.items():
        current_amount = current.get(platform, 0)
        difference = target_amount - current_amount

        if abs(difference) > 100:  # Only rebalance if difference > $100
            if difference > 0:
                # Need to add capital to this platform
                print(f"  Adding ${difference:,.2f} to {platform}")
                add_capital_to_platform(platform, difference)
            else:
                # Need to remove capital from this platform
                print(f"  Removing ${abs(difference):,.2f} from {platform}")
                remove_capital_from_platform(platform, abs(difference))

def add_capital_to_platform(platform, amount):
    """Add capital to specific lending platform"""
    if platform.startswith('compound'):
        token = platform.split('_')[1]
        compound.supply_asset(token, amount)
    elif platform.startswith('maker'):
        maker.stake_dai_in_dsr(amount)
    elif platform.startswith('aave'):
        token = platform.split('_')[1]
        aave.supply(token, amount)
    elif platform.startswith('euler'):
        token = platform.split('_')[1]
        euler.supply(token, amount)
```

### 2. Leveraged Yield Farming Strategy
```python
def leveraged_yield_farming_strategy():
    """
    Advanced leveraged yield farming across multiple protocols
    """
    print("⚡ Leveraged Yield Farming Strategy")
    print("=" * 35)

    # Step 1: Supply ETH as collateral on Compound
    eth_amount = 2.0  # 2 ETH
    compound.supply_asset('ETH', eth_amount)
    compound.enable_collateral('ceth')

    print(f"✅ Supplied {eth_amount} ETH as collateral")

    # Step 2: Borrow stablecoins against ETH
    account_liquidity = compound.get_account_liquidity()
    max_borrow_usd = account_liquidity['liquidity'] * 0.8  # 80% of max for safety

    # Borrow USDC
    usdc_borrow_amount = max_borrow_usd
    compound.borrow_asset('USDC', usdc_borrow_amount)

    print(f"✅ Borrowed {usdc_borrow_amount:,.2f} USDC")

    # Step 3: Deploy borrowed USDC for higher yield
    deployment_strategies = [
        {
            'platform': 'curve_3pool',
            'allocation': 0.5,
            'expected_apy': 8.5,
            'strategy': 'Curve 3Pool LP + Convex rewards'
        },
        {
            'platform': 'yearn_usdc_vault',
            'allocation': 0.3,
            'expected_apy': 7.2,
            'strategy': 'Yearn USDC Vault auto-compounding'
        },
        {
            'platform': 'aave_usdc',
            'allocation': 0.2,
            'expected_apy': 5.8,
            'strategy': 'Aave USDC lending for safety'
        }
    ]

    total_deployed = 0
    for strategy in deployment_strategies:
        deploy_amount = usdc_borrow_amount * strategy['allocation']

        print(f"📊 Deploying ${deploy_amount:,.2f} to {strategy['platform']}")
        print(f"   Expected APY: {strategy['expected_apy']:.1f}%")

        # Deploy capital based on strategy
        if strategy['platform'] == 'curve_3pool':
            deploy_to_curve_3pool(deploy_amount)
        elif strategy['platform'] == 'yearn_usdc_vault':
            deploy_to_yearn_vault(deploy_amount, 'USDC')
        elif strategy['platform'] == 'aave_usdc':
            aave.supply('USDC', deploy_amount)

        total_deployed += deploy_amount

    # Calculate net APY
    borrow_cost = compound.get_market_info('cusdc')['borrow_apy']
    weighted_yield = sum(s['allocation'] * s['expected_apy'] for s in deployment_strategies)
    net_apy = weighted_yield - borrow_cost

    print(f"\n📈 Strategy Summary:")
    print(f"   Total Deployed: ${total_deployed:,.2f}")
    print(f"   Borrow Cost: {borrow_cost:.2f}% APY")
    print(f"   Weighted Yield: {weighted_yield:.2f}% APY")
    print(f"   Net APY: {net_apy:.2f}% APY")

    if net_apy > 3:  # Profitable if net APY > 3%
        print("✅ Strategy is profitable!")
        monitor_leveraged_position()
    else:
        print("⚠️ Strategy may not be profitable")

def monitor_leveraged_position():
    """
    Continuously monitor leveraged position for safety
    """
    print("🔍 Monitoring Leveraged Position")

    while True:
        # Check health factor
        account_liquidity = compound.get_account_liquidity()
        health_factor = account_liquidity['health_factor']

        print(f"Health Factor: {health_factor:.2f}")

        if health_factor < 1.3:  # Danger zone
            print("🚨 Low health factor! Taking protective action...")
            emergency_deleverage()
            break
        elif health_factor < 1.5:  # Warning zone
            print("⚠️ Health factor declining, reducing leverage...")
            partial_deleverage(0.3)  # Reduce leverage by 30%

        # Check if yield strategies are still profitable
        current_yields = get_current_strategy_yields()
        borrow_cost = compound.get_market_info('cusdc')['borrow_apy']

        weighted_current_yield = calculate_weighted_yield(current_yields)

        if weighted_current_yield - borrow_cost < 1:  # Less than 1% net APY
            print("📉 Yields declined, considering position closure...")
            close_leveraged_position()
            break

        time.sleep(300)  # Check every 5 minutes

def emergency_deleverage():
    """Emergency deleveraging when health factor is critical"""
    print("🚨 EMERGENCY DELEVERAGING")

    # Quickly withdraw from highest liquidity strategy first
    strategy_liquidities = {
        'aave_usdc': 0.9,      # Highest liquidity
        'yearn_usdc_vault': 0.7,  # Medium liquidity
        'curve_3pool': 0.5     # Lower liquidity (due to IL risk)
    }

    for strategy, liquidity_score in sorted(strategy_liquidities.items(), key=lambda x: x[1], reverse=True):
        try:
            withdraw_amount = get_strategy_balance(strategy)
            withdraw_from_strategy(strategy, withdraw_amount)

            # Repay debt immediately
            compound.repay_asset('USDC', withdraw_amount)

            # Check if health factor is now safe
            if compound.get_account_liquidity()['health_factor'] > 1.5:
                break

        except Exception as e:
            print(f"Error withdrawing from {strategy}: {e}")
            continue
```

### 3. Cross-Protocol Arbitrage
```python
def cross_protocol_arbitrage():
    """
    Arbitrage lending rates across different DeFi protocols
    """
    print("ARBITRAGE: Cross-Protocol Arbitrage Strategy")
    print("=" * 35)

    # Get borrowing and lending rates across protocols
    protocols = {
        'compound': {
            'supply_apy': compound.get_market_info('cusdc')['supply_apy'],
            'borrow_apy': compound.get_market_info('cusdc')['borrow_apy']
        },
        'aave': {
            'supply_apy': aave.get_reserve_data('USDC')['supply_apy'],
            'borrow_apy': aave.get_reserve_data('USDC')['borrow_apy']
        },
        'euler': {
            'supply_apy': euler.get_market_info('USDC')['supply_apy'],
            'borrow_apy': euler.get_market_info('USDC')['borrow_apy']
        }
    }

    # Find arbitrage opportunities
    arbitrage_opportunities = []

    for borrow_protocol, borrow_data in protocols.items():
        for supply_protocol, supply_data in protocols.items():
            if borrow_protocol != supply_protocol:
                spread = supply_data['supply_apy'] - borrow_data['borrow_apy']

                if spread > 0.5:  # Minimum 0.5% spread for profitability
                    arbitrage_opportunities.append({
                        'borrow_from': borrow_protocol,
                        'supply_to': supply_protocol,
                        'spread': spread,
                        'borrow_rate': borrow_data['borrow_apy'],
                        'supply_rate': supply_data['supply_apy']
                    })

    # Execute most profitable arbitrage
    if arbitrage_opportunities:
        best_arbitrage = max(arbitrage_opportunities, key=lambda x: x['spread'])

        print(f"🎯 Best Arbitrage Opportunity:")
        print(f"   Borrow from: {best_arbitrage['borrow_from']} at {best_arbitrage['borrow_rate']:.2f}%")
        print(f"   Supply to: {best_arbitrage['supply_to']} at {best_arbitrage['supply_rate']:.2f}%")
        print(f"   Spread: {best_arbitrage['spread']:.2f}%")

        # Execute arbitrage
        arbitrage_amount = 10000  # $10,000 USDC

        execute_cross_protocol_arbitrage(
            best_arbitrage['borrow_from'],
            best_arbitrage['supply_to'],
            arbitrage_amount
        )
    else:
        print("No profitable arbitrage opportunities found")

def execute_cross_protocol_arbitrage(borrow_protocol, supply_protocol, amount):
    """Execute cross-protocol arbitrage"""
    print(f"⚡ Executing arbitrage: {amount:,.0f} USDC")

    # Step 1: Borrow from cheaper protocol
    if borrow_protocol == 'compound':
        compound.borrow_asset('USDC', amount)
    elif borrow_protocol == 'aave':
        aave.borrow('USDC', amount)
    elif borrow_protocol == 'euler':
        euler.borrow('USDC', amount)

    print(f"✅ Borrowed ${amount:,.0f} from {borrow_protocol}")

    # Step 2: Supply to higher-yield protocol
    if supply_protocol == 'compound':
        compound.supply_asset('USDC', amount)
    elif supply_protocol == 'aave':
        aave.supply('USDC', amount)
    elif supply_protocol == 'euler':
        euler.supply('USDC', amount)

    print(f"✅ Supplied ${amount:,.0f} to {supply_protocol}")

    # Step 3: Monitor position and close when spread narrows
    monitor_arbitrage_position(borrow_protocol, supply_protocol, amount)
```

## Environment Configuration

Add to your `.env` file:

```bash
# DeFi Lending Configuration
COMPOUND_RPC_URL=https://mainnet.infura.io/v3/YOUR_INFURA_KEY
COMPOUND_WALLET_ADDRESS=your_wallet_address
COMPOUND_PRIVATE_KEY=your_private_key

# MakerDAO Configuration
MAKER_RPC_URL=https://mainnet.infura.io/v3/YOUR_INFURA_KEY
MAKER_WALLET_ADDRESS=your_wallet_address
MAKER_PRIVATE_KEY=your_private_key
MAKER_PROXY_ADDRESS=your_ds_proxy_address

# Risk Management
DEFI_MAX_LEVERAGE=3.0
DEFI_MIN_HEALTH_FACTOR=1.5
DEFI_AUTO_REBALANCE=true
DEFI_YIELD_OPTIMIZATION_INTERVAL=3600

# Strategy Parameters
DEFI_MIN_APY_SPREAD=0.5
DEFI_MIN_ARBITRAGE_AMOUNT=1000
DEFI_EMERGENCY_DELEVERAGE_THRESHOLD=1.2
```

This comprehensive DeFi lending documentation provides full integration capabilities for major lending protocols with advanced strategies including yield optimization, leveraged farming, and cross-protocol arbitrage within PowerTraderAI+.
