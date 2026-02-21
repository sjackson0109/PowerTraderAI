"""
PowerTraderAI+ Utilities Module
Common utilities and helper functions used across the trading system.
"""

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class FileOperationResult:
    """Result object for file operations with success/failure tracking."""

    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    file_path: Optional[str] = None


class SafeFileHandler:
    """Safe file operations with proper error handling and logging."""

    @staticmethod
    def read_file(
        file_path: Union[str, Path], encoding: str = "utf-8"
    ) -> FileOperationResult:
        """
        Safely read file content with comprehensive error handling.

        Args:
            file_path: Path to file to read
            encoding: File encoding (default: utf-8)

        Returns:
            FileOperationResult with content or error information
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                return FileOperationResult(
                    success=False,
                    error=f"File not found: {file_path}",
                    file_path=str(file_path),
                )

            if not file_path.is_file():
                return FileOperationResult(
                    success=False,
                    error=f"Path is not a file: {file_path}",
                    file_path=str(file_path),
                )

            with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                content = f.read()

            return FileOperationResult(
                success=True, data=content, file_path=str(file_path)
            )

        except (IOError, OSError) as e:
            return FileOperationResult(
                success=False,
                error=f"IO error reading file: {e}",
                file_path=str(file_path) if file_path else None,
            )
        except Exception as e:
            return FileOperationResult(
                success=False,
                error=f"Unexpected error reading file: {e}",
                file_path=str(file_path) if file_path else None,
            )

    @staticmethod
    def write_file(
        file_path: Union[str, Path],
        content: str,
        encoding: str = "utf-8",
        create_dirs: bool = True,
    ) -> FileOperationResult:
        """
        Safely write content to file with error handling.

        Args:
            file_path: Path where to write file
            content: Content to write
            encoding: File encoding (default: utf-8)
            create_dirs: Whether to create parent directories if they don't exist

        Returns:
            FileOperationResult indicating success or failure
        """
        try:
            file_path = Path(file_path)

            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding=encoding) as f:
                f.write(content)

            return FileOperationResult(
                success=True, data=len(content), file_path=str(file_path)
            )

        except (IOError, OSError) as e:
            return FileOperationResult(
                success=False,
                error=f"IO error writing file: {e}",
                file_path=str(file_path) if file_path else None,
            )
        except Exception as e:
            return FileOperationResult(
                success=False,
                error=f"Unexpected error writing file: {e}",
                file_path=str(file_path) if file_path else None,
            )


class PerformanceTimer:
    """Context manager for timing operations."""

    def __init__(self, operation_name: str, logger: Optional[logging.Logger] = None):
        self.operation_name = operation_name
        self.logger = logger or logging.getLogger(__name__)
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.time()
        self.logger.debug(f"Starting {self.operation_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        if exc_type is None:
            self.logger.debug(f"Completed {self.operation_name} in {duration:.3f}s")
        else:
            self.logger.error(
                f"Failed {self.operation_name} after {duration:.3f}s: {exc_val}"
            )

    @property
    def duration(self) -> Optional[float]:
        """Get operation duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


class ConfigurationValidator:
    """Validates configuration parameters and trading settings."""

    @staticmethod
    def validate_timeframe(timeframe: str) -> bool:
        """Validate trading timeframe format."""
        valid_timeframes = {
            "1m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "8h",
            "12h",
            "1d",
            "1w",
        }
        return timeframe.lower() in valid_timeframes

    @staticmethod
    def validate_symbol(symbol: str) -> bool:
        """Validate trading symbol format (e.g., BTC-USD, ETH-USDT)."""
        if not symbol or not isinstance(symbol, str):
            return False

        # Basic format validation: XXX-XXX pattern
        parts = symbol.upper().split("-")
        if len(parts) != 2:
            return False

        # Each part should be 2-6 characters, alphanumeric
        for part in parts:
            if not (2 <= len(part) <= 6) or not part.isalpha():
                return False

        return True

    @staticmethod
    def validate_amount(
        amount: Union[int, float],
        min_amount: float = 0.0,
        max_amount: Optional[float] = None,
    ) -> bool:
        """Validate trading amount."""
        try:
            amount = float(amount)
            if amount < min_amount:
                return False
            if max_amount is not None and amount > max_amount:
                return False
            return True
        except (ValueError, TypeError):
            return False


def format_currency(amount: float, currency: str = "USD", decimals: int = 2) -> str:
    """Format currency amount for display."""
    if currency.upper() == "USD":
        return f"${amount:,.{decimals}f}"
    else:
        return f"{amount:,.{decimals}f} {currency.upper()}"


def format_percentage(value: float, decimals: int = 2) -> str:
    """Format percentage for display."""
    return f"{value:+.{decimals}f}%"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers, returning default if denominator is zero."""
    try:
        if denominator == 0:
            return default
        return numerator / denominator
    except (TypeError, ZeroDivisionError):
        return default


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate string to maximum length with optional suffix."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, max_calls: int, time_window: float):
        """
        Initialize rate limiter.

        Args:
            max_calls: Maximum number of calls allowed
            time_window: Time window in seconds
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []

    def can_proceed(self) -> bool:
        """Check if a call can proceed without hitting rate limit."""
        now = time.time()

        # Remove calls outside the time window
        self.calls = [
            call_time for call_time in self.calls if now - call_time < self.time_window
        ]

        # Check if we're under the limit
        return len(self.calls) < self.max_calls

    def record_call(self) -> None:
        """Record that a call was made."""
        self.calls.append(time.time())

    def wait_time(self) -> float:
        """Get time to wait before next call can be made."""
        if self.can_proceed():
            return 0.0

        if not self.calls:
            return 0.0

        # Time until the oldest call falls outside the window
        oldest_call = min(self.calls)
        return max(0.0, self.time_window - (time.time() - oldest_call))


# Global instances for common use
file_handler = SafeFileHandler()
