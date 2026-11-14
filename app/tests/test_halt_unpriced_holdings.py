"""A held asset with no USD price no longer switches the drawdown stop off.

Before, any held asset whose ``<ASSET>-USD`` quote was missing made the account
snapshot incomplete, and only a complete snapshot was ever kept: with GBP or EUR cash,
an airdropped token or a delisted coin in a live account, the trader formed no account
value at all, so the emergency stop was never checked. Now (the owner's choice, "value
what's priced, list the rest"):

* a holding with no price this pass is valued at its last bid while that is at most
  ``HELD_PRICE_MAX_AGE_SECONDS`` (10 minutes) old; after that, or with no price at all,
  it is left out of the account value and listed, with why, for Settings > Risk;
* the stop checks the value of what is counted, every pass, from the first;
* with no account value at all for over ``ACCOUNT_VALUE_MAX_AGE_SECONDS`` (the
  balances cannot be read), buys wait and sells go through; buys go on when a value
  comes again, without a restart.

No network: a fake live account behind the trader's order target, with synthetic
balances and bids."""

from __future__ import annotations

import dataclasses
import json
import os
import time
from unittest import mock

from helpers import PaperTraderCase

import risk_state
import trading_mode as tm
from pt_exchange_abstraction import MarketData


class FakeAccount:
    """A live account: the balances and bids the test sets. A coin without a bid has
    no USD market (its quote raises, as a connector's MarketNotFound does)."""

    def __init__(self, balances, bids):
        self.balances = dict(balances)
        self.bids = dict(bids)
        self.down = False  # True: the balance read fails

    def get_balance(self):
        if self.down:
            raise ConnectionError("the exchange did not answer")
        return {asset: qty for asset, qty in self.balances.items() if qty > 0}

    def get_market_data(self, symbol):
        base = symbol.split("-")[0]
        if base not in self.bids:
            raise LookupError(f"No market {symbol}")
        bid = float(self.bids[base])
        return MarketData(symbol, bid, bid, bid * 1.001, 0.0, time.time(), "fake")


class StopRun(BaseException):
    """Ends the trader's endless loop in a test (run() catches Exception)."""


class LiveAccountCase(PaperTraderCase):
    """The starting point: USD $6,000 and 0.04 BTC at a $100,000 bid ($4,000), a
    $10,000 peak and the 8% emergency stop."""

    def setUp(self):
        super().setUp()
        self.one_coin("BTC")
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.account = FakeAccount({"USD": 6000.0, "BTC": 0.04}, {"BTC": 100000.0})

    def live_trader(self, peak=10000.0):
        trader = self.trader()
        trader._target = dataclasses.replace(
            trader._target, mode=tm.TradingMode.LIVE, exchange=self.account
        )
        if peak:
            trader.risk_manager.update_portfolio_value(peak)
        return trader

    def one_pass(self, trader):
        with mock.patch("builtins.print"):
            trader.manage_trades()

    def run_check(self, trader) -> str:
        """run()'s check at the start of a cycle (the pass itself is not run)."""
        with mock.patch.object(
            trader, "manage_trades", side_effect=StopRun
        ), mock.patch("builtins.print") as said:
            with self.assertRaises(StopRun):
                trader.run()
        return str(said.call_args_list)

    def view(self, trader):
        return risk_state.current(trader.data_dir)


class UnpricedHoldingTests(LiveAccountCase):
    def test_an_unpriced_holding_from_the_first_pass_still_lets_a_9pct_fall_halt(self):
        self.account.balances["GBP"] = 1250.0  # no GBP-USD market
        trader = self.live_trader()
        self.one_pass(trader)
        self.assertEqual(trader._get_account_value(), 10000.0)  # GBP not counted
        self.account.bids["BTC"] = 77500.0  # BTC's bid falls 22.5%: the account 9%
        self.one_pass(trader)
        said = self.run_check(trader)
        self.assertTrue(trader.risk_manager.is_trading_halted())
        self.assertIn("EMERGENCY STOP: Account drawdown 9.0%", said)

    def test_an_unpriced_holding_is_listed_with_why(self):
        self.account.balances["GBP"] = 1250.0
        trader = self.live_trader()
        self.one_pass(trader)
        self.assertEqual(
            self.view(trader).not_counted, (("GBP", 1250.0, "no USD price"),)
        )

    def test_a_quote_missing_for_5_minutes_is_valued_at_its_last_bid(self):
        trader = self.live_trader()
        self.one_pass(trader)
        del self.account.bids["BTC"]  # BTC's quote is missing from now on
        trader._last_good_bid_ask["BTC-USD"]["ts"] -= 5 * 60
        self.one_pass(trader)
        self.assertEqual(trader._get_account_value(), 10000.0)
        self.assertEqual(self.view(trader).not_counted, ())

    def test_a_quote_missing_for_11_minutes_leaves_the_asset_out_and_lists_it(self):
        trader = self.live_trader()
        self.one_pass(trader)
        del self.account.bids["BTC"]
        trader._last_good_bid_ask["BTC-USD"]["ts"] -= 11 * 60
        self.one_pass(trader)
        self.assertEqual(trader._get_account_value(), 6000.0)
        self.assertEqual(
            self.view(trader).not_counted,
            (("BTC", 0.04, "no price for over 10 minutes"),),
        )
        # counted again once its quote is back
        self.account.bids["BTC"] = 100000.0
        self.one_pass(trader)
        self.assertEqual(trader._get_account_value(), 10000.0)
        self.assertEqual(self.view(trader).not_counted, ())

    def test_entries_are_sized_on_the_value_of_what_is_counted(self):
        self.account.balances["GBP"] = 1250.0
        trader = self.live_trader()
        self.one_pass(trader)
        with open(trader.trader_status_path, encoding="utf-8") as f:
            account = json.load(f)["account"]
        self.assertEqual(account["total_account_value"], 10000.0)


class NoAccountValueTests(LiveAccountCase):
    def test_no_value_for_11_minutes_makes_buys_wait_and_sells_go_through(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.down = True  # the balances cannot be read from now on
        trader._account_value_ts = time.time() - 11 * 60
        self.one_pass(trader)
        with mock.patch("builtins.print") as said:
            self.assertFalse(trader._risk_check("BTC-USD", "buy", 0.0001, 100000.0))
            self.assertTrue(trader._risk_check("BTC-USD", "sell", 0.04, 100000.0))
        self.assertIn(
            "BUYS WAITING: no account value for over 10 minutes",
            str(said.call_args_list),
        )
        self.assertEqual(
            self.view(trader).buys_waiting,
            "no account value for over 10 minutes (the balances could not be read)",
        )
        # a value again: buys go on, without a restart
        self.account.down = False
        self.one_pass(trader)
        self.assertTrue(trader._risk_check("BTC-USD", "buy", 0.0001, 100000.0))
        self.assertEqual(self.view(trader).buys_waiting, "")

    def test_no_value_for_5_minutes_lets_buys_go_on(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.down = True
        trader._account_value_ts = time.time() - 5 * 60
        self.one_pass(trader)
        with mock.patch("builtins.print"):
            self.assertTrue(trader._risk_check("BTC-USD", "buy", 0.0001, 100000.0))

    def test_no_entry_work_is_done_while_buys_wait(self):
        trader = self.live_trader()
        self.one_pass(trader)
        self.account.down = True
        trader._account_value_ts = time.time() - 11 * 60
        with mock.patch.object(trader, "_llm_entry_allowed") as llm, mock.patch.object(
            trader.signal_engine, "decide"
        ) as decide, mock.patch.object(trader, "_read_long_dca_signal") as neural:
            self.one_pass(trader)
        self.assertFalse(llm.called or decide.called or neural.called)


class SavedStateTests(LiveAccountCase):
    def test_a_risk_state_file_without_the_new_fields_still_loads(self):
        books = os.path.join(self.tmp.name, "paper")
        os.makedirs(books, exist_ok=True)
        risk_state.write_state(books, {"peak_value": 10000.0, "peak_ts": 5.0})
        view = risk_state.current(books)
        self.assertEqual(
            (view.peak_value, view.not_counted, view.buys_waiting), (10000.0, (), "")
        )
        trader = self.live_trader(peak=None)
        self.assertEqual(trader.risk_manager.peak_value, 10000.0)
