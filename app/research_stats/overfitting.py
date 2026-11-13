"""
How much a best-of-many backtest can be trusted (PTAI-RD-001 work package 2.3; brief
section 11, "repeated parameter searches" and "backtest overfitting").

**The deflated Sharpe ratio** (Bailey and Lopez de Prado 2014). The best of N trials
has a high Sharpe ratio even when none has skill. ``deflated_sharpe`` is the chance
that the chosen trial's true Sharpe ratio is above what the best of N skill-less trials
would show:

* ``probabilistic_sharpe(sr, n, skew, kurtosis, benchmark)``: Phi((SR - SR*) sqrt(n - 1)
  / sqrt(1 - skew SR + (kurtosis - 1) / 4 SR^2)), the chance the true ratio exceeds
  SR*, allowing for the returns' skew and fat tails;
* ``expected_max_sharpe(variance, trials)``: SR0 = sqrt(V) ((1 - g) Phi^-1(1 - 1/N) +
  g Phi^-1(1 - 1/(N e))), g the Euler-Mascheroni constant: the expected best of N
  skill-less ratios whose spread across trials is V;
* ``deflated_sharpe(returns, trial_sharpes)``: PSR at SR* = SR0, with V and N from every
  trial's ratio (all of them, kept in the trial ledger, not only the survivors).

Sharpe ratios here are per observation (per day for daily returns), never annualised.

**The probability of backtest overfitting** (Bailey, Borwein, Lopez de Prado and Zhu
2017), by combinatorially symmetric cross-validation: ``pbo(block_values)`` with K
members scored on S time blocks. For every way of taking half the blocks, the member
best on them is ranked among all K on the other half; PBO is the share of splits where
it ranks at or below the median (the logit of its relative rank is at most 0). Near 0.5
for members without skill; near 0 when the best in-sample is reliably good out of
sample. With ``block_weights`` a set of blocks scores sum(values) / sum(weights) (profit
over capital-days, as ``model_lab.stats.pbo``), minus infinity where the weights are 0.
"""

from __future__ import annotations

import itertools
import math
import statistics
from typing import Optional, Sequence

import numpy as np

EULER_GAMMA = 0.5772156649015329
_Z = statistics.NormalDist()


def sharpe(returns: Sequence[float]) -> Optional[float]:
    """Mean over standard deviation (n - 1), per observation; None without spread."""
    x = np.asarray(returns, dtype=float)
    if len(x) < 2:
        return None
    sd = float(np.std(x, ddof=1))
    return float(np.mean(x)) / sd if sd > 0 else None


def moments(returns: Sequence[float]):
    """(skewness, kurtosis), kurtosis not in excess (3 for a normal series)."""
    x = np.asarray(returns, dtype=float)
    centred = x - x.mean()
    var = float(np.mean(centred**2))
    if var <= 0:
        return 0.0, 3.0
    return (
        float(np.mean(centred**3)) / var**1.5,
        float(np.mean(centred**4)) / var**2,
    )


def probabilistic_sharpe(
    sr: float,
    n: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    benchmark: float = 0.0,
) -> float:
    """The chance the true per-observation Sharpe ratio exceeds ``benchmark``."""
    if n < 2:
        raise ValueError("needs at least 2 observations")
    spread = 1.0 - skew * sr + (kurtosis - 1.0) / 4.0 * sr**2
    if spread <= 0:
        raise ValueError("skew and kurtosis leave no spread")
    return _Z.cdf((sr - benchmark) * math.sqrt(n - 1) / math.sqrt(spread))


def expected_max_sharpe(variance: float, trials: int) -> float:
    """SR0: the expected largest of ``trials`` skill-less Sharpe ratios whose variance
    across trials is ``variance`` (0 for one trial)."""
    if trials < 1:
        raise ValueError("trials must be at least 1")
    if trials == 1 or variance <= 0:
        return 0.0
    n = float(trials)
    return math.sqrt(variance) * (
        (1.0 - EULER_GAMMA) * _Z.inv_cdf(1.0 - 1.0 / n)
        + EULER_GAMMA * _Z.inv_cdf(1.0 - 1.0 / (n * math.e))
    )


def deflated_sharpe(
    returns: Sequence[float], trial_sharpes: Sequence[float]
) -> Optional[float]:
    """The deflated Sharpe ratio of the chosen trial's ``returns``, given every trial's
    Sharpe ratio (the chosen one included). None when its ratio is undefined."""
    sr = sharpe(returns)
    if sr is None:
        return None
    trials = np.asarray(trial_sharpes, dtype=float)
    variance = float(np.var(trials, ddof=1)) if len(trials) > 1 else 0.0
    skew, kurt = moments(returns)
    return probabilistic_sharpe(
        sr, len(returns), skew, kurt, expected_max_sharpe(variance, len(trials))
    )


def _relative_rank(values: np.ndarray, j: int) -> float:
    """``values[j]``'s rank among them, 1 the lowest, ties averaged."""
    v = values[j]
    below = float(np.sum(values < v))
    equal = float(np.sum(values == v))
    return below + (equal + 1.0) / 2.0


def _score(values: np.ndarray, weights: Optional[np.ndarray], mask) -> np.ndarray:
    total = values[:, mask].sum(axis=1)
    if weights is None:
        return total
    held = weights[:, mask].sum(axis=1)
    out = np.full(total.shape, -np.inf)
    np.divide(total, held, out=out, where=held > 0)
    return out


def pbo(
    block_values: Sequence[Sequence[float]],
    block_weights: Optional[Sequence[Sequence[float]]] = None,
) -> Optional[float]:
    """The probability of backtest overfitting of K members scored on S blocks
    (``block_values[k][s]``); see the module docstring. None with fewer than 2 members
    or 2 blocks. An odd S leaves the last block out of every split's halves' balance:
    half is S // 2 blocks, the rest is the other side."""
    values = np.asarray(block_values, dtype=float)
    weights = None if block_weights is None else np.asarray(block_weights, dtype=float)
    if values.ndim != 2 or values.shape[0] < 2 or values.shape[1] < 2:
        return None
    if weights is not None and weights.shape != values.shape:
        raise ValueError("block_weights must match block_values")
    k, s = values.shape
    below = splits = 0
    for chosen in itertools.combinations(range(s), s // 2):
        mask = np.zeros(s, dtype=bool)
        mask[list(chosen)] = True
        best = int(np.argmax(_score(values, weights, mask)))  # ties: the first
        omega = _relative_rank(_score(values, weights, ~mask), best) / (k + 1)
        if math.log(omega / (1.0 - omega)) <= 0:
            below += 1
        splits += 1
    return below / splits
