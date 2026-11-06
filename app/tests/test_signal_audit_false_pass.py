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
