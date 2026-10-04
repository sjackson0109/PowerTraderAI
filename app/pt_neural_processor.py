#!/usr/bin/env python3
"""
Advanced Neural Processor for PowerTrader AI+ - Phase 3

This module implements multi-timeframe neural network analysis, pattern recognition,
and advanced price level prediction for enhanced trading signals.
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from datetime import datetime, timedelta

try:
    import torch
    import torch.nn.functional as F
    from sklearn.preprocessing import StandardScaler
    from pt_neural_network import TradingLSTM, FeatureEngineering
    from pt_model_evaluation import ModelEvaluator

    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False

from pt_logging_system import get_logger
from pt_caching_system import get_cache_manager

logger = get_logger()
cache_manager = get_cache_manager()


@dataclass
class TimeframeAnalysis:
    """Results from analyzing a specific timeframe."""

    timeframe: str
    patterns: Dict[str, float]
    predictions: Dict[str, float]
    support_levels: List[float]
    resistance_levels: List[float]
    signal_strength: float
    confidence: float
    timestamp: float


@dataclass
class MultiTimeframeSignal:
    """Combined signal from multiple timeframe analysis."""

    symbol: str
    long_signal: int
    short_signal: int
    confidence: float
    dominant_timeframe: str
    signal_details: Dict[str, TimeframeAnalysis]
    timestamp: float


class PatternRecognizer:
    """Advanced pattern recognition for trading signals."""

    def __init__(self):
        self.logger = get_logger()

    def identify_patterns(self, data: np.ndarray, timeframe: str) -> Dict[str, float]:
        """
        Identify trading patterns in price data.

        Args:
            data: OHLC price data array
            timeframe: Timeframe being analyzed

        Returns:
            Dictionary of pattern strengths (0.0 to 1.0)
        """
        patterns = {}

        try:
            if len(data) < 20:
                return {"insufficient_data": 1.0}

            # Extract price components
            closes = data[:, 3]  # Assuming close is 4th column
            highs = data[:, 2]  # High is 3rd column
            lows = data[:, 1]  # Low is 2nd column

            # Pattern detection
            patterns["trend_strength"] = self._calculate_trend_strength(closes)
            patterns["volatility_pattern"] = self._calculate_volatility_pattern(closes)
            patterns["support_resistance"] = self._find_support_resistance_strength(
                closes, highs, lows
            )
            patterns["momentum_divergence"] = self._detect_momentum_divergence(closes)
            patterns["breakout_potential"] = self._assess_breakout_potential(
                closes, highs, lows
            )

            self.logger.debug(f"Identified patterns for {timeframe}: {patterns}")

        except Exception as e:
            self.logger.error(f"Pattern recognition error for {timeframe}: {e}")
            patterns = {"error": 1.0}

        return patterns

    def _calculate_trend_strength(self, closes: np.ndarray) -> float:
        """Calculate trend strength (-1.0 to 1.0)."""
        if len(closes) < 10:
            return 0.0

        # Use moving averages to determine trend
        ma_short = np.mean(closes[-5:])
        ma_long = np.mean(closes[-20:] if len(closes) >= 20 else closes)

        if ma_long == 0:
            return 0.0

        trend = (ma_short - ma_long) / ma_long
        return np.clip(trend * 10, -1.0, 1.0)  # Scale and clip

    def _calculate_volatility_pattern(self, closes: np.ndarray) -> float:
        """Calculate volatility pattern strength (0.0 to 1.0)."""
        if len(closes) < 10:
            return 0.0

        returns = np.diff(closes) / closes[:-1]
        volatility = np.std(returns)

        # Normalize volatility (higher volatility = higher pattern strength)
        return min(volatility * 100, 1.0)

    def _find_support_resistance_strength(
        self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray
    ) -> float:
        """Find strength of support/resistance levels."""
        if len(closes) < 10:
            return 0.0

        current_price = closes[-1]

        # Find recent highs and lows
        recent_highs = highs[-10:]
        recent_lows = lows[-10:]

        # Count how many times price tested similar levels
        resistance_tests = 0
        support_tests = 0

        tolerance = current_price * 0.01  # 1% tolerance

        for high in recent_highs:
            if abs(current_price - high) < tolerance:
                resistance_tests += 1

        for low in recent_lows:
            if abs(current_price - low) < tolerance:
                support_tests += 1

        strength = (resistance_tests + support_tests) / 10.0
        return min(strength, 1.0)

    def _detect_momentum_divergence(self, closes: np.ndarray) -> float:
        """Detect momentum divergence patterns."""
        if len(closes) < 20:
            return 0.0

        # Simple momentum using rate of change
        roc_short = (closes[-1] - closes[-5]) / closes[-5] if closes[-5] != 0 else 0
        roc_long = (
            (closes[-1] - closes[-15]) / closes[-15]
            if len(closes) >= 15 and closes[-15] != 0
            else 0
        )

        # Divergence when short and long term momentum disagree
        if roc_short * roc_long < 0:  # Opposite signs
            return abs(roc_short - roc_long)

        return 0.0

    def _assess_breakout_potential(
        self, closes: np.ndarray, highs: np.ndarray, lows: np.ndarray
    ) -> float:
        """Assess potential for price breakout."""
        if len(closes) < 10:
            return 0.0

        # Calculate recent range
        recent_high = np.max(highs[-10:])
        recent_low = np.min(lows[-10:])
        current_price = closes[-1]

        if recent_high == recent_low:
            return 0.0

        # Position within range
        range_position = (current_price - recent_low) / (recent_high - recent_low)

        # High breakout potential near range extremes
        if range_position > 0.8:  # Near resistance
            return range_position
        elif range_position < 0.2:  # Near support
            return 1.0 - range_position

        return 0.0


class NeuralProcessor:
    """
    Advanced neural processor with multi-timeframe analysis.

    This implements the core Phase 3 functionality for analyzing multiple
    timeframes simultaneously and generating enhanced trading signals.
    """

    def __init__(self):
        self.logger = get_logger()
        self.pattern_recognizer = PatternRecognizer()
        self.scaler = StandardScaler() if PYTORCH_AVAILABLE else None

        # Timeframes for multi-timeframe analysis
        self.timeframes = [
            "1hour",
            "2hour",
            "4hour",
            "8hour",
            "12hour",
            "1day",
            "1week",
        ]

        # Cache for models and data
        self.models: Dict[str, Any] = {}
        self.feature_cache: Dict[str, Tuple[np.ndarray, float]] = {}

        self.logger.info("Advanced neural processor initialized for Phase 3")

    def step_coin(self, symbol: str) -> MultiTimeframeSignal:
        """
        Process a coin across multiple timeframes for enhanced signal generation.

        This is the main entry point that implements the Phase 3 multi-timeframe analysis.

        Args:
            symbol: Cryptocurrency symbol (e.g., 'BTC')

        Returns:
            MultiTimeframeSignal with combined analysis results
        """
        self.logger.info(f"Starting multi-timeframe analysis for {symbol}")

        timeframe_results = {}

        try:
            # Analyze each timeframe
            for timeframe in self.timeframes:
                analysis = self._analyze_timeframe(symbol, timeframe)
                if analysis:
                    timeframe_results[timeframe] = analysis

            # Combine signals from all timeframes
            combined_signal = self._combine_timeframe_signals(symbol, timeframe_results)

            self.logger.info(
                f"Multi-timeframe analysis completed for {symbol}: "
                f"Long={combined_signal.long_signal}, Short={combined_signal.short_signal}, "
                f"Confidence={combined_signal.confidence:.2f}"
            )

            return combined_signal

        except Exception as e:
            self.logger.error(f"Error in multi-timeframe analysis for {symbol}: {e}")
            # Return default signal on error
            return MultiTimeframeSignal(
                symbol=symbol,
                long_signal=0,
                short_signal=0,
                confidence=0.0,
                dominant_timeframe="none",
                signal_details={},
                timestamp=time.time(),
            )

    def _analyze_timeframe(
        self, symbol: str, timeframe: str
    ) -> Optional[TimeframeAnalysis]:
        """Analyze a specific timeframe for the symbol."""
        try:
            # Get cached or load fresh data
            cache_key = f"{symbol}_{timeframe}_data"
            cached_data = cache_manager.get_market_data(cache_key)

            if cached_data is None:
                # Load price data for this timeframe
                data = self._load_price_data(symbol, timeframe)
                if data is None or len(data) < 20:
                    return None

                cache_manager.cache_market_data(
                    cache_key, data, ttl_seconds=300
                )  # Cache for 5 minutes
            else:
                data = cached_data

            # Pattern recognition
            patterns = self.pattern_recognizer.identify_patterns(data, timeframe)

            # Neural network predictions
            predictions = self._generate_predictions(symbol, data, timeframe)

            # Support/resistance levels
            support_levels, resistance_levels = self._calculate_price_levels(data)

            # Calculate signal strength and confidence
            signal_strength = self._calculate_signal_strength(patterns, predictions)
            confidence = self._calculate_confidence(patterns, predictions, len(data))

            return TimeframeAnalysis(
                timeframe=timeframe,
                patterns=patterns,
                predictions=predictions,
                support_levels=support_levels,
                resistance_levels=resistance_levels,
                signal_strength=signal_strength,
                confidence=confidence,
                timestamp=time.time(),
            )

        except Exception as e:
            self.logger.error(f"Error analyzing {timeframe} for {symbol}: {e}")
            return None

    def _load_price_data(self, symbol: str, timeframe: str) -> Optional[np.ndarray]:
        """Load price data for the specified timeframe."""
        try:
            # Try to load from data provider
            from pt_data_provider import get_data_provider

            data_provider = get_data_provider()
            if not data_provider or not data_provider.is_available():
                self.logger.warning(
                    f"Data provider not available for {symbol} {timeframe}"
                )
                return None

            # Convert timeframe to data provider format
            provider_timeframe = (
                timeframe.replace("hour", "h").replace("day", "d").replace("week", "w")
            )

            # Get kline data
            klines = data_provider.get_kline_data(
                f"{symbol}USDT", provider_timeframe, limit=200
            )

            if not klines or len(klines) == 0:
                return None

            # Convert to numpy array [timestamp, open, high, low, close, volume]
            if isinstance(klines, str):
                import json

                klines = json.loads(klines)

            data = np.array([[float(x) for x in candle] for candle in klines])

            return data

        except Exception as e:
            self.logger.error(f"Error loading price data for {symbol} {timeframe}: {e}")
            return None

    def _generate_predictions(
        self, symbol: str, data: np.ndarray, timeframe: str
    ) -> Dict[str, float]:
        """Generate neural network predictions for the timeframe."""
        predictions = {
            "price_direction": 0.0,
            "price_magnitude": 0.0,
            "volatility": 0.0,
        }

        if not PYTORCH_AVAILABLE:
            return predictions

        try:
            # Load or get cached model
            model = self._get_model(symbol)
            if model is None:
                return predictions

            # Prepare features
            features = self._prepare_features(data)
            if features is None:
                return predictions

            # Generate predictions
            with torch.no_grad():
                if isinstance(model, torch.nn.Module):
                    model.eval()
                    tensor_features = torch.tensor(features, dtype=torch.float32)

                    if len(tensor_features.shape) == 2:
                        tensor_features = tensor_features.unsqueeze(
                            0
                        )  # Add batch dimension

                    prediction = model(tensor_features)

                    if prediction.shape[-1] >= 1:
                        predictions["price_direction"] = float(prediction[0, -1, 0])

                        if prediction.shape[-1] >= 3:
                            predictions["price_magnitude"] = float(prediction[0, -1, 1])
                            predictions["volatility"] = float(prediction[0, -1, 2])

        except Exception as e:
            self.logger.error(
                f"Error generating predictions for {symbol} {timeframe}: {e}"
            )

        return predictions

    def _get_model(self, symbol: str) -> Optional[Any]:
        """Get or load the neural network model for the symbol."""
        if symbol in self.models:
            return self.models[symbol]

        try:
            import pt_paths

            model_path = os.path.join(
                pt_paths.models_dir(), f"{symbol.lower()}_neural_model.pth"
            )
            if os.path.exists(model_path):
                model = TradingLSTM(
                    input_size=20, hidden_size=128, num_layers=3, output_size=1
                )
                model.load_state_dict(torch.load(model_path, map_location="cpu"))
                self.models[symbol] = model
                return model
        except Exception as e:
            self.logger.error(f"Error loading model for {symbol}: {e}")

        return None

    def _prepare_features(self, data: np.ndarray) -> Optional[np.ndarray]:
        """Prepare features from price data for neural network input."""
        try:
            if len(data) < 60:  # Need at least 60 data points for sequence
                return None

            # Use feature engineering if available
            feature_engineer = FeatureEngineering() if PYTORCH_AVAILABLE else None

            if feature_engineer:
                # Convert to DataFrame for feature engineering
                import pandas as pd

                df = pd.DataFrame(
                    data,
                    columns=["timestamp", "open", "high", "low", "close", "volume"],
                )
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

                features_df = feature_engineer.calculate_features(df)

                # Select last 60 rows for sequence
                features = (
                    features_df.select_dtypes(include=[np.number])
                    .fillna(0)
                    .values[-60:]
                )

                # Scale features
                if self.scaler:
                    features = self.scaler.fit_transform(features)

                return features
            else:
                # Simple feature preparation
                closes = data[-60:, 4]  # Last 60 close prices
                features = np.diff(closes) / closes[:-1]  # Returns
                features = np.pad(
                    features, (0, 1), mode="constant"
                )  # Pad to maintain length

                return features.reshape(-1, 1)

        except Exception as e:
            self.logger.error(f"Error preparing features: {e}")
            return None

    def _calculate_price_levels(
        self, data: np.ndarray
    ) -> Tuple[List[float], List[float]]:
        """Calculate dynamic support and resistance levels."""
        try:
            if len(data) < 20:
                return [], []

            highs = data[:, 2]
            lows = data[:, 1]

            # Find local maxima and minima
            resistance_levels = []
            support_levels = []

            # Simple peak/trough detection
            for i in range(1, len(highs) - 1):
                # Resistance (local high)
                if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                    resistance_levels.append(float(highs[i]))

                # Support (local low)
                if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                    support_levels.append(float(lows[i]))

            # Keep only the most significant levels (last 5)
            resistance_levels = sorted(resistance_levels, reverse=True)[:5]
            support_levels = sorted(support_levels)[:5]

            return support_levels, resistance_levels

        except Exception as e:
            self.logger.error(f"Error calculating price levels: {e}")
            return [], []

    def _calculate_signal_strength(
        self, patterns: Dict[str, float], predictions: Dict[str, float]
    ) -> float:
        """Calculate overall signal strength from patterns and predictions."""
        try:
            # Combine pattern and prediction strengths
            pattern_strength = np.mean(
                [abs(v) for v in patterns.values() if isinstance(v, (int, float))]
            )
            prediction_strength = abs(predictions.get("price_direction", 0.0))

            return (pattern_strength + prediction_strength) / 2.0

        except Exception:
            return 0.0

    def _calculate_confidence(
        self,
        patterns: Dict[str, float],
        predictions: Dict[str, float],
        data_length: int,
    ) -> float:
        """Calculate confidence level for the analysis."""
        try:
            # Base confidence on data quality and signal consistency
            data_quality = min(
                data_length / 200.0, 1.0
            )  # More data = higher confidence

            # Pattern consistency
            pattern_values = [
                v for v in patterns.values() if isinstance(v, (int, float))
            ]
            pattern_std = np.std(pattern_values) if pattern_values else 1.0
            pattern_consistency = 1.0 / (1.0 + pattern_std)

            # Prediction confidence
            pred_magnitude = abs(predictions.get("price_direction", 0.0))
            prediction_confidence = min(pred_magnitude, 1.0)

            # Combine confidences
            confidence = (
                data_quality + pattern_consistency + prediction_confidence
            ) / 3.0

            return min(confidence, 1.0)

        except Exception:
            return 0.0

    def _combine_timeframe_signals(
        self, symbol: str, timeframe_results: Dict[str, TimeframeAnalysis]
    ) -> MultiTimeframeSignal:
        """Combine signals from multiple timeframes into a unified signal."""
        if not timeframe_results:
            return MultiTimeframeSignal(
                symbol=symbol,
                long_signal=0,
                short_signal=0,
                confidence=0.0,
                dominant_timeframe="none",
                signal_details={},
                timestamp=time.time(),
            )

        # Weight timeframes by importance (longer timeframes have higher weight)
        timeframe_weights = {
            "1hour": 1.0,
            "2hour": 1.2,
            "4hour": 1.5,
            "8hour": 1.8,
            "12hour": 2.0,
            "1day": 2.5,
            "1week": 3.0,
        }

        weighted_signals = []
        total_weight = 0.0
        dominant_timeframe = "none"
        max_confidence = 0.0

        for timeframe, analysis in timeframe_results.items():
            weight = timeframe_weights.get(timeframe, 1.0)

            # Calculate signal direction from patterns and predictions
            signal_direction = analysis.predictions.get("price_direction", 0.0)
            pattern_trend = analysis.patterns.get("trend_strength", 0.0)

            # Combined signal value
            combined_signal = (signal_direction + pattern_trend) / 2.0

            # Weight by confidence
            weighted_signal = combined_signal * analysis.confidence * weight
            weighted_signals.append(weighted_signal)
            total_weight += analysis.confidence * weight

            # Track dominant timeframe
            if analysis.confidence > max_confidence:
                max_confidence = analysis.confidence
                dominant_timeframe = timeframe

        # Calculate final signals
        if total_weight > 0:
            final_signal = sum(weighted_signals) / total_weight
        else:
            final_signal = 0.0

        # Convert to discrete signals
        threshold = 0.1
        long_signal = (
            max(0, min(8, int((final_signal + 1) * 4)))
            if final_signal > threshold
            else 0
        )
        short_signal = (
            max(0, min(8, int((-final_signal + 1) * 4)))
            if final_signal < -threshold
            else 0
        )

        # Calculate overall confidence
        avg_confidence = np.mean(
            [analysis.confidence for analysis in timeframe_results.values()]
        )

        return MultiTimeframeSignal(
            symbol=symbol,
            long_signal=long_signal,
            short_signal=short_signal,
            confidence=avg_confidence,
            dominant_timeframe=dominant_timeframe,
            signal_details=timeframe_results,
            timestamp=time.time(),
        )


# Global instance for easy access
_neural_processor = None


def get_neural_processor() -> NeuralProcessor:
    """Get the global neural processor instance."""
    global _neural_processor
    if _neural_processor is None:
        _neural_processor = NeuralProcessor()
    return _neural_processor


def enhanced_step_coin(symbol: str) -> Dict[str, Any]:
    """
    Enhanced step_coin function with multi-timeframe analysis.

    This replaces the old single-timeframe approach with Phase 3's
    multi-timeframe neural analysis.

    Args:
        symbol: Cryptocurrency symbol (e.g., 'BTC')

    Returns:
        Dictionary with enhanced signal data
    """
    processor = get_neural_processor()
    signal = processor.step_coin(symbol)

    return {
        "symbol": symbol,
        "long_signal": signal.long_signal,
        "short_signal": signal.short_signal,
        "confidence": signal.confidence,
        "dominant_timeframe": signal.dominant_timeframe,
        "timestamp": signal.timestamp,
        "analysis_details": {
            tf: {
                "patterns": analysis.patterns,
                "predictions": analysis.predictions,
                "support_levels": analysis.support_levels,
                "resistance_levels": analysis.resistance_levels,
                "signal_strength": analysis.signal_strength,
                "confidence": analysis.confidence,
            }
            for tf, analysis in signal.signal_details.items()
        },
    }


if __name__ == "__main__":
    # Test the enhanced neural processor
    print("PowerTrader AI+ Phase 3 - Enhanced Neural Processor")
    print("=" * 50)

    if not PYTORCH_AVAILABLE:
        print(
            "Warning: PyTorch not available. Install with: pip install torch torchvision"
        )

    processor = get_neural_processor()

    # Test with a sample symbol
    test_symbols = ["BTC", "ETH"]

    for symbol in test_symbols:
        print(f"\nTesting enhanced neural processing for {symbol}...")
        result = enhanced_step_coin(symbol)

        print(f"Symbol: {result['symbol']}")
        print(f"Long Signal: {result['long_signal']}")
        print(f"Short Signal: {result['short_signal']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Dominant Timeframe: {result['dominant_timeframe']}")
        print(
            f"Analysis Details: {len(result['analysis_details'])} timeframes analyzed"
        )
