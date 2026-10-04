"""
Advanced Order Types & Automation Engine (Item 23)
Implements sophisticated order types and automated execution logic
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from order_management_models import OrderSide, OrderStatus, OrderType

    ORDER_MODELS_AVAILABLE = True
except ImportError:
    ORDER_MODELS_AVAILABLE = False
    print("Warning: Order management models not available")

    # Minimal stubs so that class-body annotations and default values
    # (e.g. ``status: OrderStatus = OrderStatus.PENDING``) don't raise
    # NameError when the real module is unavailable (e.g. sqlalchemy missing).
    class OrderSide(Enum):  # type: ignore[no-redef]
        BUY = "buy"
        SELL = "sell"

    class OrderStatus(Enum):  # type: ignore[no-redef]
        PENDING = "pending"
        EXECUTING = "executing"
        FILLED = "filled"
        CANCELLED = "cancelled"
        ERROR = "error"

    class OrderType(Enum):  # type: ignore[no-redef]
        MARKET = "market"
        LIMIT = "limit"


try:
    import ccxt

    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    print("Warning: CCXT not available - exchange integration limited")


class AdvancedOrderType(Enum):
    """Advanced order types beyond basic market/limit orders"""

    OCO = "one_cancels_other"  # One Cancels Other
    TRAILING_STOP = "trailing_stop"
    ICEBERG = "iceberg"
    TWAP = "time_weighted_average_price"
    VWAP = "volume_weighted_average_price"
    BRACKET = "bracket"
    CONDITIONAL = "conditional"
    ALGORITHMIC = "algorithmic"


class ConditionType(Enum):
    """Types of conditions for conditional orders"""

    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    PRICE_CROSSES = "price_crosses"
    RSI_ABOVE = "rsi_above"
    RSI_BELOW = "rsi_below"
    VOLUME_ABOVE = "volume_above"
    TIME_BASED = "time_based"
    CORRELATION = "correlation"
    PORTFOLIO_VALUE = "portfolio_value"


class AutomationTrigger(Enum):
    """Automation trigger types"""

    MANUAL = "manual"
    PRICE_CONDITION = "price_condition"
    TIME_CONDITION = "time_condition"
    TECHNICAL_INDICATOR = "technical_indicator"
    NEWS_SENTIMENT = "news_sentiment"
    PORTFOLIO_REBALANCE = "portfolio_rebalance"
    RISK_MANAGEMENT = "risk_management"


@dataclass
class OrderCondition:
    """Condition that must be met for order execution"""

    id: str
    condition_type: ConditionType
    symbol: str
    operator: str  # ">=", "<=", "==", "!=", "crosses_above", "crosses_below"
    target_value: float
    current_value: Optional[float] = None
    met: bool = False
    last_checked: Optional[datetime] = None


@dataclass
class AdvancedOrder:
    """Advanced order with complex execution logic"""

    id: str
    order_type: AdvancedOrderType
    symbol: str
    side: OrderSide
    quantity: float

    # Price parameters
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    trail_amount: Optional[float] = None
    trail_percent: Optional[float] = None

    # Execution parameters
    time_in_force: str = "GTC"  # GTC, IOC, FOK, GTD
    expire_time: Optional[datetime] = None
    min_quantity: Optional[float] = None
    display_quantity: Optional[float] = None

    # Conditional execution
    conditions: List[OrderCondition] = None
    parent_order_id: Optional[str] = None
    child_order_ids: List[str] = None

    # Algorithmic execution
    execution_algorithm: Optional[str] = None
    algorithm_params: Optional[Dict] = None

    # State
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = None
    updated_at: datetime = None
    filled_quantity: float = 0.0
    average_fill_price: float = 0.0

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.conditions is None:
            self.conditions = []
        if self.child_order_ids is None:
            self.child_order_ids = []


@dataclass
class OCOOrder:
    """One Cancels Other order configuration"""

    primary_order: AdvancedOrder
    secondary_order: AdvancedOrder
    executed_order_id: Optional[str] = None


@dataclass
class BracketOrder:
    """Bracket order with profit target and stop loss"""

    parent_order: AdvancedOrder
    take_profit_order: AdvancedOrder
    stop_loss_order: AdvancedOrder


class OrderAutomationEngine:
    """Engine for processing advanced order types and automation"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            import pt_paths

            db_path = pt_paths.data_file("automation.db")
        self.db_path = db_path
        self._init_db()

        # Order tracking
        self.active_orders: Dict[str, AdvancedOrder] = {}
        self.oco_orders: Dict[str, OCOOrder] = {}
        self.bracket_orders: Dict[str, BracketOrder] = {}

        # Execution engine
        self.execution_queue = queue.Queue()
        self.condition_checkers: Dict[ConditionType, Callable] = {}
        self.market_data_cache: Dict[str, Dict] = {}

        # Threading
        self.running = False
        self.execution_thread = None
        self.monitoring_thread = None

        # Callbacks
        self.order_update_callback: Optional[Callable] = None
        self.execution_callback: Optional[Callable] = None

        self._setup_condition_checkers()

    def _init_db(self):
        """Initialize automation database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS advanced_orders (
                    id TEXT PRIMARY KEY,
                    order_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    limit_price REAL,
                    stop_price REAL,
                    trail_amount REAL,
                    trail_percent REAL,
                    time_in_force TEXT DEFAULT 'GTC',
                    expire_time TEXT,
                    min_quantity REAL,
                    display_quantity REAL,
                    conditions_json TEXT,
                    parent_order_id TEXT,
                    child_order_ids_json TEXT,
                    execution_algorithm TEXT,
                    algorithm_params_json TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    filled_quantity REAL DEFAULT 0.0,
                    average_fill_price REAL DEFAULT 0.0
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS oco_orders (
                    id TEXT PRIMARY KEY,
                    primary_order_id TEXT NOT NULL,
                    secondary_order_id TEXT NOT NULL,
                    executed_order_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (primary_order_id) REFERENCES advanced_orders (id),
                    FOREIGN KEY (secondary_order_id) REFERENCES advanced_orders (id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bracket_orders (
                    id TEXT PRIMARY KEY,
                    parent_order_id TEXT NOT NULL,
                    take_profit_order_id TEXT NOT NULL,
                    stop_loss_order_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (parent_order_id) REFERENCES advanced_orders (id),
                    FOREIGN KEY (take_profit_order_id) REFERENCES advanced_orders (id),
                    FOREIGN KEY (stop_loss_order_id) REFERENCES advanced_orders (id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS automation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    condition_met TEXT,
                    timestamp TEXT NOT NULL,
                    details_json TEXT
                )
            """)

            conn.commit()

    def _setup_condition_checkers(self):
        """Setup condition checking functions"""
        self.condition_checkers = {
            ConditionType.PRICE_ABOVE: self._check_price_above,
            ConditionType.PRICE_BELOW: self._check_price_below,
            ConditionType.PRICE_CROSSES: self._check_price_crosses,
            ConditionType.RSI_ABOVE: self._check_rsi_above,
            ConditionType.RSI_BELOW: self._check_rsi_below,
            ConditionType.VOLUME_ABOVE: self._check_volume_above,
            ConditionType.TIME_BASED: self._check_time_based,
            ConditionType.CORRELATION: self._check_correlation,
            ConditionType.PORTFOLIO_VALUE: self._check_portfolio_value,
        }

    def start(self):
        """Start the automation engine"""
        if self.running:
            return

        self.running = True

        # Start execution thread
        self.execution_thread = threading.Thread(
            target=self._execution_worker, daemon=True
        )
        self.execution_thread.start()

        # Start monitoring thread
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_worker, daemon=True
        )
        self.monitoring_thread.start()

        print("Order automation engine started")

    def stop(self):
        """Stop the automation engine"""
        self.running = False

        if self.execution_thread and self.execution_thread.is_alive():
            self.execution_thread.join(timeout=5)

        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)

        print("Order automation engine stopped")

    def create_oco_order(
        self, primary_order: AdvancedOrder, secondary_order: AdvancedOrder
    ) -> str:
        """Create One Cancels Other order"""
        oco_id = str(uuid.uuid4())

        # Set up the orders
        primary_order.id = str(uuid.uuid4())
        secondary_order.id = str(uuid.uuid4())

        # Link orders
        primary_order.parent_order_id = oco_id
        secondary_order.parent_order_id = oco_id

        # Create OCO structure
        oco_order = OCOOrder(
            primary_order=primary_order, secondary_order=secondary_order
        )

        # Store in memory and database
        self.oco_orders[oco_id] = oco_order
        self.active_orders[primary_order.id] = primary_order
        self.active_orders[secondary_order.id] = secondary_order

        self._save_order(primary_order)
        self._save_order(secondary_order)
        self._save_oco_order(oco_id, oco_order)

        return oco_id

    def create_bracket_order(
        self,
        entry_order: AdvancedOrder,
        take_profit_price: float,
        stop_loss_price: float,
    ) -> str:
        """Create bracket order with profit target and stop loss"""
        bracket_id = str(uuid.uuid4())

        # Create child orders
        take_profit_order = AdvancedOrder(
            id=str(uuid.uuid4()),
            order_type=AdvancedOrderType.CONDITIONAL,
            symbol=entry_order.symbol,
            side=OrderSide.SELL if entry_order.side == OrderSide.BUY else OrderSide.BUY,
            quantity=entry_order.quantity,
            limit_price=take_profit_price,
            conditions=[
                OrderCondition(
                    id=str(uuid.uuid4()),
                    condition_type=(
                        ConditionType.PRICE_ABOVE
                        if entry_order.side == OrderSide.BUY
                        else ConditionType.PRICE_BELOW
                    ),
                    symbol=entry_order.symbol,
                    operator=">=",
                    target_value=take_profit_price,
                )
            ],
            parent_order_id=bracket_id,
        )

        stop_loss_order = AdvancedOrder(
            id=str(uuid.uuid4()),
            order_type=AdvancedOrderType.CONDITIONAL,
            symbol=entry_order.symbol,
            side=OrderSide.SELL if entry_order.side == OrderSide.BUY else OrderSide.BUY,
            quantity=entry_order.quantity,
            stop_price=stop_loss_price,
            conditions=[
                OrderCondition(
                    id=str(uuid.uuid4()),
                    condition_type=(
                        ConditionType.PRICE_BELOW
                        if entry_order.side == OrderSide.BUY
                        else ConditionType.PRICE_ABOVE
                    ),
                    symbol=entry_order.symbol,
                    operator="<=",
                    target_value=stop_loss_price,
                )
            ],
            parent_order_id=bracket_id,
        )

        # Link all orders
        entry_order.parent_order_id = bracket_id
        entry_order.child_order_ids = [take_profit_order.id, stop_loss_order.id]

        # Create bracket structure
        bracket_order = BracketOrder(
            parent_order=entry_order,
            take_profit_order=take_profit_order,
            stop_loss_order=stop_loss_order,
        )

        # Store in memory and database
        self.bracket_orders[bracket_id] = bracket_order
        self.active_orders[entry_order.id] = entry_order
        self.active_orders[take_profit_order.id] = take_profit_order
        self.active_orders[stop_loss_order.id] = stop_loss_order

        self._save_order(entry_order)
        self._save_order(take_profit_order)
        self._save_order(stop_loss_order)
        self._save_bracket_order(bracket_id, bracket_order)

        return bracket_id

    def create_trailing_stop_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        trail_amount: float = None,
        trail_percent: float = None,
    ) -> str:
        """Create trailing stop order"""
        order = AdvancedOrder(
            id=str(uuid.uuid4()),
            order_type=AdvancedOrderType.TRAILING_STOP,
            symbol=symbol,
            side=side,
            quantity=quantity,
            trail_amount=trail_amount,
            trail_percent=trail_percent,
        )

        self.active_orders[order.id] = order
        self._save_order(order)

        return order.id

    def create_iceberg_order(
        self,
        symbol: str,
        side: OrderSide,
        total_quantity: float,
        display_quantity: float,
        limit_price: float,
    ) -> str:
        """Create iceberg order"""
        order = AdvancedOrder(
            id=str(uuid.uuid4()),
            order_type=AdvancedOrderType.ICEBERG,
            symbol=symbol,
            side=side,
            quantity=total_quantity,
            display_quantity=display_quantity,
            limit_price=limit_price,
        )

        self.active_orders[order.id] = order
        self._save_order(order)

        return order.id

    def create_conditional_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        conditions: List[OrderCondition],
        limit_price: float = None,
    ) -> str:
        """Create conditional order"""
        order = AdvancedOrder(
            id=str(uuid.uuid4()),
            order_type=AdvancedOrderType.CONDITIONAL,
            symbol=symbol,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            conditions=conditions,
        )

        self.active_orders[order.id] = order
        self._save_order(order)

        return order.id

    def update_market_data(self, symbol: str, data: Dict):
        """Update market data for condition checking"""
        self.market_data_cache[symbol] = {**data, "timestamp": datetime.now()}

    def get_active_orders(self) -> List[AdvancedOrder]:
        """Get all active orders"""
        return list(self.active_orders.values())

    def get_order_by_id(self, order_id: str) -> Optional[AdvancedOrder]:
        """Get order by ID"""
        return self.active_orders.get(order_id)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        order = self.active_orders.get(order_id)
        if not order:
            return False

        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.now()

        self._save_order(order)

        # Handle OCO cancellation
        for oco_id, oco_order in self.oco_orders.items():
            if order_id in [oco_order.primary_order.id, oco_order.secondary_order.id]:
                # Cancel the other order
                other_order_id = (
                    oco_order.secondary_order.id
                    if order_id == oco_order.primary_order.id
                    else oco_order.primary_order.id
                )
                if other_order_id in self.active_orders:
                    self.cancel_order(other_order_id)
                break

        if self.order_update_callback:
            self.order_update_callback(order)

        return True

    def _execution_worker(self):
        """Background worker for order execution"""
        while self.running:
            try:
                # Process execution queue
                if not self.execution_queue.empty():
                    order_id = self.execution_queue.get_nowait()
                    self._execute_order(order_id)

                time.sleep(0.1)  # Small delay to prevent busy waiting

            except Exception as e:
                print(f"Error in execution worker: {e}")
                time.sleep(1)

    def _monitoring_worker(self):
        """Background worker for condition monitoring"""
        while self.running:
            try:
                self._check_all_conditions()
                time.sleep(1)  # Check conditions every second

            except Exception as e:
                print(f"Error in monitoring worker: {e}")
                time.sleep(5)

    def _check_all_conditions(self):
        """Check all order conditions"""
        for order in list(self.active_orders.values()):
            if order.status != OrderStatus.PENDING:
                continue

            if order.order_type == AdvancedOrderType.CONDITIONAL and order.conditions:
                all_met = True
                for condition in order.conditions:
                    if not self._check_condition(condition):
                        all_met = False
                        break

                if all_met and order.id not in [
                    item for item in list(self.execution_queue.queue)
                ]:
                    self.execution_queue.put(order.id)

            elif order.order_type == AdvancedOrderType.TRAILING_STOP:
                self._update_trailing_stop(order)

    def _check_condition(self, condition: OrderCondition) -> bool:
        """Check a specific condition"""
        checker = self.condition_checkers.get(condition.condition_type)
        if not checker:
            return False

        try:
            met = checker(condition)
            condition.met = met
            condition.last_checked = datetime.now()
            return met
        except Exception as e:
            print(f"Error checking condition {condition.id}: {e}")
            return False

    # Condition checker implementations
    def _check_price_above(self, condition: OrderCondition) -> bool:
        """Check if price is above target"""
        market_data = self.market_data_cache.get(condition.symbol)
        if not market_data or "price" not in market_data:
            return False

        current_price = market_data["price"]
        condition.current_value = current_price
        return current_price >= condition.target_value

    def _check_price_below(self, condition: OrderCondition) -> bool:
        """Check if price is below target"""
        market_data = self.market_data_cache.get(condition.symbol)
        if not market_data or "price" not in market_data:
            return False

        current_price = market_data["price"]
        condition.current_value = current_price
        return current_price <= condition.target_value

    def _check_price_crosses(self, condition: OrderCondition) -> bool:
        """Check if price crosses target value"""
        # Implementation would require price history
        return False

    def _check_rsi_above(self, condition: OrderCondition) -> bool:
        """Check if RSI is above target"""
        market_data = self.market_data_cache.get(condition.symbol)
        if not market_data or "rsi" not in market_data:
            return False

        current_rsi = market_data["rsi"]
        condition.current_value = current_rsi
        return current_rsi >= condition.target_value

    def _check_rsi_below(self, condition: OrderCondition) -> bool:
        """Check if RSI is below target"""
        market_data = self.market_data_cache.get(condition.symbol)
        if not market_data or "rsi" not in market_data:
            return False

        current_rsi = market_data["rsi"]
        condition.current_value = current_rsi
        return current_rsi <= condition.target_value

    def _check_volume_above(self, condition: OrderCondition) -> bool:
        """Check if volume is above target"""
        market_data = self.market_data_cache.get(condition.symbol)
        if not market_data or "volume" not in market_data:
            return False

        current_volume = market_data["volume"]
        condition.current_value = current_volume
        return current_volume >= condition.target_value

    def _check_time_based(self, condition: OrderCondition) -> bool:
        """Check time-based condition"""
        target_time = datetime.fromisoformat(
            condition.operator
        )  # operator contains target time
        return datetime.now() >= target_time

    def _check_correlation(self, condition: OrderCondition) -> bool:
        """Check correlation condition"""
        # Implementation would require correlation calculation
        return False

    def _check_portfolio_value(self, condition: OrderCondition) -> bool:
        """Check portfolio value condition"""
        # Implementation would require portfolio value calculation
        return False

    def _update_trailing_stop(self, order: AdvancedOrder):
        """Update trailing stop order"""
        market_data = self.market_data_cache.get(order.symbol)
        if not market_data or "price" not in market_data:
            return

        current_price = market_data["price"]

        if order.stop_price is None:
            # Initialize trailing stop
            if order.side == OrderSide.SELL:  # Long position
                if order.trail_amount:
                    order.stop_price = current_price - order.trail_amount
                elif order.trail_percent:
                    order.stop_price = current_price * (1 - order.trail_percent / 100)
            else:  # Short position
                if order.trail_amount:
                    order.stop_price = current_price + order.trail_amount
                elif order.trail_percent:
                    order.stop_price = current_price * (1 + order.trail_percent / 100)
        else:
            # Update trailing stop
            if order.side == OrderSide.SELL:  # Long position
                new_stop = None
                if order.trail_amount:
                    new_stop = current_price - order.trail_amount
                elif order.trail_percent:
                    new_stop = current_price * (1 - order.trail_percent / 100)

                if new_stop and new_stop > order.stop_price:
                    order.stop_price = new_stop
                    order.updated_at = datetime.now()
                    self._save_order(order)

                # Check if stop is triggered
                if current_price <= order.stop_price:
                    self.execution_queue.put(order.id)

            else:  # Short position
                new_stop = None
                if order.trail_amount:
                    new_stop = current_price + order.trail_amount
                elif order.trail_percent:
                    new_stop = current_price * (1 + order.trail_percent / 100)

                if new_stop and new_stop < order.stop_price:
                    order.stop_price = new_stop
                    order.updated_at = datetime.now()
                    self._save_order(order)

                # Check if stop is triggered
                if current_price >= order.stop_price:
                    self.execution_queue.put(order.id)

    def _execute_order(self, order_id: str):
        """Execute an order"""
        order = self.active_orders.get(order_id)
        if not order or order.status != OrderStatus.PENDING:
            return

        try:
            # Mark as executing
            order.status = OrderStatus.EXECUTING
            order.updated_at = datetime.now()

            # Simulate execution (replace with actual exchange integration)
            print(
                f"Executing order {order_id}: {order.side} {order.quantity} {order.symbol}"
            )

            # For simulation, mark as filled
            order.status = OrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.average_fill_price = order.limit_price or 0.0
            order.updated_at = datetime.now()

            self._save_order(order)

            # Handle post-execution logic
            self._handle_post_execution(order)

            if self.execution_callback:
                self.execution_callback(order)

        except Exception as e:
            print(f"Error executing order {order_id}: {e}")
            order.status = OrderStatus.ERROR
            order.updated_at = datetime.now()
            self._save_order(order)

    def _handle_post_execution(self, order: AdvancedOrder):
        """Handle post-execution logic"""
        # Handle OCO cancellation
        for oco_id, oco_order in self.oco_orders.items():
            if order.id in [oco_order.primary_order.id, oco_order.secondary_order.id]:
                oco_order.executed_order_id = order.id

                # Cancel the other order
                other_order_id = (
                    oco_order.secondary_order.id
                    if order.id == oco_order.primary_order.id
                    else oco_order.primary_order.id
                )
                if other_order_id in self.active_orders:
                    self.cancel_order(other_order_id)
                break

        # Handle bracket order activation
        for bracket_id, bracket_order in self.bracket_orders.items():
            if (
                order.id == bracket_order.parent_order.id
                and order.status == OrderStatus.FILLED
            ):
                # Activate child orders
                bracket_order.take_profit_order.status = OrderStatus.PENDING
                bracket_order.stop_loss_order.status = OrderStatus.PENDING
                self._save_order(bracket_order.take_profit_order)
                self._save_order(bracket_order.stop_loss_order)

    def _save_order(self, order: AdvancedOrder):
        """Save order to database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO advanced_orders
                (id, order_type, symbol, side, quantity, limit_price, stop_price,
                 trail_amount, trail_percent, time_in_force, expire_time, min_quantity,
                 display_quantity, conditions_json, parent_order_id, child_order_ids_json,
                 execution_algorithm, algorithm_params_json, status, created_at, updated_at,
                 filled_quantity, average_fill_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    order.id,
                    order.order_type.value,
                    order.symbol,
                    order.side.value,
                    order.quantity,
                    order.limit_price,
                    order.stop_price,
                    order.trail_amount,
                    order.trail_percent,
                    order.time_in_force,
                    order.expire_time.isoformat() if order.expire_time else None,
                    order.min_quantity,
                    order.display_quantity,
                    (
                        json.dumps([asdict(c) for c in order.conditions])
                        if order.conditions
                        else None
                    ),
                    order.parent_order_id,
                    (
                        json.dumps(order.child_order_ids)
                        if order.child_order_ids
                        else None
                    ),
                    order.execution_algorithm,
                    (
                        json.dumps(order.algorithm_params)
                        if order.algorithm_params
                        else None
                    ),
                    order.status.value,
                    order.created_at.isoformat(),
                    order.updated_at.isoformat(),
                    order.filled_quantity,
                    order.average_fill_price,
                ),
            )
            conn.commit()

    def _save_oco_order(self, oco_id: str, oco_order: OCOOrder):
        """Save OCO order to database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO oco_orders
                (id, primary_order_id, secondary_order_id, executed_order_id, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    oco_id,
                    oco_order.primary_order.id,
                    oco_order.secondary_order.id,
                    oco_order.executed_order_id,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()

    def _save_bracket_order(self, bracket_id: str, bracket_order: BracketOrder):
        """Save bracket order to database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO bracket_orders
                (id, parent_order_id, take_profit_order_id, stop_loss_order_id, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    bracket_id,
                    bracket_order.parent_order.id,
                    bracket_order.take_profit_order.id,
                    bracket_order.stop_loss_order.id,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()


# Global automation engine instance
_automation_engine = None


def get_automation_engine() -> OrderAutomationEngine:
    """Get the global automation engine instance"""
    global _automation_engine
    if _automation_engine is None:
        _automation_engine = OrderAutomationEngine()
    return _automation_engine
