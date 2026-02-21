"""
PowerTraderAI+ Error Handling Module
Centralised error handling, custom exceptions, and error reporting system.
"""

import json
import logging
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class ErrorSeverity(Enum):
    """Error severity levels for classification and handling."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Categories of errors for better organisation and handling."""

    API_ERROR = "api_error"
    NETWORK_ERROR = "network_error"
    FILE_ERROR = "file_error"
    TRADING_ERROR = "trading_error"
    VALIDATION_ERROR = "validation_error"
    CONFIGURATION_ERROR = "configuration_error"
    DATA_ERROR = "data_error"
    SYSTEM_ERROR = "system_error"


@dataclass
class ErrorReport:
    """Comprehensive error report with context and metadata."""

    error_id: str
    timestamp: datetime
    message: str
    category: ErrorCategory
    severity: ErrorSeverity
    exception_type: str
    traceback_str: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    module: Optional[str] = None
    function: Optional[str] = None
    line_number: Optional[int] = None
    user_message: Optional[str] = None
    recovery_suggestion: Optional[str] = None


# PowerTraderAI+ Custom Exceptions
class PowerTraderError(Exception):
    """Base exception for all PowerTraderAI+ errors."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.SYSTEM_ERROR,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Dict[str, Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.context = context or {}
        self.timestamp = datetime.now()


class TradingError(PowerTraderError):
    """Errors related to trading operations."""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        context: Dict[str, Any] = None,
    ):
        super().__init__(message, ErrorCategory.TRADING_ERROR, severity, context)


class APIError(PowerTraderError):
    """Errors related to API calls and responses."""

    def __init__(
        self,
        message: str,
        api_name: str = None,
        status_code: int = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Dict[str, Any] = None,
    ):
        context = context or {}
        if api_name:
            context["api_name"] = api_name
        if status_code:
            context["status_code"] = status_code
        super().__init__(message, ErrorCategory.API_ERROR, severity, context)


class NetworkError(PowerTraderError):
    """Errors related to network connectivity and timeouts."""

    def __init__(
        self,
        message: str,
        url: str = None,
        timeout: float = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Dict[str, Any] = None,
    ):
        context = context or {}
        if url:
            context["url"] = url
        if timeout:
            context["timeout"] = timeout
        super().__init__(message, ErrorCategory.NETWORK_ERROR, severity, context)


class ValidationError(PowerTraderError):
    """Errors related to data validation and input checking."""

    def __init__(
        self,
        message: str,
        field_name: str = None,
        field_value: Any = None,
        severity: ErrorSeverity = ErrorSeverity.LOW,
        context: Dict[str, Any] = None,
    ):
        context = context or {}
        if field_name:
            context["field_name"] = field_name
        if field_value is not None:
            context["field_value"] = str(field_value)
        super().__init__(message, ErrorCategory.VALIDATION_ERROR, severity, context)


class ConfigurationError(PowerTraderError):
    """Errors related to configuration and setup."""

    def __init__(
        self,
        message: str,
        config_key: str = None,
        config_file: str = None,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        context: Dict[str, Any] = None,
    ):
        context = context or {}
        if config_key:
            context["config_key"] = config_key
        if config_file:
            context["config_file"] = config_file
        super().__init__(message, ErrorCategory.CONFIGURATION_ERROR, severity, context)


class DataError(PowerTraderError):
    """Errors related to data processing and parsing."""

    def __init__(
        self,
        message: str,
        data_source: str = None,
        expected_format: str = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Dict[str, Any] = None,
    ):
        context = context or {}
        if data_source:
            context["data_source"] = data_source
        if expected_format:
            context["expected_format"] = expected_format
        super().__init__(message, ErrorCategory.DATA_ERROR, severity, context)


class FileOperationError(PowerTraderError):
    """Errors related to file operations."""

    def __init__(
        self,
        message: str,
        file_path: str = None,
        operation: str = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Dict[str, Any] = None,
    ):
        context = context or {}
        if file_path:
            context["file_path"] = file_path
        if operation:
            context["operation"] = operation
        super().__init__(message, ErrorCategory.FILE_ERROR, severity, context)


class ErrorHandler:
    """Centralised error handling and reporting system."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.error_reports: List[ErrorReport] = []
        self.error_counts: Dict[str, int] = {}

        # Recovery suggestions for common errors
        self.recovery_suggestions = {
            ErrorCategory.API_ERROR: "Check API credentials and network connection. Retry after a brief delay.",
            ErrorCategory.NETWORK_ERROR: "Verify internet connection and API endpoints. Consider implementing retry logic.",
            ErrorCategory.FILE_ERROR: "Check file permissions and disk space. Ensure file paths are correct.",
            ErrorCategory.TRADING_ERROR: "Review trading parameters and account balance. Check market conditions.",
            ErrorCategory.VALIDATION_ERROR: "Verify input data format and ranges. Check configuration parameters.",
            ErrorCategory.CONFIGURATION_ERROR: "Review configuration files and ensure all required settings are present.",
            ErrorCategory.DATA_ERROR: "Validate data source and format. Check data parsing logic.",
            ErrorCategory.SYSTEM_ERROR: "Check system resources and dependencies. Review logs for additional context.",
        }

    def generate_error_id(self) -> str:
        """Generate unique error ID for tracking."""
        import uuid

        return f"PT_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"

    def handle_error(
        self, error: Exception, context: Dict[str, Any] = None
    ) -> ErrorReport:
        """
        Handle and report an error with comprehensive logging.

        Args:
            error: The exception that occurred
            context: Additional context information

        Returns:
            ErrorReport: Detailed error report
        """
        # Extract error information
        exc_info = sys.exc_info()
        tb = traceback.extract_tb(exc_info[2]) if exc_info[2] else []

        # Get caller information
        frame_info = tb[-1] if tb else None
        module_name = frame_info.filename.split("/")[-1] if frame_info else None
        function_name = frame_info.name if frame_info else None
        line_number = frame_info.lineno if frame_info else None

        # Determine error category and severity
        if isinstance(error, PowerTraderError):
            category = error.category
            severity = error.severity
            error_context = {**(error.context or {}), **(context or {})}
        else:
            category = self._classify_error(error)
            severity = self._determine_severity(error, category)
            error_context = context or {}

        # Create error report
        error_report = ErrorReport(
            error_id=self.generate_error_id(),
            timestamp=datetime.now(),
            message=str(error),
            category=category,
            severity=severity,
            exception_type=type(error).__name__,
            traceback_str=traceback.format_exc() if exc_info[2] else None,
            context=error_context,
            module=module_name,
            function=function_name,
            line_number=line_number,
            user_message=self._generate_user_message(category, str(error)),
            recovery_suggestion=self.recovery_suggestions.get(
                category, "Contact support for assistance."
            ),
        )

        # Log the error
        self._log_error(error_report)

        # Store error report
        self.error_reports.append(error_report)
        self._update_error_counts(category)

        return error_report

    def _classify_error(self, error: Exception) -> ErrorCategory:
        """Classify error based on exception type and message."""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()

        if "api" in error_str or "http" in error_type:
            return ErrorCategory.API_ERROR
        elif (
            "network" in error_str
            or "connection" in error_str
            or "timeout" in error_str
        ):
            return ErrorCategory.NETWORK_ERROR
        elif (
            "file" in error_str or "ioerror" in error_type or "permission" in error_str
        ):
            return ErrorCategory.FILE_ERROR
        elif "trading" in error_str or "order" in error_str or "balance" in error_str:
            return ErrorCategory.TRADING_ERROR
        elif (
            "validation" in error_str or "invalid" in error_str or "value" in error_type
        ):
            return ErrorCategory.VALIDATION_ERROR
        elif "config" in error_str or "setting" in error_str:
            return ErrorCategory.CONFIGURATION_ERROR
        elif "data" in error_str or "parse" in error_str or "format" in error_str:
            return ErrorCategory.DATA_ERROR
        else:
            return ErrorCategory.SYSTEM_ERROR

    def _determine_severity(
        self, error: Exception, category: ErrorCategory
    ) -> ErrorSeverity:
        """Determine error severity based on type and category."""
        error_str = str(error).lower()

        # Critical errors that could cause system failure
        if any(
            word in error_str for word in ["critical", "fatal", "shutdown", "crash"]
        ):
            return ErrorSeverity.CRITICAL

        # High severity for trading and configuration errors
        if category in [ErrorCategory.TRADING_ERROR, ErrorCategory.CONFIGURATION_ERROR]:
            return ErrorSeverity.HIGH

        # Medium for API and network issues
        if category in [ErrorCategory.API_ERROR, ErrorCategory.NETWORK_ERROR]:
            return ErrorSeverity.MEDIUM

        # Low for validation and data errors
        return ErrorSeverity.LOW

    def _generate_user_message(
        self, category: ErrorCategory, error_message: str
    ) -> str:
        """Generate user-friendly error message."""
        category_messages = {
            ErrorCategory.API_ERROR: "There was an issue connecting to the trading API. Please check your connection and try again.",
            ErrorCategory.NETWORK_ERROR: "Network connection issue detected. Please verify your internet connection.",
            ErrorCategory.FILE_ERROR: "File operation failed. Please check file permissions and disk space.",
            ErrorCategory.TRADING_ERROR: "Trading operation encountered an issue. Please review your trading parameters.",
            ErrorCategory.VALIDATION_ERROR: "Invalid data detected. Please check your input values.",
            ErrorCategory.CONFIGURATION_ERROR: "Configuration issue found. Please review your settings.",
            ErrorCategory.DATA_ERROR: "Data processing error occurred. Please verify data source and format.",
            ErrorCategory.SYSTEM_ERROR: "System error detected. Please check system resources and try again.",
        }

        return category_messages.get(
            category,
            "An unexpected error occurred. Please try again or contact support.",
        )

    def _log_error(self, error_report: ErrorReport) -> None:
        """Log error report with appropriate level."""
        log_message = f"[{error_report.error_id}] {error_report.message}"

        if error_report.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(log_message, extra={"error_report": error_report})
        elif error_report.severity == ErrorSeverity.HIGH:
            self.logger.error(log_message, extra={"error_report": error_report})
        elif error_report.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(log_message, extra={"error_report": error_report})
        else:
            self.logger.info(log_message, extra={"error_report": error_report})

        # Log traceback for debugging
        if error_report.traceback_str and error_report.severity in [
            ErrorSeverity.HIGH,
            ErrorSeverity.CRITICAL,
        ]:
            self.logger.debug(
                f"[{error_report.error_id}] Traceback:\\n{error_report.traceback_str}"
            )

    def _update_error_counts(self, category: ErrorCategory) -> None:
        """Update error count statistics."""
        key = category.value
        self.error_counts[key] = self.error_counts.get(key, 0) + 1

    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of error statistics."""
        total_errors = len(self.error_reports)
        if total_errors == 0:
            return {"total_errors": 0, "categories": {}, "severities": {}}

        # Count by category
        category_counts = {}
        severity_counts = {}

        for report in self.error_reports:
            category_counts[report.category.value] = (
                category_counts.get(report.category.value, 0) + 1
            )
            severity_counts[report.severity.value] = (
                severity_counts.get(report.severity.value, 0) + 1
            )

        return {
            "total_errors": total_errors,
            "categories": category_counts,
            "severities": severity_counts,
            "recent_errors": [
                {
                    "id": report.error_id,
                    "timestamp": report.timestamp.isoformat(),
                    "message": report.message,
                    "category": report.category.value,
                    "severity": report.severity.value,
                }
                for report in self.error_reports[-10:]  # Last 10 errors
            ],
        }


# Global error handler instance
error_handler = ErrorHandler()


# Decorator for automatic error handling
def handle_errors(category: ErrorCategory = None, severity: ErrorSeverity = None):
    """
    Decorator for automatic error handling in functions.

    Args:
        category: Override error category classification
        severity: Override error severity determination
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Override classification if specified
                if isinstance(e, PowerTraderError):
                    if category:
                        e.category = category
                    if severity:
                        e.severity = severity

                error_report = error_handler.handle_error(
                    e,
                    {
                        "function": func.__name__,
                        "args": str(args)[:100],  # Truncate for privacy
                        "kwargs": str(kwargs)[:100],
                    },
                )

                # Re-raise the error after handling
                raise e

        return wrapper

    return decorator
