"""FDS-SR-001 milestone M3b: STRAT-005, time-series momentum decided weekly (sections
5.4.3 and 12).

* The decision schedule: every ``rebalance_days`` days from Monday 2020-01-06, on the
  bar that closes at midnight UTC; nothing in between.
* The vote: hand-worked returns over the three lookbacks; ``min_agree``; a gap at a
  lookback's date holds rather than using another bar.
* No look-ahead, and parity between the live signal engine and a replayed runner on
  every closed daily bar; next-open fills in the backtester.
* Bounds and the increasing-lookbacks rule; research-only, not enabled for research,
  refused for trading; described for the strategy list.

Synthetic candles only: no network, nothing about performance."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd
from helpers import make_candles
from test_strategy_breakout import DailyFeed

from backtest.engine import CostModel, run_backtest
from signal_engine import SignalEngine
from strategies import ParamError, StrategyError, create
from strategies import descriptions as words
from strategies.base import Action
from strategies.catalogue import CATALOGUE
from strategies.factory import build_runner
from strategies.settings import read_research_enabled, read_strategy_settings

DAY = 86_400
MONDAY = "2023-01-02"  # a decision day: 1092 days after the anchor, a multiple of 7
ZERO = CostModel(0, 0)


def daily(closes, start=MONDAY):
    return make_candles(closes, start=start, tf_seconds=DAY)


def voting_closes(r30, r90, r365, n=400):
    """``n`` daily closes of 100 whose last bar (a Monday) has the given signs of the
    30-, 90- and 365-day returns."""
    closes = [100.0] * n
    last = n - 1
    for days, sign in ((30, r30), (90, r90), (365, r365)):
        closes[last - days] = 100.0 / (1.1 if sign > 0 else 0.9)
    return closes


class ScheduleTests(unittest.TestCase):
    def test_weekly_decisions_fall_on_mondays(self):
        s = create("STRAT-005")
        days = pd.date_range("2024-01-01", periods=21, freq="D", tz="UTC")
        decided = [d for d in days if s.is_decision_bar(d)]
        self.assertEqual([d.day_name() for d in decided], ["Monday"] * 3)
        self.assertEqual(decided[0], pd.Timestamp("2024-01-01", tz="UTC"))

    def test_rebalance_days_sets_the_spacing(self):
        s = create("STRAT-005", rebalance_days=1)
        days = pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC")
        self.assertTrue(all(s.is_decision_bar(d) for d in days))
        s = create("STRAT-005", rebalance_days=28)
        days = pd.date_range("2020-01-06", periods=60, freq="D", tz="UTC")
        decided = [d for d in days if s.is_decision_bar(d)]
        self.assertEqual(  # days 0, 28 and 56 after the anchor
            decided,
            [
                pd.Timestamp("2020-01-06", tz="UTC"),
                pd.Timestamp("2020-02-03", tz="UTC"),
                pd.Timestamp("2020-03-02", tz="UTC"),
            ],
        )

    def test_on_4_hour_bars_only_the_bar_closing_at_midnight_decides(self):
        s = create("STRAT-005")
        s.set_timeframe(4 * 3600)
        self.assertTrue(s.is_decision_bar(pd.Timestamp("2024-01-01 20:00", tz="UTC")))
        self.assertFalse(s.is_decision_bar(pd.Timestamp("2024-01-01 16:00", tz="UTC")))
        self.assertFalse(s.is_decision_bar(pd.Timestamp("2024-01-02 20:00", tz="UTC")))
        self.assertEqual((s.bars(30), s.bars(365), s.warmup_bars), (180, 2190, 2191))

    def test_other_days_hold(self):
        frame = daily(voting_closes(1, 1, 1))
        s = create("STRAT-005")
        self.assertEqual(s.on_bar(frame).action, Action.ENTER_LONG)
        sunday = frame.iloc[:-1].reset_index(drop=True)
        self.assertEqual(s.on_bar(sunday).reason, "NOT_DECISION_DAY")


class VoteTests(unittest.TestCase):
    def test_two_of_three_enters_and_fewer_exits(self):
        s = create("STRAT-005")
        cases = {
            (1, 1, 1): Action.ENTER_LONG,
            (1, -1, 1): Action.ENTER_LONG,
            (-1, 1, -1): Action.EXIT_LONG,
            (-1, -1, -1): Action.EXIT_LONG,
        }
        for signs, action in cases.items():
            with self.subTest(signs=signs):
                result = s.on_bar(daily(voting_closes(*signs)))
                self.assertEqual(result.action, action)
                self.assertEqual(
                    result.indicators["positive"], sum(x > 0 for x in signs)
                )
        ind = s.on_bar(daily(voting_closes(1, -1, 1))).indicators
        self.assertAlmostEqual(ind["return_30d"], 0.1)
        self.assertAlmostEqual(ind["return_90d"], -0.1)

    def test_min_agree_sets_the_votes_needed(self):
        frame = daily(voting_closes(1, -1, 1))
        self.assertEqual(
            create("STRAT-005", min_agree=3).on_bar(frame).action, Action.EXIT_LONG
        )
        frame = daily(voting_closes(-1, -1, 1))
        self.assertEqual(
            create("STRAT-005", min_agree=1).on_bar(frame).action, Action.ENTER_LONG
        )

    def test_a_zero_return_is_not_positive(self):
        frame = daily([100.0] * 400)
        self.assertEqual(create("STRAT-005").on_bar(frame).action, Action.EXIT_LONG)

    def test_a_missing_bar_at_a_lookback_holds(self):
        frame = daily(voting_closes(1, 1, 1))
        gap = frame.drop(index=len(frame) - 1 - 50).reset_index(drop=True)
        self.assertEqual(create("STRAT-005").on_bar(gap).reason, "BARS_MISSING")

    def test_warm_up_needs_the_long_lookback(self):
        s = create("STRAT-005")
        self.assertEqual(s.warmup_bars, 366)
        self.assertEqual(s.on_bar(daily([100.0] * 365)).reason, "WARMUP")


def random_walk(n, seed):
    rng = np.random.default_rng(seed)
    return list(100 * np.exp(np.cumsum(rng.normal(0.001, 0.03, n))))


class LookAheadAndParityTests(unittest.TestCase):
    def test_appending_bars_never_changes_an_earlier_decision(self):
        frame = daily(random_walk(500, 3))
        runner = build_runner("STRAT-005")
        runner.set_timeframe(DAY)
        full = [
            runner.evaluate(runner.window(frame, i), None, "X").action
            for i in range(len(frame))
        ]
        short = frame.iloc[:420].reset_index(drop=True)
        for i in range(420):
            self.assertEqual(
                runner.evaluate(runner.window(short, i), None, "X").action, full[i], i
            )
        self.assertIn(Action.ENTER_LONG, full)

    def test_the_signal_engine_and_a_replayed_runner_agree_on_every_bar(self):
        frame = daily(random_walk(480, 5))
        settings = {"strategy": {"active_id": "STRAT-005", "timeframe": "1d"}}
        feed = DailyFeed(frame)
        engine = SignalEngine(settings, feed.provider, feed.clock)
        replay = build_runner("STRAT-005")
        replay.set_timeframe(DAY)
        actions = set()
        for k in range(366, len(frame)):
            feed.set_after_bar(k)
            got = engine.decide("BTC", None)
            want = replay.evaluate(replay.window(frame, k), None, "BTC")
            self.assertEqual((got.action, got.reason), (want.action, want.reason), k)
            actions.add(want.reason)
        self.assertTrue({"NOT_DECISION_DAY"} < actions)

    def test_the_backtester_buys_at_the_open_after_a_decision_day(self):
        closes = voting_closes(1, 1, 1, n=400) + [100.0] * 20
        frame = daily(closes)
        result = run_backtest(frame, build_runner("STRAT-005"), "X", "1d", cost=ZERO)
        trade = result.trades[0]
        self.assertEqual(trade.entry_time, frame["open_time"].iloc[400])
        self.assertEqual(frame["open_time"].iloc[399].day_name(), "Monday")


class CatalogueTests(unittest.TestCase):
    def test_bounds_and_the_increasing_lookbacks_rule(self):
        for bad in (
            {"lookback_1": 4},
            {"lookback_3": 401},
            {"min_agree": 4},
            {"rebalance_days": 0},
        ):
            with self.assertRaises(ParamError):
                create("STRAT-005", **bad)
        with self.assertRaisesRegex(StrategyError, "increase strictly"):
            create("STRAT-005", lookback_1=90, lookback_2=90)
        self.assertTrue(
            words.rule_problem(
                "STRAT-005",
                dict(CATALOGUE["STRAT-005"]["default_params"], lookback_2=400),
            )
        )

    def test_it_is_research_only_daily_and_not_enabled(self):
        e = CATALOGUE["STRAT-005"]
        self.assertEqual((e["authorisation"], e["family"]), ("research", "momentum"))
        self.assertEqual(e["timeframes_permitted"], ["1d"])
        self.assertNotIn("STRAT-005", read_research_enabled({}))
        settings = {"strategy": {"active_id": "STRAT-005", "timeframe": "1d"}}
        for mode in ("paper", "live"):
            self.assertIn(
                "research only", read_strategy_settings(settings, mode).problem
            )

    def test_it_is_described_for_the_strategy_list(self):
        d = words.DESCRIPTIONS["STRAT-005"]
        self.assertEqual(set(d.params), set(CATALOGUE["STRAT-005"]["default_params"]))


if __name__ == "__main__":
    unittest.main()
