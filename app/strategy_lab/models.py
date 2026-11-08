"""
The model cells of the strategy-against-model matrix (FDS-SR-001 section 5.9).

**The strategy and its exits are held constant.** Every cell starts from the same
candidate trades (``Simulation.candidates()``): a model can only veto a trade, or shrink
its size, and never moves an entry or an exit. A trade a cell does not veto is the same
trade, with the same exit, in every cell.

* **A generic forecast filter** (``forecast_filter``): a lab model's out-of-fold
  probabilities (FDS-MH-001, ``probabilities/<key>.npz``) at each trade's decision hour
  (the close of the bar that decided it, which is the entry fill's time). The lab does
  not save its per-fold thresholds, so the threshold is a declared, causal rule: the
  ``q``-quantile of every probability the model gave before the start of the decision's
  calendar month, all coins pooled. A trade whose hour has no probability, or that comes
  before ``min_history`` probabilities exist, is not assessable and is never vetoed.
* **A strategy-specific meta-model** (``meta_filter``): FDS-SIG-004's F_P or F_PV on this
  strategy's own trades (``signal_fusion.meta.walk_forward``, ``signal_fusion.labels``):
  M from the trade's gross return at the evaluated fee, Platt calibration strictly out of
  fold, the payoff tables from each fold's training trades, and a veto where the
  expected value is at most 0. With fewer than 200 events or 200 non-events among its
  scored trades it is marked not assessable (FDS-SIG-004 D16).
* **The baselines:** R3 vetoes the same number of trades per coin at random, among the
  trades the filter could assess and its own path could take; R3s gives the shrink's
  scales in a random order (``signal_fusion.evaluation.baselines``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from signal_fusion import labels as lb
from signal_fusion import meta
from signal_fusion import volatility as vol
from signal_fusion.evaluation import baselines as sfb
from signal_fusion.evaluation.replay import Account, Costs, Paths
from strategy_lab.candidates import Trade
from strategy_lab.simulate import Simulation

MIN_EVENTS = 200  # FDS-SIG-004 D16: events and non-events a cell needs
MIN_HISTORY = 1000  # probabilities before a generic filter's threshold is defined

Probabilities = Mapping[str, Tuple[Sequence[int], Sequence[float]]]


@dataclass
class Filter:
    """One cell's decision per trade."""

    name: str
    veto: np.ndarray  # True where the cell vetoes the trade
    assessable: np.ndarray  # True where the cell could decide
    p: np.ndarray  # the probability it used (NaN where none)
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def enough(self) -> bool:
        return bool(self.detail.get("enough", True))


def label_trades(trades: Sequence[Trade]) -> List[lb.Trade]:
    """The candidate trades as FDS-SIG-004's labelled opportunities."""
    return [
        lb.Trade(t.coin, t.entry_s, t.exit_s, t.entry_price, t.exit_price, t.forced)
        for t in trades
    ]


def development_folds() -> Tuple[Tuple[int, int], ...]:
    """FDS-MH-001's 3-month development folds (12 months' warm-up from 2021-01-01, to
    the lockbox's start on 2025-05-06)."""
    from model_lab.walkforward import make_calendar

    return make_calendar("2021-01-01", "2026-11-06").folds


def lab_probabilities(batch_id: str, key: str) -> Dict[str, Tuple[Any, Any]]:
    """A lab contestant's saved probabilities (FDS-MH-001 amendment 1)."""
    from model_lab.batch import read_probabilities

    return read_probabilities(batch_id, key)


def _month_start(t: int) -> int:
    ts = pd.Timestamp(int(t), unit="s", tz="UTC")
    return int(pd.Timestamp(year=ts.year, month=ts.month, day=1, tz="UTC").timestamp())


def forecast_filter(
    trades: Sequence[Trade],
    probabilities: Probabilities,
    q: float,
    name: str,
    min_history: int = MIN_HISTORY,
) -> Filter:
    """A lab model's probabilities as a veto (see the module docstring)."""
    times = []
    values = []
    lookup: Dict[str, Dict[int, float]] = {}
    for coin, (close_s, p) in probabilities.items():
        close_s = np.asarray(close_s, dtype=np.int64)
        p = np.asarray(p, dtype=float)
        ok = np.isfinite(p)
        times.append(close_s[ok])
        values.append(p[ok])
        lookup[coin] = dict(zip(close_s[ok].tolist(), p[ok].tolist()))
    all_t = np.concatenate(times) if times else np.zeros(0, dtype=np.int64)
    all_p = np.concatenate(values) if values else np.zeros(0)
    order = np.argsort(all_t, kind="stable")
    all_t, all_p = all_t[order], all_p[order]

    thresholds: Dict[int, float] = {}
    n = len(trades)
    p_at = np.full(n, np.nan)
    threshold = np.full(n, np.nan)
    for i, t in enumerate(trades):
        p_at[i] = lookup.get(t.coin, {}).get(int(t.entry_s), np.nan)
        month = _month_start(t.entry_s)
        if month not in thresholds:
            k = int(np.searchsorted(all_t, month, side="left"))
            thresholds[month] = (
                float(np.quantile(all_p[:k], q)) if k >= min_history else np.nan
            )
        threshold[i] = thresholds[month]
    assessable = np.isfinite(p_at) & np.isfinite(threshold)
    veto = assessable & (p_at < threshold)
    return Filter(
        name,
        veto,
        assessable,
        p_at,
        {"rule": f"q={q} of the probabilities before the decision's month", "q": q},
    )


def meta_filter(
    trades: Sequence[Trade],
    x: np.ndarray,
    folds: Sequence[Tuple[int, int]],
    fee: float,
    name: str,
    allowance: float = lb.EVALUATED_ALLOWANCE,
    tercile: Optional[np.ndarray] = None,
) -> Filter:
    """FDS-SIG-004's meta-model on this strategy's own trades (module docstring).
    ``x`` holds each trade's features at its decision hour; ``tercile`` its σ̂ tercile
    (0 to 2; pooled payoffs when not given)."""
    gross, label = lb.label_rows(label_trades(trades), fee)
    signal_s = np.array([t.entry_s for t in trades], dtype=np.int64)
    exit_s = np.array([t.exit_s for t in trades], dtype=np.int64)
    terc = (
        np.asarray(tercile, dtype=int)
        if tercile is not None
        else np.full(len(trades), -1, dtype=int)
    )
    wf = meta.walk_forward(x, label, signal_s, exit_s, folds)
    ev = np.full(len(trades), np.nan)
    for k, (a, _b) in enumerate(folds):
        rows = (wf.fold == k) & np.isfinite(wf.calibrated)
        if not rows.any():
            continue
        train = (label >= 0) & (exit_s <= a)
        table = lb.payoffs(gross[train], label[train], terc[train])
        win = np.array([table.at(int(c))[0] for c in terc[rows]])
        loss = np.array([table.at(int(c))[1] for c in terc[rows]])
        ev[rows] = lb.expected_value(wf.calibrated[rows], win, loss, fee, allowance)
    assessable = np.isfinite(ev)
    scored = assessable & (label >= 0)
    events = int(np.sum(label[scored] == 1))
    non_events = int(np.sum(label[scored] == 0))
    return Filter(
        name,
        assessable & (ev <= 0),
        assessable,
        wf.calibrated,
        {
            "events": events,
            "non_events": non_events,
            "enough": events >= MIN_EVENTS and non_events >= MIN_EVENTS,
            "fits": wf.fits,
            "fee": fee,
            "allowance": allowance,
        },
    )


def shrink_scales(sigma_hat: Sequence[float], sigma_ref: float) -> np.ndarray:
    """FDS-SIG-004's volatility shrink per trade, min(1, σ_ref / σ̂); 1 where σ̂ is
    missing (evaluated as fail-open, like the shrink in Log only)."""
    s = vol.shrink(np.asarray(sigma_hat, dtype=float), sigma_ref)
    return np.where(np.isfinite(s), s, 1.0)


def cell(
    sim: Simulation,
    trades: Sequence[Trade],
    costs: Costs,
    account: Account,
    filt: Optional[Filter] = None,
    scale: Optional[np.ndarray] = None,
    **kw,
) -> Paths:
    """One cell's path: the candidate trades with the cell's veto or scale."""
    veto = None if filt is None else filt.veto[None, :]
    sc = None if scale is None else np.asarray(scale, dtype=float)[None, :]
    return sim.replay(trades, costs, account, veto=veto, scale=sc, **kw)


def eligible_assessable(
    sim: Simulation,
    trades: Sequence[Trade],
    filt: Filter,
    costs: Costs,
    account: Account,
) -> List[int]:
    """The trades the filter could assess and its own path could take (flat, with the
    cash there): R3's candidates (FDS-SIG-004 section 6.1)."""
    path = cell(sim, trades, costs, account, filt, detail=True)
    return [i for i in path.eligible() if filt.assessable[i]]


def random_vetoes(
    trades: Sequence[Trade],
    filt: Filter,
    candidates: Sequence[int],
    seed: int,
    run: int,
    draws: int,
) -> np.ndarray:
    """R3: per coin, as many vetoes as the filter made among ``candidates``, at random."""
    coins = [t.coin for t in trades]
    counts = sfb.veto_counts(coins, candidates, np.flatnonzero(filt.veto).tolist())
    return sfb.r3(coins, candidates, counts, len(trades), seed, run, draws)


def random_scales(
    trades: Sequence[Trade],
    scales: Sequence[float],
    candidates: Sequence[int],
    seed: int,
    run: int,
    draws: int,
) -> np.ndarray:
    """R3s: the shrink's own scales at ``candidates``, in a random order."""
    coins = [t.coin for t in trades]
    return sfb.r3s(coins, candidates, scales, len(trades), seed, run, draws)
