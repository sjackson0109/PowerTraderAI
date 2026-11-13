"""
Resampling for strategies that hold positions for weeks (PTAI-RD-001 work package 1.11;
defect register N19).

**The problem.** E1's long-holding test booked each trade's whole net on its entry day,
and chose the block length by rule (L = 28 x 2^k days, with at most 1% of trades longer
than L/2). With STRAT-004's holds that gave 896-day blocks, 1.8 blocks in the period, so
its p-values carried no information.

**This module:**
* **Marks every day held** (``daily_marks``). The unit is the UTC day. Each day carries
  the strategy's marked profit or loss that day and the capital it had in the market, so
  a trade held 60 days contributes to each of its days, and its days sum to its net.
* **Draws days with the stationary bootstrap** (Politis and Romano 1994): blocks of
  random length, geometric with mean ``L``, wrapping round the period's end.
* **Chooses L from the data** (``optimal_block_length``; Politis and White 2004, with
  the correction of Patton, Politis and White 2009), on the marked daily series, capped
  at min(3 sqrt(N), N/3).
* **Tests return per capital-day**, theta = sum(pnl) / sum(capital), for H0: theta <= 0
  against theta > 0, by one of two methods (``rpcd_test``):

  - ``"percentile"``: the centred p-value of the existing bootstrap
    (``signal_fusion.evaluation.bootstrap``): (1 + #{b : theta*_b - theta_hat >=
    theta_hat}) / (B + 1), with a percentile interval.
  - ``"studentised"`` (bootstrap-t): the same, on t = theta / se, with a Bartlett-kernel
    standard error computed the same way on the original and on every resample.

**The default (O3 calibration, 2026-11-12;
``docs/dev/ptai-rd-001/O3-bootstrap-calibration.md``)** is ``"studentised"`` with the
chosen block length x1.5 (variant D). The rule, declared in the calibration brief
before the run, was:
worst null size at nominal 5% at most 6.0% across every null scenario and both lengths,
then the most power. No variant met 6.0%; the rule then takes the lowest worst-case
size, which was D's: 6.2% (AR(0.4) with Student-t(3) shocks, 750 days; 1000
replications, so about 0.75 points of Monte Carlo error). The percentile method at x1.0
(PR #266's) reached 7.5% (AR(0.7), 750 days). D costs about 1.6 points of mean power.
Synthetic series only.

It is a library, and nothing existing calls it. A declared evaluation that uses it names
the method and block scale in its registration, which the owner approves.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Tuple

import numpy as np

DAY_S = 86_400


@dataclass(frozen=True)
class DailyMarks:
    """Per UTC day from ``first_day``: marked profit or loss, and capital in the market."""

    first_day: int
    pnl: np.ndarray
    capital: np.ndarray

    @property
    def days(self) -> int:
        return int(len(self.pnl))

    def rpcd(self) -> float:
        """Return per capital-day: total profit over total capital-days (nan without capital)."""
        cap = float(np.sum(self.capital))
        return float(np.sum(self.pnl)) / cap if cap > 0 else float("nan")


def daily_marks(
    trades: Iterable[Mapping],
    closes: Mapping[str, Mapping[int, float]],
    first_day: int,
    days: int,
) -> DailyMarks:
    """Mark every trade at each UTC day's close while it is held.

    ``trades``: each with ``coin``, ``entry_s``, ``exit_s``, ``amount`` (USD committed),
    ``entry_price`` and ``net`` (USD after every cost). ``closes``: per coin, each UTC
    day number's close. The position is ``amount / entry_price`` units. Its value at the
    close of each day from the entry day up to the day before the exit day is marked; the
    exit day takes the rest, so the trade's days sum to ``net`` exactly, with its costs
    in the first and last steps. A day with no close keeps the last value. Capital is the
    amount committed, on every day from the entry day to the exit day."""
    pnl = np.zeros(days, dtype=float)
    capital = np.zeros(days, dtype=float)
    for t in trades:
        d0 = int(t["entry_s"]) // DAY_S
        d1 = max(d0, (int(t["exit_s"]) - 1) // DAY_S)
        amount = float(t["amount"])
        units = amount / float(t["entry_price"])
        coin_closes = closes.get(t["coin"], {})
        value = amount
        for d in range(d0, d1 + 1):
            i = d - first_day
            if d < d1:
                close = coin_closes.get(d)
                new = units * float(close) if close is not None else value
            else:
                new = amount + float(t["net"])
            if 0 <= i < days:
                pnl[i] += new - value
                capital[i] += amount
            value = new
    return DailyMarks(int(first_day), pnl, capital)


def _flat_top(t: float) -> float:
    t = abs(t)
    if t <= 0.5:
        return 1.0
    if t <= 1.0:
        return 2.0 * (1.0 - t)
    return 0.0


def block_cap(n: int) -> float:
    """The largest mean block length used for ``n`` days: ceil(min(3 sqrt(N), N/3)), at
    least 1."""
    return max(1.0, float(math.ceil(min(3.0 * math.sqrt(n), n / 3.0))))


def optimal_block_length(x: Iterable[float]) -> float:
    """The stationary bootstrap's mean block length for series ``x`` (Politis and White
    2004, corrected by Patton, Politis and White 2009), at least 1 and at most
    min(3 sqrt(N), N/3).

    m_hat is the smallest lag after which ``K_N = max(5, ceil(log10 N))`` autocorrelations
    in a row are all within 2 sqrt(log10(N) / N); M = 2 m_hat. Then, with the flat-top
    window lambda: G = sum_{|k|<=M} lambda(k/M) |k| R(k), g = sum_{|k|<=M} lambda(k/M)
    R(k), and b = (2 G^2 / (2 g^2))^(1/3) N^(1/3)."""
    x = np.asarray(list(x), dtype=float)
    n = len(x)
    if n < 10:
        return 1.0
    e = x - x.mean()
    acv0 = float(e @ e) / n
    b_max = block_cap(n)
    if acv0 <= 0:
        return 1.0
    kn = max(5, int(math.ceil(math.log10(n))))
    m_max = int(math.ceil(math.sqrt(n))) + kn
    acv = np.array([float(e[: n - k] @ e[k:]) / n for k in range(m_max + kn + 1)])
    rho = acv / acv0
    limit = 2.0 * math.sqrt(math.log10(n) / n)
    m_hat = None
    for m in range(0, m_max + 1):
        if np.all(np.abs(rho[m + 1 : m + kn + 1]) < limit):
            m_hat = m
            break
    big_m = min(2 * max(m_hat, 1), m_max) if m_hat is not None else m_max
    g_sum, lr = 0.0, acv[0]
    for k in range(1, big_m + 1):
        lam = _flat_top(k / big_m)
        g_sum += 2.0 * lam * k * acv[k]
        lr += 2.0 * lam * acv[k]
    if lr <= 0 or g_sum == 0:
        return 1.0
    b = (2.0 * g_sum**2 / (2.0 * lr**2)) ** (1.0 / 3.0) * n ** (1.0 / 3.0)
    return float(min(max(b, 1.0), b_max))


def stationary_indices(
    n: int, mean_block: float, draws: int, rng: np.random.Generator
) -> np.ndarray:
    """``draws`` rows of ``n`` day indices: each draw starts on a uniform day and goes on
    to the next day (wrapping round the end), or with probability 1 / ``mean_block``
    jumps to a new uniform day (Politis and Romano 1994)."""
    p = 1.0 / max(1.0, float(mean_block))
    idx = np.empty((draws, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, draws)
    jump = rng.random((draws, n)) < p
    starts = rng.integers(0, n, (draws, n))
    for t in range(1, n):
        idx[:, t] = np.where(jump[:, t], starts[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def bartlett_lrv(z: np.ndarray, bandwidth: float) -> np.ndarray:
    """The Bartlett-kernel (Newey and West 1987) long-run variance of each row of ``z``:
    R(0) + 2 sum_k (1 - k / bandwidth) R(k) over 0 < k < bandwidth, with R(k) =
    sum_t z_t z_{t+k} / N. The rows must already be centred. Never negative."""
    z = np.atleast_2d(np.asarray(z, dtype=float))
    n = z.shape[1]
    bw = max(1.0, float(bandwidth))
    out = np.einsum("ij,ij->i", z, z) / n
    for k in range(1, min(n - 1, int(math.ceil(bw)) - 1) + 1):
        w = 1.0 - k / bw
        if w <= 0.0:
            break
        out = out + 2.0 * w * np.einsum("ij,ij->i", z[:, k:], z[:, :-k]) / n
    return out


METHODS = ("percentile", "studentised")
# Variant D of the O3 calibration (module docstring): the lowest worst-case null size.
DEFAULT_METHOD = "studentised"
DEFAULT_BLOCK_SCALE = 1.5


@dataclass(frozen=True)
class Result:
    theta: float  # return per capital-day
    p_value: float  # H0: theta <= 0
    # at ``level``: the percentile interval, or the bootstrap-t one (studentised)
    interval: Tuple[float, float]
    level: float
    mean_block: float  # the mean block length used (after ``block_scale`` and the cap)
    draws: int
    days: int
    method: str = "percentile"


def rpcd_test(
    marks: DailyMarks,
    draws: int = 2000,
    seed: int = 0,
    mean_block: Optional[float] = None,
    level: float = 0.95,
    method: str = DEFAULT_METHOD,
    block_scale: float = DEFAULT_BLOCK_SCALE,
) -> Result:
    """The stationary-bootstrap test of return per capital-day (module docstring).

    The default is the O3 calibration's choice, ``method="studentised",
    block_scale=1.5``: its worst null size was 6.2% at nominal 5%, the lowest of the four
    variants measured, though above the 6.0% the declared rule asked for. PR #266's method
    is ``method="percentile", block_scale=1.0`` (worst 7.5%).

    The mean block length is chosen from the marked daily profit or loss and multiplied
    by ``block_scale``, then capped at min(3 sqrt(N), N/3) days; a ``mean_block`` given
    is used as it is. The studentised method's Bartlett bandwidth is that same length.

    ``method="percentile"``: theta_hat against the centred bootstrap draws,
    p = (1 + #{theta*_b - theta_hat >= theta_hat}) / (B + 1), with a percentile interval.

    ``method="studentised"`` (bootstrap-t): t = theta_hat / se and, on each resample,
    t*_b = (theta*_b - theta_hat) / se*_b; p = (1 + #{t*_b >= t}) / (B + 1), with the
    bootstrap-t interval. se comes from the linearised ratio, z_t = pnl_t - theta_hat
    capital_t, as se^2 = N V(z) / (sum capital)^2, with V the Bartlett-kernel long-run
    variance whose bandwidth is the mean block length (``bartlett_lrv``). se*_b is the same
    formula on resample b, with theta*_b in place of theta_hat. Using the same formula on
    the original and on each resample is the "naive" block bootstrap of a HAC t statistic:
    Goncalves and Vogelsang (2011) show, for the moving-block bootstrap, that it
    reproduces the statistic's fixed-bandwidth distribution, including the kernel
    estimate's downward bias, which a normal critical value ignores. It is a
    dependence-robust studentisation in the sense of Goetze and Kuensch (1996) and Lahiri
    (2003), but not their matched-variance form, whose observed t keeps the block
    variance's bias."""
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}, not {method!r}")
    n = marks.days
    if n < 2 or not np.sum(marks.capital) > 0:
        raise ValueError("the test needs at least two days with capital in the market")
    theta = marks.rpcd()
    if mean_block:
        block = float(mean_block)
    else:
        block = optimal_block_length(marks.pnl) * float(block_scale)
        block = max(1.0, min(block, block_cap(n)))
    idx = stationary_indices(n, block, int(draws), np.random.default_rng(seed))
    pnl_r = marks.pnl[idx]
    cap_r = marks.capital[idx]
    pnl_b = pnl_r.sum(axis=1)
    cap_b = cap_r.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        stars = np.where(cap_b > 0, pnl_b / cap_b, np.nan)
    tail = (1.0 - level) / 2.0
    if method == "percentile":
        stars = stars[np.isfinite(stars)]
        b = len(stars)
        p = (1 + int(np.sum(stars - theta >= theta))) / (b + 1)
        lo, hi = np.quantile(stars, [tail, 1.0 - tail]) if b else (np.nan, np.nan)
        return Result(theta, float(p), (float(lo), float(hi)), level, block, b, n)
    cap_total = float(np.sum(marks.capital))
    z = marks.pnl - theta * marks.capital
    se = math.sqrt(n * float(bartlett_lrv(z, block)[0])) / cap_total
    ok = np.isfinite(stars)
    z_r = pnl_r[ok] - stars[ok][:, None] * cap_r[ok]
    with np.errstate(divide="ignore", invalid="ignore"):
        se_r = np.sqrt(n * bartlett_lrv(z_r, block)) / cap_b[ok]
        t_r = (stars[ok] - theta) / se_r
    t_r = t_r[np.isfinite(t_r)]
    b = len(t_r)
    if se > 0:
        t_obs = theta / se
    else:
        t_obs = math.copysign(math.inf, theta) if theta != 0 else 0.0
    p = (1 + int(np.sum(t_r >= t_obs))) / (b + 1)
    if b and se > 0:
        q_lo, q_hi = np.quantile(t_r, [tail, 1.0 - tail])
        lo, hi = theta - q_hi * se, theta - q_lo * se
    else:
        lo, hi = theta, theta
    return Result(
        theta, float(p), (float(lo), float(hi)), level, block, b, n, "studentised"
    )
