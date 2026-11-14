"""A deposit never reduces the drawdown (N11 part 2, docs/dev/ptai-rd-001/
N11-halt-equity-design.md; the owner's decision H7 of 2026-11-13).

Each pass the stop's balances (every balance, funds on hold included, the cash
assets together) are compared with the last ones it settled on, after the fills
recorded since (the trader's own and Order Management's). A change no recorded fill
explains waits ``BALANCE_CHANGE_SETTLE_SECONDS`` (60 s, fixed) until the balances
have been still that long, so both legs of a trade land in one change; meanwhile
buys wait, the stop is checked without the change, and exits run. Then:

* a net rise, valued at the bids, is a deposit: the peak is scaled up with the
  account, so the drawdown is what it was (this is only ever stricter);
* a net fall is a loss, as before: a withdrawal can still trigger the halt (part 3,
  which would treat it as a withdrawal, is not built).

The last balances are kept in ``risk_state.json``, so a deposit made while the trader
was stopped is found at its next start; Reset peak and a Paper Account save clear
them. The starting point (design section 5): a $10,000 peak, USD $6,000 and 0.04 BTC
at a $100,000 bid, the 8% emergency stop. No network: a fake live account behind the
trader's order target."""

from __future__ import annotations

import copy
import json
import os
import time
from unittest import mock

from helpers_coinbase import recorded_http
from test_coinbase_live_trader import REAL, FakeCoinbase
from test_coinbase_paper_gate import CoinbaseGateBase
from test_halt_equity import FakeAccountWithHolds
from test_halt_unpriced_holdings import LiveAccountCase

import risk_state


class DepositCase(LiveAccountCase):
    def setUp(self):
        super().setUp()
        self.account = FakeAccountWithHolds(
            {"USD": 6000.0, "BTC": 0.04}, {"BTC": 100000.0}
        )

    def settle(self, trader, seconds=61):
        """The change waiting to settle was first seen ``seconds`` ago."""
        change = getattr(trader, "_balance_change", None)
        if change:
            change["since"] -= seconds

    def changes(self, trader):
        return risk_state.current(trader.data_dir).balance_changes

    def buys_wait(self, trader) -> bool:
        with mock.patch("builtins.print"):
            return not trader._risk_check("BTC-USD", "buy", 0.0001, 100000.0)

    def history_row(self, trader, **row):
        with open(trader.trade_history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict({"ts": time.time()}, **row)) + "\n")


class DepositTests(DepositCase):
    def test_t3_a_deposit_keeps_the_drawdown_and_a_further_111_fall_halts(self):
        self.account.bids["BTC"] = 82500.0  # $9,300: a 7.0% drawdown
        trader = self.live_trader()
        self.one_pass(trader)
        self.run_check(trader)
        self.account.balances["USD"] = 7000.0  # $1,000 deposited
        self.one_pass(trader)
        waited = self.buys_wait(trader)  # it settles first
        held_out = trader._get_halt_value()  # checked without it
        self.run_check(trader)
        self.settle(trader)
        self.one_pass(trader)
        self.run_check(trader)
        self.assertAlmostEqual(trader.risk_manager.peak_value, 11075.27, places=2)
        self.assertTrue(waited)
        self.assertEqual(held_out, 9300.0)
        self.assertFalse(trader.risk_manager.is_trading_halted())
        self.assertFalse(self.buys_wait(trader))
        (change,) = self.changes(trader)
        self.assertEqual(change.kind, "deposit")
        self.assertAlmostEqual(change.value, 1000.0)
        self.assertEqual(change.assets, (("USD", 1000.0),))
        self.assertAlmostEqual(change.peak_to, 11075.27, places=2)
        # BTC's value falls by $111: 8.0% below the scaled peak
        self.account.bids["BTC"] = (3300.0 - 111.0) / 0.04
        said = self.one_pass(trader) + self.run_check(trader)
        self.assertTrue(trader.risk_manager.is_trading_halted())
        self.assertIn("EMERGENCY STOP: Account drawdown 8.0%", said)

    def test_t8_a_deposit_made_while_the_trader_was_stopped_is_found_at_its_start(
        self,
    ):
        self.account.bids["BTC"] = 82500.0
        first = self.live_trader()
        self.one_pass(first)  # its balances are kept
        self.account.balances["USD"] = 7000.0  # deposited while it is stopped
        restarted = self.live_trader(peak=None)
        said = self.one_pass(restarted) + self.run_check(restarted)
        self.assertIn("Account drawdown 7.0% (critical level)", said)
        self.assertEqual(restarted.risk_manager.peak_value, 10000.0)
        self.settle(restarted)
        self.one_pass(restarted)
        self.run_check(restarted)
        self.assertAlmostEqual(restarted.risk_manager.peak_value, 11075.27, places=2)

    def test_an_asset_that_starts_being_counted_does_not_cut_the_drawdown(self):
        self.account.balances["GBP"] = 1250.0  # no GBP-USD price yet
        self.account.bids["BTC"] = 82500.0  # $9,300 counted: 7.0%
        trader = self.live_trader()
        self.one_pass(trader)  # GBP holds the value back at first
        self.unpriced_for(trader, "GBP-USD", 11 * 60)
        self.one_pass(trader)  # then it is left out: the value is $9,300
        self.account.bids["GBP"] = 1.28  # GBP is priced: $1,600 more is counted
        self.one_pass(trader)
        self.settle(trader)
        self.one_pass(trader)
        self.run_check(trader)
        drawdown = 1 - trader._get_halt_value() / trader.risk_manager.peak_value
        self.assertAlmostEqual(drawdown, 0.07, places=4)

    def test_a_holding_unquoted_on_a_restarts_first_pass_is_no_balance_change(self):
        self.account.balances.update(USD=4000.0, BTC=0.06)  # BTC 60% of the account
        first = self.live_trader()
        self.one_pass(first)  # its balances are kept
        del self.account.bids["BTC"]  # no quote on the restart's first pass
        restarted = self.live_trader(peak=None)
        said = self.one_pass(restarted) + self.run_check(restarted)
        self.assertIsNone(restarted._balance_change)  # nothing compared
        self.account.bids["BTC"] = 100000.0
        said += self.one_pass(restarted) + self.run_check(restarted)
        self.assertNotIn("EMERGENCY STOP", said)
        self.assertFalse(restarted.risk_manager.is_trading_halted())
        self.assertIsNone(restarted._balance_change)
        self.assertEqual(self.changes(restarted), ())
        self.assertEqual(restarted._get_halt_value(), 10000.0)


class FallTests(DepositCase):
    def test_a_withdrawal_still_triggers_the_halt_after_it_settles(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.balances["USD"] = 5100.0  # a 9% withdrawal
        self.one_pass(trader)
        self.run_check(trader)
        self.assertFalse(trader.risk_manager.is_trading_halted())  # settling
        self.assertTrue(self.buys_wait(trader))
        with mock.patch("builtins.print"):
            self.assertTrue(trader._risk_check("BTC-USD", "sell", 0.04, 100000.0))
        self.settle(trader)
        said = self.one_pass(trader) + self.run_check(trader)
        self.assertTrue(trader.risk_manager.is_trading_halted())
        self.assertIn("EMERGENCY STOP: Account drawdown 9.0%", said)
        (change,) = self.changes(trader)
        self.assertEqual((change.kind, change.assets), ("loss", (("USD", -900.0),)))

    def test_t4a_with_an_order_of_unknown_outcome_a_fall_is_still_a_loss(self):
        trader = self.live_trader()
        trader._keep_order_intent(
            "BTC-USD", "buy", {"client_order_id": "c-1", "first_ts": time.time()}
        )
        self.one_pass(trader)
        self.account.balances["USD"] = 5100.0
        self.one_pass(trader)
        self.settle(trader)
        self.one_pass(trader)
        self.run_check(trader)
        self.assertTrue(trader.risk_manager.is_trading_halted())
        self.assertEqual(self.changes(trader)[0].kind, "loss")

    def test_t4b_both_legs_of_an_unrecorded_trade_are_one_small_loss(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.balances.update(USD=5000.0, BTC=0.0499)  # -$1,000, +$990
        self.one_pass(trader)
        self.settle(trader)
        self.one_pass(trader)
        self.run_check(trader)
        self.assertFalse(trader.risk_manager.is_trading_halted())
        (change,) = self.changes(trader)
        self.assertEqual(change.kind, "loss")
        self.assertAlmostEqual(change.value, -10.0)
        self.assertEqual(trader.risk_manager.peak_value, 10000.0)  # no deposit
        self.account.bids["BTC"] = 75000.0  # BTC falls 25%
        said = self.one_pass(trader) + self.run_check(trader)
        self.assertIn("EMERGENCY STOP: Account drawdown 12.6%", said)

    def test_t4c_legs_twenty_seconds_apart_are_still_one_change(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.balances["USD"] = 5000.0  # the dollar leg first
        self.one_pass(trader)
        self.settle(trader, seconds=40)
        self.run_check(trader)
        self.assertFalse(trader.risk_manager.is_trading_halted())  # not a loss yet
        self.account.balances["BTC"] = 0.0499  # the coin leg, 20 s later
        self.one_pass(trader)
        self.settle(trader, seconds=59)  # still since the coin leg
        self.one_pass(trader)
        self.assertEqual(self.changes(trader), ())
        self.settle(trader)
        self.one_pass(trader)
        self.run_check(trader)
        (change,) = self.changes(trader)
        self.assertEqual(change.kind, "loss")
        self.assertAlmostEqual(change.value, -10.0)
        self.assertEqual(trader.risk_manager.peak_value, 10000.0)
        self.assertFalse(trader.risk_manager.is_trading_halted())


class ExplainedTests(DepositCase):
    def test_t2_a_price_move_is_no_balance_change(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.bids["BTC"] = 77500.0
        said = self.one_pass(trader) + self.run_check(trader)
        self.assertTrue(trader.risk_manager.is_trading_halted())
        self.assertIn("EMERGENCY STOP: Account drawdown 9.0%", said)
        self.assertEqual(self.changes(trader), ())

    def test_an_order_management_fill_is_explained(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.balances.update(USD=6000.0 - 1006.0, BTC=0.05)
        self.history_row(
            trader,
            side="buy",
            tag="MANUAL",
            symbol="BTC-USD",
            qty=0.01,
            price=100000.0,
            fees_usd=6.0,
            buying_power_delta=None,
        )
        self.one_pass(trader)
        self.assertFalse(self.buys_wait(trader))
        self.assertIsNone(trader._balance_change)
        self.assertEqual(self.changes(trader), ())

    def test_the_traders_own_fill_is_explained_by_its_cash_change(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.balances.update(USD=6000.0 - 1006.0, BTC=0.05)
        self.history_row(
            trader,
            side="buy",
            symbol="BTC-USD",
            qty=0.01,
            price=100500.0,  # the recorded price may differ: the cash change counts
            fees_usd=6.0,
            buying_power_delta=-1006.0,
        )
        self.one_pass(trader)
        self.assertFalse(self.buys_wait(trader))
        self.assertEqual(self.changes(trader), ())

    def test_a_rounding_residue_is_not_waited_on(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.balances["USD"] = 6000.004
        self.one_pass(trader)
        self.assertFalse(self.buys_wait(trader))

    def test_usd_into_usdc_is_no_change(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.balances.update(USD=5100.0, USDC=900.0)
        self.one_pass(trader)
        self.assertFalse(self.buys_wait(trader))


class ClearedTests(DepositCase):
    def test_reset_peak_clears_the_last_balances_so_nothing_is_classified(self):
        trader = self.live_trader()
        self.one_pass(trader)
        books = trader.data_dir
        self.assertIn("last_balances", risk_state.read_state(books))
        self.account.balances["USD"] = 7000.0
        self.one_pass(trader)
        self.assertTrue(self.buys_wait(trader))
        # Reset peak in Settings > Risk, to the value shown (checked without the rise)
        risk_state.request_peak_reset(books, trader._get_halt_value())
        self.run_check(trader)  # applies it
        self.assertNotIn("last_balances", risk_state.read_state(books))
        self.one_pass(trader)  # a fresh comparison: nothing to classify
        self.assertFalse(self.buys_wait(trader))
        self.assertEqual(self.changes(trader), ())
        self.run_check(trader)
        self.assertFalse(trader.risk_manager.is_trading_halted())
        self.assertEqual(trader.risk_manager.peak_value, 11000.0)  # measured afresh

    def test_t10_a_paper_account_save_clears_the_last_balances(self):
        trader = self.trader()  # paper
        self.one_pass(trader)
        books = trader.data_dir
        self.assertIn("last_balances", risk_state.read_state(books))
        risk_state.request_peak_reset(books, None)  # what a Paper Account save asks
        self.assertNotIn(
            "last_balances",
            risk_state.apply_requests(
                risk_state.read_state(books), risk_state.read_requests(books)
            ),
        )

    def test_a_risk_state_file_without_last_balances_has_nothing_to_compare(self):
        books = os.path.join(self.tmp.name, "paper")
        os.makedirs(books, exist_ok=True)
        risk_state.write_state(
            books, {"peak_value": 10000.0, "peak_measure": "all_balances"}
        )
        self.account.balances["USD"] = 7000.0
        trader = self.live_trader(peak=None)
        self.one_pass(trader)
        self.assertFalse(self.buys_wait(trader))
        self.assertEqual(self.changes(trader), ())


class CoinbaseFillTests(CoinbaseGateBase):
    """The trader's own fills on Coinbase (the recorded-HTTP fake of
    test_coinbase_live_trader.py, which charges its own fee) explain the balance
    changes they make."""

    def test_the_traders_own_coinbase_fills_are_explained(self):
        with recorded_http() as rec, mock.patch(
            "pt_trader.time.sleep"
        ), mock.patch.object(self.pt_trader, "crypto_symbols", ["BTC"]), mock.patch(
            "builtins.print"
        ):
            cb = FakeCoinbase(rec)
            trader = self.trader(copy.deepcopy(REAL))
            trader.manage_trades()
            trader.place_buy_order("c-buy", "buy", "market", "BTC-USD", 50.0)
            trader.manage_trades()
            self.assertIsNone(trader._balance_change)
            kept = risk_state.read_state(trader.data_dir)["last_balances"]
            self.assertAlmostEqual(kept["BTC"], cb.balances["BTC"])  # compared
            trader.place_sell_order(
                "c-sell", "sell", "market", "BTC-USD", cb.balances["BTC"]
            )
            trader.manage_trades()
            self.assertIsNone(trader._balance_change)
        self.assertEqual(cb.unknown, [])
        self.assertEqual(len(cb.order_calls()), 2)
        self.assertEqual(risk_state.current(trader.data_dir).balance_changes, ())
