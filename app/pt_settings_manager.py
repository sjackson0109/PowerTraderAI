"""
PowerTrader AI+ Settings Management
Centralized configuration management with validation and persistence
"""

import copy
import json
import os
from dataclasses import dataclass, asdict, fields
from typing import Any, Dict, List, Optional, Union, Callable
from pathlib import Path
import threading
from datetime import datetime
import shutil

# Trading-mode setting keys (see trading_mode.py for the order gate that enforces them)
TRADING_MODE_KEY = "trading.mode"
TRADING_ACTIVE_BROKER_KEY = "trading.active_broker"
TRADING_MODES = ("paper", "live")

PAPER_POLICY_KEY = "paper.price_fallback_policy"
PAPER_MAX_QUOTE_AGE_KEY = "paper.max_quote_age_s"
EMERGENCY_DRAWDOWN_KEY = "risk.emergency_drawdown_pct"
PRICE_FALLBACK_POLICIES = ("pause", "simulate_and_flag")
DEFAULT_PRICE_FALLBACK_POLICY = "pause"
DEFAULT_MAX_QUOTE_AGE_S = 30.0
DEFAULT_EMERGENCY_DRAWDOWN_PCT = 8.0
EMERGENCY_DRAWDOWN_RANGE = (1.0, 50.0)
MAX_QUOTE_AGE_RANGE = (1.0, 3600.0)


def _is_number_in(value: Any, bounds: tuple) -> bool:
    """True for a real number (not bool) within bounds, inclusive."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value  # not NaN
        and bounds[0] <= value <= bounds[1]
    )


def trading_testnet_key(broker: str) -> str:
    """Settings key holding the testnet/sandbox flag for ``broker``."""
    return f"trading.{broker}_testnet"


# Default settings configuration
DEFAULT_SETTINGS = {
    "coins": ["BTC", "ETH", "XRP", "DOGE", "BNB"],
    "main_neural_dir": ".",
    "hub_data_dir": "hub_data",
    "script_neural_runner2": "pt_thinker.py",
    "script_trader": "pt_trader.py",
    "script_neural_trainer": "pt_trainer.py",
    "auto_start_scripts": False,
    "api_server_enabled": False,
    "api_server_port": 8080,
    "api_server_host": "127.0.0.1",
    "chart_refresh_interval": 10,
    "max_log_lines": 1000,
    "enable_notifications": True,
    "notification_types": ["trade", "error", "profit"],
    "risk_management": {
        "max_position_size": 0.1,
        "stop_loss_percent": 0.05,
        "take_profit_percent": 0.15,
        "max_daily_loss": 0.02,
    },
    "exchange_config": {
        "default_exchange": "binance",
        "api_timeout": 30,
        "retry_attempts": 3,
        "rate_limit_buffer": 0.9,
    },
    # Trading-mode gate. Paper is always the default; Live needs an active broker.
    # "<broker>_testnet" keys default to True when absent (see get_testnet()).
    "trading": {
        "mode": "paper",
        "active_broker": None,
        "binance_testnet": True,
    },
    # Paper-fill price integrity (FDS-096b). "pause" never fills on a stale or
    # simulated price; "simulate_and_flag" fills but marks the fill.
    "paper": {
        "price_fallback_policy": "pause",
        "max_quote_age_s": 30,
    },
    # Account drawdown (from the peak the trader has seen) that halts trading.
    "risk": {
        "emergency_drawdown_pct": 8.0,
    },
    # Signal source (FDS-121). "catalogue" = deterministic rule-based strategies;
    # "legacy_neural" = the old (untrained, mock) trainer files. An unknown engine
    # or strategy id places no orders (the trader fails closed).
    "strategy": {
        "engine": "catalogue",
        "active_id": "STRAT-000",
        "symbols": ["BTCUSDT"],
        "timeframe": "1h",
        "overlays": [],
    },
    "neural_config": {
        "training_epochs": 100,
        "batch_size": 32,
        "learning_rate": 0.001,
        "lookback_days": 30,
        "prediction_horizon": 24,
    },
    "ui_config": {
        "theme": "dark",
        "font_size": 9,
        "chart_height": 400,
        "refresh_interval": 5000,
        "show_tooltips": True,
    },
}

SETTINGS_FILE = "pt_config.json"


STRATEGY_ENGINES = ("catalogue", "legacy_neural")


def _is_valid_timeframe(value: Any) -> bool:
    from market_data.timeframes import TIMEFRAME_SECONDS

    return isinstance(value, str) and value in TIMEFRAME_SECONDS


def _is_valid_broker_id(value: Any) -> bool:
    """True for None (no broker) or a string matching an ``ExchangeType`` value."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    from pt_exchange_abstraction import ExchangeType

    try:
        ExchangeType(value)
    except ValueError:
        return False
    return True


@dataclass
class SettingsValidationRule:
    """Rule for validating a settings field."""

    field_path: str
    validator: Callable[[Any], bool]
    error_message: str
    auto_fix: Optional[Callable[[Any], Any]] = None


class SettingsValidator:
    """
    Validates settings values and provides auto-fixing capabilities.
    """

    def __init__(self):
        self.rules: List[SettingsValidationRule] = []
        self._setup_default_rules()

    def _setup_default_rules(self):
        """Setup default validation rules."""

        # Coins validation
        self.add_rule(
            "coins",
            lambda v: isinstance(v, list)
            and len(v) > 0
            and all(isinstance(coin, str) for coin in v),
            "Coins must be a non-empty list of strings",
            lambda v: (
                ["BTC"]
                if not isinstance(v, list) or len(v) == 0
                else [str(coin).upper().strip() for coin in v]
            ),
        )

        # Port validation
        self.add_rule(
            "api_server_port",
            lambda v: isinstance(v, int) and 1024 <= v <= 65535,
            "API server port must be an integer between 1024 and 65535",
            lambda v: max(
                1024, min(65535, int(v) if isinstance(v, (int, float)) else 8080)
            ),
        )

        # Host validation
        self.add_rule(
            "api_server_host",
            lambda v: isinstance(v, str) and len(v.strip()) > 0,
            "API server host must be a non-empty string",
            lambda v: "127.0.0.1",
        )

        # Interval validation
        self.add_rule(
            "chart_refresh_interval",
            lambda v: isinstance(v, (int, float)) and v >= 1,
            "Chart refresh interval must be a number >= 1",
            lambda v: max(1, float(v) if isinstance(v, (int, float)) else 10),
        )

        # Risk management validation
        self.add_rule(
            "risk_management.max_position_size",
            lambda v: isinstance(v, (int, float)) and 0 < v <= 1,
            "Max position size must be between 0 and 1",
            lambda v: max(
                0.01, min(1.0, float(v) if isinstance(v, (int, float)) else 0.1)
            ),
        )

        self.add_rule(
            "risk_management.stop_loss_percent",
            lambda v: isinstance(v, (int, float)) and 0 < v <= 1,
            "Stop loss percent must be between 0 and 1",
            lambda v: max(
                0.001, min(1.0, float(v) if isinstance(v, (int, float)) else 0.05)
            ),
        )

        # Trading mode / broker validation (fail closed: bad values fall back to
        # paper / no broker, never to live)
        self.add_rule(
            TRADING_MODE_KEY,
            lambda v: isinstance(v, str) and v in TRADING_MODES,
            "Trading mode must be 'paper' or 'live'",
            lambda v: "paper",
        )

        self.add_rule(
            TRADING_ACTIVE_BROKER_KEY,
            _is_valid_broker_id,
            "Active broker must be null or a supported exchange id",
            lambda v: None,
        )

        # Paper price integrity + drawdown stop (invalid -> safe default)
        self.add_rule(
            PAPER_POLICY_KEY,
            lambda v: isinstance(v, str) and v in PRICE_FALLBACK_POLICIES,
            "Price fallback policy must be 'pause' or 'simulate_and_flag'",
            lambda v: DEFAULT_PRICE_FALLBACK_POLICY,
        )
        self.add_rule(
            PAPER_MAX_QUOTE_AGE_KEY,
            lambda v: _is_number_in(v, MAX_QUOTE_AGE_RANGE),
            "Max quote age must be between 1 and 3600 seconds",
            lambda v: DEFAULT_MAX_QUOTE_AGE_S,
        )
        self.add_rule(
            EMERGENCY_DRAWDOWN_KEY,
            lambda v: _is_number_in(v, EMERGENCY_DRAWDOWN_RANGE),
            "Emergency drawdown must be between 1 and 50 percent",
            lambda v: DEFAULT_EMERGENCY_DRAWDOWN_PCT,
        )

        # Strategy engine settings. No auto-fix on purpose: a wrong engine / id is
        # reported, kept as written, and makes the trader place no orders, rather
        # than silently trading a strategy the user did not choose.
        self.add_rule(
            "strategy.engine",
            lambda v: v in STRATEGY_ENGINES,
            "Strategy engine must be 'catalogue' or 'legacy_neural'",
        )
        self.add_rule(
            "strategy.active_id",
            lambda v: isinstance(v, str) and bool(v.strip()),
            "Active strategy id must be a non-empty string",
        )
        self.add_rule(
            "strategy.symbols",
            lambda v: isinstance(v, list)
            and bool(v)
            and all(isinstance(s, str) and s.strip() for s in v),
            "Strategy symbols must be a non-empty list of symbol strings",
        )
        self.add_rule(
            "strategy.timeframe",
            _is_valid_timeframe,
            "Strategy timeframe must be a supported candle timeframe",
        )
        self.add_rule(
            "strategy.overlays",
            lambda v: isinstance(v, list)
            and all(isinstance(o, dict) and isinstance(o.get("id"), str) for o in v),
            "Strategy overlays must be a list of {id, params} objects",
        )

        # Neural config validation
        self.add_rule(
            "neural_config.training_epochs",
            lambda v: isinstance(v, int) and v >= 1,
            "Training epochs must be a positive integer",
            lambda v: max(1, int(v) if isinstance(v, (int, float)) else 100),
        )

        self.add_rule(
            "neural_config.batch_size",
            lambda v: isinstance(v, int) and v >= 1,
            "Batch size must be a positive integer",
            lambda v: max(1, int(v) if isinstance(v, (int, float)) else 32),
        )

    def add_rule(
        self,
        field_path: str,
        validator: Callable[[Any], bool],
        error_message: str,
        auto_fix: Optional[Callable[[Any], Any]] = None,
    ):
        """Add a validation rule."""
        rule = SettingsValidationRule(field_path, validator, error_message, auto_fix)
        self.rules.append(rule)

    def validate(
        self, settings: Dict[str, Any], auto_fix: bool = False
    ) -> tuple[bool, List[str]]:
        """Validate settings and optionally auto-fix issues."""
        errors = []
        is_valid = True

        for rule in self.rules:
            value = self._get_nested_value(settings, rule.field_path)

            if value is None:
                # Field is missing - try to set default if auto_fix
                if auto_fix and rule.auto_fix:
                    default_value = self._get_nested_value(
                        DEFAULT_SETTINGS, rule.field_path
                    )
                    if default_value is not None:
                        self._set_nested_value(settings, rule.field_path, default_value)
                continue

            if not rule.validator(value):
                is_valid = False
                errors.append(f"{rule.field_path}: {rule.error_message}")

                if auto_fix and rule.auto_fix:
                    try:
                        fixed_value = rule.auto_fix(value)
                        self._set_nested_value(settings, rule.field_path, fixed_value)
                        errors[-1] += f" (auto-fixed to {fixed_value})"
                    except Exception as e:
                        errors[-1] += f" (auto-fix failed: {e})"

        return is_valid or auto_fix, errors

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get a nested value using dot notation."""
        keys = path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current

    def _set_nested_value(self, data: Dict[str, Any], path: str, value: Any):
        """Set a nested value using dot notation."""
        keys = path.split(".")
        current = data

        # Navigate to the parent of the target key
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # Set the final value
        current[keys[-1]] = value


class SettingsManager:
    """
    Manages application settings with validation, persistence, and change notifications.
    """

    def __init__(
        self, settings_file: str = SETTINGS_FILE, settings_dir: Optional[str] = None
    ):
        self.settings_file = settings_file
        self.settings_dir = settings_dir
        self.validator = SettingsValidator()
        self._settings: Dict[str, Any] = {}
        self._callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._lock = threading.RLock()

        # Determine full settings path
        if self.settings_dir:
            self.settings_path = os.path.join(self.settings_dir, self.settings_file)
        else:
            # Default to same directory as this module
            module_dir = os.path.dirname(os.path.abspath(__file__))
            self.settings_path = os.path.join(module_dir, self.settings_file)

        # Load settings
        self.load_settings()

    def load_settings(self) -> bool:
        """Load settings from file."""
        with self._lock:
            try:
                if os.path.exists(self.settings_path):
                    with open(self.settings_path, "r", encoding="utf-8") as f:
                        loaded_settings = json.load(f)

                    if not isinstance(loaded_settings, dict):
                        loaded_settings = {}
                else:
                    loaded_settings = {}

                # Merge with defaults (deep copy: nested sections such as
                # "trading" must never alias DEFAULT_SETTINGS, or a later set()
                # would rewrite the defaults themselves)
                self._settings = self._merge_settings(
                    copy.deepcopy(DEFAULT_SETTINGS), loaded_settings
                )

                # Normalize coins
                if "coins" in self._settings:
                    self._settings["coins"] = [
                        c.upper().strip()
                        for c in self._settings["coins"]
                        if str(c).strip()
                    ]

                # Validate and auto-fix
                is_valid, errors = self.validator.validate(
                    self._settings, auto_fix=True
                )

                if errors:
                    try:
                        from pt_logging_system import log_warning

                        for error in errors:
                            log_warning(f"Settings validation issue: {error}")
                    except ImportError:
                        print(f"Settings validation issues: {errors}")

                # Save if auto-fixes were applied
                if not is_valid:
                    self.save_settings()

                return True

            except Exception as e:
                try:
                    from pt_logging_system import log_error

                    log_error(f"Failed to load settings from {self.settings_path}: {e}")
                except ImportError:
                    print(f"Failed to load settings: {e}")

                # Fall back to defaults
                self._settings = copy.deepcopy(DEFAULT_SETTINGS)
                return False

    def save_settings(self) -> bool:
        """Save settings to file."""
        with self._lock:
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)

                # Create backup if file exists
                if os.path.exists(self.settings_path):
                    backup_path = f"{self.settings_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    shutil.copy2(self.settings_path, backup_path)

                    # Keep only last 5 backups
                    self._cleanup_backups()

                # Write settings atomically so another process (the trader reads
                # trading.mode before every order) never sees a half-written file
                tmp_path = f"{self.settings_path}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._settings, f, indent=2, sort_keys=True)
                os.replace(tmp_path, self.settings_path)

                # Notify callbacks
                for callback in self._callbacks:
                    try:
                        callback(self._settings.copy())
                    except Exception as e:
                        try:
                            from pt_logging_system import log_error

                            log_error(f"Settings callback error: {e}")
                        except ImportError:
                            print(f"Settings callback error: {e}")

                return True

            except Exception as e:
                try:
                    from pt_logging_system import log_error

                    log_error(f"Failed to save settings to {self.settings_path}: {e}")
                except ImportError:
                    print(f"Failed to save settings: {e}")
                return False

    def get(self, key: str = None, default: Any = None) -> Any:
        """Get a setting value."""
        with self._lock:
            if key is None:
                return self._settings.copy()

            # Support dot notation for nested access
            if "." in key:
                return self._get_nested_value(self._settings, key, default)
            else:
                return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> bool:
        """Set a setting value."""
        with self._lock:
            try:
                # Support dot notation for nested setting
                if "." in key:
                    self._set_nested_value(self._settings, key, value)
                else:
                    self._settings[key] = value

                # Validate the change
                is_valid, errors = self.validator.validate(
                    self._settings, auto_fix=False
                )

                if not is_valid:
                    # Revert the change
                    if "." in key:
                        original_value = self._get_nested_value(DEFAULT_SETTINGS, key)
                        self._set_nested_value(self._settings, key, original_value)
                    else:
                        if key in DEFAULT_SETTINGS:
                            self._settings[key] = DEFAULT_SETTINGS[key]
                        else:
                            del self._settings[key]

                    try:
                        from pt_logging_system import log_error

                        log_error(f"Invalid setting value for {key}: {errors}")
                    except ImportError:
                        print(f"Invalid setting value for {key}: {errors}")

                    return False

                return True

            except Exception as e:
                try:
                    from pt_logging_system import log_error

                    log_error(f"Error setting {key}: {e}")
                except ImportError:
                    print(f"Error setting {key}: {e}")
                return False

    def update(self, new_settings: Dict[str, Any], merge: bool = True) -> bool:
        """Update multiple settings at once."""
        with self._lock:
            if merge:
                # Merge with existing settings
                original_settings = self._settings.copy()
                self._settings = self._merge_settings(self._settings, new_settings)
            else:
                # Replace settings entirely
                original_settings = self._settings.copy()
                self._settings = self._merge_settings(
                    copy.deepcopy(DEFAULT_SETTINGS), new_settings
                )

            # Validate the updated settings
            is_valid, errors = self.validator.validate(self._settings, auto_fix=True)

            if errors:
                try:
                    from pt_logging_system import log_warning

                    for error in errors:
                        log_warning(f"Settings validation during update: {error}")
                except ImportError:
                    print(f"Settings validation issues during update: {errors}")

            return True

    def reset_to_defaults(self) -> bool:
        """Reset all settings to defaults."""
        with self._lock:
            self._settings = copy.deepcopy(DEFAULT_SETTINGS)
            return self.save_settings()

    # --- Trading mode accessors -------------------------------------------
    # These only expose/validate the persisted values. The enforcement point
    # that every order passes through is trading_mode.resolve_order_target().

    def get_trading_mode(self) -> str:
        """Return "live" only when explicitly set to live; anything else is "paper"."""
        mode = self.get(TRADING_MODE_KEY, "paper")
        return "live" if mode == "live" else "paper"

    def get_active_broker(self) -> Optional[str]:
        """Return the active broker id, or None when unset/invalid."""
        broker = self.get(TRADING_ACTIVE_BROKER_KEY)
        return broker if broker and _is_valid_broker_id(broker) else None

    def get_testnet(self, broker: str) -> bool:
        """Testnet flag for ``broker``; defaults to True (the safe choice)."""
        return bool(self.get(trading_testnet_key(broker), True))

    def get_price_fallback_policy(self) -> str:
        """"simulate_and_flag" only when explicitly set; anything else is "pause"."""
        policy = self.get(PAPER_POLICY_KEY, DEFAULT_PRICE_FALLBACK_POLICY)
        return policy if policy in PRICE_FALLBACK_POLICIES else DEFAULT_PRICE_FALLBACK_POLICY

    def set_price_fallback_policy(self, policy: str, persist: bool = True) -> bool:
        if policy not in PRICE_FALLBACK_POLICIES:
            return False
        if not self.set(PAPER_POLICY_KEY, policy):
            return False
        return self.save_settings() if persist else True

    def set_active_broker(self, broker: Optional[str], persist: bool = True) -> bool:
        """Select the broker used when trading live (None clears it)."""
        if not _is_valid_broker_id(broker):
            return False
        # Clearing the broker while live would leave live mode half-configured,
        # so fall back to paper in the same write.
        if broker is None and self.get_trading_mode() == "live":
            self.set(TRADING_MODE_KEY, "paper")
        if not self.set(TRADING_ACTIVE_BROKER_KEY, broker):
            return False
        return self.save_settings() if persist else True

    def set_testnet(self, broker: str, enabled: bool, persist: bool = True) -> bool:
        """Persist the testnet/sandbox flag for ``broker``."""
        if not _is_valid_broker_id(broker) or broker is None:
            return False
        if not self.set(trading_testnet_key(broker), bool(enabled)):
            return False
        return self.save_settings() if persist else True

    def set_trading_mode(
        self, mode: str, broker: Optional[str] = None, persist: bool = True
    ) -> bool:
        """
        Switch between paper and live.

        Live is refused (returns False, nothing changed) unless a valid broker
        is passed or already active. ``broker`` also updates the active broker.
        """
        if mode not in TRADING_MODES:
            return False
        if broker is not None and not _is_valid_broker_id(broker):
            return False
        effective_broker = broker if broker is not None else self.get_active_broker()
        if mode == "live" and not effective_broker:
            return False

        if broker is not None and not self.set(TRADING_ACTIVE_BROKER_KEY, broker):
            return False
        if not self.set(TRADING_MODE_KEY, mode):
            return False
        return self.save_settings() if persist else True

    def get_coins(self) -> List[str]:
        """Get the list of coins."""
        return [c.upper().strip() for c in self.get("coins", [])]

    def add_coin(self, coin: str) -> bool:
        """Add a coin to the list."""
        coin = coin.upper().strip()
        if not coin:
            return False

        coins = self.get_coins()
        if coin not in coins:
            coins.append(coin)
            return self.set("coins", coins)
        return True

    def remove_coin(self, coin: str) -> bool:
        """Remove a coin from the list."""
        coin = coin.upper().strip()
        coins = self.get_coins()

        if coin in coins:
            coins.remove(coin)
            return self.set("coins", coins)
        return True

    def register_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Register a callback for settings changes."""
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable):
        """Unregister a settings callback."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def get_validation_errors(self) -> List[str]:
        """Get current validation errors without auto-fixing."""
        is_valid, errors = self.validator.validate(
            self._settings.copy(), auto_fix=False
        )
        return errors

    def export_settings(self, file_path: str) -> bool:
        """Export settings to a file."""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2, sort_keys=True)
            return True
        except Exception as e:
            try:
                from pt_logging_system import log_error

                log_error(f"Failed to export settings to {file_path}: {e}")
            except ImportError:
                print(f"Failed to export settings: {e}")
            return False

    def import_settings(self, file_path: str) -> bool:
        """Import settings from a file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                imported_settings = json.load(f)

            if isinstance(imported_settings, dict):
                return self.update(imported_settings, merge=False)
            else:
                try:
                    from pt_logging_system import log_error

                    log_error(f"Invalid settings format in {file_path}")
                except ImportError:
                    print(f"Invalid settings format in {file_path}")
                return False

        except Exception as e:
            try:
                from pt_logging_system import log_error

                log_error(f"Failed to import settings from {file_path}: {e}")
            except ImportError:
                print(f"Failed to import settings: {e}")
            return False

    def _merge_settings(
        self, base: Dict[str, Any], override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Recursively merge two settings dictionaries."""
        result = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._merge_settings(result[key], value)
            else:
                result[key] = value

        return result

    def _get_nested_value(
        self, data: Dict[str, Any], path: str, default: Any = None
    ) -> Any:
        """Get a nested value using dot notation."""
        keys = path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current

    def _set_nested_value(self, data: Dict[str, Any], path: str, value: Any):
        """Set a nested value using dot notation."""
        keys = path.split(".")
        current = data

        # Navigate to the parent of the target key
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            elif not isinstance(current[key], dict):
                current[key] = {}  # Override non-dict values
            current = current[key]

        # Set the final value
        current[keys[-1]] = value

    def _cleanup_backups(self):
        """Keep only the last 5 backup files."""
        try:
            backup_pattern = f"{self.settings_path}.backup.*"
            backup_dir = os.path.dirname(self.settings_path)
            backup_files = []

            for file in os.listdir(backup_dir):
                file_path = os.path.join(backup_dir, file)
                if file.startswith(f"{os.path.basename(self.settings_path)}.backup."):
                    backup_files.append((file_path, os.path.getmtime(file_path)))

            # Sort by modification time (newest first)
            backup_files.sort(key=lambda x: x[1], reverse=True)

            # Remove old backups (keep only 5 newest)
            for backup_path, _ in backup_files[5:]:
                try:
                    os.unlink(backup_path)
                except Exception:
                    pass

        except Exception:
            pass


# Global settings manager instance
_global_settings_manager: Optional[SettingsManager] = None


def get_settings_manager() -> SettingsManager:
    """Get the global settings manager instance."""
    global _global_settings_manager
    if _global_settings_manager is None:
        _global_settings_manager = SettingsManager()
    return _global_settings_manager


def setup_settings_manager(
    settings_file: str = SETTINGS_FILE, settings_dir: Optional[str] = None
) -> SettingsManager:
    """Setup and return the global settings manager."""
    global _global_settings_manager
    _global_settings_manager = SettingsManager(settings_file, settings_dir)
    return _global_settings_manager


# Convenience functions for common settings operations
def get_setting(key: str, default: Any = None) -> Any:
    """Get a setting value using the global manager."""
    return get_settings_manager().get(key, default)


def set_setting(key: str, value: Any) -> bool:
    """Set a setting value using the global manager."""
    return get_settings_manager().set(key, value)


def save_settings() -> bool:
    """Save settings using the global manager."""
    return get_settings_manager().save_settings()


def get_coins() -> List[str]:
    """Get the coins list using the global manager."""
    return get_settings_manager().get_coins()


if __name__ == "__main__":
    # Example usage
    settings_manager = SettingsManager("test_settings.json")

    # Test basic operations
    print("Initial settings:")
    print(json.dumps(settings_manager.get(), indent=2))

    # Test setting values
    print("\nTesting setting values...")
    settings_manager.set("api_server_port", 9000)
    settings_manager.set("neural_config.learning_rate", 0.002)

    # Test adding coins
    settings_manager.add_coin("ADA")
    settings_manager.add_coin("DOT")

    print("\nUpdated coins:", settings_manager.get_coins())

    # Test validation
    print("\nTesting validation...")
    errors = settings_manager.get_validation_errors()
    if errors:
        print("Validation errors:", errors)
    else:
        print("All settings valid!")

    # Test invalid value (should be rejected)
    success = settings_manager.set("api_server_port", "invalid")
    print(f"Setting invalid port: {success}")
    print(f"Port value after invalid set: {settings_manager.get('api_server_port')}")

    # Save settings
    settings_manager.save_settings()
    print("\nSettings saved successfully!")

    # Clean up test file
    try:
        os.unlink("test_settings.json")
        print("Test file cleaned up.")
    except Exception:
        pass
