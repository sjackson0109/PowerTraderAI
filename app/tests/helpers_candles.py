"""Synthetic candle fixtures for the pattern trainer tests (FDS-MDL Phase 1).

* ``synthetic_hourly`` makes a seeded random walk of 1h bars (no network, no files).
* ``resample`` builds the higher timeframes from it the way the exchange does: each
  bar covers the 1h bars that open inside it, and only complete bars are kept.
  Weekly bars open on Monday 00:00 UTC, like Binance's.
* ``seed_cache`` writes frames in the candle cache format
  (``app/market_data/candles.py``), so ``get_candles(..., offline=True)`` reads them.
* ``seed_trainer_window`` does that for the coins a hub test trains, and points every
  trainer child at the fixture window, offline.
"""

import os
import random

import pandas as pd

from market_data.candles import (
    CANDLE_COLUMNS,
    _write_cache,
    cache_dir_default,
    cache_path,
)
from market_data.timeframes import bar_open_floor, candle_timeframe_seconds

TRAINER_TFS = ("1h", "2h", "4h", "8h", "12h", "1d", "1w")
FIXTURE_START = pd.Timestamp("2024-01-01", tz="UTC")  # a Monday
FIXTURE_HOURS = 1680  # ten weeks


def synthetic_hourly(n, start, seed=0, price=100.0, vol=0.01, tick=None):
    """``n`` hourly bars from ``start`` (UTC, on the hour): a seeded random walk.
    Prices are rounded to 4 decimals, as an exchange quotes them, or to a multiple
    of ``tick`` (a coarse tick makes many candles alike, so patterns match often)."""
    rng = random.Random(seed)
    start = pd.Timestamp(start)
    start = (
        start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    )

    def quote(value):
        value = max(value, tick or 0.01)
        return round(round(value / tick) * tick, 4) if tick else round(value, 4)

    rows = []
    close = quote(price)
    for i in range(n):
        open_ = close
        close = quote(open_ * (1 + rng.gauss(0, vol)))
        high = quote(max(open_, close) * (1 + abs(rng.gauss(0, vol / 2))))
        low = quote(min(open_, close) * (1 - abs(rng.gauss(0, vol / 2))))
        rows.append(
            {
                "open_time": start + pd.Timedelta(hours=i),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": round(rng.uniform(1, 100), 3),
            }
        )
    return pd.DataFrame(rows, columns=CANDLE_COLUMNS)


def alike_hourly(n, start, seed=0, price=100.0, body_pct=0.5, jitter=0.001):
    """``n`` hourly bars whose bodies are all ``body_pct`` % up or down, each scaled
    by a random factor within ``1 +/- jitter``: many patterns nearly match, so the
    trainer's match threshold falls below 0.1 and its finest steps matter."""
    rng = random.Random(seed)
    start = pd.Timestamp(start)
    start = (
        start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    )
    rows = []
    close = price
    for i in range(n):
        open_ = close
        body = rng.choice((1, -1)) * body_pct * (1 + rng.uniform(-jitter, jitter))
        close = round(open_ * (1 + body / 100), 4)
        rows.append(
            {
                "open_time": start + pd.Timedelta(hours=i),
                "open": open_,
                "high": round(max(open_, close) * (1 + rng.uniform(0, 0.002)), 4),
                "low": round(min(open_, close) * (1 - rng.uniform(0, 0.002)), 4),
                "close": close,
                "volume": round(rng.uniform(1, 100), 3),
            }
        )
    return pd.DataFrame(rows, columns=CANDLE_COLUMNS)


def resample(hourly, tf):
    """Complete ``tf`` bars built from 1h bars (open/close of the first/last hour)."""
    if tf == "1h":
        return hourly.reset_index(drop=True)
    per_bar = candle_timeframe_seconds(tf) // 3600
    seconds = hourly["open_time"].map(lambda t: int(t.timestamp()))
    buckets = seconds.map(lambda s: bar_open_floor(s, tf))
    rows = []
    for bucket, group in hourly.groupby(buckets, sort=True):
        if len(group) != per_bar:
            continue  # a partial bar at either end of the data
        rows.append(
            {
                "open_time": pd.Timestamp(bucket, unit="s", tz="UTC"),
                "open": group["open"].iloc[0],
                "high": group["high"].max(),
                "low": group["low"].min(),
                "close": group["close"].iloc[-1],
                "volume": round(group["volume"].sum(), 3),
            }
        )
    return pd.DataFrame(rows, columns=CANDLE_COLUMNS)


def all_timeframes(hourly, tfs=TRAINER_TFS):
    return {tf: resample(hourly, tf) for tf in tfs}


def seed_cache(cache_dir, symbol, frames):
    """Write ``{tf: frame}`` to ``cache_dir`` in the candle cache format."""
    os.makedirs(cache_dir, exist_ok=True)
    for tf, frame in frames.items():
        _write_cache(cache_path(symbol, tf, cache_dir), frame)
    return cache_dir


def seed_trainer_window(monkeypatch, coins, hours=FIXTURE_HOURS, seed=1):
    """Seed the candle cache under POWERTRADER_HOME with ``hours`` of 1h bars (and
    the higher timeframes) for each coin, and set the pattern trainer's window and
    offline flag for every child process. Returns (train_start, train_end)."""
    end = FIXTURE_START + pd.Timedelta(hours=hours)
    for i, coin in enumerate(coins):
        hourly = synthetic_hourly(hours, FIXTURE_START, seed=seed + i)
        seed_cache(cache_dir_default(), f"{coin}USDT", all_timeframes(hourly))
    monkeypatch.setenv("POWERTRADER_TRAIN_START", FIXTURE_START.isoformat())
    monkeypatch.setenv("POWERTRADER_TRAIN_END", end.isoformat())
    monkeypatch.setenv("POWERTRADER_CANDLES_OFFLINE", "1")
    return FIXTURE_START, end
