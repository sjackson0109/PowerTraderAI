"""The drawdown stop's own measure (N11 part 1, docs/dev/ptai-rd-001/
N11-halt-equity-design.md; the owner's decisions H3 to H6 and H9 of 2026-11-13).

The stop measures every balance, funds on hold included, with USD, ZUSD, USDT, USDC
and BUSD at $1 and every other asset at its bid (the owner's own coins still count).
Entries are still sized on the account value, unchanged. A peak saved by an earlier
version (measured on the account value) is scaled once, on the first pass, by the
new measure over the old, so a drawdown in progress is kept; the scaling is recorded.
A Paper Account save still clears the paper peak.

The starting point (design section 5): a $10,000 peak, USD $6,000 and 0.04 BTC at a
$100,000 bid ($4,000), the 8% emergency stop. No network: a fake live account behind
the trader's order target, synthetic balances, holds and bids."""

from __future__ import annotations

import json
import os
from unittest import mock

from test_halt_unpriced_holdings import FakeAccount, LiveAccountCase

import risk_state


class FakeAccountWithHolds(FakeAccount):
    """A live account whose connector also reports funds on hold."""

    def __init__(self, balances, bids, holds=None):
        super().__init__(balances, bids)
        self.holds = dict(holds or {})

    def get_balance_with_holds(self):
        if self.down:
            raise ConnectionError("the exchange did not answer")
        out = dict(self.get_balance())
        for asset, qty in self.holds.items():
            out[asset] = out.get(asset, 0.0) + qty
        return {asset: qty for asset, qty in out.items() if qty > 0}


class HaltEquityCase(LiveAccountCase):
    def setUp(self):
        super().setUp()
        self.account = FakeAccountWithHolds(
            {"USD": 6000.0, "BTC": 0.04}, {"BTC": 100000.0}
        )

    def status_account(self, trader):
        with open(trader.trader_status_path, encoding="utf-8") as f:
            return json.load(f)["account"]


class MeasureTests(HaltEquityCase):
    def test_t5_usd_moved_into_usdc_does_not_move_the_drawdown(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.balances.update(USD=5100.0, USDC=900.0)
        self.one_pass(trader)
        self.run_check(trader)
        self.assertFalse(trader.risk_manager.is_trading_halted())
        self.assertEqual(trader._get_halt_value(), 10000.0)

    def test_t7_funds_on_hold_for_a_resting_order_still_count(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.balances["USD"] = 5100.0  # $900 on hold for a resting order
        self.account.holds["USD"] = 900.0
        self.one_pass(trader)
        self.run_check(trader)
        self.assertFalse(trader.risk_manager.is_trading_halted())
        self.assertEqual(trader._get_halt_value(), 10000.0)

    def test_t2_a_fall_in_price_still_halts(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.bids["BTC"] = 77500.0  # BTC falls 22.5%: the account 9%
        said = self.one_pass(trader) + self.run_check(trader)
        self.assertTrue(trader.risk_manager.is_trading_halted())
        self.assertIn("EMERGENCY STOP: Account drawdown 9.0%", said)

    def test_the_owners_own_coins_still_count(self):
        self.account.balances["ETH"] = 1.0  # not a coin the trader trades
        self.account.bids["ETH"] = 2000.0
        trader = self.live_trader(peak=12000.0)
        self.one_pass(trader)
        self.assertEqual(trader._get_halt_value(), 12000.0)
        self.account.bids["ETH"] = 800.0  # its fall is a loss like any other
        self.one_pass(trader)
        self.assertEqual(trader._get_halt_value(), 10800.0)

    def test_t11_entries_are_still_sized_on_the_account_value(self):
        self.account.balances["USDC"] = 2000.0
        trader = self.live_trader(peak=None)
        self.one_pass(trader)
        account = self.status_account(trader)
        self.assertEqual(account["total_account_value"], 10000.0)
        self.assertEqual(trader._get_account_value(), 10000.0)
        self.assertEqual(account["halt_equity"], 12000.0)
        self.assertEqual(trader._get_halt_value(), 12000.0)
        self.run_check(trader)
        self.assertEqual(trader.risk_manager.peak_value, 12000.0)  # the stop's peak

    def test_the_peak_before_an_order_is_raised_on_the_stops_measure(self):
        self.account.balances["USDC"] = 2000.0
        trader = self.live_trader(peak=None)
        self.one_pass(trader)
        with mock.patch("builtins.print"):
            self.assertTrue(trader._risk_check("BTC-USD", "buy", 0.0001, 100000.0))
        self.assertEqual(trader.risk_manager.peak_value, 12000.0)

    def test_a_connector_without_holds_is_measured_on_its_balances(self):
        self.account = FakeAccount(
            {"USD": 5100.0, "USDC": 900.0, "BTC": 0.04}, {"BTC": 100000.0}
        )
        trader = self.live_trader()
        self.one_pass(trader)
        self.assertEqual(trader._get_halt_value(), 10000.0)

    def test_holds_that_cannot_be_read_form_no_value(self):
        trader = self.live_trader()
        self.one_pass(trader)
        with mock.patch.object(
            self.account, "get_balance_with_holds", side_effect=ConnectionError("x")
        ):
            self.account.balances["USD"] = 1000.0
            self.one_pass(trader)
        self.assertEqual(trader._get_halt_value(), 10000.0)  # the last complete one


class MigrationTests(HaltEquityCase):
    def saved_peak(self, state):
        books = os.path.join(self.tmp.name, "paper")
        os.makedirs(books, exist_ok=True)
        risk_state.write_state(books, state)
        return books

    def test_t9_the_saved_peak_is_scaled_once_so_the_drawdown_is_kept(self):
        books = self.saved_peak({"peak_value": 10000.0, "peak_ts": 5.0})
        self.account.balances.update(USD=5300.0, USDC=2000.0)  # old measure 9,300
        trader = self.live_trader(peak=None)
        with mock.patch("builtins.print") as said:
            trader.manage_trades()
        self.assertAlmostEqual(trader.risk_manager.peak_value, 12150.54, places=2)
        self.assertEqual(trader._get_halt_value(), 11300.0)
        drawdown = 1 - 11300.0 / trader.risk_manager.peak_value
        self.assertAlmostEqual(drawdown, 0.07, places=6)
        saved = risk_state.read_state(books)
        self.assertEqual(saved["peak_measure"], "all_balances")
        self.assertEqual(saved["peak_scaled"]["from"], 10000.0)
        self.assertAlmostEqual(saved["peak_scaled"]["to"], 12150.54, places=2)
        self.assertIn(
            "Peak account value scaled from $10,000.00 to $12,150.54",
            str(said.call_args_list),
        )
        # not repeated: on the next pass, nor after a restart
        self.one_pass(trader)
        restarted = self.live_trader(peak=None)
        self.one_pass(restarted)
        self.assertAlmostEqual(restarted.risk_manager.peak_value, 12150.54, places=2)
        view = risk_state.current(books)
        self.assertAlmostEqual(view.peak_scaled[1], 12150.54, places=2)

    def test_t14_no_saved_peak_needs_no_scaling(self):
        books = self.saved_peak({})
        trader = self.live_trader(peak=None)
        self.one_pass(trader)
        self.run_check(trader)  # the first value is the peak
        saved = risk_state.read_state(books)
        self.assertEqual(saved["peak_measure"], "all_balances")
        self.assertNotIn("peak_scaled", saved)
        self.assertEqual(saved["peak_value"], 10000.0)

    def test_a_reset_after_the_scaling_hides_its_note(self):
        books = self.saved_peak({"peak_value": 10000.0})
        self.account.balances.update(USD=5300.0, USDC=2000.0)
        trader = self.live_trader(peak=None)
        self.one_pass(trader)
        self.assertIsNotNone(risk_state.current(books).peak_scaled)
        risk_state.request_peak_reset(books, 11300.0)
        self.assertIsNone(risk_state.current(books).peak_scaled)


class PaperTests(HaltEquityCase):
    def paper_trader(self):
        return self.trader()  # the paper account: no holds, no stablecoins

    def test_t10_paper_measures_its_book_and_a_paper_account_save_clears_the_peak(
        self,
    ):
        trader = self.paper_trader()
        self.one_pass(trader)
        value = trader._get_account_value()
        self.assertGreater(value, 0.0)
        self.assertEqual(trader._get_halt_value(), value)  # no holds, no stablecoins
        self.run_check(trader)
        self.assertEqual(trader.risk_manager.peak_value, value)
        books = trader.data_dir
        self.assertEqual(risk_state.read_state(books)["peak_measure"], "all_balances")
        risk_state.request_peak_reset(books, None)  # what a Paper Account save asks
        self.assertEqual(risk_state.current(books).peak_value, 0.0)
        restarted = self.paper_trader()
        self.assertEqual(restarted.risk_manager.peak_value, 0.0)
        self.one_pass(restarted)
        self.run_check(restarted)
        self.assertEqual(restarted.risk_manager.peak_value, value)  # the book's first

    def test_a_paper_peak_is_kept_as_it_was(self):
        books = os.path.join(self.tmp.name, "paper")
        os.makedirs(books, exist_ok=True)
        risk_state.write_state(books, {"peak_value": 1_000_000.0, "peak_ts": 5.0})
        trader = self.paper_trader()
        self.one_pass(trader)
        saved = risk_state.read_state(books)
        self.assertEqual(saved["peak_measure"], "all_balances")
        self.assertNotIn("peak_scaled", saved)  # the same measure in paper
        self.assertEqual(saved["peak_value"], 1_000_000.0)
