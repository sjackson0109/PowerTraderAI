"""
Features of the pooled contestants (FDS-MH-001 section 5.5, amendment 1).

**Complete bars only.** A feature at an hour uses only bars that closed by that hour.
Every feature is scale-free (a log, a ratio or a share of a range), so coins can share
one model.

**The hourly grid.** A coin's bars are laid on a grid of every hour from its first bar to
its last. An hour with no bar (a gap the series keeps, 24 hours at most) is missing, and
so is an invalid bar: a low at or below 0, a high below the low, an open or close outside
[low, high], a negative volume, or a value that is not a finite number. A missing hour is
never a row, and a feature that needs it is missing. For volume, a missing hour counts as
zero volume in a sum, because no trade was reported then.

**The 26 features** (section 5.5's order), each at hour t, with C, O, H, L, V the bar's
close, open, high, low and volume:

* ``r1`` ... ``r336``: ln(C_t / C_{t-h}) for h = 1, 4, 12, 24, 72, 168 and 336 hours;
* ``rv24``, ``rv168``: the root mean square of the hourly log returns over the last 24 or
  168 hours, and ``rv_ratio`` = rv24 / rv168;
* ``park24``: Parkinson's range volatility over the last 24 hours,
  sqrt(mean(ln(H / L)^2) / (4 ln 2));
* ``ma24`` ... ``ma1200``: ln(C_t / the mean close over the last 24, 168, 720 and 1,200
  hours), that is 24 hours, 7, 30 and 50 days of hourly closes;
* ``dd30``, ``up30``: ln(C_t / the highest high) and ln(C_t / the lowest low) over the last
  720 hours;
* ``v1``: ln(the last 24 hours' volume / the mean daily volume of the 30 completed UTC days
  that end with the last completed day);
* ``body``, ``wick_up``, ``wick_down``: (C - O), (H - max(O, C)) and (min(O, C) - L), each
  over H - L (all 0 when H = L);
* ``btc_r24``, ``btc_r168``, ``btc_rv168``: BTC's r24, r168 and rv168 at the same hour;
* ``rel_r24``, ``rel_r168``: the coin's r24 and r168 minus BTC's.

A rolling statistic needs at least 90% of its window's hours. A log of 0 or of a negative
number is missing.

**Blocks** (amendment 1): ``P``, the 25 features other than ``v1``; ``v1``; ``v2``, ln(the
hour's volume / the mean volume of the same UTC hour on the 20 previous days); and ``V`` =
``v1`` and ``v2``. Batch 1's pooled contestants use P and v1: the 26 above.

**The placebo** (section 7a). Variant j's block at hour t is V at hour t - lag_j, on the same
coin's grid: Ṽ_j(t) = V(t - lag_j). It uses only bars that closed by t - lag_j, never a later
bar, and nothing wraps. When t - lag_j is before the grid's first hour, or V is missing there,
the placebo is missing. A series always starts after its last gap longer than 24 hours
(``series``), so t - lag_j is always in the same series as t.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

import numpy as np

from model_lab.series import DAY_S, HOUR_S, Series

RETURN_HOURS = (1, 4, 12, 24, 72, 168, 336)
MEAN_HOURS = (24, 168, 720, 1200)
COVERAGE = 0.9  # a rolling statistic needs this share of its window's hours

# section 5.5's 26, in its order
FEATURES_26: Tuple[str, ...] = (
    *(f"r{h}" for h in RETURN_HOURS),
    "rv24",
    "rv168",
    "rv_ratio",
    "park24",
    *(f"ma{h}" for h in MEAN_HOURS),
    "dd30",
    "up30",
    "v1",
    "body",
    "wick_up",
    "wick_down",
    "btc_r24",
    "btc_r168",
    "btc_rv168",
    "rel_r24",
    "rel_r168",
)
P: Tuple[str, ...] = tuple(n for n in FEATURES_26 if n != "v1")
V: Tuple[str, ...] = ("v1", "v2")
BLOCKS: Dict[str, Tuple[str, ...]] = {"P": P, "v1": ("v1",), "v2": ("v2",), "V": V}

# the placebo's lags (section 7a): 3,840 + 24 a_j + b_j hours, seeded
PLACEBO_SEED = 700000
PLACEBO_VARIANTS = 5


def placebo_lags(
    n: int = PLACEBO_VARIANTS, seed: int = PLACEBO_SEED
) -> Tuple[int, ...]:
    """The placebo's lags in hours, for j = 1 to n: with r = random.Random(seed + j),
    a_j = int(10 r.random()), then b_j = 1 + int(23 r.random())."""
    out = []
    for j in range(1, n + 1):
        r = random.Random(seed + j)
        a = int(10 * r.random())
        b = 1 + int(23 * r.random())
        out.append(160 * 24 + 24 * a + b)
    return tuple(out)


PLACEBO_LAGS = placebo_lags()


def placebo_names(lag: int) -> Tuple[str, ...]:
    return tuple(f"{name}@{int(lag)}h" for name in V)


def block_names(spec: Sequence[str]) -> Tuple[str, ...]:
    """The feature names of the blocks in ``spec``: "P", "v1", "v2", "V", or "Vp<j>" for
    the placebo's variant j (1 to 5)."""
    out = []
    for b in spec:
        if b.startswith("Vp"):
            out += placebo_names(PLACEBO_LAGS[int(b[2:]) - 1])
        else:
            out += BLOCKS[b]
    return tuple(out)


# --- the hourly grid ---------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Grid:
    """A coin's bars on a grid of every hour: ``close_s`` is each hour's close time;
    prices and volume are NaN where the hour is missing (``present`` False)."""

    coin: str
    close_s: np.ndarray
    present: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    def __len__(self) -> int:
        return int(len(self.close_s))

    def positions(self, close_s: Sequence[int]) -> np.ndarray:
        """Each close time's grid position, or -1 when it is not on the grid."""
        t = np.asarray(close_s, dtype=np.int64)
        if not len(self.close_s):
            return np.full(len(t), -1, dtype=np.int64)
        k = (t - int(self.close_s[0])) // HOUR_S
        ok = (
            (k >= 0)
            & (k < len(self.close_s))
            & ((t - int(self.close_s[0])) % HOUR_S == 0)
        )
        return np.where(ok, k, -1)


def valid_bars(o, h, lo, c, v) -> np.ndarray:
    """Which bars are valid (the module docstring)."""
    with np.errstate(invalid="ignore"):
        finite = (
            np.isfinite(o) & np.isfinite(h) & np.isfinite(lo) & np.isfinite(c)
        ) & np.isfinite(v)
        return (
            finite
            & (lo > 0)
            & (h >= lo)
            & (o >= lo)
            & (o <= h)
            & (c >= lo)
            & (c <= h)
            & (v >= 0)
        )


def grid(series: Series) -> Grid:
    if not len(series):
        empty = np.array([], dtype=float)
        return Grid(
            series.coin,
            np.array([], dtype=np.int64),
            np.array([], dtype=bool),
            empty,
            empty,
            empty,
            empty,
            empty,
        )
    first = int(series.close_s[0])
    n = (int(series.close_s[-1]) - first) // HOUR_S + 1
    k = (series.close_s - first) // HOUR_S
    ok = valid_bars(series.open, series.high, series.low, series.close, series.volume)
    present = np.zeros(n, dtype=bool)
    present[k[ok]] = True

    def lay(values: np.ndarray) -> np.ndarray:
        out = np.full(n, np.nan)
        out[k[ok]] = values[ok]
        return out

    return Grid(
        series.coin,
        first + HOUR_S * np.arange(n, dtype=np.int64),
        present,
        lay(series.open),
        lay(series.high),
        lay(series.low),
        lay(series.close),
        lay(series.volume),
    )


# --- rolling helpers ----------------------------------------------------------------------


def _rolling(values: np.ndarray, window: int, how: str) -> np.ndarray:
    import pandas as pd

    r = pd.Series(values).rolling(window, min_periods=math.ceil(COVERAGE * window))
    return getattr(r, how)().to_numpy()


def _shift(values: np.ndarray, hours: int) -> np.ndarray:
    """values[k - hours] at position k (NaN before the start); never a later value."""
    out = np.full(len(values), np.nan)
    if hours < len(values):
        out[hours:] = values[: len(values) - hours]
    return out


def _log(x: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(x > 0, np.log(np.where(x > 0, x, 1.0)), np.nan)


def _ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where((b > 0) & np.isfinite(a), a / np.where(b > 0, b, 1.0), np.nan)


def _price_features(g: Grid) -> Dict[str, np.ndarray]:
    log_c = _log(g.close)
    out: Dict[str, np.ndarray] = {}
    for h in RETURN_HOURS:
        out[f"r{h}"] = log_c - _shift(log_c, h)
    r1sq = out["r1"] ** 2
    out["rv24"] = np.sqrt(_rolling(r1sq, 24, "mean"))
    out["rv168"] = np.sqrt(_rolling(r1sq, 168, "mean"))
    out["rv_ratio"] = _ratio(out["rv24"], out["rv168"])
    hl = _log(_ratio(g.high, g.low)) ** 2
    out["park24"] = np.sqrt(_rolling(hl, 24, "mean") / (4.0 * math.log(2.0)))
    for h in MEAN_HOURS:
        out[f"ma{h}"] = log_c - _log(_rolling(g.close, h, "mean"))
    out["dd30"] = log_c - _log(_rolling(g.high, 720, "max"))
    out["up30"] = log_c - _log(_rolling(g.low, 720, "min"))
    rng = g.high - g.low
    flat = rng == 0
    with np.errstate(divide="ignore", invalid="ignore"):
        safe = np.where(flat, 1.0, rng)
        out["body"] = np.where(flat, 0.0, (g.close - g.open) / safe)
        out["wick_up"] = np.where(
            flat, 0.0, (g.high - np.maximum(g.open, g.close)) / safe
        )
        out["wick_down"] = np.where(
            flat, 0.0, (np.minimum(g.open, g.close) - g.low) / safe
        )
    return out


def _volume_features(g: Grid) -> Dict[str, np.ndarray]:
    n = len(g)
    vz = np.where(g.present, g.volume, 0.0)  # a missing hour: no trade reported
    out: Dict[str, np.ndarray] = {}
    # v1: the last 24 hours over the mean of the 30 completed days ending yesterday's
    total = np.concatenate([[0.0], np.cumsum(vz)])
    last24 = np.full(n, np.nan)
    if n >= 24:
        last24[23:] = total[24:] - total[: n - 23]
    first_close = int(g.close_s[0]) if n else 0
    day = (g.close_s - HOUR_S) // DAY_S  # each hour's UTC day (its bar's open day)
    first_full_day = -(
        -(first_close - HOUR_S) // DAY_S
    )  # the first whole day on the grid
    last_done = g.close_s // DAY_S - 1  # the last completed UTC day at each close
    # daily volume of every whole day on the grid, by day number
    days = np.arange(first_full_day, (int(g.close_s[-1]) // DAY_S) if n else 0)
    by_day = np.zeros(len(days))
    if len(days):
        in_range = (day >= days[0]) & (day <= days[-1])
        np.add.at(by_day, (day[in_range] - days[0]).astype(np.int64), vz[in_range])
    day_total = np.concatenate([[0.0], np.cumsum(by_day)])
    lo_day = last_done - 29
    ok = (lo_day >= first_full_day) & (last_done <= (days[-1] if len(days) else -1))
    mean30 = np.full(n, np.nan)
    if len(days):
        a = np.where(ok, lo_day - days[0], 0).astype(np.int64)
        b = np.where(ok, last_done - days[0] + 1, 0).astype(np.int64)
        mean30 = np.where(ok, (day_total[b] - day_total[a]) / 30.0, np.nan)
    out["v1"] = _log(_ratio(last24, mean30))
    # v2: the hour's volume over the same UTC hour on the 20 previous days
    same = np.zeros(n)
    have = np.zeros(n, dtype=bool)
    if n > 480:
        have[480:] = True
        for d in range(1, 21):
            same[480:] += vz[480 - 24 * d : n - 24 * d]
    mean_same = np.where(have, same / 20.0, np.nan)
    hour_v = np.where(g.present, g.volume, np.nan)
    out["v2"] = _log(_ratio(hour_v, mean_same))
    return out


# --- the feature table --------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Table:
    """A coin's features on its grid (NaN where missing)."""

    grid: Grid
    values: Dict[str, np.ndarray]

    def column(self, name: str) -> np.ndarray:
        if name in self.values:
            return self.values[name]
        base, _, lag = name.partition("@")
        if lag:  # a placebo column: V lagged on the same grid
            return _shift(self.values[base], int(lag.rstrip("h")))
        raise KeyError(name)

    def matrix(self, names: Sequence[str]) -> np.ndarray:
        """Every grid hour's features, one column per name."""
        if not len(self.grid):
            return np.zeros((0, len(names)))
        return np.column_stack([self.column(n) for n in names])

    def complete(self, names: Sequence[str]) -> np.ndarray:
        """The grid hours where the bar is present and every named feature is a
        number."""
        x = self.matrix(names)
        return self.grid.present & np.isfinite(x).all(axis=1)


def build(series: Series, btc: Optional[Series]) -> Table:
    """The coin's feature table, with BTC's figures from ``btc`` (the coin's own when it
    is BTC)."""
    g = grid(series)
    values = {**_price_features(g), **_volume_features(g)}
    mine = (values["r24"], values["r168"], values["rv168"])
    if btc is None or btc is series:
        theirs = mine
    else:
        bt = build_price_only(btc)
        k = bt.positions(g.close_s)
        ok = k >= 0
        theirs = tuple(
            np.where(ok, col[np.where(ok, k, 0)], np.nan)
            for col in (bt.values["r24"], bt.values["r168"], bt.values["rv168"])
        )
    values["btc_r24"], values["btc_r168"], values["btc_rv168"] = theirs
    values["rel_r24"] = values["r24"] - values["btc_r24"]
    values["rel_r168"] = values["r168"] - values["btc_r168"]
    for name in values:
        values[name] = np.where(g.present, values[name], np.nan)
    return Table(g, values)


@dataclass(frozen=True, eq=False)
class _PriceOnly:
    grid: Grid
    values: Dict[str, np.ndarray]

    def positions(self, close_s) -> np.ndarray:
        return self.grid.positions(close_s)


def build_price_only(series: Series) -> _PriceOnly:
    g = grid(series)
    values = _price_features(g)
    return _PriceOnly(
        g, {n: np.where(g.present, values[n], np.nan) for n in ("r24", "r168", "rv168")}
    )


def table(data, coin: str) -> Table:
    """The coin's feature table for ``data`` (a ``LabData``), built once."""
    key = ("features", coin)
    if key not in data.cache:
        btc = data.series.get(data.context)
        data.cache[key] = build(data.series[coin], btc)
    return data.cache[key]


def common_mask(t: Table, lags: Sequence[int] = PLACEBO_LAGS) -> np.ndarray:
    """The common rows of batch PV-1 (section 7a): where P, V and every placebo variant
    exist."""
    names = list(P) + list(V)
    for lag in lags:
        names += placebo_names(lag)
    return t.complete(names)
