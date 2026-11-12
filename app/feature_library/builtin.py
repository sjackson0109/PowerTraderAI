"""
The features the library starts with (PTAI-RD-001 work package 4.1), by family. Windows
are in bars, and every rolling window ends at, and includes, the bar it is for.

**price**
* ``price.return`` (n=1): close / close n bars back - 1.
* ``price.sma_ratio`` (n=20): close / its n-bar simple average - 1 (STRAT-006's
  quantity: above 0 is above the average).
* ``price.ema_ratio`` (n=20): close / its n-bar exponential average - 1, with the
  strategies' EMA (alpha = 2 / (n + 1), started at the first close). Start-dependent.
* ``price.channel_position`` (n=20): where the close sits in the range of the last n
  closes, 0 at the lowest, 1 at the highest (STRAT-004's channel, closes only).
* ``price.rsi`` (n=14): Wilder's relative strength index, 0 to 100, with the
  strategies' Wilder smoothing (seeded at the mean of the first n changes).
  Start-dependent.

**volatility**
* ``volatility.realised`` (n=20): the standard deviation (n - 1) of the last n log
  returns, per bar, not annualised.
* ``volatility.parkinson`` (n=20): sqrt(mean(ln(high / low)^2) / (4 ln 2)) over the
  last n bars (Parkinson 1980): the range estimator, per bar.
* ``volatility.ewma`` (lam=0.94, burn_in=30): RiskMetrics: s2_t = lam s2_{t-1} +
  (1 - lam) r_t^2, started at the first squared log return. Start-dependent; the burn-in
  bars carry no value.
* ``volatility.atr_ratio`` (n=14): the strategies' ATR (Wilder) over the close.
  Start-dependent.

**volume**
* ``volume.relative`` (n=20): this bar's volume over the mean of the previous n bars'
  (this bar excluded).
* ``volume.signed_share`` (n=20): the sum over the last n bars of volume signed by the
  close's change (+ up, - down, 0 flat), over their total volume: -1 to 1. On-balance
  volume's change over n bars, as a share, so the series' start does not matter.
* ``volume.cmf`` (n=20): Chaikin money flow: the sum of ((close - low) - (high - close)) /
  (high - low) x volume over the last n bars, over their volume (a bar with high = low
  counts 0).
* ``volume.mfi`` (n=14): the money flow index: 100 - 100 / (1 + positive / negative
  flow) over the last n bars, flow = typical price x volume, positive when the typical
  price rose (high + low + close) / 3. 100 when no flow was negative.

Volume is in each exchange's own unit (usually the coin's); the volume features are
ratios, so the unit cancels within one series.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from feature_library.base import Feature, register
from strategies.indicators import _wilder, atr, ema


def _n(p) -> int:
    return int(p["n"])


def _rolling_sum(x: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).sum()


def _log_returns(close: pd.Series) -> pd.Series:
    return np.log(close / close.shift(1))


# -- price --------------------------------------------------------------------------------

register(
    Feature(
        "price.return",
        1,
        "Close over the close n bars back, less 1.",
        ("close",),
        {"n": 1},
        lambda c, p: c["close"] / c["close"].shift(_n(p)) - 1.0,
        _n,
        bounds={"n": (1, 1000)},
    )
)
register(
    Feature(
        "price.sma_ratio",
        1,
        "Close over its n-bar simple average, less 1.",
        ("close",),
        {"n": 20},
        lambda c, p: c["close"] / c["close"].rolling(_n(p), min_periods=_n(p)).mean()
        - 1.0,
        lambda p: _n(p) - 1,
        bounds={"n": (2, 1000)},
    )
)
register(
    Feature(
        "price.ema_ratio",
        1,
        "Close over its n-bar exponential average, less 1.",
        ("close",),
        {"n": 20},
        lambda c, p: c["close"] / ema(c["close"], _n(p)) - 1.0,
        lambda p: _n(p) - 1,
        window_local=False,
        bounds={"n": (2, 1000)},
    )
)


def _channel_position(c: pd.DataFrame, p) -> pd.Series:
    close = c["close"]
    lo = close.rolling(_n(p), min_periods=_n(p)).min()
    hi = close.rolling(_n(p), min_periods=_n(p)).max()
    width = hi - lo
    return ((close - lo) / width).where(width > 0, 0.5)


register(
    Feature(
        "price.channel_position",
        1,
        "Where the close sits in the range of the last n closes: 0 lowest, 1 highest "
        "(0.5 when they are all equal).",
        ("close",),
        {"n": 20},
        _channel_position,
        lambda p: _n(p) - 1,
        bounds={"n": (2, 1000)},
    )
)


def _rsi(c: pd.DataFrame, p) -> pd.Series:
    change = c["close"].diff()
    up = _wilder(change.clip(lower=0.0), _n(p), "mean")
    down = _wilder((-change).clip(lower=0.0), _n(p), "mean")
    rs = up / down
    return (100.0 - 100.0 / (1.0 + rs)).where(down > 0, 100.0).where(up.notna())


register(
    Feature(
        "price.rsi",
        1,
        "Wilder's relative strength index, 0 to 100.",
        ("close",),
        {"n": 14},
        _rsi,
        _n,
        window_local=False,
        bounds={"n": (2, 500)},
    )
)

# -- volatility ---------------------------------------------------------------------------

register(
    Feature(
        "volatility.realised",
        1,
        "Standard deviation of the last n log returns, per bar.",
        ("close",),
        {"n": 20},
        lambda c, p: _log_returns(c["close"]).rolling(_n(p), min_periods=_n(p)).std(),
        _n,
        bounds={"n": (2, 1000)},
    )
)

_PARKINSON = 1.0 / (4.0 * math.log(2.0))
register(
    Feature(
        "volatility.parkinson",
        1,
        "Parkinson's range estimator over the last n bars, per bar.",
        ("high", "low"),
        {"n": 20},
        lambda c, p: np.sqrt(
            (np.log(c["high"] / c["low"]) ** 2).rolling(_n(p), min_periods=_n(p)).mean()
            * _PARKINSON
        ),
        lambda p: _n(p) - 1,
        bounds={"n": (2, 1000)},
    )
)


def _ewma(c: pd.DataFrame, p) -> pd.Series:
    r2 = (_log_returns(c["close"]) ** 2).to_numpy()
    lam = float(p["lam"])
    out = np.full(len(r2), np.nan)
    s2 = np.nan
    for i, x in enumerate(r2):
        if np.isnan(x):
            continue
        s2 = x if np.isnan(s2) else lam * s2 + (1.0 - lam) * x
        out[i] = s2
    return pd.Series(np.sqrt(out), index=c.index)


register(
    Feature(
        "volatility.ewma",
        1,
        "RiskMetrics exponentially weighted volatility of log returns, per bar.",
        ("close",),
        {"lam": 0.94, "burn_in": 30},
        _ewma,
        lambda p: int(p["burn_in"]),
        window_local=False,
        bounds={"lam": (0.5, 0.999), "burn_in": (1, 1000)},
    )
)
register(
    Feature(
        "volatility.atr_ratio",
        1,
        "Average true range (Wilder) over the close.",
        ("high", "low", "close"),
        {"n": 14},
        lambda c, p: atr(c["high"], c["low"], c["close"], _n(p)) / c["close"],
        lambda p: _n(p) - 1,
        window_local=False,
        bounds={"n": (2, 500)},
    )
)

# -- volume -------------------------------------------------------------------------------

register(
    Feature(
        "volume.relative",
        1,
        "This bar's volume over the mean of the previous n bars'.",
        ("volume",),
        {"n": 20},
        lambda c, p: c["volume"]
        / c["volume"].shift(1).rolling(_n(p), min_periods=_n(p)).mean(),
        _n,
        bounds={"n": (1, 1000)},
    )
)


def _signed_share(c: pd.DataFrame, p) -> pd.Series:
    sign = np.sign(c["close"].diff())
    signed = _rolling_sum(sign * c["volume"], _n(p))
    total = _rolling_sum(c["volume"], _n(p)).where(sign.notna())
    return signed / total


register(
    Feature(
        "volume.signed_share",
        1,
        "Volume signed by the close's change over the last n bars, as a share of "
        "their volume: -1 to 1.",
        ("close", "volume"),
        {"n": 20},
        _signed_share,
        _n,
        bounds={"n": (1, 1000)},
    )
)


def _cmf(c: pd.DataFrame, p) -> pd.Series:
    h, lo, cl, v = c["high"], c["low"], c["close"], c["volume"]
    rng = h - lo
    mult = (((cl - lo) - (h - cl)) / rng).where(rng > 0, 0.0)
    return _rolling_sum(mult * v, _n(p)) / _rolling_sum(v, _n(p))


register(
    Feature(
        "volume.cmf",
        1,
        "Chaikin money flow over the last n bars: -1 to 1.",
        ("high", "low", "close", "volume"),
        {"n": 20},
        _cmf,
        lambda p: _n(p) - 1,
        bounds={"n": (1, 1000)},
    )
)


def _mfi(c: pd.DataFrame, p) -> pd.Series:
    tp = (c["high"] + c["low"] + c["close"]) / 3.0
    flow = tp * c["volume"]
    change = tp.diff()
    pos = _rolling_sum(flow.where(change > 0, 0.0).where(change.notna()), _n(p))
    neg = _rolling_sum(flow.where(change < 0, 0.0).where(change.notna()), _n(p))
    return (100.0 - 100.0 / (1.0 + pos / neg)).where(neg > 0, 100.0).where(pos.notna())


register(
    Feature(
        "volume.mfi",
        1,
        "Money flow index over the last n bars, 0 to 100.",
        ("high", "low", "close", "volume"),
        {"n": 14},
        _mfi,
        _n,
        bounds={"n": (1, 500)},
    )
)
