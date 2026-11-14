"""A settings file that exists but cannot be read (A2 defect register N10).

``pt_config.json`` cut short (a write that did not finish), or one that cannot be
opened, used to read as no settings at all: paper mode with the default strategy,
STRAT-001 on 1h, and no problem reported. So a paper trader set to another strategy
went on trading STRAT-001. Now such a file is a problem: the strategy settings report
it, the trader places no orders in either mode, and its status says why. A missing
file (a fresh install) still reads as the defaults.

The candles are the synthetic series of test_signal_engine.py; nothing leaves the
machine.
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
import unittest
from unittest import mock

from helpers import Feed, PaperTraderCase, make_candles
from test_signal_engine import expected_actions, trend_series

import trading_mode as tm
from signal_engine import SignalEngine
from strategies.settings import read_strategy_settings

# the owner's file, STRAT-000 chosen, cut short in the middle of the strategy id
WHOLE = {"trading": {"mode": "paper"}, "strategy": {"active_id": "STRAT-000"}}
CUT_SHORT = json.dumps(WHOLE)[:-8]


def write(path: str, text) -> None:
    mode = "wb" if isinstance(text, bytes) else "w"
    with open(path, mode) as f:
        f.write(text)


class SettingsFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "pt_config.json")

    def test_a_file_that_cannot_be_read_is_a_problem_whatever_is_wrong_with_it(self):
        for name, text in (
            ("cut short", CUT_SHORT),
            ("empty", ""),
            ("not a JSON object", "[1, 2]"),
            ("not UTF-8", b'{"trading": {"mode": "\xff"}}'),
        ):
            write(self.path, text)
            for mode in (None, "paper", "live"):
                problem = read_strategy_settings(self.path, mode=mode).problem
                self.assertIsNotNone(problem, f"{name}, {mode}")
                self.assertIn("pt_config.json", problem)
            self.assertEqual(tm.settings_problem(self.path), problem, name)
            # the mode still reads as paper, as before: trading is blocked instead
            self.assertIs(
                tm.read_trading_settings(self.path).mode, tm.TradingMode.PAPER
            )
        os.remove(self.path)
        os.mkdir(self.path)  # cannot be opened as a file
        self.assertIn(
            "cannot be read", read_strategy_settings(self.path, mode="paper").problem
        )

    def test_a_missing_file_still_reads_as_the_defaults(self):
        s = read_strategy_settings(self.path, mode="paper")
        self.assertIsNone(s.problem)
        self.assertEqual(
            (s.engine, s.active_id, s.timeframe), ("catalogue", "STRAT-001", "1h")
        )
        self.assertIs(tm.read_trading_settings(self.path).mode, tm.TradingMode.PAPER)
        self.assertEqual(tm.settings_mapping(self.path), {})


class UnreadableSettingsTraderTests(PaperTraderCase):
    def setUp(self):
        super().setUp()
        self.frame = make_candles(trend_series())
        self.feed = Feed(self.frame)
        self.path = os.path.join(self.tmp.name, "pt_config.json")
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.one_coin("BTC")

    def file_trader(self):
        """A trader whose settings are the file at ``self.path``, as the app's are."""
        engine = SignalEngine(self.path, self.feed.provider, self.feed.clock)
        self.feed.set_after_bar(150)
        trader = self.pt_trader.CryptoAPITrading(
            settings_source=self.path, signal_engine=engine
        )
        trader._order_poll_seconds = 0.0
        return trader

    def orders(self):
        return list(tm.get_paper_exchange().account.orders.values())

    def test_a_paper_trader_with_a_settings_file_cut_short_places_no_orders(self):
        # STRAT-001, what the cut-short file used to read as, trades on these bars
        self.assertTrue(expected_actions(self.frame, "STRAT-001"))
        write(self.path, CUT_SHORT)
        trader = self.file_trader()
        with mock.patch.object(self.pt_trader.logger, "warning") as warned:
            for k in range(150, len(self.frame)):
                self.feed.set_after_bar(k)
                trader.manage_trades()
            bought = trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        traded = [(r["side"], r.get("strategy_id")) for r in self.ledger_rows()]
        self.assertEqual(self.orders(), [], f"it traded: {traded}")
        self.assertIsNone(bought)
        status = trader._signals_status()
        self.assertIn("pt_config.json cannot be read", status["blocked"])
        self.assertEqual(status["note"], "SIGNALS: BLOCKED")
        self.assertIn("pt_config.json cannot be read", str(warned.call_args_list))

    def test_orders_stop_while_the_file_cannot_be_read_and_go_on_once_it_can(self):
        write(self.path, json.dumps(WHOLE))
        trader = self.file_trader()
        write(self.path, CUT_SHORT)
        self.assertIsNone(
            trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        )
        self.assertEqual(self.orders(), [])
        write(self.path, json.dumps(WHOLE))
        bought = trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        self.assertEqual(bought["state"], "filled")

    def test_a_live_trader_says_the_file_cannot_be_read_not_that_the_mode_changed(
        self,
    ):
        write(self.path, json.dumps(WHOLE))
        trader = self.file_trader()
        # a trader that started live (its pinned target); the file is then cut short,
        # so the mode reads as paper and the per-pass mode check stops it
        trader._target = dataclasses.replace(
            trader._target, mode=tm.TradingMode.LIVE, key="live:coinbase"
        )
        write(self.path, CUT_SHORT)
        with mock.patch("builtins.print") as said:
            trader.manage_trades()
        printed = str(said.call_args_list)
        self.assertIn("pt_config.json cannot be read", printed)
        self.assertNotIn("Trading mode changed", printed)
        self.assertEqual(self.orders(), [])


if __name__ == "__main__":
    unittest.main()
