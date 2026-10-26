"""Build candle sizes an exchange does not serve from a smaller size it does
(FDS-MX-001 section 5.3). Pure data; no dependencies beyond the timeframe table.

Coinbase has no 2h, 4h, 8h, 12h or weekly candles; Kraken has no 2h, 8h or 12h; and
the weekly candles of Kraken and KuCoin open on Thursday, where the app's open on
Monday 00:00 UTC (``bar_open_floor``). Those are built here, from complete groups
only: a 4h bar with one of its hours missing is not built, so it shows as a gap.
"""

from typing import Iterable, List, Optional

from market_data.timeframes import bar_open_floor, candle_timeframe_seconds


def build_from(tf: str, native: Iterable[str]) -> Optional[str]:
    """The largest of the ``native`` sizes that ``tf`` can be built from (one whose
    length divides ``tf``'s), or None when there is none."""
    want = candle_timeframe_seconds(tf)
    best: Optional[str] = None
    for candidate in native:
        try:
            seconds = candle_timeframe_seconds(candidate)
        except ValueError:
            continue  # a size the app has no name for
        if seconds < want and want % seconds == 0:
            if best is None or seconds > candle_timeframe_seconds(best):
                best = candidate
    return best


def build_candles(rows: Iterable[list], from_tf: str, to_tf: str) -> List[list]:
    """``to_tf`` bars built from ``from_tf`` bars. Both are oldest first, as
    ``[open_time_ms, open, high, low, close, volume]``. A group is built only when
    every one of its ``from_tf`` bars is there."""
    from_ms = candle_timeframe_seconds(from_tf) * 1000
    to_seconds = candle_timeframe_seconds(to_tf)
    if to_seconds * 1000 % from_ms:
        raise ValueError(f"{to_tf} bars cannot be built from {from_tf} bars")
    per_group = to_seconds * 1000 // from_ms

    groups = {}
    for row in rows:
        opened = int(row[0])
        key = bar_open_floor(opened // 1000, to_tf) * 1000
        groups.setdefault(key, {})[opened] = row

    built = []
    for key in sorted(groups):
        bars = groups[key]
        expected = [key + i * from_ms for i in range(per_group)]
        if any(t not in bars for t in expected):
            continue  # incomplete: a gap, not a guess
        group = [bars[t] for t in expected]
        built.append(
            [
                key,
                float(group[0][1]),
                max(float(r[2]) for r in group),
                min(float(r[3]) for r in group),
                float(group[-1][4]),
                sum(float(r[5]) for r in group),
            ]
        )
    return built
