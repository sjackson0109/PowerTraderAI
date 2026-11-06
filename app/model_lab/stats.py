"""
The tests a batch's contestants pass or fail (FDS-MH-001 section 5.6).

* **p-values** against random draws (Phipson & Smyth 2010): (1 + the draws scoring at
  least the contestant's score) / (draws + 1). The lower tail counts the draws scoring
  at most it.
* **Benjamini-Hochberg** at q over a batch's K p-values: the screen, shown only.
* **Holm** at a family-wise error rate over the K p-values: valid whatever the
  dependence between contestants.
* **The smallest detectable edge**: (z at 1 - alpha/K, plus z at the power) x the
  spread of the random draws' scores. It is the edge a contestant would have had that
  chance of passing at the Holm level.
* **The probability of backtest overfitting** (Bailey et al. 2017): combinatorially
  symmetric cross-validation over S time blocks. For every way of taking half the
  blocks, the contestant that scores best on them is ranked among all K on the other
  half; PBO is the share of splits where it ranks at or below the median.
"""

from __future__ import annotations

import itertools
import math
import statistics
from typing import List, Optional, Sequence

import numpy as np


def p_upper(value: float, draws: Sequence[float]) -> float:
    n = len(draws)
    return (1 + sum(1 for d in draws if d >= value)) / (n + 1)


def p_lower(value: float, draws: Sequence[float]) -> float:
    n = len(draws)
    return (1 + sum(1 for d in draws if d <= value)) / (n + 1)


def benjamini_hochberg(ps: Sequence[float], q: float) -> List[bool]:
    """Which hypotheses Benjamini-Hochberg rejects at false discovery rate ``q``."""
    k = len(ps)
    order = sorted(range(k), key=lambda i: (ps[i], i))
    last = -1
    for rank, i in enumerate(order, start=1):
        if ps[i] <= rank * q / k:
            last = rank
    out = [False] * k
    for rank, i in enumerate(order, start=1):
        out[i] = rank <= last
    return out


def holm(ps: Sequence[float], alpha: float) -> List[bool]:
    """Which hypotheses Holm's step-down rejects at family-wise error ``alpha``."""
    k = len(ps)
    order = sorted(range(k), key=lambda i: (ps[i], i))
    out = [False] * k
    for rank, i in enumerate(order):
        if ps[i] > alpha / (k - rank):
            break
        out[i] = True
    return out


def smallest_edge(spread: float, k: int, alpha: float = 0.05, power: float = 0.8):
    z = statistics.NormalDist()
    return (z.inv_cdf(1 - alpha / max(1, int(k))) + z.inv_cdf(power)) * spread


def _rates(net: np.ndarray, held: np.ndarray) -> np.ndarray:
    """Profit over capital-days, -inf where nothing was held (no trade)."""
    out = np.full(net.shape, -np.inf)
    np.divide(net, held, out=out, where=held > 0)
    return out


def _rank(values: np.ndarray, j: int) -> float:
    """``values[j]``'s rank among ``values``, 1 the lowest, ties averaged."""
    v = values[j]
    below = float(np.sum(values < v))
    equal = float(np.sum(values == v))
    return below + (equal + 1.0) / 2.0


def pbo(block_net: Sequence[Sequence[float]], block_held: Sequence[Sequence[float]]):
    """The probability of backtest overfitting for K contestants scored on S blocks:
    ``block_net[k][s]`` and ``block_held[k][s]`` are contestant k's profit and
    capital-days on block s. None with fewer than 2 contestants or blocks."""
    net = np.asarray(block_net, dtype=float)
    held = np.asarray(block_held, dtype=float)
    if net.ndim != 2 or net.shape[0] < 2 or net.shape[1] < 2:
        return None
    k, s = net.shape
    half = s // 2
    below = 0
    splits = 0
    blocks = range(s)
    for chosen in itertools.combinations(blocks, half):
        mask = np.zeros(s, dtype=bool)
        mask[list(chosen)] = True
        inside = _rates(net[:, mask].sum(axis=1), held[:, mask].sum(axis=1))
        outside = _rates(net[:, ~mask].sum(axis=1), held[:, ~mask].sum(axis=1))
        best = int(np.argmax(inside))  # ties: the first contestant
        omega = _rank(outside, best) / (k + 1)
        if math.log(omega / (1 - omega)) <= 0:
            below += 1
        splits += 1
    return below / splits


def block_of(close_s: Sequence[int], start_s: int, end_s: int, blocks: int):
    """Each time's block: ``blocks`` equal stretches of [start_s, end_s)."""
    t = np.asarray(close_s, dtype=float)
    width = (end_s - start_s) / blocks
    return np.clip(((t - start_s) // width).astype(int), 0, blocks - 1)


def median(values: Sequence[float]) -> Optional[float]:
    return float(statistics.median(values)) if values else None
