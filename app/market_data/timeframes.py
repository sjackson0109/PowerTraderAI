"""Supported candle timeframes (pure data; no dependencies)."""

TIMEFRAME_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "8h": 28800,
    "12h": 43200,
    "1d": 86400,
}

# Candle-only timeframes: the candle cache can fetch, validate and filter them
# (candle_timeframe_seconds), but they are not strategy timeframes: strategy settings,
# the catalogue, the signal engine and the backtester use TIMEFRAME_SECONDS through
# timeframe_seconds. The pattern trainer needs weekly bars (FDS-MDL). Binance weekly
# bars open on Monday 00:00 UTC, not on a multiple of the period since the epoch.
CANDLE_ONLY_TIMEFRAME_SECONDS = {
    "1w": 604800,
}

# 1970-01-01 was a Thursday; the first Monday 00:00 UTC is 4 days later.
_WEEK_ORIGIN_SECONDS = 4 * 86400


def timeframe_seconds(tf: str) -> int:
    try:
        return TIMEFRAME_SECONDS[tf]
    except KeyError:
        raise ValueError(
            f"Unsupported timeframe {tf!r}; use one of {sorted(TIMEFRAME_SECONDS)}"
        ) from None


def candle_timeframe_seconds(tf: str) -> int:
    """Bar length of a strategy timeframe or a candle-only one (``1w``)."""
    if tf in CANDLE_ONLY_TIMEFRAME_SECONDS:
        return CANDLE_ONLY_TIMEFRAME_SECONDS[tf]
    try:
        return TIMEFRAME_SECONDS[tf]
    except KeyError:
        raise ValueError(
            f"Unsupported candle timeframe {tf!r}; use one of "
            f"{sorted(TIMEFRAME_SECONDS) + sorted(CANDLE_ONLY_TIMEFRAME_SECONDS)}"
        ) from None


def bar_open_floor(epoch_seconds: int, tf: str) -> int:
    """Open time (epoch seconds) of the ``tf`` bar that contains ``epoch_seconds``.
    Weekly bars open on Monday 00:00 UTC; the others on multiples of their period."""
    step = candle_timeframe_seconds(tf)
    origin = _WEEK_ORIGIN_SECONDS if tf == "1w" else 0
    return (int(epoch_seconds) - origin) // step * step + origin
