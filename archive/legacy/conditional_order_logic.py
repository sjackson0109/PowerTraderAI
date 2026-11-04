"""
Conditional Order Logic System
Implements sophisticated if-then logic, multiple criteria evaluation,
market event triggers, and automated order chains for advanced trading strategies.
"""

import json
import operator
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    from order_management_db import OrderManagementDB
    from order_management_models import ConditionType, OrderSide, OrderStatus, OrderType

    CONDITIONAL_AVAILABLE = True
except ImportError:
    CONDITIONAL_AVAILABLE = False


class ConditionOperator(Enum):
    """Logical operators for condition evaluation."""

    EQUAL = "=="
    NOT_EQUAL = "!="
    GREATER_THAN = ">"
    GREATER_EQUAL = ">="
    LESS_THAN = "<"
    LESS_EQUAL = "<="
    BETWEEN = "between"
    NOT_BETWEEN = "not_between"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"


class LogicalOperator(Enum):
    """Logical operators for combining conditions."""

    AND = "and"
    OR = "or"
    NOT = "not"
    XOR = "xor"


class ConditionType(Enum):
    """Types of conditions that can be evaluated."""

    PRICE = "price"
    PERCENTAGE_CHANGE = "percentage_change"
    VOLUME = "volume"
    RSI = "rsi"
    MOVING_AVERAGE = "moving_average"
    BOLLINGER_BANDS = "bollinger_bands"
    TIME = "time"
    ORDER_STATUS = "order_status"
    POSITION_SIZE = "position_size"
    PROFIT_LOSS = "profit_loss"
    DRAWDOWN = "drawdown"
    NEWS_SENTIMENT = "news_sentiment"
    MARKET_CAP = "market_cap"
    CUSTOM = "custom"


class ActionType(Enum):
    """Types of actions that can be triggered."""

    CREATE_ORDER = "create_order"
    MODIFY_ORDER = "modify_order"
    CANCEL_ORDER = "cancel_order"
    CLOSE_POSITION = "close_position"
    SEND_NOTIFICATION = "send_notification"
    SET_STOP_LOSS = "set_stop_loss"
    SET_TAKE_PROFIT = "set_take_profit"
    CHAIN_ORDER = "chain_order"
    PAUSE_STRATEGY = "pause_strategy"
    CUSTOM_FUNCTION = "custom_function"


@dataclass
class Condition:
    """Represents a single condition to be evaluated."""

    name: str
    condition_type: ConditionType
    operator: ConditionOperator
    value: Any
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    parameters: Dict = None

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


@dataclass
class Action:
    """Represents an action to be executed when conditions are met."""

    name: str
    action_type: ActionType
    parameters: Dict
    delay: Optional[int] = 0  # Delay in seconds before execution
    repeat: bool = False
    max_executions: Optional[int] = None
    execution_count: int = 0


@dataclass
class ConditionalRule:
    """Represents a conditional rule with conditions and actions."""

    id: str
    name: str
    description: str
    conditions: List[Union[Condition, "ConditionGroup"]]
    actions: List[Action]
    logical_operator: LogicalOperator = LogicalOperator.AND
    active: bool = True
    created_at: datetime = None
    last_triggered: datetime = None
    trigger_count: int = 0

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class ConditionGroup:
    """Represents a group of conditions with logical operators."""

    conditions: List[Union[Condition, "ConditionGroup"]]
    logical_operator: LogicalOperator = LogicalOperator.AND


class ConditionEvaluator:
    """Evaluates individual conditions against market data."""

    def __init__(self, market_data_provider):
        self.market_data_provider = market_data_provider
        self.operator_map = {
            ConditionOperator.EQUAL.value: operator.eq,
            ConditionOperator.NOT_EQUAL.value: operator.ne,
            ConditionOperator.GREATER_THAN.value: operator.gt,
            ConditionOperator.GREATER_EQUAL.value: operator.ge,
            ConditionOperator.LESS_THAN.value: operator.lt,
            ConditionOperator.LESS_EQUAL.value: operator.le,
        }

    def evaluate_condition(self, condition: Condition, context: Dict = None) -> bool:
        """Evaluate a single condition."""
        try:
            if context is None:
                context = {}

            # Get the actual value to compare
            actual_value = self._get_condition_value(condition, context)

            if actual_value is None:
                return False

            # Perform the comparison
            return self._compare_values(
                actual_value, condition.operator, condition.value
            )

        except Exception as e:
            print(f"Error evaluating condition {condition.name}: {e}")
            return False

    def _get_condition_value(self, condition: Condition, context: Dict) -> Any:
        """Get the actual value for the condition based on its type."""
        try:
            if condition.condition_type == ConditionType.PRICE:
                return self.market_data_provider.get_current_price(condition.symbol)

            elif condition.condition_type == ConditionType.PERCENTAGE_CHANGE:
                return self._calculate_percentage_change(condition, context)

            elif condition.condition_type == ConditionType.VOLUME:
                return self.market_data_provider.get_volume(condition.symbol)

            elif condition.condition_type == ConditionType.RSI:
                period = condition.parameters.get("period", 14)
                return self.market_data_provider.get_rsi(condition.symbol, period)

            elif condition.condition_type == ConditionType.MOVING_AVERAGE:
                period = condition.parameters.get("period", 20)
                ma_type = condition.parameters.get("type", "simple")
                return self.market_data_provider.get_moving_average(
                    condition.symbol, period, ma_type
                )

            elif condition.condition_type == ConditionType.BOLLINGER_BANDS:
                return self._evaluate_bollinger_bands(condition)

            elif condition.condition_type == ConditionType.TIME:
                return datetime.now()

            elif condition.condition_type == ConditionType.ORDER_STATUS:
                order_id = condition.parameters.get("order_id")
                return self.market_data_provider.get_order_status(order_id)

            elif condition.condition_type == ConditionType.POSITION_SIZE:
                return self.market_data_provider.get_position_size(condition.symbol)

            elif condition.condition_type == ConditionType.PROFIT_LOSS:
                return self.market_data_provider.get_unrealized_pnl(condition.symbol)

            elif condition.condition_type == ConditionType.DRAWDOWN:
                return self.market_data_provider.get_drawdown(condition.symbol)

            elif condition.condition_type == ConditionType.CUSTOM:
                custom_function = condition.parameters.get("function")
                if custom_function and callable(custom_function):
                    return custom_function(condition, context)

            return None

        except Exception as e:
            print(f"Error getting condition value: {e}")
            return None

    def _calculate_percentage_change(
        self, condition: Condition, context: Dict
    ) -> float:
        """Calculate percentage change over a time period."""
        try:
            current_price = self.market_data_provider.get_current_price(
                condition.symbol
            )
            timeframe = condition.timeframe or "24h"

            if timeframe == "24h":
                hours_ago = 24
            elif timeframe == "1h":
                hours_ago = 1
            elif timeframe == "1w":
                hours_ago = 168  # 7 days
            else:
                hours_ago = 24

            historical_price = self.market_data_provider.get_historical_price(
                condition.symbol, hours_ago
            )

            if current_price and historical_price and historical_price != 0:
                return ((current_price - historical_price) / historical_price) * 100

            return 0.0

        except Exception as e:
            print(f"Error calculating percentage change: {e}")
            return 0.0

    def _evaluate_bollinger_bands(self, condition: Condition) -> bool:
        """Evaluate Bollinger Bands condition."""
        try:
            period = condition.parameters.get("period", 20)
            std_dev = condition.parameters.get("std_dev", 2)
            band_type = condition.parameters.get(
                "band_type", "upper"
            )  # upper, lower, middle

            bands = self.market_data_provider.get_bollinger_bands(
                condition.symbol, period, std_dev
            )

            if not bands:
                return False

            if band_type == "upper":
                return bands["upper"]
            elif band_type == "lower":
                return bands["lower"]
            else:
                return bands["middle"]

        except Exception as e:
            print(f"Error evaluating Bollinger Bands: {e}")
            return False

    def _compare_values(
        self, actual_value: Any, operator: ConditionOperator, expected_value: Any
    ) -> bool:
        """Compare actual value with expected value using the given operator."""
        try:
            if operator in [
                ConditionOperator.EQUAL,
                ConditionOperator.NOT_EQUAL,
                ConditionOperator.GREATER_THAN,
                ConditionOperator.GREATER_EQUAL,
                ConditionOperator.LESS_THAN,
                ConditionOperator.LESS_EQUAL,
            ]:
                op_func = self.operator_map[operator.value]
                return op_func(actual_value, expected_value)

            elif operator == ConditionOperator.BETWEEN:
                if (
                    isinstance(expected_value, (list, tuple))
                    and len(expected_value) == 2
                ):
                    return expected_value[0] <= actual_value <= expected_value[1]
                return False

            elif operator == ConditionOperator.NOT_BETWEEN:
                if (
                    isinstance(expected_value, (list, tuple))
                    and len(expected_value) == 2
                ):
                    return not (expected_value[0] <= actual_value <= expected_value[1])
                return False

            elif operator == ConditionOperator.IN:
                return (
                    actual_value in expected_value
                    if hasattr(expected_value, "__contains__")
                    else False
                )

            elif operator == ConditionOperator.NOT_IN:
                return (
                    actual_value not in expected_value
                    if hasattr(expected_value, "__contains__")
                    else False
                )

            elif operator == ConditionOperator.CONTAINS:
                return (
                    expected_value in actual_value
                    if hasattr(actual_value, "__contains__")
                    else False
                )

            elif operator == ConditionOperator.NOT_CONTAINS:
                return (
                    expected_value not in actual_value
                    if hasattr(actual_value, "__contains__")
                    else False
                )

            return False

        except Exception as e:
            print(f"Error comparing values: {e}")
            return False


class RuleEngine:
    """Main engine for evaluating conditional rules."""

    def __init__(self, market_data_provider):
        self.market_data_provider = market_data_provider
        self.condition_evaluator = ConditionEvaluator(market_data_provider)
        self.rules = {}
        self.rule_history = {}

    def add_rule(self, rule: ConditionalRule) -> bool:
        """Add a conditional rule to the engine."""
        try:
            self.rules[rule.id] = rule
            self.rule_history[rule.id] = []
            return True
        except Exception as e:
            print(f"Error adding rule {rule.id}: {e}")
            return False

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a conditional rule from the engine."""
        try:
            if rule_id in self.rules:
                del self.rules[rule_id]
                if rule_id in self.rule_history:
                    del self.rule_history[rule_id]
                return True
            return False
        except Exception as e:
            print(f"Error removing rule {rule_id}: {e}")
            return False

    def evaluate_rule(self, rule: ConditionalRule, context: Dict = None) -> bool:
        """Evaluate a single conditional rule."""
        try:
            if not rule.active:
                return False

            if context is None:
                context = {}

            # Evaluate all conditions
            condition_results = []
            for condition in rule.conditions:
                if isinstance(condition, Condition):
                    result = self.condition_evaluator.evaluate_condition(
                        condition, context
                    )
                    condition_results.append(result)
                elif isinstance(condition, ConditionGroup):
                    result = self._evaluate_condition_group(condition, context)
                    condition_results.append(result)

            # Apply logical operator to combine results
            if not condition_results:
                return False

            final_result = self._apply_logical_operator(
                condition_results, rule.logical_operator
            )

            # Record evaluation in history
            evaluation_record = {
                "timestamp": datetime.now(),
                "result": final_result,
                "condition_results": condition_results,
                "context": context.copy(),
            }

            if rule.id not in self.rule_history:
                self.rule_history[rule.id] = []

            self.rule_history[rule.id].append(evaluation_record)

            # Keep only last 100 evaluations
            if len(self.rule_history[rule.id]) > 100:
                self.rule_history[rule.id] = self.rule_history[rule.id][-100:]

            return final_result

        except Exception as e:
            print(f"Error evaluating rule {rule.id}: {e}")
            return False

    def _evaluate_condition_group(self, group: ConditionGroup, context: Dict) -> bool:
        """Evaluate a group of conditions."""
        try:
            condition_results = []

            for condition in group.conditions:
                if isinstance(condition, Condition):
                    result = self.condition_evaluator.evaluate_condition(
                        condition, context
                    )
                    condition_results.append(result)
                elif isinstance(condition, ConditionGroup):
                    result = self._evaluate_condition_group(condition, context)
                    condition_results.append(result)

            if not condition_results:
                return False

            return self._apply_logical_operator(
                condition_results, group.logical_operator
            )

        except Exception as e:
            print(f"Error evaluating condition group: {e}")
            return False

    def _apply_logical_operator(
        self, results: List[bool], logical_op: LogicalOperator
    ) -> bool:
        """Apply logical operator to a list of boolean results."""
        try:
            if not results:
                return False

            if logical_op == LogicalOperator.AND:
                return all(results)
            elif logical_op == LogicalOperator.OR:
                return any(results)
            elif logical_op == LogicalOperator.NOT:
                return not results[0] if len(results) >= 1 else False
            elif logical_op == LogicalOperator.XOR:
                return sum(results) == 1
            else:
                return False

        except Exception as e:
            print(f"Error applying logical operator: {e}")
            return False

    def evaluate_all_rules(self, context: Dict = None) -> List[Dict]:
        """Evaluate all active rules and return triggered actions."""
        triggered_actions = []

        try:
            for rule_id, rule in self.rules.items():
                if not rule.active:
                    continue

                is_triggered = self.evaluate_rule(rule, context)

                if is_triggered:
                    rule.trigger_count += 1
                    rule.last_triggered = datetime.now()

                    # Prepare actions for execution
                    for action in rule.actions:
                        # Check if action should be executed (repeat limits, etc.)
                        if self._should_execute_action(action, rule):
                            triggered_actions.append(
                                {
                                    "rule_id": rule_id,
                                    "rule_name": rule.name,
                                    "action": action,
                                    "trigger_time": rule.last_triggered,
                                    "context": context.copy() if context else {},
                                }
                            )

        except Exception as e:
            print(f"Error evaluating all rules: {e}")

        return triggered_actions

    def _should_execute_action(self, action: Action, rule: ConditionalRule) -> bool:
        """Check if an action should be executed based on its configuration."""
        try:
            # Check maximum executions
            if (
                action.max_executions
                and action.execution_count >= action.max_executions
            ):
                return False

            # Check if it's a repeating action
            if not action.repeat and action.execution_count > 0:
                return False

            return True

        except Exception as e:
            print(f"Error checking action execution: {e}")
            return False


class ActionExecutor:
    """Executes actions triggered by conditional rules."""

    def __init__(self, order_manager, notification_system):
        self.order_manager = order_manager
        self.notification_system = notification_system
        self.custom_functions = {}

    def register_custom_function(self, name: str, function: Callable):
        """Register a custom function for execution."""
        self.custom_functions[name] = function

    def execute_action(self, action: Action, context: Dict) -> Dict[str, Any]:
        """Execute a single action."""
        try:
            result = {"success": False, "message": "", "data": {}}

            # Apply delay if specified
            if action.delay > 0:
                time.sleep(action.delay)

            if action.action_type == ActionType.CREATE_ORDER:
                result = self._create_order(action, context)

            elif action.action_type == ActionType.MODIFY_ORDER:
                result = self._modify_order(action, context)

            elif action.action_type == ActionType.CANCEL_ORDER:
                result = self._cancel_order(action, context)

            elif action.action_type == ActionType.CLOSE_POSITION:
                result = self._close_position(action, context)

            elif action.action_type == ActionType.SEND_NOTIFICATION:
                result = self._send_notification(action, context)

            elif action.action_type == ActionType.SET_STOP_LOSS:
                result = self._set_stop_loss(action, context)

            elif action.action_type == ActionType.SET_TAKE_PROFIT:
                result = self._set_take_profit(action, context)

            elif action.action_type == ActionType.CUSTOM_FUNCTION:
                result = self._execute_custom_function(action, context)

            # Update execution count
            if result["success"]:
                action.execution_count += 1

            return result

        except Exception as e:
            return {"success": False, "message": str(e), "data": {}}

    def _create_order(self, action: Action, context: Dict) -> Dict[str, Any]:
        """Create a new order."""
        try:
            order_params = action.parameters.copy()

            # Replace context variables in parameters
            order_params = self._substitute_context_variables(order_params, context)

            if self.order_manager:
                result = self.order_manager.create_order(order_params)
                return {"success": True, "message": "Order created", "data": result}
            else:
                return {"success": False, "message": "Order manager not available"}

        except Exception as e:
            return {"success": False, "message": f"Error creating order: {e}"}

    def _modify_order(self, action: Action, context: Dict) -> Dict[str, Any]:
        """Modify an existing order."""
        try:
            order_id = action.parameters.get("order_id")
            modifications = action.parameters.get("modifications", {})

            modifications = self._substitute_context_variables(modifications, context)

            if self.order_manager:
                result = self.order_manager.modify_order(order_id, modifications)
                return {"success": True, "message": "Order modified", "data": result}
            else:
                return {"success": False, "message": "Order manager not available"}

        except Exception as e:
            return {"success": False, "message": f"Error modifying order: {e}"}

    def _cancel_order(self, action: Action, context: Dict) -> Dict[str, Any]:
        """Cancel an existing order."""
        try:
            order_id = action.parameters.get("order_id")

            if self.order_manager:
                result = self.order_manager.cancel_order(order_id)
                return {"success": True, "message": "Order canceled", "data": result}
            else:
                return {"success": False, "message": "Order manager not available"}

        except Exception as e:
            return {"success": False, "message": f"Error canceling order: {e}"}

    def _close_position(self, action: Action, context: Dict) -> Dict[str, Any]:
        """Close a position."""
        try:
            symbol = action.parameters.get("symbol")
            close_params = action.parameters.get("close_params", {})

            close_params = self._substitute_context_variables(close_params, context)

            if self.order_manager:
                result = self.order_manager.close_position(symbol, close_params)
                return {"success": True, "message": "Position closed", "data": result}
            else:
                return {"success": False, "message": "Order manager not available"}

        except Exception as e:
            return {"success": False, "message": f"Error closing position: {e}"}

    def _send_notification(self, action: Action, context: Dict) -> Dict[str, Any]:
        """Send a notification."""
        try:
            message = action.parameters.get("message", "")
            notification_type = action.parameters.get("type", "info")
            recipients = action.parameters.get("recipients", [])

            # Substitute context variables in message
            message = self._substitute_context_variables_in_string(message, context)

            if self.notification_system:
                result = self.notification_system.send_notification(
                    message, notification_type, recipients
                )
                return {"success": True, "message": "Notification sent", "data": result}
            else:
                print(f"Notification: {message}")  # Fallback to console
                return {"success": True, "message": "Notification logged"}

        except Exception as e:
            return {"success": False, "message": f"Error sending notification: {e}"}

    def _set_stop_loss(self, action: Action, context: Dict) -> Dict[str, Any]:
        """Set stop-loss for a position."""
        try:
            symbol = action.parameters.get("symbol")
            stop_loss_params = action.parameters.copy()

            stop_loss_params = self._substitute_context_variables(
                stop_loss_params, context
            )

            if self.order_manager:
                result = self.order_manager.set_stop_loss(symbol, stop_loss_params)
                return {"success": True, "message": "Stop-loss set", "data": result}
            else:
                return {"success": False, "message": "Order manager not available"}

        except Exception as e:
            return {"success": False, "message": f"Error setting stop-loss: {e}"}

    def _set_take_profit(self, action: Action, context: Dict) -> Dict[str, Any]:
        """Set take-profit for a position."""
        try:
            symbol = action.parameters.get("symbol")
            take_profit_params = action.parameters.copy()

            take_profit_params = self._substitute_context_variables(
                take_profit_params, context
            )

            if self.order_manager:
                result = self.order_manager.set_take_profit(symbol, take_profit_params)
                return {"success": True, "message": "Take-profit set", "data": result}
            else:
                return {"success": False, "message": "Order manager not available"}

        except Exception as e:
            return {"success": False, "message": f"Error setting take-profit: {e}"}

    def _execute_custom_function(self, action: Action, context: Dict) -> Dict[str, Any]:
        """Execute a custom function."""
        try:
            function_name = action.parameters.get("function_name")
            function_params = action.parameters.get("function_params", {})

            if function_name in self.custom_functions:
                func = self.custom_functions[function_name]
                result = func(function_params, context)
                return {
                    "success": True,
                    "message": "Custom function executed",
                    "data": result,
                }
            else:
                return {
                    "success": False,
                    "message": f"Custom function '{function_name}' not found",
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"Error executing custom function: {e}",
            }

    def _substitute_context_variables(self, params: Dict, context: Dict) -> Dict:
        """Substitute context variables in parameters."""
        try:
            result = {}
            for key, value in params.items():
                if (
                    isinstance(value, str)
                    and value.startswith("{")
                    and value.endswith("}")
                ):
                    # Context variable substitution
                    var_name = value[1:-1]
                    result[key] = context.get(var_name, value)
                elif isinstance(value, dict):
                    result[key] = self._substitute_context_variables(value, context)
                else:
                    result[key] = value
            return result
        except:
            return params.copy()

    def _substitute_context_variables_in_string(self, text: str, context: Dict) -> str:
        """Substitute context variables in a string."""
        try:
            for var_name, var_value in context.items():
                placeholder = f"{{{var_name}}}"
                text = text.replace(placeholder, str(var_value))
            return text
        except:
            return text


class MockMarketDataProvider:
    """Mock market data provider for testing."""

    def __init__(self):
        import random

        self.prices = {"BTCUSDT": 45000, "ETHUSDT": 3000, "ADAUSDT": 0.5}
        self.volumes = {
            symbol: random.uniform(1000000, 5000000) for symbol in self.prices
        }

    def get_current_price(self, symbol: str) -> float:
        import random

        base = self.prices.get(symbol, 100)
        return base * (1 + random.uniform(-0.02, 0.02))

    def get_volume(self, symbol: str) -> float:
        import random

        base = self.volumes.get(symbol, 1000000)
        return base * (1 + random.uniform(-0.1, 0.1))

    def get_rsi(self, symbol: str, period: int = 14) -> float:
        import random

        return random.uniform(20, 80)

    def get_moving_average(
        self, symbol: str, period: int, ma_type: str = "simple"
    ) -> float:
        current_price = self.get_current_price(symbol)
        import random

        return current_price * (1 + random.uniform(-0.05, 0.05))

    def get_bollinger_bands(self, symbol: str, period: int, std_dev: float) -> Dict:
        current_price = self.get_current_price(symbol)
        band_width = current_price * 0.04  # 4% band width
        return {
            "upper": current_price + band_width,
            "middle": current_price,
            "lower": current_price - band_width,
        }

    def get_historical_price(self, symbol: str, hours_ago: int) -> float:
        current_price = self.get_current_price(symbol)
        import random

        return current_price * (1 + random.uniform(-0.1, 0.1))

    def get_order_status(self, order_id: str) -> str:
        import random

        statuses = ["pending", "filled", "cancelled", "partially_filled"]
        return random.choice(statuses)

    def get_position_size(self, symbol: str) -> float:
        import random

        return random.uniform(0, 10)

    def get_unrealized_pnl(self, symbol: str) -> float:
        import random

        return random.uniform(-1000, 1000)

    def get_drawdown(self, symbol: str) -> float:
        import random

        return random.uniform(0, 0.2)  # 0-20%


class ConditionalOrderEngine:
    """Main engine for conditional order management."""

    def __init__(self, db_path: Optional[str] = None):
        self.db = OrderManagementDB(db_path) if CONDITIONAL_AVAILABLE else None

        # Initialize components
        self.market_data_provider = MockMarketDataProvider()
        self.rule_engine = RuleEngine(self.market_data_provider)
        self.action_executor = ActionExecutor(
            None, None
        )  # Initialize with None for now

        # Storage
        self.active_rules = {}
        self.execution_history = []

    def create_conditional_rule(self, rule_config: Dict) -> Dict[str, Any]:
        """Create a new conditional rule."""
        try:
            rule_id = f"rule_{int(time.time())}"

            # Parse conditions
            conditions = []
            for cond_config in rule_config.get("conditions", []):
                condition = Condition(
                    name=cond_config["name"],
                    condition_type=ConditionType(cond_config["type"]),
                    operator=ConditionOperator(cond_config["operator"]),
                    value=cond_config["value"],
                    symbol=cond_config.get("symbol"),
                    timeframe=cond_config.get("timeframe"),
                    parameters=cond_config.get("parameters", {}),
                )
                conditions.append(condition)

            # Parse actions
            actions = []
            for action_config in rule_config.get("actions", []):
                action = Action(
                    name=action_config["name"],
                    action_type=ActionType(action_config["type"]),
                    parameters=action_config["parameters"],
                    delay=action_config.get("delay", 0),
                    repeat=action_config.get("repeat", False),
                    max_executions=action_config.get("max_executions"),
                )
                actions.append(action)

            # Create rule
            rule = ConditionalRule(
                id=rule_id,
                name=rule_config["name"],
                description=rule_config.get("description", ""),
                conditions=conditions,
                actions=actions,
                logical_operator=LogicalOperator(
                    rule_config.get("logical_operator", "and")
                ),
            )

            # Add to engine
            if self.rule_engine.add_rule(rule):
                self.active_rules[rule_id] = rule

                # Save to database
                if self.db:
                    rule_data = {
                        "id": rule_id,
                        "name": rule.name,
                        "type": "conditional",
                        "status": "active",
                        "created_at": rule.created_at,
                        "rule_config": json.dumps(asdict(rule), default=str),
                    }
                    # Note: Saving to orders table as conditional order type
                    # In a real implementation, you might want a separate rules table

                return {
                    "success": True,
                    "rule_id": rule_id,
                    "message": f"Conditional rule '{rule.name}' created successfully",
                }
            else:
                return {"success": False, "error": "Failed to add rule to engine"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def evaluate_rules(self) -> List[Dict]:
        """Evaluate all active rules and execute triggered actions."""
        try:
            # Build context with current market state
            context = {
                "timestamp": datetime.now(),
                "market_session": self._get_market_session(),
            }

            # Add current prices to context
            for symbol in ["BTCUSDT", "ETHUSDT", "ADAUSDT"]:
                context[f"{symbol}_price"] = (
                    self.market_data_provider.get_current_price(symbol)
                )

            # Evaluate all rules
            triggered_actions = self.rule_engine.evaluate_all_rules(context)

            execution_results = []

            # Execute triggered actions
            for action_data in triggered_actions:
                action = action_data["action"]
                rule_id = action_data["rule_id"]

                execution_result = self.action_executor.execute_action(
                    action, action_data["context"]
                )

                execution_record = {
                    "rule_id": rule_id,
                    "rule_name": action_data["rule_name"],
                    "action_name": action.name,
                    "action_type": action.action_type.value,
                    "execution_result": execution_result,
                    "triggered_at": action_data["trigger_time"],
                    "context": action_data["context"],
                }

                execution_results.append(execution_record)
                self.execution_history.append(execution_record)

                # Keep only last 1000 executions
                if len(self.execution_history) > 1000:
                    self.execution_history = self.execution_history[-1000:]

            return execution_results

        except Exception as e:
            print(f"Error evaluating rules: {e}")
            return []

    def _get_market_session(self) -> str:
        """Get current market session."""
        import datetime

        now = datetime.datetime.now()
        hour = now.hour

        if 0 <= hour < 6:
            return "asian"
        elif 6 <= hour < 14:
            return "european"
        elif 14 <= hour < 22:
            return "american"
        else:
            return "after_hours"

    def get_rule_status(self, rule_id: str) -> Optional[Dict]:
        """Get status of a specific rule."""
        if rule_id not in self.active_rules:
            return None

        rule = self.active_rules[rule_id]
        history = self.rule_engine.rule_history.get(rule_id, [])

        # Calculate statistics
        total_evaluations = len(history)
        triggered_count = sum(1 for h in history if h["result"])
        trigger_rate = (
            (triggered_count / total_evaluations * 100) if total_evaluations > 0 else 0
        )

        return {
            "rule_id": rule_id,
            "name": rule.name,
            "description": rule.description,
            "active": rule.active,
            "created_at": rule.created_at,
            "last_triggered": rule.last_triggered,
            "trigger_count": rule.trigger_count,
            "total_evaluations": total_evaluations,
            "trigger_rate": trigger_rate,
            "conditions_count": len(rule.conditions),
            "actions_count": len(rule.actions),
        }

    def pause_rule(self, rule_id: str) -> bool:
        """Pause a conditional rule."""
        if rule_id in self.active_rules:
            self.active_rules[rule_id].active = False
            return True
        return False

    def resume_rule(self, rule_id: str) -> bool:
        """Resume a conditional rule."""
        if rule_id in self.active_rules:
            self.active_rules[rule_id].active = True
            return True
        return False

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a conditional rule."""
        if rule_id in self.active_rules:
            self.rule_engine.remove_rule(rule_id)
            del self.active_rules[rule_id]
            return True
        return False

    def get_rules_summary(self) -> Dict[str, Any]:
        """Get summary of all conditional rules."""
        try:
            summary = {
                "total_rules": len(self.active_rules),
                "active_rules": sum(
                    1 for rule in self.active_rules.values() if rule.active
                ),
                "paused_rules": sum(
                    1 for rule in self.active_rules.values() if not rule.active
                ),
                "total_executions": len(self.execution_history),
                "recent_executions": len(
                    [
                        e
                        for e in self.execution_history
                        if e["triggered_at"] > datetime.now() - timedelta(hours=24)
                    ]
                ),
                "rules": [],
            }

            for rule_id in self.active_rules:
                rule_status = self.get_rule_status(rule_id)
                if rule_status:
                    summary["rules"].append(rule_status)

            return summary

        except Exception as e:
            return {"error": str(e)}


# Global conditional order engine
_conditional_engine = None


def get_conditional_engine(
    db_path: Optional[str] = None,
) -> ConditionalOrderEngine:
    """Get the global conditional order engine instance."""
    global _conditional_engine
    if _conditional_engine is None:
        _conditional_engine = ConditionalOrderEngine(db_path)
    return _conditional_engine


if __name__ == "__main__":
    # Test the conditional order engine
    engine = get_conditional_engine()

    print("Conditional Order Engine Test")
    print("=" * 40)

    # Test rule: Buy BTC when price drops below 44000 and RSI < 30
    buy_dip_rule = {
        "name": "Buy the Dip",
        "description": "Buy BTC when price drops below 44000 and RSI is oversold",
        "conditions": [
            {
                "name": "price_below_threshold",
                "type": "price",
                "operator": "<=",
                "value": 44000,
                "symbol": "BTCUSDT",
            },
            {
                "name": "rsi_oversold",
                "type": "rsi",
                "operator": "<=",
                "value": 30,
                "symbol": "BTCUSDT",
                "parameters": {"period": 14},
            },
        ],
        "actions": [
            {
                "name": "buy_btc",
                "type": "create_order",
                "parameters": {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "type": "market",
                    "quantity": 0.01,
                },
            },
            {
                "name": "notify_buy",
                "type": "send_notification",
                "parameters": {
                    "message": "Bought BTC at {BTCUSDT_price} due to oversold conditions",
                    "type": "info",
                },
            },
        ],
        "logical_operator": "and",
    }

    result = engine.create_conditional_rule(buy_dip_rule)
    print(f"Buy Dip Rule: {result}")

    # Test rule: Take profit when BTC rises 5%
    take_profit_rule = {
        "name": "Take Profit 5%",
        "description": "Sell BTC when it rises 5% from entry",
        "conditions": [
            {
                "name": "profit_target",
                "type": "percentage_change",
                "operator": ">=",
                "value": 5.0,
                "symbol": "BTCUSDT",
                "timeframe": "24h",
            }
        ],
        "actions": [
            {
                "name": "sell_btc",
                "type": "close_position",
                "parameters": {
                    "symbol": "BTCUSDT",
                    "close_params": {"percentage": 100},
                },
            }
        ],
    }

    result = engine.create_conditional_rule(take_profit_rule)
    print(f"Take Profit Rule: {result}")

    # Evaluate rules
    print("\nEvaluating rules...")
    executions = engine.evaluate_rules()
    print(f"Triggered Actions: {executions}")

    # Get summary
    summary = engine.get_rules_summary()
    print(f"Rules Summary: {summary}")
