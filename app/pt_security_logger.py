"""
PowerTraderAI+ Security & Audit Logging
Standalone security event logging module providing:
- Correlation ID context (thread-local, propagated through request chains)
- Security event logging: API auth attempts, credential usage, suspicious activity
- Dedicated audit log (separate file, rotation, secure permissions)
- Structured JSON security events for SIEM integration

Note: This module does NOT depend on pt_logging_system. It manages its own
logging handler so security events are always written to a dedicated audit
file regardless of the application's root logger configuration.

Usage:
    from pt_security_logger import get_security_logger, CorrelationContext

    # Propagate correlation ID through a trading workflow
    with CorrelationContext("trade-abc-123"):
        get_security_logger().log_auth_attempt("robinhood", success=True)
        get_security_logger().log_trade_event("BTC-USD", "buy", 0.1, 45000.0)

    # Standalone
    get_security_logger().log_suspicious_activity(
        "rate_limit_exceeded", source_ip="10.0.0.1", details={"endpoint": "/orders"}
    )
"""

import collections
import hashlib
import json
import logging
import logging.handlers
import os
import stat
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Security event types
# ---------------------------------------------------------------------------
class SecurityEventType(Enum):
    AUTH_ATTEMPT = "auth_attempt"       # API key authentication attempt
    AUTH_SUCCESS = "auth_success"       # Successful authentication
    AUTH_FAILURE = "auth_failure"       # Failed authentication
    CREDENTIAL_USE = "credential_use"   # Credential accessed/used
    CREDENTIAL_ROTATION = "credential_rotation"   # Credential rotated
    SUSPICIOUS_ACTIVITY = "suspicious_activity"   # Anomalous behavior detected
    PERMISSION_DENIED = "permission_denied"       # Insufficient API permissions
    RATE_LIMIT = "rate_limit"           # Rate limit hit
    TRADE_EXECUTED = "trade_executed"   # Order placed
    TRADE_REJECTED = "trade_rejected"   # Order rejected
    CONFIG_CHANGE = "config_change"     # Configuration modified
    SYSTEM_START = "system_start"       # Application started
    SYSTEM_STOP = "system_stop"         # Application stopped


@dataclass
class SecurityEvent:
    """Structured security event for audit trail."""

    event_id: str
    event_type: str
    timestamp: float
    message: str
    correlation_id: Optional[str]
    source: Optional[str] = None
    user_id: Optional[str] = None
    source_ip: Optional[str] = None
    success: Optional[bool] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @staticmethod
    def new_id() -> str:
        # UTC timestamp in ID so audit records are timezone-unambiguous
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"SEC_{ts}_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Correlation ID context (thread-local)
# ---------------------------------------------------------------------------
_correlation_local = threading.local()


def get_correlation_id() -> Optional[str]:
    """Return the current thread's correlation ID, or None if not set."""
    return getattr(_correlation_local, "correlation_id", None)


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current thread."""
    _correlation_local.correlation_id = cid


def clear_correlation_id() -> None:
    """Clear the correlation ID for the current thread."""
    try:
        del _correlation_local.correlation_id
    except AttributeError:
        pass


class CorrelationContext:
    """
    Context manager that sets a correlation ID for the current thread,
    then restores the previous value on exit.

    Each call to __enter__ saves the previous ID on a stack, so nested
    and reused instances are safe.

    Usage:
        with CorrelationContext("trade-workflow-xyz"):
            process_order()  # all logs within will carry this correlation ID
    """

    def __init__(self, correlation_id: Optional[str] = None):
        self._cid = correlation_id or f"CID_{uuid.uuid4().hex[:12]}"
        self._stack: List[Optional[str]] = []

    def __enter__(self) -> str:
        self._stack.append(get_correlation_id())
        set_correlation_id(self._cid)
        return self._cid

    def __exit__(self, *_) -> None:
        if self._stack:
            previous = self._stack.pop()
            if previous is not None:
                set_correlation_id(previous)
            else:
                clear_correlation_id()


# Keep snake_case alias for backwards compatibility
correlation_context = CorrelationContext


# ---------------------------------------------------------------------------
# CorrelationLogFilter — injects correlation_id into log records
# ---------------------------------------------------------------------------
class CorrelationLogFilter(logging.Filter):
    """
    Logging filter that injects the current thread's correlation ID
    into every LogRecord. Works with any handler/formatter.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or ""
        return True


# ---------------------------------------------------------------------------
# SecureRotatingFileHandler — chmod backup files after rotation
# ---------------------------------------------------------------------------
class _SecureRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """RotatingFileHandler subclass that applies owner-only permissions after rollover."""

    def doRollover(self) -> None:
        super().doRollover()
        # Re-secure the new active file and all existing backups
        for path in self._audit_paths():
            _chmod_secure(path)

    def _audit_paths(self):
        yield self.baseFilename
        for n in range(1, self.backupCount + 1):
            candidate = f"{self.baseFilename}.{n}"
            if os.path.exists(candidate):
                yield candidate


def _chmod_secure(path: str) -> None:
    """Set owner-only read/write on path; log warning on failure."""
    try:
        if os.path.exists(path):
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        logger.warning(
            "Could not secure audit log permissions on %s: %s — "
            "file may have permissive permissions",
            path,
            exc,
        )


# ---------------------------------------------------------------------------
# SecurityLogger
# ---------------------------------------------------------------------------
class SecurityLogger:
    """
    Application-wide security and audit logger.

    Writes structured JSON security events to a dedicated audit log file
    (separate from the main application log). The audit log uses a
    RotatingFileHandler with secure (owner-only) file permissions.

    Args:
        log_dir: Directory for the audit log file.  Defaults to
            ~/.powertraderai/logs so the source tree is never polluted.
    """

    AUDIT_LOG_FILENAME = "security_audit.jsonl"
    MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
    BACKUP_COUNT = 10              # Keep 10 rotated files

    def __init__(self, log_dir: Optional[str] = None):
        self._log_dir = log_dir or os.path.join(
            os.path.expanduser("~"), ".powertraderai", "logs"
        )
        os.makedirs(self._log_dir, exist_ok=True)
        self._audit_path = os.path.join(self._log_dir, self.AUDIT_LOG_FILENAME)
        self._lock = threading.Lock()
        # Use a private logger instance (not the global registry) to avoid the
        # shared-handler pitfall when two SecurityLogger instances use the same dir.
        self._audit_logger = logging.Logger(
            f"pt.security.audit.{id(self)}", level=logging.DEBUG
        )
        self._audit_logger.propagate = False
        self._handler = self._create_handler()
        self._audit_logger.addHandler(self._handler)

    def _create_handler(self) -> _SecureRotatingFileHandler:
        handler = _SecureRotatingFileHandler(
            self._audit_path,
            maxBytes=self.MAX_BYTES,
            backupCount=self.BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))  # Raw JSON lines
        handler.addFilter(CorrelationLogFilter())
        # Secure permissions once at creation
        _chmod_secure(self._audit_path)
        return handler

    def close(self) -> None:
        """Flush and close the underlying handler (call on shutdown)."""
        if self._handler:
            self._handler.flush()
            self._handler.close()
            self._audit_logger.removeHandler(self._handler)

    def _emit(self, event: SecurityEvent) -> None:
        """Write security event to audit log (thread-safe)."""
        with self._lock:
            try:
                self._audit_logger.info(event.to_json())
            except Exception as exc:
                logger.error("Failed to write security audit event: %s", exc)

    def _make_event(
        self,
        event_type: SecurityEventType,
        message: str,
        source: Optional[str] = None,
        success: Optional[bool] = None,
        details: Optional[Dict[str, Any]] = None,
        source_ip: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> SecurityEvent:
        return SecurityEvent(
            event_id=SecurityEvent.new_id(),
            event_type=event_type.value,
            timestamp=time.time(),
            message=message,
            correlation_id=get_correlation_id(),
            source=source,
            success=success,
            details=details,
            source_ip=source_ip,
            user_id=user_id,
        )

    # ------------------------------------------------------------------
    # Public logging methods
    # ------------------------------------------------------------------
    def log_auth_attempt(
        self,
        api_name: str,
        success: bool,
        user_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an API authentication attempt (success or failure)."""
        event_type = (
            SecurityEventType.AUTH_SUCCESS if success else SecurityEventType.AUTH_FAILURE
        )
        msg = f"API auth {'succeeded' if success else 'FAILED'} for {api_name}"
        if not success:
            logger.warning("SECURITY: %s", msg)
        self._emit(self._make_event(
            event_type, msg, source=api_name, success=success,
            details=details, source_ip=source_ip, user_id=user_id,
        ))

    def log_credential_use(
        self,
        api_name: str,
        operation: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log that credentials were accessed/used for an operation."""
        msg = f"Credential used: {api_name} for {operation}"
        self._emit(self._make_event(
            SecurityEventType.CREDENTIAL_USE, msg, source=api_name, success=True,
            details={**(details or {}), "operation": operation},
        ))

    def log_credential_rotation(
        self,
        api_name: str,
        success: bool,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a credential rotation event."""
        msg = f"Credential rotation {'succeeded' if success else 'FAILED'} for {api_name}"
        if not success:
            logger.critical("SECURITY: %s", msg)
        self._emit(self._make_event(
            SecurityEventType.CREDENTIAL_ROTATION, msg, source=api_name,
            success=success, details=details,
        ))

    def log_suspicious_activity(
        self,
        activity_type: str,
        source_ip: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log detected suspicious activity."""
        msg = f"Suspicious activity detected: {activity_type}"
        logger.warning("SECURITY ALERT: %s", msg)
        self._emit(self._make_event(
            SecurityEventType.SUSPICIOUS_ACTIVITY, msg, source=activity_type,
            success=False, source_ip=source_ip, user_id=user_id, details=details,
        ))

    def log_permission_denied(
        self,
        api_name: str,
        required_permission: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an API permission denial."""
        msg = f"Permission denied: {required_permission} on {api_name}"
        logger.error("SECURITY: %s", msg)
        self._emit(self._make_event(
            SecurityEventType.PERMISSION_DENIED, msg, source=api_name, success=False,
            details={**(details or {}), "required_permission": required_permission},
        ))

    def log_trade_event(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        success: bool = True,
        order_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a trade execution event to the audit trail."""
        event_type = (
            SecurityEventType.TRADE_EXECUTED if success else SecurityEventType.TRADE_REJECTED
        )
        msg = f"Trade {'executed' if success else 'REJECTED'}: {side} {quantity} {symbol} @ {price}"
        self._emit(self._make_event(
            event_type, msg, success=success,
            details={"symbol": symbol, "side": side, "quantity": quantity,
                     "price": price, "order_id": order_id, **(details or {})},
        ))

    def log_rate_limit(
        self,
        api_name: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a rate limit event."""
        msg = f"Rate limit hit on {api_name}"
        logger.warning("SECURITY: %s", msg)
        self._emit(self._make_event(
            SecurityEventType.RATE_LIMIT, msg, source=api_name,
            success=False, details=details,
        ))

    def log_config_change(
        self,
        component: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a configuration change event."""
        msg = f"Configuration changed: {component}"
        logger.info("SECURITY: %s", msg)
        self._emit(self._make_event(
            SecurityEventType.CONFIG_CHANGE, msg, source=component, details=details,
        ))

    def log_system_event(
        self,
        event_type: SecurityEventType,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a system lifecycle event (start, stop, config change, rate limit)."""
        self._emit(self._make_event(event_type, message, details=details))

    def get_recent_events(self, limit: int = 100) -> List[dict]:
        """
        Read the last `limit` events from the audit log.

        Uses O(limit) tail reading via collections.deque so cost scales with
        limit, not file size.  Only reads the active log file; rotated backup
        files are not included.
        """
        if not os.path.exists(self._audit_path):
            return []
        try:
            with open(self._audit_path, "r", encoding="utf-8") as f:
                tail = collections.deque(f, maxlen=limit)
            events = []
            for line in tail:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return events
        except OSError:
            return []


# ---------------------------------------------------------------------------
# Module-level lazy singleton
# ---------------------------------------------------------------------------
_security_logger_instance: Optional[SecurityLogger] = None
_security_logger_lock = threading.Lock()


def get_security_logger(log_dir: Optional[str] = None) -> SecurityLogger:
    """
    Return the application-wide SecurityLogger singleton.

    Lazy: the logger (and its audit file) is only created on first call,
    not at module import time.  Pass log_dir only on the first call;
    subsequent calls return the existing instance.
    """
    global _security_logger_instance
    if _security_logger_instance is None:
        with _security_logger_lock:
            if _security_logger_instance is None:
                _security_logger_instance = SecurityLogger(log_dir=log_dir)
    return _security_logger_instance


# Convenience alias — module-level name that lazily resolves on first attribute access
class _LazySecurityLogger:
    """Proxy that forwards all attribute access to get_security_logger()."""

    def __getattr__(self, name: str):
        return getattr(get_security_logger(), name)


security_logger = _LazySecurityLogger()
