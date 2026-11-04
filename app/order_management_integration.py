#!/usr/bin/env python3
"""
PowerTrader AI - Order Management Integration
============================================

Integration module that connects the new order management system with
the existing PowerTrader architecture. Provides seamless integration
with pt_hub.py GUI and existing trading logic.
"""

import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

# Add the current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from order_management_db import (
        OrderManagementDB,
        PowerTraderOrderIntegration,
        close_order_db,
        get_order_db,
    )
    from order_management_models import (
        ConditionOperator,
        ConditionType,
        Notification,
        NotificationType,
        Order,
        OrderCondition,
        OrderExecution,
        OrderSide,
        OrderStatus,
        OrderType,
    )

    ORDER_MANAGEMENT_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Order management system not available: {e}")
    ORDER_MANAGEMENT_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class MarketData:
    """Market data structure for order condition evaluation."""

    symbol: str
    price: float
    volume: float
    timestamp: datetime
    neural_level: Optional[int] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None


class OrderManager:
    """Main order management system integration."""

    def __init__(self, database_url: Optional[str] = None):
        """Initialize the order manager."""
        self.is_available = ORDER_MANAGEMENT_AVAILABLE
        self.db = None
        self.integration = None
        self.market_data_cache = {}
        self.condition_check_thread = None
        self.is_monitoring = False
        self._monitoring_stopped = threading.Event()  # wakes the loop on stop
        self.update_callbacks = []

        if self.is_available:
            try:
                self.db = get_order_db(database_url)
                self.integration = PowerTraderOrderIntegration(self.db)
                logger.info("Order management system initialized")
            except Exception as e:
                logger.error(f"Failed to initialize order management: {e}")
                self.is_available = False

    def start_monitoring(self, check_interval: int = 5):
        """Start the condition monitoring thread."""
        if not self.is_available:
            logger.warning("Order management not available")
            return False

        if self.is_monitoring:
            logger.warning("Monitoring already started")
            return True

        self.is_monitoring = True
        self._monitoring_stopped.clear()
        self.condition_check_thread = threading.Thread(
            target=self._condition_monitoring_loop, args=(check_interval,), daemon=True
        )
        self.condition_check_thread.start()
        logger.info("Started order condition monitoring")
        return True

    def stop_monitoring(self):
        """Stop the condition monitoring thread."""
        if self.is_monitoring:
            self.is_monitoring = False
            self._monitoring_stopped.set()  # no waiting out check_interval
            if self.condition_check_thread:
                self.condition_check_thread.join(timeout=10)
            logger.info("Stopped order condition monitoring")

    def _condition_monitoring_loop(self, check_interval: int):
        """Main monitoring loop for order conditions."""
        while self.is_monitoring:
            try:
                if self.market_data_cache:
                    # Check conditions against current market data
                    triggered_orders = self.db.check_and_update_conditions(
                        self.market_data_cache
                    )

                    if triggered_orders:
                        for order in triggered_orders:
                            self._handle_triggered_order(order)

                    # Clean up old market data
                    self._cleanup_old_market_data()

                self._monitoring_stopped.wait(check_interval)

            except Exception as e:
                logger.error(f"Error in condition monitoring: {e}")
                self._monitoring_stopped.wait(check_interval)

    def _handle_triggered_order(self, order: Dict):
        """Handle an order that has been triggered."""
        try:
            logger.info(f"Order triggered: {order.id} - {order.symbol}")

            # Update order status to submitted (ready for execution)
            self.db.update_order_status(order.id, OrderStatus.SUBMITTED)

            # Notify callbacks about triggered order
            for callback in self.update_callbacks:
                try:
                    callback("order_triggered", order)
                except Exception as e:
                    logger.error(f"Error in callback: {e}")

        except Exception as e:
            logger.error(f"Error handling triggered order {order.id}: {e}")

    def _cleanup_old_market_data(self, max_age_seconds: int = 300):
        """Remove old market data from cache."""
        current_time = datetime.utcnow()
        cutoff_time = current_time - timedelta(seconds=max_age_seconds)

        symbols_to_remove = []
        for symbol, data in self.market_data_cache.items():
            if isinstance(data, dict) and "timestamp" in data:
                data_time = datetime.fromisoformat(
                    data["timestamp"].replace("Z", "+00:00")
                )
                if data_time < cutoff_time:
                    symbols_to_remove.append(symbol)

        for symbol in symbols_to_remove:
            del self.market_data_cache[symbol]

    def update_market_data(
        self,
        symbol: str,
        price: float,
        volume: float = 0,
        neural_level: Optional[int] = None,
        **kwargs,
    ):
        """Update market data for condition evaluation."""
        if not self.is_available:
            return

        market_data = {
            "symbol": symbol.upper(),
            "price": price,
            "volume": volume,
            "neural_level": neural_level,
            "timestamp": datetime.utcnow().isoformat(),
            **kwargs,
        }

        self.market_data_cache[symbol.upper()] = market_data

    def create_dca_order(
        self,
        symbol: str,
        quantity: Decimal,
        dca_stage: int,
        neural_level: int,
        price: Optional[Decimal] = None,
    ) -> Optional[str]:
        """Create a DCA order with neural level condition."""
        if not self.is_available:
            logger.warning("Order management not available for DCA order creation")
            return None

        try:
            order_id = self.integration.create_dca_order(
                symbol, quantity, dca_stage, neural_level
            )
            if order_id and price:
                # Update the order with price (would need additional method)
                pass

            logger.info(f"Created DCA order: {order_id} for {symbol} stage {dca_stage}")
            return order_id
        except Exception as e:
            logger.error(f"Failed to create DCA order: {e}")
            return None

    def create_stop_loss_order(
        self,
        symbol: str,
        quantity: Decimal,
        stop_price: Decimal,
        limit_price: Optional[Decimal] = None,
    ) -> Optional[str]:
        """Create a stop loss order."""
        if not self.is_available:
            return None

        try:
            # OrderType has no STOP_LOSS: naming it raised, so a stop without a
            # limit price was never created
            order_type = OrderType.STOP if limit_price is None else OrderType.STOP_LIMIT

            order = self.db.create_order(
                symbol=symbol,
                order_type=order_type,
                side=OrderSide.SELL,
                quantity=quantity,
                price=limit_price,
                stop_price=stop_price,
                tag="STOP_LOSS",
            )

            # Add price condition
            self.db.add_condition_to_order(
                order.id,
                ConditionType.PRICE,
                ConditionOperator.LTE,
                stop_price,
                symbol=symbol,
            )

            logger.info(f"Created stop loss order: {order.id} for {symbol}")
            return order.id

        except Exception as e:
            logger.error(f"Failed to create stop loss order: {e}")
            return None

    def create_take_profit_order(
        self, symbol: str, quantity: Decimal, target_price: Decimal
    ) -> Optional[str]:
        """Create a take profit order."""
        if not self.is_available:
            return None

        try:
            order = self.db.create_order(
                symbol=symbol,
                order_type=OrderType.LIMIT,
                side=OrderSide.SELL,
                quantity=quantity,
                price=target_price,
                tag="TAKE_PROFIT",
            )

            # Add price condition
            self.db.add_condition_to_order(
                order.id,
                ConditionType.PRICE,
                ConditionOperator.GTE,
                target_price,
                symbol=symbol,
            )

            logger.info(f"Created take profit order: {order.id} for {symbol}")
            return order.id

        except Exception as e:
            logger.error(f"Failed to create take profit order: {e}")
            return None

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get active orders as dictionaries."""
        if not self.is_available:
            return []

        try:
            if symbol:
                return self.db.get_active_orders_for_symbol(symbol)
            else:
                # Get all active orders
                with self.db.get_session() as session:
                    orders = (
                        session.query(Order)
                        .filter(
                            Order.status.in_(
                                [
                                    OrderStatus.PENDING,
                                    OrderStatus.SUBMITTED,
                                    OrderStatus.PARTIAL,
                                ]
                            )
                        )
                        .all()
                    )

                    # Convert to dictionaries
                    result = []
                    for order in orders:
                        order_dict = {
                            "id": str(order.id),  # Convert UUID to string
                            "symbol": order.symbol,
                            "order_type": order.order_type,
                            "side": order.side,
                            "quantity": order.quantity,
                            "price": order.price,
                            "stop_price": order.stop_price,
                            "status": order.status,
                            "created_at": order.created_at,
                            "conditions": [],
                        }

                        # Load conditions explicitly
                        for condition in order.conditions:
                            cond_dict = {
                                "condition_type": condition.condition_type,
                                "operator": condition.operator,
                                "target_value": condition.target_value,
                                "is_met": condition.is_met,
                            }
                            order_dict["conditions"].append(cond_dict)

                        result.append(order_dict)

                    return result
        except Exception as e:
            logger.error(f"Failed to get active orders: {e}")
            return []

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if not self.is_available:
            return False

        try:
            success = self.db.cancel_order(order_id)
            if success:
                logger.info(f"Cancelled order: {order_id}")

                # Notify callbacks
                for callback in self.update_callbacks:
                    try:
                        callback("order_cancelled", order_id)
                    except Exception as e:
                        logger.error(f"Error in callback: {e}")

            return success

        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def get_order_history(
        self, symbol: Optional[str] = None, limit: int = 100
    ) -> List[Dict]:
        """Get order history."""
        if not self.is_available:
            return []

        try:
            return self.db.get_order_history(symbol, limit)
        except Exception as e:
            logger.error(f"Failed to get order history: {e}")
            return []

    def get_unread_notifications(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get unread notifications as dictionaries."""
        if not self.is_available:
            return []

        try:
            return self.db.get_unread_notifications(limit=limit)
        except Exception as e:
            logger.error(f"Failed to get notifications: {e}")
            return []

    def mark_notification_read(self, notification_id: str) -> bool:
        """Mark a notification as read."""
        if not self.is_available:
            return False

        try:
            return self.db.mark_notification_read(notification_id)
        except Exception as e:
            logger.error(f"Failed to mark notification read: {e}")
            return False

    def add_update_callback(self, callback: Callable):
        """Add a callback for order updates."""
        self.update_callbacks.append(callback)

    def remove_update_callback(self, callback: Callable):
        """Remove an update callback."""
        if callback in self.update_callbacks:
            self.update_callbacks.remove(callback)

    def get_performance_stats(
        self, symbol: Optional[str] = None, days: int = 30
    ) -> Dict[str, Any]:
        """Get performance statistics."""
        if not self.is_available:
            return {}

        try:
            return self.db.get_performance_stats(symbol, days)
        except Exception as e:
            logger.error(f"Failed to get performance stats: {e}")
            return {}


class PowerTraderOrderManagerAdapter:
    """Adapter to integrate OrderManager with existing PowerTrader systems."""

    def __init__(self, order_manager: OrderManager):
        """Initialize the adapter."""
        self.order_manager = order_manager
        self.logger = logging.getLogger(f"{__name__}.Adapter")
        self._connected_systems = {}

    def connect_neural_signal_system(self, neural_signal_callback: Callable):
        """Connect to PowerTrader's neural signal system."""
        self._connected_systems["neural_signals"] = neural_signal_callback
        self.logger.info("Connected to neural signal system")

    def connect_price_feed(self, price_feed_callback: Callable):
        """Connect to PowerTrader's price feed system."""
        self._connected_systems["price_feed"] = price_feed_callback
        self.logger.info("Connected to price feed system")

    def connect_position_manager(self, position_manager_callback: Callable):
        """Connect to PowerTrader's position management system."""
        self._connected_systems["position_manager"] = position_manager_callback
        self.logger.info("Connected to position manager")

    def process_powertrader_signal(self, symbol: str, signal_data: Dict[str, Any]):
        """Process signals from PowerTrader systems."""
        try:
            # Extract relevant data
            price = signal_data.get("price", 0)
            neural_level = signal_data.get("neural_level", 0)
            volume = signal_data.get("volume", 0)

            # Update market data for order condition evaluation
            self.order_manager.update_market_data(
                symbol=symbol,
                price=price,
                volume=volume,
                neural_level=neural_level,
                **signal_data,
            )

            # Check if this triggers any DCA stage logic
            if neural_level > 0:
                self._check_dca_triggers(symbol, neural_level, signal_data)

        except Exception as e:
            self.logger.error(f"Error processing PowerTrader signal: {e}")

    def _check_dca_triggers(
        self, symbol: str, neural_level: int, signal_data: Dict[str, Any]
    ):
        """Check if neural level changes should trigger DCA orders."""
        # This would integrate with existing PowerTrader DCA logic
        # For now, just log the event
        self.logger.debug(f"Neural level {neural_level} for {symbol}: {signal_data}")

    def create_powertrader_orders_from_existing_logic(
        self, trades_data: List[Dict[str, Any]]
    ):
        """Create order management entries from existing PowerTrader trade data."""
        for trade in trades_data:
            try:
                symbol = trade.get("symbol", "")
                if not symbol:
                    continue

                # Convert existing trade to order management system
                order_type = OrderType.MARKET
                side = (
                    OrderSide.BUY
                    if trade.get("side", "").upper() == "BUY"
                    else OrderSide.SELL
                )
                quantity = Decimal(str(trade.get("quantity", 0)))
                price = (
                    Decimal(str(trade.get("price", 0))) if trade.get("price") else None
                )

                if quantity > 0:
                    order_id = self.order_manager.db.create_order(
                        symbol=symbol,
                        order_type=order_type,
                        side=side,
                        quantity=quantity,
                        price=price,
                        tag=trade.get("tag", "POWERTRADER_IMPORT"),
                    )

                    self.logger.debug(
                        f"Created order from PowerTrader trade: {order_id.id}"
                    )

            except Exception as e:
                self.logger.error(f"Error creating order from trade data: {e}")


# Global order manager instance
_global_order_manager: Optional[OrderManager] = None


def shutdown_order_management() -> None:
    """Stop the global order manager's monitoring and close its database, so the
    next ``get_global_order_manager`` starts afresh (and an SQLite file it held
    open is released)."""
    global _global_order_manager
    if _global_order_manager is not None:
        _global_order_manager.stop_monitoring()
        _global_order_manager = None
    if ORDER_MANAGEMENT_AVAILABLE:
        close_order_db()


def get_global_order_manager(database_url: Optional[str] = None) -> OrderManager:
    """Get or create the global order manager instance."""
    global _global_order_manager
    if _global_order_manager is None:
        _global_order_manager = OrderManager(database_url)
    return _global_order_manager


def initialize_order_management_for_powertrader(
    database_url: Optional[str] = None, start_monitoring: bool = True
) -> OrderManager:
    """Initialize order management system for PowerTrader integration."""
    try:
        # Initialize database if needed
        if ORDER_MANAGEMENT_AVAILABLE:
            try:
                # Try importing from current directory first
                import os
                import sys

                parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if parent_dir not in sys.path:
                    sys.path.insert(0, parent_dir)

                from migrations import initialize_order_management_database

                db_path = None
                if database_url and database_url.startswith("sqlite:///"):
                    db_path = database_url[10:]  # Remove 'sqlite:///' prefix

                if not initialize_order_management_database(db_path):
                    logger.error("Failed to initialize order management database")
                    return OrderManager()  # Return disabled manager
            except ImportError as e:
                logger.warning(f"Could not import migrations module: {e}")
                # Continue without database initialization
        # Create order manager
        order_manager = get_global_order_manager(database_url)

        if order_manager.is_available and start_monitoring:
            order_manager.start_monitoring()

        logger.info("Order management system initialized for PowerTrader")
        return order_manager

    except Exception as e:
        logger.error(f"Failed to initialize order management for PowerTrader: {e}")
        return OrderManager()  # Return disabled manager


# Helper functions for PowerTrader integration
def create_order_from_powertrader_signal(
    symbol: str, neural_level: int, dca_stage: int, quantity: float
) -> Optional[str]:
    """Helper to create orders from PowerTrader neural signals."""
    order_manager = get_global_order_manager()

    if not order_manager.is_available:
        return None

    return order_manager.create_dca_order(
        symbol=symbol,
        quantity=Decimal(str(quantity)),
        dca_stage=dca_stage,
        neural_level=neural_level,
    )


def update_market_data_from_powertrader(
    symbol: str, price: float, neural_level: Optional[int] = None, **kwargs
):
    """Helper to update market data from PowerTrader systems."""
    order_manager = get_global_order_manager()
    order_manager.update_market_data(symbol, price, neural_level=neural_level, **kwargs)


def get_order_notifications_for_gui() -> List[Dict[str, Any]]:
    """Get formatted notifications for GUI display."""
    order_manager = get_global_order_manager()

    if not order_manager.is_available:
        return []

    notifications = order_manager.get_unread_notifications()

    return [
        {
            "id": notif.id,
            "title": notif.title,
            "message": notif.message,
            "type": notif.notification_type.value,
            "order_id": notif.order_id,
            "created_at": notif.created_at,
            "is_read": notif.is_read,
        }
        for notif in notifications
    ]


if __name__ == "__main__":
    # Test the order management integration
    import logging

    logging.basicConfig(level=logging.INFO)

    # Initialize order management
    order_manager = initialize_order_management_for_powertrader()

    if order_manager.is_available:
        print("Order management system is available")

        # Test creating an order
        order_id = order_manager.create_dca_order(
            symbol="BTCUSDT", quantity=Decimal("0.001"), dca_stage=1, neural_level=7
        )

        if order_id:
            print(f"Created test order: {order_id}")

            # Test updating market data
            order_manager.update_market_data("BTCUSDT", 45000.0, neural_level=8)

            # Check active orders
            active_orders = order_manager.get_active_orders("BTCUSDT")
            print(f"Active orders for BTCUSDT: {len(active_orders)}")

    else:
        print("Order management system is not available")
