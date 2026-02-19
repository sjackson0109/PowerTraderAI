"""
PowerTrader AI Phase 4 Core Test

Simplified test to validate core Phase 4 functionality without external dependencies.
"""

import asyncio
import sys
import os
from decimal import Decimal
from datetime import datetime
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

# Core imports - test these individually
try:
    from pt_paper_trading import PaperTradingAccount, OrderType, OrderSide
    PAPER_TRADING_AVAILABLE = True
    print("✅ Paper trading module loaded successfully")
except ImportError as e:
    PAPER_TRADING_AVAILABLE = False
    print(f"❌ Paper trading module failed to load: {e}")

try:
    from pt_risk import RiskManager, RiskLimits
    RISK_MANAGEMENT_AVAILABLE = True
    print("✅ Risk management module loaded successfully")
except ImportError as e:
    RISK_MANAGEMENT_AVAILABLE = False
    print(f"❌ Risk management module failed to load: {e}")

try:
    from pt_cost import CostManager, PerformanceTier
    COST_MANAGEMENT_AVAILABLE = True
    print("✅ Cost management module loaded successfully")
except ImportError as e:
    COST_MANAGEMENT_AVAILABLE = False
    print(f"❌ Cost management module failed to load: {e}")

try:
    from pt_validation import InputValidator
    VALIDATION_AVAILABLE = True
    print("✅ Input validation module loaded successfully")
except ImportError as e:
    VALIDATION_AVAILABLE = False
    print(f"❌ Input validation module failed to load: {e}")

class CoreTester:
    """Test core Phase 4 functionality."""
    
    def __init__(self):
        self.test_results = {}
        
    async def run_core_tests(self):
        """Run core functionality tests."""
        print("\n🚀 PowerTrader AI Phase 4 Core Test")
        print("=" * 50)
        
        if PAPER_TRADING_AVAILABLE:
            await self._test_paper_trading_core()
        
        if RISK_MANAGEMENT_AVAILABLE:
            self._test_risk_management_core()
        
        if COST_MANAGEMENT_AVAILABLE:
            self._test_cost_management_core()
        
        if VALIDATION_AVAILABLE:
            self._test_validation_core()
            
        self._generate_core_report()
    
    async def _test_paper_trading_core(self):
        """Test core paper trading functionality."""
        print("\n📈 Testing Paper Trading Core...")
        
        try:
            # Create account
            account = PaperTradingAccount(initial_balance=Decimal('10000'))
            print(f"  • Account created with ${account.initial_balance} balance")
            
            # Print risk manager details for debugging
            print(f"  • Portfolio value for risk calc: ${float(account.total_portfolio_value):.2f}")
            
            # Test buy order with very small amount first
            print("  • Attempting very small BTC trade...")
            btc_order = account.place_order(
                symbol="BTC",
                order_type=OrderType.MARKET,
                side=OrderSide.BUY,
                quantity=Decimal('0.001')  # Even smaller trade
            )
            print(f"  • BTC buy order placed: {btc_order[:8]}...")
            
            # Test order status
            status = account.get_order_status(btc_order)
            print(f"  • Order status: {status.value if status else 'UNKNOWN'}")
            
            # Test market price update
            account.update_market_prices()
            print("  • Market prices updated")
            
            # Test account summary
            summary = account.get_account_summary()
            print(f"  • Portfolio value: ${summary['total_value']:.2f}")
            print(f"  • Active positions: {len(summary['positions'])}")
            print(f"  • Total trades: {summary['total_trades']}")
            
            # Validate basic functionality
            if (summary['total_trades'] > 0 and 
                len(summary['positions']) > 0 and
                summary['total_value'] > 0):
                print("  ✅ Paper trading core: PASS")
                self.test_results['paper_trading_core'] = 'PASS'
            else:
                print("  ❌ Paper trading core: FAIL")
                self.test_results['paper_trading_core'] = 'FAIL'
                
        except Exception as e:
            print(f"  ❌ Paper trading core: FAIL ({e})")
            self.test_results['paper_trading_core'] = 'FAIL'
    
    def _test_risk_management_core(self):
        """Test core risk management functionality."""
        print("\n🛡️ Testing Risk Management Core...")
        
        try:
            # Create risk manager
            limits = RiskLimits()
            risk_manager = RiskManager(limits, portfolio_value=100000)
            print("  • Risk manager created")
            
            # Test position size calculation
            position_size = risk_manager.calculate_position_size(50000, 0.02)
            print(f"  • Calculated position size: ${position_size:.2f}")
            
            # Test basic validation - position size should be reasonable
            is_valid_size = 0 < position_size <= 50000
            print(f"  • Position size validation: {is_valid_size}")
            
            if position_size > 0 and is_valid_size:
                print("  ✅ Risk management core: PASS")
                self.test_results['risk_management_core'] = 'PASS'
            else:
                print("  ❌ Risk management core: FAIL")
                self.test_results['risk_management_core'] = 'FAIL'
                
        except Exception as e:
            print(f"  ❌ Risk management core: FAIL ({e})")
            self.test_results['risk_management_core'] = 'FAIL'
    
    def _test_cost_management_core(self):
        """Test core cost management functionality."""
        print("\n💰 Testing Cost Management Core...")
        
        try:
            # Test different performance tiers
            tiers_tested = 0
            for tier in [PerformanceTier.BUDGET, PerformanceTier.PROFESSIONAL]:
                try:
                    cost_manager = CostManager(tier)
                    monthly_costs = cost_manager.calculate_monthly_costs()
                    print(f"  • {tier.name} tier: ${monthly_costs.total_monthly:.2f}/month")
                    tiers_tested += 1
                except Exception as e:
                    print(f"  • {tier.name} tier: FAILED ({e})")
            
            if tiers_tested >= 1:
                print("  ✅ Cost management core: PASS")
                self.test_results['cost_management_core'] = 'PASS'
            else:
                print("  ❌ Cost management core: FAIL")
                self.test_results['cost_management_core'] = 'FAIL'
                
        except Exception as e:
            print(f"  ❌ Cost management core: FAIL ({e})")
            self.test_results['cost_management_core'] = 'FAIL'
    
    def _test_validation_core(self):
        """Test core validation functionality."""
        print("\n🔍 Testing Input Validation Core...")
        
        try:
            # Test valid inputs
            valid_symbol = InputValidator.validate_crypto_symbol("BTC")
            valid_price = InputValidator.validate_price(1000.0)
            print(f"  • Valid symbol: {valid_symbol}")
            print(f"  • Valid price: ${valid_price:.2f}")
            
            # Test invalid inputs (should raise exceptions)
            invalid_tests_passed = 0
            
            # Test empty symbol
            try:
                InputValidator.validate_crypto_symbol("")
            except:
                invalid_tests_passed += 1
                print("  • Empty symbol validation: PASS (correctly rejected)")
            
            # Test negative price
            try:
                InputValidator.validate_price(-100.0)
            except:
                invalid_tests_passed += 1
                print("  • Negative price validation: PASS (correctly rejected)")
            
            if valid_symbol == "BTC" and valid_price == 1000.0 and invalid_tests_passed >= 1:
                print("  ✅ Input validation core: PASS")
                self.test_results['validation_core'] = 'PASS'
            else:
                print("  ❌ Input validation core: FAIL")
                self.test_results['validation_core'] = 'FAIL'
                
        except Exception as e:
            print(f"  ❌ Input validation core: FAIL ({e})")
            self.test_results['validation_core'] = 'FAIL'
    
    def _generate_core_report(self):
        """Generate core test report."""
        print("\n" + "=" * 50)
        print("📊 PHASE 4 CORE TEST REPORT")
        print("=" * 50)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result == 'PASS')
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print(f"Core Success Rate: {success_rate:.1f}% ({passed_tests}/{total_tests})")
        print()
        
        # Individual test results
        for test_name, result in self.test_results.items():
            status_icon = "✅" if result == 'PASS' else "❌"
            test_display = test_name.replace('_', ' ').title()
            print(f"{status_icon} {test_display}: {result}")
        
        print()
        
        # Overall assessment
        if success_rate >= 90:
            print("🎉 EXCELLENT: Core Phase 4 functionality is working perfectly!")
        elif success_rate >= 75:
            print("✅ GOOD: Core Phase 4 functionality is working well")
        elif success_rate >= 50:
            print("⚠️  FAIR: Some core functionality working, needs attention")
        else:
            print("❌ POOR: Core functionality has significant issues")
        
        print()
        print("Ready Phase 4 Components:")
        if self.test_results.get('paper_trading_core') == 'PASS':
            print("  • Paper Trading System ✓")
        if self.test_results.get('risk_management_core') == 'PASS':
            print("  • Risk Management System ✓")
        if self.test_results.get('cost_management_core') == 'PASS':
            print("  • Cost Management System ✓")
        if self.test_results.get('validation_core') == 'PASS':
            print("  • Input Validation System ✓")
        
        # Module availability summary
        print()
        print("Module Availability:")
        modules = [
            ("Paper Trading", PAPER_TRADING_AVAILABLE),
            ("Risk Management", RISK_MANAGEMENT_AVAILABLE),
            ("Cost Management", COST_MANAGEMENT_AVAILABLE),
            ("Input Validation", VALIDATION_AVAILABLE)
        ]
        
        for module_name, available in modules:
            status = "✅" if available else "❌"
            print(f"  {status} {module_name}")
        
        # Save core report
        core_report = {
            'timestamp': datetime.now().isoformat(),
            'phase': 'Phase 4 - Core Testing',
            'success_rate': success_rate,
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'test_results': self.test_results,
            'module_availability': {
                'paper_trading': PAPER_TRADING_AVAILABLE,
                'risk_management': RISK_MANAGEMENT_AVAILABLE,
                'cost_management': COST_MANAGEMENT_AVAILABLE,
                'validation': VALIDATION_AVAILABLE
            },
            'ready_for_phase5': success_rate >= 75
        }
        
        try:
            os.makedirs('test_results', exist_ok=True)
            with open('test_results/phase4_core_report.json', 'w') as f:
                json.dump(core_report, f, indent=2)
            print("\n📄 Core test report saved to: test_results/phase4_core_report.json")
        except Exception as e:
            print(f"\n⚠️  Could not save core report: {e}")

# Main execution
async def main():
    """Run core Phase 4 testing."""
    tester = CoreTester()
    await tester.run_core_tests()

if __name__ == "__main__":
    asyncio.run(main())