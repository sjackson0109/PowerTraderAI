"""
The baselines every strategy is compared with (FDS-SR-001 section 5.4.1, as amended by
the owner on 2026-11-07).

* **REF-HOLD**: each coin bought once, at the open after its first decision bar, and
  held to the last close; sized and costed like any trade in the replay.
* **REF-CASH**: no trades (net 0).
* **REF-RANDOM**: random entries replayed through the strategy's **own exit rules**, in
  the same account, with the same costs and constraints. Resampled holding periods are
  not used: the owner asked that a random baseline keep the strategy's execution and
  exit constraints (2026-11-07).

  Per coin, a draw keeps the strategy's number of entries and the waits between them
  ("same waits, random order", as FDS-MH-001's R1): the flat waits before each of the
  strategy's entries (from its first decision bar, or from the previous exit) are put
  in a random order, and from the first decision bar each wait is followed by an entry
  whose exit is the strategy's own (``TradeTable.trade_from``). A draw that runs out of
  bars stops there; the count it reached is recorded.

  Draw b of a run uses ``random.Random(seed + b)``, and only its ``random()``, so a seed
  gives the same draws on any Python version (FDS-MH-001 section 5.6).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from signal_fusion.evaluation.replay import Account, Costs, Paths
from strategy_lab.candidates import Trade
from strategy_lab.simulate import Simulation


def _first_free(table, from_s: Optional[int]) -> int:
    """The first bar a trade may be decided on: the strategy's warm-up met, and the bar
    opening at or after ``from_s`` (a run's start) when given."""
    first = table.first_decision
    if from_s is not None:
        opens = table.candles["open_time"].map(lambda t: int(t.timestamp()))
        later = np.flatnonzero(opens.to_numpy() >= int(from_s))
        first = max(first, int(later[0]) if len(later) else table.n)
    return first


def hold_trades(sim: Simulation, from_s: Optional[int] = None) -> List[Trade]:
    """REF-HOLD: one trade per coin, from its first decision bar (at or after
    ``from_s``) to the last close."""
    out = []
    for table in sim.tables.values():
        first = _first_free(table, from_s)
        if first <= table.n - 2:
            entry = first + 1
            out.append(table._trade(first, entry, table.n - 1, "end_of_data", True))
    return sorted(out, key=lambda t: (t.entry_s, t.coin))


def _shuffled(values: List[int], rng: random.Random) -> List[int]:
    """Fisher-Yates with ``random()`` only."""
    out = list(values)
    for i in range(len(out) - 1, 0, -1):
        j = int(rng.random() * (i + 1))
        out[i], out[j] = out[j], out[i]
    return out


def waits(
    sim: Simulation, taken: Sequence[Trade], from_s: Optional[int] = None
) -> Dict[str, List[int]]:
    """Per coin, the flat bars before each of ``taken``'s entries: from the coin's first
    decision bar (at or after ``from_s``), then from each exit fill's bar."""
    out: Dict[str, List[int]] = {}
    for coin, table in sim.tables.items():
        free = _first_free(table, from_s)
        mine = sorted((t for t in taken if t.coin == coin), key=lambda t: t.decided)
        gaps = []
        for t in mine:
            gaps.append(max(0, t.decided - free))
            free = t.exit_i
        out[coin] = gaps
    return out


@dataclass
class RandomDraws:
    """Each draw's trades, and how many entries it reached against the strategy's."""

    draws: List[List[Trade]]
    wanted: int
    reached: List[int]


def random_draws(
    sim: Simulation,
    taken: Sequence[Trade],
    seed: int,
    count: int,
    from_s: Optional[int] = None,
) -> RandomDraws:
    """``count`` REF-RANDOM draws matched to ``taken`` (the strategy's path's trades),
    starting at ``from_s`` when given."""
    gaps = waits(sim, taken, from_s)
    draws: List[List[Trade]] = []
    reached: List[int] = []
    for b in range(count):
        rng = random.Random(seed + b)
        trades: List[Trade] = []
        for coin in sorted(sim.tables):
            table = sim.tables[coin]
            cursor = _first_free(table, from_s)
            for wait in _shuffled(gaps[coin], rng):
                decided = cursor + wait
                if decided > table.n - 2:
                    break
                trade = table.trade_from(decided)
                trades.append(trade)
                cursor = trade.exit_i
        draws.append(sorted(trades, key=lambda t: (t.entry_s, t.coin)))
        reached.append(len(trades))
    return RandomDraws(draws, sum(len(g) for g in gaps.values()), reached)


def replay_draws(
    sim: Simulation,
    draws: Sequence[Sequence[Trade]],
    costs: Costs,
    account: Account,
    chunk: int = 200,
) -> Paths:
    """Every draw as one path of the replay. Draws are replayed ``chunk`` at a time over
    the union of their trades, each vetoing the trades that are not its own."""
    parts: List[Paths] = []
    for a in range(0, len(draws), chunk):
        group = draws[a : a + chunk]
        union: Dict[tuple, int] = {}
        order: List[Trade] = []
        for trades in group:
            for t in trades:
                key = (t.coin, t.decided)
                if key not in union:
                    union[key] = len(order)
                    order.append(t)
        veto = np.ones((len(group), len(order)), dtype=bool)
        for p, trades in enumerate(group):
            for t in trades:
                veto[p, union[(t.coin, t.decided)]] = False
        parts.append(sim.replay(order, costs, account, veto=veto))
    return _concat(parts)


def _concat(parts: List[Paths]) -> Paths:
    if len(parts) == 1:
        return parts[0]
    arrays = {}
    for name in (
        "net",
        "capital_days",
        "trades",
        "skipped_cash",
        "skipped_minimum",
        "vetoed",
        "max_drawdown",
        "max_drawdown_usd",
        "halt_s",
        "final_equity",
        "time_in_market",
        "mean_committed",
        "peak_committed",
        "skipped_cooldown",
        "dust_usd",
        "halt_exposure",
        "halt_further_loss",
    ):
        arrays[name] = np.concatenate([getattr(p, name) for p in parts])
    return Paths(start=parts[0].start, **arrays)
