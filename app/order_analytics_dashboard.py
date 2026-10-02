"""
Order Analytics Dashboard
Provides comprehensive analytics interface with order performance metrics,
success rates, profit/loss analysis, trading patterns, and strategy optimization insights.
"""

import json
import math
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    from order_management_db import OrderManagementDB
    from order_management_models import ConditionType, OrderSide, OrderStatus, OrderType

    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False


class AnalyticsTimeframe(Enum):
    """Analytics timeframes."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    ALL_TIME = "all_time"


class PerformanceMetric(Enum):
    """Performance metrics to calculate."""

    WIN_RATE = "win_rate"
    PROFIT_FACTOR = "profit_factor"
    SHARPE_RATIO = "sharpe_ratio"
    MAX_DRAWDOWN = "max_drawdown"
    AVERAGE_WIN = "average_win"
    AVERAGE_LOSS = "average_loss"
    TOTAL_RETURN = "total_return"
    VOLATILITY = "volatility"


class OrderAnalytics:
    """Core analytics engine for order performance analysis."""

    def __init__(self, db_path: Optional[str] = None):
        self.db = OrderManagementDB(db_path) if ANALYTICS_AVAILABLE else None
        self.cache = {}
        self.cache_expiry = {}

    def get_order_performance_summary(
        self, timeframe: str = "monthly", symbol: str = None
    ) -> Dict[str, Any]:
        """Get comprehensive order performance summary."""
        try:
            cache_key = f"performance_{timeframe}_{symbol}"

            # Check cache
            if self._is_cache_valid(cache_key):
                return self.cache[cache_key]

            # Get orders within timeframe
            orders = self._get_orders_for_timeframe(timeframe, symbol)

            if not orders:
                return {"error": "No orders found for the specified timeframe"}

            # Calculate metrics
            summary = {
                "timeframe": timeframe,
                "symbol_filter": symbol,
                "total_orders": len(orders),
                "executed_orders": 0,
                "pending_orders": 0,
                "cancelled_orders": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "profit_factor": 0.0,
                "average_win": 0.0,
                "average_loss": 0.0,
                "largest_win": 0.0,
                "largest_loss": 0.0,
                "average_hold_time": 0.0,
                "success_by_type": {},
                "pnl_by_symbol": {},
                "monthly_performance": [],
                "order_size_analysis": {},
                "time_analysis": {},
            }

            # Categorize orders by status
            executed_orders = []
            for order in orders:
                status = order.get("status", "")
                if status == OrderStatus.FILLED.value:
                    summary["executed_orders"] += 1
                    executed_orders.append(order)
                elif status == OrderStatus.PENDING.value:
                    summary["pending_orders"] += 1
                elif status == OrderStatus.CANCELLED.value:
                    summary["cancelled_orders"] += 1

            if executed_orders:
                # Calculate PnL metrics
                pnl_analysis = self._calculate_pnl_metrics(executed_orders)
                summary.update(pnl_analysis)

                # Calculate success rates by order type
                summary["success_by_type"] = self._calculate_success_by_type(
                    executed_orders
                )

                # PnL by symbol
                summary["pnl_by_symbol"] = self._calculate_pnl_by_symbol(
                    executed_orders
                )

                # Monthly performance breakdown
                summary["monthly_performance"] = self._calculate_monthly_performance(
                    executed_orders
                )

                # Order size analysis
                summary["order_size_analysis"] = self._calculate_order_size_analysis(
                    executed_orders
                )

                # Time-based analysis
                summary["time_analysis"] = self._calculate_time_analysis(
                    executed_orders
                )

            # Cache result
            self.cache[cache_key] = summary
            self.cache_expiry[cache_key] = datetime.now() + timedelta(minutes=5)

            return summary

        except Exception as e:
            return {"error": str(e)}

    def _get_orders_for_timeframe(
        self, timeframe: str, symbol: str = None
    ) -> List[Dict]:
        """Get orders for specified timeframe."""
        try:
            if not self.db:
                return []

            # Calculate date range
            end_date = datetime.now()

            if timeframe == AnalyticsTimeframe.DAILY.value:
                start_date = end_date - timedelta(days=1)
            elif timeframe == AnalyticsTimeframe.WEEKLY.value:
                start_date = end_date - timedelta(weeks=1)
            elif timeframe == AnalyticsTimeframe.MONTHLY.value:
                start_date = end_date - timedelta(days=30)
            elif timeframe == AnalyticsTimeframe.QUARTERLY.value:
                start_date = end_date - timedelta(days=90)
            elif timeframe == AnalyticsTimeframe.YEARLY.value:
                start_date = end_date - timedelta(days=365)
            else:  # ALL_TIME
                start_date = datetime(2020, 1, 1)  # Far back date

            # Get orders from database
            all_orders = self.db.get_orders()

            # Filter by timeframe and symbol
            filtered_orders = []
            for order in all_orders:
                order_date = order.get("created_at")
                if isinstance(order_date, str):
                    order_date = datetime.fromisoformat(order_date)

                if start_date <= order_date <= end_date:
                    if symbol is None or order.get("symbol") == symbol:
                        filtered_orders.append(order)

            return filtered_orders

        except Exception as e:
            print(f"Error getting orders for timeframe: {e}")
            return []

    def _calculate_pnl_metrics(self, orders: List[Dict]) -> Dict[str, float]:
        """Calculate PnL-related metrics."""
        try:
            wins = []
            losses = []
            all_pnl = []

            for order in orders:
                # Get order executions to calculate PnL
                pnl = self._calculate_order_pnl(order)
                if pnl is not None:
                    all_pnl.append(pnl)
                    if pnl > 0:
                        wins.append(pnl)
                    elif pnl < 0:
                        losses.append(abs(pnl))

            if not all_pnl:
                return {
                    "total_pnl": 0.0,
                    "gross_profit": 0.0,
                    "gross_loss": 0.0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "average_win": 0.0,
                    "average_loss": 0.0,
                    "largest_win": 0.0,
                    "largest_loss": 0.0,
                }

            total_pnl = sum(all_pnl)
            gross_profit = sum(wins) if wins else 0.0
            gross_loss = sum(losses) if losses else 0.0
            win_rate = (len(wins) / len(all_pnl)) * 100 if all_pnl else 0.0

            return {
                "total_pnl": total_pnl,
                "gross_profit": gross_profit,
                "gross_loss": gross_loss,
                "win_rate": win_rate,
                "profit_factor": (
                    gross_profit / gross_loss
                    if gross_loss > 0
                    else float("inf") if gross_profit > 0 else 0.0
                ),
                "average_win": statistics.mean(wins) if wins else 0.0,
                "average_loss": statistics.mean(losses) if losses else 0.0,
                "largest_win": max(wins) if wins else 0.0,
                "largest_loss": max(losses) if losses else 0.0,
            }

        except Exception as e:
            print(f"Error calculating PnL metrics: {e}")
            return {}

    def _calculate_order_pnl(self, order: Dict) -> Optional[float]:
        """Calculate PnL for a single order."""
        try:
            # This is a simplified calculation
            # In a real implementation, you would get actual execution data
            order_type = order.get("type", "")
            side = order.get("side", "")
            quantity = float(order.get("quantity", 0))
            entry_price = float(order.get("price", 0))

            # Mock current price for calculation (in real implementation, get actual exit price)
            import random

            exit_price = entry_price * (1 + random.uniform(-0.05, 0.05))

            if side.upper() == "BUY":
                pnl = (exit_price - entry_price) * quantity
            else:  # SELL
                pnl = (entry_price - exit_price) * quantity

            return pnl

        except Exception as e:
            print(f"Error calculating order PnL: {e}")
            return None

    def _calculate_success_by_type(self, orders: List[Dict]) -> Dict[str, Dict]:
        """Calculate success rates by order type."""
        try:
            type_stats = defaultdict(
                lambda: {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0}
            )

            for order in orders:
                order_type = order.get("type", OrderType.MARKET.value)
                pnl = self._calculate_order_pnl(order)

                if pnl is not None:
                    type_stats[order_type]["total"] += 1
                    if pnl > 0:
                        type_stats[order_type]["wins"] += 1
                    else:
                        type_stats[order_type]["losses"] += 1

            # Calculate win rates
            for order_type in type_stats:
                total = type_stats[order_type]["total"]
                wins = type_stats[order_type]["wins"]
                type_stats[order_type]["win_rate"] = (
                    (wins / total * 100) if total > 0 else 0.0
                )

            return dict(type_stats)

        except Exception as e:
            print(f"Error calculating success by type: {e}")
            return {}

    def _calculate_pnl_by_symbol(self, orders: List[Dict]) -> Dict[str, Dict]:
        """Calculate PnL breakdown by symbol."""
        try:
            symbol_stats = defaultdict(
                lambda: {"total_pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}
            )

            for order in orders:
                symbol = order.get("symbol", "UNKNOWN")
                pnl = self._calculate_order_pnl(order)

                if pnl is not None:
                    symbol_stats[symbol]["total_pnl"] += pnl
                    symbol_stats[symbol]["trades"] += 1
                    if pnl > 0:
                        symbol_stats[symbol]["wins"] += 1
                    else:
                        symbol_stats[symbol]["losses"] += 1

            # Calculate additional metrics
            for symbol in symbol_stats:
                stats = symbol_stats[symbol]
                trades = stats["trades"]
                wins = stats["wins"]

                stats["win_rate"] = (wins / trades * 100) if trades > 0 else 0.0
                stats["avg_pnl"] = stats["total_pnl"] / trades if trades > 0 else 0.0

            return dict(symbol_stats)

        except Exception as e:
            print(f"Error calculating PnL by symbol: {e}")
            return {}

    def _calculate_monthly_performance(self, orders: List[Dict]) -> List[Dict]:
        """Calculate monthly performance breakdown."""
        try:
            monthly_data = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})

            for order in orders:
                order_date = order.get("created_at")
                if isinstance(order_date, str):
                    order_date = datetime.fromisoformat(order_date)

                month_key = order_date.strftime("%Y-%m")
                pnl = self._calculate_order_pnl(order)

                if pnl is not None:
                    monthly_data[month_key]["pnl"] += pnl
                    monthly_data[month_key]["trades"] += 1
                    if pnl > 0:
                        monthly_data[month_key]["wins"] += 1

            # Convert to list and add calculated metrics
            monthly_performance = []
            for month, data in sorted(monthly_data.items()):
                trades = data["trades"]
                wins = data["wins"]

                monthly_performance.append(
                    {
                        "month": month,
                        "pnl": data["pnl"],
                        "trades": trades,
                        "wins": wins,
                        "win_rate": (wins / trades * 100) if trades > 0 else 0.0,
                    }
                )

            return monthly_performance

        except Exception as e:
            print(f"Error calculating monthly performance: {e}")
            return []

    def _calculate_order_size_analysis(self, orders: List[Dict]) -> Dict[str, Any]:
        """Analyze order sizes and their performance."""
        try:
            size_buckets = {
                "small": {"max": 1000, "orders": [], "pnl": 0.0},
                "medium": {"max": 5000, "orders": [], "pnl": 0.0},
                "large": {"max": 25000, "orders": [], "pnl": 0.0},
                "xlarge": {"max": float("inf"), "orders": [], "pnl": 0.0},
            }

            for order in orders:
                quantity = float(order.get("quantity", 0))
                price = float(order.get("price", 0))
                order_size = quantity * price
                pnl = self._calculate_order_pnl(order)

                # Categorize by size
                for bucket_name, bucket in size_buckets.items():
                    if order_size <= bucket["max"]:
                        bucket["orders"].append(order)
                        if pnl:
                            bucket["pnl"] += pnl
                        break

            # Calculate metrics for each bucket
            analysis = {}
            for bucket_name, bucket in size_buckets.items():
                order_count = len(bucket["orders"])

                analysis[bucket_name] = {
                    "order_count": order_count,
                    "total_pnl": bucket["pnl"],
                    "avg_pnl": bucket["pnl"] / order_count if order_count > 0 else 0.0,
                    "max_size": (
                        bucket["max"] if bucket["max"] != float("inf") else "No limit"
                    ),
                }

            return analysis

        except Exception as e:
            print(f"Error calculating order size analysis: {e}")
            return {}

    def _calculate_time_analysis(self, orders: List[Dict]) -> Dict[str, Any]:
        """Analyze performance by time of day, day of week, etc."""
        try:
            hour_performance = defaultdict(lambda: {"trades": 0, "pnl": 0.0})
            dow_performance = defaultdict(
                lambda: {"trades": 0, "pnl": 0.0}
            )  # Day of week

            for order in orders:
                order_date = order.get("created_at")
                if isinstance(order_date, str):
                    order_date = datetime.fromisoformat(order_date)

                hour = order_date.hour
                dow = order_date.strftime("%A")
                pnl = self._calculate_order_pnl(order)

                if pnl is not None:
                    hour_performance[hour]["trades"] += 1
                    hour_performance[hour]["pnl"] += pnl

                    dow_performance[dow]["trades"] += 1
                    dow_performance[dow]["pnl"] += pnl

            # Find best performing times
            best_hour = max(
                hour_performance.items(),
                key=lambda x: x[1]["pnl"],
                default=(0, {"pnl": 0}),
            )
            best_dow = max(
                dow_performance.items(),
                key=lambda x: x[1]["pnl"],
                default=("Monday", {"pnl": 0}),
            )

            return {
                "hourly_performance": dict(hour_performance),
                "dow_performance": dict(dow_performance),
                "best_hour": {"hour": best_hour[0], "pnl": best_hour[1]["pnl"]},
                "best_day": {"day": best_dow[0], "pnl": best_dow[1]["pnl"]},
            }

        except Exception as e:
            print(f"Error calculating time analysis: {e}")
            return {}

    def get_strategy_performance(self, strategy_name: str = None) -> Dict[str, Any]:
        """Analyze performance by trading strategy."""
        try:
            if not self.db:
                return {"error": "Database not available"}

            # Get orders filtered by strategy if specified
            orders = self.db.get_orders()

            if strategy_name:
                orders = [o for o in orders if o.get("strategy") == strategy_name]

            # Group by strategy
            strategy_performance = defaultdict(
                lambda: {
                    "orders": [],
                    "total_pnl": 0.0,
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                }
            )

            for order in orders:
                strategy = order.get("strategy", "default")
                pnl = self._calculate_order_pnl(order)

                strategy_performance[strategy]["orders"].append(order)
                strategy_performance[strategy]["trades"] += 1

                if pnl is not None:
                    strategy_performance[strategy]["total_pnl"] += pnl
                    if pnl > 0:
                        strategy_performance[strategy]["wins"] += 1
                    else:
                        strategy_performance[strategy]["losses"] += 1

            # Calculate metrics for each strategy
            results = {}
            for strategy, data in strategy_performance.items():
                trades = data["trades"]
                wins = data["wins"]

                results[strategy] = {
                    "total_orders": trades,
                    "total_pnl": data["total_pnl"],
                    "avg_pnl_per_trade": (
                        data["total_pnl"] / trades if trades > 0 else 0.0
                    ),
                    "win_rate": (wins / trades * 100) if trades > 0 else 0.0,
                    "wins": wins,
                    "losses": data["losses"],
                }

            return results

        except Exception as e:
            return {"error": str(e)}

    def get_risk_metrics(self, timeframe: str = "monthly") -> Dict[str, Any]:
        """Calculate risk-adjusted performance metrics."""
        try:
            orders = self._get_orders_for_timeframe(timeframe)

            if not orders:
                return {"error": "No orders found"}

            # Calculate daily returns
            daily_returns = self._calculate_daily_returns(orders)

            if not daily_returns:
                return {"error": "Insufficient data for risk metrics"}

            # Risk metrics
            returns_mean = statistics.mean(daily_returns)
            returns_std = (
                statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0.0
            )

            # Sharpe ratio (assuming 0% risk-free rate)
            sharpe_ratio = (
                (returns_mean / returns_std * math.sqrt(252))
                if returns_std > 0
                else 0.0
            )

            # Maximum drawdown
            max_drawdown = self._calculate_max_drawdown(daily_returns)

            # Value at Risk (95% confidence)
            var_95 = self._calculate_var(daily_returns, 0.05) if daily_returns else 0.0

            # Sortino ratio (downside deviation)
            sortino_ratio = self._calculate_sortino_ratio(daily_returns)

            return {
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": max_drawdown,
                "volatility": returns_std * math.sqrt(252),  # Annualized
                "var_95": var_95,
                "sortino_ratio": sortino_ratio,
                "avg_daily_return": returns_mean,
                "total_trading_days": len(daily_returns),
            }

        except Exception as e:
            return {"error": str(e)}

    def _calculate_daily_returns(self, orders: List[Dict]) -> List[float]:
        """Calculate daily returns from orders."""
        try:
            daily_pnl = defaultdict(float)

            for order in orders:
                order_date = order.get("created_at")
                if isinstance(order_date, str):
                    order_date = datetime.fromisoformat(order_date)

                day_key = order_date.strftime("%Y-%m-%d")
                pnl = self._calculate_order_pnl(order)

                if pnl is not None:
                    daily_pnl[day_key] += pnl

            # Convert to returns (assuming starting portfolio value)
            portfolio_value = 100000  # Mock portfolio value
            daily_returns = [pnl / portfolio_value for pnl in daily_pnl.values()]

            return daily_returns

        except Exception as e:
            print(f"Error calculating daily returns: {e}")
            return []

    def _calculate_max_drawdown(self, returns: List[float]) -> float:
        """Calculate maximum drawdown."""
        try:
            if not returns:
                return 0.0

            # Calculate cumulative returns
            cumulative = 1.0
            peak = 1.0
            max_dd = 0.0

            for ret in returns:
                cumulative *= 1 + ret
                peak = max(peak, cumulative)
                drawdown = (peak - cumulative) / peak
                max_dd = max(max_dd, drawdown)

            return max_dd * 100  # Convert to percentage

        except Exception as e:
            print(f"Error calculating max drawdown: {e}")
            return 0.0

    def _calculate_var(self, returns: List[float], confidence: float) -> float:
        """Calculate Value at Risk."""
        try:
            if len(returns) < 10:
                return 0.0

            sorted_returns = sorted(returns)
            index = int(len(sorted_returns) * confidence)
            return abs(sorted_returns[index]) * 100  # Convert to percentage

        except Exception as e:
            print(f"Error calculating VaR: {e}")
            return 0.0

    def _calculate_sortino_ratio(self, returns: List[float]) -> float:
        """Calculate Sortino ratio."""
        try:
            if not returns:
                return 0.0

            avg_return = statistics.mean(returns)
            downside_returns = [r for r in returns if r < 0]

            if not downside_returns:
                return float("inf") if avg_return > 0 else 0.0

            downside_std = statistics.stdev(downside_returns)

            if downside_std == 0:
                return float("inf") if avg_return > 0 else 0.0

            return (avg_return / downside_std) * math.sqrt(252)  # Annualized

        except Exception as e:
            print(f"Error calculating Sortino ratio: {e}")
            return 0.0

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache is still valid."""
        try:
            if cache_key not in self.cache_expiry:
                return False

            return datetime.now() < self.cache_expiry[cache_key]

        except Exception as e:
            return False

    def clear_cache(self):
        """Clear analytics cache."""
        self.cache.clear()
        self.cache_expiry.clear()

    def generate_performance_report(self, timeframe: str = "monthly") -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        try:
            report = {
                "generated_at": datetime.now(),
                "timeframe": timeframe,
                "sections": {},
            }

            # Overall performance
            report["sections"]["overall_performance"] = (
                self.get_order_performance_summary(timeframe)
            )

            # Strategy performance
            report["sections"]["strategy_performance"] = self.get_strategy_performance()

            # Risk metrics
            report["sections"]["risk_metrics"] = self.get_risk_metrics(timeframe)

            # Recommendations
            report["sections"]["recommendations"] = self._generate_recommendations(
                report["sections"]["overall_performance"],
                report["sections"]["risk_metrics"],
            )

            return report

        except Exception as e:
            return {"error": str(e)}

    def _generate_recommendations(
        self, performance: Dict, risk_metrics: Dict
    ) -> List[str]:
        """Generate performance recommendations."""
        recommendations = []

        try:
            # Win rate recommendations
            win_rate = performance.get("win_rate", 0)
            if win_rate < 40:
                recommendations.append(
                    "Low win rate detected - consider refining entry criteria"
                )
            elif win_rate > 80:
                recommendations.append(
                    "Very high win rate - ensure you're not avoiding necessary losses"
                )

            # Profit factor recommendations
            profit_factor = performance.get("profit_factor", 0)
            if profit_factor < 1.2:
                recommendations.append("Low profit factor - review risk/reward ratios")

            # Risk recommendations
            sharpe_ratio = risk_metrics.get("sharpe_ratio", 0)
            if sharpe_ratio < 1.0:
                recommendations.append(
                    "Low risk-adjusted returns - consider reducing position sizes"
                )

            max_dd = risk_metrics.get("max_drawdown", 0)
            if max_dd > 15:
                recommendations.append(
                    "High maximum drawdown - implement better risk management"
                )

            # Size analysis recommendations
            size_analysis = performance.get("order_size_analysis", {})
            if size_analysis:
                large_orders = size_analysis.get("large", {})
                if large_orders.get("avg_pnl", 0) < 0:
                    recommendations.append(
                        "Large orders performing poorly - consider position sizing"
                    )

            return recommendations

        except Exception as e:
            print(f"Error generating recommendations: {e}")
            return ["Error generating recommendations"]


# Global analytics engine
_analytics_engine = None


def get_analytics_engine(db_path: Optional[str] = None) -> OrderAnalytics:
    """Get the global analytics engine instance."""
    global _analytics_engine
    if _analytics_engine is None:
        _analytics_engine = OrderAnalytics(db_path)
    return _analytics_engine


if __name__ == "__main__":
    # Test the analytics engine
    engine = get_analytics_engine()

    print("Order Analytics Engine Test")
    print("=" * 40)

    # Test performance summary
    performance = engine.get_order_performance_summary("monthly")
    print(f"Performance Summary: {performance}")

    # Test strategy performance
    strategy_perf = engine.get_strategy_performance()
    print(f"Strategy Performance: {strategy_perf}")

    # Test risk metrics
    risk_metrics = engine.get_risk_metrics("monthly")
    print(f"Risk Metrics: {risk_metrics}")

    # Generate full report
    report = engine.generate_performance_report("monthly")
    print(f"Performance Report Generated: {len(report.get('sections', {}))} sections")
