"""
PowerTraderAI+ Database Security & Transaction Management
Provides atomic transaction wrappers with retry-on-busy, connection health
monitoring, input sanitization, and retry-on-contention (SQLITE_BUSY/LOCKED) for SQLite.

Note: SQLite uses file-level locking, not true deadlocks. The retry mechanism handles
SQLITE_BUSY and SQLITE_LOCKED (write contention), not classic deadlocks.

Designed to complement the existing OrderManagementDB / SQLAlchemy layer.
Can also be used standalone for direct SQLite access.
"""

import logging
import os
import re
import sqlite3
import time
import threading
from contextlib import contextmanager
from typing import Any, Callable, Generator, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_BUSY_TIMEOUT_MS = 5_000
DEFAULT_MAX_RETRIES = 5
DEFAULT_RETRY_DELAY = 0.1
MAX_RETRY_DELAY = 2.0
INTEGRITY_CHECK_INTERVAL = 3600


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class DatabaseError(Exception):
    """Base database error."""


class TransactionError(DatabaseError):
    """Raised when a transaction cannot complete after retries."""


class DatabaseCorruptionError(DatabaseError):
    """Raised when integrity_check detects database corruption."""


class DBConnectionError(DatabaseError):
    """Raised when a database connection cannot be established."""


# ---------------------------------------------------------------------------
# DatabaseConnectionPool
# ---------------------------------------------------------------------------
class DatabaseConnectionPool:
    """
    Thread-local SQLite connection pool with health monitoring.

    Each thread gets its own connection via threading.local(), which is safe
    for SQLite's threading model. Connection creation is serialized via a lock
    so that `PRAGMA journal_mode=WAL` (which requires a brief write-lock) does
    not cause SQLITE_LOCKED when two threads initialize simultaneously.

    Args:
        db_path: Path to the SQLite database file
        busy_timeout_ms: Milliseconds before SQLITE_BUSY is raised
    """

    def __init__(self, db_path: str, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS):
        self.db_path = os.path.abspath(db_path)
        self.busy_timeout_ms = busy_timeout_ms
        self._local = threading.local()
        self._create_lock = threading.Lock()  # Serializes connection creation
        self._stats_lock = threading.Lock()
        self._connection_count = 0
        self._health_failures = 0

    def get_connection(self) -> sqlite3.Connection:
        """Return thread-local connection, creating it if needed."""
        if not getattr(self._local, "conn", None):
            self._local.conn = self._create_connection()
        return self._local.conn

    def _create_connection(self) -> sqlite3.Connection:
        """
        Create a new configured SQLite connection, serialized under lock.
        Serialization prevents concurrent PRAGMA journal_mode=WAL from
        triggering SQLITE_LOCKED on Windows.
        """
        with self._create_lock:
            try:
                conn = sqlite3.connect(
                    self.db_path,
                    timeout=self.busy_timeout_ms / 1000,
                    # Thread-local pool guarantees each connection is only accessed
                    # from the thread that created it; check_same_thread=True lets
                    # SQLite enforce this as a safety net.
                    check_same_thread=True,
                    isolation_level=None,  # Manual transaction control
                )
                conn.row_factory = sqlite3.Row
                self._apply_pragmas(conn)
                with self._stats_lock:
                    self._connection_count += 1
                logger.debug(
                    "New DB connection #%d for thread %s",
                    self._connection_count,
                    threading.current_thread().name,
                )
                return conn
            except sqlite3.Error as exc:
                raise DBConnectionError(
                    f"Cannot connect to {self.db_path}: {exc}"
                ) from exc

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        """Apply performance and safety PRAGMAs."""
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        conn.execute("PRAGMA foreign_keys=ON")

    def close_thread_connection(self) -> None:
        """Close this thread's connection (call at thread exit)."""
        conn = getattr(self._local, "conn", None)
        if conn:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            self._local.conn = None

    def check_health(self) -> bool:
        """Run PRAGMA integrity_check on a fresh connection. Returns True if OK."""
        if not os.path.exists(self.db_path):
            logger.warning("Database file missing: %s", self.db_path)
            with self._stats_lock:
                self._health_failures += 1
            return False
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            try:
                result = conn.execute("PRAGMA integrity_check").fetchone()
            finally:
                conn.close()
            healthy = result and result[0] == "ok"
            with self._stats_lock:
                if not healthy:
                    self._health_failures += 1
                    logger.error("DB integrity check FAILED: %s", result)
                else:
                    self._health_failures = 0
            return healthy
        except sqlite3.Error as exc:
            with self._stats_lock:
                self._health_failures += 1
            logger.error("DB health check error: %s", exc)
            return False

    def get_stats(self) -> dict:
        with self._stats_lock:
            return {
                "db_path": self.db_path,
                "total_connections_created": self._connection_count,
                "health_failures": self._health_failures,
                "db_exists": os.path.exists(self.db_path),
            }


# ---------------------------------------------------------------------------
# AtomicTransaction context manager
# ---------------------------------------------------------------------------
@contextmanager
def atomic_transaction(
    conn: sqlite3.Connection,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_RETRY_DELAY,
) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for atomic SQLite transactions with exponential-backoff
    retry on SQLITE_BUSY / SQLITE_LOCKED.

    Usage:
        with atomic_transaction(conn) as c:
            c.execute("INSERT INTO orders ...")
            c.execute("UPDATE balances ...")
        # Committed on clean exit, rolled back on any exception.

    Args:
        conn: SQLite connection with isolation_level=None (manual control)
        max_retries: Retry limit on busy/locked errors
        base_delay: Starting retry delay in seconds (exponential backoff)

    Raises:
        TransactionError: When max_retries exceeded on contention
        Exception: Any non-retryable exception from within the block
    """
    attempt = 0
    delay = base_delay

    while True:
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
            # COMMIT is outside the inner try so contention here reaches the
            # outer retry loop rather than being silently swallowed.
            # Apply a short retry loop specifically for COMMIT contention.
            commit_attempts = 0
            commit_delay = base_delay
            while True:
                try:
                    conn.execute("COMMIT")
                    return
                except sqlite3.OperationalError as commit_exc:
                    ce_lower = str(commit_exc).lower()
                    if not any(w in ce_lower for w in ("busy", "locked")):
                        try:
                            conn.execute("ROLLBACK")
                        except sqlite3.Error:
                            pass
                        raise
                    if commit_attempts >= max_retries:
                        try:
                            conn.execute("ROLLBACK")
                        except sqlite3.Error:
                            pass
                        raise TransactionError(
                            f"COMMIT failed after {commit_attempts + 1} attempt(s): {commit_exc}"
                        ) from commit_exc
                    commit_attempts += 1
                    actual = min(commit_delay, MAX_RETRY_DELAY)
                    logger.warning(
                        "COMMIT contention (attempt %d/%d), retrying in %.2fs",
                        commit_attempts,
                        max_retries,
                        actual,
                    )
                    time.sleep(actual)
                    commit_delay *= 2

        except sqlite3.OperationalError as exc:
            err_lower = str(exc).lower()
            is_contention = any(
                w in err_lower for w in ("busy", "locked", "cannot start")
            )
            if not is_contention:
                # Non-contention OperationalError (e.g. constraint violation, syntax error)
                # — propagate original exception unchanged; do not wrap as TransactionError.
                raise
            if attempt >= max_retries:
                logger.error(
                    "Transaction failed after %d attempt(s): %s", attempt + 1, exc
                )
                raise TransactionError(
                    f"Transaction failed after {attempt + 1} attempt(s): {exc}"
                ) from exc

            attempt += 1
            actual_delay = min(delay, MAX_RETRY_DELAY)
            logger.warning(
                "DB contention (attempt %d/%d), retrying in %.2fs: %s",
                attempt,
                max_retries,
                actual_delay,
                exc,
            )
            time.sleep(actual_delay)
            delay *= 2


# ---------------------------------------------------------------------------
# InputSanitizer
# ---------------------------------------------------------------------------
class InputSanitizer:
    """
    Sanitize values before they reach the database.
    Always prefer parameterized queries; use this as an additional defense layer.
    """

    # Alphabetic SQL keywords use word-boundary matching to avoid false positives
    # on legitimate values like "dropbox", "selection", "truncate_me".
    # Punctuation tokens (-- ; ) are matched as exact substrings.
    _SQL_KEYWORDS_WORD = frozenset(
        [
            "drop",
            "delete",
            "truncate",
            "insert",
            "update",
            "alter",
            "create",
            "exec",
            "execute",
            "union",
            "select",
        ]
    )
    _SQL_TOKENS_EXACT = frozenset(["--", ";"])
    _SQL_KEYWORD_RE = re.compile(
        r"(?:"
        + "|".join(
            re.escape(k)
            for k in [
                "drop",
                "delete",
                "truncate",
                "insert",
                "update",
                "alter",
                "create",
                "exec",
                "execute",
                "union",
                "select",
            ]
        )
        + r")"
    )
    _IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    @staticmethod
    def sanitize_string(value: Any, max_length: int = 500) -> str:
        """Strip null bytes and control chars, cap length."""
        if not isinstance(value, str):
            value = str(value)
        cleaned = "".join(c for c in value if ord(c) >= 32 or c in "\n\r\t")
        return cleaned[:max_length].strip()

    @staticmethod
    def check_sql_injection(value: str) -> bool:
        """
        Returns True if value contains SQL injection patterns.
        NOTE: Heuristic only — always use parameterized queries.
        Uses word-boundary matching for alphabetic keywords to avoid false
        positives on values like "dropbox", "selection", "truncate_me".
        """
        lower = value.lower()
        return bool(InputSanitizer._SQL_KEYWORD_RE.search(lower)) or any(
            tok in lower for tok in InputSanitizer._SQL_TOKENS_EXACT
        )

    @staticmethod
    def safe_identifier(name: str) -> str:
        """Validate a SQL identifier (table/column name). Raises ValueError if invalid."""
        if not InputSanitizer._IDENTIFIER_RE.match(name):
            raise ValueError(f"Invalid SQL identifier: {name!r}")
        return name

    @staticmethod
    def sanitize_record(record: dict, max_str_length: int = 500) -> dict:
        """Sanitize all string values in a dict before DB insert."""
        result = {}
        for k, v in record.items():
            if isinstance(v, str):
                sanitized = InputSanitizer.sanitize_string(v, max_str_length)
                if InputSanitizer.check_sql_injection(sanitized):
                    logger.warning(
                        "Potential SQL injection in field '%s' — value cleared", k
                    )
                    sanitized = ""
                result[k] = sanitized
            else:
                result[k] = v
        return result


# ---------------------------------------------------------------------------
# DatabaseHealthMonitor
# ---------------------------------------------------------------------------
class DatabaseHealthMonitor:
    """
    Background daemon thread that periodically runs integrity_check and
    fires a callback when corruption is detected.

    Usage:
        monitor = DatabaseHealthMonitor(
            db_path="order_management.db",
            on_corrupt=lambda: trigger_emergency_stop(),
        )
        monitor.start()
    """

    def __init__(
        self,
        db_path: str,
        on_corrupt: Optional[Callable[[], None]] = None,
        check_interval: float = INTEGRITY_CHECK_INTERVAL,
    ):
        self.db_path = db_path
        self._on_corrupt = on_corrupt
        self._interval = check_interval
        self._pool = DatabaseConnectionPool(db_path)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_check_ok: Optional[bool] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="DBHealthMonitor", daemon=True
        )
        self._thread.start()
        logger.info("DB health monitor started (interval: %ss)", self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.warning(
                    "DB health monitor thread did not stop within 5s — "
                    "it may still be running"
                )
            else:
                logger.info("DB health monitor stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                healthy = self._pool.check_health()
                self._last_check_ok = healthy
                if not healthy and self._on_corrupt:
                    logger.critical(
                        "DB corruption detected — firing on_corrupt callback"
                    )
                    self._on_corrupt()
            except Exception as exc:
                logger.error("DB health monitor error: %s", exc)
            self._stop_event.wait(timeout=self._interval)

    def check_now(self) -> bool:
        healthy = self._pool.check_health()
        self._last_check_ok = healthy
        return healthy

    def get_status(self) -> dict:
        return {
            "db_path": self.db_path,
            "last_check_ok": self._last_check_ok,
            "monitor_running": bool(self._thread and self._thread.is_alive()),
            "pool_stats": self._pool.get_stats(),
        }
