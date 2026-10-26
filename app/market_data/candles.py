"""
Candle data layer (FDS-121 section 8): real candles + an on-disk cache.

* ``exchange_candles``: candles from the exchanges in Settings, the primary exchange
  first (FDS-MX-001 phase E). One series comes from one exchange: the first that can
  serve the whole range, from its own cache topped up from that exchange only.
  Public market data only: no keys, no authentication.
* Cache: ``<cache>/candles/<exchange>/<PAIR>_<TF>.csv`` (``PAIR`` is that exchange's
  market, e.g. ``BTC-USD``). Files cached before FDS-MX-001 phase F sit directly in
  ``<cache>/candles`` and hold Binance bars; they move once into ``binance/``
  (``move_flat_cache``). CSV: parquet needs pyarrow, which is not a project
  dependency. Only missing ranges are fetched, and a forming (not yet closed) bar
  is never written to the cache.
* Validation: timestamps must be strictly increasing with no duplicates (raises);
  gaps are *reported* in ``df.attrs["report"]``, never filled silently.

Candle frames have exactly the columns the strategy interface expects::

    open_time (UTC, ascending), open, high, low, close, volume
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import pandas as pd

from market_data.timeframes import candle_timeframe_seconds

# Every bar cached before FDS-MX-001 phase F came from Binance spot klines.
FLAT_CACHE_EXCHANGE = "binance"
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
    """``<cache>/candles`` (see pt_paths): downloaded klines are safe to delete."""
    import pt_paths

    return os.path.join(pt_paths.cache_dir(), "candles")


def cache_path(
    symbol: str,
    tf: str,
    cache_dir: Optional[str] = None,
    exchange: Optional[str] = None,
) -> str:
    """The cache file for ``symbol``/``tf``: in the exchange's own folder when
    ``exchange`` is given (one series, one exchange)."""
    folder = cache_dir or cache_dir_default()
    if exchange:
        folder = os.path.join(folder, str(exchange).lower())
    return os.path.join(folder, f"{symbol.upper()}_{tf}.csv")


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
    step = pd.Timedelta(seconds=candle_timeframe_seconds(tf))
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


# --- candle rows -------------------------------------------------------------

RawFetcher = Callable[[str, str, int, Optional[int]], List[list]]


def _frame_from_klines(rows: List[list]) -> pd.DataFrame:
    if not rows:
        # Typed like a full frame: a page with no bars (a range before the pair was
        # listed, or after it stopped trading) is still compared by open_time.
        return pd.DataFrame(columns=CANDLE_COLUMNS).astype(
            {"open_time": "datetime64[ns, UTC]", **{c: "float64" for c in _NUMERIC}}
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
    if df.empty:
        return df.reset_index(drop=True)
    close_time = df["open_time"] + pd.Timedelta(seconds=candle_timeframe_seconds(tf))
    return df[close_time <= now].reset_index(drop=True)


def get_candles(
    symbol: str,
    tf: str,
    start,
    end,
    closed_only: bool = True,
    cache_dir: Optional[str] = None,
    fetcher: Optional[object] = None,
    offline: bool = False,
    now=None,
    exchange: Optional[str] = None,
) -> pd.DataFrame:
    """
    Candles for ``symbol``/``tf`` with ``start <= open_time < end`` (UTC). With
    ``exchange``, the cache is that exchange's own (``cache_path``), and ``fetcher``
    should read from that exchange (``exchange_candles`` does both).

    Missing ranges are fetched with ``fetcher`` (``.fetch(symbol, tf, start_ms,
    end_ms)``; ``exchange_candles`` passes one per exchange) and cached; with
    ``offline=True`` only the cache is used and a request it cannot satisfy raises
    ``CandleDataError``.
    ``closed_only`` (default) never returns the still-forming bar. The result's
    ``attrs["report"]`` is a ``CandleReport`` (gaps are reported, not filled).

    ``now`` (default: the wall clock) also decides which fetched bars are closed enough
    to be written to the cache. A past ``now`` with ``offline=False`` drops the fetched
    bars that close after it, which can leave a hole the cache never refills; pass a
    past ``now`` only with ``offline=True``.
    """
    step = pd.Timedelta(seconds=candle_timeframe_seconds(tf))
    start_ts, end_ts = to_utc(start), to_utc(end)
    now_ts = to_utc(now) if now is not None else pd.Timestamp.now(tz="UTC")
    path = cache_path(symbol, tf, cache_dir, exchange)
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
        if fetcher is None:
            raise CandleDataError(
                f"no fetcher for the missing {symbol} {tf} bars: read through "
                "exchange_candles (the exchanges in Settings)"
            )
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


# --- the exchanges in Settings (FDS-MX-001 phase E) ----------------------------------


def _exchange_manager():
    """The exchange layer (an ExchangeManager): the exchanges in Settings, primary
    first, connected for public market data."""
    from pt_multi_exchange import market_exchanges

    return market_exchanges().exchange_manager


class ExchangeFetcher:
    """Reads one exchange's candles through the exchange layer, for ``get_candles``:
    a cached series is only ever topped up from the exchange it came from."""

    def __init__(self, manager, exchange: str, symbol: str) -> None:
        self.manager = manager
        self.exchange = exchange
        self.symbol = symbol  # the coin's market as the layer takes it, e.g. BTC-USD

    def fetch(
        self, symbol: str, tf: str, start_ms: int, end_ms: Optional[int] = None
    ) -> List[list]:
        now_ms = int(time.time() * 1000)
        end = now_ms if end_ms is None else int(end_ms)
        return self.manager.candles(
            self.symbol, tf, int(start_ms), end, now_ms, only=self.exchange
        ).value


def exchange_candles(
    symbol: str,
    tf: str,
    start,
    end,
    closed_only: bool = True,
    cache_dir: Optional[str] = None,
    offline: bool = False,
    now=None,
    manager=None,
    exchanges: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Candles for a coin (``BTC``, ``BTC-USD`` or ``BTCUSDT``) with ``start <= open_time
    < end``, from the exchanges in Settings: the primary exchange first, then the
    others in order (``exchanges`` narrows or reorders them). The first exchange that
    can serve the whole range gives the series, from its own cache topped up from it
    only; one that has no market for the coin, cannot reach back, or fails is passed
    over. ``df.attrs`` names the ``exchange`` and ``pair``.

    ``offline=True`` reads the caches only: the first exchange whose cache covers the
    range. Raises MarketNotFound when no exchange has the coin, otherwise
    CandleDataError with each exchange's answer.
    """
    from pt_exchange_abstraction import (
        MarketDataUnavailable,
        MarketNotFound,
        dollar_symbol,
    )

    market = dollar_symbol(symbol)
    move_flat_cache(cache_dir)
    manager = manager if manager is not None else _exchange_manager()
    names = list(exchanges) if exchanges is not None else manager.exchange_names()
    reasons: List[str] = []
    not_found = 0
    for name in names:
        connector = _connector(manager, name)
        if connector is None:
            reasons.append(f"{name}: not connected")
            continue
        pair = connector.market_symbol(market)
        try:
            df = get_candles(
                pair,
                tf,
                start,
                end,
                closed_only=closed_only,
                cache_dir=cache_dir,
                fetcher=ExchangeFetcher(manager, name, market),
                offline=offline,
                now=now,
                exchange=name,
            )
        except MarketNotFound as exc:
            not_found += 1
            reasons.append(f"{name}: {exc}")
            continue
        except (CandleDataError, MarketDataUnavailable, OSError) as exc:
            reasons.append(f"{name}: {exc}")
            continue
        df.attrs["exchange"] = name
        df.attrs["pair"] = pair
        return df
    if reasons and not_found == len(reasons):
        raise MarketNotFound(
            f"No exchange has a market for {market}: " + "; ".join(reasons)
        )
    raise CandleDataError(
        f"No exchange gave {tf} candles for {market}: "
        + ("; ".join(reasons) or "no exchange connected")
    )


_moved: set = set()
_move_lock = threading.Lock()


def move_flat_cache(cache_dir: Optional[str] = None) -> None:
    """Move the files cached before FDS-MX-001 phase F (directly in the cache folder;
    every one holds Binance bars) into the ``binance`` folder, once per folder and
    process. A file already there is kept, and the old one stays where it was."""
    folder = os.path.abspath(cache_dir or cache_dir_default())
    with _move_lock:
        if folder in _moved:
            return
        _moved.add(folder)
        try:
            names = [
                n
                for n in os.listdir(folder)
                if n.endswith(".csv") and os.path.isfile(os.path.join(folder, n))
            ]
        except OSError:
            return
        target = os.path.join(folder, FLAT_CACHE_EXCHANGE)
        for name in names:
            destination = os.path.join(target, name)
            if os.path.exists(destination):
                continue
            try:
                os.makedirs(target, exist_ok=True)
                shutil.move(os.path.join(folder, name), destination)
            except OSError:
                continue


def _connector(manager, name: str):
    for exchange_type, exchange in manager.exchanges.items():
        if exchange_type.value == name:
            return exchange
    return None


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
