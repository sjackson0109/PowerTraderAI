"""FDS-122: STRAT-001, the DEMA/TEMA trend crossover."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import numpy as np
from helpers import Feed, PaperTraderCase, make_candles

import trading_mode as tm
from backtest import cli
from backtest.engine import CostModel, run_backtest
from backtest.kpis import KPI_KEYS
from signal_engine import SignalEngine
from strategies import ParamError, StrategyError, create
from strategies import indicators as ind
from strategies.base import Action
from strategies.catalogue import CATALOGUE
from strategies.factory import build_runner
from strategies.runner import StrategyRunner
from strategies.settings import read_strategy_settings

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "BTCUSDT_1h.csv")
ZERO = CostModel(0, 0)
WARMUP = 3 * 48 + 14  # default STRAT-001


def wave_series(n=340):
    """A smooth wave: one golden cross (bar 229) and one death cross (bar 298) after the
    158-bar warm-up. SYNTHETIC. (TEMA is lag-free on a straight line, so a ramp would give
    degenerate crosses; a curved price gives realistic turning-point crosses.)"""
    return 200 + 40 * np.sin(np.arange(n) / 22.0)


def chop_series(n=420):
    """A sideways oscillation: lots of crosses, no trend (ADX about 15-18). SYNTHETIC."""
    return 100 + 3 * np.sin(np.arange(n) / 2.2)


def scan(strategy, frame):
    """Every bar's decision from the same windowed runner the backtester/trader use."""
    runner = StrategyRunner(strategy)
    return [strategy.on_bar(runner.window(frame, i)) for i in range(len(frame))]


def enter_bars(signals):
    return [i for i, s in enumerate(signals) if s.action is Action.ENTER_LONG]


def above_flags(frame, ma, fast_len, slow_len):
    fast, slow = ma(frame["close"], fast_len), ma(frame["close"], slow_len)
    return (fast > slow).to_numpy(), fast, slow


def up_crosses(above):
    return [i for i in range(1, len(above)) if above[i] and not above[i - 1]]


def reference_entries(above, persistence, warmup):
    """Independent restatement of the rule: in each maximal run of fast>slow that began at
    ``s`` (a fresh cross), ENTER on bar ``s + persistence`` if the run lasts that long and the
    strategy is past warm-up. At most one entry per run."""
    out, i, n = [], 1, len(above)
    while i < n:
        if above[i] and not above[i - 1]:
            j = i
            while j < n and above[j]:
                j += 1
            length = j - i
            if length >= persistence + 1 and i + persistence >= warmup - 1:
                out.append(i + persistence)
            i = j
        else:
            i += 1
    return out


class ConstructionTests(unittest.TestCase):
    def test_defaults_match_the_spec(self):
        s = create("STRAT-001")
        self.assertEqual(
            s.params,
            {"ma_type": "TEMA", "fast_len": 12, "slow_len": 48, "persistence_bars": 2,
             "regime_filter": "adx", "adx_len": 14, "adx_min": 20},
        )
        self.assertEqual(s.warmup_bars, WARMUP)

    def test_catalogue_entry(self):
        e = CATALOGUE["STRAT-001"]
        self.assertEqual((e["family"], e["class_type"], e["long_short_mode"], e["timeframe_primary"]),
                         ("trend", "main", "long_only", "1h"))
        self.assertEqual(e["param_bounds"]["slow_len"], {"min": 20, "max": 200})
        self.assertEqual(e["param_bounds"]["ma_type"], {"values": ["DEMA", "TEMA"]})

    def test_slow_not_greater_than_fast_is_rejected_with_a_clear_error(self):
        for fast, slow in ((30, 30), (40, 25)):
            with self.assertRaises(StrategyError) as ctx:
                create("STRAT-001", fast_len=fast, slow_len=slow)
            self.assertIn("slow_len", str(ctx.exception))
            self.assertIn("fast_len", str(ctx.exception))

    def test_out_of_bounds_parameters_are_rejected(self):
        for bad in ({"ma_type": "SMA"}, {"slow_len": 10}, {"slow_len": 300}, {"fast_len": 4},
                    {"persistence_bars": 6}, {"persistence_bars": -1}, {"regime_filter": "maybe"},
                    {"adx_len": 6}, {"adx_min": 5}, {"adx_min": 41}):
            with self.subTest(bad=bad), self.assertRaises(ParamError):
                create("STRAT-001", **bad)

    def test_warmup_depends_on_slow_len_and_adx_len(self):
        self.assertEqual(create("STRAT-001", slow_len=20, fast_len=5, adx_len=7).warmup_bars, 67)

    def test_it_is_the_default_active_strategy(self):
        self.assertEqual(read_strategy_settings({}).active_id, "STRAT-001")


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.frame = make_candles(wave_series())
        self.above, self.fast, self.slow = above_flags(self.frame, ind.tema, 12, 48)
        late = [c for c in up_crosses(self.above) if c >= WARMUP]
        self.assertEqual(len(late), 1, "fixture must have exactly one golden cross after warm-up")
        self.up = late[0]
        self.down = next(i for i in range(self.up + 1, len(self.frame)) if self.fast.iloc[i] < self.slow.iloc[i])

    def test_fixture_geometry(self):
        self.assertEqual((self.up, self.down), (229, 298))

    def test_enter_fires_exactly_on_the_bar_where_persistence_is_first_satisfied(self):
        for k in (0, 1, 2, 3, 5):
            with self.subTest(persistence_bars=k):
                s = create("STRAT-001", persistence_bars=k, regime_filter="none")
                self.assertEqual(enter_bars(scan(s, self.frame)), [self.up + k])

    def test_it_never_fires_before_persistence_is_satisfied(self):
        s = create("STRAT-001", persistence_bars=3, regime_filter="none")
        signals = scan(s, self.frame)
        for i in range(self.up, self.up + 3):
            self.assertEqual(signals[i].action, Action.HOLD, f"bar {i} is before persistence")
        self.assertEqual(signals[self.up + 3].action, Action.ENTER_LONG)

    def test_it_fires_once_not_on_every_bar_of_the_uptrend(self):
        s = create("STRAT-001", persistence_bars=2, regime_filter="none")
        signals = scan(s, self.frame)
        for i in range(self.up + 3, self.down):
            self.assertEqual(signals[i].action, Action.HOLD, f"stale state at bar {i}")
            self.assertEqual(signals[i].reason, "NO_FRESH_CROSS")

    def test_entries_match_an_independent_restatement_of_the_rule_on_a_choppy_market(self):
        # many short-lived crosses: a cross that does not persist must never enter
        frame = make_candles(chop_series())
        for ma_name, ma in (("TEMA", ind.tema), ("DEMA", ind.dema)):
            above, _, _ = above_flags(frame, ma, 12, 48)
            for k in (0, 1, 2, 4):
                with self.subTest(ma=ma_name, persistence_bars=k):
                    s = create("STRAT-001", ma_type=ma_name, persistence_bars=k, regime_filter="none")
                    got = enter_bars(scan(s, frame))
                    self.assertEqual(got, reference_entries(above, k, s.warmup_bars))
                    self.assertGreater(len(up_crosses(above)), len(got) or 1, "some crosses must be rejected" if k >= 2 else "")

    def test_a_cross_that_reverses_before_persistence_completes_never_enters(self):
        # tight persistence=5 on chop: the vast majority of crosses reverse first
        frame = make_candles(chop_series())
        above, _, _ = above_flags(frame, ind.tema, 12, 48)
        s = create("STRAT-001", persistence_bars=5, regime_filter="none")
        entries = enter_bars(scan(s, frame))
        for e in entries:
            self.assertTrue(above[e - 5 : e + 1].all() and not above[e - 6])

    def test_dema_variant_enters_on_the_same_kind_of_cross(self):
        above, _, _ = above_flags(self.frame, ind.dema, 12, 48)
        s = create("STRAT-001", ma_type="DEMA", persistence_bars=2, regime_filter="none")
        self.assertEqual(enter_bars(scan(s, self.frame)), reference_entries(above, 2, s.warmup_bars))
        self.assertTrue(enter_bars(scan(s, self.frame)))

    def test_indicators_are_reported_with_the_signal(self):
        s = create("STRAT-001", persistence_bars=2)
        sig = scan(s, self.frame)[self.up + 2]
        self.assertEqual(sig.action, Action.ENTER_LONG)
        for key in ("fast", "slow", "adx", "adx_min"):
            self.assertIn(key, sig.indicators)
        self.assertGreater(sig.indicators["fast"], sig.indicators["slow"])
        self.assertEqual(sig.reason, "TREND_CROSS_CONFIRMED")


class RegimeFilterTests(unittest.TestCase):
    def setUp(self):
        self.chop = make_candles(chop_series())

    def test_adx_below_min_blocks_every_entry_in_a_choppy_market(self):
        free = scan(create("STRAT-001", persistence_bars=1, regime_filter="none"), self.chop)
        self.assertGreaterEqual(len(enter_bars(free)), 3, "the chop fixture must cross repeatedly")

        signals = scan(create("STRAT-001", persistence_bars=1, regime_filter="adx", adx_min=20), self.chop)
        self.assertEqual(enter_bars(signals), [])
        blocked = [s for s in signals if s.reason == "ADX_BELOW_MIN"]
        self.assertGreaterEqual(len(blocked), 3)
        for s in blocked:
            self.assertLess(s.indicators["adx"], 20)

    def test_the_threshold_is_inclusive_and_every_entry_clears_it(self):
        adx = ind.adx(self.chop["high"], self.chop["low"], self.chop["close"], 14)
        lo, hi = float(adx.dropna().min()), float(adx.dropna().max())
        self.assertLess(hi, 20, "fixture assumption")
        mid = int((lo + hi) / 2)
        self.assertGreaterEqual(mid, 10)
        signals = scan(create("STRAT-001", persistence_bars=1, regime_filter="adx", adx_min=mid), self.chop)
        for s in signals:
            if s.action is Action.ENTER_LONG:
                self.assertGreaterEqual(s.indicators["adx"], mid)
            if s.reason == "ADX_BELOW_MIN":
                self.assertLess(s.indicators["adx"], mid)
        self.assertTrue(enter_bars(signals), "some entries should clear a threshold inside the ADX range")

    def test_a_strong_trend_passes_the_default_filter(self):
        frame = make_candles(wave_series())
        s = create("STRAT-001", persistence_bars=2, regime_filter="adx", adx_min=20)
        signals = scan(s, frame)
        (bar,) = enter_bars(signals)
        self.assertGreaterEqual(signals[bar].indicators["adx"], 20)

    def test_regime_filter_none_does_not_compute_or_require_adx(self):
        frame = make_candles(wave_series())
        sig = scan(create("STRAT-001", regime_filter="none"), frame)[231]
        self.assertNotIn("adx", sig.indicators)
        self.assertEqual(sig.action, Action.ENTER_LONG)

    def test_adx_filter_only_gates_entries_not_exits(self):
        frame = make_candles(wave_series())
        s = create("STRAT-001", persistence_bars=2, regime_filter="adx", adx_min=40)
        signals = scan(s, frame)
        self.assertEqual(signals[298].action, Action.EXIT_LONG)


class ExitTests(unittest.TestCase):
    def setUp(self):
        self.frame = make_candles(wave_series())
        self.strategy = create("STRAT-001", persistence_bars=2, regime_filter="none")
        self.signals = scan(self.strategy, self.frame)
        self.up, self.down = 229, 298

    def test_exit_fires_on_the_first_bar_fast_is_below_slow(self):
        self.assertEqual(self.signals[self.down].action, Action.EXIT_LONG)
        self.assertEqual(self.signals[self.down].reason, "FAST_BELOW_SLOW")
        for i in range(self.up, self.down):
            self.assertNotEqual(self.signals[i].action, Action.EXIT_LONG)

    def test_runner_closes_the_position_on_that_bar_via_the_strategy_rule(self):
        runner = StrategyRunner(self.strategy)
        entry = enter_bars(self.signals)[0]
        pos = runner.open_position("X", self.frame["close"].iloc[entry], self.frame["open_time"].iloc[entry], self.frame)
        exits = []
        for i in range(entry + 1, len(self.frame)):
            d = runner.evaluate(runner.window(self.frame, i), pos, "X")
            if d.action is Action.EXIT_LONG:
                exits.append((i, d.exit_rule))
                break
        self.assertEqual(exits, [(self.down, "strategy")])

    def test_exit_has_no_persistence_a_single_bar_below_is_enough(self):
        closes = list(wave_series()[: self.up + 20]) + [60.0]  # one crash bar mid-uptrend
        frame = make_candles(closes)
        s = create("STRAT-001", persistence_bars=2, regime_filter="none")
        signals = scan(s, frame)
        self.assertNotEqual(signals[-2].action, Action.EXIT_LONG)
        self.assertEqual(signals[-1].action, Action.EXIT_LONG)

    def test_the_backtest_round_trip_enters_after_persistence_and_exits_at_the_cross_back(self):
        runner = build_runner("STRAT-001", {"persistence_bars": 2, "regime_filter": "none"})
        res = run_backtest(self.frame, runner, "X", "1h", cost=ZERO)
        (trade,) = res.trades
        times = self.frame["open_time"]
        self.assertEqual(trade.entry_time, times.iloc[self.up + 2 + 1])  # signal bar + 1 = next open
        self.assertEqual(trade.exit_time, times.iloc[self.down + 1])
        self.assertEqual(trade.exit_rule, "strategy")


class WarmupTests(unittest.TestCase):
    def test_no_signal_during_warmup_even_with_an_obvious_cross(self):
        frame = make_candles(wave_series())
        s = create("STRAT-001", regime_filter="none", persistence_bars=0)
        self.assertEqual(s.warmup_bars, WARMUP)
        # the first golden cross (bar 90) sits inside the warm-up period
        self.assertLess(up_crosses(above_flags(frame, ind.tema, 12, 48)[0])[0], WARMUP)
        for k in range(1, s.warmup_bars):
            sig = s.on_bar(frame.iloc[:k])
            self.assertEqual((sig.action, sig.reason), (Action.HOLD, "WARMUP"), f"bars={k}")
        self.assertTrue(all(i >= WARMUP for i in enter_bars(scan(s, frame))))

    def test_signals_start_exactly_at_the_warmup_length(self):
        frame = make_candles(wave_series())
        s = create("STRAT-001", regime_filter="none")
        self.assertEqual(s.on_bar(frame.iloc[: s.warmup_bars - 1]).reason, "WARMUP")
        self.assertNotEqual(s.on_bar(frame.iloc[: s.warmup_bars]).reason, "WARMUP")


class BacktestOnRealCandlesTests(unittest.TestCase):
    def test_cli_runs_strat_001_on_cached_btcusdt_1h_candles_with_full_kpis(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli.main(["--strategy", "STRAT-001", "--symbol", "BTCUSDT", "--tf", "1h",
                                 "--candles-file", FIXTURE, "--out", out])
            self.assertEqual(code, 0)
            res = json.load(open(out, encoding="utf-8"))
        self.assertEqual(res["strategy_id"], "STRAT-001")
        self.assertEqual(res["params"]["ma_type"], "TEMA")
        for sample in ("in_sample", "out_of_sample"):
            for series in ("strategy", "buy_and_hold"):
                self.assertEqual(set(res[sample][series]), set(KPI_KEYS))
            self.assertIsNotNone(res[sample]["strategy"]["vs_buy_hold_pct"])

    def test_a_run_on_real_candles_is_deterministic(self):
        from market_data.candles import load_candles_csv

        frame = load_candles_csv(FIXTURE, "1h")
        a = run_backtest(frame, build_runner("STRAT-001"), "BTCUSDT", "1h")
        b = run_backtest(frame, build_runner("STRAT-001"), "BTCUSDT", "1h")
        self.assertEqual(a.equity, b.equity)
        self.assertEqual(a.kpis, b.kpis)


class PaperTraderTests(PaperTraderCase):
    """Acceptance 7: the paper trader runs STRAT-001 on a scripted fixture end to end."""

    def test_trader_enters_and_exits_on_strat_001_with_no_runtime_errors(self):
        frame = make_candles(wave_series())
        settings = {"trading": {"mode": "paper"}, "strategy": {"active_id": "STRAT-001"}}
        feed = Feed(frame)
        engine = SignalEngine(settings, feed.provider, feed.clock)
        feed.set_after_bar(160)
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        trader = self.pt_trader.CryptoAPITrading(settings_source=settings, signal_engine=engine)
        trader._order_poll_seconds = 0.0

        want_runner = build_runner("STRAT-001")
        pos, expected = None, []
        for i in range(len(frame)):
            d = want_runner.evaluate(want_runner.window(frame, i), pos, "BTC")
            if d.action is Action.ENTER_LONG and pos is None:
                pos = want_runner.open_position("BTC", frame["close"].iloc[i], d.bar_time, frame)
                expected.append((i, "buy"))
            elif d.action is Action.EXIT_LONG and pos is not None:
                pos = None
                expected.append((i, "sell"))
        self.assertEqual(expected, [(231, "buy"), (298, "sell")])

        acted = {}
        for k in range(160, len(frame)):
            feed.set_after_bar(k)
            before = len(tm.get_paper_exchange().account.orders)
            trader.manage_trades()
            orders = list(tm.get_paper_exchange().account.orders.values())
            if len(orders) > before:
                acted[k] = orders[-1].side.value
        self.assertEqual(acted, dict(expected))
        self.assertEqual([r["tag"] for r in self.ledger_rows()], ["ENTRY", "EXIT:strategy"])


if __name__ == "__main__":
    unittest.main()
