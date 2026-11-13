"""PTAI-RD-001 work package 1.11: the stationary bootstrap on marked daily results.

* Marking: a trade contributes to every day it is held, and its days sum to its net.
* The block length follows the data's dependence and is capped at min(3 sqrt(N), N/3),
  so it can never be E1's 896 days.
* On synthetic series the test holds its size under the null, with independent and
  with dependent days, and detects a known edge.

Synthetic data only."""

from __future__ import annotations

import math

import numpy as np
import pytest

from research_stats import resampling as rs

DAY = rs.DAY_S


def ar1(n, phi, rng, sd=1.0):
    e = rng.normal(0, sd, n)
    x = np.empty(n)
    x[0] = e[0] / math.sqrt(max(1e-9, 1 - phi**2))
    for t in range(1, n):
        x[t] = phi * x[t - 1] + e[t]
    return x


# -- marking -------------------------------------------------------------------------------


def test_a_trade_is_marked_on_every_day_held_and_sums_to_its_net():
    closes = {"X": {d: 100.0 + d for d in range(0, 200)}}
    trade = {
        "coin": "X",
        "entry_s": 10 * DAY + 60,  # bought on day 10, at 110
        "exit_s": 70 * DAY,  # sold at day 70's open: the last mark is day 69's close
        "amount": 110.0,
        "entry_price": 110.0,
        "net": 55.0,
    }
    marks = rs.daily_marks([trade], closes, first_day=0, days=100)
    held = np.flatnonzero(marks.capital)
    assert held[0] == 10 and held[-1] == 69  # every day held, each at the amount
    assert np.all(marks.capital[held] == 110.0)
    assert marks.pnl.sum() == pytest.approx(55.0)
    assert marks.pnl[10] == pytest.approx(0.0)  # day 10's close is the entry price
    assert marks.pnl[11] == pytest.approx(1.0)  # one unit, up 1 a day
    assert marks.rpcd() == pytest.approx(55.0 / (110.0 * 60))


def test_a_day_without_a_close_keeps_the_last_value():
    closes = {"X": {0: 100.0, 1: 100.0, 3: 104.0}}  # no close on day 2
    trade = {
        "coin": "X",
        "entry_s": 0,
        "exit_s": 5 * DAY,
        "amount": 100.0,
        "entry_price": 100.0,
        "net": 3.0,
    }
    marks = rs.daily_marks([trade], closes, 0, 6)
    assert marks.pnl[2] == 0.0 and marks.pnl[3] == pytest.approx(4.0)
    assert marks.pnl.sum() == pytest.approx(3.0)


def test_trades_outside_the_period_add_nothing_and_overlaps_add_up():
    closes = {"X": {d: 100.0 for d in range(50)}, "Y": {d: 50.0 for d in range(50)}}
    trades = [
        {
            "coin": "X",
            "entry_s": 0,
            "exit_s": 10 * DAY,
            "amount": 100.0,
            "entry_price": 100.0,
            "net": -1.0,
        },
        {
            "coin": "Y",
            "entry_s": 5 * DAY,
            "exit_s": 8 * DAY,
            "amount": 50.0,
            "entry_price": 50.0,
            "net": 2.0,
        },
        {
            "coin": "X",
            "entry_s": 40 * DAY,
            "exit_s": 45 * DAY,
            "amount": 100.0,
            "entry_price": 100.0,
            "net": 9.0,
        },
    ]
    marks = rs.daily_marks(trades, closes, first_day=0, days=20)
    assert marks.pnl.sum() == pytest.approx(1.0)
    assert marks.capital[6] == 150.0 and marks.capital[15] == 0.0


# -- the block length ----------------------------------------------------------------------


def test_the_block_length_grows_with_dependence():
    rng = np.random.default_rng(1)
    n = 1500
    lengths = [rs.optimal_block_length(ar1(n, phi, rng)) for phi in (0.0, 0.5, 0.9)]
    assert lengths[0] < 5
    assert lengths[0] < lengths[1] < lengths[2]


def test_the_block_length_is_capped_and_never_e1s_896_days():
    rng = np.random.default_rng(2)
    n = 1586  # E1's scored days
    walk = np.cumsum(rng.normal(size=n))  # as dependent as a series gets
    b = rs.optimal_block_length(walk)
    assert 1.0 <= b <= math.ceil(min(3 * math.sqrt(n), n / 3))
    assert b < 896 / 7
    assert rs.optimal_block_length([1.0] * 50) == 1.0  # no variance
    assert rs.optimal_block_length([1.0, 2.0]) == 1.0  # too short


def test_stationary_draws_follow_runs_with_the_mean_block():
    idx = rs.stationary_indices(1000, 20.0, 200, np.random.default_rng(3))
    assert idx.shape == (200, 1000) and idx.min() >= 0 and idx.max() < 1000
    runs = (np.diff(idx, axis=1) != 1) & ~((idx[:, :-1] == 999) & (idx[:, 1:] == 0))
    mean_run = 1000 * 200 / (runs.sum() + 200)
    assert 16 < mean_run < 25  # geometric runs with mean 20


# -- size and power -------------------------------------------------------------------------


def rejection_rate(make, reps, rng, draws=199, alpha=0.05):
    hits = 0
    for r in range(reps):
        pnl = make(rng)
        marks = rs.DailyMarks(0, pnl, np.ones(len(pnl)))
        hits += rs.rpcd_test(marks, draws=draws, seed=r).p_value <= alpha
    return hits / reps


@pytest.mark.parametrize("phi", [0.0, 0.4])
def test_the_size_under_the_null_is_near_five_percent(phi):
    rng = np.random.default_rng(10 + int(phi * 10))
    rate = rejection_rate(lambda g: ar1(750, phi, g), reps=300, rng=rng)
    # 300 replications: a standard error of about 1.3 points around 5%
    assert 0.015 <= rate <= 0.10, rate


def test_a_known_edge_is_detected():
    rng = np.random.default_rng(20)
    # mean 0.2 a day; AR 0.4 with unit shocks has a long-run sd of 1 / 0.6, so over 750
    # days t is about 0.2 x sqrt(750) x 0.6 = 3.3, and the power at 5% about 0.95
    rate = rejection_rate(lambda g: ar1(750, 0.4, g) + 0.2, reps=100, rng=rng)
    assert rate >= 0.8, rate


def test_the_same_seed_gives_the_same_result():
    rng = np.random.default_rng(30)
    marks = rs.DailyMarks(0, ar1(500, 0.3, rng) + 0.05, np.ones(500))
    a = rs.rpcd_test(marks, draws=300, seed=7)
    b = rs.rpcd_test(marks, draws=300, seed=7)
    assert a == b
    assert a.interval[0] < a.theta < a.interval[1]
    assert a.days == 500 and a.draws == 300


def test_a_period_without_capital_is_refused():
    with pytest.raises(ValueError):
        rs.rpcd_test(rs.DailyMarks(0, np.zeros(10), np.zeros(10)))
