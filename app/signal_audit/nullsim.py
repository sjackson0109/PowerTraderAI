"""
Simulated no-skill data for FDS-SIG-001 section 16 item 2: rules that carry no
information must not pass, at or below 5% per family and alpha/F per test, within Monte
Carlo error.

Each scenario makes one row of eligible pairs whose calls are independent of the
outcomes given the regimes (no skill), in the forms section 16 item 2 lists:

* ``random``: seeded random calls, independent returns;
* ``near_constant``: "always up" with seeded 10% flips, at an up share above and below
  50%, exercising the best-constant comparator;
* ``persistent``: calls in runs of 100-200 bars over regime-drifting returns (month-long
  regimes in the up share, +-4 points, and in the mean return);
* ``drift``: calls drawn with a probability that drifts slowly (a cycle of two weeks to a
  month, random phase; or a fixed ``period_days``, such as exactly a month, the cycle
  the Bartlett window cannot see) by +-0.15 or +-0.30 around 0.5, over regime-drifting
  returns: a
  one-sided (up-only) candidate for the one-sided hit test, a two-sided one for the
  two-sided magnitude test.

``false_pass_rates`` runs the full test of section 7.4 (the exact, block bootstrap and
batch-means p-values, the largest entering Holm) on ``trials`` rows, in ``runs``
independent runs (the owner, 2026-11-06: every simulation locally, ten times over), and
reports per-test and per-family false-pass rates. A family is ``F`` independent rows'
tests; the family false-pass rate is the share of families with any Holm survivor.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from signal_audit import stats as st

MONTH_1H = 720


def _regimes(rng, E: int, length: int, size: float) -> np.ndarray:
    k = -(-E // length)
    return np.repeat(rng.uniform(-size, size, k), length)[:E]


def scenario(name: str, rng: np.random.Generator, E: int, **kw) -> st.Pairs:
    tf = kw.get("timeframe", "1h")
    if name == "random":
        calls = rng.choice([st.UP, st.DOWN], size=E)
        up = (rng.random(E) < 0.5).astype(np.int8)
        ret = np.where(up == 1, 1, -1) * rng.uniform(0.0005, 0.01, E)
        return st.Pairs(calls.astype(np.int8), up, ret, st.TWO_SIDED, tf)
    if name == "near_constant":
        share = kw["up_share"]
        calls = np.where(rng.random(E) < 0.10, st.DOWN, st.UP)
        up = (rng.random(E) < share).astype(np.int8)
        ret = np.where(up == 1, 1, -1) * rng.uniform(0.0005, 0.01, E)
        return st.Pairs(calls.astype(np.int8), up, ret, st.TWO_SIDED, tf)
    regime = _regimes(rng, E, MONTH_1H, 0.04)
    drift_ret = _regimes(rng, E, MONTH_1H, 0.002)
    up = (rng.random(E) < 0.5 + regime).astype(np.int8)
    ret = np.where(up == 1, 1, -1) * rng.uniform(0.0005, 0.01, E) + drift_ret
    up = (ret > 0).astype(np.int8)
    if name == "persistent":
        calls = np.empty(E, dtype=np.int8)
        i = 0
        while i < E:
            n = int(rng.integers(100, 201))
            calls[i : i + n] = rng.choice([st.UP, st.DOWN])
            i += n
        return st.Pairs(calls, up, ret, st.TWO_SIDED, tf)
    if name == "drift":
        amp = kw["amplitude"]
        if kw.get("period_days"):
            period = float(kw["period_days"]) * 24  # a fixed cycle (the worst case)
        else:
            period = rng.uniform(14 * 24, 30 * 24)
        phase = rng.uniform(0, 2 * math.pi)
        prob = 0.5 + amp * np.sin(2 * math.pi * np.arange(E) / period + phase)
        draw = rng.random(E) < prob
        if kw["kind"] == st.UP_ONLY:
            calls = np.where(draw, st.UP, st.ABSTAIN).astype(np.int8)
            return st.Pairs(calls, up, ret, st.UP_ONLY, tf)
        calls = np.where(draw, st.UP, st.DOWN).astype(np.int8)
        return st.Pairs(calls, up, ret, st.TWO_SIDED, tf)
    raise ValueError(name)


def false_pass_rates(
    name: str,
    statistic: str,
    trials: int,
    runs: int,
    family_size: int,
    E: int,
    seed: int,
    draws: Optional[int] = None,
    **kw,
) -> Dict[str, Any]:
    """Per-test and per-family false-pass rates of ``statistic`` on scenario ``name``.

    A test "passes" when it is assessable, its p-value entering Holm is at most
    alpha_1 = 5% / F and it meets its extra condition (a pass at Holm's first step,
    the strictest; per-test rate to compare with alpha / F). Families group ``F``
    consecutive trials and pass when any member survives Holm and meets its extra
    condition. NOT ASSESSABLE trials count as not passing, and are counted."""
    alpha1 = st.first_holm_alpha(family_size)
    B = draws or st.min_bootstrap_draws(family_size)
    out_runs = []
    for r in range(runs):
        rng = np.random.default_rng(int(seed) + r)
        passes = 0
        assessable = 0
        family_hits = 0
        families = 0
        member_p: List[float] = []
        member_ok: List[bool] = []
        for t in range(trials):
            p = scenario(name, rng, E, **kw)
            blocks = st.block_length(p)
            res = st.evaluate_statistic(
                p, statistic, blocks, B, rng, np.random.default_rng(rng.integers(2**63))
            )
            ok = res.assessable and res.extra_met
            assessable += res.assessable
            passes += int(ok and res.p_holm <= alpha1)
            member_p.append(res.p_holm)
            member_ok.append(ok)
            if len(member_p) == family_size:
                adj = st.holm_adjusted(member_p)
                families += 1
                family_hits += int(any(a <= 0.05 and o for a, o in zip(adj, member_ok)))
                member_p, member_ok = [], []
        out_runs.append(
            {
                "trials": trials,
                "assessable": assessable,
                "per_test_passes": passes,
                "per_test_rate": passes / trials,
                "families": families,
                "family_passes": family_hits,
                "family_rate": family_hits / families if families else None,
            }
        )
    total = sum(x["trials"] for x in out_runs)
    total_pass = sum(x["per_test_passes"] for x in out_runs)
    total_fam = sum(x["families"] for x in out_runs)
    fam_pass = sum(x["family_passes"] for x in out_runs)
    return {
        "scenario": name,
        "statistic": statistic,
        "params": kw,
        "E": E,
        "family_size": family_size,
        "alpha_1": alpha1,
        "bootstrap_draws": B,
        "runs": out_runs,
        "per_test_rate": total_pass / total,
        "per_test_mc_se": math.sqrt(alpha1 * (1 - alpha1) / total),
        "family_rate": fam_pass / total_fam if total_fam else None,
        "family_mc_se": math.sqrt(0.05 * 0.95 / total_fam) if total_fam else None,
        "seeds": [int(seed) + r for r in range(runs)],
    }
