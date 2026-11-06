"""
A row's eligible pairs (FDS-SIG-001 section 6).

* **Pairs.** A pair is two consecutive bars (t, t+1) of the timeframe. It counts toward
  the window when bar t opens at or after the window start and bar t+1 closes at or
  before the window end. The window's pairs are taken on the timeframe's grid from the
  start: a pair whose bar t or t+1 is missing from the candles is a pair across a data
  gap, **skipped and counted**.
* **Direction.** Up if close[t+1] > close[t], down if lower. An equal close is a **tie**,
  excluded and counted.
* **The call** for pair (t, t+1) is the candidate's call at the close of bar t, from
  closed bars only (``candidates``); warm-up bars come from before the window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

import numpy as np

from signal_audit.candidates import TIMEFRAME_SECONDS, Bars, Candidate
from signal_audit.stats import Pairs


@dataclass(frozen=True, eq=False)
class RowPairs:
    pairs: Pairs  # the eligible pairs, in time order
    open_s: np.ndarray  # bar t's open time for each eligible pair
    close_t: np.ndarray  # close[t]
    close_next: np.ndarray  # close[t+1]
    window_pairs: int  # pairs on the window's grid
    skipped: int  # across a data gap (bar t or t+1 missing)
    ties: int
    missing_bars: int  # bars of the window's grid missing from the candles

    @property
    def eligible(self) -> int:
        return self.pairs.eligible


def row_pairs(
    candidate: Candidate,
    bars: Bars,
    inputs: Mapping[str, Bars],
    start_s: int,
    end_s: int,
    calls: Optional[np.ndarray] = None,
) -> RowPairs:
    """The eligible pairs of ``candidate`` on ``bars`` over the window [start_s, end_s]
    (the end is the close time of the last outcome bar). ``calls`` may be given (the
    candidate's calls at every bar of ``bars``)."""
    step = TIMEFRAME_SECONDS[bars.timeframe]
    if calls is None:
        calls = candidate.calls(bars, inputs)
    first = -(-int(start_s) // step) * step  # the first bar opening at or after start
    opens = np.arange(first, int(end_s) - 2 * step + 1, step, dtype=np.int64)
    window_pairs = int(len(opens))
    grid_bars = np.arange(first, int(end_s) - step + 1, step, dtype=np.int64)
    k = np.searchsorted(bars.open_s, grid_bars)
    present = (
        (k < len(bars))
        & (bars.open_s[np.minimum(k, max(len(bars) - 1, 0))] == grid_bars)
        if len(bars)
        else np.zeros(len(grid_bars), dtype=bool)
    )
    missing = int((~present).sum())
    idx = {int(t): int(i) for t, i in zip(grid_bars[present], k[present])}
    keep_open, keep_call, keep_up, keep_ret, keep_c0, keep_c1 = [], [], [], [], [], []
    skipped = ties = 0
    for t0 in opens.tolist():
        i, j = idx.get(t0), idx.get(t0 + step)
        if i is None or j is None:
            skipped += 1
            continue
        c0, c1 = float(bars.close[i]), float(bars.close[j])
        if c1 == c0:
            ties += 1
            continue
        keep_open.append(t0)
        keep_call.append(int(calls[i]))
        keep_up.append(1 if c1 > c0 else 0)
        keep_ret.append(c1 / c0 - 1.0)
        keep_c0.append(c0)
        keep_c1.append(c1)
    pairs = Pairs(
        np.array(keep_call, dtype=np.int8),
        np.array(keep_up, dtype=np.int8),
        np.array(keep_ret, dtype=float),
        candidate.kind,
        bars.timeframe,
    )
    return RowPairs(
        pairs,
        np.array(keep_open, dtype=np.int64),
        np.array(keep_c0),
        np.array(keep_c1),
        window_pairs,
        skipped,
        ties,
        missing,
    )
