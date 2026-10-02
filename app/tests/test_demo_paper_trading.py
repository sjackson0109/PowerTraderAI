"""FDS-087: the paper-trading demo goes through the real gate; Binance is mocked."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

import requests
from helpers import FakeBinance

import demo_paper_trading as demo
import trading_mode as tm

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class DemoTests(unittest.TestCase):
    def setUp(self):
        tm.reset_paper_exchange()
        tm._quote_cache.clear()
        self.addCleanup(tm.reset_paper_exchange)
        self.addCleanup(tm._quote_cache.clear)
        self.binance = FakeBinance()
        self.lines = []
        patcher = mock.patch.object(tm.urllib.request, "urlopen", self.binance)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_demo(self, **kwargs):
        code = demo.run_demo(out=self.lines.append, **kwargs)
        return code, "\n".join(self.lines)

    # 1. happy path
    def test_happy_path_exits_zero_and_reports_operational_with_live_source(self):
        code, output = self.run_demo()
        self.assertEqual(code, 0, output)
        self.assertIn("Paper trading system: OPERATIONAL", output)
        self.assertIn("source=live", output)
        self.assertIn("Order target     : PAPER (via trading-mode gate)", output)
        self.assertIn("Starting balance : $10,000.00", output)
        self.assertIn("BUY  0.01 BTC @ $101.00  -> filled", output)
        self.assertIn("SELL 0.01 BTC @ $99.00  -> filled", output)
        self.assertIn("Unrealized PnL", output)
        self.assertIn("Realized PnL", output)
        self.assertIn("Final balance", output)

    def test_realized_pnl_includes_fees(self):
        code, output = self.run_demo()
        self.assertEqual(code, 0)
        # buy at ask 101, sell at bid 99, 0.01 BTC, 0.1% commission each way
        gross = (99.0 - 101.0) * 0.01
        fees = (101.0 + 99.0) * 0.01 * 0.001
        net = gross - fees
        self.assertIn(
            f"Realized PnL     : {'-' if net < 0 else ''}${abs(net):,.2f}", output
        )
        self.assertIn(f"(fees ${fees:,.2f})", output)
        self.assertNotIn("$-", output)  # negatives render as -$x.xx

    # 2. network failure: degraded, never simulated
    def test_network_failure_exits_two_and_is_degraded_without_simulating(self):
        self.binance.reachable = False
        code, output = self.run_demo()
        self.assertEqual(code, 2)
        self.assertIn("DEGRADED", output)
        self.assertIn("Paper trading system: DEGRADED (no live price)", output)
        self.assertNotIn("OPERATIONAL", output)
        self.assertNotIn("BUY", output)

    def test_stale_price_is_degraded_too(self):
        self.binance.age_s = 300.0
        code, output = self.run_demo()
        self.assertEqual(code, 2)
        self.assertIn("DEGRADED", output)

    def test_degraded_even_if_settings_would_allow_simulation(self):
        # the demo's own policy is pause; it must not be loosened by accident
        self.binance.reachable = False
        code, output = self.run_demo(
            settings={
                "trading": {"mode": "paper"},
                "paper": {"price_fallback_policy": "simulate_and_flag"},
            }
        )
        # the demo checks the live feed itself before ordering
        self.assertEqual(code, 2)

    # gate failure
    def test_a_gate_that_does_not_return_paper_is_a_failure(self):
        live = tm.OrderTarget(
            mode=tm.TradingMode.LIVE, broker="kraken", exchange=mock.MagicMock(), key="live:kraken"
        )
        with mock.patch.object(demo.tm, "resolve_order_target", return_value=live):
            code, output = self.run_demo()
        self.assertEqual(code, 1)
        self.assertIn("FAILED: gate did not return paper", output)
        live.exchange.place_order.assert_not_called()

    def test_demo_uses_the_gate(self):
        with mock.patch.object(
            demo.tm, "resolve_order_target", wraps=tm.resolve_order_target
        ) as gate:
            self.run_demo()
        gate.assert_called_once()

    # 3. never touches the user's config or ledger
    def test_never_reads_or_writes_the_users_config_or_ledger(self):
        config = os.path.join(APP_DIR, "pt_config.json")
        hub_data = os.path.join(APP_DIR, "hub_data")
        config_before = os.path.getmtime(config) if os.path.exists(config) else None
        hub_before = set(os.listdir(hub_data)) if os.path.isdir(hub_data) else None

        with mock.patch.object(
            tm, "_read_settings_file", side_effect=AssertionError("read settings file")
        ), mock.patch(
            "pt_settings_manager.SettingsManager.save_settings",
            side_effect=AssertionError("wrote settings"),
        ), tempfile.TemporaryDirectory() as workdir:
            code, output = self.run_demo(workdir=workdir)
            self.assertEqual(code, 0, output)
            self.assertTrue(os.path.exists(os.path.join(workdir, "paper_account.json")))

        self.assertEqual(os.path.exists(config), config_before is not None)
        if config_before is not None:
            self.assertEqual(os.path.getmtime(config), config_before)
        hub_after = set(os.listdir(hub_data)) if os.path.isdir(hub_data) else None
        self.assertEqual(hub_after, hub_before)

    def test_default_run_cleans_up_its_temp_ledger(self):
        made = []
        real = tempfile.TemporaryDirectory

        def tracking(*a, **k):
            d = real(*a, **k)
            made.append(d.name)
            return d

        with mock.patch.object(demo.tempfile, "TemporaryDirectory", tracking):
            self.assertEqual(self.run_demo()[0], 0)
        self.assertEqual(len(made), 1)
        self.assertFalse(os.path.exists(made[0]))

    # 4. only the public ticker is ever called
    def test_only_the_public_ticker_endpoint_is_called(self):
        with mock.patch.object(
            requests.Session, "request", side_effect=AssertionError("requests used")
        ) as session, mock.patch.object(
            requests, "get", side_effect=AssertionError("requests used")
        ) as get, mock.patch.object(
            requests, "post", side_effect=AssertionError("requests used")
        ) as post:
            code, output = self.run_demo()
        self.assertEqual(code, 0, output)
        self.assertEqual(session.call_count + get.call_count + post.call_count, 0)
        self.assertTrue(self.binance.urls)
        for url in self.binance.urls:
            self.assertTrue(
                url.startswith("https://api.binance.com/api/v3/ticker/bookTicker?symbol=BTCUSDT"),
                url,
            )

    def test_main_returns_one_on_unexpected_errors(self):
        with mock.patch.object(demo, "run_demo", side_effect=RuntimeError("boom")):
            self.assertEqual(demo.main(), 1)


if __name__ == "__main__":
    unittest.main()
