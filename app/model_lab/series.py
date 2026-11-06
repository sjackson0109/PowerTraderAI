"""
The data a batch runs on (FDS-MH-001 section 5.2): one coin's 1-hour candles over the
batch's window, from one exchange, and the daily bars built from them.

* **Source.** ``market_data.candles.exchange_candles``: the exchanges in Settings, the
  primary exchange first, then the others in their order. One series comes from one
  exchange, and a frozen batch reads it again from that exchange only.
* **Window.** From the batch's start, or the series' first bar if later (a pair listed
  after the start is served from its first bar), to the batch's end.
* **Gaps.** A gap of up to ``MAX_GAP_S`` (24 hours) is kept: there is no bar in it, so
  no entry is made there, and an open trade carries on at the next close. A longer gap
  ends the earlier part: the series is the stretch after the last such gap.
* **Daily bars** are built from the 1-hour bars (``market_data.resample.build_candles``),
  by UTC day, from complete days only: a day with an hour missing is not built.
* **Identity.** ``sha256`` is the SHA-256 of the bars used, in the candle cache's CSV
  format (``pt_pattern_trainer.candle_sha256``). The cache file itself is shared and
  grows, so its own hash would not identify them.
"""

from __future__ import annotations

import functools
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

HOUR_S = 3600
DAY_S = 24 * HOUR_S
MAX_GAP_S = 24 * HOUR_S  # a longer gap ends the earlier part of a series


class SeriesError(RuntimeError):
    """A series could not be read, or is not the one a frozen batch recorded."""


def iso(epoch_s: int) -> str:
    return datetime.fromtimestamp(int(epoch_s), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def epoch(value) -> int:
    """Seconds since the epoch for a datetime, pandas Timestamp, ISO text or number
    (naive values are UTC)."""
    if isinstance(value, (int, float, np.integer, np.floating)):
        return int(value)
    import pandas as pd

    ts = pd.Timestamp(value)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return int(ts.timestamp())


@dataclass(frozen=True, eq=False)
class Series:
    """One coin's 1-hour bars, oldest first, as arrays: ``open_s`` (each bar's open
    time, seconds), ``open``, ``high``, ``low``, ``close`` and ``volume``."""

    coin: str
    exchange: str
    pair: str
    open_s: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    sha256: str = ""
    # the gaps kept: (first missing bar's open, last missing bar's open, bars missing)
    gaps: Tuple[Tuple[int, int, int], ...] = ()
    # the last gap longer than MAX_GAP_S, when one ended an earlier part: (the earlier
    # part's last open, the first open used)
    dropped: Optional[Tuple[int, int]] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return int(len(self.open_s))

    @functools.cached_property
    def close_s(self) -> np.ndarray:
        """Each bar's close time: the hour at whose close it is known."""
        return self.open_s + HOUR_S

    @property
    def first_open_s(self) -> int:
        return int(self.open_s[0])

    @property
    def last_open_s(self) -> int:
        return int(self.open_s[-1])

    @functools.cached_property
    def daily(self) -> "Daily":
        return build_daily(self)

    def cut(self, until_s: int) -> "Series":
        """The bars that close by ``until_s``: what was known at that close."""
        n = int(np.searchsorted(self.close_s, int(until_s), side="right"))
        return self._slice(0, n)

    def between(self, from_open_s: int, until_close_s: int) -> "Series":
        """The bars that open at or after ``from_open_s`` and close by
        ``until_close_s``."""
        a = int(np.searchsorted(self.open_s, int(from_open_s), side="left"))
        b = int(np.searchsorted(self.close_s, int(until_close_s), side="right"))
        return self._slice(a, max(a, b))

    def _slice(self, a: int, b: int) -> "Series":
        if b <= a:
            gaps: Tuple[Tuple[int, int, int], ...] = ()
        else:
            first, last = int(self.open_s[a]), int(self.open_s[b - 1])
            gaps = tuple(g for g in self.gaps if first < g[0] and g[1] < last)
        return Series(
            self.coin,
            self.exchange,
            self.pair,
            self.open_s[a:b],
            self.open[a:b],
            self.high[a:b],
            self.low[a:b],
            self.close[a:b],
            self.volume[a:b],
            "",
            gaps,
            self.dropped,
        )

    def close_at(self, t_s: int) -> Optional[float]:
        """The close of the last bar that closed by ``t_s``, or None."""
        k = int(np.searchsorted(self.close_s, int(t_s), side="right")) - 1
        return float(self.close[k]) if k >= 0 else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "coin": self.coin,
            "exchange": self.exchange,
            "pair": self.pair,
            "bars": len(self),
            "first_open": iso(self.first_open_s) if len(self) else None,
            "last_open": iso(self.last_open_s) if len(self) else None,
            "sha256": self.sha256,
            "gaps": [
                {"from": iso(a), "to": iso(b), "missing_bars": n}
                for a, b, n in self.gaps
            ],
            "dropped_before": (
                None
                if self.dropped is None
                else {
                    "last_open": iso(self.dropped[0]),
                    "next_open": iso(self.dropped[1]),
                }
            ),
        }


@dataclass(frozen=True, eq=False)
class Daily:
    """Complete UTC days, oldest first: each day's open time and close."""

    open_s: np.ndarray
    close: np.ndarray

    def index_of(self, day_open_s: np.ndarray) -> np.ndarray:
        """For each day open time, its position here, or -1 when that day was not
        built."""
        day_open_s = np.asarray(day_open_s, dtype=np.int64)
        k = np.searchsorted(self.open_s, day_open_s, side="left")
        k_safe = np.minimum(k, max(len(self.open_s) - 1, 0))
        found = (
            (k < len(self.open_s)) & (self.open_s[k_safe] == day_open_s)
            if len(self.open_s)
            else np.zeros(len(day_open_s), dtype=bool)
        )
        return np.where(found, k, -1)


def build_daily(series: Series) -> Daily:
    from market_data.resample import build_candles

    rows = [
        [int(t) * 1000, o, h, lo, c, v]
        for t, o, h, lo, c, v in zip(
            series.open_s.tolist(),
            series.open.tolist(),
            series.high.tolist(),
            series.low.tolist(),
            series.close.tolist(),
            series.volume.tolist(),
        )
    ]
    built = build_candles(rows, "1h", "1d")
    return Daily(
        np.array([r[0] // 1000 for r in built], dtype=np.int64),
        np.array([r[4] for r in built], dtype=float),
    )


def last_completed_day(close_s: np.ndarray) -> np.ndarray:
    """For each close time, the open time of the last UTC day that had ended by
    then (a day ends at the next 00:00, so at 00:00 the day just ended counts)."""
    close_s = np.asarray(close_s, dtype=np.int64)
    return (close_s // DAY_S) * DAY_S - DAY_S


def bars_sha256(series: Series) -> str:
    """``pt_pattern_trainer.candle_sha256`` of these bars: the candle cache's CSV
    format, so the same bars give the same hash wherever they are read."""
    lines = ["open_time_ms,open,high,low,close,volume"]
    for row in zip(
        series.open_s.tolist(),
        series.open.tolist(),
        series.high.tolist(),
        series.low.tolist(),
        series.close.tolist(),
        series.volume.tolist(),
    ):
        lines.append(
            ",".join([str(int(row[0]) * 1000)] + [repr(float(v)) for v in row[1:]])
        )
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def from_frame(coin: str, exchange: str, pair: str, df) -> Series:
    """A Series from a candle frame (open_time, open, high, low, close, volume),
    with the gap rules applied (module docstring)."""
    if df is None or len(df) == 0:
        raise SeriesError(f"{coin}: no 1-hour bars in the window")
    open_s = np.array([int(t.timestamp()) for t in df["open_time"]], dtype=np.int64)
    cols = {c: df[c].astype(float).to_numpy(copy=True) for c in _COLUMNS}
    step = np.diff(open_s)
    long_gaps = np.nonzero(step - HOUR_S > MAX_GAP_S)[0]
    dropped = None
    start = 0
    if len(long_gaps):
        k = int(long_gaps[-1])
        dropped = (int(open_s[k]), int(open_s[k + 1]))
        start = k + 1
    open_s = open_s[start:]
    cols = {c: v[start:] for c, v in cols.items()}
    gaps: List[Tuple[int, int, int]] = []
    for k in np.nonzero(np.diff(open_s) > HOUR_S)[0].tolist():
        a, b = int(open_s[k]), int(open_s[k + 1])
        gaps.append((a + HOUR_S, b - HOUR_S, (b - a) // HOUR_S - 1))
    series = Series(
        coin.upper(),
        exchange,
        pair,
        open_s,
        cols["open"],
        cols["high"],
        cols["low"],
        cols["close"],
        cols["volume"],
        "",
        tuple(gaps),
        dropped,
    )
    return _with_sha(series)


_COLUMNS = ("open", "high", "low", "close", "volume")


def _with_sha(series: Series) -> Series:
    return Series(
        series.coin,
        series.exchange,
        series.pair,
        series.open_s,
        series.open,
        series.high,
        series.low,
        series.close,
        series.volume,
        bars_sha256(series),
        series.gaps,
        series.dropped,
    )


def load(
    coin: str,
    start,
    end,
    cache_dir: Optional[str] = None,
    offline: bool = False,
    manager=None,
    exchanges: Optional[Sequence[str]] = None,
) -> Series:
    """The coin's 1-hour bars opening from ``start`` and closing by ``end``, from the
    first exchange in Settings that can serve them (``exchanges`` narrows or reorders
    them). Raises SeriesError when none can."""
    import pandas as pd

    from market_data.candles import CandleDataError, exchange_candles
    from pt_exchange_abstraction import MarketDataUnavailable, MarketNotFound

    start_s, end_s = epoch(start), epoch(end)
    try:
        df = exchange_candles(
            coin,
            "1h",
            pd.Timestamp(start_s, unit="s", tz="UTC"),
            pd.Timestamp(end_s, unit="s", tz="UTC"),
            cache_dir=cache_dir,
            offline=offline,
            manager=manager,
            exchanges=list(exchanges) if exchanges is not None else None,
        )
    except (CandleDataError, MarketNotFound, MarketDataUnavailable, OSError) as exc:
        raise SeriesError(f"{coin}: {exc}") from exc
    closes = df["open_time"] + pd.Timedelta(hours=1)
    df = df[closes <= pd.Timestamp(end_s, unit="s", tz="UTC")]
    return from_frame(coin, df.attrs.get("exchange", ""), df.attrs.get("pair", ""), df)


def load_frozen(
    record: Dict[str, Any],
    end,
    cache_dir: Optional[str] = None,
    offline: bool = False,
    manager=None,
) -> Series:
    """A series a frozen batch recorded (``Series.to_dict``), read again from the
    same exchange from its recorded first bar. Raises SeriesError when its bars are
    not the ones recorded."""
    first = record.get("first_open")
    if not first:
        raise SeriesError(f"{record.get('coin')}: the batch recorded no bars")
    series = load(
        record["coin"],
        first,
        end,
        cache_dir,
        offline,
        manager,
        exchanges=[record["exchange"]],
    )
    if series.sha256 != record.get("sha256"):
        raise SeriesError(
            f"{record['coin']}: the candles from {record['exchange']} are not the ones "
            "the batch was frozen with"
        )
    return series
