"""
Gaps in a candle series longer than a day (an exchange halt, a delisting and
relisting), one rule for research and trading:

* the strategy lab uses a series from after its last such gap
  (``strategy_lab.simulate``);
* the signal engine holds entries while the bars a decision reads contain one
  (``signal_engine``).

A gap of up to 24 hours is kept, as in the model lab (``model_lab.series``).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

MAX_GAP_S = 24 * 3600  # a longer gap ends the earlier part of a series (model lab's)


def after_long_gaps(
    frame: pd.DataFrame, bar_seconds: int
) -> Tuple[pd.DataFrame, Optional[Dict[str, Any]]]:
    """``frame`` from the first bar after its last gap longer than ``MAX_GAP_S``, and
    the cut for the run's record (None when there is no such gap).

    A gap of up to 24 hours is kept: there is no bar in it, so no entry is made there,
    and an open trade carries on at the next bar. A longer gap (an exchange halt, a
    delisting and relisting) ends the earlier part, as in the model lab
    (``model_lab.series``): otherwise a trade, or an indicator's lookback, would run
    straight across months with no market."""
    if len(frame) < 2:
        return frame, None
    times = frame["open_time"]
    missing_s = times.diff().dt.total_seconds().to_numpy() - float(bar_seconds)
    long_gaps = np.flatnonzero(missing_s > MAX_GAP_S)
    if not len(long_gaps):
        return frame, None
    k = int(long_gaps[-1])  # the first bar after the last long gap
    kept = frame.iloc[k:].reset_index(drop=True)
    kept.attrs = dict(frame.attrs)
    cut = {
        "earlier_last_bar": times.iloc[k - 1].isoformat(),
        "kept_from": times.iloc[k].isoformat(),
        "bars_dropped": k,
    }
    return kept, cut
