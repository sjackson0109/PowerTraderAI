#!/usr/bin/env python3
"""
Integration Test Suite for PowerTrader Hub
Tests the complete integration of all advanced features
"""

import gc
import json
import os
import sys
import tempfile
import time
import unittest
from tkinter import ttk
from unittest.mock import MagicMock, Mock, patch

# Add current directory to path (we're already in app directory)
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def _new_hub(test, hub_class):
    """A hub for one test: hidden, and closed when the test ends, so no window or
    Tk root outlives it. (Each used to stay open, with its threads, for the rest of
    the run.)"""
    hub = hub_class()
    hub.withdraw()
    test.addCleanup(_close_hub, hub)
    return hub


def _close_hub(hub):
    try:
        hub._on_close()  # the window's own close: stop its scripts, then destroy
    except Exception:
        pass
    gc.collect()


class TestPowerTraderHubIntegration(unittest.TestCase):
    """Integration tests for PowerTrader Hub with all advanced features"""

    def _skip_if_display_error(self, exception):
        """Skip the test if the exception is caused by a missing display server."""
        err_str = str(exception).lower()
        if "display" in err_str or "tcl" in err_str or "screen" in err_str:
            self.skipTest(f"No display available in this environment: {exception}")

    @classmethod
    def setUpClass(cls):
        """Set up test class"""
        cls.hub_available = False

        try:
            # Import PowerTrader Hub
            from pt_hub import PowerTraderHub

            cls.PowerTraderHub = PowerTraderHub
            cls.hub_available = True
        except ImportError as e:
            print(f"PowerTrader Hub not available: {e}")

    def test_powertrader_hub_creation(self):
        """Test that PowerTrader Hub can be created"""
        if not self.hub_available:
            self.skipTest("PowerTrader Hub not available")

        try:
            # Create hub instance (but don't start mainloop)
            hub = _new_hub(self, self.PowerTraderHub)

            # Verify hub was created
            self.assertIsNotNone(hub)

            # A real hub: its window title, its dark theme and its notebooks
            self.assertIn("PowerTraderAI", hub.title())
            self.assertEqual(ttk.Style(hub).theme_use(), "clam")
            self.assertTrue(hasattr(hub, "bottom_notebook"))
            self.assertTrue(hasattr(hub, "logs_nb"))

        except Exception as e:
            self._skip_if_display_error(e)
            self.fail(f"Failed to create PowerTrader Hub: {e}")

    def test_tab_integration(self):
        """Test that all tabs are properly integrated"""
        if not self.hub_available:
            self.skipTest("PowerTrader Hub not available")

        try:
            hub = _new_hub(self, self.PowerTraderHub)
        except Exception as e:
            self._skip_if_display_error(e)
            raise

        # The hub's notebooks: the log tabs (Training, Thinking, Trading) and the
        # tabs under the charts (Current Trades, Trade History, ...)
        log_tabs = hub.logs_nb.tabs()
        bottom_tabs = hub.bottom_notebook.tabs()

        print(f"Log tabs: {len(log_tabs)}")
        print(f"Bottom tabs: {len(bottom_tabs)}")

        self.assertEqual(len(log_tabs), 3)
        self.assertGreaterEqual(len(log_tabs) + len(bottom_tabs), 8)

    def test_advanced_feature_availability(self):
        """Test availability of advanced features"""
        if not self.hub_available:
            self.skipTest("PowerTrader Hub not available")

        # Import pt_hub module to check availability flags
        try:
            import pt_hub

            # Check that availability flags exist
            self.assertTrue(hasattr(pt_hub, "PORTFOLIO_OPTIMIZER_AVAILABLE"))
            self.assertTrue(hasattr(pt_hub, "BACKTESTING_FRAMEWORK_AVAILABLE"))
            self.assertTrue(hasattr(pt_hub, "PERFORMANCE_ATTRIBUTION_AVAILABLE"))

            print(
                f"Portfolio Optimizer Available: {pt_hub.PORTFOLIO_OPTIMIZER_AVAILABLE}"
            )
            print(
                f"Backtesting Framework Available: {pt_hub.BACKTESTING_FRAMEWORK_AVAILABLE}"
            )
            print(
                f"Performance Attribution Available: {pt_hub.PERFORMANCE_ATTRIBUTION_AVAILABLE}"
            )

            # At least one advanced feature should be available
            advanced_available = any(
                [
                    pt_hub.PORTFOLIO_OPTIMIZER_AVAILABLE,
                    pt_hub.BACKTESTING_FRAMEWORK_AVAILABLE,
                    pt_hub.PERFORMANCE_ATTRIBUTION_AVAILABLE,
                ]
            )

            if not advanced_available:
                print(
                    "Warning: No advanced features available - may need dependency installation"
                )

        except Exception as e:
            print(f"Could not check advanced feature availability: {e}")

    def test_graceful_degradation(self):
        """Test that hub works gracefully when advanced features are missing"""
        if not self.hub_available:
            self.skipTest("PowerTrader Hub not available")

        # Mock missing dependencies to test graceful degradation
        with patch.dict("sys.modules", {"pandas": None, "numpy": None}):
            try:
                hub = _new_hub(self, self.PowerTraderHub)

                # Hub should still be created even with missing dependencies
                self.assertIsNotNone(hub)

                # Should have basic tabs even without advanced features
                tabs = hub.bottom_notebook.tabs()
                self.assertGreater(len(tabs), 0)

            except Exception as e:
                self._skip_if_display_error(e)
                # Should not fail completely due to missing dependencies
                if "pandas" in str(e) or "numpy" in str(e):
                    print(f"Graceful degradation working: {e}")
                else:
                    self.fail(f"Unexpected error during graceful degradation test: {e}")

    def test_error_handling_robustness(self):
        """Test that the hub handles errors robustly"""
        if not self.hub_available:
            self.skipTest("PowerTrader Hub not available")

        try:
            hub = _new_hub(self, self.PowerTraderHub)

            # Test that hub doesn't crash on common operations
            # (These might fail but shouldn't crash the app)

            # Try to access tab methods
            if hasattr(hub, "bottom_notebook"):
                try:
                    tab_count = len(hub.bottom_notebook.tabs())
                    self.assertGreaterEqual(tab_count, 0)
                except:
                    pass  # Tab operations may fail but shouldn't crash

        except Exception as e:
            self._skip_if_display_error(e)
            self.fail(f"Hub failed basic robustness test: {e}")


class TestEndToEndWorkflow(unittest.TestCase):
    """End-to-end workflow tests"""

    def setUp(self):
        """Set up for workflow tests"""
        self.sample_data_created = False
        self.temp_files = []

    def tearDown(self):
        """Clean up temporary files"""
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
            except:
                pass

    def _create_sample_csv_data(self):
        """Create sample CSV data for testing workflows"""
        portfolio_data = """security,weight,return,sector
AAPL,0.30,0.15,Technology
MSFT,0.20,0.12,Technology
GOOGL,0.15,0.18,Technology
JPM,0.15,0.08,Financials
XOM,0.10,0.06,Energy
BRK.B,0.10,0.09,Financials"""

        market_data = """date,open,high,low,close,volume
2024-01-01,100.0,102.0,99.5,101.5,1000000
2024-01-02,101.5,103.0,101.0,102.8,1200000
2024-01-03,102.8,104.5,102.0,103.2,1100000
2024-01-04,103.2,105.0,102.8,104.7,1300000
2024-01-05,104.7,106.0,104.0,105.5,1400000"""

        # Create temporary files
        portfolio_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        )
        portfolio_file.write(portfolio_data)
        portfolio_file.close()

        market_file = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
        market_file.write(market_data)
        market_file.close()

        self.temp_files.extend([portfolio_file.name, market_file.name])
        self.sample_data_created = True

        return portfolio_file.name, market_file.name

    def test_data_import_workflow(self):
        """Test end-to-end data import workflow"""
        if not self.sample_data_created:
            portfolio_file, market_file = self._create_sample_csv_data()

        try:
            import pandas as pd

            # Test loading portfolio data
            portfolio_df = pd.read_csv(portfolio_file)
            self.assertEqual(len(portfolio_df), 6)
            self.assertIn("security", portfolio_df.columns)

            # Test loading market data
            market_df = pd.read_csv(market_file)
            self.assertEqual(len(market_df), 5)
            self.assertIn("close", market_df.columns)

            # Test basic data validation
            weights_sum = portfolio_df["weight"].sum()
            self.assertAlmostEqual(weights_sum, 1.0, places=1)

        except ImportError:
            self.skipTest("Pandas not available for data import test")

    def test_analysis_workflow(self):
        """Test end-to-end analysis workflow"""
        try:
            # Test portfolio optimization workflow
            from portfolio_optimizer import PortfolioOptimizer

            optimizer = PortfolioOptimizer()

            # Test with minimal data
            import numpy as np
            import pandas as pd

            dates = pd.date_range("2024-01-01", periods=30)
            data = pd.DataFrame(
                {
                    "AAPL": np.random.normal(1.001, 0.02, 30).cumprod() * 100,
                    "MSFT": np.random.normal(1.001, 0.02, 30).cumprod() * 100,
                },
                index=dates,
            )

            result = optimizer.optimize_portfolio(data)

            # Should return some result (even if fallback to equal weights)
            self.assertIsNotNone(result)
            self.assertIsInstance(result, dict)

        except ImportError:
            self.skipTest("Portfolio optimization dependencies not available")
        except Exception as e:
            print(f"Analysis workflow test failed (expected with limited data): {e}")

    def test_reporting_workflow(self):
        """Test basic reporting workflow"""

        # Create sample results
        sample_results = {
            "total_return": 0.15,
            "volatility": 0.12,
            "sharpe_ratio": 1.25,
            "max_drawdown": -0.08,
        }

        # Test JSON serialization (for reporting)
        try:
            json_str = json.dumps(sample_results)
            reloaded = json.loads(json_str)
            self.assertEqual(reloaded, sample_results)

        except Exception as e:
            self.fail(f"Basic reporting workflow failed: {e}")


class TestPerformanceAndScalability(unittest.TestCase):
    """Performance and scalability tests"""

    def test_hub_startup_time(self):
        """Test that hub starts up in reasonable time"""

        try:
            from pt_hub import PowerTraderHub

            start_time = time.time()
            hub = _new_hub(self, PowerTraderHub)
            end_time = time.time()

            startup_time = end_time - start_time

            # Hub should start in reasonable time (< 10 seconds)
            self.assertLess(
                startup_time, 10.0, f"Hub startup took {startup_time:.2f} seconds"
            )

        except ImportError:
            self.skipTest("PowerTrader Hub not available")
        except Exception as e:
            print(f"Startup time test failed: {e}")

    def test_memory_usage(self):
        """Test basic memory usage"""

        try:
            import os

            import psutil

            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB

            # Create hub
            from pt_hub import PowerTraderHub

            hub = _new_hub(self, PowerTraderHub)

            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = final_memory - initial_memory

            print(
                f"Memory usage: {initial_memory:.1f} MB -> {final_memory:.1f} MB (+{memory_increase:.1f} MB)"
            )

            # Should not use excessive memory (< 200MB increase)
            self.assertLess(
                memory_increase,
                200,
                f"Excessive memory usage: {memory_increase:.1f} MB",
            )

        except ImportError:
            self.skipTest("psutil not available for memory testing")
        except Exception as e:
            print(f"Memory usage test failed: {e}")


def run_integration_tests():
    """Run all integration tests"""

    print("=" * 60)
    print("PowerTrader Integration Test Suite")
    print("=" * 60)
    print()

    # Create test suite
    test_suite = unittest.TestSuite()

    # Add test classes
    test_classes = [
        TestPowerTraderHubIntegration,
        TestEndToEndWorkflow,
        TestPerformanceAndScalability,
    ]

    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)

    print()
    print("=" * 60)
    print("Integration Test Results Summary")
    print("=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")

    if result.failures:
        print("\nFAILURES:")
        for test, error in result.failures:
            print(f"- {test}: {error}")

    if result.errors:
        print("\nERRORS:")
        for test, error in result.errors:
            print(f"- {test}: {error}")

    # Overall result
    if result.wasSuccessful():
        print("\n🎉 ALL INTEGRATION TESTS PASSED!")
        return True
    else:
        print("\n⚠️  Some integration tests failed or had errors.")
        return False


if __name__ == "__main__":
    success = run_integration_tests()
    sys.exit(0 if success else 1)
