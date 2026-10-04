"""
Advanced Take-Profit System
Implements take-profit orders with partial fills, scaling out strategies, and profit target management.
"""

import math
import time
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    from order_management_db import OrderManagementDB
    from order_management_models import ConditionType, OrderSide, OrderStatus, OrderType

    TAKE_PROFIT_AVAILABLE = True
except ImportError:
    TAKE_PROFIT_AVAILABLE = False


class TakeProfitType(Enum):
    """Types of take-profit orders."""

    BASIC = "basic"  # Simple take-profit at fixed price
    LADDER = "ladder"  # Multiple profit levels (scaling out)
    TRAILING = "trailing"  # Trailing take-profit
    PERCENTAGE = "percentage"  # Percentage-based profit targets
    FIBONACCI = "fibonacci"  # Fibonacci retracement levels
    SUPPORT_RESISTANCE = "support_resistance"  # Based on S/R levels
    RISK_REWARD = "risk_reward"  # Risk/reward ratio based
    TIME_BASED = "time_based"  # Time-limited profit taking


class ScalingStrategy(Enum):
    """Strategies for scaling out of positions."""

    EQUAL_PARTS = "equal_parts"  # Equal quantities at each level
    PYRAMID = "pyramid"  # Decreasing quantities
    INVERSE_PYRAMID = "inverse_pyramid"  # Increasing quantities
    FIBONACCI_SCALING = "fibonacci_scaling"  # Fibonacci-based quantities
    CUSTOM = "custom"  # User-defined quantities


class ProfitLadderManager:
    """Manages ladder-style take-profit orders (scaling out)."""

    def __init__(self, price_provider):
        self.price_provider = price_provider
        self.ladder_data = {}  # order_id -> ladder configuration

    def create_profit_ladder(self, order_id: str, order_data: Dict) -> bool:
        """Create a profit ladder with multiple take-profit levels."""
        try:
            symbol = order_data["symbol"]
            side = order_data["side"]
            total_quantity = float(order_data["quantity"])
            entry_price = float(order_data.get("entry_price", 0))

            # Get ladder configuration
            profit_levels = order_data.get("profit_levels", [])
            scaling_strategy = order_data.get(
                "scaling_strategy", ScalingStrategy.EQUAL_PARTS.value
            )

            if not profit_levels:
                return False

            # Calculate quantities for each level
            level_quantities = self._calculate_level_quantities(
                total_quantity, len(profit_levels), scaling_strategy
            )

            # Create ladder structure
            ladder_config = {
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "total_quantity": total_quantity,
                "remaining_quantity": total_quantity,
                "levels": [],
                "filled_levels": [],
                "scaling_strategy": scaling_strategy,
                "created_at": datetime.now(),
            }

            # Configure each level
            for i, (level_price, quantity) in enumerate(
                zip(profit_levels, level_quantities)
            ):
                level_config = {
                    "level": i + 1,
                    "target_price": float(level_price),
                    "quantity": quantity,
                    "filled": False,
                    "fill_price": 0.0,
                    "fill_time": None,
                    "profit_pct": self._calculate_profit_percentage(
                        entry_price, level_price, side
                    ),
                }
                ladder_config["levels"].append(level_config)

            self.ladder_data[order_id] = ladder_config
            return True

        except Exception as e:
            print(f"Error creating profit ladder: {e}")
            return False

    def _calculate_level_quantities(
        self, total_quantity: float, num_levels: int, strategy: str
    ) -> List[float]:
        """Calculate quantities for each profit level based on scaling strategy."""
        try:
            quantities = []

            if strategy == ScalingStrategy.EQUAL_PARTS.value:
                # Equal quantities at each level
                level_qty = total_quantity / num_levels
                quantities = [level_qty] * num_levels

            elif strategy == ScalingStrategy.PYRAMID.value:
                # Decreasing quantities (largest first)
                weights = [num_levels - i for i in range(num_levels)]
                total_weight = sum(weights)
                for weight in weights:
                    quantities.append(total_quantity * weight / total_weight)

            elif strategy == ScalingStrategy.INVERSE_PYRAMID.value:
                # Increasing quantities (smallest first)
                weights = [i + 1 for i in range(num_levels)]
                total_weight = sum(weights)
                for weight in weights:
                    quantities.append(total_quantity * weight / total_weight)

            elif strategy == ScalingStrategy.FIBONACCI_SCALING.value:
                # Fibonacci-based scaling
                fib_ratios = [0.236, 0.382, 0.618, 1.0, 1.618][:num_levels]
                total_weight = sum(fib_ratios)
                for ratio in fib_ratios:
                    quantities.append(total_quantity * ratio / total_weight)

            else:  # Default to equal parts
                level_qty = total_quantity / num_levels
                quantities = [level_qty] * num_levels

            # Ensure total equals original quantity
            actual_total = sum(quantities)
            if actual_total != total_quantity:
                # Adjust last quantity to match exactly
                difference = total_quantity - actual_total
                quantities[-1] += difference

            return quantities

        except Exception as e:
            print(f"Error calculating level quantities: {e}")
            return [total_quantity / num_levels] * num_levels

    def _calculate_profit_percentage(
        self, entry_price: float, target_price: float, side: str
    ) -> float:
        """Calculate profit percentage for a target price."""
        try:
            if side.upper() == "SELL":  # Long position
                return ((target_price - entry_price) / entry_price) * 100
            else:  # Short position
                return ((entry_price - target_price) / entry_price) * 100
        except:
            return 0.0

    def check_ladder_triggers(self, order_id: str, current_price: float) -> List[Dict]:
        """Check which ladder levels should be triggered."""
        triggered_levels = []

        try:
            if order_id not in self.ladder_data:
                return triggered_levels

            ladder = self.ladder_data[order_id]
            side = ladder["side"]

            for level in ladder["levels"]:
                if level["filled"]:
                    continue

                target_price = level["target_price"]
                should_trigger = False

                if side.upper() == "SELL":  # Long position
                    should_trigger = current_price >= target_price
                else:  # Short position
                    should_trigger = current_price <= target_price

                if should_trigger:
                    triggered_levels.append(
                        {
                            "level": level["level"],
                            "target_price": target_price,
                            "quantity": level["quantity"],
                            "profit_pct": level["profit_pct"],
                        }
                    )

        except Exception as e:
            print(f"Error checking ladder triggers: {e}")

        return triggered_levels

    def execute_ladder_level(
        self, order_id: str, level: int, fill_price: float
    ) -> bool:
        """Mark a ladder level as executed."""
        try:
            if order_id not in self.ladder_data:
                return False

            ladder = self.ladder_data[order_id]

            for level_config in ladder["levels"]:
                if level_config["level"] == level and not level_config["filled"]:
                    level_config["filled"] = True
                    level_config["fill_price"] = fill_price
                    level_config["fill_time"] = datetime.now()

                    # Update remaining quantity
                    ladder["remaining_quantity"] -= level_config["quantity"]
                    ladder["filled_levels"].append(level)

                    return True

            return False

        except Exception as e:
            print(f"Error executing ladder level: {e}")
            return False

    def get_ladder_status(self, order_id: str) -> Optional[Dict]:
        """Get current status of a profit ladder."""
        if order_id in self.ladder_data:
            ladder = self.ladder_data[order_id].copy()

            # Calculate summary statistics
            total_levels = len(ladder["levels"])
            filled_levels = len(ladder["filled_levels"])
            completion_pct = (
                (filled_levels / total_levels) * 100 if total_levels > 0 else 0
            )

            # Calculate realized profit
            realized_profit = 0.0
            for level in ladder["levels"]:
                if level["filled"]:
                    entry_price = ladder["entry_price"]
                    fill_price = level["fill_price"]
                    quantity = level["quantity"]

                    if ladder["side"].upper() == "SELL":
                        profit = (fill_price - entry_price) * quantity
                    else:
                        profit = (entry_price - fill_price) * quantity

                    realized_profit += profit

            ladder["completion_pct"] = completion_pct
            ladder["realized_profit"] = realized_profit

            return ladder

        return None


class TrailingProfitManager:
    """Manages trailing take-profit orders."""

    def __init__(self, price_provider):
        self.price_provider = price_provider
        self.trailing_data = {}  # order_id -> trailing configuration

    def initialize_trailing_profit(self, order_id: str, order_data: Dict) -> bool:
        """Initialize a trailing take-profit order."""
        try:
            symbol = order_data["symbol"]
            side = order_data["side"]
            entry_price = float(order_data.get("entry_price", 0))
            trailing_amount = float(order_data.get("trailing_amount", 0))
            trailing_percent = float(order_data.get("trailing_percent", 0))
            min_profit_pct = float(order_data.get("min_profit_pct", 1.0))

            current_price = self.price_provider.get_current_price(symbol)
            if not current_price:
                return False

            # Calculate minimum profit price
            if side.upper() == "SELL":  # Long position
                min_profit_price = entry_price * (1 + min_profit_pct / 100)
                if current_price < min_profit_price:
                    # Not yet at minimum profit
                    initial_trigger = min_profit_price
                else:
                    # Already profitable, set trailing stop
                    if trailing_percent > 0:
                        initial_trigger = current_price * (1 - trailing_percent / 100)
                    else:
                        initial_trigger = current_price - trailing_amount
                peak_price = current_price
            else:  # Short position
                min_profit_price = entry_price * (1 - min_profit_pct / 100)
                if current_price > min_profit_price:
                    # Not yet at minimum profit
                    initial_trigger = min_profit_price
                else:
                    # Already profitable, set trailing stop
                    if trailing_percent > 0:
                        initial_trigger = current_price * (1 + trailing_percent / 100)
                    else:
                        initial_trigger = current_price + trailing_amount
                peak_price = current_price

            self.trailing_data[order_id] = {
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "current_trigger": initial_trigger,
                "peak_price": peak_price,
                "min_profit_price": min_profit_price,
                "trailing_amount": trailing_amount,
                "trailing_percent": trailing_percent,
                "min_profit_reached": (
                    current_price >= min_profit_price
                    if side.upper() == "SELL"
                    else current_price <= min_profit_price
                ),
                "last_update": datetime.now(),
                "max_profit_pct": self._calculate_profit_percentage(
                    entry_price, current_price, side
                ),
            }

            return True

        except Exception as e:
            print(f"Error initializing trailing profit: {e}")
            return False

    def _calculate_profit_percentage(
        self, entry_price: float, current_price: float, side: str
    ) -> float:
        """Calculate current profit percentage."""
        try:
            if side.upper() == "SELL":  # Long position
                return ((current_price - entry_price) / entry_price) * 100
            else:  # Short position
                return ((entry_price - current_price) / entry_price) * 100
        except:
            return 0.0

    def update_trailing_profit(
        self, order_id: str, current_price: float
    ) -> Tuple[bool, float, Dict]:
        """Update trailing profit and return (should_trigger, current_trigger, status)."""
        try:
            if order_id not in self.trailing_data:
                return False, 0.0, {}

            data = self.trailing_data[order_id]
            side = data["side"]
            trailing_amount = data["trailing_amount"]
            trailing_percent = data["trailing_percent"]
            min_profit_price = data["min_profit_price"]

            # Update profit statistics
            current_profit_pct = self._calculate_profit_percentage(
                data["entry_price"], current_price, side
            )
            data["max_profit_pct"] = max(data["max_profit_pct"], current_profit_pct)

            # Check if minimum profit is reached
            if not data["min_profit_reached"]:
                if side.upper() == "SELL":
                    data["min_profit_reached"] = current_price >= min_profit_price
                else:
                    data["min_profit_reached"] = current_price <= min_profit_price

            # Update trailing logic
            should_trigger = False

            if data["min_profit_reached"]:
                if side.upper() == "SELL":  # Long position
                    if current_price > data["peak_price"]:
                        data["peak_price"] = current_price

                        # Calculate new trigger price
                        if trailing_percent > 0:
                            new_trigger = current_price * (1 - trailing_percent / 100)
                        else:
                            new_trigger = current_price - trailing_amount

                        # Only move trigger up (tighten)
                        if new_trigger > data["current_trigger"]:
                            data["current_trigger"] = new_trigger
                            data["last_update"] = datetime.now()

                    # Check if trigger is hit
                    should_trigger = current_price <= data["current_trigger"]

                else:  # Short position
                    if current_price < data["peak_price"]:
                        data["peak_price"] = current_price

                        # Calculate new trigger price
                        if trailing_percent > 0:
                            new_trigger = current_price * (1 + trailing_percent / 100)
                        else:
                            new_trigger = current_price + trailing_amount

                        # Only move trigger down (tighten)
                        if new_trigger < data["current_trigger"]:
                            data["current_trigger"] = new_trigger
                            data["last_update"] = datetime.now()

                    # Check if trigger is hit
                    should_trigger = current_price >= data["current_trigger"]

            status = {
                "min_profit_reached": data["min_profit_reached"],
                "current_profit_pct": current_profit_pct,
                "max_profit_pct": data["max_profit_pct"],
                "peak_price": data["peak_price"],
                "current_trigger": data["current_trigger"],
            }

            return should_trigger, data["current_trigger"], status

        except Exception as e:
            print(f"Error updating trailing profit: {e}")
            return False, 0.0, {}


class FibonacciProfitManager:
    """Manages Fibonacci-based take-profit levels."""

    def __init__(self, price_provider):
        self.price_provider = price_provider
        # Standard Fibonacci retracement levels
        self.fib_levels = [0.236, 0.382, 0.500, 0.618, 0.786, 1.000, 1.272, 1.618]

    def calculate_fibonacci_levels(
        self,
        entry_price: float,
        target_price: float,
        side: str,
        levels: Optional[List[float]] = None,
    ) -> List[Dict]:
        """Calculate Fibonacci-based profit levels."""
        try:
            if levels is None:
                levels = self.fib_levels[:6]  # Use first 6 levels by default

            fib_targets = []
            price_range = abs(target_price - entry_price)

            for fib_level in levels:
                if side.upper() == "SELL":  # Long position
                    fib_price = entry_price + (price_range * fib_level)
                else:  # Short position
                    fib_price = entry_price - (price_range * fib_level)

                profit_pct = (
                    ((fib_price - entry_price) / entry_price) * 100
                    if side.upper() == "SELL"
                    else ((entry_price - fib_price) / entry_price) * 100
                )

                fib_targets.append(
                    {
                        "fibonacci_level": fib_level,
                        "target_price": fib_price,
                        "profit_percentage": profit_pct,
                        "risk_reward_ratio": fib_level,
                    }
                )

            return fib_targets

        except Exception as e:
            print(f"Error calculating Fibonacci levels: {e}")
            return []


class RiskRewardManager:
    """Manages risk/reward ratio-based take-profit orders."""

    def __init__(self, price_provider):
        self.price_provider = price_provider

    def calculate_risk_reward_targets(
        self,
        entry_price: float,
        stop_loss_price: float,
        side: str,
        risk_reward_ratios: List[float],
    ) -> List[Dict]:
        """Calculate take-profit targets based on risk/reward ratios."""
        try:
            targets = []

            # Calculate risk amount
            risk_amount = abs(entry_price - stop_loss_price)

            for rr_ratio in risk_reward_ratios:
                reward_amount = risk_amount * rr_ratio

                if side.upper() == "SELL":  # Long position
                    target_price = entry_price + reward_amount
                else:  # Short position
                    target_price = entry_price - reward_amount

                profit_pct = (
                    ((target_price - entry_price) / entry_price) * 100
                    if side.upper() == "SELL"
                    else ((entry_price - target_price) / entry_price) * 100
                )

                targets.append(
                    {
                        "risk_reward_ratio": rr_ratio,
                        "target_price": target_price,
                        "profit_percentage": profit_pct,
                        "reward_amount": reward_amount,
                    }
                )

            return targets

        except Exception as e:
            print(f"Error calculating risk/reward targets: {e}")
            return []


class TakeProfitEngine:
    """Main engine for managing take-profit orders."""

    def __init__(self, db_path: Optional[str] = None):
        self.db = OrderManagementDB(db_path) if TAKE_PROFIT_AVAILABLE else None
        self.ladder_manager = ProfitLadderManager(self)
        self.trailing_manager = TrailingProfitManager(self)
        self.fibonacci_manager = FibonacciProfitManager(self)
        self.risk_reward_manager = RiskRewardManager(self)

        # Mock price provider
        self.mock_prices = {}

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price (mock implementation)."""
        import random

        base_prices = {"BTCUSDT": 45000, "ETHUSDT": 3000, "ADAUSDT": 0.5}

        base = base_prices.get(symbol, 100)
        # Add some random movement with slight upward bias for testing
        return base * (1 + random.uniform(-0.01, 0.03))

    def create_take_profit_order(self, order_data: Dict) -> Dict[str, Any]:
        """Create a take-profit order of specified type."""
        try:
            tp_type = order_data.get("tp_type", TakeProfitType.BASIC.value)
            symbol = order_data["symbol"]
            side = order_data["side"]
            quantity = float(order_data["quantity"])

            if not symbol or not side or quantity <= 0:
                return {"success": False, "error": "Invalid order parameters"}

            # Create based on type
            if tp_type == TakeProfitType.LADDER.value:
                return self._create_ladder_tp(order_data)
            elif tp_type == TakeProfitType.TRAILING.value:
                return self._create_trailing_tp(order_data)
            elif tp_type == TakeProfitType.FIBONACCI.value:
                return self._create_fibonacci_tp(order_data)
            elif tp_type == TakeProfitType.RISK_REWARD.value:
                return self._create_risk_reward_tp(order_data)
            elif tp_type == TakeProfitType.PERCENTAGE.value:
                return self._create_percentage_tp(order_data)
            else:
                return self._create_basic_tp(order_data)

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_ladder_tp(self, order_data: Dict) -> Dict[str, Any]:
        """Create a ladder take-profit order."""
        try:
            order_id = f"ladder_tp_{int(time.time())}"

            if self.ladder_manager.create_profit_ladder(order_id, order_data):
                if self.db:
                    db_order_data = {
                        **order_data,
                        "id": order_id,
                        "type": OrderType.TAKE_PROFIT.value,
                        "status": OrderStatus.PENDING.value,
                        "created_at": datetime.now(),
                    }
                    self.db.create_order(db_order_data)

                return {
                    "success": True,
                    "order_id": order_id,
                    "tp_type": TakeProfitType.LADDER.value,
                    "levels_count": len(order_data.get("profit_levels", [])),
                    "message": "Ladder take-profit order created",
                }
            else:
                return {"success": False, "error": "Failed to create profit ladder"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_trailing_tp(self, order_data: Dict) -> Dict[str, Any]:
        """Create a trailing take-profit order."""
        try:
            order_id = f"trail_tp_{int(time.time())}"

            if self.trailing_manager.initialize_trailing_profit(order_id, order_data):
                if self.db:
                    db_order_data = {
                        **order_data,
                        "id": order_id,
                        "type": OrderType.TAKE_PROFIT.value,
                        "status": OrderStatus.PENDING.value,
                        "created_at": datetime.now(),
                    }
                    self.db.create_order(db_order_data)

                return {
                    "success": True,
                    "order_id": order_id,
                    "tp_type": TakeProfitType.TRAILING.value,
                    "trailing_percent": order_data.get("trailing_percent", 0),
                    "min_profit_pct": order_data.get("min_profit_pct", 1.0),
                    "message": "Trailing take-profit order created",
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to create trailing take-profit",
                }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_fibonacci_tp(self, order_data: Dict) -> Dict[str, Any]:
        """Create Fibonacci-based take-profit order."""
        try:
            entry_price = float(order_data.get("entry_price", 0))
            target_price = float(order_data.get("target_price", 0))
            side = order_data["side"]

            if entry_price <= 0 or target_price <= 0:
                return {"success": False, "error": "Invalid entry or target price"}

            fib_levels = self.fibonacci_manager.calculate_fibonacci_levels(
                entry_price, target_price, side
            )

            if not fib_levels:
                return {
                    "success": False,
                    "error": "Failed to calculate Fibonacci levels",
                }

            order_id = f"fib_tp_{int(time.time())}"

            if self.db:
                db_order_data = {
                    **order_data,
                    "id": order_id,
                    "type": OrderType.TAKE_PROFIT.value,
                    "status": OrderStatus.PENDING.value,
                    "created_at": datetime.now(),
                    "fibonacci_levels": fib_levels,
                }
                self.db.create_order(db_order_data)

            return {
                "success": True,
                "order_id": order_id,
                "tp_type": TakeProfitType.FIBONACCI.value,
                "fibonacci_levels": fib_levels,
                "message": f"Fibonacci take-profit created with {len(fib_levels)} levels",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_risk_reward_tp(self, order_data: Dict) -> Dict[str, Any]:
        """Create risk/reward ratio-based take-profit order."""
        try:
            entry_price = float(order_data.get("entry_price", 0))
            stop_loss_price = float(order_data.get("stop_loss_price", 0))
            side = order_data["side"]
            rr_ratios = order_data.get("risk_reward_ratios", [1.0, 2.0, 3.0])

            if entry_price <= 0 or stop_loss_price <= 0:
                return {"success": False, "error": "Invalid entry or stop loss price"}

            targets = self.risk_reward_manager.calculate_risk_reward_targets(
                entry_price, stop_loss_price, side, rr_ratios
            )

            if not targets:
                return {
                    "success": False,
                    "error": "Failed to calculate risk/reward targets",
                }

            order_id = f"rr_tp_{int(time.time())}"

            if self.db:
                db_order_data = {
                    **order_data,
                    "id": order_id,
                    "type": OrderType.TAKE_PROFIT.value,
                    "status": OrderStatus.PENDING.value,
                    "created_at": datetime.now(),
                    "risk_reward_targets": targets,
                }
                self.db.create_order(db_order_data)

            return {
                "success": True,
                "order_id": order_id,
                "tp_type": TakeProfitType.RISK_REWARD.value,
                "targets": targets,
                "message": f"Risk/reward take-profit created with {len(targets)} targets",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_percentage_tp(self, order_data: Dict) -> Dict[str, Any]:
        """Create percentage-based take-profit order."""
        try:
            entry_price = float(order_data.get("entry_price", 0))
            profit_percent = float(order_data.get("profit_percent", 0))
            side = order_data["side"]

            if entry_price <= 0 or profit_percent <= 0:
                return {
                    "success": False,
                    "error": "Invalid entry price or profit percentage",
                }

            if side.upper() == "SELL":  # Long position
                target_price = entry_price * (1 + profit_percent / 100)
            else:  # Short position
                target_price = entry_price * (1 - profit_percent / 100)

            order_id = f"pct_tp_{int(time.time())}"

            if self.db:
                db_order_data = {
                    **order_data,
                    "id": order_id,
                    "price": target_price,
                    "type": OrderType.TAKE_PROFIT.value,
                    "status": OrderStatus.PENDING.value,
                    "created_at": datetime.now(),
                    "profit_percent": profit_percent,
                }
                self.db.create_order(db_order_data)

            return {
                "success": True,
                "order_id": order_id,
                "tp_type": TakeProfitType.PERCENTAGE.value,
                "target_price": target_price,
                "profit_percent": profit_percent,
                "message": f"Percentage take-profit created at {profit_percent}% ({target_price:.4f})",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_basic_tp(self, order_data: Dict) -> Dict[str, Any]:
        """Create a basic take-profit order."""
        try:
            target_price = float(order_data.get("price", 0))
            if target_price <= 0:
                return {"success": False, "error": "Invalid target price"}

            order_id = f"basic_tp_{int(time.time())}"

            if self.db:
                db_order_data = {
                    **order_data,
                    "id": order_id,
                    "type": OrderType.TAKE_PROFIT.value,
                    "status": OrderStatus.PENDING.value,
                    "created_at": datetime.now(),
                }
                self.db.create_order(db_order_data)

            return {
                "success": True,
                "order_id": order_id,
                "tp_type": TakeProfitType.BASIC.value,
                "target_price": target_price,
                "message": f"Basic take-profit created at {target_price}",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_take_profit_triggers(self) -> List[Dict]:
        """Check all take-profit orders for trigger conditions."""
        triggered_orders = []

        try:
            if not self.db:
                return triggered_orders

            # Get all pending take-profit orders
            tp_orders = self.db.get_orders_by_type(OrderType.TAKE_PROFIT.value)

            for order in tp_orders:
                if order["status"] != OrderStatus.PENDING.value:
                    continue

                symbol = order["symbol"]
                current_price = self.get_current_price(symbol)
                if not current_price:
                    continue

                order_id = order["id"]
                tp_type = order.get("tp_type", TakeProfitType.BASIC.value)

                # Check different TP types
                if tp_type == TakeProfitType.LADDER.value:
                    triggered_levels = self.ladder_manager.check_ladder_triggers(
                        order_id, current_price
                    )
                    if triggered_levels:
                        for level in triggered_levels:
                            triggered_orders.append(
                                {
                                    "order": order,
                                    "trigger_type": "ladder_level",
                                    "level_info": level,
                                    "current_price": current_price,
                                }
                            )

                elif tp_type == TakeProfitType.TRAILING.value:
                    (
                        should_trigger,
                        trigger_price,
                        status,
                    ) = self.trailing_manager.update_trailing_profit(
                        order_id, current_price
                    )
                    if should_trigger:
                        triggered_orders.append(
                            {
                                "order": order,
                                "trigger_type": "trailing_profit",
                                "trigger_price": trigger_price,
                                "status": status,
                                "current_price": current_price,
                            }
                        )

                else:  # Basic, percentage, etc.
                    target_price = float(order.get("price", 0))
                    should_trigger = False

                    if order["side"].upper() == "SELL":  # Long position
                        should_trigger = current_price >= target_price
                    else:  # Short position
                        should_trigger = current_price <= target_price

                    if should_trigger:
                        triggered_orders.append(
                            {
                                "order": order,
                                "trigger_type": "basic_profit",
                                "target_price": target_price,
                                "current_price": current_price,
                            }
                        )

        except Exception as e:
            print(f"Error checking take-profit triggers: {e}")

        return triggered_orders

    def get_take_profit_summary(self) -> Dict[str, Any]:
        """Get summary of all take-profit orders."""
        try:
            if not self.db:
                return {"error": "Database not available"}

            tp_orders = self.db.get_orders_by_type(OrderType.TAKE_PROFIT.value)

            summary = {
                "total_tp_orders": len(tp_orders),
                "pending_orders": 0,
                "triggered_orders": 0,
                "tp_types": {},
                "total_projected_profit": 0.0,
                "orders": [],
            }

            for order in tp_orders:
                tp_type = order.get("tp_type", TakeProfitType.BASIC.value)

                # Count by type
                if tp_type not in summary["tp_types"]:
                    summary["tp_types"][tp_type] = 0
                summary["tp_types"][tp_type] += 1

                # Count by status
                if order["status"] == OrderStatus.PENDING.value:
                    summary["pending_orders"] += 1
                else:
                    summary["triggered_orders"] += 1

                # Add order info
                order_info = {
                    "id": order["id"][:8],
                    "symbol": order["symbol"],
                    "type": tp_type,
                    "status": order["status"],
                    "created": order["created_at"],
                }

                # Add type-specific info
                if tp_type == TakeProfitType.LADDER.value:
                    ladder_status = self.ladder_manager.get_ladder_status(order["id"])
                    if ladder_status:
                        order_info["completion_pct"] = ladder_status["completion_pct"]
                        order_info["realized_profit"] = ladder_status["realized_profit"]
                        summary["total_projected_profit"] += ladder_status[
                            "realized_profit"
                        ]

                elif tp_type == TakeProfitType.TRAILING.value:
                    trailing_data = self.trailing_manager.trailing_data.get(order["id"])
                    if trailing_data:
                        order_info["max_profit_pct"] = trailing_data.get(
                            "max_profit_pct", 0
                        )
                        order_info["current_trigger"] = trailing_data.get(
                            "current_trigger", 0
                        )

                summary["orders"].append(order_info)

            return summary

        except Exception as e:
            return {"error": str(e)}


# Global take-profit engine
_take_profit_engine = None


def get_take_profit_engine(db_path: Optional[str] = None) -> TakeProfitEngine:
    """Get the global take-profit engine instance."""
    global _take_profit_engine
    if _take_profit_engine is None:
        _take_profit_engine = TakeProfitEngine(db_path)
    return _take_profit_engine


if __name__ == "__main__":
    # Test the take-profit engine
    engine = get_take_profit_engine()

    print("Advanced Take-Profit Engine Test")
    print("=" * 40)

    # Test ladder take-profit
    ladder_order = {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "quantity": 1.0,
        "entry_price": 45000,
        "profit_levels": [46000, 47000, 48000, 49000],
        "scaling_strategy": ScalingStrategy.EQUAL_PARTS.value,
        "tp_type": TakeProfitType.LADDER.value,
    }

    result = engine.create_take_profit_order(ladder_order)
    print(f"Ladder TP: {result}")

    # Test trailing take-profit
    trailing_order = {
        "symbol": "ETHUSDT",
        "side": "SELL",
        "quantity": 5.0,
        "entry_price": 3000,
        "trailing_percent": 3.0,
        "min_profit_pct": 2.0,
        "tp_type": TakeProfitType.TRAILING.value,
    }

    result = engine.create_take_profit_order(trailing_order)
    print(f"Trailing TP: {result}")

    # Test Fibonacci take-profit
    fib_order = {
        "symbol": "ADAUSDT",
        "side": "SELL",
        "quantity": 1000,
        "entry_price": 0.5,
        "target_price": 0.8,
        "tp_type": TakeProfitType.FIBONACCI.value,
    }

    result = engine.create_take_profit_order(fib_order)
    print(f"Fibonacci TP: {result}")

    # Check triggers
    triggered = engine.check_take_profit_triggers()
    print(f"Triggered Orders: {len(triggered)}")

    # Get summary
    summary = engine.get_take_profit_summary()
    print(f"Summary: {summary}")
