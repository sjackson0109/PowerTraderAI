"""
Block S, the volatility forecast, and the volatility shrink (FDS-SIG-004 sections 5.2
and 5.6).

**σ̂** is a forecast of the next 24 hours' volatility (the square root of their summed
squared hourly log returns), chosen from three declared candidates by QLIKE loss on the
development folds (Patton 2011):

* ``ewma``: an EWMA of hourly squared log returns, λ = 0.94 (RiskMetrics 1996), times 24.
  It starts after a burn-in of 168 bars (0.94^168 is about 3e-5);
* ``parkinson``: Parkinson's range variance over the last 24 bars (Parkinson 1980), times
  24;
* ``naive``: the last 24 hours' summed squared log returns.

The chosen candidate must beat the naive one, or the naive one is used (``choose``). Every
forecast at hour t uses bars that closed by t; the realised value it is scored against is
the next 24 hours', used only in evaluation.

**The shrink** (section 5.6): s_vol = min(1, σ_ref / σ̂), where σ_ref is the pooled
median of σ̂ over the evaluation's training rows, fixed and recorded with the evidence. It
only ever shrinks.
"""

from __future__ import annotations

import math
from typing import Dict, Sequence

import numpy as np

from signal_fusion.evaluation.scoring import qlike

LAMBDA = 0.94
BURN_IN = 168
HOURS = 24
CANDIDATES = ("ewma", "parkinson", "naive")


def _log_returns(close: np.ndarray) -> np.ndarray:
    c = np.asarray(close, dtype=float)
    out = np.full(len(c), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[1:] = np.log(c[1:] / c[:-1])
    return out


def _rolling_sum(x: np.ndarray, n: int) -> np.ndarray:
    import pandas as pd

    return pd.Series(x).rolling(n, min_periods=n).sum().to_numpy()


def variances(high, low, close) -> Dict[str, np.ndarray]:
    """Each candidate's forecast of the next 24 hours' variance, per hourly bar on a
    gap-free grid (NaN where it is not available)."""
    r = _log_returns(close)
    r2 = r**2
    n = len(r2)
    ewma = np.full(n, np.nan)
    v = None
    seen = 0
    for k in range(n):
        if not np.isfinite(r2[k]):
            v, seen = None, 0  # a missing return restarts the average
            continue
        v = r2[k] if v is None else LAMBDA * v + (1.0 - LAMBDA) * r2[k]
        seen += 1
        if seen > BURN_IN:
            ewma[k] = HOURS * v
    hl = np.log(np.asarray(high, dtype=float) / np.asarray(low, dtype=float)) ** 2
    park = _rolling_sum(hl, HOURS) / (4.0 * math.log(2.0))
    naive = _rolling_sum(r2, HOURS)
    return {"ewma": ewma, "parkinson": park, "naive": naive}


def realised(close) -> np.ndarray:
    """The next 24 hours' summed squared log returns, at each bar (evaluation only)."""
    r2 = _log_returns(close) ** 2
    s = _rolling_sum(r2, HOURS)
    out = np.full(len(s), np.nan)
    out[: len(s) - HOURS] = s[HOURS:]
    return out


def choose(forecasts: Dict[str, np.ndarray], truth: np.ndarray, rows: Sequence[int]):
    """The candidate with the lowest mean QLIKE on ``rows`` (the development folds' rows
    where every candidate and the truth exist), if it beats the naive one; else naive.
    (name, {candidate: mean QLIKE})."""
    rows = np.asarray(rows, dtype=np.int64)
    ok = np.isfinite(truth[rows]) & (truth[rows] > 0)
    for f in forecasts.values():
        ok &= np.isfinite(f[rows]) & (f[rows] > 0)
    use = rows[ok]
    losses = {
        name: float(np.mean(qlike(forecasts[name][use], truth[use])))
        for name in CANDIDATES
    }
    best = min(losses, key=losses.get)
    return (best if losses[best] < losses["naive"] else "naive"), losses


def sigma(variance: np.ndarray) -> np.ndarray:
    v = np.asarray(variance, dtype=float)
    return np.where(v > 0, np.sqrt(np.where(v > 0, v, 0.0)), np.nan)


def reference(sigma_rows: np.ndarray) -> float:
    """σ_ref: the pooled median of σ̂ over the training rows."""
    s = np.asarray(sigma_rows, dtype=float)
    s = s[np.isfinite(s) & (s > 0)]
    return float(np.median(s)) if len(s) else float("nan")


def shrink(sigma_hat, sigma_ref: float) -> np.ndarray:
    """s_vol = min(1, σ_ref / σ̂); NaN where σ̂ is missing (the shrink then fails closed
    when it is On)."""
    s = np.asarray(sigma_hat, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.minimum(1.0, sigma_ref / s)
    return np.where(np.isfinite(s) & (s > 0), out, np.nan)


def terciles(sigma_rows: np.ndarray):
    """The tercile cut points of σ̂ on the training rows."""
    s = np.asarray(sigma_rows, dtype=float)
    s = s[np.isfinite(s)]
    return tuple(float(x) for x in np.percentile(s, [100 / 3, 200 / 3]))


def tercile_of(sigma_hat, cuts) -> np.ndarray:
    """0, 1 or 2 for each σ̂ (-1 where it is missing)."""
    s = np.asarray(sigma_hat, dtype=float)
    out = np.searchsorted(np.asarray(cuts), s, side="right")
    return np.where(np.isfinite(s), out, -1)
