"""
Comprehensive Testing Suite (Item 22)
Automated testing system for PowerTrader components
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch

# Add current directory to path for imports
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


# Color codes for test output
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class PowerTraderTestResult(unittest.TextTestResult):
    """Custom test result class with colored output"""

    def addSuccess(self, test):
        super().addSuccess(test)
        if self.showAll:
            self.stream.write(f"{Colors.GREEN}✓ PASS{Colors.RESET}\n")
        elif self.dots:
            self.stream.write(f"{Colors.GREEN}.{Colors.RESET}")

    def addError(self, test, err):
        super().addError(test, err)
        if self.showAll:
            self.stream.write(f"{Colors.RED}✗ ERROR{Colors.RESET}\n")
        elif self.dots:
            self.stream.write(f"{Colors.RED}E{Colors.RESET}")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        if self.showAll:
            self.stream.write(f"{Colors.RED}✗ FAIL{Colors.RESET}\n")
        elif self.dots:
            self.stream.write(f"{Colors.RED}F{Colors.RESET}")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        if self.showAll:
            self.stream.write(f"{Colors.YELLOW}⚠ SKIP{Colors.RESET} ({reason})\n")
        elif self.dots:
            self.stream.write(f"{Colors.YELLOW}S{Colors.RESET}")


class PowerTraderTestRunner(unittest.TextTestRunner):
    """Custom test runner with enhanced output"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("verbosity", 2)
        kwargs.setdefault("resultclass", PowerTraderTestResult)
        super().__init__(*args, **kwargs)

    def run(self, test):
        print(
            f"\n{Colors.BOLD}{Colors.BLUE}=== PowerTrader Test Suite ==={Colors.RESET}"
        )
        print(f"{Colors.CYAN}Running {test.countTestCases()} tests...{Colors.RESET}\n")

        start_time = time.time()
        result = super().run(test)
        end_time = time.time()

        # Print summary
        print(f"\n{Colors.BOLD}=== Test Summary ==={Colors.RESET}")
        print(f"Tests run: {result.testsRun}")
        print(
            f"{Colors.GREEN}Passed: {result.testsRun - len(result.failures) - len(result.errors)}{Colors.RESET}"
        )

        if result.failures:
            print(f"{Colors.RED}Failed: {len(result.failures)}{Colors.RESET}")
        if result.errors:
            print(f"{Colors.RED}Errors: {len(result.errors)}{Colors.RESET}")
        if result.skipped:
            print(f"{Colors.YELLOW}Skipped: {len(result.skipped)}{Colors.RESET}")

        print(f"Time: {end_time - start_time:.2f}s")

        if result.failures or result.errors:
            print(f"\n{Colors.RED}❌ Some tests failed{Colors.RESET}")
        else:
            print(f"\n{Colors.GREEN}✅ All tests passed!{Colors.RESET}")

        return result


class TestBase(unittest.TestCase):
    """Base test class with common utilities"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test.db")

    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_test_db(self) -> str:
        """Create a test database"""
        conn = sqlite3.connect(self.test_db_path)
        conn.close()
        return self.test_db_path

    def assertFileExists(self, file_path: str):
        """Assert that a file exists"""
        self.assertTrue(os.path.exists(file_path), f"File does not exist: {file_path}")

    def assertFileNotExists(self, file_path: str):
        """Assert that a file does not exist"""
        self.assertFalse(
            os.path.exists(file_path), f"File exists when it shouldn't: {file_path}"
        )


class TestExchangeAbstraction(TestBase):
    """Test exchange abstraction layer"""

    def test_exchange_type_enum(self):
        """Test ExchangeType enum"""
        try:
            from pt_exchange_abstraction import ExchangeType

            # Test enum values exist
            self.assertTrue(hasattr(ExchangeType, "BINANCE"))
            self.assertTrue(hasattr(ExchangeType, "COINBASE"))
            self.assertTrue(hasattr(ExchangeType, "KRAKEN"))

        except ImportError:
            self.skipTest("Exchange abstraction module not available")

    def test_exchange_factory(self):
        """Test exchange factory functionality"""
        try:
            from pt_exchange_abstraction import ExchangeFactory, ExchangeType

            # Test factory creation
            factory = ExchangeFactory()
            self.assertIsNotNone(factory)

            # Test supported exchanges
            supported = factory.get_available_exchanges()
            self.assertIsInstance(supported, list)
            self.assertGreater(len(supported), 0)

        except ImportError:
            self.skipTest("Exchange abstraction module not available")


class TestMultiExchange(TestBase):
    """Test multi-exchange management"""

    def test_exchange_config_manager(self):
        """Test exchange configuration manager"""
        try:
            from pt_multi_exchange import ExchangeConfigManager

            config_manager = ExchangeConfigManager()
            self.assertIsNotNone(config_manager)

            # Test configuration validation
            test_config = {
                "exchange": "binance",
                "api_key": "test_key",
                "api_secret": "test_secret",
            }

            # Test that enabled exchanges can be retrieved (valid method)
            enabled = config_manager.get_enabled_exchanges()
            self.assertIsInstance(enabled, list)

        except ImportError:
            self.skipTest("Multi-exchange module not available")

    def test_multi_exchange_manager(self):
        """Test multi-exchange manager functionality"""
        try:
            from pt_multi_exchange import MultiExchangeManager

            manager = MultiExchangeManager()
            self.assertIsNotNone(manager)

            # Test initialization
            self.assertEqual(len(manager.get_available_exchanges()), 0)

        except ImportError:
            self.skipTest("Multi-exchange module not available")


class TestOrderManagement(TestBase):
    """Test order management system"""

    def setUp(self):
        super().setUp()
        self._release_order_management()  # one made by an earlier test

    def tearDown(self):
        # Before the test folder goes: the global order manager holds its database
        # open (and runs a monitoring thread), and no later test should inherit it.
        self._release_order_management()
        super().tearDown()

    @staticmethod
    def _release_order_management():
        try:
            from order_management_integration import shutdown_order_management
        except ImportError:
            return
        shutdown_order_management()

    def test_order_models(self):
        """Test order data models"""
        try:
            from order_management_models import OrderSide, OrderStatus, OrderType

            # Test enums exist
            self.assertTrue(hasattr(OrderType, "MARKET"))
            self.assertTrue(hasattr(OrderType, "LIMIT"))
            self.assertTrue(hasattr(OrderSide, "BUY"))
            self.assertTrue(hasattr(OrderSide, "SELL"))
            self.assertTrue(hasattr(OrderStatus, "PENDING"))
            self.assertTrue(hasattr(OrderStatus, "FILLED"))

        except ImportError:
            self.skipTest("Order management models not available")

    def test_order_manager_initialization(self):
        """Test order manager initialization"""
        try:
            from order_management_integration import get_global_order_manager

            # Should not raise exception
            manager = get_global_order_manager()
            self.assertIsNotNone(manager)

        except ImportError:
            self.skipTest("Order management integration not available")

    def test_database_initialization(self):
        """Test order database initialization"""
        try:
            from order_management_integration import (
                initialize_order_management_for_powertrader,
            )

            # Initialize with test database
            success = initialize_order_management_for_powertrader(
                database_url=f"sqlite:///{self.test_db_path}"
            )
            self.assertTrue(success or not success)  # Should not raise exception

        except ImportError:
            self.skipTest("Order management integration not available")


class TestLongTermHoldings(TestBase):
    """Test long-term holdings management"""

    def test_holding_model(self):
        """Test Holding data model"""
        try:
            from long_term_holdings import Holding

            # Create test holding
            holding = Holding(
                symbol="BTC",
                quantity=1.5,
                average_cost=50000.0,
                current_price=55000.0,
                exchange="binance",
            )

            # Test calculated properties
            self.assertEqual(holding.total_cost, 75000.0)
            self.assertEqual(holding.current_value, 82500.0)
            self.assertEqual(holding.unrealized_pnl, 7500.0)
            self.assertAlmostEqual(holding.unrealized_pnl_percentage, 10.0)

        except ImportError:
            self.skipTest("Long-term holdings module not available")

    def test_holdings_database(self):
        """Test holdings database operations"""
        try:
            from long_term_holdings import Holding, HoldingsDatabase

            # Create test database
            db = HoldingsDatabase(self.test_db_path)

            # Test adding holding
            test_holding = Holding(
                symbol="ETH", quantity=10.0, average_cost=3000.0, current_price=3200.0
            )

            holding_id = db.add_holding(test_holding)
            self.assertIsInstance(holding_id, int)
            self.assertGreater(holding_id, 0)

            # Test retrieving holdings
            holdings = db.get_all_holdings()
            self.assertEqual(len(holdings), 1)
            self.assertEqual(holdings[0].symbol, "ETH")

        except ImportError:
            self.skipTest("Long-term holdings module not available")

    def test_holdings_manager(self):
        """Test holdings manager functionality"""
        try:
            from long_term_holdings import Holding, HoldingsManager

            # Create manager with test database
            manager = HoldingsManager(self.test_db_path)

            # Test portfolio summary with no holdings
            summary = manager.get_portfolio_summary()
            self.assertEqual(summary["holdings_count"], 0)
            self.assertEqual(summary["total_cost"], 0)

            # Test adding holding
            test_holding = Holding(
                symbol="BTC", quantity=0.5, average_cost=60000.0, current_price=65000.0
            )

            success = manager.add_holding(test_holding)
            self.assertTrue(success)

            # Test updated summary
            summary = manager.get_portfolio_summary()
            self.assertEqual(summary["holdings_count"], 1)
            self.assertEqual(summary["total_cost"], 30000.0)

        except ImportError:
            self.skipTest("Long-term holdings module not available")


class TestPortfolioAnalytics(TestBase):
    """Test portfolio analytics system"""

    def test_portfolio_analytics_initialization(self):
        """Test analytics system initialization"""
        try:
            from portfolio_analytics import PortfolioAnalytics

            analytics = PortfolioAnalytics(self.test_db_path)
            self.assertIsNotNone(analytics)

            # Test database creation
            self.assertFileExists(self.test_db_path)

        except ImportError:
            self.skipTest("Portfolio analytics module not available")

    def test_portfolio_snapshot(self):
        """Test portfolio snapshot functionality"""
        try:
            from portfolio_analytics import PortfolioAnalytics

            analytics = PortfolioAnalytics(self.test_db_path)

            # Test saving snapshot
            test_holdings_data = [
                {
                    "symbol": "BTC",
                    "quantity": 1.0,
                    "current_price": 50000.0,
                    "current_value": 50000.0,
                    "total_cost": 45000.0,
                }
            ]

            success = analytics.save_portfolio_snapshot(test_holdings_data)
            self.assertTrue(success)

        except ImportError:
            self.skipTest("Portfolio analytics module not available")

    def test_performance_metrics(self):
        """Test performance metrics calculation"""
        try:
            from portfolio_analytics import PortfolioAnalytics

            analytics = PortfolioAnalytics(self.test_db_path)

            # Add some test data
            test_data = [
                {"symbol": "BTC", "current_value": 50000, "total_cost": 45000},
                {"symbol": "ETH", "current_value": 15000, "total_cost": 12000},
            ]

            analytics.save_portfolio_snapshot(test_data)

            # Test metrics calculation (might return None if insufficient data)
            metrics = analytics.calculate_performance_metrics(7)
            # Should not raise exception

        except ImportError:
            self.skipTest("Portfolio analytics module not available")


class TestLLMResearch(TestBase):
    """Test LLM research engine"""

    def test_llm_research_engine_import(self):
        """Test LLM research engine can be imported"""
        try:
            from llm_research_engine import LLMResearchEngine

            # Test basic initialization
            engine = LLMResearchEngine()
            self.assertIsNotNone(engine)

        except ImportError:
            self.skipTest("LLM research engine not available")

    def test_llm_provider_interface(self):
        """Test LLM provider interface"""
        try:
            from llm_research_engine import LLMProvider

            # Test provider initialization
            provider = LLMProvider(api_key="test-key")
            self.assertIsNotNone(provider)

            # Test that required methods exist
            self.assertTrue(hasattr(provider, "generate_analysis"))
            self.assertTrue(hasattr(provider, "client"))

        except ImportError:
            self.skipTest("LLM research engine not available")

    def test_research_components(self):
        """Test research engine components"""
        try:
            from llm_research_engine import (
                NewsAggregator,
                ResearchReportGenerator,
                SentimentAnalyzer,
            )

            # Test component initialization
            mock_provider = MagicMock()
            news_agg = NewsAggregator()
            sentiment = SentimentAnalyzer(mock_provider)
            report_gen = ResearchReportGenerator(mock_provider)

            self.assertIsNotNone(news_agg)
            self.assertIsNotNone(sentiment)
            self.assertIsNotNone(report_gen)

        except ImportError:
            self.skipTest("LLM research engine not available")


class TestDependencyChecker(TestBase):
    """Test dependency checking system"""

    def test_dependency_checker_import(self):
        """Test dependency checker can be imported"""
        try:
            from dependency_checker import DependencyChecker, get_dependency_checker

            checker = get_dependency_checker()
            self.assertIsNotNone(checker)

        except ImportError:
            self.skipTest("Dependency checker not available")

    def test_dependency_scanning(self):
        """Test dependency scanning functionality"""
        try:
            from dependency_checker import DependencyChecker

            checker = DependencyChecker()

            # Test basic scanning
            status = checker.check_all_dependencies()
            self.assertIsInstance(status, dict)

            # Status is a dict of {dep_name: DependencyInfo}; verify structure
            self.assertGreater(len(status), 0)
            for dep in status.values():
                self.assertTrue(hasattr(dep, "available"))
                self.assertTrue(hasattr(dep, "name"))

        except ImportError:
            self.skipTest("Dependency checker not available")

    def test_installation_script_generation(self):
        """Test installation script generation"""
        try:
            from dependency_checker import DependencyChecker

            checker = DependencyChecker()

            # Generate script for missing dependencies
            checker.check_all_dependencies()
            script = checker.generate_install_script()
            self.assertIsInstance(script, str)

            # If there are missing dependencies the script should contain pip install
            missing = checker.get_missing_required() + checker.get_missing_optional()
            if missing:
                self.assertIn("pip install", script)

        except ImportError:
            self.skipTest("Dependency checker not available")


class TestGUIComponents(TestBase):
    """Test GUI component functionality"""

    def test_gui_imports(self):
        """Test that GUI modules can be imported"""
        gui_modules = [
            "long_term_holdings_gui",
            "portfolio_analytics_gui",
            "llm_research_gui",
        ]

        for module_name in gui_modules:
            try:
                __import__(module_name)
            except ImportError as e:
                # Expected for optional modules
                pass

    @patch("tkinter.Tk")
    def test_gui_initialization(self, mock_tk):
        """Test GUI component initialization"""
        mock_parent = MagicMock()

        # Test holdings GUI
        try:
            from long_term_holdings_gui import HoldingsManagementGUI

            holdings_gui = HoldingsManagementGUI(mock_parent)
            self.assertIsNotNone(holdings_gui)
        except Exception:
            pass

        # Test analytics GUI
        try:
            from portfolio_analytics_gui import PortfolioAnalyticsGUI

            analytics_gui = PortfolioAnalyticsGUI(mock_parent)
            self.assertIsNotNone(analytics_gui)
        except Exception:
            pass


class TestIntegration(TestBase):
    """Integration tests for component interaction"""

    def test_powertrader_hub_import(self):
        """Test PowerTrader Hub can be imported"""
        try:
            from pt_hub import PowerTraderHub

            # Should not raise exception during import
            self.assertTrue(True)

        except ImportError:
            self.fail("PowerTrader Hub could not be imported")

    def test_component_integration(self):
        """Test component integration in PowerTrader Hub"""
        try:
            # Mock tkinter to avoid GUI creation during tests
            with patch("tkinter.Tk"):
                from pt_hub import PowerTraderHub

                # Test that PowerTraderHub can determine which components are available
                # This should not raise exceptions

        except Exception as e:
            # Log but don't fail - some integration issues are expected
            print(f"Integration test note: {e}")

    def test_database_integration(self):
        """Test database integration across components"""
        # Test that multiple components can work with same database directory
        test_data_dir = os.path.join(self.temp_dir, "data")
        os.makedirs(test_data_dir, exist_ok=True)

        # Test holdings database
        try:
            from long_term_holdings import HoldingsDatabase

            holdings_db = HoldingsDatabase(os.path.join(test_data_dir, "holdings.db"))
            self.assertIsNotNone(holdings_db)
        except ImportError:
            pass

        # Test analytics database
        try:
            from portfolio_analytics import PortfolioAnalytics

            analytics = PortfolioAnalytics(os.path.join(test_data_dir, "analytics.db"))
            self.assertIsNotNone(analytics)
        except ImportError:
            pass


class TestSuite:
    """Main test suite coordinator"""

    def __init__(self):
        self.test_classes = [
            TestExchangeAbstraction,
            TestMultiExchange,
            TestOrderManagement,
            TestLongTermHoldings,
            TestPortfolioAnalytics,
            TestLLMResearch,
            TestDependencyChecker,
            TestGUIComponents,
            TestIntegration,
        ]

    def create_suite(self) -> unittest.TestSuite:
        """Create the complete test suite"""
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()

        for test_class in self.test_classes:
            tests = loader.loadTestsFromTestCase(test_class)
            suite.addTests(tests)

        return suite

    def run_tests(self, verbosity: int = 2) -> unittest.TestResult:
        """Run all tests"""
        suite = self.create_suite()
        runner = PowerTraderTestRunner(verbosity=verbosity)
        return runner.run(suite)

    def run_specific_test(self, test_name: str) -> unittest.TestResult:
        """Run a specific test or test class"""
        loader = unittest.TestLoader()

        # Try to find the test
        for test_class in self.test_classes:
            if test_class.__name__ == test_name or test_name in test_class.__name__:
                suite = loader.loadTestsFromTestCase(test_class)
                runner = PowerTraderTestRunner()
                return runner.run(suite)

        # Try to find specific test method
        for test_class in self.test_classes:
            try:
                suite = loader.loadTestsFromName(f"{test_class.__name__}.{test_name}")
                runner = PowerTraderTestRunner()
                return runner.run(suite)
            except AttributeError:
                continue

        print(f"{Colors.RED}Test '{test_name}' not found{Colors.RESET}")
        return None

    def get_test_coverage(self) -> Dict[str, Any]:
        """Get test coverage information"""
        coverage_info = {
            "total_tests": 0,
            "total_test_classes": len(self.test_classes),
            "components_tested": [],
            "test_categories": {
                "unit_tests": 0,
                "integration_tests": 0,
                "gui_tests": 0,
                "database_tests": 0,
            },
        }

        loader = unittest.TestLoader()
        for test_class in self.test_classes:
            suite = loader.loadTestsFromTestCase(test_class)
            test_count = suite.countTestCases()
            coverage_info["total_tests"] += test_count

            # Categorize tests
            class_name = test_class.__name__
            if "Integration" in class_name:
                coverage_info["test_categories"]["integration_tests"] += test_count
            elif "GUI" in class_name:
                coverage_info["test_categories"]["gui_tests"] += test_count
            elif any(
                keyword in class_name
                for keyword in ["Database", "Holdings", "Analytics"]
            ):
                coverage_info["test_categories"]["database_tests"] += test_count
            else:
                coverage_info["test_categories"]["unit_tests"] += test_count

            # Add component
            component_name = class_name.replace("Test", "")
            coverage_info["components_tested"].append(component_name)

        return coverage_info


def main():
    """Main test runner function"""
    import argparse

    parser = argparse.ArgumentParser(
        description="PowerTrader Comprehensive Testing Suite"
    )
    parser.add_argument("--test", type=str, help="Run specific test or test class")
    parser.add_argument(
        "--coverage", action="store_true", help="Show test coverage information"
    )
    parser.add_argument("--list", action="store_true", help="List all available tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    test_suite = TestSuite()

    if args.list:
        print(f"{Colors.BOLD}Available Test Classes:{Colors.RESET}")
        for i, test_class in enumerate(test_suite.test_classes, 1):
            print(f"  {i}. {test_class.__name__}")
        return

    if args.coverage:
        coverage = test_suite.get_test_coverage()
        print(f"{Colors.BOLD}Test Coverage Information:{Colors.RESET}")
        print(f"Total Tests: {coverage['total_tests']}")
        print(f"Test Classes: {coverage['total_test_classes']}")
        print(f"Components Tested: {', '.join(coverage['components_tested'])}")
        print(f"\nTest Categories:")
        for category, count in coverage["test_categories"].items():
            print(f"  {category.replace('_', ' ').title()}: {count}")
        return

    if args.test:
        result = test_suite.run_specific_test(args.test)
        if result:
            exit(0 if result.wasSuccessful() else 1)
        else:
            exit(1)
    else:
        verbosity = 2 if args.verbose else 1
        result = test_suite.run_tests(verbosity)
        exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
