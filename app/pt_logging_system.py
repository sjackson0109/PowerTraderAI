"""
PowerTrader AI+ Enhanced Logging System
Comprehensive logging with structured data, performance metrics, and real-time monitoring
"""

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
import traceback


class LogLevel(Enum):
    """Enhanced log levels for financial trading systems."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    TRADE = "TRADE"  # Special level for trade events
    SECURITY = "SECURITY"  # Security-related events
    PERFORMANCE = "PERFORMANCE"  # Performance metrics
    AUDIT = "AUDIT"  # Audit trail events


@dataclass
class LogEntry:
    """Structured log entry with metadata."""

    timestamp: float
    level: str
    message: str
    module: str
    function: str
    line_number: int
    thread_id: str
    process_id: int
    session_id: str
    user_id: Optional[str] = None
    correlation_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    stack_trace: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class StructuredFormatter(logging.Formatter):
    """Structured JSON formatter for logs."""

    def __init__(self, session_id: str):
        super().__init__()
        self.session_id = session_id

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        entry = LogEntry(
            timestamp=record.created,
            level=record.levelname,
            message=record.getMessage(),
            module=record.module,
            function=record.funcName,
            line_number=record.lineno,
            thread_id=threading.get_ident(),
            process_id=os.getpid(),
            session_id=self.session_id,
            metadata=getattr(record, "metadata", None),
            stack_trace=(
                self.formatException(record.exc_info) if record.exc_info else None
            ),
        )

        # Add correlation ID if available
        if hasattr(record, "correlation_id"):
            entry.correlation_id = record.correlation_id

        # Add user ID if available
        if hasattr(record, "user_id"):
            entry.user_id = record.user_id

        return entry.to_json()


class ColoredConsoleFormatter(logging.Formatter):
    """Colored console formatter for better readability."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "TRADE": "\033[34m",  # Blue
        "SECURITY": "\033[91m",  # Bright Red
        "PERFORMANCE": "\033[96m",  # Bright Cyan
        "AUDIT": "\033[93m",  # Bright Yellow
        "RESET": "\033[0m",  # Reset
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format with colors for console output."""
        color = self.COLORS.get(record.levelname, "")
        reset = self.COLORS["RESET"]

        timestamp = datetime.fromtimestamp(record.created).strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]

        formatted = (
            f"{color}[{timestamp}] "
            f"{record.levelname:12} "
            f"{record.module:15}.{record.funcName}:{record.lineno:3} "
            f"- {record.getMessage()}{reset}"
        )

        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"

        return formatted


class PerformanceTimer:
    """Context manager for timing operations."""

    def __init__(
        self,
        logger: "PowerTraderLogger",
        operation_name: str,
        threshold_ms: float = 1000.0,
    ):
        self.logger = logger
        self.operation_name = operation_name
        self.threshold_ms = threshold_ms
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (time.time() - self.start_time) * 1000  # Convert to milliseconds

        level = (
            LogLevel.WARNING if duration > self.threshold_ms else LogLevel.PERFORMANCE
        )

        self.logger.log(
            level=level,
            message=f"Operation '{self.operation_name}' completed in {duration:.2f}ms",
            metadata={
                "operation": self.operation_name,
                "duration_ms": duration,
                "threshold_ms": self.threshold_ms,
                "exceeded_threshold": duration > self.threshold_ms,
            },
        )


class SecurityLogger:
    """Specialized logger for security events."""

    def __init__(self, main_logger: "PowerTraderLogger"):
        self.logger = main_logger

    def authentication_attempt(
        self, user_id: str, success: bool, ip_address: str = None
    ):
        """Log authentication attempt."""
        self.logger.log(
            level=LogLevel.SECURITY,
            message=f"Authentication {'succeeded' if success else 'failed'} for user {user_id}",
            metadata={
                "user_id": user_id,
                "success": success,
                "ip_address": ip_address,
                "event_type": "authentication",
            },
        )

    def api_key_usage(self, exchange: str, operation: str, success: bool):
        """Log API key usage."""
        self.logger.log(
            level=LogLevel.SECURITY,
            message=f"API key used for {operation} on {exchange}: {'success' if success else 'failure'}",
            metadata={
                "exchange": exchange,
                "operation": operation,
                "success": success,
                "event_type": "api_key_usage",
            },
        )

    def suspicious_activity(self, activity_type: str, details: Dict[str, Any]):
        """Log suspicious activity."""
        self.logger.log(
            level=LogLevel.SECURITY,
            message=f"Suspicious activity detected: {activity_type}",
            metadata={
                "activity_type": activity_type,
                "details": details,
                "event_type": "suspicious_activity",
            },
        )


class TradeLogger:
    """Specialized logger for trading events."""

    def __init__(self, main_logger: "PowerTraderLogger"):
        self.logger = main_logger

    def order_created(
        self,
        order_id: str,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        order_type: str,
    ):
        """Log order creation."""
        self.logger.log(
            level=LogLevel.TRADE,
            message=f"Order created: {side} {amount} {symbol} at {price} ({order_type})",
            metadata={
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": price,
                "order_type": order_type,
                "event_type": "order_created",
            },
        )

    def order_filled(
        self,
        order_id: str,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        fees: float = 0.0,
    ):
        """Log order fill."""
        self.logger.log(
            level=LogLevel.TRADE,
            message=f"Order filled: {side} {amount} {symbol} at {price} (fees: {fees})",
            metadata={
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": price,
                "fees": fees,
                "event_type": "order_filled",
            },
        )

    def order_cancelled(self, order_id: str, reason: str):
        """Log order cancellation."""
        self.logger.log(
            level=LogLevel.TRADE,
            message=f"Order cancelled: {order_id} - {reason}",
            metadata={
                "order_id": order_id,
                "reason": reason,
                "event_type": "order_cancelled",
            },
        )

    def position_change(
        self, symbol: str, old_position: float, new_position: float, pnl: float = 0.0
    ):
        """Log position changes."""
        self.logger.log(
            level=LogLevel.TRADE,
            message=f"Position changed for {symbol}: {old_position} -> {new_position} (PnL: {pnl})",
            metadata={
                "symbol": symbol,
                "old_position": old_position,
                "new_position": new_position,
                "position_change": new_position - old_position,
                "pnl": pnl,
                "event_type": "position_change",
            },
        )


class AuditLogger:
    """Specialized logger for audit trail."""

    def __init__(self, main_logger: "PowerTraderLogger"):
        self.logger = main_logger

    def configuration_change(
        self, setting_name: str, old_value: Any, new_value: Any, user_id: str = None
    ):
        """Log configuration changes."""
        self.logger.log(
            level=LogLevel.AUDIT,
            message=f"Configuration changed: {setting_name}",
            metadata={
                "setting_name": setting_name,
                "old_value": str(old_value),
                "new_value": str(new_value),
                "user_id": user_id,
                "event_type": "configuration_change",
            },
        )

    def system_action(self, action: str, details: Dict[str, Any], user_id: str = None):
        """Log system actions."""
        self.logger.log(
            level=LogLevel.AUDIT,
            message=f"System action: {action}",
            metadata={
                "action": action,
                "details": details,
                "user_id": user_id,
                "event_type": "system_action",
            },
        )


class LogAnalyzer:
    """Analyzer for log patterns and metrics."""

    def __init__(self, log_directory: str):
        self.log_directory = Path(log_directory)

    def get_error_summary(self, hours: int = 24) -> Dict[str, int]:
        """Get error summary for the last N hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        error_counts = {}

        for log_file in self.log_directory.glob("*.log"):
            try:
                with open(log_file, "r") as f:
                    for line in f:
                        try:
                            entry_data = json.loads(line)
                            entry_time = datetime.fromtimestamp(entry_data["timestamp"])

                            if entry_time > cutoff and entry_data["level"] in [
                                "ERROR",
                                "CRITICAL",
                            ]:
                                module = entry_data["module"]
                                error_counts[module] = error_counts.get(module, 0) + 1
                        except (json.JSONDecodeError, KeyError):
                            continue
            except Exception:
                continue

        return error_counts

    def get_performance_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """Get performance metrics for the last N hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        operations = {}

        for log_file in self.log_directory.glob("*.log"):
            try:
                with open(log_file, "r") as f:
                    for line in f:
                        try:
                            entry_data = json.loads(line)
                            entry_time = datetime.fromtimestamp(entry_data["timestamp"])

                            if (
                                entry_time > cutoff
                                and entry_data["level"] == "PERFORMANCE"
                                and "metadata" in entry_data
                            ):

                                metadata = entry_data["metadata"]
                                if (
                                    "operation" in metadata
                                    and "duration_ms" in metadata
                                ):
                                    op_name = metadata["operation"]
                                    duration = metadata["duration_ms"]

                                    if op_name not in operations:
                                        operations[op_name] = []
                                    operations[op_name].append(duration)

                        except (json.JSONDecodeError, KeyError):
                            continue
            except Exception:
                continue

        # Calculate statistics
        metrics = {}
        for op_name, durations in operations.items():
            metrics[op_name] = {
                "count": len(durations),
                "avg_ms": sum(durations) / len(durations),
                "min_ms": min(durations),
                "max_ms": max(durations),
                "median_ms": sorted(durations)[len(durations) // 2] if durations else 0,
            }

        return metrics


class PowerTraderLogger:
    """
    Enhanced logging system for PowerTrader AI+ with structured logging,
    performance monitoring, and specialized loggers.
    """

    def __init__(self, log_directory: str = None, session_id: str = None):
        if log_directory is None:
            import pt_paths

            log_directory = pt_paths.log_dir()
        self.log_directory = Path(log_directory)
        self.log_directory.mkdir(parents=True, exist_ok=True)

        self.session_id = session_id or f"session_{int(time.time())}"

        # Initialize loggers
        self.main_logger = self._setup_main_logger()
        self.security = SecurityLogger(self)
        self.trade = TradeLogger(self)
        self.audit = AuditLogger(self)
        self.analyzer = LogAnalyzer(str(self.log_directory))

        # Performance monitoring
        self.performance_metrics = {}
        self._metrics_lock = threading.Lock()

        self.info(
            "PowerTrader AI+ Logger initialized",
            metadata={"session_id": self.session_id},
        )

    def _setup_main_logger(self) -> logging.Logger:
        """Setup the main logger with multiple handlers."""
        logger = logging.getLogger("powertrader")
        logger.setLevel(logging.DEBUG)

        # Clear existing handlers to avoid duplicates
        logger.handlers.clear()

        # Console handler with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(ColoredConsoleFormatter())
        logger.addHandler(console_handler)

        # Main log file (rotating)
        main_file = self.log_directory / "powertrader.log"
        file_handler = RotatingFileHandler(
            main_file,
            maxBytes=50 * 1024 * 1024,
            backupCount=10,  # 50MB per file, keep 10
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(StructuredFormatter(self.session_id))
        logger.addHandler(file_handler)

        # Error log file (only errors and critical)
        error_file = self.log_directory / "errors.log"
        error_handler = RotatingFileHandler(
            error_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,  # 10MB per file, keep 5
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(StructuredFormatter(self.session_id))
        logger.addHandler(error_handler)

        # Trade log file
        trade_file = self.log_directory / "trades.log"
        trade_handler = TimedRotatingFileHandler(
            trade_file,
            when="midnight",
            interval=1,
            backupCount=30,  # Daily rotation, keep 30 days
        )
        trade_handler.setLevel(logging.INFO)
        trade_handler.addFilter(lambda record: record.levelname == "TRADE")
        trade_handler.setFormatter(StructuredFormatter(self.session_id))
        logger.addHandler(trade_handler)

        # Security log file
        security_file = self.log_directory / "security.log"
        security_handler = TimedRotatingFileHandler(
            security_file,
            when="midnight",
            interval=1,
            backupCount=90,  # Daily rotation, keep 90 days
        )
        security_handler.setLevel(logging.INFO)
        security_handler.addFilter(lambda record: record.levelname == "SECURITY")
        security_handler.setFormatter(StructuredFormatter(self.session_id))
        logger.addHandler(security_handler)

        # Audit log file
        audit_file = self.log_directory / "audit.log"
        audit_handler = TimedRotatingFileHandler(
            audit_file,
            when="midnight",
            interval=1,
            backupCount=365,  # Daily rotation, keep 1 year
        )
        audit_handler.setLevel(logging.INFO)
        audit_handler.addFilter(lambda record: record.levelname == "AUDIT")
        audit_handler.setFormatter(StructuredFormatter(self.session_id))
        logger.addHandler(audit_handler)

        return logger

    def log(
        self,
        level: Union[LogLevel, str],
        message: str,
        metadata: Dict[str, Any] = None,
        correlation_id: str = None,
        user_id: str = None,
        exc_info: bool = False,
    ):
        """Log a message with optional metadata."""
        if isinstance(level, LogLevel):
            level = level.value

        # Create log record
        record = logging.LogRecord(
            name="powertrader",
            level=getattr(logging, level),
            pathname="",
            lineno=0,
            msg=message,
            args=(),
            exc_info=sys.exc_info() if exc_info else None,
        )

        # Add custom attributes
        if metadata:
            record.metadata = metadata
        if correlation_id:
            record.correlation_id = correlation_id
        if user_id:
            record.user_id = user_id

        # Get caller information
        frame = sys._getframe(2)
        record.pathname = frame.f_code.co_filename
        record.module = os.path.splitext(os.path.basename(record.pathname))[0]
        record.lineno = frame.f_lineno
        record.funcName = frame.f_code.co_name

        # Update level name for custom levels
        record.levelname = level

        self.main_logger.handle(record)

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self.log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message."""
        kwargs["exc_info"] = kwargs.get("exc_info", True)
        self.log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        """Log critical message."""
        kwargs["exc_info"] = kwargs.get("exc_info", True)
        self.log(LogLevel.CRITICAL, message, **kwargs)

    def performance_timer(
        self, operation_name: str, threshold_ms: float = 1000.0
    ) -> PerformanceTimer:
        """Create a performance timer context manager."""
        return PerformanceTimer(self, operation_name, threshold_ms)

    def record_metric(
        self, metric_name: str, value: float, tags: Dict[str, str] = None
    ):
        """Record a performance metric."""
        with self._metrics_lock:
            timestamp = time.time()

            if metric_name not in self.performance_metrics:
                self.performance_metrics[metric_name] = []

            self.performance_metrics[metric_name].append(
                {"timestamp": timestamp, "value": value, "tags": tags or {}}
            )

            # Keep only the last 1000 metrics per metric name
            if len(self.performance_metrics[metric_name]) > 1000:
                self.performance_metrics[metric_name] = self.performance_metrics[
                    metric_name
                ][-1000:]

        self.log(
            LogLevel.PERFORMANCE,
            f"Metric recorded: {metric_name} = {value}",
            metadata={"metric_name": metric_name, "value": value, "tags": tags},
        )

    def get_recent_metrics(
        self, metric_name: str, minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """Get recent metrics for analysis."""
        cutoff = time.time() - (minutes * 60)

        with self._metrics_lock:
            metrics = self.performance_metrics.get(metric_name, [])
            return [m for m in metrics if m["timestamp"] > cutoff]

    def exception(self, message: str, **kwargs):
        """Log an exception with traceback."""
        kwargs["exc_info"] = True
        self.error(message, **kwargs)

    def close(self):
        """Close all log handlers."""
        for handler in self.main_logger.handlers:
            handler.close()
        self.main_logger.handlers.clear()


# Global logger instance
_global_logger: Optional[PowerTraderLogger] = None


def get_logger() -> PowerTraderLogger:
    """Get the global logger instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = PowerTraderLogger()
    return _global_logger


def setup_logger(
    log_directory: str = None, session_id: str = None
) -> PowerTraderLogger:
    """Setup and return the global logger."""
    global _global_logger
    _global_logger = PowerTraderLogger(log_directory, session_id)
    return _global_logger


def close_logger():
    """Close the global logger."""
    global _global_logger
    if _global_logger:
        _global_logger.close()
        _global_logger = None


# Convenience functions
def log_debug(message: str, **kwargs):
    """Log debug message using global logger."""
    get_logger().debug(message, **kwargs)


def log_info(message: str, **kwargs):
    """Log info message using global logger."""
    get_logger().info(message, **kwargs)


def log_warning(message: str, **kwargs):
    """Log warning message using global logger."""
    get_logger().warning(message, **kwargs)


def log_error(message: str, **kwargs):
    """Log error message using global logger."""
    get_logger().error(message, **kwargs)


def log_critical(message: str, **kwargs):
    """Log critical message using global logger."""
    get_logger().critical(message, **kwargs)


def log_trade(message: str, **kwargs):
    """Log trade-specific message using global logger."""
    logger = get_logger()
    logger.info(f"[TRADE] {message}", extra=kwargs)


def log_security(message: str, **kwargs):
    """Log security-specific message using global logger."""
    logger = get_logger()
    logger.warning(f"[SECURITY] {message}", extra=kwargs)


def setup_logging(
    log_dir: str = None, app_name: str = None, log_level: str = "INFO"
) -> PowerTraderLogger:
    """Compatibility function for setup_logging (alias for setup_logger)."""
    session_id = f"{app_name}_{int(time.time())}" if app_name else None
    return setup_logger(log_directory=log_dir, session_id=session_id)


if __name__ == "__main__":
    # Example usage and testing
    logger = PowerTraderLogger("test_logs")

    # Basic logging
    logger.info("System started", metadata={"version": "3.0.0"})
    logger.warning("This is a warning", metadata={"component": "test"})

    # Performance timing
    with logger.performance_timer("test_operation", threshold_ms=100):
        time.sleep(0.15)  # Simulate work

    # Trade logging
    logger.trade.order_created("order_123", "BTCUSDT", "buy", 0.1, 50000, "limit")
    logger.trade.order_filled("order_123", "BTCUSDT", "buy", 0.1, 50010, 5.0)

    # Security logging
    logger.security.authentication_attempt("user_123", True, "192.168.1.1")

    # Audit logging
    logger.audit.configuration_change("max_position_size", 1000, 1500, "admin")

    # Metrics
    logger.record_metric("cpu_usage", 75.5, {"server": "trading-01"})
    logger.record_metric("memory_usage", 8192, {"server": "trading-01"})

    # Error with exception
    try:
        1 / 0
    except Exception:
        logger.exception("Division by zero error occurred")

    print("Test logging completed. Check 'test_logs' directory for output files.")

    logger.close()
