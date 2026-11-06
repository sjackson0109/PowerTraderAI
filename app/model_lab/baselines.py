"""
Random baselines (FDS-MH-001 section 5.6). Both keep the contestant's patience, and
both hold one trade at a time per coin, as the trader does.

**R1, same waits, random order** (``r1_run``). Per coin: from the coin's first stream
hour, and after each exit, wait one of the contestant's own waits on that coin, drawn
with replacement, then enter at the first decided hour that far on
(``model_gate.same_waits``, as the trainer's gate does). A wait is the time from being
free to entering; the time after the contestant's last exit is not a wait. R1's entry
count varies around the contestant's.

**R2, same schedule, other dates** (``r2_run``). The contestant's entry signal on every
coin is moved by an offset and replayed one trade at a time; it wraps round each coin's
stream. This keeps how its entries cluster in time and across coins, which R1 does not.
The offset stays at least ``min_shift`` (D = 160 days: the longest look-back, 100 days,
plus 60 for a trade) from 0 and from the stream's length, so a moved signal is never
built from the prices of the trade it starts. A draw takes one number ``u`` in [0, 1),
and each coin's offset is that share of its allowed range (``shift``): coins whose
streams have the same length, as most do, are moved by the same offset. A coin whose
stream is shorter than 2D takes no part.

Draw b of either baseline uses ``random.Random(seed + b)`` and its ``random()`` alone,
so a seed repeats exactly across Python versions; R2's draw b moves every contestant by
the same offset.
"""

from __future__ import annotations

import bisect
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import entry_gate
import model_gate
from model_lab.replay import Trade, TradeTable, schedule
from model_lab.series import DAY_S, HOUR_S
from model_lab.walkforward import Decisions, Stopped

MIN_SHIFT_DAYS = 160  # D
R1 = entry_gate.SAME_WAITS
R2 = "other dates"


@dataclass(eq=False)
class Plan:
    """One contestant on one coin, ready for random draws."""

    coin: str
    start: int  # the coin's first position in the contestant's stream
    length: int  # positions from ``start`` to the stream's end
    table: TradeTable
    decided: List[int]
    ones: List[int]
    entries: List[Tuple[int, Trade]]  # the contestant's own trades, one at a time
    waits: List[int]


def plan(decisions: Decisions, table: TradeTable) -> Plan:
    ones = decisions.ones()
    entries = schedule(ones, table, decisions.join)
    return Plan(
        decisions.coin,
        decisions.join,
        max(0, len(table) - decisions.join),
        table,
        decisions.decided(),
        ones,
        entries,
        model_gate.waits_of(entries, decisions.join),
    )


def r1_run(plans: Sequence[Plan], rng: random.Random) -> List[Trade]:
    """One R1 draw over every coin (in the order given)."""
    out: List[Trade] = []
    for p in plans:
        out.extend(
            model_gate.same_waits(p.decided, p.waits, p.table.trade, rng, p.start)
        )
    return out


def min_shift_hours(days: int = MIN_SHIFT_DAYS) -> int:
    return int(days) * DAY_S // HOUR_S


def takes_part(p: Plan, min_shift: int) -> bool:
    return p.length >= 2 * min_shift


def shift(u: float, length: int, min_shift: int) -> int:
    """The offset of a stream of ``length`` positions for the draw's ``u``: from
    ``min_shift`` to ``length - min_shift``."""
    return min_shift + int(u * (length - 2 * min_shift + 1))


def moved(ones: Sequence[int], start: int, length: int, delta: int) -> List[int]:
    """The positions of ``ones`` (each at least ``start``) moved by ``delta``, wrapping
    round the ``length`` positions from ``start``, ascending."""
    rel = [i - start for i in ones]
    k = bisect.bisect_left(rel, length - delta)
    return [start + r + delta - length for r in rel[k:]] + [
        start + r + delta for r in rel[:k]
    ]


def r2_run(plans: Sequence[Plan], rng: random.Random, min_shift: int) -> List[Trade]:
    """One R2 draw over the coins that take part (in the order given)."""
    u = rng.random()
    out: List[Trade] = []
    for p in plans:
        if not takes_part(p, min_shift):
            continue
        ones = moved(p.ones, p.start, p.length, shift(u, p.length, min_shift))
        out.extend(t for _i, t in schedule(ones, p.table, p.start))
    return out


def draws(
    kind: str,
    plans: Sequence[Plan],
    runs: int,
    seed: int,
    min_shift: int,
    stop=None,
) -> Optional[entry_gate.Baseline]:
    """``runs`` draws of baseline ``kind`` (R1 or R2), scored by return per day held
    after fees over every coin's trades. None when no draw has a score."""

    def draw_run(rng: random.Random) -> List[Trade]:
        if stop is not None and stop():
            raise Stopped()
        if kind == R1:
            return r1_run(plans, rng)
        return r2_run(plans, rng, min_shift)

    return entry_gate.run_draws(draw_run, runs, seed, entry_gate.PER_DAY, kind)


def r2_coins(plans: Sequence[Plan], min_shift: int) -> Tuple[List[str], List[str]]:
    """(the coins that take part in R2, those whose streams are too short)."""
    part = [p.coin for p in plans if takes_part(p, min_shift)]
    return part, [p.coin for p in plans if not takes_part(p, min_shift)]


def own_trades(
    plans: Sequence[Plan], coins: Optional[Sequence[str]] = None
) -> List[Trade]:
    keep = None if coins is None else set(coins)
    return [t for p in plans if keep is None or p.coin in keep for _i, t in p.entries]


def by_coin(plans: Sequence[Plan]) -> Dict[str, Plan]:
    return {p.coin: p for p in plans}
