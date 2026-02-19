"""
PowerTrader AI Basic Functionality Tests

Simple tests to verify core functionality without complex integration.
"""

import unittest
from pt_risk import RiskManager, RiskLevel, RiskLimits
from pt_cost import CostManager, PerformanceTier, PerformanceMetrics

class TestBasicFunctionality(unittest.TestCase):
    """Test basic functionality of risk and cost systems"""
    
    def test_risk_manager_creation(self):
        """Test that RiskManager can be created"""
        limits = RiskLimits()
        risk_manager = RiskManager(limits, portfolio_value=100000)
        self.assertIsNotNone(risk_manager)
        self.assertEqual(risk_manager.portfolio_value, 100000)
        
    def test_cost_manager_creation(self):
        """Test that CostManager can be created"""
        cost_manager = CostManager(PerformanceTier.PROFESSIONAL)
        self.assertIsNotNone(cost_manager)
        self.assertEqual(cost_manager.tier, PerformanceTier.PROFESSIONAL)
    
    def test_cost_calculation(self):
        """Test basic cost calculations"""
        cost_manager = CostManager(PerformanceTier.BUDGET)
        monthly_costs = cost_manager.calculate_monthly_costs()
        
        self.assertGreater(monthly_costs.total_monthly, 0)
        self.assertEqual(monthly_costs.total_annual, monthly_costs.total_monthly * 12)
        
    def test_break_even_calculation(self):
        """Test break-even calculations"""
        cost_manager = CostManager(PerformanceTier.BUDGET)
        capital = 50000
        
        required_return, breakdown = cost_manager.calculate_break_even_return(capital)
        
        self.assertIsInstance(required_return, float)
        self.assertGreater(required_return, 0)
        self.assertIn('annual_costs', breakdown)
        
    def test_tier_comparison(self):
        """Test that different tiers have different costs"""
        budget_manager = CostManager(PerformanceTier.BUDGET)
        professional_manager = CostManager(PerformanceTier.PROFESSIONAL)
        enterprise_manager = CostManager(PerformanceTier.ENTERPRISE)
        
        budget_costs = budget_manager.calculate_monthly_costs()
        professional_costs = professional_manager.calculate_monthly_costs()
        enterprise_costs = enterprise_manager.calculate_monthly_costs()
        
        # Costs should increase with tier level
        self.assertLess(budget_costs.total_monthly, professional_costs.total_monthly)
        self.assertLess(professional_costs.total_monthly, enterprise_costs.total_monthly)
        
    def test_roi_analysis_basic(self):
        """Test basic ROI analysis"""
        cost_manager = CostManager(PerformanceTier.BUDGET)
        
        performance = PerformanceMetrics(
            total_return=10000,
            annualized_return=0.10,
            sharpe_ratio=1.2,
            max_drawdown=0.05,
            win_rate=0.60,
            profit_factor=1.5,
            total_trades=50,
            capital_deployed=100000
        )
        
        analysis = cost_manager.analyze_roi(performance)
        
        self.assertIn('net_return', analysis)
        self.assertIn('is_profitable', analysis)
        self.assertIsInstance(analysis['is_profitable'], bool)
        
    def test_position_size_calculation(self):
        """Test position size calculation"""
        limits = RiskLimits()
        risk_manager = RiskManager(limits, portfolio_value=100000)
        
        position_size = risk_manager.calculate_position_size(
            account_value=100000,
            risk_per_trade=0.02   # 2% risk
        )
        
        self.assertIsInstance(position_size, float)
        self.assertGreater(position_size, 0)
        
    def test_trade_validation(self):
        """Test trade validation functionality"""
        limits = RiskLimits()
        risk_manager = RiskManager(limits, portfolio_value=100000)
        
        # Test a reasonable trade
        is_valid, reason = risk_manager.validate_trade(
            symbol='BTC',
            quantity=0.01,
            price=50000
        )
        
        self.assertIsInstance(is_valid, bool)
        self.assertIsInstance(reason, str)
        
    def test_tier_optimization(self):
        """Test tier optimization recommendations"""
        cost_manager = CostManager()
        
        recommendation = cost_manager.optimize_tier_selection(
            capital=150000,
            expected_return=0.15
        )
        
        self.assertIn('recommended_tier', recommendation)
        self.assertIn('tier_analysis', recommendation)
        
    def test_scaling_costs(self):
        """Test cost scaling analysis"""
        cost_manager = CostManager(PerformanceTier.PROFESSIONAL)
        
        single_user_costs = cost_manager.calculate_scaling_costs(1.0)
        multi_user_costs = cost_manager.calculate_scaling_costs(5.0)
        
        self.assertEqual(single_user_costs['user_multiplier'], 1.0)
        self.assertEqual(multi_user_costs['user_multiplier'], 5.0)
        self.assertGreater(multi_user_costs['scaled_monthly_cost'], 
                          single_user_costs['scaled_monthly_cost'])

class TestConfigurationIntegration(unittest.TestCase):
    """Test configuration and integration"""
    
    def test_risk_limits_defaults(self):
        """Test default risk limits are reasonable"""
        limits = RiskLimits()
        
        self.assertGreater(limits.max_position_size, 0)
        self.assertLess(limits.max_position_size, 0.5)  # Should be less than 50%
        self.assertGreater(limits.max_daily_loss, 0)
        self.assertLess(limits.max_daily_loss, 0.2)     # Should be less than 20%
        
    def test_performance_metrics_creation(self):
        """Test performance metrics can be created"""
        metrics = PerformanceMetrics(
            total_return=5000,
            annualized_return=0.05,
            sharpe_ratio=1.0,
            max_drawdown=0.03,
            win_rate=0.55,
            profit_factor=1.2,
            total_trades=25,
            capital_deployed=100000
        )
        
        self.assertEqual(metrics.total_return, 5000)
        self.assertEqual(metrics.capital_deployed, 100000)
        self.assertGreater(metrics.win_rate, 0)
        self.assertLess(metrics.win_rate, 1)

if __name__ == '__main__':
    print("Running PowerTrader AI Basic Functionality Tests...")
    print("=" * 60)
    
    # Run the tests
    unittest.main(verbosity=2)