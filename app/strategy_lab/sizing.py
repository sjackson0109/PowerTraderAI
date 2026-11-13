"""
Sizing policies for research replays (PTAI-RD-001 work package 4.2; architecture layer
L6). Nothing in trading reads this module: the trader sizes as ``position_sizing`` says.

A policy gives each trade a **scale** from 0 to 1, applied once, at entry, to the amount
the account's own rules give it (``replay``'s ``scale``): a scaled amount below the
venue's minimum entry is skipped, never raised, and no position is ever topped up or cut
while it is held. So a policy only shrinks trades and never adds one.

* ``Fixed``: every trade at the account's own size (scale 1), as today.
* ``VolatilityTarget``: scale = min(cap, target / sigma), sigma the coin's volatility at
  the close of the bar that decided the trade (``Trade.decided``), from the feature
  library and so as of that close, annualised over a 365-day year (crypto trades every
  day). The cap is at most 1: a spot account cannot hold more than it has, so where
  Zarattini et al. (2025) size up to 200% this sizes up to 100%. A trade with no sigma
  (the estimator's warm-up) keeps scale 1 and is counted as ``unsized``.

**Random order** (``random_orders``): the same scales in a random order over the same
trades. Sizing by volatility helps only if it beats its own scales handed out at random;
the repository's earlier test of a volatility shrink did not (FDS-SIG-004 Q3, p = 0.69).

A policy is recorded with each run (``record``) and rebuilt from it (``from_record``).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Sequence

import numpy as np

import feature_library as fl
from strategy_lab.candidates import Trade

YEAR_S = 365 * 86_400
FIXED = "fixed"
VOLATILITY_TARGET = "volatility-target"
# the estimators a volatility target may use: per-bar volatility of returns
ESTIMATORS = (
    "volatility.ewma",
    "volatility.realised",
    "volatility.parkinson",
    "volatility.yang_zhang",
)
TARGET_BOUNDS = (0.05, 2.0)  # annualised


@dataclass(frozen=True)
class Sizing:
    """One policy's scale for each trade, in the trades' order."""

    scale: np.ndarray
    sigma: np.ndarray  # the annualised volatility used (NaN: none, or not used)
    unsized: int  # trades with no volatility, left at scale 1

    def summary(self) -> Dict[str, Any]:
        s = self.scale
        return {
            "trades": int(len(s)),
            "unsized": int(self.unsized),
            "mean_scale": float(np.mean(s)) if len(s) else None,
            "min_scale": float(np.min(s)) if len(s) else None,
            "share_below_one": float(np.mean(s < 1.0)) if len(s) else None,
        }


@dataclass(frozen=True)
class Fixed:
    id: str = FIXED

    def scales(self, sim, trades: Sequence[Trade]) -> Sizing:
        n = len(trades)
        return Sizing(np.ones(n), np.full(n, np.nan), 0)

    def record(self) -> Dict[str, Any]:
        return {"id": self.id}


@dataclass(frozen=True)
class VolatilityTarget:
    target: float = 0.25  # Zarattini et al.'s 25% a year
    feature: str = "volatility.ewma"
    params: Mapping[str, Any] = field(default_factory=dict)
    cap: float = 1.0
    id: str = VOLATILITY_TARGET

    def __post_init__(self) -> None:
        lo, hi = TARGET_BOUNDS
        if not lo <= float(self.target) <= hi:
            raise ValueError(f"the volatility target must be from {lo:.0%} to {hi:.0%}")
        if self.feature not in ESTIMATORS:
            raise ValueError(f"{self.feature} is not a volatility estimator")
        if not 0.0 < float(self.cap) <= 1.0:
            raise ValueError("the cap is above 0 and at most 1 (100%)")
        fl.get(self.feature).params(**dict(self.params))  # refuses bad parameters

    def scales(self, sim, trades: Sequence[Trade]) -> Sizing:
        per_year = math.sqrt(YEAR_S / float(sim.spec.bar_seconds))
        series: Dict[str, np.ndarray] = {}
        sigma = np.full(len(trades), np.nan)
        for k, t in enumerate(trades):
            if t.coin not in series:
                candles = sim.tables[t.coin].candles
                values = fl.compute(self.feature, candles, **dict(self.params))
                series[t.coin] = values.to_numpy(dtype=float) * per_year
            values = series[t.coin]
            if 0 <= t.decided < len(values):
                sigma[k] = values[t.decided]
        ok = np.isfinite(sigma) & (sigma > 0)
        scale = np.ones(len(trades))
        with np.errstate(divide="ignore", invalid="ignore"):
            scale[ok] = np.minimum(float(self.cap), float(self.target) / sigma[ok])
        return Sizing(scale, np.where(ok, sigma, np.nan), int((~ok).sum()))

    def record(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "target": float(self.target),
            "feature": fl.key(self.feature, dict(self.params)),
            "cap": float(self.cap),
        }


def from_record(record: Mapping[str, Any] | None):
    """The policy a run recorded (``Fixed`` for None or a record without one)."""
    if not record or record.get("id", FIXED) == FIXED:
        return Fixed()
    if record["id"] != VOLATILITY_TARGET:
        raise ValueError(f"no sizing policy {record['id']!r}")
    feature = str(record.get("feature", "volatility.ewma"))
    params: Dict[str, Any] = dict(record.get("params") or {})
    if "@" in feature:  # a recorded key: id@version{params}
        name, rest = feature.split("@", 1)
        brace = rest.find("{")
        if brace >= 0:
            params = {**json.loads(rest[brace:]), **params}
        feature = name
    return VolatilityTarget(
        target=float(record.get("target", 0.25)),
        feature=feature,
        params=params,
        cap=float(record.get("cap", 1.0)),
    )


def random_orders(scale: np.ndarray, draws: int, seed: int) -> np.ndarray:
    """``draws`` random orders of ``scale`` over the same trades: (draws, trades)."""
    rng = np.random.default_rng(seed)
    s = np.asarray(scale, dtype=float)
    out = np.empty((int(draws), len(s)))
    for d in range(int(draws)):
        out[d] = rng.permutation(s)
    return out
