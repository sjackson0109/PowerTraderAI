"""
PowerTrader AI Phase 4 Implementation Test

Comprehensive test script that validates all Phase 4 components:
- Integration testing framework
- Paper trading system
- Live monitoring system
- End-to-end workflow validation
"""

import asyncio
import sys
import os
from decimal import Decimal
from datetime import datetime
import json
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

# Import Phase 4 components
from pt_integration import LiveIntegrationTester
from pt_paper_trading import PaperTradingAccount, OrderType, OrderSide
from pt_live_monitor import LiveMonitor
from pt_logging import get_logger

class Phase4Tester:
    """Comprehensive Phase 4 testing orchestrator."""
    
    def __init__(self):
        self.logger = get_logger("phase4_tester")
        self.test_results = {}
        
    async def run_phase4_tests(self):
        """Run comprehensive Phase 4 testing suite."""
        print("🚀 PowerTrader AI Phase 4 Implementation Test")
        print("=" * 60)
        print("Testing: Integration Framework + Paper Trading + Live Monitoring")
        print("=" * 60)
        
        # Test 1: Integration Testing Framework
        print("\n📋 Test 1: Integration Testing Framework")
        await self._test_integration_framework()
        
        # Test 2: Paper Trading System
        print("\n📈 Test 2: Paper Trading System") 
        await self._test_paper_trading()
        
        # Test 3: Live Monitoring System
        print("\n📊 Test 3: Live Monitoring System")
        await self._test_live_monitoring()
        
        # Test 4: End-to-End Workflow
        print("\n🔄 Test 4: End-to-End Workflow")
        await self._test_end_to_end()
        
        # Generate final report
        self._generate_test_report()
        
    async def _test_integration_framework(self):
        """Test the integration testing framework."""
        try:
            print("  • Creating integration tester...")
            tester = LiveIntegrationTester()
            
            print("  • Running comprehensive integration tests...")
            report = await tester.run_comprehensive_tests()
            
            # Validate results
            summary = report['summary']
            success_rate = summary['success_rate']
            
            print(f"  • Integration tests completed:")
            print(f"    - Total tests: {summary['total_tests']}")
            print(f"    - Success rate: {success_rate:.1f}%")
            print(f"    - Duration: {summary['total_duration_ms']:.0f}ms")
            
            # Check if acceptable
            if success_rate >= 80:
                print("  ✅ Integration framework: PASS")
                self.test_results['integration_framework'] = 'PASS'
            else:
                print("  ❌ Integration framework: FAIL (low success rate)")
                self.test_results['integration_framework'] = 'FAIL'
            
        except Exception as e:
            print(f"  ❌ Integration framework: FAIL ({e})")
            self.test_results['integration_framework'] = 'FAIL'
            self.logger.error(f"Integration framework test failed: {e}")
    
    async def _test_paper_trading(self):
        """Test the paper trading system."""
        try:
            print("  • Creating paper trading account...")
            account = PaperTradingAccount(initial_balance=Decimal('10000'))
            
            print("  • Testing buy orders...")
            # Place buy orders
            btc_order = account.place_order("BTC", OrderType.MARKET, OrderSide.BUY, Decimal('0.1'))
            eth_order = account.place_order("ETH", OrderType.MARKET, OrderSide.BUY, Decimal('1.5'))
            
            # Check orders were created
            btc_status = account.get_order_status(btc_order)
            eth_status = account.get_order_status(eth_order)
            
            print(f"    - BTC order: {btc_status.value if btc_status else 'NOT_FOUND'}")
            print(f"    - ETH order: {eth_status.value if eth_status else 'NOT_FOUND'}")
            
            print("  • Updating market prices...")
            account.update_market_prices()
            
            print("  • Testing sell orders...")
            # Test partial sell
            if "BTC" in account.positions:
                sell_order = account.place_order("BTC", OrderType.MARKET, OrderSide.SELL, Decimal('0.05'))
                print(f"    - BTC sell order: {account.get_order_status(sell_order).value}")
            
            # Get account summary
            summary = account.get_account_summary()
            
            print("  • Account summary:")
            print(f"    - Total value: ${summary['total_value']:.2f}")
            print(f"    - Cash balance: ${summary['cash_balance']:.2f}")
            print(f"    - Total P&L: ${summary['total_pnl']:.2f}")
            print(f"    - Total trades: {summary['total_trades']}")
            print(f"    - Active positions: {len(summary['positions'])}")
            
            # Validate functionality
            if (summary['total_trades'] >= 2 and 
                summary['total_value'] > 0 and
                len(summary['positions']) > 0):
                print("  ✅ Paper trading system: PASS")
                self.test_results['paper_trading'] = 'PASS'
            else:
                print("  ❌ Paper trading system: FAIL (insufficient activity)")
                self.test_results['paper_trading'] = 'FAIL'
            
        except Exception as e:
            print(f"  ❌ Paper trading system: FAIL ({e})")
            self.test_results['paper_trading'] = 'FAIL'
            self.logger.error(f"Paper trading test failed: {e}")
    
    async def _test_live_monitoring(self):
        """Test the live monitoring system."""
        try:
            print("  • Creating live monitor...")
            monitor = LiveMonitor()
            
            print("  • Creating paper account for monitoring...")
            account = PaperTradingAccount(Decimal('10000'))
            
            # Do some trading to generate metrics
            account.place_order("BTC", OrderType.MARKET, OrderSide.BUY, Decimal('0.1'))
            account.place_order("ETH", OrderType.MARKET, OrderSide.BUY, Decimal('2.0'))
            account.update_market_prices()
            
            print("  • Registering account with monitor...")
            monitor.register_paper_account(account)
            
            print("  • Starting monitoring...")
            monitor.start_monitoring()
            
            # Let it collect some metrics
            await asyncio.sleep(3)
            
            print("  • Checking system health...")
            health = monitor.get_system_health()
            
            print(f"    - System status: {health.status}")
            print(f"    - Uptime: {health.uptime_seconds:.1f}s")
            print(f"    - Components: {sum(health.components.values())}/{len(health.components)} healthy")
            print(f"    - Recent alerts: {sum(health.alerts_count.values())}")
            
            print("  • Getting dashboard data...")
            dashboard = monitor.get_dashboard_data()
            
            print(f"    - Metrics collected: {len(dashboard['current_metrics'])}")
            print(f"    - Chart data series: {len(dashboard['chart_data'])}")
            
            print("  • Stopping monitoring...")
            monitor.stop_monitoring()
            
            # Validate functionality
            if (health.status in ['healthy', 'warning'] and
                len(dashboard['current_metrics']) > 0 and
                sum(health.components.values()) >= len(health.components) // 2):
                print("  ✅ Live monitoring system: PASS")
                self.test_results['live_monitoring'] = 'PASS'
            else:
                print("  ❌ Live monitoring system: FAIL (insufficient functionality)")
                self.test_results['live_monitoring'] = 'FAIL'
            
        except Exception as e:
            print(f"  ❌ Live monitoring system: FAIL ({e})")
            self.test_results['live_monitoring'] = 'FAIL'
            self.logger.error(f"Live monitoring test failed: {e}")
    
    async def _test_end_to_end(self):
        """Test end-to-end workflow integration."""
        try:
            print("  • Setting up complete Phase 4 environment...")
            
            # Create all components
            integration_tester = LiveIntegrationTester()
            account = PaperTradingAccount(Decimal('15000'))
            monitor = LiveMonitor()
            
            print("  • Configuring integrated system...")
            monitor.register_paper_account(account)
            
            # Add custom alert handler for testing
            alerts_received = []
            def test_alert_handler(alert):
                alerts_received.append(alert)
            monitor.add_alert_handler(test_alert_handler)
            
            print("  • Starting monitoring...")
            monitor.start_monitoring()
            
            print("  • Executing trading scenario...")
            # Execute a realistic trading scenario
            trades = [
                ("BTC", OrderType.MARKET, OrderSide.BUY, Decimal('0.2')),
                ("ETH", OrderType.MARKET, OrderSide.BUY, Decimal('3.0')),
                ("ADA", OrderType.MARKET, OrderSide.BUY, Decimal('1000'))
            ]
            
            executed_trades = 0
            for symbol, order_type, side, quantity in trades:
                try:
                    order_id = account.place_order(symbol, order_type, side, quantity)
                    if account.get_order_status(order_id) == account.orders[order_id].status:
                        executed_trades += 1
                    await asyncio.sleep(0.5)  # Brief pause between trades
                except Exception as e:
                    print(f"    - Trade failed: {symbol} {side.value} {quantity} ({e})")
            
            print(f"    - Executed trades: {executed_trades}/{len(trades)}")
            
            print("  • Updating market data...")
            account.update_market_prices()
            
            print("  • Collecting metrics...")
            await asyncio.sleep(2)  # Allow metrics collection
            
            print("  • Running quick integration test...")
            # Run subset of integration tests
            quick_report = await integration_tester.run_comprehensive_tests()
            
            # Get final state
            account_summary = account.get_account_summary()
            system_health = monitor.get_system_health()
            
            print("  • End-to-end results:")
            print(f"    - Account value: ${account_summary['total_value']:.2f}")
            print(f"    - Active positions: {len(account_summary['positions'])}")
            print(f"    - System status: {system_health.status}")
            print(f"    - Integration success: {quick_report['summary']['success_rate']:.1f}%")
            print(f"    - Alerts received: {len(alerts_received)}")
            
            print("  • Stopping monitoring...")
            monitor.stop_monitoring()
            
            # Validate end-to-end functionality
            success_criteria = [
                executed_trades >= 2,
                account_summary['total_trades'] >= 2,
                len(account_summary['positions']) >= 2,
                system_health.status in ['healthy', 'warning'],
                quick_report['summary']['success_rate'] >= 70
            ]
            
            passed_criteria = sum(success_criteria)
            
            if passed_criteria >= 4:  # At least 4/5 criteria
                print("  ✅ End-to-end workflow: PASS")
                self.test_results['end_to_end'] = 'PASS'
            else:
                print(f"  ❌ End-to-end workflow: FAIL ({passed_criteria}/5 criteria)")
                self.test_results['end_to_end'] = 'FAIL'
            
        except Exception as e:
            print(f"  ❌ End-to-end workflow: FAIL ({e})")
            self.test_results['end_to_end'] = 'FAIL'
            self.logger.error(f"End-to-end test failed: {e}")
    
    def _generate_test_report(self):
        """Generate final test report."""
        print("\n" + "=" * 60)
        print("📊 PHASE 4 IMPLEMENTATION TEST REPORT")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result == 'PASS')
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print(f"Overall Success Rate: {success_rate:.1f}% ({passed_tests}/{total_tests})")
        print()
        
        # Individual test results
        for test_name, result in self.test_results.items():
            status_icon = "✅" if result == 'PASS' else "❌"
            test_display = test_name.replace('_', ' ').title()
            print(f"{status_icon} {test_display}: {result}")
        
        print()
        
        # Overall assessment
        if success_rate >= 90:
            print("🎉 EXCELLENT: Phase 4 implementation is fully functional!")
        elif success_rate >= 75:
            print("✅ GOOD: Phase 4 implementation is working well with minor issues")
        elif success_rate >= 50:
            print("⚠️  FAIR: Phase 4 implementation has some functionality but needs work")
        else:
            print("❌ POOR: Phase 4 implementation needs significant fixes")
        
        print()
        print("Phase 4 Components Ready:")
        if self.test_results.get('integration_framework') == 'PASS':
            print("  • Integration testing framework ✓")
        if self.test_results.get('paper_trading') == 'PASS':
            print("  • Paper trading system ✓")
        if self.test_results.get('live_monitoring') == 'PASS':
            print("  • Live monitoring system ✓")
        if self.test_results.get('end_to_end') == 'PASS':
            print("  • End-to-end workflow ✓")
        
        print()
        print("Next Steps:")
        if success_rate >= 75:
            print("  • Ready to proceed to Phase 5 (Production Deployment)")
            print("  • Consider setting up live API credentials")
            print("  • Configure production monitoring alerts")
        else:
            print("  • Fix failing components before proceeding")
            print("  • Review error logs for specific issues")
            print("  • Re-run tests after fixes")
        
        # Save report
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'phase': 'Phase 4 - Integration & Live Testing',
            'success_rate': success_rate,
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'test_results': self.test_results,
            'next_phase_ready': success_rate >= 75
        }
        
        try:
            with open('test_results/phase4_test_report.json', 'w') as f:
                json.dump(report_data, f, indent=2)
            print("\n📄 Detailed report saved to: test_results/phase4_test_report.json")
        except Exception as e:
            print(f"\n⚠️  Could not save report: {e}")

# Main execution
async def main():
    """Run Phase 4 testing."""
    tester = Phase4Tester()
    await tester.run_phase4_tests()

if __name__ == "__main__":
    # Ensure test results directory exists
    os.makedirs('test_results', exist_ok=True)
    
    # Run the tests
    asyncio.run(main())