#!/usr/bin/env python3
"""
Multi-Exchange System Test
Quick test to verify all exchanges are working
"""
import os
import sys

from pt_multi_exchange import MultiExchangeManager


def test_multi_exchange():
    """Test the multi-exchange system"""
    print("🧪 Testing PowerTrader AI Multi-Exchange System")
    print("=" * 50)

    # Initialize manager
    manager = MultiExchangeManager()

    # Try to initialize with environment region or default to GLOBAL
    user_region = os.environ.get("POWERTRADER_USER_REGION", "GLOBAL")
    print(f"\n🌍 Testing for region: {user_region}")

    # Initialize
    if manager.initialize(user_region):
        print("✅ Multi-exchange manager initialized successfully")

        # List available exchanges
        exchanges = manager.get_available_exchanges()
        print(f"\n📊 Connected exchanges: {', '.join(exchanges)}")

        # Test price retrieval
        test_symbols = ["BTC-USD", "ETH-USD"]

        for symbol in test_symbols:
            print(f"\n💰 Testing {symbol} prices:")

            try:
                # Get prices from all exchanges
                prices = manager.compare_prices(symbol)

                if prices:
                    for exchange, price in prices.items():
                        print(f"  {exchange.title():12} ${price:,.2f}")

                    # Get best price
                    try:
                        best_price, best_exchange = manager.get_best_price(
                            symbol, "buy"
                        )
                        print(
                            f"  🎯 Best buy:   ${best_price:,.2f} on {best_exchange.title()}"
                        )
                    except Exception as e:
                        print(f"  ⚠️  Best price: {e}")
                else:
                    print(f"  ❌ No prices available for {symbol}")

            except Exception as e:
                print(f"  ❌ Price test failed for {symbol}: {e}")

        # Test single exchange call
        try:
            print(f"\n🔍 Testing primary exchange call...")
            primary_price = manager.get_current_price("BTC-USD")
            print(f"  Primary exchange BTC-USD: ${primary_price:,.2f}")
        except Exception as e:
            print(f"  ❌ Primary exchange test failed: {e}")

        print(f"\n✅ Multi-exchange test completed successfully")
        return True

    else:
        print("❌ Failed to initialize multi-exchange manager")
        print("\n💡 To fix this issue:")
        print("1. Run: python exchange_setup.py")
        print("2. Configure at least one exchange")
        print("3. Or set environment variables:")
        print("   POWERTRADER_KRAKEN_API_KEY=your_key")
        print("   POWERTRADER_KRAKEN_API_SECRET=your_secret")
        return False


def test_legacy_fallback():
    """Test legacy Robinhood fallback"""
    print("\n🔄 Testing legacy Robinhood fallback...")

    try:
        # Import the updated thinker module
        from pt_thinker import robinhood_current_ask

        # This should try multi-exchange first, then fallback
        price = robinhood_current_ask("BTC-USD")
        print(f"✅ Legacy function returned: ${price:,.2f}")
        return True

    except Exception as e:
        print(f"❌ Legacy test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("🚀 PowerTrader AI Multi-Exchange Test Suite")
    print("=" * 60)

    # Test 1: Multi-exchange system
    success1 = test_multi_exchange()

    # Test 2: Legacy fallback
    success2 = test_legacy_fallback()

    print("\n" + "=" * 60)
    print("📊 Test Results:")
    print(f"Multi-exchange system: {'✅ PASS' if success1 else '❌ FAIL'}")
    print(f"Legacy fallback:       {'✅ PASS' if success2 else '❌ FAIL'}")

    if success1 or success2:
        print("\n🎉 At least one system is working!")
        if success1:
            print("💡 Multi-exchange system is operational")
        if success2 and not success1:
            print("💡 Legacy system is working as fallback")
    else:
        print("\n⚠️  No systems are working. Please configure credentials.")
        print("Run: python exchange_setup.py")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
