"""FDS-SR-001 milestone M4c: the model cells (sections 5.9 and 12).

* The strategy and its exits stay constant: a cell only vetoes or shrinks the same
  candidate trades; every trade it keeps is the candidate itself, exit included.
* A generic forecast filter reads a lab model's probability at each trade's decision
  hour, against a causal threshold (the quantile of the probabilities before that
  month); without a probability, or without enough history, it cannot assess and never
  vetoes.
* A strategy-specific meta-model is FDS-SIG-004's on this strategy's own trades: forced
  trades are never labels, calibration is out of fold, a veto is an expected value at
  most 0, and too few events or non-events make it not assessable.
* R3 vetoes the filter's per-coin count among its assessable, eligible trades; R3s gives
  the shrink's scales in a random order; both repeat for a seed.

Synthetic data only: no network, nothing about performance."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from test_strategy_lab import frame_for

from signal_fusion.evaluation.replay import Account, Costs
from strategy_lab import models as md
from strategy_lab.candidates import RunnerSpec, Trade
from strategy_lab.simulate import Simulation, Universe

DAY, HOUR = 86_400, 3_600
T0 = int(pd.Timestamp("2023-01-01", tz="UTC").timestamp())


def trade(coin, entry_s, exit_s, entry=100.0, exit_=101.0, forced=False):
    return Trade(
        coin, 0, 1, 2, int(entry_s), int(exit_s), entry, exit_, "strategy", forced
    )


def hourly_probabilities(coins=("A", "B"), days=730, missing=()):
    out = {}
    for j, coin in enumerate(coins):
        close_s = T0 + HOUR * np.arange(1, days * 24 + 1)
        p = 0.5 + 0.4 * np.sin(close_s / 86_400.0 + j)
        keep = ~np.isin(close_s, np.asarray(missing, dtype=np.int64))
        out[coin] = (close_s[keep], p[keep])
    return out


class TestFolds:
    def test_the_development_folds_are_the_labs(self):
        folds = md.development_folds()
        assert folds[0][0] == int(pd.Timestamp("2022-01-01", tz="UTC").timestamp())
        assert folds[-1][1] == int(pd.Timestamp("2025-05-06", tz="UTC").timestamp())
        assert len(folds) == 14


class TestForecastFilter:
    def test_the_threshold_uses_only_earlier_months(self):
        probs = hourly_probabilities()
        when = int(pd.Timestamp("2024-03-15", tz="UTC").timestamp())
        f = md.forecast_filter([trade("A", when, when + 5 * DAY)], probs, 0.5, "f")
        month = int(pd.Timestamp("2024-03-01", tz="UTC").timestamp())
        before = np.concatenate([p[t < month] for t, p in probs.values()])
        expected = np.quantile(before, 0.5)
        p_here = probs["A"][1][probs["A"][0] == when][0]
        assert f.assessable[0] and f.p[0] == pytest.approx(p_here)
        assert f.veto[0] == (p_here < expected)

    def test_without_a_probability_or_history_it_cannot_assess(self):
        early = T0 + 2 * DAY  # before 1,000 probabilities exist
        late = int(pd.Timestamp("2024-06-01", tz="UTC").timestamp())
        probs = hourly_probabilities(missing=[late])
        f = md.forecast_filter(
            [
                trade("A", early, early + DAY),
                trade("A", late, late + DAY),
                trade("C", late, late + DAY),
            ],
            probs,
            0.5,
            "f",
        )
        assert not f.assessable.any() and not f.veto.any()

    def test_about_q_of_the_assessable_trades_are_vetoed(self):
        probs = hourly_probabilities()
        start = int(pd.Timestamp("2023-06-01", tz="UTC").timestamp())
        trades = [
            trade("A", start + k * DAY, start + (k + 1) * DAY) for k in range(500)
        ]
        f = md.forecast_filter(trades, probs, 0.3, "f")
        share = f.veto[f.assessable].mean()
        assert 0.15 < share < 0.45


class TestMetaFilter:
    def setup_method(self):
        rng = np.random.default_rng(0)
        start = int(pd.Timestamp("2021-01-01", tz="UTC").timestamp())
        self.trades, x = [], []
        for k in range(900):
            entry_s = start + k * DAY + 12 * HOUR
            gross = rng.normal(0.004, 0.04)
            self.trades.append(
                trade(
                    "A" if k % 2 else "B",
                    entry_s,
                    entry_s + 3 * DAY,
                    100.0,
                    100.0 * (1 + gross),
                    forced=(k == 899),
                )
            )
            x.append([gross + rng.normal(0, 0.02), rng.normal()])
        self.x = np.array(x)
        self.folds = md.development_folds()

    def test_a_forced_trade_is_never_a_label_and_scores_are_out_of_fold(self):
        f = md.meta_filter(self.trades, self.x, self.folds, fee=0.005, name="F_P")
        assert f.assessable.any()
        first_fold = self.folds[0]
        in_first = np.array(
            [first_fold[0] <= t.entry_s < first_fold[1] for t in self.trades]
        )
        assert not f.assessable[in_first].any()  # fold 1 has no calibration
        assert f.detail["events"] + f.detail["non_events"] < len(self.trades)

    def test_the_veto_is_an_expected_value_at_most_zero(self):
        f = md.meta_filter(self.trades, self.x, self.folds, fee=0.005, name="F_P")
        assert f.veto.sum() > 0 and (~f.veto & f.assessable).sum() > 0
        # an informative feature: vetoed trades lost more than the kept ones
        gross = np.array([t.exit_price / t.entry_price - 1 for t in self.trades])
        assert gross[f.veto].mean() < gross[f.assessable & ~f.veto].mean()

    def test_too_few_events_are_not_assessable(self):
        f = md.meta_filter(
            self.trades[:300], self.x[:300], self.folds, fee=0.005, name="F_P"
        )
        assert f.enough is False


class TestCells:
    def setup_method(self):
        frames = {
            "AAA": frame_for("1d", 700, seed=21),
            "BBB": frame_for("1d", 700, seed=22, phase=1.5),
        }
        spec = RunnerSpec("STRAT-004", {"entry_days": 20, "exit_days": 10}, (), "1d")
        self.sim = Simulation(Universe("1d", frames), spec)
        self.trades = self.sim.candidates()
        n = len(self.trades)
        veto = np.zeros(n, dtype=bool)
        veto[::3] = True
        self.filt = md.Filter(
            "every third", veto, np.ones(n, dtype=bool), np.full(n, 0.5)
        )
        self.costs = Costs(fee=0.005, minimum_usd={"AAA": 1.0, "BBB": 1.0})

    def test_a_cell_keeps_the_candidates_own_trades(self):
        plain = md.cell(self.sim, self.trades, self.costs, Account(), detail=True)
        gated = md.cell(
            self.sim, self.trades, self.costs, Account(), self.filt, detail=True
        )
        taken = [i for i, *_ in gated.detail]
        assert taken and all(not self.filt.veto[i] for i in taken)
        assert taken != [i for i, *_ in plain.detail]  # the veto changed the path
        m = self.costs.multiplier()
        for i, amount, net, _days in gated.detail:
            # the candidate's own trade, its exit included: net = (1 + r_g) m - 1
            gross = self.trades[i].exit_price / self.trades[i].entry_price - 1.0
            assert net / amount == pytest.approx((1.0 + gross) * m - 1.0, rel=1e-9)

    def test_r3_matches_the_filters_count_per_coin(self):
        candidates = md.eligible_assessable(
            self.sim, self.trades, self.filt, self.costs, Account()
        )
        draws = md.random_vetoes(
            self.trades, self.filt, candidates, seed=500_000, run=0, draws=25
        )
        coins = np.array([t.coin for t in self.trades])
        for coin in ("AAA", "BBB"):
            mine = [i for i in candidates if coins[i] == coin]
            k = int(sum(self.filt.veto[i] for i in mine))
            assert all(int(draws[b, mine].sum()) == k for b in range(25))
            outside = [i for i in range(len(self.trades)) if i not in set(candidates)]
            assert not draws[:, outside].any()
        again = md.random_vetoes(
            self.trades, self.filt, candidates, seed=500_000, run=0, draws=25
        )
        np.testing.assert_array_equal(draws, again)

    def test_the_shrink_and_r3s(self):
        scales = md.shrink_scales([0.02, 0.05, np.nan, 0.01], sigma_ref=0.02)
        np.testing.assert_allclose(scales, [1.0, 0.4, 1.0, 1.0])
        n = len(self.trades)
        rng = np.random.default_rng(3)
        s = np.minimum(1.0, rng.uniform(0.3, 1.5, n))
        candidates = list(range(0, n, 2))
        draws = md.random_scales(
            self.trades, s, candidates, seed=600_000, run=0, draws=10
        )
        for b in range(10):
            np.testing.assert_allclose(
                sorted(draws[b, candidates]), sorted(s[candidates])
            )
        assert np.all(draws[:, 1::2] == 1.0)
