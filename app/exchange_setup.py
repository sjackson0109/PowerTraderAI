#!/usr/bin/env python3
"""
PowerTraderAI+ Exchange Configuration Tool
Setup and manage multiple cryptocurrency exchanges
"""
import os
import sys
from typing import List, Optional

from pt_exchange_abstraction import ExchangeType
from pt_multi_exchange import ExchangeConfigManager, MultiExchangeManager


def print_header():
    """Print tool header"""
    print("\n" + "=" * 60)
    print("PowerTraderAI+ - Exchange Configuration Tool")
    print("=" * 60)


def print_available_exchanges():
    """Print all available exchanges by region"""
    print("\n📊 Available Exchanges by Region:")
    print("\n🇺🇸 United States:")
    print("  • Robinhood (US Crypto Trading)")
    print("  • Coinbase Advanced Trade")
    print("  • Kraken (Global)")
    print("  • Binance (Check local regulations)")
    print("  • KuCoin (Global)")

    print("\n🇪🇺 European Union:")
    print("  • Kraken (EU-based)")
    print("  • Binance (EU regulations apply)")
    print("  • Coinbase (EU)")
    print("  • Bitstamp (EU-regulated)")
    print("  • KuCoin (Global)")

    print("\n🇬🇧 United Kingdom:")
    print("  • Kraken (Post-Brexit approved)")
    print("  • Coinbase (UK)")
    print("  • Binance (Check FCA regulations)")
    print("  • KuCoin (Global)")

    print("\n🌍 Global (Check local laws):")
    print("  • Binance (Largest global exchange)")
    print("  • KuCoin (Wide availability)")
    print("  • Bybit (Derivatives focus)")
    print("  • OKX (Global platform)")


def get_user_region() -> str:
    """Get user's region"""
    print("\n🌍 Select your region:")
    print("1. United States (US)")
    print("2. European Union (EU)")
    print("3. United Kingdom (UK)")
    print("4. Global/Other")

    while True:
        choice = input("\nEnter your choice (1-4): ").strip()
        if choice == "1":
            return "US"
        elif choice == "2":
            return "EU"
        elif choice == "3":
            return "UK"
        elif choice == "4":
            return "GLOBAL"
        else:
            print("Invalid choice. Please enter 1, 2, 3, or 4.")


def setup_exchange_credentials(
    config_manager: ExchangeConfigManager, exchange_name: str
):
    """Setup credentials for a specific exchange"""
    print(f"\n🔑 Setting up {exchange_name.title()} API credentials")
    print("━" * 50)

    # Exchange-specific instructions
    if exchange_name == "robinhood":
        print("Robinhood Crypto Trading API Setup:")
        print("1. Go to: https://robinhood.com/crypto/trading/api")
        print("2. Navigate: Settings → Crypto → API Trading")
        print("3. Generate keypair and upload public key")
        print("4. Copy your API key (starts with 'rh_crypto_')")
        print("5. Convert your private key to Base64 format")

    elif exchange_name == "kraken":
        print("Kraken API Setup:")
        print("1. Go to: https://www.kraken.com/u/security/api")
        print("2. Create new API key")
        print("3. Enable required permissions (Query Funds, Create Orders)")
        print("4. Copy API Key and Private Key")

    elif exchange_name == "binance":
        print("Binance API Setup:")
        print("1. Go to: https://www.binance.com/en/my/settings/api-management")
        print("2. Create new API key")
        print("3. Enable Spot & Margin Trading")
        print("4. Copy API Key and Secret Key")
        print("⚠️  Check local regulations before using Binance")

    elif exchange_name == "coinbase":
        print("Coinbase Advanced Trade API Setup:")
        print("1. Go to: https://www.coinbase.com/settings/api")
        print("2. Create new API key")
        print("3. Enable trading permissions")
        print("4. Copy API Key and Secret")

    elif exchange_name == "kucoin":
        print("KuCoin API Setup:")
        print("1. Go to: https://www.kucoin.com/account/api")
        print("2. Create new API key")
        print("3. Enable General and Trade permissions")
        print("4. Copy API Key, Secret, and Passphrase")

    print("\n" + "━" * 50)

    # Get credentials
    api_key = input(f"Enter {exchange_name.title()} API Key: ").strip()
    if not api_key:
        print("❌ API Key is required")
        return False

    api_secret = input(f"Enter {exchange_name.title()} API Secret: ").strip()
    if not api_secret:
        print("❌ API Secret is required")
        return False

    passphrase = ""
    if exchange_name == "kucoin":
        passphrase = input("Enter KuCoin API Passphrase: ").strip()
        if not passphrase:
            print("❌ Passphrase is required for KuCoin")
            return False

    # Update configuration
    config_manager.update_exchange_credentials(
        exchange_name, api_key, api_secret, passphrase
    )
    config_manager.enable_exchange(exchange_name, True)

    print(f"✅ {exchange_name.title()} credentials saved and enabled")
    return True


def configure_exchanges(config_manager: ExchangeConfigManager):
    """Interactive exchange configuration"""
    config = config_manager.load_config()
    if not config:
        region = get_user_region()
        config = config_manager.create_default_config(region)
        print(f"\n✅ Created default configuration for {region}")

    print(f"\n📋 Current configuration:")
    print(f"Region: {config.user_region}")
    print(f"Primary exchange: {config.primary_exchange}")

    print(f"\nExchanges:")
    for ex in config.exchanges:
        status = "✅ Enabled" if ex.enabled else "❌ Disabled"
        cred_status = "🔑 Configured" if ex.api_key else "❌ No credentials"
        print(f"  {ex.exchange_type.title():12} - {status} - {cred_status}")

    print(f"\n⚙️  Configuration Menu:")
    print("1. Setup exchange credentials")
    print("2. Enable/disable exchange")
    print("3. Set primary exchange")
    print("4. Test connections")
    print("5. Save and exit")
    print("6. Exit without saving")

    while True:
        choice = input("\nSelect option (1-6): ").strip()

        if choice == "1":
            # Setup credentials
            print("\nAvailable exchanges:")
            for i, ex in enumerate(config.exchanges, 1):
                print(f"{i}. {ex.exchange_type.title()}")

            try:
                ex_choice = int(input("Select exchange to configure (number): ")) - 1
                if 0 <= ex_choice < len(config.exchanges):
                    exchange_name = config.exchanges[ex_choice].exchange_type
                    setup_exchange_credentials(config_manager, exchange_name)
                    config = config_manager.load_config()  # Reload
                else:
                    print("❌ Invalid exchange number")
            except ValueError:
                print("❌ Please enter a valid number")

        elif choice == "2":
            # Enable/disable exchange
            print("\nExchanges:")
            for i, ex in enumerate(config.exchanges, 1):
                status = "Enabled" if ex.enabled else "Disabled"
                print(f"{i}. {ex.exchange_type.title()} - {status}")

            try:
                ex_choice = int(input("Select exchange to toggle (number): ")) - 1
                if 0 <= ex_choice < len(config.exchanges):
                    exchange = config.exchanges[ex_choice]
                    new_status = not exchange.enabled
                    config_manager.enable_exchange(exchange.exchange_type, new_status)
                    action = "enabled" if new_status else "disabled"
                    print(f"✅ {exchange.exchange_type.title()} {action}")
                    config = config_manager.load_config()  # Reload
                else:
                    print("❌ Invalid exchange number")
            except ValueError:
                print("❌ Please enter a valid number")

        elif choice == "3":
            # Set primary exchange
            enabled_exchanges = [
                ex for ex in config.exchanges if ex.enabled and ex.api_key
            ]
            if not enabled_exchanges:
                print("❌ No enabled exchanges with credentials found")
                continue

            print("\nEnabled exchanges with credentials:")
            for i, ex in enumerate(enabled_exchanges, 1):
                print(f"{i}. {ex.exchange_type.title()}")

            try:
                ex_choice = int(input("Select primary exchange (number): ")) - 1
                if 0 <= ex_choice < len(enabled_exchanges):
                    new_primary = enabled_exchanges[ex_choice].exchange_type
                    config.primary_exchange = new_primary
                    config_manager.save_config(config)
                    print(f"✅ Primary exchange set to {new_primary.title()}")
                else:
                    print("❌ Invalid exchange number")
            except ValueError:
                print("❌ Please enter a valid number")

        elif choice == "4":
            # Test connections
            print("\n🔍 Testing exchange connections...")
            manager = MultiExchangeManager(config_manager)
            if manager.initialize():
                print("✅ Multi-exchange manager initialized successfully")

                # Test price retrieval
                test_symbol = "BTC-USD"
                try:
                    prices = manager.compare_prices(test_symbol)
                    if prices:
                        print(f"\n💰 Current {test_symbol} prices:")
                        for exchange, price in prices.items():
                            print(f"  {exchange.title():12} ${price:,.2f}")

                        # Show best price
                        best_price, best_exchange = manager.get_best_price(
                            test_symbol, "buy"
                        )
                        print(
                            f"\n🎯 Best buy price: ${best_price:,.2f} on {best_exchange.title()}"
                        )
                    else:
                        print("❌ No price data available")
                except Exception as e:
                    print(f"❌ Price test failed: {e}")
            else:
                print("❌ Failed to initialize exchanges")
                print("Check your credentials and try again")

        elif choice == "5":
            print("✅ Configuration saved. Exiting...")
            break

        elif choice == "6":
            print("❌ Exiting without saving...")
            break

        else:
            print("❌ Invalid choice. Please enter 1-6.")


def main():
    """Main configuration tool"""
    print_header()

    # Check if we're in the right directory
    if not os.path.exists("pt_multi_exchange.py"):
        print("❌ Error: Please run this tool from the PowerTraderAI+ app directory")
        print("Expected files: pt_multi_exchange.py, pt_exchanges.py")
        return

    print("\n🚀 Welcome to PowerTraderAI+ Exchange Configuration!")
    print("\nThis tool helps you:")
    print("• Configure multiple exchange APIs")
    print("• Set regional preferences")
    print("• Test connections")
    print("• Compare prices across exchanges")

    print_available_exchanges()

    config_manager = ExchangeConfigManager()
    configure_exchanges(config_manager)

    print("\n🎉 Configuration complete!")
    print("\nNext steps:")
    print("1. Run PowerTraderAI+ with: python pt_hub.py")
    print("2. Your configured exchanges will be available")
    print("3. Price comparison and best execution enabled")
    print("\n💡 Tip: You can re-run this tool anytime to update settings")


if __name__ == "__main__":
    main()
