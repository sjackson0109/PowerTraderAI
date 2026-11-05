#!/usr/bin/env python3
"""
PowerTrader AI - Advanced Order Management Database Models
===========================================================

SQLAlchemy models for advanced order management system including:
- Orders (market, limit, stop, conditional)
- Order conditions and triggers
- Order executions and fills
- Notifications and alerts

This integrates with the existing PowerTrader trading system while adding
sophisticated order management capabilities.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, validates

Base = declarative_base()


class OrderType(Enum):
    """Types of trading orders."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    CONDITIONAL = "conditional"
    BRACKET = "bracket"
    OCO = "oco"  # One-Cancels-Other
    TRAILING_STOP = "trailing_stop"


class OrderSide(Enum):
    """Order side - buy or sell."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    """Status of trading orders."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"


class ConditionType(Enum):
    """Types of order conditions."""

    PRICE = "price"
    TIME = "time"
    VOLUME = "volume"
    INDICATOR = "indicator"
    NEURAL_LEVEL = "neural_level"
    PORTFOLIO_PCT = "portfolio_pct"


class ConditionOperator(Enum):
    """Condition comparison operators."""

    GT = "gt"  # greater than
    LT = "lt"  # less than
    GTE = "gte"  # greater than or equal
    LTE = "lte"  # less than or equal
    EQ = "eq"  # equal
    NE = "ne"  # not equal


class NotificationType(Enum):
    """Types of notifications."""

    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_EXPIRED = "order_expired"
    CONDITION_TRIGGERED = "condition_triggered"
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_HIT = "take_profit_hit"
    RISK_ALERT = "risk_alert"


class Order(Base):
    """Advanced order management table."""

    __tablename__ = "orders"

    # Primary identification
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(50), nullable=True, index=True)  # For multi-user support
    client_order_id = Column(String(100), nullable=False, unique=True)
    exchange_order_id = Column(String(100), nullable=True)

    # Order basics
    symbol = Column(String(20), nullable=False, index=True)
    order_type = Column(SQLEnum(OrderType), nullable=False)
    side = Column(SQLEnum(OrderSide), nullable=False)
    status = Column(SQLEnum(OrderStatus), nullable=False, default=OrderStatus.PENDING)

    # Quantities and pricing
    quantity = Column(Numeric(20, 8), nullable=False)
    price = Column(Numeric(20, 8), nullable=True)  # For limit orders
    stop_price = Column(Numeric(20, 8), nullable=True)  # For stop orders
    filled_quantity = Column(Numeric(20, 8), nullable=False, default=0)
    average_fill_price = Column(Numeric(20, 8), nullable=True)

    # Timing
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    submitted_at = Column(DateTime, nullable=True)
    filled_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)  # For expiring orders

    # Order relationships
    parent_order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    parent_order = relationship("Order", remote_side=[id], backref="child_orders")

    # Trading context
    tag = Column(String(50), nullable=True)  # DCA, ENTRY, PROFIT_TAKE, etc.
    notes = Column(Text, nullable=True)

    # Risk management
    max_slippage_pct = Column(
        Numeric(5, 4), nullable=True
    )  # Maximum acceptable slippage
    time_in_force = Column(
        String(10), nullable=True, default="GTC"
    )  # GTC, IOC, FOK, etc.

    # Cost tracking
    commission = Column(Numeric(20, 8), nullable=False, default=0)
    total_cost = Column(Numeric(20, 8), nullable=True)  # Total cost including fees

    # Relationships
    conditions = relationship(
        "OrderCondition", back_populates="order", cascade="all, delete-orphan"
    )
    executions = relationship(
        "OrderExecution", back_populates="order", cascade="all, delete-orphan"
    )
    notifications = relationship(
        "Notification", back_populates="order", cascade="all, delete-orphan"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_orders_symbol_status", "symbol", "status"),
        Index("idx_orders_created_at", "created_at"),
        Index("idx_orders_user_status", "user_id", "status"),
    )

    @validates("quantity", "price", "stop_price")
    def validate_positive_numbers(self, key, value):
        """Ensure financial values are positive."""
        if value is not None and value <= 0:
            raise ValueError(f"{key} must be positive")
        return value

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == OrderStatus.FILLED

    @property
    def is_active(self) -> bool:
        """Check if order is still active (can be filled)."""
        return self.status in [
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIAL,
        ]

    @property
    def remaining_quantity(self) -> Decimal:
        """Get remaining quantity to fill."""
        return self.quantity - self.filled_quantity

    @property
    def fill_percentage(self) -> float:
        """Get percentage of order filled."""
        if self.quantity == 0:
            return 0.0
        return float(self.filled_quantity / self.quantity * 100)


class OrderCondition(Base):
    """Order conditions and triggers."""

    __tablename__ = "order_conditions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)

    # Condition definition
    condition_type = Column(SQLEnum(ConditionType), nullable=False)
    operator = Column(SQLEnum(ConditionOperator), nullable=False)
    target_value = Column(Numeric(20, 8), nullable=False)

    # Condition state
    current_value = Column(Numeric(20, 8), nullable=True)
    is_met = Column(Boolean, nullable=False, default=False)
    met_at = Column(DateTime, nullable=True)

    # Additional context
    symbol = Column(String(20), nullable=True)  # For cross-symbol conditions
    timeframe = Column(String(10), nullable=True)  # 1m, 5m, 1h, etc.
    indicator_name = Column(String(50), nullable=True)  # RSI, MACD, etc.

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    order = relationship("Order", back_populates="conditions")

    __table_args__ = (
        Index("idx_conditions_order_type", "order_id", "condition_type"),
        Index("idx_conditions_unmet", "is_met", "condition_type"),
    )

    def check_condition(self, current_val: Decimal) -> bool:
        """Check if condition is met with current value."""
        self.current_value = current_val

        if self.operator == ConditionOperator.GT:
            met = current_val > self.target_value
        elif self.operator == ConditionOperator.LT:
            met = current_val < self.target_value
        elif self.operator == ConditionOperator.GTE:
            met = current_val >= self.target_value
        elif self.operator == ConditionOperator.LTE:
            met = current_val <= self.target_value
        elif self.operator == ConditionOperator.EQ:
            met = current_val == self.target_value
        elif self.operator == ConditionOperator.NE:
            met = current_val != self.target_value
        else:
            met = False

        if met and not self.is_met:
            self.is_met = True
            self.met_at = datetime.utcnow()

        return met


class OrderExecution(Base):
    """Individual order executions/fills."""

    __tablename__ = "order_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)

    # Execution details
    execution_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    quantity = Column(Numeric(20, 8), nullable=False)
    price = Column(Numeric(20, 8), nullable=False)
    commission = Column(Numeric(20, 8), nullable=False, default=0)

    # Exchange details
    exchange_execution_id = Column(String(100), nullable=True)
    exchange_name = Column(String(50), nullable=True)

    # Market data at execution
    bid_price = Column(Numeric(20, 8), nullable=True)
    ask_price = Column(Numeric(20, 8), nullable=True)
    spread_pct = Column(Numeric(5, 4), nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    order = relationship("Order", back_populates="executions")

    __table_args__ = (
        Index("idx_executions_order_time", "order_id", "execution_time"),
        Index("idx_executions_time", "execution_time"),
    )

    @property
    def total_value(self) -> Decimal:
        """Total value of this execution including commission."""
        return self.quantity * self.price + self.commission


class Notification(Base):
    """Order-related notifications."""

    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    user_id = Column(String(50), nullable=True, index=True)

    # Notification content
    notification_type = Column(SQLEnum(NotificationType), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)

    # Notification state
    is_read = Column(Boolean, nullable=False, default=False)
    is_dismissed = Column(Boolean, nullable=False, default=False)

    # Priority and routing
    priority = Column(
        String(10), nullable=False, default="normal"
    )  # low, normal, high, critical
    send_email = Column(Boolean, nullable=False, default=False)
    send_sms = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    read_at = Column(DateTime, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="notifications")

    __table_args__ = (
        Index("idx_notifications_user_unread", "user_id", "is_read"),
        Index("idx_notifications_type_created", "notification_type", "created_at"),
    )


class ManagedOrder(Base):
    """How Order Management carries out an order it created (order_management_
    execution): one row per order, and per group and leg of an OCO or Bracket
    order. Kept with the orders, so monitoring resumes when the app starts again.

    ``account`` is the trading settings' key when the order was made ("paper",
    "live:binance", ...) and ``books`` the folder of that account's books under the
    hub folder (TradingSettings.data_subdir). ``exchange`` and ``pair`` are the
    exchange whose market the order is on and that exchange's symbol. ``handling``
    is "exchange" when the exchange holds the order as its own (``exchange_order_id``
    on the order), "powertrader" when the app watches the price and places a market
    order, or fills the paper account, when it is reached. ``role`` is "order" for
    a single order, "group" for an OCO or Bracket order, and "entry",
    "take_profit" or "stop" for its legs. ``state``: "new" (not sent yet),
    "waiting" (a bracket's exits, until its entry fills), "working", "triggered" (a
    stop-limit order whose stop was reached: its limit order works), "placing" (being
    sent to the exchange) and "done". A trailing stop keeps its trail (a percent, or
    a multiple of ``atr``, the average true range when it was made) and the best
    price it has seen; ``note`` is the last thing that held the order up."""

    __tablename__ = "managed_orders"

    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), primary_key=True)
    account = Column(String(60), nullable=False)
    books = Column(String(120), nullable=False)
    exchange = Column(String(30), nullable=False, default="")
    pair = Column(String(30), nullable=False, default="")
    coin = Column(String(20), nullable=False)
    kind = Column(String(20), nullable=False)
    role = Column(String(20), nullable=False, default="order")
    handling = Column(String(12), nullable=False, default="powertrader")
    state = Column(String(12), nullable=False, default="new")
    trail_mode = Column(String(10), nullable=True)  # "percent" | "atr"
    trail_value = Column(Numeric(20, 8), nullable=True)  # the percent or the multiple
    atr = Column(Numeric(20, 8), nullable=True)
    best_price = Column(Numeric(20, 8), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("idx_managed_account_state", "account", "state"),)


class OrderTemplate(Base):
    """Saved order templates for quick reuse."""

    __tablename__ = "order_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(50), nullable=True, index=True)

    # Template metadata
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    # Order template data (JSON)
    template_data = Column(Text, nullable=False)  # Serialized order configuration

    # Usage tracking
    use_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_templates_user_active", "user_id", "is_active"),
        UniqueConstraint("user_id", "name", name="uq_user_template_name"),
    )


# Database utility functions
def create_order_management_tables(engine):
    """Create all order management tables."""
    Base.metadata.create_all(engine)


def get_active_orders(
    session, symbol: Optional[str] = None, user_id: Optional[str] = None
):
    """Get all active orders."""
    query = session.query(Order).filter(
        Order.status.in_(
            [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL]
        )
    )

    if symbol:
        query = query.filter(Order.symbol == symbol.upper())
    if user_id:
        query = query.filter(Order.user_id == user_id)

    return query.order_by(Order.created_at.desc()).all()


def get_orders_with_unmet_conditions(session):
    """Get orders that have unmet conditions."""
    return (
        session.query(Order)
        .join(OrderCondition)
        .filter(
            Order.status.in_([OrderStatus.PENDING, OrderStatus.SUBMITTED]),
            OrderCondition.is_met == False,
        )
        .distinct()
        .all()
    )


def create_notification(
    session,
    order_id: str,
    notification_type: NotificationType,
    title: str,
    message: str,
    user_id: Optional[str] = None,
    priority: str = "normal",
) -> Notification:
    """Create a new notification."""
    notification = Notification(
        order_id=order_id,
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        message=message,
        priority=priority,
    )
    session.add(notification)
    return notification
