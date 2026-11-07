"""
A round's candle evidence (FDS-SIG-001 section 12, steps 3 and 4): immutable,
window-scoped snapshots of the bars the run evaluates.

The candle cache is shared and grows: a later fetch appends bars, so a cache file's own
SHA-256 changes even when the window's bars do not, and the cache never asks again for a
bar it already holds, so it cannot see an exchange's later correction. So the round's
evidence is not the cache file but a **snapshot** per (coin, timeframe):

* **What it holds.** Exactly the bars of the round's span on that timeframe: from the
  warm-up before the window start to the last bar closing by the window end, as
  ``open_time_ms, open, high, low, close, volume`` in the candle cache's CSV form
  (``repr`` of each float, LF line ends). Their SHA-256 (``bars_sha256``) is the form
  ``pt_pattern_trainer.candle_sha256`` and FDS-MH-001's series use, so the same bars
  give the same hash wherever they are read.
* **Where it is** (owner, D11). Gzip-compressed (no file name, time 0, level 9, so the
  same bars give the same bytes) in the round's folder, ``candles/<coin>_<tf>.csv.gz``,
  committed with the results. The record holds both the bars' SHA-256 and the file's.
* **Fetch** (``fetch_round``). Each series is read through the exchange layer from the
  registered exchange only (``exchange_candles``, which fills the cache), and fetched again
  from that exchange alone without the cache (``ExchangeManager.candles``; a size the
  exchange does not serve is built from its smaller bars, fetched alike), which must
  name the same exchange and pair. The two must be identical, bar for bar: a
  difference means a historical correction or a cache fault, and the fetch stops,
  naming the first bars that differ. A series fetched before must equal its earlier
  record, or the fetch stops. Only then is the snapshot written (it is never
  overwritten with other bars) and recorded with its exchange, pair, first and last bar,
  bar count and SHA-256.
* **Run** (``load_round``). Only the snapshots are read, never the cache, and each must
  match its record; a snapshot that differs stops the run. The same snapshots give the
  same series, so a repeated run gives the same results; the cache can grow freely.
* **Verify** (``load_round`` again, and ``refetch_differences``). Anyone with the repo
  can check every snapshot against its record and the registration without the
  exchange, re-derive the results from them with the frozen code, and fetch the span
  from the exchange again to see whether its bars still agree.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from signal_audit.candidates import TIMEFRAME_SECONDS, Bars

HEADER = "open_time_ms,open,high,low,close,volume"
Row = Tuple[int, float, float, float, float, float]


class EvidenceError(RuntimeError):
    """The candle evidence cannot be established or does not match its record."""


def _ms(t: Any) -> int:
    return int(t.timestamp() * 1000)


def rows_of(df) -> List[Row]:
    """A candle frame's bars as canonical rows."""
    return [
        (_ms(t), float(o), float(h), float(lo), float(c), float(v))
        for t, o, h, lo, c, v in zip(
            df["open_time"],
            df["open"],
            df["high"],
            df["low"],
            df["close"],
            df["volume"],
        )
    ]


def canonical_bytes(rows: Sequence[Row]) -> bytes:
    lines = [HEADER]
    for r in rows:
        lines.append(",".join([str(int(r[0]))] + [repr(float(v)) for v in r[1:]]))
    return ("\n".join(lines) + "\n").encode("utf-8")


def bars_sha256(rows: Sequence[Row]) -> str:
    return hashlib.sha256(canonical_bytes(rows)).hexdigest()


def differences(a: Sequence[Row], b: Sequence[Row], limit: int = 5) -> List[str]:
    """The first bars that differ between two series (empty when none)."""
    out = []
    by_a = {r[0]: r for r in a}
    by_b = {r[0]: r for r in b}
    for t in sorted(set(by_a) | set(by_b)):
        if by_a.get(t) != by_b.get(t):
            when = datetime.fromtimestamp(t / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            out.append(f"{when}: {by_a.get(t)} vs {by_b.get(t)}")
            if len(out) >= limit:
                break
    return out


def span(record: Mapping[str, Any], tf: str) -> Tuple[int, int]:
    """The round's span on ``tf`` (seconds): from the longest registered warm-up (and
    one bar more, for the first pair's call) before the window start, to the window
    end."""
    from signal_audit.registration import parse_time

    start = parse_time(record["window"]["start"])
    end = parse_time(record["window"]["end"])
    warm = max(int(c["warmup_bars"]) for c in record["candidates"])
    step = TIMEFRAME_SECONDS[tf]
    first = start - timedelta(seconds=(warm + 1) * step)
    return int(first.timestamp()), int(end.timestamp())


def _in_span(rows: Sequence[Row], start_s: int, end_s: int, step: int) -> List[Row]:
    """The bars that open at or after ``start_s`` and close by ``end_s``."""
    return [
        r for r in rows if r[0] >= start_s * 1000 and r[0] + step * 1000 <= end_s * 1000
    ]


def fresh_rows(manager, exchange: str, coin: str, tf: str, start_s: int, end_s: int):
    """The span's closed bars straight from the exchange, through the exchange layer
    without the cache (``ExchangeManager.candles`` with ``only``: a size the exchange
    does not serve is built from its smaller bars, fetched alike)."""
    from pt_exchange_abstraction import dollar_symbol

    step = TIMEFRAME_SECONDS[tf]
    try:
        got = manager.candles(
            dollar_symbol(coin),
            tf,
            start_s * 1000,
            (end_s - step) * 1000,
            only=exchange,
        )
    except Exception as exc:
        raise EvidenceError(
            f"{coin}/{tf}: {exchange} gave no bars to check the cache against "
            f"({type(exc).__name__}: {exc})"
        ) from exc
    if got.exchange != exchange:
        raise EvidenceError(f"{coin}/{tf}: answered by {got.exchange}, not {exchange}")
    rows = [
        (int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]))
        for r in got.value
    ]
    return _in_span(sorted(set(rows)), start_s, end_s, step), got.pair


def _gzip(data: bytes) -> bytes:
    """The same bytes for the same data: no file name, time 0, level 9."""
    buf = io.BytesIO()
    with gzip.GzipFile(
        filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9
    ) as g:
        g.write(data)
    return buf.getvalue()


def write_snapshot(path: str, rows: Sequence[Row]) -> Dict[str, Any]:
    """Write ``rows`` as a compressed snapshot, once: an existing snapshot is never
    rewritten, and one with other bars stops the fetch. Returns the bars' SHA-256, the
    file's and the bar count."""
    data = canonical_bytes(rows)
    sha = hashlib.sha256(data).hexdigest()
    if os.path.exists(path):
        with open(path, "rb") as f:
            packed = f.read()
        try:
            same = hashlib.sha256(gzip.decompress(packed)).hexdigest() == sha
        except (OSError, EOFError):
            same = False
        if not same:
            raise EvidenceError(f"{path}: a snapshot with other bars already exists")
    else:
        packed = _gzip(data)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(packed)
        os.replace(tmp, path)
    return {
        "sha256": sha,
        "file_sha256": hashlib.sha256(packed).hexdigest(),
        "bars": len(rows),
    }


def read_snapshot(path: str, record: Mapping[str, Any]) -> List[Row]:
    """The snapshot's bars, after checking the file and its bars against ``record``."""
    try:
        with open(path, "rb") as f:
            packed = f.read()
    except OSError as exc:
        raise EvidenceError(f"{path}: the snapshot cannot be read ({exc})") from exc
    if hashlib.sha256(packed).hexdigest() != record["file_sha256"]:
        raise EvidenceError(f"{path}: the snapshot file differs from its record")
    try:
        data = gzip.decompress(packed)
    except (OSError, EOFError) as exc:
        raise EvidenceError(
            f"{path}: the snapshot cannot be decompressed ({exc})"
        ) from exc
    if hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise EvidenceError(f"{path}: the snapshot's bars differ from its record")
    rows: List[Row] = []
    for line in data.decode("utf-8").splitlines()[1:]:
        t, o, h, lo, c, v = line.split(",")
        rows.append((int(t), float(o), float(h), float(lo), float(c), float(v)))
    if len(rows) != int(record["bars"]) or bars_sha256(rows) != record["sha256"]:
        raise EvidenceError(f"{path}: the snapshot's bars differ from its record")
    return rows


def snapshot_name(coin: str, tf: str) -> str:
    return f"{coin}_{tf}.csv.gz"


def fetch_round(
    record: Mapping[str, Any],
    manager,
    snapshot_dir: str,
    earlier: Optional[Mapping[str, Any]] = None,
    cache_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Step 3: every audited and input coin's span on each timeframe, from the
    registered exchange, checked against a fresh fetch and any earlier record, and
    written as snapshots (the module docstring). Returns the data record."""
    import pandas as pd

    from market_data import candles

    exchange = record["exchange"]
    files: Dict[str, Any] = {}
    earlier_files = (earlier or {}).get("files", {})
    for coin in sorted(set(record["coins"]) | set(record["input_coins"])):
        for tf in record["timeframes"]:
            start_s, end_s = span(record, tf)
            step = TIMEFRAME_SECONDS[tf]
            df = candles.exchange_candles(
                coin,
                tf,
                pd.Timestamp(start_s, unit="s", tz="UTC"),
                pd.Timestamp(end_s - step + 1, unit="s", tz="UTC"),
                cache_dir=cache_dir,
                manager=manager,
                exchanges=[exchange],
            )
            key = f"{coin}/{tf}"
            if df.attrs.get("exchange") != exchange:
                raise EvidenceError(
                    f"{key}: the cache answered from {df.attrs.get('exchange')}, "
                    f"not {exchange}"
                )
            cached = _in_span(rows_of(df), start_s, end_s, step)
            fresh, pair = fresh_rows(manager, exchange, coin, tf, start_s, end_s)
            if pair != df.attrs.get("pair"):
                raise EvidenceError(
                    f"{key}: {exchange}'s market is {pair} now, the cache's "
                    f"{df.attrs.get('pair')}"
                )
            diff = differences(cached, fresh)
            if diff:
                raise EvidenceError(
                    f"{key}: the cached bars differ from {exchange}'s now (a historical "
                    f"correction or a cache fault): {diff}"
                )
            sha = bars_sha256(cached)
            was = earlier_files.get(key)
            if was is not None and (was["sha256"] != sha or was.get("pair") != pair):
                raise EvidenceError(
                    f"{key}: the series differs from its earlier record ({was['sha256'][:12]} "
                    f"then, {sha[:12]} now)"
                )
            if not cached:
                raise EvidenceError(
                    f"{key}: {exchange} has no bars in the round's span"
                )
            name = snapshot_name(coin, tf)
            written = write_snapshot(os.path.join(snapshot_dir, name), cached)
            files[key] = {
                "exchange": exchange,
                "pair": pair,
                "snapshot": name,
                "sha256": sha,
                "file_sha256": written["file_sha256"],
                "bars": len(cached),
                "first_open_ms": cached[0][0],
                "last_open_ms": cached[-1][0],
                "span": [start_s, end_s],
            }
    return {"exchange": exchange, "files": files}


def load_round(
    record: Mapping[str, Any], data: Mapping[str, Any], snapshot_dir: str
) -> Dict[Tuple[str, str], Bars]:
    """Step 4: every snapshot, checked against the data record and the registration
    (the registered exchange, every audited and input coin on every registered
    timeframe, each over the round's span), as the candidates' bars; never the
    cache."""
    exchange = record["exchange"]
    if data.get("exchange") != exchange:
        raise EvidenceError(
            f"the data record is from {data.get('exchange')}, not the registered "
            f"{exchange}"
        )
    wanted = {
        f"{c}/{tf}"
        for c in set(record["coins"]) | set(record["input_coins"])
        for tf in record["timeframes"]
    }
    have = set(data["files"])
    if have != wanted:
        raise EvidenceError(
            f"the data record does not hold the registered series: missing "
            f"{sorted(wanted - have)}, not registered {sorted(have - wanted)}"
        )
    out: Dict[Tuple[str, str], Bars] = {}
    for key, f in sorted(data["files"].items()):
        coin, tf = key.split("/")
        if f.get("exchange") != exchange:
            raise EvidenceError(f"{key}: from {f.get('exchange')}, not {exchange}")
        if list(f.get("span", [])) != list(span(record, tf)):
            raise EvidenceError(f"{key}: the snapshot's span is not the round's")
        rows = read_snapshot(os.path.join(snapshot_dir, f["snapshot"]), f)
        start_s, end_s = span(record, tf)
        if not rows or _in_span(rows, start_s, end_s, TIMEFRAME_SECONDS[tf]) != rows:
            raise EvidenceError(f"{key}: the snapshot holds bars outside the span")
        if rows[0][0] != f["first_open_ms"] or rows[-1][0] != f["last_open_ms"]:
            raise EvidenceError(f"{key}: the snapshot's first or last bar differs")
        a = np.array(rows, dtype=float)
        out[(coin, tf)] = Bars(
            coin,
            tf,
            np.array([r[0] // 1000 for r in rows], dtype=np.int64),
            a[:, 2],
            a[:, 3],
            a[:, 4],
            a[:, 5],
        )
    return out


def refetch_differences(
    record: Mapping[str, Any],
    data: Mapping[str, Any],
    snapshot_dir: str,
    manager,
) -> Dict[str, List[str]]:
    """Each series whose snapshot no longer agrees with the registered exchange's own
    bars now, fetched again without the cache (empty when every one agrees): the
    independent check of the evidence against its source. A difference is reported,
    not resolved: it may be a correction the exchange made since the fetch."""
    load_round(record, data, snapshot_dir)  # the snapshots match their record first
    out: Dict[str, List[str]] = {}
    for key, f in sorted(data["files"].items()):
        coin, tf = key.split("/")
        start_s, end_s = span(record, tf)
        rows = read_snapshot(os.path.join(snapshot_dir, f["snapshot"]), f)
        fresh, pair = fresh_rows(manager, record["exchange"], coin, tf, start_s, end_s)
        diff = differences(rows, fresh)
        if pair != f.get("pair"):
            diff = [f"the market is {pair} now, {f.get('pair')} in the record"] + diff
        if diff:
            out[key] = diff
    return out
