"""
Dollar Cost Averaging (DCA) Automation System
Implements systematic investment strategies with automated buy/sell scheduling,
smart entry timing, and position management.
"""

import json
import math
import time
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from order_management_db import OrderManagementDB
    from order_management_models import ConditionType, OrderSide, OrderStatus, OrderType

    DCA_AVAILABLE = True
except ImportError:
    DCA_AVAILABLE = False


class DCAStrategy(Enum):
    """Types of DCA strategies."""

    FIXED_AMOUNT = "fixed_amount"  # Fixed dollar amount each interval
    FIXED_QUANTITY = "fixed_quantity"  # Fixed quantity each interval
    PRICE_WEIGHTED = "price_weighted"  # More when price is lower
    VOLATILITY_ADJUSTED = "volatility_adjusted"  # Adjusted based on volatility
    MOMENTUM_DCA = "momentum_dca"  # DCA with trend consideration
    GRID_DCA = "grid_dca"  # Grid-based accumulation
    SMART_DCA = "smart_dca"  # AI/ML enhanced timing
    REVERSE_DCA = "reverse_dca"  # Selling strategy


class DCAInterval(Enum):
    """DCA execution intervals."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class DCACondition(Enum):
    """Conditions that can trigger or pause DCA."""

    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    RSI_OVERSOLD = "rsi_oversold"
    RSI_OVERBOUGHT = "rsi_overbought"
    VOLUME_SPIKE = "volume_spike"
    DRAWDOWN_LIMIT = "drawdown_limit"
    PROFIT_TARGET = "profit_target"
    TIME_WINDOW = "time_window"


class FixedAmountDCA:
    """Implements fixed dollar amount DCA strategy."""

    def __init__(self, config: Dict):
        self.amount_per_purchase = float(config.get("amount_per_purchase", 100))
        self.currency = config.get("currency", "USDT")
        self.min_order_size = float(config.get("min_order_size", 10))

    def calculate_order_size(self, current_price: float, market_data: Dict) -> float:
        """Calculate order quantity based on fixed amount."""
        try:
            if current_price <= 0:
                return 0.0

            quantity = self.amount_per_purchase / current_price

            # Check minimum order size
            if quantity * current_price < self.min_order_size:
                return 0.0

            return quantity

        except Exception as e:
            print(f"Error calculating fixed amount DCA: {e}")
            return 0.0


class PriceWeightedDCA:
    """Implements price-weighted DCA (buy more when price is lower)."""

    def __init__(self, config: Dict):
        self.base_amount = float(config.get("base_amount", 100))
        self.reference_price = float(config.get("reference_price", 0))
        self.max_multiplier = float(config.get("max_multiplier", 5.0))
        self.price_history = []

    def calculate_order_size(self, current_price: float, market_data: Dict) -> float:
        """Calculate order size based on price weighting."""
        try:
            if current_price <= 0:
                return 0.0

            # Update price history
            self.price_history.append(current_price)
            if len(self.price_history) > 50:  # Keep last 50 prices
                self.price_history = self.price_history[-50:]

            # Calculate reference price if not set
            if self.reference_price <= 0:
                if len(self.price_history) >= 20:
                    self.reference_price = sum(self.price_history[-20:]) / 20
                else:
                    self.reference_price = current_price

            # Calculate price ratio
            price_ratio = self.reference_price / current_price

            # Apply multiplier with cap
            multiplier = min(price_ratio, self.max_multiplier)

            # Calculate adjusted amount
            adjusted_amount = self.base_amount * multiplier
            quantity = adjusted_amount / current_price

            return quantity

        except Exception as e:
            print(f"Error calculating price-weighted DCA: {e}")
            return 0.0


class VolatilityAdjustedDCA:
    """Implements volatility-adjusted DCA strategy."""

    def __init__(self, config: Dict):
        self.base_amount = float(config.get("base_amount", 100))
        self.volatility_window = int(config.get("volatility_window", 20))
        self.volatility_multiplier = float(config.get("volatility_multiplier", 2.0))
        self.price_history = []

    def calculate_volatility(self) -> float:
        """Calculate price volatility."""
        try:
            if len(self.price_history) < self.volatility_window:
                return 0.02  # Default volatility

            prices = self.price_history[-self.volatility_window :]
            returns = [
                math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))
            ]

            if not returns:
                return 0.02

            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            volatility = math.sqrt(variance)

            return volatility

        except Exception as e:
            print(f"Error calculating volatility: {e}")
            return 0.02

    def calculate_order_size(self, current_price: float, market_data: Dict) -> float:
        """Calculate order size based on volatility adjustment."""
        try:
            if current_price <= 0:
                return 0.0

            # Update price history
            self.price_history.append(current_price)
            if len(self.price_history) > 100:
                self.price_history = self.price_history[-100:]

            # Calculate volatility
            volatility = self.calculate_volatility()

            # Higher volatility = larger position size
            volatility_factor = 1 + (volatility * self.volatility_multiplier)
            adjusted_amount = self.base_amount * volatility_factor

            quantity = adjusted_amount / current_price

            return quantity

        except Exception as e:
            print(f"Error calculating volatility-adjusted DCA: {e}")
            return 0.0


class GridDCA:
    """Implements grid-based DCA strategy."""

    def __init__(self, config: Dict):
        self.grid_levels = config.get("grid_levels", 10)
        self.grid_spacing = float(config.get("grid_spacing", 0.05))  # 5%
        self.amount_per_level = float(config.get("amount_per_level", 100))
        self.base_price = float(config.get("base_price", 0))
        self.grid_orders = {}  # level -> order_id
        self.executed_levels = set()

    def initialize_grid(self, current_price: float) -> List[Dict]:
        """Initialize grid levels around current price."""
        try:
            if self.base_price <= 0:
                self.base_price = current_price

            grid_orders = []

            # Create buy levels below current price
            for i in range(1, self.grid_levels + 1):
                level_price = self.base_price * (1 - (i * self.grid_spacing))

                if level_price > 0:
                    quantity = self.amount_per_level / level_price

                    grid_order = {
                        "level": -i,  # Negative for buy levels
                        "price": level_price,
                        "quantity": quantity,
                        "amount": self.amount_per_level,
                        "side": "BUY",
                        "type": "grid_dca",
                    }
                    grid_orders.append(grid_order)

            # Create sell levels above current price (for profit taking)
            for i in range(1, self.grid_levels + 1):
                level_price = self.base_price * (1 + (i * self.grid_spacing))

                # Assume we have some quantity to sell (from previous accumulation)
                quantity = self.amount_per_level / self.base_price

                grid_order = {
                    "level": i,  # Positive for sell levels
                    "price": level_price,
                    "quantity": quantity,
                    "amount": level_price * quantity,
                    "side": "SELL",
                    "type": "grid_dca",
                }
                grid_orders.append(grid_order)

            return grid_orders

        except Exception as e:
            print(f"Error initializing grid: {e}")
            return []

    def check_grid_triggers(self, current_price: float) -> List[Dict]:
        """Check which grid levels should be triggered."""
        triggered_levels = []

        try:
            for level, order_data in self.grid_orders.items():
                if level in self.executed_levels:
                    continue

                target_price = order_data["price"]
                side = order_data["side"]

                should_trigger = False

                if side == "BUY" and current_price <= target_price:
                    should_trigger = True
                elif side == "SELL" and current_price >= target_price:
                    should_trigger = True

                if should_trigger:
                    triggered_levels.append(
                        {
                            "level": level,
                            "order_data": order_data,
                            "current_price": current_price,
                        }
                    )

        except Exception as e:
            print(f"Error checking grid triggers: {e}")

        return triggered_levels


class SmartDCA:
    """Implements AI/ML enhanced DCA with market condition analysis."""

    def __init__(self, config: Dict):
        self.base_amount = float(config.get("base_amount", 100))
        self.rsi_period = int(config.get("rsi_period", 14))
        self.ma_period = int(config.get("ma_period", 20))
        self.market_data = []

    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate Relative Strength Index."""
        try:
            if len(prices) < period + 1:
                return 50.0  # Neutral RSI

            gains = []
            losses = []

            for i in range(1, len(prices)):
                change = prices[i] - prices[i - 1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(change))

            if len(gains) < period:
                return 50.0

            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period

            if avg_loss == 0:
                return 100.0

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            return rsi

        except Exception as e:
            print(f"Error calculating RSI: {e}")
            return 50.0

    def calculate_moving_average(self, prices: List[float], period: int) -> float:
        """Calculate simple moving average."""
        try:
            if len(prices) < period:
                return prices[-1] if prices else 0.0

            return sum(prices[-period:]) / period

        except Exception as e:
            return prices[-1] if prices else 0.0

    def get_market_signal(self, current_price: float, market_data: Dict) -> float:
        """Get market signal strength (0-2, where 1 is neutral)."""
        try:
            # Update market data
            self.market_data.append(current_price)
            if len(self.market_data) > 100:
                self.market_data = self.market_data[-100:]

            if len(self.market_data) < self.rsi_period:
                return 1.0  # Neutral

            # Calculate technical indicators
            rsi = self.calculate_rsi(self.market_data, self.rsi_period)
            ma = self.calculate_moving_average(self.market_data, self.ma_period)

            # Signal calculation
            signal_strength = 1.0

            # RSI component (oversold = buy signal, overbought = sell signal)
            if rsi < 30:  # Oversold - strong buy signal
                signal_strength += 0.5
            elif rsi < 40:  # Mildly oversold
                signal_strength += 0.3
            elif rsi > 70:  # Overbought - sell signal
                signal_strength -= 0.5
            elif rsi > 60:  # Mildly overbought
                signal_strength -= 0.3

            # Price vs MA component
            if current_price < ma * 0.95:  # Significantly below MA
                signal_strength += 0.3
            elif current_price < ma:  # Below MA
                signal_strength += 0.2
            elif current_price > ma * 1.05:  # Significantly above MA
                signal_strength -= 0.3
            elif current_price > ma:  # Above MA
                signal_strength -= 0.2

            # Clamp signal between 0 and 2
            return max(0.0, min(2.0, signal_strength))

        except Exception as e:
            print(f"Error calculating market signal: {e}")
            return 1.0

    def calculate_order_size(self, current_price: float, market_data: Dict) -> float:
        """Calculate order size based on market conditions."""
        try:
            if current_price <= 0:
                return 0.0

            # Get market signal
            signal = self.get_market_signal(current_price, market_data)

            # Adjust amount based on signal
            # Signal > 1 = bullish/good buying opportunity
            # Signal < 1 = bearish/wait or reduce buying
            adjusted_amount = self.base_amount * signal

            quantity = adjusted_amount / current_price

            return quantity

        except Exception as e:
            print(f"Error calculating smart DCA: {e}")
            return 0.0


class DCAScheduler:
    """Manages DCA execution scheduling and timing."""

    def __init__(self, config: Dict):
        self.interval = config.get("interval", DCAInterval.DAILY.value)
        self.start_time = config.get("start_time", datetime.now())
        self.end_time = config.get("end_time", None)
        self.max_executions = config.get("max_executions", None)
        self.execution_count = 0
        self.last_execution = None

    def is_time_to_execute(self) -> bool:
        """Check if it's time for next DCA execution."""
        try:
            now = datetime.now()

            # Check if DCA period has ended
            if self.end_time and now > self.end_time:
                return False

            # Check max executions
            if self.max_executions and self.execution_count >= self.max_executions:
                return False

            # Check if first execution
            if self.last_execution is None:
                return now >= self.start_time

            # Calculate next execution time
            if self.interval == DCAInterval.HOURLY.value:
                next_time = self.last_execution + timedelta(hours=1)
            elif self.interval == DCAInterval.DAILY.value:
                next_time = self.last_execution + timedelta(days=1)
            elif self.interval == DCAInterval.WEEKLY.value:
                next_time = self.last_execution + timedelta(weeks=1)
            elif self.interval == DCAInterval.MONTHLY.value:
                next_time = self.last_execution + timedelta(days=30)
            else:
                return False

            return now >= next_time

        except Exception as e:
            print(f"Error checking execution time: {e}")
            return False

    def mark_execution(self):
        """Mark that a DCA execution has occurred."""
        self.last_execution = datetime.now()
        self.execution_count += 1


class DCAConditionChecker:
    """Checks conditions that can trigger, pause, or stop DCA."""

    def __init__(self):
        self.conditions = {}

    def add_condition(self, name: str, condition_type: str, parameters: Dict):
        """Add a condition to check."""
        self.conditions[name] = {
            "type": condition_type,
            "parameters": parameters,
            "active": True,
        }

    def check_conditions(
        self, current_price: float, market_data: Dict
    ) -> Dict[str, bool]:
        """Check all conditions and return results."""
        results = {}

        try:
            for name, condition in self.conditions.items():
                if not condition["active"]:
                    results[name] = True  # Inactive conditions pass
                    continue

                condition_type = condition["type"]
                params = condition["parameters"]

                if condition_type == DCACondition.PRICE_ABOVE.value:
                    threshold = float(params.get("price", 0))
                    results[name] = current_price >= threshold

                elif condition_type == DCACondition.PRICE_BELOW.value:
                    threshold = float(params.get("price", 0))
                    results[name] = current_price <= threshold

                elif condition_type == DCACondition.RSI_OVERSOLD.value:
                    rsi_threshold = float(params.get("rsi_threshold", 30))
                    rsi = market_data.get("rsi", 50)
                    results[name] = rsi <= rsi_threshold

                elif condition_type == DCACondition.RSI_OVERBOUGHT.value:
                    rsi_threshold = float(params.get("rsi_threshold", 70))
                    rsi = market_data.get("rsi", 50)
                    results[name] = rsi >= rsi_threshold

                elif condition_type == DCACondition.VOLUME_SPIKE.value:
                    volume_multiplier = float(params.get("volume_multiplier", 2.0))
                    current_volume = market_data.get("volume", 0)
                    avg_volume = market_data.get("avg_volume", 1)
                    results[name] = current_volume >= (avg_volume * volume_multiplier)

                else:
                    results[name] = True  # Unknown condition passes

        except Exception as e:
            print(f"Error checking conditions: {e}")
            # Return all conditions as passed on error
            results = {name: True for name in self.conditions.keys()}

        return results


class DCAEngine:
    """Main DCA automation engine."""

    def __init__(self, db_path: Optional[str] = None):
        self.db = OrderManagementDB(db_path) if DCA_AVAILABLE else None
        self.dca_plans = {}  # plan_id -> DCA configuration
        self.strategy_classes = {
            DCAStrategy.FIXED_AMOUNT.value: FixedAmountDCA,
            DCAStrategy.PRICE_WEIGHTED.value: PriceWeightedDCA,
            DCAStrategy.VOLATILITY_ADJUSTED.value: VolatilityAdjustedDCA,
            DCAStrategy.GRID_DCA.value: GridDCA,
            DCAStrategy.SMART_DCA.value: SmartDCA,
        }

        # Mock price and market data provider
        self.market_data_cache = {}

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price (mock implementation)."""
        import random

        base_prices = {"BTCUSDT": 45000, "ETHUSDT": 3000, "ADAUSDT": 0.5}

        base = base_prices.get(symbol, 100)
        return base * (1 + random.uniform(-0.02, 0.02))

    def get_market_data(self, symbol: str) -> Dict:
        """Get market data (mock implementation)."""
        import random

        return {
            "rsi": random.uniform(20, 80),
            "volume": random.uniform(1000000, 5000000),
            "avg_volume": 2000000,
            "volatility": random.uniform(0.01, 0.05),
        }

    def create_dca_plan(self, plan_config: Dict) -> Dict[str, Any]:
        """Create a new DCA plan."""
        try:
            # Validate configuration
            required_fields = ["symbol", "strategy", "interval"]
            for field in required_fields:
                if field not in plan_config:
                    return {
                        "success": False,
                        "error": f"Missing required field: {field}",
                    }

            plan_id = f"dca_{int(time.time())}"

            # Initialize strategy
            strategy_type = plan_config["strategy"]
            if strategy_type not in self.strategy_classes:
                return {"success": False, "error": f"Unknown strategy: {strategy_type}"}

            strategy_class = self.strategy_classes[strategy_type]
            strategy_instance = strategy_class(plan_config)

            # Initialize scheduler
            scheduler = DCAScheduler(plan_config)

            # Initialize condition checker
            condition_checker = DCAConditionChecker()
            conditions = plan_config.get("conditions", [])
            for condition in conditions:
                condition_checker.add_condition(
                    condition["name"], condition["type"], condition["parameters"]
                )

            # Create plan
            dca_plan = {
                "id": plan_id,
                "config": plan_config,
                "strategy": strategy_instance,
                "scheduler": scheduler,
                "condition_checker": condition_checker,
                "status": "active",
                "created_at": datetime.now(),
                "total_invested": 0.0,
                "total_quantity": 0.0,
                "execution_history": [],
                "statistics": {
                    "total_executions": 0,
                    "avg_price": 0.0,
                    "last_execution": None,
                },
            }

            self.dca_plans[plan_id] = dca_plan

            # Save to database if available
            if self.db:
                db_plan_data = {
                    "id": plan_id,
                    "symbol": plan_config["symbol"],
                    "type": OrderType.DCA.value,
                    "status": OrderStatus.PENDING.value,
                    "quantity": 0.0,  # Will be updated as executions occur
                    "price": 0.0,
                    "side": plan_config.get("side", "BUY"),
                    "created_at": datetime.now(),
                    "dca_config": json.dumps(plan_config),
                }
                self.db.create_order(db_plan_data)

            return {
                "success": True,
                "plan_id": plan_id,
                "message": f"DCA plan created with {strategy_type} strategy",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def execute_dca_plans(self) -> List[Dict]:
        """Execute all active DCA plans that are due."""
        executions = []

        try:
            for plan_id, plan in self.dca_plans.items():
                if plan["status"] != "active":
                    continue

                # Check if it's time to execute
                if not plan["scheduler"].is_time_to_execute():
                    continue

                # Get current market data
                symbol = plan["config"]["symbol"]
                current_price = self.get_current_price(symbol)
                market_data = self.get_market_data(symbol)

                if not current_price:
                    continue

                # Check conditions
                condition_results = plan["condition_checker"].check_conditions(
                    current_price, market_data
                )

                # If any blocking condition fails, skip execution
                blocking_conditions = [
                    name for name, result in condition_results.items() if not result
                ]
                if blocking_conditions:
                    executions.append(
                        {
                            "plan_id": plan_id,
                            "status": "skipped",
                            "reason": f"Blocked by conditions: {blocking_conditions}",
                            "current_price": current_price,
                        }
                    )
                    continue

                # Calculate order size using strategy
                quantity = plan["strategy"].calculate_order_size(
                    current_price, market_data
                )

                if quantity <= 0:
                    executions.append(
                        {
                            "plan_id": plan_id,
                            "status": "skipped",
                            "reason": "Strategy calculated zero quantity",
                            "current_price": current_price,
                        }
                    )
                    continue

                # Execute the order
                execution_result = self._execute_dca_order(
                    plan_id, plan, quantity, current_price, market_data
                )
                executions.append(execution_result)

                # Mark execution in scheduler
                plan["scheduler"].mark_execution()

        except Exception as e:
            print(f"Error executing DCA plans: {e}")

        return executions

    def _execute_dca_order(
        self,
        plan_id: str,
        plan: Dict,
        quantity: float,
        current_price: float,
        market_data: Dict,
    ) -> Dict:
        """Execute a single DCA order."""
        try:
            symbol = plan["config"]["symbol"]
            side = plan["config"].get("side", "BUY")
            amount = quantity * current_price

            # Create execution record
            execution = {
                "timestamp": datetime.now(),
                "price": current_price,
                "quantity": quantity,
                "amount": amount,
                "market_data": market_data.copy(),
            }

            # Update plan statistics
            plan["execution_history"].append(execution)
            plan["total_invested"] += amount
            plan["total_quantity"] += quantity
            plan["statistics"]["total_executions"] += 1
            plan["statistics"]["last_execution"] = datetime.now()

            # Calculate average price
            if plan["total_quantity"] > 0:
                plan["statistics"]["avg_price"] = (
                    plan["total_invested"] / plan["total_quantity"]
                )

            # Record execution in database
            if self.db:
                execution_data = {
                    "order_id": plan_id,
                    "execution_price": current_price,
                    "executed_quantity": quantity,
                    "execution_time": datetime.now(),
                    "status": "executed",
                    "execution_type": "dca_auto",
                }
                self.db.create_order_execution(execution_data)

            return {
                "plan_id": plan_id,
                "status": "executed",
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": current_price,
                "amount": amount,
                "total_invested": plan["total_invested"],
                "avg_price": plan["statistics"]["avg_price"],
                "execution_count": plan["statistics"]["total_executions"],
            }

        except Exception as e:
            print(f"Error executing DCA order: {e}")
            return {
                "plan_id": plan_id,
                "status": "failed",
                "error": str(e),
                "current_price": current_price,
            }

    def get_dca_plan_status(self, plan_id: str) -> Optional[Dict]:
        """Get status of a specific DCA plan."""
        if plan_id not in self.dca_plans:
            return None

        plan = self.dca_plans[plan_id]

        # Calculate performance metrics
        current_price = self.get_current_price(plan["config"]["symbol"])
        unrealized_pnl = 0.0
        unrealized_pct = 0.0

        if current_price and plan["total_quantity"] > 0:
            avg_price = plan["statistics"]["avg_price"]
            current_value = plan["total_quantity"] * current_price
            total_invested = plan["total_invested"]

            unrealized_pnl = current_value - total_invested
            unrealized_pct = (
                (unrealized_pnl / total_invested) * 100 if total_invested > 0 else 0
            )

        status = {
            "plan_id": plan_id,
            "symbol": plan["config"]["symbol"],
            "strategy": plan["config"]["strategy"],
            "status": plan["status"],
            "created_at": plan["created_at"],
            "statistics": plan["statistics"],
            "total_invested": plan["total_invested"],
            "total_quantity": plan["total_quantity"],
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pct": unrealized_pct,
            "execution_count": len(plan["execution_history"]),
            "last_execution": (
                plan["execution_history"][-1] if plan["execution_history"] else None
            ),
        }

        return status

    def pause_dca_plan(self, plan_id: str) -> bool:
        """Pause a DCA plan."""
        if plan_id in self.dca_plans:
            self.dca_plans[plan_id]["status"] = "paused"
            return True
        return False

    def resume_dca_plan(self, plan_id: str) -> bool:
        """Resume a DCA plan."""
        if plan_id in self.dca_plans:
            self.dca_plans[plan_id]["status"] = "active"
            return True
        return False

    def stop_dca_plan(self, plan_id: str) -> bool:
        """Stop a DCA plan permanently."""
        if plan_id in self.dca_plans:
            self.dca_plans[plan_id]["status"] = "stopped"
            return True
        return False

    def get_all_dca_plans(self) -> List[Dict]:
        """Get status of all DCA plans."""
        return [self.get_dca_plan_status(plan_id) for plan_id in self.dca_plans.keys()]

    def get_dca_summary(self) -> Dict[str, Any]:
        """Get summary of all DCA activities."""
        try:
            summary = {
                "total_plans": len(self.dca_plans),
                "active_plans": 0,
                "paused_plans": 0,
                "stopped_plans": 0,
                "total_invested": 0.0,
                "total_executions": 0,
                "strategies": {},
                "top_performers": [],
                "plans": [],
            }

            plan_performances = []

            for plan_id, plan in self.dca_plans.items():
                status = plan["status"]
                strategy = plan["config"]["strategy"]

                # Count by status
                if status == "active":
                    summary["active_plans"] += 1
                elif status == "paused":
                    summary["paused_plans"] += 1
                elif status == "stopped":
                    summary["stopped_plans"] += 1

                # Count by strategy
                if strategy not in summary["strategies"]:
                    summary["strategies"][strategy] = 0
                summary["strategies"][strategy] += 1

                # Accumulate totals
                summary["total_invested"] += plan["total_invested"]
                summary["total_executions"] += plan["statistics"]["total_executions"]

                # Get plan status for performance tracking
                plan_status = self.get_dca_plan_status(plan_id)
                if plan_status:
                    summary["plans"].append(
                        {
                            "id": plan_id,
                            "symbol": plan_status["symbol"],
                            "strategy": plan_status["strategy"],
                            "status": plan_status["status"],
                            "invested": plan_status["total_invested"],
                            "unrealized_pct": plan_status["unrealized_pct"],
                        }
                    )

                    plan_performances.append(
                        {
                            "plan_id": plan_id,
                            "symbol": plan_status["symbol"],
                            "unrealized_pct": plan_status["unrealized_pct"],
                        }
                    )

            # Sort and get top performers
            plan_performances.sort(key=lambda x: x["unrealized_pct"], reverse=True)
            summary["top_performers"] = plan_performances[:5]

            return summary

        except Exception as e:
            return {"error": str(e)}


# Global DCA engine
_dca_engine = None


def get_dca_engine(db_path: Optional[str] = None) -> DCAEngine:
    """Get the global DCA engine instance."""
    global _dca_engine
    if _dca_engine is None:
        _dca_engine = DCAEngine(db_path)
    return _dca_engine


if __name__ == "__main__":
    # Test the DCA engine
    engine = get_dca_engine()

    print("DCA Automation Engine Test")
    print("=" * 40)

    # Test fixed amount DCA
    fixed_dca_config = {
        "symbol": "BTCUSDT",
        "strategy": DCAStrategy.FIXED_AMOUNT.value,
        "interval": DCAInterval.DAILY.value,
        "amount_per_purchase": 100,
        "side": "BUY",
        "start_time": datetime.now(),
        "max_executions": 10,
    }

    result = engine.create_dca_plan(fixed_dca_config)
    print(f"Fixed DCA: {result}")

    # Test smart DCA
    smart_dca_config = {
        "symbol": "ETHUSDT",
        "strategy": DCAStrategy.SMART_DCA.value,
        "interval": DCAInterval.DAILY.value,
        "base_amount": 200,
        "side": "BUY",
        "conditions": [
            {
                "name": "price_below_resistance",
                "type": DCACondition.PRICE_BELOW.value,
                "parameters": {"price": 3500},
            }
        ],
    }

    result = engine.create_dca_plan(smart_dca_config)
    print(f"Smart DCA: {result}")

    # Execute plans
    executions = engine.execute_dca_plans()
    print(f"Executions: {executions}")

    # Get summary
    summary = engine.get_dca_summary()
    print(f"DCA Summary: {summary}")
