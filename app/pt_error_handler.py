"""
PowerTraderAI Centralized Error Management System
Single application-wide error handler with notification routing and
classification. All modules should use `get_handler()` instead of
creating their own ErrorHandler instances.

Usage:
    from pt_error_handler import get_handler, on_critical, handle

    # Register a GUI alert callback for critical errors
    on_critical(lambda report: show_alert(report.user_message))

    # Handle an exception anywhere in the codebase
    try:
        risky_operation()
    except Exception as exc:
        handle(exc, context={"operation": "risky_operation"})

    # Or via the global handler directly. The exception variable is only
    # bound inside the `except` block on Python 3 (PEP 3134), so callers
    # must invoke handle()/get_handler().handle() from within that block.
    try:
        risky_operation()
    except Exception as exc:
        get_handler().handle(exc)
"""

import logging
import sys
import threading
from typing import Callable, Dict, List, Optional

from pt_errors import (
    ErrorHandler,
    ErrorReport,
    ErrorSeverity,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Notification callback type alias
# ---------------------------------------------------------------------------
NotificationCallback = Callable[[ErrorReport], None]


# ---------------------------------------------------------------------------
# ApplicationErrorHandler — singleton wrapping ErrorHandler
# ---------------------------------------------------------------------------
class ApplicationErrorHandler:
    """
    Application-wide singleton error handler.

    Wraps pt_errors.ErrorHandler and adds:
    - Per-severity notification callbacks (e.g. pop GUI alerts for CRITICAL)
    - Global error bus: all modules share one instance
    - Thread-safe init, callback registration, and invocation
    - Error suppression rules for known noisy modules
    """

    _instance: Optional["ApplicationErrorHandler"] = None
    _class_lock = threading.Lock()  # Guards singleton creation
    _init_lock = threading.Lock()  # Guards lazy initialisation

    def __new__(cls) -> "ApplicationErrorHandler":
        with cls._class_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialised = False
            return cls._instance

    def _ensure_init(self) -> None:
        """Thread-safe double-checked lazy initialisation."""
        if self._initialised:
            return
        with self._init_lock:
            if self._initialised:  # re-check after acquiring lock
                return
            self._handler = ErrorHandler(logger=logging.getLogger("pt.errors"))
            self._callbacks: Dict[ErrorSeverity, List[NotificationCallback]] = {
                sev: [] for sev in ErrorSeverity
            }
            self._suppressed_modules: set = set()
            self._cb_lock = threading.Lock()
            # Guards mutation/read of the underlying ErrorHandler state
            # (error_reports, error_counts, error_counts_by_severity) so
            # concurrent handle()/clear_history()/get_summary() calls can't
            # lose increments or observe partially-updated counters.
            self._state_lock = threading.Lock()
            self._initialised = True

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------
    def register_callback(
        self, severity: ErrorSeverity, callback: NotificationCallback
    ) -> None:
        """
        Register a callback fired whenever an error of `severity` is handled.
        Callbacks must be non-blocking (offload heavy work to a thread).
        """
        self._ensure_init()
        with self._cb_lock:
            self._callbacks[severity].append(callback)

    def unregister_all(self, severity: Optional[ErrorSeverity] = None) -> None:
        """Clear callbacks for a severity level, or all levels if severity is None."""
        self._ensure_init()
        with self._cb_lock:
            if severity is not None:
                self._callbacks[severity].clear()
            else:
                for cbs in self._callbacks.values():
                    cbs.clear()

    # ------------------------------------------------------------------
    # Suppression
    # ------------------------------------------------------------------
    def suppress_module(self, module_name: str) -> None:
        """Suppress notification callbacks for errors originating from
        ``module_name``.

        Accepts either the bare module name (``"pt_trader"``) or the filename
        (``"pt_trader.py"``). :class:`ErrorReport` stores the filename, and
        suppression normalizes both sides, so either spelling works.
        """
        self._ensure_init()
        with self._cb_lock:
            self._suppressed_modules.add(self._normalize_module(module_name))

    def unsuppress_module(self, module_name: str) -> None:
        self._ensure_init()
        with self._cb_lock:
            self._suppressed_modules.discard(self._normalize_module(module_name))

    # ------------------------------------------------------------------
    # Core handle
    # ------------------------------------------------------------------
    def handle(
        self,
        error: Exception,
        context: Optional[Dict] = None,
        reraise: bool = False,
    ) -> ErrorReport:
        """
        Handle an exception: classify, log, fire callbacks.

        Args:
            error: The exception to handle
            context: Additional key/value context for the report
            reraise: If True, re-raise the exception after handling

        Returns:
            ErrorReport with full classification and metadata
        """
        self._ensure_init()
        with self._state_lock:
            report = self._handler.handle_error(error, context=context)
        self._fire_callbacks(report)
        if reraise:
            # If error is the currently active exception (called from inside an except
            # block), bare raise preserves the original traceback exactly.
            # Otherwise fall back to raise error which uses the traceback already
            # attached to the exception object.
            _, active_exc, _ = sys.exc_info()
            if active_exc is error:
                raise
            raise error
        return report

    def handle_critical(
        self, error: Exception, context: Optional[Dict] = None
    ) -> ErrorReport:
        """
        Handle an exception and escalate to CRITICAL severity regardless of
        automatic classification. Fires CRITICAL-level callbacks only.

        Uses ``ErrorHandler.handle_error(..., severity_override=CRITICAL)`` so
        the underlying logger records the error at CRITICAL from the start —
        no post-hoc severity mutation, no double-counting in
        ``error_counts``, and ``get_critical_errors()`` sees the escalated
        severity consistently.
        """
        self._ensure_init()
        with self._state_lock:
            report = self._handler.handle_error(
                error,
                context=context,
                severity_override=ErrorSeverity.CRITICAL,
            )
        self._fire_callbacks(report)
        return report

    def _fire_callbacks(self, report: ErrorReport) -> None:
        self._ensure_init()
        with self._cb_lock:
            if self._is_module_suppressed(report.module):
                return
            callbacks = list(self._callbacks.get(report.severity, []))
        for cb in callbacks:
            try:
                cb(report)
            except Exception:
                # Log full traceback so callback bugs are diagnosable
                logger.warning("Error callback raised an exception", exc_info=True)

    @staticmethod
    def _normalize_module(name: Optional[str]) -> Optional[str]:
        """Strip a trailing ``.py`` so callers can pass either the module
        name (``pt_trader``) or the filename (``pt_trader.py``) when
        registering suppression — :class:`ErrorReport` carries the filename
        but a module name reads more naturally in code that calls
        :meth:`suppress_module`."""
        if not name:
            return name
        return name[:-3] if name.endswith(".py") else name

    def _is_module_suppressed(self, module: Optional[str]) -> bool:
        normalized = self._normalize_module(module)
        return normalized is not None and normalized in self._suppressed_modules

    # ------------------------------------------------------------------
    # Query / stats
    # ------------------------------------------------------------------
    def get_summary(self) -> Dict:
        self._ensure_init()
        with self._state_lock:
            return self._handler.get_error_summary()

    def get_recent_errors(self, limit: int = 20) -> List[ErrorReport]:
        self._ensure_init()
        if limit <= 0:
            return []
        with self._state_lock:
            return self._handler.error_reports[-limit:]

    def get_critical_errors(self) -> List[ErrorReport]:
        self._ensure_init()
        with self._state_lock:
            return [
                r
                for r in self._handler.error_reports
                if r.severity == ErrorSeverity.CRITICAL
            ]

    def clear_history(self) -> None:
        """Clear in-memory error history (does NOT affect log files).

        Resets every accumulator on the underlying ErrorHandler so that
        subsequent ``get_summary()`` calls don't return stale severity totals
        from the cleared run. Without clearing ``error_counts_by_severity``,
        ``severities`` and ``by_category_severity`` would compound forever
        across clears.
        """
        self._ensure_init()
        with self._state_lock:
            self._handler.error_reports.clear()
            self._handler.error_counts.clear()
            self._handler.error_counts_by_severity.clear()

    @classmethod
    def reset_singleton(cls) -> None:
        """Destroy singleton and force re-init on next call. For testing only."""
        with cls._class_lock:
            cls._instance = None


# ---------------------------------------------------------------------------
# Module-level convenience API
# ---------------------------------------------------------------------------
def get_handler() -> ApplicationErrorHandler:
    """Return the application-wide singleton error handler."""
    h = ApplicationErrorHandler()
    h._ensure_init()
    return h


def handle(
    error: Exception,
    context: Optional[Dict] = None,
    reraise: bool = False,
) -> ErrorReport:
    """Module-level shortcut: handle(exc) from anywhere."""
    return get_handler().handle(error, context=context, reraise=reraise)


def on_critical(callback: NotificationCallback) -> None:
    """Register a callback that fires on every CRITICAL error."""
    get_handler().register_callback(ErrorSeverity.CRITICAL, callback)


def on_error(callback: NotificationCallback) -> None:
    """Register a callback that fires on HIGH severity errors."""
    get_handler().register_callback(ErrorSeverity.HIGH, callback)


def on_warning(callback: NotificationCallback) -> None:
    """Register a callback that fires on MEDIUM severity errors."""
    get_handler().register_callback(ErrorSeverity.MEDIUM, callback)


def configure_gui_alerts(
    critical_callback: Optional[NotificationCallback] = None,
    error_callback: Optional[NotificationCallback] = None,
) -> None:
    """
    Convenience: register GUI alert callbacks for CRITICAL and HIGH errors.
    Call once during application startup.

    Example:
        configure_gui_alerts(
            critical_callback=lambda r: messagebox.showerror("Critical", r.user_message),
            error_callback=lambda r: messagebox.showwarning("Error", r.user_message),
        )
    """
    handler = get_handler()
    if critical_callback is not None:
        handler.register_callback(ErrorSeverity.CRITICAL, critical_callback)
    if error_callback is not None:
        handler.register_callback(ErrorSeverity.HIGH, error_callback)
