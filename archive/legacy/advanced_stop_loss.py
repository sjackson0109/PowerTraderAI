"""
Advanced Stop-Loss Order Types
Implements trailing stops, percentage-based stops, and conditional stop-loss orders.
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

    STOP_LOSS_AVAILABLE = True
except ImportError:
    STOP_LOSS_AVAILABLE = False


class StopLossType(Enum):
    """Types of stop-loss orders."""

    BASIC = "basic"  # Simple stop at fixed price
    TRAILING = "trailing"  # Follows price with fixed distance
    PERCENTAGE = "percentage"  # Percentage-based stop
    ATR_TRAILING = "atr_trailing"  # Trails using ATR (Average True Range)
    CONDITIONAL = "conditional"  # Multi-condition stop
    TIME_BASED = "time_based"  # Stop with time constraints
    VOLUME_WEIGHTED = "volume_weighted"  # Volume-weighted stop


class TrailingStopManager:
    """Manages trailing stop-loss orders."""

    def __init__(self, price_provider):
        self.price_provider = price_provider
        self.trailing_data = {}  # order_id -> trailing info

    def initialize_trailing_stop(self, order_id: str, order_data: Dict) -> bool:
        """Initialize a trailing stop-loss order."""
        try:
            symbol = order_data["symbol"]
            side = order_data["side"]
            trailing_amount = float(order_data.get("trailing_amount", 0))
            trailing_percent = float(order_data.get("trailing_percent", 0))

            current_price = self.price_provider.get_current_price(symbol)
            if not current_price:
                return False

            # Determine initial stop price based on side
            if side.upper() == "SELL":  # Long position protection
                if trailing_percent > 0:
                    initial_stop = current_price * (1 - trailing_percent / 100)
                else:
                    initial_stop = current_price - trailing_amount
                peak_price = current_price
            else:  # Short position protection
                if trailing_percent > 0:
                    initial_stop = current_price * (1 + trailing_percent / 100)
                else:
                    initial_stop = current_price + trailing_amount
                peak_price = current_price

            self.trailing_data[order_id] = {
                "symbol": symbol,
                "side": side,
                "current_stop": initial_stop,
                "peak_price": peak_price,
                "trailing_amount": trailing_amount,
                "trailing_percent": trailing_percent,
                "last_update": datetime.now(),
                "trigger_count": 0,
            }

            return True

        except Exception as e:
            print(f"Error initializing trailing stop: {e}")
            return False

    def update_trailing_stop(
        self, order_id: str, current_price: float
    ) -> Tuple[bool, float]:
        """Update trailing stop and return (should_trigger, current_stop_price)."""
        try:
            if order_id not in self.trailing_data:
                return False, 0.0

            data = self.trailing_data[order_id]
            side = data["side"]
            trailing_amount = data["trailing_amount"]
            trailing_percent = data["trailing_percent"]

            # Update peak price and stop level
            if side.upper() == "SELL":  # Long position
                if current_price > data["peak_price"]:
                    data["peak_price"] = current_price

                    # Calculate new stop price
                    if trailing_percent > 0:
                        new_stop = current_price * (1 - trailing_percent / 100)
                    else:
                        new_stop = current_price - trailing_amount

                    # Only move stop up (tighten)
                    if new_stop > data["current_stop"]:
                        data["current_stop"] = new_stop
                        data["last_update"] = datetime.now()

                # Check if stop is triggered
                should_trigger = current_price <= data["current_stop"]

            else:  # Short position
                if current_price < data["peak_price"]:
                    data["peak_price"] = current_price

                    # Calculate new stop price
                    if trailing_percent > 0:
                        new_stop = current_price * (1 + trailing_percent / 100)
                    else:
                        new_stop = current_price + trailing_amount

                    # Only move stop down (tighten)
                    if new_stop < data["current_stop"]:
                        data["current_stop"] = new_stop
                        data["last_update"] = datetime.now()

                # Check if stop is triggered
                should_trigger = current_price >= data["current_stop"]

            if should_trigger:
                data["trigger_count"] += 1

            return should_trigger, data["current_stop"]

        except Exception as e:
            print(f"Error updating trailing stop: {e}")
            return False, 0.0

    def get_trailing_info(self, order_id: str) -> Optional[Dict]:
        """Get current trailing stop information."""
        return self.trailing_data.get(order_id)

    def remove_trailing_stop(self, order_id: str):
        """Remove trailing stop data."""
        self.trailing_data.pop(order_id, None)


class PercentageStopManager:
    """Manages percentage-based stop-loss orders."""

    def __init__(self, price_provider):
        self.price_provider = price_provider

    def calculate_stop_price(
        self, entry_price: float, stop_percent: float, side: str
    ) -> float:
        """Calculate stop price based on percentage from entry."""
        try:
            if side.upper() == "SELL":  # Long position
                return entry_price * (1 - stop_percent / 100)
            else:  # Short position
                return entry_price * (1 + stop_percent / 100)
        except:
            return 0.0

    def is_stop_triggered(
        self, current_price: float, stop_price: float, side: str
    ) -> bool:
        """Check if percentage stop is triggered."""
        try:
            if side.upper() == "SELL":
                return current_price <= stop_price
            else:
                return current_price >= stop_price
        except:
            return False


class ATRTrailingStopManager:
    """Manages ATR (Average True Range) based trailing stops."""

    def __init__(self, price_provider):
        self.price_provider = price_provider
        self.price_history = {}  # symbol -> list of price data
        self.atr_data = {}  # symbol -> ATR value

    def calculate_atr(self, symbol: str, period: int = 14) -> float:
        """Calculate Average True Range for a symbol."""
        try:
            if symbol not in self.price_history:
                return 0.0

            prices = self.price_history[symbol]
            if len(prices) < period + 1:
                return 0.0

            true_ranges = []
            for i in range(1, len(prices)):
                high = max(prices[i]["high"], prices[i - 1]["close"])
                low = min(prices[i]["low"], prices[i - 1]["close"])
                true_range = high - low
                true_ranges.append(true_range)

            # Calculate ATR as simple moving average of true ranges
            if len(true_ranges) >= period:
                atr = sum(true_ranges[-period:]) / period
                self.atr_data[symbol] = atr
                return atr

            return 0.0

        except Exception as e:
            print(f"Error calculating ATR for {symbol}: {e}")
            return 0.0

    def update_price_data(self, symbol: str, price_data: Dict):
        """Update price history for ATR calculation."""
        try:
            if symbol not in self.price_history:
                self.price_history[symbol] = []

            self.price_history[symbol].append(
                {
                    "timestamp": datetime.now(),
                    "high": price_data.get("high", price_data.get("price", 0)),
                    "low": price_data.get("low", price_data.get("price", 0)),
                    "close": price_data.get("close", price_data.get("price", 0)),
                }
            )

            # Keep only last 100 periods
            if len(self.price_history[symbol]) > 100:
                self.price_history[symbol] = self.price_history[symbol][-100:]

        except Exception as e:
            print(f"Error updating price data for {symbol}: {e}")

    def calculate_atr_stop(
        self, symbol: str, entry_price: float, atr_multiplier: float, side: str
    ) -> float:
        """Calculate ATR-based stop price."""
        try:
            atr = self.calculate_atr(symbol)
            if atr <= 0:
                return 0.0

            stop_distance = atr * atr_multiplier

            if side.upper() == "SELL":  # Long position
                return entry_price - stop_distance
            else:  # Short position
                return entry_price + stop_distance

        except Exception as e:
            print(f"Error calculating ATR stop: {e}")
            return 0.0


class ConditionalStopManager:
    """Manages conditional stop-loss orders with multiple criteria."""

    def __init__(self, price_provider):
        self.price_provider = price_provider

    def evaluate_conditional_stop(
        self, order_data: Dict, market_data: Dict
    ) -> Tuple[bool, str]:
        """Evaluate complex conditional stop criteria."""
        try:
            conditions = order_data.get("conditions", [])
            symbol = order_data["symbol"]
            current_price = market_data.get("price", 0)

            triggered_conditions = []

            for condition in conditions:
                condition_type = condition.get("type")

                # Price-based conditions
                if condition_type == "PRICE_BELOW":
                    if current_price <= float(condition["value"]):
                        triggered_conditions.append(f"Price below {condition['value']}")

                elif condition_type == "PRICE_ABOVE":
                    if current_price >= float(condition["value"]):
                        triggered_conditions.append(f"Price above {condition['value']}")

                # Volume-based conditions
                elif condition_type == "VOLUME_SPIKE":
                    volume_threshold = float(condition["value"])
                    current_volume = market_data.get("volume", 0)
                    avg_volume = market_data.get("avg_volume", current_volume)
                    if current_volume > avg_volume * volume_threshold:
                        triggered_conditions.append(f"Volume spike {volume_threshold}x")

                # Time-based conditions
                elif condition_type == "TIME_AFTER":
                    trigger_time = datetime.fromisoformat(condition["value"])
                    if datetime.now() > trigger_time:
                        triggered_conditions.append(f"Time after {condition['value']}")

                # Technical indicator conditions
                elif condition_type == "RSI_OVERSOLD":
                    rsi = market_data.get("rsi", 50)
                    if rsi <= float(condition["value"]):
                        triggered_conditions.append(f"RSI oversold {rsi}")

                elif condition_type == "RSI_OVERBOUGHT":
                    rsi = market_data.get("rsi", 50)
                    if rsi >= float(condition["value"]):
                        triggered_conditions.append(f"RSI overbought {rsi}")

            # Check if we need all conditions or just one
            require_all = order_data.get("require_all_conditions", True)

            if require_all:
                should_trigger = len(triggered_conditions) == len(conditions)
            else:
                should_trigger = len(triggered_conditions) > 0

            reason = (
                "; ".join(triggered_conditions)
                if triggered_conditions
                else "No conditions met"
            )

            return should_trigger, reason

        except Exception as e:
            print(f"Error evaluating conditional stop: {e}")
            return False, f"Error: {str(e)}"


class AdvancedStopLossEngine:
    """Main engine for managing advanced stop-loss orders."""

    def __init__(self, db_path: Optional[str] = None):
        self.db = OrderManagementDB(db_path) if STOP_LOSS_AVAILABLE else None
        self.trailing_manager = TrailingStopManager(self)
        self.percentage_manager = PercentageStopManager(self)
        self.atr_manager = ATRTrailingStopManager(self)
        self.conditional_manager = ConditionalStopManager(self)

        # Mock price provider for testing
        self.mock_prices = {}

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price (mock implementation)."""
        import random

        base_prices = {"BTCUSDT": 45000, "ETHUSDT": 3000, "ADAUSDT": 0.5}

        base = base_prices.get(symbol, 100)
        # Add some random movement
        return base * (1 + random.uniform(-0.02, 0.02))

    def create_stop_loss_order(self, order_data: Dict) -> Dict[str, Any]:
        """Create an advanced stop-loss order."""
        try:
            stop_type = order_data.get("stop_type", StopLossType.BASIC.value)
            symbol = order_data["symbol"]
            side = order_data["side"]
            quantity = float(order_data["quantity"])

            # Validate order data
            if not symbol or not side or quantity <= 0:
                return {"success": False, "error": "Invalid order parameters"}

            # Set up specific stop-loss type
            if stop_type == StopLossType.TRAILING.value:
                return self._create_trailing_stop(order_data)
            elif stop_type == StopLossType.PERCENTAGE.value:
                return self._create_percentage_stop(order_data)
            elif stop_type == StopLossType.ATR_TRAILING.value:
                return self._create_atr_trailing_stop(order_data)
            elif stop_type == StopLossType.CONDITIONAL.value:
                return self._create_conditional_stop(order_data)
            else:
                return self._create_basic_stop(order_data)

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_trailing_stop(self, order_data: Dict) -> Dict[str, Any]:
        """Create a trailing stop-loss order."""
        try:
            order_id = f"trail_{int(time.time())}"

            if self.trailing_manager.initialize_trailing_stop(order_id, order_data):
                if self.db:
                    db_order_data = {
                        **order_data,
                        "id": order_id,
                        "type": OrderType.STOP_LOSS.value,
                        "status": OrderStatus.PENDING.value,
                        "created_at": datetime.now(),
                    }
                    self.db.create_order(db_order_data)

                return {
                    "success": True,
                    "order_id": order_id,
                    "stop_type": StopLossType.TRAILING.value,
                    "message": "Trailing stop-loss order created",
                }
            else:
                return {"success": False, "error": "Failed to initialize trailing stop"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_percentage_stop(self, order_data: Dict) -> Dict[str, Any]:
        """Create a percentage-based stop-loss order."""
        try:
            entry_price = float(order_data.get("entry_price", 0))
            stop_percent = float(order_data.get("stop_percent", 0))
            side = order_data["side"]

            if entry_price <= 0 or stop_percent <= 0:
                return {
                    "success": False,
                    "error": "Invalid entry price or stop percentage",
                }

            stop_price = self.percentage_manager.calculate_stop_price(
                entry_price, stop_percent, side
            )

            order_id = f"pct_{int(time.time())}"

            if self.db:
                db_order_data = {
                    **order_data,
                    "id": order_id,
                    "price": stop_price,
                    "type": OrderType.STOP_LOSS.value,
                    "status": OrderStatus.PENDING.value,
                    "created_at": datetime.now(),
                    "stop_percent": stop_percent,
                    "entry_price": entry_price,
                }
                self.db.create_order(db_order_data)

            return {
                "success": True,
                "order_id": order_id,
                "stop_type": StopLossType.PERCENTAGE.value,
                "stop_price": stop_price,
                "stop_percent": stop_percent,
                "message": f"Percentage stop-loss created at {stop_percent}% ({stop_price:.4f})",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_atr_trailing_stop(self, order_data: Dict) -> Dict[str, Any]:
        """Create an ATR-based trailing stop-loss order."""
        try:
            symbol = order_data["symbol"]
            entry_price = float(order_data.get("entry_price", 0))
            atr_multiplier = float(order_data.get("atr_multiplier", 2.0))
            side = order_data["side"]

            # Update price data for ATR calculation
            current_price = self.get_current_price(symbol)
            self.atr_manager.update_price_data(symbol, {"price": current_price})

            stop_price = self.atr_manager.calculate_atr_stop(
                symbol, entry_price, atr_multiplier, side
            )

            order_id = f"atr_{int(time.time())}"

            if self.db:
                db_order_data = {
                    **order_data,
                    "id": order_id,
                    "price": stop_price,
                    "type": OrderType.STOP_LOSS.value,
                    "status": OrderStatus.PENDING.value,
                    "created_at": datetime.now(),
                    "atr_multiplier": atr_multiplier,
                }
                self.db.create_order(db_order_data)

            return {
                "success": True,
                "order_id": order_id,
                "stop_type": StopLossType.ATR_TRAILING.value,
                "stop_price": stop_price,
                "atr_multiplier": atr_multiplier,
                "message": f"ATR trailing stop created with {atr_multiplier}x multiplier",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_conditional_stop(self, order_data: Dict) -> Dict[str, Any]:
        """Create a conditional stop-loss order."""
        try:
            conditions = order_data.get("conditions", [])
            if not conditions:
                return {"success": False, "error": "No conditions specified"}

            order_id = f"cond_{int(time.time())}"

            if self.db:
                db_order_data = {
                    **order_data,
                    "id": order_id,
                    "type": OrderType.STOP_LOSS.value,
                    "status": OrderStatus.PENDING.value,
                    "created_at": datetime.now(),
                }
                self.db.create_order(db_order_data)

                # Add conditions to database
                for condition in conditions:
                    condition_data = {
                        "order_id": order_id,
                        "condition_type": condition["type"],
                        "target_value": str(condition["value"]),
                        "created_at": datetime.now(),
                    }
                    self.db.create_order_condition(condition_data)

            return {
                "success": True,
                "order_id": order_id,
                "stop_type": StopLossType.CONDITIONAL.value,
                "conditions_count": len(conditions),
                "message": f"Conditional stop created with {len(conditions)} conditions",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_basic_stop(self, order_data: Dict) -> Dict[str, Any]:
        """Create a basic stop-loss order."""
        try:
            stop_price = float(order_data.get("price", 0))
            if stop_price <= 0:
                return {"success": False, "error": "Invalid stop price"}

            order_id = f"basic_{int(time.time())}"

            if self.db:
                db_order_data = {
                    **order_data,
                    "id": order_id,
                    "type": OrderType.STOP_LOSS.value,
                    "status": OrderStatus.PENDING.value,
                    "created_at": datetime.now(),
                }
                self.db.create_order(db_order_data)

            return {
                "success": True,
                "order_id": order_id,
                "stop_type": StopLossType.BASIC.value,
                "stop_price": stop_price,
                "message": f"Basic stop-loss created at {stop_price}",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_stop_triggers(self) -> List[Dict]:
        """Check all stop-loss orders for trigger conditions."""
        triggered_orders = []

        try:
            if not self.db:
                return triggered_orders

            # Get all pending stop-loss orders
            stop_orders = self.db.get_orders_by_type(OrderType.STOP_LOSS.value)

            for order in stop_orders:
                if order["status"] != OrderStatus.PENDING.value:
                    continue

                symbol = order["symbol"]
                current_price = self.get_current_price(symbol)
                if not current_price:
                    continue

                # Check different stop types
                order_id = order["id"]
                stop_type = order.get("stop_type", StopLossType.BASIC.value)

                should_trigger = False
                trigger_reason = ""

                if stop_type == StopLossType.TRAILING.value:
                    (
                        should_trigger,
                        current_stop,
                    ) = self.trailing_manager.update_trailing_stop(
                        order_id, current_price
                    )
                    if should_trigger:
                        trigger_reason = (
                            f"Trailing stop triggered at {current_stop:.4f}"
                        )

                elif stop_type == StopLossType.PERCENTAGE.value:
                    stop_price = float(order.get("price", 0))
                    should_trigger = self.percentage_manager.is_stop_triggered(
                        current_price, stop_price, order["side"]
                    )
                    if should_trigger:
                        trigger_reason = (
                            f"Percentage stop triggered at {stop_price:.4f}"
                        )

                elif stop_type == StopLossType.CONDITIONAL.value:
                    market_data = {
                        "price": current_price,
                        "volume": 1000000,  # Mock data
                        "rsi": 45,  # Mock data
                    }
                    (
                        should_trigger,
                        trigger_reason,
                    ) = self.conditional_manager.evaluate_conditional_stop(
                        order, market_data
                    )

                else:  # Basic stop
                    stop_price = float(order.get("price", 0))
                    if order["side"].upper() == "SELL":
                        should_trigger = current_price <= stop_price
                    else:
                        should_trigger = current_price >= stop_price

                    if should_trigger:
                        trigger_reason = f"Basic stop triggered at {stop_price:.4f}"

                if should_trigger:
                    triggered_orders.append(
                        {
                            "order": order,
                            "trigger_reason": trigger_reason,
                            "current_price": current_price,
                        }
                    )

        except Exception as e:
            print(f"Error checking stop triggers: {e}")

        return triggered_orders

    def get_stop_loss_summary(self) -> Dict[str, Any]:
        """Get summary of all stop-loss orders."""
        try:
            if not self.db:
                return {"error": "Database not available"}

            stop_orders = self.db.get_orders_by_type(OrderType.STOP_LOSS.value)

            summary = {
                "total_stops": len(stop_orders),
                "pending_stops": 0,
                "triggered_stops": 0,
                "stop_types": {},
                "orders": [],
            }

            for order in stop_orders:
                stop_type = order.get("stop_type", StopLossType.BASIC.value)

                # Count by type
                if stop_type not in summary["stop_types"]:
                    summary["stop_types"][stop_type] = 0
                summary["stop_types"][stop_type] += 1

                # Count by status
                if order["status"] == OrderStatus.PENDING.value:
                    summary["pending_stops"] += 1
                else:
                    summary["triggered_stops"] += 1

                # Add order info
                order_info = {
                    "id": order["id"][:8],
                    "symbol": order["symbol"],
                    "type": stop_type,
                    "status": order["status"],
                    "created": order["created_at"],
                }

                # Add type-specific info
                if stop_type == StopLossType.TRAILING.value:
                    trailing_info = self.trailing_manager.get_trailing_info(order["id"])
                    if trailing_info:
                        order_info["current_stop"] = trailing_info["current_stop"]
                        order_info["peak_price"] = trailing_info["peak_price"]

                summary["orders"].append(order_info)

            return summary

        except Exception as e:
            return {"error": str(e)}


# Global stop-loss engine
_stop_loss_engine = None


def get_stop_loss_engine(
    db_path: Optional[str] = None,
) -> AdvancedStopLossEngine:
    """Get the global stop-loss engine instance."""
    global _stop_loss_engine
    if _stop_loss_engine is None:
        _stop_loss_engine = AdvancedStopLossEngine(db_path)
    return _stop_loss_engine


if __name__ == "__main__":
    # Test the stop-loss engine
    engine = get_stop_loss_engine()

    print("Advanced Stop-Loss Engine Test")
    print("=" * 40)

    # Test trailing stop
    trailing_order = {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "quantity": 0.1,
        "trailing_percent": 5.0,
        "stop_type": StopLossType.TRAILING.value,
    }

    result = engine.create_stop_loss_order(trailing_order)
    print(f"Trailing Stop: {result}")

    # Test percentage stop
    pct_order = {
        "symbol": "ETHUSDT",
        "side": "SELL",
        "quantity": 1.0,
        "entry_price": 3000,
        "stop_percent": 10.0,
        "stop_type": StopLossType.PERCENTAGE.value,
    }

    result = engine.create_stop_loss_order(pct_order)
    print(f"Percentage Stop: {result}")

    # Check triggers
    triggered = engine.check_stop_triggers()
    print(f"Triggered Orders: {len(triggered)}")

    # Get summary
    summary = engine.get_stop_loss_summary()
    print(f"Summary: {summary}")
