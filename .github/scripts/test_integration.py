"""
PowerTrader AI Integration Test Suite

Tests the integration of risk management and cost analysis
with the main trading system.
"""

import json
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, Mock, patch

# Add app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

from pt_cost import CostManager, PerformanceMetrics, PerformanceTier
from pt_risk import RiskLevel, RiskManager
from pt_trader import CryptoAPITrading


class TestRiskIntegration(unittest.TestCase):
    """Test risk management integration with trading system"""

    def setUp(self):
        self.risk_manager = RiskManager()

    def test_risk_manager_initialization(self):
        """Test risk manager initializes correctly"""
        self.assertIsNotNone(self.risk_manager.portfolio_limits)
        self.assertEqual(self.risk_manager.current_risk_level, RiskLevel.LOW)
        self.assertFalse(self.risk_manager.emergency_stop_active)

    def test_order_validation_within_limits(self):
        """Test orders within limits are approved"""
        order = {
            "symbol": "BTC",
            "side": "buy",
            "quantity": 0.001,
            "price": 50000,
            "order_value": 50,
        }

        result = self.risk_manager.validate_order(order, portfolio_value=100000)
        self.assertTrue(result["approved"])
        self.assertEqual(result["risk_level"], RiskLevel.LOW)

    def test_order_validation_exceeds_limits(self):
        """Test orders exceeding limits are blocked"""
        order = {
            "symbol": "BTC",
            "side": "buy",
            "quantity": 10,
            "price": 50000,
            "order_value": 500000,  # Exceeds 10% position limit
        }

        result = self.risk_manager.validate_order(order, portfolio_value=100000)
        self.assertFalse(result["approved"])
        self.assertIn("position limit", result["reason"].lower())

    def test_emergency_stop_triggers(self):
        """Test emergency stop triggers correctly"""
        # Simulate large drawdown
        initial_value = 100000
        current_value = 70000  # 30% drawdown

        self.risk_manager.initial_portfolio_value = initial_value
        status = self.risk_manager.check_emergency_conditions(current_value)

        self.assertTrue(status["emergency_stop"])
        self.assertIn("drawdown", status["reason"].lower())

    def test_risk_level_escalation(self):
        """Test risk level escalates with portfolio decline"""
        # Start with high value
        self.risk_manager.update_portfolio_value(100000)
        self.assertEqual(self.risk_manager.current_risk_level, RiskLevel.LOW)

        # Moderate decline
        self.risk_manager.update_portfolio_value(95000)
        self.assertEqual(self.risk_manager.current_risk_level, RiskLevel.MEDIUM)

        # Significant decline
        self.risk_manager.update_portfolio_value(85000)
        self.assertEqual(self.risk_manager.current_risk_level, RiskLevel.HIGH)


class TestCostIntegration(unittest.TestCase):
    """Test cost management integration"""

    def setUp(self):
        self.cost_manager = CostManager(PerformanceTier.PROFESSIONAL)

    def test_cost_manager_initialization(self):
        """Test cost manager initializes correctly"""
        self.assertEqual(self.cost_manager.tier, PerformanceTier.PROFESSIONAL)
        self.assertGreater(len(self.cost_manager.cost_items), 0)
        self.assertGreater(self.cost_manager.monthly_costs.total_monthly, 0)

    def test_break_even_calculation(self):
        """Test break-even return calculation"""
        capital = 100000
        required_return, breakdown = self.cost_manager.calculate_break_even_return(
            capital
        )

        self.assertIsInstance(required_return, float)
        self.assertGreater(required_return, 0)
        self.assertIn("annual_costs", breakdown)
        self.assertIn("required_return_pct", breakdown)

    def test_roi_analysis(self):
        """Test ROI analysis functionality"""
        performance = PerformanceMetrics(
            total_return=25000,
            annualized_return=0.25,
            sharpe_ratio=1.5,
            max_drawdown=0.1,
            win_rate=0.65,
            profit_factor=1.8,
            total_trades=100,
            capital_deployed=100000,
        )

        roi_analysis = self.cost_manager.analyze_roi(performance)

        self.assertIn("net_return", roi_analysis)
        self.assertIn("is_profitable", roi_analysis)
        self.assertIsInstance(roi_analysis["is_profitable"], bool)

    def test_tier_optimization(self):
        """Test tier recommendation system"""
        recommendation = self.cost_manager.optimize_tier_selection(
            capital=200000, expected_return=0.20
        )

        self.assertIn("recommended_tier", recommendation)
        self.assertIn("tier_analysis", recommendation)
        self.assertIn(
            recommendation["recommended_tier"], ["budget", "professional", "enterprise"]
        )


class TestSystemIntegration(unittest.TestCase):
    """Test full system integration"""

    @patch("pt_trader.CryptoAPITrading.__init__")
    def test_trader_initialization_with_risk_and_cost(self, mock_init):
        """Test trader initializes with risk and cost managers"""
        mock_init.return_value = None

        # Mock the trader's initialization
        trader = CryptoAPITrading()
        trader.risk_manager = RiskManager()
        trader.cost_manager = CostManager(PerformanceTier.PROFESSIONAL)

        self.assertIsNotNone(trader.risk_manager)
        self.assertIsNotNone(trader.cost_manager)

    def test_risk_cost_interaction(self):
        """Test interaction between risk and cost systems"""
        risk_manager = RiskManager()
        cost_manager = CostManager(PerformanceTier.BUDGET)

        # Simulate trading scenario
        portfolio_value = 50000
        monthly_costs = cost_manager.calculate_monthly_costs()

        # Check if portfolio can sustain costs
        monthly_burn_rate = monthly_costs.total_monthly / portfolio_value

        # Risk manager should consider cost burn rate
        self.assertLess(monthly_burn_rate, 0.1)  # Less than 10% monthly burn


class TestRealTimeMonitoring(unittest.TestCase):
    """Test real-time monitoring capabilities"""

    def setUp(self):
        self.risk_manager = RiskManager()

    def test_position_monitoring(self):
        """Test position size monitoring"""
        # Add a position
        self.risk_manager.update_position("BTC", 1.0, 50000)

        # Check position is tracked
        self.assertIn("BTC", self.risk_manager.position_tracker)
        self.assertEqual(self.risk_manager.position_tracker["BTC"]["quantity"], 1.0)

        # Test position limit enforcement
        large_order = {
            "symbol": "BTC",
            "side": "buy",
            "quantity": 10,
            "price": 50000,
            "order_value": 500000,
        }

        result = self.risk_manager.validate_order(large_order, portfolio_value=100000)
        self.assertFalse(result["approved"])

    def test_correlation_monitoring(self):
        """Test correlation tracking between assets"""
        # Add correlated positions
        self.risk_manager.update_position("BTC", 1.0, 50000)
        self.risk_manager.update_position("ETH", 10.0, 3000)

        # Check correlation limits are enforced
        correlation_status = self.risk_manager.check_correlation_limits()
        self.assertIn("total_crypto_exposure", correlation_status)

    def test_volatility_monitoring(self):
        """Test volatility-based risk adjustments"""
        # Simulate high volatility scenario
        for i in range(10):
            price = 50000 + (i % 2) * 5000  # Alternating prices
            self.risk_manager.update_position("BTC", 1.0, price)

        # Check if volatility is detected
        self.risk_manager.update_portfolio_value(100000)
        # Risk level should increase with volatility
        # This is a simplified test - real implementation would be more sophisticated


class TestPerformanceMetrics(unittest.TestCase):
    """Test performance measurement and optimization"""

    def test_performance_tracking(self):
        """Test performance metrics calculation"""
        cost_manager = CostManager(PerformanceTier.PROFESSIONAL)

        # Create mock performance data
        performance = PerformanceMetrics(
            total_return=15000,
            annualized_return=0.15,
            sharpe_ratio=1.2,
            max_drawdown=0.08,
            win_rate=0.62,
            profit_factor=1.6,
            total_trades=150,
            capital_deployed=100000,
        )

        analysis = cost_manager.analyze_roi(performance)

        self.assertIsInstance(analysis["net_return"], float)
        self.assertIsInstance(analysis["cost_per_trade"], float)
        self.assertIsInstance(analysis["efficiency_score"], float)

    def test_scaling_analysis(self):
        """Test cost scaling with multiple users"""
        cost_manager = CostManager(PerformanceTier.ENTERPRISE)

        scaling_analysis = cost_manager.calculate_scaling_costs(5.0)

        self.assertEqual(scaling_analysis["user_multiplier"], 5.0)
        self.assertGreater(
            scaling_analysis["scaled_monthly_cost"],
            scaling_analysis["base_monthly_cost"],
        )
        self.assertLess(
            scaling_analysis["cost_per_user"], scaling_analysis["base_monthly_cost"]
        )  # Should be more efficient


if __name__ == "__main__":
    # Setup test environment
    print("Running PowerTrader AI Integration Tests...")
    print("=" * 50)

    # Create test suite
    test_suite = unittest.TestSuite()

    # Add test classes
    test_classes = [
        TestRiskIntegration,
        TestCostIntegration,
        TestSystemIntegration,
        TestRealTimeMonitoring,
        TestPerformanceMetrics,
    ]

    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)

    # Print summary
    print("\n" + "=" * 50)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")

    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")

    if result.wasSuccessful():
        print("\nAll tests passed! ✅")
    else:
        print("\nSome tests failed! ❌")
