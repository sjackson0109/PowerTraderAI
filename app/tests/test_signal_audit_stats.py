"""FDS-SIG-001 section 16, item 1: the statistics module.

Hand-worked values and independent scalar references (exact integer sums for the
binomial and hypergeometric tails, plain loops for the autocorrelation time, the block
bootstrap's means, batch means and Holm), at a 1e-6 tolerance, as
``tests/test_indicators.py`` does for FDS-121. Covers the exact paired test, Fisher's
one-sided and lower-tail tests, both magnitude statistics, the per-pair contributions,
the bootstrap with a fixed seed, batch means, the floors, the m = 0 and full-coverage
cases, the block-length rule (long blocks for calls whose tendency drifts slowly), the
largest-of-three rule (each component the largest in turn), both Holm procedures, the
minimum detectable effects and 95% upper bounds (with their coverage checked), and the
section 7.1 illustration from the counts derived from trainer-port-evidence-phase2.json.
"""

import json
import math
import os
import sys
from fractions import Fraction

import numpy as np
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
REPO = os.path.dirname(APP_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from signal_audit import engine  # noqa: E402
from signal_audit import stats as st  # noqa: E402

TOL = 1e-6


# --- independent references ----------------------------------------------------------


def ref_binomial_upper(k, m):
    """P(Binomial(m, 1/2) >= k), as an exact fraction."""
    if m == 0:
        return 1.0
    total = sum(math.comb(m, i) for i in range(max(k, 0), m + 1))
    return float(Fraction(total, 2**m))


def ref_hypergeom(a, b, c, d, upper=True):
    """One-sided Fisher on [[a, b], [c, d]]: P(top-left >= a) (or <= a), exact."""
    row1, col1, total = a + b, a + c, a + b + c + d
    lo, hi = max(0, row1 + col1 - total), min(row1, col1)
    denom = math.comb(total, row1)
    cells = range(a, hi + 1) if upper else range(lo, a + 1)
    num = sum(math.comb(col1, x) * math.comb(total - col1, row1 - x) for x in cells)
    return float(Fraction(num, denom))


def ref_tau(x, M):
    n = len(x)
    mean = sum(x) / n
    d = [v - mean for v in x]
    c0 = sum(v * v for v in d)
    s = 0.0
    for k in range(1, M + 1):
        ck = sum(d[t] * d[t + k] for t in range(n - k))
        s += (1 - k / (M + 1)) * ck / c0
    return max(1.0, 1 + 2 * s)


def ref_batch_means(x, L):
    from scipy.stats import t as student_t

    E = len(x)
    K = E // L
    kept = list(x[E - K * L :])
    means = [sum(kept[i * L : (i + 1) * L]) / L for i in range(K)]
    mbar = sum(means) / K
    var = sum((m - mbar) ** 2 for m in means) / (K - 1)
    se = math.sqrt(var) / math.sqrt(K)
    t = mbar / se
    return K, E - K * L, mbar, se, student_t.sf(t, K - 1), student_t.cdf(t, K - 1)


def pairs_of(calls, up, ret=None, kind=st.TWO_SIDED, tf="1h"):
    calls = np.asarray(calls, dtype=np.int8)
    up = np.asarray(up, dtype=np.int8)
    ret = np.asarray(
        ret if ret is not None else np.where(up == 1, 0.01, -0.01), dtype=float
    )
    return st.Pairs(calls, up, ret, kind, tf)


# --- exact tests ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "k,m", [(0, 0), (3, 5), (5, 5), (596, 1199), (1003, 1990), (0, 10)]
)
def test_the_exact_paired_tail_matches_an_exact_integer_sum(k, m):
    assert abs(st.binomial_upper(k, m) - ref_binomial_upper(k, m)) < TOL


@pytest.mark.parametrize(
    "a,b,c,d",
    [(8, 2, 1, 5), (3, 7, 6, 4), (0, 5, 5, 0), (12, 30, 20, 25), (10, 0, 0, 10)],
)
def test_fishers_one_sided_tails_match_exact_hypergeometric_sums(a, b, c, d):
    assert abs(st.fisher_upper(a, b, c, d) - ref_hypergeom(a, b, c, d, True)) < TOL
    assert abs(st.fisher_lower(a, b, c, d) - ref_hypergeom(a, b, c, d, False)) < TOL


def test_fisher_has_no_evidence_when_a_margin_is_empty():
    # at 100% coverage the abstained row is empty: p = 1 (section 7.2)
    assert st.fisher_upper(10, 5, 0, 0) == 1.0
    assert st.fisher_lower(10, 5, 0, 0) == 1.0


def test_the_section_7_1_illustration_from_the_phase2_evidence():
    """Counts derived from trainer-port-evidence-phase2.json (rate x n; each an exact
    integer): a fixture for the statistics, not a measurement, and no verdict."""
    with open(
        os.path.join(REPO, "docs", "dev", "trainer-port-evidence-phase2.json")
    ) as f:
        metrics = json.load(f)["checks"]
    found = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if (
                    k in ("L1 BTC, 3 years", "L2 ETH, 3 years")
                    and "direction_hit_rate" in v
                ):
                    found[k[3:6]] = v
                walk(v)

    walk(metrics)
    want = {
        "BTC": (1199, 596, -0.20, 0.59, 0.502, 0.0116),
        "ETH": (1990, 1003, 0.36, 0.37, 0.502, 0.0197),
    }
    for coin, (m_want, k_want, z_want, p_want, chance_want, ub_want) in want.items():
        v = found[coin]
        n = v["direction_considered"]
        hits = v["direction_hit_rate"] * n
        ups = v["up_share_of_considered"] * n
        up_calls = v["predicted_up_share_of_considered"] * n
        for x in (hits, ups, up_calls):
            assert abs(x - round(x)) < 1e-6  # an exact integer
        hits, ups, up_calls = round(hits), round(ups), round(up_calls)
        # build a row with these counts: always-up is the constant (p_c >= 0.5)
        calls, up = [], []
        k = (hits - ups + (n - up_calls)) // 2
        m = n - up_calls
        # discordant (down calls): k right (down outcome), m - k wrong (up outcome)
        calls += [-1] * m
        up += [0] * k + [1] * (m - k)
        # concordant (up calls): the rest of the up outcomes
        calls += [1] * up_calls
        rest_up = ups - (m - k)
        up += [1] * rest_up + [0] * (up_calls - rest_up)
        p = pairs_of(calls, up)
        c = st.counts(p)
        assert (c.n, c.m, c.k, c.constant) == (n, m_want, k_want, "up")
        assert round(c.h * n) == hits and round(c.p_c * n) == ups
        z = (2 * c.k - c.m) / math.sqrt(c.m)
        assert round(z, 2) == z_want
        assert round(st.binomial_upper(c.k, c.m), 2) == p_want
        assert round(c.chance_at_mix, 3) == chance_want
        # the 95% upper bound with the independent standard error alone (section 9)
        ub = (2 * c.k - c.m) / n + 1.96 * math.sqrt(c.m) / n
        assert round(ub, 4) == ub_want


# --- counts, statistics and contributions ---------------------------------------------


def test_hand_worked_counts_of_a_small_two_sided_row():
    #           up   up   dn   dn   up   ab   dn   up
    calls = [1, 1, -1, -1, 1, 0, -1, 1]
    up = [1, 0, 0, 1, 1, 1, 0, 1]
    p = pairs_of(calls, up)
    c = st.counts(p)
    # called: 7; up outcomes on called: 1,0,0,1,1,0,1 = 4 -> p_c = 4/7, constant up
    assert (c.eligible, c.n, c.abstained, c.up_calls) == (8, 7, 1, 4)
    assert abs(c.p_c - 4 / 7) < TOL and c.constant == "up"
    # hits: up&up, up&dn(no), dn&dn, dn&up(no), up&up, dn&dn, up&up = 5
    assert abs(c.h - 5 / 7) < TOL
    # discordant = down calls (3); right among them: 2
    assert (c.m, c.k) == (3, 2)
    assert abs(st.statistic_value(p, st.HIT) - (2 * 2 - 3) / 7) < TOL
    assert abs(c.chance_at_mix - ((4 / 7) * (4 / 7) + (3 / 7) * (3 / 7))) < TOL


@pytest.mark.parametrize("kind", [st.TWO_SIDED, st.UP_ONLY, st.DOWN_ONLY])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_the_contributions_reproduce_each_statistic_exactly(kind, seed):
    rng = np.random.default_rng(seed)
    E = 400
    if kind == st.TWO_SIDED:
        calls = rng.choice([1, -1, 0], size=E, p=[0.45, 0.4, 0.15])
    elif kind == st.UP_ONLY:
        calls = rng.choice([1, 0], size=E, p=[0.6, 0.4])
    else:
        calls = rng.choice([-1, 0], size=E, p=[0.6, 0.4])
    up = (rng.random(E) < 0.52).astype(np.int8)
    ret = np.where(up == 1, 1, -1) * rng.uniform(0.001, 0.02, E)
    p = pairs_of(calls, up, ret, kind)
    for s in st.STATISTICS:
        x = st.contributions(p, s)
        assert abs(x.mean() - st.statistic_value(p, s)) < 1e-12
    called = p.calls != 0
    # the statistics by their definitions, written out again
    if kind == st.TWO_SIDED:
        c = st.counts(p)
        assert abs(st.statistic_value(p, st.HIT) - (c.h - c.best_constant)) < 1e-12
        cr = p.calls[called] * (p.ret[called] - p.ret[called].mean())
        assert abs(st.statistic_value(p, st.MAGNITUDE) - cr.mean()) < 1e-12
        w = st.contributions(p, st.HIT, worse=True)
        assert abs(w.mean() - (c.h - c.chance_at_mix)) < 1e-12
    else:
        sign = 1 if kind == st.UP_ONLY else -1
        hit = sign * (p.up[called].mean() - p.up[~called].mean())
        mag = sign * (p.ret[called].mean() - p.ret[~called].mean())
        assert abs(st.statistic_value(p, st.HIT) - hit) < 1e-12
        assert abs(st.statistic_value(p, st.MAGNITUDE) - mag) < 1e-12


def test_a_constant_caller_scores_zero_on_the_demeaned_magnitude():
    rng = np.random.default_rng(3)
    up = (rng.random(500) < 0.6).astype(np.int8)
    ret = rng.normal(0.001, 0.01, 500)
    p = pairs_of(np.ones(500), up, ret)
    assert abs(st.statistic_value(p, st.MAGNITUDE)) < 1e-15
    # its raw mean of c x r is the mean return itself
    assert abs(st.extra_condition(p, st.MAGNITUDE)[1] - ret.mean()) < 1e-15


def test_the_extra_conditions():
    # two-sided magnitude: the raw mean of c x r must be above 0
    p = pairs_of([1, -1, 1, -1], [1, 0, 0, 1], [0.02, -0.01, -0.03, 0.01])
    met, raw = st.extra_condition(p, st.MAGNITUDE)
    assert abs(raw - (0.02 + 0.01 - 0.03 - 0.01) / 4) < TOL and not met
    # one-sided hit rate: the called pairs' own hit rate above 50%
    p = pairs_of([1, 1, 1, 0, 0], [1, 1, 0, 0, 1], kind=st.UP_ONLY)
    met, rate = st.extra_condition(p, st.HIT)
    assert abs(rate - 2 / 3) < TOL and met
    # one-sided magnitude: the called mean return has the called sign
    p = pairs_of([-1, -1, 0, 0], [0, 1, 1, 0], [-0.02, 0.01, 0.03, -0.01], st.DOWN_ONLY)
    met, mean = st.extra_condition(p, st.MAGNITUDE)
    assert abs(mean - (-0.005)) < TOL and met


# --- dependence -----------------------------------------------------------------------


def test_the_autocorrelation_time_matches_a_scalar_loop():
    rng = np.random.default_rng(5)
    x = (np.cumsum(rng.normal(size=600)) > 0).astype(float)
    for M in (1, 10, 150):
        assert abs(st.autocorrelation_time(x, M) - ref_tau(list(x), M)) < TOL


def test_the_block_length_rule():
    rng = np.random.default_rng(6)
    # independent calls: one day of bars
    p = pairs_of(rng.choice([1, -1], size=2400), rng.integers(0, 2, 2400))
    b = st.block_length(p)
    assert b.L == 24 and b.K == 100 and not b.constant_calls
    p4 = pairs_of(rng.choice([1, -1], size=2400), rng.integers(0, 2, 2400), tf="4h")
    assert st.block_length(p4).L == 6
    # a constant caller: L = E, one block
    p = pairs_of(np.ones(500), rng.integers(0, 2, 500))
    b = st.block_length(p)
    assert (b.L, b.K, b.constant_calls) == (500, 1, True)
    # calls that persist for runs of 200 bars get long blocks (2 tau, above one day)
    runs = np.repeat(rng.choice([1, -1], size=30), 200)
    b = st.block_length(pairs_of(runs, rng.integers(0, 2, len(runs))))
    assert b.L > 100 and b.L == math.ceil(2 * b.tau)
    # the maximum lag is min(one month of bars, a quarter of the series)
    assert st.max_lag(10_000, "1h") == 720 and st.max_lag(400, "1h") == 100
    assert st.max_lag(10_000, "4h") == 180


def test_calls_whose_tendency_drifts_slowly_raise_tau():
    """Calls that flicker bar to bar, with a probability drifting over weeks: the
    Bartlett-weighted tau over a month of lags sees the drift (tau well above 1), and
    L = max(one day, ceil(2 tau)). Whether that L is long enough is section 16 item 2's
    false-pass test on such data (test_signal_audit_false_pass.py); section 7.4 raises
    M if it is not."""
    rng = np.random.default_rng(7)
    E = 8760
    t = np.arange(E)
    for drift, at_least in ((0.30, 5.0), (0.15, 1.5)):
        prob = 0.5 + drift * np.sin(2 * np.pi * t / (24 * 21))  # a three-week cycle
        calls = np.where(rng.random(E) < prob, 1, -1)
        b = st.block_length(pairs_of(calls, rng.integers(0, 2, E)))
        assert b.tau == b.tau_by_indicator["u"] and b.tau > at_least
        assert b.L == max(24, math.ceil(2 * b.tau))
    # a cycle as long as the maximum lag (a month at 1h) is not seen: its
    # autocorrelations cancel inside the Bartlett window, so tau stays near 1 and L is
    # one day. This is the under-blocking section 7.4 warns of; section 16 item 2's
    # false-pass test decides whether M must be raised
    prob = 0.5 + 0.30 * np.sin(2 * np.pi * t / 720)
    monthly = st.block_length(
        pairs_of(np.where(rng.random(E) < prob, 1, -1), rng.integers(0, 2, E))
    )
    assert monthly.tau < 2.0 and monthly.L == 24


# --- the dependence-robust p-values ---------------------------------------------------


def ref_bootstrap(x, L, draws, seed, chunk=4096):
    """The circular block bootstrap with the same random starts, means in a loop."""
    rng = np.random.default_rng(seed)
    E = len(x)
    T = sum(x) / E
    c = [v - T for v in x]
    nb = -(-E // L)
    above = below = 0
    done = 0
    stars = []
    while done < draws:
        size = min(chunk, draws - done)
        starts = rng.integers(0, E, size=(size, nb))
        for row in starts:
            series = []
            for j in row:
                series += [c[(j + i) % E] for i in range(L)]
            series = series[:E]
            t_star = sum(series) / E
            stars.append(t_star)
            above += t_star >= T - 1e-12
            below += t_star <= T + 1e-12
        done += size
    return (
        (1 + above) / (draws + 1),
        (1 + below) / (draws + 1),
        float(np.std(stars, ddof=1)),
    )


def test_the_block_bootstrap_matches_a_loop_with_a_fixed_seed():
    rng = np.random.default_rng(8)
    x = rng.normal(0.05, 1.0, 137)
    for L in (1, 10, 24, 137):
        got = st.circular_block_bootstrap(x, L, 900, np.random.default_rng(42))
        up, lo, sd = ref_bootstrap(list(x), L, 900, 42)
        assert abs(got.p_upper - up) < TOL and abs(got.p_lower - lo) < TOL
        assert abs(got.sd - sd) < 1e-9
        # the same seed gives the same p-values again
        again = st.circular_block_bootstrap(x, L, 900, np.random.default_rng(42))
        assert again == got
        assert (
            abs(got.se_upper - math.sqrt(got.p_upper * (1 - got.p_upper) / 900)) < 1e-12
        )


def test_batch_means_matches_a_loop():
    rng = np.random.default_rng(9)
    x = rng.normal(0.02, 1, 1003)
    for L in (24, 50, 333):
        got = st.batch_means(x, L)
        K, dropped, mbar, se, pu, pl = ref_batch_means(list(x), L)
        assert (got.K, got.dropped) == (K, dropped)
        assert abs(got.mean - mbar) < TOL and abs(got.se - se) < TOL
        assert abs(got.p_upper - pu) < TOL and abs(got.p_lower - pl) < TOL


# --- floors, m = 0 and full coverage --------------------------------------------------


def _evaluate(p, draws=500, seed=0):
    b = st.block_length(p)
    return {
        s: st.evaluate_statistic(
            p, s, b, draws, np.random.default_rng(seed), np.random.default_rng(seed + 1)
        )
        for s in st.STATISTICS
    }, b


def test_the_floors_and_the_m_equals_0_case():
    rng = np.random.default_rng(10)
    up = (rng.random(3000) < 0.55).astype(np.int8)
    # "always up" with p_c >= 0.5: m = 0, exact p = 1, below the m and block floors
    res, b = _evaluate(pairs_of(np.ones(3000), up))
    hit = res[st.HIT]
    assert hit.p_exact == 1.0 and not hit.assessable and hit.p_holm == 1.0
    assert any("m = 0" in f for f in hit.below_floor)
    assert any("K = 1" in f for f in hit.below_floor)
    # fewer than 1,000 calls: both statistics NOT ASSESSABLE
    p = pairs_of(np.where(rng.random(3000) < 0.3, rng.choice([1, -1], 3000), 0), up)
    res, _ = _evaluate(p)
    assert all(not r.assessable for r in res.values())
    assert all(any("calls <" in f for f in r.below_floor) for r in res.values())


def test_full_coverage_leaves_a_one_sided_row_not_assessable():
    up = (np.random.default_rng(11).random(2000) < 0.5).astype(np.int8)
    res, _ = _evaluate(pairs_of(np.ones(2000), up, kind=st.UP_ONLY))
    assert res[st.HIT].p_exact == 1.0
    for r in res.values():
        assert not r.assessable and any("abstained" in f for f in r.below_floor)


def test_the_p_value_entering_holm_is_the_largest_component_each_in_turn():
    """Fixtures where the exact, the bootstrap and the batch-means p-value are in turn
    the largest; the one entering Holm is always that one."""
    seen = set()
    rng = np.random.default_rng(12)
    for trial in range(60):
        E = 2400
        persistent = trial % 3 == 0
        if persistent:
            calls = np.repeat(rng.choice([1, -1], size=E // 48), 48)
        else:
            calls = rng.choice([1, -1], size=E)
        edge = rng.uniform(0.0, 0.06)
        right = rng.random(E) < 0.5 + edge
        up = np.where(calls == 1, right, ~right).astype(np.int8)
        res, _ = _evaluate(pairs_of(calls, up), draws=2000, seed=trial)
        r = res[st.HIT]
        if not r.assessable:
            continue
        parts = {
            "exact": r.p_exact,
            "bootstrap": r.bootstrap.p_upper,
            "batch": r.batch.p_upper,
        }
        assert r.p_holm == max(parts.values())
        seen.add(max(parts, key=parts.get))
        mag = res[st.MAGNITUDE]
        assert mag.p_holm == max(mag.bootstrap.p_upper, mag.batch.p_upper)
        assert r.q_holm == max(
            r.q_exact, r.bootstrap_opposite.p_lower, r.batch_opposite.p_lower
        )
    assert seen == {"exact", "bootstrap", "batch"}


# --- Holm -------------------------------------------------------------------------------


def ref_holm_adjusted(ps):
    F = len(ps)
    order = sorted(range(F), key=lambda i: (ps[i], i))
    out = [0.0] * F
    for rank, i in enumerate(order):
        out[i] = min(
            1.0, max(min(1.0, (F - j) * ps[order[j]]) for j in range(rank + 1))
        )
    return out


def test_holm_by_adjusted_p_values_and_by_its_thresholds_agree():
    rng = np.random.default_rng(13)
    for _ in range(200):
        F = int(rng.integers(1, 40))
        ps = list(rng.random(F) ** 3)
        if rng.random() < 0.3:
            ps[: F // 2] = [1.0] * (F // 2)  # NOT ASSESSABLE members at p = 1
        adj = st.holm_adjusted(ps)
        assert max(abs(a - b) for a, b in zip(adj, ref_holm_adjusted(ps))) < 1e-12
        assert [a <= 0.05 for a in adj] == engine._step_down_survivors(ps, 0.05)


def test_holm_by_hand():
    ps = [0.01, 0.04, 0.03, 0.005, 0.2]
    # thresholds 0.05/5, /4, /3, /2, /1: 0.005 <= 0.01, 0.01 <= 0.0125, 0.03 > 0.0167
    assert st.holm_survivors(ps) == [True, False, False, True, False]
    assert st.holm_adjusted(ps) == pytest.approx([0.04, 0.09, 0.09, 0.025, 0.2])


# --- power ------------------------------------------------------------------------------


def test_the_closed_form_minimum_detectable_effects():
    rng = np.random.default_rng(14)
    E = 3000
    calls = rng.choice([1, 0], size=E, p=[0.5, 0.5])
    up = (rng.random(E) < 0.5).astype(np.int8)
    ret = rng.normal(0, 0.01, E)
    p = pairs_of(calls, up, ret, st.UP_ONLY)
    res, _ = _evaluate(p, draws=1000)
    za = st.z_upper(0.05 / 40)
    hit, mag = res[st.HIT], res[st.MAGNITUDE]
    assert (
        abs(st.mde_closed_form(p, hit, 40) - (za + st._NORMAL.inv_cdf(0.8)) * hit.se)
        < 1e-12
    )
    assert abs(st.mde_closed_form(p, mag, 40) - (za + 0.84) * mag.se) < 1e-12
    # the standard error used is the largest of the three
    assert hit.se == max(hit.se_independent, hit.se_bootstrap, hit.se_batch)


def test_the_two_sided_mde_by_simulation_is_above_the_planning_lower_bound():
    """Section 9's planning table gives lower bounds: at n = 2,190 and F = 76, at least
    6.1 points; the simulated MDE with the largest-of-three rule is at least that,
    within simulation error, and its ten runs agree with the pooled figure."""
    d = st.mde_two_sided_hit(2190, 2190, 0.5, 0.5, 76, "1h", 150, 10, 1)
    assert d["mde"] is not None
    assert d["mde"] >= 0.061 - 0.004
    assert d["mde"] < 0.10
    assert (
        len(d["replicates"]) == 10
        and d["replicate_min"] <= d["mde"] <= d["replicate_max"]
    )
    again = st.mde_two_sided_hit(2190, 2190, 0.5, 0.5, 76, "1h", 150, 10, 1)
    assert again == d  # the same seeds, the same figure


def test_the_95_percent_upper_bounds_cover_a_zero_edge():
    """Coverage on independent data at an up share of 0.5 and on persistent data
    (section 16 item 1): with no skill, the true edge (0) is below the 95% upper bound
    in at least about 95% of rows, for each statistic."""
    rng = np.random.default_rng(15)
    covered = {
        (kind, s): 0 for kind in ("independent", "persistent") for s in st.STATISTICS
    }
    trials = 120
    for t in range(trials):
        for kind in ("independent", "persistent"):
            E = 2400
            if kind == "independent":
                calls = rng.choice([1, -1], size=E)
                up = (rng.random(E) < 0.5).astype(np.int8)
                ret = np.where(up == 1, 1, -1) * rng.uniform(0.001, 0.01, E)
            else:
                calls = np.repeat(rng.choice([1, -1], size=E // 120), 120)
                regime = np.repeat(rng.uniform(-0.04, 0.04, E // 240), 240)
                up = (rng.random(E) < 0.5 + regime).astype(np.int8)
                ret = np.where(up == 1, 1, -1) * rng.uniform(0.001, 0.01, E)
            p = pairs_of(calls, up, ret)
            res, _ = _evaluate(p, draws=400, seed=t)
            for s in st.STATISTICS:
                ub = st.upper_bound_95(p, res[s])
                # the true edge over the best constant is at most 0 with no skill;
                # the de-meaned magnitude's true value is 0
                covered[(kind, s)] += ub >= 0.0
    for key, n in covered.items():
        assert n / trials >= 0.90, (key, n)
