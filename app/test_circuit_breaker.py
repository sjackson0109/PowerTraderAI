"""Tests for pt_circuit_breaker module."""

import time
import unittest

from pt_circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerRegistry,
    CircuitState,
    registry,
)


def _raise(exc):
    """Helper: raise exc — cleaner than lambda generator-throw pattern."""
    raise exc


class TestCircuitBreakerBasic(unittest.TestCase):
    def setUp(self):
        self.cb = CircuitBreaker(
            "test", failure_threshold=3, success_threshold=2, timeout=0.1
        )

    def test_starts_closed(self):
        self.assertEqual(self.cb.state, CircuitState.CLOSED)

    def test_passes_through_on_success(self):
        result = self.cb.call(lambda: 42)
        self.assertEqual(result, 42)

    def test_opens_after_threshold_failures(self):
        for _ in range(3):
            with self.assertRaises(ValueError):
                self.cb.call(_raise, ValueError("fail"))
        self.assertEqual(self.cb.state, CircuitState.OPEN)

    def test_rejects_when_open(self):
        for _ in range(3):
            try:
                self.cb.call(_raise, ValueError("fail"))
            except ValueError:
                pass
        with self.assertRaises(CircuitBreakerError):
            self.cb.call(lambda: 42)

    def test_half_open_after_timeout(self):
        for _ in range(3):
            try:
                self.cb.call(_raise, ValueError())
            except ValueError:
                pass
        time.sleep(0.15)
        self.assertEqual(self.cb.state, CircuitState.HALF_OPEN)

    def test_recovers_to_closed_after_successes(self):
        for _ in range(3):
            try:
                self.cb.call(_raise, ValueError())
            except ValueError:
                pass
        time.sleep(0.15)
        self.cb.call(lambda: True)
        self.cb.call(lambda: True)
        self.assertEqual(self.cb.state, CircuitState.CLOSED)

    def test_reopens_on_failure_in_half_open(self):
        for _ in range(3):
            try:
                self.cb.call(_raise, ValueError())
            except ValueError:
                pass
        time.sleep(0.15)
        try:
            self.cb.call(_raise, ValueError())
        except ValueError:
            pass
        self.assertEqual(self.cb.state, CircuitState.OPEN)

    def test_failure_count_reset_on_half_open_reopen(self):
        """failure_count should be 1 (not cumulative) when HALF_OPEN → OPEN."""
        for _ in range(3):
            try:
                self.cb.call(_raise, ValueError())
            except ValueError:
                pass
        time.sleep(0.15)
        try:
            self.cb.call(_raise, ValueError())
        except ValueError:
            pass
        stats = self.cb.get_stats()
        # Re-opened by exactly one failure from HALF_OPEN
        self.assertEqual(stats["stats"]["failure_count"], 1)

    def test_manual_reset(self):
        for _ in range(3):
            try:
                self.cb.call(_raise, ValueError())
            except ValueError:
                pass
        self.cb.reset()
        self.assertEqual(self.cb.state, CircuitState.CLOSED)

    def test_success_resets_failure_streak(self):
        """Successes reset the failure streak while CLOSED."""
        for _ in range(2):
            try:
                self.cb.call(_raise, ValueError())
            except ValueError:
                pass
        self.cb.call(lambda: True)  # success resets failure_count
        self.assertEqual(self.cb.state, CircuitState.CLOSED)
        # Need full threshold again to open
        for _ in range(3):
            try:
                self.cb.call(_raise, ValueError())
            except ValueError:
                pass
        self.assertEqual(self.cb.state, CircuitState.OPEN)

    def test_get_stats_does_not_mutate_state(self):
        """get_stats() must not cause OPEN → HALF_OPEN transition as a side effect."""
        for _ in range(3):
            try:
                self.cb.call(_raise, ValueError())
            except ValueError:
                pass
        self.assertEqual(self.cb._state, CircuitState.OPEN)
        # Manipulate open_at so timeout appears elapsed
        self.cb._open_at = time.time() - self.cb.timeout - 1
        # Reading stats must NOT mutate internal state
        stats = self.cb.get_stats()
        self.assertEqual(self.cb._state, CircuitState.OPEN)  # still OPEN internally
        # But the reported effective state reflects the timeout elapsed
        self.assertEqual(stats["state"], CircuitState.HALF_OPEN.value)


class TestCircuitBreakerDecorator(unittest.TestCase):
    def test_decorator_usage(self):
        cb = CircuitBreaker(
            "deco_test", failure_threshold=2, success_threshold=1, timeout=0.1
        )

        @cb
        def api_call(value):
            if value < 0:
                raise ValueError("negative")
            return value * 2

        self.assertEqual(api_call(5), 10)
        with self.assertRaises(ValueError):
            api_call(-1)
        with self.assertRaises(ValueError):
            api_call(-1)
        self.assertEqual(cb.state, CircuitState.OPEN)


class TestCircuitBreakerRegistry(unittest.TestCase):
    def setUp(self):
        # Isolate each test from module-level breakers and other tests
        registry.clear()

    def tearDown(self):
        registry.clear()

    def test_singleton(self):
        r1 = CircuitBreakerRegistry()
        r2 = CircuitBreakerRegistry()
        self.assertIs(r1, r2)

    def test_register_and_get(self):
        cb = registry.register("reg_test_x", failure_threshold=4, timeout=30)
        self.assertIs(registry.get("reg_test_x"), cb)

    def test_idempotent_register(self):
        cb1 = registry.register("reg_idem", failure_threshold=3, timeout=30)
        cb2 = registry.register("reg_idem", failure_threshold=99, timeout=99)
        self.assertIs(cb1, cb2)
        # Config from first registration is preserved
        self.assertEqual(cb1.failure_threshold, 3)

    def test_health_summary_empty(self):
        health = registry.get_health_summary()
        self.assertIn("healthy", health)
        self.assertIn("open_circuits", health)
        self.assertTrue(health["healthy"])

    def test_health_summary_with_open_circuit(self):
        cb = registry.register("health_test", failure_threshold=1, timeout=60)
        try:
            cb.call(_raise, RuntimeError())
        except RuntimeError:
            pass
        health = registry.get_health_summary()
        self.assertFalse(health["healthy"])
        self.assertIn("health_test", health["open_circuits"])

    def test_clear(self):
        registry.register("to_clear", failure_threshold=3, timeout=30)
        registry.clear()
        self.assertIsNone(registry.get("to_clear"))

    def test_reset_all(self):
        cb = registry.register("reset_test", failure_threshold=1, timeout=60)
        try:
            cb.call(_raise, RuntimeError())
        except RuntimeError:
            pass
        self.assertEqual(cb.state, CircuitState.OPEN)
        registry.reset_all()
        self.assertEqual(cb.state, CircuitState.CLOSED)


class TestCircuitBreakerStats(unittest.TestCase):
    def test_stats_track_calls(self):
        # Use isolated breaker (not registry) to avoid state leakage
        cb = CircuitBreaker("stats_test_isolated", failure_threshold=10, timeout=60)
        cb.call(lambda: True)
        try:
            cb.call(_raise, RuntimeError())
        except RuntimeError:
            pass
        stats = cb.get_stats()
        self.assertEqual(stats["stats"]["success_count"], 1)
        self.assertEqual(stats["stats"]["failure_count"], 1)
        self.assertEqual(stats["stats"]["total_calls"], 2)

    def test_stats_track_rejections(self):
        cb = CircuitBreaker("reject_test_isolated", failure_threshold=2, timeout=60)
        for _ in range(2):
            try:
                cb.call(_raise, RuntimeError())
            except RuntimeError:
                pass
        try:
            cb.call(lambda: True)
        except CircuitBreakerError:
            pass
        stats = cb.get_stats()
        self.assertEqual(stats["stats"]["rejected_count"], 1)

    def test_stats_reset_on_recovery(self):
        cb = CircuitBreaker(
            "recovery_stats", failure_threshold=2, success_threshold=1, timeout=0.05
        )
        for _ in range(2):
            try:
                cb.call(_raise, RuntimeError())
            except RuntimeError:
                pass
        time.sleep(0.08)
        cb.call(lambda: True)  # triggers CLOSED
        stats = cb.get_stats()
        # After recovery, failure_count reset to 0
        self.assertEqual(stats["stats"]["failure_count"], 0)


if __name__ == "__main__":
    unittest.main()
