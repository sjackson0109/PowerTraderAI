"""FDS-SR-001 milestone M3a: STRAT-004, the daily Donchian breakout (sections 5.4.3
and 12).

* Hand-worked signals on constructed closes: a new closing high enters, a tie does not,
  a new closing low exits; the warm-up; the lookbacks in calendar days on 4-hour bars.
* No look-ahead: appending bars after t never changes the decision at t, and the rule
  reads exactly the window the runner gives it.
* Parity: the live signal engine and a replayed runner give the same decision on every
  closed daily bar.
* Bounds and the rule between the two parameters; research-only, not enabled for
  research, and refused for trading; described for the strategy list.

Synthetic candles only: no network, nothing about performance."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd
from helpers import make_candles

from backtest.engine import CostModel, run_backtest
from signal_engine import SignalEngine
from strategies import ParamError, StrategyError, create
from strategies import descriptions as words
from strategies.base import Action
from strategies.catalogue import CATALOGUE
from strategies.factory import build_runner
from strategies.settings import read_research_enabled, read_strategy_settings

DAY = 86_400
ZERO = CostModel(0, 0)


def daily(closes, start="2024-01-01"):
    return make_candles(closes, start=start, tf_seconds=DAY)


class DailyFeed:
    """The test helpers' Feed for daily bars: reveals only closed bars."""

    def __init__(self, frame):
        self.frame = frame
        self.now = 0.0

    def set_after_bar(self, k, seconds_after_close=10):
        close = self.frame["open_time"].iloc[k] + pd.Timedelta(days=1)
        self.now = close.timestamp() + seconds_after_close

    def clock(self):
        return self.now

    def provider(self, symbol, tf, n, now):
        closed = self.frame[self.frame["open_time"] + pd.Timedelta(days=1) <= now]
        return closed.tail(n).reset_index(drop=True)


def signal(strategy, frame):
    s = strategy.on_bar(frame)
    return s.action, s.reason


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.s = create("STRAT-004", entry_days=20, exit_days=10)

    def test_a_new_closing_high_enters_and_a_tie_does_not(self):
        base = [100.0] * 20
        self.assertEqual(
            signal(self.s, daily(base + [101.0])),
            (Action.ENTER_LONG, "NEW_CLOSING_HIGH"),
        )
        self.assertEqual(
            signal(self.s, daily(base + [100.0])), (Action.HOLD, "INSIDE_CHANNEL")
        )

    def test_a_new_closing_low_exits_and_a_tie_does_not(self):
        closes = list(np.linspace(100, 120, 20))
        low10 = min(closes[-10:])
        self.assertEqual(
            signal(self.s, daily(closes + [low10 - 0.01])),
            (Action.EXIT_LONG, "NEW_CLOSING_LOW"),
        )
        self.assertEqual(signal(self.s, daily(closes + [low10]))[0], Action.HOLD)

    def test_only_the_lookback_closes_count(self):
        # a higher close 21 days back is outside the 20-day channel
        closes = [200.0] + [100.0] * 20 + [150.0]
        frame = daily(closes)
        self.assertEqual(signal(self.s, frame)[0], Action.ENTER_LONG)
        ind = self.s.on_bar(frame).indicators
        self.assertEqual(ind["channel_high"], 100.0)
        self.assertEqual(ind["channel_low"], 100.0)

    def test_warm_up_holds_until_the_channel_is_full(self):
        self.assertEqual(self.s.warmup_bars, 21)
        self.assertEqual(signal(self.s, daily([100.0] * 20))[1], "WARMUP")
        self.assertEqual(signal(self.s, daily([100.0] * 21))[1], "INSIDE_CHANNEL")

    def test_the_lookbacks_are_calendar_days_on_any_candles(self):
        s = create("STRAT-004")
        self.assertEqual((s.bars(55), s.bars(20), s.warmup_bars), (55, 20, 56))
        s.set_timeframe(4 * 3600)
        self.assertEqual((s.bars(55), s.bars(20), s.warmup_bars), (330, 120, 331))
        s.set_timeframe(3600)
        self.assertEqual(s.lookback_bars, 55 * 24 + 1)

    def test_bounds_and_the_rule_between_the_days(self):
        for bad in ({"entry_days": 10}, {"entry_days": 300}, {"exit_days": 4}):
            with self.assertRaises(ParamError):
                create("STRAT-004", **bad)
        with self.assertRaises(ParamError):
            create("STRAT-004", entry_days=55.5)
        with self.assertRaisesRegex(StrategyError, "exit_days .* less than entry_days"):
            create("STRAT-004", entry_days=30, exit_days=30)
        self.assertIsNone(
            words.rule_problem("STRAT-004", {"entry_days": 30, "exit_days": 20})
        )
        self.assertTrue(
            words.rule_problem("STRAT-004", {"entry_days": 30, "exit_days": 30})
        )


def random_walk(n=400, seed=7):
    rng = np.random.default_rng(seed)
    return list(100 * np.exp(np.cumsum(rng.normal(0, 0.03, n))))


class LookAheadTests(unittest.TestCase):
    def test_appending_bars_never_changes_an_earlier_decision(self):
        frame = daily(random_walk())
        runner = build_runner("STRAT-004", {"entry_days": 30, "exit_days": 10})
        runner.set_timeframe(DAY)
        decisions = [
            runner.evaluate(runner.window(frame, i), None, "X").action
            for i in range(len(frame))
        ]
        for cut in (60, 150, 299):
            short = frame.iloc[: cut + 1].reset_index(drop=True)
            for i in range(cut + 1):
                self.assertEqual(
                    runner.evaluate(runner.window(short, i), None, "X").action,
                    decisions[i],
                    (cut, i),
                )
        self.assertIn(Action.ENTER_LONG, decisions)

    def test_the_rule_reads_exactly_the_runners_window(self):
        frame = daily(random_walk())
        runner = build_runner("STRAT-004")
        runner.set_timeframe(DAY)
        for i in (56, 120, 399):
            window = runner.window(frame, i)
            self.assertEqual(len(window), 56)
            # changing a bar just before the window changes nothing
            altered = frame.copy()
            altered.loc[i - 56, "close"] = 1e9
            self.assertEqual(
                runner.evaluate(runner.window(altered, i), None, "X").action,
                runner.evaluate(window, None, "X").action,
            )


class ParityTests(unittest.TestCase):
    def test_the_signal_engine_and_a_replayed_runner_agree_on_every_bar(self):
        frame = daily(random_walk(300, seed=11))
        settings = {"strategy": {"active_id": "STRAT-004", "timeframe": "1d"}}
        feed = DailyFeed(frame)
        engine = SignalEngine(settings, feed.provider, feed.clock)
        replay = build_runner("STRAT-004")
        replay.set_timeframe(DAY)
        seen = set()
        for k in range(56, len(frame)):
            feed.set_after_bar(k)
            got = engine.decide("BTC", None)
            want = replay.evaluate(replay.window(frame, k), None, "BTC")
            self.assertIsNotNone(got, k)
            self.assertEqual((got.action, got.reason), (want.action, want.reason), k)
            self.assertEqual(got.bar_time, frame["open_time"].iloc[k])
            seen.add(want.action)
        self.assertIn(Action.ENTER_LONG, seen)

    def test_the_backtester_enters_at_the_next_open_after_a_breakout(self):
        frame = daily([100.0] * 55 + [110.0, 111.0, 112.0] + [90.0] * 25)
        runner = build_runner("STRAT-004")
        result = run_backtest(frame, runner, "X", "1d", cost=ZERO)
        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade.entry_time, frame["open_time"].iloc[56])
        self.assertEqual(trade.entry_price, frame["open"].iloc[56])
        # 90 is below every close of the previous 20 days: exit at the next open
        self.assertEqual(trade.exit_time, frame["open_time"].iloc[59])


class CatalogueTests(unittest.TestCase):
    def test_it_is_paper_and_daily(self):
        e = CATALOGUE["STRAT-004"]
        self.assertEqual(e["authorisation"], "paper")  # the owner, 2026-11-12
        self.assertEqual(e["family"], "breakout")
        self.assertEqual(
            (e["timeframe_primary"], e["timeframes_permitted"]), ("1d", ["1d"])
        )
        self.assertEqual(e["default_params"], {"entry_days": 55, "exit_days": 20})

    def test_it_is_not_enabled_for_research_by_default(self):
        self.assertNotIn("STRAT-004", read_research_enabled({}))

    def test_it_is_allowed_in_paper_and_refused_in_live(self):
        settings = {"strategy": {"active_id": "STRAT-004", "timeframe": "1d"}}
        self.assertIsNone(read_strategy_settings(settings).problem)  # research use
        self.assertIsNone(read_strategy_settings(settings, "paper").problem)
        problem = read_strategy_settings(settings, "live").problem
        self.assertIn("STRAT-004 can be used for paper trading, not live", problem)

    def test_it_is_described_for_the_strategy_list(self):
        d = words.DESCRIPTIONS["STRAT-004"]
        self.assertEqual(set(d.params), set(CATALOGUE["STRAT-004"]["default_params"]))
        for p in d.params.values():
            self.assertTrue(p.label and p.help)


if __name__ == "__main__":
    unittest.main()
