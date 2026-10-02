"""
Order Execution Engine
Monitors order conditions and automatically executes trades when criteria are met.
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

try:
    from order_management_db import OrderManagementDB
    from order_management_models import (
        ConditionType,
        ExecutionStatus,
        OrderSide,
        OrderStatus,
        OrderType,
    )

    EXECUTION_ENGINE_AVAILABLE = True
except ImportError:
    EXECUTION_ENGINE_AVAILABLE = False


# Mock PowerTrader interface for order execution
class PowerTraderExecutor:
    """Interface to PowerTrader's trading engine for order execution."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.mock_mode = True  # Set to False when integrated with real trading engine

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current market price for a symbol."""
        # Mock implementation - replace with real market data feed
        import random

        if symbol == "BTCUSDT":
            return round(45000 + random.uniform(-5000, 5000), 2)
        elif symbol == "ETHUSDT":
            return round(3000 + random.uniform(-500, 500), 2)
        else:
            return round(100 + random.uniform(-50, 50), 2)

    def execute_market_order(
        self, symbol: str, side: str, quantity: float
    ) -> Dict[str, Any]:
        """Execute a market order through PowerTrader."""
        try:
            current_price = self.get_current_price(symbol)
            if not current_price:
                return {"success": False, "error": "Unable to get market price"}

            # Mock execution - replace with real trading engine call
            execution_id = f"exec_{int(time.time())}"
            fill_price = current_price * (
                1.001 if side.upper() == "BUY" else 0.999
            )  # Simulate slippage

            result = {
                "success": True,
                "execution_id": execution_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "fill_price": fill_price,
                "fill_quantity": quantity,
                "timestamp": datetime.now().isoformat(),
                "fees": quantity * fill_price * 0.001,  # 0.1% fee
            }

            self.logger.info(
                f"Executed {side} {quantity} {symbol} at ${fill_price:.2f}"
            )
            return result

        except Exception as e:
            self.logger.error(f"Order execution failed: {e}")
            return {"success": False, "error": str(e)}

    def execute_limit_order(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> Dict[str, Any]:
        """Execute a limit order through PowerTrader."""
        try:
            # Mock implementation - in reality, this would place a limit order
            order_id = f"limit_{int(time.time())}"

            result = {
                "success": True,
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "status": "PENDING",
                "timestamp": datetime.now().isoformat(),
            }

            self.logger.info(
                f"Placed {side} limit order: {quantity} {symbol} at ${price:.2f}"
            )
            return result

        except Exception as e:
            self.logger.error(f"Limit order placement failed: {e}")
            return {"success": False, "error": str(e)}


class ConditionEvaluator:
    """Evaluates order conditions against current market data."""

    def __init__(self, price_provider: PowerTraderExecutor):
        self.price_provider = price_provider
        self.logger = logging.getLogger(__name__)

    def evaluate_price_condition(
        self,
        symbol: str,
        condition_type: str,
        target_price: float,
        current_price: Optional[float] = None,
    ) -> bool:
        """Evaluate a price-based condition."""
        try:
            if current_price is None:
                current_price = self.price_provider.get_current_price(symbol)

            if current_price is None:
                return False

            if condition_type == "PRICE_ABOVE":
                return current_price > target_price
            elif condition_type == "PRICE_BELOW":
                return current_price < target_price
            elif condition_type == "PRICE_EQUALS":
                # Allow 0.1% tolerance for price equality
                tolerance = target_price * 0.001
                return abs(current_price - target_price) <= tolerance

            return False

        except Exception as e:
            self.logger.error(f"Error evaluating price condition: {e}")
            return False

    def evaluate_percentage_condition(
        self,
        symbol: str,
        condition_type: str,
        reference_price: float,
        percentage: float,
        current_price: Optional[float] = None,
    ) -> bool:
        """Evaluate a percentage-based condition."""
        try:
            if current_price is None:
                current_price = self.price_provider.get_current_price(symbol)

            if current_price is None:
                return False

            price_change = (current_price - reference_price) / reference_price

            if condition_type == "PERCENT_GAIN":
                return price_change >= (percentage / 100)
            elif condition_type == "PERCENT_LOSS":
                return price_change <= -(percentage / 100)

            return False

        except Exception as e:
            self.logger.error(f"Error evaluating percentage condition: {e}")
            return False


class OrderExecutionEngine:
    """Main execution engine that monitors and executes orders."""

    def __init__(self, db_path: Optional[str] = None):
        self.db = OrderManagementDB(db_path)
        self.executor = PowerTraderExecutor()
        self.evaluator = ConditionEvaluator(self.executor)
        self.logger = logging.getLogger(__name__)

        self._monitoring = False
        self._monitor_thread = None
        self._execution_callbacks: List[Callable] = []

        # Execution statistics
        self.stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "conditions_checked": 0,
            "last_execution": None,
        }

        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    def add_execution_callback(self, callback: Callable):
        """Add callback to be notified when orders are executed."""
        self._execution_callbacks.append(callback)

    def _notify_execution(self, order_data: Dict, execution_result: Dict):
        """Notify all callbacks about order execution."""
        for callback in self._execution_callbacks:
            try:
                callback(order_data, execution_result)
            except Exception as e:
                self.logger.error(f"Execution callback error: {e}")

    def start_monitoring(self, check_interval: float = 5.0):
        """Start monitoring orders for execution."""
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitoring_loop, args=(check_interval,), daemon=True
        )
        self._monitor_thread.start()
        self.logger.info("Order execution monitoring started")

    def stop_monitoring(self):
        """Stop monitoring orders."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=10)
        self.logger.info("Order execution monitoring stopped")

    def _monitoring_loop(self, check_interval: float):
        """Main monitoring loop."""
        while self._monitoring:
            try:
                self._check_and_execute_orders()
                time.sleep(check_interval)
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(check_interval * 2)  # Back off on errors

    def _check_and_execute_orders(self):
        """Check all pending orders and execute those with met conditions."""
        try:
            # Get all pending orders
            pending_orders = self.db.get_orders_by_status(OrderStatus.PENDING.value)

            for order in pending_orders:
                self.stats["conditions_checked"] += 1

                if self._should_execute_order(order):
                    self._execute_order(order)

        except Exception as e:
            self.logger.error(f"Error checking orders: {e}")

    def _should_execute_order(self, order: Dict) -> bool:
        """Check if an order should be executed based on its conditions."""
        try:
            symbol = order["symbol"]
            order_type = order["type"]

            # Get current price
            current_price = self.executor.get_current_price(symbol)
            if current_price is None:
                return False

            # Get order conditions
            conditions = self.db.get_order_conditions(order["id"])
            if not conditions:
                # No conditions means execute immediately (market order)
                return order_type == OrderType.MARKET.value

            # Evaluate all conditions
            for condition in conditions:
                condition_type = condition["condition_type"]
                target_value = float(condition["target_value"])

                # Price-based conditions
                if condition_type in ["PRICE_ABOVE", "PRICE_BELOW", "PRICE_EQUALS"]:
                    if not self.evaluator.evaluate_price_condition(
                        symbol, condition_type, target_value, current_price
                    ):
                        return False

                # Percentage-based conditions
                elif condition_type in ["PERCENT_GAIN", "PERCENT_LOSS"]:
                    reference_price = float(
                        condition.get("reference_value", order["price"])
                    )
                    if not self.evaluator.evaluate_percentage_condition(
                        symbol,
                        condition_type,
                        reference_price,
                        target_value,
                        current_price,
                    ):
                        return False

                # Time-based conditions
                elif condition_type == "TIME_AFTER":
                    target_time = datetime.fromisoformat(condition["target_value"])
                    if datetime.now() < target_time:
                        return False

            return True

        except Exception as e:
            self.logger.error(f"Error evaluating order conditions: {e}")
            return False

    def _execute_order(self, order: Dict):
        """Execute an order."""
        try:
            order_id = order["id"]
            symbol = order["symbol"]
            side = order["side"]
            quantity = float(order["quantity"])
            order_type = order["type"]
            price = float(order.get("price", 0))

            self.stats["total_executions"] += 1

            # Execute based on order type
            if order_type == OrderType.MARKET.value:
                result = self.executor.execute_market_order(symbol, side, quantity)
            elif order_type in [
                OrderType.LIMIT.value,
                OrderType.STOP_LOSS.value,
                OrderType.TAKE_PROFIT.value,
            ]:
                result = self.executor.execute_limit_order(
                    symbol, side, quantity, price
                )
            else:
                result = {
                    "success": False,
                    "error": f"Unsupported order type: {order_type}",
                }

            # Record execution
            if result["success"]:
                self._record_successful_execution(order, result)
                self.stats["successful_executions"] += 1
            else:
                self._record_failed_execution(order, result)
                self.stats["failed_executions"] += 1

            # Update order status
            new_status = (
                OrderStatus.FILLED.value
                if result["success"]
                else OrderStatus.REJECTED.value
            )
            self.db.update_order_status(order_id, new_status)

            # Notify callbacks
            self._notify_execution(order, result)

            self.stats["last_execution"] = datetime.now().isoformat()

        except Exception as e:
            self.logger.error(f"Error executing order {order.get('id')}: {e}")
            self.stats["failed_executions"] += 1

    def _record_successful_execution(self, order: Dict, result: Dict):
        """Record a successful order execution."""
        try:
            execution_data = {
                "order_id": order["id"],
                "execution_id": result.get("execution_id", f"exec_{int(time.time())}"),
                "fill_price": result.get("fill_price", 0),
                "fill_quantity": result.get("fill_quantity", order["quantity"]),
                "fees": result.get("fees", 0),
                "status": ExecutionStatus.COMPLETED.value,
                "execution_time": datetime.now(),
                "notes": f"Successfully executed {order['type']} order",
            }

            self.db.create_order_execution(execution_data)

            # Create notification
            self.db.create_notification(
                {
                    "type": "EXECUTION_SUCCESS",
                    "message": f"Order {order['id'][:8]} executed: {result.get('fill_quantity', 0)} {order['symbol']} at ${result.get('fill_price', 0):.2f}",
                    "order_id": order["id"],
                }
            )

            self.logger.info(f"Successfully executed order {order['id'][:8]}")

        except Exception as e:
            self.logger.error(f"Error recording successful execution: {e}")

    def _record_failed_execution(self, order: Dict, result: Dict):
        """Record a failed order execution."""
        try:
            execution_data = {
                "order_id": order["id"],
                "execution_id": f"failed_{int(time.time())}",
                "fill_price": 0,
                "fill_quantity": 0,
                "fees": 0,
                "status": ExecutionStatus.FAILED.value,
                "execution_time": datetime.now(),
                "notes": f"Execution failed: {result.get('error', 'Unknown error')}",
            }

            self.db.create_order_execution(execution_data)

            # Create notification
            self.db.create_notification(
                {
                    "type": "EXECUTION_FAILED",
                    "message": f"Order {order['id'][:8]} failed: {result.get('error', 'Unknown error')}",
                    "order_id": order["id"],
                }
            )

            self.logger.warning(
                f"Failed to execute order {order['id'][:8]}: {result.get('error')}"
            )

        except Exception as e:
            self.logger.error(f"Error recording failed execution: {e}")

    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution engine statistics."""
        return {
            **self.stats,
            "success_rate": (
                self.stats["successful_executions"]
                / max(1, self.stats["total_executions"])
            )
            * 100,
            "monitoring_active": self._monitoring,
            "engine_status": "RUNNING" if self._monitoring else "STOPPED",
        }

    def manual_execution_check(self, order_id: str) -> Dict[str, Any]:
        """Manually check and potentially execute a specific order."""
        try:
            order = self.db.get_order_by_id(order_id)
            if not order:
                return {"success": False, "error": "Order not found"}

            if order["status"] != OrderStatus.PENDING.value:
                return {"success": False, "error": "Order is not pending"}

            if self._should_execute_order(order):
                self._execute_order(order)
                return {"success": True, "message": "Order executed"}
            else:
                return {"success": False, "message": "Order conditions not met"}

        except Exception as e:
            return {"success": False, "error": str(e)}


# Global execution engine instance
_execution_engine = None


def get_execution_engine(db_path: Optional[str] = None) -> OrderExecutionEngine:
    """Get the global execution engine instance."""
    global _execution_engine
    if _execution_engine is None:
        _execution_engine = OrderExecutionEngine(db_path)
    return _execution_engine


if __name__ == "__main__":
    # Test the execution engine
    engine = get_execution_engine()

    print("Order Execution Engine Test")
    print("=" * 40)

    # Start monitoring
    engine.start_monitoring(check_interval=2.0)

    try:
        # Run for 30 seconds
        time.sleep(30)

        # Show stats
        stats = engine.get_execution_stats()
        print("\nExecution Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

    except KeyboardInterrupt:
        print("\nStopping execution engine...")
    finally:
        engine.stop_monitoring()
