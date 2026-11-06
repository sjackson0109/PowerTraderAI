"""
The contestants a batch can be made of, with their fixed parameters (FDS-MH-001
section 5.8). Adding or changing one is a reviewed code change, and makes new
contestants: the window that runs batches has no parameter fields, so results cannot be
tuned by trying values on screen.

Batch 1 (section 7) adds the trained contestants (logistic regression and gradient-
boosted trees) in phase C.
"""

from __future__ import annotations

from typing import Dict, List

from model_lab.contestants import (
    AlwaysFlat,
    Contestant,
    DailyAboveAverage,
    Dip,
    Momentum,
    NewHigh,
    Pattern,
)


def catalogue() -> List[Contestant]:
    """Every contestant, in the order the report lists them."""
    return [
        AlwaysFlat(),
        DailyAboveAverage(20),
        DailyAboveAverage(50),
        DailyAboveAverage(100),
        Momentum(14),
        NewHigh(20),
        DailyAboveAverage(50, context=True),
        Dip(24, 10.0, 90),
        Pattern(),
    ]


def by_key() -> Dict[str, Contestant]:
    return {c.key: c for c in catalogue()}


def get(key: str) -> Contestant:
    try:
        return by_key()[key]
    except KeyError:
        raise KeyError(f"no contestant {key!r} in the catalogue") from None


BATCH_1 = [c.key for c in catalogue()]
