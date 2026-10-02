"""
PowerTrader AI+ Model Evaluation and Performance Analysis
Advanced evaluation metrics and visualization for trading models
"""

import json
import os
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

warnings.filterwarnings("ignore")

try:
    from sklearn.metrics import (
        confusion_matrix,
        classification_report,
        mean_squared_error,
        mean_absolute_error,
        r2_score,
        explained_variance_score,
    )

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


class ModelEvaluator:
    """
    Comprehensive model evaluation and performance analysis
    """

    def __init__(self, save_dir: str = None):
        if save_dir is None:
            import pt_paths

            save_dir = os.path.join(pt_paths.data_dir(), "model_evaluations")
        self.save_dir = save_dir
        os.makedirs(save_dir, exist_ok=True)

    def evaluate_regression_model(
        self, y_true: np.ndarray, y_pred: np.ndarray, model_name: str = "model"
    ) -> Dict:
        """
        Comprehensive regression model evaluation
        """
        if not SKLEARN_AVAILABLE:
            print("Warning: sklearn not available for full evaluation")
            return {}

        # Basic metrics
        mse = mean_squared_error(y_true, y_pred)
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mse)
        r2 = r2_score(y_true, y_pred)
        explained_var = explained_variance_score(y_true, y_pred)

        # Trading-specific metrics
        directional_accuracy = self._calculate_directional_accuracy(y_true, y_pred)
        profit_correlation = self._calculate_profit_correlation(y_true, y_pred)

        # Statistical metrics
        residuals = y_true - y_pred
        residual_mean = np.mean(residuals)
        residual_std = np.std(residuals)

        # Maximum error
        max_error = np.max(np.abs(residuals))

        results = {
            "model_name": model_name,
            "timestamp": datetime.now().isoformat(),
            "regression_metrics": {
                "mse": float(mse),
                "mae": float(mae),
                "rmse": float(rmse),
                "r2_score": float(r2),
                "explained_variance": float(explained_var),
                "max_error": float(max_error),
            },
            "trading_metrics": {
                "directional_accuracy": float(directional_accuracy),
                "profit_correlation": float(profit_correlation),
            },
            "residual_analysis": {
                "mean": float(residual_mean),
                "std": float(residual_std),
                "min": float(np.min(residuals)),
                "max": float(np.max(residuals)),
            },
        }

        self._print_evaluation_results(results)
        return results

    def _calculate_directional_accuracy(
        self, y_true: np.ndarray, y_pred: np.ndarray
    ) -> float:
        """Calculate directional prediction accuracy"""
        if len(y_true) < 2:
            return 0.0

        true_direction = np.diff(y_true) > 0
        pred_direction = np.diff(y_pred) > 0

        return np.mean(true_direction == pred_direction)

    def _calculate_profit_correlation(
        self, y_true: np.ndarray, y_pred: np.ndarray
    ) -> float:
        """Calculate correlation between predicted and actual price movements"""
        if len(y_true) < 2:
            return 0.0

        true_returns = np.diff(y_true) / y_true[:-1]
        pred_returns = np.diff(y_pred) / y_pred[:-1]

        # Handle any NaN or infinite values
        mask = np.isfinite(true_returns) & np.isfinite(pred_returns)
        if np.sum(mask) < 2:
            return 0.0

        correlation = np.corrcoef(true_returns[mask], pred_returns[mask])[0, 1]
        return correlation if not np.isnan(correlation) else 0.0

    def _print_evaluation_results(self, results: Dict):
        """Print formatted evaluation results"""
        print(f"\n{results['model_name'].upper()} EVALUATION RESULTS")
        print("=" * 50)

        reg_metrics = results["regression_metrics"]
        print("Regression Metrics:")
        print(f"  MSE: {reg_metrics['mse']:.6f}")
        print(f"  MAE: {reg_metrics['mae']:.6f}")
        print(f"  RMSE: {reg_metrics['rmse']:.6f}")
        print(f"  R² Score: {reg_metrics['r2_score']:.4f}")
        print(f"  Explained Variance: {reg_metrics['explained_variance']:.4f}")
        print(f"  Max Error: {reg_metrics['max_error']:.6f}")

        trading_metrics = results["trading_metrics"]
        print("\nTrading-Specific Metrics:")
        print(f"  Directional Accuracy: {trading_metrics['directional_accuracy']:.4f}")
        print(f"  Profit Correlation: {trading_metrics['profit_correlation']:.4f}")

        residual = results["residual_analysis"]
        print("\nResidual Analysis:")
        print(f"  Mean: {residual['mean']:.6f}")
        print(f"  Std: {residual['std']:.6f}")
        print(f"  Range: [{residual['min']:.6f}, {residual['max']:.6f}]")

    def create_evaluation_plots(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        model_name: str = "model",
        save: bool = True,
    ):
        """
        Create comprehensive evaluation plots
        """
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))

        # 1. Actual vs Predicted scatter plot
        axes[0, 0].scatter(y_true, y_pred, alpha=0.6, s=20)
        axes[0, 0].plot(
            [y_true.min(), y_true.max()],
            [y_true.min(), y_true.max()],
            "r--",
            lw=2,
            label="Perfect Prediction",
        )
        axes[0, 0].set_xlabel("Actual Values")
        axes[0, 0].set_ylabel("Predicted Values")
        axes[0, 0].set_title("Actual vs Predicted")
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)

        # 2. Residuals plot
        residuals = y_true - y_pred
        axes[0, 1].scatter(y_pred, residuals, alpha=0.6, s=20)
        axes[0, 1].axhline(y=0, color="r", linestyle="--")
        axes[0, 1].set_xlabel("Predicted Values")
        axes[0, 1].set_ylabel("Residuals")
        axes[0, 1].set_title("Residual Plot")
        axes[0, 1].grid(True, alpha=0.3)

        # 3. Time series comparison
        time_index = range(len(y_true))
        axes[1, 0].plot(time_index, y_true, label="Actual", alpha=0.8)
        axes[1, 0].plot(time_index, y_pred, label="Predicted", alpha=0.8)
        axes[1, 0].set_xlabel("Time Steps")
        axes[1, 0].set_ylabel("Values")
        axes[1, 0].set_title("Time Series Comparison")
        axes[1, 0].legend()
        axes[1, 0].grid(True, alpha=0.3)

        # 4. Residuals histogram
        axes[1, 1].hist(residuals, bins=30, alpha=0.7, density=True, edgecolor="black")
        axes[1, 1].axvline(x=0, color="r", linestyle="--")
        axes[1, 1].set_xlabel("Residuals")
        axes[1, 1].set_ylabel("Density")
        axes[1, 1].set_title("Residuals Distribution")
        axes[1, 1].grid(True, alpha=0.3)

        plt.tight_layout()

        if save:
            plot_path = os.path.join(
                self.save_dir, f"{model_name}_evaluation_plots.png"
            )
            plt.savefig(plot_path, dpi=300, bbox_inches="tight")
            print(f"Evaluation plots saved to: {plot_path}")

        return fig

    def backtest_strategy(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        initial_capital: float = 10000.0,
        transaction_cost: float = 0.001,
    ) -> Dict:
        """
        Simple backtesting based on prediction signals
        """
        if len(y_true) < 2:
            return {"error": "Insufficient data for backtesting"}

        # Calculate returns
        true_returns = np.diff(y_true) / y_true[:-1]
        predicted_direction = np.diff(y_pred) > 0

        # Generate trading signals (1 for buy, -1 for sell, 0 for hold)
        signals = np.where(predicted_direction, 1, -1)

        # Calculate strategy returns
        strategy_returns = signals * true_returns - transaction_cost * np.abs(
            np.diff(signals, prepend=0)
        )

        # Calculate cumulative returns
        cumulative_returns = np.cumprod(1 + strategy_returns)
        final_value = initial_capital * cumulative_returns[-1]

        # Calculate performance metrics
        total_return = (final_value - initial_capital) / initial_capital
        volatility = np.std(strategy_returns) * np.sqrt(252)  # Annualized

        # Sharpe ratio (assuming risk-free rate of 0)
        sharpe_ratio = (
            np.mean(strategy_returns) / np.std(strategy_returns) * np.sqrt(252)
            if np.std(strategy_returns) > 0
            else 0
        )

        # Maximum drawdown
        peak = np.maximum.accumulate(cumulative_returns)
        drawdown = (cumulative_returns - peak) / peak
        max_drawdown = np.min(drawdown)

        # Win rate
        win_rate = np.mean(strategy_returns > 0)

        results = {
            "initial_capital": initial_capital,
            "final_value": float(final_value),
            "total_return": float(total_return),
            "volatility": float(volatility),
            "sharpe_ratio": float(sharpe_ratio),
            "max_drawdown": float(max_drawdown),
            "win_rate": float(win_rate),
            "num_trades": len(signals),
            "strategy_returns": strategy_returns.tolist(),
            "cumulative_returns": cumulative_returns.tolist(),
        }

        print(f"\nBACKTEST RESULTS")
        print("=" * 30)
        print(f"Initial Capital: ${initial_capital:,.2f}")
        print(f"Final Value: ${final_value:,.2f}")
        print(f"Total Return: {total_return:.2%}")
        print(f"Volatility (Annual): {volatility:.2%}")
        print(f"Sharpe Ratio: {sharpe_ratio:.3f}")
        print(f"Max Drawdown: {max_drawdown:.2%}")
        print(f"Win Rate: {win_rate:.2%}")
        print(f"Number of Trades: {len(signals)}")

        return results

    def save_evaluation(self, evaluation_results: Dict, filename: Optional[str] = None):
        """Save evaluation results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"evaluation_{timestamp}.json"

        filepath = os.path.join(self.save_dir, filename)

        with open(filepath, "w") as f:
            json.dump(evaluation_results, f, indent=2, default=str)

        print(f"Evaluation results saved to: {filepath}")
        return filepath

    def load_evaluation(self, filepath: str) -> Dict:
        """Load evaluation results from JSON file"""
        with open(filepath, "r") as f:
            results = json.load(f)

        print(f"Evaluation results loaded from: {filepath}")
        return results

    def compare_models(self, evaluations: List[Dict]) -> pd.DataFrame:
        """
        Compare multiple model evaluations

        Args:
            evaluations: List of evaluation result dictionaries

        Returns:
            DataFrame with comparison metrics
        """
        comparison_data = []

        for eval_result in evaluations:
            reg_metrics = eval_result.get("regression_metrics", {})
            trading_metrics = eval_result.get("trading_metrics", {})

            comparison_data.append(
                {
                    "Model": eval_result.get("model_name", "Unknown"),
                    "R² Score": reg_metrics.get("r2_score", 0),
                    "RMSE": reg_metrics.get("rmse", 0),
                    "MAE": reg_metrics.get("mae", 0),
                    "Directional Accuracy": trading_metrics.get(
                        "directional_accuracy", 0
                    ),
                    "Profit Correlation": trading_metrics.get("profit_correlation", 0),
                }
            )

        df = pd.DataFrame(comparison_data)

        print("\nMODEL COMPARISON")
        print("=" * 50)
        print(df.to_string(index=False, float_format="{:.4f}".format))

        return df


class TradingBacktest:
    """
    Advanced backtesting framework for trading strategies
    """

    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.reset()

    def reset(self):
        """Reset backtest to initial state"""
        self.capital = self.initial_capital
        self.positions = {}
        self.trades = []
        self.portfolio_values = [self.initial_capital]
        self.timestamps = []

    def add_trade(
        self,
        timestamp: str,
        symbol: str,
        action: str,
        quantity: float,
        price: float,
        fees: float = 0.0,
    ):
        """Add a trade to the backtest"""
        trade_value = quantity * price

        if action.lower() == "buy":
            if self.capital >= trade_value + fees:
                self.capital -= trade_value + fees
                self.positions[symbol] = self.positions.get(symbol, 0) + quantity
            else:
                return False  # Insufficient capital
        elif action.lower() == "sell":
            if self.positions.get(symbol, 0) >= quantity:
                self.capital += trade_value - fees
                self.positions[symbol] -= quantity
            else:
                return False  # Insufficient position

        self.trades.append(
            {
                "timestamp": timestamp,
                "symbol": symbol,
                "action": action,
                "quantity": quantity,
                "price": price,
                "fees": fees,
                "trade_value": trade_value,
            }
        )

        return True

    def update_portfolio_value(self, timestamp: str, prices: Dict[str, float]):
        """Update portfolio value based on current prices"""
        total_value = self.capital

        for symbol, quantity in self.positions.items():
            if quantity > 0 and symbol in prices:
                total_value += quantity * prices[symbol]

        self.portfolio_values.append(total_value)
        self.timestamps.append(timestamp)

    def get_performance_metrics(self) -> Dict:
        """Calculate comprehensive performance metrics"""
        if len(self.portfolio_values) < 2:
            return {}

        returns = np.diff(self.portfolio_values) / self.portfolio_values[:-1]

        total_return = (
            self.portfolio_values[-1] - self.initial_capital
        ) / self.initial_capital
        volatility = np.std(returns) * np.sqrt(252) if len(returns) > 1 else 0
        sharpe_ratio = (
            np.mean(returns) / np.std(returns) * np.sqrt(252)
            if np.std(returns) > 0
            else 0
        )

        # Maximum drawdown
        peak = np.maximum.accumulate(self.portfolio_values)
        drawdown = (np.array(self.portfolio_values) - peak) / peak
        max_drawdown = np.min(drawdown)

        return {
            "total_return": float(total_return),
            "volatility": float(volatility),
            "sharpe_ratio": float(sharpe_ratio),
            "max_drawdown": float(max_drawdown),
            "final_value": float(self.portfolio_values[-1]),
            "num_trades": len(self.trades),
        }


if __name__ == "__main__":
    # Example usage
    evaluator = ModelEvaluator()

    # Generate sample data for demonstration
    np.random.seed(42)
    y_true = np.cumsum(np.random.randn(100) * 0.1) + 100
    y_pred = y_true + np.random.randn(100) * 0.5

    # Evaluate model
    results = evaluator.evaluate_regression_model(y_true, y_pred, "Example Model")

    # Create plots
    evaluator.create_evaluation_plots(y_true, y_pred, "Example Model")

    # Run backtest
    backtest_results = evaluator.backtest_strategy(y_true, y_pred)

    # Save results
    evaluator.save_evaluation(results)
