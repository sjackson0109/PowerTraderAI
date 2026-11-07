"""
The venue compatibility test (FDS-SIG-004 section 5.2.3).

A model is evaluated on one venue. It runs on another only after that venue passes this
test, for the same model and code hash, over the latest 28 complete days for which both
venues have the full 1,224-bar history for the coin. Every feature, p̂ and the sign of the
expected value are computed from each venue's own bars, and the test passes when all of
these hold (the proposed tolerances, D17):

* each feature's Spearman correlation between the venues, pooled over coins and hours, is
  at least 0.90;
* the median absolute difference in p̂ is at most 0.02, and its 95th percentile at most
  0.05;
* the sign of the expected value agrees on at least 95% of hours.

A venue that fails, or has not been tested, has no predictive part. The protective part
uses each venue's own data and needs no compatibility test.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

import numpy as np

WINDOW_DAYS = 28
MIN_SPEARMAN = 0.90
MAX_MEDIAN_DP = 0.02
MAX_P95_DP = 0.05
MIN_SIGN_AGREEMENT = 0.95


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    import pandas as pd

    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return float("nan")
    return float(pd.Series(a[ok]).rank().corr(pd.Series(b[ok]).rank()))


def compatibility(
    features_a: Mapping[str, np.ndarray],
    features_b: Mapping[str, np.ndarray],
    p_a: np.ndarray,
    p_b: np.ndarray,
    ev_a: np.ndarray,
    ev_b: np.ndarray,
) -> Dict[str, Any]:
    """The test on aligned hours (the same hours, pooled over coins, from each venue)."""
    spearman = {
        name: _spearman(
            np.asarray(features_a[name], float), np.asarray(features_b[name], float)
        )
        for name in sorted(features_a)
    }
    p_a = np.asarray(p_a, dtype=float)
    p_b = np.asarray(p_b, dtype=float)
    ok = np.isfinite(p_a) & np.isfinite(p_b)
    dp = np.abs(p_a[ok] - p_b[ok])
    ev_a = np.asarray(ev_a, dtype=float)
    ev_b = np.asarray(ev_b, dtype=float)
    both = np.isfinite(ev_a) & np.isfinite(ev_b)
    agree = (
        float(np.mean((ev_a[both] > 0) == (ev_b[both] > 0)))
        if both.any()
        else float("nan")
    )
    median_dp = float(np.median(dp)) if len(dp) else float("nan")
    p95_dp = float(np.percentile(dp, 95)) if len(dp) else float("nan")
    checks = {
        "spearman": bool(spearman)
        and all(np.isfinite(v) and v >= MIN_SPEARMAN for v in spearman.values()),
        "median_dp": np.isfinite(median_dp) and median_dp <= MAX_MEDIAN_DP,
        "p95_dp": np.isfinite(p95_dp) and p95_dp <= MAX_P95_DP,
        "ev_sign": np.isfinite(agree) and agree >= MIN_SIGN_AGREEMENT,
    }
    return {
        "spearman": spearman,
        "median_dp": median_dp,
        "p95_dp": p95_dp,
        "ev_sign_agreement": agree,
        "hours": int(ok.sum()),
        "checks": {k: bool(v) for k, v in checks.items()},
        "passes": bool(all(checks.values())),
    }
