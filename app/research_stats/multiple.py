"""
Testing many hypotheses at once (PTAI-RD-001 work package 2.3; brief section 11).

Every function takes one family's results and returns one answer per member, in the
input order.

* ``p_upper(value, draws)``: a resampling p-value that is never 0 (Phipson and Smyth
  2010): (1 + the draws at or above ``value``) / (draws + 1).
* ``holm_adjusted(ps)`` and ``holm(ps, alpha)``: Holm's step-down. It controls the
  family-wise error (the chance of any false rejection) whatever the dependence between
  members.
* ``benjamini_hochberg(ps, q)``: controls the expected share of false rejections among
  the rejections (the false discovery rate), for independent or positively dependent
  members. A screen, never a pass.
* ``romano_wolf(observed, draws)``: the Romano and Wolf (2005) step-down on bootstrap
  draws of every member's statistic, taken together. It controls the family-wise error
  as Holm does, but uses the dependence between members that the draws carry, so with
  correlated members (strategies on the same coins, variants of one rule) it rejects
  at least as often as Holm and usually more.

The lab-specific copies (``model_lab.stats``, ``signal_audit.stats``) stay as they are,
since frozen records were computed with them; the tests show these agree with them.
"""

from __future__ import annotations

from typing import List, Sequence

import numpy as np


def p_upper(value: float, draws: Sequence[float]) -> float:
    """(1 + #{draws >= value}) / (len(draws) + 1)."""
    d = np.asarray(draws, dtype=float)
    return float((1 + np.sum(d >= value)) / (len(d) + 1))


def _order(ps: Sequence[float]) -> List[int]:
    return sorted(range(len(ps)), key=lambda i: (float(ps[i]), i))


def holm_adjusted(ps: Sequence[float]) -> List[float]:
    """Holm's adjusted p-values: the i-th smallest is the largest, over j <= i, of
    min(1, (K - j + 1) p_(j)). A member is rejected at ``alpha`` when its adjusted
    p-value is at most ``alpha``."""
    k = len(ps)
    out = [1.0] * k
    running = 0.0
    for rank, i in enumerate(_order(ps)):
        running = max(running, min(1.0, (k - rank) * float(ps[i])))
        out[i] = running
    return out


def holm(ps: Sequence[float], alpha: float) -> List[bool]:
    """Which members Holm rejects at family-wise error ``alpha``."""
    return [a <= alpha for a in holm_adjusted(ps)]


def benjamini_hochberg(ps: Sequence[float], q: float) -> List[bool]:
    """Which members Benjamini-Hochberg rejects at false discovery rate ``q``: every
    member up to the largest rank r with p_(r) <= r q / K."""
    k = len(ps)
    order = _order(ps)
    last = 0
    for rank, i in enumerate(order, start=1):
        if float(ps[i]) <= rank * q / k:
            last = rank
    out = [False] * k
    for rank, i in enumerate(order, start=1):
        out[i] = rank <= last
    return out


def romano_wolf(
    observed: Sequence[float], draws: np.ndarray, centred: bool = False
) -> List[float]:
    """Romano-Wolf step-down adjusted p-values for H0: theta_k <= 0 against
    theta_k > 0, member by member.

    ``observed[k]`` is member k's statistic (larger is better; a t-statistic is best,
    since the maximum then compares like with like). ``draws[b, k]`` is its b-th
    bootstrap draw, all members from the same resample. The null distribution is that
    of the draws centred at the observed values (``centred=True`` when they already
    are).

    Members are taken from the largest statistic down; the j-th one's p-value is
    (1 + #{b : max over the members not yet taken (including it) of the centred draw
    >= its statistic}) / (B + 1), and never below the one before."""
    t = np.asarray(observed, dtype=float)
    d = np.asarray(draws, dtype=float)
    if d.ndim != 2 or d.shape[1] != len(t):
        raise ValueError("draws must be (resamples, members)")
    null = d if centred else d - t[None, :]
    b = d.shape[0]
    order = sorted(range(len(t)), key=lambda i: (-t[i], i))
    out = [1.0] * len(t)
    running = 0.0
    for j, i in enumerate(order):
        rest = order[j:]
        largest = null[:, rest].max(axis=1)
        p = (1 + np.sum(largest >= t[i])) / (b + 1)
        running = max(running, float(p))
        out[i] = running
    return out
