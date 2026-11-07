"""
The tests of FDS-SIG-001 section 7, their dependence-robust p-values (section 7.4), Holm
(section 8.1) and the power figures (section 9).

A row is one (candidate, coin, timeframe). Its **eligible pairs**, in time order, are the
input: on each, the candidate's call (``UP`` = +1, ``DOWN`` = -1, ``ABSTAIN`` = 0), the
outcome (up when close[t+1] > close[t]; ties are not eligible pairs) and the return
r = close[t+1] / close[t] - 1.

**Kinds** (section 5, item 4). A two-sided candidate can emit both up and down; a
one-sided one only up (``UP_ONLY``) or only down (``DOWN_ONLY``), plus abstain.

**Each row gets two one-sided tests** (section 7): the hit rate and the magnitude.

* Two-sided hit rate (7.1): an exact paired test against the best constant. The
  constant is "always up" when the up share on the called pairs is at least 0.5, else
  "always down". m counts the called pairs where the candidate's call differs from the
  constant's, k those of them it got right; p = P(Binomial(m, 1/2) >= k), and p = 1 when
  m = 0.
* One-sided hit rate (7.2): one-sided Fisher's exact test on the 2 x 2 table of
  called/abstained x up/down (the called direction's share, called against abstained);
  p = 1 at 100% coverage. A pass also needs the called pairs' own hit rate above 50%.
* Magnitude (7.3): two-sided, the mean over the called pairs of c (r - r_bar) (c = +1 for
  an up call, -1 for a down call; r_bar the mean return on the called pairs), and a pass
  also needs the raw mean of c r above 0; one-sided, the mean return on called pairs
  minus that on abstained eligible pairs (negated for a down-only candidate), and a pass
  also needs the called pairs' mean return to have the called sign.

**Per-pair contributions** (7.4). Every statistic is the mean of per-pair contributions
over the eligible pairs in time order (``contributions``), so the same block bootstrap
and batch means serve them all.

**Block length** L comes from the calls alone (``block_length``): the larger of one day
of bars and ceil(2 tau), tau the larger Bartlett-weighted autocorrelation time of the
call indicators (I, called or not, over the eligible pairs; u, up call or not, over the
called pairs), with maximum lag M = min(one month of bars, floor(S/4)). When no call
indicator varies, L = E.

**Floors** (7.4): K = floor(E / L) >= 30 blocks; m >= 200 for the two-sided hit rate; at
least 200 abstained eligible pairs for the one-sided hit rate and one-sided magnitude.
A row with fewer than 1,000 calls is NOT ASSESSABLE on both statistics (section 6).

**The p-value that enters Holm** is the largest of the exact (hit rate only), circular
block bootstrap and batch-means p-values. The opposite direction (7.5, WORSE) is judged
for the two-sided hit rate against chance at the candidate's mix (Fisher's lower tail on
the call x outcome table, and the 7.5 contribution's lower tails), and otherwise by the
opposite tails of the same statistic. A NOT ASSESSABLE member enters every Holm
procedure with p = 1.

**Power** (section 9): every standard error used is the largest of the
independent-sample, bootstrap and batch-means ones. The minimum detectable effect is at
80% power against Holm's first step; for the two-sided hit rate it is found by
simulation (``mde_two_sided_hit``).
"""

from __future__ import annotations

import math
import statistics as _statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

UP, DOWN, ABSTAIN = 1, -1, 0
TWO_SIDED = "two-sided"
UP_ONLY = "up-only"
DOWN_ONLY = "down-only"
KINDS = (TWO_SIDED, UP_ONLY, DOWN_ONLY)

HIT = "hit_rate"
MAGNITUDE = "magnitude"
STATISTICS = (HIT, MAGNITUDE)

FAMILY_ERROR = 0.05  # section 8.1
MIN_CALLS = 1000  # section 6
MIN_BLOCKS = 30  # section 7.4
MIN_DISCORDANT = 200
MIN_ABSTAINED = 200
POWER = 0.8  # section 9
MAGNITUDE_POWER_Z = 0.84  # section 9: "(z for alpha_1 + 0.84) x the standard error"
ROUND_TRIP_COST = 0.003  # section 7.3: 30 bps, for information

# one day and one month of bars, per timeframe (section 7.4)
DAY_BARS = {"1h": 24, "4h": 6}
MONTH_BARS = {"1h": 720, "4h": 180}

_NORMAL = _statistics.NormalDist()


def z_upper(alpha: float) -> float:
    """z such that P(Z >= z) = alpha."""
    return _NORMAL.inv_cdf(1.0 - alpha)


def first_holm_alpha(family_size: int, family_error: float = FAMILY_ERROR) -> float:
    """Holm's first step, alpha_1 = family error / F."""
    return family_error / max(1, int(family_size))


def min_bootstrap_draws(family_size: int, family_error: float = FAMILY_ERROR) -> int:
    """B >= 100 / alpha_1 (section 7.4)."""
    return int(math.ceil(100.0 / first_holm_alpha(family_size, family_error)))


# --- exact tests -----------------------------------------------------------------------


def binomial_upper(k: int, m: int) -> float:
    """P(Binomial(m, 1/2) >= k); 1 when m = 0 (section 7.1)."""
    from scipy.stats import binom

    if m <= 0:
        return 1.0
    return float(min(1.0, binom.sf(int(k) - 1, int(m), 0.5)))


def fisher_upper(a: int, b: int, c: int, d: int) -> float:
    """One-sided Fisher's exact test of the table [[a, b], [c, d]]: the chance, with the
    margins fixed, of a top-left cell at least ``a`` (row 1's share of column 1 at least
    as far above row 2's)."""
    from scipy.stats import hypergeom

    total, row1, col1 = a + b + c + d, a + b, a + c
    if total == 0 or row1 == 0 or row1 == total or col1 == 0 or col1 == total:
        return 1.0
    return float(min(1.0, hypergeom.sf(a - 1, total, col1, row1)))


def fisher_lower(a: int, b: int, c: int, d: int) -> float:
    """The lower tail: a top-left cell at most ``a``."""
    from scipy.stats import hypergeom

    total, row1, col1 = a + b + c + d, a + b, a + c
    if total == 0 or row1 == 0 or row1 == total or col1 == 0 or col1 == total:
        return 1.0
    return float(min(1.0, hypergeom.cdf(a, total, col1, row1)))


# --- a row's figures -----------------------------------------------------------------


@dataclass(frozen=True)
class Pairs:
    """A row's eligible pairs, in time order."""

    calls: np.ndarray  # int8: UP, DOWN or ABSTAIN
    up: np.ndarray  # int8: 1 when the next close was higher, 0 when lower
    ret: np.ndarray  # float: close[t+1] / close[t] - 1
    kind: str
    timeframe: str

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind {self.kind!r}")
        if not (len(self.calls) == len(self.up) == len(self.ret)):
            raise ValueError("calls, outcomes and returns differ in length")
        bad = set(np.unique(self.calls).tolist()) - {UP, DOWN, ABSTAIN}
        if bad:
            raise ValueError(f"calls must be UP, DOWN or ABSTAIN, not {sorted(bad)}")
        if self.kind == UP_ONLY and np.any(self.calls == DOWN):
            raise ValueError("an up-only candidate called down")
        if self.kind == DOWN_ONLY and np.any(self.calls == UP):
            raise ValueError("a down-only candidate called up")

    @property
    def eligible(self) -> int:
        return int(len(self.calls))

    @property
    def called(self) -> np.ndarray:
        return self.calls != ABSTAIN


@dataclass(frozen=True)
class Counts:
    """Section 6's counts and comparators on a row's eligible pairs."""

    eligible: int
    n: int  # calls
    abstained: int
    up_calls: int
    coverage: Optional[float]
    q: Optional[float]  # share of calls that were up
    h: Optional[float]  # share of calls that were right
    p_c: Optional[float]  # up share on the called pairs
    best_constant: Optional[float]  # b = max(p_c, 1 - p_c)
    constant: Optional[str]  # "up" or "down"
    chance_at_mix: Optional[float]
    up_share_all: Optional[float]  # up share on all eligible pairs
    m: Optional[int] = None  # two-sided: discordant pairs
    k: Optional[int] = None  # two-sided: discordant pairs the candidate got right
    table: Optional[Dict[str, int]] = None  # one-sided: called/abstained x up/down


def counts(p: Pairs) -> Counts:
    called = p.called
    E = p.eligible
    n = int(called.sum())
    up_calls = int((p.calls == UP).sum())
    up_all = float(p.up.mean()) if E else None
    if n == 0:
        return Counts(
            E, 0, E, 0, 0.0 if E else None, None, None, None, None, None, None, up_all
        )
    y = p.up[called].astype(float)
    u = (p.calls[called] == UP).astype(float)
    hits = int(((u == 1) & (y == 1)).sum() + ((u == 0) & (y == 0)).sum())
    q = up_calls / n
    p_c = float(y.mean())
    b = max(p_c, 1.0 - p_c)
    constant = "up" if p_c >= 0.5 else "down"
    chance = q * p_c + (1.0 - q) * (1.0 - p_c)
    m = k = None
    table = None
    if p.kind == TWO_SIDED:
        differs = (u == 0) if constant == "up" else (u == 1)
        right = ((u == 1) & (y == 1)) | ((u == 0) & (y == 0))
        m = int(differs.sum())
        k = int((differs & right).sum())
    else:
        abst = ~called
        table = {
            "called_up": int(p.up[called].sum()),
            "called_down": int(n - p.up[called].sum()),
            "abstained_up": int(p.up[abst].sum()),
            "abstained_down": int(abst.sum() - p.up[abst].sum()),
        }
    return Counts(
        E,
        n,
        E - n,
        up_calls,
        n / E,
        q,
        hits / n,
        p_c,
        b,
        constant,
        chance,
        up_all,
        m,
        k,
        table,
    )


# --- per-pair contributions (section 7.4) ----------------------------------------------


def contributions(p: Pairs, statistic: str, worse: bool = False) -> np.ndarray:
    """The per-pair contributions, before centring, whose mean over the eligible pairs
    is the statistic: section 7.4's table. ``worse`` gives the two-sided hit rate's
    section 7.5 contribution (h minus chance at the mix); for the other statistics the
    opposite direction uses the same contributions' lower tail."""
    E = p.eligible
    called = p.called
    n = int(called.sum())
    out = np.zeros(E, dtype=float)
    if E == 0 or n == 0:
        return out
    y = p.up.astype(float)
    if p.kind == TWO_SIDED:
        u = (p.calls == UP).astype(float)
        scale = E / n
        if statistic == HIT and not worse:
            c = counts(p)
            const_up = 1.0 if c.constant == "up" else 0.0
            cand_hit = np.where(u == 1, y, 1.0 - y)
            const_hit = y if const_up else 1.0 - y
            out[called] = (cand_hit - const_hit)[called] * scale
        elif statistic == HIT and worse:
            u_bar = u[called].mean()
            y_bar = y[called].mean()
            out[called] = 2.0 * (u[called] - u_bar) * (y[called] - y_bar) * scale
        elif statistic == MAGNITUDE:
            cvec = p.calls.astype(float)
            r_bar = p.ret[called].mean()
            out[called] = cvec[called] * (p.ret[called] - r_bar) * scale
        else:
            raise ValueError(statistic)
        return out
    # one-sided: the covariance form, means over all eligible pairs
    if worse and statistic == HIT:
        raise ValueError("a one-sided row's opposite tail uses the 7.2 contribution")
    indicator = called.astype(float)
    cov = indicator.mean()
    if cov in (0.0, 1.0):
        return out
    sign = 1.0 if p.kind == UP_ONLY else -1.0
    if statistic == HIT:
        out = (indicator - cov) * (y - y.mean()) / (cov * (1.0 - cov))
    elif statistic == MAGNITUDE:
        out = (indicator - cov) * (p.ret - p.ret.mean()) / (cov * (1.0 - cov))
    else:
        raise ValueError(statistic)
    return sign * out


def statistic_value(p: Pairs, statistic: str) -> Optional[float]:
    """The statistic itself, computed directly from its definition (section 7)."""
    called = p.called
    n = int(called.sum())
    if n == 0:
        return None
    if p.kind == TWO_SIDED:
        if statistic == HIT:
            c = counts(p)
            return (2 * c.k - c.m) / n
        cvec = p.calls[called].astype(float)
        r = p.ret[called]
        return float(np.mean(cvec * (r - r.mean())))
    abst = ~called
    if not abst.any():
        return None
    sign = 1.0 if p.kind == UP_ONLY else -1.0
    if statistic == HIT:
        return sign * float(p.up[called].mean() - p.up[abst].mean())
    return sign * float(p.ret[called].mean() - p.ret[abst].mean())


def extra_condition(p: Pairs, statistic: str) -> Tuple[bool, Optional[float]]:
    """The pass condition each statistic adds (sections 7.2, 7.3): (met, its value)."""
    called = p.called
    n = int(called.sum())
    if n == 0:
        return False, None
    if p.kind == TWO_SIDED:
        if statistic == HIT:
            return True, None  # beating the best constant is the statistic itself
        raw = float(np.mean(p.calls[called].astype(float) * p.ret[called]))
        return raw > 0.0, raw
    if statistic == HIT:
        hits = p.up[called] if p.kind == UP_ONLY else 1 - p.up[called]
        rate = float(hits.mean())
        return rate > 0.5, rate
    mean = float(p.ret[called].mean())
    return (mean > 0.0 if p.kind == UP_ONLY else mean < 0.0), mean


# --- dependence (section 7.4) ----------------------------------------------------------


def autocorrelation_time(x: np.ndarray, max_lag: int) -> float:
    """tau = max(1, 1 + 2 sum_{k=1..M} (1 - k/(M+1)) rho_k), the sample autocorrelations
    rho_k taken about the series' mean (the usual estimator, normalised by the lag-0
    sum)."""
    x = np.asarray(x, dtype=float)
    S = len(x)
    M = int(max_lag)
    if S < 2 or M < 1:
        return 1.0
    d = x - x.mean()
    denom = float(np.dot(d, d))
    if denom == 0.0:
        return 1.0
    size = 1 << int(math.ceil(math.log2(2 * S)))
    f = np.fft.rfft(d, size)
    acov = np.fft.irfft(f * np.conj(f), size)[: M + 1]
    rho = acov[1 : M + 1] / denom
    k = np.arange(1, M + 1)
    tau = 1.0 + 2.0 * float(np.sum((1.0 - k / (M + 1.0)) * rho))
    return max(1.0, tau)


def max_lag(series_length: int, timeframe: str) -> int:
    return min(MONTH_BARS[timeframe], series_length // 4)


@dataclass(frozen=True)
class Blocks:
    L: int
    K: int
    tau: Optional[float]  # the larger tau of the varying call indicators
    tau_by_indicator: Dict[str, float]
    constant_calls: bool  # no call indicator varies: L = E


def block_length(p: Pairs) -> Blocks:
    """Section 7.4's block length, from the calls alone (never the outcomes)."""
    E = p.eligible
    called = p.called
    taus: Dict[str, float] = {}
    indicator = called.astype(float)
    if E and 0 < indicator.sum() < E:
        taus["I"] = autocorrelation_time(indicator, max_lag(E, p.timeframe))
    u = (p.calls[called] == UP).astype(float)
    S = len(u)
    if S and 0 < u.sum() < S:
        taus["u"] = autocorrelation_time(u, max_lag(S, p.timeframe))
    if not taus:
        return Blocks(E, 1 if E else 0, None, {}, True)
    tau = max(taus.values())
    L = max(DAY_BARS[p.timeframe], int(math.ceil(2.0 * tau)))
    L = min(L, E) if E else L
    return Blocks(L, E // L if L else 0, tau, taus, False)


def mean_run_length(calls: np.ndarray) -> Optional[float]:
    """The mean length of runs of one call value (abstentions included)."""
    if len(calls) == 0:
        return None
    changes = int(np.sum(calls[1:] != calls[:-1]))
    return len(calls) / (changes + 1)


def lag1_autocorrelation(x: np.ndarray) -> Optional[float]:
    x = np.asarray(x, dtype=float)
    if len(x) < 3:
        return None
    d = x - x.mean()
    denom = float(np.dot(d, d))
    if denom == 0.0:
        return None
    return float(np.dot(d[:-1], d[1:]) / denom)


# --- the dependence-robust p-values ----------------------------------------------------


@dataclass(frozen=True)
class Bootstrap:
    p_upper: float
    p_lower: float
    se_upper: float  # Monte Carlo standard errors of the two p-values
    se_lower: float
    sd: float  # the bootstrap standard error of the statistic (sd of T*)
    draws: int


def circular_block_bootstrap(
    x: np.ndarray, L: int, draws: int, rng: np.random.Generator, chunk: int = 4096
) -> Bootstrap:
    """Circular block bootstrap of the centred contributions ``x`` (section 7.4): each
    resample joins ceil(E/L) blocks of L consecutive pairs (wrapping round the end) with
    uniformly random starts, cut to E pairs. T is the mean of ``x``; T* the mean of a
    resample of ``x - mean(x)``. p = (1 + #{T* >= T}) / (B + 1), and the lower tail
    alike."""
    x = np.asarray(x, dtype=float)
    E = len(x)
    T = float(x.mean()) if E else 0.0
    if E == 0 or L <= 0:
        return Bootstrap(1.0, 1.0, 0.0, 0.0, 0.0, 0)
    c = x - T
    doubled = np.concatenate([c, c])
    prefix = np.concatenate([[0.0], np.cumsum(doubled)])
    nb = -(-E // L)
    last = E - (nb - 1) * L
    tol = 1e-12 * max(1.0, float(np.max(np.abs(c))))
    above = below = 0
    total = 0.0
    total_sq = 0.0
    done = 0
    while done < draws:
        size = min(chunk, draws - done)
        starts = rng.integers(0, E, size=(size, nb))
        sums = np.zeros(size)
        if nb > 1:
            full = starts[:, :-1]
            sums += (prefix[full + L] - prefix[full]).sum(axis=1)
        tail = starts[:, -1]
        sums += prefix[tail + last] - prefix[tail]
        t_star = sums / E
        above += int(np.sum(t_star >= T - tol))
        below += int(np.sum(t_star <= T + tol))
        total += float(t_star.sum())
        total_sq += float(np.dot(t_star, t_star))
        done += size
    p_up = (1 + above) / (draws + 1)
    p_lo = (1 + below) / (draws + 1)
    mean = total / draws
    var = max(0.0, total_sq / draws - mean * mean)
    return Bootstrap(
        p_up,
        p_lo,
        math.sqrt(p_up * (1 - p_up) / draws),
        math.sqrt(p_lo * (1 - p_lo) / draws),
        math.sqrt(var * draws / max(1, draws - 1)),
        draws,
    )


@dataclass(frozen=True)
class BatchMeans:
    K: int
    dropped: int  # the oldest E - K L pairs
    mean: float
    se: float
    t: Optional[float]
    p_upper: float
    p_lower: float


def batch_means(x: np.ndarray, L: int) -> BatchMeans:
    """Batch means on the uncentred contributions (section 7.4): drop the oldest E - K L
    pairs, split the rest into K blocks of L, and refer the mean of the block means
    over its standard error to t(K - 1)."""
    from scipy.stats import t as student_t

    x = np.asarray(x, dtype=float)
    E = len(x)
    K = E // L if L > 0 else 0
    if K < 2:
        return BatchMeans(
            K, E - K * L if L > 0 else E, float("nan"), float("nan"), None, 1.0, 1.0
        )
    dropped = E - K * L
    blocks = x[dropped:].reshape(K, L).mean(axis=1)
    mean = float(blocks.mean())
    se = float(blocks.std(ddof=1) / math.sqrt(K))
    if se == 0.0:
        if mean > 0:
            return BatchMeans(K, dropped, mean, se, math.inf, 0.0, 1.0)
        if mean < 0:
            return BatchMeans(K, dropped, mean, se, -math.inf, 1.0, 0.0)
        return BatchMeans(K, dropped, mean, se, 0.0, 1.0, 1.0)
    t = mean / se
    return BatchMeans(
        K,
        dropped,
        mean,
        se,
        t,
        float(student_t.sf(t, K - 1)),
        float(student_t.cdf(t, K - 1)),
    )


# --- Holm (section 8.1) ----------------------------------------------------------------


def holm_adjusted(p_values: Sequence[float]) -> List[float]:
    """Holm's step-down adjusted p-values, in the input order: the i-th smallest is
    max over j <= i of min(1, (F - j + 1) p_(j)). A member survives at family error
    alpha when its adjusted p-value is at most alpha."""
    F = len(p_values)
    order = sorted(range(F), key=lambda i: (p_values[i], i))
    adjusted = [1.0] * F
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (F - rank) * float(p_values[i])))
        adjusted[i] = running
    return adjusted


def holm_survivors(
    p_values: Sequence[float], family_error: float = FAMILY_ERROR
) -> List[bool]:
    return [a <= family_error for a in holm_adjusted(p_values)]


# --- one statistic of one row ----------------------------------------------------------


@dataclass
class StatisticResult:
    statistic: str
    value: Optional[float]
    assessable: bool
    below_floor: List[str]
    # forward direction
    p_exact: Optional[float]
    bootstrap: Optional[Bootstrap]
    batch: Optional[BatchMeans]
    p_holm: float  # the largest of the registered components, or 1 when NOT ASSESSABLE
    # opposite direction (section 7.5)
    q_exact: Optional[float]
    bootstrap_opposite: Optional[
        Bootstrap
    ]  # two-sided hit rate: the 7.5 contribution's
    batch_opposite: Optional[BatchMeans]
    q_holm: float
    extra_met: bool
    extra_value: Optional[float]
    se_independent: Optional[float]
    se_bootstrap: Optional[float]
    se_batch: Optional[float]
    mde: Optional[float] = None
    upper_95: Optional[float] = None
    mde_detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def se(self) -> Optional[float]:
        """The largest of the three standard errors (section 9)."""
        ses = [
            s
            for s in (self.se_independent, self.se_bootstrap, self.se_batch)
            if s is not None and math.isfinite(s)
        ]
        return max(ses) if ses else None


def _largest(*ps: Optional[float]) -> float:
    vals = [float(p) for p in ps if p is not None]
    return max(vals) if vals else 1.0


def independent_se(p: Pairs, statistic: str) -> Optional[float]:
    """The independent-sample standard error of the statistic (section 9)."""
    called = p.called
    n = int(called.sum())
    if n == 0:
        return None
    if p.kind == TWO_SIDED:
        if statistic == HIT:
            c = counts(p)
            return math.sqrt(c.m) / n if c.m else 0.0
        v = p.calls[called].astype(float) * (p.ret[called] - p.ret[called].mean())
        return float(v.std(ddof=1) / math.sqrt(n)) if n > 1 else None
    abst = ~called
    n_a = int(abst.sum())
    if n_a == 0:
        return None
    if statistic == HIT:
        share = p.up if p.kind == UP_ONLY else 1 - p.up
        pooled = float(share.mean())
        return math.sqrt(pooled * (1 - pooled) * (1.0 / n + 1.0 / n_a))
    rc, ra = p.ret[called], p.ret[abst]
    vc = float(rc.var(ddof=1)) if n > 1 else 0.0
    va = float(ra.var(ddof=1)) if n_a > 1 else 0.0
    return math.sqrt(vc / n + va / n_a)


def evaluate_statistic(
    p: Pairs,
    statistic: str,
    blocks: Blocks,
    draws: int,
    rng: np.random.Generator,
    rng_opposite: Optional[np.random.Generator] = None,
) -> StatisticResult:
    """One statistic of one row: its value, floors, every p-value of both tails, and
    the standard errors. Holm and the power figures come afterwards (``engine``)."""
    c = counts(p)
    value = statistic_value(p, statistic)
    floors: List[str] = []
    if c.n < MIN_CALLS:
        floors.append(f"n = {c.n} calls < {MIN_CALLS}")
    if blocks.K < MIN_BLOCKS:
        floors.append(f"K = {blocks.K} blocks < {MIN_BLOCKS}")
    if p.kind == TWO_SIDED and statistic == HIT and (c.m or 0) < MIN_DISCORDANT:
        floors.append(f"m = {c.m or 0} discordant pairs < {MIN_DISCORDANT}")
    if p.kind != TWO_SIDED and c.abstained < MIN_ABSTAINED:
        floors.append(f"{c.abstained} abstained pairs < {MIN_ABSTAINED}")
    x = contributions(p, statistic)
    boot = circular_block_bootstrap(x, blocks.L, draws, rng) if c.n else None
    batch = batch_means(x, blocks.L) if c.n else None
    p_exact = q_exact = None
    boot_opp = batch_opp = None
    if statistic == HIT and c.n:
        if p.kind == TWO_SIDED:
            p_exact = binomial_upper(c.k, c.m)
            u = p.calls[p.called] == UP
            y = p.up[p.called] == 1
            a = int((u & y).sum())
            b = int((u & ~y).sum())
            cc = int((~u & y).sum())
            d = int((~u & ~y).sum())
            q_exact = fisher_lower(a, b, cc, d)  # worse than chance at the mix
            w = contributions(p, HIT, worse=True)
            boot_opp = circular_block_bootstrap(w, blocks.L, draws, rng_opposite or rng)
            batch_opp = batch_means(w, blocks.L)
        else:
            t = c.table
            if p.kind == UP_ONLY:
                cells = (
                    t["called_up"],
                    t["called_down"],
                    t["abstained_up"],
                    t["abstained_down"],
                )
            else:
                cells = (
                    t["called_down"],
                    t["called_up"],
                    t["abstained_down"],
                    t["abstained_up"],
                )
            p_exact = fisher_upper(*cells)
            q_exact = fisher_lower(*cells)
    if boot_opp is None:
        boot_opp, batch_opp = boot, batch  # the same statistic's lower tail
    assessable = not floors
    p_holm = (
        _largest(
            p_exact, boot.p_upper if boot else None, batch.p_upper if batch else None
        )
        if assessable
        else 1.0
    )
    q_holm = (
        _largest(
            q_exact,
            boot_opp.p_lower if boot_opp else None,
            batch_opp.p_lower if batch_opp else None,
        )
        if assessable
        else 1.0
    )
    met, extra = extra_condition(p, statistic)
    return StatisticResult(
        statistic,
        value,
        assessable,
        floors,
        p_exact,
        boot,
        batch,
        p_holm,
        q_exact,
        boot_opp,
        batch_opp,
        q_holm,
        met,
        extra,
        independent_se(p, statistic),
        boot.sd if boot else None,
        batch.se if batch and math.isfinite(batch.se) else None,
    )


# --- power (section 9) -----------------------------------------------------------------


def upper_bound_95(p: Pairs, result: StatisticResult) -> Optional[float]:
    """The 95% upper bound on the edge: (h - b) + 1.96 SE for the two-sided hit rate (the
    1.96 allows for the constant chosen from the same pairs); otherwise the statistic
    plus 1.645 SE."""
    se = result.se
    if result.value is None or se is None:
        return None
    if p.kind == TWO_SIDED and result.statistic == HIT:
        return result.value + 1.96 * se
    return result.value + 1.645 * se


def mde_closed_form(
    p: Pairs, result: StatisticResult, family_size: int
) -> Optional[float]:
    """The minimum detectable effect at 80% power against Holm's first step, where
    section 9 gives it in closed form: the one-sided hit rate (two-proportion power at
    the row's called and abstained counts) and the magnitude ((z for alpha_1 + 0.84) x
    SE). None for the two-sided hit rate (by simulation)."""
    se = result.se
    if se is None:
        return None
    za = z_upper(first_holm_alpha(family_size))
    if result.statistic == MAGNITUDE:
        return (za + MAGNITUDE_POWER_Z) * se
    if p.kind != TWO_SIDED:
        return (za + _NORMAL.inv_cdf(POWER)) * se
    return None


def _circular_block_sd(d: np.ndarray, L: int) -> np.ndarray:
    """The exact standard deviation of the circular block bootstrap's mean (B -> inf)
    for each row of ``d`` (sims x E), for blocks of L: ceil(E/L) independent block sums,
    the last cut to E - (nb - 1) L pairs, each block's start uniform on the circle."""
    S, E = d.shape
    c = d - d.mean(axis=1, keepdims=True)
    doubled = np.concatenate([c, c], axis=1)
    prefix = np.concatenate([np.zeros((S, 1)), np.cumsum(doubled, axis=1)], axis=1)
    nb = -(-E // L)
    last = E - (nb - 1) * L
    j = np.arange(E)
    full = prefix[:, j + L] - prefix[:, j]
    part = prefix[:, j + last] - prefix[:, j]
    var = ((nb - 1) * full.var(axis=1) + part.var(axis=1)) / (E * E)
    return np.sqrt(var)


def _simulated_rows(seed: int, sims: int, E: int, n: int):
    """The draws for one run of simulated rows: which n of the E pairs are called, and
    two uniforms per pair for the call and the outcome. Regenerated from the seed at
    every edge, so every edge sees the same draws."""
    rng = np.random.default_rng(int(seed))
    order = np.argsort(rng.random((sims, E)), axis=1)
    called = np.zeros((sims, E), dtype=bool)
    np.put_along_axis(called, order[:, :n], True, axis=1)
    return called, rng.random((sims, E)), rng.random((sims, E))


def _power_two_sided(
    edge: float,
    E: int,
    n: int,
    q: float,
    p_c: float,
    alpha1: float,
    L: int,
    draws,
) -> Optional[float]:
    """The share of simulated rows (independent pairs; the row's E, n, q and p_c; a hit
    rate of b + edge) whose p-value entering Holm (the largest of the exact, bootstrap
    and batch-means p-values, with the best constant chosen afresh from each simulated
    row) is at most alpha_1. None when the edge is not reachable at this q and p_c."""
    from scipy.stats import binom
    from scipy.stats import norm
    from scipy.stats import t as student_t

    b = max(p_c, 1.0 - p_c)
    h = b + edge
    a = (h - 1.0 + q + p_c) / 2.0  # P(up call and up outcome)
    if not (max(0.0, q + p_c - 1.0) - 1e-12 <= a <= min(q, p_c) + 1e-12):
        return None
    py_up = min(1.0, max(0.0, a / q)) if q > 0 else 0.0
    py_down = min(1.0, max(0.0, (p_c - a) / (1.0 - q))) if q < 1 else 0.0
    called, u_call, u_out = draws
    up_call = u_call < q
    up_out = np.where(up_call, u_out < py_up, u_out < py_down)
    nn = called.sum(axis=1)
    pc_hat = np.where(called, up_out, False).sum(axis=1) / np.maximum(nn, 1)
    const_up = pc_hat >= 0.5
    cand_hit = np.where(up_call, up_out, ~up_out)
    const_hit = np.where(const_up[:, None], up_out, ~up_out)
    contrib = np.where(called, cand_hit.astype(float) - const_hit.astype(float), 0.0)
    contrib *= (E / np.maximum(nn, 1))[:, None]
    differs = called & np.where(const_up[:, None], ~up_call, up_call)
    m = differs.sum(axis=1)
    k = (differs & cand_hit).sum(axis=1)
    p_exact = np.where(m > 0, binom.sf(k - 1, np.maximum(m, 1), 0.5), 1.0)
    T = contrib.mean(axis=1)
    sd = _circular_block_sd(contrib, L)
    with np.errstate(divide="ignore", invalid="ignore"):
        p_boot = np.where(sd > 0, norm.sf(T / sd), np.where(T > 0, 0.0, 1.0))
    K = E // L
    if K < 2:
        return 0.0
    blocks = contrib[:, E - K * L :].reshape(len(T), K, L).mean(axis=2)
    se = blocks.std(axis=1, ddof=1) / math.sqrt(K)
    with np.errstate(divide="ignore", invalid="ignore"):
        tstat = blocks.mean(axis=1) / se
        p_bm = np.where(se > 0, student_t.sf(tstat, K - 1), np.where(T > 0, 0.0, 1.0))
    largest = np.maximum(np.maximum(p_exact, p_boot), p_bm)
    return float(np.mean(largest <= alpha1))


def mde_two_sided_hit(
    E: int,
    n: int,
    q: float,
    p_c: float,
    family_size: int,
    timeframe: str,
    sims: int,
    replicates: int,
    seed: int,
    tolerance: float = 0.0005,
) -> Dict[str, Any]:
    """The two-sided hit rate's minimum detectable effect (section 9): the smallest edge
    over the best constant that the row's own test passes at Holm's first step in 80%
    of simulated rows, at the row's E, n, q and p_c, with the constant chosen afresh
    from each simulated row and the largest-of-three rule.

    * Simulated pairs are independent, so their block length is one day of bars (the
      section 7.4 rule applied to independent calls).
    * The bootstrap p-value is taken at its B -> inf limit: the circular block
      bootstrap's exact variance, with a normal tail. The audit's own tests use the full
      bootstrap: at B >= 100 / alpha_1 per simulated row the search would need about
      10^14 resamples.
    * ``replicates`` independent runs of ``sims`` simulated rows each (seeds
      ``seed + r``), every run seeing the same draws at every edge. The MDE is reported
      pooled over all runs, with each run's own beside it (the owner, 2026-11-06:
      every simulation runs locally, ten times over).
    """
    alpha1 = first_holm_alpha(family_size)
    if E < 2 or n < 2 or q is None or p_c is None:
        return {"mde": None, "reason": "too few pairs", "replicates": []}
    L = min(DAY_BARS[timeframe], E)
    seeds = [int(seed) + r for r in range(replicates)]
    cache: Dict[Tuple[int, float], Optional[float]] = {}

    def run_power(r: int, edge: float) -> Optional[float]:
        key = (r, round(edge, 12))
        if key not in cache:
            cache[key] = _power_two_sided(
                edge, E, n, q, p_c, alpha1, L, _simulated_rows(seeds[r], sims, E, n)
            )
        return cache[key]

    def power(edge: float, which: Sequence[int]) -> Optional[float]:
        vals = [run_power(r, edge) for r in which]
        if any(v is None for v in vals):
            return None
        return float(np.mean(vals))

    def search(which: Sequence[int]) -> Optional[float]:
        b = max(p_c, 1.0 - p_c)
        hi = 1.0 - abs(q - p_c) - b  # the largest reachable edge
        if hi <= 0:
            return None
        top = power(hi, which)
        if top is None or top < POWER:
            return None
        lo = 0.0
        while hi - lo > tolerance:
            mid = 0.5 * (lo + hi)
            pw = power(mid, which)
            if pw is not None and pw >= POWER:
                hi = mid
            else:
                lo = mid
        return hi

    pooled = search(range(replicates))
    each = [search([r]) for r in range(replicates)]
    vals = [v for v in each if v is not None]
    return {
        "mde": pooled,
        "replicates": each,
        "replicate_min": min(vals) if vals else None,
        "replicate_max": max(vals) if vals else None,
        "sims_per_replicate": int(sims),
        "seeds": seeds,
        "block_length": L,
        "alpha_1": alpha1,
        "bootstrap_in_simulation": "B -> inf limit (the exact circular-block variance, "
        "normal tail)",
        "reason": None if pooled is not None else "no reachable edge has 80% power",
    }
