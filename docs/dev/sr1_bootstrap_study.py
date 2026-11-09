"""
FDS-SR-001 amendment 1's simulation study: resampling methods for return per
capital-day when trades are long, variable in length and overlapping.

The study is pre-stated in ``docs/dev/sr1-bootstrap-study/PRE-STATEMENT.md``, which was
committed before this script existed. Synthetic data only: no market data, no candle
cache, no network, and nothing from E1.

    "$PY" docs/dev/sr1_bootstrap_study.py <out-dir> [--jobs N] [--quick]

* Every simulation runs as 10 seeded runs, run r seeded 20261108 + r, reported pooled and
  per run (owner, 2026-11-06).
* Every circular day-block method uses the repository's own bootstrap
  (``signal_fusion.evaluation.bootstrap``): ``Bootstrap.resampled``, ``ratio``,
  ``centred_p`` and ``interval``. Only ``Bootstrap.starts`` is replaced, by numpy draws,
  for speed; a self-check shows the replaced class sums the same days.
* The real-implementation check reruns six methods through ``bootstrap.test_statistic``
  unchanged: its own ``random()`` draws, 10 runs of 1,000 seeded ``seed + r``.

Writes ``<out-dir>/results.json``, ``<out-dir>/tables.md`` and ``<out-dir>/progress.log``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from statistics import NormalDist
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "app"))

from model_lab import stats  # noqa: E402
from signal_fusion.evaluation import bootstrap as bs  # noqa: E402

# --- the design (PRE-STATEMENT.md) ------------------------------------------------------------

SEED = 20261108
RUNS = 10
REPS = 300  # a run's replications per cell
BATCH = 100  # replications simulated together
ORACLE_REPS = 4000
B = 1000  # bootstrap draws per replication
ALPHA = 0.05
SIZE_BAND = (0.025, 0.075)  # Bradley's liberal criterion
FWER_MAX = 0.075
TIE = 0.01
LAMBDA_DECIDE = 2.5
LAMBDAS = (1.0, 2.0, 2.5, 3.0, 4.0)
DELTAS = (0.00025, 0.0005, 0.001, 0.002)  # per capital-day

N_DAYS = 1586
COINS = 11
WARM = 400
FEE = 0.005
ALLOWANCE = 0.0005
M_COST = (
    (1.0 - FEE) ** 2 * (1.0 - ALLOWANCE) / (1.0 + ALLOWANCE)
)  # signal_fusion.labels

# markets
F_VOL, F_A, F_B = 0.035, 0.10, 0.85
BETAS = np.linspace(0.8, 1.3, COINS)
I_VOL = np.linspace(0.020, 0.035, COINS)
I_A, I_B = 0.08, 0.88
T_DF = 4
BEAR_DAYS, BEAR_DRIFT, BEAR_VOL = 365, -0.0025, 1.5
REGIME_DRIFT, REGIME_SPELL, REGIME_VOL = 0.0015, 365, 1.5

# trades
HOLD_SIGMA = 1.0
MIN_GAP = 2.0
VETO = 0.3
RULE_BASE, RULE_SHARE = 28, 0.01  # FDS-SR-001 section 6.0
CAP = 112

FLOOR_WINDOWS = (183, 274, 365, 549, 731, 1586)

FIXED_E = (14, 28, 56, 112, 224, 448, 896)
FIXED_M = (1, 7, 14, 28, 56, 112, 224, 448, 896)
METHODS: Tuple[str, ...] = (
    ("E-rule", "E-rule-cap")
    + tuple(f"E-{L}" for L in FIXED_E)
    + ("E-PW", "E-SB")
    + tuple(f"M-{L}" for L in FIXED_M)
    + ("M-PW", "M-SB", "T-iid", "T-episode", "NW")
)
ELIGIBLE = tuple(m for m in METHODS if m != "NW")
DATA_DRIVEN = {"E-rule", "E-rule-cap", "E-PW", "E-SB", "M-PW", "M-SB"}
REAL_CHECK = ("E-rule", "E-28", "M-14", "M-28", "M-56", "M-112")

# fields stored per replication and method
FIELDS = (
    "theta", "p0", "t05", "lo90p", "hi90p", "lo95p", "hi95p",
    "lo90b", "hi90b", "lo95b", "hi95b", "units", "L",
)  # fmt: skip
F = {name: i for i, name in enumerate(FIELDS)}
K05 = int(math.floor(ALPHA * (B + 1) - 1 + 1e-9))  # exceedances allowed at p <= 5%
Z95 = NormalDist().inv_cdf(0.95)


# --- cells ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    id: int
    group: str  # core, stress, fwer, floor
    market: str  # base, bear, regime
    gen: str  # exo, donchian, tsmom, fwer-exo, fwer-strat
    n: int = 0
    h: int = 0
    days: int = N_DAYS
    circle: int = N_DAYS
    deciding: bool = False
    alias: int = (
        -1
    )  # a floor cell identical in design to this core cell reuses its results

    @property
    def name(self) -> str:
        what = f"exo({self.n},{self.h})" if "exo" in self.gen else self.gen
        if self.gen == "fwer-exo":
            what = f"fwer exo({self.n},{self.h})"
        if self.gen == "fwer-strat":
            what = "fwer donchian+tsmom"
        tail = f" N={self.days}" if self.group == "floor" else ""
        return f"{self.group}:{what}:{self.market}{tail}"


def expected_hold(h: int, days: int) -> float:
    """E[min(hold, days left)] for an entry on a uniform day (the gap calibration)."""
    rng = np.random.default_rng([SEED, 4242, h, days])
    hold = np.maximum(
        1.0, np.ceil(np.exp(np.log(h) + HOLD_SIGMA * rng.standard_normal(200_000)))
    )
    left = days - 1 - rng.integers(0, days - 1, size=200_000)
    return float(np.minimum(hold, left).mean())


def mean_gap(n: float, h: int, days: int) -> float:
    return COINS * days / n - expected_hold(h, days)


def build_cells() -> Tuple[List[Cell], List[dict]]:
    cells: List[Cell] = []
    dropped: List[dict] = []

    def add(**kw):
        cells.append(Cell(id=len(cells), **kw))

    for market in ("base", "bear"):
        for n in (50, 100, 150, 300):
            for h in (10, 30, 60, 120):
                gap = mean_gap(n, h, N_DAYS)
                if gap < MIN_GAP:
                    if market == "base":
                        dropped.append({"n": n, "h": h, "mean_gap": gap})
                    continue
                add(group="core", market=market, gen="exo", n=n, h=h, deciding=n >= 100)
        for gen in ("donchian", "tsmom"):
            add(group="core", market=market, gen=gen, deciding=True)
    add(group="stress", market="regime", gen="exo", n=150, h=30)
    add(group="stress", market="regime", gen="exo", n=50, h=120)
    add(group="stress", market="regime", gen="donchian")
    add(group="fwer", market="base", gen="fwer-exo", n=150, h=30)
    add(group="fwer", market="bear", gen="fwer-exo", n=100, h=60)
    add(group="fwer", market="bear", gen="fwer-strat")
    for market in ("base", "bear"):
        for days in FLOOR_WINDOWS:
            n = int(round(300 * days / N_DAYS))
            for gen in ("exo", "donchian"):
                same = [
                    c.id for c in cells
                    if c.group == "core" and c.market == market and c.gen == gen and days == N_DAYS
                    and (gen != "exo" or (c.n, c.h) == (n, 30))
                ]  # fmt: skip
                add(
                    group="floor", market=market, gen=gen, n=n if gen == "exo" else 0,
                    h=30 if gen == "exo" else 0, days=days, alias=same[0] if same else -1,
                )  # fmt: skip
    return cells, dropped


# --- the market -------------------------------------------------------------------------------


def _garch(z: np.ndarray, vol, a: float, b: float) -> np.ndarray:
    """GARCH(1,1) shocks for standardised innovations z (..., T)."""
    vol = np.asarray(vol, dtype=float)
    w = vol**2 * (1.0 - a - b)
    h = np.broadcast_to(vol**2, z.shape[:-1]).astype(float).copy()
    out = np.empty_like(z)
    for t in range(z.shape[-1]):
        e = np.sqrt(h) * z[..., t]
        out[..., t] = e
        h = w + a * e * e + b * h
    return out


def simulate_market(rng, reps: int, days: int, kind: str, circle: int) -> np.ndarray:
    """Close prices (reps, COINS, WARM + days), starting at 1 before the first day."""
    T = WARM + days
    zf = rng.standard_t(T_DF, size=(reps, T)) / math.sqrt(T_DF / (T_DF - 2))
    zi = rng.standard_t(T_DF, size=(reps, COINS, T)) / math.sqrt(T_DF / (T_DF - 2))
    ef = _garch(zf, F_VOL, F_A, F_B)
    ei = _garch(zi, np.broadcast_to(I_VOL[None, :], (reps, COINS)), I_A, I_B)
    drift = np.zeros((reps, T))
    volm = np.ones((reps, T))
    if kind == "bear":
        bull = -BEAR_DRIFT * BEAR_DAYS / (circle - BEAR_DAYS)
        start = rng.integers(0, circle, size=reps)
        inside = ((np.arange(days)[None, :] - start[:, None]) % circle) < BEAR_DAYS
        drift[:, :WARM] = bull
        drift[:, WARM:] = np.where(inside, BEAR_DRIFT, bull)
        volm[:, WARM:] = np.where(inside, BEAR_VOL, 1.0)
    elif kind == "regime":
        down0 = rng.random(reps) < 0.5
        switches = (
            np.cumsum(rng.random((reps, T)) < 1.0 / REGIME_SPELL, axis=1) % 2 == 1
        )
        down = down0[:, None] ^ switches
        drift = np.where(down, -REGIME_DRIFT, REGIME_DRIFT)
        volm = np.where(down, REGIME_VOL, 1.0)
    elif kind != "base":
        raise ValueError(kind)
    f = drift + volm * ef
    r = BETAS[None, :, None] * f[:, None, :] + ei
    np.maximum(r, -0.9, out=r)
    return np.cumprod(1.0 + r, axis=2)


# --- trades -----------------------------------------------------------------------------------


def exo_inputs(rng, P: np.ndarray, days: int, n: int, h: int):
    """Entry opportunities and holding times for exo(n, h) (PRE-STATEMENT section 4)."""
    R, C, T = P.shape
    W0 = T - days
    lam0 = 1.0 / mean_gap(n, h, days)
    up = P[:, :, W0:] / P[:, :, W0 - 30 : T - 30] > 1.0
    p = np.where(up, 1.0 - math.exp(-1.5 * lam0), 1.0 - math.exp(-0.5 * lam0))
    enter = rng.random((R, C, days)) < p
    z = rng.standard_normal((R, C, days))
    holds = np.maximum(1.0, np.ceil(np.exp(np.log(h) + HOLD_SIGMA * z))).astype(
        np.int64
    )
    return enter, holds


def donchian_inputs(P: np.ndarray, days: int, entry: int = 55, exit_: int = 20):
    """STRAT-004 at its defaults: a close above the previous 55, below the previous 20."""
    T = P.shape[2]
    W0 = T - days
    hi = sliding_window_view(P[:, :, W0 - entry : T - 1], entry, axis=2).max(axis=-1)
    lo = sliding_window_view(P[:, :, W0 - exit_ : T - 1], exit_, axis=2).min(axis=-1)
    close = P[:, :, W0:]
    return close > hi, close < lo


def tsmom_inputs(P: np.ndarray, days: int, lbs=(30, 90, 365), agree=2, every=7):
    """STRAT-005 at its defaults: two of three returns positive, decided every 7 days."""
    T = P.shape[2]
    W0 = T - days
    close = P[:, :, W0:]
    votes = sum((close / P[:, :, W0 - L : T - L] > 1.0).astype(int) for L in lbs)
    want = votes >= agree
    decide = (np.arange(days) % every == 0)[None, None, :]
    return want & decide, (~want) & decide


def positions(P, days, enter, holds=None, exit_sig=None, veto=None) -> dict:
    """One position per coin; a flat coin takes an entry opportunity unless vetoed, and
    cannot re-enter on its exit day. Returns the trades and the marked day sums."""
    R, C, T = P.shape
    W0 = T - days
    inpos = np.zeros((R, C), dtype=bool)
    entry_d = np.zeros((R, C), dtype=np.int64)
    exit_d = np.full((R, C), -1, dtype=np.int64)
    pe = np.ones((R, C))
    nm = np.zeros((R, days))
    cm = np.zeros((R, days))
    rec = []
    none = np.zeros((R, C), dtype=bool)
    for d in range(days):
        g = W0 + d
        pg = P[:, :, g]
        ex = none
        if inpos.any():
            change = (pg - P[:, :, g - 1]) / pe
            nm[:, d] += M_COST * np.where(inpos, change, 0.0).sum(axis=1)
            cm[:, d] += inpos.sum(axis=1)
            if d == days - 1:
                ex = inpos.copy()
            elif holds is not None:
                ex = inpos & (exit_d == d)
            else:
                ex = inpos & exit_sig[:, :, d]
            if ex.any():
                ri, ci = np.nonzero(ex)
                rec.append(
                    (
                        ri,
                        ci,
                        entry_d[ri, ci],
                        np.full(len(ri), d),
                        M_COST * pg[ri, ci] / pe[ri, ci] - 1.0,
                    )
                )
                inpos = inpos & ~ex
        if d < days - 1:
            can = enter[:, :, d] & ~inpos & ~ex
            if veto is not None:
                can &= ~veto[:, :, d]
            if can.any():
                inpos = inpos | can
                entry_d[can] = d
                pe[can] = pg[can]
                if holds is not None:
                    exit_d[can] = np.minimum(d + holds[:, :, d][can], days - 1)
                nm[:, d] += (M_COST - 1.0) * can.sum(axis=1)
    if rec:
        ri, ci, e, x, net = (np.concatenate(v) for v in zip(*rec))
    else:
        ri = ci = e = x = np.zeros(0, dtype=np.int64)
        net = np.zeros(0)
    order = np.lexsort((e, ri))
    ri, ci, e, x, net = ri[order], ci[order], e[order], x[order], net[order]
    ne = np.zeros((R, days))
    ce = np.zeros((R, days))
    np.add.at(ne, (ri, e), net)
    np.add.at(ce, (ri, e), (x - e).astype(float))
    bounds = np.searchsorted(ri, np.arange(R + 1))
    return {
        "nm": nm,
        "cm": cm,
        "ne": ne,
        "ce": ce,
        "e": e,
        "x": x,
        "net": net,
        "coin": ci,
        "bounds": bounds,
    }


def make_data(cell: Cell, rng, reps: int) -> Dict[str, dict]:
    """The cell's members for ``reps`` replications: {"A": ...} or the four FWER members."""
    P = simulate_market(rng, reps, cell.days, cell.market, cell.circle)
    if cell.gen == "exo":
        enter, holds = exo_inputs(rng, P, cell.days, cell.n, cell.h)
        return {"A": positions(P, cell.days, enter, holds=holds)}
    if cell.gen in ("donchian", "tsmom"):
        fn = donchian_inputs if cell.gen == "donchian" else tsmom_inputs
        enter, exit_sig = fn(P, cell.days)
        return {"A": positions(P, cell.days, enter, exit_sig=exit_sig)}
    if cell.gen == "fwer-exo":
        ea, ha = exo_inputs(rng, P, cell.days, cell.n, cell.h)
        eb, hb = exo_inputs(rng, P, cell.days, cell.n, cell.h)
        va = rng.random(ea.shape) < VETO
        vb = rng.random(eb.shape) < VETO
        return {
            "A": positions(P, cell.days, ea, holds=ha),
            "A-veto": positions(P, cell.days, ea, holds=ha, veto=va),
            "B": positions(P, cell.days, eb, holds=hb),
            "B-veto": positions(P, cell.days, eb, holds=hb, veto=vb),
        }
    if cell.gen == "fwer-strat":
        ea, xa = donchian_inputs(P, cell.days)
        eb, xb = tsmom_inputs(P, cell.days)
        va = rng.random(ea.shape) < VETO
        vb = rng.random(eb.shape) < VETO
        return {
            "A": positions(P, cell.days, ea, exit_sig=xa),
            "A-veto": positions(P, cell.days, ea, exit_sig=xa, veto=va),
            "B": positions(P, cell.days, eb, exit_sig=xb),
            "B-veto": positions(P, cell.days, eb, exit_sig=xb, veto=vb),
        }
    raise ValueError(cell.gen)


def rep_view(m: dict, i: int) -> dict:
    a, b = m["bounds"][i], m["bounds"][i + 1]
    return {
        "nm": m["nm"][i], "cm": m["cm"][i], "ne": m["ne"][i], "ce": m["ce"][i],
        "e": m["e"][a:b], "x": m["x"][a:b], "net": m["net"][a:b], "coin": m["coin"][a:b],
    }  # fmt: skip


# --- the methods ------------------------------------------------------------------------------


class FastBootstrap(bs.Bootstrap):
    """The repository's circular block bootstrap with numpy start days (one run of
    ``per_run`` draws). Everything but ``starts`` is the original code."""

    def __init__(self, days: int, block: int, rng, per_run: int = B):
        super().__init__(days, 0, block, runs=1, per_run=per_run)
        self._rng = rng

    def starts(self, run: int) -> np.ndarray:
        return self._rng.integers(
            0, self.days, size=(self.per_run, self.blocks), dtype=np.int64
        )


def rule_length(holds: Sequence[float], cap: Optional[int] = None) -> int:
    """FDS-SR-001 section 6.0 (``strategy_lab.e1.block_length``), optionally capped."""
    d = np.asarray(list(holds), dtype=float)
    length = RULE_BASE
    if len(d):
        while np.mean(d > length / 2.0) > RULE_SHARE:
            length *= 2
    return min(length, cap) if cap else length


def pw_lengths(x: np.ndarray) -> Tuple[float, float]:
    """Politis and White (2004) with Patton, Politis and White's (2009) correction: the
    optimal block lengths for the circular and the stationary bootstrap."""
    n = len(x)
    eps = np.asarray(x, dtype=float) - float(np.mean(x))
    if not np.any(eps):
        return 1.0, 1.0
    b_max = math.ceil(min(3 * math.sqrt(n), n / 3))
    kn = max(5, int(math.log10(n)))
    m_max = int(math.ceil(math.sqrt(n))) + kn
    cv = 2.0 * math.sqrt(math.log10(n) / n)
    acv = np.zeros(m_max + 1)
    abs_acorr = np.zeros(m_max + 1)
    opt_m = None
    for i in range(m_max + 1):
        v1 = eps[i + 1 :] @ eps[i + 1 :]
        v2 = eps[: -(i + 1)] @ eps[: -(i + 1)]
        cross = eps[i:] @ eps[: n - i]
        acv[i] = cross / n
        abs_acorr[i] = abs(cross) / math.sqrt(v1 * v2) if v1 > 0 and v2 > 0 else 0.0
        if i >= kn and opt_m is None and np.all(abs_acorr[i - kn : i] < cv):
            opt_m = i - kn
    m = 2 * max(opt_m, 1) if opt_m is not None else m_max
    m = min(m, m_max)
    g = 0.0
    lr = acv[0]
    for k in range(1, m + 1):
        lam = 1.0 if k / m <= 0.5 else 2.0 * (1.0 - k / m)
        g += 2.0 * lam * k * acv[k]
        lr += 2.0 * lam * acv[k]
    if lr <= 0:
        return 1.0, 1.0
    b_sb = ((2.0 * g * g) / (2.0 * lr * lr)) ** (1 / 3) * n ** (1 / 3)
    b_cb = ((2.0 * g * g) / (4.0 / 3.0 * lr * lr)) ** (1 / 3) * n ** (1 / 3)
    return float(min(max(b_cb, 1.0), b_max)), float(min(max(b_sb, 1.0), b_max))


def clip_len(b: float, cap: int = CAP) -> int:
    return int(min(max(round(b), 1), cap))


def sb_draws(
    num: np.ndarray,
    den: np.ndarray,
    mean_len: float,
    rng,
    draws: int = B,
    form: Optional[str] = None,
) -> np.ndarray:
    """The stationary bootstrap (Politis and Romano 1994), circular, cut to N days.

    Short mean lengths use the day-by-day form (each day starts a new block with
    probability 1 / mean_len), longer ones draw whole blocks; both sample the same
    scheme."""
    n = len(num)
    p = 1.0 / mean_len
    if form == "days" or (form is None and mean_len < 8):
        new = rng.random((draws, n)) < p
        new[:, 0] = True
        start = rng.integers(0, n, size=(draws, n))
        t = np.arange(n)
        first = np.maximum.accumulate(np.where(new, t[None, :], 0), axis=1)
        idx = (np.take_along_axis(start, first, axis=1) + (t[None, :] - first)) % n
        tot = np.column_stack([num[idx].sum(axis=1), den[idx].sum(axis=1)])
        return bs.ratio(0, 1)(tot)
    kmax = int(math.ceil(n * p + 6.0 * math.sqrt(n * p) + 10))
    lengths = np.minimum(rng.geometric(p, size=(draws, kmax)), n)
    starts = rng.integers(0, n, size=(draws, kmax))
    while True:
        cum_len = np.cumsum(lengths, axis=1)
        short = cum_len[:, -1] < n
        if not short.any():
            break
        lengths = np.hstack(
            [lengths, np.minimum(rng.geometric(p, size=(draws, kmax)), n)]
        )
        starts = np.hstack([starts, rng.integers(0, n, size=(draws, kmax))])
    used = np.clip(n - (cum_len - lengths), 0, lengths)
    ends = starts + used
    cols = []
    for v in (num, den):
        cum = np.concatenate([[0.0], np.cumsum(np.concatenate([v, v]))])
        cols.append((cum[ends] - cum[starts]).sum(axis=1))
    return bs.ratio(0, 1)(np.column_stack(cols))


def unit_draws(num: np.ndarray, den: np.ndarray, rng, draws: int = B) -> np.ndarray:
    """Units (trades or episodes) resampled independently with replacement."""
    k = len(num)
    idx = rng.integers(0, k, size=(draws, k))
    tot = np.column_stack([num[idx].sum(axis=1), den[idx].sum(axis=1)])
    return bs.ratio(0, 1)(tot)


def episodes(e: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Each trade's episode: chains of trades whose held days (entry, exit] overlap."""
    if not len(e):
        return np.zeros(0, dtype=np.int64)
    order = np.argsort(e, kind="stable")
    es, xs = e[order], x[order]
    run_max = np.maximum.accumulate(xs)
    new = np.ones(len(es), dtype=bool)
    new[1:] = es[1:] >= run_max[:-1]
    lab = np.empty(len(es), dtype=np.int64)
    lab[order] = np.cumsum(new) - 1
    return lab


def summarise(theta: float, draws: np.ndarray) -> List[float]:
    d = np.asarray(draws, dtype=float).ravel()
    p0 = bs.centred_p(theta, d)
    c = np.sort(d - theta)[::-1]
    lo90, hi90 = bs.interval(d, 0.90)
    lo95, hi95 = bs.interval(d, 0.95)
    return [
        theta, p0, float(c[K05]), lo90, hi90, lo95, hi95,
        2 * theta - hi90, 2 * theta - lo90, 2 * theta - hi95, 2 * theta - lo95,
    ]  # fmt: skip


def newey_west(theta: float, z: np.ndarray, den_total: float) -> List[float]:
    n = len(z)
    q = int(math.floor(4 * (n / 100.0) ** (2 / 9)))
    zc = z - z.mean()
    s = zc @ zc
    for k in range(1, q + 1):
        s += 2.0 * (1.0 - k / (q + 1.0)) * (zc[k:] @ zc[:-k])
    se = math.sqrt(max(s, 0.0)) / den_total if den_total > 0 else float("inf")
    p0 = 1.0 - NormalDist().cdf(theta / se) if se > 0 else (0.0 if theta > 0 else 1.0)
    h90, h95 = Z95 * se, NormalDist().inv_cdf(0.975) * se
    return [
        theta, p0, Z95 * se, theta - h90, theta + h90, theta - h95, theta + h95,
        theta - h90, theta + h90, theta - h95, theta + h95,
    ]  # fmt: skip


def evaluate(
    rep: dict, theta_true: float, key: Sequence[int], rule_holds=None
) -> np.ndarray:
    """Every method on one replication, after the null shift. (len(METHODS), FIELDS)."""
    days = len(rep["nm"])
    cm, ce = rep["cm"], rep["ce"]
    num_m = rep["nm"] - theta_true * cm
    num_e = rep["ne"] - theta_true * ce
    cd = (rep["x"] - rep["e"]).astype(float)
    tnet = rep["net"] - theta_true * cd
    total_c = float(cm.sum())
    theta = float(num_m.sum() / total_c) if total_c > 0 else 0.0
    holds = cd if rule_holds is None else rule_holds
    out = np.full((len(METHODS), len(FIELDS)), np.nan)
    pw_e = pw_lengths(num_e - theta * ce)
    pw_m = pw_lengths(num_m - theta * cm)
    sums_e = bs.DaySums(0, np.column_stack([num_e, ce]))
    sums_m = bs.DaySums(0, np.column_stack([num_m, cm]))
    lab = None
    for j, name in enumerate(METHODS):
        rng = np.random.default_rng([*key, j])
        units = float("nan")
        length = float("nan")
        if name == "NW":
            row = newey_west(theta, num_m - theta * cm, total_c)
        elif name.startswith(("E-", "M-")):
            kind, rule = name.split("-", 1)
            num, den, sums, pw = (
                (num_e, ce, sums_e, pw_e) if kind == "E" else (num_m, cm, sums_m, pw_m)
            )
            if rule == "SB":
                length = clip_len(pw[1])
                draws = sb_draws(num, den, float(length), rng)
                units = days / length
            else:
                if rule == "rule":
                    length = rule_length(holds)
                elif rule == "rule-cap":
                    length = rule_length(holds, CAP)
                elif rule == "PW":
                    length = clip_len(pw[0])
                else:
                    length = int(rule)
                draws = FastBootstrap(days, int(length), rng).draws(
                    sums, bs.ratio(0, 1)
                )[0]
                units = math.ceil(days / length)
            row = summarise(theta, draws)
        elif name == "T-iid":
            units = len(tnet)
            draws = unit_draws(tnet, cd, rng) if len(tnet) else np.zeros(B)
            row = summarise(theta, draws)
        elif name == "T-episode":
            if lab is None:
                lab = episodes(rep["e"], rep["x"])
            k = int(lab.max()) + 1 if len(lab) else 0
            units = k
            if k:
                cnet = np.bincount(lab, weights=tnet, minlength=k)
                ccd = np.bincount(lab, weights=cd, minlength=k)
                draws = unit_draws(cnet, ccd, rng)
            else:
                draws = np.zeros(B)
            row = summarise(theta, draws)
        else:
            raise ValueError(name)
        out[j, : len(row)] = row
        out[j, F["units"]] = units
        out[j, F["L"]] = length
    return out


def rep_stats(rep: dict, days: int) -> List[float]:
    """Trades, trades in the first half, time in market, mean open positions, episodes,
    the section 6.0 rule's L, median, p90 and p99 hold."""
    cd = rep["x"] - rep["e"]
    middle = days // 2
    lab = episodes(rep["e"], rep["x"])
    q = np.percentile(cd, [50, 90, 99]) if len(cd) else [np.nan] * 3
    return [
        len(cd),
        int(np.sum(rep["e"] < middle)),
        float(rep["cm"].sum() / (COINS * days)),
        float(rep["cm"].sum() / days),
        int(lab.max()) + 1 if len(lab) else 0,
        rule_length(cd),
        *[float(v) for v in q],
    ]


STAT_NAMES = (
    "trades",
    "first_half",
    "time_in_market",
    "open_positions",
    "episodes",
    "rule_L",
    "hold_p50",
    "hold_p90",
    "hold_p99",
)


# --- tasks ------------------------------------------------------------------------------------


def oracle_task(cell: Cell, chunk: int, reps: int) -> dict:
    """Raw sums for theta_true and SD0, per member."""
    rng = np.random.default_rng([SEED, 9999, cell.id, chunk])
    out: Dict[str, dict] = {}
    done = 0
    while done < reps:
        k = min(BATCH, reps - done)
        data = make_data(cell, rng, k)
        for name, m in data.items():
            o = out.setdefault(name, {"net": [], "cd": [], "stats": []})
            for i in range(k):
                rep = rep_view(m, i)
                o["net"].append(float(rep["nm"].sum()))
                o["cd"].append(float(rep["cm"].sum()))
                o["stats"].append(rep_stats(rep, cell.days))
        done += k
    return {"cell": cell.id, "chunk": chunk, "members": out}


def study_task(cell: Cell, run: int, reps: int, theta_true: Dict[str, float]) -> dict:
    t0 = time.time()
    rng = np.random.default_rng([SEED + run, cell.id, 0])
    members = sorted(theta_true)
    res = []
    fwer_p = []
    stats_rows = []
    done = 0
    while done < reps:
        k = min(BATCH, reps - done)
        data = make_data(cell, rng, k)
        for i in range(k):
            r = done + i
            if cell.group == "fwer":
                reps_i = {name: rep_view(data[name], i) for name in members}
                pooled = np.concatenate(
                    [reps_i[nm]["x"] - reps_i[nm]["e"] for nm in ("A", "B")]
                ).astype(float)
                row = []
                for mi, name in enumerate(members):
                    ev = evaluate(
                        reps_i[name],
                        theta_true[name],
                        [SEED + run, cell.id, r, mi],
                        pooled,
                    )
                    row.append(ev[:, [F["theta"], F["p0"]]])
                fwer_p.append(np.stack(row))  # (members, methods, 2)
                stats_rows.append(rep_stats(reps_i["A"], cell.days))
            else:
                rep = rep_view(data["A"], i)
                res.append(evaluate(rep, theta_true["A"], [SEED + run, cell.id, r]))
                stats_rows.append(rep_stats(rep, cell.days))
        done += k
    return {
        "cell": cell.id,
        "run": run,
        "out": np.stack(res) if res else None,
        "fwer": np.stack(fwer_p) if fwer_p else None,
        "members": members,
        "stats": np.array(stats_rows, dtype=float),
        "seconds": time.time() - t0,
    }


def real_check_task(cell: Cell, run: int, reps: int, theta_true: float) -> dict:
    """REAL_CHECK through ``bootstrap.test_statistic`` unchanged, beside the fast version."""
    t0 = time.time()
    rng = np.random.default_rng([SEED + run, cell.id, 900])
    data = make_data(cell, rng, reps)["A"]
    real = np.zeros((reps, len(REAL_CHECK)))
    fast = np.zeros((reps, len(REAL_CHECK)))
    for i in range(reps):
        rep = rep_view(data, i)
        ev = evaluate(rep, theta_true, [SEED + run, cell.id, 900, i])
        cd = rep["x"] - rep["e"]
        for j, name in enumerate(REAL_CHECK):
            kind, rule = name.split("-", 1)
            if kind == "E":
                num, den = rep["ne"] - theta_true * rep["ce"], rep["ce"]
            else:
                num, den = rep["nm"] - theta_true * rep["cm"], rep["cm"]
            block = rule_length(cd) if rule == "rule" else int(rule)
            sums = bs.DaySums(0, np.column_stack([num, den]))
            seed = 1_000_000 * (run + 1) + 10_000 * cell.id + 10 * i + j
            real[i, j] = bs.test_statistic(sums, bs.ratio(0, 1), seed, block)["p"]
            fast[i, j] = ev[METHODS.index(name), F["p0"]]
    return {
        "cell": cell.id,
        "run": run,
        "real": real,
        "fast": fast,
        "seconds": time.time() - t0,
    }


# --- self-checks (fail closed) ----------------------------------------------------------------


def self_check() -> Dict[str, object]:
    out: Dict[str, object] = {}
    rng = np.random.default_rng([SEED, 1])
    # 1. FastBootstrap sums the same days as the original for the same starts
    days = 300
    sums = bs.DaySums(0, rng.standard_normal((days, 2)))
    for block in (1, 2, 7, 28, 112, 299, 300, 896):
        orig = bs.Bootstrap(days, 123, block, runs=1, per_run=50)
        starts = orig.starts(0)

        class Fixed(FastBootstrap):
            def starts(self, run):
                return starts

        fast = Fixed(days, block, None, per_run=50)
        if not np.array_equal(orig.resampled(sums, 0), fast.resampled(sums, 0)):
            raise AssertionError(f"FastBootstrap differs from Bootstrap at L={block}")
    out["fast_bootstrap_equals_original"] = True
    # 2. marked day sums add up to the trades; theta is the same under E and M
    cell = Cell(id=0, group="check", market="bear", gen="exo", n=150, h=30)
    data = make_data(cell, np.random.default_rng([SEED, 2]), 5)["A"]
    for i in range(5):
        rep = rep_view(data, i)
        cd = (rep["x"] - rep["e"]).astype(float)
        assert abs(rep["nm"].sum() - rep["net"].sum()) < 1e-9 * max(1, len(cd))
        assert abs(rep["cm"].sum() - cd.sum()) < 1e-9
        assert abs(rep["ne"].sum() - rep["net"].sum()) < 1e-9 * max(1, len(cd))
        # entry-day sums equal the implementation's own day_sums
        ref = bs.day_sums(
            rep["e"] * bs.DAY_S, [rep["net"], cd], 0, (cell.days - 1) * bs.DAY_S
        )
        assert np.allclose(ref.sums[:, 0], rep["ne"]) and np.allclose(
            ref.sums[:, 1], rep["ce"]
        )
        # one position per coin, no re-entry on the exit day
        for c in range(COINS):
            sel = rep["coin"] == c
            es, xs = rep["e"][sel], rep["x"][sel]
            assert np.all(xs > es) and np.all(es[1:] > xs[:-1])
    out["marked_sums_telescope"] = True
    # 3. the shift: theta and every draw move by exactly delta
    rep = rep_view(data, 0)
    base = evaluate(rep, 0.0, [SEED, 3])
    shifted = evaluate(rep, -0.001, [SEED, 3])  # subtracting -delta adds delta
    for j, name in enumerate(METHODS):
        for fld in ("theta", "lo90p", "hi90p", "lo90b"):
            a, b = base[j, F[fld]], shifted[j, F[fld]]
            assert abs((b - a) - 0.001) < 1e-9, (name, fld, a, b)
        assert abs(base[j, F["t05"]] - shifted[j, F["t05"]]) < 1e-9, name
    out["shift_invariance"] = True
    # 4. p <= 5% exactly when theta > t05
    for j in range(len(METHODS) - 1):
        th, p, t = base[j, F["theta"]], base[j, F["p0"]], base[j, F["t05"]]
        assert (p <= ALPHA) == (th > t), METHODS[j]
    out["p_matches_threshold"] = True
    # 5. Donchian windows against a direct computation
    P = simulate_market(np.random.default_rng([SEED, 4]), 2, 120, "base", 120)
    en, xs = donchian_inputs(P, 120)
    W0 = P.shape[2] - 120
    for d in (0, 1, 57, 119):
        g = W0 + d
        assert np.array_equal(en[:, :, d], P[:, :, g] > P[:, :, g - 55 : g].max(axis=2))
        assert np.array_equal(xs[:, :, d], P[:, :, g] < P[:, :, g - 20 : g].min(axis=2))
    out["donchian_windows"] = True
    # 5b. the two forms of the stationary bootstrap agree in distribution
    x = np.random.default_rng([SEED, 5]).standard_normal(400) + 0.1
    ones = np.ones(400)
    for mean_len in (3.0, 6.0):
        a = sb_draws(x, ones, mean_len, np.random.default_rng([SEED, 6]), 4000, "days")
        b = sb_draws(
            x, ones, mean_len, np.random.default_rng([SEED, 7]), 4000, "blocks"
        )
        if (
            abs(a.std() / b.std() - 1) > 0.08
            or abs(a.mean() - b.mean()) > 0.1 * a.std()
        ):
            raise AssertionError(f"stationary bootstrap forms differ at {mean_len}")
    out["stationary_forms_agree"] = True
    # 6. the section 6.0 rule on hand-worked holds
    assert rule_length([10] * 100) == 28
    assert rule_length([10] * 98 + [15, 15]) == 56  # 2% above 14 days
    assert rule_length([10] * 99 + [15]) == 28  # exactly 1% is allowed
    assert rule_length([300] * 2 + [5] * 98) == 896
    assert rule_length([300] * 2 + [5] * 98, CAP) == CAP
    out["rule_hand_worked"] = True
    return out


# --- aggregation ------------------------------------------------------------------------------


def _rate(x: np.ndarray) -> float:
    return float(np.mean(x)) if x.size else float("nan")


def cell_metrics(out: np.ndarray, runs: np.ndarray, sd0: float) -> Dict[str, dict]:
    """Per method: pooled and per-run size, coverage, agreement, power and units."""
    res: Dict[str, dict] = {}
    th = out[:, :, F["theta"]]
    for j, name in enumerate(METHODS):
        o = out[:, j, :]
        theta = th[:, j]
        rej0 = o[:, F["p0"]] <= ALPHA
        d25 = LAMBDA_DECIDE * sd0

        def by_run(fn):
            vals = [fn(runs == r) for r in range(RUNS) if np.any(runs == r)]
            return {"pooled": fn(np.ones(len(runs), dtype=bool)), "runs": vals}

        m = {
            "size": by_run(lambda s: _rate(rej0[s])),
            "coverage": {
                key: by_run(
                    lambda s, lo=lo, hi=hi: _rate(
                        (o[s, F[lo]] <= 0) & (0 <= o[s, F[hi]])
                    )
                )
                for key, lo, hi in (
                    ("pct90", "lo90p", "hi90p"),
                    ("pct95", "lo95p", "hi95p"),
                    ("basic90", "lo90b", "hi90b"),
                    ("basic95", "lo95b", "hi95b"),
                )
            },
            "agreement": {
                "pct_null": by_run(lambda s: _rate(rej0[s] == (o[s, F["lo90p"]] > 0))),
                "basic_null": by_run(
                    lambda s: _rate(rej0[s] == (o[s, F["lo90b"]] > 0))
                ),
                "pct_alt": by_run(
                    lambda s: _rate(
                        (theta[s] + d25 > o[s, F["t05"]])
                        == (o[s, F["lo90p"]] + d25 > 0)
                    )
                ),
                "basic_alt": by_run(
                    lambda s: _rate(
                        (theta[s] + d25 > o[s, F["t05"]])
                        == (o[s, F["lo90b"]] + d25 > 0)
                    )
                ),
            },
            "power_lambda": {
                str(lam): by_run(
                    lambda s, lam=lam: _rate(theta[s] + lam * sd0 > o[s, F["t05"]])
                )
                for lam in LAMBDAS
            },
            "power_delta": {
                str(dl): by_run(lambda s, dl=dl: _rate(theta[s] + dl > o[s, F["t05"]]))
                for dl in DELTAS
            },
            "units": (
                {
                    "mean": float(np.nanmean(o[:, F["units"]])),
                    "min": float(np.nanmin(o[:, F["units"]])),
                }
                if np.any(np.isfinite(o[:, F["units"]]))
                else None
            ),
            "L": (
                {
                    "mean": float(np.nanmean(o[:, F["L"]])),
                    "min": float(np.nanmin(o[:, F["L"]])),
                    "max": float(np.nanmax(o[:, F["L"]])),
                }
                if np.any(np.isfinite(o[:, F["L"]]))
                else None
            ),
        }
        res[name] = m
    return res


def size_given_floor(
    out: np.ndarray, stats_arr: np.ndarray, days: int
) -> Dict[str, Optional[float]]:
    """Size over the replications meeting F3's trade floor (100 trades, 30 a half)."""
    n = stats_arr[:, 0]
    first = stats_arr[:, 1]
    ok = (n >= 100) & (first >= 30) & (n - first >= 30)
    res = {"share_meeting_floor": float(np.mean(ok))}
    for j, name in enumerate(METHODS):
        res[name] = _rate(out[ok, j, F["p0"]] <= ALPHA) if ok.any() else None
    return res


# --- tables -----------------------------------------------------------------------------------


def pct(v, digits=1) -> str:
    return (
        "–"
        if v is None or (isinstance(v, float) and not np.isfinite(v))
        else f"{100 * v:.{digits}f}"
    )


def rng_str(vals) -> str:
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    return f"{pct(min(vals))}–{pct(max(vals))}" if vals else "–"


def write_tables(results: dict, path: str) -> None:
    cells = results["cells"]
    lines = [
        "# SR-001 bootstrap study: generated tables",
        "",
        f"Generated by `docs/dev/sr1_bootstrap_study.py`. Percentages unless stated. Per-run ranges are the smallest and largest of the 10 runs.",
        "",
    ]
    lines += [
        "## Cells",
        "",
        "| Cell | Deciding | Trades (mean) | Time in market | Open positions | Hold p50 / p90 / p99 (days) | Episodes (mean) | §6.0 rule L (median) | θ_true | SD₀ |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in cells:
        s = c["oracle"]["A"]["stats"]
        lines.append(
            f"| {c['name']} | {'yes' if c['deciding'] else ''} | {s['trades']:.0f} | {pct(s['time_in_market'])} | {s['open_positions']:.1f} | "
            f"{s['hold_p50']:.0f} / {s['hold_p90']:.0f} / {s['hold_p99']:.0f} | {s['episodes']:.1f} | {s['rule_L_median']:.0f} | "
            f"{100 * c['oracle']['A']['theta_true']:+.4f}% | {100 * c['oracle']['A']['sd0']:.4f}% |"
        )
    lines.append("")
    for c in cells:
        if c["group"] == "fwer":
            continue
        lines += [
            f"## {c['name']}",
            "",
            "| Method | Size (runs) | Cover 90 pct / basic | Cover 95 pct / basic | Agree pct / basic (null) | Power λ=1 / 2 / 2.5 / 3 / 4 | Power δ=0.05% / 0.10% | Units mean (min) | L mean (min–max) |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for name in METHODS:
            m = c["methods"][name]
            u = m["units"]
            L = m["L"]
            lines.append(
                f"| {name} | {pct(m['size']['pooled'])} ({rng_str(m['size']['runs'])}) | "
                f"{pct(m['coverage']['pct90']['pooled'])} / {pct(m['coverage']['basic90']['pooled'])} | "
                f"{pct(m['coverage']['pct95']['pooled'])} / {pct(m['coverage']['basic95']['pooled'])} | "
                f"{pct(m['agreement']['pct_null']['pooled'])} / {pct(m['agreement']['basic_null']['pooled'])} | "
                + " / ".join(
                    pct(m["power_lambda"][str(lam)]["pooled"], 0) for lam in LAMBDAS
                )
                + f" | {pct(m['power_delta'][str(0.0005)]['pooled'], 0)} / {pct(m['power_delta'][str(0.001)]['pooled'], 0)} | "
                + (f"{u['mean']:.1f} ({u['min']:.0f})" if u else "–")
                + " | "
                + (f"{L['mean']:.0f} ({L['min']:.0f}–{L['max']:.0f})" if L else "–")
                + " |"
            )
        if c.get("size_given_floor"):
            g = c["size_given_floor"]
            lines += [
                "",
                f"Size given F3's trade floor (share of replications meeting it: {pct(g['share_meeting_floor'])}): "
                + ", ".join(f"{n} {pct(g[n])}" for n in METHODS),
                "",
            ]
        lines.append("")
    lines += [
        "## Family-wise error under Holm (4 members, global null)",
        "",
        "| Method | "
        + " | ".join(c["name"] for c in cells if c["group"] == "fwer")
        + " |",
        "|---|" + "---|" * sum(1 for c in cells if c["group"] == "fwer"),
    ]
    for name in METHODS:
        row = []
        for c in cells:
            if c["group"] != "fwer":
                continue
            fw = c["fwer"][name]
            row.append(f"{pct(fw['pooled'])} ({rng_str(fw['runs'])})")
        lines.append(f"| {name} | " + " | ".join(row) + " |")
    lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# --- the selection rule (PRE-STATEMENT section 8) ---------------------------------------------


def select(results: dict) -> dict:
    cells = results["cells"]
    deciding = [c for c in cells if c["deciding"]]
    fwer_cells = [c for c in cells if c["group"] == "fwer"]
    table = {}
    for name in ELIGIBLE:
        sizes = [c["methods"][name]["size"]["pooled"] for c in deciding]
        fw = [c["fwer"][name]["pooled"] for c in fwer_cells]
        powers = [
            c["methods"][name]["power_lambda"][str(LAMBDA_DECIDE)]["pooled"]
            for c in deciding
        ]
        cov_b = [c["methods"][name]["coverage"]["basic90"]["pooled"] for c in deciding]
        cov_p = [c["methods"][name]["coverage"]["pct90"]["pooled"] for c in deciding]
        worst_b = max(abs(v - 0.90) for v in cov_b)
        worst_p = max(abs(v - 0.90) for v in cov_p)
        interval = "percentile" if worst_b > worst_p + 0.05 else "basic"
        units = [
            c["methods"][name]["units"]["min"]
            for c in deciding
            if c["methods"][name]["units"]
        ]
        table[name] = {
            "max_size": max(sizes),
            "min_size": min(sizes),
            "max_fwer": max(fw),
            "valid": all(SIZE_BAND[0] <= s <= SIZE_BAND[1] for s in sizes)
            and all(f <= FWER_MAX for f in fw),
            "min_power": min(powers),
            "interval": interval,
            "worst_coverage_gap": worst_b if interval == "basic" else worst_p,
            "min_units": min(units) if units else float("nan"),
        }
    valid = [n for n in ELIGIBLE if table[n]["valid"]]
    out: Dict[str, object] = {"table": table, "valid": valid}
    if valid:
        best = max(table[n]["min_power"] for n in valid)
        tied = [n for n in valid if table[n]["min_power"] >= best - TIE]
        tied.sort(
            key=lambda n: (
                table[n]["worst_coverage_gap"],
                n in DATA_DRIVEN,
                -table[n]["min_units"],
            )
        )
        out.update({"selected": tied[0], "tied": tied, "fallback": False})
    else:
        least = min(ELIGIBLE, key=lambda n: table[n]["max_size"])
        ok = table[least]["max_size"] <= 0.10
        out.update({"selected": least if ok else None, "tied": [], "fallback": True})
    sel = out["selected"]
    if sel:
        floor = []
        for c in cells:
            if c["group"] != "floor":
                continue
            m = c["methods"][sel]
            floor.append(
                {
                    "cell": c["name"], "market": c["market"], "gen": c["gen"], "days": c["days"],
                    "units": m["units"]["mean"] if m["units"] else None,
                    "size": m["size"]["pooled"], "runs": m["size"]["runs"],
                }
            )  # fmt: skip
        windows = sorted({f["days"] for f in floor})
        base_ok = {
            w: all(
                f["size"] <= SIZE_BAND[1]
                for f in floor
                if f["market"] == "base" and f["days"] == w
            )
            for w in windows
        }
        chosen = None
        for w in windows:
            if all(base_ok[v] for v in windows if v >= w):
                chosen = w
                break
        units_at = (
            [f["units"] for f in floor if f["days"] == chosen and f["market"] == "base"]
            if chosen
            else []
        )
        out["floor"] = {
            "cells": floor,
            "window_days": chosen,
            "units": min(units_at) if units_at else None,
        }
    return out


# --- main ------------------------------------------------------------------------------------


def _parts(out_dir: str) -> str:
    """The folder of finished tasks, tied to this script's exact text (fail closed)."""
    import hashlib

    with open(os.path.abspath(__file__), "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    folder = os.path.join(out_dir, "parts")
    os.makedirs(folder, exist_ok=True)
    stamp = os.path.join(folder, "SCRIPT_SHA256")
    if os.path.exists(stamp):
        with open(stamp, encoding="utf-8") as fh:
            if fh.read().strip() != digest:
                raise SystemExit(
                    f"{folder} holds results of another version of the script: remove it"
                )
    else:
        with open(stamp, "w", encoding="utf-8") as fh:
            fh.write(digest)
    return folder


def _load(folder: str, name: str):
    import pickle

    path = os.path.join(folder, name + ".pkl")
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return pickle.load(fh)
    return None


def _save(folder: str, name: str, obj) -> None:
    import pickle

    tmp = os.path.join(folder, name + ".tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(obj, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, os.path.join(folder, name + ".pkl"))


def main(argv=None) -> int:
    global RUNS, REPS, ORACLE_REPS
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir")
    parser.add_argument(
        "--jobs", type=int, default=max(1, min(12, (os.cpu_count() or 2) - 2))
    )
    parser.add_argument(
        "--quick", action="store_true", help="a small run for testing the script"
    )
    parser.add_argument("--real-reps", type=int, default=20)
    args = parser.parse_args(argv)
    if args.quick:
        RUNS, REPS, ORACLE_REPS = 2, 20, 200
        args.real_reps = 4
    os.makedirs(args.out_dir, exist_ok=True)
    log_path = os.path.join(args.out_dir, "progress.log")
    t_start = time.time()

    def log(msg: str) -> None:
        line = f"[{time.time() - t_start:8.1f}s] {msg}"
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    log(f"start: runs={RUNS} reps={REPS} oracle={ORACLE_REPS} B={B} jobs={args.jobs}")
    checks = self_check()
    log(f"self-checks passed: {sorted(checks)}")
    cells, dropped = build_cells()
    log(f"{len(cells)} cells; dropped as infeasible: {dropped}")

    # 1. the oracle: theta_true and SD0 per cell and member
    oracle: Dict[int, Dict[str, dict]] = {}
    chunks = 10
    per = ORACLE_REPS // chunks
    parts = _parts(args.out_dir)
    live = [c for c in cells if c.alias < 0]
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results_o = []
        futs = {}
        for c in live:
            for k in range(chunks):
                got = _load(parts, f"oracle_{c.id}_{k}")
                if got is not None:
                    results_o.append(got)
                else:
                    futs[pool.submit(oracle_task, c, k, per)] = f"oracle_{c.id}_{k}"
        for f in as_completed(futs):
            _save(parts, futs[f], f.result())
            results_o.append(f.result())
        raw: Dict[int, Dict[str, dict]] = {}
        for r in results_o:
            for name, o in r["members"].items():
                dst = raw.setdefault(r["cell"], {}).setdefault(
                    name, {"net": [], "cd": [], "stats": []}
                )
                for key in dst:
                    dst[key].extend(o[key])
    for cid, members in raw.items():
        oracle[cid] = {}
        for name, o in members.items():
            net, cd = np.array(o["net"]), np.array(o["cd"])
            theta_true = float(net.sum() / cd.sum())
            theta = np.where(cd > 0, net / np.where(cd > 0, cd, 1), 0.0)
            st = np.array(o["stats"], dtype=float)
            oracle[cid][name] = {
                "theta_true": theta_true,
                "sd0": float(np.std(theta, ddof=1)),
                "theta_true_se": float(
                    np.std(net - theta_true * cd, ddof=1)
                    / (cd.mean() * math.sqrt(len(cd)))
                ),
                "reps": len(cd),
                "stats": {
                    **{
                        k: float(np.nanmean(st[:, i])) for i, k in enumerate(STAT_NAMES)
                    },
                    "rule_L_median": float(np.median(st[:, 5])),
                    "rule_L_min": float(np.min(st[:, 5])),
                    "rule_L_max": float(np.max(st[:, 5])),
                    "trades_min": float(np.min(st[:, 0])),
                    "trades_max": float(np.max(st[:, 0])),
                },
            }
    for c in cells:
        if c.alias >= 0:
            oracle[c.id] = oracle[c.alias]
    log("oracle done")

    # 2. the study, and the real-implementation check
    by_cell: Dict[int, List[dict]] = {}
    real: Dict[int, List[dict]] = {}
    check_cells = [
        c for c in cells
        if c.group == "core" and (
            (c.gen == "exo" and (c.n, c.h, c.market) in ((150, 30, "base"), (100, 60, "bear")))
            or (c.gen == "donchian" and c.market == "bear")
        )
    ]  # fmt: skip
    order = sorted(live, key=lambda c: -(4 if c.group == "fwer" else 1) * c.days)
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futs = {}
        for c in order:
            tt = {name: o["theta_true"] for name, o in oracle[c.id].items()}
            for r in range(RUNS):
                got = _load(parts, f"study_{c.id}_{r}")
                if got is not None:
                    by_cell.setdefault(c.id, []).append(got)
                else:
                    futs[pool.submit(study_task, c, r, REPS, tt)] = (
                        "study",
                        c,
                        f"study_{c.id}_{r}",
                    )
        for c in check_cells:
            for r in range(RUNS):
                got = _load(parts, f"real_{c.id}_{r}")
                if got is not None:
                    real.setdefault(c.id, []).append(got)
                else:
                    tt = oracle[c.id]["A"]["theta_true"]
                    futs[pool.submit(real_check_task, c, r, args.real_reps, tt)] = (
                        "real",
                        c,
                        f"real_{c.id}_{r}",
                    )
        log(
            f"{len(futs)} tasks to run, {sum(len(v) for v in by_cell.values()) + sum(len(v) for v in real.values())} loaded"
        )
        done = 0
        for f in as_completed(futs):
            kind, c, name = futs[f]
            res = f.result()
            _save(parts, name, res)
            done += 1
            (by_cell if kind == "study" else real).setdefault(c.id, []).append(res)
            if done % 20 == 0 or done == len(futs):
                log(
                    f"{done}/{len(futs)} tasks ({kind} {c.name} run {res['run']}: {res['seconds']:.0f}s)"
                )
    for c in cells:
        if c.alias >= 0:
            by_cell[c.id] = by_cell[c.alias]

    # 3. aggregate
    results = {
        "design": {
            "seed": SEED, "runs": RUNS, "reps_per_run": REPS, "oracle_reps": ORACLE_REPS, "B": B,
            "alpha": ALPHA, "size_band": SIZE_BAND, "fwer_max": FWER_MAX, "lambda_decide": LAMBDA_DECIDE,
            "lambdas": LAMBDAS, "deltas": DELTAS, "days": N_DAYS, "coins": COINS, "warm": WARM,
            "fee": FEE, "allowance": ALLOWANCE, "cost_multiplier": M_COST, "cap": CAP,
            "methods": METHODS, "quick": bool(args.quick),
        },  # fmt: skip
        "self_checks": checks,
        "dropped_cells": dropped,
        "cells": [],
    }
    for c in cells:
        parts = sorted(by_cell[c.id], key=lambda r: r["run"])
        entry = {**asdict(c), "name": c.name, "oracle": oracle[c.id]}
        sd0 = oracle[c.id]["A"]["sd0"]
        if c.group == "fwer":
            fw = np.concatenate(
                [p["fwer"] for p in parts]
            )  # (reps, members, methods, 2)
            runs = np.concatenate([np.full(len(p["fwer"]), p["run"]) for p in parts])
            members = parts[0]["members"]
            entry["members"] = members
            entry["fwer"] = {}
            entry["member_size"] = {}
            for j, name in enumerate(METHODS):
                ps = fw[:, :, j, 1]
                anyrej = np.array([any(stats.holm(list(row), ALPHA)) for row in ps])
                entry["fwer"][name] = {
                    "pooled": float(anyrej.mean()),
                    "runs": [float(anyrej[runs == r].mean()) for r in range(RUNS)],
                }
                entry["member_size"][name] = {
                    m: float(np.mean(ps[:, i] <= ALPHA)) for i, m in enumerate(members)
                }
            th = fw[:, :, 0, 0]
            entry["theta_correlation"] = np.corrcoef(th.T).tolist()
        else:
            out = np.concatenate([p["out"] for p in parts])
            runs = np.concatenate([np.full(len(p["out"]), p["run"]) for p in parts])
            st = np.concatenate([p["stats"] for p in parts])
            entry["methods"] = cell_metrics(out, runs, sd0)
            entry["size_given_floor"] = (
                size_given_floor(out, st, c.days) if c.group == "core" else None
            )
            entry["ideal_power_lambda"] = {
                str(lam): 1 - NormalDist().cdf(Z95 - lam) for lam in LAMBDAS
            }
            entry["ideal_power_delta"] = {
                str(dl): 1 - NormalDist().cdf(Z95 - dl / sd0) for dl in DELTAS
            }
            mism = 0
            for j in range(len(METHODS) - 1):
                mism += int(
                    np.sum(
                        (out[:, j, F["p0"]] <= ALPHA)
                        != (out[:, j, F["theta"]] > out[:, j, F["t05"]])
                    )
                )
            if mism:
                raise AssertionError(f"{c.name}: p and threshold disagree {mism} times")
        entry["seconds"] = float(sum(p["seconds"] for p in parts))
        results["cells"].append(entry)
    real_out = []
    for c in check_cells:
        parts = real[c.id]
        rp = np.concatenate([p["real"] for p in parts])
        fp = np.concatenate([p["fast"] for p in parts])
        real_out.append(
            {
                "cell": c.name,
                "reps": int(len(rp)),
                "methods": {
                    name: {
                        "size_real": float(np.mean(rp[:, j] <= ALPHA)),
                        "size_fast": float(np.mean(fp[:, j] <= ALPHA)),
                        "same_decision": float(
                            np.mean((rp[:, j] <= ALPHA) == (fp[:, j] <= ALPHA))
                        ),
                        "mean_abs_p_diff": float(np.mean(np.abs(rp[:, j] - fp[:, j]))),
                    }
                    for j, name in enumerate(REAL_CHECK)
                },
                "seconds": float(sum(p["seconds"] for p in parts)),
            }
        )
    results["real_check"] = real_out
    results["selection"] = select(results)
    results["runtime_seconds"] = time.time() - t_start
    with open(os.path.join(args.out_dir, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1, default=float)
    write_tables(results, os.path.join(args.out_dir, "tables.md"))
    log(
        f"selected: {results['selection'].get('selected')}; floor: {results['selection'].get('floor', {}).get('window_days')}"
    )
    log(f"done in {results['runtime_seconds']:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
