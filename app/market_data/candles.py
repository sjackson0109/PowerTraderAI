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
  dependency. Only missing ranges are fetched, and a bar that has not settled (closed
  less than ``SETTLE_SECONDS`` ago, or still forming) is never written to the cache.
  Each request for new bars also asks for the last ``REFETCH_TAIL_BARS`` cached ones
  again: a bar the exchange revised after it was cached is replaced, and logged.
  When the exchange has no bars before a series' first one (a pair listed later),
  ``<PAIR>_<TF>.start.json`` says so, and that stretch is not asked for again for
  ``NO_BARS_BEFORE_MAX_AGE``. A gap inside the cached series is asked for again,
  within limits (``_gaps_to_ask``); one the exchange has no bars in either (a halt)
  is recorded in ``<PAIR>_<TF>.gaps.json``.
* Validation: timestamps must be strictly increasing with no duplicates (raises);
  gaps are *reported* in ``df.attrs["report"]``, never filled with made-up bars.

Candle frames have exactly the columns the strategy interface expects::

    open_time (UTC, ascending), open, high, low, close, volume
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import pandas as pd

from market_data.timeframes import candle_timeframe_seconds

logger = logging.getLogger("market_data.candles")

# Every bar cached before FDS-MX-001 phase F came from Binance spot klines.
FLAT_CACHE_EXCHANGE = "binance"
CANDLE_COLUMNS = ["open_time", "open", "high", "low", "close", "volume"]
_NUMERIC = ["open", "high", "low", "close", "volume"]


# How long "the exchange has no bars before the cached first one" is trusted before
# that stretch is asked for again (an exchange can add older history).
NO_BARS_BEFORE_MAX_AGE = pd.Timedelta(days=30)

# A bar counts as closed only this many seconds after its close time, by the wall
# clock: before that it is neither cached nor decided on (the signal engine uses the
# same rule, through ``settled``). Two things can make a bar read at its close wrong:
# this computer's clock running a few seconds fast (a PC clock drifts between its
# corrections from a time server), and the exchange still adding the last trades to
# the bar. 30 s covers both with room to spare, matches the signal engine's 30 s
# retry for a bar the exchange publishes late, and delays a 1h decision by under 1%
# of the bar. A bar the exchange changes later than that is caught by the refetched
# tail (``REFETCH_TAIL_BARS``).
SETTLE_SECONDS = 30

# Each request for new bars starts this many cached bars earlier, so the last cached
# bars are compared with the exchange's current ones and replaced when they differ.
# Three bars: a bar is read again with each of the next two bars (for 1h, up to two
# hours after it was first cached), in the request made for them anyway.
REFETCH_TAIL_BARS = 3
# At most this many revised bars are logged one by one per read (then a count).
_REVISIONS_LOGGED = 5

# How long "the exchange has no bars in this gap inside the series" is trusted before
# the gap is asked for again (as NO_BARS_BEFORE_MAX_AGE: an exchange can backfill).
NO_BARS_IN_GAP_MAX_AGE = pd.Timedelta(days=30)


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


def settled(now) -> pd.Timestamp:
    """The latest close time that counts as closed at wall-clock time ``now``: a bar
    is closed only ``SETTLE_SECONDS`` after its close."""
    return to_utc(now) - pd.Timedelta(seconds=SETTLE_SECONDS)


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


def start_record_path(path: str) -> str:
    """``BTC-USD_1h.csv`` -> ``BTC-USD_1h.start.json``: where the exchange's bars of
    that series begin."""
    return os.path.splitext(path)[0] + ".start.json"


def _known_empty_from(
    path: str, first_open: pd.Timestamp, now: pd.Timestamp
) -> Optional[pd.Timestamp]:
    """The time from which the exchange was asked and had no bars until the cached
    first bar ``first_open``, or None: never asked, asked about another first bar,
    or asked longer than ``NO_BARS_BEFORE_MAX_AGE`` ago."""
    try:
        with open(start_record_path(path), "r", encoding="utf-8") as f:
            data = json.load(f)
        if to_utc(data["first_open"]) != first_open:
            return None
        if now - to_utc(data["checked_at"]) > NO_BARS_BEFORE_MAX_AGE:
            return None
        return to_utc(data["empty_from"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _record_empty_from(
    path: str, empty_from: pd.Timestamp, first_open: pd.Timestamp
) -> None:
    """Record that the exchange has no bars from ``empty_from`` until ``first_open``.
    A record that cannot be written only costs the requests next time."""
    record = {
        "empty_from": empty_from.isoformat(),
        "first_open": first_open.isoformat(),
        "checked_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    target = start_record_path(path)
    tmp = f"{target}.tmp"
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f)
        os.replace(tmp, target)
    except OSError:
        pass


def gap_record_path(path: str) -> str:
    """``BTC-USD_1h.csv`` -> ``BTC-USD_1h.gaps.json``: the gaps inside that series the
    exchange was asked for again and had no bars in."""
    return os.path.splitext(path)[0] + ".gaps.json"


def _empty_gaps(path: str) -> List[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """(first, last open time, checked_at) of each stretch inside the series that the
    exchange had no bars in, when asked less than ``NO_BARS_IN_GAP_MAX_AGE`` ago."""
    now = pd.Timestamp.now(tz="UTC")
    try:
        with open(gap_record_path(path), "r", encoding="utf-8") as f:
            data = json.load(f)
        stretches = [
            (to_utc(s["from"]), to_utc(s["to"]), to_utc(s["checked_at"]))
            for s in data["empty"]
        ]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return [s for s in stretches if now - s[2] <= NO_BARS_IN_GAP_MAX_AGE]


def _record_empty_gaps(
    path: str, stretches: List[Tuple[pd.Timestamp, pd.Timestamp]]
) -> None:
    """Record that the exchange, asked just now, has no bars in ``stretches`` (first,
    last open time). A recorded stretch inside a new one is dropped. A record that
    cannot be written only costs the requests next time."""
    now = pd.Timestamp.now(tz="UTC")
    new = [(a, b, now) for a, b in stretches]
    kept = [
        s
        for s in _empty_gaps(path)
        if not any(a <= s[0] and s[1] <= b for a, b, _ in new)
    ]
    record = {
        "empty": [
            {"from": a.isoformat(), "to": b.isoformat(), "checked_at": c.isoformat()}
            for a, b, c in kept + new
        ]
    }
    target = gap_record_path(path)
    tmp = f"{target}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f)
        os.replace(tmp, target)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


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
    """Cache format: ``open_time_ms`` (epoch ms, exact) + open, high, low, close, volume.

    The temporary file is this process's own, so the hub, the trader and research
    workers can refresh the same cache at once. A cache that cannot be replaced (on
    Windows, while another process reads it) is left as it was: that only costs the
    requests next time, and the caller still gets the bars it fetched."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    out = df[_NUMERIC].copy()
    out.insert(
        0,
        "open_time_ms",
        ((df["open_time"] - epoch) // pd.Timedelta(milliseconds=1)).astype("int64"),
    )
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        out.to_csv(tmp, index=False)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _closed_only(df: pd.DataFrame, tf: str, now: pd.Timestamp) -> pd.DataFrame:
    if df.empty:
        return df.reset_index(drop=True)
    close_time = df["open_time"] + pd.Timedelta(seconds=candle_timeframe_seconds(tf))
    return df[close_time <= now].reset_index(drop=True)


def _log_revisions(
    symbol: str,
    tf: str,
    exchange: Optional[str],
    cached: pd.DataFrame,
    fetched: pd.DataFrame,
) -> None:
    """Log the cached bars that the exchange's ``fetched`` bars change: it revised them
    after they were cached (each is replaced by the exchange's). Once per revision: the
    cache holds the exchange's bar afterwards."""
    if cached.empty or fetched.empty:
        return
    both = cached.merge(fetched, on="open_time", suffixes=("_old", "_new"))
    changed = pd.Series(False, index=both.index)
    for column in _NUMERIC:
        old, new = both[f"{column}_old"], both[f"{column}_new"]
        changed |= (old != new) & ~(old.isna() & new.isna())
    revised = both[changed]
    series = f"{exchange} {symbol} {tf}" if exchange else f"{symbol} {tf}"
    for bar in revised.head(_REVISIONS_LOGGED).itertuples(index=False):
        logger.warning(
            f"{series} bar {bar.open_time} revised by the exchange after it was "
            f"cached: close {bar.close_old} -> {bar.close_new}, volume "
            f"{bar.volume_old} -> {bar.volume_new}; the cache now holds the new bar"
        )
    if len(revised) > _REVISIONS_LOGGED:
        logger.warning(
            f"{series}: {len(revised) - _REVISIONS_LOGGED} more bars revised by the "
            "exchange after they were cached"
        )


# The gaps inside a cache already asked for again in this process, each as (cache
# file, first missing open time, last missing open time).
_gaps_asked: set = set()
_gaps_lock = threading.Lock()


def _gaps_to_ask(
    path: str,
    report: CandleReport,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    tail_from: pd.Timestamp,
) -> Tuple[List[Tuple[pd.Timestamp, pd.Timestamp]], List[tuple]]:
    """The gaps inside the cached series (``report``) to ask the exchange for again,
    as (first, last open time) within ``start_ts`` .. ``end_ts`` (end exclusive), with
    their ``_gaps_asked`` keys. A gap that is real (a halt, such as Coinbase's
    2.5-year XRP halt, or no trades in a bar) must not cost requests on every read, so
    a gap is asked for only when:

    * it is inside the range read (and only that part of it is asked for);
    * it ends before the last ``REFETCH_TAIL_BARS`` cached bars (``tail_from``): those
      are asked for again with each new bar anyway;
    * it has not been asked for in this process, whatever the answer was (so a
      failing exchange is not asked again and again);
    * the exchange has not answered, in the last ``NO_BARS_IN_GAP_MAX_AGE``, that it
      has no bars there (``<PAIR>_<TF>.gaps.json``, written by any process).
    """
    last_wanted = end_ts - pd.Timedelta(milliseconds=1)
    known_empty = None
    gaps: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    keys: List[tuple] = []
    for first, last, _ in report.gaps:
        if last >= tail_from:
            continue
        a, b = max(first, start_ts), min(last, last_wanted)
        if a > b:
            continue
        key = (os.path.abspath(path), first, last)
        with _gaps_lock:
            if key in _gaps_asked:
                continue
        if known_empty is None:
            known_empty = _empty_gaps(path)
        if any(f <= a and b <= t for f, t, _ in known_empty):
            continue
        gaps.append((a, b))
        keys.append(key)
    return gaps, keys


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
    A request for new bars starts ``REFETCH_TAIL_BARS`` cached bars earlier: a cached
    bar the exchange now gives differently is replaced with the exchange's, and logged.
    Gaps inside the cached series are asked for again within the limits of
    ``_gaps_to_ask``, all in one request range (from the first gap to the last), so
    refilling them never costs more requests than reading the range once. A refill
    that fails is logged and the cached bars are returned.

    ``now`` decides which bars have closed: one that closes after it is not returned
    (with ``closed_only``) and never written to the cache. Default: the wall clock
    less ``SETTLE_SECONDS`` (``settled``), so a bar counts as closed only once it has
    settled. An explicit ``now`` is used as it is (a research cut, such as the
    trainer's ``train_end``). A past ``now`` with ``offline=False`` drops the fetched
    bars that close after it, which can leave a hole the cache never refills; pass a
    past ``now`` only with ``offline=True``.
    """
    step = pd.Timedelta(seconds=candle_timeframe_seconds(tf))
    start_ts, end_ts = to_utc(start), to_utc(end)
    now_ts = (
        to_utc(now)
        if now is not None
        else settled(pd.Timestamp(time.time(), unit="s", tz="UTC"))
    )
    path = cache_path(symbol, tf, cache_dir, exchange)
    cached = _read_cache(path)
    # a corrupt cache is an error, not something to repair silently
    cached_report = validate_candles(cached, tf)

    # Ranges are (first open_time, last open_time) INCLUSIVE; bars opening at or
    # after ``end`` (exclusive) or after ``now`` are not wanted.
    last_wanted = min(end_ts, now_ts) - pd.Timedelta(milliseconds=1)
    want: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    extend_from: Optional[pd.Timestamp] = None  # the first new bar after the cache
    tail_from: Optional[pd.Timestamp] = None  # the first of the last cached bars
    if cached.empty:
        want.append((start_ts, last_wanted))
    else:
        first_c, last_c = cached["open_time"].iloc[0], cached["open_time"].iloc[-1]
        tail_from = max(first_c, last_c - (REFETCH_TAIL_BARS - 1) * step)
        if start_ts < first_c:
            # a stretch the exchange was asked for and had no bars in is not asked
            # for again
            empty_from = _known_empty_from(path, first_c, now_ts)
            if empty_from is None:
                want.append((start_ts, first_c - step))
            elif start_ts < empty_from:
                want.append((start_ts, empty_from - step))
        if last_wanted >= last_c + step:
            extend_from = last_c + step
            want.append((extend_from, last_wanted))
    want = [(a, b) for a, b in want if b >= a]

    if want and offline:
        raise CandleDataError(
            f"offline: cache for {symbol} {tf} does not cover {start_ts} -> {end_ts} "
            f"(missing {[(str(a), str(b)) for a, b in want]})"
        )

    gaps: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    gap_keys: List[tuple] = []
    if not offline and fetcher is not None and tail_from is not None:
        gaps, gap_keys = _gaps_to_ask(path, cached_report, start_ts, end_ts, tail_from)

    if want or gaps:
        if want and fetcher is None:
            raise CandleDataError(
                f"no fetcher for the missing {symbol} {tf} bars: read through "
                "exchange_candles (the exchanges in Settings)"
            )
        frames = [cached]
        for a, b in want:
            # the request for new bars asks for the last cached bars again too
            ask_from = tail_from if extend_from is not None and a == extend_from else a
            rows = fetcher.fetch(symbol, tf, _ms(ask_from), _ms(b))
            fetched = _closed_only(_frame_from_klines(rows), tf, now_ts)
            _log_revisions(symbol, tf, exchange, cached, fetched)
            frames.append(fetched)
        gaps_answered = None
        if gaps:
            span = (gaps[0][0], gaps[-1][1])
            with _gaps_lock:
                _gaps_asked.update(gap_keys)
            try:
                rows = fetcher.fetch(symbol, tf, _ms(span[0]), _ms(span[1]))
            except Exception as exc:  # noqa: BLE001 - the gaps stay as they were
                series = f"{exchange} {symbol} {tf}" if exchange else f"{symbol} {tf}"
                logger.warning(
                    f"{series}: the gaps in {span[0]} .. {span[1]} could not be asked "
                    f"for again ({type(exc).__name__}: {exc}); using the cached bars"
                )
            else:
                fetched = _closed_only(_frame_from_klines(rows), tf, now_ts)
                _log_revisions(symbol, tf, exchange, cached, fetched)
                frames.append(fetched)
                gaps_answered = span
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
        if not merged.empty:
            # every range asked for that starts before the first bar now held: the
            # exchange has no bars between its start and that bar
            first_now = merged["open_time"].iloc[0]
            asked_from = [a for a, _ in want if a < first_now]
            if asked_from:
                _record_empty_from(path, min(asked_from), first_now)
        if gaps_answered is not None:
            # what is still missing in the range asked for: the exchange has no bars
            lo, hi = gaps_answered
            empty = [
                (max(a, lo), min(b, hi))
                for a, b, _ in validate_candles(merged, tf).gaps
                if a <= hi and b >= lo
            ]
            if empty:
                _record_empty_gaps(path, empty)
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
    a cached series is only ever topped up from the exchange it came from.

    A size the exchange does not serve (Coinbase's 2h, 4h, 8h, 12h and weekly bars)
    is built from the smaller size it does serve, read through the same cache
    (``cache_dir``): only the smaller bars missing there are fetched, so building
    four sizes from 1h bars downloads the 1h bars once."""

    def __init__(
        self, manager, exchange: str, symbol: str, cache_dir: Optional[str] = None
    ) -> None:
        self.manager = manager
        self.exchange = exchange
        self.symbol = symbol  # the coin's market as the layer takes it, e.g. BTC-USD
        self.cache_dir = cache_dir

    def fetch(
        self, symbol: str, tf: str, start_ms: int, end_ms: Optional[int] = None
    ) -> List[list]:
        now_ms = int(time.time() * 1000)
        end = now_ms if end_ms is None else int(end_ms)
        base = self._built_from(tf)
        if base is not None:
            return self._build(symbol, tf, base, int(start_ms), end)
        return self.manager.candles(
            self.symbol, tf, int(start_ms), end, now_ms, only=self.exchange
        ).value

    def _built_from(self, tf: str) -> Optional[str]:
        """The cached size ``tf`` is built from, or None when the exchange serves
        ``tf`` itself (or serves nothing to build it from: the layer says so)."""
        from market_data.resample import build_from

        connector = _connector(self.manager, self.exchange)
        if connector is None:
            return None
        native = connector.candle_timeframes()
        return None if tf in native else build_from(tf, native)

    def _build(
        self, symbol: str, tf: str, base: str, start_ms: int, end_ms: int
    ) -> List[list]:
        """``tf`` bars opening from ``start_ms`` to ``end_ms`` (inclusive), built from
        the cached closed ``base`` bars (a group still forming is not built)."""
        from market_data.resample import build_candles
        from market_data.timeframes import bar_open_floor

        step_ms = candle_timeframe_seconds(tf) * 1000
        # every base bar of the last tf bar opening by end_ms (end exclusive)
        last_open_ms = bar_open_floor(end_ms // 1000, tf) * 1000
        df = get_candles(
            symbol,
            base,
            pd.Timestamp(start_ms, unit="ms", tz="UTC"),
            pd.Timestamp(last_open_ms + step_ms, unit="ms", tz="UTC"),
            cache_dir=self.cache_dir,
            fetcher=self,
            exchange=self.exchange,
        )
        rows = [
            [_ms(t), o, h, lo, c, v]
            for t, o, h, lo, c, v in zip(
                df["open_time"],
                df["open"],
                df["high"],
                df["low"],
                df["close"],
                df["volume"],
            )
        ]
        return [r for r in build_candles(rows, base, tf) if start_ms <= r[0] <= end_ms]


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
                fetcher=ExchangeFetcher(manager, name, market, cache_dir),
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
