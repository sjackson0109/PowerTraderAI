#!/usr/bin/env python3
"""
PowerTrader AI - Order Management Database Manager
==================================================

Database manager for advanced order management system that integrates with
the existing PowerTrader architecture and provides ORM operations.
"""

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from order_management_models import (
    Base,
    ConditionOperator,
    ConditionType,
    Notification,
    NotificationType,
    Order,
    OrderCondition,
    OrderExecution,
    OrderSide,
    OrderStatus,
    OrderTemplate,
    OrderType,
    create_notification,
    create_order_management_tables,
    get_active_orders,
    get_orders_with_unmet_conditions,
)
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Configure logging
logger = logging.getLogger(__name__)


class OrderManagementDB:
    """Database manager for order management system."""

    def __init__(self, database_url: Optional[str] = None):
        """Initialize the database manager."""
        if database_url is None:
            # Default to SQLite for development
            import pt_paths

            db_path = pt_paths.data_file("order_management.db")
            database_url = f"sqlite:///{db_path}"

        self.database_url = database_url
        self.engine = None
        self.SessionLocal = None
        self._setup_database()

    def _setup_database(self):
        """Set up database engine and session factory."""
        try:
            # Configure engine based on database type
            if self.database_url.startswith("sqlite"):
                self.engine = create_engine(
                    self.database_url,
                    poolclass=StaticPool,
                    connect_args={"check_same_thread": False},
                    echo=False,  # Set to True for SQL debugging
                )

                # Enable WAL mode for better concurrency in SQLite
                @event.listens_for(self.engine, "connect")
                def set_sqlite_pragma(dbapi_connection, connection_record):
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                    cursor.execute("PRAGMA temp_store=MEMORY")
                    cursor.execute("PRAGMA mmap_size=268435456")  # 256MB
                    cursor.close()

            else:
                # PostgreSQL or other database
                self.engine = create_engine(
                    self.database_url, pool_pre_ping=True, pool_recycle=300, echo=False
                )

            # Create session factory
            self.SessionLocal = sessionmaker(
                autocommit=False, autoflush=False, bind=self.engine
            )

            # Create tables
            create_order_management_tables(self.engine)

            logger.info(f"Order management database initialized: {self.database_url}")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    @contextmanager
    def get_session(self):
        """Get a database session with automatic cleanup."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    def create_order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        client_order_id: Optional[str] = None,
        tag: Optional[str] = None,
        user_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> Order:
        """Create a new order."""
        with self.get_session() as session:
            order = Order(
                symbol=symbol.upper(),
                order_type=order_type,
                side=side,
                quantity=quantity,
                price=price,
                stop_price=stop_price,
                client_order_id=client_order_id
                or f"PT_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                tag=tag,
                user_id=user_id,
                expires_at=expires_at,
            )

            session.add(order)
            session.flush()  # Get the ID

            # Create notification for new order
            create_notification(
                session,
                order.id,
                NotificationType.ORDER_FILLED,  # Will be updated when actually filled
                f"Order Created: {side.value.upper()} {symbol}",
                f"Created {order_type.value} order for {quantity} {symbol} at {price or 'market price'}",
                user_id=user_id,
            )

            # Refresh the object to ensure all attributes are loaded
            session.refresh(order)

            # Create a detached copy to return
            order_dict = {
                "id": order.id,
                "symbol": order.symbol,
                "order_type": order.order_type,
                "side": order.side,
                "quantity": order.quantity,
                "price": order.price,
                "stop_price": order.stop_price,
                "client_order_id": order.client_order_id,
                "tag": order.tag,
                "user_id": order.user_id,
                "status": order.status,
                "created_at": order.created_at,
                "expires_at": order.expires_at,
            }

            logger.info(f"Created order: {order.id} - {side.value} {quantity} {symbol}")

            # Return a new instance with the same data (detached from session)
            return Order(**order_dict)

    def add_condition_to_order(
        self,
        order_id: str,
        condition_type: ConditionType,
        operator: ConditionOperator,
        target_value: Decimal,
        symbol: Optional[str] = None,
        indicator_name: Optional[str] = None,
    ) -> OrderCondition:
        """Add a condition to an order."""
        with self.get_session() as session:
            condition = OrderCondition(
                order_id=order_id,
                condition_type=condition_type,
                operator=operator,
                target_value=target_value,
                symbol=symbol,
                indicator_name=indicator_name,
            )

            session.add(condition)
            logger.info(
                f"Added condition to order {order_id}: {condition_type.value} {operator.value} {target_value}"
            )
            return condition

    def update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        exchange_order_id: Optional[str] = None,
    ) -> bool:
        """Update order status."""
        with self.get_session() as session:
            order = session.query(Order).filter(Order.id == order_id).first()
            if not order:
                logger.warning(f"Order not found: {order_id}")
                return False

            old_status = order.status
            order.status = status
            order.updated_at = datetime.utcnow()

            if exchange_order_id:
                order.exchange_order_id = exchange_order_id

            if status == OrderStatus.SUBMITTED:
                order.submitted_at = datetime.utcnow()
            elif status in [
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.EXPIRED,
            ]:
                order.filled_at = datetime.utcnow()

            # Create notification for status change
            if old_status != status:
                notification_type = {
                    OrderStatus.FILLED: NotificationType.ORDER_FILLED,
                    OrderStatus.CANCELLED: NotificationType.ORDER_CANCELLED,
                    OrderStatus.EXPIRED: NotificationType.ORDER_EXPIRED,
                }.get(status, NotificationType.ORDER_FILLED)

                create_notification(
                    session,
                    order.id,
                    notification_type,
                    f"Order {status.value.title()}: {order.symbol}",
                    f"Order {order.client_order_id} is now {status.value}",
                    user_id=order.user_id,
                )

            logger.info(
                f"Updated order {order_id} status: {old_status.value} -> {status.value}"
            )
            return True

    def add_execution(
        self,
        order_id: str,
        quantity: Decimal,
        price: Decimal,
        commission: Decimal = Decimal("0"),
        exchange_execution_id: Optional[str] = None,
    ) -> Optional[OrderExecution]:
        """Add an execution to an order."""
        with self.get_session() as session:
            order = session.query(Order).filter(Order.id == order_id).first()
            if not order:
                logger.warning(f"Order not found for execution: {order_id}")
                return None

            execution = OrderExecution(
                order_id=order_id,
                quantity=quantity,
                price=price,
                commission=commission,
                exchange_execution_id=exchange_execution_id,
            )

            session.add(execution)

            # Update order fill information
            order.filled_quantity += quantity

            if order.filled_quantity >= order.quantity:
                order.status = OrderStatus.FILLED
                order.filled_at = datetime.utcnow()
            elif order.filled_quantity > 0:
                order.status = OrderStatus.PARTIAL

            # Calculate average fill price
            total_quantity = sum(exec.quantity for exec in order.executions) + quantity
            total_value = sum(
                exec.quantity * exec.price for exec in order.executions
            ) + (quantity * price)
            order.average_fill_price = (
                total_value / total_quantity if total_quantity > 0 else price
            )

            logger.info(f"Added execution to order {order_id}: {quantity} @ {price}")
            return execution

    def get_active_orders_for_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        """Get all active orders for a symbol as dictionaries."""
        with self.get_session() as session:
            orders = (
                session.query(Order)
                .filter(
                    Order.symbol == symbol.upper(),
                    Order.status.in_(
                        [
                            OrderStatus.PENDING,
                            OrderStatus.SUBMITTED,
                            OrderStatus.PARTIAL,
                        ]
                    ),
                )
                .all()
            )

            # Convert to dictionaries to avoid session issues
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

    def get_orders_pending_conditions(self) -> List[Order]:
        """Get orders with unmet conditions."""
        with self.get_session() as session:
            return get_orders_with_unmet_conditions(session)

    def check_and_update_conditions(self, market_data: Dict[str, Any]) -> List[Order]:
        """Check all pending conditions against market data."""
        triggered_orders = []

        with self.get_session() as session:
            # Get all orders with unmet conditions
            orders = get_orders_with_unmet_conditions(session)

            for order in orders:
                order_triggered = True

                for condition in order.conditions:
                    if condition.is_met:
                        continue

                    # Get current value based on condition type
                    current_value = None

                    if condition.condition_type == ConditionType.PRICE:
                        symbol_data = market_data.get(order.symbol, {})
                        current_value = Decimal(str(symbol_data.get("price", 0)))

                    elif condition.condition_type == ConditionType.NEURAL_LEVEL:
                        # Integration with existing PowerTrader neural levels
                        # This would connect to the existing neural signal system
                        current_value = Decimal(
                            str(market_data.get(f"{order.symbol}_neural_level", 0))
                        )

                    elif condition.condition_type == ConditionType.VOLUME:
                        symbol_data = market_data.get(order.symbol, {})
                        current_value = Decimal(str(symbol_data.get("volume", 0)))

                    if current_value is not None:
                        condition_met = condition.check_condition(current_value)
                        if not condition_met:
                            order_triggered = False
                            break
                    else:
                        order_triggered = False
                        break

                if order_triggered and all(c.is_met for c in order.conditions):
                    triggered_orders.append(order)

                    # Create notification for triggered order
                    create_notification(
                        session,
                        order.id,
                        NotificationType.CONDITION_TRIGGERED,
                        f"Order Triggered: {order.symbol}",
                        f"All conditions met for order {order.client_order_id}",
                        user_id=order.user_id,
                    )

                    logger.info(f"Order {order.id} conditions triggered")

        return triggered_orders

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        return self.update_order_status(order_id, OrderStatus.CANCELLED)

    def expire_old_orders(self, age_hours: int = 24) -> int:
        """Expire orders older than specified age."""
        cutoff_time = datetime.utcnow() - timedelta(hours=age_hours)
        expired_count = 0

        with self.get_session() as session:
            old_orders = (
                session.query(Order)
                .filter(
                    Order.status.in_([OrderStatus.PENDING, OrderStatus.SUBMITTED]),
                    Order.created_at < cutoff_time,
                )
                .all()
            )

            for order in old_orders:
                order.status = OrderStatus.EXPIRED
                order.updated_at = datetime.utcnow()
                expired_count += 1

                create_notification(
                    session,
                    order.id,
                    NotificationType.ORDER_EXPIRED,
                    f"Order Expired: {order.symbol}",
                    f"Order {order.client_order_id} expired after {age_hours} hours",
                    user_id=order.user_id,
                )

        if expired_count > 0:
            logger.info(f"Expired {expired_count} old orders")

        return expired_count

    def get_unread_notifications(
        self, user_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get unread notifications as dictionaries."""
        with self.get_session() as session:
            query = (
                session.query(Notification)
                .filter(Notification.is_read == False)
                .order_by(Notification.created_at.desc())
                .limit(limit)
            )

            if user_id:
                query = query.filter(Notification.user_id == user_id)

            notifications = query.all()

            # Convert to dictionaries
            result = []
            for notif in notifications:
                notif_dict = {
                    "id": str(notif.id),  # Convert UUID to string
                    "title": notif.title,
                    "message": notif.message,
                    "notification_type": notif.notification_type,
                    "is_read": notif.is_read,
                    "created_at": notif.created_at,
                    "order_id": str(notif.order_id) if notif.order_id else None,
                }
                result.append(notif_dict)

            return result

    def mark_notification_read(self, notification_id: str) -> bool:
        """Mark a notification as read."""
        with self.get_session() as session:
            notification = (
                session.query(Notification)
                .filter(Notification.id == notification_id)
                .first()
            )

            if notification:
                notification.is_read = True
                notification.read_at = datetime.utcnow()
                return True

            return False

    def get_order_history(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
        user_id: Optional[str] = None,
    ) -> List[Order]:
        """Get order history."""
        with self.get_session() as session:
            query = session.query(Order).order_by(Order.created_at.desc()).limit(limit)

            if symbol:
                query = query.filter(Order.symbol == symbol.upper())
            if user_id:
                query = query.filter(Order.user_id == user_id)

            return query.all()

    def get_performance_stats(
        self, symbol: Optional[str] = None, days: int = 30
    ) -> Dict[str, Any]:
        """Get performance statistics for orders."""
        start_date = datetime.utcnow() - timedelta(days=days)

        with self.get_session() as session:
            query = session.query(Order).filter(
                Order.created_at >= start_date, Order.status == OrderStatus.FILLED
            )

            if symbol:
                query = query.filter(Order.symbol == symbol.upper())

            orders = query.all()

            stats = {
                "total_orders": len(orders),
                "filled_orders": len(
                    [o for o in orders if o.status == OrderStatus.FILLED]
                ),
                "cancelled_orders": len(
                    [o for o in orders if o.status == OrderStatus.CANCELLED]
                ),
                "total_volume": sum(
                    o.filled_quantity * o.average_fill_price
                    for o in orders
                    if o.average_fill_price
                ),
                "total_commission": sum(o.commission for o in orders),
                "avg_fill_time_seconds": 0,  # Could calculate from execution times
                "symbols_traded": len(set(o.symbol for o in orders)),
            }

            return stats


# Global database instance
_db_instance: Optional[OrderManagementDB] = None


def get_order_db(database_url: Optional[str] = None) -> OrderManagementDB:
    """Get or create the global order management database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = OrderManagementDB(database_url)
    return _db_instance


def initialize_order_management_system(
    database_url: Optional[str] = None,
) -> OrderManagementDB:
    """Initialize the order management system."""
    db = get_order_db(database_url)
    logger.info("Order management system initialized")
    return db


# Integration with existing PowerTrader systems
class PowerTraderOrderIntegration:
    """Integration layer between PowerTrader and Order Management."""

    def __init__(self, order_db: OrderManagementDB):
        self.order_db = order_db
        self.logger = logging.getLogger(f"{__name__}.Integration")

    def create_dca_order(
        self, symbol: str, quantity: Decimal, dca_stage: int, neural_level: int
    ) -> str:
        """Create a DCA order with neural level condition."""
        order = self.order_db.create_order(
            symbol=symbol,
            order_type=OrderType.CONDITIONAL,
            side=OrderSide.BUY,
            quantity=quantity,
            tag=f"DCA_STAGE_{dca_stage}",
        )

        # Add neural level condition
        self.order_db.add_condition_to_order(
            order.id,
            ConditionType.NEURAL_LEVEL,
            ConditionOperator.GTE,
            Decimal(str(neural_level)),
            symbol=symbol,
        )

        return order.id

    def create_trailing_stop(
        self, symbol: str, quantity: Decimal, trail_percent: Decimal
    ) -> Order:
        """Create a trailing stop order."""
        order = self.order_db.create_order(
            symbol=symbol,
            order_type=OrderType.CONDITIONAL,
            side=OrderSide.SELL,
            quantity=quantity,
            tag="TRAILING_STOP",
        )

        # This would integrate with the existing trailing PM logic
        return order

    def sync_with_powertrader_positions(self, positions: Dict[str, Any]):
        """Sync order management with PowerTrader position data."""
        # This would update order quantities and statuses based on
        # actual PowerTrader positions and trade history
        pass
