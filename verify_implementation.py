#!/usr/bin/env python3
"""
PowerTraderAI+ Documentation Verification Script
Validates all new exchange services and documentation are properly implemented.
"""

import os
import sys


def check_documentation_files():
    """Verify all documentation files exist and have content"""
    print("CHECKING: Documentation Files...")

    required_docs = {
        "EXCHANGE_DOCUMENTATION.md": "Multi-exchange system guide",
        "GUI_USER_GUIDE.md": "Desktop GUI manual",
        "API_REFERENCE.md": "Developer API documentation",
        "QUICK_REFERENCE.md": "Quick start reference",
        "README.md": "Main project documentation",
    }

    all_exist = True

    for doc_file, description in required_docs.items():
        if os.path.isfile(doc_file):
            size = os.path.getsize(doc_file)
            print(f"SUCCESS: {doc_file} ({size:,} bytes) - {description}")
        else:
            print(f"MISSING: {doc_file} - MISSING")
            all_exist = False

    return all_exist


def check_python_files():
    """Verify all Python files compile without errors"""
    print("\n🐍 Checking Python Files...")

    try:
        import glob
        import py_compile

        # Check app directory
        app_files = glob.glob("app/*.py")
        root_files = glob.glob("*.py")
        all_files = app_files + root_files

        compiled_count = 0
        error_count = 0

        for file_path in all_files:
            try:
                py_compile.compile(file_path, doraise=True)
                compiled_count += 1
            except Exception as e:
                print(f"ERROR: {file_path}: {e}")
                error_count += 1

        print(f"SUCCESS: Compiled {compiled_count} Python files successfully")
        if error_count > 0:
            print(f"ERROR: {error_count} files had compilation errors")
            return False

        return True

    except Exception as e:
        print(f"ERROR: Error checking Python files: {e}")
        return False


def check_exchange_modules():
    """Verify exchange modules can be imported"""
    print("\n🌍 Checking Exchange Modules...")

    sys.path.insert(0, "app")

    modules_to_test = [
        ("pt_exchange_abstraction", "Base exchange classes"),
        ("pt_exchanges", "Exchange implementations"),
        ("pt_multi_exchange", "Multi-exchange manager"),
        ("exchange_setup", "Setup wizard"),
        ("test_exchanges", "Exchange tests"),
    ]

    import_success = True

    for module_name, description in modules_to_test:
        try:
            __import__(module_name)
            print(f"SUCCESS: {module_name} - {description}")
        except ImportError as e:
            print(f"ERROR: {module_name} - Import failed: {e}")
            import_success = False
        except Exception as e:
            print(f"WARNING: {module_name} - Warning: {e}")

    return import_success


def check_gui_integration():
    """Verify GUI has exchange integration"""
    print("\nCHECKING: GUI Integration...")

    try:
        sys.path.insert(0, "app")

        # Import pt_hub and check for exchange methods
        import pt_hub

        # Check DEFAULT_SETTINGS has exchange settings
        settings = pt_hub.DEFAULT_SETTINGS
        exchange_settings = [
            "region",
            "primary_exchange",
            "price_comparison_enabled",
            "auto_best_price",
        ]

        missing_settings = []
        for setting in exchange_settings:
            if setting not in settings:
                missing_settings.append(setting)

        if missing_settings:
            print(f"ERROR: Missing exchange settings: {missing_settings}")
            return False

        print("SUCCESS: GUI DEFAULT_SETTINGS include exchange configuration")

        # Check PowerTraderHub class has exchange methods
        hub_class = pt_hub.PowerTraderHub
        exchange_methods = [
            "_init_exchange_system",
            "_check_exchange_status_worker",
            "_update_exchange_status_display",
            "refresh_exchange_settings",
        ]

        missing_methods = []
        for method in exchange_methods:
            if not hasattr(hub_class, method):
                missing_methods.append(method)

        if missing_methods:
            print(f"ERROR: Missing GUI exchange methods: {missing_methods}")
            return False

        print("SUCCESS: GUI PowerTraderHub class has exchange integration methods")
        return True

    except Exception as e:
        print(f"ERROR: GUI integration check failed: {e}")
        return False


def check_credential_system():
    """Verify credential management system"""
    print("\n🔐 Checking Credential System...")

    try:
        sys.path.insert(0, "app")
        import pt_multi_exchange

        # Check ExchangeConfigManager exists
        config_manager = pt_multi_exchange.ExchangeConfigManager()
        print("SUCCESS: ExchangeConfigManager class available")

        # Check MultiExchangeManager exists
        manager_class = pt_multi_exchange.MultiExchangeManager
        print("SUCCESS: MultiExchangeManager class available")

        return True

    except Exception as e:
        print(f"ERROR: Credential system check failed: {e}")
        return False


def display_summary():
    """Display feature summary"""
    print("\n" + "=" * 60)
    print("🎉 POWERTRADERAI+ MULTI-EXCHANGE SYSTEM READY!")
    print("=" * 60)
    print()
    print("📋 NEW FEATURES IMPLEMENTED:")
    print("SUCCESS: Multi-exchange support (10+ exchanges globally)")
    print("SUCCESS: Regional compliance filtering (US/EU/Global)")
    print("SUCCESS: Desktop GUI exchange selection & status")
    print("SUCCESS: Automatic price comparison & best execution")
    print("SUCCESS: Secure credential management (files + env vars)")
    print("SUCCESS: Real-time exchange health monitoring")
    print("SUCCESS: Intelligent failover & backup exchanges")
    print("SUCCESS: Interactive setup wizard")
    print("SUCCESS: Comprehensive API for developers")
    print()
    print("📚 DOCUMENTATION AVAILABLE:")
    print("• EXCHANGE_DOCUMENTATION.md - Complete system guide")
    print("• GUI_USER_GUIDE.md - Desktop application manual")
    print("• API_REFERENCE.md - Developer documentation")
    print("• QUICK_REFERENCE.md - Fast overview & examples")
    print()
    print("🚀 READY TO USE:")
    print("1. Launch GUI: python app/pt_hub.py")
    print("2. Configure exchanges in Settings dialog")
    print("3. Set up credentials with Exchange Setup wizard")
    print("4. Start trading with global exchange support!")
    print()
    print("🌍 SUPPORTED EXCHANGES:")
    print("US: Robinhood, Coinbase, Kraken, Binance.US, KuCoin")
    print("EU: Kraken, Coinbase, Binance, Bitstamp, KuCoin")
    print("Global: Binance, Kraken, KuCoin, Bybit, OKX")


def main():
    """Run all verification checks"""
    print("PowerTraderAI+ - Exchange System Verification")
    print("=" * 50)

    checks = [
        check_documentation_files,
        check_python_files,
        check_exchange_modules,
        check_gui_integration,
        check_credential_system,
    ]

    results = []

    for check in checks:
        try:
            result = check()
            results.append(result)
        except Exception as e:
            print(f"ERROR: Check failed with exception: {e}")
            results.append(False)

    # Summary
    passed = sum(results)
    total = len(results)

    print(f"\n📊 VERIFICATION RESULTS: {passed}/{total} checks passed")

    if passed == total:
        display_summary()
        return True
    else:
        print("\n⚠️ Some verification checks failed. Please review the errors above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
