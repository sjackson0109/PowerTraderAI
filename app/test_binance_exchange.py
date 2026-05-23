"""
Tests for BinanceExchange authenticated order execution - issue #85.
All tests mock HTTP calls; no real Binance API credentials required.
"""

import hashlib
import hmac
import unittest
from unittest.mock import MagicMock, patch

import sys

sys.path.insert(0, ".")

from pt_exchanges import (
    BinanceExchange,
    BinanceRateLimitError,
    BinanceTimestampError,
)


def _make_exchange(key="test_key", secret="test_secret", testnet=False):
    ex = BinanceExchange(api_key=key, api_secret=secret, testnet=testnet)
    # Skip /api/v3/time round-trip in tests; offset stays at 0 (good enough).
    ex._time_synced = True
    return ex


def _sign(secret: str, params: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), params.encode("utf-8"), hashlib.sha256
    ).hexdigest()


class TestBinanceSign(unittest.TestCase):
    """HMAC-SHA256 signature generation."""

    def test_sign_produces_hex_digest(self):
        ex = _make_exchange()
        result = ex._sign("symbol=BTCUSDT&timestamp=1234567890")
        self.assertEqual(len(result), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_sign_deterministic(self):
        ex = _make_exchange()
        params = "symbol=BTCUSDT&side=BUY&timestamp=1000000"
        self.assertEqual(ex._sign(params), ex._sign(params))

    def test_sign_matches_reference(self):
        """Verify against a known HMAC-SHA256 value."""
        secret = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
        ex = BinanceExchange(api_key="key", api_secret=secret)
        params = (
            "symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC"
            "&quantity=1&price=0.1&recvWindow=5000&timestamp=1499827319559"
        )
        result = ex._sign(params)
        # Reference from Binance docs
        self.assertEqual(
            result, "c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71"
        )


def _seed_filters(
    ex,
    binance_symbol="BTCUSDT",
    step="0.00001000",
    tick="0.01000000",
    min_qty="0.00001000",
    min_notional="10.00000000",
):
    """Pre-seed the symbol filter cache so place_order does not hit /exchangeInfo."""
    from decimal import Decimal as _D

    ex._symbol_filters[binance_symbol] = {
        "stepSize": _D(step),
        "tickSize": _D(tick),
        "minQty": _D(min_qty),
        "minNotional": _D(min_notional),
    }


class TestBinancePlaceOrder(unittest.TestCase):
    def setUp(self):
        self.ex = _make_exchange()
        _seed_filters(self.ex, "BTCUSDT")
        _seed_filters(self.ex, "ETHUSDT")

    @patch("pt_exchanges.requests.post")
    def test_market_buy_success(self, mock_post):
        mock_post.return_value.json.return_value = {
            "orderId": 12345,
            "status": "FILLED",
            "executedQty": "0.00100000",
            "price": "0.00000000",
            "transactTime": 1499827319559,
        }
        result = self.ex.place_order("BTC-USD", "buy", 0.001)
        self.assertEqual(result.exchange, "binance")
        self.assertEqual(result.side, "buy")
        self.assertIn("BTCUSDT:12345", result.order_id)
        self.assertEqual(result.status, "filled")

    @patch("pt_exchanges.requests.post")
    def test_limit_sell_sends_price_and_tif(self, mock_post):
        mock_post.return_value.json.return_value = {
            "orderId": 99,
            "status": "NEW",
            "executedQty": "0",
            "price": "75000.00",
            "transactTime": 1499827319559,
        }
        self.ex.place_order("BTC-USD", "sell", 0.001, price=75000.0)
        call_url = mock_post.call_args[0][0]
        self.assertIn("type=LIMIT", call_url)
        self.assertIn("timeInForce=GTC", call_url)
        self.assertIn("price=", call_url)

    @patch("pt_exchanges.requests.post")
    def test_market_order_no_price_param(self, mock_post):
        mock_post.return_value.json.return_value = {
            "orderId": 1,
            "status": "FILLED",
            "executedQty": "0.001",
            "price": "0",
            "transactTime": 1000,
        }
        self.ex.place_order("ETH-USD", "buy", 0.01)
        call_url = mock_post.call_args[0][0]
        self.assertIn("type=MARKET", call_url)
        self.assertNotIn("timeInForce", call_url)

    @patch("pt_exchanges.requests.post")
    def test_api_error_raises_runtime_error(self, mock_post):
        mock_post.return_value.json.return_value = {
            "code": -1013,
            "msg": "Filter failure: MIN_NOTIONAL",
        }
        # 0.001 survives local LOT_SIZE/minQty checks so we exercise the
        # Binance-side error propagation path.
        with self.assertRaises(RuntimeError) as ctx:
            self.ex.place_order("BTC-USD", "buy", 0.001)
        self.assertIn("-1013", str(ctx.exception))

    def test_missing_credentials_raises(self):
        ex = BinanceExchange(api_key="", api_secret="")
        with self.assertRaises(RuntimeError):
            ex.place_order("BTC-USD", "buy", 0.001)

    @patch("pt_exchanges.requests.post")
    def test_signature_in_url(self, mock_post):
        mock_post.return_value.json.return_value = {
            "orderId": 1,
            "status": "FILLED",
            "executedQty": "0.001",
            "price": "0",
            "transactTime": 1000,
        }
        self.ex.place_order("BTC-USD", "buy", 0.001)
        call_url = mock_post.call_args[0][0]
        self.assertIn("signature=", call_url)
        self.assertIn("X-MBX-APIKEY", mock_post.call_args[1]["headers"])

    @patch("pt_exchanges.requests.post")
    def test_symbol_converted_to_binance_format(self, mock_post):
        mock_post.return_value.json.return_value = {
            "orderId": 2,
            "status": "FILLED",
            "executedQty": "0.1",
            "price": "0",
            "transactTime": 1000,
        }
        self.ex.place_order("BTC-USD", "buy", 0.1)
        call_url = mock_post.call_args[0][0]
        self.assertIn("symbol=BTCUSDT", call_url)


class TestBinanceFilterEnforcement(unittest.TestCase):
    """Symbol filter rounding and rejection (LOT_SIZE, PRICE_FILTER, MIN_NOTIONAL)."""

    def setUp(self):
        self.ex = _make_exchange()
        _seed_filters(self.ex, "BTCUSDT")

    @patch("pt_exchanges.requests.post")
    def test_quantity_rounded_down_to_step(self, mock_post):
        """0.0012345 with stepSize 0.00001 must send "0.00123" (truncated)."""
        mock_post.return_value.json.return_value = {
            "orderId": 1,
            "status": "FILLED",
            "executedQty": "0.00123",
            "price": "0",
            "transactTime": 1,
        }
        self.ex.place_order("BTC-USD", "buy", 0.0012345)
        call_url = mock_post.call_args[0][0]
        self.assertIn("quantity=0.00123", call_url)
        # Must never round up
        self.assertNotIn("quantity=0.00124", call_url)

    @patch("pt_exchanges.requests.post")
    def test_price_rounded_down_to_tick(self, mock_post):
        """75000.999 with tickSize 0.01 must send "75000.99" (truncated)."""
        mock_post.return_value.json.return_value = {
            "orderId": 1,
            "status": "NEW",
            "executedQty": "0",
            "price": "75000.99",
            "transactTime": 1,
        }
        self.ex.place_order("BTC-USD", "sell", 0.001, price=75000.999)
        call_url = mock_post.call_args[0][0]
        self.assertIn("price=75000.99", call_url)

    def test_quantity_below_min_qty_raises(self):
        """Qty 0.0000001 rounds to 0, below minQty 0.00001 — reject locally."""
        with self.assertRaises(RuntimeError) as ctx:
            self.ex.place_order("BTC-USD", "buy", 0.0000001)
        self.assertIn("minQty", str(ctx.exception))

    def test_notional_below_min_notional_raises(self):
        """Qty 0.00001 * price 1.00 = 0.00001 < minNotional 10 — reject locally."""
        with self.assertRaises(RuntimeError) as ctx:
            self.ex.place_order("BTC-USD", "buy", 0.00001, price=1.00)
        self.assertIn("minNotional", str(ctx.exception))

    @patch("pt_exchanges.requests.get")
    def test_filters_fetched_and_cached(self, mock_get):
        """First call fetches /exchangeInfo; second call uses cache."""
        mock_get.return_value.json.return_value = {
            "symbols": [
                {
                    "filters": [
                        {
                            "filterType": "LOT_SIZE",
                            "stepSize": "0.001",
                            "minQty": "0.001",
                        },
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                        {"filterType": "NOTIONAL", "minNotional": "5"},
                    ],
                }
            ],
        }
        fresh = _make_exchange()
        f1 = fresh._get_symbol_filters("ETHUSDT")
        f2 = fresh._get_symbol_filters("ETHUSDT")
        self.assertEqual(mock_get.call_count, 1)  # cached on 2nd call
        self.assertEqual(f1, f2)
        self.assertEqual(str(f1["stepSize"]), "0.001")
        self.assertEqual(str(f1["minNotional"]), "5")


class TestBinanceGetBalance(unittest.TestCase):
    def setUp(self):
        self.ex = _make_exchange()

    @patch("pt_exchanges.requests.get")
    def test_returns_nonzero_balances(self, mock_get):
        mock_get.return_value.json.return_value = {
            "balances": [
                {"asset": "BTC", "free": "0.5", "locked": "0.0"},
                {"asset": "USDT", "free": "1000.0", "locked": "50.0"},
                {"asset": "XRP", "free": "0.0", "locked": "0.0"},  # zero - excluded
            ]
        }
        result = self.ex.get_balance()
        self.assertIn("BTC", result)
        self.assertIn("USDT", result)
        self.assertNotIn("XRP", result)
        self.assertAlmostEqual(result["BTC"], 0.5)

    @patch("pt_exchanges.requests.get")
    def test_includes_locked_nonzero(self, mock_get):
        mock_get.return_value.json.return_value = {
            "balances": [
                {"asset": "ETH", "free": "0.0", "locked": "1.0"},
            ]
        }
        result = self.ex.get_balance()
        self.assertIn("ETH", result)

    def test_missing_credentials_raises(self):
        ex = BinanceExchange(api_key="", api_secret="")
        with self.assertRaises(RuntimeError):
            ex.get_balance()


class TestBinanceGetOrderStatus(unittest.TestCase):
    def setUp(self):
        self.ex = _make_exchange()

    @patch("pt_exchanges.requests.get")
    def test_returns_order_result(self, mock_get):
        mock_get.return_value.json.return_value = {
            "orderId": 12345,
            "side": "BUY",
            "status": "FILLED",
            "executedQty": "0.001",
            "price": "75000.00",
            "time": 1499827319559,
        }
        result = self.ex.get_order_status("BTCUSDT:12345")
        self.assertEqual(result.status, "filled")
        self.assertEqual(result.side, "buy")
        self.assertEqual(result.exchange, "binance")

    @patch("pt_exchanges.requests.get")
    def test_symbol_in_request(self, mock_get):
        mock_get.return_value.json.return_value = {
            "orderId": 99,
            "side": "SELL",
            "status": "NEW",
            "executedQty": "0",
            "price": "0",
            "time": 1000,
        }
        self.ex.get_order_status("BTCUSDT:99")
        call_url = mock_get.call_args[0][0]
        self.assertIn("symbol=BTCUSDT", call_url)
        self.assertIn("orderId=99", call_url)

    def test_invalid_format_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.ex.get_order_status("12345")  # missing symbol prefix

    def test_missing_credentials_raises(self):
        ex = BinanceExchange(api_key="", api_secret="")
        with self.assertRaises(RuntimeError):
            ex.get_order_status("BTCUSDT:1")


class TestBinanceCancelOrder(unittest.TestCase):
    def setUp(self):
        self.ex = _make_exchange()

    @patch("pt_exchanges.requests.delete")
    def test_cancel_success(self, mock_del):
        mock_del.return_value.json.return_value = {"status": "CANCELED"}
        self.assertTrue(self.ex.cancel_order("BTCUSDT:12345"))

    @patch("pt_exchanges.requests.delete")
    def test_cancel_already_filled_returns_false(self, mock_del):
        mock_del.return_value.json.return_value = {
            "code": -2011,
            "msg": "Unknown order sent.",
        }
        self.assertFalse(self.ex.cancel_order("BTCUSDT:99999"))

    @patch("pt_exchanges.requests.delete")
    def test_cancel_sends_correct_endpoint(self, mock_del):
        mock_del.return_value.json.return_value = {"status": "CANCELED"}
        self.ex.cancel_order("ETHUSDT:777")
        call_url = mock_del.call_args[0][0]
        self.assertIn("/api/v3/order", call_url)
        self.assertIn("symbol=ETHUSDT", call_url)
        self.assertIn("orderId=777", call_url)

    def test_invalid_format_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.ex.cancel_order("plain_id_no_symbol")

    def test_missing_credentials_raises(self):
        ex = BinanceExchange(api_key="", api_secret="")
        with self.assertRaises(RuntimeError):
            ex.cancel_order("BTCUSDT:1")

    @patch("pt_exchanges.requests.delete")
    def test_unexpected_error_propagates(self, mock_del):
        mock_del.return_value.json.return_value = {
            "code": -1100,
            "msg": "Illegal characters found in parameter",
        }
        with self.assertRaises(RuntimeError):
            self.ex.cancel_order("BTCUSDT:123")


class TestBinanceTestnet(unittest.TestCase):
    """Testnet flag flips REST + WebSocket base URLs."""

    def test_default_is_production(self):
        ex = BinanceExchange(api_key="k", api_secret="s")
        self.assertEqual(ex.base_url, "https://api.binance.com")
        self.assertEqual(ex.ws_base, "wss://stream.binance.com:9443/ws")
        self.assertFalse(ex.testnet)

    def test_testnet_flag_switches_urls(self):
        ex = BinanceExchange(api_key="k", api_secret="s", testnet=True)
        self.assertEqual(ex.base_url, "https://testnet.binance.vision")
        self.assertEqual(ex.ws_base, "wss://stream.testnet.binance.vision/ws")
        self.assertTrue(ex.testnet)

    def test_recv_window_clamped_to_max(self):
        ex = BinanceExchange(api_key="k", api_secret="s", recv_window=99999)
        self.assertEqual(ex.recv_window, 60000)

    def test_recv_window_clamped_to_min(self):
        ex = BinanceExchange(api_key="k", api_secret="s", recv_window=0)
        self.assertEqual(ex.recv_window, 1)


class TestBinanceServerTimeSync(unittest.TestCase):
    """sync_time + _now_ms offset behaviour."""

    @patch("pt_exchanges.requests.get")
    def test_sync_time_sets_positive_offset(self, mock_get):
        mock_get.return_value.json.return_value = {
            "serverTime": int(__import__("time").time() * 1000) + 5000
        }
        ex = _make_exchange()
        ex._time_synced = False  # force a real sync
        offset = ex.sync_time()
        self.assertGreaterEqual(offset, 4000)  # ~5000 ms
        self.assertTrue(ex._time_synced)

    @patch("pt_exchanges.requests.get")
    def test_sync_time_bad_response_raises(self, mock_get):
        mock_get.return_value.json.return_value = {"unexpected": "shape"}
        ex = _make_exchange()
        ex._time_synced = False
        with self.assertRaises(RuntimeError):
            ex.sync_time()

    def test_now_ms_applies_offset(self):
        ex = _make_exchange()
        ex._time_offset_ms = 1234
        import time as _t

        actual = ex._now_ms()
        expected = int(_t.time() * 1000) + 1234
        self.assertAlmostEqual(actual, expected, delta=200)

    @patch("pt_exchanges.requests.post")
    @patch("pt_exchanges.requests.get")
    def test_minus_1021_persists_raises_timestamp_error(self, mock_get, mock_post):
        """Two consecutive -1021 responses (resync + retry both fail) → BinanceTimestampError."""
        mock_get.return_value.json.return_value = {
            "serverTime": int(__import__("time").time() * 1000)
        }
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.json.return_value = {"code": -1021, "msg": "Timestamp drift"}
        mock_post.return_value = resp
        ex = _make_exchange()
        _seed_filters(ex, "BTCUSDT")
        with self.assertRaises(BinanceTimestampError):
            ex.place_order("BTC-USD", "buy", 0.001)

    @patch("pt_exchanges.requests.post")
    @patch("pt_exchanges.requests.get")
    def test_minus_1021_triggers_resync_and_retry(self, mock_get, mock_post):
        """First POST returns -1021. After /api/v3/time resync, retry succeeds."""
        # /api/v3/time response when resync triggers
        mock_get.return_value.json.return_value = {
            "serverTime": int(__import__("time").time() * 1000)
        }
        # POST fails once then succeeds
        first = MagicMock()
        first.status_code = 200
        first.headers = {}
        first.json.return_value = {"code": -1021, "msg": "Timestamp drift"}
        second = MagicMock()
        second.status_code = 200
        second.headers = {}
        second.json.return_value = {
            "orderId": 1,
            "status": "FILLED",
            "executedQty": "0.001",
            "price": "0",
            "transactTime": 1000,
        }
        mock_post.side_effect = [first, second]

        ex = _make_exchange()
        _seed_filters(ex, "BTCUSDT")
        result = ex.place_order("BTC-USD", "buy", 0.001)
        self.assertEqual(result.status, "filled")
        # Retried exactly once
        self.assertEqual(mock_post.call_count, 2)


class TestBinanceRateLimit(unittest.TestCase):
    """HTTP 429/418 raise BinanceRateLimitError with Retry-After."""

    @patch("pt_exchanges.requests.post")
    def test_429_raises_rate_limit_error(self, mock_post):
        resp = MagicMock()
        resp.status_code = 429
        resp.headers = {"Retry-After": "12", "X-MBX-USED-WEIGHT-1M": "1200"}
        resp.json.return_value = {"code": -1003, "msg": "Too many requests"}
        mock_post.return_value = resp

        ex = _make_exchange()
        _seed_filters(ex, "BTCUSDT")
        with self.assertRaises(BinanceRateLimitError) as ctx:
            ex.place_order("BTC-USD", "buy", 0.001)
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.retry_after, 12.0)
        self.assertEqual(ex.last_rate_limit_headers.get("X-MBX-USED-WEIGHT-1M"), "1200")

    @patch("pt_exchanges.requests.post")
    def test_418_raises_rate_limit_error(self, mock_post):
        resp = MagicMock()
        resp.status_code = 418
        resp.headers = {"Retry-After": "300"}
        resp.json.return_value = {"code": -1003, "msg": "IP banned"}
        mock_post.return_value = resp
        ex = _make_exchange()
        _seed_filters(ex, "BTCUSDT")
        with self.assertRaises(BinanceRateLimitError) as ctx:
            ex.place_order("BTC-USD", "buy", 0.001)
        self.assertEqual(ctx.exception.status_code, 418)

    @patch("pt_exchanges.requests.post")
    def test_used_weight_headers_captured(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {
            "X-MBX-USED-WEIGHT-1M": "42",
            "X-MBX-ORDER-COUNT-10S": "3",
            "Content-Type": "application/json",
        }
        resp.json.return_value = {
            "orderId": 1,
            "status": "FILLED",
            "executedQty": "0.001",
            "price": "0",
            "transactTime": 1,
        }
        mock_post.return_value = resp
        ex = _make_exchange()
        _seed_filters(ex, "BTCUSDT")
        ex.place_order("BTC-USD", "buy", 0.001)
        self.assertIn("X-MBX-USED-WEIGHT-1M", ex.last_rate_limit_headers)
        self.assertIn("X-MBX-ORDER-COUNT-10S", ex.last_rate_limit_headers)
        # Non-rate-limit headers excluded
        self.assertNotIn("Content-Type", ex.last_rate_limit_headers)


class TestBinanceExtendedOrderTypes(unittest.TestCase):
    """STOP_LOSS_LIMIT, TAKE_PROFIT_LIMIT, LIMIT_MAKER, quoteOrderQty, etc."""

    def setUp(self):
        self.ex = _make_exchange()
        _seed_filters(self.ex, "BTCUSDT")

    @patch("pt_exchanges.requests.post")
    def test_stop_loss_limit_sends_stop_price(self, mock_post):
        mock_post.return_value.json.return_value = {
            "orderId": 1,
            "status": "NEW",
            "executedQty": "0",
            "price": "70000",
            "transactTime": 1,
        }
        self.ex.place_order(
            "BTC-USD",
            "sell",
            0.001,
            order_type="STOP_LOSS_LIMIT",
            price=70000.0,
            stop_price=70500.0,
            time_in_force="GTC",
        )
        url = mock_post.call_args[0][0]
        self.assertIn("type=STOP_LOSS_LIMIT", url)
        self.assertIn("stopPrice=", url)
        self.assertIn("timeInForce=GTC", url)

    @patch("pt_exchanges.requests.post")
    def test_take_profit_limit_sends_stop_and_price(self, mock_post):
        mock_post.return_value.json.return_value = {
            "orderId": 2,
            "status": "NEW",
            "executedQty": "0",
            "price": "80000",
            "transactTime": 1,
        }
        self.ex.place_order(
            "BTC-USD",
            "sell",
            0.001,
            order_type="TAKE_PROFIT_LIMIT",
            price=80000.0,
            stop_price=79500.0,
        )
        url = mock_post.call_args[0][0]
        self.assertIn("type=TAKE_PROFIT_LIMIT", url)
        self.assertIn("stopPrice=", url)

    @patch("pt_exchanges.requests.post")
    def test_limit_maker_sends_price_no_stop(self, mock_post):
        mock_post.return_value.json.return_value = {
            "orderId": 3,
            "status": "NEW",
            "executedQty": "0",
            "price": "75000",
            "transactTime": 1,
        }
        self.ex.place_order(
            "BTC-USD",
            "sell",
            0.001,
            order_type="LIMIT_MAKER",
            price=75000.0,
        )
        url = mock_post.call_args[0][0]
        self.assertIn("type=LIMIT_MAKER", url)
        self.assertNotIn("stopPrice", url)

    @patch("pt_exchanges.requests.post")
    def test_market_with_quote_order_qty(self, mock_post):
        mock_post.return_value.json.return_value = {
            "orderId": 4,
            "status": "FILLED",
            "executedQty": "0",
            "price": "0",
            "transactTime": 1,
        }
        # quoteOrderQty path: amount=0 to bypass the both-given guard
        self.ex.place_order(
            "BTC-USD",
            "buy",
            0,
            order_type="MARKET",
            quote_order_qty=100.0,
        )
        url = mock_post.call_args[0][0]
        self.assertIn("quoteOrderQty=", url)
        self.assertNotIn("quantity=", url)

    @patch("pt_exchanges.requests.post")
    def test_trailing_delta_sent_as_int(self, mock_post):
        mock_post.return_value.json.return_value = {
            "orderId": 5,
            "status": "NEW",
            "executedQty": "0",
            "price": "70000",
            "transactTime": 1,
        }
        self.ex.place_order(
            "BTC-USD",
            "sell",
            0.001,
            order_type="STOP_LOSS_LIMIT",
            price=70000.0,
            trailing_delta=500,
        )
        url = mock_post.call_args[0][0]
        self.assertIn("trailingDelta=500", url)

    @patch("pt_exchanges.requests.post")
    def test_client_order_id_forwarded(self, mock_post):
        mock_post.return_value.json.return_value = {
            "orderId": 6,
            "status": "FILLED",
            "executedQty": "0.001",
            "price": "0",
            "transactTime": 1,
        }
        self.ex.place_order(
            "BTC-USD",
            "buy",
            0.001,
            client_order_id="my-custom-id-123",
        )
        url = mock_post.call_args[0][0]
        self.assertIn("newClientOrderId=my-custom-id-123", url)

    def test_invalid_order_type_raises(self):
        with self.assertRaises(ValueError):
            self.ex.place_order("BTC-USD", "buy", 0.001, order_type="FUTURES_BRACKET")

    def test_limit_without_price_raises(self):
        with self.assertRaises(ValueError):
            self.ex.place_order("BTC-USD", "buy", 0.001, order_type="LIMIT")

    def test_stop_loss_limit_without_stop_raises(self):
        with self.assertRaises(ValueError):
            self.ex.place_order(
                "BTC-USD",
                "sell",
                0.001,
                order_type="STOP_LOSS_LIMIT",
                price=70000.0,
            )

    def test_market_with_both_qty_and_quote_raises(self):
        with self.assertRaises(ValueError):
            self.ex.place_order(
                "BTC-USD",
                "buy",
                0.001,
                order_type="MARKET",
                quote_order_qty=100.0,
            )


class TestBinanceOCO(unittest.TestCase):
    def setUp(self):
        self.ex = _make_exchange()
        _seed_filters(self.ex, "BTCUSDT")

    @patch("pt_exchanges.requests.post")
    def test_place_oco_uses_above_below_schema(self, mock_post):
        mock_post.return_value.json.return_value = {
            "orderListId": 42,
            "contingencyType": "OCO",
            "orders": [{"orderId": 1}, {"orderId": 2}],
        }
        result = self.ex.place_oco_order(
            "BTC-USD",
            "sell",
            0.001,
            above_type="STOP_LOSS_LIMIT",
            above_price=69000.0,
            above_stop_price=68500.0,
            above_time_in_force="GTC",
            below_type="LIMIT_MAKER",
            below_price=80000.0,
        )
        url = mock_post.call_args[0][0]
        self.assertIn("/api/v3/orderList/oco", url)
        self.assertIn("aboveType=STOP_LOSS_LIMIT", url)
        self.assertIn("belowType=LIMIT_MAKER", url)
        self.assertIn("abovePrice=", url)
        self.assertIn("aboveStopPrice=", url)
        self.assertIn("belowPrice=", url)
        self.assertEqual(result["orderListId"], 42)

    @patch("pt_exchanges.requests.delete")
    def test_cancel_order_list_by_id(self, mock_del):
        mock_del.return_value.json.return_value = {"orderListId": 42}
        self.ex.cancel_order_list("BTC-USD", order_list_id=42)
        url = mock_del.call_args[0][0]
        self.assertIn("/api/v3/orderList", url)
        self.assertIn("orderListId=42", url)

    def test_cancel_order_list_requires_some_id(self):
        with self.assertRaises(ValueError):
            self.ex.cancel_order_list("BTC-USD")

    def test_oco_missing_credentials_raises(self):
        ex = BinanceExchange(api_key="", api_secret="")
        with self.assertRaises(RuntimeError):
            ex.place_oco_order(
                "BTC-USD",
                "sell",
                0.001,
                above_type="STOP_LOSS_LIMIT",
                below_type="LIMIT_MAKER",
            )


class TestBinanceListenKey(unittest.TestCase):
    def setUp(self):
        self.ex = _make_exchange()

    @patch("pt_exchanges.requests.post")
    def test_create_returns_listen_key(self, mock_post):
        mock_post.return_value.content = b'{"listenKey":"abc123"}'
        mock_post.return_value.json.return_value = {"listenKey": "abc123"}
        key = self.ex.create_listen_key()
        self.assertEqual(key, "abc123")
        url = mock_post.call_args[0][0]
        self.assertIn("/api/v3/userDataStream", url)
        # X-MBX-APIKEY required, no signature for listenKey endpoints
        headers = mock_post.call_args[1]["headers"]
        self.assertEqual(headers["X-MBX-APIKEY"], "test_key")

    @patch("pt_exchanges.requests.put")
    def test_keepalive_puts_with_key_param(self, mock_put):
        mock_put.return_value.content = b"{}"
        mock_put.return_value.json.return_value = {}
        self.ex.keepalive_listen_key("xyz789")
        url = mock_put.call_args[0][0]
        self.assertIn("listenKey=xyz789", url)

    @patch("pt_exchanges.requests.delete")
    def test_close_deletes_with_key_param(self, mock_del):
        mock_del.return_value.content = b"{}"
        mock_del.return_value.json.return_value = {}
        self.ex.close_listen_key("xyz789")
        url = mock_del.call_args[0][0]
        self.assertIn("listenKey=xyz789", url)

    def test_user_data_stream_url_prod(self):
        url = self.ex.user_data_stream_url("k1")
        self.assertEqual(url, "wss://stream.binance.com:9443/ws/k1")

    def test_user_data_stream_url_testnet(self):
        ex = _make_exchange(testnet=True)
        url = ex.user_data_stream_url("k2")
        self.assertEqual(url, "wss://stream.testnet.binance.vision/ws/k2")

    def test_create_without_key_raises(self):
        ex = BinanceExchange(api_key="", api_secret="")
        with self.assertRaises(RuntimeError):
            ex.create_listen_key()


class TestBinanceBrokerSelectorHelpers(unittest.TestCase):
    """Hooks consumed by the broker-selector UI in #96."""

    def test_masked_api_key_shows_last_four(self):
        ex = BinanceExchange(api_key="abcdefghij1234", api_secret="x")
        self.assertEqual(ex.get_masked_api_key(), "****1234")

    def test_masked_api_key_short_key(self):
        ex = BinanceExchange(api_key="ab", api_secret="x")
        self.assertEqual(ex.get_masked_api_key(), "****ab")

    def test_masked_api_key_empty(self):
        ex = BinanceExchange(api_key="", api_secret="")
        self.assertEqual(ex.get_masked_api_key(), "Not configured")

    def test_test_connection_no_creds_returns_false(self):
        ex = BinanceExchange(api_key="", api_secret="")
        self.assertFalse(ex.test_connection())

    @patch("pt_exchanges.requests.get")
    def test_test_connection_success(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.json.return_value = {"balances": [], "canTrade": True}
        mock_get.return_value = resp
        ex = _make_exchange()
        self.assertTrue(ex.test_connection())

    @patch("pt_exchanges.requests.get")
    def test_test_connection_swallows_errors(self, mock_get):
        mock_get.side_effect = Exception("network down")
        ex = _make_exchange()
        self.assertFalse(ex.test_connection())


if __name__ == "__main__":
    unittest.main()
