"""
Tests for PaperTradingAccount wired into pt_integration.py - issue #86.
Verifies account lifecycle, order placement, and account summary.
"""

import asyncio
import os
import tempfile
import unittest
from decimal import Decimal

from pt_paper_trading import (
    MarketDataSimulator,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperTradingAccount,
)


class TestPaperTradingIntegration(unittest.TestCase):
    """Tests confirming PaperTradingAccount works as integration layer expects."""

    def setUp(self):
        self.account = PaperTradingAccount(initial_balance=Decimal("10000"))

    def test_account_initialises_with_balance(self):
        self.assertEqual(float(self.account.cash_balance), 10000.0)

    def test_market_buy_fills(self):
        order_id = self.account.place_order(
            symbol="BTC",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
        )
        status = self.account.get_order_status(order_id)
        self.assertEqual(status, OrderStatus.FILLED)

    def test_market_buy_reduces_cash(self):
        self.account.place_order(
            symbol="BTC",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
        )
        self.assertLess(float(self.account.cash_balance), 10000.0)

    def test_buy_creates_position(self):
        self.account.place_order(
            symbol="BTC",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
        )
        position = self.account.get_position("BTC")
        self.assertIsNotNone(position)
        self.assertEqual(float(position.quantity), 0.001)

    def test_account_summary_structure(self):
        summary = self.account.get_account_summary()
        required = [
            "account_id",
            "cash_balance",
            "positions_value",
            "total_value",
            "unrealized_pnl",
            "realized_pnl",
            "total_pnl",
            "total_trades",
            "win_rate_pct",
            "positions",
        ]
        for key in required:
            self.assertIn(key, summary)

    def test_sell_after_buy(self):
        self.account.place_order(
            symbol="ETH",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            quantity=Decimal("0.01"),
        )
        sell_id = self.account.place_order(
            symbol="ETH",
            order_type=OrderType.MARKET,
            side=OrderSide.SELL,
            quantity=Decimal("0.01"),
        )
        status = self.account.get_order_status(sell_id)
        self.assertEqual(status, OrderStatus.FILLED)
        self.assertIsNone(self.account.get_position("ETH"))

    def test_cancel_pending_limit_order(self):
        price = MarketDataSimulator().get_current_price("BTC") * Decimal("0.5")
        order_id = self.account.place_order(
            symbol="BTC",
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),
            price=price,
        )
        cancelled = self.account.cancel_order(order_id)
        self.assertTrue(cancelled)
        self.assertEqual(self.account.get_order_status(order_id), OrderStatus.CANCELLED)

    def test_oversized_order_rejected(self):
        """Order exceeding risk limits (>10% of $10k portfolio) should be rejected.

        Quantity is derived from the live simulator price so this test remains
        valid regardless of what price MarketDataSimulator returns.  We request
        5× the entire portfolio value worth of BTC — always above any reasonable
        risk limit.
        """
        btc_price = MarketDataSimulator().get_current_price("BTC")
        # 5x portfolio value in BTC, pure Decimal — no float round-trip
        excessive_qty = (Decimal("50000") / btc_price).quantize(Decimal("0.0001"))
        order_id = self.account.place_order(
            symbol="BTC",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            quantity=excessive_qty,
        )
        self.assertEqual(self.account.get_order_status(order_id), OrderStatus.REJECTED)

    def test_integration_method_produces_pass_results(self):
        """Verify _test_trading_simulation produces PASS results, not SKIP.

        Uses a TemporaryDirectory for config_path so the test is hermetic and
        creates no files in the working tree.
        """
        try:
            from pt_integration import LiveIntegrationTester
        except ImportError:
            self.skipTest("LiveIntegrationTester not importable in this environment")

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "integration_test.json")
            tester = LiveIntegrationTester(config_path=config_path)
            asyncio.run(tester._test_trading_simulation())
            statuses = [r.status for r in tester.test_results]
            self.assertNotIn("SKIP", statuses)
            self.assertIn("PASS", statuses)


if __name__ == "__main__":
    unittest.main()
