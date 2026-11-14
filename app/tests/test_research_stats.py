"""PTAI-RD-001 work package 1.11: the stationary bootstrap on marked daily results.

* Marking: a trade contributes to every day it is held, and its days sum to its net.
* The block length follows the data's dependence and is capped at min(3 sqrt(N), N/3),
  so it can never be E1's 896 days.
* On synthetic series the test holds its size under the null, with independent and
  with dependent days, and detects a known edge.
* The O3 variants (percentile or studentised; block length x1 or x1.5) each run and
  repeat with the seed; the default is the calibration's choice, variant D.
* The test of a daily series' mean (``mean_test``, SR1-E2's comparison with a hold):
  both methods hold their size on independent days, find a clear positive mean, repeat
  with the seed, and agree with ``rpcd_test`` when every day has one unit of capital.

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


# -- the variants (O3 calibration: docs/dev/ptai-rd-001/O3-bootstrap-calibration.md) -------

VARIANTS = [
    ("percentile", 1.0),  # A
    ("studentised", 1.0),  # B
    ("percentile", 1.5),  # C
    ("studentised", 1.5),  # D
]


@pytest.mark.parametrize("method,scale", VARIANTS)
def test_each_variant_runs_and_is_deterministic_per_seed(method, scale):
    rng = np.random.default_rng(40)
    marks = rs.DailyMarks(0, ar1(400, 0.4, rng) + 0.05, np.ones(400))
    a = rs.rpcd_test(marks, draws=199, seed=11, method=method, block_scale=scale)
    b = rs.rpcd_test(marks, draws=199, seed=11, method=method, block_scale=scale)
    c = rs.rpcd_test(marks, draws=199, seed=12, method=method, block_scale=scale)
    assert a == b
    assert a.method == method and a.draws == 199 and a.days == 400
    assert 0.0 < a.p_value <= 1.0
    assert a.interval[0] < a.theta < a.interval[1]
    assert c.interval != a.interval  # another seed, other draws


def test_the_default_is_the_calibrated_variant_d():
    # O3: no variant met the 6.0% worst-case size; D's 6.2% was the lowest
    assert (rs.DEFAULT_METHOD, rs.DEFAULT_BLOCK_SCALE) == ("studentised", 1.5)
    rng = np.random.default_rng(44)
    marks = rs.DailyMarks(0, ar1(300, 0.4, rng), np.ones(300))
    explicit = rs.rpcd_test(
        marks, draws=99, seed=5, method="studentised", block_scale=1.5
    )
    assert rs.rpcd_test(marks, draws=99, seed=5) == explicit


def test_an_unknown_method_is_refused():
    marks = rs.DailyMarks(0, np.ones(20), np.ones(20))
    with pytest.raises(ValueError):
        rs.rpcd_test(marks, method="basic")


def test_the_block_scale_multiplies_the_chosen_length_within_the_cap():
    rng = np.random.default_rng(41)
    n = 600
    x = ar1(n, 0.5, rng)
    marks = rs.DailyMarks(0, x, np.ones(n))
    chosen = rs.optimal_block_length(x)
    assert rs.rpcd_test(marks, draws=50, block_scale=1.0).mean_block == chosen
    assert rs.rpcd_test(marks, draws=50, block_scale=1.5).mean_block == pytest.approx(
        1.5 * chosen
    )
    walk = rs.DailyMarks(0, np.cumsum(rng.normal(size=n)), np.ones(n))
    assert rs.rpcd_test(walk, draws=50, block_scale=1.5).mean_block <= rs.block_cap(n)
    given = rs.rpcd_test(marks, draws=50, mean_block=7.0, block_scale=1.5)
    assert given.mean_block == 7.0  # a length given is used as it is


def test_the_bartlett_long_run_variance():
    z = np.array([[1.0, -1.0, 1.0, -1.0]])
    assert rs.bartlett_lrv(z, 1.0)[0] == pytest.approx(1.0)  # R(0) only
    # bandwidth 2: R(0) + 2 x 0.5 x R(1), R(1) = -3/4
    assert rs.bartlett_lrv(z, 2.0)[0] == pytest.approx(0.25)
    rng = np.random.default_rng(42)
    rows = rng.normal(size=(5, 300))
    rows -= rows.mean(axis=1, keepdims=True)
    assert np.all(rs.bartlett_lrv(rows, 12.0) >= 0.0)


def marked_null_trades(n, rng, sigma=0.03):
    """The real use case under no edge: a martingale price, long-only trades of 20 to 60
    days with flat gaps of 30 to 120 days, marked daily (most days hold no capital)."""
    close = 100.0 * np.exp(np.cumsum(rng.normal(-0.5 * sigma**2, sigma, n)))
    closes = {"X": {d: float(close[d]) for d in range(n)}}
    trades, d0 = [], int(rng.integers(0, 121))
    while True:
        d1 = d0 + int(rng.integers(20, 61)) - 1
        if d1 >= n:
            break
        amount = float(rng.uniform(50.0, 150.0))
        trades.append(
            {
                "coin": "X",
                "entry_s": d0 * DAY + 60,
                "exit_s": (d1 + 1) * DAY,
                "amount": amount,
                "entry_price": float(close[d0]),
                "net": amount / close[d0] * close[d1] - amount,
            }
        )
        d0 = d1 + 1 + int(rng.integers(30, 121))
    return rs.daily_marks(trades, closes, 0, n)


def test_the_default_holds_its_size_on_marked_trades_without_an_edge():
    rng = np.random.default_rng(43)
    reps, hits = 200, 0
    for r in range(reps):
        marks = marked_null_trades(500, rng)
        hits += rs.rpcd_test(marks, draws=199, seed=r).p_value <= 0.05
    # 200 replications: a standard error of about 1.5 points around 5%
    assert 0.01 <= hits / reps <= 0.10, hits / reps


# -- the mean of a daily series (mean_test: SR1-E2's comparison with a hold) ---------------


@pytest.mark.parametrize("method", rs.METHODS)
def test_the_mean_test_holds_its_size_on_independent_days(method):
    rng = np.random.default_rng(50)
    reps, hits = 200, 0
    for r in range(reps):
        x = rng.normal(0.0, 0.02, 500)  # daily log-return differences with mean 0
        hits += rs.mean_test(x, draws=199, seed=r, method=method).p_value <= 0.05
    # 200 replications: a standard error of about 1.5 points around 5%
    assert 0.01 <= hits / reps <= 0.10, hits / reps


@pytest.mark.parametrize("method", rs.METHODS)
def test_the_mean_test_finds_a_clear_positive_mean_and_not_a_negative_one(method):
    rng = np.random.default_rng(51)
    # AR 0.3 with unit shocks has a long-run sd of 1 / 0.7, so the mean's standard error
    # over 600 days is about 0.058, and 0.4 a day is about 7 of them
    x = ar1(600, 0.3, rng) + 0.4
    up = rs.mean_test(x, draws=499, seed=1, method=method)
    assert up.p_value <= 0.01, up.p_value
    assert 0.0 < up.interval[0] < up.mean < up.interval[1]
    down = rs.mean_test(-x, draws=499, seed=1, method=method)
    assert down.p_value >= 0.99, down.p_value  # one-sided: H0 is mean <= 0


@pytest.mark.parametrize("method", rs.METHODS)
def test_the_mean_test_repeats_with_its_seed_and_reports_per_day(method):
    rng = np.random.default_rng(52)
    x = 0.01 * ar1(400, 0.4, rng) + 0.001
    a = rs.mean_test(x, draws=199, seed=11, method=method)
    b = rs.mean_test(list(x), draws=199, seed=11, method=method)
    c = rs.mean_test(x, draws=199, seed=12, method=method)
    assert a == b
    assert c.interval != a.interval  # another seed, other draws
    assert a.method == method and a.draws == 199 and a.days == 400 and a.level == 0.95
    assert a.mean == float(np.mean(x))  # per day, not annualised
    assert 0.0 < a.p_value <= 1.0
    assert a.interval[0] < a.mean < a.interval[1]


@pytest.mark.parametrize("method", rs.METHODS)
def test_the_mean_test_is_rpcd_test_with_one_unit_of_capital_every_day(method):
    # with the same capital every day, return per capital-day is the mean, so the two
    # tests must agree draw for draw: the same blocks, the same statistic, the same p
    rng = np.random.default_rng(53)
    x = ar1(500, 0.4, rng) + 0.05
    marks = rs.DailyMarks(0, x, np.ones(500))
    for kw in ({"block_scale": 1.0}, {"block_scale": 1.5}, {"mean_block": 7.0}):
        m = rs.mean_test(x, draws=299, seed=3, method=method, **kw)
        r = rs.rpcd_test(marks, draws=299, seed=3, method=method, **kw)
        assert m.mean == pytest.approx(r.theta)
        assert m.p_value == r.p_value
        assert m.interval == pytest.approx(r.interval)
        assert (m.mean_block, m.draws, m.days) == (r.mean_block, r.draws, r.days)


def test_the_mean_tests_methods_differ_and_the_default_is_studentised_x1_5():
    rng = np.random.default_rng(54)
    x = ar1(300, 0.4, rng)
    p = rs.mean_test(x, draws=199, seed=5, method="percentile")
    s = rs.mean_test(x, draws=199, seed=5, method="studentised")
    assert p.method == "percentile" and s.method == "studentised"
    assert p.interval != s.interval and p.p_value != s.p_value
    explicit = rs.mean_test(x, draws=199, seed=5, method="studentised", block_scale=1.5)
    assert rs.mean_test(x, draws=199, seed=5) == explicit


def test_the_mean_tests_block_length_scale_cap_and_a_length_given():
    rng = np.random.default_rng(55)
    n = 600
    x = ar1(n, 0.5, rng)
    chosen = rs.optimal_block_length(x)
    assert rs.mean_test(x, draws=50, block_scale=1.0).mean_block == chosen
    assert rs.mean_test(x, draws=50, block_scale=1.5).mean_block == pytest.approx(
        1.5 * chosen
    )
    walk = np.cumsum(rng.normal(size=n))  # its chosen length x3 is past the cap
    assert 3.0 * rs.optimal_block_length(walk) > rs.block_cap(n)
    assert rs.mean_test(walk, draws=50, block_scale=3.0).mean_block == rs.block_cap(n)
    # a length given is used as it is, whatever the scale, and above the cap too
    given = rs.mean_test(x, draws=50, mean_block=7.0, block_scale=1.5)
    assert given.mean_block == 7.0
    assert given == rs.mean_test(x, draws=50, mean_block=7.0, block_scale=1.0)
    assert given != rs.mean_test(x, draws=50, block_scale=1.5)
    assert rs.mean_test(x, draws=50, mean_block=400.0).mean_block == 400.0


@pytest.mark.parametrize(
    "bad",
    [[], [0.01], [0.01, float("nan"), 0.0], [0.01, float("inf"), 0.0], [0.01, None]],
)
def test_the_mean_test_refuses_too_few_days_and_values_that_are_not_finite(bad):
    with pytest.raises(ValueError):
        rs.mean_test(bad)


def test_the_mean_test_refuses_an_unknown_method_and_a_table():
    with pytest.raises(ValueError):
        rs.mean_test(np.ones(20), method="basic")
    with pytest.raises(ValueError):
        rs.mean_test(np.ones((5, 4)))
