"""
A round's rows, both Holm procedures, the verdicts, and confirmation rounds
(FDS-SIG-001 sections 7.6, 8 and 9).

* **The family** is every (candidate, exchange, coin, timeframe, statistic) the round
  registered: F = 2 x the registered rows. Rows later NOT ASSESSABLE stay in F, and each
  NOT ASSESSABLE (row, statistic) enters the forward and the opposite-direction Holm with
  p = 1.
* **A row's verdict** (7.6): NOT ASSESSABLE when n < 1,000 or both statistics are below
  their floors; otherwise PASS (provisional) when either statistic survives the forward
  Holm at 5% and meets its extra condition; otherwise WORSE when either survives the
  opposite-direction Holm; otherwise FAIL. Rows are never pooled, averaged or counted
  into a verdict (8.2).
* **Checked twice.** ``recheck_verdicts`` re-derives every verdict another way (Holm by
  its step-down thresholds rather than adjusted p-values, the floors from the counts,
  the rule written out again), as ``backtest.model_eval.recheck_verdict`` does, and the
  report asserts the two agree.
* **Confirmation** (8.3): one member per provisional (row, statistic), Holm at 5% over
  those members, CONFIRMED only when a member survives and meets its extra condition on
  the confirmation window; otherwise, below a floor included, FAIL (not confirmed).
* **Seeds.** The bootstrap of row i (in registration order) and stream s uses
  ``numpy.random.SeedSequence(seed, spawn_key=(i, s))``: s = 0 the hit rate, 1 the
  two-sided hit rate's opposite direction, 2 the magnitude; the two-sided hit rate's
  minimum detectable effect uses seeds ``seed + 1_000_000 + 100 i + r`` for its runs r.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from signal_audit import stats as st
from signal_audit.pairs import RowPairs

PASS = "PASS (provisional)"
FAIL = "FAIL"
WORSE = "WORSE"
NOT_ASSESSABLE = "NOT ASSESSABLE"
CONFIRMED = "CONFIRMED"
NOT_CONFIRMED = "FAIL (not confirmed)"
VERDICTS = (PASS, FAIL, WORSE, NOT_ASSESSABLE)

HIT_STREAM, WORSE_STREAM, MAGNITUDE_STREAM = 0, 1, 2
MDE_SEED_OFFSET = 1_000_000


@dataclass(frozen=True)
class RowKey:
    candidate: str
    exchange: str
    coin: str
    timeframe: str

    def text(self) -> str:
        return f"{self.candidate} {self.coin} {self.timeframe} ({self.exchange})"

    def to_dict(self) -> Dict[str, str]:
        return dict(self.__dict__)


@dataclass
class Row:
    key: RowKey
    kind: str
    data: RowPairs
    counts: st.Counts
    blocks: st.Blocks
    results: Dict[str, st.StatisticResult]
    holm: Dict[str, float] = field(default_factory=dict)  # forward adjusted p
    holm_opposite: Dict[str, float] = field(default_factory=dict)
    survives: Dict[str, bool] = field(default_factory=dict)
    survives_opposite: Dict[str, bool] = field(default_factory=dict)
    verdict: Optional[str] = None
    passing: List[str] = field(default_factory=list)  # statistics that pass

    def not_assessable(self) -> bool:
        return self.counts.n < st.MIN_CALLS or not any(
            r.assessable for r in self.results.values()
        )


def _rng(seed: int, row: int, stream: int) -> np.random.Generator:
    return np.random.default_rng(
        np.random.SeedSequence(int(seed), spawn_key=(row, stream))
    )


def evaluate_row(
    index: int,
    key: RowKey,
    data: RowPairs,
    draws: int,
    seed: int,
) -> Row:
    """One row's counts, block length and both statistics' p-values."""
    p = data.pairs
    c = st.counts(p)
    blocks = st.block_length(p)
    results = {
        st.HIT: st.evaluate_statistic(
            p,
            st.HIT,
            blocks,
            draws,
            _rng(seed, index, HIT_STREAM),
            _rng(seed, index, WORSE_STREAM),
        ),
        st.MAGNITUDE: st.evaluate_statistic(
            p, st.MAGNITUDE, blocks, draws, _rng(seed, index, MAGNITUDE_STREAM)
        ),
    }
    return Row(key, p.kind, data, c, blocks, results)


def apply_holm(rows: Sequence[Row], family_error: float = st.FAMILY_ERROR) -> None:
    """Both Holm procedures over the family of every (row, statistic)."""
    members = [(r, s) for r in rows for s in st.STATISTICS]
    forward = st.holm_adjusted([r.results[s].p_holm for r, s in members])
    opposite = st.holm_adjusted([r.results[s].q_holm for r, s in members])
    for (r, s), a, b in zip(members, forward, opposite):
        r.holm[s] = a
        r.holm_opposite[s] = b
        r.survives[s] = a <= family_error
        r.survives_opposite[s] = b <= family_error


def verdict_of(row: Row) -> Tuple[str, List[str]]:
    """Section 7.6, from the Holm results already applied."""
    if row.not_assessable():
        return NOT_ASSESSABLE, []
    passing = [
        s
        for s in st.STATISTICS
        if row.results[s].assessable and row.survives[s] and row.results[s].extra_met
    ]
    if passing:
        return PASS, passing
    if any(
        row.results[s].assessable and row.survives_opposite[s] for s in st.STATISTICS
    ):
        return WORSE, []
    return FAIL, []


def add_power(
    rows: Sequence[Row],
    family_size: int,
    seed: int,
    mde_sims: int,
    mde_replicates: int,
) -> None:
    """Every statistic's minimum detectable effect and 95% upper bound (section 9)."""
    for i, row in enumerate(rows):
        p = row.data.pairs
        for s in st.STATISTICS:
            res = row.results[s]
            res.upper_95 = st.upper_bound_95(p, res)
            if p.kind == st.TWO_SIDED and s == st.HIT:
                c = row.counts
                if c.n >= 2 and c.q is not None:
                    detail = st.mde_two_sided_hit(
                        c.eligible,
                        c.n,
                        c.q,
                        c.p_c,
                        family_size,
                        p.timeframe,
                        mde_sims,
                        mde_replicates,
                        seed + MDE_SEED_OFFSET + 100 * i,
                    )
                    res.mde = detail["mde"]
                    res.mde_detail = detail
            else:
                res.mde = st.mde_closed_form(p, res, family_size)


@dataclass
class RoundResult:
    rows: List[Row]
    family_size: int
    family_error: float
    draws: int
    seed: int


def evaluate_round(
    rows_data: Sequence[Tuple[RowKey, RowPairs]],
    draws: int,
    seed: int,
    family_error: float = st.FAMILY_ERROR,
    mde_sims: int = 0,
    mde_replicates: int = 0,
) -> RoundResult:
    """Every registered row, in registration order. F = 2 x len(rows_data)."""
    rows = [evaluate_row(i, k, d, draws, seed) for i, (k, d) in enumerate(rows_data)]
    F = 2 * len(rows)
    apply_holm(rows, family_error)
    for row in rows:
        row.verdict, row.passing = verdict_of(row)
    if mde_sims > 0 and mde_replicates > 0:
        add_power(rows, F, seed, mde_sims, mde_replicates)
    else:
        for row in rows:
            for s in st.STATISTICS:
                res = row.results[s]
                res.upper_95 = st.upper_bound_95(row.data.pairs, res)
                if not (row.kind == st.TWO_SIDED and s == st.HIT):
                    res.mde = st.mde_closed_form(row.data.pairs, res, F)
    return RoundResult(rows, F, family_error, draws, seed)


# --- the verdicts again, derived another way --------------------------------------------


def _step_down_survivors(ps: Sequence[float], alpha: float) -> List[bool]:
    """Holm by its thresholds: walk the p-values from the smallest, rejecting while
    p_(i) <= alpha / (F - i + 1) (i from 1), and stop at the first that is not."""
    F = len(ps)
    ranked = sorted(range(F), key=lambda i: (ps[i], i))
    out = [False] * F
    i = 1
    for idx in ranked:
        if ps[idx] <= alpha / (F - i + 1):
            out[idx] = True
            i += 1
        else:
            break
    return out


def recheck_verdicts(result: RoundResult) -> List[str]:
    """Every row's verdict re-derived from the numbers, independently of
    ``verdict_of``: the floors from the counts and blocks, the p-value entering Holm
    as the largest registered component, Holm by its thresholds."""
    rows = result.rows
    alpha = result.family_error

    def forward_p(row: Row, s: str) -> float:
        r = row.results[s]
        if not _assessable_again(row, s):
            return 1.0
        parts = [r.bootstrap.p_upper, r.batch.p_upper]
        if s == st.HIT:
            parts.append(r.p_exact)
        return max(parts)

    def opposite_p(row: Row, s: str) -> float:
        r = row.results[s]
        if not _assessable_again(row, s):
            return 1.0
        parts = [r.bootstrap_opposite.p_lower, r.batch_opposite.p_lower]
        if s == st.HIT:
            parts.append(r.q_exact)
        return max(parts)

    members = [(row, s) for row in rows for s in (st.HIT, st.MAGNITUDE)]
    fwd = _step_down_survivors([forward_p(r, s) for r, s in members], alpha)
    opp = _step_down_survivors([opposite_p(r, s) for r, s in members], alpha)
    survive = {(id(r), s): v for (r, s), v in zip(members, fwd)}
    survive_opp = {(id(r), s): v for (r, s), v in zip(members, opp)}
    out = []
    for row in rows:
        hit_ok = _assessable_again(row, st.HIT)
        mag_ok = _assessable_again(row, st.MAGNITUDE)
        if row.counts.n < 1000 or not (hit_ok or mag_ok):
            out.append(NOT_ASSESSABLE)
            continue
        passed = False
        for s, ok in ((st.HIT, hit_ok), (st.MAGNITUDE, mag_ok)):
            if ok and survive[(id(row), s)] and _extra_again(row, s):
                passed = True
        if passed:
            out.append(PASS)
            continue
        worse = any(
            ok and survive_opp[(id(row), s)]
            for s, ok in ((st.HIT, hit_ok), (st.MAGNITUDE, mag_ok))
        )
        out.append(WORSE if worse else FAIL)
    return out


def _assessable_again(row: Row, s: str) -> bool:
    c, b = row.counts, row.blocks
    if c.n < 1000 or b.K < 30:
        return False
    if row.kind == st.TWO_SIDED and s == st.HIT:
        return (c.m or 0) >= 200
    if row.kind != st.TWO_SIDED:
        return c.abstained >= 200
    return True


def _extra_again(row: Row, s: str) -> bool:
    p = row.data.pairs
    called = p.calls != 0
    if not called.any():
        return False
    if row.kind == st.TWO_SIDED:
        if s == st.HIT:
            return True
        return float(np.sum(p.calls[called] * p.ret[called])) > 0.0
    if s == st.HIT:
        right = p.up[called] if row.kind == st.UP_ONLY else 1 - p.up[called]
        return 2 * int(right.sum()) > int(called.sum())
    total = float(np.sum(p.ret[called]))
    return total > 0.0 if row.kind == st.UP_ONLY else total < 0.0


def check_verdicts(result: RoundResult) -> None:
    """Assert each verdict against the numbers, re-derived independently."""
    again = recheck_verdicts(result)
    for row, v in zip(result.rows, again):
        if row.verdict != v:
            raise AssertionError(
                f"{row.key.text()}: verdict {row.verdict} but re-derived as {v}"
            )


# --- confirmation (section 8.3) ---------------------------------------------------------


@dataclass(frozen=True)
class Member:
    """A provisional (row, statistic) from an earlier round, re-tested unchanged."""

    key: RowKey
    statistic: str
    kind: str
    candidate_registration: Mapping[str, Any]  # its rule, parameters, kind, inputs


@dataclass
class ConfirmationResult:
    member: Member
    result: st.StatisticResult
    counts: st.Counts
    blocks: st.Blocks
    holm: float
    outcome: str


def confirm(
    members: Sequence[Member],
    data: Sequence[RowPairs],
    draws: int,
    seed: int,
    family_error: float = st.FAMILY_ERROR,
) -> List[ConfirmationResult]:
    """The confirmation round: Holm at 5% over exactly the provisional members, each
    CONFIRMED only when it survives and meets its extra condition on the new window."""
    if len(members) != len(data):
        raise ValueError("one data set per member")
    evaluated = []
    for i, (m, d) in enumerate(zip(members, data)):
        if d.pairs.kind != m.kind:
            raise ValueError(f"{m.key.text()}: its kind changed")
        p = d.pairs
        c = st.counts(p)
        blocks = st.block_length(p)
        stream = HIT_STREAM if m.statistic == st.HIT else MAGNITUDE_STREAM
        res = st.evaluate_statistic(
            p,
            m.statistic,
            blocks,
            draws,
            _rng(seed, i, stream),
            _rng(seed, i, WORSE_STREAM),
        )
        evaluated.append((m, res, c, blocks))
    adjusted = st.holm_adjusted([r.p_holm for _m, r, _c, _b in evaluated])
    out = []
    for (m, res, c, blocks), a in zip(evaluated, adjusted):
        ok = res.assessable and a <= family_error and res.extra_met
        out.append(
            ConfirmationResult(m, res, c, blocks, a, CONFIRMED if ok else NOT_CONFIRMED)
        )
    return out
