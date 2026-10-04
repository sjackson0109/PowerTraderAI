"""
Candle data layer (FDS-121 section 8): real Binance klines + an on-disk cache.

* Public endpoint only (``GET /api/v3/klines``): no keys, no authentication.
* Pagination (1000 rows per request) with backoff on rate limits / transient errors.
* Cache: ``<hub_data>/candles/<SYMBOL>_<TF>.csv`` (CSV: parquet needs pyarrow, which
  is not a project dependency). Only missing ranges are fetched, and a forming
  (not yet closed) bar is never written to the cache.
* Validation: timestamps must be strictly increasing with no duplicates (raises);
  gaps are *reported* in ``df.attrs["report"]``, never filled silently.

Candle frames have exactly the columns the strategy interface expects::

    open_time (UTC, ascending), open, high, low, close, volume
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import pandas as pd

from market_data.timeframes import timeframe_seconds

KLINES_URL = "https://api.binance.com/api/v3/klines"
PAGE_LIMIT = 1000
CANDLE_COLUMNS = ["open_time", "open", "high", "low", "close", "volume"]
_NUMERIC = ["open", "high", "low", "close", "volume"]


class CandleDataError(RuntimeError):
    """Candle data is invalid (duplicates, out of order) or could not be obtained."""


class CandleFetchError(CandleDataError):
    """The klines endpoint could not be read after retries."""


# --- time helpers --------------------------------------------------------------


def to_utc(value) -> pd.Timestamp:
    """Any date-like -> tz-aware UTC Timestamp (naive input is taken as UTC)."""
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _ms(ts: pd.Timestamp) -> int:
    return int(ts.timestamp() * 1000)


def cache_dir_default() -> str:
    base = os.environ.get(
        "POWERTRADER_HUB_DIR",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hub_data"
        ),
    )
    return os.path.join(base, "candles")


def cache_path(symbol: str, tf: str, cache_dir: Optional[str] = None) -> str:
    return os.path.join(cache_dir or cache_dir_default(), f"{symbol.upper()}_{tf}.csv")


# --- validation ----------------------------------------------------------------


@dataclass
class CandleReport:
    rows: int
    first: Optional[pd.Timestamp]
    last: Optional[pd.Timestamp]
    # (gap_start_open_time, gap_end_open_time, missing_bar_count)
    gaps: List[Tuple[pd.Timestamp, pd.Timestamp, int]] = field(default_factory=list)

    @property
    def missing_bars(self) -> int:
        return sum(g[2] for g in self.gaps)

    def to_dict(self) -> dict:
        return {
            "rows": self.rows,
            "first": self.first.isoformat() if self.first is not None else None,
            "last": self.last.isoformat() if self.last is not None else None,
            "gaps": [
                {"from": a.isoformat(), "to": b.isoformat(), "missing_bars": n}
                for a, b, n in self.gaps
            ],
            "missing_bars": self.missing_bars,
        }


def validate_candles(df: pd.DataFrame, tf: str) -> CandleReport:
    """Raise on duplicate / non-monotonic timestamps; report (don't fill) gaps."""
    step = pd.Timedelta(seconds=timeframe_seconds(tf))
    if df.empty:
        return CandleReport(rows=0, first=None, last=None)
    times = df["open_time"]
    if times.duplicated().any():
        raise CandleDataError(
            f"{int(times.duplicated().sum())} duplicate candle timestamps (first: "
            f"{times[times.duplicated()].iloc[0]})"
        )
    if not times.is_monotonic_increasing:
        raise CandleDataError("candle timestamps are not in ascending order")
    gaps = []
    diffs = times.diff()
    for idx in diffs.index[diffs > step]:
        pos = df.index.get_loc(idx)
        prev, cur = times.iloc[pos - 1], times.iloc[pos]
        gaps.append((prev + step, cur - step, int((cur - prev) / step) - 1))
    return CandleReport(
        rows=len(df), first=times.iloc[0], last=times.iloc[-1], gaps=gaps
    )


# --- binance klines ------------------------------------------------------------

RawFetcher = Callable[[str, str, int, Optional[int]], List[list]]


def _frame_from_klines(rows: List[list]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=CANDLE_COLUMNS).astype(
            {c: "float64" for c in _NUMERIC}
        )
    df = pd.DataFrame(
        {
            "open_time": pd.to_datetime([int(r[0]) for r in rows], unit="ms", utc=True),
            "open": [float(r[1]) for r in rows],
            "high": [float(r[2]) for r in rows],
            "low": [float(r[3]) for r in rows],
            "close": [float(r[4]) for r in rows],
            "volume": [float(r[5]) for r in rows],
        }
    )
    return df


class BinanceKlines:
    """Paginating, backing-off reader for the public klines endpoint."""

    def __init__(
        self,
        opener: Callable = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 5,
        timeout: float = 10.0,
    ) -> None:
        self._opener = opener
        self._sleep = sleep
        self.max_retries = max_retries
        self.timeout = timeout
        self.requests_made = 0

    def _page(
        self, symbol: str, tf: str, start_ms: int, end_ms: Optional[int]
    ) -> List[list]:
        params = {
            "symbol": symbol.upper(),
            "interval": tf,
            "startTime": start_ms,
            "limit": PAGE_LIMIT,
        }
        if end_ms is not None:
            params["endTime"] = end_ms
        url = f"{KLINES_URL}?{urllib.parse.urlencode(params)}"
        delay = 1.0
        for attempt in range(self.max_retries + 1):
            self.requests_made += 1
            try:
                with self._opener(url, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                # 429/418: rate limited -> honour Retry-After; 5xx: transient
                retryable = exc.code in (418, 429) or exc.code >= 500
                if not retryable or attempt == self.max_retries:
                    raise CandleFetchError(
                        f"klines HTTP {exc.code} for {symbol} {tf}"
                    ) from exc
                retry_after = None
                try:
                    retry_after = (
                        float(exc.headers.get("Retry-After")) if exc.headers else None
                    )
                except (TypeError, ValueError):
                    retry_after = None
                self._sleep(retry_after if retry_after is not None else delay)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                if attempt == self.max_retries:
                    raise CandleFetchError(
                        f"klines unreachable for {symbol} {tf}: {exc}"
                    ) from exc
                self._sleep(delay)
            delay = min(delay * 2, 30.0)
        raise CandleFetchError("unreachable")  # pragma: no cover

    def fetch(
        self, symbol: str, tf: str, start_ms: int, end_ms: Optional[int] = None
    ) -> List[list]:
        """All klines with open_time in [start_ms, end_ms] (inclusive), paginated."""
        step_ms = timeframe_seconds(tf) * 1000
        out: List[list] = []
        cursor = start_ms
        while True:
            page = self._page(symbol, tf, cursor, end_ms)
            if not page:
                break
            out.extend(page)
            last_open = int(page[-1][0])
            if len(page) < PAGE_LIMIT:
                break
            cursor = last_open + step_ms
            if end_ms is not None and cursor > end_ms:
                break
        return out


# --- cache + public API --------------------------------------------------------


def _read_cache(path: str) -> pd.DataFrame:
    if not os.path.isfile(path):
        return _frame_from_klines([])
    raw = pd.read_csv(path)
    if raw.empty:
        return _frame_from_klines([])
    df = raw.copy()
    df["open_time"] = pd.to_datetime(
        df["open_time_ms"].astype("int64"), unit="ms", utc=True
    )
    return df[CANDLE_COLUMNS].reset_index(drop=True)


def _write_cache(path: str, df: pd.DataFrame) -> None:
    """Cache format: ``open_time_ms`` (epoch ms, exact) + open, high, low, close, volume."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    out = df[_NUMERIC].copy()
    out.insert(
        0,
        "open_time_ms",
        ((df["open_time"] - epoch) // pd.Timedelta(milliseconds=1)).astype("int64"),
    )
    tmp = f"{path}.tmp"
    out.to_csv(tmp, index=False)
    os.replace(tmp, path)


def _closed_only(df: pd.DataFrame, tf: str, now: pd.Timestamp) -> pd.DataFrame:
    close_time = df["open_time"] + pd.Timedelta(seconds=timeframe_seconds(tf))
    return df[close_time <= now].reset_index(drop=True)


def get_candles(
    symbol: str,
    tf: str,
    start,
    end,
    closed_only: bool = True,
    cache_dir: Optional[str] = None,
    fetcher: Optional[BinanceKlines] = None,
    offline: bool = False,
    now=None,
) -> pd.DataFrame:
    """
    Candles for ``symbol``/``tf`` with ``start <= open_time < end`` (UTC).

    Missing ranges are fetched from Binance and cached; with ``offline=True`` only
    the cache is used and a request it cannot satisfy raises ``CandleDataError``.
    ``closed_only`` (default) never returns the still-forming bar. The result's
    ``attrs["report"]`` is a ``CandleReport`` (gaps are reported, not filled).
    """
    step = pd.Timedelta(seconds=timeframe_seconds(tf))
    start_ts, end_ts = to_utc(start), to_utc(end)
    now_ts = to_utc(now) if now is not None else pd.Timestamp.now(tz="UTC")
    path = cache_path(symbol, tf, cache_dir)
    cached = _read_cache(path)
    validate_candles(
        cached, tf
    )  # a corrupt cache is an error, not something to repair silently

    # Ranges are (first open_time, last open_time) INCLUSIVE; bars opening at or
    # after ``end`` (exclusive) or after ``now`` are not wanted.
    last_wanted = min(end_ts, now_ts) - pd.Timedelta(milliseconds=1)
    want: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    if cached.empty:
        want.append((start_ts, last_wanted))
    else:
        first_c, last_c = cached["open_time"].iloc[0], cached["open_time"].iloc[-1]
        if start_ts < first_c:
            want.append((start_ts, first_c - step))
        if last_wanted >= last_c + step:
            want.append((last_c + step, last_wanted))
    want = [(a, b) for a, b in want if b >= a]

    if want and offline:
        raise CandleDataError(
            f"offline: cache for {symbol} {tf} does not cover {start_ts} -> {end_ts} "
            f"(missing {[(str(a), str(b)) for a, b in want]})"
        )

    if want:
        fetcher = fetcher or BinanceKlines()
        frames = [cached]
        for a, b in want:
            rows = fetcher.fetch(symbol, tf, _ms(a), _ms(b))
            frames.append(_closed_only(_frame_from_klines(rows), tf, now_ts))
        merged = (
            pd.concat([f for f in frames if not f.empty], ignore_index=True)
            if any(not f.empty for f in frames)
            else _frame_from_klines([])
        )
        merged = (
            merged.drop_duplicates("open_time", keep="last")
            .sort_values("open_time")
            .reset_index(drop=True)
        )
        if not merged.equals(cached):
            _write_cache(path, merged)
        cached = merged

    df = cached[(cached["open_time"] >= start_ts) & (cached["open_time"] < end_ts)]
    if closed_only:
        df = _closed_only(df, tf, now_ts)
    df = df.reset_index(drop=True)
    df.attrs["report"] = validate_candles(df, tf)
    return df


def load_candles_csv(path: str, tf: str) -> pd.DataFrame:
    """Load candles from a cache-format CSV (e.g. a recorded test fixture)."""
    df = _read_cache(path)
    df.attrs["report"] = validate_candles(df, tf)
    return df


def file_sha256(path: str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
