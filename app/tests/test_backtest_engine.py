"""FDS-121 acceptance 2-4: lookahead, fills + costs, buy-and-hold, split, warm-up, KPIs."""

from __future__ import annotations

import json
import math
import unittest

import numpy as np
import pandas as pd
from helpers import make_candles
from scripted import Scripted

from backtest.engine import (
    CostModel,
    buy_and_hold,
    evaluate_split,
    run_backtest,
    split_index,
)
from backtest.kpis import KPI_KEYS, compute_kpis
from strategies import create
from strategies.base import Action
from strategies.runner import StrategyRunner

ZERO = CostModel(fee_bps=0, slippage_bps=0)


def stepped(n, base=100.0, drift=1.0, up=0.5):
    """opens 100, 101, ... and closes open+0.5 (synthetic, for exact fill arithmetic)."""
    opens = [base + drift * i for i in range(n)]
    closes = [o + up for o in opens]
    return make_candles(closes, opens=opens)


def runner_for(frame, script, warmup=1):
    return StrategyRunner(Scripted(frame, script, warmup))


def wavy(n=400):
    """Deterministic trend + two sine waves: lots of EMA crosses (SYNTHETIC)."""
    x = np.arange(n)
    return make_candles(1000 + 0.8 * x + 40 * np.sin(x / 9.0) + 15 * np.sin(x / 3.1))


class FillTests(unittest.TestCase):
    def test_signal_at_t_fills_at_the_next_bar_open_with_fees_and_slippage(self):
        frame = stepped(20)
        runner = runner_for(frame, {5: Action.ENTER_LONG, 9: Action.EXIT_LONG})
        cost = CostModel(fee_bps=10, slippage_bps=5)
        res = run_backtest(
            frame, runner, "BTCUSDT", "1h", cost=cost, initial_equity=10_000
        )

        (trade,) = res.trades
        open6, open10 = 106.0, 110.0  # bar t+1 opens (t = 5 and 9)
        entry_fill = open6 * (1 + 0.0005)
        exit_fill = open10 * (1 - 0.0005)
        self.assertEqual(trade.entry_time, frame["open_time"].iloc[6])
        self.assertEqual(trade.exit_time, frame["open_time"].iloc[10])
        self.assertAlmostEqual(trade.entry_price, entry_fill, places=9)
        self.assertAlmostEqual(trade.exit_price, exit_fill, places=9)
        entry_fee = 10_000 * 0.001
        qty = (10_000 - entry_fee) / entry_fill
        self.assertAlmostEqual(trade.qty, qty, places=9)
        gross = qty * exit_fill
        exit_fee = gross * 0.001
        self.assertAlmostEqual(trade.fees, entry_fee + exit_fee, places=9)
        self.assertAlmostEqual(trade.pnl, gross - exit_fee - 10_000, places=9)
        self.assertAlmostEqual(res.equity[-1], 10_000 + trade.pnl, places=9)
        self.assertEqual(trade.exit_rule, "strategy")
        self.assertFalse(trade.forced_close)

    def test_fill_price_is_never_the_signal_bars_close(self):
        frame = stepped(20)
        res = run_backtest(
            frame,
            runner_for(frame, {5: Action.ENTER_LONG, 9: Action.EXIT_LONG}),
            "X",
            "1h",
            cost=ZERO,
        )
        self.assertEqual(
            res.trades[0].entry_price, 106.0
        )  # bar 6 open, not bar 5 close (105.5)
        self.assertEqual(res.trades[0].exit_price, 110.0)

    def test_zero_cost_round_trip_is_exact(self):
        frame = stepped(20)
        res = run_backtest(
            frame,
            runner_for(frame, {5: Action.ENTER_LONG, 9: Action.EXIT_LONG}),
            "X",
            "1h",
            cost=ZERO,
            initial_equity=10_000,
        )
        self.assertAlmostEqual(res.equity[-1], 10_000 / 106.0 * 110.0, places=8)

    def test_costs_are_applied_to_every_fill_and_reduce_the_result(self):
        frame = stepped(20)
        script = {
            5: Action.ENTER_LONG,
            9: Action.EXIT_LONG,
            12: Action.ENTER_LONG,
            15: Action.EXIT_LONG,
        }
        free = run_backtest(frame, runner_for(frame, script), "X", "1h", cost=ZERO)
        paid = run_backtest(
            frame, runner_for(frame, script), "X", "1h", cost=CostModel(10, 5)
        )
        self.assertEqual(len(paid.trades), 2)
        self.assertLess(paid.equity[-1], free.equity[-1])
        self.assertAlmostEqual(
            paid.fees_paid, sum(t.fees for t in paid.trades), places=9
        )
        self.assertGreater(paid.slippage_cost, 0)

    def test_size_fraction_commits_only_part_of_equity(self):
        frame = stepped(20)
        script = {5: Action.ENTER_LONG, 9: Action.EXIT_LONG}
        res = run_backtest(
            frame,
            runner_for(frame, script),
            "X",
            "1h",
            cost=CostModel(0, 0, size_fraction=0.5),
            initial_equity=10_000,
        )
        self.assertAlmostEqual(res.trades[0].qty, 5_000 / 106.0, places=9)
        self.assertAlmostEqual(res.equity[-1], 5_000 + 5_000 / 106.0 * 110.0, places=8)

    def test_signals_on_the_last_bar_cannot_fill(self):
        frame = stepped(10)
        res = run_backtest(
            frame, runner_for(frame, {9: Action.ENTER_LONG}), "X", "1h", cost=ZERO
        )
        self.assertEqual(res.trades, [])

    def test_position_open_at_the_end_is_closed_at_the_final_close_with_costs(self):
        frame = stepped(12)
        cost = CostModel(10, 5)
        res = run_backtest(
            frame, runner_for(frame, {3: Action.ENTER_LONG}), "X", "1h", cost=cost
        )
        (trade,) = res.trades
        self.assertTrue(trade.forced_close)
        self.assertEqual(trade.exit_rule, "end_of_data")
        self.assertEqual(trade.exit_time, frame["open_time"].iloc[-1])
        self.assertAlmostEqual(
            trade.exit_price, frame["close"].iloc[-1] * (1 - 0.0005), places=9
        )

    def test_enter_while_long_and_exit_while_flat_are_ignored(self):
        frame = stepped(20)
        script = {
            3: Action.EXIT_LONG,
            5: Action.ENTER_LONG,
            6: Action.ENTER_LONG,
            9: Action.EXIT_LONG,
        }
        res = run_backtest(frame, runner_for(frame, script), "X", "1h", cost=ZERO)
        self.assertEqual(len(res.trades), 1)
        self.assertEqual(res.trades[0].entry_time, frame["open_time"].iloc[6])


class NoLookaheadTests(unittest.TestCase):
    def setUp(self):
        self.frame = wavy(400)
        self.strategy = create("STRAT-000", fast_len=3, slow_len=8)

    def runner(self):
        return StrategyRunner(create("STRAT-000", fast_len=3, slow_len=8))

    def test_mutating_bars_after_t_does_not_change_the_decision_at_t(self):
        rng = np.random.default_rng(11)  # garbage future data
        runner = self.runner()
        for t in range(runner.strategy.warmup_bars, 399, 7):
            before = runner.evaluate(runner.window(self.frame, t), None, "X")
            mutated = self.frame.copy()
            for col in ("open", "high", "low", "close"):
                mutated.loc[t + 1 :, col] = rng.uniform(1, 5000, len(mutated) - t - 1)
            after = runner.evaluate(runner.window(mutated, t), None, "X")
            self.assertEqual(
                (before.action, before.reason, before.indicators),
                (after.action, after.reason, after.indicators),
                f"decision at bar {t} changed when later bars changed",
            )

    def test_window_never_contains_bars_after_the_decision_bar(self):
        runner = self.runner()
        for t in (10, 50, 399):
            w = runner.window(self.frame, t)
            self.assertEqual(w["open_time"].iloc[-1], self.frame["open_time"].iloc[t])

    def test_backtest_trades_before_a_cut_are_unaffected_by_later_data(self):
        full = run_backtest(self.frame, self.runner(), "X", "1h", cost=CostModel())
        cut = 200
        mutated = self.frame.copy()
        for col in ("open", "high", "low", "close"):
            mutated.loc[cut + 1 :, col] = 123.0
        other = run_backtest(mutated, self.runner(), "X", "1h", cost=CostModel())
        cut_time = self.frame["open_time"].iloc[cut]
        a = [t for t in full.trades if t.exit_time <= cut_time and not t.forced_close]
        b = [t for t in other.trades if t.exit_time <= cut_time and not t.forced_close]
        self.assertGreater(
            len(a), 2, "fixture should trade several times before the cut"
        )
        self.assertEqual(
            [(t.entry_time, t.exit_time, t.entry_price, t.exit_price) for t in a],
            [(t.entry_time, t.exit_time, t.entry_price, t.exit_price) for t in b],
        )
        self.assertEqual(full.equity[:cut], other.equity[:cut])


class WarmupTests(unittest.TestCase):
    def test_strategy_holds_during_warmup_even_if_a_cross_occurs(self):
        # a clean golden cross at bar 10, long before STRAT-000(3,6) has 18 bars
        closes = [100.0] * 10 + [100 + 5 * k for k in range(1, 40)]
        frame = make_candles(closes)
        strategy = create("STRAT-000", fast_len=3, slow_len=6)
        self.assertEqual(strategy.warmup_bars, 18)
        for k in range(1, 18):
            sig = strategy.on_bar(frame.iloc[:k])
            self.assertEqual((sig.action, sig.reason), (Action.HOLD, "WARMUP"))

    def test_no_position_is_opened_before_warmup_completes(self):
        closes = [100.0] * 10 + [100 + 5 * k for k in range(1, 60)]
        frame = make_candles(closes)
        runner = StrategyRunner(create("STRAT-000", fast_len=3, slow_len=6))
        res = run_backtest(frame, runner, "X", "1h", cost=ZERO)
        # the cross at bar 11 is inside warm-up (needs 18 bars): nothing may be bought
        # on the strength of it; a later EMA state may not enter either (no new cross)
        for trade in res.trades:
            entry_index = int(frame.index[frame["open_time"] == trade.entry_time][0])
            self.assertGreaterEqual(entry_index, runner.strategy.warmup_bars)

    def test_the_backtester_enforces_warmup_through_the_strategy_contract(self):
        frame = stepped(40)
        runner = runner_for(
            frame,
            {
                2: Action.ENTER_LONG,
                4: Action.EXIT_LONG,
                25: Action.ENTER_LONG,
                28: Action.EXIT_LONG,
            },
            warmup=20,
        )
        res = run_backtest(frame, runner, "X", "1h", cost=ZERO)
        self.assertEqual(len(res.trades), 1)  # the signals at bars 2 and 4 are warm-up
        self.assertEqual(res.trades[0].entry_time, frame["open_time"].iloc[26])


class BuyAndHoldTests(unittest.TestCase):
    def test_benchmark_is_one_buy_at_the_first_open_and_one_sell_at_the_last_close(
        self,
    ):
        frame = stepped(50)
        cost = CostModel(10, 5)
        bh = buy_and_hold(frame, "1h", 10, 40, cost, 10_000)
        fill = frame["open"].iloc[10] * 1.0005
        qty = (10_000 - 10_000 * 0.001) / fill
        sell = frame["close"].iloc[39] * 0.9995
        gross = qty * sell
        final = gross - gross * 0.001
        self.assertAlmostEqual(bh.equity[-1], final, places=8)
        self.assertAlmostEqual(
            bh.kpis["total_return_pct"], (final / 10_000 - 1) * 100, places=9
        )
        self.assertEqual(bh.kpis["trade_count"], 1)
        self.assertAlmostEqual(bh.fees_paid, 10_000 * 0.001 + gross * 0.001, places=9)
        self.assertEqual(bh.bars, 30)

    def test_benchmark_and_strategy_use_the_same_cost_model_and_window(self):
        frame = wavy(300)
        runner = StrategyRunner(create("STRAT-000", fast_len=3, slow_len=8))
        cost = CostModel(25, 10)
        out = evaluate_split(
            frame,
            lambda: StrategyRunner(create("STRAT-000", fast_len=3, slow_len=8)),
            "X",
            "1h",
            cost,
        )
        for name in ("in_sample", "out_of_sample"):
            a, b = out[name]["window"]
            strat, bench = out[name]["strategy"], out[name]["buy_and_hold"]
            self.assertEqual(
                (strat.first_bar, strat.last_bar), (bench.first_bar, bench.last_bar)
            )
            self.assertEqual(strat.bars, b - a)
            expected = buy_and_hold(frame, "1h", a, b, cost)
            self.assertEqual(bench.kpis, expected.kpis)
            self.assertAlmostEqual(
                strat.kpis["vs_buy_hold_pct"],
                strat.kpis["total_return_pct"] - bench.kpis["total_return_pct"],
                places=9,
            )

    def test_higher_costs_lower_the_benchmark_too(self):
        frame = stepped(50)
        cheap = buy_and_hold(frame, "1h", 0, 50, CostModel(1, 0))
        dear = buy_and_hold(frame, "1h", 0, 50, CostModel(50, 20))
        self.assertLess(dear.kpis["total_return_pct"], cheap.kpis["total_return_pct"])


class SplitTests(unittest.TestCase):
    def test_split_is_70_30_by_time(self):
        self.assertEqual(split_index(1000), 700)
        self.assertEqual(split_index(101), 70)
        with self.assertRaises(ValueError):
            split_index(100, 1.0)

    def test_out_of_sample_starts_flat_and_in_sample_never_trades_past_the_split(self):
        frame = stepped(1000)
        script = {650: Action.ENTER_LONG, 800: Action.EXIT_LONG, 820: Action.ENTER_LONG}
        out = evaluate_split(frame, lambda: runner_for(frame, script), "X", "1h", ZERO)
        cut = split_index(1000)
        times = frame["open_time"]

        is_res, oos_res = out["in_sample"]["strategy"], out["out_of_sample"]["strategy"]
        self.assertEqual((is_res.bars, oos_res.bars), (700, 300))
        # in-sample: entered at 651, still long at the split -> closed at bar 699's close
        (is_trade,) = is_res.trades
        self.assertEqual(is_trade.entry_time, times.iloc[651])
        self.assertEqual(
            (is_trade.exit_time, is_trade.exit_rule),
            (times.iloc[cut - 1], "end_of_data"),
        )
        # out-of-sample: the ENTER at 650 is history only; the position at bar 800 does not
        # exist, so only the later ENTER (820) trades
        (oos_trade,) = oos_res.trades
        self.assertEqual(oos_trade.entry_time, times.iloc[821])
        self.assertGreaterEqual(oos_trade.entry_time, times.iloc[cut])

    def test_runner_factory_gives_each_window_fresh_state(self):
        frame = stepped(200)
        built = []

        def factory():
            built.append(1)
            return runner_for(frame, {})

        evaluate_split(frame, factory, "X", "1h", ZERO)
        self.assertEqual(len(built), 2)

    def test_tiny_windows_are_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_split(
                stepped(3), lambda: runner_for(stepped(3), {}), "X", "1h", ZERO
            )


class KpiTests(unittest.TestCase):
    TF = 3600

    def test_keys_and_json_safety(self):
        frame = wavy(300)
        res = run_backtest(
            frame,
            StrategyRunner(create("STRAT-000", fast_len=3, slow_len=8)),
            "X",
            "1h",
        )
        self.assertEqual(set(res.kpis), set(KPI_KEYS))
        json.dumps(res.kpis)  # None / floats only; no NaN or inf

    def test_total_return_drawdown_and_exposure_hand_values(self):
        equity = [11_000, 12_000, 9_000, 9_900]
        k = compute_kpis(
            equity,
            10_000,
            self.TF,
            [5.0, -2.0, 3.0],
            bars_in_position=2,
            fees_paid=12.5,
        )
        self.assertAlmostEqual(k["total_return_pct"], -1.0)
        self.assertAlmostEqual(k["max_drawdown_pct"], -25.0)
        self.assertAlmostEqual(k["exposure_pct"], 50.0)
        self.assertEqual(k["trade_count"], 3)
        self.assertAlmostEqual(k["win_rate_pct"], 100 * 2 / 3)
        self.assertAlmostEqual(k["avg_trade_pct"], 2.0)
        self.assertEqual(k["fees_paid"], 12.5)

    def test_sharpe_and_sortino_match_the_definition(self):
        equity = [10_100, 10_000, 10_300, 10_200]
        k = compute_kpis(equity, 10_000, self.TF, [], 4, 0)
        eq = np.array([10_000] + equity, dtype=float)
        r = eq[1:] / eq[:-1] - 1
        ann = math.sqrt(365.25 * 24)
        self.assertAlmostEqual(k["sharpe"], r.mean() / r.std(ddof=1) * ann, places=9)
        downside = math.sqrt(np.mean(np.minimum(r, 0) ** 2))
        self.assertAlmostEqual(k["sortino"], r.mean() / downside * ann, places=9)

    def test_cagr_uses_calendar_time(self):
        # 8766 hourly bars = exactly one 365.25-day year; doubling -> 100% CAGR
        equity = [10_000.0] * 8765 + [20_000.0]
        k = compute_kpis(equity, 10_000, self.TF, [], 0, 0)
        self.assertAlmostEqual(k["cagr_pct"], 100.0, places=6)

    def test_undefined_values_are_none_not_zero(self):
        k = compute_kpis([10_000.0, 10_000.0, 10_000.0], 10_000, self.TF, [], 0, 0)
        self.assertIsNone(k["sharpe"])  # zero variance
        self.assertIsNone(k["sortino"])
        self.assertIsNone(k["win_rate_pct"])  # no trades
        self.assertIsNone(k["avg_trade_pct"])
        self.assertEqual(k["trade_count"], 0)
        self.assertEqual(k["exposure_pct"], 0.0)
        self.assertEqual(k["total_return_pct"], 0.0)

    def test_empty_curve_is_all_none(self):
        k = compute_kpis([], 10_000, self.TF, [], 0, 0)
        self.assertIsNone(k["total_return_pct"])

    def test_a_flat_market_with_no_trades_has_zero_exposure_and_equity(self):
        frame = stepped(60)
        res = run_backtest(frame, runner_for(frame, {}), "X", "1h", cost=CostModel())
        self.assertEqual(set(res.equity), {10_000.0})
        self.assertEqual(res.kpis["trade_count"], 0)
        self.assertEqual(res.kpis["exposure_pct"], 0.0)


class CostModelTests(unittest.TestCase):
    def test_validation(self):
        for bad in (
            {"fee_bps": -1},
            {"slippage_bps": -1},
            {"size_fraction": 0},
            {"size_fraction": 1.5},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                CostModel(**bad)

    def test_defaults_are_ten_and_five_bps_full_size(self):
        c = CostModel()
        self.assertEqual((c.fee_bps, c.slippage_bps, c.size_fraction), (10.0, 5.0, 1.0))


if __name__ == "__main__":
    unittest.main()
