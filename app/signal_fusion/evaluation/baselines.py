"""
Random baselines for filters and sizing (FDS-SIG-004 sections 6.1 and 6.3).

**R3, a random veto that keeps the trader's constraints.** For each coin c, k_c is the
number of opportunities the filter vetoed among its assessable, eligible opportunities on
that coin (eligible: the coin was flat and the cash was there, in the filter's own path).
Each R3 draw vetoes k_c of that coin's assessable, eligible opportunities, chosen
uniformly without replacement. Each draw is replayed through the same portfolio replay
(``replay``); an opportunity that turns ineligible in a draw's own path is skipped there
and counted. An unstratified R3 (k = the total, drawn over every coin) is shown beside it.

**R3s, random sizing.** Each draw gives the scales realised at the assessable
opportunities to those same opportunities in a random order, pooled over coins; a shuffle
within each coin is shown beside it. Because R3s uses the same scales, it separates where
the shrink falls from how much it shrinks on average.

Draws come in runs: run r uses ``random.Random(seed + r)`` and its ``random()`` alone, so a
seed repeats exactly across Python versions.
"""

from __future__ import annotations

import random
from typing import Dict, List, Sequence

import numpy as np


def _choose(rng: random.Random, items: List[int], k: int) -> List[int]:
    """k of ``items`` uniformly without replacement (a partial Fisher-Yates shuffle)."""
    pool = list(items)
    m = len(pool)
    k = min(k, m)
    for i in range(k):
        j = i + int(rng.random() * (m - i))
        pool[i], pool[j] = pool[j], pool[i]
    return pool[:k]


def _shuffle(rng: random.Random, values: List[float]) -> List[float]:
    out = list(values)
    for i in range(len(out) - 1, 0, -1):
        j = int(rng.random() * (i + 1))
        out[i], out[j] = out[j], out[i]
    return out


def veto_counts(
    coins: Sequence[str], candidates: Sequence[int], vetoed: Sequence[int]
) -> Dict[str, int]:
    """k_c: per coin, the filter's vetoes among its candidates (assessable, eligible)."""
    pool = set(candidates)
    out: Dict[str, int] = {}
    for i in vetoed:
        if i in pool:
            out[coins[i]] = out.get(coins[i], 0) + 1
    return out


def r3(
    coins: Sequence[str],
    candidates: Sequence[int],
    counts: Dict[str, int],
    n: int,
    seed: int,
    run: int,
    draws: int,
    stratified: bool = True,
) -> np.ndarray:
    """One run of R3: (draws, n) True where a draw vetoes an opportunity."""
    rng = random.Random(int(seed) + int(run))
    out = np.zeros((draws, n), dtype=bool)
    by_coin: Dict[str, List[int]] = {}
    for i in candidates:
        by_coin.setdefault(coins[i], []).append(i)
    total = sum(counts.values())
    every = sorted(candidates)
    for b in range(draws):
        if stratified:
            for c in sorted(by_coin):
                k = counts.get(c, 0)
                if k:
                    out[b, _choose(rng, by_coin[c], k)] = True
        elif total:
            out[b, _choose(rng, every, total)] = True
    return out


def r3s(
    coins: Sequence[str],
    candidates: Sequence[int],
    scales: Sequence[float],
    n: int,
    seed: int,
    run: int,
    draws: int,
    within_coin: bool = False,
) -> np.ndarray:
    """One run of R3s: (draws, n) scales, the candidates' own scales in a random order
    (1 elsewhere)."""
    rng = random.Random(int(seed) + int(run))
    out = np.ones((draws, n))
    cand = list(candidates)
    values = [float(scales[i]) for i in cand]
    groups: Dict[str, List[int]] = {}
    for k, i in enumerate(cand):
        groups.setdefault(coins[i], []).append(k)
    for b in range(draws):
        if within_coin:
            for c in sorted(groups):
                ks = groups[c]
                mixed = _shuffle(rng, [values[k] for k in ks])
                for k, v in zip(ks, mixed):
                    out[b, cand[k]] = v
        else:
            mixed = _shuffle(rng, values)
            out[b, cand] = mixed
    return out


def upper_p(value: float, draws: np.ndarray) -> float:
    """(1 + #{draw >= value}) / (B + 1): how often random does at least as well."""
    d = np.asarray(draws, dtype=float).ravel()
    return float((1 + np.sum(d >= value)) / (len(d) + 1))


def lower_p(value: float, draws: np.ndarray) -> float:
    """(1 + #{draw <= value}) / (B + 1): how often random does at most this (a lower
    drawdown is better)."""
    d = np.asarray(draws, dtype=float).ravel()
    return float((1 + np.sum(d <= value)) / (len(d) + 1))
