"""
Tests for pt_paper_mode helpers.

These tests intentionally avoid spinning up a Tk root - the helpers exposed by
pt_paper_mode that touch Tk are exercised separately via test_paper_mode_gui
(opt-in) so the CI box without a display still passes.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from decimal import Decimal
from unittest import mock

from pt_paper_mode import (
    DARK_PALETTE,
    PAPER_MODE_SETTING_KEY,
    PAPER_PALETTE,
    fetch_binance_btc_price,
    get_palette,
    is_paper_mode,
    read_paper_mode_from_disk,
    run_sample_scenario,
    settings_path_for,
)
from pt_paper_trading import PaperTradingAccount


class TestPalette(unittest.TestCase):
    """Palette pairs must mirror each other key-for-key."""

    def test_dark_palette_keys_match_paper_palette(self):
        self.assertEqual(set(DARK_PALETTE.keys()), set(PAPER_PALETTE.keys()))

    def test_get_palette_paper_is_blue(self):
        # BG hex starts with 0A1B = blueish; basic sanity check that we did not
        # accidentally swap the constants.
        self.assertTrue(get_palette(True)["BG"].lower().startswith("#0a1b"))
        self.assertTrue(get_palette(False)["BG"].lower().startswith("#070b"))


class TestSettingsPersistence(unittest.TestCase):
    def test_read_paper_mode_from_missing_file_is_false(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(read_paper_mode_from_disk(os.path.join(d, "x.json")))

    def test_read_paper_mode_from_disk_true(self):
        with tempfile.TemporaryDirectory() as d:
            path = settings_path_for(d, "gui_settings.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({PAPER_MODE_SETTING_KEY: True}, f)
            self.assertTrue(read_paper_mode_from_disk(path))

    def test_read_paper_mode_from_disk_garbage_is_false(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{not json")
            self.assertFalse(read_paper_mode_from_disk(path))

    def test_is_paper_mode_helper(self):
        self.assertFalse(is_paper_mode(None))
        self.assertFalse(is_paper_mode({}))
        self.assertFalse(is_paper_mode({PAPER_MODE_SETTING_KEY: False}))
        self.assertTrue(is_paper_mode({PAPER_MODE_SETTING_KEY: True}))


class TestBinanceTickerFetch(unittest.TestCase):
    def test_fetch_returns_decimal_on_success(self):
        def fake_opener(url, timeout):
            return json.dumps({"symbol": "BTCUSDT", "price": "76460.58"})

        price = fetch_binance_btc_price(opener=fake_opener)
        self.assertIsNotNone(price)
        self.assertEqual(price, Decimal("76460.58"))

    def test_fetch_returns_none_on_missing_price_key(self):
        def fake_opener(url, timeout):
            return json.dumps({"symbol": "BTCUSDT"})

        self.assertIsNone(fetch_binance_btc_price(opener=fake_opener))

    def test_fetch_returns_none_on_url_error(self):
        def fake_opener(url, timeout):
            raise OSError("network down")

        self.assertIsNone(fetch_binance_btc_price(opener=fake_opener))


class TestSampleScenario(unittest.TestCase):
    def test_buy_then_sell_with_live_price(self):
        account = PaperTradingAccount(initial_balance=Decimal("10000"))
        result = run_sample_scenario(
            account,
            quantity=Decimal("0.001"),
            price_fetcher=lambda: Decimal("76000"),
        )
        self.assertEqual(result["source"], "binance_public")
        self.assertEqual(result["buy_status"], "filled")
        self.assertEqual(result["sell_status"], "filled")
        # Buy fill happens at the seeded price; sell fill after the simulator's
        # ±0.5% drift. Both should be in the ballpark of the live price.
        self.assertAlmostEqual(result["buy_price"], 76000.0, delta=500.0)
        self.assertAlmostEqual(result["sell_price"], 76000.0, delta=500.0)

    def test_falls_back_when_fetch_returns_none(self):
        account = PaperTradingAccount(initial_balance=Decimal("10000"))
        result = run_sample_scenario(
            account,
            quantity=Decimal("0.001"),
            price_fetcher=lambda: None,
        )
        self.assertEqual(result["source"], "simulated")
        self.assertIsNone(result["live_price"])
        self.assertEqual(result["buy_status"], "filled")
        self.assertEqual(result["sell_status"], "filled")

    def test_account_balance_round_trip_close_to_start(self):
        # Buy then immediate sell with tiny drift + commission should leave
        # the account within commission * 2 of starting balance.
        account = PaperTradingAccount(initial_balance=Decimal("10000"))
        result = run_sample_scenario(
            account,
            quantity=Decimal("0.001"),
            price_fetcher=lambda: Decimal("76000"),
        )
        delta = abs(result["final_balance"] - result["starting_balance"])
        # 0.001 BTC at $76k = $76 notional. 0.1% commission each side = $0.152.
        # Combined drift (±0.5% sim) on the sell leg: up to ~$0.38. Allow $5.
        self.assertLess(delta, 5.0)


class TestUrllibIntegration(unittest.TestCase):
    """Sanity check the default opener path actually calls urllib."""

    def test_default_opener_uses_urlopen(self):
        fake_payload = json.dumps({"symbol": "BTCUSDT", "price": "100.00"}).encode()

        class FakeResp:
            def read(self):
                return fake_payload

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with mock.patch(
            "pt_paper_mode.urllib.request.urlopen", return_value=FakeResp()
        ) as patched:
            price = fetch_binance_btc_price()
            self.assertTrue(patched.called)
            self.assertEqual(price, Decimal("100.00"))


if __name__ == "__main__":
    unittest.main()
