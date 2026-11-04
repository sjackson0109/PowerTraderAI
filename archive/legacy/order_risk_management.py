"""
Order Risk Management System
Implements comprehensive risk controls including position sizing, portfolio-level risk limits,
correlation analysis, drawdown protection, and automated risk alerts.
"""

import json
import math
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    from order_management_db import OrderManagementDB
    from order_management_models import ConditionType, OrderSide, OrderStatus, OrderType

    RISK_MANAGEMENT_AVAILABLE = True
except ImportError:
    RISK_MANAGEMENT_AVAILABLE = False


class RiskLevel(Enum):
    """Risk severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskType(Enum):
    """Types of risk checks."""

    POSITION_SIZE = "position_size"
    PORTFOLIO_CONCENTRATION = "portfolio_concentration"
    CORRELATION = "correlation"
    LEVERAGE = "leverage"
    DRAWDOWN = "drawdown"
    VOLATILITY = "volatility"
    LIQUIDITY = "liquidity"
    NEWS_SENTIMENT = "news_sentiment"
    MARKET_HOURS = "market_hours"
    CUSTOM = "custom"


class AlertType(Enum):
    """Types of risk alerts."""

    POSITION_LIMIT = "position_limit"
    PORTFOLIO_RISK = "portfolio_risk"
    CORRELATION_WARNING = "correlation_warning"
    DRAWDOWN_LIMIT = "drawdown_limit"
    VOLATILITY_SPIKE = "volatility_spike"
    LIQUIDITY_RISK = "liquidity_risk"
    MARGIN_CALL = "margin_call"
    CUSTOM_RISK = "custom_risk"


@dataclass
class RiskLimit:
    """Represents a risk limit configuration."""

    name: str
    risk_type: RiskType
    limit_value: float
    warning_threshold: float
    enabled: bool = True
    symbols: List[str] = None  # Empty means applies to all symbols
    parameters: Dict = None

    def __post_init__(self):
        if self.symbols is None:
            self.symbols = []
        if self.parameters is None:
            self.parameters = {}


@dataclass
class RiskAlert:
    """Represents a risk alert."""

    id: str
    alert_type: AlertType
    risk_level: RiskLevel
    symbol: str
    message: str
    current_value: float
    limit_value: float
    triggered_at: datetime
    acknowledged: bool = False
    resolved: bool = False


class PositionSizer:
    """Calculates optimal position sizes based on risk parameters."""

    def __init__(self, config: Dict):
        self.max_position_pct = float(
            config.get("max_position_pct", 5.0)
        )  # % of portfolio
        self.max_risk_per_trade = float(
            config.get("max_risk_per_trade", 2.0)
        )  # % risk per trade
        self.volatility_adjustment = config.get("volatility_adjustment", True)
        self.correlation_adjustment = config.get("correlation_adjustment", True)

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        portfolio_value: float,
        market_data: Dict = None,
    ) -> Dict[str, Any]:
        """Calculate optimal position size."""
        try:
            if market_data is None:
                market_data = {}

            result = {
                "recommended_quantity": 0.0,
                "recommended_notional": 0.0,
                "risk_amount": 0.0,
                "position_pct": 0.0,
                "risk_pct": 0.0,
                "adjustments": [],
                "warnings": [],
            }

            # Calculate base position size
            max_portfolio_allocation = portfolio_value * (self.max_position_pct / 100)
            max_risk_amount = portfolio_value * (self.max_risk_per_trade / 100)

            # Calculate risk per share
            if entry_price <= 0 or stop_loss_price <= 0:
                result["warnings"].append("Invalid entry or stop loss price")
                return result

            risk_per_share = abs(entry_price - stop_loss_price)
            if risk_per_share <= 0:
                result["warnings"].append(
                    "No risk difference between entry and stop loss"
                )
                return result

            # Position size based on risk
            risk_based_quantity = max_risk_amount / risk_per_share
            risk_based_notional = risk_based_quantity * entry_price

            # Position size based on portfolio allocation
            allocation_based_notional = max_portfolio_allocation
            allocation_based_quantity = allocation_based_notional / entry_price

            # Use the smaller of the two
            recommended_quantity = min(risk_based_quantity, allocation_based_quantity)
            recommended_notional = recommended_quantity * entry_price

            # Apply volatility adjustment
            if self.volatility_adjustment:
                volatility = market_data.get("volatility", 0.02)
                volatility_factor = max(0.5, min(1.5, 1 / (1 + volatility * 10)))
                recommended_quantity *= volatility_factor
                recommended_notional = recommended_quantity * entry_price
                result["adjustments"].append(
                    f"Volatility adjustment: {volatility_factor:.2f}"
                )

            # Apply correlation adjustment
            if self.correlation_adjustment:
                correlation = market_data.get("portfolio_correlation", 0.0)
                if correlation > 0.5:
                    correlation_factor = max(0.5, 1 - correlation * 0.5)
                    recommended_quantity *= correlation_factor
                    recommended_notional = recommended_quantity * entry_price
                    result["adjustments"].append(
                        f"Correlation adjustment: {correlation_factor:.2f}"
                    )

            # Calculate final metrics
            actual_risk_amount = recommended_quantity * risk_per_share
            position_pct = (recommended_notional / portfolio_value) * 100
            risk_pct = (actual_risk_amount / portfolio_value) * 100

            # Check limits
            if position_pct > self.max_position_pct:
                result["warnings"].append(
                    f"Position size exceeds limit ({position_pct:.2f}% > {self.max_position_pct}%)"
                )

            if risk_pct > self.max_risk_per_trade:
                result["warnings"].append(
                    f"Risk exceeds limit ({risk_pct:.2f}% > {self.max_risk_per_trade}%)"
                )

            result.update(
                {
                    "recommended_quantity": recommended_quantity,
                    "recommended_notional": recommended_notional,
                    "risk_amount": actual_risk_amount,
                    "position_pct": position_pct,
                    "risk_pct": risk_pct,
                }
            )

            return result

        except Exception as e:
            return {"error": str(e), "recommended_quantity": 0.0}


class CorrelationAnalyzer:
    """Analyzes correlations between positions."""

    def __init__(self):
        self.price_history = {}  # symbol -> list of prices
        self.correlation_matrix = {}
        self.last_update = None

    def add_price_data(self, symbol: str, price: float):
        """Add price data for correlation calculation."""
        try:
            if symbol not in self.price_history:
                self.price_history[symbol] = []

            self.price_history[symbol].append(
                {"price": price, "timestamp": datetime.now()}
            )

            # Keep only last 100 data points
            if len(self.price_history[symbol]) > 100:
                self.price_history[symbol] = self.price_history[symbol][-100:]

        except Exception as e:
            print(f"Error adding price data: {e}")

    def calculate_correlation_matrix(self) -> Dict[str, Dict[str, float]]:
        """Calculate correlation matrix between symbols."""
        try:
            symbols = list(self.price_history.keys())
            matrix = {}

            for symbol1 in symbols:
                matrix[symbol1] = {}

                for symbol2 in symbols:
                    if symbol1 == symbol2:
                        matrix[symbol1][symbol2] = 1.0
                    else:
                        correlation = self._calculate_correlation(symbol1, symbol2)
                        matrix[symbol1][symbol2] = correlation

            self.correlation_matrix = matrix
            self.last_update = datetime.now()
            return matrix

        except Exception as e:
            print(f"Error calculating correlation matrix: {e}")
            return {}

    def _calculate_correlation(self, symbol1: str, symbol2: str) -> float:
        """Calculate correlation between two symbols."""
        try:
            history1 = self.price_history.get(symbol1, [])
            history2 = self.price_history.get(symbol2, [])

            if len(history1) < 20 or len(history2) < 20:
                return 0.0  # Not enough data

            # Get the most recent common data points
            min_length = min(len(history1), len(history2), 50)
            prices1 = [h["price"] for h in history1[-min_length:]]
            prices2 = [h["price"] for h in history2[-min_length:]]

            # Calculate returns
            returns1 = [
                (prices1[i] - prices1[i - 1]) / prices1[i - 1]
                for i in range(1, len(prices1))
            ]
            returns2 = [
                (prices2[i] - prices2[i - 1]) / prices2[i - 1]
                for i in range(1, len(prices2))
            ]

            if len(returns1) < 10 or len(returns2) < 10:
                return 0.0

            # Calculate correlation coefficient
            mean1 = statistics.mean(returns1)
            mean2 = statistics.mean(returns2)

            numerator = sum(
                (r1 - mean1) * (r2 - mean2) for r1, r2 in zip(returns1, returns2)
            )

            sum_sq1 = sum((r1 - mean1) ** 2 for r1 in returns1)
            sum_sq2 = sum((r2 - mean2) ** 2 for r2 in returns2)

            denominator = math.sqrt(sum_sq1 * sum_sq2)

            if denominator == 0:
                return 0.0

            correlation = numerator / denominator
            return max(-1.0, min(1.0, correlation))  # Clamp to [-1, 1]

        except Exception as e:
            print(f"Error calculating correlation: {e}")
            return 0.0

    def get_portfolio_correlation(self, positions: Dict[str, float]) -> float:
        """Calculate overall portfolio correlation."""
        try:
            if not positions or not self.correlation_matrix:
                return 0.0

            # Weight correlations by position sizes
            total_weight = sum(abs(size) for size in positions.values())
            if total_weight == 0:
                return 0.0

            weighted_correlation = 0.0
            total_pairs = 0

            symbols = list(positions.keys())
            for i, symbol1 in enumerate(symbols):
                for symbol2 in symbols[i + 1 :]:
                    if (
                        symbol1 in self.correlation_matrix
                        and symbol2 in self.correlation_matrix[symbol1]
                    ):
                        weight1 = abs(positions[symbol1]) / total_weight
                        weight2 = abs(positions[symbol2]) / total_weight
                        correlation = self.correlation_matrix[symbol1][symbol2]

                        weighted_correlation += correlation * weight1 * weight2
                        total_pairs += 1

            return weighted_correlation if total_pairs > 0 else 0.0

        except Exception as e:
            print(f"Error calculating portfolio correlation: {e}")
            return 0.0


class DrawdownMonitor:
    """Monitors portfolio drawdown and individual position drawdowns."""

    def __init__(self, config: Dict):
        self.max_portfolio_drawdown = float(
            config.get("max_portfolio_drawdown", 10.0)
        )  # %
        self.max_position_drawdown = float(
            config.get("max_position_drawdown", 15.0)
        )  # %
        self.portfolio_history = []
        self.position_history = {}
        self.peak_values = {}

    def update_portfolio_value(self, portfolio_value: float):
        """Update portfolio value for drawdown calculation."""
        try:
            timestamp = datetime.now()

            self.portfolio_history.append(
                {"value": portfolio_value, "timestamp": timestamp}
            )

            # Keep only last 1000 data points
            if len(self.portfolio_history) > 1000:
                self.portfolio_history = self.portfolio_history[-1000:]

            # Update peak value
            if (
                "portfolio" not in self.peak_values
                or portfolio_value > self.peak_values["portfolio"]["value"]
            ):
                self.peak_values["portfolio"] = {
                    "value": portfolio_value,
                    "timestamp": timestamp,
                }

        except Exception as e:
            print(f"Error updating portfolio value: {e}")

    def update_position_value(self, symbol: str, position_value: float):
        """Update position value for drawdown calculation."""
        try:
            timestamp = datetime.now()

            if symbol not in self.position_history:
                self.position_history[symbol] = []

            self.position_history[symbol].append(
                {"value": position_value, "timestamp": timestamp}
            )

            # Keep only last 500 data points per position
            if len(self.position_history[symbol]) > 500:
                self.position_history[symbol] = self.position_history[symbol][-500:]

            # Update peak value
            peak_key = f"position_{symbol}"
            if (
                peak_key not in self.peak_values
                or position_value > self.peak_values[peak_key]["value"]
            ):
                self.peak_values[peak_key] = {
                    "value": position_value,
                    "timestamp": timestamp,
                }

        except Exception as e:
            print(f"Error updating position value: {e}")

    def calculate_portfolio_drawdown(self) -> Dict[str, Any]:
        """Calculate current portfolio drawdown."""
        try:
            if not self.portfolio_history or "portfolio" not in self.peak_values:
                return {"current_drawdown": 0.0, "max_drawdown": 0.0, "warning": False}

            current_value = self.portfolio_history[-1]["value"]
            peak_value = self.peak_values["portfolio"]["value"]

            if peak_value <= 0:
                return {"current_drawdown": 0.0, "max_drawdown": 0.0, "warning": False}

            current_drawdown = ((peak_value - current_value) / peak_value) * 100

            # Calculate maximum drawdown over period
            max_drawdown = 0.0
            local_peak = self.portfolio_history[0]["value"]

            for data_point in self.portfolio_history:
                value = data_point["value"]
                if value > local_peak:
                    local_peak = value
                else:
                    drawdown = ((local_peak - value) / local_peak) * 100
                    max_drawdown = max(max_drawdown, drawdown)

            warning = current_drawdown > self.max_portfolio_drawdown

            return {
                "current_drawdown": current_drawdown,
                "max_drawdown": max_drawdown,
                "peak_value": peak_value,
                "current_value": current_value,
                "warning": warning,
                "limit": self.max_portfolio_drawdown,
            }

        except Exception as e:
            print(f"Error calculating portfolio drawdown: {e}")
            return {"current_drawdown": 0.0, "max_drawdown": 0.0, "warning": False}

    def calculate_position_drawdown(self, symbol: str) -> Dict[str, Any]:
        """Calculate current position drawdown."""
        try:
            peak_key = f"position_{symbol}"

            if symbol not in self.position_history or peak_key not in self.peak_values:
                return {"current_drawdown": 0.0, "max_drawdown": 0.0, "warning": False}

            history = self.position_history[symbol]
            if not history:
                return {"current_drawdown": 0.0, "max_drawdown": 0.0, "warning": False}

            current_value = history[-1]["value"]
            peak_value = self.peak_values[peak_key]["value"]

            if peak_value <= 0:
                return {"current_drawdown": 0.0, "max_drawdown": 0.0, "warning": False}

            current_drawdown = ((peak_value - current_value) / peak_value) * 100

            # Calculate maximum drawdown for this position
            max_drawdown = 0.0
            local_peak = history[0]["value"]

            for data_point in history:
                value = data_point["value"]
                if value > local_peak:
                    local_peak = value
                else:
                    drawdown = ((local_peak - value) / local_peak) * 100
                    max_drawdown = max(max_drawdown, drawdown)

            warning = current_drawdown > self.max_position_drawdown

            return {
                "current_drawdown": current_drawdown,
                "max_drawdown": max_drawdown,
                "peak_value": peak_value,
                "current_value": current_value,
                "warning": warning,
                "limit": self.max_position_drawdown,
            }

        except Exception as e:
            print(f"Error calculating position drawdown: {e}")
            return {"current_drawdown": 0.0, "max_drawdown": 0.0, "warning": False}


class RiskEngine:
    """Main risk management engine."""

    def __init__(self, config: Dict = None, db_path: Optional[str] = None):
        if config is None:
            config = {}

        self.db = OrderManagementDB(db_path) if RISK_MANAGEMENT_AVAILABLE else None

        # Initialize components
        self.position_sizer = PositionSizer(config.get("position_sizing", {}))
        self.correlation_analyzer = CorrelationAnalyzer()
        self.drawdown_monitor = DrawdownMonitor(config.get("drawdown", {}))

        # Risk limits
        self.risk_limits = []
        self.active_alerts = {}
        self.alert_history = []

        # Configuration
        self.auto_close_on_drawdown = config.get("auto_close_on_drawdown", True)
        self.auto_reduce_on_correlation = config.get("auto_reduce_on_correlation", True)
        self.notification_enabled = config.get("notifications", True)

        # Load default risk limits
        self._setup_default_limits()

    def _setup_default_limits(self):
        """Setup default risk limits."""
        default_limits = [
            RiskLimit(
                name="Max Position Size",
                risk_type=RiskType.POSITION_SIZE,
                limit_value=10.0,  # 10% of portfolio
                warning_threshold=8.0,
            ),
            RiskLimit(
                name="Portfolio Concentration",
                risk_type=RiskType.PORTFOLIO_CONCENTRATION,
                limit_value=25.0,  # 25% in any single asset
                warning_threshold=20.0,
            ),
            RiskLimit(
                name="Portfolio Correlation",
                risk_type=RiskType.CORRELATION,
                limit_value=0.8,  # 80% correlation limit
                warning_threshold=0.6,
            ),
            RiskLimit(
                name="Portfolio Drawdown",
                risk_type=RiskType.DRAWDOWN,
                limit_value=15.0,  # 15% maximum drawdown
                warning_threshold=10.0,
            ),
            RiskLimit(
                name="Volatility Limit",
                risk_type=RiskType.VOLATILITY,
                limit_value=0.05,  # 5% daily volatility
                warning_threshold=0.04,
            ),
        ]

        self.risk_limits.extend(default_limits)

    def add_risk_limit(self, risk_limit: RiskLimit) -> bool:
        """Add a new risk limit."""
        try:
            self.risk_limits.append(risk_limit)
            return True
        except Exception as e:
            print(f"Error adding risk limit: {e}")
            return False

    def validate_order(self, order_data: Dict, portfolio_data: Dict) -> Dict[str, Any]:
        """Validate an order against risk limits."""
        try:
            result = {
                "approved": True,
                "warnings": [],
                "violations": [],
                "suggested_modifications": {},
                "risk_score": 0.0,
            }

            symbol = order_data.get("symbol", "")
            side = order_data.get("side", "BUY")
            quantity = float(order_data.get("quantity", 0))
            price = float(order_data.get("price", 0))

            if not symbol or quantity <= 0 or price <= 0:
                result["approved"] = False
                result["violations"].append("Invalid order parameters")
                return result

            # Calculate order value
            order_value = quantity * price
            portfolio_value = portfolio_data.get("total_value", 0)

            if portfolio_value <= 0:
                result["warnings"].append("Invalid portfolio value")
                return result

            # Check position size limits
            position_check = self._check_position_size(
                order_data, portfolio_data, order_value
            )
            result["warnings"].extend(position_check["warnings"])
            result["violations"].extend(position_check["violations"])
            result["risk_score"] += position_check["risk_score"]

            # Check concentration limits
            concentration_check = self._check_concentration(
                symbol, order_value, portfolio_data
            )
            result["warnings"].extend(concentration_check["warnings"])
            result["violations"].extend(concentration_check["violations"])
            result["risk_score"] += concentration_check["risk_score"]

            # Check correlation limits
            correlation_check = self._check_correlation(
                symbol, order_value, portfolio_data
            )
            result["warnings"].extend(correlation_check["warnings"])
            result["violations"].extend(correlation_check["violations"])
            result["risk_score"] += correlation_check["risk_score"]

            # Check drawdown limits
            drawdown_check = self._check_drawdown_risk(order_data, portfolio_data)
            result["warnings"].extend(drawdown_check["warnings"])
            result["violations"].extend(drawdown_check["violations"])
            result["risk_score"] += drawdown_check["risk_score"]

            # Determine overall approval
            if result["violations"]:
                result["approved"] = False
            elif result["risk_score"] > 0.7:  # High risk threshold
                result["approved"] = False
                result["violations"].append("Overall risk score too high")

            # Suggest position size adjustment if needed
            if not result["approved"] and "position_size" in str(result["violations"]):
                suggested_size = self._suggest_position_adjustment(
                    order_data, portfolio_data
                )
                if suggested_size:
                    result["suggested_modifications"]["quantity"] = suggested_size

            return result

        except Exception as e:
            return {
                "approved": False,
                "error": str(e),
                "warnings": [],
                "violations": [f"Risk validation error: {str(e)}"],
                "risk_score": 1.0,
            }

    def _check_position_size(
        self, order_data: Dict, portfolio_data: Dict, order_value: float
    ) -> Dict:
        """Check position size against limits."""
        result = {"warnings": [], "violations": [], "risk_score": 0.0}

        try:
            portfolio_value = portfolio_data.get("total_value", 0)
            position_pct = (order_value / portfolio_value) * 100

            for limit in self.risk_limits:
                if limit.risk_type == RiskType.POSITION_SIZE and limit.enabled:
                    if position_pct > limit.limit_value:
                        result["violations"].append(
                            f"Position size {position_pct:.1f}% exceeds limit {limit.limit_value:.1f}%"
                        )
                        result["risk_score"] = max(result["risk_score"], 0.8)
                    elif position_pct > limit.warning_threshold:
                        result["warnings"].append(
                            f"Position size {position_pct:.1f}% above warning threshold {limit.warning_threshold:.1f}%"
                        )
                        result["risk_score"] = max(result["risk_score"], 0.4)

        except Exception as e:
            result["violations"].append(f"Position size check error: {e}")

        return result

    def _check_concentration(
        self, symbol: str, order_value: float, portfolio_data: Dict
    ) -> Dict:
        """Check portfolio concentration limits."""
        result = {"warnings": [], "violations": [], "risk_score": 0.0}

        try:
            portfolio_value = portfolio_data.get("total_value", 0)
            current_positions = portfolio_data.get("positions", {})

            # Calculate new concentration
            current_symbol_value = current_positions.get(symbol, {}).get("value", 0)
            new_symbol_value = current_symbol_value + order_value
            concentration_pct = (new_symbol_value / portfolio_value) * 100

            for limit in self.risk_limits:
                if (
                    limit.risk_type == RiskType.PORTFOLIO_CONCENTRATION
                    and limit.enabled
                ):
                    if concentration_pct > limit.limit_value:
                        result["violations"].append(
                            f"Portfolio concentration in {symbol} {concentration_pct:.1f}% exceeds limit {limit.limit_value:.1f}%"
                        )
                        result["risk_score"] = max(result["risk_score"], 0.7)
                    elif concentration_pct > limit.warning_threshold:
                        result["warnings"].append(
                            f"Portfolio concentration in {symbol} {concentration_pct:.1f}% above warning threshold"
                        )
                        result["risk_score"] = max(result["risk_score"], 0.3)

        except Exception as e:
            result["violations"].append(f"Concentration check error: {e}")

        return result

    def _check_correlation(
        self, symbol: str, order_value: float, portfolio_data: Dict
    ) -> Dict:
        """Check correlation limits."""
        result = {"warnings": [], "violations": [], "risk_score": 0.0}

        try:
            current_positions = portfolio_data.get("positions", {})

            # Simulate new portfolio with this order
            new_positions = current_positions.copy()
            if symbol in new_positions:
                new_positions[symbol]["value"] += order_value
            else:
                new_positions[symbol] = {"value": order_value}

            # Calculate portfolio correlation
            position_values = {sym: pos["value"] for sym, pos in new_positions.items()}
            portfolio_correlation = self.correlation_analyzer.get_portfolio_correlation(
                position_values
            )

            for limit in self.risk_limits:
                if limit.risk_type == RiskType.CORRELATION and limit.enabled:
                    if portfolio_correlation > limit.limit_value:
                        result["violations"].append(
                            f"Portfolio correlation {portfolio_correlation:.2f} exceeds limit {limit.limit_value:.2f}"
                        )
                        result["risk_score"] = max(result["risk_score"], 0.6)
                    elif portfolio_correlation > limit.warning_threshold:
                        result["warnings"].append(
                            f"Portfolio correlation {portfolio_correlation:.2f} above warning threshold"
                        )
                        result["risk_score"] = max(result["risk_score"], 0.3)

        except Exception as e:
            result["warnings"].append(f"Correlation check error: {e}")

        return result

    def _check_drawdown_risk(self, order_data: Dict, portfolio_data: Dict) -> Dict:
        """Check drawdown risk."""
        result = {"warnings": [], "violations": [], "risk_score": 0.0}

        try:
            # Check current portfolio drawdown
            drawdown_info = self.drawdown_monitor.calculate_portfolio_drawdown()
            current_drawdown = drawdown_info.get("current_drawdown", 0)

            for limit in self.risk_limits:
                if limit.risk_type == RiskType.DRAWDOWN and limit.enabled:
                    if current_drawdown > limit.limit_value:
                        result["violations"].append(
                            f"Portfolio drawdown {current_drawdown:.1f}% exceeds limit {limit.limit_value:.1f}%"
                        )
                        result["risk_score"] = max(result["risk_score"], 0.9)
                    elif current_drawdown > limit.warning_threshold:
                        result["warnings"].append(
                            f"Portfolio drawdown {current_drawdown:.1f}% above warning threshold"
                        )
                        result["risk_score"] = max(result["risk_score"], 0.5)

        except Exception as e:
            result["warnings"].append(f"Drawdown check error: {e}")

        return result

    def _suggest_position_adjustment(
        self, order_data: Dict, portfolio_data: Dict
    ) -> Optional[float]:
        """Suggest position size adjustment."""
        try:
            symbol = order_data.get("symbol", "")
            entry_price = float(order_data.get("price", 0))
            stop_loss = order_data.get("stop_loss_price")

            if not stop_loss:
                return None

            stop_loss_price = float(stop_loss)
            portfolio_value = portfolio_data.get("total_value", 0)

            # Use position sizer to calculate optimal size
            sizing_result = self.position_sizer.calculate_position_size(
                symbol, entry_price, stop_loss_price, portfolio_value
            )

            return sizing_result.get("recommended_quantity")

        except Exception as e:
            print(f"Error suggesting position adjustment: {e}")
            return None

    def monitor_portfolio_risk(self, portfolio_data: Dict) -> List[RiskAlert]:
        """Monitor portfolio for risk violations."""
        new_alerts = []

        try:
            current_time = datetime.now()

            # Update correlation data
            positions = portfolio_data.get("positions", {})
            for symbol, position in positions.items():
                price = position.get("current_price", 0)
                if price > 0:
                    self.correlation_analyzer.add_price_data(symbol, price)

            # Update drawdown data
            portfolio_value = portfolio_data.get("total_value", 0)
            if portfolio_value > 0:
                self.drawdown_monitor.update_portfolio_value(portfolio_value)

                for symbol, position in positions.items():
                    position_value = position.get("value", 0)
                    self.drawdown_monitor.update_position_value(symbol, position_value)

            # Check all risk limits
            for limit in self.risk_limits:
                if not limit.enabled:
                    continue

                alert = self._check_risk_limit(limit, portfolio_data)
                if alert:
                    alert_id = f"{limit.name}_{int(current_time.timestamp())}"

                    # Avoid duplicate alerts
                    if alert_id not in self.active_alerts:
                        alert.id = alert_id
                        self.active_alerts[alert_id] = alert
                        self.alert_history.append(alert)
                        new_alerts.append(alert)

            # Clean up old alerts
            self._cleanup_old_alerts()

        except Exception as e:
            print(f"Error monitoring portfolio risk: {e}")

        return new_alerts

    def _check_risk_limit(
        self, limit: RiskLimit, portfolio_data: Dict
    ) -> Optional[RiskAlert]:
        """Check a specific risk limit."""
        try:
            if limit.risk_type == RiskType.PORTFOLIO_CONCENTRATION:
                return self._check_concentration_alert(limit, portfolio_data)
            elif limit.risk_type == RiskType.CORRELATION:
                return self._check_correlation_alert(limit, portfolio_data)
            elif limit.risk_type == RiskType.DRAWDOWN:
                return self._check_drawdown_alert(limit, portfolio_data)
            # Add more risk type checks as needed

            return None

        except Exception as e:
            print(f"Error checking risk limit: {e}")
            return None

    def _check_concentration_alert(
        self, limit: RiskLimit, portfolio_data: Dict
    ) -> Optional[RiskAlert]:
        """Check for concentration violations."""
        try:
            portfolio_value = portfolio_data.get("total_value", 0)
            positions = portfolio_data.get("positions", {})

            for symbol, position in positions.items():
                position_value = position.get("value", 0)
                concentration = (
                    (position_value / portfolio_value) * 100
                    if portfolio_value > 0
                    else 0
                )

                if concentration > limit.limit_value:
                    return RiskAlert(
                        id="",  # Will be set by caller
                        alert_type=AlertType.PORTFOLIO_RISK,
                        risk_level=RiskLevel.HIGH,
                        symbol=symbol,
                        message=f"Concentration in {symbol} exceeds limit: {concentration:.1f}% > {limit.limit_value:.1f}%",
                        current_value=concentration,
                        limit_value=limit.limit_value,
                        triggered_at=datetime.now(),
                    )

            return None

        except Exception as e:
            print(f"Error checking concentration alert: {e}")
            return None

    def _check_correlation_alert(
        self, limit: RiskLimit, portfolio_data: Dict
    ) -> Optional[RiskAlert]:
        """Check for correlation violations."""
        try:
            positions = portfolio_data.get("positions", {})
            position_values = {
                sym: pos.get("value", 0) for sym, pos in positions.items()
            }

            correlation = self.correlation_analyzer.get_portfolio_correlation(
                position_values
            )

            if correlation > limit.limit_value:
                return RiskAlert(
                    id="",
                    alert_type=AlertType.CORRELATION_WARNING,
                    risk_level=RiskLevel.MEDIUM,
                    symbol="PORTFOLIO",
                    message=f"Portfolio correlation exceeds limit: {correlation:.2f} > {limit.limit_value:.2f}",
                    current_value=correlation,
                    limit_value=limit.limit_value,
                    triggered_at=datetime.now(),
                )

            return None

        except Exception as e:
            print(f"Error checking correlation alert: {e}")
            return None

    def _check_drawdown_alert(
        self, limit: RiskLimit, portfolio_data: Dict
    ) -> Optional[RiskAlert]:
        """Check for drawdown violations."""
        try:
            drawdown_info = self.drawdown_monitor.calculate_portfolio_drawdown()
            current_drawdown = drawdown_info.get("current_drawdown", 0)

            if current_drawdown > limit.limit_value:
                risk_level = (
                    RiskLevel.CRITICAL
                    if current_drawdown > limit.limit_value * 1.2
                    else RiskLevel.HIGH
                )

                return RiskAlert(
                    id="",
                    alert_type=AlertType.DRAWDOWN_LIMIT,
                    risk_level=risk_level,
                    symbol="PORTFOLIO",
                    message=f"Portfolio drawdown exceeds limit: {current_drawdown:.1f}% > {limit.limit_value:.1f}%",
                    current_value=current_drawdown,
                    limit_value=limit.limit_value,
                    triggered_at=datetime.now(),
                )

            return None

        except Exception as e:
            print(f"Error checking drawdown alert: {e}")
            return None

    def _cleanup_old_alerts(self):
        """Remove old alerts."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=24)

            # Remove old active alerts
            to_remove = []
            for alert_id, alert in self.active_alerts.items():
                if alert.triggered_at < cutoff_time or alert.resolved:
                    to_remove.append(alert_id)

            for alert_id in to_remove:
                del self.active_alerts[alert_id]

            # Keep only last 1000 alerts in history
            if len(self.alert_history) > 1000:
                self.alert_history = self.alert_history[-1000:]

        except Exception as e:
            print(f"Error cleaning up alerts: {e}")

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge a risk alert."""
        try:
            if alert_id in self.active_alerts:
                self.active_alerts[alert_id].acknowledged = True
                return True
            return False
        except Exception as e:
            print(f"Error acknowledging alert: {e}")
            return False

    def resolve_alert(self, alert_id: str) -> bool:
        """Mark a risk alert as resolved."""
        try:
            if alert_id in self.active_alerts:
                self.active_alerts[alert_id].resolved = True
                return True
            return False
        except Exception as e:
            print(f"Error resolving alert: {e}")
            return False

    def get_risk_summary(self, portfolio_data: Dict) -> Dict[str, Any]:
        """Get comprehensive risk summary."""
        try:
            # Calculate various risk metrics
            portfolio_value = portfolio_data.get("total_value", 0)
            positions = portfolio_data.get("positions", {})

            # Concentration metrics
            concentrations = {}
            if portfolio_value > 0:
                for symbol, position in positions.items():
                    concentration = (position.get("value", 0) / portfolio_value) * 100
                    concentrations[symbol] = concentration

            # Correlation metrics
            position_values = {
                sym: pos.get("value", 0) for sym, pos in positions.items()
            }
            portfolio_correlation = self.correlation_analyzer.get_portfolio_correlation(
                position_values
            )

            # Drawdown metrics
            drawdown_info = self.drawdown_monitor.calculate_portfolio_drawdown()

            # Risk score calculation
            risk_score = self._calculate_overall_risk_score(portfolio_data)

            summary = {
                "timestamp": datetime.now(),
                "portfolio_value": portfolio_value,
                "overall_risk_score": risk_score,
                "risk_level": self._get_risk_level(risk_score),
                "concentrations": concentrations,
                "portfolio_correlation": portfolio_correlation,
                "drawdown": drawdown_info,
                "active_alerts": len(self.active_alerts),
                "active_alert_details": list(self.active_alerts.values()),
                "risk_limits": len([l for l in self.risk_limits if l.enabled]),
                "recommendations": self._generate_recommendations(portfolio_data),
            }

            return summary

        except Exception as e:
            return {"error": str(e)}

    def _calculate_overall_risk_score(self, portfolio_data: Dict) -> float:
        """Calculate overall portfolio risk score (0-1)."""
        try:
            risk_components = []

            # Concentration component
            concentrations = []
            portfolio_value = portfolio_data.get("total_value", 0)
            positions = portfolio_data.get("positions", {})

            if portfolio_value > 0:
                for position in positions.values():
                    concentration = (position.get("value", 0) / portfolio_value) * 100
                    concentrations.append(concentration)

            if concentrations:
                max_concentration = max(concentrations)
                concentration_risk = min(
                    1.0, max_concentration / 25.0
                )  # 25% = max acceptable
                risk_components.append(concentration_risk)

            # Correlation component
            position_values = {
                sym: pos.get("value", 0) for sym, pos in positions.items()
            }
            correlation = self.correlation_analyzer.get_portfolio_correlation(
                position_values
            )
            correlation_risk = (
                max(0.0, correlation - 0.3) / 0.7
            )  # 0.3 baseline, 1.0 max
            risk_components.append(correlation_risk)

            # Drawdown component
            drawdown_info = self.drawdown_monitor.calculate_portfolio_drawdown()
            drawdown = drawdown_info.get("current_drawdown", 0)
            drawdown_risk = min(1.0, drawdown / 20.0)  # 20% = critical level
            risk_components.append(drawdown_risk)

            # Overall score is weighted average
            if risk_components:
                return sum(risk_components) / len(risk_components)
            else:
                return 0.0

        except Exception as e:
            print(f"Error calculating risk score: {e}")
            return 0.5

    def _get_risk_level(self, risk_score: float) -> RiskLevel:
        """Convert risk score to risk level."""
        if risk_score < 0.25:
            return RiskLevel.LOW
        elif risk_score < 0.5:
            return RiskLevel.MEDIUM
        elif risk_score < 0.75:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    def _generate_recommendations(self, portfolio_data: Dict) -> List[str]:
        """Generate risk management recommendations."""
        recommendations = []

        try:
            # Check concentration
            portfolio_value = portfolio_data.get("total_value", 0)
            positions = portfolio_data.get("positions", {})

            if portfolio_value > 0:
                for symbol, position in positions.items():
                    concentration = (position.get("value", 0) / portfolio_value) * 100
                    if concentration > 20:
                        recommendations.append(
                            f"Consider reducing {symbol} position (currently {concentration:.1f}%)"
                        )

            # Check correlation
            position_values = {
                sym: pos.get("value", 0) for sym, pos in positions.items()
            }
            correlation = self.correlation_analyzer.get_portfolio_correlation(
                position_values
            )
            if correlation > 0.6:
                recommendations.append(
                    "Portfolio shows high correlation - consider diversifying"
                )

            # Check drawdown
            drawdown_info = self.drawdown_monitor.calculate_portfolio_drawdown()
            current_drawdown = drawdown_info.get("current_drawdown", 0)
            if current_drawdown > 10:
                recommendations.append(
                    "High portfolio drawdown - consider risk reduction"
                )

            # Check active alerts
            if len(self.active_alerts) > 3:
                recommendations.append(
                    "Multiple active risk alerts - review portfolio immediately"
                )

            return recommendations

        except Exception as e:
            print(f"Error generating recommendations: {e}")
            return ["Error generating recommendations"]


# Global risk engine
_risk_engine = None


def get_risk_engine(config: Dict = None, db_path: Optional[str] = None) -> RiskEngine:
    """Get the global risk engine instance."""
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = RiskEngine(config, db_path)
    return _risk_engine


if __name__ == "__main__":
    # Test the risk management engine
    engine = get_risk_engine()

    print("Risk Management Engine Test")
    print("=" * 40)

    # Mock portfolio data
    portfolio_data = {
        "total_value": 100000,
        "positions": {
            "BTCUSDT": {"value": 30000, "current_price": 45000},
            "ETHUSDT": {"value": 25000, "current_price": 3000},
            "ADAUSDT": {"value": 10000, "current_price": 0.5},
        },
    }

    # Test order validation
    order_data = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "quantity": 1.0,
        "price": 45000,
        "stop_loss_price": 42000,
    }

    validation_result = engine.validate_order(order_data, portfolio_data)
    print(f"Order Validation: {validation_result}")

    # Monitor portfolio risk
    alerts = engine.monitor_portfolio_risk(portfolio_data)
    print(f"Risk Alerts: {alerts}")

    # Get risk summary
    summary = engine.get_risk_summary(portfolio_data)
    print(f"Risk Summary: {summary}")
