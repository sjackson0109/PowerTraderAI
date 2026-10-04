"""Coinbase "Test Connection": one read-only authenticated call, distinct outcomes.

All HTTP is mocked at the requests Session layer; keys are generated per test.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

import requests

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(__file__))

from helpers_coinbase import KEY_NAME, make_ec_pem, recorded_http  # noqa: E402
from pt_exchange_abstraction import (  # noqa: E402
    ConnectionStatus,
    ExchangeType,
)
from pt_exchanges import CoinbaseExchange  # noqa: E402
from pt_multi_exchange import (  # noqa: E402
    ExchangeConfig,
    ExchangeConfigManager,
    MultiExchangeManager,
    TradingConfig,
)

PERMS_URL = "https://api.coinbase.com/api/v3/brokerage/key_permissions"
FULL_PERMS = {
    "can_view": True,
    "can_trade": True,
    "can_transfer": False,
    "portfolio_uuid": "x",
    "portfolio_type": "CONSUMER",
}


def _exchange(pem=None, key_name=KEY_NAME):
    return CoinbaseExchange(api_key=key_name, api_secret=pem or make_ec_pem())


class TestOutcomes(unittest.TestCase):
    def check(self, status, body=None, raw=None):
        with recorded_http() as http:
            http.respond_with(status, body, raw)
            result = _exchange().check_connection()
        return result, http

    def test_success_reports_permissions(self):
        result, http = self.check(200, FULL_PERMS)
        self.assertTrue(result.ok)
        self.assertIs(result.status, ConnectionStatus.OK)
        self.assertIn("trade: yes", result.message)
        self.assertIn("transfer: no", result.message)
        self.assertNotIn("Warning", result.message)
        self.assertEqual(result.details["portfolio_type"], "CONSUMER")

    def test_success_view_only_key_is_noted(self):
        result, _ = self.check(200, {**FULL_PERMS, "can_trade": False})
        self.assertTrue(result.ok)
        self.assertIn("cannot trade", result.message)

    def test_success_warns_when_key_can_transfer(self):
        result, _ = self.check(200, {**FULL_PERMS, "can_transfer": True})
        self.assertTrue(result.ok)
        self.assertIn("move funds", result.message)

    def test_401_is_auth_failure(self):
        result, _ = self.check(401, {"error": "unauthorized"})
        self.assertIs(result.status, ConnectionStatus.AUTH_FAILED)
        self.assertFalse(result.ok)
        self.assertEqual(result.details["http_status"], 401)
        self.assertIn("rejected the credentials", result.message)

    def test_403_is_permission_failure(self):
        result, _ = self.check(403, {"error": "forbidden"})
        self.assertIs(result.status, ConnectionStatus.PERMISSION_DENIED)
        self.assertIn("View permission", result.message)

    def test_200_without_view_permission_is_permission_failure(self):
        result, _ = self.check(200, {**FULL_PERMS, "can_view": False})
        self.assertIs(result.status, ConnectionStatus.PERMISSION_DENIED)
        self.assertFalse(result.details["can_view"])

    def test_network_failures_are_network_errors(self):
        for exc in (
            requests.exceptions.ConnectionError("dns"),
            requests.exceptions.Timeout("slow"),
            requests.exceptions.SSLError("cert"),
        ):
            with self.subTest(exc=type(exc).__name__):
                with recorded_http() as http:
                    http.raise_on_request(exc)
                    result = _exchange().check_connection()
                self.assertIs(result.status, ConnectionStatus.NETWORK_ERROR)
                self.assertIn("Could not reach Coinbase", result.message)

    def test_endpoint_problems_are_not_reported_as_auth_verdicts(self):
        for code in (404, 429, 500, 502, 302):
            with self.subTest(code=code):
                result, _ = self.check(code, {})
                self.assertIs(result.status, ConnectionStatus.ENDPOINT_ERROR)
                self.assertEqual(result.details["http_status"], code)

    def test_200_with_garbage_body_is_endpoint_error(self):
        for raw in (b"<html>captive portal</html>", b"[]", b'{"nope": 1}'):
            with self.subTest(raw=raw):
                result, _ = self.check(200, raw=raw)
                self.assertIs(result.status, ConnectionStatus.ENDPOINT_ERROR)

    def test_all_outcomes_are_distinct(self):
        seen = {
            self.check(200, FULL_PERMS)[0].status,
            self.check(401)[0].status,
            self.check(403)[0].status,
            self.check(500)[0].status,
        }
        with recorded_http() as http:
            http.raise_on_request(requests.exceptions.ConnectionError())
            seen.add(_exchange().check_connection().status)
        self.assertEqual(len(seen), 5)


class TestReadOnlyAndSingleCall(unittest.TestCase):
    def test_exactly_one_get_to_key_permissions(self):
        with recorded_http() as http:
            http.respond_with(200, FULL_PERMS)
            _exchange().check_connection()
        self.assertEqual(http.methods, ["GET"])
        self.assertEqual(http.urls, [PERMS_URL])
        self.assertEqual(http.order_like(), [])

    def test_request_carries_bearer_jwt_and_no_body_or_redirects(self):
        with recorded_http() as http:
            http.respond_with(200, FULL_PERMS)
            _exchange().check_connection()
        kwargs = http.calls[0][2]
        auth = kwargs["headers"]["Authorization"]
        self.assertTrue(auth.startswith("Bearer "))
        self.assertEqual(auth.count("."), 2)
        self.assertFalse(kwargs.get("allow_redirects", True))
        # requests.get passes params=None; nothing may be sent as query/body.
        self.assertIsNone(kwargs.get("params"))
        self.assertIsNone(kwargs.get("data"))
        self.assertIsNone(kwargs.get("json"))
        self.assertGreater(kwargs["timeout"], 0)

    def test_no_http_call_for_every_failure_kind_other_than_the_one_get(self):
        for status in (200, 401, 403, 404, 500):
            with self.subTest(status=status):
                with recorded_http() as http:
                    http.respond_with(status, FULL_PERMS)
                    _exchange().check_connection()
                self.assertEqual(len(http.calls), 1)
                self.assertEqual(http.order_like(), [])

    def test_order_methods_stay_unimplemented(self):
        ex = _exchange()
        with recorded_http() as http:
            with self.assertRaises(NotImplementedError):
                ex.place_order("BTC-USD", "buy", 0.001)
            with self.assertRaises(NotImplementedError):
                ex.cancel_order("abc")
        self.assertEqual(http.calls, [])


class TestBadCredentialsNeverLeaveTheMachine(unittest.TestCase):
    def assertInvalid(self, key_name, secret):
        with recorded_http() as http:
            result = CoinbaseExchange(
                api_key=key_name, api_secret=secret
            ).check_connection()
        self.assertIs(result.status, ConnectionStatus.INVALID_CREDENTIALS)
        self.assertEqual(http.calls, [])
        return result

    def test_empty(self):
        self.assertInvalid("", "")

    def test_legacy_short_key_and_hmac_secret(self):
        result = self.assertInvalid("a1b2c3d4e5f6", "bGVnYWN5LXNlY3JldA==")
        self.assertIn("retired", result.message)

    def test_missing_begin_end_lines(self):
        pem = make_ec_pem()
        body = "".join(pem.splitlines()[1:-1])
        self.assertInvalid(KEY_NAME, body)

    def test_ed25519_key_rejected_with_explanation(self):
        from helpers_coinbase import make_ed25519_pem

        result = self.assertInvalid(KEY_NAME, make_ed25519_pem())
        self.assertIn("Ed25519", result.message)

    def test_garbage_between_markers(self):
        self.assertInvalid(
            KEY_NAME,
            "-----BEGIN EC PRIVATE KEY-----\nAAAAnotakey\n-----END EC PRIVATE KEY-----",
        )


class TestNoSecretsInMessages(unittest.TestCase):
    def test_messages_contain_neither_token_nor_key_material(self):
        pem = make_ec_pem()
        body = "".join(pem.splitlines()[1:-1])
        with recorded_http() as http:
            for status in (200, 401, 403, 500):
                http.respond_with(status, FULL_PERMS)
                result = _exchange(pem).check_connection()
                token = http.calls[-1][2]["headers"]["Authorization"].split()[-1]
                blob = result.message + repr(result.details)
                self.assertNotIn(token, blob)
                self.assertNotIn(body[:40], blob)
            http.raise_on_request(requests.exceptions.ConnectionError(pem))
            result = _exchange(pem).check_connection()
            self.assertNotIn(body[:40], result.message)


class TestManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config_manager = ExchangeConfigManager(self.tmp.name)
        self.manager = MultiExchangeManager(self.config_manager)
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("POWERTRADER_COINBASE")
        }
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_method_exists_the_gui_calls(self):
        # Regression: the GUI called a method the manager never defined.
        self.assertTrue(
            callable(getattr(MultiExchangeManager, "test_exchange_connection"))
        )

    def test_typed_credentials_are_tested_and_not_saved(self):
        with recorded_http() as http:
            http.respond_with(200, FULL_PERMS)
            result = self.manager.test_exchange_connection(
                "coinbase", KEY_NAME, make_ec_pem()
            )
        self.assertTrue(result.ok)
        self.assertEqual(len(http.calls), 1)
        self.assertFalse(os.path.exists(self.config_manager.config_file))
        self.assertIsNone(self.config_manager.config)

    def test_blank_form_falls_back_to_saved_credentials(self):
        self.config_manager.save_config(
            TradingConfig(
                "EU",
                "coinbase",
                [ExchangeConfig("coinbase", True, 1, KEY_NAME, make_ec_pem())],
            )
        )
        with recorded_http() as http:
            http.respond_with(401)
            result = self.manager.test_exchange_connection("coinbase")
        self.assertIs(result.status, ConnectionStatus.AUTH_FAILED)
        self.assertEqual(len(http.calls), 1)

    def test_no_credentials_anywhere(self):
        with recorded_http() as http:
            result = self.manager.test_exchange_connection("coinbase")
        self.assertIs(result.status, ConnectionStatus.INVALID_CREDENTIALS)
        self.assertEqual(http.calls, [])

    def test_unknown_and_unimplemented_exchanges_are_unsupported_not_ok(self):
        with recorded_http() as http:
            unknown = self.manager.test_exchange_connection("nosuchexchange", "k", "s")
            # Registered but without a read-only check implemented.
            kraken = self.manager.test_exchange_connection("kraken", "k", "s")
        self.assertIs(unknown.status, ConnectionStatus.UNSUPPORTED)
        self.assertIs(kraken.status, ConnectionStatus.UNSUPPORTED)
        self.assertFalse(kraken.ok)
        self.assertEqual(http.calls, [])

    def test_connector_exception_becomes_a_result(self):
        with mock.patch.object(
            CoinbaseExchange, "check_connection", side_effect=RuntimeError("boom")
        ):
            result = self.manager.test_exchange_connection("coinbase", KEY_NAME, "x")
        self.assertIs(result.status, ConnectionStatus.ENDPOINT_ERROR)
        self.assertNotIn("boom", result.message)


class TestGuiFormatting(unittest.TestCase):
    def test_each_status_has_a_distinct_headline(self):
        from exchange_config_gui import STATUS_HEADLINES, format_test_result
        from pt_exchange_abstraction import ConnectionTestResult

        self.assertEqual(set(STATUS_HEADLINES), set(ConnectionStatus))
        self.assertEqual(len(set(STATUS_HEADLINES.values())), len(ConnectionStatus))
        for status in ConnectionStatus:
            text = format_test_result(
                "coinbase", ConnectionTestResult("coinbase", status, "msg")
            )
            self.assertIn("Coinbase", text)
            self.assertIn(STATUS_HEADLINES[status], text)
            self.assertIn("msg", text)


if __name__ == "__main__":
    unittest.main()
