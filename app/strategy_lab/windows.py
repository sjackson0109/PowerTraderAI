"""
The data windows of strategy research (FDS-SR-001 section 6.1).

* **Development**: 2021-01-01 to 2025-05-06 (UTC, [start, end)). Everything declared
  under FDS-SR-001 is scored here, and research backtests in Settings read only this.
* **Lockbox**: 2025-05-06 to 2026-11-06, FDS-MH-001's (section 5.7). Read only by a
  declared evaluation's final check, within FDS-MH-001's limit of 5 openings a month
  across every batch.
* **After 2026-11-06**: reserved for a registered forward confirmation.

History before the development period (from 2020-01-01) is warm-up only.
"""

from __future__ import annotations

from typing import Tuple

import pandas as pd

HISTORY_START = pd.Timestamp("2020-01-01", tz="UTC")
DEVELOPMENT = (
    pd.Timestamp("2021-01-01", tz="UTC"),
    pd.Timestamp("2025-05-06", tz="UTC"),
)
LOCKBOX = (pd.Timestamp("2025-05-06", tz="UTC"), pd.Timestamp("2026-11-06", tz="UTC"))
RESERVED_FROM = LOCKBOX[0]


class ReservedPeriod(ValueError):
    """A run would read months reserved for a final check or a forward window."""


def _utc(t) -> pd.Timestamp:
    ts = pd.Timestamp(t)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def development_only(start, end) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """``[start, end)`` as UTC timestamps, refused when it reaches past the development
    period's end (FDS-SR-001 E-D7): no exploratory run reads the lockbox or later."""
    a, b = _utc(start), _utc(end)
    if not a < b:
        raise ValueError(f"the period must start before it ends: {a} to {b}")
    if b > RESERVED_FROM:
        raise ReservedPeriod(
            f"the period runs to {b.date()}; research runs end by "
            f"{RESERVED_FROM.date()}, where the reserved months begin"
        )
    if a < HISTORY_START:
        raise ValueError(f"no candles are read before {HISTORY_START.date()}")
    return a, b
