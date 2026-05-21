"""Tests for pt_error_handler centralized error management system."""

import unittest
from unittest.mock import MagicMock, patch

from pt_error_handler import (
    ApplicationErrorHandler,
    configure_gui_alerts,
    get_handler,
    handle,
    on_critical,
    on_error,
    on_warning,
)
from pt_errors import ErrorSeverity, TradingError, ErrorCategory


class TestApplicationErrorHandlerSingleton(unittest.TestCase):
    def setUp(self):
        ApplicationErrorHandler.reset_singleton()

    def tearDown(self):
        ApplicationErrorHandler.reset_singleton()

    def test_singleton_same_instance(self):
        h1 = get_handler()
        h2 = get_handler()
        self.assertIs(h1, h2)

    def test_initialises_on_first_call(self):
        h = get_handler()
        self.assertTrue(h._initialised)


class TestErrorHandling(unittest.TestCase):
    def setUp(self):
        ApplicationErrorHandler.reset_singleton()

    def tearDown(self):
        ApplicationErrorHandler.reset_singleton()

    def test_handle_returns_report(self):
        try:
            raise ValueError("test error")
        except ValueError as exc:
            report = handle(exc)
        self.assertIsNotNone(report)
        self.assertEqual(report.exception_type, "ValueError")

    def test_handle_with_context(self):
        try:
            raise RuntimeError("ctx test")
        except RuntimeError as exc:
            report = handle(exc, context={"operation": "test_op"})
        self.assertEqual(report.context.get("operation"), "test_op")

    def test_handle_reraise(self):
        with self.assertRaises(ValueError):
            try:
                raise ValueError("reraise me")
            except ValueError as exc:
                handle(exc, reraise=True)

    def test_handle_critical_forces_severity(self):
        handler = get_handler()
        try:
            raise ValueError("low but critical context")
        except ValueError as exc:
            report = handler.handle_critical(exc)
        self.assertEqual(report.severity, ErrorSeverity.CRITICAL)

    def test_handle_critical_updates_error_counts(self):
        """get_critical_errors must see the escalated severity."""
        handler = get_handler()
        try:
            raise ValueError("escalated")
        except ValueError as exc:
            handler.handle_critical(exc)
        criticals = handler.get_critical_errors()
        self.assertEqual(len(criticals), 1)
        self.assertEqual(criticals[0].severity, ErrorSeverity.CRITICAL)

    def test_powertrader_error_preserved_severity(self):
        try:
            raise TradingError("market closed", severity=ErrorSeverity.HIGH)
        except TradingError as exc:
            report = handle(exc)
        self.assertEqual(report.severity, ErrorSeverity.HIGH)
        self.assertEqual(report.category, ErrorCategory.TRADING_ERROR)


class TestCallbacks(unittest.TestCase):
    def setUp(self):
        ApplicationErrorHandler.reset_singleton()

    def tearDown(self):
        ApplicationErrorHandler.reset_singleton()

    def test_critical_callback_fired(self):
        cb = MagicMock()
        on_critical(cb)
        try:
            raise RuntimeError("critical!")
        except RuntimeError as exc:
            get_handler().handle_critical(exc)
        cb.assert_called_once()

    def test_callback_receives_report(self):
        received = []
        on_error(lambda r: received.append(r))
        try:
            raise TradingError("order failed", severity=ErrorSeverity.HIGH)
        except TradingError as exc:
            handle(exc)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].exception_type, "TradingError")

    def test_warning_callback_fired_for_medium_error(self):
        """MEDIUM-severity TradingError must trigger on_warning callbacks."""
        cb = MagicMock()
        on_warning(cb)
        try:
            raise TradingError("minor issue", severity=ErrorSeverity.MEDIUM)
        except TradingError as exc:
            handle(exc)
        cb.assert_called_once()
        self.assertEqual(cb.call_args[0][0].severity, ErrorSeverity.MEDIUM)

    def test_callback_exception_does_not_propagate(self):
        def bad_cb(report):
            raise RuntimeError("callback exploded")

        on_critical(bad_cb)
        try:
            get_handler().handle_critical(ValueError("test"))
        except RuntimeError:
            self.fail("Callback exception should not propagate")

    def test_unregister_all_specific_severity(self):
        cb = MagicMock()
        on_critical(cb)
        get_handler().unregister_all(ErrorSeverity.CRITICAL)
        get_handler().handle_critical(ValueError("test"))
        cb.assert_not_called()

    def test_unregister_all_clears_every_severity(self):
        cb_crit = MagicMock()
        cb_high = MagicMock()
        on_critical(cb_crit)
        on_error(cb_high)
        get_handler().unregister_all()  # no argument → all
        get_handler().handle_critical(ValueError("x"))
        try:
            raise TradingError("y", severity=ErrorSeverity.HIGH)
        except TradingError as exc:
            handle(exc)
        cb_crit.assert_not_called()
        cb_high.assert_not_called()

    def test_suppress_module_blocks_callbacks(self):
        """Callbacks must NOT fire when the error originates from a suppressed module."""
        cb = MagicMock()
        on_critical(cb)
        get_handler().suppress_module("pt_trader")

        # ErrorHandler captures the test file's frame as report.module, so
        # patch handle_error to override the module to simulate origin in
        # the suppressed source file. Use patch.object so the override is
        # restored via addCleanup regardless of test outcome (no manual
        # try/finally, no leakage to other tests in this class).
        original = get_handler()._handler.handle_error

        def patched(error, context=None, severity_override=None):
            report = original(
                error, context=context, severity_override=severity_override
            )
            report.module = "pt_trader.py"  # filename form, suppression normalizes
            return report

        patcher = patch.object(
            get_handler()._handler, "handle_error", side_effect=patched
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        try:
            raise ValueError("from suppressed module")
        except ValueError as exc:
            get_handler().handle_critical(exc)

        cb.assert_not_called()

    def test_suppress_module_accepts_filename_and_module_name(self):
        """Suppression normalizes — passing either 'pt_trader' or 'pt_trader.py'
        suppresses errors reported as either form."""
        h = get_handler()
        # Both spellings collapse to the same suppressed entry
        h.suppress_module("pt_trader")
        h.suppress_module("pt_trader.py")
        self.assertTrue(h._is_module_suppressed("pt_trader"))
        self.assertTrue(h._is_module_suppressed("pt_trader.py"))
        h.unsuppress_module("pt_trader.py")
        self.assertFalse(h._is_module_suppressed("pt_trader"))


class TestQueryAPI(unittest.TestCase):
    def setUp(self):
        ApplicationErrorHandler.reset_singleton()

    def tearDown(self):
        ApplicationErrorHandler.reset_singleton()

    def test_get_summary_empty(self):
        summary = get_handler().get_summary()
        self.assertEqual(summary["total_errors"], 0)

    def test_get_recent_errors(self):
        for i in range(5):
            try:
                raise ValueError(f"error {i}")
            except ValueError as exc:
                handle(exc)
        recent = get_handler().get_recent_errors(limit=3)
        self.assertEqual(len(recent), 3)

    def test_get_critical_errors_filtered(self):
        try:
            raise ValueError("normal")
        except ValueError as exc:
            handle(exc)
        try:
            raise TradingError("critical trade fail")
        except TradingError as exc:
            get_handler().handle_critical(exc)
        criticals = get_handler().get_critical_errors()
        self.assertEqual(len(criticals), 1)

    def test_clear_history(self):
        try:
            raise ValueError("to clear")
        except ValueError as exc:
            handle(exc)
        get_handler().clear_history()
        self.assertEqual(len(get_handler().get_recent_errors()), 0)


class TestConfigureGuiAlerts(unittest.TestCase):
    def setUp(self):
        ApplicationErrorHandler.reset_singleton()

    def tearDown(self):
        ApplicationErrorHandler.reset_singleton()

    def test_configure_gui_alerts_registers_critical(self):
        critical_cb = MagicMock()
        error_cb = MagicMock()
        configure_gui_alerts(critical_callback=critical_cb, error_callback=error_cb)
        get_handler().handle_critical(ValueError("gui test"))
        critical_cb.assert_called_once()
        error_cb.assert_not_called()

    def test_configure_gui_alerts_registers_error(self):
        error_cb = MagicMock()
        configure_gui_alerts(error_callback=error_cb)
        try:
            raise TradingError("high err", severity=ErrorSeverity.HIGH)
        except TradingError as exc:
            handle(exc)
        error_cb.assert_called_once()

    def test_configure_gui_alerts_none_callbacks_safe(self):
        """Passing None should not raise."""
        configure_gui_alerts(critical_callback=None, error_callback=None)


if __name__ == "__main__":
    unittest.main()
