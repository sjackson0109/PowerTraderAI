"""FDS-SR-001 milestone M3b: STRAT-005, time-series momentum decided weekly (sections
5.4.3 and 12).

* The decision schedule: every ``rebalance_days`` days from Monday 2020-01-06, on the
  bar that closes at midnight UTC; nothing in between.
* The vote: hand-worked returns over the three lookbacks; ``min_agree``.
* Gaps: each reference bar is found by its open time. A missing reference bar holds,
  and no other bar, earlier or later, stands in. A gap anywhere else, alone or in a
  run, changes nothing, on daily, 12h and 4h bars. On complete series every decision
  is the one counting bars gave.
* No look-ahead, and parity between the live signal engine and a replayed runner on
  every closed daily bar, with and without gaps; next-open fills in the backtester.
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


def voting_closes(r30, r90, r365, n=400, per_day=1):
    """``n`` closes of 100 whose last bar has the given signs of the 30-, 90- and
    365-day returns (``per_day`` bars a day)."""
    closes = [100.0] * n
    last = n - 1
    for days, sign in ((30, r30), (90, r90), (365, r365)):
        closes[last - days * per_day] = 100.0 / (1.1 if sign > 0 else 0.9)
    return closes


def without(frame, days_back=(), times=()):
    """``frame`` less the bars opening ``days_back`` days before its last bar, and the
    bars opening at ``times``: gaps, with every other bar's time unchanged."""
    last = frame["open_time"].iloc[-1]
    gone = {last - pd.Timedelta(days=d) for d in days_back} | set(times)
    return frame[~frame["open_time"].isin(gone)].reset_index(drop=True)


def intraday(closes, tf_hours):
    """Candles of ``tf_hours`` whose last bar closes at midnight ending Monday
    2023-01-02, a decision day."""
    last_open = pd.Timestamp("2023-01-03", tz="UTC") - pd.Timedelta(hours=tf_hours)
    start = last_open - pd.Timedelta(hours=tf_hours * (len(closes) - 1))
    return make_candles(
        closes, start=str(start.tz_convert(None)), tf_seconds=tf_hours * 3600
    )


def by_position(strategy, candles):
    """The vote as it was before lookbacks were found by time: by counting bars. On a
    series with no gaps the two must agree."""
    close = candles["close"].to_numpy(dtype=float)
    votes, returns = 0, {}
    for key in ("lookback_1", "lookback_2", "lookback_3"):
        days = strategy.params[key]
        r = close[-1] / close[len(close) - 1 - strategy.bars(days)] - 1.0
        returns[f"return_{days}d"] = r
        votes += r > 0
    action = (
        Action.ENTER_LONG if votes >= strategy.params["min_agree"] else Action.EXIT_LONG
    )
    return action, returns


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
        gap = without(frame, days_back=(90,))
        self.assertEqual(create("STRAT-005").on_bar(gap).reason, "BARS_MISSING")

    def test_warm_up_needs_the_long_lookback(self):
        s = create("STRAT-005")
        self.assertEqual(s.warmup_bars, 366)
        self.assertEqual(s.on_bar(daily([100.0] * 365)).reason, "WARMUP")


class GapTests(unittest.TestCase):
    """Each lookback's reference bar is found by its open time: only a missing reference
    bar holds a decision, and no other bar, earlier or later, stands in."""

    def setUp(self):
        self.s = create("STRAT-005")
        self.frame = daily(voting_closes(1, -1, 1))
        self.full = self.s.on_bar(self.frame)
        self.assertEqual(self.full.action, Action.ENTER_LONG)

    def assert_same(self, frame, strategy=None, full=None):
        strategy, full = strategy or self.s, full or self.full
        got = strategy.on_bar(frame)
        self.assertEqual((got.action, got.reason), (full.action, full.reason))
        for key in ("return_30d", "return_90d", "return_365d"):
            self.assertAlmostEqual(got.indicators[key], full.indicators[key])

    def test_an_isolated_gap_away_from_the_references_changes_nothing(self):
        for d in (1, 29, 31, 50, 89, 91, 200, 364):
            with self.subTest(days_back=d):
                self.assert_same(without(self.frame, days_back=(d,)))

    def test_a_missing_reference_bar_holds(self):
        for d in (30, 90, 365):
            with self.subTest(days_back=d):
                gap = without(self.frame, days_back=(d,))
                self.assertEqual(self.s.on_bar(gap).reason, "BARS_MISSING")

    def test_consecutive_gaps(self):
        # 59 missing days between the 30- and 90-day references: no matter
        self.assert_same(without(self.frame, days_back=range(31, 90)))
        # the days either side of every reference missing, the references there
        around = [d + e for d in (30, 90, 365) for e in (-1, 1)]
        self.assert_same(without(self.frame, days_back=around))
        # a run of missing days over a reference holds
        run = without(self.frame, days_back=range(85, 96))
        self.assertEqual(self.s.on_bar(run).reason, "BARS_MISSING")

    def test_the_reference_is_the_bar_at_the_exact_open_time(self):
        last = self.frame["open_time"].iloc[-1]
        ref = last - pd.Timedelta(days=90)
        for shift in (pd.Timedelta(hours=1), -pd.Timedelta(hours=1)):
            with self.subTest(shift=shift):  # a bar an hour off is not the reference
                moved = self.frame.copy()
                moved.loc[moved["open_time"] == ref, "open_time"] = ref + shift
                self.assertEqual(self.s.on_bar(moved).reason, "BARS_MISSING")
        # a window that starts exactly at the 365-day reference decides
        edge = self.frame[self.frame["open_time"] >= last - pd.Timedelta(days=365)]
        edge = edge.reset_index(drop=True)
        self.assertEqual(len(edge), self.s.warmup_bars)
        self.assert_same(edge)
        # one day shorter: too few bars to start
        self.assertEqual(self.s.on_bar(edge.iloc[1:]).reason, "WARMUP")

    def test_a_gap_in_the_first_year_does_not_hold_a_complete_vote(self):
        """The warm-up is by time: candles from exactly 365 days back, with five days
        missing between, are fewer than ``warmup_bars`` but hold every reference."""
        last = self.frame["open_time"].iloc[-1]
        year = self.frame[self.frame["open_time"] >= last - pd.Timedelta(days=365)]
        short = without(
            year.reset_index(drop=True), days_back=(100, 150, 200, 250, 300)
        )
        self.assertLess(len(short), self.s.warmup_bars)
        self.assert_same(short)

    def test_a_later_bar_never_stands_in(self):
        closes = voting_closes(1, 1, 1) + random_walk(30, 9)
        frame = daily(closes)
        decision = frame["open_time"].iloc[399]
        gap = without(frame, times=[decision - pd.Timedelta(days=90)])
        k = int(np.flatnonzero(gap["open_time"] == decision)[0])
        runner = build_runner("STRAT-005")
        runner.set_timeframe(DAY)
        got = runner.evaluate(runner.window(gap, k), None, "X")
        self.assertEqual(got.reason, "BARS_MISSING")  # the 29 bars after it are no help

    def test_on_12h_and_4h_bars_only_a_missing_reference_holds(self):
        for tf_hours in (12, 4):
            with self.subTest(tf_hours=tf_hours):
                per_day = 24 // tf_hours
                closes = voting_closes(1, -1, 1, n=400 * per_day, per_day=per_day)
                frame = intraday(closes, tf_hours)
                s = create("STRAT-005")
                s.set_timeframe(tf_hours * 3600)
                full = s.on_bar(frame)
                self.assertEqual(full.action, Action.ENTER_LONG)
                last = frame["open_time"].iloc[-1]
                lone = [last - pd.Timedelta(days=50)]
                half_day = [
                    last - pd.Timedelta(days=200, hours=h)
                    for h in range(0, 12, tf_hours)
                ]
                for gone in (lone, half_day):
                    self.assert_same(without(frame, times=gone), s, full)
                ref = without(frame, times=[last - pd.Timedelta(days=30)])
                self.assertEqual(s.on_bar(ref).reason, "BARS_MISSING")
                beside = [last - pd.Timedelta(days=30, hours=tf_hours)]
                self.assert_same(without(frame, times=beside), s, full)

    def test_with_no_gaps_it_decides_as_by_counting_bars(self):
        """On complete daily, 12h and 4h series every decision is the one counting
        bars gave (the rule before lookbacks were found by time), and the warm-up ends
        on the same bar."""
        for tf_hours in (24, 12, 4):
            with self.subTest(tf_hours=tf_hours):
                per_day = 24 // tf_hours
                closes = random_walk((366 + 60) * per_day, tf_hours)
                frame = daily(closes) if tf_hours == 24 else intraday(closes, tf_hours)
                s = create("STRAT-005")
                s.set_timeframe(tf_hours * 3600)
                for i in (0, 1, s.warmup_bars // 2, s.warmup_bars - 2):
                    window = frame.iloc[: i + 1].reset_index(drop=True)
                    self.assertEqual(s.on_bar(window).reason, "WARMUP", i)
                checked = 0
                for i in range(s.warmup_bars - 1, len(frame)):
                    window = frame.iloc[: i + 1].reset_index(drop=True)
                    got = s.on_bar(window)
                    self.assertNotEqual(got.reason, "WARMUP", i)
                    if got.reason == "NOT_DECISION_DAY":
                        continue
                    action, returns = by_position(s, window)
                    self.assertEqual(got.action, action, i)
                    for key, value in returns.items():
                        self.assertAlmostEqual(got.indicators[key], value)
                    checked += 1
                self.assertGreaterEqual(checked, 8)


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

    def test_the_engine_and_the_runner_agree_with_gaps(self):
        frame = daily(random_walk(480, 5))
        frame = without(
            frame, times=list(frame["open_time"].iloc[[100, 230, 231, 400]])
        )
        present = set(frame["open_time"])
        settings = {"strategy": {"active_id": "STRAT-005", "timeframe": "1d"}}
        feed = DailyFeed(frame)
        engine = SignalEngine(settings, feed.provider, feed.clock)
        replay = build_runner("STRAT-005")
        replay.set_timeframe(DAY)
        reasons = set()
        for k in range(366, len(frame)):
            feed.set_after_bar(k)
            got = engine.decide("BTC", None)
            want = replay.evaluate(replay.window(frame, k), None, "BTC")
            self.assertEqual((got.action, got.reason), (want.action, want.reason), k)
            reasons.add(want.reason)
            if want.reason == "BARS_MISSING":  # only when a reference bar is missing
                t = frame["open_time"].iloc[k]
                refs = {t - pd.Timedelta(days=d) for d in (30, 90, 365)}
                self.assertFalse(refs <= present, k)
        self.assertTrue({"MOMENTUM_UP", "MOMENTUM_DOWN"} & reasons)

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
