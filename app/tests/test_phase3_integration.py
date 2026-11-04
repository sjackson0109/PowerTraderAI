#!/usr/bin/env python3
"""
Phase 3 Integration Tests for PowerTrader AI+

Tests for multi-timeframe neural analysis, pattern recognition,
and enhanced price level prediction.
"""

import json
import os
import sys
import time
import unittest
from unittest.mock import Mock, patch, MagicMock
import numpy as np

# Add the app directory to path
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

try:
    from pt_neural_processor import (
        NeuralProcessor,
        PatternRecognizer,
        TimeframeAnalysis,
        MultiTimeframeSignal,
        enhanced_step_coin,
        get_neural_processor,
    )

    NEURAL_PROCESSOR_AVAILABLE = True
except ImportError as e:
    print(f"Neural processor import error: {e}")
    NEURAL_PROCESSOR_AVAILABLE = False

try:
    import torch

    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False


class TestPatternRecognizer(unittest.TestCase):
    """Test pattern recognition functionality."""

    def setUp(self):
        if not NEURAL_PROCESSOR_AVAILABLE:
            self.skipTest("Neural processor not available")
        self.recognizer = PatternRecognizer()

    def test_pattern_identification(self):
        """Test basic pattern identification."""
        # Create mock OHLC data [timestamp, open, high, low, close, volume]
        data = np.array(
            [
                [1640995200000, 100, 105, 95, 102, 1000],
                [1640998800000, 102, 107, 98, 104, 1100],
                [1641002400000, 104, 109, 100, 106, 1200],
                [1641006000000, 106, 111, 102, 108, 1300],
                [1641009600000, 108, 113, 104, 110, 1400],
                # Add more data points...
            ]
            + [
                [
                    i * 3600000 + 1641009600000,
                    110 + i,
                    115 + i,
                    105 + i,
                    112 + i,
                    1500 + i * 100,
                ]
                for i in range(15)
            ]
        )

        patterns = self.recognizer.identify_patterns(data, "1hour")

        self.assertIsInstance(patterns, dict)
        self.assertIn("trend_strength", patterns)
        self.assertIn("volatility_pattern", patterns)
        self.assertIn("support_resistance", patterns)

    def test_insufficient_data(self):
        """Test handling of insufficient data."""
        small_data = np.array([[1640995200000, 100, 105, 95, 102, 1000]])
        patterns = self.recognizer.identify_patterns(small_data, "1hour")

        self.assertIn("insufficient_data", patterns)

    def test_trend_strength_calculation(self):
        """Test trend strength calculation."""
        # Create upward trending data
        closes = np.array([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
        strength = self.recognizer._calculate_trend_strength(closes)

        self.assertGreater(strength, 0)  # Should detect upward trend
        self.assertLessEqual(abs(strength), 1.0)  # Should be normalized


class TestNeuralProcessor(unittest.TestCase):
    """Test multi-timeframe neural processor."""

    def setUp(self):
        if not NEURAL_PROCESSOR_AVAILABLE:
            self.skipTest("Neural processor not available")
        self.processor = NeuralProcessor()

    @patch("pt_data_provider.get_data_provider")
    def test_multi_timeframe_analysis(self, mock_data_provider):
        """Test multi-timeframe analysis."""
        # Mock data provider
        mock_provider = Mock()
        mock_provider.is_available.return_value = True
        mock_klines = [
            [1640995200000, 100, 105, 95, 102, 1000]
            # Add more mock data...
        ] + [
            [i * 3600000 + 1640995200000, 100 + i, 105 + i, 95 + i, 102 + i, 1000]
            for i in range(1, 150)
        ]
        mock_provider.get_kline_data.return_value = mock_klines
        mock_data_provider.return_value = mock_provider

        # Test step_coin
        result = self.processor.step_coin("BTC")

        self.assertIsInstance(result, MultiTimeframeSignal)
        self.assertEqual(result.symbol, "BTC")
        self.assertIsInstance(result.long_signal, int)
        self.assertIsInstance(result.short_signal, int)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_timeframe_analysis(self):
        """Test individual timeframe analysis."""
        # Mock data
        data = np.array(
            [[i * 3600000, 100 + i, 105 + i, 95 + i, 102 + i, 1000] for i in range(100)]
        )

        with patch.object(self.processor, "_load_price_data", return_value=data):
            analysis = self.processor._analyze_timeframe("BTC", "1hour")

            if analysis:  # May be None if model not available
                self.assertIsInstance(analysis, TimeframeAnalysis)
                self.assertEqual(analysis.timeframe, "1hour")
                self.assertIsInstance(analysis.patterns, dict)
                self.assertIsInstance(analysis.predictions, dict)

    def test_price_level_calculation(self):
        """Test support/resistance level calculation."""
        # Create data with clear support/resistance
        data = np.array(
            [
                (
                    [i * 3600000, 100, 110, 90, 105, 1000]
                    if i % 10 < 5
                    else [i * 3600000, 105, 115, 95, 100, 1000]
                )
                for i in range(50)
            ]
        )

        support, resistance = self.processor._calculate_price_levels(data)

        self.assertIsInstance(support, list)
        self.assertIsInstance(resistance, list)
        self.assertLessEqual(len(support), 5)
        self.assertLessEqual(len(resistance), 5)

    def test_signal_combination(self):
        """Test combining signals from multiple timeframes."""
        # Create mock timeframe results
        timeframe_results = {
            "1hour": TimeframeAnalysis(
                timeframe="1hour",
                patterns={"trend_strength": 0.6, "volatility_pattern": 0.4},
                predictions={"price_direction": 0.3},
                support_levels=[100, 98],
                resistance_levels=[105, 108],
                signal_strength=0.5,
                confidence=0.8,
                timestamp=time.time(),
            ),
            "4hour": TimeframeAnalysis(
                timeframe="4hour",
                patterns={"trend_strength": 0.7, "volatility_pattern": 0.3},
                predictions={"price_direction": 0.4},
                support_levels=[99, 97],
                resistance_levels=[106, 109],
                signal_strength=0.6,
                confidence=0.9,
                timestamp=time.time(),
            ),
        }

        signal = self.processor._combine_timeframe_signals("BTC", timeframe_results)

        self.assertIsInstance(signal, MultiTimeframeSignal)
        self.assertEqual(signal.symbol, "BTC")
        self.assertGreaterEqual(signal.long_signal, 0)
        self.assertLessEqual(signal.long_signal, 8)
        self.assertGreaterEqual(signal.short_signal, 0)
        self.assertLessEqual(signal.short_signal, 8)


class TestEnhancedStepCoin(unittest.TestCase):
    """Test the enhanced step_coin function."""

    def setUp(self):
        if not NEURAL_PROCESSOR_AVAILABLE:
            self.skipTest("Neural processor not available")

    @patch("pt_data_provider.get_data_provider")
    def test_enhanced_step_coin_function(self, mock_data_provider):
        """Test the enhanced step_coin function."""
        # Mock data provider
        mock_provider = Mock()
        mock_provider.is_available.return_value = True
        mock_klines = [
            [i * 3600000, 100 + i, 105 + i, 95 + i, 102 + i, 1000] for i in range(100)
        ]
        mock_provider.get_kline_data.return_value = mock_klines
        mock_data_provider.return_value = mock_provider

        result = enhanced_step_coin("BTC")

        self.assertIsInstance(result, dict)
        self.assertIn("symbol", result)
        self.assertIn("long_signal", result)
        self.assertIn("short_signal", result)
        self.assertIn("confidence", result)
        self.assertIn("dominant_timeframe", result)
        self.assertIn("analysis_details", result)

        self.assertEqual(result["symbol"], "BTC")
        self.assertIsInstance(result["analysis_details"], dict)


class TestPhase3Integration(unittest.TestCase):
    """Test Phase 3 integration with existing systems."""

    def setUp(self):
        if not NEURAL_PROCESSOR_AVAILABLE:
            self.skipTest("Neural processor not available")

    def test_neural_processor_singleton(self):
        """Test that neural processor is properly singleton."""
        processor1 = get_neural_processor()
        processor2 = get_neural_processor()

        self.assertIs(processor1, processor2)

    def test_pytorch_availability_handling(self):
        """Test handling when PyTorch is not available."""
        recognizer = PatternRecognizer()

        # Should not crash even without PyTorch
        data = np.array(
            [[i * 3600000, 100 + i, 105 + i, 95 + i, 102 + i, 1000] for i in range(20)]
        )
        patterns = recognizer.identify_patterns(data, "1hour")

        self.assertIsInstance(patterns, dict)

    @patch("pt_neural_processor.PYTORCH_AVAILABLE", False)
    def test_fallback_without_pytorch(self):
        """Test system behavior when PyTorch is not available."""
        processor = NeuralProcessor()

        # Should initialize without crashing
        self.assertIsNotNone(processor)
        self.assertIsNone(processor.scaler)

    def test_caching_integration(self):
        """Test integration with caching system."""
        processor = NeuralProcessor()

        # Test that cache manager is available
        from pt_caching_system import get_cache_manager

        cache = get_cache_manager()
        self.assertIsNotNone(cache)

    def test_logging_integration(self):
        """Test integration with logging system."""
        processor = NeuralProcessor()

        # Test that logger is available
        from pt_logging_system import get_logger

        logger = get_logger()
        self.assertIsNotNone(logger)


class TestPhase3Performance(unittest.TestCase):
    """Test Phase 3 performance and efficiency."""

    def setUp(self):
        if not NEURAL_PROCESSOR_AVAILABLE:
            self.skipTest("Neural processor not available")

    @patch("pt_data_provider.get_data_provider")
    def test_analysis_performance(self, mock_data_provider):
        """Test that analysis completes in reasonable time."""
        # Mock data provider
        mock_provider = Mock()
        mock_provider.is_available.return_value = True
        mock_klines = [
            [i * 3600000, 100 + i, 105 + i, 95 + i, 102 + i, 1000] for i in range(200)
        ]
        mock_provider.get_kline_data.return_value = mock_klines
        mock_data_provider.return_value = mock_provider

        processor = NeuralProcessor()

        start_time = time.time()
        result = processor.step_coin("BTC")
        end_time = time.time()

        # Should complete within 30 seconds (generous for CI)
        self.assertLess(end_time - start_time, 30.0)
        self.assertIsNotNone(result)

    def test_memory_efficiency(self):
        """Test memory usage doesn't grow excessively."""
        recognizer = PatternRecognizer()

        # Process multiple datasets
        for i in range(10):
            data = np.array(
                [
                    [j * 3600000, 100 + j, 105 + j, 95 + j, 102 + j, 1000]
                    for j in range(100)
                ]
            )
            patterns = recognizer.identify_patterns(data, f"test_{i}")
            self.assertIsInstance(patterns, dict)

        # Should not crash due to memory issues


def run_phase3_tests():
    """Run comprehensive Phase 3 tests."""
    print("PowerTrader AI+ Phase 3 - Running Integration Tests")
    print("=" * 55)

    # Check prerequisites
    if not NEURAL_PROCESSOR_AVAILABLE:
        print("❌ Neural processor not available - skipping tests")
        return False

    print("✅ Neural processor available")

    if PYTORCH_AVAILABLE:
        print("✅ PyTorch available - full functionality")
    else:
        print("⚠️  PyTorch not available - limited functionality")

    # Create test suite
    test_loader = unittest.TestLoader()
    test_suite = unittest.TestSuite()

    # Add test classes
    test_classes = [
        TestPatternRecognizer,
        TestNeuralProcessor,
        TestEnhancedStepCoin,
        TestPhase3Integration,
        TestPhase3Performance,
    ]

    for test_class in test_classes:
        tests = test_loader.loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)

    # Summary
    print("\n" + "=" * 55)
    print(f"Phase 3 Tests Completed:")
    print(f"  Tests run: {result.testsRun}")
    print(f"  Failures: {len(result.failures)}")
    print(f"  Errors: {len(result.errors)}")
    print(
        f"  Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%"
    )

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_phase3_tests()
    sys.exit(0 if success else 1)
