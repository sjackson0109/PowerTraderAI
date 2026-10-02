"""FDS-123: the Supertrend indicator and STRAT-002."""

from __future__ import annotations

import contextlib
import io
import json
import math
import os
import tempfile
import unittest
from fractions import Fraction
from unittest import mock

import numpy as np
import pandas as pd
from helpers import Feed, PaperTraderCase, make_candles

import trading_mode as tm
from backtest import cli
from backtest.engine import CostModel, run_backtest
from backtest.kpis import KPI_KEYS
from market_data.candles import load_candles_csv
from signal_engine import SignalEngine
from strategies import ParamError, create
from strategies import indicators as ind
from strategies.base import Action
from strategies.catalogue import CATALOGUE
from strategies.factory import build_runner
from strategies.runner import StrategyRunner

HERE = os.path.dirname(os.path.abspath(__file__))
BTC = os.path.join(HERE, "fixtures", "BTCUSDT_1h.csv")
ETH = os.path.join(HERE, "fixtures", "ETHUSDT_1h.csv")
ZERO = CostModel(0, 0)


# --- independent scalar reference ---------------------------------------------------------


def ref_atr(h, l, c, n):
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    out = [math.nan] * (n - 1) + [sum(tr[:n]) / n]
    for i in range(n, len(c)):
        out.append((out[-1] * (n - 1) + tr[i]) / n)
    return out


def ref_supertrend(h, l, c, atr_len, mult):
    """Straight from the definition in strategies.indicators.supertrend's docstring."""
    n = len(c)
    atr = ref_atr(h, l, c, atr_len)
    line, direction = [math.nan] * n, [math.nan] * n
    f_up, f_lo = [math.nan] * n, [math.nan] * n
    s = atr_len - 1
    hl2 = [(h[i] + l[i]) / 2 for i in range(n)]
    f_up[s], f_lo[s] = hl2[s] + mult * atr[s], hl2[s] - mult * atr[s]
    direction[s] = 1 if c[s] > hl2[s] else -1
    line[s] = f_lo[s] if direction[s] == 1 else f_up[s]
    for t in range(s + 1, n):
        b_up, b_lo = hl2[t] + mult * atr[t], hl2[t] - mult * atr[t]
        if direction[t - 1] == 1:
            f_lo[t], f_up[t] = max(b_lo, f_lo[t - 1]), b_up
            direction[t] = -1 if c[t] < f_lo[t - 1] else 1
        else:
            f_up[t], f_lo[t] = min(b_up, f_up[t - 1]), b_lo
            direction[t] = 1 if c[t] > f_up[t - 1] else -1
        line[t] = f_lo[t] if direction[t] == 1 else f_up[t]
    return line, direction, f_up, f_lo


def frame_from(h, l, c, o=None):
    o = o or [c[0]] + list(c[:-1])
    return pd.DataFrame(
        {"open_time": pd.date_range("2026-01-01", periods=len(c), freq="1h", tz="UTC"),
         "open": o, "high": h, "low": l, "close": c, "volume": 1.0}
    )


def wavy_ohlc(n=70):
    """Deterministic trend + wave with irregular wicks: both flip directions occur. SYNTHETIC."""
    c = [100 + 12 * math.sin(i / 4.0) + 0.1 * i for i in range(n)]
    h = [x + 0.8 + 0.1 * (i % 3) for i, x in enumerate(c)]
    l = [x - 0.9 - 0.15 * (i % 4) for i, x in enumerate(c)]
    return h, l, c


def assert_band_properties(tc, st, label=""):
    d, lo, up, line = (st[k].to_numpy() for k in ("direction", "final_lower", "final_upper", "line"))
    for t in range(1, len(d)):
        if np.isnan(d[t - 1]) or np.isnan(d[t]):
            continue
        if d[t - 1] > 0 and d[t] > 0:
            tc.assertGreaterEqual(lo[t], lo[t - 1] - 1e-12, f"{label}: lower band fell at bar {t} while direction was up")
        if d[t - 1] < 0 and d[t] < 0:
            tc.assertLessEqual(up[t], up[t - 1] + 1e-12, f"{label}: upper band rose at bar {t} while direction was down")
        tc.assertEqual(line[t], lo[t] if d[t] > 0 else up[t], f"{label}: line is the active band at bar {t}")


class HandComputedTests(unittest.TestCase):
    """An 8-bar case worked by hand with exact fractions (atr_len=3, mult=1)."""

    H = [10, 11, 12, 13, 12, 11, 10, 14]
    L = [8, 9, 10, 11, 9, 8, 7, 10]
    C = [9, 10, 11.5, 12, 9.8, 9, 8, 13]

    def setUp(self):
        self.st = ind.supertrend(frame_from(self.H, self.L, self.C), 3, 1.0)

    def test_atr_by_hand(self):
        # TR = 2,2,2,2,3,3,3,6 ; ATR2 = 2, ATR3 = 2, ATR4 = 7/3, ATR5 = 23/9, ATR6 = 73/27, ATR7 = 308/81
        want = [None, None, Fraction(2), Fraction(2), Fraction(7, 3), Fraction(23, 9), Fraction(73, 27), Fraction(308, 81)]
        for got, w in zip(self.st["atr"], want):
            if w is None:
                self.assertTrue(math.isnan(got))
            else:
                self.assertAlmostEqual(got, float(w), places=12)

    def test_directions_by_hand(self):
        # bar2 close 11.5 > hl2 11 -> up ; bar4 close 9.8 < lower[3]=10 -> down ; bar7 close 13 > upper[6] -> up
        want = [math.nan, math.nan, 1, 1, -1, -1, -1, 1]
        got = self.st["direction"].tolist()
        self.assertTrue(math.isnan(got[0]) and math.isnan(got[1]))
        self.assertEqual(got[2:], want[2:])

    def test_line_values_by_hand_to_1e_9(self):
        # bar2: lower = 11 - 2 = 9 ; bar3: lower = max(12 - 2, 9) = 10
        # bar4 (flip down): upper = 10.5 + 7/3 = 77/6 ; bar5: min(9.5 + 23/9, 77/6)
        # bar6: min(8.5 + 73/27, bar5) ; bar7 (flip up): lower = 12 - 308/81
        want = [
            None, None, Fraction(9), Fraction(10), Fraction(77, 6),
            Fraction(19, 2) + Fraction(23, 9), Fraction(17, 2) + Fraction(73, 27), 12 - Fraction(308, 81),
        ]
        for i, w in enumerate(want):
            if w is None:
                self.assertTrue(math.isnan(self.st["line"].iloc[i]))
            else:
                self.assertAlmostEqual(self.st["line"].iloc[i], float(w), places=9, msg=f"bar {i}")

    def test_the_lower_band_holds_at_10_even_after_the_flip_down_check(self):
        self.assertAlmostEqual(self.st["final_lower"].iloc[4], 10.0, places=12)  # max(8.1667, 10)

    def test_a_tie_is_not_a_flip(self):
        # bar 4's close exactly equal to the prior lower band (10) must NOT flip down
        c = list(self.C)
        c[4] = 10.0
        st = ind.supertrend(frame_from(self.H, self.L, c), 3, 1.0)
        self.assertEqual(st["direction"].iloc[4], 1)


class ReferenceTests(unittest.TestCase):
    def check(self, h, l, c, atr_len, mult):
        got = ind.supertrend(frame_from(h, l, c), atr_len, mult)
        line, direction, f_up, f_lo = ref_supertrend(h, l, c, atr_len, mult)
        for name, want in (("line", line), ("direction", direction), ("final_upper", f_up), ("final_lower", f_lo)):
            g = got[name].to_numpy(dtype=float)
            w = np.asarray(want, dtype=float)
            self.assertTrue(np.array_equal(np.isnan(g), np.isnan(w)), f"{name} NaN positions")
            m = ~np.isnan(w)
            np.testing.assert_allclose(g[m], w[m], rtol=0, atol=1e-6, err_msg=name)
        return direction

    def test_matches_the_reference_on_a_70_bar_fixture_with_flips_both_ways(self):
        h, l, c = wavy_ohlc(70)
        direction = self.check(h, l, c, 10, 3.0)
        d = [x for x in direction if not math.isnan(x)]
        flips_up = sum(1 for i in range(1, len(d)) if d[i] > 0 > d[i - 1])
        flips_down = sum(1 for i in range(1, len(d)) if d[i] < 0 < d[i - 1])
        self.assertGreaterEqual(flips_up, 1)
        self.assertGreaterEqual(flips_down, 1)

    def test_matches_the_reference_for_several_parameter_sets(self):
        h, l, c = wavy_ohlc(70)
        for atr_len, mult in ((5, 1.0), (7, 2.0), (10, 3.0), (14, 4.5), (30, 5.0)):
            with self.subTest(atr_len=atr_len, mult=mult):
                self.check(h, l, c, atr_len, mult)

    def test_matches_the_reference_on_real_candles(self):
        df = load_candles_csv(BTC, "1h").iloc[:600]
        self.check(df["high"].tolist(), df["low"].tolist(), df["close"].tolist(), 10, 3.0)

    def test_nan_before_the_first_valid_atr(self):
        st = ind.supertrend(frame_from(*wavy_ohlc(30)), 10, 3.0)
        self.assertEqual(int(st["line"].isna().sum()), 9)
        self.assertEqual(int(st["direction"].isna().sum()), 9)

    def test_too_short_input_is_all_nan_not_an_error(self):
        st = ind.supertrend(frame_from(*wavy_ohlc(5)), 10, 3.0)
        self.assertTrue(st["line"].isna().all())

    def test_does_not_use_future_bars(self):
        df = frame_from(*wavy_ohlc(70))
        full = ind.supertrend(df, 7, 2.0)
        for cut in (20, 35, 55):
            part = ind.supertrend(df.iloc[:cut], 7, 2.0)
            self.assertTrue(np.allclose(part["line"].to_numpy(), full["line"].iloc[:cut].to_numpy(), equal_nan=True))
            self.assertTrue(np.allclose(part["direction"].to_numpy(), full["direction"].iloc[:cut].to_numpy(), equal_nan=True))


class BandPropertyTests(unittest.TestCase):
    """Acceptance 2: the final lower band never decreases while the direction is up (and the
    upper never rises while down), over fixtures, real candles and many random walks."""

    def test_on_the_hand_and_70_bar_fixtures(self):
        assert_band_properties(self, ind.supertrend(frame_from(HandComputedTests.H, HandComputedTests.L, HandComputedTests.C), 3, 1.0), "hand")
        h, l, c = wavy_ohlc(70)
        for atr_len, mult in ((5, 1.0), (10, 3.0), (14, 5.0)):
            assert_band_properties(self, ind.supertrend(frame_from(h, l, c), atr_len, mult), f"wavy {atr_len}/{mult}")

    def test_on_cached_real_candles(self):
        for name, path in (("BTC", BTC), ("ETH", ETH)):
            df = load_candles_csv(path, "1h")
            for atr_len, mult in ((5, 1.5), (10, 3.0), (14, 4.0), (21, 2.5)):
                with self.subTest(symbol=name, atr_len=atr_len, mult=mult):
                    assert_band_properties(self, ind.supertrend(df, atr_len, mult), f"{name} {atr_len}/{mult}")

    def test_on_many_random_walks(self):
        rng = np.random.default_rng(2024)  # synthetic: only used to exercise the invariant
        for seed in range(40):
            n = 300
            c = 100 + np.cumsum(rng.normal(0, 1.0, n))
            spread = rng.uniform(0.1, 1.5, n)
            df = frame_from((c + spread).tolist(), (c - spread).tolist(), c.tolist())
            for atr_len, mult in ((5, 1.0), (10, 3.0), (20, 5.0)):
                assert_band_properties(self, ind.supertrend(df, atr_len, mult), f"seed {seed} {atr_len}/{mult}")

    def test_flips_follow_the_spec_rules_exactly(self):
        df = load_candles_csv(BTC, "1h")
        st = ind.supertrend(df, 10, 3.0)
        d, up, lo, c = st["direction"].to_numpy(), st["final_upper"].to_numpy(), st["final_lower"].to_numpy(), df["close"].to_numpy()
        flips = 0
        for t in range(10, len(d)):
            if d[t] > 0 > d[t - 1]:
                flips += 1
                self.assertGreater(c[t], up[t - 1], f"flip up at {t} needs close > prior final upper")
            elif d[t] < 0 < d[t - 1]:
                flips += 1
                self.assertLess(c[t], lo[t - 1], f"flip down at {t} needs close < prior final lower")
            else:
                if d[t - 1] < 0:
                    self.assertLessEqual(c[t], up[t - 1])  # no flip => close did not exceed it
                else:
                    self.assertGreaterEqual(c[t], lo[t - 1])
        self.assertGreater(flips, 10)


def expected_enters(st_direction, confirm, warmup):
    """Independent restatement: a bar where direction was down, turned up, and has stayed up
    ``confirm`` further bars; at most once per flip; nothing during warm-up."""
    d = st_direction
    out = []
    for f in range(1, len(d)):
        if d[f] > 0 > d[f - 1]:
            t = f + confirm
            if t < len(d) and all(d[k] > 0 for k in range(f, t + 1)) and t >= warmup - 1:
                out.append(t)
    return out


def scan(strategy, frame):
    runner = StrategyRunner(strategy)
    return [strategy.on_bar(runner.window(frame, i)) for i in range(len(frame))]


def waves(n=220, period=10.0, amp=20.0):
    """SYNTHETIC smooth swings; n stays below the strategy's lookback so window == full history."""
    return 200 + amp * np.sin(np.arange(n) / period)


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.frame = make_candles(waves())
        self.st = ind.supertrend(self.frame, 10, 3.0)
        self.direction = self.st["direction"].to_numpy()

    def test_defaults_and_catalogue_entry(self):
        s = create("STRAT-002")
        self.assertEqual(s.params, {"atr_len": 10, "mult": 3.0, "confirm_bars": 1})
        self.assertEqual(s.warmup_bars, 30)
        e = CATALOGUE["STRAT-002"]
        self.assertEqual((e["family"], e["class_type"], e["long_short_mode"], e["timeframe_primary"]),
                         ("trend", "main", "long_only", "4h"))
        self.assertEqual(e["param_bounds"], {"atr_len": {"min": 5, "max": 30},
                                              "mult": {"min": 1.0, "max": 5.0},
                                              "confirm_bars": {"min": 0, "max": 3}})

    def test_bounds_are_enforced(self):
        for bad in ({"atr_len": 4}, {"atr_len": 31}, {"mult": 0.9}, {"mult": 5.1},
                    {"confirm_bars": -1}, {"confirm_bars": 4}, {"atr_len": 10.5}, {"mult": "3"}):
            with self.subTest(bad=bad), self.assertRaises(ParamError):
                create("STRAT-002", **bad)

    def test_the_fixture_flips_both_ways_after_warmup(self):
        d = self.direction
        ups = [i for i in range(30, len(d)) if d[i] > 0 > d[i - 1]]
        downs = [i for i in range(30, len(d)) if d[i] < 0 < d[i - 1]]
        self.assertGreaterEqual(len(ups), 3)
        self.assertGreaterEqual(len(downs), 3)

    def test_enter_respects_confirm_bars(self):
        for confirm in (0, 1, 2, 3):
            with self.subTest(confirm_bars=confirm):
                s = create("STRAT-002", confirm_bars=confirm)
                got = [i for i, x in enumerate(scan(s, self.frame)) if x.action is Action.ENTER_LONG]
                self.assertEqual(got, expected_enters(self.direction, confirm, s.warmup_bars))
                self.assertTrue(got)

    def test_confirm_zero_enters_on_the_flip_bar_itself(self):
        s = create("STRAT-002", confirm_bars=0)
        signals = scan(s, self.frame)
        d = self.direction
        flip = next(i for i in range(30, len(d)) if d[i] > 0 > d[i - 1])
        self.assertEqual(signals[flip].action, Action.ENTER_LONG)
        self.assertEqual(signals[flip].reason, "SUPERTREND_FLIPPED_UP")

    def test_a_flip_that_reverses_inside_the_confirmation_window_never_enters(self):
        # whipsaw market + a tight band: many flips die within 1-2 bars
        frame = make_candles(100 + 10 * np.sin(np.arange(260) / 1.1), wick=0.01)
        d = ind.supertrend(frame, 5, 1.0)["direction"].to_numpy()
        s = create("STRAT-002", atr_len=5, mult=1.0, confirm_bars=3)
        got = [i for i, x in enumerate(scan(s, frame)) if x.action is Action.ENTER_LONG]
        self.assertEqual(got, expected_enters(d, 3, s.warmup_bars))
        flips_up = [i for i in range(1, len(d)) if d[i] > 0 > d[i - 1]]
        self.assertGreater(len(flips_up), len(got), "some flips must have been rejected for reversing early")
        for t in got:
            self.assertTrue((d[t - 3 : t + 1] > 0).all() and d[t - 4] < 0)

    def test_it_fires_once_per_flip_not_every_bar_of_the_uptrend(self):
        s = create("STRAT-002", confirm_bars=1)
        signals = scan(s, self.frame)
        enters = [i for i, x in enumerate(signals) if x.action is Action.ENTER_LONG]
        for a, b in zip(enters, enters[1:]):
            self.assertTrue(any(self.direction[k] < 0 for k in range(a, b)), "two entries without a down leg between")

    def test_exit_fires_on_the_flip_bar_and_every_bar_while_down(self):
        s = create("STRAT-002", confirm_bars=1)
        signals = scan(s, self.frame)
        d = self.direction
        for i in range(30, len(d)):
            if d[i] < 0:
                self.assertEqual(signals[i].action, Action.EXIT_LONG, i)
                self.assertEqual(signals[i].reason, "SUPERTREND_DOWN")
            else:
                self.assertNotEqual(signals[i].action, Action.EXIT_LONG, i)
        first_down = next(i for i in range(30, len(d)) if d[i] < 0 and d[i - 1] > 0)
        self.assertEqual(signals[first_down].action, Action.EXIT_LONG)

    def test_indicators_report_line_atr_and_direction(self):
        s = create("STRAT-002")
        sig = scan(s, self.frame)[100]
        for key in ("line", "atr", "direction", "close"):
            self.assertIn(key, sig.indicators)

    def test_no_signal_during_warmup(self):
        s = create("STRAT-002")
        for k in range(1, s.warmup_bars):
            sig = s.on_bar(self.frame.iloc[:k])
            self.assertEqual((sig.action, sig.reason), (Action.HOLD, "WARMUP"))
        self.assertNotEqual(s.on_bar(self.frame.iloc[: s.warmup_bars]).reason, "WARMUP")

    def test_the_runner_exits_via_the_strategy_rule_on_the_flip_bar(self):
        s = create("STRAT-002", confirm_bars=1)
        runner = StrategyRunner(s)
        d = self.direction
        entry = next(i for i, x in enumerate(scan(s, self.frame)) if x.action is Action.ENTER_LONG)
        pos = runner.open_position("X", self.frame["close"].iloc[entry], self.frame["open_time"].iloc[entry], self.frame)
        for i in range(entry + 1, len(self.frame)):
            dec = runner.evaluate(runner.window(self.frame, i), pos, "X")
            if dec.action is Action.EXIT_LONG:
                self.assertEqual(dec.exit_rule, "strategy")
                self.assertTrue(d[i] < 0 and d[i - 1] > 0)
                break
        else:
            self.fail("never exited")

    def test_backtest_round_trip_fills_at_the_next_open(self):
        runner = build_runner("STRAT-002", {"confirm_bars": 1})
        res = run_backtest(self.frame, runner, "X", "1h", cost=ZERO)
        self.assertGreaterEqual(len(res.trades), 2)
        times = list(self.frame["open_time"])
        for tr in res.trades[:-1]:
            ei, xi = times.index(tr.entry_time), times.index(tr.exit_time)
            self.assertGreater(self.direction[ei - 2], 0)  # signal bar (entry-1) had a confirmed up-flip behind it
            self.assertLess(self.direction[xi - 1], 0)  # signal bar (exit-1) is down
            self.assertEqual(tr.exit_rule, "strategy")


def resample_4h(csv_path, out_path):
    """Aggregate a cached 1h CSV to complete 4h bars (UTC-aligned, identical to exchange 4h)."""
    df = load_candles_csv(csv_path, "1h")
    g = df.groupby(df["open_time"].dt.floor("4h"))
    agg = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum"), n=("open", "size"))
    agg = agg[agg["n"] == 4].drop(columns="n").reset_index()
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    agg.insert(0, "open_time_ms", ((agg["open_time"] - epoch) // pd.Timedelta(milliseconds=1)).astype("int64"))
    agg.drop(columns="open_time").to_csv(out_path, index=False)
    return len(agg)


class CliTests(unittest.TestCase):
    def test_runs_btcusdt_and_ethusdt_at_1h_and_4h_with_full_kpis(self):
        with tempfile.TemporaryDirectory() as d:
            for symbol, path in (("BTCUSDT", BTC), ("ETHUSDT", ETH)):
                path4 = os.path.join(d, f"{symbol}_4h.csv")
                bars4 = resample_4h(path, path4)
                self.assertGreaterEqual(bars4, 370)
                for tf, candles in (("1h", path), ("4h", path4)):
                    with self.subTest(symbol=symbol, tf=tf):
                        out = os.path.join(d, f"{symbol}_{tf}.json")
                        with contextlib.redirect_stdout(io.StringIO()):
                            code = cli.main(["--strategy", "STRAT-002", "--symbol", symbol, "--tf", tf,
                                             "--candles-file", candles, "--out", out])
                        self.assertEqual(code, 0)
                        res = json.load(open(out, encoding="utf-8"))
                        self.assertEqual((res["strategy_id"], res["symbol"], res["timeframe"]),
                                         ("STRAT-002", symbol, tf))
                        for sample in ("in_sample", "out_of_sample"):
                            for series in ("strategy", "buy_and_hold"):
                                self.assertEqual(set(res[sample][series]), set(KPI_KEYS))
                            self.assertIsNotNone(res[sample]["strategy"]["vs_buy_hold_pct"])
                        self.assertTrue(os.path.isfile(os.path.join(d, f"{symbol}_{tf}_trades.csv")))

    def test_the_4h_fixture_is_a_faithful_aggregation(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.csv")
            resample_4h(BTC, p)
            h4 = load_candles_csv(p, "4h")
            h1 = load_candles_csv(BTC, "1h")
            first = h1.iloc[:4]
            self.assertEqual(h4["open"].iloc[0], first["open"].iloc[0])
            self.assertEqual(h4["high"].iloc[0], first["high"].max())
            self.assertEqual(h4["low"].iloc[0], first["low"].min())
            self.assertEqual(h4["close"].iloc[0], first["close"].iloc[-1])
            self.assertEqual(h4.attrs["report"].missing_bars, 0)


class PaperTraderTests(PaperTraderCase):
    """Acceptance 6: the paper trader runs STRAT-002 on a scripted fixture end to end (no network)."""

    def test_trader_follows_strat_002_through_several_round_trips(self):
        frame = make_candles(waves(n=170))
        settings = {"trading": {"mode": "paper"}, "strategy": {"active_id": "STRAT-002"}}
        feed = Feed(frame)
        engine = SignalEngine(settings, feed.provider, feed.clock)
        feed.set_after_bar(40)
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        trader = self.pt_trader.CryptoAPITrading(settings_source=settings, signal_engine=engine)
        trader._order_poll_seconds = 0.0

        # the trader starts flat at bar 40; replay the same decisions from there
        replay = build_runner("STRAT-002")
        pos, expected = None, {}
        for i in range(40, len(frame)):
            dec = replay.evaluate(replay.window(frame, i), pos, "BTC")
            if dec.action is Action.ENTER_LONG and pos is None:
                pos = replay.open_position("BTC", frame["close"].iloc[i], dec.bar_time, frame)
                expected[i] = "buy"
            elif dec.action is Action.EXIT_LONG and pos is not None:
                pos = None
                expected[i] = "sell"
        self.assertGreaterEqual(list(expected.values()).count("sell"), 2, "fixture must give several round trips")

        acted = {}
        for k in range(40, len(frame)):
            feed.set_after_bar(k)
            before = len(tm.get_paper_exchange().account.orders)
            trader.manage_trades()
            orders = list(tm.get_paper_exchange().account.orders.values())
            if len(orders) > before:
                acted[k] = orders[-1].side.value
        self.assertEqual(acted, expected)
        sides = [r["side"] for r in self.ledger_rows()]
        self.assertEqual(sides, list(expected.values()))


if __name__ == "__main__":
    unittest.main()
