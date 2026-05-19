"""Tests for pt_security_logger - issue #55."""

import json
import os
import shutil
import tempfile
import threading
import time
import unittest

from pt_security_logger import (
    CorrelationContext,
    SecurityEvent,
    SecurityEventType,
    SecurityLogger,
    clear_correlation_id,
    correlation_context,
    get_correlation_id,
    set_correlation_id,
)


class TestCorrelationID(unittest.TestCase):
    def tearDown(self):
        clear_correlation_id()

    def test_default_is_none(self):
        clear_correlation_id()
        self.assertIsNone(get_correlation_id())

    def test_set_and_get(self):
        set_correlation_id("test-cid-123")
        self.assertEqual(get_correlation_id(), "test-cid-123")

    def test_context_manager_sets_id(self):
        with CorrelationContext("ctx-abc") as cid:
            self.assertEqual(cid, "ctx-abc")
            self.assertEqual(get_correlation_id(), "ctx-abc")

    def test_context_manager_restores_previous(self):
        set_correlation_id("outer")
        with CorrelationContext("inner"):
            self.assertEqual(get_correlation_id(), "inner")
        self.assertEqual(get_correlation_id(), "outer")

    def test_context_manager_clears_when_no_previous(self):
        clear_correlation_id()
        with CorrelationContext("temp"):
            pass
        self.assertIsNone(get_correlation_id())

    def test_context_manager_auto_generates_id(self):
        with CorrelationContext() as cid:
            self.assertIsNotNone(cid)
            self.assertTrue(cid.startswith("CID_"))

    def test_context_manager_nested_safe(self):
        """Reusing the same CorrelationContext instance in nested with-blocks is safe."""
        ctx = CorrelationContext("reused")
        with ctx as cid1:
            self.assertEqual(cid1, "reused")
            with ctx as cid2:
                self.assertEqual(cid2, "reused")
            # Inner exit must restore the outer's saved state
            self.assertEqual(get_correlation_id(), "reused")
        self.assertIsNone(get_correlation_id())

    def test_snake_case_alias_works(self):
        """correlation_context alias must still function for backwards compatibility."""
        with correlation_context("alias-test") as cid:
            self.assertEqual(cid, "alias-test")

    def test_thread_local_isolation(self):
        """Each thread has its own correlation ID."""
        results = {}

        def worker(name, cid):
            set_correlation_id(cid)
            time.sleep(0.01)
            results[name] = get_correlation_id()

        t1 = threading.Thread(target=worker, args=("t1", "cid-thread-1"))
        t2 = threading.Thread(target=worker, args=("t2", "cid-thread-2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.assertEqual(results["t1"], "cid-thread-1")
        self.assertEqual(results["t2"], "cid-thread-2")


class TestSecurityEvent(unittest.TestCase):
    def test_new_id_format(self):
        eid = SecurityEvent.new_id()
        self.assertTrue(eid.startswith("SEC_"))
        self.assertGreater(len(eid), 10)

    def test_new_id_uses_utc(self):
        """Event ID must be UTC-based (no timezone-ambiguous local time)."""
        from datetime import datetime, timezone

        before = datetime.now(timezone.utc).strftime("%Y%m%d")
        eid = SecurityEvent.new_id()
        self.assertIn(before, eid)

    def test_to_dict_has_required_fields(self):
        event = SecurityEvent(
            event_id="SEC_001",
            event_type=SecurityEventType.AUTH_ATTEMPT.value,
            timestamp=time.time(),
            message="test",
            correlation_id=None,
        )
        d = event.to_dict()
        for field in ("event_id", "event_type", "timestamp", "message"):
            self.assertIn(field, d)

    def test_to_json_valid(self):
        event = SecurityEvent(
            event_id="SEC_002",
            event_type=SecurityEventType.AUTH_SUCCESS.value,
            timestamp=time.time(),
            message="auth ok",
            correlation_id="cid-test",
        )
        parsed = json.loads(event.to_json())
        self.assertEqual(parsed["correlation_id"], "cid-test")


class TestSecurityLogger(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sec_logger = SecurityLogger(log_dir=self.tmpdir)
        clear_correlation_id()

    def tearDown(self):
        clear_correlation_id()
        # close() flushes and releases file handles (critical on Windows)
        self.sec_logger.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _events(self):
        return self.sec_logger.get_recent_events()

    def test_log_auth_attempt_success(self):
        self.sec_logger.log_auth_attempt("robinhood", success=True)
        events = self._events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], SecurityEventType.AUTH_SUCCESS.value)
        self.assertTrue(events[0]["success"])

    def test_log_auth_attempt_failure(self):
        self.sec_logger.log_auth_attempt("robinhood", success=False)
        events = self._events()
        self.assertEqual(events[0]["event_type"], SecurityEventType.AUTH_FAILURE.value)
        self.assertFalse(events[0]["success"])

    def test_log_credential_use(self):
        self.sec_logger.log_credential_use("robinhood", "place_order")
        events = self._events()
        self.assertEqual(
            events[0]["event_type"], SecurityEventType.CREDENTIAL_USE.value
        )
        self.assertEqual(events[0]["details"]["operation"], "place_order")

    def test_log_credential_rotation(self):
        self.sec_logger.log_credential_rotation("robinhood", success=True)
        events = self._events()
        self.assertEqual(
            events[0]["event_type"], SecurityEventType.CREDENTIAL_ROTATION.value
        )

    def test_log_suspicious_activity(self):
        self.sec_logger.log_suspicious_activity(
            "rate_limit_exceeded",
            source_ip="1.2.3.4",
            details={"endpoint": "/orders", "count": 100},
        )
        events = self._events()
        self.assertEqual(
            events[0]["event_type"], SecurityEventType.SUSPICIOUS_ACTIVITY.value
        )
        self.assertEqual(events[0]["source_ip"], "1.2.3.4")

    def test_log_permission_denied(self):
        self.sec_logger.log_permission_denied("robinhood", "sell")
        events = self._events()
        self.assertEqual(
            events[0]["event_type"], SecurityEventType.PERMISSION_DENIED.value
        )
        self.assertEqual(events[0]["details"]["required_permission"], "sell")

    def test_log_trade_event_success(self):
        self.sec_logger.log_trade_event(
            "BTC-USD", "buy", 0.1, 45000.0, order_id="ord-001"
        )
        events = self._events()
        self.assertEqual(
            events[0]["event_type"], SecurityEventType.TRADE_EXECUTED.value
        )
        self.assertEqual(events[0]["details"]["symbol"], "BTC-USD")

    def test_log_trade_event_rejected(self):
        self.sec_logger.log_trade_event("ETH-USD", "sell", 1.0, 3000.0, success=False)
        events = self._events()
        self.assertEqual(
            events[0]["event_type"], SecurityEventType.TRADE_REJECTED.value
        )

    def test_log_rate_limit(self):
        self.sec_logger.log_rate_limit("binance", details={"endpoint": "/api/v3/order"})
        events = self._events()
        self.assertEqual(events[0]["event_type"], SecurityEventType.RATE_LIMIT.value)
        self.assertEqual(events[0]["source"], "binance")

    def test_log_config_change(self):
        self.sec_logger.log_config_change("risk_limits", details={"max_position": 0.1})
        events = self._events()
        self.assertEqual(events[0]["event_type"], SecurityEventType.CONFIG_CHANGE.value)
        self.assertEqual(events[0]["source"], "risk_limits")

    def test_correlation_id_captured_in_event(self):
        with CorrelationContext("trade-workflow-xyz"):
            self.sec_logger.log_auth_attempt("robinhood", success=True)
        events = self._events()
        self.assertEqual(events[0]["correlation_id"], "trade-workflow-xyz")

    def test_correlation_id_none_outside_context(self):
        clear_correlation_id()
        self.sec_logger.log_auth_attempt("robinhood", success=True)
        events = self._events()
        self.assertIsNone(events[0]["correlation_id"])

    def test_multiple_events_ordered(self):
        self.sec_logger.log_auth_attempt("robinhood", success=True)
        self.sec_logger.log_credential_use("robinhood", "fetch_positions")
        self.sec_logger.log_trade_event("BTC-USD", "buy", 0.5, 44000.0)
        events = self._events()
        self.assertEqual(len(events), 3)
        timestamps = [e["timestamp"] for e in events]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_audit_file_created(self):
        self.sec_logger.log_auth_attempt("robinhood", success=True)
        self.assertTrue(os.path.exists(self.sec_logger._audit_path))

    def test_get_recent_events_empty_when_no_log(self):
        """get_recent_events() returns [] when no audit log file exists."""
        tmpdir2 = tempfile.mkdtemp()
        try:
            sl = SecurityLogger(log_dir=tmpdir2)
            # Close immediately — no events written, so file may not exist yet
            sl.close()
            # Remove the file if it was created
            audit_path = sl._audit_path
            if os.path.exists(audit_path):
                os.remove(audit_path)
            # Now verify empty result
            self.assertEqual(sl.get_recent_events(), [])
        finally:
            shutil.rmtree(tmpdir2, ignore_errors=True)

    def test_get_recent_events_limit(self):
        """get_recent_events(limit=N) returns exactly the last N events."""
        for i in range(10):
            self.sec_logger.log_auth_attempt("api", success=True)
        events = self.sec_logger.get_recent_events(limit=5)
        self.assertEqual(len(events), 5)
        # Should be the last 5 — timestamps are non-decreasing
        all_events = self.sec_logger.get_recent_events(limit=100)
        self.assertEqual(events, all_events[-5:])

    def test_log_system_event(self):
        self.sec_logger.log_system_event(
            SecurityEventType.SYSTEM_START,
            "PowerTraderAI started",
            details={"version": "1.0"},
        )
        events = self._events()
        self.assertEqual(events[0]["event_type"], SecurityEventType.SYSTEM_START.value)


if __name__ == "__main__":
    unittest.main()
