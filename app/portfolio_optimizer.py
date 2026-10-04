#!/usr/bin/env python3
"""
Portfolio Optimization Engine for PowerTrader
Advanced portfolio optimization with Modern Portfolio Theory, efficient frontier, and risk management.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

# Optional imports with graceful degradation
try:
    import scipy.optimize
    from scipy.optimize import minimize

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    import seaborn as sns

    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False


class PortfolioOptimizer:
    """
    Advanced portfolio optimization engine implementing Modern Portfolio Theory,
    efficient frontier calculation, and sophisticated rebalancing strategies.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the portfolio optimizer with database storage."""
        if db_path is None:
            import pt_paths

            db_path = pt_paths.data_file("portfolio_optimization.db")
        self.db_path = db_path
        self.logger = self._setup_logging()
        self._init_database()

        # Risk-free rate (can be updated based on current treasury rates)
        self.risk_free_rate = 0.02  # 2% annual

        # Optimization constraints
        self.default_constraints = {
            "max_weight": 0.4,  # Maximum 40% in any single asset
            "min_weight": 0.01,  # Minimum 1% in any asset
            "max_volatility": 0.25,  # Maximum 25% portfolio volatility
            "max_correlation": 0.8,  # Maximum correlation between assets
        }

    def _setup_logging(self) -> logging.Logger:
        """Setup logging for portfolio optimization."""
        logger = logging.getLogger("PortfolioOptimizer")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def _init_database(self):
        """Initialize database tables for portfolio optimization."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS optimized_portfolios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_name TEXT UNIQUE,
                    optimization_type TEXT,
                    target_return REAL,
                    target_risk REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    constraints_json TEXT,
                    results_json TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS asset_allocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id INTEGER,
                    symbol TEXT,
                    weight REAL,
                    expected_return REAL,
                    volatility REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (portfolio_id) REFERENCES optimized_portfolios (id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS rebalancing_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id INTEGER,
                    rebalance_date TIMESTAMP,
                    old_weights_json TEXT,
                    new_weights_json TEXT,
                    rebalance_reason TEXT,
                    transaction_costs REAL,
                    FOREIGN KEY (portfolio_id) REFERENCES optimized_portfolios (id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS efficient_frontier_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id INTEGER,
                    expected_return REAL,
                    volatility REAL,
                    sharpe_ratio REAL,
                    weights_json TEXT,
                    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (portfolio_id) REFERENCES optimized_portfolios (id)
                )
            """)

    def calculate_returns_covariance(
        self, price_data: pd.DataFrame, period: int = 252
    ) -> Tuple[pd.Series, pd.DataFrame]:
        """
        Calculate expected returns and covariance matrix from price data.

        Args:
            price_data: DataFrame with asset prices (columns = assets, index = dates)
            period: Number of periods for annualization (252 for daily data)

        Returns:
            Tuple of (expected_returns, covariance_matrix)
        """
        # Calculate returns
        returns = price_data.pct_change().dropna()

        # Expected returns (annualized)
        expected_returns = returns.mean() * period

        # Covariance matrix (annualized)
        covariance_matrix = returns.cov() * period

        return expected_returns, covariance_matrix

    def portfolio_performance(
        self, weights: np.ndarray, expected_returns: pd.Series, cov_matrix: pd.DataFrame
    ) -> Tuple[float, float, float]:
        """
        Calculate portfolio performance metrics.

        Args:
            weights: Asset weights array
            expected_returns: Expected returns for each asset
            cov_matrix: Covariance matrix

        Returns:
            Tuple of (portfolio_return, portfolio_volatility, sharpe_ratio)
        """
        # Portfolio return
        portfolio_return = np.dot(weights, expected_returns)

        # Portfolio volatility
        portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))

        # Sharpe ratio
        sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_volatility

        return portfolio_return, portfolio_volatility, sharpe_ratio

    def optimize_portfolio(
        self,
        expected_returns: pd.Series,
        cov_matrix: pd.DataFrame,
        optimization_type: str = "max_sharpe",
        target_return: Optional[float] = None,
        constraints: Optional[Dict] = None,
    ) -> Dict:
        """
        Optimize portfolio weights based on specified objective.

        Args:
            expected_returns: Expected returns for each asset
            cov_matrix: Covariance matrix
            optimization_type: 'max_sharpe', 'min_variance', 'target_return'
            target_return: Required for 'target_return' optimization
            constraints: Custom constraints dictionary

        Returns:
            Dictionary with optimization results
        """
        if not SCIPY_AVAILABLE:
            self.logger.warning("SciPy not available - using equal weight allocation")
            n_assets = len(expected_returns)
            weights = np.array([1.0 / n_assets] * n_assets)
            port_return, port_vol, sharpe = self.portfolio_performance(
                weights, expected_returns, cov_matrix
            )
            return {
                "weights": dict(zip(expected_returns.index, weights)),
                "expected_return": port_return,
                "volatility": port_vol,
                "sharpe_ratio": sharpe,
                "success": True,
                "method": "equal_weight_fallback",
            }

        # Merge constraints
        active_constraints = {**self.default_constraints}
        if constraints:
            active_constraints.update(constraints)

        n_assets = len(expected_returns)

        # Bounds for weights (min_weight, max_weight)
        bounds = tuple(
            (active_constraints["min_weight"], active_constraints["max_weight"])
            for _ in range(n_assets)
        )

        # Constraint: weights sum to 1
        constraints_list = [{"type": "eq", "fun": lambda x: np.sum(x) - 1.0}]

        # Volatility constraint
        if "max_volatility" in active_constraints:
            constraints_list.append(
                {
                    "type": "ineq",
                    "fun": lambda x: active_constraints["max_volatility"]
                    - np.sqrt(np.dot(x.T, np.dot(cov_matrix, x))),
                }
            )

        # Define objective function
        if optimization_type == "max_sharpe":
            # Maximize Sharpe ratio (minimize negative Sharpe ratio)
            def objective(weights):
                _, _, sharpe = self.portfolio_performance(
                    weights, expected_returns, cov_matrix
                )
                return -sharpe

        elif optimization_type == "min_variance":
            # Minimize portfolio variance
            def objective(weights):
                return np.dot(weights.T, np.dot(cov_matrix, weights))

        elif optimization_type == "target_return":
            if target_return is None:
                raise ValueError(
                    "target_return must be specified for target_return optimization"
                )

            # Minimize variance subject to target return
            constraints_list.append(
                {
                    "type": "eq",
                    "fun": lambda x: np.dot(x, expected_returns) - target_return,
                }
            )

            def objective(weights):
                return np.dot(weights.T, np.dot(cov_matrix, weights))

        else:
            raise ValueError(f"Unknown optimization type: {optimization_type}")

        # Initial guess (equal weights)
        x0 = np.array([1.0 / n_assets] * n_assets)

        try:
            # Perform optimization
            result = minimize(
                objective,
                x0,
                method="SLSQP",
                bounds=bounds,
                constraints=constraints_list,
                options={"disp": False, "ftol": 1e-9, "maxiter": 1000},
            )

            if result.success:
                optimal_weights = result.x
                port_return, port_vol, sharpe = self.portfolio_performance(
                    optimal_weights, expected_returns, cov_matrix
                )

                return {
                    "weights": dict(zip(expected_returns.index, optimal_weights)),
                    "expected_return": port_return,
                    "volatility": port_vol,
                    "sharpe_ratio": sharpe,
                    "success": True,
                    "method": optimization_type,
                    "optimization_result": result,
                }
            else:
                self.logger.warning(f"Optimization failed: {result.message}")
                # Fallback to equal weights
                weights = np.array([1.0 / n_assets] * n_assets)
                port_return, port_vol, sharpe = self.portfolio_performance(
                    weights, expected_returns, cov_matrix
                )
                return {
                    "weights": dict(zip(expected_returns.index, weights)),
                    "expected_return": port_return,
                    "volatility": port_vol,
                    "sharpe_ratio": sharpe,
                    "success": False,
                    "method": "equal_weight_fallback",
                    "error": result.message,
                }

        except Exception as e:
            self.logger.error(f"Optimization error: {e}")
            # Fallback to equal weights
            weights = np.array([1.0 / n_assets] * n_assets)
            port_return, port_vol, sharpe = self.portfolio_performance(
                weights, expected_returns, cov_matrix
            )
            return {
                "weights": dict(zip(expected_returns.index, weights)),
                "expected_return": port_return,
                "volatility": port_vol,
                "sharpe_ratio": sharpe,
                "success": False,
                "method": "equal_weight_fallback",
                "error": str(e),
            }

    def calculate_efficient_frontier(
        self,
        expected_returns: pd.Series,
        cov_matrix: pd.DataFrame,
        num_points: int = 50,
    ) -> pd.DataFrame:
        """
        Calculate the efficient frontier.

        Args:
            expected_returns: Expected returns for each asset
            cov_matrix: Covariance matrix
            num_points: Number of points on the efficient frontier

        Returns:
            DataFrame with efficient frontier points
        """
        if not SCIPY_AVAILABLE:
            self.logger.warning(
                "SciPy not available - cannot calculate efficient frontier"
            )
            # Return a simple single point (equal weights)
            n_assets = len(expected_returns)
            weights = np.array([1.0 / n_assets] * n_assets)
            port_return, port_vol, sharpe = self.portfolio_performance(
                weights, expected_returns, cov_matrix
            )
            return pd.DataFrame(
                {
                    "Return": [port_return],
                    "Volatility": [port_vol],
                    "Sharpe_Ratio": [sharpe],
                    "Weights": [dict(zip(expected_returns.index, weights))],
                }
            )

        # Define return range
        min_ret = expected_returns.min()
        max_ret = expected_returns.max()
        target_returns = np.linspace(min_ret, max_ret, num_points)

        frontier_results = []

        for target_ret in target_returns:
            try:
                result = self.optimize_portfolio(
                    expected_returns,
                    cov_matrix,
                    optimization_type="target_return",
                    target_return=target_ret,
                )

                if result["success"]:
                    frontier_results.append(
                        {
                            "Return": result["expected_return"],
                            "Volatility": result["volatility"],
                            "Sharpe_Ratio": result["sharpe_ratio"],
                            "Weights": result["weights"],
                        }
                    )

            except Exception as e:
                self.logger.debug(f"Skipping target return {target_ret}: {e}")
                continue

        return pd.DataFrame(frontier_results)

    def suggest_rebalancing(
        self,
        current_weights: Dict[str, float],
        target_weights: Dict[str, float],
        threshold: float = 0.05,
        transaction_cost: float = 0.001,
    ) -> Dict:
        """
        Suggest portfolio rebalancing based on drift from target weights.

        Args:
            current_weights: Current portfolio weights
            target_weights: Target portfolio weights
            threshold: Rebalancing threshold (5% drift)
            transaction_cost: Transaction cost rate (0.1%)

        Returns:
            Rebalancing recommendation dictionary
        """
        recommendations = []
        total_drift = 0
        rebalancing_needed = False

        # Check each asset
        for symbol in target_weights:
            current_weight = current_weights.get(symbol, 0)
            target_weight = target_weights[symbol]
            drift = abs(current_weight - target_weight)

            if drift > threshold:
                rebalancing_needed = True
                action = "Buy" if current_weight < target_weight else "Sell"
                change_needed = target_weight - current_weight

                recommendations.append(
                    {
                        "symbol": symbol,
                        "current_weight": current_weight,
                        "target_weight": target_weight,
                        "drift": drift,
                        "action": action,
                        "change_needed": change_needed,
                        "urgency": "High" if drift > threshold * 2 else "Medium",
                    }
                )

            total_drift += drift

        # Estimate transaction costs
        if rebalancing_needed:
            total_trades = sum(
                1 for rec in recommendations if abs(rec["change_needed"]) > 0.01
            )
            estimated_cost = total_trades * transaction_cost
        else:
            estimated_cost = 0

        return {
            "rebalancing_needed": rebalancing_needed,
            "total_drift": total_drift,
            "recommendations": recommendations,
            "estimated_transaction_cost": estimated_cost,
            "cost_benefit_ratio": total_drift
            / (estimated_cost + 1e-10),  # Avoid division by zero
        }

    def save_optimized_portfolio(
        self,
        portfolio_name: str,
        optimization_result: Dict,
        optimization_type: str,
        constraints: Dict = None,
    ) -> int:
        """Save optimized portfolio to database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Save main portfolio record
            cursor.execute(
                """
                INSERT OR REPLACE INTO optimized_portfolios
                (portfolio_name, optimization_type, target_return, target_risk,
                 constraints_json, results_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    portfolio_name,
                    optimization_type,
                    optimization_result.get("expected_return", 0),
                    optimization_result.get("volatility", 0),
                    json.dumps(constraints or {}),
                    json.dumps(optimization_result, default=str),
                ),
            )

            portfolio_id = cursor.lastrowid

            # Save asset allocations
            for symbol, weight in optimization_result["weights"].items():
                cursor.execute(
                    """
                    INSERT INTO asset_allocations
                    (portfolio_id, symbol, weight, expected_return, volatility)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (portfolio_id, symbol, weight, 0, 0),
                )  # TODO: Add individual asset metrics

        self.logger.info(
            f"Saved optimized portfolio '{portfolio_name}' with ID {portfolio_id}"
        )
        return portfolio_id

    def load_portfolio(self, portfolio_name: str) -> Optional[Dict]:
        """Load saved portfolio from database."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                """
                SELECT * FROM optimized_portfolios WHERE portfolio_name = ?
            """,
                (portfolio_name,),
            ).fetchone()

            if result:
                portfolio_data = {
                    "id": result[0],
                    "name": result[1],
                    "optimization_type": result[2],
                    "target_return": result[3],
                    "target_risk": result[4],
                    "created_at": result[5],
                    "constraints": json.loads(result[6]),
                    "results": json.loads(result[7]),
                }

                # Load allocations
                allocations = conn.execute(
                    """
                    SELECT symbol, weight FROM asset_allocations
                    WHERE portfolio_id = ?
                """,
                    (result[0],),
                ).fetchall()

                portfolio_data["allocations"] = dict(allocations)
                return portfolio_data

        return None

    def get_portfolio_summary(self) -> pd.DataFrame:
        """Get summary of all saved portfolios."""
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(
                """
                SELECT portfolio_name, optimization_type, target_return,
                       target_risk, created_at
                FROM optimized_portfolios
                ORDER BY created_at DESC
            """,
                conn,
            )

        return df


# Example usage and testing
if __name__ == "__main__":
    # Create sample price data for testing
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", "2024-01-01", freq="D")

    # Simulate price data for 5 assets
    assets = ["BTC", "ETH", "ADA", "DOT", "LINK"]
    price_data = pd.DataFrame(index=dates, columns=assets)

    # Generate correlated random walks
    for i, asset in enumerate(assets):
        returns = np.random.normal(0.001, 0.02, len(dates))  # Daily returns
        prices = [100]  # Starting price
        for ret in returns[1:]:
            prices.append(prices[-1] * (1 + ret))
        price_data[asset] = prices[: len(dates)]

    # Initialize optimizer
    optimizer = PortfolioOptimizer()

    # Calculate returns and covariance
    expected_returns, cov_matrix = optimizer.calculate_returns_covariance(price_data)

    print("Expected Returns (Annual):")
    print(expected_returns)
    print("\nCovariance Matrix:")
    print(cov_matrix)

    # Optimize for maximum Sharpe ratio
    result = optimizer.optimize_portfolio(expected_returns, cov_matrix, "max_sharpe")

    print(f"\nMax Sharpe Portfolio:")
    print(f"Expected Return: {result['expected_return']:.2%}")
    print(f"Volatility: {result['volatility']:.2%}")
    print(f"Sharpe Ratio: {result['sharpe_ratio']:.3f}")
    print("Weights:")
    for asset, weight in result["weights"].items():
        print(f"  {asset}: {weight:.1%}")

    # Save portfolio
    portfolio_id = optimizer.save_optimized_portfolio(
        "Test_Max_Sharpe", result, "max_sharpe"
    )

    # Calculate efficient frontier
    frontier = optimizer.calculate_efficient_frontier(expected_returns, cov_matrix, 20)
    print(f"\nEfficient Frontier calculated with {len(frontier)} points")

    print("\nPortfolio optimization system ready!")
