"""
Statistical power and the three verdicts (PTAI-RD-001 work package 2.3; brief section
11: "statistical power", "minimum detectable economic advantage", and "a candidate with
inadequate statistical power must be labelled INCONCLUSIVE").

For an estimate with a standard error ``se`` (for a mean of serially correlated daily
results, the long-run standard deviation over sqrt(n), not the plain one), tested
one-sided at ``alpha`` (two-sided with ``sides=2``):

* ``minimum_detectable(se, alpha, power)``: (z(1 - alpha / sides) + z(power)) x se, the
  smallest true effect the test finds with that chance. With a family of K members
  corrected by Holm, pass alpha / K (Holm's first step) for a conservative figure.
* ``power_at(effect, se, alpha)``: the chance the test finds a true ``effect``.
* ``observations_needed(effect, sd, alpha, power)``: the n at which an effect is
  detectable, with ``sd`` the standard deviation of one observation (long-run for
  correlated ones).
* ``verdict(estimate, se, p_value, alpha, smallest_effect)``: ``DETECTED`` when the
  (family-adjusted) p-value is at most alpha; ``BELOW_SMALLEST`` when it is not and the
  one-sided upper (1 - alpha) bound, estimate + z(1 - alpha) se, is below the smallest
  effect worth having (an equivalence test, not a confidence interval that happens to
  contain zero); otherwise ``INCONCLUSIVE``: the data cannot tell an effect of that
  size from none.
"""

from __future__ import annotations

import math
import statistics

_Z = statistics.NormalDist()

DETECTED = "DETECTED"
BELOW_SMALLEST = "BELOW_SMALLEST"
INCONCLUSIVE = "INCONCLUSIVE"
VERDICTS = (DETECTED, BELOW_SMALLEST, INCONCLUSIVE)


def _check(alpha: float, sides: int) -> None:
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if sides not in (1, 2):
        raise ValueError("sides must be 1 or 2")


def minimum_detectable(
    se: float, alpha: float = 0.05, power: float = 0.8, sides: int = 1
) -> float:
    """The smallest true effect found with chance ``power`` (module docstring)."""
    _check(alpha, sides)
    if not 0 < power < 1:
        raise ValueError("power must be between 0 and 1")
    return (_Z.inv_cdf(1 - alpha / sides) + _Z.inv_cdf(power)) * float(se)


def power_at(effect: float, se: float, alpha: float = 0.05, sides: int = 1) -> float:
    """The chance the test finds a true ``effect`` (both tails when two-sided)."""
    _check(alpha, sides)
    if se <= 0:
        raise ValueError("se must be positive")
    z = _Z.inv_cdf(1 - alpha / sides)
    shift = float(effect) / float(se)
    out = 1 - _Z.cdf(z - shift)
    if sides == 2:
        out += _Z.cdf(-z - shift)
    return out


def observations_needed(
    effect: float, sd: float, alpha: float = 0.05, power: float = 0.8, sides: int = 1
) -> int:
    """The fewest observations at which ``effect`` is detectable with ``power``."""
    if effect <= 0 or sd <= 0:
        raise ValueError("effect and sd must be positive")
    per_se = minimum_detectable(1.0, alpha, power, sides)
    return int(math.ceil((per_se * float(sd) / float(effect)) ** 2))


def verdict(
    estimate: float,
    se: float,
    p_value: float,
    alpha: float,
    smallest_effect: float,
) -> str:
    """DETECTED, BELOW_SMALLEST or INCONCLUSIVE (module docstring)."""
    _check(alpha, 1)
    if p_value <= alpha:
        return DETECTED
    upper = float(estimate) + _Z.inv_cdf(1 - alpha) * float(se)
    if upper < smallest_effect:
        return BELOW_SMALLEST
    return INCONCLUSIVE
