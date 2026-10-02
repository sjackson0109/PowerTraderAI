"""
Advanced Risk Management System (Item 25)
Portfolio-wide risk controls including position sizing, exposure limits,
correlation analysis, drawdown protection, and automated risk alerts
"""

import json
import logging
import math
import sqlite3
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("Warning: NumPy not available. Limited risk calculations.")

try:
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("Warning: Pandas not available. Limited data analysis.")

try:
    from scipy import stats
    from scipy.stats import norm

    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("Warning: SciPy not available. Advanced risk metrics disabled.")


class RiskLevel(Enum):
    """Risk severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskType(Enum):
    """Types of risk"""

    POSITION_SIZE = "position_size"
    PORTFOLIO_EXPOSURE = "portfolio_exposure"
    CORRELATION = "correlation"
    DRAWDOWN = "drawdown"
    VOLATILITY = "volatility"
    LIQUIDITY = "liquidity"
    CONCENTRATION = "concentration"
    LEVERAGE = "leverage"
    VAR = "value_at_risk"
    MARGIN = "margin"


class AlertStatus(Enum):
    """Alert status"""

    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


@dataclass
class RiskMetric:
    """Individual risk metric"""

    name: str
    value: float
    threshold: float
    risk_type: RiskType
    risk_level: RiskLevel
    description: str
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_breached(self) -> bool:
        """Check if risk threshold is breached"""
        return self.value > self.threshold

    @property
    def breach_severity(self) -> float:
        """Calculate breach severity as percentage over threshold"""
        if self.threshold == 0:
            return 0.0
        return max(0.0, (self.value - self.threshold) / self.threshold * 100)


@dataclass
class RiskAlert:
    """Risk alert"""

    id: str
    alert_type: RiskType
    level: RiskLevel
    message: str
    metric_value: float
    threshold: float
    symbol: Optional[str] = None
    action_required: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    status: AlertStatus = AlertStatus.PENDING
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    def acknowledge(self):
        """Acknowledge the alert"""
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.now()

    def resolve(self):
        """Mark alert as resolved"""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.now()

    def dismiss(self):
        """Dismiss the alert"""
        self.status = AlertStatus.DISMISSED
        self.acknowledged_at = datetime.now()


@dataclass
class Position:
    """Trading position"""

    symbol: str
    side: str  # 'long' or 'short'
    quantity: float
    entry_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    margin_used: float = 0.0
    leverage: float = 1.0
    entry_time: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)

    @property
    def notional_value(self) -> float:
        """Calculate notional value"""
        return abs(self.quantity * self.current_price)

    @property
    def pnl_percent(self) -> float:
        """Calculate P&L percentage"""
        if self.market_value == 0:
            return 0.0
        return (self.unrealized_pnl / abs(self.market_value)) * 100

    @property
    def is_profitable(self) -> bool:
        """Check if position is profitable"""
        return self.unrealized_pnl > 0


class RiskLimits:
    """Risk limits configuration"""

    def __init__(self):
        # Position limits
        self.max_position_size_usd = 50000.0
        self.max_position_size_percent = 20.0  # % of portfolio
        self.max_single_asset_exposure = 25.0  # % of portfolio
        self.max_sector_exposure = 40.0  # % of portfolio

        # Portfolio limits
        self.max_portfolio_drawdown = 15.0  # %
        self.max_daily_loss_usd = 5000.0
        self.max_daily_loss_percent = 5.0  # % of portfolio
        self.max_leverage = 3.0
        self.min_liquidity_ratio = 0.1  # 10% cash minimum

        # Risk metrics limits
        self.max_portfolio_var_95 = 10.0  # % (95% confidence)
        self.max_portfolio_var_99 = 15.0  # % (99% confidence)
        self.max_correlation_concentration = 0.8
        self.max_volatility_threshold = 50.0  # % annualized

        # Alert thresholds
        self.warning_drawdown = 8.0  # %
        self.critical_drawdown = 12.0  # %
        self.warning_correlation = 0.6
        self.critical_correlation = 0.8

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary"""
        return {
            "max_position_size_usd": self.max_position_size_usd,
            "max_position_size_percent": self.max_position_size_percent,
            "max_single_asset_exposure": self.max_single_asset_exposure,
            "max_sector_exposure": self.max_sector_exposure,
            "max_portfolio_drawdown": self.max_portfolio_drawdown,
            "max_daily_loss_usd": self.max_daily_loss_usd,
            "max_daily_loss_percent": self.max_daily_loss_percent,
            "max_leverage": self.max_leverage,
            "min_liquidity_ratio": self.min_liquidity_ratio,
            "max_portfolio_var_95": self.max_portfolio_var_95,
            "max_portfolio_var_99": self.max_portfolio_var_99,
            "max_correlation_concentration": self.max_correlation_concentration,
            "max_volatility_threshold": self.max_volatility_threshold,
            "warning_drawdown": self.warning_drawdown,
            "critical_drawdown": self.critical_drawdown,
            "warning_correlation": self.warning_correlation,
            "critical_correlation": self.critical_correlation,
        }

    def from_dict(self, data: Dict[str, float]):
        """Load from dictionary"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)


class PortfolioRiskCalculator:
    """Calculate portfolio risk metrics"""

    def __init__(self):
        self.price_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=252)
        )  # 1 year
        self.returns_cache: Dict[str, List[float]] = {}
        self.correlation_cache: Dict[Tuple[str, str], float] = {}
        self.volatility_cache: Dict[str, float] = {}
        self.cache_ttl = 300  # 5 minutes
        self.last_cache_update = {}

    def add_price_data(self, symbol: str, price: float, timestamp: datetime = None):
        """Add price data for risk calculations"""
        if timestamp is None:
            timestamp = datetime.now()

        self.price_history[symbol].append({"price": price, "timestamp": timestamp})

        # Clear cached calculations for this symbol
        self._clear_symbol_cache(symbol)

    def _clear_symbol_cache(self, symbol: str):
        """Clear cached calculations for a symbol"""
        if symbol in self.returns_cache:
            del self.returns_cache[symbol]

        if symbol in self.volatility_cache:
            del self.volatility_cache[symbol]

        # Clear correlation cache entries involving this symbol
        keys_to_remove = [k for k in self.correlation_cache.keys() if symbol in k]
        for key in keys_to_remove:
            del self.correlation_cache[key]

    def calculate_returns(self, symbol: str, periods: int = 30) -> List[float]:
        """Calculate historical returns for a symbol"""
        cache_key = f"{symbol}_{periods}"

        # Check cache
        if (
            cache_key in self.returns_cache
            and symbol in self.last_cache_update
            and (datetime.now() - self.last_cache_update[symbol]).seconds
            < self.cache_ttl
        ):
            return self.returns_cache[cache_key]

        if symbol not in self.price_history or len(self.price_history[symbol]) < 2:
            return []

        prices = [p["price"] for p in list(self.price_history[symbol])[-periods - 1 :]]

        if len(prices) < 2:
            return []

        returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0:
                ret = (prices[i] - prices[i - 1]) / prices[i - 1]
                returns.append(ret)

        # Cache result
        self.returns_cache[cache_key] = returns
        self.last_cache_update[symbol] = datetime.now()

        return returns

    def calculate_volatility(
        self, symbol: str, periods: int = 30, annualized: bool = True
    ) -> float:
        """Calculate volatility for a symbol"""
        cache_key = f"{symbol}_vol_{periods}"

        # Check cache
        if (
            cache_key in self.volatility_cache
            and symbol in self.last_cache_update
            and (datetime.now() - self.last_cache_update[symbol]).seconds
            < self.cache_ttl
        ):
            return self.volatility_cache[cache_key]

        returns = self.calculate_returns(symbol, periods)

        if len(returns) < 5:  # Need at least 5 data points
            return 0.0

        if not NUMPY_AVAILABLE:
            # Simple standard deviation calculation
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
            volatility = math.sqrt(variance)
        else:
            volatility = np.std(returns, ddof=1)

        # Annualize if requested (assuming daily returns)
        if annualized:
            volatility = volatility * math.sqrt(252)  # 252 trading days

        # Cache result
        self.volatility_cache[cache_key] = volatility

        return volatility

    def calculate_correlation(
        self, symbol1: str, symbol2: str, periods: int = 30
    ) -> float:
        """Calculate correlation between two symbols"""
        cache_key = (symbol1, symbol2) if symbol1 < symbol2 else (symbol2, symbol1)

        # Check cache
        if cache_key in self.correlation_cache:
            # Check if cache is still valid
            for symbol in [symbol1, symbol2]:
                if (
                    symbol in self.last_cache_update
                    and (datetime.now() - self.last_cache_update[symbol]).seconds
                    > self.cache_ttl
                ):
                    del self.correlation_cache[cache_key]
                    break
            else:
                return self.correlation_cache[cache_key]

        returns1 = self.calculate_returns(symbol1, periods)
        returns2 = self.calculate_returns(symbol2, periods)

        if len(returns1) < 5 or len(returns2) < 5:
            return 0.0

        # Align returns (same length)
        min_length = min(len(returns1), len(returns2))
        returns1 = returns1[-min_length:]
        returns2 = returns2[-min_length:]

        if not NUMPY_AVAILABLE:
            # Manual correlation calculation
            mean1 = sum(returns1) / len(returns1)
            mean2 = sum(returns2) / len(returns2)

            numerator = sum(
                (r1 - mean1) * (r2 - mean2) for r1, r2 in zip(returns1, returns2)
            )

            variance1 = sum((r1 - mean1) ** 2 for r1 in returns1)
            variance2 = sum((r2 - mean2) ** 2 for r2 in returns2)

            denominator = math.sqrt(variance1 * variance2)

            correlation = numerator / denominator if denominator != 0 else 0.0
        else:
            correlation = np.corrcoef(returns1, returns2)[0, 1]

            # Handle NaN
            if math.isnan(correlation):
                correlation = 0.0

        # Cache result
        self.correlation_cache[cache_key] = correlation

        return correlation

    def calculate_portfolio_var(
        self, positions: List[Position], confidence: float = 0.95, periods: int = 30
    ) -> float:
        """Calculate portfolio Value at Risk"""
        if not NUMPY_AVAILABLE or not SCIPY_AVAILABLE:
            return 0.0  # Can't calculate VaR without scipy

        if not positions:
            return 0.0

        # Get position weights and returns
        total_value = sum(abs(pos.market_value) for pos in positions)
        if total_value == 0:
            return 0.0

        symbols = list(set(pos.symbol for pos in positions))
        weights = {}

        # Calculate weights for each symbol
        for symbol in symbols:
            symbol_value = sum(
                pos.market_value for pos in positions if pos.symbol == symbol
            )
            weights[symbol] = symbol_value / total_value

        # Get returns matrix
        returns_matrix = []
        for symbol in symbols:
            symbol_returns = self.calculate_returns(symbol, periods)
            if len(symbol_returns) < 10:  # Need sufficient data
                return 0.0
            returns_matrix.append(symbol_returns)

        # Ensure all return series have same length
        min_length = min(len(returns) for returns in returns_matrix)
        if min_length < 10:
            return 0.0

        returns_matrix = [returns[-min_length:] for returns in returns_matrix]

        # Calculate portfolio returns
        portfolio_returns = []
        for i in range(min_length):
            portfolio_return = sum(
                weights[symbols[j]] * returns_matrix[j][i] for j in range(len(symbols))
            )
            portfolio_returns.append(portfolio_return)

        # Calculate VaR
        portfolio_returns = np.array(portfolio_returns)
        var_percentile = norm.ppf(1 - confidence)

        portfolio_mean = np.mean(portfolio_returns)
        portfolio_std = np.std(portfolio_returns, ddof=1)

        var = abs(portfolio_mean + var_percentile * portfolio_std) * total_value

        return var

    def calculate_drawdown(self, portfolio_values: List[Dict]) -> Tuple[float, float]:
        """Calculate current and maximum drawdown"""
        if len(portfolio_values) < 2:
            return 0.0, 0.0

        values = [pv["value"] for pv in portfolio_values]
        peak = values[0]
        max_drawdown = 0.0
        current_drawdown = 0.0

        for value in values:
            if value > peak:
                peak = value

            drawdown = (peak - value) / peak if peak > 0 else 0.0
            current_drawdown = drawdown
            max_drawdown = max(max_drawdown, drawdown)

        return current_drawdown * 100, max_drawdown * 100  # Convert to percentage


class RiskManager:
    """Main risk management system"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            import pt_paths

            db_path = pt_paths.data_file("risk_management.db")
        self.db_path = db_path
        self.limits = RiskLimits()
        self.calculator = PortfolioRiskCalculator()
        self.positions: Dict[str, Position] = {}
        self.alerts: Dict[str, RiskAlert] = {}
        self.alert_handlers: List[Callable] = []
        self.portfolio_history: deque = deque(maxlen=252)  # 1 year of daily values
        self.monitoring_active = True
        self.monitoring_thread = None

        self._setup_database()
        self._setup_logging()
        self.start_monitoring()

    def _setup_database(self):
        """Setup SQLite database for risk management"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Risk alerts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_alerts (
                id TEXT PRIMARY KEY,
                alert_type TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                metric_value REAL NOT NULL,
                threshold_value REAL NOT NULL,
                symbol TEXT,
                action_required TEXT,
                created_at DATETIME NOT NULL,
                status TEXT NOT NULL,
                acknowledged_at DATETIME,
                resolved_at DATETIME
            )
        """)

        # Risk metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                value REAL NOT NULL,
                threshold_value REAL NOT NULL,
                risk_type TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                description TEXT NOT NULL,
                symbol TEXT,
                timestamp DATETIME NOT NULL
            )
        """)

        # Portfolio history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL,
                total_value REAL NOT NULL,
                total_pnl REAL NOT NULL,
                total_margin REAL NOT NULL,
                drawdown REAL NOT NULL,
                var_95 REAL,
                var_99 REAL,
                num_positions INTEGER NOT NULL
            )
        """)

        # Risk limits configuration table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_limits (
                id INTEGER PRIMARY KEY,
                config_data TEXT NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """)

        # Create indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON risk_alerts(created_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON risk_metrics(timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_portfolio_timestamp ON portfolio_history(timestamp)"
        )

        conn.commit()
        conn.close()

        # Load risk limits from database
        self.load_risk_limits()

    def _setup_logging(self):
        """Setup logging for risk management"""
        self.logger = logging.getLogger("RiskManager")
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def load_risk_limits(self):
        """Load risk limits from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT config_data FROM risk_limits WHERE id = 1 ORDER BY updated_at DESC LIMIT 1"
            )
            result = cursor.fetchone()

            if result:
                config_data = json.loads(result[0])
                self.limits.from_dict(config_data)

            conn.close()
        except Exception as e:
            self.logger.error(f"Error loading risk limits: {e}")

    def save_risk_limits(self):
        """Save risk limits to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            config_data = json.dumps(self.limits.to_dict())

            cursor.execute(
                """
                INSERT OR REPLACE INTO risk_limits (id, config_data, updated_at)
                VALUES (1, ?, ?)
            """,
                (config_data, datetime.now()),
            )

            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Error saving risk limits: {e}")

    def add_alert_handler(self, handler: Callable):
        """Add alert handler callback"""
        self.alert_handlers.append(handler)

    def remove_alert_handler(self, handler: Callable):
        """Remove alert handler callback"""
        if handler in self.alert_handlers:
            self.alert_handlers.remove(handler)

    def update_position(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        current_price: float,
    ):
        """Update or add a position"""
        market_value = quantity * current_price

        if side.lower() == "long":
            unrealized_pnl = (current_price - entry_price) * quantity
        else:  # short
            unrealized_pnl = (entry_price - current_price) * quantity

        position = Position(
            symbol=symbol,
            side=side.lower(),
            quantity=quantity,
            entry_price=entry_price,
            current_price=current_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
        )

        self.positions[symbol] = position

        # Add price data for risk calculations
        self.calculator.add_price_data(symbol, current_price)

        # Check position-specific risks
        self._check_position_risks(position)

    def remove_position(self, symbol: str):
        """Remove a position"""
        if symbol in self.positions:
            del self.positions[symbol]

    def update_portfolio_value(
        self, total_value: float, total_pnl: float, total_margin: float = 0.0
    ):
        """Update portfolio value and trigger risk checks"""
        portfolio_data = {
            "timestamp": datetime.now(),
            "value": total_value,
            "pnl": total_pnl,
            "margin": total_margin,
            "num_positions": len(self.positions),
        }

        self.portfolio_history.append(portfolio_data)

        # Calculate current metrics
        current_drawdown, max_drawdown = self.calculator.calculate_drawdown(
            list(self.portfolio_history)
        )

        portfolio_data["drawdown"] = current_drawdown

        # Calculate VaR if we have positions
        if self.positions:
            var_95 = self.calculate_portfolio_var(0.95)
            var_99 = self.calculate_portfolio_var(0.99)

            portfolio_data["var_95"] = var_95
            portfolio_data["var_99"] = var_99

        # Store in database
        self._store_portfolio_history(portfolio_data)

        # Check portfolio-wide risks
        self._check_portfolio_risks()

    def calculate_portfolio_var(self, confidence: float) -> float:
        """Calculate portfolio VaR"""
        if not self.positions:
            return 0.0

        return self.calculator.calculate_portfolio_var(
            list(self.positions.values()), confidence
        )

    def get_risk_summary(self) -> Dict[str, Any]:
        """Get comprehensive risk summary"""
        if not self.portfolio_history:
            return {}

        latest = self.portfolio_history[-1]
        current_drawdown, max_drawdown = self.calculator.calculate_drawdown(
            list(self.portfolio_history)
        )

        # Calculate portfolio metrics
        total_exposure = sum(abs(pos.market_value) for pos in self.positions.values())
        total_leverage = sum(
            pos.leverage * abs(pos.market_value) for pos in self.positions.values()
        )
        if latest["value"] > 0:
            avg_leverage = total_leverage / latest["value"]
        else:
            avg_leverage = 0.0

        # Position concentration
        position_concentrations = {}
        for symbol, position in self.positions.items():
            concentration = (
                abs(position.market_value) / latest["value"] * 100
                if latest["value"] > 0
                else 0
            )
            position_concentrations[symbol] = concentration

        max_position_concentration = (
            max(position_concentrations.values()) if position_concentrations else 0
        )

        # Alert summary
        active_alerts = len(
            [a for a in self.alerts.values() if a.status == AlertStatus.PENDING]
        )
        critical_alerts = len(
            [
                a
                for a in self.alerts.values()
                if a.status == AlertStatus.PENDING and a.level == RiskLevel.CRITICAL
            ]
        )

        return {
            "portfolio_value": latest["value"],
            "total_pnl": latest["pnl"],
            "current_drawdown": current_drawdown,
            "max_drawdown": max_drawdown,
            "total_exposure": total_exposure,
            "average_leverage": avg_leverage,
            "num_positions": len(self.positions),
            "max_position_concentration": max_position_concentration,
            "var_95": latest.get("var_95", 0),
            "var_99": latest.get("var_99", 0),
            "active_alerts": active_alerts,
            "critical_alerts": critical_alerts,
            "position_concentrations": position_concentrations,
        }

    def _check_position_risks(self, position: Position):
        """Check risks for individual position"""
        # Position size risk
        if abs(position.market_value) > self.limits.max_position_size_usd:
            self._create_alert(
                RiskType.POSITION_SIZE,
                RiskLevel.HIGH,
                f"Position size {abs(position.market_value):.0f} exceeds limit {self.limits.max_position_size_usd:.0f}",
                abs(position.market_value),
                self.limits.max_position_size_usd,
                position.symbol,
                "Consider reducing position size",
            )

        # Position concentration risk
        if self.portfolio_history:
            latest_value = self.portfolio_history[-1]["value"]
            concentration = (
                abs(position.market_value) / latest_value * 100
                if latest_value > 0
                else 0
            )

            if concentration > self.limits.max_single_asset_exposure:
                self._create_alert(
                    RiskType.CONCENTRATION,
                    RiskLevel.HIGH,
                    f"Asset concentration {concentration:.1f}% exceeds limit {self.limits.max_single_asset_exposure:.1f}%",
                    concentration,
                    self.limits.max_single_asset_exposure,
                    position.symbol,
                    "Consider diversifying positions",
                )

        # Volatility risk
        volatility = self.calculator.calculate_volatility(position.symbol, 30, True)
        if volatility > self.limits.max_volatility_threshold:
            self._create_alert(
                RiskType.VOLATILITY,
                RiskLevel.MEDIUM,
                f"Asset volatility {volatility:.1f}% exceeds threshold {self.limits.max_volatility_threshold:.1f}%",
                volatility,
                self.limits.max_volatility_threshold,
                position.symbol,
                "Monitor position closely due to high volatility",
            )

    def _check_portfolio_risks(self):
        """Check portfolio-wide risks"""
        if not self.portfolio_history:
            return

        latest = self.portfolio_history[-1]

        # Drawdown risk
        current_drawdown, _ = self.calculator.calculate_drawdown(
            list(self.portfolio_history)
        )

        if current_drawdown > self.limits.critical_drawdown:
            self._create_alert(
                RiskType.DRAWDOWN,
                RiskLevel.CRITICAL,
                f"Portfolio drawdown {current_drawdown:.1f}% exceeds critical threshold {self.limits.critical_drawdown:.1f}%",
                current_drawdown,
                self.limits.critical_drawdown,
                None,
                "Immediate risk reduction required",
            )
        elif current_drawdown > self.limits.warning_drawdown:
            self._create_alert(
                RiskType.DRAWDOWN,
                RiskLevel.HIGH,
                f"Portfolio drawdown {current_drawdown:.1f}% exceeds warning threshold {self.limits.warning_drawdown:.1f}%",
                current_drawdown,
                self.limits.warning_drawdown,
                None,
                "Consider reducing risk exposure",
            )

        # Leverage risk
        total_leverage = sum(
            pos.leverage * abs(pos.market_value) for pos in self.positions.values()
        )
        avg_leverage = total_leverage / latest["value"] if latest["value"] > 0 else 0

        if avg_leverage > self.limits.max_leverage:
            self._create_alert(
                RiskType.LEVERAGE,
                RiskLevel.HIGH,
                f"Portfolio leverage {avg_leverage:.2f}x exceeds limit {self.limits.max_leverage:.2f}x",
                avg_leverage,
                self.limits.max_leverage,
                None,
                "Reduce leverage by closing leveraged positions",
            )

        # VaR risk
        if "var_95" in latest and latest["var_95"]:
            var_95_pct = (
                latest["var_95"] / latest["value"] * 100 if latest["value"] > 0 else 0
            )

            if var_95_pct > self.limits.max_portfolio_var_95:
                self._create_alert(
                    RiskType.VAR,
                    RiskLevel.MEDIUM,
                    f"Portfolio VaR (95%) {var_95_pct:.1f}% exceeds limit {self.limits.max_portfolio_var_95:.1f}%",
                    var_95_pct,
                    self.limits.max_portfolio_var_95,
                    None,
                    "Portfolio risk exposure is high",
                )

        # Correlation risk
        self._check_correlation_risk()

    def _check_correlation_risk(self):
        """Check for correlation concentration risk"""
        symbols = list(self.positions.keys())

        if len(symbols) < 2:
            return

        high_correlations = []

        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                correlation = self.calculator.calculate_correlation(
                    symbols[i], symbols[j]
                )

                if abs(correlation) > self.limits.critical_correlation:
                    high_correlations.append(
                        {"pair": (symbols[i], symbols[j]), "correlation": correlation}
                    )

                    self._create_alert(
                        RiskType.CORRELATION,
                        RiskLevel.HIGH,
                        f"High correlation {correlation:.2f} between {symbols[i]} and {symbols[j]}",
                        abs(correlation),
                        self.limits.critical_correlation,
                        f"{symbols[i]}-{symbols[j]}",
                        "Consider reducing correlated positions",
                    )

    def _create_alert(
        self,
        alert_type: RiskType,
        level: RiskLevel,
        message: str,
        metric_value: float,
        threshold: float,
        symbol: str = None,
        action_required: str = "",
    ):
        """Create a new risk alert"""
        alert_id = f"{alert_type.value}_{symbol or 'portfolio'}_{int(time.time())}"

        # Check if similar alert already exists and is active
        existing_alert = None
        for alert in self.alerts.values():
            if (
                alert.alert_type == alert_type
                and alert.symbol == symbol
                and alert.status == AlertStatus.PENDING
            ):
                existing_alert = alert
                break

        if existing_alert:
            # Update existing alert
            existing_alert.metric_value = metric_value
            existing_alert.level = level
            existing_alert.message = message
            existing_alert.created_at = datetime.now()
        else:
            # Create new alert
            alert = RiskAlert(
                id=alert_id,
                alert_type=alert_type,
                level=level,
                message=message,
                metric_value=metric_value,
                threshold=threshold,
                symbol=symbol,
                action_required=action_required,
            )

            self.alerts[alert_id] = alert

            # Store in database
            self._store_alert(alert)

            # Notify handlers
            for handler in self.alert_handlers:
                try:
                    handler(alert)
                except Exception as e:
                    self.logger.error(f"Error in alert handler: {e}")

    def _store_alert(self, alert: RiskAlert):
        """Store alert in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO risk_alerts (
                    id, alert_type, level, message, metric_value, threshold_value,
                    symbol, action_required, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    alert.id,
                    alert.alert_type.value,
                    alert.level.value,
                    alert.message,
                    alert.metric_value,
                    alert.threshold,
                    alert.symbol,
                    alert.action_required,
                    alert.created_at,
                    alert.status.value,
                ),
            )

            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Error storing alert: {e}")

    def _store_portfolio_history(self, data: Dict):
        """Store portfolio history in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO portfolio_history (
                    timestamp, total_value, total_pnl, total_margin, drawdown,
                    var_95, var_99, num_positions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    data["timestamp"],
                    data["value"],
                    data["pnl"],
                    data["margin"],
                    data["drawdown"],
                    data.get("var_95"),
                    data.get("var_99"),
                    data["num_positions"],
                ),
            )

            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Error storing portfolio history: {e}")

    def start_monitoring(self):
        """Start risk monitoring thread"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            return

        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop, daemon=True
        )
        self.monitoring_thread.start()
        self.logger.info("Risk monitoring started")

    def stop_monitoring(self):
        """Stop risk monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        self.logger.info("Risk monitoring stopped")

    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                # Periodic risk checks
                if self.positions:
                    self._check_portfolio_risks()

                # Clean up old resolved alerts
                self._cleanup_old_alerts()

                time.sleep(30)  # Check every 30 seconds

            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(5)

    def _cleanup_old_alerts(self):
        """Clean up old resolved alerts"""
        cutoff_time = datetime.now() - timedelta(days=7)  # Keep 7 days

        alerts_to_remove = []
        for alert_id, alert in self.alerts.items():
            if (
                alert.status in [AlertStatus.RESOLVED, AlertStatus.DISMISSED]
                and alert.created_at < cutoff_time
            ):
                alerts_to_remove.append(alert_id)

        for alert_id in alerts_to_remove:
            del self.alerts[alert_id]

    def get_active_alerts(self, level: RiskLevel = None) -> List[RiskAlert]:
        """Get active alerts, optionally filtered by level"""
        active_alerts = [
            alert
            for alert in self.alerts.values()
            if alert.status == AlertStatus.PENDING
        ]

        if level:
            active_alerts = [alert for alert in active_alerts if alert.level == level]

        return sorted(active_alerts, key=lambda a: a.created_at, reverse=True)

    def acknowledge_alert(self, alert_id: str):
        """Acknowledge an alert"""
        if alert_id in self.alerts:
            self.alerts[alert_id].acknowledge()
            self._update_alert_status(alert_id, AlertStatus.ACKNOWLEDGED)

    def resolve_alert(self, alert_id: str):
        """Resolve an alert"""
        if alert_id in self.alerts:
            self.alerts[alert_id].resolve()
            self._update_alert_status(alert_id, AlertStatus.RESOLVED)

    def dismiss_alert(self, alert_id: str):
        """Dismiss an alert"""
        if alert_id in self.alerts:
            self.alerts[alert_id].dismiss()
            self._update_alert_status(alert_id, AlertStatus.DISMISSED)

    def _update_alert_status(self, alert_id: str, status: AlertStatus):
        """Update alert status in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE risk_alerts SET status = ?, acknowledged_at = ?, resolved_at = ?
                WHERE id = ?
            """,
                (
                    status.value,
                    self.alerts[alert_id].acknowledged_at,
                    self.alerts[alert_id].resolved_at,
                    alert_id,
                ),
            )

            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Error updating alert status: {e}")


# Global risk manager instance
_risk_manager = None


def get_risk_manager() -> RiskManager:
    """Get global risk manager instance"""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager


def initialize_risk_management():
    """Initialize risk management system"""
    manager = get_risk_manager()
    return manager


# Example usage
if __name__ == "__main__":
    # Initialize risk management
    risk_manager = initialize_risk_management()

    # Add some example positions
    risk_manager.update_position("BTCUSDT", "long", 1.5, 45000, 47000)
    risk_manager.update_position("ETHUSDT", "long", 10.0, 3000, 3200)

    # Update portfolio value
    risk_manager.update_portfolio_value(100000, 5000, 10000)

    # Get risk summary
    summary = risk_manager.get_risk_summary()
    print(f"Risk Summary: {summary}")

    # Get active alerts
    alerts = risk_manager.get_active_alerts()
    for alert in alerts:
        print(f"Alert: {alert.level.value} - {alert.message}")

    # Stop monitoring
    time.sleep(5)
    risk_manager.stop_monitoring()
