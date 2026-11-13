"""
Dataset snapshots and the one bar hash (PTAI-RD-001 work package 2.2; architecture C,
layer L1).

**The bar hash** (``bar_hash``) names a series' bars by their content: each bar's open
time, prices and volume, whatever frame holds them. Rows in another order, another
column order, extra columns, an index, integer or float columns, and times of any
resolution or time zone give the same hash; a bar revised in any value gives another.
``canonical_bar_bytes`` defines the encoding. It is the candle cache's CSV form, which
three existing functions already write, so for the same bars the new hash is the
digest they record (see "Earlier hashes" below).

**A dataset snapshot** (``build``) records what a piece of research read. Per coin: the
exchange and pair (``df.attrs``, as ``market_data.candles.exchange_candles`` sets them),
the bar count and bar hash, the first and last bar, the gaps (runs of missing bars on
the timeframe's step) and listing evidence. For the whole dataset: the coins (sorted),
the timeframe, the requested range and the range actually served. Its id
(``DatasetSnapshot.id``) is the SHA-256 of its manifest in canonical JSON (sorted keys,
no spaces, ASCII, NaN refused; the rule ``research_engine.store.canonical`` uses). The
same bars over the same range give the same id; a revised bar, another exchange or
another range give another.

**Storage** (``save``, ``load``). One file per snapshot, ``<root>/datasets/<id>.json``,
holding exactly the canonical manifest's bytes, so the file's own SHA-256 is its id.
The root is the caller's (the research engine's folder); this module never works out a
user folder. A snapshot is written once: saving it again changes nothing, and a file
under its id that holds anything else is refused, never replaced. ``load`` refuses a
file whose bytes no longer hash to its name.

**Verification** (``verify``). The bars are read again (frames given, or a loader that
reads each coin from its recorded exchange only, such as ``exchange_loader``), hashed
again and compared coin by coin, naming each coin whose bars changed and how: the bar
count, the first or last bar, the gaps, or the same times with other values (a revised
bar).

**Earlier hashes.** They stay as they are, for the records that hold them; new code
uses ``bar_hash``.

* ``pt_pattern_trainer.candle_sha256(df)``: the same encoding over a frame's rows in
  the frame's order. The same digest as ``bar_hash`` for a frame in time order, on
  whole seconds, with finite values and no negative zero. Kept for the trainer's
  records (``candles[tf].sha256``, and the model store's ``candle_file_sha256``, which
  holds these bar hashes, not file hashes).
* ``model_lab.series.bars_sha256(series)``: the same encoding over a ``Series``' arrays
  (after its gap rule). The same digest as ``bar_hash`` of the bars the series holds.
  Kept for frozen model-lab batches (``series[].sha256``, checked by ``load_frozen``).
* ``signal_audit.evidence.bars_sha256(rows)``: the same encoding over canonical rows.
  The same digest as ``bar_hash`` of those bars. Kept for signal-audit round evidence
  (``candles/<coin>_<tf>.csv.gz`` and its record).
* ``strategy_lab.e1.frame_sha256(frame)``: another encoding (pandas ``to_csv`` with 12
  significant digits, so not exact), so not comparable with ``bar_hash``. Kept for
  E1's frozen ``market.series_sha256``, checked by ``strategy_lab.experiment.verify``.
* ``market_data.candles.file_sha256(path)``: a whole cache file, which grows, so not
  an identity of any bars. Kept for the backtest CLI's source records.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

from market_data.timeframes import candle_timeframe_seconds

KIND = "dataset_snapshot"
VERSION = 1
BAR_ENCODING = "candle-csv-v1"  # canonical_bar_bytes
HEADER = "open_time_ms,open,high,low,close,volume"
VALUES = ("open", "high", "low", "close", "volume")
DATASETS = "datasets"  # the snapshots' folder in the root given
MARKET_STATUS_KEYS = ("pair", "trading", "reason", "exchange")  # no checked_at

Row = Tuple[int, float, float, float, float, float]
Loader = Callable[[str, str, pd.Timestamp, pd.Timestamp, str], pd.DataFrame]

_ID = re.compile(r"[0-9a-f]{64}")
_MS = pd.Timedelta(milliseconds=1)
_EPOCH = pd.Timestamp(0, tz="UTC")
# what an open_time column may hold (pandas.api.types.infer_dtype); numbers are
# refused because their unit (s, ms, ns) cannot be told from the values
_TIME_KINDS = ("datetime64", "datetime", "date", "string", "empty")


class BarDataError(ValueError):
    """Bars that cannot be hashed or recorded: a column missing, an open time missing
    or repeated, a value that is not a finite number, or bars off the timeframe's
    step or outside the requested range."""


class SnapshotError(RuntimeError):
    """A snapshot cannot be stored or read: another manifest under its id, or a file
    that has changed."""


# --- the bar hash ---------------------------------------------------------------------


def iso(ms: int) -> str:
    """``2024-01-01T00:00:00Z`` for a time in milliseconds (with ``.mmm`` only when the
    time is not on a whole second)."""
    ms = int(ms)
    text = pd.Timestamp(ms, unit="ms", tz="UTC").strftime("%Y-%m-%dT%H:%M:%S")
    return f"{text}.{ms % 1000:03d}Z" if ms % 1000 else f"{text}Z"


def to_ms(value) -> int:
    """Milliseconds since the epoch for a datetime, pandas Timestamp or ISO text (naive
    values are UTC)."""
    ts = pd.Timestamp(value)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return int((ts - _EPOCH) // _MS)


def _open_ms(times: pd.Series) -> np.ndarray:
    kind = pd.api.types.infer_dtype(times, skipna=True)
    if kind not in _TIME_KINDS:
        raise BarDataError(
            f"open_time holds {kind} values, not times (numbers are refused: their "
            "unit is unknown)"
        )
    try:
        when = pd.to_datetime(times, utc=True)
    except (ValueError, TypeError, OverflowError) as exc:
        raise BarDataError(f"open_time cannot be read as times ({exc})") from exc
    if when.isna().any():
        raise BarDataError("a bar has no open time")
    since = when - _EPOCH
    if (since % _MS != pd.Timedelta(0)).any():
        raise BarDataError("an open time is not on a whole millisecond")
    return (since // _MS).to_numpy(dtype=np.int64)


def _values(column: pd.Series, name: str) -> np.ndarray:
    try:
        numbers = pd.to_numeric(column, errors="raise")
        out = np.asarray(
            numbers.to_numpy(dtype=np.float64, na_value=np.nan), dtype=np.float64
        )
    except (ValueError, TypeError) as exc:
        raise BarDataError(f"{name} holds values that are not numbers ({exc})") from exc
    if not np.isfinite(out).all():
        raise BarDataError(f"{name}: a value is missing or not finite")
    return out + 0.0  # negative zero becomes zero


def bar_rows(frame: pd.DataFrame) -> List[Row]:
    """The frame's bars as canonical rows ``(open_ms, open, high, low, close, volume)``,
    oldest first: integer milliseconds and Python floats (binary64).

    Read from the columns ``open_time``, ``open``, ``high``, ``low``, ``close`` and
    ``volume``, wherever they are; other columns and the index are ignored.
    ``open_time``: datetimes of any resolution, aware (converted to UTC) or naive
    (taken as UTC), or ISO text. The values: any numbers (integer, float, object,
    Decimal or numeric text), each converted to a binary64 float. A float32 column
    is hashed at its float32 values. Raises BarDataError for a missing column, a
    missing or repeated open time, a time that is not a whole millisecond, numeric
    open times, or a value that is missing or not finite."""
    missing = [c for c in ("open_time",) + VALUES if c not in frame.columns]
    if missing:
        raise BarDataError(f"no {', '.join(missing)} column")
    ms = _open_ms(frame["open_time"])
    values = [_values(frame[name], name) for name in VALUES]
    order = np.argsort(ms, kind="stable")
    ms = ms[order]
    repeated = np.flatnonzero(np.diff(ms) == 0)
    if len(repeated):
        raise BarDataError(f"two bars open at {iso(ms[repeated[0]])}")
    columns = [ms.tolist()] + [v[order].tolist() for v in values]
    return list(zip(*columns))


def _encode(rows: List[Row]) -> bytes:
    lines = [HEADER]
    lines.extend(",".join([str(r[0])] + [repr(v) for v in r[1:]]) for r in rows)
    return ("\n".join(lines) + "\n").encode("utf-8")


def canonical_bar_bytes(frame: pd.DataFrame) -> bytes:
    """The canonical encoding of a frame's bars (``bar_rows`` reads and checks them).

    The bars in open-time order, one line each, after the header line::

        open_time_ms,open,high,low,close,volume
        <open time>,<open>,<high>,<low>,<close>,<volume>

    * open time: integer milliseconds since 1970-01-01T00:00:00Z, in decimal;
    * each price and the volume: its IEEE 754 binary64 value written by Python's
      ``repr`` (the shortest text that reads back as the same float: ``100.0``,
      ``0.1``, ``1e-07``, ``2.5e+16``), with negative zero written as ``0.0``;
    * fields separated by ``,``; every line, the last included, ended by LF; no
      spaces; UTF-8 (ASCII in practice).

    No bars: the header line alone. This is the candle cache's CSV form, the form
    ``pt_pattern_trainer.candle_sha256``, ``model_lab.series.bars_sha256`` and
    ``signal_audit.evidence.bars_sha256`` write (module docstring)."""
    return _encode(bar_rows(frame))


def bar_hash(frame: pd.DataFrame) -> str:
    """The bar hash: SHA-256 of ``canonical_bar_bytes(frame)``, as 64 lower-case hex
    digits."""
    return hashlib.sha256(canonical_bar_bytes(frame)).hexdigest()


# --- the snapshot ---------------------------------------------------------------------


def canonical(value: Any) -> str:
    """``value`` as canonical JSON: sorted keys, no spaces, ASCII; NaN refused."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class DatasetSnapshot:
    """A dataset's manifest, held as its canonical JSON text, so it cannot be changed
    in place. ``id`` is the SHA-256 of that text. ``manifest`` gives a fresh copy."""

    text: str
    id: str = field(init=False)
    _parsed: Dict[str, Any] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        try:
            parsed = json.loads(self.text)
        except ValueError as exc:
            raise SnapshotError(f"not a snapshot manifest ({exc})") from exc
        if not isinstance(parsed, dict) or parsed.get("kind") != KIND:
            raise SnapshotError("not a snapshot manifest")
        if parsed.get("version") != VERSION:
            raise SnapshotError(f"snapshot version {parsed.get('version')!r} unknown")
        if canonical(parsed) != self.text:
            raise SnapshotError("the manifest is not in canonical form")
        object.__setattr__(self, "_parsed", parsed)
        digest = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        object.__setattr__(self, "id", digest)

    @property
    def manifest(self) -> Dict[str, Any]:
        return json.loads(self.text)

    @property
    def timeframe(self) -> str:
        return self._parsed["timeframe"]

    @property
    def coins(self) -> Tuple[str, ...]:
        return tuple(self._parsed["coins"])

    @property
    def start(self) -> pd.Timestamp:
        return pd.Timestamp(self._parsed["requested"]["start"])

    @property
    def end(self) -> pd.Timestamp:
        return pd.Timestamp(self._parsed["requested"]["end"])

    def series(self, coin: str) -> Dict[str, Any]:
        """A copy of the coin's entry: exchange, pair, bars, bar_hash, first_open,
        last_open, gaps, missing_bars and listing."""
        return json.loads(canonical(self._parsed["series"][str(coin).upper()]))


def _coin_keys(frames: Mapping[str, Any]) -> Dict[str, Any]:
    """Coin (upper case) -> the caller's key. Raises on an empty or repeated coin."""
    out: Dict[str, Any] = {}
    for key in frames:
        coin = str(key).strip().upper()
        if not coin:
            raise ValueError("a coin with no name")
        if coin in out:
            raise ValueError(f"{coin} is given twice")
        out[coin] = key
    return out


def _market_status(record: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """The recorded verdict's lasting fields (``market_data.listing``'s
    ``market_status.json``). ``checked_at`` is left out, so checking again and finding
    the same verdict does not change the id."""
    if record is None:
        return None
    out: Dict[str, Any] = {}
    for key in MARKET_STATUS_KEYS:
        value = record.get(key)
        if value is None:
            continue
        if key == "trading" and not isinstance(value, bool):
            raise ValueError(
                f"market status 'trading' must be true or false: {value!r}"
            )
        out[key] = value if key == "trading" else str(value)
    return out


def _coin_entry(
    frame: pd.DataFrame,
    step_ms: int,
    start_ms: int,
    end_ms: int,
    status: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Optional[int], Optional[int]]:
    """(the coin's manifest entry, its first open, its last open)."""
    exchange = str(frame.attrs.get("exchange") or "")
    if not exchange:
        raise BarDataError("the frame does not name its exchange (attrs['exchange'])")
    rows = bar_rows(frame)
    opens = np.array([r[0] for r in rows], dtype=np.int64)
    if len(opens) and (opens[0] < start_ms or opens[-1] >= end_ms):
        outside = opens[(opens < start_ms) | (opens >= end_ms)]
        raise BarDataError(
            f"a bar opens at {iso(outside[0])}, outside the requested range "
            f"{iso(start_ms)} to {iso(end_ms)}"
        )
    steps = np.diff(opens)
    off = np.flatnonzero(steps % step_ms)
    if len(off):
        a, b = int(opens[off[0]]), int(opens[off[0] + 1])
        raise BarDataError(
            f"the bars opening at {iso(a)} and {iso(b)} are not a whole number of "
            "bars apart"
        )
    gaps = []
    for k in np.flatnonzero(steps > step_ms).tolist():
        a, b = int(opens[k]), int(opens[k + 1])
        gaps.append(
            {
                "from": iso(a + step_ms),
                "to": iso(b - step_ms),
                "missing_bars": (b - a) // step_ms - 1,
            }
        )
    first = int(opens[0]) if len(opens) else None
    last = int(opens[-1]) if len(opens) else None
    entry = {
        "exchange": exchange,
        "pair": str(frame.attrs.get("pair") or ""),
        "bars": len(rows),
        "bar_hash": hashlib.sha256(_encode(rows)).hexdigest(),
        "first_open": iso(first) if first is not None else None,
        "last_open": iso(last) if last is not None else None,
        "gaps": gaps,
        "missing_bars": sum(g["missing_bars"] for g in gaps),
        "listing": {
            # whole bars on the series' own step between the requested start and the
            # first bar (listed later, or not served), and between the last bar and
            # the requested end (stopped, or not served yet)
            "missing_at_start": (
                (first - start_ms) // step_ms if first is not None else None
            ),
            "missing_at_end": (
                (end_ms - 1 - last) // step_ms if last is not None else None
            ),
            "market_status": status,
        },
    }
    return entry, first, last


def _manifest(
    timeframe: str,
    step_ms: int,
    start_ms: int,
    end_ms: int,
    series: Dict[str, Dict[str, Any]],
    firsts: List[int],
    lasts: List[int],
) -> Dict[str, Any]:
    return {
        "kind": KIND,
        "version": VERSION,
        "bar_encoding": BAR_ENCODING,
        "timeframe": timeframe,
        "step_s": step_ms // 1000,
        "requested": {"start": iso(start_ms), "end": iso(end_ms)},
        "actual": {
            "first_open": iso(min(firsts)) if firsts else None,
            "last_open": iso(max(lasts)) if lasts else None,
            "last_close": iso(max(lasts) + step_ms) if lasts else None,
        },
        "coins": sorted(series),
        "series": series,
    }


def build(
    frames: Mapping[str, pd.DataFrame],
    timeframe: str,
    start,
    end,
    market_status: Optional[Mapping[str, Optional[Mapping[str, Any]]]] = None,
) -> DatasetSnapshot:
    """The snapshot of per-coin frames (coin -> frame, as ``exchange_candles`` returns
    them, with ``attrs["exchange"]`` and ``attrs["pair"]``) read on ``timeframe`` for
    the requested range: bars opening from ``start`` and before ``end`` (naive times
    are UTC). ``market_status``: per coin, the verdict ``market_data.listing``
    recorded (``read_market_status``), where the caller has one.

    Raises ValueError for an unknown timeframe, an empty range, no coins or a coin
    given twice, and BarDataError (naming the coin) for bars that cannot be hashed or
    lie outside the range or off the timeframe's step."""
    step_ms = candle_timeframe_seconds(timeframe) * 1000
    start_ms, end_ms = to_ms(start), to_ms(end)
    if end_ms <= start_ms:
        raise ValueError(f"the range {iso(start_ms)} to {iso(end_ms)} is empty")
    coins = _coin_keys(frames)
    if not coins:
        raise ValueError("no coins")
    statuses = _coin_keys(market_status or {})
    unknown = sorted(set(statuses) - set(coins))
    if unknown:
        raise ValueError(f"market status for coins not given: {', '.join(unknown)}")
    series: Dict[str, Dict[str, Any]] = {}
    firsts: List[int] = []
    lasts: List[int] = []
    for coin, key in coins.items():
        status = (
            _market_status(market_status[statuses[coin]]) if coin in statuses else None
        )
        try:
            entry, first, last = _coin_entry(
                frames[key], step_ms, start_ms, end_ms, status
            )
        except BarDataError as exc:
            raise BarDataError(f"{coin}: {exc}") from exc
        series[coin] = entry
        if first is not None:
            firsts.append(first)
            lasts.append(last)
    manifest = _manifest(timeframe, step_ms, start_ms, end_ms, series, firsts, lasts)
    return DatasetSnapshot(canonical(manifest))


# --- storage --------------------------------------------------------------------------


def snapshot_path(root: str, snapshot_id: str) -> str:
    """``<root>/datasets/<id>.json``. ``root`` must be an absolute folder (the caller's,
    such as the research engine's), so the file never resolves against the working
    directory; ``snapshot_id`` must be 64 lower-case hex digits."""
    if not os.path.isabs(str(root)):
        raise ValueError(f"expected an absolute folder, got {root!r}")
    if not _ID.fullmatch(str(snapshot_id)):
        raise ValueError(f"not a snapshot id: {snapshot_id!r}")
    return os.path.join(str(root), DATASETS, f"{snapshot_id}.json")


def save(snapshot: DatasetSnapshot, root: str) -> str:
    """Write the snapshot once; returns its path. Saving it again changes nothing. A
    file under its id that holds anything else is refused (SnapshotError) and kept.
    Two processes saving the same snapshot at once write the same bytes."""
    path = snapshot_path(root, snapshot.id)
    data = snapshot.text.encode("utf-8")
    if os.path.exists(path):
        with open(path, "rb") as f:
            held = f.read()
        if held != data:
            raise SnapshotError(
                f"snapshot {snapshot.id}: {path} holds another manifest; it is kept, "
                "not replaced"
            )
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.writing"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def load(snapshot_id: str, root: str) -> DatasetSnapshot:
    """The snapshot saved under ``snapshot_id``; SnapshotError when it is missing,
    unreadable, or its bytes no longer hash to its id."""
    path = snapshot_path(root, snapshot_id)
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as exc:
        raise SnapshotError(f"snapshot {snapshot_id}: cannot be read ({exc})") from exc
    if hashlib.sha256(data).hexdigest() != snapshot_id:
        raise SnapshotError(f"snapshot {snapshot_id}: its file has changed")
    return DatasetSnapshot(data.decode("utf-8"))  # the bytes save wrote: ASCII JSON


# --- verification ---------------------------------------------------------------------


@dataclass(frozen=True)
class Verification:
    """``differences``: per coin, what changed (empty when nothing did). ``now``: the
    snapshot the bars read now give (None when a coin could not be read or hashed,
    or a coin not in the snapshot was given); its id is the snapshot's when nothing
    changed."""

    snapshot_id: str
    differences: Mapping[str, Tuple[str, ...]]
    now: Optional[DatasetSnapshot]

    @property
    def ok(self) -> bool:
        return not self.differences


def exchange_loader(
    cache_dir: Optional[str] = None, offline: bool = False, manager=None
) -> Loader:
    """A loader for ``verify``: each coin's bars from its recorded exchange only,
    through ``market_data.candles.exchange_candles`` (``offline``: that exchange's
    cache only)."""

    def load_coin(coin, timeframe, start, end, exchange):
        from market_data.candles import exchange_candles

        return exchange_candles(
            coin,
            timeframe,
            start,
            end,
            cache_dir=cache_dir,
            offline=offline,
            manager=manager,
            exchanges=[exchange],
        )

    return load_coin


def _compare(was: Mapping[str, Any], now: Mapping[str, Any]) -> Tuple[str, ...]:
    out: List[str] = []
    for key, label in (
        ("exchange", "exchange"),
        ("pair", "pair"),
        ("bars", "bars"),
        ("first_open", "first bar"),
        ("last_open", "last bar"),
    ):
        if was.get(key) != now.get(key):
            out.append(f"{label}: {was.get(key)} -> {now.get(key)}")
    if was.get("gaps") != now.get("gaps"):
        out.append(
            f"gaps: {len(was.get('gaps') or [])} ({was.get('missing_bars')} bars) -> "
            f"{len(now.get('gaps') or [])} ({now.get('missing_bars')} bars)"
        )
    if was.get("bar_hash") != now.get("bar_hash"):
        line = f"bar hash: {str(was.get('bar_hash'))[:12]} -> "
        line += str(now.get("bar_hash"))[:12]
        if not out:
            line += " (the same bar times with other values: a revised bar)"
        out.append(line)
    return tuple(out)


def verify(
    snapshot: DatasetSnapshot,
    frames: Optional[Mapping[str, pd.DataFrame]] = None,
    loader: Optional[Loader] = None,
) -> Verification:
    """Hash the bars again and compare them with the snapshot, coin by coin. Give the
    ``frames`` (coin -> frame), or a ``loader`` called as ``loader(coin, timeframe,
    start, end, exchange)`` for each coin with its recorded exchange (for example
    ``exchange_loader``). A coin that cannot be read or hashed is reported, never
    skipped."""
    if (frames is None) == (loader is None):
        raise ValueError("give the frames or a loader")
    m = snapshot.manifest
    step_ms = int(m["step_s"]) * 1000
    start_ms, end_ms = to_ms(m["requested"]["start"]), to_ms(m["requested"]["end"])
    recorded = m["series"]
    differences: Dict[str, Tuple[str, ...]] = {}
    given: Dict[str, pd.DataFrame] = {}
    if frames is not None:
        given = {coin: frames[key] for coin, key in _coin_keys(frames).items()}
    else:
        for coin in m["coins"]:
            try:
                given[coin] = loader(
                    coin,
                    m["timeframe"],
                    snapshot.start,
                    snapshot.end,
                    recorded[coin]["exchange"],
                )
            except Exception as exc:  # recorded per coin, never silently
                differences[coin] = (
                    f"could not be read ({type(exc).__name__}: {exc})",
                )
    series: Dict[str, Dict[str, Any]] = {}
    firsts: List[int] = []
    lasts: List[int] = []
    for coin, frame in given.items():
        if coin not in recorded:
            differences[coin] = ("not in the snapshot",)
            continue
        status = recorded[coin]["listing"]["market_status"]
        try:
            entry, first, last = _coin_entry(frame, step_ms, start_ms, end_ms, status)
        except BarDataError as exc:
            differences[coin] = (f"its bars cannot be recorded ({exc})",)
            continue
        series[coin] = entry
        if first is not None:
            firsts.append(first)
            lasts.append(last)
        changed = _compare(recorded[coin], entry)
        if changed:
            differences[coin] = changed
    for coin in m["coins"]:
        if coin not in given and coin not in differences:
            differences[coin] = ("no bars given",)
    now = None
    if set(series) == set(m["coins"]) and set(given) <= set(recorded):
        now = DatasetSnapshot(
            canonical(
                _manifest(
                    m["timeframe"], step_ms, start_ms, end_ms, series, firsts, lasts
                )
            )
        )
    return Verification(snapshot.id, dict(sorted(differences.items())), now)
