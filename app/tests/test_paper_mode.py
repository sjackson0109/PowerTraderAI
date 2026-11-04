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

import pt_paper_mode
import trading_mode as tm
import ui_tokens
from pt_paper_mode import (
    LivePrice,
    fetch_live_price,
    is_paper_mode,
    read_paper_mode_from_disk,
    run_sample_scenario,
    settings_path_for,
)
from pt_paper_trading import PaperTradingAccount


class TestPalette(unittest.TestCase):
    """Palette pairs must mirror each other key-for-key."""

    def test_dark_palette_keys_match_paper_palette(self):
        self.assertEqual(set(ui_tokens.DARK), set(ui_tokens.PAPER))

    def test_get_palette_paper_is_blue(self):
        # BG hex starts with 0A1B = blueish; basic sanity check that we did not
        # accidentally swap the constants.
        self.assertTrue(ui_tokens.palette(True)["BG"].lower().startswith("#0a1b"))
        self.assertTrue(ui_tokens.palette(False)["BG"].lower().startswith("#070b"))


class TestSettingsPersistence(unittest.TestCase):
    """Paper mode now derives from `trading.mode` (paper unless explicitly live)."""

    def _write(self, directory, data):
        path = settings_path_for(directory, "pt_config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def test_read_paper_mode_from_missing_file_is_paper(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(read_paper_mode_from_disk(os.path.join(d, "x.json")))

    def test_read_paper_mode_from_disk_paper(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, {"trading": {"mode": "paper"}})
            self.assertTrue(read_paper_mode_from_disk(path))

    def test_read_paper_mode_from_disk_live_is_not_paper(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(
                d, {"trading": {"mode": "live", "active_broker": "kraken"}}
            )
            self.assertFalse(read_paper_mode_from_disk(path))

    def test_read_paper_mode_from_disk_garbage_is_paper(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{not json")
            self.assertTrue(read_paper_mode_from_disk(path))

    def test_legacy_paper_mode_enabled_flag_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, {"paper_mode_enabled": False})
            self.assertTrue(read_paper_mode_from_disk(path))

    def test_is_paper_mode_helper(self):
        self.assertTrue(is_paper_mode({}))
        self.assertTrue(is_paper_mode({"trading": {"mode": "paper"}}))
        self.assertTrue(is_paper_mode({"trading": {"mode": "bogus"}}))
        self.assertFalse(
            is_paper_mode({"trading": {"mode": "live", "active_broker": "kraken"}})
        )


class TestLivePriceFetch(unittest.TestCase):
    """The sample's live price comes from the exchanges in Settings, primary first
    (trading_mode.fetch_public_quote), never from one exchange of its own."""

    def quote(self, bid, ask, exchange="coinbase"):
        return tm.Quote(bid, ask, 1.0, 1.0, exchange=exchange, pair="BTC-USD")

    def test_the_mid_price_and_the_exchange_that_gave_it(self):
        with mock.patch.object(
            pt_paper_mode, "fetch_public_quote", return_value=self.quote(99, 101)
        ) as fetch:
            price = fetch_live_price()
        fetch.assert_called_once_with("BTC")
        self.assertEqual(price, LivePrice(Decimal("100.0"), "coinbase"))

    def test_no_quote_is_no_price(self):
        with mock.patch.object(pt_paper_mode, "fetch_public_quote", return_value=None):
            self.assertIsNone(fetch_live_price())


class TestSampleScenario(unittest.TestCase):
    def test_buy_then_sell_with_live_price(self):
        account = PaperTradingAccount(initial_balance=Decimal("10000"))
        seed = Decimal("76000")
        result = run_sample_scenario(
            account,
            quantity=Decimal("0.001"),
            price_fetcher=lambda: LivePrice(seed, "kraken"),
        )
        self.assertEqual((result["source"], result["exchange"]), ("live", "kraken"))
        self.assertEqual(result["buy_status"], "filled")
        self.assertEqual(result["sell_status"], "filled")
        # The PaperTradingAccount calls MarketDataSimulator.get_current_price
        # multiple times per order (risk check + cost estimate + execution),
        # and each call drifts the simulator by up to +-0.5%. Across both the
        # buy and the sell paths that compounds to about +-3% from the seed,
        # so allow 5% headroom here - the assertion is "near the live price",
        # not exact.
        self.assertAlmostEqual(result["buy_price"], 76000.0, delta=float(seed) * 0.05)
        self.assertAlmostEqual(result["sell_price"], 76000.0, delta=float(seed) * 0.05)

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
        # Buy then immediate sell at a live-seeded price should leave the
        # account close to its starting balance. The exact delta is dominated
        # by simulator drift (per-call +-0.5%, called multiple times per
        # order) plus 0.1% commission on each side. On 0.001 BTC at $76k that
        # is roughly $0.15 in commission + a few dollars of drift noise, so
        # allow $20 of headroom to keep the test non-flaky on CI.
        account = PaperTradingAccount(initial_balance=Decimal("10000"))
        result = run_sample_scenario(
            account,
            quantity=Decimal("0.001"),
            price_fetcher=lambda: Decimal("76000"),
        )
        delta = abs(result["final_balance"] - result["starting_balance"])
        self.assertLess(delta, 20.0)


class TestDefaultFetcher(unittest.TestCase):
    """Without a price_fetcher, the sample asks the exchange layer."""

    def test_default_fetcher_is_the_exchanges_in_settings(self):
        account = PaperTradingAccount(initial_balance=Decimal("10000"))
        with mock.patch.object(
            pt_paper_mode,
            "fetch_live_price",
            return_value=LivePrice(Decimal("76000"), "coinbase"),
        ) as fetch:
            result = run_sample_scenario(account, quantity=Decimal("0.001"))
        fetch.assert_called_once_with("BTC")
        self.assertEqual((result["source"], result["exchange"]), ("live", "coinbase"))


if __name__ == "__main__":
    unittest.main()
