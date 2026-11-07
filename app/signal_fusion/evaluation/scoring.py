"""
Proper scoring rules and their diagnostics (FDS-SIG-004 sections 5.5 and 6.1).

* ``log_loss`` and ``brier``: strictly proper scoring rules (Gneiting and Raftery 2007),
  per row and as means. Probabilities are clipped to [1e-6, 1 - 1e-6] for every model
  alike before a log is taken (section 6.1).
* ``murphy``: the Brier score's decomposition into reliability, resolution and
  uncertainty (Murphy 1973), over 10 equal-count bins of the forecast. Binning makes it
  exact for the bins' mean forecasts; the rest of the Brier score is reported as
  ``within``, so the parts always add up to the Brier score.
* ``brier_skill``: 1 - Brier / Brier of the climatology, where each row's climatology is
  the base rate of its fold's training rows (never of the scored rows).
* ``calibration_intercept`` (a, calibration in the large: a logistic fit of the outcome
  with logit(p) as an offset, the slope held at 1) and ``calibration_slope`` (b: the
  slope of a logistic fit of the outcome on logit(p), Cox 1958). Both are fitted by
  Newton's method, unpenalised. They are diagnostics only and never change a forecast.
* ``sharpness``: the standard deviation of the forecasts and their 10th-to-90th
  percentile range.
* ``qlike``: the QLIKE loss of a variance forecast against a realised variance proxy
  (Patton 2011), r2 / s2 - ln(r2 / s2) - 1, which is 0 for a perfect forecast.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

EPS = 1e-6
BINS = 10


def clip(p) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=float), EPS, 1.0 - EPS)


def logit(p) -> np.ndarray:
    q = clip(p)
    return np.log(q / (1.0 - q))


def sigmoid(z) -> np.ndarray:
    z = np.asarray(z, dtype=float)
    return np.where(z >= 0, 1.0 / (1.0 + np.exp(-z)), np.exp(z) / (1.0 + np.exp(z)))


def log_loss_rows(y, p) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    q = clip(p)
    return -(y * np.log(q) + (1.0 - y) * np.log(1.0 - q))


def brier_rows(y, p) -> np.ndarray:
    return (np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2


def _mean(x, w=None) -> float:
    x = np.asarray(x, dtype=float)
    if w is None:
        return float(np.mean(x)) if len(x) else float("nan")
    w = np.asarray(w, dtype=float)
    return float(np.sum(w * x) / np.sum(w)) if np.sum(w) > 0 else float("nan")


def log_loss(y, p, w=None) -> float:
    return _mean(log_loss_rows(y, p), w)


def brier(y, p, w=None) -> float:
    return _mean(brier_rows(y, p), w)


def brier_skill(y, p, climatology) -> float:
    """1 - Brier(p) / Brier(climatology)."""
    ref = brier(y, climatology)
    return 1.0 - brier(y, p) / ref if ref > 0 else float("nan")


def equal_count_bins(p, bins: int = BINS) -> np.ndarray:
    """Each row's bin, 0 to bins - 1, by rank of the forecast (ties broken by order)."""
    p = np.asarray(p, dtype=float)
    n = len(p)
    out = np.zeros(n, dtype=np.int64)
    if n:
        order = np.argsort(p, kind="stable")
        out[order] = (np.arange(n) * bins) // n
    return out


def reliability_table(y, p, bins: int = BINS):
    """Per bin: (rows, mean forecast, observed frequency)."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    b = equal_count_bins(p, bins)
    rows = []
    for k in range(bins):
        m = b == k
        if m.any():
            rows.append((int(m.sum()), float(p[m].mean()), float(y[m].mean())))
    return rows


def murphy(y, p, bins: int = BINS) -> Dict[str, float]:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    n = len(y)
    base = float(y.mean()) if n else float("nan")
    rel = res = 0.0
    for count, f, o in reliability_table(y, p, bins):
        rel += count * (f - o) ** 2
        res += count * (o - base) ** 2
    rel /= max(n, 1)
    res /= max(n, 1)
    unc = base * (1.0 - base)
    total = brier(y, p)
    return {
        "brier": total,
        "reliability": rel,
        "resolution": res,
        "uncertainty": unc,
        "within": total - (rel - res + unc),
    }


def calibration_intercept(
    y, p, w=None, iterations: int = 100, tol: float = 1e-12
) -> float:
    """a in logit(P(y = 1)) = a + logit(p): Newton's method on the score equation."""
    y = np.asarray(y, dtype=float)
    z = logit(p)
    w = np.ones(len(y)) if w is None else np.asarray(w, dtype=float)
    a = 0.0
    for _ in range(iterations):
        q = sigmoid(a + z)
        grad = float(np.sum(w * (y - q)))
        hess = float(np.sum(w * q * (1.0 - q)))
        if hess <= 0:
            return float("nan")
        step = grad / hess
        a += step
        if abs(step) < tol:
            break
    return float(a)


def calibration_slope(
    y, p, w=None, iterations: int = 100, tol: float = 1e-12
) -> Tuple[float, float]:
    """(alpha, b) in logit(P(y = 1)) = alpha + b logit(p): Newton's method (IRLS)."""
    y = np.asarray(y, dtype=float)
    z = logit(p)
    w = np.ones(len(y)) if w is None else np.asarray(w, dtype=float)
    x = np.column_stack([np.ones(len(z)), z])
    beta = np.zeros(2)
    for _ in range(iterations):
        q = sigmoid(x @ beta)
        grad = x.T @ (w * (y - q))
        hess = (x * (w * q * (1.0 - q))[:, None]).T @ x
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            return float("nan"), float("nan")
        beta = beta + step
        if np.max(np.abs(step)) < tol:
            break
    return float(beta[0]), float(beta[1])


def sharpness(p) -> Dict[str, float]:
    p = np.asarray(p, dtype=float)
    if not len(p):
        return {"std": float("nan"), "p10_p90": float("nan")}
    lo, hi = np.percentile(p, [10.0, 90.0])
    return {"std": float(np.std(p)), "p10_p90": float(hi - lo)}


def qlike(variance_forecast, realised) -> np.ndarray:
    """Per row; NaN where either is not positive."""
    s = np.asarray(variance_forecast, dtype=float)
    r = np.asarray(realised, dtype=float)
    ok = (s > 0) & (r > 0)
    ratio = np.where(ok, r / np.where(ok, s, 1.0), np.nan)
    return np.where(ok, ratio - np.log(np.where(ok, ratio, 1.0)) - 1.0, np.nan)


def summary(y, p, climatology: Optional[Any] = None) -> Dict[str, Any]:
    """Every measure of section 5.5 for one set of scored rows."""
    out: Dict[str, Any] = {
        "rows": int(len(np.asarray(y))),
        "events": int(np.sum(np.asarray(y) == 1)),
        "log_loss": log_loss(y, p),
        **murphy(y, p),
        "reliability_table": reliability_table(y, p),
        "intercept": calibration_intercept(y, p),
        "slope": calibration_slope(y, p)[1],
        "sharpness": sharpness(p),
    }
    if climatology is not None:
        out["brier_skill"] = brier_skill(y, p, climatology)
    return out
