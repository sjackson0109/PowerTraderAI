"""FDS-129: composable risk overlays (ratchet, ATR, progressive lock, cooldown)."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd
from helpers import Feed, PaperTraderCase, make_candles
from scripted import Scripted

import trading_mode as tm
from backtest import cli
from backtest.engine import CostModel, run_backtest
from backtest.kpis import KPI_KEYS
from signal_engine import SignalEngine
from strategies import ParamError, StrategyError, create
from strategies import indicators as ind
from strategies.base import Action
from strategies.catalogue import CATALOGUE, list_ids
from strategies.factory import build_runner
from strategies.overlays import AtrStop, EntryCooldown, ProgressiveLock, RatchetStop
from strategies.runner import PositionState, StrategyRunner

HERE = os.path.dirname(os.path.abspath(__file__))
BTC = os.path.join(HERE, "fixtures", "BTCUSDT_1h.csv")
ETH = os.path.join(HERE, "fixtures", "ETHUSDT_1h.csv")
ZERO = CostModel(0, 0)


def hold_runner(frame, *overlays, tf=3600):
    """A runner whose strategy never signals, so only the overlays decide."""
    runner = StrategyRunner(Scripted(frame, {}), list(overlays))
    runner.set_timeframe(tf)
    return runner


def drive(runner, frame, entry_bar, entry_price, bars=None):
    """Open a long at ``entry_bar`` and evaluate each following bar. Returns (pos, decisions)."""
    pos = runner.open_position("X", entry_price, frame["open_time"].iloc[entry_bar], runner.window(frame, entry_bar))
    out = []
    for i in range(entry_bar + 1, len(frame) if bars is None else entry_bar + 1 + bars):
        out.append((i, runner.evaluate(runner.window(frame, i), pos, "X")))
    return pos, out


def candles_from_closes(closes):
    return make_candles(closes, wick=0.0005)


class CatalogueTests(unittest.TestCase):
    def test_all_four_overlays_are_registered_as_risk_overlays(self):
        self.assertEqual(list_ids("risk_overlay"), ["OVL-ATR", "OVL-COOLDOWN", "OVL-PLOCK", "OVL-RATCHET"])
        for oid in list_ids("risk_overlay"):
            self.assertEqual(CATALOGUE[oid]["class_type"], "risk_overlay")

    def test_defaults_match_the_spec(self):
        self.assertEqual(create("OVL-RATCHET").params, {"trigger_pct": 2.0, "lock_pct": 0.5, "step_pct": 1.0})
        self.assertEqual(create("OVL-ATR").params, {"atr_len": 14, "mult": 2.5})
        self.assertEqual(create("OVL-PLOCK").params, {"stages": [[3, 1], [6, 3], [10, 6]]})
        self.assertEqual(create("OVL-COOLDOWN").params,
                         {"bars_after_exit": 3, "bars_after_loss": 12, "global": False})

    def test_bad_parameters_are_rejected(self):
        for oid, bad in (
            ("OVL-RATCHET", {"trigger_pct": 0}), ("OVL-RATCHET", {"step_pct": 0}),
            ("OVL-ATR", {"atr_len": 4}), ("OVL-ATR", {"mult": 0.1}), ("OVL-ATR", {"atr_len": 14.5}),
            ("OVL-PLOCK", {"stages": [[3, 1], [2, 1]]}), ("OVL-PLOCK", {"stages": []}),
            ("OVL-PLOCK", {"stages": [[3, 3]]}),
            ("OVL-COOLDOWN", {"bars_after_exit": -1}), ("OVL-COOLDOWN", {"bars_after_loss": 1.5}),
            ("OVL-COOLDOWN", {"global": "yes"}),
        ):
            with self.subTest(oid=oid, bad=bad), self.assertRaises(ParamError):
                create(oid, **bad)

    def test_ratchet_lock_must_be_below_trigger(self):
        with self.assertRaises(StrategyError):
            create("OVL-RATCHET", trigger_pct=2.0, lock_pct=2.0)

    def test_build_runner_attaches_overlays_by_id(self):
        runner = build_runner("STRAT-000", {}, [{"id": "OVL-ATR"}, {"id": "OVL-COOLDOWN", "params": {"global": True}}])
        self.assertEqual([o.overlay_id for o in runner.overlays], ["OVL-ATR", "OVL-COOLDOWN"])
        self.assertTrue(runner.overlays[1].params["global"])
        self.assertEqual(runner.lookback_bars, max(runner.strategy.lookback_bars, 70))


class RatchetTests(unittest.TestCase):
    CLOSES = [100, 101, 101.99, 102, 103, 104, 105, 106, 105.5, 104.5, 104.4, 103]

    def setUp(self):
        self.frame = candles_from_closes(self.CLOSES)
        self.overlay = create("OVL-RATCHET")  # trigger 2, lock 0.5, step 1
        self.runner = hold_runner(self.frame, self.overlay)
        self.pos, self.out = drive(self.runner, self.frame, 0, 100.0)
        self.by_bar = dict(self.out)

    def test_nothing_before_the_trigger(self):
        for i in (1, 2):  # gains 1.0% and 1.99%
            self.assertIsNone(self.by_bar[i].stop_price, i)

    def test_triggers_exactly_when_the_gain_reaches_trigger_pct(self):
        self.assertAlmostEqual(self.by_bar[3].stop_price, 100.5)  # gain 2.0% -> entry*(1+0.5%)

    def test_each_further_step_raises_the_stop_by_step_pct(self):
        want = {4: 101.5, 5: 102.5, 6: 103.5, 7: 104.5}  # gains 3,4,5,6% -> lock 1.5,2.5,3.5,4.5%
        for bar, stop in want.items():
            self.assertAlmostEqual(self.by_bar[bar].stop_price, stop, places=9, msg=f"bar {bar}")

    def test_the_stop_never_decreases_through_the_rally_and_pullback(self):
        stops = [d.stop_price for _, d in self.out if d.stop_price is not None]
        self.assertEqual(stops, sorted(stops))
        self.assertAlmostEqual(self.by_bar[8].stop_price, 104.5)  # pulled back, stop held
        self.assertAlmostEqual(self.by_bar[9].stop_price, 104.5)

    def test_exit_when_the_close_falls_below_the_stop_and_names_the_overlay(self):
        self.assertEqual(self.by_bar[9].action, Action.HOLD)  # 104.5 == stop: not below
        d = self.by_bar[10]  # 104.4 < 104.5
        self.assertEqual((d.action, d.exit_rule), (Action.EXIT_LONG, "stop:OVL-RATCHET"))

    def test_state_is_exposed_per_position(self):
        st = self.pos.overlay_state["OVL-RATCHET"]
        self.assertTrue(st["armed"])
        self.assertEqual(st["steps"], 4)

    def test_a_close_exactly_on_a_step_counts_despite_float_noise(self):
        for gain, steps in ((2.0, 0), (3.0, 1), (4.0, 2), (5.0, 3), (7.0, 5)):
            overlay = create("OVL-RATCHET")
            pos = PositionState("X", 100.0, pd.Timestamp("2026-01-01", tz="UTC"), 100.0 * (1 + gain / 100))
            d = overlay.on_bar(pos, self.frame)
            self.assertEqual(pos.overlay_state["OVL-RATCHET"]["steps"], steps, gain)

    def test_custom_parameters(self):
        o = RatchetStop(trigger_pct=1.0, lock_pct=0.2, step_pct=0.5)
        pos = PositionState("X", 200.0, pd.Timestamp("2026-01-01", tz="UTC"), 203.0)  # +1.5%
        d = o.on_bar(pos, self.frame)
        self.assertAlmostEqual(d.stop_price, 200 * (1 + (0.2 + 1 * 0.5) / 100))


class AtrTests(unittest.TestCase):
    def setUp(self):
        n = 130
        rally = np.linspace(100, 140, 70)
        pull = np.linspace(140, 125, n - 70)
        closes = np.concatenate([rally, pull])
        frame = make_candles(closes, wick=0.002)
        # widen the ranges steadily so ATR (and so the raw stop distance) grows
        grow = 1 + np.linspace(0, 1.5, n)
        frame["high"] = frame["close"] + (frame["high"] - frame["close"]).abs() * grow + 0.05 * grow
        frame["low"] = frame["close"] - (frame["close"] - frame["low"]).abs() * grow - 0.05 * grow
        self.frame = frame
        self.overlay = create("OVL-ATR", atr_len=14, mult=2.5)
        self.runner = hold_runner(frame, self.overlay)
        self.entry_bar = 40

    def expected_raw_stop(self, i, highest):
        w = self.runner.window(self.frame, i)
        a = float(ind.atr(w["high"], w["low"], w["close"], 14).iloc[-1])
        return highest - 2.5 * a

    def test_stop_tracks_highest_close_minus_mult_times_atr(self):
        entry_price = float(self.frame["close"].iloc[self.entry_bar])
        pos = self.runner.open_position("X", entry_price, self.frame["open_time"].iloc[self.entry_bar],
                                        self.runner.window(self.frame, self.entry_bar))
        highest = entry_price
        best = -np.inf
        for i in range(self.entry_bar + 1, len(self.frame)):
            highest = max(highest, float(self.frame["close"].iloc[i]))
            d = self.runner.evaluate(self.runner.window(self.frame, i), pos, "X")
            raw = self.expected_raw_stop(i, highest)
            best = max(best, raw)
            self.assertAlmostEqual(pos.current_stop, best, places=9, msg=f"bar {i}")
            self.assertAlmostEqual(pos.overlay_state["OVL-ATR"]["stop"], raw, places=9)

    def test_the_effective_stop_never_decreases_even_when_atr_widens(self):
        pos, out = drive(self.runner, self.frame, self.entry_bar,
                         float(self.frame["close"].iloc[self.entry_bar]))
        stops = [d.stop_price for _, d in out if d.stop_price is not None]
        self.assertGreater(len(stops), 30)
        self.assertEqual(stops, sorted(stops))
        raw = [pos.overlay_state["OVL-ATR"]["stop"]]
        # the raw (per-bar) stop did fall at some point while the effective stop held
        raws = []
        runner = hold_runner(self.frame, create("OVL-ATR", atr_len=14, mult=2.5))
        p = runner.open_position("X", float(self.frame["close"].iloc[self.entry_bar]),
                                 self.frame["open_time"].iloc[self.entry_bar], runner.window(self.frame, self.entry_bar))
        for i in range(self.entry_bar + 1, len(self.frame)):
            runner.evaluate(runner.window(self.frame, i), p, "X")
            raws.append(p.overlay_state["OVL-ATR"]["stop"])
        self.assertTrue(any(b < a for a, b in zip(raws, raws[1:])), "fixture must make the raw stop fall")

    def test_exit_names_the_atr_overlay_when_price_closes_below_the_stop(self):
        pos, out = drive(self.runner, self.frame, self.entry_bar, float(self.frame["close"].iloc[self.entry_bar]))
        exits = [(i, d) for i, d in out if d.action is Action.EXIT_LONG]
        self.assertTrue(exits, "the pullback should hit the trailing stop")
        i, d = exits[0]
        self.assertEqual(d.exit_rule, "stop:OVL-ATR")
        self.assertLess(float(self.frame["close"].iloc[i]), d.stop_price)

    def test_no_stop_until_enough_history_for_the_atr(self):
        short = self.frame.iloc[:10]
        runner = hold_runner(short, create("OVL-ATR"))
        pos, out = drive(runner, short, 2, 100.0)
        self.assertTrue(all(d.stop_price is None for _, d in out))

    def test_lookback_covers_atr_convergence(self):
        self.assertEqual(AtrStop(atr_len=20).lookback_bars, 100)


class ProgressiveLockTests(unittest.TestCase):
    def test_each_stage_engages_exactly_when_its_threshold_is_crossed(self):
        closes = [100, 102.99, 103, 105.99, 106, 109.99, 110, 120, 119]
        frame = candles_from_closes(closes)
        runner = hold_runner(frame, create("OVL-PLOCK"))  # [[3,1],[6,3],[10,6]]
        pos, out = drive(runner, frame, 0, 100.0)
        got = {i: (d.stop_price, pos_state) for (i, d), pos_state in zip(out, [None] * len(out))}
        stops = {i: d.stop_price for i, d in out}
        self.assertIsNone(stops[1])  # +2.99%: below stage 1
        self.assertAlmostEqual(stops[2], 101.0)  # +3.0%: stage 1 -> lock 1%
        self.assertAlmostEqual(stops[3], 101.0)  # +5.99%: still stage 1
        self.assertAlmostEqual(stops[4], 103.0)  # +6.0%: stage 2 -> lock 3%
        self.assertAlmostEqual(stops[5], 103.0)  # +9.99%
        self.assertAlmostEqual(stops[6], 106.0)  # +10%: stage 3 -> lock 6%
        self.assertAlmostEqual(stops[7], 106.0)  # +20%: no stage beyond the last
        self.assertAlmostEqual(stops[8], 106.0)  # pullback keeps the lock

    def test_stage_state_is_recorded(self):
        frame = candles_from_closes([100, 103, 106, 110])
        runner = hold_runner(frame, create("OVL-PLOCK"))
        pos, _ = drive(runner, frame, 0, 100.0)
        self.assertEqual(pos.overlay_state["OVL-PLOCK"]["stage"], 3)

    def test_a_pullback_through_the_locked_stop_exits_and_names_the_overlay(self):
        frame = candles_from_closes([100, 104, 107, 106, 102.5])
        runner = hold_runner(frame, create("OVL-PLOCK"))
        pos, out = drive(runner, frame, 0, 100.0)
        last_i, last = out[-1]
        # stage 2 lock at 103; close 102.5 < 103
        self.assertEqual((last.action, last.exit_rule), (Action.EXIT_LONG, "stop:OVL-PLOCK"))

    def test_stages_are_configurable(self):
        frame = candles_from_closes([100, 101, 102])
        o = ProgressiveLock(stages=[[1, 0.2], [2, 1.0]])
        pos, out = drive(hold_runner(frame, o), frame, 0, 100.0)
        self.assertAlmostEqual(out[0][1].stop_price, 100.2)
        self.assertAlmostEqual(out[1][1].stop_price, 101.0)


class CooldownTests(unittest.TestCase):
    def run_script(self, closes, script, **params):
        frame = candles_from_closes(closes)
        runner = StrategyRunner(Scripted(frame, script), [create("OVL-COOLDOWN", **params)])
        res = run_backtest(frame, runner, "X", "1h", cost=ZERO)
        return frame, res

    def enters_everywhere(self, first_enter, exit_bar, last):
        script = {first_enter: Action.ENTER_LONG, exit_bar: Action.EXIT_LONG}
        script.update({i: Action.ENTER_LONG for i in range(exit_bar + 1, last)})
        return script

    def test_after_a_winning_exit_entries_are_blocked_for_bars_after_exit(self):
        closes = [100, 100, 100, 101, 102, 103] + [104 + i * 0.1 for i in range(40)]
        frame, res = self.run_script(closes, self.enters_everywhere(2, 5, 45))
        t = list(frame["open_time"])
        self.assertEqual(res.trades[0].exit_time, t[6])  # exit signalled on 5 fills at 6 (a gain)
        self.assertGreater(res.trades[0].pnl, 0)
        # bars 6,7,8 are inside the 3-bar cooldown; bar 9 may enter and fills at bar 10
        self.assertEqual(res.trades[1].entry_time, t[10])

    def test_after_a_losing_exit_the_longer_bars_after_loss_applies(self):
        closes = [100, 100, 100, 99, 98, 97] + [96 - i * 0.1 for i in range(40)]
        frame, res = self.run_script(closes, self.enters_everywhere(2, 5, 45))
        t = list(frame["open_time"])
        self.assertLess(res.trades[0].pnl, 0)
        # blocked bars 6..17 (12 bars); first allowed signal bar 18 fills at 19
        self.assertEqual(res.trades[1].entry_time, t[19])

    def test_whichever_is_longer_wins(self):
        closes = [100, 100, 100, 99, 98, 97] + [96 - i * 0.1 for i in range(40)]
        _, res = self.run_script(closes, self.enters_everywhere(2, 5, 45), bars_after_exit=20, bars_after_loss=5)
        frame = candles_from_closes(closes)
        self.assertEqual(res.trades[1].entry_time, frame["open_time"].iloc[6 + 20 + 1])

    def test_zero_bars_means_no_cooldown(self):
        closes = [100, 100, 100, 101, 102, 103] + [104] * 20
        frame, res = self.run_script(closes, self.enters_everywhere(2, 5, 25), bars_after_exit=0, bars_after_loss=0)
        self.assertEqual(res.trades[1].entry_time, frame["open_time"].iloc[7])  # signal at bar 6 -> fills at 7

    def test_per_symbol_by_default_and_global_when_asked(self):
        t0 = pd.Timestamp("2026-01-01", tz="UTC")
        pos = PositionState("A", 100.0, t0, 100.0)
        for global_flag, other_blocked in ((False, False), (True, True)):
            o = create("OVL-COOLDOWN", **{"global": global_flag})
            o.bar_seconds = 3600
            o.on_exit(pos, t0 + pd.Timedelta(hours=10), 101.0)
            same = o.allow_entry("A", t0 + pd.Timedelta(hours=11))
            other = o.allow_entry("B", t0 + pd.Timedelta(hours=11))
            self.assertFalse(same.allowed)
            self.assertEqual(not other.allowed, other_blocked)

    def test_the_gate_reports_how_many_bars_remain_and_why(self):
        t0 = pd.Timestamp("2026-01-01", tz="UTC")
        o = create("OVL-COOLDOWN")
        o.bar_seconds = 3600
        loser = PositionState("A", 100.0, t0, 100.0)
        o.on_exit(loser, t0 + pd.Timedelta(hours=10), 90.0)
        gate = o.allow_entry("A", t0 + pd.Timedelta(hours=14))
        self.assertFalse(gate.allowed)
        self.assertIn("8 bar(s) left", gate.reason)  # 12 - 4
        self.assertIn("loss", gate.reason)
        self.assertTrue(o.allow_entry("A", t0 + pd.Timedelta(hours=22)).allowed)

    def test_needs_the_bar_length(self):
        t0 = pd.Timestamp("2026-01-01", tz="UTC")
        o = create("OVL-COOLDOWN")
        o.on_exit(PositionState("A", 1.0, t0, 1.0), t0, 2.0)
        with self.assertRaises(RuntimeError):
            o.allow_entry("A", t0 + pd.Timedelta(hours=1))

    def test_no_exit_yet_means_no_block_even_without_a_bar_length(self):
        o = create("OVL-COOLDOWN")
        self.assertTrue(o.allow_entry("A", pd.Timestamp("2026-01-01", tz="UTC")).allowed)

    def test_state_survives_export_and_import(self):
        t0 = pd.Timestamp("2026-01-01", tz="UTC")
        a = create("OVL-COOLDOWN")
        a.bar_seconds = 3600
        a.on_exit(PositionState("A", 100.0, t0, 100.0), t0 + pd.Timedelta(hours=10), 90.0)
        b = create("OVL-COOLDOWN")
        b.bar_seconds = 3600
        b.import_state(json.loads(json.dumps(a.export_state())))
        for h in (10, 13, 21, 22, 30):
            t = t0 + pd.Timedelta(hours=h)
            self.assertEqual(a.allow_entry("A", t).allowed, b.allow_entry("A", t).allowed, h)
        b.import_state({"garbage": 1})  # unreadable entries are ignored, not fatal


class CompositionTests(unittest.TestCase):
    def setUp(self):
        # a rally with a shallow early dip, a second leg, then a pullback
        closes = ([100 + 0.9 * i for i in range(6)] + [104, 103.2, 103.6, 104.4, 105.5, 106.8, 108.0, 109.5,
                  111.0, 112.5, 112.0, 111.5, 110.4, 109.0, 107.5, 106.0, 104.0, 102.0, 100.0])
        self.frame = make_candles(closes, wick=0.004)
        self.params = {
            "OVL-RATCHET": {"trigger_pct": 1.0, "lock_pct": 0.2, "step_pct": 0.5},
            "OVL-ATR": {"atr_len": 5, "mult": 2.0},
            "OVL-PLOCK": {"stages": [[2, 0.5], [4, 2.0], [8, 5.0]]},
        }

    def runner(self, ids):
        return hold_runner(self.frame, *[create(i, **self.params[i]) for i in ids])

    def test_effective_stop_is_the_max_and_the_exit_names_the_triggering_overlay(self):
        ids = ["OVL-RATCHET", "OVL-ATR", "OVL-PLOCK"]
        combined = self.runner(ids)
        singles = {i: self.runner([i]) for i in ids}
        entry_bar, entry = 5, float(self.frame["close"].iloc[5])
        tm_open = self.frame["open_time"].iloc[entry_bar]
        cpos = combined.open_position("X", entry, tm_open, combined.window(self.frame, entry_bar))
        spos = {i: r.open_position("X", entry, tm_open, r.window(self.frame, entry_bar)) for i, r in singles.items()}

        owners, exit_info = [], None
        running = {i: None for i in ids}
        for i in range(entry_bar + 1, len(self.frame)):
            d = combined.evaluate(combined.window(self.frame, i), cpos, "X")
            for oid, r in singles.items():
                r.evaluate(r.window(self.frame, i), spos[oid], "X")
                if spos[oid].current_stop is not None:
                    running[oid] = spos[oid].current_stop
            candidates = {k: v for k, v in running.items() if v is not None}
            if candidates:
                want = max(candidates.values())
                self.assertAlmostEqual(cpos.current_stop, want, places=9, msg=f"bar {i}")
                owners.append(cpos.stop_owner)
                self.assertAlmostEqual(candidates[cpos.stop_owner], want, places=9)
            if d.action is Action.EXIT_LONG:
                exit_info = (i, d)
                break

        self.assertGreaterEqual(len(set(owners)), 2, f"fixture should hand the stop between overlays: {owners}")
        self.assertIsNotNone(exit_info, "the pullback must hit the combined stop")
        i, d = exit_info
        self.assertTrue(d.exit_rule.startswith("stop:"))
        self.assertEqual(d.exit_rule, f"stop:{cpos.stop_owner}")
        self.assertLess(float(self.frame["close"].iloc[i]), cpos.current_stop)
        self.assertIn(f"STOP:{cpos.stop_owner}", d.reason)

    def test_the_combined_stop_never_decreases(self):
        runner = self.runner(["OVL-RATCHET", "OVL-ATR", "OVL-PLOCK"])
        pos, out = drive(runner, self.frame, 5, float(self.frame["close"].iloc[5]))
        stops = []
        for i, d in out:
            if d.stop_price is not None:
                stops.append(d.stop_price)
            if d.action is Action.EXIT_LONG:
                break
        self.assertEqual(stops, sorted(stops))

    def test_a_tighter_overlay_exits_earlier_than_a_looser_one_alone(self):
        def exit_bar(ids):
            r = self.runner(ids)
            _, out = drive(r, self.frame, 5, float(self.frame["close"].iloc[5]))
            return next((i for i, d in out if d.action is Action.EXIT_LONG), None)

        combined = exit_bar(["OVL-RATCHET", "OVL-ATR", "OVL-PLOCK"])
        for oid in ("OVL-RATCHET", "OVL-ATR", "OVL-PLOCK"):
            alone = exit_bar([oid])
            if alone is not None:
                self.assertLessEqual(combined, alone, f"adding overlays must never exit later than {oid} alone")

    def test_overlays_never_make_the_strategy_exit_later(self):
        frame = make_candles([100 + i for i in range(10)] + [110 - 2 * i for i in range(15)], wick=0.002)
        script = {1: Action.ENTER_LONG, 17: Action.EXIT_LONG}
        base = run_backtest(frame, StrategyRunner(Scripted(frame, script)), "X", "1h", cost=ZERO)
        with_ovl = run_backtest(
            frame, StrategyRunner(Scripted(frame, script), [create("OVL-RATCHET", trigger_pct=1, lock_pct=0.2, step_pct=0.5)]),
            "X", "1h", cost=ZERO)
        self.assertLessEqual(with_ovl.trades[0].exit_time, base.trades[0].exit_time)
        self.assertTrue(with_ovl.trades[0].exit_rule.startswith("stop:") or with_ovl.trades[0].exit_rule == "strategy")


class PersistenceTests(unittest.TestCase):
    def test_position_state_round_trips_through_json(self):
        pos = PositionState("BTC", 100.0, pd.Timestamp("2026-03-01 12:00", tz="UTC"), 107.5, 104.2, "OVL-ATR",
                            {"OVL-ATR": {"atr": 1.5, "stop": 104.2}, "OVL-RATCHET": {"armed": True, "steps": 3}})
        back = PositionState.from_dict(json.loads(json.dumps(pos.to_dict())))
        self.assertEqual(back, pos)

    def test_engine_state_file_survives_garbage_and_unreadable_positions(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "strategy_state.json")
            open(path, "w", encoding="utf-8").write("{ not json")
            engine = SignalEngine({"strategy": {"active_id": "STRAT-000"}})
            engine.attach_state(path)
            self.assertIsNone(engine.position("BTC"))
            open(path, "w", encoding="utf-8").write(json.dumps({"positions": {"BTC": {"symbol": "BTC"}}}))
            engine.attach_state(path)
            self.assertIsNone(engine.position("BTC"))

    def test_engine_saves_on_entry_exit_and_forget(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "strategy_state.json")
            engine = SignalEngine({"strategy": {"active_id": "STRAT-000"}})
            engine.attach_state(path)
            t = pd.Timestamp("2026-01-01", tz="UTC")
            engine.record_entry("BTC", 100.0, t)
            self.assertEqual(list(json.load(open(path))["positions"]), ["BTC"])
            engine.record_exit("BTC", 101.0, t)
            self.assertEqual(json.load(open(path))["positions"], {})
            engine.record_entry("BTC", 100.0, t)
            engine.forget("BTC")
            self.assertEqual(json.load(open(path))["positions"], {})


def wave(n=340):
    return 200 + 40 * np.sin(np.arange(n) / 22.0)


class TraderRestartTests(PaperTraderCase):
    """Acceptance 6: a trader restarted mid-position restores overlay state and the stop."""

    SETTINGS = {
        "trading": {"mode": "paper"},
        "strategy": {
            "active_id": "STRAT-001",
            "overlays": [
                {"id": "OVL-RATCHET", "params": {"trigger_pct": 0.5, "lock_pct": 0.1, "step_pct": 0.5}},
                {"id": "OVL-COOLDOWN"},
            ],
        },
    }

    def setUp(self):
        super().setUp()
        self.frame = make_candles(wave())
        self.feed = Feed(self.frame)
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def make_trader(self):
        settings = copy.deepcopy(self.SETTINGS)
        engine = SignalEngine(settings, self.feed.provider, self.feed.clock)
        trader = self.pt_trader.CryptoAPITrading(settings_source=settings, signal_engine=engine)
        trader._order_poll_seconds = 0.0
        return trader

    def tick(self, trader, k):
        self.feed.set_after_bar(k)
        # the paper quote follows the scripted candles, as the real feed would
        close = float(self.frame["close"].iloc[k])
        self.binance.bid, self.binance.ask = close * 0.9995, close * 1.0005
        tm._quote_cache.clear()
        trader.manage_trades()

    def status_position(self):
        with open(os.path.join(self.tmp.name, "paper", "trader_status.json")) as f:
            return json.load(f)["positions"].get("BTC", {})

    def test_overlay_state_and_stop_survive_a_restart_mid_position(self):
        trader1 = self.make_trader()
        for k in range(160, 290):
            self.tick(trader1, k)
            if trader1.signal_engine.position("BTC") is not None and \
                    trader1.signal_engine.position("BTC").current_stop is not None:
                break
        pos1 = trader1.signal_engine.position("BTC")
        self.assertIsNotNone(pos1, "the strategy should be long by now")
        self.assertIsNotNone(pos1.current_stop, "the ratchet should have armed")
        # let the stop move a few more bars, then 'crash'
        for k2 in range(k + 1, k + 6):
            self.tick(trader1, k2)
            if trader1.signal_engine.position("BTC") is None:
                break
        k_restart = k2
        pos1 = trader1.signal_engine.position("BTC")
        self.assertIsNotNone(pos1, "still long at the restart point")
        saved = copy.deepcopy(pos1.to_dict())

        trader2 = self.make_trader()  # a fresh process: new engine, same data dir
        pos2 = trader2.signal_engine.position("BTC")
        self.assertIsNotNone(pos2, "the open position must be restored")
        self.assertEqual(pos2.to_dict(), saved)
        self.assertEqual(pos2.current_stop, saved["current_stop"])
        self.assertEqual(pos2.stop_owner, saved["stop_owner"])
        self.assertEqual(pos2.overlay_state["OVL-RATCHET"], saved["overlay_state"]["OVL-RATCHET"])

        # keep trading with the restored state: the stop never moves down and the position closes
        stops = [saved["current_stop"]]
        for k3 in range(k_restart + 1, len(self.frame)):
            self.tick(trader2, k3)
            p = trader2.signal_engine.position("BTC")
            if p is None:
                break
            stops.append(p.current_stop)
        self.assertEqual(stops, sorted(stops))
        self.assertIsNone(trader2.signal_engine.position("BTC"), "the position should have been closed")
        sells = [r for r in self.ledger_rows() if r["side"] == "sell"]
        self.assertEqual(len(sells), 1)
        self.assertTrue(sells[0]["tag"].startswith("EXIT:"))
        with open(os.path.join(self.tmp.name, "paper", "strategy_state.json")) as f:
            self.assertEqual(json.load(f)["positions"], {})

    def test_cooldown_state_survives_a_restart(self):
        trader1 = self.make_trader()
        exit_k = None
        for k in range(160, len(self.frame)):
            self.tick(trader1, k)
            sells = [r for r in self.ledger_rows() if r["side"] == "sell"]
            if sells:
                exit_k = k
                break
        self.assertIsNotNone(exit_k, "the fixture should complete a round trip")
        saved = trader1.signal_engine._runner.export_state()["OVL-COOLDOWN"]
        self.assertTrue(saved, "the exit should have started a cooldown")

        trader2 = self.make_trader()
        self.feed.set_after_bar(exit_k)
        trader2.signal_engine.decide("BTC")  # builds the runner and imports saved state
        self.assertEqual(trader2.signal_engine._runner.export_state()["OVL-COOLDOWN"], saved)

    def test_status_reports_overlays_effective_stop_and_owner_for_the_hub(self):
        trader = self.make_trader()
        seen = None
        for k in range(160, len(self.frame)):
            self.tick(trader, k)
            p = trader.signal_engine.position("BTC")
            if p is not None and p.current_stop is not None:
                seen = self.status_position()
                break
        self.assertIsNotNone(seen)
        self.assertEqual(seen["overlays"], ["OVL-RATCHET", "OVL-COOLDOWN"])
        self.assertEqual(seen["stop_owner"], "OVL-RATCHET")
        self.assertAlmostEqual(seen["effective_stop"], trader.signal_engine.position("BTC").current_stop)
        self.assertIn("OVL-RATCHET", seen["overlay_state"])

    def test_per_cycle_log_names_the_stop_owner_and_overlay_state(self):
        import signal_engine as se

        trader = self.make_trader()
        logged = []
        with mock.patch.object(se.logger, "info", side_effect=lambda m, *a, **k: logged.append(str(m))):
            for k in range(160, len(self.frame)):
                self.tick(trader, k)
                p = trader.signal_engine.position("BTC")
                if p is not None and p.current_stop is not None:
                    self.tick(trader, k + 1)
                    break
        text = "\n".join(logged)
        self.assertIn("stop_owner=OVL-RATCHET", text)
        self.assertIn("overlay_state=", text)


class BacktestCliOverlayTests(unittest.TestCase):
    def run_cli(self, d, strategy, tf_path, tf, overlays=None, symbol="BTCUSDT"):
        out = os.path.join(d, f"{strategy}_{symbol}_{overlays or 'none'}.json".replace(",", "_"))
        argv = ["--strategy", strategy, "--symbol", symbol, "--tf", tf, "--candles-file", tf_path, "--out", out]
        if overlays:
            argv += ["--overlays", overlays]
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(argv)
        self.assertEqual(code, 0)
        return json.load(open(out, encoding="utf-8"))

    def test_runs_strat_001_and_strat_002_with_and_without_overlays(self):
        with tempfile.TemporaryDirectory() as d:
            for strategy in ("STRAT-001", "STRAT-002"):
                plain = self.run_cli(d, strategy, BTC, "1h")
                over = self.run_cli(d, strategy, BTC, "1h", "OVL-ATR,OVL-COOLDOWN")
                self.assertEqual(plain["overlays"], [])
                self.assertEqual([o["id"] for o in over["overlays"]], ["OVL-ATR", "OVL-COOLDOWN"])
                for res in (plain, over):
                    for sample in ("in_sample", "out_of_sample"):
                        for series in ("strategy", "buy_and_hold"):
                            self.assertEqual(set(res[sample][series]), set(KPI_KEYS))
                # the benchmark does not depend on overlays
                self.assertEqual(plain["in_sample"]["buy_and_hold"], over["in_sample"]["buy_and_hold"])
                self.assertEqual(plain["out_of_sample"]["buy_and_hold"], over["out_of_sample"]["buy_and_hold"])

    def test_overlays_actually_change_the_run_on_real_candles(self):
        with tempfile.TemporaryDirectory() as d:
            plain = self.run_cli(d, "STRAT-002", ETH, "1h", symbol="ETHUSDT")
            over = self.run_cli(d, "STRAT-002", ETH, "1h", "OVL-RATCHET,OVL-ATR,OVL-PLOCK", symbol="ETHUSDT")
            self.assertNotEqual(plain["in_sample"]["strategy"], over["in_sample"]["strategy"])

    def test_overlay_params_are_accepted_and_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["--strategy", "STRAT-000", "--candles-file", BTC, "--overlays", "OVL-ATR",
                                 "--overlay-params", '{"OVL-ATR": {"mult": 4.0}}', "--out", out])
            self.assertEqual(code, 0)
            res = json.load(open(out, encoding="utf-8"))
            self.assertEqual(res["overlays"], [{"id": "OVL-ATR", "params": {"mult": 4.0}}])

    def test_exit_rules_name_the_overlay_in_the_trades_csv(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_cli(d, "STRAT-002", ETH, "1h", "OVL-RATCHET,OVL-ATR,OVL-PLOCK", symbol="ETHUSDT")
            trades = pd.read_csv(os.path.join(d, "STRAT-002_ETHUSDT_OVL-RATCHET_OVL-ATR_OVL-PLOCK_trades.csv"))
            rules = set(trades.loc[trades["series"] == "strategy", "exit_rule"])
            self.assertTrue(any(r.startswith("stop:") for r in rules), rules)

    def test_a_bad_overlay_param_exits_2(self):
        with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["--strategy", "STRAT-000", "--candles-file", BTC, "--overlays", "OVL-ATR",
                             "--overlay-params", '{"OVL-ATR": {"mult": 99}}'])
        self.assertEqual(code, 2)
        self.assertIn("mult", err.getvalue())


if __name__ == "__main__":
    unittest.main()
