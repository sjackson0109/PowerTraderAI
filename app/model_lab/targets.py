"""
Targets of the trained contestants (FDS-MH-001 section 5.5), the purge (section 5.4) and
the uniqueness weights.

**T1, clean win.** From the close of hour t, does the price reach the first profit line
before the first DCA level, within H = 336 hours? Both barriers come from the batch's trade
rules and the coin's fee, as ``model_gate.replay`` computes them: an entry at the close C_t
has an average cost of C_t (1 + slippage) / (1 - fee); the profit line is
``pm_start_pct_no_dca`` above it, and the DCA level ``dca_levels[0]`` below it (a negative
percentage). Hits are judged on the hourly highs and lows of the bars after t. A bar that
touches both counts as a loss, and so does reaching neither within H. A label whose 336
hours are not all on the grid, and that hit nothing before the grid ends, is unresolved.

**T2, trade return per capital-day.** The trade ``model_gate.replay`` makes from an entry at
hour t, on the bars of the next 720 hours only, so that a trade still open after 30 days is
sold at that close; its net return over its capital-days. Unresolved when the 720 hours run
past the grid's end before the trade has closed.

**The purge.** A training row at hour t is used for a fit at ``until`` only when
t + H <= until (H = 336 hours for T1, 720 for T2): its label never looks past the fold's
start.

**Uniqueness.** Labels overlap, so each training row is weighted by its average uniqueness
(Lopez de Prado 2018, ch. 4): over the hours its label spans (from t to its barrier hit or
exit, or to t + H), the mean of 1 / the number of the coin's training labels spanning each
hour.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

import model_gate
from model_lab.features import Grid
from model_lab.series import HOUR_S

T1_HOURS = 336
T2_HOURS = 720
HORIZON = {"t1": T1_HOURS, "t2": T2_HOURS}


def t1_barriers(price: np.ndarray, rules, fees) -> Tuple[np.ndarray, np.ndarray]:
    """(the profit line, the DCA level) of an entry at each price."""
    avg = price * (1.0 + fees.slippage) / (1.0 - fees.rate)
    up = avg * (1.0 + rules.pm_start_pct_no_dca / 100.0)
    down = avg * (1.0 + rules.dca_levels[0] / 100.0)
    return up, down


def t1(g: Grid, rules, fees, hours: int = T1_HOURS, chunk: int = 4096):
    """(label, end) for every grid hour: label 1.0 or 0.0, NaN when unresolved or the
    hour has no bar; end is the grid position where the label was decided."""
    n = len(g)
    label = np.full(n, np.nan)
    end = np.full(n, -1, dtype=np.int64)
    if n < 2:
        return label, end
    up, down = t1_barriers(g.close, rules, fees)
    pad = np.full(hours, np.nan)
    high = np.concatenate([g.high, pad])
    low = np.concatenate([g.low, pad])
    win_h = np.lib.stride_tricks.sliding_window_view(high[1:], hours)
    win_l = np.lib.stride_tricks.sliding_window_view(low[1:], hours)
    for a in range(0, n, chunk):
        b = min(n, a + chunk)
        with np.errstate(invalid="ignore"):
            hit_u = win_h[a:b] >= up[a:b, None]
            hit_d = win_l[a:b] <= down[a:b, None]
        any_hit = hit_u | hit_d
        first = np.argmax(any_hit, axis=1)
        hit = any_hit[np.arange(b - a), first]
        lost = hit_d[np.arange(b - a), first]
        k = np.arange(a, b)
        full = k + hours <= n - 1  # all of the label's hours are on the grid
        lab = np.where(hit, np.where(lost, 0.0, 1.0), np.where(full, 0.0, np.nan))
        lab = np.where(g.present[a:b], lab, np.nan)
        label[a:b] = lab
        end[a:b] = np.where(hit, k + 1 + first, np.where(full, k + hours, -1))
    end = np.where(np.isnan(label), -1, end)
    return label, end


def t2(g: Grid, rules, fees, hours: int = T2_HOURS):
    """(label, end) for every grid hour: the replayed trade's net return per capital-day
    on the next ``hours`` hours (NaN when unresolved or the hour has no bar), and the grid
    position where it ended."""
    n = len(g)
    label = np.full(n, np.nan)
    end = np.full(n, -1, dtype=np.int64)
    pos = np.nonzero(g.present)[0]
    close_s = g.close_s[pos]
    price = g.close[pos]
    for m, k in enumerate(pos.tolist()):
        stop = int(np.searchsorted(close_s, close_s[m] + hours * HOUR_S, "right"))
        sub = model_gate.Hours(
            tuple(int(t) for t in close_s[m:stop]),
            tuple(float(p) for p in price[m:stop]),
            (None,) * (stop - m),
            (None,) * (stop - m),
        )
        trade = model_gate.replay(0, sub, rules, fees)
        full = k + hours <= n - 1
        closed = trade.end < stop - m - 1
        if not (full or closed) or trade.capital_days <= 0:
            continue
        label[k] = trade.net / trade.capital_days
        end[k] = int(pos[m + trade.end])
    return label, end


def labels(data, coin: str, target: str):
    """The coin's (label, end) for ``target``, built once for ``data``."""
    from model_lab.features import table

    key = ("target", target, coin)
    if key not in data.cache:
        g = table(data, coin).grid
        fees = data.fees[coin]
        make = t1 if target == "t1" else t2
        data.cache[key] = make(g, data.rules, fees)
    return data.cache[key]


def usable(g: Grid, label: np.ndarray, until: int, target: str) -> np.ndarray:
    """The grid hours whose labels a fit at ``until`` may use: resolved, and purged
    (t + H <= until)."""
    return np.isfinite(label) & (g.close_s + HORIZON[target] * HOUR_S <= int(until))


def uniqueness(rows: np.ndarray, end: np.ndarray, n: int) -> np.ndarray:
    """Each row's average uniqueness among ``rows`` (grid positions, with their labels'
    end positions), on a grid of ``n`` hours."""
    rows = np.asarray(rows, dtype=np.int64)
    if not len(rows):
        return np.zeros(0)
    stop = np.asarray(end, dtype=np.int64)[rows]
    count = np.zeros(n + 1)
    np.add.at(count, rows, 1.0)
    np.add.at(count, stop + 1, -1.0)
    concurrent = np.cumsum(count)[:n]
    inverse = np.where(
        concurrent > 0, 1.0 / np.where(concurrent > 0, concurrent, 1.0), 0.0
    )
    total = np.concatenate([[0.0], np.cumsum(inverse)])
    return (total[stop + 1] - total[rows]) / (stop - rows + 1)
