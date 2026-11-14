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
* **Matched holding**: random entries held for as long as the strategy's own trades, so
  entries and exits are tested together. It is reported only (the owner's decision of
  2026-11-13): no pass/fail rule, verdict or registered experiment reads it.

  A trade's hold is its bars from the entry fill's bar to the exit fill (``held_bars``;
  a trade closed at the end of the data holds the last bar too). For each of the
  strategy's trades, a draw places one on the same coin, held for the same number of
  bars, from an entry bar drawn uniformly among those whose decision bar is in the
  window (REF-RANDOM's: ``_first_free``) and for which the coin has bars for the whole
  hold. It exits at the open after the hold, or at the last close when the hold ends
  with the data. No two trades of a draw share a bar of one coin (from the entry's bar
  to the exit's), so each enters after the bar its coin's last exit filled on, as the
  strategy's own trades do; a placement that would share one is drawn again, up to
  ``TRIES`` times, and a trade that still has no place is dropped and counted. Each
  coin's longer holds are placed first. Draw b uses ``random.Random(seed + b)`` and
  only its ``random()``, as REF-RANDOM's draws do.
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


TRIES = 100  # placements drawn for one matched hold before it is dropped


def held_bars(trade: Trade) -> int:
    """The bars ``trade`` was held: from its entry fill's bar to its exit fill (a trade
    closed at the end of the data holds the last bar too)."""
    return trade.exit_i - trade.entry_i + (1 if trade.forced else 0)


def _held_trade(table, opens_s: np.ndarray, entry: int, exit_i: int, forced: bool):
    """The trade ``table._trade`` makes for a matched hold, built from the bars' open
    times in seconds: a run's draws make tens of thousands, too many for pandas
    lookups each (the tests check every one against ``_trade``)."""
    return Trade(
        coin=table.coin,
        decided=entry - 1,
        entry_i=entry,
        exit_i=exit_i,
        entry_s=int(opens_s[entry]),
        exit_s=int(opens_s[exit_i]) + (table.spec.bar_seconds if forced else 0),
        entry_price=float(table._open[entry]),
        exit_price=float(table._close[exit_i] if forced else table._open[exit_i]),
        exit_rule="matched_holding",
        forced=forced,
    )


@dataclass
class MatchedDraws:
    """Each draw's trades, and how many of the strategy's trades it could not place."""

    draws: List[List[Trade]]
    wanted: int
    dropped: List[int]


def matched_draws(
    sim: Simulation,
    taken: Sequence[Trade],
    seed: int,
    count: int,
    from_s: Optional[int] = None,
    tries: int = TRIES,
) -> MatchedDraws:
    """``count`` matched-holding draws for ``taken`` (the strategy's path's trades),
    deciding at or after ``from_s`` when given (see the module docstring)."""
    holds: Dict[str, List[int]] = {}
    for t in taken:
        holds.setdefault(t.coin, []).append(held_bars(t))
    coins = []  # each coin's table, first entry bar and bar open times, once
    for coin in sorted(sim.tables):
        table = sim.tables[coin]
        opens = table.candles["open_time"].map(lambda t: int(t.timestamp()))
        coins.append((coin, table, _first_free(table, from_s) + 1, opens.to_numpy()))
    draws: List[List[Trade]] = []
    dropped: List[int] = []
    for b in range(count):
        rng = random.Random(seed + b)
        trades: List[Trade] = []
        missed = 0
        for coin, table, first, opens_s in coins:
            busy = np.zeros(table.n, dtype=bool)  # bars this draw holds on the coin
            for bars in sorted(holds.get(coin, ()), reverse=True):
                last = table.n - bars  # the last entry with bars for the whole hold
                entry = None
                if last >= first:
                    for _ in range(tries):
                        e = first + int(rng.random() * (last - first + 1))
                        if not busy[e : e + bars + 1].any():  # its bars and exit's
                            entry = e
                            break
                if entry is None:
                    missed += 1
                    continue
                forced = entry + bars == table.n  # held to the last close
                exit_i = table.n - 1 if forced else entry + bars
                busy[entry : exit_i + 1] = True
                trades.append(_held_trade(table, opens_s, entry, exit_i, forced))
        draws.append(sorted(trades, key=lambda t: (t.entry_s, t.coin)))
        dropped.append(missed)
    return MatchedDraws(draws, sum(len(h) for h in holds.values()), dropped)


def replay_draws(
    sim: Simulation,
    draws: Sequence[Sequence[Trade]],
    costs: Costs,
    account: Account,
    chunk: int = 200,
    policy=None,
) -> Paths:
    """Every draw as one path of the replay. Draws are replayed ``chunk`` at a time over
    the union of their trades, each vetoing the trades that are not its own. With a
    sizing ``policy`` (``strategy_lab.sizing``) each trade is sized as the strategy's
    own trades are, at its own decision."""
    parts: List[Paths] = []
    for a in range(0, len(draws), chunk):
        group = draws[a : a + chunk]
        # each distinct trade once: a random entry from a bar is always the same
        # trade, but matched holds decided on one bar can differ in length
        union: Dict[Trade, int] = {}
        order: List[Trade] = []
        for trades in group:
            for t in trades:
                if t not in union:
                    union[t] = len(order)
                    order.append(t)
        veto = np.ones((len(group), len(order)), dtype=bool)
        for p, trades in enumerate(group):
            for t in trades:
                veto[p, union[t]] = False
        kw = {}
        if policy is not None:
            scale = policy.scales(sim, order).scale
            kw["scale"] = np.tile(scale, (len(group), 1))
        parts.append(sim.replay(order, costs, account, veto=veto, **kw))
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
    for name in (  # the intrabar figures: None unless every part has them
        "intrabar_max_drawdown",
        "intrabar_max_drawdown_usd",
        "intrabar_halt_s",
    ):
        got = [getattr(p, name) for p in parts]
        arrays[name] = None if any(g is None for g in got) else np.concatenate(got)
    return Paths(start=parts[0].start, **arrays)
