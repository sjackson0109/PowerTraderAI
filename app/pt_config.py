"""
PowerTraderAI+ Configuration Management Module
Advanced configuration handling with validation, hot-reloading, and environment support.
"""

import configparser
import json
import logging
import os
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, Union

import yaml

# Optional imports for advanced features
try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = None

from pt_errors import ConfigurationError, ErrorSeverity, ValidationError, handle_errors
from pt_utils import ConfigurationValidator, SafeFileHandler


@dataclass
class TradingConfig:
    """Trading strategy configuration parameters."""

    # Basic trading parameters
    default_amount: float = 100.0
    max_position_size: float = 1000.0
    min_trade_amount: float = 10.0
    max_daily_trades: int = 50

    # Risk management
    stop_loss_percent: float = 2.0
    take_profit_percent: float = 5.0
    max_drawdown_percent: float = 10.0
    position_size_percent: float = 5.0

    # Timeframes and intervals
    primary_timeframe: str = "1h"
    analysis_timeframes: List[str] = field(
        default_factory=lambda: ["5m", "15m", "1h", "4h"]
    )
    update_interval: int = 60  # seconds

    # Neural network parameters
    learning_rate: float = 0.001
    epochs: int = 100
    batch_size: int = 32
    validation_split: float = 0.2

    # API settings
    api_timeout: int = 30
    api_retry_count: int = 3
    rate_limit_per_minute: int = 60


@dataclass
class ExchangeConfig:
    """Exchange-specific configuration."""

    name: str
    api_key: str = ""
    api_secret: str = ""
    sandbox: bool = True
    base_url: str = ""

    # Trading pairs
    primary_pair: str = "BTC-USD"
    supported_pairs: List[str] = field(
        default_factory=lambda: ["BTC-USD", "ETH-USD", "LTC-USD"]
    )

    # Fees and limits
    trading_fee: float = 0.1  # percent
    withdrawal_fee: float = 0.0
    min_order_size: float = 10.0
    max_order_size: float = 10000.0


@dataclass
class SecurityConfig:
    """Security and authentication configuration."""

    enable_encryption: bool = True
    key_rotation_days: int = 30
    session_timeout: int = 3600  # seconds
    max_login_attempts: int = 3

    # API security
    require_api_signature: bool = True
    api_key_length: int = 32
    webhook_secret: str = ""

    # Logging and audit
    enable_audit_log: bool = True
    log_retention_days: int = 90
    enable_debug_mode: bool = False


@dataclass
class UIConfig:
    """User interface configuration."""

    theme: str = "dark"
    font_size: int = 11
    chart_refresh_rate: int = 1000  # milliseconds
    enable_animations: bool = True

    # Window settings
    window_width: int = 1200
    window_height: int = 800
    auto_save_layout: bool = True

    # Notifications
    enable_notifications: bool = True
    notification_types: List[str] = field(
        default_factory=lambda: ["trades", "errors", "alerts"]
    )
    sound_enabled: bool = True


@dataclass
class SystemConfig:
    """System and performance configuration."""

    # Logging
    log_level: str = "INFO"
    log_file_path: str = "logs/powertrader.log"
    max_log_size_mb: int = 100
    log_backup_count: int = 5

    # Performance
    enable_performance_monitoring: bool = True
    metrics_collection_interval: float = 1.0
    cache_size_mb: int = 100
    thread_pool_size: int = 10

    # Data storage
    data_directory: str = "data"
    backup_directory: str = "backups"
    auto_backup_hours: int = 24
    max_backup_files: int = 30


class ConfigValidator:
    """Validates configuration parameters and constraints."""

    @staticmethod
    def validate_trading_config(config: TradingConfig) -> List[str]:
        """Validate trading configuration parameters."""
        errors = []

        if config.default_amount <= 0:
            errors.append("default_amount must be positive")

        if config.max_position_size < config.default_amount:
            errors.append("max_position_size must be >= default_amount")

        if config.stop_loss_percent <= 0 or config.stop_loss_percent > 50:
            errors.append("stop_loss_percent must be between 0 and 50")

        if config.take_profit_percent <= config.stop_loss_percent:
            errors.append("take_profit_percent must be > stop_loss_percent")

        if not ConfigurationValidator.validate_timeframe(config.primary_timeframe):
            errors.append(f"Invalid primary_timeframe: {config.primary_timeframe}")

        for tf in config.analysis_timeframes:
            if not ConfigurationValidator.validate_timeframe(tf):
                errors.append(f"Invalid analysis timeframe: {tf}")

        return errors

    @staticmethod
    def validate_exchange_config(config: ExchangeConfig) -> List[str]:
        """Validate exchange configuration parameters."""
        errors = []

        if not config.name:
            errors.append("Exchange name is required")

        if not config.primary_pair or not ConfigurationValidator.validate_symbol(
            config.primary_pair
        ):
            errors.append(f"Invalid primary_pair: {config.primary_pair}")

        for pair in config.supported_pairs:
            if not ConfigurationValidator.validate_symbol(pair):
                errors.append(f"Invalid supported pair: {pair}")

        if config.trading_fee < 0 or config.trading_fee > 5:
            errors.append("trading_fee must be between 0 and 5 percent")

        if config.min_order_size >= config.max_order_size:
            errors.append("min_order_size must be < max_order_size")

        return errors

    @staticmethod
    def validate_security_config(config: SecurityConfig) -> List[str]:
        """Validate security configuration parameters."""
        errors = []

        if config.session_timeout < 60 or config.session_timeout > 86400:
            errors.append("session_timeout must be between 60 and 86400 seconds")

        if config.max_login_attempts < 1 or config.max_login_attempts > 10:
            errors.append("max_login_attempts must be between 1 and 10")

        if config.api_key_length < 16 or config.api_key_length > 128:
            errors.append("api_key_length must be between 16 and 128")

        return errors


if WATCHDOG_AVAILABLE:

    class ConfigFileHandler(FileSystemEventHandler):
        """Handles configuration file changes for hot-reloading."""

        def __init__(self, config_manager):
            self.config_manager = config_manager
            self.logger = logging.getLogger(__name__)

        def on_modified(self, event):
            """Handle file modification events."""
            if event.is_directory:
                return

            if event.src_path in self.config_manager.watched_files:
                self.logger.info(f"Configuration file changed: {event.src_path}")
                self.config_manager.reload_config()

else:

    class ConfigFileHandler:
        """Dummy handler when watchdog is not available."""

        def __init__(self, config_manager):
            pass


class ConfigurationManager:
    """Advanced configuration management with validation and hot-reloading."""

    def __init__(
        self, config_dir: Union[str, Path] = "config", enable_hot_reload: bool = True
    ):
        """
        Initialize configuration manager.

        Args:
            config_dir: Directory containing configuration files
            enable_hot_reload: Whether to watch for file changes
        """
        self.config_dir = Path(config_dir)
        self.enable_hot_reload = enable_hot_reload
        self.logger = logging.getLogger(__name__)

        # Configuration instances
        self.trading = TradingConfig()
        self.exchange = ExchangeConfig("")  # No default exchange - user must configure
        self.security = SecurityConfig()
        self.ui = UIConfig()
        self.system = SystemConfig()

        # File watching
        self.observer = None
        self.watched_files: List[str] = []
        self.config_handlers = {}

        # Change callbacks
        self.change_callbacks: List[Callable] = []

        # Environment-specific overrides
        self.environment = os.getenv("POWERTRADER_ENV", "development")

        self._setup_config_directory()
        self._register_config_handlers()
        self.load_all_configs()

        if self.enable_hot_reload:
            self._start_file_watching()

    def _setup_config_directory(self) -> None:
        """Ensure configuration directory exists."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Configuration directory: {self.config_dir}")
        except Exception as e:
            raise ConfigurationError(f"Failed to create config directory: {e}")

    def _register_config_handlers(self) -> None:
        """Register configuration file handlers."""
        self.config_handlers = {
            "trading.yaml": self._load_trading_config,
            "exchange.yaml": self._load_exchange_config,
            "security.yaml": self._load_security_config,
            "ui.yaml": self._load_ui_config,
            "system.yaml": self._load_system_config,
        }

    @handle_errors(category="configuration", severity=ErrorSeverity.HIGH)
    def load_all_configs(self) -> None:
        """Load all configuration files."""
        self.logger.info("Loading configuration files...")

        for filename, handler in self.config_handlers.items():
            try:
                handler()
            except Exception as e:
                self.logger.error(f"Failed to load {filename}: {e}")
                # Continue loading other configs even if one fails

        self._apply_environment_overrides()
        self._validate_all_configs()
        self.logger.info("Configuration loading completed")

    def _load_trading_config(self) -> None:
        """Load trading configuration from file."""
        config_path = self.config_dir / "trading.yaml"
        self._load_config_file(config_path, self.trading, TradingConfig)

    def _load_exchange_config(self) -> None:
        """Load exchange configuration from file."""
        config_path = self.config_dir / "exchange.yaml"
        self._load_config_file(config_path, self.exchange, ExchangeConfig)

    def _load_security_config(self) -> None:
        """Load security configuration from file."""
        config_path = self.config_dir / "security.yaml"
        self._load_config_file(config_path, self.security, SecurityConfig)

    def _load_ui_config(self) -> None:
        """Load UI configuration from file."""
        config_path = self.config_dir / "ui.yaml"
        self._load_config_file(config_path, self.ui, UIConfig)

    def _load_system_config(self) -> None:
        """Load system configuration from file."""
        config_path = self.config_dir / "system.yaml"
        self._load_config_file(config_path, self.system, SystemConfig)

    def _load_config_file(
        self, file_path: Path, config_instance: Any, config_class: Type
    ) -> None:
        """Load configuration from YAML file into dataclass instance."""
        if not file_path.exists():
            self.logger.warning(f"Config file not found: {file_path}, using defaults")
            self._save_default_config(file_path, config_instance)
            return

        try:
            with open(file_path, "r") as f:
                data = yaml.safe_load(f) or {}

            # Update config instance with loaded data
            field_names = {field.name for field in fields(config_class)}
            for key, value in data.items():
                if key in field_names:
                    setattr(config_instance, key, value)
                else:
                    self.logger.warning(f"Unknown config key '{key}' in {file_path}")

            # Track this file for hot-reloading
            self.watched_files.append(str(file_path))
            self.logger.debug(f"Loaded config from {file_path}")

        except Exception as e:
            raise ConfigurationError(f"Failed to load {file_path}: {e}")

    def _save_default_config(self, file_path: Path, config_instance: Any) -> None:
        """Save default configuration to file."""
        try:
            # Convert dataclass to dict
            config_dict = self._dataclass_to_dict(config_instance)

            with open(file_path, "w") as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)

            self.logger.info(f"Created default config file: {file_path}")

        except Exception as e:
            self.logger.error(f"Failed to save default config {file_path}: {e}")

    def _dataclass_to_dict(self, instance: Any) -> Dict[str, Any]:
        """Convert dataclass instance to dictionary."""
        result = {}
        for field in fields(instance):
            value = getattr(instance, field.name)
            if isinstance(value, list):
                result[field.name] = value.copy()
            else:
                result[field.name] = value
        return result

    def _apply_environment_overrides(self) -> None:
        """Apply environment-specific configuration overrides."""
        env_file = self.config_dir / f"environment.{self.environment}.yaml"
        if env_file.exists():
            try:
                with open(env_file, "r") as f:
                    overrides = yaml.safe_load(f) or {}

                self._apply_overrides(overrides)
                self.logger.info(
                    f"Applied environment overrides for: {self.environment}"
                )

            except Exception as e:
                self.logger.error(f"Failed to apply environment overrides: {e}")

    def _apply_overrides(self, overrides: Dict[str, Any]) -> None:
        """Apply configuration overrides from environment file."""
        override_mapping = {
            "trading": self.trading,
            "exchange": self.exchange,
            "security": self.security,
            "ui": self.ui,
            "system": self.system,
        }

        for section, config_data in overrides.items():
            if section in override_mapping and isinstance(config_data, dict):
                config_instance = override_mapping[section]
                for key, value in config_data.items():
                    if hasattr(config_instance, key):
                        setattr(config_instance, key, value)
                        self.logger.debug(f"Override {section}.{key} = {value}")

    def _validate_all_configs(self) -> None:
        """Validate all configuration instances."""
        validation_errors = []

        validation_errors.extend(ConfigValidator.validate_trading_config(self.trading))
        validation_errors.extend(
            ConfigValidator.validate_exchange_config(self.exchange)
        )
        validation_errors.extend(
            ConfigValidator.validate_security_config(self.security)
        )

        if validation_errors:
            error_msg = "Configuration validation errors:\\n" + "\\n".join(
                validation_errors
            )
            raise ConfigurationError(error_msg)

        self.logger.info("All configurations validated successfully")

    def _start_file_watching(self) -> None:
        """Start watching configuration files for changes."""
        if not WATCHDOG_AVAILABLE:
            self.logger.warning("Watchdog not available, hot-reloading disabled")
            return

        if not self.watched_files:
            return

        try:
            event_handler = ConfigFileHandler(self)
            self.observer = Observer()
            self.observer.schedule(event_handler, str(self.config_dir), recursive=True)
            self.observer.start()
            self.logger.info("Started configuration file watching")

        except Exception as e:
            self.logger.error(f"Failed to start file watching: {e}")

    def reload_config(self) -> None:
        """Reload configuration from files."""
        try:
            self.load_all_configs()
            self._notify_change_callbacks()
            self.logger.info("Configuration reloaded successfully")

        except Exception as e:
            self.logger.error(f"Failed to reload configuration: {e}")

    def add_change_callback(self, callback: Callable) -> None:
        """Add callback to be called when configuration changes."""
        self.change_callbacks.append(callback)

    def _notify_change_callbacks(self) -> None:
        """Notify all registered callbacks of configuration changes."""
        for callback in self.change_callbacks:
            try:
                callback()
            except Exception as e:
                self.logger.error(f"Error in config change callback: {e}")

    def save_current_config(self) -> None:
        """Save current configuration to files."""
        config_files = {
            "trading.yaml": self.trading,
            "exchange.yaml": self.exchange,
            "security.yaml": self.security,
            "ui.yaml": self.ui,
            "system.yaml": self.system,
        }

        for filename, config_instance in config_files.items():
            file_path = self.config_dir / filename
            self._save_config_file(file_path, config_instance)

    def _save_config_file(self, file_path: Path, config_instance: Any) -> None:
        """Save configuration instance to YAML file."""
        try:
            config_dict = self._dataclass_to_dict(config_instance)

            with open(file_path, "w") as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)

            self.logger.debug(f"Saved config to {file_path}")

        except Exception as e:
            raise ConfigurationError(f"Failed to save {file_path}: {e}")

    def get_config_summary(self) -> Dict[str, Any]:
        """Get summary of all configuration settings."""
        return {
            "environment": self.environment,
            "config_directory": str(self.config_dir),
            "hot_reload_enabled": self.enable_hot_reload,
            "watched_files": len(self.watched_files),
            "trading": self._dataclass_to_dict(self.trading),
            "exchange": self._dataclass_to_dict(self.exchange),
            "security": self._dataclass_to_dict(self.security),
            "ui": self._dataclass_to_dict(self.ui),
            "system": self._dataclass_to_dict(self.system),
        }

    def stop(self) -> None:
        """Stop configuration manager and cleanup resources."""
        if self.observer:
            self.observer.stop()
            self.observer.join()

        self.logger.info("Configuration manager stopped")


# Global configuration manager instance
config_manager = ConfigurationManager()
