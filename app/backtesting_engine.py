#!/usr/bin/env python3
"""
Backtesting Framework for PowerTrader
Comprehensive backtesting system with historical simulation, strategy testing, and performance analysis.
"""

import json
import logging
import sqlite3
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# Optional imports with graceful degradation
try:
    import matplotlib.pyplot as plt
    import seaborn as sns

    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False

try:
    import scipy.optimize as opt
    from scipy import stats

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


class PositionType(Enum):
    """Position types for backtesting."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class Trade:
    """Represents a completed trade in the backtest."""

    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    position_type: PositionType
    pnl: float
    pnl_percent: float
    holding_period: timedelta
    commission: float = 0.0


@dataclass
class Position:
    """Represents an open position during backtesting."""

    symbol: str
    entry_time: datetime
    entry_price: float
    quantity: float
    position_type: PositionType
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    commission: float = 0.0


@dataclass
class BacktestResults:
    """Complete backtesting results."""

    trades: List[Trade]
    equity_curve: pd.Series
    benchmark_curve: Optional[pd.Series]
    metrics: Dict[str, float]
    drawdowns: pd.Series
    positions: List[Position]
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float


class TradingStrategy:
    """Base class for trading strategies."""

    def __init__(self, name: str, parameters: Dict = None):
        """Initialize trading strategy."""
        self.name = name
        self.parameters = parameters or {}
        self.lookback = parameters.get("lookback", 20) if parameters else 20

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on price data.

        Args:
            data: DataFrame with OHLCV data

        Returns:
            Series with signals: 1 for buy, -1 for sell, 0 for hold
        """
        raise NotImplementedError("Strategy must implement generate_signals method")

    def calculate_position_size(
        self, data: pd.DataFrame, capital: float, price: float
    ) -> float:
        """Calculate position size for a trade."""
        # Default: use 10% of capital
        return (capital * 0.1) / price


class MovingAverageCrossStrategy(TradingStrategy):
    """Simple moving average crossover strategy."""

    def __init__(self, short_window: int = 20, long_window: int = 50):
        super().__init__(
            "MA Cross", {"short_window": short_window, "long_window": long_window}
        )
        self.short_window = short_window
        self.long_window = long_window

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Generate MA cross signals."""
        if "close" not in data.columns:
            raise ValueError("Data must contain 'close' column")

        short_ma = data["close"].rolling(window=self.short_window).mean()
        long_ma = data["close"].rolling(window=self.long_window).mean()

        signals = pd.Series(0, index=data.index)

        # Buy signal when short MA crosses above long MA
        signals[(short_ma > long_ma) & (short_ma.shift(1) <= long_ma.shift(1))] = 1

        # Sell signal when short MA crosses below long MA
        signals[(short_ma < long_ma) & (short_ma.shift(1) >= long_ma.shift(1))] = -1

        return signals


class RSIStrategy(TradingStrategy):
    """RSI-based mean reversion strategy."""

    def __init__(
        self, rsi_period: int = 14, oversold: float = 30, overbought: float = 70
    ):
        super().__init__(
            "RSI Strategy",
            {"rsi_period": rsi_period, "oversold": oversold, "overbought": overbought},
        )
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought

    def calculate_rsi(self, prices: pd.Series) -> pd.Series:
        """Calculate RSI indicator."""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(window=self.rsi_period).mean()
        avg_loss = loss.rolling(window=self.rsi_period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Generate RSI signals."""
        if "close" not in data.columns:
            raise ValueError("Data must contain 'close' column")

        rsi = self.calculate_rsi(data["close"])
        signals = pd.Series(0, index=data.index)

        # Buy when RSI crosses above oversold level
        signals[(rsi > self.oversold) & (rsi.shift(1) <= self.oversold)] = 1

        # Sell when RSI crosses below overbought level
        signals[(rsi < self.overbought) & (rsi.shift(1) >= self.overbought)] = -1

        return signals


class BacktestEngine:
    """
    Comprehensive backtesting engine for strategy evaluation.
    """

    def __init__(self, initial_capital: float = 100000, commission: float = 0.001):
        """Initialize backtesting engine."""
        self.initial_capital = initial_capital
        self.commission = commission
        self.logger = self._setup_logging()

        # Results storage
        self.trades = []
        self.equity_curve = []
        self.positions = {}
        self.capital = initial_capital

        # Performance tracking
        self.max_drawdown = 0.0
        self.peak_capital = initial_capital

    def _setup_logging(self) -> logging.Logger:
        """Setup logging for backtesting."""
        logger = logging.getLogger("BacktestEngine")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def run_backtest(
        self,
        data: pd.DataFrame,
        strategy: TradingStrategy,
        benchmark_data: Optional[pd.DataFrame] = None,
    ) -> BacktestResults:
        """
        Run comprehensive backtest of trading strategy.

        Args:
            data: Historical price data (OHLCV format)
            strategy: Trading strategy to test
            benchmark_data: Optional benchmark data for comparison

        Returns:
            BacktestResults object with complete analysis
        """
        # Reset state
        self.trades = []
        self.equity_curve = []
        self.positions = {}
        self.capital = self.initial_capital
        self.peak_capital = self.initial_capital

        # Validate data
        required_columns = ["open", "high", "low", "close"]
        if not all(col in data.columns for col in required_columns):
            raise ValueError(f"Data must contain columns: {required_columns}")

        # Generate signals
        signals = strategy.generate_signals(data)

        # Create equity curve storage
        equity_values = []
        timestamps = []

        # Run simulation
        for i, (timestamp, row) in enumerate(data.iterrows()):
            current_price = row["close"]
            signal = signals.iloc[i] if i < len(signals) else 0

            # Process signal
            if signal == 1:  # Buy signal
                self._open_position(timestamp, current_price, strategy, row)
            elif signal == -1:  # Sell signal
                self._close_positions(timestamp, current_price)

            # Update equity curve
            current_equity = self._calculate_current_equity(current_price)
            equity_values.append(current_equity)
            timestamps.append(timestamp)

            # Update drawdown tracking
            if current_equity > self.peak_capital:
                self.peak_capital = current_equity

            current_drawdown = (self.peak_capital - current_equity) / self.peak_capital
            self.max_drawdown = max(self.max_drawdown, current_drawdown)

        # Close any remaining positions
        final_price = data.iloc[-1]["close"]
        self._close_positions(data.index[-1], final_price)

        # Create results
        equity_curve = pd.Series(equity_values, index=timestamps)

        # Calculate benchmark if provided
        benchmark_curve = None
        if benchmark_data is not None:
            benchmark_curve = self._calculate_benchmark_returns(
                benchmark_data, data.index
            )

        # Calculate performance metrics
        metrics = self._calculate_performance_metrics(equity_curve, benchmark_curve)

        # Calculate drawdowns
        drawdowns = self._calculate_drawdowns(equity_curve)

        results = BacktestResults(
            trades=self.trades,
            equity_curve=equity_curve,
            benchmark_curve=benchmark_curve,
            metrics=metrics,
            drawdowns=drawdowns,
            positions=[],  # Only closed positions in trades
            start_date=data.index[0],
            end_date=data.index[-1],
            initial_capital=self.initial_capital,
            final_capital=equity_curve.iloc[-1],
        )

        self.logger.info(
            f"Backtest completed: {len(self.trades)} trades, "
            f"{metrics['total_return']:.2%} total return"
        )

        return results

    def _open_position(
        self,
        timestamp: datetime,
        price: float,
        strategy: TradingStrategy,
        row: pd.Series,
    ):
        """Open a new position."""
        if len(self.positions) > 0:  # Already have position
            return

        quantity = strategy.calculate_position_size(None, self.capital, price)
        commission_cost = quantity * price * self.commission

        if self.capital >= (quantity * price + commission_cost):
            position = Position(
                symbol="ASSET",
                entry_time=timestamp,
                entry_price=price,
                quantity=quantity,
                position_type=PositionType.LONG,
                commission=commission_cost,
            )

            self.positions["ASSET"] = position
            self.capital -= quantity * price + commission_cost

    def _close_positions(self, timestamp: datetime, price: float):
        """Close all open positions."""
        for symbol, position in list(self.positions.items()):
            exit_commission = position.quantity * price * self.commission
            proceeds = position.quantity * price - exit_commission

            # Calculate PnL
            total_cost = position.quantity * position.entry_price + position.commission
            pnl = proceeds - total_cost
            pnl_percent = pnl / total_cost

            # Create trade record
            trade = Trade(
                symbol=symbol,
                entry_time=position.entry_time,
                exit_time=timestamp,
                entry_price=position.entry_price,
                exit_price=price,
                quantity=position.quantity,
                position_type=position.position_type,
                pnl=pnl,
                pnl_percent=pnl_percent,
                holding_period=timestamp - position.entry_time,
                commission=position.commission + exit_commission,
            )

            self.trades.append(trade)
            self.capital += proceeds

            # Remove position
            del self.positions[symbol]

    def _calculate_current_equity(self, current_price: float) -> float:
        """Calculate current total equity."""
        total_equity = self.capital

        for position in self.positions.values():
            current_value = position.quantity * current_price
            total_equity += current_value

        return total_equity

    def _calculate_benchmark_returns(
        self, benchmark_data: pd.DataFrame, test_dates: pd.DatetimeIndex
    ) -> pd.Series:
        """Calculate benchmark returns aligned with test period."""
        # Align benchmark to test period
        aligned_benchmark = benchmark_data.reindex(test_dates, method="ffill")

        # Calculate cumulative returns from initial investment
        initial_price = aligned_benchmark["close"].iloc[0]
        benchmark_returns = (
            aligned_benchmark["close"] / initial_price
        ) * self.initial_capital

        return benchmark_returns

    def _calculate_performance_metrics(
        self, equity_curve: pd.Series, benchmark_curve: Optional[pd.Series] = None
    ) -> Dict[str, float]:
        """Calculate comprehensive performance metrics."""
        if len(equity_curve) < 2:
            return {}

        # Basic returns
        total_return = (
            equity_curve.iloc[-1] - equity_curve.iloc[0]
        ) / equity_curve.iloc[0]

        # Daily returns
        daily_returns = equity_curve.pct_change().dropna()

        # Risk metrics
        volatility = daily_returns.std() * np.sqrt(252)  # Annualized
        sharpe_ratio = (
            (daily_returns.mean() * 252) / (daily_returns.std() * np.sqrt(252))
            if volatility > 0
            else 0
        )

        # Drawdown metrics
        drawdowns = self._calculate_drawdowns(equity_curve)
        max_drawdown = drawdowns.min()

        # Trade metrics
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl <= 0]

        win_rate = len(winning_trades) / len(self.trades) if self.trades else 0
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0

        metrics = {
            "total_return": total_return,
            "annualized_return": (
                (1 + total_return) ** (252 / len(daily_returns)) - 1
                if len(daily_returns) > 0
                else 0
            ),
            "volatility": volatility,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": abs(max_drawdown),
            "calmar_ratio": (
                (total_return / abs(max_drawdown)) if max_drawdown != 0 else 0
            ),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "total_trades": len(self.trades),
            "avg_trade_duration": (
                np.mean([t.holding_period.days for t in self.trades])
                if self.trades
                else 0
            ),
            "best_trade": max([t.pnl for t in self.trades]) if self.trades else 0,
            "worst_trade": min([t.pnl for t in self.trades]) if self.trades else 0,
        }

        # Alpha and Beta vs benchmark
        if benchmark_curve is not None and len(benchmark_curve) == len(equity_curve):
            benchmark_returns = benchmark_curve.pct_change().dropna()
            strategy_returns = equity_curve.pct_change().dropna()

            if len(benchmark_returns) > 1 and len(strategy_returns) > 1:
                covariance = np.cov(strategy_returns, benchmark_returns)[0][1]
                benchmark_variance = np.var(benchmark_returns)

                beta = covariance / benchmark_variance if benchmark_variance > 0 else 0
                alpha = strategy_returns.mean() - beta * benchmark_returns.mean()

                metrics["alpha"] = alpha * 252  # Annualized
                metrics["beta"] = beta

        return metrics

    def _calculate_drawdowns(self, equity_curve: pd.Series) -> pd.Series:
        """Calculate drawdown series."""
        peak = equity_curve.expanding().max()
        drawdowns = (equity_curve - peak) / peak
        return drawdowns

    def monte_carlo_simulation(
        self,
        data: pd.DataFrame,
        strategy: TradingStrategy,
        num_simulations: int = 1000,
        confidence_level: float = 0.95,
    ) -> Dict:
        """
        Run Monte Carlo simulation with random data resampling.

        Args:
            data: Historical price data
            strategy: Trading strategy to test
            num_simulations: Number of simulation runs
            confidence_level: Confidence level for statistics

        Returns:
            Dictionary with simulation results
        """
        if not SCIPY_AVAILABLE:
            self.logger.warning("SciPy not available - running simplified Monte Carlo")

        self.logger.info(
            f"Running Monte Carlo simulation with {num_simulations} iterations..."
        )

        results = []

        for i in range(num_simulations):
            # Bootstrap resampling
            sample_data = data.sample(n=len(data), replace=True).sort_index()

            try:
                result = self.run_backtest(sample_data, strategy)
                results.append(
                    {
                        "total_return": result.metrics.get("total_return", 0),
                        "max_drawdown": result.metrics.get("max_drawdown", 0),
                        "sharpe_ratio": result.metrics.get("sharpe_ratio", 0),
                        "final_capital": result.final_capital,
                    }
                )
            except Exception as e:
                self.logger.debug(f"Simulation {i+1} failed: {e}")
                continue

        if not results:
            return {"error": "No successful simulations completed"}

        # Calculate statistics
        returns = [r["total_return"] for r in results]
        drawdowns = [r["max_drawdown"] for r in results]
        sharpe_ratios = [r["sharpe_ratio"] for r in results]
        final_capitals = [r["final_capital"] for r in results]

        # Confidence intervals
        alpha = 1 - confidence_level
        lower_percentile = (alpha / 2) * 100
        upper_percentile = (1 - alpha / 2) * 100

        stats_dict = {
            "num_simulations": len(results),
            "mean_return": np.mean(returns),
            "median_return": np.median(returns),
            "std_return": np.std(returns),
            "min_return": np.min(returns),
            "max_return": np.max(returns),
            "return_ci_lower": np.percentile(returns, lower_percentile),
            "return_ci_upper": np.percentile(returns, upper_percentile),
            "mean_max_drawdown": np.mean(drawdowns),
            "worst_drawdown": np.max(drawdowns),
            "drawdown_ci_upper": np.percentile(drawdowns, upper_percentile),
            "mean_sharpe": np.mean(sharpe_ratios),
            "median_sharpe": np.median(sharpe_ratios),
            "final_capital_mean": np.mean(final_capitals),
            "final_capital_ci_lower": np.percentile(final_capitals, lower_percentile),
            "final_capital_ci_upper": np.percentile(final_capitals, upper_percentile),
            "probability_positive": len([r for r in returns if r > 0]) / len(returns),
            "probability_beat_benchmark": 0.5,  # Would need benchmark comparison
            "confidence_level": confidence_level,
            "raw_results": results,
        }

        self.logger.info(
            f"Monte Carlo completed: {len(results)} successful simulations"
        )
        return stats_dict

    def parameter_optimization(
        self,
        data: pd.DataFrame,
        strategy_class: type,
        parameter_grid: Dict,
        optimization_metric: str = "sharpe_ratio",
    ) -> Dict:
        """
        Optimize strategy parameters using grid search.

        Args:
            data: Historical price data
            strategy_class: Strategy class to optimize
            parameter_grid: Grid of parameters to test
            optimization_metric: Metric to optimize

        Returns:
            Optimization results
        """
        self.logger.info("Starting parameter optimization...")

        best_score = -np.inf
        best_params = None
        all_results = []

        # Generate parameter combinations
        param_names = list(parameter_grid.keys())
        param_values = list(parameter_grid.values())

        from itertools import product

        for param_combo in product(*param_values):
            params = dict(zip(param_names, param_combo))

            try:
                strategy = strategy_class(**params)
                result = self.run_backtest(data, strategy)

                score = result.metrics.get(optimization_metric, -np.inf)

                all_results.append(
                    {"parameters": params, "score": score, "metrics": result.metrics}
                )

                if score > best_score:
                    best_score = score
                    best_params = params

            except Exception as e:
                self.logger.debug(f"Parameter combination {params} failed: {e}")
                continue

        return {
            "best_parameters": best_params,
            "best_score": best_score,
            "optimization_metric": optimization_metric,
            "all_results": sorted(all_results, key=lambda x: x["score"], reverse=True),
        }


# DEMO ONLY - SYNTHETIC DATA.
# The block below exercises the API on randomly generated prices. Its numbers say
# nothing about any strategy's performance. For real results use the honest
# backtester on cached Binance candles: ``python -m app.backtest`` (see
# app/backtest/cli.py): next-bar-open fills, fees + slippage, out-of-sample split.
if __name__ == "__main__":
    print("=" * 70)
    print("DEMO ONLY - SYNTHETIC DATA (random prices; results are meaningless)")
    print("=" * 70)

    # Create sample data for testing
    np.random.seed(42)

    dates = pd.date_range("2023-01-01", "2024-01-01", freq="D")
    n_days = len(dates)

    # Simulate realistic price data
    initial_price = 100
    returns = np.random.normal(0.0005, 0.02, n_days)  # Daily returns
    prices = [initial_price]

    for ret in returns[1:]:
        new_price = prices[-1] * (1 + ret)
        prices.append(new_price)

    # Create OHLCV data
    data = pd.DataFrame(
        {
            "open": [p * (1 + np.random.uniform(-0.01, 0.01)) for p in prices],
            "high": [p * (1 + abs(np.random.uniform(0, 0.02))) for p in prices],
            "low": [p * (1 - abs(np.random.uniform(0, 0.02))) for p in prices],
            "close": prices,
            "volume": np.random.randint(1000, 10000, n_days),
        },
        index=dates,
    )

    # Initialize backtesting engine
    engine = BacktestEngine(initial_capital=100000, commission=0.001)

    # Test MA Cross strategy
    ma_strategy = MovingAverageCrossStrategy(short_window=20, long_window=50)

    print("Running MA Cross Strategy Backtest...")
    results = engine.run_backtest(data, ma_strategy)

    print(f"\nBacktest Results:")
    print(f"Total Return: {results.metrics['total_return']:.2%}")
    print(f"Sharpe Ratio: {results.metrics['sharpe_ratio']:.3f}")
    print(f"Max Drawdown: {results.metrics['max_drawdown']:.2%}")
    print(f"Win Rate: {results.metrics['win_rate']:.2%}")
    print(f"Total Trades: {results.metrics['total_trades']}")

    # Test parameter optimization
    print("\nRunning Parameter Optimization...")
    param_grid = {"short_window": [10, 20, 30], "long_window": [40, 50, 60]}

    opt_results = engine.parameter_optimization(
        data, MovingAverageCrossStrategy, param_grid
    )
    print(f"Best Parameters: {opt_results['best_parameters']}")
    print(f"Best Score (Sharpe): {opt_results['best_score']:.3f}")

    # Test Monte Carlo
    print("\nRunning Monte Carlo Simulation...")
    mc_results = engine.monte_carlo_simulation(data, ma_strategy, num_simulations=100)
    print(f"Mean Return: {mc_results['mean_return']:.2%}")
    print(f"Return Std: {mc_results['std_return']:.2%}")
    print(f"Probability Positive: {mc_results['probability_positive']:.2%}")

    print("\nBacktesting framework ready!")
