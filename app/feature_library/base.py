"""
The feature library's registry (PTAI-RD-001 work package 4.1; architecture layer L2).

A **feature** turns a coin's candles into one value per bar. Each has an id, a version,
the candle columns it reads, default parameters, and a warm-up: the number of leading
bars without a value. Windows are counted in bars; the caller chooses the timeframe.

**As of each bar.** A feature's value at bar t reads only bars 0..t: computing it on the
candles up to t gives the same value as computing it on all of them (``as_of_problems``
checks this). No value looks ahead.

**Window-local or start-dependent.** A window-local feature reads only its own window
(for example the last 20 closes), so where the candles start does not matter once the
window is full. A start-dependent one (an exponential average) carries the whole
history with a decaying weight: its warm-up is a burn-in, after which the start matters
little but not nothing. ``Feature.window_local`` says which.

* ``register(feature)``, ``FEATURES``: the registry, by id.
* ``compute(feature_id, candles, **params)``: the feature's values, a float Series on
  the candles' index, NaN during the warm-up and where its inputs are missing.
* ``key(feature_id, params)``: the id, version and full parameters as one string, for
  caching by (dataset snapshot, key).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Tuple

import numpy as np
import pandas as pd

COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class Feature:
    id: str  # "family.name"
    version: int
    summary: str
    inputs: Tuple[str, ...]  # the candle columns it reads
    defaults: Mapping[str, Any]
    fn: Callable[[pd.DataFrame, Mapping[str, Any]], pd.Series]
    warmup: Callable[[Mapping[str, Any]], int]  # leading bars without a value
    window_local: bool = True
    bounds: Mapping[str, Tuple[float, float]] = field(default_factory=dict)

    @property
    def family(self) -> str:
        return self.id.split(".", 1)[0]

    def params(self, **given) -> Dict[str, Any]:
        """The defaults with ``given`` over them; an unknown name or a value outside
        its bounds is refused."""
        unknown = set(given) - set(self.defaults)
        if unknown:
            raise ValueError(f"{self.id}: unknown parameter(s) {sorted(unknown)}")
        out = {**self.defaults, **given}
        for name, (lo, hi) in self.bounds.items():
            if not lo <= out[name] <= hi:
                raise ValueError(f"{self.id}: {name} must be from {lo} to {hi}")
        return out


FEATURES: Dict[str, Feature] = {}


def register(feature: Feature) -> Feature:
    if feature.id in FEATURES:
        raise ValueError(f"feature {feature.id} is registered twice")
    FEATURES[feature.id] = feature
    return feature


def get(feature_id: str) -> Feature:
    try:
        return FEATURES[feature_id]
    except KeyError:
        raise KeyError(f"no feature {feature_id!r}") from None


def compute(feature_id: str, candles: pd.DataFrame, **params) -> pd.Series:
    """``feature_id``'s values on ``candles`` (module docstring)."""
    f = get(feature_id)
    p = f.params(**params)
    missing = [c for c in f.inputs if c not in candles.columns]
    if missing:
        raise ValueError(f"{feature_id}: the candles have no {missing}")
    out = f.fn(candles, p).astype(float)
    out = out.replace([np.inf, -np.inf], np.nan)
    out.iloc[: min(len(out), f.warmup(p))] = np.nan
    out.name = key(feature_id, p)
    return out


def key(feature_id: str, params: Mapping[str, Any]) -> str:
    """``id@version`` and the full parameters, canonical: the same feature and
    parameters always give the same key."""
    f = get(feature_id)
    full = f.params(**dict(params))
    return f"{f.id}@{f.version}" + json.dumps(
        full, sort_keys=True, separators=(",", ":")
    )


def as_of_problems(
    feature_id: str, candles: pd.DataFrame, cuts: List[int], **params
) -> List[int]:
    """The cuts t at which computing on bars 0..t changes any value up to t (none for
    a feature that never looks ahead)."""
    full = compute(feature_id, candles, **params).to_numpy()
    bad = []
    for t in cuts:
        part = compute(
            feature_id, candles.iloc[: t + 1].reset_index(drop=True), **params
        ).to_numpy()
        if not np.allclose(part, full[: t + 1], equal_nan=True, rtol=1e-12, atol=0):
            bad.append(t)
    return bad
