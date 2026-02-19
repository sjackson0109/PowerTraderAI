"""
PowerTrader AI Testing Framework
Comprehensive testing utilities for trading strategies, API integrations, and system components.
"""

import unittest
import unittest.mock as mock
import pytest
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import tempfile
from pathlib import Path
import logging
import threading
import time
import random

from pt_errors import TradingError, APIError, ValidationError
from pt_utils import SafeFileHandler, ConfigurationValidator
from pt_performance import PerformanceMonitor
from pt_config import ConfigurationManager

@dataclass
class TestResult:
    """Test execution result with performance metrics."""
    test_name: str
    passed: bool
    duration_ms: float
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class MockMarketData:
    """Mock market data for testing."""
    symbol: str
    price: float
    volume: float
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None

class MarketDataGenerator:
    """Generates realistic mock market data for testing."""
    
    def __init__(self, base_price: float = 50000.0, volatility: float = 0.02):
        self.base_price = base_price
        self.current_price = base_price
        self.volatility = volatility
        self.trend = 0.0
        
    def next_price(self) -> float:
        """Generate next price using random walk with trend."""
        # Random price change
        change = random.gauss(0, self.volatility)
        
        # Add trend component
        change += self.trend * 0.1
        
        # Apply change
        self.current_price *= (1 + change)
        
        # Prevent negative prices
        self.current_price = max(self.current_price, 1.0)
        
        # Occasionally change trend
        if random.random() < 0.05:
            self.trend = random.gauss(0, 0.01)
        
        return self.current_price
    
    def generate_ohlcv(self, periods: int = 100) -> List[Dict[str, float]]:
        """Generate OHLCV data for multiple periods."""
        data = []
        
        for i in range(periods):
            open_price = self.current_price
            high = open_price
            low = open_price
            
            # Generate intra-period price movements
            for _ in range(random.randint(5, 20)):
                price = self.next_price()
                high = max(high, price)
                low = min(low, price)
            
            close = self.current_price
            volume = random.uniform(100, 10000)
            
            data.append({
                'timestamp': datetime.now() - timedelta(periods=(periods-i)),
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume
            })
        
        return data

class MockExchangeAPI:
    """Mock exchange API for testing trading operations."""
    
    def __init__(self, initial_balance: float = 10000.0):
        self.balance = initial_balance
        self.positions: Dict[str, float] = {}
        self.orders: List[Dict[str, Any]] = []
        self.trade_history: List[Dict[str, Any]] = []
        self.market_data = MarketDataGenerator()
        self.api_calls = 0
        self.error_rate = 0.0  # Percentage of calls that should fail
        
    def get_balance(self) -> float:
        """Get current account balance."""
        self._increment_api_calls()
        self._maybe_raise_error()
        return self.balance
    
    def get_position(self, symbol: str) -> float:
        """Get current position size for symbol."""
        self._increment_api_calls()
        self._maybe_raise_error()
        return self.positions.get(symbol, 0.0)
    
    def get_market_price(self, symbol: str) -> float:
        """Get current market price for symbol."""
        self._increment_api_calls()
        self._maybe_raise_error()
        return self.market_data.next_price()
    
    def place_order(self, symbol: str, side: str, quantity: float, 
                   price: Optional[float] = None) -> Dict[str, Any]:
        """Place a trading order."""
        self._increment_api_calls()
        self._maybe_raise_error()
        
        order_id = f"order_{len(self.orders) + 1:06d}"
        market_price = self.get_market_price(symbol)
        
        # Use market price if no price specified
        if price is None:
            price = market_price
        
        order = {
            'id': order_id,
            'symbol': symbol,
            'side': side.lower(),
            'quantity': quantity,
            'price': price,
            'status': 'filled',  # Assume immediate fill for testing
            'timestamp': datetime.now()
        }
        
        # Update positions and balance
        if side.lower() == 'buy':
            cost = quantity * price
            if cost <= self.balance:
                self.balance -= cost
                self.positions[symbol] = self.positions.get(symbol, 0) + quantity
            else:
                raise TradingError(f"Insufficient balance: {self.balance} < {cost}")
        
        elif side.lower() == 'sell':
            current_position = self.positions.get(symbol, 0)
            if quantity <= current_position:
                self.balance += quantity * price
                self.positions[symbol] = current_position - quantity
            else:
                raise TradingError(f"Insufficient position: {current_position} < {quantity}")
        
        self.orders.append(order)
        self.trade_history.append(order.copy())
        
        return order
    
    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get status of an order."""
        self._increment_api_calls()
        self._maybe_raise_error()
        
        for order in self.orders:
            if order['id'] == order_id:
                return order
        return None
    
    def get_trade_history(self, symbol: str = None, 
                         limit: int = 100) -> List[Dict[str, Any]]:
        """Get trade history."""
        self._increment_api_calls()
        self._maybe_raise_error()
        
        history = self.trade_history
        if symbol:
            history = [trade for trade in history if trade['symbol'] == symbol]
        
        return history[-limit:]
    
    def set_error_rate(self, rate: float) -> None:
        """Set the percentage of API calls that should fail."""
        self.error_rate = max(0.0, min(1.0, rate))
    
    def _increment_api_calls(self) -> None:
        """Track API call count."""
        self.api_calls += 1
    
    def _maybe_raise_error(self) -> None:
        """Randomly raise API errors based on error rate."""
        if random.random() < self.error_rate:
            raise APIError("Simulated API error for testing")
    
    def reset(self) -> None:
        """Reset exchange state for testing."""
        self.balance = 10000.0
        self.positions.clear()
        self.orders.clear()
        self.trade_history.clear()
        self.api_calls = 0
        self.market_data = MarketDataGenerator()

class TradingStrategyTester:
    """Framework for testing trading strategies with backtesting capabilities."""
    
    def __init__(self, initial_balance: float = 10000.0):
        self.initial_balance = initial_balance
        self.mock_exchange = MockExchangeAPI(initial_balance)
        self.performance_monitor = PerformanceMonitor()
        self.test_results: List[TestResult] = []
        
    def run_strategy_test(self, strategy_func: Callable, 
                         market_data: List[Dict[str, Any]],
                         test_name: str = "Strategy Test") -> TestResult:
        """
        Run a trading strategy against historical market data.
        
        Args:
            strategy_func: Function that implements trading strategy
            market_data: List of OHLCV data points
            test_name: Name for the test
            
        Returns:
            TestResult with performance metrics
        """
        start_time = time.time()
        
        try:
            # Reset exchange state
            self.mock_exchange.reset()
            
            # Run strategy against market data
            for data_point in market_data:
                # Update mock market data
                self.mock_exchange.market_data.current_price = data_point['close']
                
                # Execute strategy
                strategy_func(self.mock_exchange, data_point)
            
            # Calculate performance metrics
            final_balance = self.mock_exchange.get_balance()
            total_return = (final_balance - self.initial_balance) / self.initial_balance
            
            metrics = {
                'initial_balance': self.initial_balance,
                'final_balance': final_balance,
                'total_return': total_return,
                'total_trades': len(self.mock_exchange.trade_history),
                'api_calls': self.mock_exchange.api_calls
            }
            
            duration_ms = (time.time() - start_time) * 1000
            
            result = TestResult(
                test_name=test_name,
                passed=True,
                duration_ms=duration_ms,
                metrics=metrics
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            result = TestResult(
                test_name=test_name,
                passed=False,
                duration_ms=duration_ms,
                error_message=str(e)
            )
        
        self.test_results.append(result)
        return result
    
    def run_stress_test(self, strategy_func: Callable, 
                       test_duration_seconds: int = 60,
                       api_error_rate: float = 0.1) -> TestResult:
        """
        Run stress test with random market conditions and API errors.
        
        Args:
            strategy_func: Function that implements trading strategy
            test_duration_seconds: How long to run the stress test
            api_error_rate: Percentage of API calls that should fail
            
        Returns:
            TestResult with stress test metrics
        """
        start_time = time.time()
        test_name = f"Stress Test ({test_duration_seconds}s)"
        
        try:
            self.mock_exchange.reset()
            self.mock_exchange.set_error_rate(api_error_rate)
            
            error_count = 0
            iteration_count = 0
            
            while (time.time() - start_time) < test_duration_seconds:
                try:
                    # Generate random market data
                    market_price = self.mock_exchange.market_data.next_price()
                    data_point = {
                        'timestamp': datetime.now(),
                        'open': market_price * 0.999,
                        'high': market_price * 1.001,
                        'low': market_price * 0.998,
                        'close': market_price,
                        'volume': random.uniform(100, 1000)
                    }
                    
                    strategy_func(self.mock_exchange, data_point)
                    iteration_count += 1
                    
                except Exception:
                    error_count += 1
                
                # Small delay to prevent overwhelming CPU
                time.sleep(0.01)
            
            duration_ms = (time.time() - start_time) * 1000
            error_rate = error_count / max(iteration_count + error_count, 1)
            
            metrics = {
                'iterations': iteration_count,
                'errors': error_count,
                'error_rate': error_rate,
                'api_calls': self.mock_exchange.api_calls,
                'final_balance': self.mock_exchange.get_balance()
            }
            
            # Test passes if error rate is reasonable
            passed = error_rate < 0.5  # Less than 50% error rate
            
            result = TestResult(
                test_name=test_name,
                passed=passed,
                duration_ms=duration_ms,
                metrics=metrics,
                warnings=["High error rate"] if error_rate > 0.2 else []
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            result = TestResult(
                test_name=test_name,
                passed=False,
                duration_ms=duration_ms,
                error_message=str(e)
            )
        
        self.test_results.append(result)
        return result
    
    def generate_test_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report."""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r.passed)
        
        return {
            'summary': {
                'total_tests': total_tests,
                'passed': passed_tests,
                'failed': total_tests - passed_tests,
                'success_rate': passed_tests / max(total_tests, 1)
            },
            'performance': {
                'average_duration_ms': sum(r.duration_ms for r in self.test_results) / max(total_tests, 1),
                'fastest_test_ms': min((r.duration_ms for r in self.test_results), default=0),
                'slowest_test_ms': max((r.duration_ms for r in self.test_results), default=0)
            },
            'test_results': [
                {
                    'name': r.test_name,
                    'passed': r.passed,
                    'duration_ms': r.duration_ms,
                    'error': r.error_message,
                    'warnings': r.warnings,
                    'metrics': r.metrics
                }
                for r in self.test_results
            ]
        }

class ComponentTester:
    """Unit testing utilities for PowerTrader AI components."""
    
    @staticmethod
    def test_configuration_validation() -> TestResult:
        """Test configuration validation functionality."""
        start_time = time.time()
        
        try:
            # Test valid configuration
            validator = ConfigurationValidator()
            
            # Test symbol validation
            assert validator.validate_symbol("BTC-USD") == True
            assert validator.validate_symbol("invalid") == False
            assert validator.validate_symbol("") == False
            
            # Test timeframe validation
            assert validator.validate_timeframe("1h") == True
            assert validator.validate_timeframe("5m") == True
            assert validator.validate_timeframe("invalid") == False
            
            # Test amount validation
            assert validator.validate_amount(100.0) == True
            assert validator.validate_amount(-10.0) == False
            assert validator.validate_amount("invalid") == False
            
            duration_ms = (time.time() - start_time) * 1000
            
            return TestResult(
                test_name="Configuration Validation",
                passed=True,
                duration_ms=duration_ms,
                metrics={'validations_tested': 8}
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return TestResult(
                test_name="Configuration Validation",
                passed=False,
                duration_ms=duration_ms,
                error_message=str(e)
            )
    
    @staticmethod
    def test_file_operations() -> TestResult:
        """Test file operation utilities."""
        start_time = time.time()
        
        try:
            # Test file writing and reading
            test_content = "PowerTrader AI Test Content"
            
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                temp_path = f.name
                f.write(test_content)
            
            # Test reading
            result = SafeFileHandler.read_file(temp_path)
            assert result.success == True
            assert result.data == test_content
            
            # Test reading non-existent file
            result = SafeFileHandler.read_file("non_existent_file.txt")
            assert result.success == False
            assert result.error is not None
            
            # Cleanup
            Path(temp_path).unlink(missing_ok=True)
            
            duration_ms = (time.time() - start_time) * 1000
            
            return TestResult(
                test_name="File Operations",
                passed=True,
                duration_ms=duration_ms,
                metrics={'operations_tested': 3}
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return TestResult(
                test_name="File Operations",
                passed=False,
                duration_ms=duration_ms,
                error_message=str(e)
            )
    
    @staticmethod
    def test_performance_monitoring() -> TestResult:
        """Test performance monitoring functionality."""
        start_time = time.time()
        
        try:
            monitor = PerformanceMonitor(enable_system_metrics=False)
            
            # Test timer functionality
            monitor.start_timer("test_operation")
            time.sleep(0.1)  # Simulate work
            duration = monitor.end_timer("test_operation")
            
            assert duration is not None
            assert duration >= 100  # Should be at least 100ms
            
            # Test counter functionality
            monitor.increment_counter("test_counter", 5)
            assert monitor.get_counter("test_counter") == 5
            
            # Test metric addition
            monitor.add_metric_value("test_metric", 42.0, "units")
            summary = monitor.get_metric_summary("test_metric")
            assert summary is not None
            assert summary['latest'] == 42.0
            
            duration_ms = (time.time() - start_time) * 1000
            
            return TestResult(
                test_name="Performance Monitoring",
                passed=True,
                duration_ms=duration_ms,
                metrics={'features_tested': 3}
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return TestResult(
                test_name="Performance Monitoring",
                passed=False,
                duration_ms=duration_ms,
                error_message=str(e)
            )

def run_comprehensive_tests() -> Dict[str, Any]:
    """Run all component tests and return comprehensive report."""
    component_tester = ComponentTester()
    
    # Run individual component tests
    test_results = [
        component_tester.test_configuration_validation(),
        component_tester.test_file_operations(),
        component_tester.test_performance_monitoring()
    ]
    
    # Calculate summary
    total_tests = len(test_results)
    passed_tests = sum(1 for r in test_results if r.passed)
    
    return {
        'component_tests': {
            'total': total_tests,
            'passed': passed_tests,
            'failed': total_tests - passed_tests,
            'success_rate': passed_tests / total_tests
        },
        'results': [
            {
                'name': r.test_name,
                'passed': r.passed,
                'duration_ms': r.duration_ms,
                'error': r.error_message,
                'metrics': r.metrics
            }
            for r in test_results
        ]
    }

# Example trading strategy for testing
def simple_momentum_strategy(exchange: MockExchangeAPI, market_data: Dict[str, Any]) -> None:
    """
    Simple momentum trading strategy for testing.
    Buys when price increases, sells when price decreases.
    """
    symbol = "BTC-USD"
    current_price = market_data['close']
    
    # Get current position
    position = exchange.get_position(symbol)
    balance = exchange.get_balance()
    
    # Simple momentum logic
    if len(exchange.trade_history) > 0:
        last_price = exchange.trade_history[-1]['price']
        
        # Buy if price increased and we have cash
        if current_price > last_price * 1.01 and balance > 100:
            quantity = balance * 0.1 / current_price  # Use 10% of balance
            exchange.place_order(symbol, "buy", quantity)
        
        # Sell if price decreased and we have position
        elif current_price < last_price * 0.99 and position > 0:
            quantity = position * 0.5  # Sell 50% of position
            exchange.place_order(symbol, "sell", quantity)

# Global testing instance
strategy_tester = TradingStrategyTester()