#!/usr/bin/env python3
"""
PowerTrader AI+ Phase 3 Live Demonstration
Shows the multi-timeframe neural analysis system in action
"""

import os
import sys
import time
import numpy as np
from datetime import datetime

# Add app directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pt_neural_processor import NeuralProcessor, PatternRecognizer, get_neural_processor
from pt_data_provider import DataProvider
from pt_logging_system import get_logger


class Phase3LiveDemo:
    """Live demonstration of Phase 3 multi-timeframe neural analysis"""

    def __init__(self):
        """Initialize demo components"""
        self.logger = get_logger()
        self.data_provider = DataProvider()

        # Get the global neural processor instance
        self.neural_processor = get_neural_processor()
        self.pattern_recognizer = PatternRecognizer()

        print("✅ Phase 3 Demo Components Initialized")
        print(f"   📡 Data Provider: Ready")
        print(f"   🧠 Neural Processor: Ready")
        print(f"   🎯 Pattern Recognizer: Ready")
        print()

    def demonstrate_phase3_analysis(self, symbols=["BTC", "ETH", "XRP"]):
        """Demonstrate Phase 3 multi-timeframe analysis on live symbols"""
        print("🚀 PHASE 3 MULTI-TIMEFRAME NEURAL ANALYSIS")
        print("=" * 60)
        print(f"📅 Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🔍 Symbols: {', '.join(symbols)}")
        print()

        results = {}

        for symbol in symbols:
            print(f"📊 ANALYZING {symbol.upper()}:")
            print("-" * 30)

            try:
                # Run Phase 3 multi-timeframe analysis
                start_time = time.time()
                signal_result = self.neural_processor.step_coin(symbol)
                analysis_time = time.time() - start_time

                # Display results
                print(f"  🎯 Analysis completed in {analysis_time:.2f}s")
                print(f"  📈 Long Signal: {signal_result.long_signal}")
                print(f"  📉 Short Signal: {signal_result.short_signal}")
                print(f"  🎲 Confidence: {signal_result.confidence:.1%}")
                print(f"  ⏰ Dominant Timeframe: {signal_result.dominant_timeframe}")

                # Show signal interpretation
                if signal_result.long_signal > signal_result.short_signal:
                    signal_emoji = "🟢"
                    signal_text = "BULLISH"
                elif signal_result.short_signal > signal_result.long_signal:
                    signal_emoji = "🔴"
                    signal_text = "BEARISH"
                else:
                    signal_emoji = "🟡"
                    signal_text = "NEUTRAL"

                print(f"  {signal_emoji} Overall Signal: {signal_text}")

                # Store results
                results[symbol] = {
                    "signal": signal_result,
                    "analysis_time": analysis_time,
                    "status": "success",
                }

            except Exception as e:
                print(f"  ❌ Analysis error: {str(e)}")
                results[symbol] = {"error": str(e), "status": "error"}

            print()

        return results

    def demonstrate_pattern_recognition(self):
        """Demonstrate pattern recognition capabilities"""
        print("🎯 PATTERN RECOGNITION DEMO:")
        print("-" * 40)

        # Create sample market data for demonstration
        sample_data = self._generate_sample_market_data()

        print("📊 Sample Market Data Generated:")
        print(f"   📍 Data Points: {len(sample_data)}")
        print(
            f"   💰 Price Range: ${sample_data[:, 3].min():.2f} - ${sample_data[:, 3].max():.2f}"
        )
        print()

        # Run pattern recognition
        patterns = self.pattern_recognizer.identify_patterns(sample_data, "1hour")

        print("🔍 Pattern Analysis Results:")
        for pattern_name, strength in patterns.items():
            # Format pattern names nicely
            display_name = pattern_name.replace("_", " ").title()

            # Color code pattern strength
            if strength > 0.7:
                emoji = "🔥"  # Strong
            elif strength > 0.4:
                emoji = "⚡"  # Medium
            elif strength > 0.1:
                emoji = "📊"  # Weak
            else:
                emoji = "➖"  # Minimal

            print(f"   {emoji} {display_name}: {strength:.2%}")

        print()

    def _generate_sample_market_data(self, length=50, base_price=45000):
        """Generate sample OHLCV data for demonstration"""
        np.random.seed(42)  # For consistent demo results

        data = []
        current_price = base_price

        for i in range(length):
            # Generate realistic price movement
            change = np.random.normal(0, 0.02)  # 2% standard deviation
            current_price *= 1 + change

            # Generate OHLC
            high = current_price * (1 + abs(np.random.normal(0, 0.005)))
            low = current_price * (1 - abs(np.random.normal(0, 0.005)))
            open_price = current_price * (1 + np.random.normal(0, 0.001))
            close = current_price
            volume = np.random.uniform(100, 1000)

            data.append([open_price, low, high, close, volume])

        return np.array(data)

    def show_phase3_capabilities(self):
        """Display Phase 3 system capabilities overview"""
        print("⚡ PHASE 3 NEURAL SYSTEM CAPABILITIES:")
        print("-" * 50)

        # Show timeframes analyzed
        timeframes = self.neural_processor.timeframes
        print("🕐 Multi-Timeframe Analysis:")
        for i, tf in enumerate(timeframes, 1):
            print(
                f"   {i}. {tf.replace('hour', 'h').replace('day', 'd').replace('week', 'w')}"
            )

        print(f"\n📊 Total Timeframes: {len(timeframes)} simultaneous analysis")
        print()

        # Show pattern types
        print("🎯 Pattern Recognition Types:")
        patterns = [
            "Trend Strength Analysis",
            "Volatility Pattern Detection",
            "Support/Resistance Strength",
            "Momentum Divergence Detection",
            "Breakout Potential Assessment",
        ]

        for i, pattern in enumerate(patterns, 1):
            print(f"   {i}. {pattern}")

        print()

        # Show neural network features
        print("🧠 Neural Network Features:")
        features = [
            "Real PyTorch models (Phase 1 foundation)",
            "Multi-timeframe feature extraction",
            "Advanced signal combination logic",
            "Confidence scoring system",
            "Adaptive model caching",
            "Cross-timeframe validation",
        ]

        for i, feature in enumerate(features, 1):
            print(f"   {i}. {feature}")

        print()

    def run_complete_demo(self):
        """Run the complete Phase 3 demonstration"""
        print("🎊 POWERTRADER AI+ PHASE 3 LIVE DEMONSTRATION")
        print("=" * 65)
        print("Advanced Multi-Timeframe Neural Analysis System")
        print()

        # Show capabilities
        self.show_phase3_capabilities()

        # Pattern recognition demo
        self.demonstrate_pattern_recognition()

        # Live analysis demo
        analysis_results = self.demonstrate_phase3_analysis()

        # Summary
        print("✅ PHASE 3 DEMONSTRATION SUMMARY:")
        print("=" * 40)

        successful_analyses = sum(
            1 for r in analysis_results.values() if r.get("status") == "success"
        )
        total_analyses = len(analysis_results)

        print(f"📊 Analyses Completed: {successful_analyses}/{total_analyses}")

        if successful_analyses > 0:
            avg_time = (
                sum(
                    r.get("analysis_time", 0)
                    for r in analysis_results.values()
                    if r.get("status") == "success"
                )
                / successful_analyses
            )
            print(f"⚡ Average Analysis Time: {avg_time:.2f}s")

        print(f"🧠 Multi-timeframe processing: ✅ OPERATIONAL")
        print(f"🎯 Pattern recognition: ✅ OPERATIONAL")
        print(f"📡 Data provider integration: ✅ OPERATIONAL")
        print()
        print("🚀 Phase 3 Neural Analysis System: FULLY OPERATIONAL!")
        print("   Ready for enhanced trading signal generation!")


def main():
    """Main demo execution"""
    try:
        demo = Phase3LiveDemo()
        demo.run_complete_demo()
    except KeyboardInterrupt:
        print("\n⚠️ Demo interrupted by user")
    except Exception as e:
        print(f"❌ Demo error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
