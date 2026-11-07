"""FDS-SIG-001 section 16 item 2: no-skill rules never pass.

* "Always up" and "always down" are never PASS: they are NOT ASSESSABLE under the block
  floor, with the up share above and below 50%.
* Near-constant callers that clear the floors ("always up" with seeded 10% flips), seeded
  random calls, persistent signals (runs of 100-200 bars) over regime-drifting returns,
  and calls whose probability drifts slowly (weeks to a month) by +-0.15 and +-0.30 (the
  one-sided hit test and the two-sided magnitude test) pass at or below alpha / F per
  test and 5% per family, within Monte Carlo error (a binomial 99.9% bound).

This is the unit-scale run: one run of each scenario, 2,000 bootstrap draws. The full
scale (ten independent runs, B >= 100 / alpha_1; owner, 2026-11-06) is
``docs/dev/sig_false_pass_study.py``, and its results are the acceptance evidence
(``docs/dev/RUN-LOG-sig-1.md``).
"""

import os
import sys

import numpy as np
import pytest
from scipy.stats import binom

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from signal_audit import engine, nullsim  # noqa: E402
from signal_audit import stats as st  # noqa: E402
from signal_audit.pairs import RowPairs  # noqa: E402

F = 4
TRIALS = 160
E = 2190  # three months of 1h pairs
DRAWS = 2000


def _row(p: st.Pairs) -> RowPairs:
    n = p.eligible
    return RowPairs(
        p,
        1_767_225_600 + 3600 * np.arange(n, dtype=np.int64),
        np.ones(n),
        np.ones(n),
        n,
        0,
        0,
        0,
    )


@pytest.mark.parametrize("direction", [st.UP, st.DOWN])
@pytest.mark.parametrize("share", [0.53, 0.47])
def test_constant_callers_are_not_assessable(direction, share):
    rng = np.random.default_rng(1)
    up = (rng.random(E) < share).astype(np.int8)
    p = st.Pairs(
        np.full(E, direction, dtype=np.int8),
        up,
        np.where(up == 1, 0.003, -0.003),
        st.TWO_SIDED,
        "1h",
    )
    res = engine.evaluate_round(
        [(engine.RowKey("c", "x", "A", "1h"), _row(p))], DRAWS, 0
    )
    row = res.rows[0]
    assert row.verdict == engine.NOT_ASSESSABLE
    assert row.blocks.constant_calls and row.blocks.K == 1
    assert all(not row.results[s].assessable for s in st.STATISTICS)


SCENARIOS = [
    ("random", st.HIT, {}),
    ("random", st.MAGNITUDE, {}),
    ("near_constant", st.HIT, {"up_share": 0.53}),
    ("near_constant", st.HIT, {"up_share": 0.47}),
    ("persistent", st.HIT, {}),
    ("persistent", st.MAGNITUDE, {}),
    ("drift", st.HIT, {"amplitude": 0.15, "kind": st.UP_ONLY}),
    ("drift", st.HIT, {"amplitude": 0.30, "kind": st.UP_ONLY}),
    ("drift", st.MAGNITUDE, {"amplitude": 0.15, "kind": st.TWO_SIDED}),
    ("drift", st.MAGNITUDE, {"amplitude": 0.30, "kind": st.TWO_SIDED}),
    # a cycle of exactly a month, which the Bartlett window cannot see (block length
    # one day): the worst case for section 7.4's rule
    ("drift", st.HIT, {"amplitude": 0.30, "kind": st.UP_ONLY, "period_days": 30}),
    (
        "drift",
        st.MAGNITUDE,
        {"amplitude": 0.30, "kind": st.TWO_SIDED, "period_days": 30},
    ),
]


@pytest.mark.parametrize("name,statistic,kw", SCENARIOS)
def test_no_skill_rules_pass_at_or_below_the_nominal_rates(name, statistic, kw):
    r = nullsim.false_pass_rates(
        name, statistic, TRIALS, 1, F, E, 4242, draws=DRAWS, **kw
    )
    alpha1 = 0.05 / F
    per_test = r["runs"][0]["per_test_passes"]
    families = r["runs"][0]["families"]
    family = r["runs"][0]["family_passes"]
    assert per_test <= binom.ppf(0.999, TRIALS, alpha1), r
    assert family <= binom.ppf(0.999, families, 0.05), r


# --- a whole round (the PR #228 review, finding 4) ----------------------------------------
# The full scale (ten runs of whole rounds, F = 76, B >= 100 / alpha_1) is
# docs/dev/sig_round_false_pass_study.py; these check the simulation and the shortcut.


def test_a_simulated_round_is_round_ones_family_with_its_dependence():
    rng = np.random.default_rng(11)
    bars, names, start_s, end_s = nullsim.simulate_round(rng, coins=10, days=60)
    rows = nullsim.round_rows(bars, names, start_s, end_s, ("1h", "4h"))
    assert len(rows) == 38 and 2 * len(rows) == 76  # 10 x 2 SIG-A, 9 x 2 SIG-B
    btc = np.diff(np.log(bars[("BTC", "1h")].close))
    for name in names[1:]:
        coin = np.diff(np.log(bars[(name, "1h")].close))
        n = min(len(btc), len(coin))
        assert 0.5 < np.corrcoef(btc[:n], coin[:n])[0, 1] < 0.95  # one market factor
        # no lead: the sign of BTC's return says nothing of the coin's next one (within
        # four standard errors of a fair coin)
        agree = np.sign(btc[: n - 1]) * np.sign(coin[1:n])
        assert abs(agree.mean()) < 4 / np.sqrt(n - 1)
    # the nine SIG-B rows of a timeframe share BTC's calls
    sig_b = [
        d.pairs.calls for k, d in rows if k.candidate == "SIG-B" and k.timeframe == "1h"
    ]
    assert len(sig_b) == 9 and all(np.array_equal(sig_b[0], c) for c in sig_b[1:])
    # the 4h bars are the 1h bars aggregated: each 4h close is its last hour's close
    one, four = bars[("C01", "1h")], bars[("C01", "4h")]
    k = np.searchsorted(one.open_s, four.open_s + 3 * 3600)
    assert np.array_equal(one.close[k], four.close)
    # volume persists and rises with the absolute return
    v = np.log(one.volume)
    assert np.corrcoef(v[:-1], v[1:])[0, 1] > 0.5
    r = np.abs(np.diff(np.log(one.close)))
    assert np.corrcoef(v[1:], r)[0, 1] > 0.1


@pytest.mark.parametrize("seed,lead", [(3, {2: 0.3}), (4, {}), (5, {1: 0.12})])
def test_the_screened_round_reaches_the_engines_decisions(seed, lead):
    """The shortcut skips a bootstrap only where it cannot change a decision: every
    verdict, survivor and adjusted p-value at or below 5% is the engine's own."""
    rng = np.random.default_rng(seed)
    bars, names, start_s, end_s = nullsim.simulate_round(
        rng, coins=4, days=60, lead=lead
    )
    rows_data = nullsim.round_rows(bars, names, start_s, end_s, ("1h", "4h"))
    full = engine.evaluate_round(rows_data, draws=DRAWS, seed=9)
    rows = [
        nullsim.screened_row(i, k, d, DRAWS, 9, 0.05)[0]
        for i, (k, d) in enumerate(rows_data)
    ]
    engine.apply_holm(rows)
    skipped = 0
    for a, b in zip(rows, full.rows):
        a.verdict, a.passing = engine.verdict_of(a)
        assert (a.verdict, a.passing) == (b.verdict, b.passing), a.key
        assert a.survives == b.survives and a.survives_opposite == b.survives_opposite
        for s in st.STATISTICS:
            x, y = a.results[s], b.results[s]
            if x.bootstrap is None:  # skipped: a lower bound above 5% stands in
                skipped += 1
                assert min(x.p_holm, x.q_holm) > 0.05
                assert x.p_holm <= y.p_holm and x.q_holm <= y.q_holm
            else:  # evaluated: exactly the engine's, seeds included
                assert (x.p_holm, x.q_holm) == (y.p_holm, y.q_holm)
            for mine, theirs in (
                (a.holm[s], b.holm[s]),
                (a.holm_opposite[s], b.holm_opposite[s]),
            ):
                if theirs <= 0.05:
                    assert mine == theirs
    assert skipped > 0
    if lead.get(2) == 0.3:  # real skill is still found
        assert any(r.verdict == engine.PASS and r.key.coin == "C02" for r in rows)
