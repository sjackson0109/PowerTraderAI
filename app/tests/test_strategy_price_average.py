"""PTAI-RD-001 backlog 3.2: STRAT-006, long or cash by the price against its average.

* Hand-worked signals: a close above the average (that close included) enters, below
  exits, equal holds; the warm-up; the days in calendar days on 4-hour bars.
* No look-ahead: appending bars never changes an earlier decision, and the rule reads
  exactly the runner's window.
* Parity: the live signal engine and a replayed runner agree on every closed daily
  bar; the backtester fills at the next open.
* Research-only, in the momentum family, not enabled for research by default, refused
  for trading; described for the strategy list; an exploratory backtest runs it.

Synthetic candles only: no network, nothing about performance."""

from __future__ import annotations

import unittest

import numpy as np
from test_strategy_breakout import ZERO, DailyFeed, daily, random_walk, signal

from backtest.engine import run_backtest
from signal_engine import SignalEngine
from strategies import ParamError, create
from strategies import descriptions as words
from strategies.base import Action
from strategies.catalogue import CATALOGUE
from strategies.factory import build_runner
from strategies.settings import read_research_enabled, read_strategy_settings

DAY = 86_400


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.s = create("STRAT-006", average_days=5)

    def test_above_the_average_enters_below_exits_and_equal_holds(self):
        # the average of the last 5 closes includes the decision close
        self.assertEqual(
            signal(self.s, daily([10.0, 10.0, 10.0, 10.0, 11.0])),
            (Action.ENTER_LONG, "ABOVE_AVERAGE"),
        )
        self.assertEqual(
            signal(self.s, daily([10.0, 10.0, 10.0, 10.0, 9.0])),
            (Action.EXIT_LONG, "BELOW_AVERAGE"),
        )
        self.assertEqual(signal(self.s, daily([10.0] * 5)), (Action.HOLD, "AT_AVERAGE"))

    def test_only_the_average_days_count(self):
        frame = daily([1000.0] + [10.0, 12.0, 14.0, 16.0, 13.0])
        s = self.s.on_bar(frame)
        self.assertEqual(s.indicators["average"], 13.0)
        self.assertEqual(s.action, Action.HOLD)  # 13 is the average of 10..16, 13

    def test_warm_up_holds_until_the_average_is_full(self):
        self.assertEqual(self.s.warmup_bars, 5)
        self.assertEqual(signal(self.s, daily([10.0] * 4))[1], "WARMUP")
        self.assertEqual(signal(self.s, daily([10.0] * 5))[1], "AT_AVERAGE")

    def test_the_days_are_calendar_days_on_any_candles(self):
        s = create("STRAT-006")
        self.assertEqual((s.bars(20), s.warmup_bars, s.lookback_bars), (20, 20, 20))
        s.set_timeframe(4 * 3600)
        self.assertEqual(s.warmup_bars, 120)

    def test_bounds(self):
        for bad in ({"average_days": 4}, {"average_days": 201}):
            with self.assertRaises(ParamError):
                create("STRAT-006", **bad)
        with self.assertRaises(ParamError):
            create("STRAT-006", average_days=20.5)


class LookAheadTests(unittest.TestCase):
    def test_appending_bars_never_changes_an_earlier_decision(self):
        frame = daily(random_walk())
        runner = build_runner("STRAT-006", {"average_days": 30})
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
        runner = build_runner("STRAT-006")
        runner.set_timeframe(DAY)
        for i in (20, 120, 399):
            window = runner.window(frame, i)
            self.assertEqual(len(window), 20)
            altered = frame.copy()
            altered.loc[i - 20, "close"] = 1e9  # just before the window
            self.assertEqual(
                runner.evaluate(runner.window(altered, i), None, "X").action,
                runner.evaluate(window, None, "X").action,
            )


class ParityTests(unittest.TestCase):
    def test_the_signal_engine_and_a_replayed_runner_agree_on_every_bar(self):
        frame = daily(random_walk(300, seed=11))
        settings = {"strategy": {"active_id": "STRAT-006", "timeframe": "1d"}}
        feed = DailyFeed(frame)
        engine = SignalEngine(settings, feed.provider, feed.clock)
        replay = build_runner("STRAT-006")
        replay.set_timeframe(DAY)
        seen = set()
        for k in range(20, len(frame)):
            feed.set_after_bar(k)
            got = engine.decide("BTC", None)
            want = replay.evaluate(replay.window(frame, k), None, "BTC")
            self.assertIsNotNone(got, k)
            self.assertEqual((got.action, got.reason), (want.action, want.reason), k)
            self.assertEqual(got.bar_time, frame["open_time"].iloc[k])
            seen.add(want.action)
        # flat throughout: the runner turns EXIT into HOLD while no coin is held
        self.assertEqual(seen, {Action.ENTER_LONG, Action.HOLD})

    def test_the_backtester_fills_at_the_next_open(self):
        closes = [100.0] * 20 + [110.0, 111.0] + list(np.linspace(105, 80, 10))
        frame = daily(closes)
        result = run_backtest(frame, build_runner("STRAT-006"), "X", "1d", cost=ZERO)
        trade = result.trades[0]
        self.assertEqual(trade.entry_time, frame["open_time"].iloc[21])
        self.assertEqual(trade.entry_price, frame["open"].iloc[21])
        # the first close below its 20-day average exits at the next open
        k = next(
            i
            for i in range(21, len(closes))
            if closes[i] < np.mean(closes[i - 19 : i + 1])
        )
        self.assertEqual(trade.exit_time, frame["open_time"].iloc[k + 1])


class CatalogueTests(unittest.TestCase):
    def test_it_is_research_only_daily_and_in_the_momentum_family(self):
        e = CATALOGUE["STRAT-006"]
        self.assertEqual(e["authorisation"], "research")
        self.assertEqual(e["family"], "momentum")
        self.assertEqual(
            (e["timeframe_primary"], e["timeframes_permitted"]), ("1d", ["1d"])
        )
        self.assertEqual(e["default_params"], {"average_days": 20})

    def test_it_is_not_enabled_for_research_by_default(self):
        self.assertNotIn("STRAT-006", read_research_enabled({}))

    def test_it_is_refused_for_trading_in_both_modes(self):
        settings = {"strategy": {"active_id": "STRAT-006", "timeframe": "1d"}}
        self.assertIsNone(read_strategy_settings(settings).problem)
        for mode in ("paper", "live"):
            problem = read_strategy_settings(settings, mode).problem
            self.assertIn("STRAT-006 can be used for research only", problem)

    def test_it_is_described_for_the_strategy_list(self):
        d = words.DESCRIPTIONS["STRAT-006"]
        self.assertEqual(set(d.params), set(CATALOGUE["STRAT-006"]["default_params"]))
        for p in d.params.values():
            self.assertTrue(p.label and p.help)


def test_an_exploratory_backtest_runs_it(tmp_path, monkeypatch):
    from test_strategy_backtest_window import config, loader, venue

    from strategy_lab import experiment, runs

    monkeypatch.setattr(experiment, "lab_dir", lambda: str(tmp_path / "strategy_lab"))
    record = runs.run(
        config(strategy_id="STRAT-006", params={"average_days": 20}),
        loader=loader,
        venue=venue,
        save=False,
    )
    assert record["strategy"]["id"] == "STRAT-006"
    assert record["strategy_result"]["trades"] > 0


if __name__ == "__main__":
    unittest.main()
