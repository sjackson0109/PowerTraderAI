"""
The contestants a batch can be made of, with their fixed parameters (FDS-MH-001
section 5.8). Adding or changing one is a reviewed code change, and makes new
contestants: the window that runs batches has no parameter fields, so results cannot be
tuned by trying values on screen.

The trained contestants (logistic regression and gradient-boosted trees) are batch 1's
9 to 14 (section 7) and batch PV-1's (section 7a, amendment 1).

**Declared batches** (amendment 1). ``BATCH_1`` and ``BATCH_PV_1`` are explicit lists:
adding a contestant to the catalogue never adds it to a declared batch. ``DECLARED`` gives
each one's spec version: "1" for batch 1, declared in section 7 on 2026-11-06, and "1.1"
for PV-1.

**Earlier looks** (``LOOKS``, section 5.7). Every time a contestant's results were
looked at outside a batch's walk-forward, the months they covered are recorded here, in
a reviewed code change, with where the look is written up. A look at a feature's relation
to trade outcomes is recorded for every contestant that uses the feature (amendment 1). A
batch records, when it is frozen, which of them overlap its lockbox (``seen_in``). A
contestant whose lockbox months were seen before cannot have its final check counted as
unseen evidence: the check is shown, and its verdict says so. Months are compared as
[start, end), in UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from model_lab.contestants import (
    AlwaysFlat,
    Contestant,
    DailyAboveAverage,
    Dip,
    Momentum,
    NewHigh,
    Pattern,
    batch_1_models,
    pv_1_models,
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
        *batch_1_models(),
        *pv_1_models(),
    ]


def by_key() -> Dict[str, Contestant]:
    return {c.key: c for c in catalogue()}


def get(key: str) -> Contestant:
    try:
        return by_key()[key]
    except KeyError:
        raise KeyError(f"no contestant {key!r} in the catalogue") from None


# Declared batches (amendment 1): explicit lists, so a contestant added to the catalogue
# never joins a declared batch. Batch 1 is section 7's reference and 14 contestants, in
# its order; batch PV-1 is section 7a's three, then the placebo's variants 2 to 5.
BATCH_1 = [
    "ref.always",
    "rule.sma20",
    "rule.sma50",
    "rule.sma100",
    "rule.mom14",
    "rule.high20",
    "rule.btc50",
    "rule.dip24",
    "pattern",
    "linear.t1.q50",
    "linear.t1.q20",
    "trees.t1.q50",
    "trees.t1.q20",
    "trees.t2.q50",
    "trees.t2.q20",
]
BATCH_PV_1 = [
    "pv.linear.t1.P.q50",
    "pv.linear.t1.PV.q50",
    "pv.linear.t1.PVp.q50",
    "pv.linear.t1.PVp2.q50",
    "pv.linear.t1.PVp3.q50",
    "pv.linear.t1.PVp4.q50",
    "pv.linear.t1.PVp5.q50",
]
# each declared batch: the spec version it was declared under, and its contestants
DECLARED: Dict[str, Tuple[str, List[str]]] = {
    "batch-1": ("1", BATCH_1),
    "pv-1": ("1.1", BATCH_PV_1),
}
SPEC_VERSION = "1.1"  # the current version: amendment 1


# --- earlier looks at contestants' results --------------------------------------------


@dataclass(frozen=True)
class Look:
    key: str  # the contestant
    start: str  # the first day its results covered (UTC)
    end: str  # the day after the last (UTC)
    coins: str
    when: str  # the day the results were looked at
    what: str  # where the look is written up

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


_PHASE_B = (
    "the phase B timing run, batch 20261106-143033: walk-forward only, the lockbox "
    "not read (docs/dev/RUN-LOG-mh-1.md)"
)

LOOKS: Tuple[Look, ...] = (
    (
        Look(
            "pattern",
            "2024-07-01",
            "2026-10-01",
            "BTC, ETH",
            "2026-10-07",
            "FDS-MDL Tests A and B, the pattern model as STRAT-003 with that strategy's "
            "exits (docs/dev/BACKTEST-REPORT-model-1.md)",
        ),
        Look(
            "pattern",
            "2026-03-31",
            "2026-11-05",
            "10 coins",
            "2026-11-05",
            "the volume research's held-out replay and model experiment "
            "(docs/research/volume-module.md, sections 6.4 and 6.5)",
        ),
        Look(
            "pattern",
            "2026-04-01",
            "2026-11-06",
            "the coins with a model in use",
            "2026-11-05",
            "the entry gate's held-out slices of the models in use (the last 20% of each "
            "one's window), in Check the models in use... and the trainer's gate",
        ),
        Look(
            "pattern",
            "2026-04-05",
            "2026-11-05",
            "13 coins",
            "2026-11-05",
            "the entry gate diagnostic (docs/dev/GATE-DIAGNOSTIC-2026-11-05.md)",
        ),
    )
    + tuple(
        Look(key, "2021-01-01", "2025-05-06", "13 coins", "2026-11-06", _PHASE_B)
        for key in (
            "rule.sma20",
            "rule.sma50",
            "rule.sma100",
            "rule.mom14",
            "rule.high20",
            "rule.btc50",
            "rule.dip24",
            "pattern",
        )
    )
    + tuple(
        # amendment 1: a look at a feature, v2, recorded for PV-1's contestants that use it
        Look(
            key,
            "2023-11-06",
            "2026-11-05",
            "10 coins",
            "2026-11-05",
            "the volume research's look at v2 (as rv_hod20) against STRAT-001's trades: a "
            "look at a feature, not at this contestant's results "
            "(docs/research/volume-module.md, sections 5.4 and 6.2)",
        )
        for key in ("pv.linear.t1.PV.q50", "pv.linear.t1.PVp.q50")
    )
)


def looks(key: str) -> List[Look]:
    return [look for look in LOOKS if look.key == key]


def seen_in(key: str, start_s: int, end_s: int, register: Sequence[Look] = LOOKS):
    """The earlier looks at ``key``'s results that cover any of [start_s, end_s)."""
    from model_lab.series import epoch

    return [
        look
        for look in register
        if look.key == key and epoch(look.start) < end_s and start_s < epoch(look.end)
    ]
