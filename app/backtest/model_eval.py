"""
The pre-declared evaluation of STRAT-003 (docs/dev/BACKTEST-REPORT-model-1.md), as pure
functions the report generator calls: decision records and their counts, the verdict
rule, an independent re-derivation of it, and the verdict line.

Every rule here is the header's; nothing is chosen from results.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from pattern_model import TIMEFRAMES
from strategies.runner import Decision, StrategyRunner

BEFORE_WEEK = tuple(tf for tf in TIMEFRAMES if tf != "1week")
EDGE = "evidence of an edge"
NO_EDGE = "no evidence of an edge"
RANK_NEEDED = 95.0
COMBINATIONS_NEEDED = 3
DATA_HOLDS = ("BARS_MISSING", "TIMEFRAME_UNKNOWN")  # a data or set-up problem

# TRAINER-AUDIT.md 11.8, quoted in every verdict line
AUDIT_11_8 = (
    "1-hour hit rate vs share of closes that rose, BTC 50.3% vs 50.4% and ETH 51.3% vs "
    "51.0% (n = 5,257 pairs each)."
)
TEST_A_HOLDOUT = ("2025-02-05T12:00:00Z", "2025-08-16T04:00:00Z")


class RecordingRunner(StrategyRunner):
    """A ``StrategyRunner`` that keeps every decision's action, reason and the
    strategy's per-timeframe activity (``active_<tf>``): the counts come from these."""

    def __init__(self, strategy, overlays=()) -> None:
        super().__init__(strategy, overlays)
        self.records: List[Dict[str, Any]] = []

    def evaluate(self, candles, position, symbol) -> Decision:
        decision = super().evaluate(candles, position, symbol)
        self.records.append(
            {
                "bar_time": decision.bar_time,
                "action": decision.action.value,
                "reason": decision.reason,
                "active": {
                    k: float(v)
                    for k, v in decision.indicators.items()
                    if k.startswith("active_")
                },
            }
        )
        return decision


def hold_counts(records: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Decisions held because the rule could not be applied, by class (with each
    missing timeframe's count)."""
    out: Dict[str, Any] = {
        "BARS_MISSING": 0,
        "TIMEFRAME_UNKNOWN": 0,
        "BOUNDS_NOT_CONVERGED": 0,
        "by_reason": {},
    }
    for r in records:
        if r["action"] != "HOLD":
            continue
        reason = r["reason"]
        if reason.startswith("BARS_MISSING"):
            out["BARS_MISSING"] += 1
        elif reason == "TIMEFRAME_UNKNOWN":
            out["TIMEFRAME_UNKNOWN"] += 1
        elif reason == "BOUNDS_NOT_CONVERGED":
            out["BOUNDS_NOT_CONVERGED"] += 1
        else:
            continue
        out["by_reason"][reason] = out["by_reason"].get(reason, 0) + 1
    return out


def data_holds(counts: Mapping[str, Any]) -> int:
    """Holds that make a window "not assessable" (missing bars, unknown timeframe)."""
    return int(sum(counts[k] for k in DATA_HOLDS))


def quirk_counts(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """E1 and E2 over a window's decisions. E1: decisions with all seven activities
    known and two or more of 1hour..1day inactive. E2: gap-pass limit holds. The
    denominator is every decision (one per bar but the window's last)."""
    decisions = len(records)
    e1 = 0
    for r in records:
        active = r["active"]
        if len(active) != len(TIMEFRAMES):
            continue  # held before all seven predictions were made
        inactive = sum(1 for tf in BEFORE_WEEK if active[f"active_{tf}"] == 0.0)
        if inactive >= 2:
            e1 += 1
    e2 = sum(
        1
        for r in records
        if r["action"] == "HOLD" and r["reason"] == "BOUNDS_NOT_CONVERGED"
    )
    return {
        "decisions": decisions,
        "e1": e1,
        "e1_share": (e1 / decisions) if decisions else None,
        "e2": e2,
    }


def median(values: Sequence[float]) -> float:
    """The median; for an even count, the mean of the two middle values."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("median of nothing")
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _number(value, what: str) -> float:
    if value is None:
        raise ValueError(f"{what} is undefined; the verdict cannot be computed")
    return float(value)


def verdict(
    test_a: Mapping[Tuple[str, str], Mapping[str, Any]],
    test_b: Sequence[Mapping[str, Any]],
    expected_windows: int,
) -> Dict[str, Any]:
    """The header's verdict rule.

    ``test_a``: per combination, from the out-of-sample run without overlays:
    ``vs_bh`` (points), ``data_holds`` (missing-bar or unknown-timeframe holds) and
    ``rank`` (the random-baseline rank without overlays; ``None`` when there is none).
    ``test_b``: one entry per window without overlays: ``combination``, ``vs_bh``,
    ``data_holds``."""
    if len(test_b) != expected_windows:
        raise ValueError(f"{len(test_b)} Test B windows, expected {expected_windows}")
    c1_combos = sorted(
        c
        for c, a in test_a.items()
        if a["data_holds"] == 0 and _number(a["vs_bh"], f"Test A {c} vs B&H") > 0
    )
    not_assessable_a = sorted(c for c, a in test_a.items() if a["data_holds"] > 0)
    c1 = len(c1_combos) >= COMBINATIONS_NEEDED
    c2_failing = sorted(
        c
        for c in c1_combos
        if test_a[c]["rank"] is None or test_a[c]["rank"] < RANK_NEEDED
    )
    c2 = not c2_failing
    values = [_number(w["vs_bh"], f"Test B {w['combination']} vs B&H") for w in test_b]
    b_holds = sum(int(w["data_holds"]) for w in test_b)
    pooled = median(values)
    c3 = b_holds == 0 and pooled > 0
    by_combination: Dict[Tuple[str, str], List[float]] = {}
    for w, v in zip(test_b, values):
        by_combination.setdefault(tuple(w["combination"]), []).append(v)
    return {
        "criterion_1": c1,
        "criterion_1_combinations": c1_combos,
        "criterion_2": c2,
        "criterion_2_failing": c2_failing,
        "criterion_3": c3,
        "test_a_not_assessable": not_assessable_a,
        "test_b_data_holds": b_holds,
        "pooled_median": pooled,
        "pooled_worst": min(values),
        "combination_medians": {c: median(v) for c, v in by_combination.items()},
        "verdict": EDGE if (c1 and c2 and c3) else NO_EDGE,
    }


def recheck_verdict(
    test_a: Mapping[Tuple[str, str], Mapping[str, Any]],
    test_b: Sequence[Mapping[str, Any]],
) -> str:
    """The verdict again, derived differently (counted loops, a sorted list's middle,
    the header's thresholds written out rather than shared), for the report to check
    against ``verdict``."""
    beat = []
    for combo in test_a:
        a = test_a[combo]
        if a["data_holds"] > 0:
            continue
        if float(a["vs_bh"]) > 0.0:
            beat.append(combo)
    ok1 = len(beat) >= 3  # at least 3 of the 4
    ok2 = True
    for combo in beat:
        rank = test_a[combo]["rank"]
        if rank is None or not rank >= 95.0:
            ok2 = False
    holds = 0
    xs = []
    for w in test_b:
        holds += int(w["data_holds"])
        xs.append(float(w["vs_bh"]))
    xs.sort()
    n = len(xs)
    middle = xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])
    ok3 = holds == 0 and middle > 0.0
    return EDGE if ok1 and ok2 and ok3 else NO_EDGE


def _pct(value) -> Optional[str]:
    return None if value is None else f"{100.0 * float(value):.1f}%"


def manifest_values(manifest: Mapping[str, Any]) -> Dict[str, str]:
    """The verdict line's three values for one Test A model: its validation fit's
    1-hour hit rate, up share and n, or "n/a (reason)" in each missing place."""
    validation = manifest.get("validation") or {}
    metrics = (manifest.get("validation_metrics") or {}).get("1hour") or {}
    reason = validation.get("reason") or metrics.get("error") or "no value"
    ok = validation.get("status") == "ok"
    hit = _pct(metrics.get("direction_hit_rate")) if ok else None
    up = _pct(metrics.get("up_share_of_considered")) if ok else None
    n = metrics.get("direction_considered") if ok else None
    na = f"n/a ({reason})"
    return {
        "hit": hit if hit is not None else na,
        "up": up if up is not None else na,
        "n": f"{int(n):,}" if n is not None else na,
    }


def check_test_a_holdout(
    manifest: Mapping[str, Any], holdout: Tuple[str, str] = TEST_A_HOLDOUT
) -> None:
    """Each Test A manifest's held-out slice must be the one the verdict line names."""
    validation = manifest.get("validation") or {}
    got = (validation.get("holdout_start"), validation.get("holdout_end"))
    # checked whenever the trainer wrote the dates (it does when validation is
    # unavailable too); skipped only when it wrote neither
    if got != (None, None) and got != tuple(holdout):
        raise ValueError(
            f"model {manifest.get('model_id')}: held-out slice {got}, but the verdict "
            f"line names {tuple(holdout)}"
        )


def _when(stamp: str) -> str:
    """``2025-02-05T12:00:00Z`` as ``2025-02-05 12:00``."""
    return f"{stamp[:10]} {stamp[11:16]}"


def verdict_line(
    result: str,
    test_a_manifests: Mapping[str, Mapping[str, Any]],
    not_assessable: Sequence[Tuple[str, str, int]] = (),
    gap_limit: Sequence[Tuple[str, str, int]] = (),
    holdout: Tuple[str, str] = TEST_A_HOLDOUT,
) -> str:
    """The header's verdict line. ``test_a_manifests`` is ``{"BTC": manifest, "ETH":
    manifest}``; ``not_assessable`` and ``gap_limit`` list ``(combination, window or
    test, count)`` and add their notes, in that order, when not empty."""
    for manifest in test_a_manifests.values():
        check_test_a_holdout(manifest, holdout)
    btc = manifest_values(test_a_manifests["BTC"])
    eth = manifest_values(test_a_manifests["ETH"])
    v = result[0].upper() + result[1:]
    line = (
        f"***{v}*; in TRAINER-AUDIT 11.8 the trainer's held-out direction calls showed "
        f"no skill above the up-rate base rate:** {AUDIT_11_8} Held-out metrics in Test "
        "A's manifests (a separate fit on the first 80% of each training window, scored "
        f"on the last 20%, {_when(holdout[0])} to {_when(holdout[1])}): "
        f"BTC {btc['hit']} vs {btc['up']} (n = {btc['n']}), "
        f"ETH {eth['hit']} vs {eth['up']} (n = {eth['n']})."
    )
    if not_assessable:
        k = sum(c for _, _, c in not_assessable)
        items = "; ".join(
            f"{combo}, {where}, {c}" for combo, where, c in not_assessable
        )
        line += (
            f" (not assessable: {k} decisions held for missing bars or an unknown "
            f"timeframe: {items})"
        )
    if gap_limit:
        k = sum(c for _, _, c in gap_limit)
        items = "; ".join(f"{combo}, {where}, {c}" for combo, where, c in gap_limit)
        line += f" (gap-pass limit reached on {k} decisions: {items})"
    return line
