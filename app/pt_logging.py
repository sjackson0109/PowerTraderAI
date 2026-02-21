"""
PowerTraderAI+ Enhanced Logging System
Advanced logging with structured output, performance tracking, and audit trails.
"""

import atexit
import json
import logging
import logging.handlers
import queue
import sys
import threading
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class LogLevel(Enum):
    """Enhanced log levels with trading-specific categories."""

    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"
    TRADE = "TRADE"  # Trading operations
    AUDIT = "AUDIT"  # Audit trail
    PERFORMANCE = "PERF"  # Performance metrics


@dataclass
class LogEntry:
    """Structured log entry with comprehensive metadata."""

    timestamp: str
    level: str
    message: str
    logger_name: str
    module: str
    function: str
    line_number: int
    thread_id: int
    thread_name: str
    process_id: int
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    trade_id: Optional[str] = None
    correlation_id: Optional[str] = None
    tags: Optional[List[str]] = None
    context: Optional[Dict[str, Any]] = None
    exception_info: Optional[Dict[str, Any]] = None
    performance_metrics: Optional[Dict[str, float]] = None


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def __init__(self, include_context: bool = True, include_performance: bool = True):
        super().__init__()
        self.include_context = include_context
        self.include_performance = include_performance

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Extract exception information
        exc_info = None
        if record.exc_info:
            exc_info = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Build log entry
        log_entry = LogEntry(
            timestamp=datetime.fromtimestamp(record.created).isoformat(),
            level=record.levelname,
            message=record.getMessage(),
            logger_name=record.name,
            module=record.module or "unknown",
            function=record.funcName or "unknown",
            line_number=record.lineno,
            thread_id=record.thread,
            thread_name=record.threadName,
            process_id=record.process,
            session_id=getattr(record, "session_id", None),
            user_id=getattr(record, "user_id", None),
            trade_id=getattr(record, "trade_id", None),
            correlation_id=getattr(record, "correlation_id", None),
            tags=getattr(record, "tags", None),
            context=getattr(record, "context", None) if self.include_context else None,
            exception_info=exc_info,
            performance_metrics=getattr(record, "performance_metrics", None)
            if self.include_performance
            else None,
        )

        return json.dumps(asdict(log_entry), default=str, separators=(",", ":"))


class ColoredFormatter(logging.Formatter):
    """Colored console formatter for better readability."""

    # Color codes
    COLORS = {
        "CRITICAL": "\033[41m",  # Red background
        "ERROR": "\033[91m",  # Bright red
        "WARNING": "\033[93m",  # Yellow
        "INFO": "\033[92m",  # Green
        "DEBUG": "\033[94m",  # Blue
        "TRADE": "\033[95m",  # Magenta
        "AUDIT": "\033[96m",  # Cyan
        "PERF": "\033[97m",  # White
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        # Apply color based on level
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET if color else ""

        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]

        # Build formatted message
        formatted = f"{color}[{timestamp}] {record.levelname:8} {record.name:20} {record.getMessage()}{reset}"

        # Add exception info if present
        if record.exc_info:
            formatted += f"\\n{self.formatException(record.exc_info)}"

        return formatted


class PerformanceLogFilter(logging.Filter):
    """Filter for performance-related log entries."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Only allow performance-related records."""
        return (
            hasattr(record, "performance_metrics")
            or record.levelname == "PERF"
            or "performance" in record.getMessage().lower()
        )


class AuditLogFilter(logging.Filter):
    """Filter for audit trail entries."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Only allow audit-related records."""
        return (
            hasattr(record, "audit_event")
            or record.levelname == "AUDIT"
            or "audit" in record.getMessage().lower()
        )


class TradeLogFilter(logging.Filter):
    """Filter for trading-related log entries."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Only allow trading-related records."""
        return (
            hasattr(record, "trade_id")
            or record.levelname == "TRADE"
            or any(
                word in record.getMessage().lower()
                for word in ["trade", "order", "position", "buy", "sell"]
            )
        )


class AsyncFileHandler(logging.Handler):
    """Asynchronous file handler to prevent I/O blocking."""

    def __init__(
        self,
        filename: str,
        maxBytes: int = 10485760,
        backupCount: int = 5,
        encoding: str = "utf-8",
    ):
        super().__init__()
        self.filename = filename
        self.maxBytes = maxBytes
        self.backupCount = backupCount
        self.encoding = encoding

        # Create background thread for file writing
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

        # Setup file handler
        self._setup_file_handler()

        # Register cleanup
        atexit.register(self.close)

    def _setup_file_handler(self):
        """Setup rotating file handler."""
        self.file_handler = logging.handlers.RotatingFileHandler(
            self.filename,
            maxBytes=self.maxBytes,
            backupCount=self.backupCount,
            encoding=self.encoding,
        )

    def _worker(self):
        """Background worker thread for file writing."""
        while True:
            try:
                record = self.queue.get(timeout=1.0)
                if record is None:  # Shutdown signal
                    break
                self.file_handler.emit(record)
                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                # Handle errors in background thread
                sys.stderr.write(f"Error in async log handler: {e}\\n")

    def emit(self, record: logging.LogRecord):
        """Queue log record for async processing."""
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            # If queue is full, skip this log entry
            pass

    def close(self):
        """Close handler and cleanup resources."""
        # Send shutdown signal
        self.queue.put(None)
        self.thread.join(timeout=5.0)
        self.file_handler.close()
        super().close()


class PowerTraderLogger:
    """Enhanced logger for PowerTraderAI+ with structured logging capabilities."""

    def __init__(self, name: str = "PowerTrader"):
        self.name = name
        self.logger = logging.getLogger(name)
        self.session_id = self._generate_session_id()
        self.correlation_counter = 0
        self.context_stack: List[Dict[str, Any]] = []

        # Add custom log levels
        self._add_custom_levels()

        # Configure handlers
        self._configured = False

    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        import uuid

        return str(uuid.uuid4())[:8]

    def _add_custom_levels(self):
        """Add custom log levels."""
        # Add TRADE level
        logging.addLevelName(25, "TRADE")

        def trade(self, message, *args, **kwargs):
            if self.isEnabledFor(25):
                self._log(25, message, args, **kwargs)

        logging.Logger.trade = trade

        # Add AUDIT level
        logging.addLevelName(35, "AUDIT")

        def audit(self, message, *args, **kwargs):
            if self.isEnabledFor(35):
                self._log(35, message, args, **kwargs)

        logging.Logger.audit = audit

        # Add PERF level
        logging.addLevelName(15, "PERF")

        def perf(self, message, *args, **kwargs):
            if self.isEnabledFor(15):
                self._log(15, message, args, **kwargs)

        logging.Logger.perf = perf

    def configure(
        self,
        log_level: str = "INFO",
        log_file: Optional[str] = None,
        json_output: bool = False,
        colored_console: bool = True,
        enable_performance_logging: bool = True,
        enable_audit_logging: bool = True,
        enable_trade_logging: bool = True,
    ) -> None:
        """
        Configure logger with handlers and formatters.

        Args:
            log_level: Minimum log level
            log_file: Log file path (if None, no file logging)
            json_output: Use JSON formatting for file output
            colored_console: Use colored console output
            enable_performance_logging: Enable separate performance log
            enable_audit_logging: Enable separate audit log
            enable_trade_logging: Enable separate trade log
        """
        if self._configured:
            return

        self.logger.setLevel(getattr(logging, log_level.upper()))

        # Clear existing handlers
        self.logger.handlers.clear()

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        if colored_console:
            console_formatter = ColoredFormatter()
        else:
            console_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # Main file handler
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            main_handler = AsyncFileHandler(str(log_path))
            if json_output:
                main_formatter = JSONFormatter()
            else:
                main_formatter = logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
                )
            main_handler.setFormatter(main_formatter)
            self.logger.addHandler(main_handler)

            # Specialized log handlers
            log_dir = log_path.parent

            # Performance log
            if enable_performance_logging:
                perf_handler = AsyncFileHandler(str(log_dir / "performance.log"))
                perf_handler.addFilter(PerformanceLogFilter())
                perf_handler.setFormatter(JSONFormatter(include_context=False))
                self.logger.addHandler(perf_handler)

            # Audit log
            if enable_audit_logging:
                audit_handler = AsyncFileHandler(str(log_dir / "audit.log"))
                audit_handler.addFilter(AuditLogFilter())
                audit_handler.setFormatter(JSONFormatter())
                self.logger.addHandler(audit_handler)

            # Trade log
            if enable_trade_logging:
                trade_handler = AsyncFileHandler(str(log_dir / "trades.log"))
                trade_handler.addFilter(TradeLogFilter())
                trade_handler.setFormatter(JSONFormatter())
                self.logger.addHandler(trade_handler)

        self._configured = True

    def get_correlation_id(self) -> str:
        """Get unique correlation ID for tracking related operations."""
        self.correlation_counter += 1
        return f"{self.session_id}_{self.correlation_counter:06d}"

    def push_context(self, **kwargs) -> None:
        """Push context onto the context stack."""
        self.context_stack.append(kwargs)

    def pop_context(self) -> Optional[Dict[str, Any]]:
        """Pop context from the context stack."""
        return self.context_stack.pop() if self.context_stack else None

    def _enrich_record(self, record: logging.LogRecord, **kwargs) -> None:
        """Enrich log record with additional metadata."""
        # Add session info
        record.session_id = self.session_id

        # Add context
        merged_context = {}
        for ctx in self.context_stack:
            merged_context.update(ctx)
        merged_context.update(kwargs.get("context", {}))

        if merged_context:
            record.context = merged_context

        # Add other metadata
        for key, value in kwargs.items():
            if key != "context":
                setattr(record, key, value)

    def log_trade(
        self,
        message: str,
        trade_id: str = None,
        symbol: str = None,
        side: str = None,
        quantity: float = None,
        price: float = None,
        **kwargs,
    ) -> None:
        """Log trading operations with structured data."""
        trade_data = {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
        }
        trade_data.update(kwargs)

        # Filter out None values
        trade_data = {k: v for k, v in trade_data.items() if v is not None}

        self.logger.trade(message, extra=trade_data)

    def log_performance(self, operation: str, duration_ms: float, **metrics) -> None:
        """Log performance metrics."""
        perf_metrics = {"operation": operation, "duration_ms": duration_ms, **metrics}

        self.logger.perf(
            f"Performance: {operation} completed in {duration_ms:.2f}ms",
            extra={"performance_metrics": perf_metrics},
        )

    def log_audit(
        self, event: str, user_id: str = None, details: Dict[str, Any] = None, **kwargs
    ) -> None:
        """Log audit events for compliance and security."""
        audit_data = {
            "audit_event": event,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "details": details or {},
        }
        audit_data.update(kwargs)

        self.logger.audit(f"Audit: {event}", extra=audit_data)

    def log_error_with_context(
        self, message: str, error: Exception = None, **context
    ) -> None:
        """Log error with comprehensive context."""
        error_data = {"context": context}
        if error:
            error_data["error_type"] = type(error).__name__
            error_data["error_message"] = str(error)

        self.logger.error(message, exc_info=error is not None, extra=error_data)

    def get_logger(self) -> logging.Logger:
        """Get the underlying logger instance."""
        return self.logger

    def shutdown(self) -> None:
        """Shutdown logger and cleanup resources."""
        # Close all handlers
        for handler in self.logger.handlers:
            handler.close()

        self.logger.handlers.clear()


# Context manager for temporary logging context
class LogContext:
    """Context manager for adding temporary context to logs."""

    def __init__(self, logger: PowerTraderLogger, **context):
        self.logger = logger
        self.context = context

    def __enter__(self):
        self.logger.push_context(**self.context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.pop_context()


# Global logger instance
logger = PowerTraderLogger("PowerTrader")


# Convenience functions
def configure_logging(**kwargs):
    """Configure global logger."""
    logger.configure(**kwargs)


def get_logger(name: str = None) -> logging.Logger:
    """Get logger instance."""
    if name:
        return logging.getLogger(name)
    return logger.get_logger()


def log_context(**context):
    """Create logging context manager."""
    return LogContext(logger, **context)


def shutdown_logging():
    """Shutdown logging system."""
    logger.shutdown()
