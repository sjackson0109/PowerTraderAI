"""
Enhanced Portfolio Analytics System (Item 21)
Advanced analytics for cryptocurrency portfolio performance
"""

import json
import math
import os
import sqlite3
import tkinter as tk
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("Warning: pandas/numpy not available. Advanced analytics disabled.")

try:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import seaborn as sns
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib/seaborn not available. Charts disabled.")

try:
    from scipy import stats

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("Warning: scipy not available. Statistical analysis limited.")


@dataclass
class PortfolioSnapshot:
    """Portfolio snapshot for historical analysis"""

    timestamp: str
    total_value: float
    total_cost: float
    holdings_count: int
    allocations: Dict[str, float]  # symbol -> percentage
    prices: Dict[str, float]  # symbol -> price
    quantities: Dict[str, float]  # symbol -> quantity


@dataclass
class PerformanceMetrics:
    """Portfolio performance metrics"""

    total_return: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown: float
    volatility: float
    alpha: float
    beta: float
    daily_returns: List[float]
    cumulative_returns: List[float]
    timestamps: List[str]


@dataclass
class RiskMetrics:
    """Risk analysis metrics"""

    var_95: float  # Value at Risk 95%
    var_99: float  # Value at Risk 99%
    expected_shortfall_95: float
    expected_shortfall_99: float
    correlation_matrix: Dict[str, Dict[str, float]]
    portfolio_volatility: float
    concentration_risk: float


class PortfolioAnalytics:
    """Main portfolio analytics engine"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            import pt_paths

            db_path = pt_paths.data_file("portfolio_analytics.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize analytics database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Portfolio snapshots table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    total_value REAL NOT NULL,
                    total_cost REAL NOT NULL,
                    holdings_count INTEGER NOT NULL,
                    allocations_json TEXT NOT NULL,
                    prices_json TEXT NOT NULL,
                    quantities_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Performance metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    portfolio_value REAL NOT NULL,
                    daily_return REAL NOT NULL,
                    cumulative_return REAL NOT NULL,
                    benchmark_return REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Risk metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS risk_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    calculation_date TEXT NOT NULL,
                    var_95 REAL NOT NULL,
                    var_99 REAL NOT NULL,
                    expected_shortfall_95 REAL NOT NULL,
                    expected_shortfall_99 REAL NOT NULL,
                    portfolio_volatility REAL NOT NULL,
                    concentration_risk REAL NOT NULL,
                    correlation_matrix_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

    def save_portfolio_snapshot(self, holdings_data: List[Dict]) -> bool:
        """Save a portfolio snapshot"""
        try:
            timestamp = datetime.now().isoformat()
            total_value = sum(h.get("current_value", 0) for h in holdings_data)
            total_cost = sum(h.get("total_cost", 0) for h in holdings_data)
            holdings_count = len(holdings_data)

            # Calculate allocations
            allocations = {}
            prices = {}
            quantities = {}

            for holding in holdings_data:
                symbol = holding.get("symbol", "")
                value = holding.get("current_value", 0)
                allocations[symbol] = (
                    (value / total_value * 100) if total_value > 0 else 0
                )
                prices[symbol] = holding.get("current_price", 0)
                quantities[symbol] = holding.get("quantity", 0)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO portfolio_snapshots
                    (timestamp, total_value, total_cost, holdings_count,
                     allocations_json, prices_json, quantities_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        timestamp,
                        total_value,
                        total_cost,
                        holdings_count,
                        json.dumps(allocations),
                        json.dumps(prices),
                        json.dumps(quantities),
                    ),
                )
                conn.commit()

            return True

        except Exception as e:
            print(f"Error saving portfolio snapshot: {e}")
            return False

    def calculate_performance_metrics(
        self, days: int = 30
    ) -> Optional[PerformanceMetrics]:
        """Calculate portfolio performance metrics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Get historical snapshots
                cursor.execute("""
                    SELECT timestamp, total_value, total_cost
                    FROM portfolio_snapshots
                    WHERE datetime(timestamp) >= datetime('now', '-{} days')
                    ORDER BY timestamp
                """.format(days))

                snapshots = cursor.fetchall()

                if len(snapshots) < 2:
                    return None

                # Calculate returns
                values = [s[1] for s in snapshots]
                timestamps = [s[0] for s in snapshots]

                daily_returns = []
                for i in range(1, len(values)):
                    daily_return = (
                        (values[i] - values[i - 1]) / values[i - 1]
                        if values[i - 1] > 0
                        else 0
                    )
                    daily_returns.append(daily_return)

                # Calculate cumulative returns
                cumulative_returns = []
                cumulative = 1.0
                for ret in daily_returns:
                    cumulative *= 1 + ret
                    cumulative_returns.append(cumulative - 1)

                # Calculate metrics
                total_return = values[-1] - values[0]
                total_return_pct = (
                    total_return / values[0] * 100 if values[0] > 0 else 0
                )

                # Volatility (standard deviation of returns)
                if PANDAS_AVAILABLE:
                    volatility = (
                        np.std(daily_returns) * math.sqrt(365) if daily_returns else 0
                    )

                    # Sharpe ratio (assuming risk-free rate = 0 for simplicity)
                    mean_return = np.mean(daily_returns) if daily_returns else 0
                    sharpe_ratio = (
                        mean_return / volatility * math.sqrt(365)
                        if volatility > 0
                        else 0
                    )

                    # Max drawdown
                    peak = values[0]
                    max_dd = 0
                    for value in values:
                        if value > peak:
                            peak = value
                        drawdown = (peak - value) / peak if peak > 0 else 0
                        max_dd = max(max_dd, drawdown)

                    max_drawdown = max_dd * 100
                else:
                    volatility = 0
                    sharpe_ratio = 0
                    max_drawdown = 0

                return PerformanceMetrics(
                    total_return=total_return,
                    total_return_pct=total_return_pct,
                    sharpe_ratio=sharpe_ratio,
                    max_drawdown=max_drawdown,
                    volatility=volatility,
                    alpha=0,  # Would need benchmark for accurate calculation
                    beta=0,  # Would need benchmark for accurate calculation
                    daily_returns=daily_returns,
                    cumulative_returns=cumulative_returns,
                    timestamps=timestamps[1:],  # Align with returns
                )

        except Exception as e:
            print(f"Error calculating performance metrics: {e}")
            return None

    def calculate_risk_metrics(
        self, confidence_level: float = 0.95
    ) -> Optional[RiskMetrics]:
        """Calculate risk metrics including VaR and Expected Shortfall"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Get recent snapshots for correlation analysis
                cursor.execute("""
                    SELECT allocations_json, total_value
                    FROM portfolio_snapshots
                    WHERE datetime(timestamp) >= datetime('now', '-30 days')
                    ORDER BY timestamp DESC
                    LIMIT 30
                """)

                snapshots = cursor.fetchall()

                if len(snapshots) < 10:
                    return None

                # Calculate portfolio returns
                values = [s[1] for s in snapshots]
                returns = []
                for i in range(1, len(values)):
                    ret = (
                        (values[i] - values[i - 1]) / values[i - 1]
                        if values[i - 1] > 0
                        else 0
                    )
                    returns.append(ret)

                if not returns:
                    return None

                if PANDAS_AVAILABLE and SCIPY_AVAILABLE:
                    returns_array = np.array(returns)

                    # Calculate VaR
                    var_95 = (
                        np.percentile(returns_array, 5) * values[-1]
                        if len(returns_array) > 0
                        else 0
                    )
                    var_99 = (
                        np.percentile(returns_array, 1) * values[-1]
                        if len(returns_array) > 0
                        else 0
                    )

                    # Calculate Expected Shortfall (Conditional VaR)
                    es_95_threshold = np.percentile(returns_array, 5)
                    es_99_threshold = np.percentile(returns_array, 1)

                    tail_95 = returns_array[returns_array <= es_95_threshold]
                    tail_99 = returns_array[returns_array <= es_99_threshold]

                    expected_shortfall_95 = (
                        np.mean(tail_95) * values[-1] if len(tail_95) > 0 else 0
                    )
                    expected_shortfall_99 = (
                        np.mean(tail_99) * values[-1] if len(tail_99) > 0 else 0
                    )

                    # Portfolio volatility
                    portfolio_volatility = np.std(returns_array) * math.sqrt(365)

                    # Concentration risk (Herfindahl index)
                    latest_allocations = json.loads(snapshots[0][0])
                    allocation_values = list(latest_allocations.values())
                    concentration_risk = (
                        sum([(w / 100) ** 2 for w in allocation_values])
                        if allocation_values
                        else 0
                    )

                    # Simple correlation matrix (would be enhanced with individual asset returns)
                    correlation_matrix = {"BTC": {"BTC": 1.0}, "ETH": {"ETH": 1.0}}

                else:
                    # Fallback calculations without advanced libraries
                    sorted_returns = sorted(returns)
                    portfolio_value = values[-1]

                    var_95_idx = max(0, int(len(sorted_returns) * 0.05))
                    var_99_idx = max(0, int(len(sorted_returns) * 0.01))

                    var_95 = (
                        sorted_returns[var_95_idx] * portfolio_value
                        if sorted_returns
                        else 0
                    )
                    var_99 = (
                        sorted_returns[var_99_idx] * portfolio_value
                        if sorted_returns
                        else 0
                    )

                    expected_shortfall_95 = var_95  # Simplified
                    expected_shortfall_99 = var_99  # Simplified

                    # Basic volatility
                    mean_return = sum(returns) / len(returns) if returns else 0
                    variance = (
                        sum([(r - mean_return) ** 2 for r in returns]) / len(returns)
                        if returns
                        else 0
                    )
                    portfolio_volatility = math.sqrt(variance) * math.sqrt(365)

                    concentration_risk = 0
                    correlation_matrix = {}

                return RiskMetrics(
                    var_95=abs(var_95),
                    var_99=abs(var_99),
                    expected_shortfall_95=abs(expected_shortfall_95),
                    expected_shortfall_99=abs(expected_shortfall_99),
                    correlation_matrix=correlation_matrix,
                    portfolio_volatility=portfolio_volatility,
                    concentration_risk=concentration_risk,
                )

        except Exception as e:
            print(f"Error calculating risk metrics: {e}")
            return None

    def get_asset_allocation_history(
        self, days: int = 30
    ) -> Dict[str, List[Tuple[str, float]]]:
        """Get historical asset allocation data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, allocations_json
                    FROM portfolio_snapshots
                    WHERE datetime(timestamp) >= datetime('now', '-{} days')
                    ORDER BY timestamp
                """.format(days))

                snapshots = cursor.fetchall()

                allocation_history = {}
                for timestamp, allocations_json in snapshots:
                    allocations = json.loads(allocations_json)
                    for symbol, percentage in allocations.items():
                        if symbol not in allocation_history:
                            allocation_history[symbol] = []
                        allocation_history[symbol].append((timestamp, percentage))

                return allocation_history

        except Exception as e:
            print(f"Error getting allocation history: {e}")
            return {}

    def export_analytics_report(self, file_path: str, days: int = 30) -> bool:
        """Export comprehensive analytics report"""
        try:
            performance = self.calculate_performance_metrics(days)
            risk_metrics = self.calculate_risk_metrics()
            allocation_history = self.get_asset_allocation_history(days)

            report_data = {
                "generated_at": datetime.now().isoformat(),
                "analysis_period_days": days,
                "performance_metrics": asdict(performance) if performance else None,
                "risk_metrics": asdict(risk_metrics) if risk_metrics else None,
                "allocation_history": allocation_history,
            }

            with open(file_path, "w") as f:
                json.dump(report_data, f, indent=2)

            return True

        except Exception as e:
            print(f"Error exporting analytics report: {e}")
            return False


# Global instance
_portfolio_analytics = None


def get_portfolio_analytics() -> PortfolioAnalytics:
    """Get the global portfolio analytics instance"""
    global _portfolio_analytics
    if _portfolio_analytics is None:
        _portfolio_analytics = PortfolioAnalytics()
    return _portfolio_analytics
