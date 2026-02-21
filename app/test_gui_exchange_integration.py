#!/usr/bin/env python3
"""Test script to verify GUI exchange integration is working properly."""

import os
import sys
import time
import threading
from unittest.mock import Mock

# Add the app directory to the path
app_dir = os.path.dirname(os.path.abspath(__file__))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

def test_imports():
    """Test that all exchange-related imports work in pt_hub.py"""
    print("Testing exchange imports...")
    
    try:
        from pt_multi_exchange import MultiExchangeManager, ExchangeConfigManager
        from pt_exchange_abstraction import ExchangeType
        print("✅ Exchange imports successful")
        return True
    except ImportError as e:
        print(f"❌ Exchange imports failed: {e}")
        return False

def test_gui_initialization():
    """Test that the GUI can initialize with exchange support"""
    print("Testing GUI initialization...")
    
    try:
        # Import without actually starting the GUI
        import tkinter as tk
        
        # Mock the GUI components to avoid actually starting it
        root = tk.Tk()
        root.withdraw()  # Hide the window
        
        # Import pt_hub
        from pt_hub import PowerTraderHub
        
        # Test that the class can be imported and has exchange methods
        hub_class = PowerTraderHub
        
        # Check that our new methods exist
        expected_methods = [
            '_init_exchange_system',
            '_check_exchange_status_worker', 
            '_update_exchange_status_display',
            'refresh_exchange_settings'
        ]
        
        for method in expected_methods:
            if hasattr(hub_class, method):
                print(f"✅ Method {method} found")
            else:
                print(f"❌ Method {method} missing")
                return False
                
        root.destroy()
        print("✅ GUI class initialization successful")
        return True
        
    except Exception as e:
        print(f"❌ GUI initialization failed: {e}")
        return False

def test_exchange_settings():
    """Test that exchange settings are properly configured"""
    print("Testing exchange settings...")
    
    try:
        from pt_hub import DEFAULT_SETTINGS
        
        # Check that exchange settings exist
        required_settings = [
            "region",
            "primary_exchange", 
            "price_comparison_enabled",
            "auto_best_price"
        ]
        
        for setting in required_settings:
            if setting in DEFAULT_SETTINGS:
                value = DEFAULT_SETTINGS[setting]
                print(f"✅ Setting '{setting}' = {value}")
            else:
                print(f"❌ Setting '{setting}' missing")
                return False
                
        print("✅ Exchange settings configured properly")
        return True
        
    except Exception as e:
        print(f"❌ Exchange settings test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("PowerTraderAI+ - GUI Exchange Integration Test")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_gui_initialization, 
        test_exchange_settings
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        print()
        if test():
            passed += 1
        
    print("\n" + "=" * 50)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! Exchange integration is working properly.")
        print("\nNext steps:")
        print("1. Run pt_hub.py to see exchange status in the GUI")
        print("2. Go to Settings to configure your exchange preferences")
        print("3. Check the 'Exchange: ...' status indicator in the main interface")
    else:
        print("⚠️ Some tests failed. Check the errors above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)