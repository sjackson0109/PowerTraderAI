"""The shared decision core: composition rules (FDS-129 section 2) on stub overlays."""

from __future__ import annotations

import unittest

from helpers import make_candles
from scripted import Scripted, StubOverlay

from backtest.engine import CostModel, run_backtest
from strategies.base import Action
from strategies.runner import StrategyRunner

CLOSES = [100, 101, 102, 103, 104, 105, 104, 103, 102, 101, 100, 99, 98, 97, 96, 95, 94, 93, 92, 91]


def frame():
    return make_candles(CLOSES)


def evaluate_at(runner, f, i, pos, symbol="X"):
    return runner.evaluate(runner.window(f, i), pos, symbol)


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.f = frame()

    def runner(self, script=None, overlays=()):
        return StrategyRunner(Scripted(self.f, script or {}), list(overlays))

    def open_position(self, runner, i=3, price=103.0):
        return runner.open_position("X", price, self.f["open_time"].iloc[i], runner.window(self.f, i))

    def test_effective_stop_is_the_max_of_all_overlay_stops(self):
        a = StubOverlay("OVL-A", self.f, stops={4: 100.0})
        b = StubOverlay("OVL-B", self.f, stops={4: 102.0})
        c = StubOverlay("OVL-C", self.f, stops={4: 101.0})
        runner = self.runner(overlays=[a, b, c])
        pos = self.open_position(runner)
        d = evaluate_at(runner, self.f, 4, pos)
        self.assertEqual((d.action, d.stop_price, d.stop_owner), (Action.HOLD, 102.0, "OVL-B"))
        self.assertEqual((pos.current_stop, pos.stop_owner), (102.0, "OVL-B"))

    def test_stop_only_ever_moves_up_whichever_overlay_sets_it(self):
        a = StubOverlay("OVL-A", self.f, stops={4: 100.0, 5: 99.0, 6: 90.0})
        b = StubOverlay("OVL-B", self.f, stops={5: 100.5})
        runner = self.runner(overlays=[a, b])
        pos = self.open_position(runner)
        stops = []
        for i in (4, 5, 6):
            stops.append(evaluate_at(runner, self.f, i, pos).stop_price)
        self.assertEqual(stops, [100.0, 100.5, 100.5])  # never 99 or 90
        self.assertEqual(pos.stop_owner, "OVL-B")

    def test_close_below_the_stop_exits_and_names_the_owner(self):
        a = StubOverlay("OVL-A", self.f, stops={5: 104.5})
        runner = self.runner(overlays=[a])
        pos = self.open_position(runner)
        evaluate_at(runner, self.f, 5, pos)  # close 105 is above the 104.5 stop: hold
        self.assertEqual(pos.current_stop, 104.5)
        d = evaluate_at(runner, self.f, 7, pos)  # close 103 < 104.5: stopped out
        self.assertEqual(d.action, Action.EXIT_LONG)
        self.assertEqual(d.exit_rule, "stop:OVL-A")
        self.assertIn("STOP:OVL-A", d.reason)

    def test_overlay_exit_now_exits_and_names_the_overlay(self):
        a = StubOverlay("OVL-A", self.f, exit_now={6: "TIME_STOP"})
        runner = self.runner(overlays=[a])
        pos = self.open_position(runner)
        d = evaluate_at(runner, self.f, 6, pos)
        self.assertEqual((d.action, d.exit_rule), (Action.EXIT_LONG, "OVL-A"))
        self.assertIn("OVL-A:TIME_STOP", d.reason)

    def test_strategy_exit_is_recorded_as_strategy(self):
        runner = self.runner({8: Action.EXIT_LONG})
        pos = self.open_position(runner)
        d = evaluate_at(runner, self.f, 8, pos)
        self.assertEqual((d.action, d.exit_rule), (Action.EXIT_LONG, "strategy"))

    def test_when_several_rules_fire_the_overlay_is_named_first_and_all_are_listed(self):
        a = StubOverlay("OVL-A", self.f, stops={4: 110.0}, exit_now={8: "X"})
        runner = self.runner({8: Action.EXIT_LONG}, [a])
        pos = self.open_position(runner)
        evaluate_at(runner, self.f, 4, pos)
        d = evaluate_at(runner, self.f, 8, pos)
        self.assertEqual(d.exit_rule, "OVL-A")
        for part in ("OVL-A:X", "STOP:OVL-A", "STRATEGY:"):
            self.assertIn(part, d.reason)

    def test_entry_needs_the_strategy_and_every_overlay_gate(self):
        a = StubOverlay("OVL-A", self.f)
        b = StubOverlay("OVL-B", self.f, blocked={3: "COOLDOWN"})
        runner = self.runner({3: Action.ENTER_LONG, 4: Action.ENTER_LONG}, [a, b])
        blocked = evaluate_at(runner, self.f, 3, None)
        self.assertEqual(blocked.action, Action.HOLD)
        self.assertEqual(blocked.reason, "ENTRY_BLOCKED:OVL-B:COOLDOWN")
        allowed = evaluate_at(runner, self.f, 4, None)
        self.assertEqual(allowed.action, Action.ENTER_LONG)

    def test_an_overlay_cannot_enter_when_the_strategy_does_not(self):
        runner = self.runner({}, [StubOverlay("OVL-A", self.f)])
        self.assertEqual(evaluate_at(runner, self.f, 5, None).action, Action.HOLD)

    def test_flat_exit_and_long_enter_are_ignored(self):
        runner = self.runner({3: Action.EXIT_LONG, 5: Action.ENTER_LONG})
        flat = evaluate_at(runner, self.f, 3, None)
        self.assertEqual(flat.action, Action.HOLD)
        pos = self.open_position(runner, 4)
        long_ = evaluate_at(runner, self.f, 5, pos)
        self.assertEqual((long_.action, long_.reason), (Action.HOLD, "HOLDING"))

    def test_highest_close_since_entry_is_tracked(self):
        runner = self.runner()
        pos = self.open_position(runner, 3, 103.0)
        for i in range(4, 10):
            evaluate_at(runner, self.f, i, pos)
        self.assertEqual(pos.highest_close, 105.0)

    def test_overlays_are_told_about_entries_and_exits(self):
        a = StubOverlay("OVL-A", self.f)
        runner = self.runner({3: Action.ENTER_LONG, 8: Action.EXIT_LONG}, [a])
        res = run_backtest(self.f, runner, "X", "1h", cost=CostModel(0, 0))
        self.assertEqual(len(res.trades), 1)
        self.assertEqual(len(a.exits_seen), 1)
        self.assertEqual(a.exits_seen[0][0], self.f["open_time"].iloc[9])  # exit executes at bar 9 open

    def test_decision_carries_bar_time_and_strategy_id(self):
        runner = self.runner()
        d = evaluate_at(runner, self.f, 5, None)
        self.assertEqual(d.bar_time, self.f["open_time"].iloc[5])
        self.assertEqual(d.strategy_id, "T-SCRIPT")

    def test_lookback_is_the_largest_any_component_needs(self):
        a = StubOverlay("OVL-A", self.f)
        runner = self.runner(overlays=[a])
        self.assertEqual(runner.lookback_bars, 50)


if __name__ == "__main__":
    unittest.main()
