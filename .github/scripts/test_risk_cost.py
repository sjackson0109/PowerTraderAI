"""
PowerTrader AI Unit Tests - Risk and Cost Systems

Unit tests that don't require trading credentials or API access.
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, Mock, patch

# Add app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

from pt_cost import CostManager, PerformanceMetrics, PerformanceTier
from pt_risk import RiskLevel, RiskLimits, RiskManager


class TestRiskManagementCore(unittest.TestCase):
    """Test core risk management functionality"""

    def setUp(self):
        # Create default risk limits
        self.limits = RiskLimits()
        self.risk_manager = RiskManager(self.limits, portfolio_value=100000)

    def test_risk_manager_initialization(self):
        """Test risk manager initializes correctly"""
        self.assertIsNotNone(self.risk_manager.portfolio_limits)
        self.assertEqual(self.risk_manager.current_risk_level, RiskLevel.LOW)
        self.assertFalse(self.risk_manager.emergency_stop_active)
        self.assertIsNotNone(self.risk_manager.position_tracker)

    def test_order_validation_approved(self):
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
        self.assertIn("reason", result)

    def test_order_validation_denied_large_position(self):
        """Test orders exceeding position limits are blocked"""
        order = {
            "symbol": "BTC",
            "side": "buy",
            "quantity": 10,
            "price": 50000,
            "order_value": 500000,  # 500% of portfolio
        }

        result = self.risk_manager.validate_order(order, portfolio_value=100000)
        self.assertFalse(result["approved"])
        self.assertIn("position limit", result["reason"].lower())

    def test_emergency_conditions_drawdown(self):
        """Test emergency stop triggers on large drawdown"""
        initial_value = 100000
        current_value = 70000  # 30% drawdown

        self.risk_manager.initial_portfolio_value = initial_value
        status = self.risk_manager.check_emergency_conditions(current_value)

        self.assertTrue(status["emergency_stop"])
        self.assertIn("drawdown", status["reason"].lower())

    def test_position_tracking(self):
        """Test position tracking functionality"""
        # Add a position
        self.risk_manager.update_position("BTC", 1.0, 50000)

        # Check position is tracked
        self.assertIn("BTC", self.risk_manager.position_tracker)
        position = self.risk_manager.position_tracker["BTC"]
        self.assertEqual(position["quantity"], 1.0)
        self.assertEqual(position["avg_price"], 50000)

        # Update position
        self.risk_manager.update_position("BTC", 0.5, 55000)
        position = self.risk_manager.position_tracker["BTC"]
        self.assertEqual(position["quantity"], 1.5)
        # Average price should be calculated
        expected_avg = (1.0 * 50000 + 0.5 * 55000) / 1.5
        self.assertAlmostEqual(position["avg_price"], expected_avg, places=2)

    def test_risk_level_calculation(self):
        """Test risk level calculation based on drawdown"""
        self.risk_manager.initial_portfolio_value = 100000

        # Low risk (small drawdown)
        self.risk_manager.update_portfolio_value(98000)
        self.assertEqual(self.risk_manager.current_risk_level, RiskLevel.LOW)

        # Medium risk (moderate drawdown)
        self.risk_manager.update_portfolio_value(95000)
        self.assertEqual(self.risk_manager.current_risk_level, RiskLevel.MEDIUM)

        # High risk (significant drawdown)
        self.risk_manager.update_portfolio_value(85000)
        self.assertEqual(self.risk_manager.current_risk_level, RiskLevel.HIGH)


class TestCostManagementCore(unittest.TestCase):
    """Test core cost management functionality"""

    def setUp(self):
        self.cost_manager = CostManager(PerformanceTier.PROFESSIONAL)

    def test_cost_manager_initialization(self):
        """Test cost manager initializes correctly"""
        self.assertEqual(self.cost_manager.tier, PerformanceTier.PROFESSIONAL)
        self.assertGreater(len(self.cost_manager.cost_items), 0)
        self.assertGreater(self.cost_manager.monthly_costs.total_monthly, 0)

    def test_monthly_cost_calculation(self):
        """Test monthly cost calculation"""
        monthly_costs = self.cost_manager.calculate_monthly_costs()

        self.assertGreater(monthly_costs.total_monthly, 0)
        self.assertEqual(monthly_costs.total_annual, monthly_costs.total_monthly * 12)
        self.assertGreater(monthly_costs.infrastructure, 0)
        self.assertGreater(monthly_costs.data_feeds, 0)

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
        self.assertEqual(breakdown["required_return_pct"], required_return * 100)

    def test_roi_analysis(self):
        """Test ROI analysis calculation"""
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
        self.assertIn("cost_per_trade", roi_analysis)
        self.assertIn("efficiency_score", roi_analysis)

        # Net return should be gross return minus costs
        expected_net = (
            performance.total_return - self.cost_manager.monthly_costs.total_annual
        )
        self.assertAlmostEqual(roi_analysis["net_return"], expected_net, places=0)

    def test_tier_optimization(self):
        """Test tier recommendation system"""
        recommendation = self.cost_manager.optimize_tier_selection(
            capital=200000, expected_return=0.20
        )

        self.assertIn("recommended_tier", recommendation)
        self.assertIn("tier_analysis", recommendation)

        # Should analyze all tiers
        tier_analysis = recommendation["tier_analysis"]
        self.assertIn("budget", tier_analysis)
        self.assertIn("professional", tier_analysis)
        self.assertIn("enterprise", tier_analysis)

        # Each tier should have required fields
        for tier_data in tier_analysis.values():
            self.assertIn("feasible", tier_data)
            self.assertIn("expected_profit", tier_data)
            self.assertIn("required_return_pct", tier_data)


class TestTierComparison(unittest.TestCase):
    """Test different tier configurations"""

    def test_budget_tier_costs(self):
        """Test budget tier has lowest costs"""
        budget_manager = CostManager(PerformanceTier.BUDGET)
        budget_costs = budget_manager.calculate_monthly_costs()

        professional_manager = CostManager(PerformanceTier.PROFESSIONAL)
        professional_costs = professional_manager.calculate_monthly_costs()

        enterprise_manager = CostManager(PerformanceTier.ENTERPRISE)
        enterprise_costs = enterprise_manager.calculate_monthly_costs()

        # Budget should be cheapest
        self.assertLess(budget_costs.total_monthly, professional_costs.total_monthly)
        self.assertLess(
            professional_costs.total_monthly, enterprise_costs.total_monthly
        )

    def test_enterprise_tier_features(self):
        """Test enterprise tier has most comprehensive features"""
        enterprise_manager = CostManager(PerformanceTier.ENTERPRISE)
        enterprise_costs = enterprise_manager.calculate_monthly_costs()

        # Enterprise should have significant personnel costs
        self.assertGreater(enterprise_costs.personnel, 50000)

        # Enterprise should have compliance costs
        self.assertGreater(enterprise_costs.compliance, 0)


class TestScalingAnalysis(unittest.TestCase):
    """Test cost scaling analysis"""

    def setUp(self):
        self.cost_manager = CostManager(PerformanceTier.PROFESSIONAL)

    def test_scaling_efficiency(self):
        """Test cost efficiency improves with scale"""
        single_user = self.cost_manager.calculate_scaling_costs(1.0)
        five_users = self.cost_manager.calculate_scaling_costs(5.0)

        # Cost per user should decrease with scale
        self.assertLess(five_users["cost_per_user"], single_user["cost_per_user"])

        # Total costs should increase but not linearly
        self.assertGreater(
            five_users["scaled_monthly_cost"], single_user["scaled_monthly_cost"]
        )
        self.assertLess(
            five_users["scaled_monthly_cost"], single_user["scaled_monthly_cost"] * 5
        )


if __name__ == "__main__":
    print("Running PowerTrader AI Risk & Cost Management Tests...")
    print("=" * 60)

    # Create test suite
    test_suite = unittest.TestSuite()

    # Add test classes
    test_classes = [
        TestRiskManagementCore,
        TestCostManagementCore,
        TestTierComparison,
        TestScalingAnalysis,
    ]

    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)

    # Print summary
    print("\n" + "=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")

    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"- {test}")

    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"- {test}")

    if result.wasSuccessful():
        print(f"\n✅ All {result.testsRun} tests passed!")
        print("\n🎉 Risk Management and Cost Analysis systems are working correctly!")
    else:
        print(f"\n❌ Some tests failed!")
