"""One coin's error never ends the trader's pass (defect N8 in
docs/dev/ptai-rd-001/A2-defect-register.md).

* The signal engine holds a coin that no exchange in Settings lists (``MarketNotFound``,
  a ``RuntimeError``), for its own candles and for an entry gate's context series,
  instead of raising.
* The trader holds a coin whose decision raised anything, and goes on: with a coin that
  has no market first in Settings, the coin after it still trades on its own bars, and
  the status file is still written each pass.

Before, the error ended the pass at that coin: the coins after it were neither decided
nor managed, and the status file was not written.

Synthetic candles; no network."""

from __future__ import annotations

import copy
import json
import os
import unittest
from unittest import mock

import pandas as pd
from helpers import Feed, PaperTraderCase, make_candles
from test_signal_engine import PAPER, expected_actions, trend_series

import trading_mode as tm
from pt_exchange_abstraction import MarketNotFound
from signal_engine import SignalEngine
from strategies.base import Action


class NoMarket:
    """The feed's bars for every pair but ``missing``, for which no exchange lists it."""

    def __init__(self, feed: Feed, missing: str = "XMR-USD"):
        self.feed = feed
        self.missing = missing
        self.asked = []

    def provider(self, symbol, tf, n, now):
        self.asked.append(symbol)
        if symbol == self.missing:
            raise MarketNotFound(f"no exchange in Settings lists {symbol}")
        return self.feed.provider(symbol, tf, n, now)


class EngineTests(unittest.TestCase):
    def test_a_coin_with_no_market_holds(self):
        feed = Feed(make_candles(trend_series()))
        feed.set_after_bar(200)
        source = NoMarket(feed)
        engine = SignalEngine(copy.deepcopy(PAPER), source.provider, feed.clock)
        decision = engine.decide("XMR")
        self.assertEqual(
            (decision.action, decision.reason), (Action.HOLD, "CANDLES_UNAVAILABLE")
        )
        self.assertIsNotNone(engine.decide("BTC"))

    def test_a_context_series_with_no_market_is_left_out(self):
        feed = Feed(make_candles(trend_series()))
        feed.set_after_bar(200)
        source = NoMarket(feed)
        engine = SignalEngine(copy.deepcopy(PAPER), source.provider, feed.clock)
        now = pd.Timestamp(feed.clock(), unit="s", tz="UTC")
        self.assertIsNone(engine._context_candles("XMR-USD", "1d", 30, now))


class TraderTests(PaperTraderCase):
    def setUp(self):
        super().setUp()
        self.frame = make_candles(trend_series())
        self.feed = Feed(self.frame)
        for p in (
            mock.patch.object(self.pt_trader.time, "sleep"),
            # a coin no exchange lists, first in Settings
            mock.patch.object(self.pt_trader, "crypto_symbols", ["XMR", "BTC"]),
        ):
            p.start()
            self.addCleanup(p.stop)
        tm.reset_paper_exchange()

    def trader(self, provider):
        settings = copy.deepcopy(PAPER)
        engine = SignalEngine(settings, provider, self.feed.clock)
        self.feed.set_after_bar(150)
        trader = self.pt_trader.CryptoAPITrading(
            settings_source=settings, signal_engine=engine
        )
        trader._order_poll_seconds = 0.0
        return trader

    def run_session(self, trader):
        acted = {}
        statuses = 0
        for k in range(150, len(self.frame)):
            self.feed.set_after_bar(k)
            before = len(tm.get_paper_exchange().account.orders)
            if os.path.exists(trader.trader_status_path):
                os.remove(trader.trader_status_path)
            trader.manage_trades()
            statuses += os.path.exists(trader.trader_status_path)
            orders = list(tm.get_paper_exchange().account.orders.values())
            if len(orders) > before:
                acted[k] = (orders[-1].symbol, orders[-1].side.value)
        return acted, statuses

    def expected(self):
        (enter_bar, _), (exit_bar, _) = expected_actions(self.frame)
        return {enter_bar: ("BTC", "buy"), exit_bar: ("BTC", "sell")}

    def test_the_coin_after_one_with_no_market_still_trades(self):
        source = NoMarket(self.feed)
        trader = self.trader(source.provider)
        acted, statuses = self.run_session(trader)
        self.assertIn("XMR-USD", source.asked)  # it was asked, and held
        self.assertEqual(acted, self.expected())
        self.assertEqual(statuses, len(self.frame) - 150)  # written every pass
        with open(trader.trader_status_path, encoding="utf-8") as f:
            self.assertIn("BTC", json.load(f)["signals"]["last_decisions"])

    def test_any_error_deciding_one_coin_holds_only_that_coin(self):
        trader = self.trader(self.feed.provider)
        real = trader.signal_engine.decide

        def broken_for_xmr(base, position=None):
            if base == "XMR":
                raise ValueError("something unexpected")
            return real(base, position)

        with mock.patch.object(
            trader.signal_engine, "decide", side_effect=broken_for_xmr
        ), mock.patch("builtins.print") as said:
            acted, statuses = self.run_session(trader)
        self.assertEqual(acted, self.expected())
        self.assertEqual(statuses, len(self.frame) - 150)
        told = [str(c) for c in said.call_args_list if "No decision for XMR" in str(c)]
        self.assertEqual(len(told), 1)  # said once, not every pass
        self.assertIn("ValueError: something unexpected", told[0])


if __name__ == "__main__":
    unittest.main()
