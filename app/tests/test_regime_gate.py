"""FDS-SR-001 milestone M3c: OVL-REGIME and the entry gate's market context (sections
5.4.3, 5.6 and 12).

* ``slice_context`` gives only bars closed at or before the decision bar's close, and
  only as many as declared; a need with no bars is left out.
* The gate allows an entry only while the reference's last daily close is above its
  average; it fails closed with no, too few, stale or broken bars; it never exits.
* The existing overlays declare nothing and are called exactly as before.
* The backtester and the live engine give the gate the same closed bars, so their
  decisions agree on every bar; without context the backtester's gate blocks.
* The CLI loads the reference bars from the run's own source and records them.
* Research-only, not enabled, refused for trading; described.

Synthetic candles only: no network, nothing about performance."""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np
import pandas as pd
from helpers import make_candles

from backtest import cli
from backtest.engine import CostModel, run_backtest
from market_data.candles import SETTLE_SECONDS
from signal_engine import SignalEngine
from strategies import create
from strategies import descriptions as words
from strategies.base import Action
from strategies.catalogue import CATALOGUE
from strategies.factory import build_runner
from strategies.runner import Overlay, slice_context
from strategies.settings import read_research_enabled, read_strategy_settings

DAY = 86_400
HOUR = 3_600
ZERO = CostModel(0, 0)


def daily(closes, start="2024-01-01"):
    return make_candles(closes, start=start, tf_seconds=DAY)


def gate(**params):
    g = create("OVL-REGIME", **params)
    g.bar_seconds = DAY
    return g


class SliceTests(unittest.TestCase):
    def test_only_bars_closed_by_the_decision_count(self):
        frame = daily(list(range(1, 11)))  # opens 2024-01-01 .. 01-10
        # a 1-hour decision bar opening 2024-01-05 09:00 closes at 10:00: the daily
        # bar of 01-05 is still forming, so the last closed one is 01-04
        out = slice_context(
            {("BTC", "1d"): frame},
            [("BTC", "1d", 3)],
            pd.Timestamp("2024-01-05 10:00", tz="UTC"),
        )
        bars = out[("BTC", "1d")]
        self.assertEqual(list(bars["close"]), [2.0, 3.0, 4.0])
        # a daily decision bar of 01-05 closes at midnight: it is included
        out = slice_context(
            {("BTC", "1d"): frame},
            [("BTC", "1d", 2)],
            pd.Timestamp("2024-01-06", tz="UTC"),
        )
        self.assertEqual(list(out[("BTC", "1d")]["close"]), [4.0, 5.0])

    def test_a_need_without_bars_is_left_out(self):
        out = slice_context(
            {}, [("BTC", "1d", 5)], pd.Timestamp("2024-01-05", tz="UTC")
        )
        self.assertEqual(out, {})
        frame = daily([1.0, 2.0])
        out = slice_context(
            {("BTC", "1d"): frame},
            [("BTC", "1d", 5)],
            pd.Timestamp("2023-12-31", tz="UTC"),
        )
        self.assertEqual(out, {})


class GateTests(unittest.TestCase):
    def decide(self, closes, decision_open="last", **params):
        g = gate(**params)
        frame = daily(closes)
        when = (
            frame["open_time"].iloc[-1]
            if decision_open == "last"
            else pd.Timestamp(decision_open, tz="UTC")
        )
        context = slice_context(
            {(g.params["reference"], "1d"): frame},
            g.context_needs(),
            when + pd.Timedelta(days=1),
        )
        return g.allow_entry_in("ETH", when, context)

    def test_above_the_average_allows_and_otherwise_blocks(self):
        rising = list(np.linspace(100, 200, 60))
        self.assertTrue(self.decide(rising, sma_days=50).allowed)
        falling = list(np.linspace(200, 100, 60))
        result = self.decide(falling, sma_days=50)
        self.assertEqual((result.allowed, result.reason), (False, "BELOW_AVERAGE"))
        flat = [100.0] * 60  # equal to the average is not above it
        self.assertFalse(self.decide(flat, sma_days=50).allowed)

    def test_the_average_includes_the_last_close_and_only_sma_days(self):
        closes = [1000.0] + [100.0] * 49 + [101.0]
        self.assertTrue(self.decide(closes, sma_days=50).allowed)
        self.assertFalse(self.decide(closes, sma_days=51).allowed)

    def test_it_fails_closed(self):
        g = gate(sma_days=50)
        when = pd.Timestamp("2024-03-01", tz="UTC")
        for context in (None, {}):
            self.assertEqual(
                g.allow_entry_in("ETH", when, context).reason, "REFERENCE_UNAVAILABLE"
            )
        self.assertEqual(g.allow_entry("ETH", when).reason, "REFERENCE_UNAVAILABLE")
        short = self.decide(list(np.linspace(100, 200, 49)), sma_days=50)
        self.assertEqual(short.reason, "REFERENCE_UNAVAILABLE")
        # the reference's last daily close is 3 days before the decision: stale
        stale = self.decide(
            list(np.linspace(100, 200, 60)), decision_open="2024-03-03", sma_days=50
        )
        self.assertEqual(stale.reason, "REFERENCE_STALE")
        broken = list(np.linspace(100, 200, 60))
        broken[-5] = float("nan")
        self.assertEqual(
            self.decide(broken, sma_days=50).reason, "REFERENCE_UNAVAILABLE"
        )

    def test_it_declares_its_reference_and_never_exits(self):
        self.assertEqual(gate().context_needs(), (("BTC", "1d", 200),))
        self.assertEqual(
            gate(reference="self", sma_days=80).context_needs(), (("self", "1d", 80),)
        )
        decision = gate().on_bar(None, daily([1.0, 2.0]))
        self.assertIsNone(decision.stop_price)
        self.assertFalse(decision.exit_now)


class CompatibilityTests(unittest.TestCase):
    def test_existing_overlays_declare_nothing(self):
        for oid in ("OVL-RATCHET", "OVL-ATR", "OVL-PLOCK", "OVL-COOLDOWN"):
            self.assertEqual(create(oid).context_needs(), ())
        runner = build_runner("STRAT-000", overlays=[{"id": "OVL-COOLDOWN"}])
        self.assertEqual(runner.context_needs(), ())

    def test_an_overlay_with_only_allow_entry_is_called_as_before(self):
        calls = []

        class Old(Overlay):
            overlay_id = "OVL-COOLDOWN"  # borrows a registered id for its params

            def allow_entry(self, symbol, now_bar_time):
                calls.append(symbol)
                return super().allow_entry(symbol, now_bar_time)

        old = Old()
        self.assertTrue(
            old.allow_entry_in("BTC", pd.Timestamp("2024-01-01", tz="UTC"), {}).allowed
        )
        self.assertEqual(calls, ["BTC"])

    def test_the_runner_reports_the_gate_that_blocked(self):
        runner = build_runner(
            "STRAT-004",
            {"entry_days": 20, "exit_days": 10},
            [{"id": "OVL-REGIME", "params": {"reference": "self", "sma_days": 50}}],
        )
        runner.set_timeframe(DAY)
        frame = daily(list(np.linspace(200, 100, 60)) + [300.0])
        context = slice_context(
            {("self", "1d"): frame},
            runner.context_needs(),
            frame["open_time"].iloc[-1] + pd.Timedelta(days=1),
        )
        d = runner.evaluate(runner.window(frame, len(frame) - 1), None, "X", context)
        self.assertEqual(d.action, Action.ENTER_LONG)  # 300 is above the 50-day average
        frame = daily(list(np.linspace(100, 300, 60)) + [301.0])
        frame.loc[len(frame) - 1, "close"] = 301.0
        runner2 = build_runner(
            "STRAT-004",
            {"entry_days": 20, "exit_days": 10},
            [{"id": "OVL-REGIME", "params": {"reference": "BTC", "sma_days": 50}}],
        )
        runner2.set_timeframe(DAY)
        btc = daily(list(np.linspace(300, 100, 61)))
        context = slice_context(
            {("BTC", "1d"): btc},
            runner2.context_needs(),
            frame["open_time"].iloc[-1] + pd.Timedelta(days=1),
        )
        d = runner2.evaluate(runner2.window(frame, len(frame) - 1), None, "X", context)
        self.assertEqual(
            (d.action, d.reason),
            (Action.HOLD, "ENTRY_BLOCKED:OVL-REGIME:BELOW_AVERAGE"),
        )


def zigzag(n, seed):
    rng = np.random.default_rng(seed)
    return list(100 * np.exp(np.cumsum(rng.normal(0, 0.04, n))))


def waves(n, phase=0.0):
    """Rising waves: new closing highs and lows at known, regular intervals."""
    i = np.arange(n)
    return list(100 + 30 * np.sin(i / 12.0 + phase) + 0.15 * i)


class BacktestAndEngineTests(unittest.TestCase):
    def test_without_context_the_backtesters_gate_blocks_every_entry(self):
        frame = daily(waves(300))
        overlays = [
            {"id": "OVL-REGIME", "params": {"reference": "self", "sma_days": 50}}
        ]
        free = run_backtest(frame, build_runner("STRAT-004"), "X", "1d", cost=ZERO)
        self.assertGreater(len(free.trades), 0)
        gated = run_backtest(
            frame, build_runner("STRAT-004", overlays=overlays), "X", "1d", cost=ZERO
        )
        self.assertEqual(gated.trades, [])
        given = run_backtest(
            frame,
            build_runner("STRAT-004", overlays=overlays),
            "X",
            "1d",
            cost=ZERO,
            context_frames={("self", "1d"): frame},
        )
        self.assertLessEqual(len(given.trades), len(free.trades))
        self.assertGreater(len(given.trades), 0)

    def test_the_engine_and_a_replay_agree_on_every_hourly_bar(self):
        """STRAT-000 on 1-hour bars, gated by BTC's daily average."""
        hourly = make_candles(waves(24 * 75), start="2024-01-01", tf_seconds=HOUR)
        # BTC rises for 60 days, then falls below its 50-day average
        btc_daily = daily(
            list(np.linspace(100, 200, 60)) + list(np.linspace(195, 110, 15))
        )
        overlays = [
            {"id": "OVL-REGIME", "params": {"reference": "BTC", "sma_days": 50}}
        ]
        settings = {
            "strategy": {
                "active_id": "STRAT-000",
                "timeframe": "1h",
                "overlays": overlays,
            }
        }
        state = {"now": 0.0}

        def provider(symbol, tf, n, now):
            frame = hourly if tf == "1h" else btc_daily
            step = pd.Timedelta(seconds=HOUR if tf == "1h" else DAY)
            closed = frame[frame["open_time"] + step <= now]
            return closed.tail(n).reset_index(drop=True)

        engine = SignalEngine(settings, provider, lambda: state["now"])
        replay = build_runner("STRAT-000", overlays=overlays)
        replay.set_timeframe(HOUR)
        needs = replay.context_needs()
        reasons = set()
        for k in range(24 * 52, len(hourly)):
            close = hourly["open_time"].iloc[k] + pd.Timedelta(hours=1)
            state["now"] = close.timestamp() + SETTLE_SECONDS + 10  # once settled
            got = engine.decide("ETH", None)
            want = replay.evaluate(
                replay.window(hourly, k),
                None,
                "ETH",
                slice_context({("BTC", "1d"): btc_daily}, needs, close),
            )
            self.assertEqual((got.action, got.reason), (want.action, want.reason), k)
            reasons.add(want.reason)
        blocked = {r for r in reasons if r.startswith("ENTRY_BLOCKED:OVL-REGIME")}
        self.assertTrue(blocked, reasons)  # the gate decided some entries
        self.assertIn("FAST_CROSSED_ABOVE_SLOW", reasons)  # and allowed others

    def test_the_cli_loads_the_reference_from_the_runs_source(self):
        frame = daily(zigzag(320, 2))
        btc = daily(zigzag(320, 3))
        seen = []

        def fake(symbol, tf, start, end, **kw):
            seen.append((symbol, tf, kw.get("offline")))
            out = (btc if "BTC" in symbol else frame).copy()
            out.attrs.update(exchange="fake", pair=symbol)
            return out

        args = cli.build_parser().parse_args(
            [
                "--strategy",
                "STRAT-004",
                "--symbol",
                "ETH-USD",
                "--tf",
                "1d",
                "--start",
                "2024-01-01",
                "--end",
                "2024-11-15",
                "--overlays",
                "OVL-REGIME",
            ]
        )
        with mock.patch.object(cli, "exchange_candles", fake):
            results = cli.run(args)
        self.assertIn(("BTC-USD", "1d", False), seen)
        context = results["data"]["source"]["context"]["BTC:1d"]
        self.assertEqual((context["exchange"], context["bars"]), ("fake", 320))


class CatalogueTests(unittest.TestCase):
    def test_it_is_a_research_only_gate(self):
        e = CATALOGUE["OVL-REGIME"]
        self.assertEqual(
            (e["class_type"], e["family"], e["authorisation"]),
            ("risk_overlay", "regime", "research"),
        )
        self.assertEqual(e["data_requirements"], {"coins": "own+reference"})
        self.assertEqual(e["default_params"], {"reference": "BTC", "sma_days": 200})
        self.assertNotIn("OVL-REGIME", read_research_enabled({}))

    def test_it_is_refused_for_trading(self):
        settings = {"strategy": {"overlays": [{"id": "OVL-REGIME"}]}}
        self.assertIsNone(read_strategy_settings(settings).problem)
        for mode in ("paper", "live"):
            self.assertIn(
                "OVL-REGIME can be used for research only",
                read_strategy_settings(settings, mode).problem,
            )

    def test_it_is_described(self):
        d = words.DESCRIPTIONS["OVL-REGIME"]
        self.assertEqual(set(d.params), {"reference", "sma_days"})
        self.assertEqual(set(d.params["reference"].choices), {"BTC", "self"})


if __name__ == "__main__":
    unittest.main()
