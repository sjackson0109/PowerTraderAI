"""
Indicator library (FDS-121 section 4): vectorised pandas functions.

Conventions (pinned by tests against independent reference implementations):

* ``ema``   - exponential moving average, smoothing ``2/(n+1)``, seeded with the
              first value (``adjust=False``). Defined from bar 0.
* ``dema``  - ``2*EMA - EMA(EMA)``.
* ``tema``  - ``3*EMA - 3*EMA(EMA) + EMA(EMA(EMA))``.
* ``atr``   - Wilder: true range ``max(h-l, |h-pc|, |l-pc|)`` (first bar: ``h-l``),
              seeded with the simple mean of the first ``n`` true ranges, then
              ``ATR_t = (ATR_{t-1}*(n-1) + TR_t)/n``. NaN before bar ``n-1``.
* ``adx``   - Wilder DMI/ADX: smoothed +DM/-DM/TR (sum seed, Wilder recursion),
              ``DX = 100*|+DI - -DI|/(+DI + -DI)``, ADX = Wilder mean of DX seeded
              with the mean of the first ``n`` DX values. NaN before bar ``2n-2``.

All functions are pure and never look past the bar they are computing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, n: int) -> pd.Series:
    if n < 1:
        raise ValueError("EMA length must be >= 1")
    return series.ewm(span=n, adjust=False).mean()


def dema(series: pd.Series, n: int) -> pd.Series:
    e1 = ema(series, n)
    return 2.0 * e1 - ema(e1, n)


def tema(series: pd.Series, n: int) -> pd.Series:
    e1 = ema(series, n)
    e2 = ema(e1, n)
    e3 = ema(e2, n)
    return 3.0 * e1 - 3.0 * e2 + e3


def _wilder(values: pd.Series, n: int, seed: str) -> pd.Series:
    """
    Wilder smoothing ``y_t = (y_{t-1}*(n-1) + x_t)/n`` of the first-valid-value
    series ``values`` (NaN-prefixed allowed). The recursion starts at the first
    valid index with the *mean* of the first ``n`` valid values (``seed="mean"``)
    or their *sum* (``seed="sum"``).
    """
    x = values.to_numpy(dtype=float)
    valid = np.flatnonzero(~np.isnan(x))
    if len(valid) < n:
        return pd.Series(np.nan, index=values.index, dtype=float)
    first = valid[0]
    seed_idx = first + n - 1
    # Wilder's recursion is an exponential average with alpha = 1/n started at
    # the seed. A "sum" series is simply n times the "mean" series
    # (y_t = y_{t-1} - y_{t-1}/n + x_t  <=>  y_t/n = (1-1/n) y_{t-1}/n + x_t/n),
    # so seed the EWM at the window mean and scale at the end.
    start = np.full(len(x), np.nan)
    start[seed_idx] = x[first : seed_idx + 1].mean()
    start[seed_idx + 1 :] = x[seed_idx + 1 :]
    out = pd.Series(start, index=values.index).ewm(alpha=1.0 / n, adjust=False).mean()
    return out * n if seed == "sum" else out


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    tr.iloc[0] = high.iloc[0] - low.iloc[0]
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    if n < 1:
        raise ValueError("ATR length must be >= 1")
    return _wilder(true_range(high, low, close), n, seed="mean")


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's ADX (see module docstring)."""
    if n < 1:
        raise ValueError("ADX length must be >= 1")
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    # bar 0 has no previous bar: DM and TR start from bar 1
    plus_dm.iloc[0] = np.nan
    minus_dm.iloc[0] = np.nan
    tr = true_range(high, low, close)
    tr.iloc[0] = np.nan

    s_tr = _wilder(tr, n, seed="sum")
    s_plus = _wilder(plus_dm, n, seed="sum")
    s_minus = _wilder(minus_dm, n, seed="sum")
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * s_plus / s_tr
        minus_di = 100.0 * s_minus / s_tr
        dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    dx = dx.where((plus_di + minus_di) != 0, 0.0).where(~s_tr.isna())
    return _wilder(dx, n, seed="mean")


def supertrend(df: pd.DataFrame, atr_len: int = 10, mult: float = 3.0) -> pd.DataFrame:
    """
    Supertrend. Returns a frame with ``line``, ``direction`` (+1 up / -1 down), the
    two ``final_upper`` / ``final_lower`` bands and ``atr`` (Wilder); NaN until the
    first valid ATR (bar ``atr_len - 1``).

    ``hl2 = (high + low)/2``; ``basic_upper = hl2 + mult*ATR``;
    ``basic_lower = hl2 - mult*ATR``. The bands carry forward with the trend:

    * while the direction is **up** the final lower band only rises
      (``max(basic_lower, previous final lower)``) and the line is that band;
    * while the direction is **down** the final upper band only falls
      (``min(basic_upper, previous final upper)``) and the line is that band;
    * the direction flips to up when ``close > previous final upper`` and to down
      when ``close < previous final lower``; on a flip the new line is the fresh
      basic band of that bar.

    The first valid bar starts up if ``close > hl2``, else down.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    atr_s = atr(high, low, close, atr_len)
    a = atr_s.to_numpy(dtype=float)
    hl2 = ((high + low) / 2.0).to_numpy(dtype=float)
    c = close.to_numpy(dtype=float)
    n = len(c)

    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    direction = np.full(n, np.nan)
    line = np.full(n, np.nan)

    start = atr_len - 1
    if n > start:
        basic_upper = hl2 + mult * a
        basic_lower = hl2 - mult * a
        upper[start] = basic_upper[start]
        lower[start] = basic_lower[start]
        direction[start] = 1.0 if c[start] > hl2[start] else -1.0
        line[start] = lower[start] if direction[start] > 0 else upper[start]
        for t in range(start + 1, n):
            if direction[t - 1] > 0:
                lower[t] = max(basic_lower[t], lower[t - 1])
                upper[t] = basic_upper[t]
                direction[t] = -1.0 if c[t] < lower[t - 1] else 1.0
            else:
                upper[t] = min(basic_upper[t], upper[t - 1])
                lower[t] = basic_lower[t]
                direction[t] = 1.0 if c[t] > upper[t - 1] else -1.0
            line[t] = lower[t] if direction[t] > 0 else upper[t]

    return pd.DataFrame(
        {
            "line": line,
            "direction": direction,
            "final_upper": upper,
            "final_lower": lower,
            "atr": a,
        },
        index=df.index,
    )
