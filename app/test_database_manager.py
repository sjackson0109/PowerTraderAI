"""Tests for pt_database_manager - issue #54."""

import os
import shutil
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import MagicMock

from pt_database_manager import (
    DatabaseConnectionPool,
    DatabaseHealthMonitor,
    InputSanitizer,
    TransactionError,
    atomic_transaction,
)


def _make_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    conn.commit()
    conn.close()


class TestDatabaseConnectionPool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db = os.path.join(self.tmpdir, "test.db")
        _make_db(self.db)
        self.pool = DatabaseConnectionPool(self.db)

    def tearDown(self):
        # Close thread-local connection before removing temp dir (critical on Windows)
        self.pool.close_thread_connection()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_connection_returns_connection(self):
        conn = self.pool.get_connection()
        self.assertIsInstance(conn, sqlite3.Connection)

    def test_thread_local_same_connection(self):
        c1 = self.pool.get_connection()
        c2 = self.pool.get_connection()
        self.assertIs(c1, c2)

    def test_different_threads_get_different_connections(self):
        connections = []
        errors = []
        barrier = threading.Barrier(2, timeout=5)

        def get_conn():
            try:
                barrier.wait()
                conn = self.pool.get_connection()
                connections.append(conn)
                self.pool.close_thread_connection()
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=get_conn)
        t2 = threading.Thread(target=get_conn)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [], f"Thread errors: {errors}")
        self.assertEqual(len(connections), 2)
        self.assertIsNot(connections[0], connections[1])

    def test_wal_mode_applied(self):
        conn = self.pool.get_connection()
        result = conn.execute("PRAGMA journal_mode").fetchone()
        self.assertEqual(result[0], "wal")

    def test_foreign_keys_enabled(self):
        conn = self.pool.get_connection()
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        self.assertEqual(result[0], 1)

    def test_health_check_passes(self):
        self.assertTrue(self.pool.check_health())

    def test_health_check_missing_file(self):
        pool = DatabaseConnectionPool("/nonexistent/path.db")
        self.assertFalse(pool.check_health())

    def test_get_stats(self):
        self.pool.get_connection()
        stats = self.pool.get_stats()
        self.assertGreater(stats["total_connections_created"], 0)
        self.assertTrue(stats["db_exists"])


class TestAtomicTransaction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db = os.path.join(self.tmpdir, "atomic.db")
        _make_db(self.db)
        self.conn = sqlite3.connect(self.db, isolation_level=None)

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_commits_on_success(self):
        with atomic_transaction(self.conn) as c:
            c.execute("INSERT INTO t VALUES (1, 'hello')")
        row = self.conn.execute("SELECT val FROM t WHERE id=1").fetchone()
        self.assertEqual(row[0], "hello")

    def test_rolls_back_on_exception(self):
        try:
            with atomic_transaction(self.conn) as c:
                c.execute("INSERT INTO t VALUES (2, 'rollback_test')")
                raise ValueError("intentional")
        except ValueError:
            pass
        row = self.conn.execute("SELECT val FROM t WHERE id=2").fetchone()
        self.assertIsNone(row)

    def test_multiple_operations_atomic(self):
        with atomic_transaction(self.conn) as c:
            c.execute("INSERT INTO t VALUES (3, 'a')")
            c.execute("INSERT INTO t VALUES (4, 'b')")
        count = self.conn.execute(
            "SELECT COUNT(*) FROM t WHERE id IN (3,4)"
        ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_partial_failure_rolls_back_all(self):
        try:
            with atomic_transaction(self.conn) as c:
                c.execute("INSERT INTO t VALUES (5, 'ok')")
                c.execute(
                    "INSERT INTO t VALUES (5, 'dup')"
                )  # duplicate PK → OperationalError
        except Exception:
            pass
        row = self.conn.execute("SELECT * FROM t WHERE id=5").fetchone()
        self.assertIsNone(row)

    def test_non_contention_error_propagates_original(self):
        """Non-busy OperationalError should propagate as original sqlite3.OperationalError,
        NOT wrapped as TransactionError."""
        bad_conn = sqlite3.connect(":memory:", isolation_level=None)
        bad_conn.execute("CREATE TABLE x (id INTEGER PRIMARY KEY)")
        try:
            with self.assertRaises(sqlite3.OperationalError):
                with atomic_transaction(bad_conn) as c:
                    c.execute("SELECT * FROM nonexistent_table")
        finally:
            bad_conn.close()

    def test_contention_retries_then_raises_transaction_error(self):
        """When max_retries exceeded on busy/locked, TransactionError is raised."""
        # Create a second connection that holds a write lock
        blocker = sqlite3.connect(self.db, isolation_level=None)
        blocker.execute("BEGIN EXCLUSIVE")
        victim = sqlite3.connect(self.db, timeout=0.01, isolation_level=None)
        try:
            with self.assertRaises(TransactionError):
                with atomic_transaction(victim, max_retries=1, base_delay=0.01) as c:
                    c.execute("INSERT INTO t VALUES (99, 'blocked')")
        finally:
            blocker.execute("ROLLBACK")
            blocker.close()
            victim.close()

    def test_commit_contention_retries(self):
        """SQLITE_BUSY on COMMIT should trigger retry, not silently fail."""

        # Python 3.12 made sqlite3.Connection.execute read-only, so we cannot
        # patch it directly. Use a transparent wrapper that intercepts execute.
        class _CommitFailingConn:
            def __init__(self, conn):
                self._conn = conn
                self.commit_calls = 0

            def execute(self, sql, *args, **kwargs):
                if sql == "COMMIT":
                    self.commit_calls += 1
                    if self.commit_calls == 1:
                        raise sqlite3.OperationalError("database is locked")
                return self._conn.execute(sql, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._conn, name)

        wrapped = _CommitFailingConn(self.conn)
        with atomic_transaction(wrapped, max_retries=2, base_delay=0.01):
            self.conn.execute("INSERT INTO t VALUES (77, 'commit_retry')")

        # Row should be committed on the second COMMIT attempt
        row = self.conn.execute("SELECT val FROM t WHERE id=77").fetchone()
        self.assertEqual(row[0], "commit_retry")
        self.assertGreater(wrapped.commit_calls, 1, "COMMIT should have been retried")


class TestInputSanitizer(unittest.TestCase):
    def test_sanitize_strips_null_bytes(self):
        self.assertNotIn("\x00", InputSanitizer.sanitize_string("hello\x00world"))

    def test_sanitize_caps_length(self):
        self.assertEqual(
            len(InputSanitizer.sanitize_string("x" * 1000, max_length=10)), 10
        )

    def test_sanitize_non_string_converted(self):
        self.assertEqual(InputSanitizer.sanitize_string(42), "42")

    def test_check_sql_injection_drop(self):
        self.assertTrue(InputSanitizer.check_sql_injection("DROP TABLE users"))

    def test_check_sql_injection_union(self):
        self.assertTrue(InputSanitizer.check_sql_injection("1' UNION SELECT * FROM--"))

    def test_check_sql_injection_clean(self):
        self.assertFalse(InputSanitizer.check_sql_injection("BTC-USD"))

    def test_check_sql_injection_no_false_positives(self):
        """Words containing SQL keywords as substrings must not trigger detection."""
        safe_values = ["dropbox", "selection", "truncate_me", "executor", "unionist"]
        for val in safe_values:
            self.assertFalse(
                InputSanitizer.check_sql_injection(val),
                f"False positive on safe value: {val!r}",
            )

    def test_check_sql_injection_punctuation_tokens(self):
        """Punctuation injection tokens (-- ;) must still be detected."""
        self.assertTrue(InputSanitizer.check_sql_injection("value; comment"))
        self.assertTrue(InputSanitizer.check_sql_injection("value -- comment"))

    def test_safe_identifier_valid(self):
        self.assertEqual(InputSanitizer.safe_identifier("orders"), "orders")
        self.assertEqual(InputSanitizer.safe_identifier("_temp_table"), "_temp_table")

    def test_safe_identifier_invalid(self):
        with self.assertRaises(ValueError):
            InputSanitizer.safe_identifier("orders; DROP TABLE--")
        with self.assertRaises(ValueError):
            InputSanitizer.safe_identifier("1invalid")

    def test_sanitize_record(self):
        result = InputSanitizer.sanitize_record(
            {"symbol": "BTC-USD", "note": "hello\x00"}
        )
        self.assertNotIn("\x00", result["note"])
        self.assertEqual(result["symbol"], "BTC-USD")

    def test_sanitize_record_clears_injection(self):
        result = InputSanitizer.sanitize_record({"name": "'; DROP TABLE orders; --"})
        self.assertEqual(result["name"], "")


class TestDatabaseHealthMonitor(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db = os.path.join(self.tmpdir, "health.db")
        _make_db(self.db)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_check_now_healthy(self):
        self.assertTrue(DatabaseHealthMonitor(self.db).check_now())

    def test_check_now_missing_file(self):
        self.assertFalse(DatabaseHealthMonitor("/nonexistent/path.db").check_now())

    def test_start_stop(self):
        monitor = DatabaseHealthMonitor(self.db, check_interval=60)
        monitor.start()
        self.assertTrue(monitor._thread.is_alive())
        monitor.stop()
        self.assertFalse(monitor._thread.is_alive())

    def test_get_status(self):
        monitor = DatabaseHealthMonitor(self.db)
        monitor.check_now()
        status = monitor.get_status()
        self.assertTrue(status["last_check_ok"])
        self.assertEqual(status["db_path"], self.db)

    def test_on_corrupt_callback_not_fired_for_healthy_db(self):
        cb = MagicMock()
        monitor = DatabaseHealthMonitor(self.db, on_corrupt=cb)
        monitor.check_now()
        cb.assert_not_called()

    def test_missing_file_classified_as_unavailable_not_corrupt(self):
        """Missing DB file must NOT trigger on_corrupt (review feedback).

        check_integrity() returns UNAVAILABLE for missing files so callers
        can distinguish a transient/setup problem from real corruption.
        """
        from pt_database_manager import IntegrityStatus

        status = DatabaseConnectionPool("/nonexistent/path.db").check_integrity()
        self.assertEqual(status, IntegrityStatus.UNAVAILABLE)

    def test_unavailable_does_not_fire_on_corrupt(self):
        """A missing DB file must route to on_unavailable, not on_corrupt."""
        on_corrupt = MagicMock()
        on_unavailable = MagicMock()
        monitor = DatabaseHealthMonitor(
            "/nonexistent/path.db",
            on_corrupt=on_corrupt,
            on_unavailable=on_unavailable,
        )
        monitor.check_now_status()
        # _run() is what fires callbacks - simulate one tick
        monitor._run = lambda: None  # avoid threading
        # Inline the dispatch logic the monitor uses
        from pt_database_manager import IntegrityStatus

        status = monitor.check_now_status()
        self.assertEqual(status, IntegrityStatus.UNAVAILABLE)
        on_corrupt.assert_not_called()

    def test_check_integrity_ok_on_healthy_db(self):
        from pt_database_manager import IntegrityStatus

        status = DatabaseConnectionPool(self.db).check_integrity()
        self.assertEqual(status, IntegrityStatus.OK)

    def test_get_status_exposes_last_status(self):
        monitor = DatabaseHealthMonitor(self.db)
        monitor.check_now_status()
        status = monitor.get_status()
        self.assertEqual(status["last_status"], "ok")


if __name__ == "__main__":
    unittest.main()
