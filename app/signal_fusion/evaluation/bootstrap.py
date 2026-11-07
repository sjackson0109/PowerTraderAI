"""
The block bootstrap every FDS-SIG-004 test uses (section 6.0).

* **Unit:** the UTC calendar day. A forecast row belongs to its hour's day; a trade to its
  entry's day, with all of its profit and capital-days.
* **Blocks:** circular blocks of L = 28 days (Politis and Romano 1992). A draw takes
  ceil(N / L) blocks, each starting on a day drawn uniformly from the N days of the scored
  period and wrapping round its end; they are joined and cut to N days. The wrap only
  resamples days of rows already scored; it never moves a feature or a label in time.
* **Long trades:** when more than 1% of a family's scored trades last longer than 14 days,
  L = 56 days for every test in that family (``block_length``).
* **All coins together:** every coin's rows on a day move together.
* **Pairs:** every statistic of one test is computed from the same days in each draw, so
  the members of a pair, and the placebo, always share their days.
* **Statistics** are functions of per-day sums (``DaySums``): a mean is a sum over a
  count, a return per capital-day a profit over capital-days, and so on.
* **p-value** for H0: theta <= 0 against theta > 0: (1 + #{b : theta*_b - theta_hat >=
  theta_hat}) / (B + 1), the centred bootstrap (Hall and Wilson 1991).
* **Runs:** 10 runs of 1,000 draws, run r seeded ``seed + r``; draws use ``random()``
  alone, so a seed repeats exactly across Python versions. The deciding p-value pools all
  10,000 draws; each run's p is shown beside it, with the largest minus the smallest.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

DAY_S = 86400
BLOCK_DAYS = 28
LONG_TRADE_DAYS = 14
LONG_SHARE = 0.01
RUNS = 10
DRAWS_PER_RUN = 1000


def block_length(trade_days: Optional[Sequence[float]] = None) -> int:
    """28 days, or 56 when more than 1% of the family's trades last longer than 14."""
    if trade_days is None or not len(trade_days):
        return BLOCK_DAYS
    long = np.mean(np.asarray(trade_days, dtype=float) > LONG_TRADE_DAYS)
    return 2 * BLOCK_DAYS if long > LONG_SHARE else BLOCK_DAYS


@dataclass(frozen=True, eq=False)
class DaySums:
    """Per-day sums of the columns a test needs, over the scored period's N days."""

    first_day: int  # the period's first UTC day number
    sums: np.ndarray  # (N, m)

    @property
    def days(self) -> int:
        return int(self.sums.shape[0])

    def total(self) -> np.ndarray:
        return self.sums.sum(axis=0)


def day_sums(times_s, columns, first_s: Optional[int] = None, last_s=None) -> DaySums:
    """Per-day sums of ``columns`` (each a sequence the length of ``times_s``) by the UTC
    day of each time. The period runs from ``first_s``'s day (default the first time's) to
    ``last_s``'s (default the last time's)."""
    t = np.asarray(times_s, dtype=np.int64)
    values = np.column_stack([np.asarray(c, dtype=float) for c in columns])
    day = t // DAY_S
    first = int(day.min() if first_s is None else int(first_s) // DAY_S)
    last = int(day.max() if last_s is None else int(last_s) // DAY_S)
    n = last - first + 1
    out = np.zeros((n, values.shape[1]))
    np.add.at(out, day - first, values)
    return DaySums(first, out)


class Bootstrap:
    """Circular block draws of N days, in runs (the module docstring)."""

    def __init__(
        self,
        days: int,
        seed: int,
        block: int = BLOCK_DAYS,
        runs: int = RUNS,
        per_run: int = DRAWS_PER_RUN,
    ):
        if days <= 0:
            raise ValueError("a bootstrap needs at least one day")
        self.days = int(days)
        self.block = int(block)
        self.seed = int(seed)
        self.runs = int(runs)
        self.per_run = int(per_run)
        self.blocks = math.ceil(self.days / self.block)
        self.last_len = self.days - (self.blocks - 1) * self.block

    def starts(self, run: int) -> np.ndarray:
        """Run ``run``'s block start days: (per_run, blocks)."""
        rng = random.Random(self.seed + run)
        n = self.per_run * self.blocks
        flat = [int(rng.random() * self.days) for _ in range(n)]
        return np.array(flat, dtype=np.int64).reshape(self.per_run, self.blocks)

    def day_counts(self, run: int) -> np.ndarray:
        """How often each day is drawn, per draw: (per_run, N)."""
        out = np.zeros((self.per_run, self.days))
        starts = self.starts(run)
        for j in range(self.blocks):
            length = self.block if j < self.blocks - 1 else self.last_len
            for k in range(length):
                np.add.at(
                    out, (np.arange(self.per_run), (starts[:, j] + k) % self.days), 1.0
                )
        return out

    def resampled(self, sums: DaySums, run: int) -> np.ndarray:
        """Each draw's summed columns: (per_run, m)."""
        if sums.days != self.days:
            raise ValueError("the sums cover a different period")
        ext = np.vstack([sums.sums, sums.sums])
        cum = np.vstack([np.zeros((1, ext.shape[1])), np.cumsum(ext, axis=0)])
        starts = self.starts(run)
        lengths = np.full(self.blocks, self.block)
        lengths[-1] = self.last_len
        total = np.zeros((self.per_run, sums.sums.shape[1]))
        for j in range(self.blocks):
            s = starts[:, j]
            total += cum[s + lengths[j]] - cum[s]
        return total

    def draws(self, sums: DaySums, statistic: Callable[[np.ndarray], np.ndarray]):
        """theta* per draw, per run: (runs, per_run). ``statistic`` maps summed columns
        (k, m) to k values."""
        return np.vstack([statistic(self.resampled(sums, r)) for r in range(self.runs)])


def centred_p(theta_hat: float, draws: np.ndarray) -> float:
    d = np.asarray(draws, dtype=float).ravel()
    d = d[np.isfinite(d)]
    if not np.isfinite(theta_hat) or not len(d):
        return 1.0
    return float((1 + np.sum(d - theta_hat >= theta_hat)) / (len(d) + 1))


def ten_runs(theta_hat: float, draws: np.ndarray) -> Dict[str, object]:
    """The pooled p and each run's p (the module docstring)."""
    per_run = [centred_p(theta_hat, row) for row in np.atleast_2d(draws)]
    return {
        "p": centred_p(theta_hat, draws),
        "runs": per_run,
        "spread": max(per_run) - min(per_run),
    }


def interval(draws: np.ndarray, level: float = 0.90) -> List[float]:
    d = np.asarray(draws, dtype=float).ravel()
    d = d[np.isfinite(d)]
    if not len(d):
        return [float("nan"), float("nan")]
    lo, hi = np.percentile(d, [50 * (1 - level), 100 - 50 * (1 - level)])
    return [float(lo), float(hi)]


def lower_bound(draws: np.ndarray, level: float = 0.95) -> float:
    """The one-sided ``level`` lower bound."""
    d = np.asarray(draws, dtype=float).ravel()
    d = d[np.isfinite(d)]
    return float(np.percentile(d, 100 * (1 - level))) if len(d) else float("nan")


def test_statistic(
    sums: DaySums,
    statistic: Callable[[np.ndarray], np.ndarray],
    seed: int,
    block: int = BLOCK_DAYS,
    level: float = 0.90,
) -> Dict[str, object]:
    """theta_hat, its one-sided p-value with H0: theta <= 0 (pooled and per run), and its
    percentile interval."""
    theta = float(statistic(sums.total()[None, :])[0])
    boot = Bootstrap(sums.days, seed, block)
    draws = boot.draws(sums, statistic)
    return {
        "theta": theta,
        **ten_runs(theta, draws),
        "interval": interval(draws, level),
        "lower_95": lower_bound(draws, 0.95),
        "draws": int(draws.size),
        "block_days": int(block),
        "days": sums.days,
        "seed": int(seed),
    }


# common statistics on per-day sums ---------------------------------------------------------


def mean_of(col_sum: int = 0, col_count: int = 1):
    """sum / count."""

    def f(x: np.ndarray) -> np.ndarray:
        with np.errstate(invalid="ignore", divide="ignore"):
            return x[:, col_sum] / x[:, col_count]

    return f


def ratio_difference(a_num=0, a_den=1, b_num=2, b_den=3):
    """a_num / a_den - b_num / b_den (for example, one path's return per capital-day minus
    another's). A path with no capital-days scores 0."""

    def f(x: np.ndarray) -> np.ndarray:
        with np.errstate(invalid="ignore", divide="ignore"):
            a = np.where(x[:, a_den] > 0, x[:, a_num] / x[:, a_den], 0.0)
            b = np.where(x[:, b_den] > 0, x[:, b_num] / x[:, b_den], 0.0)
        return a - b

    return f


def ratio(num=0, den=1):
    def f(x: np.ndarray) -> np.ndarray:
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(x[:, den] > 0, x[:, num] / x[:, den], 0.0)

    return f


def skill(model=0, reference=1):
    """1 - model / reference (a Brier skill score from summed Brier scores)."""

    def f(x: np.ndarray) -> np.ndarray:
        with np.errstate(invalid="ignore", divide="ignore"):
            return 1.0 - x[:, model] / x[:, reference]

    return f
