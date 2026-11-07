"""
Block L, liquidity (FDS-SIG-004 sections 5.2 and 5.7).

**Approximate dollar volume of a bar:** DV̂ = TP x V, where TP = (H + L + C) / 3 is the
typical price and V the base volume. It approximates the bar's true traded value,
DV = VWAP x V, which Coinbase does not state; it is labelled approximate everywhere and
never called quote volume.

**Relative error is defined against the true value:** e = |DV̂ - DV| / DV = |TP - VWAP| /
VWAP. Every trade, so VWAP, lies between L and H, and so does TP. When L > 0 and V > 0:

    e <= ē = max((TP - L) / L, (H - TP) / H),

the least bound the bar's OHLC supports. With the estimate as denominator the bound is
different (max(TP - L, H - TP) / TP); it is never used here, and no tighter bound is
claimed.

**Zero volume:** DV̂ = DV = 0; the hour counts as 0 in sums and medians and has no ē.
**An invalid bar** (L <= 0, H < L, O or C outside [L, H], V < 0, a value that is not a
finite number) has a missing DV̂: never 0, left out of medians and counted.

**Hourly liquidity** (``hourly_median``): the median DV̂ over the 20 previous complete UTC
days' valid hours, zero-volume hours included as 0. With ε_max the largest ē among its
hours with volume, an entry's share of the true median over the same hours is at most
(1 + ε_max) x its share of the estimate (``participation``).

**The two protective limits** (section 5.7): the participation cap (the entry's dollars at
most π x the median; proposed π = 1%) and the spread cap (the live spread, (ask - bid) /
mid, at most s_max; proposed 0.50%). A missing input is reported as missing, never as a
pass: the assessment fails closed on it when the limit is On (section 5.8.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

DAY_S = 86400
HOUR_S = 3600
MEDIAN_DAYS = 20
PARTICIPATION_PI = 0.01  # proposed (D11)
SPREAD_MAX = 0.005  # proposed (D11)


def valid(o, h, lo, c, v) -> np.ndarray:
    o, h, lo, c, v = (np.asarray(x, dtype=float) for x in (o, h, lo, c, v))
    with np.errstate(invalid="ignore"):
        finite = np.isfinite(o) & np.isfinite(h) & np.isfinite(lo) & np.isfinite(c)
        finite &= np.isfinite(v)
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


def typical_price(h, lo, c) -> np.ndarray:
    return (np.asarray(h, float) + np.asarray(lo, float) + np.asarray(c, float)) / 3.0


def dollar_volume(o, h, lo, c, v) -> np.ndarray:
    """DV̂ per bar; NaN for an invalid bar."""
    ok = valid(o, h, lo, c, v)
    tp = typical_price(h, lo, c)
    return np.where(ok, tp * np.asarray(v, dtype=float), np.nan)


def error_bound(o, h, lo, c, v) -> np.ndarray:
    """ē per bar, the bound on |DV̂ - DV| / DV; NaN for an invalid bar or zero volume."""
    ok = valid(o, h, lo, c, v) & (np.asarray(v, dtype=float) > 0)
    h = np.asarray(h, dtype=float)
    lo = np.asarray(lo, dtype=float)
    tp = typical_price(h, lo, c)
    with np.errstate(divide="ignore", invalid="ignore"):
        bound = np.maximum((tp - lo) / lo, (h - tp) / h)
    return np.where(ok, bound, np.nan)


def relative_error(dv_hat, dv_true) -> np.ndarray:
    """|DV̂ - DV| / DV: the true value is the denominator."""
    dv_hat = np.asarray(dv_hat, dtype=float)
    dv_true = np.asarray(dv_true, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(dv_true > 0, np.abs(dv_hat - dv_true) / dv_true, np.nan)


@dataclass(frozen=True)
class Median:
    """The hourly median and what it rests on."""

    value: Optional[float]  # None when there is none (missing: fail closed when On)
    eps_max: Optional[float]
    hours: int  # valid hours in the window
    invalid: int  # invalid hours left out
    reason: str = ""


def hourly_median(
    open_s: Sequence[int], o, h, lo, c, v, at_s: int, days: int = MEDIAN_DAYS
) -> Median:
    """The median DV̂ over the ``days`` complete UTC days before the day of ``at_s`` (the
    decision's close time), from that venue's own bars. An hour with no bar counts as zero
    volume; an invalid bar is left out."""
    t = np.asarray(open_s, dtype=np.int64)
    day_end = (int(at_s) // DAY_S) * DAY_S  # the decision's day starts here
    start = day_end - days * DAY_S
    if not len(t) or int(t[0]) > start:
        return Median(None, None, 0, 0, f"fewer than {days} complete days of bars")
    inside = (t >= start) & (t < day_end)
    dv = dollar_volume(o, h, lo, c, v)[inside]
    eb = error_bound(o, h, lo, c, v)[inside]
    present = int(inside.sum())
    hours_total = days * 24
    absent = hours_total - present  # no bar reported: zero volume
    bad = int(np.sum(np.isnan(dv)))
    values = np.concatenate([dv[~np.isnan(dv)], np.zeros(max(absent, 0))])
    if not len(values):
        return Median(None, None, 0, bad, "no valid hours")
    med = float(np.median(values))
    if med <= 0:
        return Median(None, None, len(values), bad, "the median is zero")
    eps = float(np.nanmax(eb)) if np.any(np.isfinite(eb)) else 0.0
    return Median(med, eps, len(values), bad)


@dataclass(frozen=True)
class Check:
    """A protective limit's result: ``ok`` is None when its input is missing."""

    ok: Optional[bool]
    value: Optional[float]
    limit: float
    reason: str = ""
    bound: Optional[float] = (
        None  # participation: the share of the true median, at most
    )


def participation(
    amount_usd: float, median: Median, pi: float = PARTICIPATION_PI
) -> Check:
    if median.value is None:
        return Check(None, None, pi, median.reason or "no hourly volume")
    share = float(amount_usd) / median.value
    bound = (1.0 + (median.eps_max or 0.0)) * share
    return Check(share <= pi, share, pi, "", bound)


def spread(
    bid: Optional[float],
    ask: Optional[float],
    quote_age_s: Optional[float],
    s_max: float = SPREAD_MAX,
    max_age_s: float = 60.0,
) -> Check:
    """The live spread (ask - bid) / mid against s_max; missing when the quote is not
    usable (bid or ask missing, ask <= bid, or older than ``max_age_s``)."""
    if bid is None or ask is None:
        return Check(None, None, s_max, "no bid or ask")
    if not (np.isfinite(bid) and np.isfinite(ask)) or bid <= 0 or ask <= bid:
        return Check(None, None, s_max, "the quote is not usable")
    if quote_age_s is None or quote_age_s > max_age_s:
        return Check(None, None, s_max, "the quote is too old")
    mid = (bid + ask) / 2.0
    s = (ask - bid) / mid
    return Check(s <= s_max, float(s), s_max)


def abdi_ranaldo(h, lo, c, window: int = 48) -> np.ndarray:
    """An OHLC spread estimate (Abdi and Ranaldo 2017), as a sensitivity only: per bar,
    sqrt(max(4 mean((c_t - eta_t)(c_t - eta_{t+1})), 0)) over the last ``window`` bars,
    with c the log close and eta the log mid-range. It looks one bar ahead inside the
    window, so it is a historical sensitivity, never a decision input."""
    import pandas as pd

    lc = np.log(np.asarray(c, dtype=float))
    eta = (np.log(np.asarray(h, dtype=float)) + np.log(np.asarray(lo, dtype=float))) / 2
    prod = (lc - eta) * (lc - np.concatenate([eta[1:], [np.nan]]))
    mean = pd.Series(prod).rolling(window, min_periods=window // 2).mean().to_numpy()
    return np.sqrt(np.maximum(4.0 * mean, 0.0))
