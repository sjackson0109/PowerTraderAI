"""
The meta-models F_P and F_PV on M, and their calibration (FDS-SIG-004 sections 5.4 and
5.5).

**The model:** a regularised logistic regression (L2, C = 1), its features standardised on
the training rows only, fitted at the start of each fold on every opportunity before it.

**Purge by the trade's own exit.** A training row is an opportunity whose trade exited by
the fold's start and has a label (a trade the bars forced closed has none).

**Calibration, strictly out of fold** (Platt 1999). For fold k, a two-parameter logistic
fit of M on logit(the raw probability), over the out-of-fold predictions of the folds
before k whose trades exited by fold k's start; it never sees fold k's rows. Fold 1 has no
calibration, so its rows have no eligible probability (the live veto fails open there).

**Climatology:** each row's reference is the base rate of M on its fold's training rows,
never on the scored rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from signal_fusion.evaluation import scoring as sc


@dataclass
class Fit:
    model: Any
    mean: np.ndarray
    std: np.ndarray
    rows: int
    base_rate: float

    def raw(self, x: np.ndarray) -> np.ndarray:
        if self.model is None or not len(x):
            return np.full(len(x), np.nan)
        return self.model.predict_proba((x - self.mean) / self.std)[:, 1]


def fit(x: np.ndarray, y: np.ndarray) -> Fit:
    """One fold's fit; an empty or one-class training set gives no model."""
    y = np.asarray(y, dtype=int)
    n = len(y)
    base = float(y.mean()) if n else float("nan")
    if n == 0 or len(np.unique(y)) < 2:
        return Fit(None, np.zeros(x.shape[1]), np.ones(x.shape[1]), n, base)
    from sklearn.linear_model import LogisticRegression

    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std = np.where(std > 0, std, 1.0)
    model = LogisticRegression(C=1.0, max_iter=1000)
    model.fit((x - mean) / std, y)
    return Fit(model, mean, std, n, base)


@dataclass(frozen=True)
class Platt:
    alpha: float
    beta: float
    rows: int

    def apply(self, raw: np.ndarray) -> np.ndarray:
        return sc.sigmoid(self.alpha + self.beta * sc.logit(raw))


def platt(raw: np.ndarray, y: np.ndarray) -> Optional[Platt]:
    raw = np.asarray(raw, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = np.isfinite(raw)
    if ok.sum() < 2 or len(np.unique(y[ok])) < 2:
        return None
    alpha, beta = sc.calibration_slope(y[ok], raw[ok])
    if not (np.isfinite(alpha) and np.isfinite(beta)):
        return None
    return Platt(alpha, beta, int(ok.sum()))


@dataclass
class WalkForward:
    """Per opportunity: its fold, the raw and calibrated probabilities (NaN where there is
    none), and its climatology."""

    fold: np.ndarray
    raw: np.ndarray
    calibrated: np.ndarray
    climatology: np.ndarray
    fits: List[Dict[str, Any]]


def walk_forward(
    x: np.ndarray,
    label: np.ndarray,
    signal_s: Sequence[int],
    exit_s: Sequence[int],
    folds: Sequence[Tuple[int, int]],
) -> WalkForward:
    """Fit at each fold's start on the rows whose trades exited by then; score the fold's
    rows (those whose signal falls in it). ``label`` is M, or -1 for a forced trade.
    Rows with a missing feature are never used and get no probability."""
    x = np.asarray(x, dtype=float)
    label = np.asarray(label, dtype=int)
    t = np.asarray(signal_s, dtype=np.int64)
    done = np.asarray(exit_s, dtype=np.int64)
    complete = np.isfinite(x).all(axis=1)
    n = len(label)
    fold = np.full(n, -1, dtype=np.int64)
    raw = np.full(n, np.nan)
    cal = np.full(n, np.nan)
    clim = np.full(n, np.nan)
    fits = []
    for k, (a, b) in enumerate(folds):
        here = (t >= a) & (t < b)
        fold[here] = k
        train = complete & (label >= 0) & (done <= a)
        f = fit(x[train], label[train])
        rows = here & complete
        raw[rows] = f.raw(x[rows])
        clim[here] = f.base_rate
        # calibration: earlier folds' out-of-fold predictions, their trades done by a
        earlier = (
            (fold >= 0) & (fold < k) & np.isfinite(raw) & (label >= 0) & (done <= a)
        )
        p = platt(raw[earlier], label[earlier]) if k > 0 else None
        if p is not None:
            cal[rows] = p.apply(raw[rows])
        fits.append(
            {
                "fold": k + 1,
                "training_rows": int(train.sum()),
                "base_rate": f.base_rate,
                "calibration_rows": p.rows if p else 0,
                "platt": [p.alpha, p.beta] if p else None,
            }
        )
    return WalkForward(fold, raw, cal, clim, fits)
