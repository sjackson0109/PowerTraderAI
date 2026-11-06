"""
A round's results, report and evidence (FDS-SIG-001 section 13).

* ``results_record``: every row with every section 13 field, both Holm procedures, the
  provisional members and the run state; the exact p-values, both Holm procedures and
  every verdict can be recomputed from it alone, and the bootstrap and batch-means
  p-values from the evidence series with the registered seed.
* ``series_csv``: a row's per-pair call and return series.
* ``report_markdown``: ``docs/dev/SIG-AUDIT-REPORT-round-<N>.md``. One section per
  (candidate, coin, timeframe), none dropped. Every verdict line carries its caveat in
  the same line, with the score, the comparator and n side by side, and names the
  statistic and the family; PASS lines give the Holm-adjusted p-value, FAIL lines the
  95% upper bound and the minimum detectable effect.
* **No pooling.** The report gives counts for information only, never a pooled,
  averaged or counted verdict, and ``pooled_verdict`` refuses to make one (section 8.2).
"""

from __future__ import annotations

import io
import math
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence

import numpy as np

from signal_audit import engine
from signal_audit import stats as st

STAT_NAMES = {st.HIT: "hit rate", st.MAGNITUDE: "magnitude"}


class NoPooling(RuntimeError):
    """Rows are never pooled, averaged or counted into a verdict (section 8.2)."""


def pooled_verdict(*_args, **_kwargs):
    raise NoPooling(
        "the audit gives each row's verdict alone; rows are never pooled, averaged or "
        "counted into a verdict (FDS-SIG-001 section 8.2)"
    )


# --- formatting -------------------------------------------------------------------------


def _pct(x: Optional[float], digits: int = 1, sign: bool = False) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    return f"{x:+.{digits}%}" if sign else f"{x:.{digits}%}"


def _pts(x: Optional[float]) -> str:
    """An edge in percentage points."""
    if x is None or not math.isfinite(x):
        return "n/a"
    return f"{x * 100:.1f} points"


def _p(x: Optional[float]) -> str:
    if x is None:
        return "n/a"
    return f"{x:.3g}" if x < 0.001 else f"{x:.3f}"


def _num(x: Optional[float], digits: int = 4) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    return f"{x:.{digits}g}"


def _int(x: Optional[int]) -> str:
    return "n/a" if x is None else f"{x:,}"


# --- verdict lines ----------------------------------------------------------------------


def statistic_outcome(row: engine.Row, s: str) -> str:
    """One statistic's own outcome, as its verdict line reads it."""
    r = row.results[s]
    if row.counts.n < st.MIN_CALLS or not r.assessable:
        return engine.NOT_ASSESSABLE
    if row.survives[s] and r.extra_met:
        return engine.PASS
    if row.survives_opposite[s]:
        return engine.WORSE
    return engine.FAIL


def _figure(row: engine.Row, s: str) -> str:
    c = row.counts
    r = row.results[s]
    if s == st.HIT:
        if row.kind == st.TWO_SIDED:
            return (
                f"hit rate {_pct(c.h)} vs best constant {_pct(c.best_constant)} "
                f"(always {c.constant or 'n/a'}; n = {_int(c.n)}; m = {_int(c.m)}, "
                f"k = {_int(c.k)}"
            )
        word = "up" if row.kind == st.UP_ONLY else "down"
        t = c.table or {}
        called = t.get("called_up", 0) + t.get("called_down", 0)
        abst = t.get("abstained_up", 0) + t.get("abstained_down", 0)
        share_c = (t.get(f"called_{word}", 0) / called) if called else None
        share_a = (t.get(f"abstained_{word}", 0) / abst) if abst else None
        return (
            f"{word} share {_pct(share_c)} on called pairs vs {_pct(share_a)} on "
            f"abstained pairs (n = {_int(c.n)}; abstained = {_int(c.abstained)}"
        )
    if row.kind == st.TWO_SIDED:
        return (
            f"mean c x (r - r_bar) {_pct(r.value, 4, True)} a bar vs 0 (raw mean c x r "
            f"{_pct(r.extra_value, 4, True)}; n = {_int(c.n)}"
        )
    return (
        f"called minus abstained mean return {_pct(r.value, 4, True)} a bar vs 0 "
        f"(called mean {_pct(r.extra_value, 4, True)}; n = {_int(c.n)}; abstained = "
        f"{_int(c.abstained)}"
    )


def verdict_line(row: engine.Row, s: str, family_size: int, family_error: float) -> str:
    """Section 13's verdict line for one statistic of one row."""
    r = row.results[s]
    family = f"{STAT_NAMES[s]}; family of {family_size} tests at {family_error:.0%}"
    outcome = statistic_outcome(row, s)
    figure = _figure(row, s)
    if outcome == engine.PASS:
        return (
            f"**PASS (provisional, not yet confirmed; {family})**: {figure}; Holm p = "
            f"{_p(row.holm[s])})."
        )
    if outcome == engine.NOT_ASSESSABLE:
        floors = (
            "; ".join(r.below_floor) or f"n = {row.counts.n} calls < {st.MIN_CALLS}"
        )
        return f"**NOT ASSESSABLE ({family})**: below its floors: {floors} ({figure}))."
    if outcome == engine.WORSE:
        if s == st.HIT and row.kind == st.TWO_SIDED:
            against = f"chance at the mix {_pct(row.counts.chance_at_mix)}"
        else:
            against = "the comparator"
        return (
            f"**WORSE, information only, not a pass ({family})**: {figure}); worse than "
            f"{against}; opposite-direction Holm p = {_p(row.holm_opposite[s])}. "
            "Inverting the rule would be a new candidate."
        )
    unmet = ""
    if row.survives[s] and not r.extra_met:
        unmet = "; it survived Holm but its extra condition is not met"
    upper = _pts(r.upper_95) if s == st.HIT else f"{_pct(r.upper_95, 4, True)} a bar"
    mde = _pts(r.mde) if s == st.HIT else f"{_pct(r.mde, 4)} a bar"
    return (
        f"**FAIL, no evidence of an edge at this power ({family})**: {figure}); edge "
        f"at most {upper} (95%); smallest detectable edge {mde}{unmet}."
    )


def _taus(dep: Mapping[str, Any]) -> str:
    taus = dep.get("tau_by_indicator") or {}
    if not taus:
        return "none (no call indicator varies)"
    return ", ".join(f"{k} {v:.2f}" for k, v in taus.items())


def row_verdict_line(row: engine.Row) -> str:
    parts = ", ".join(
        f"{STAT_NAMES[s]}: {statistic_outcome(row, s)}" for s in st.STATISTICS
    )
    return f"{row.key.text()}: **{row.verdict}** ({parts})"


# --- the results record ------------------------------------------------------------------


def _bootstrap(b: Optional[st.Bootstrap]) -> Optional[Dict[str, Any]]:
    if b is None:
        return None
    return {
        "p_upper": b.p_upper,
        "p_lower": b.p_lower,
        "mcse_upper": b.se_upper,
        "mcse_lower": b.se_lower,
        "sd": b.sd,
        "draws": b.draws,
    }


def _batch(b: Optional[st.BatchMeans]) -> Optional[Dict[str, Any]]:
    if b is None:
        return None
    return {
        "K": b.K,
        "dropped": b.dropped,
        "mean": None if not math.isfinite(b.mean) else b.mean,
        "se": None if not math.isfinite(b.se) else b.se,
        "t": None if b.t is None or not math.isfinite(b.t) else b.t,
        "p_upper": b.p_upper,
        "p_lower": b.p_lower,
    }


def row_record(
    row: engine.Row, family_size: int, family_error: float
) -> Dict[str, Any]:
    c = row.counts
    d = row.data
    p = d.pairs
    called = p.calls != 0
    right = np.where(p.calls[called] == st.UP, p.up[called], 1 - p.up[called])
    stats_out = {}
    for s in st.STATISTICS:
        r = row.results[s]
        stats_out[s] = {
            "value": r.value,
            "assessable": r.assessable,
            "below_floor": r.below_floor,
            "p_exact": r.p_exact,
            "bootstrap": _bootstrap(r.bootstrap),
            "batch_means": _batch(r.batch),
            "p_holm": r.p_holm,
            "holm_adjusted": row.holm[s],
            "survives_holm": row.survives[s],
            "q_exact": r.q_exact,
            "bootstrap_opposite": _bootstrap(r.bootstrap_opposite),
            "batch_means_opposite": _batch(r.batch_opposite),
            "q_holm": r.q_holm,
            "holm_opposite_adjusted": row.holm_opposite[s],
            "survives_opposite_holm": row.survives_opposite[s],
            "extra_condition_met": r.extra_met,
            "extra_condition_value": r.extra_value,
            "se": {
                "independent": r.se_independent,
                "bootstrap": r.se_bootstrap,
                "batch_means": r.se_batch,
                "used": r.se,
            },
            "mde": r.mde,
            "mde_detail": r.mde_detail,
            "upper_95": r.upper_95,
            "outcome": statistic_outcome(row, s),
            "verdict_line": verdict_line(row, s, family_size, family_error),
        }
    return {
        "key": row.key.to_dict(),
        "kind": row.kind,
        "counts": {
            "window_pairs": d.window_pairs,
            "skipped_pairs": d.skipped,
            "ties": d.ties,
            "missing_bars": d.missing_bars,
            "eligible_pairs": c.eligible,
            "calls": c.n,
            "abstentions": c.abstained,
            "coverage": c.coverage,
            "q": c.q,
            "h": c.h,
            "p_c": c.p_c,
            "best_constant": c.best_constant,
            "constant": c.constant,
            "chance_at_mix": c.chance_at_mix,
            "up_share_all": c.up_share_all,
            "m": c.m,
            "k": c.k,
            "table": c.table,
        },
        "dependence": {
            "tau": row.blocks.tau,
            "tau_by_indicator": row.blocks.tau_by_indicator,
            "constant_calls": row.blocks.constant_calls,
            "L": row.blocks.L,
            "K": row.blocks.K,
            "batch_means_dropped": (
                row.results[st.HIT].batch.dropped if row.results[st.HIT].batch else None
            ),
            "mean_call_run": st.mean_run_length(p.calls),
            "hit_lag1_autocorrelation": st.lag1_autocorrelation(right),
        },
        "statistics": stats_out,
        "magnitude_conditions": {
            "raw_mean_c_r": (
                row.results[st.MAGNITUDE].extra_value
                if row.kind == st.TWO_SIDED
                else None
            ),
            "called_mean_return": (
                row.results[st.MAGNITUDE].extra_value
                if row.kind != st.TWO_SIDED
                else None
            ),
            "round_trip_cost": st.ROUND_TRIP_COST,
        },
        "verdict": row.verdict,
        "passing": row.passing,
        "verdict_line": row_verdict_line(row),
    }


def results_record(
    result: engine.RoundResult,
    round_number: int,
    registration_sha256: str,
    state: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    engine.check_verdicts(result)  # asserted against the numbers, re-derived
    rows = [row_record(r, result.family_size, result.family_error) for r in result.rows]
    provisional = [
        {**r.key.to_dict(), "statistic": s} for r in result.rows for s in r.passing
    ]
    return {
        "round": round_number,
        "registration_sha256": registration_sha256,
        "family_size": result.family_size,
        "family_error": result.family_error,
        "bootstrap_draws": result.draws,
        "seed": result.seed,
        "rows": rows,
        "provisional": provisional,
        "rechecked_verdicts": engine.recheck_verdicts(result),
        "state": dict(state) if state is not None else None,
    }


def series_csv(row: engine.Row) -> str:
    """The row's per-pair series: bar t's open (UTC), the call, the outcome, r, and
    both closes."""
    d = row.data
    out = io.StringIO()
    out.write("open_time_utc,call,up,r,close_t,close_t1\n")
    for t, call, up, r, c0, c1 in zip(
        d.open_s.tolist(),
        d.pairs.calls.tolist(),
        d.pairs.up.tolist(),
        d.pairs.ret.tolist(),
        d.close_t.tolist(),
        d.close_next.tolist(),
    ):
        when = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.write(f"{when},{call},{up},{r!r},{c0!r},{c1!r}\n")
    return out.getvalue()


# --- the report -------------------------------------------------------------------------


def report_markdown(
    registration: Mapping[str, Any],
    results: Mapping[str, Any],
    superseded: Sequence[Mapping[str, Any]] = (),
) -> str:
    F = results["family_size"]
    alpha = results["family_error"]
    rows = results["rows"]
    n_pass = sum(1 for r in rows if r["verdict"] == engine.PASS)
    state = results.get("state") or {}
    window = registration["window"]
    lines = [
        f"# Signal-candidate audit, round {results['round']}",
        "",
        f"- **Registration:** `{registration.get('path', 'registration.json')}`, SHA-256 "
        f"`{results['registration_sha256']}`; window {window['start']} to "
        f"{window['end']}; exchange {registration['exchange']}.",
        f"- **Family:** F = {F} tests (candidate x coin x timeframe x statistic), "
        f"family error rate {alpha:.0%}, Holm one-sided; NOT ASSESSABLE members enter "
        "every Holm procedure with p = 1.",
        f"- **Provisional passes:** {n_pass} of {len(rows)} rows, for information only. "
        "A provisional pass is not yet replicated: it counts only after a confirmation "
        "round on the next fresh window.",
        "- **The tests are positively dependent.** The 1h and 4h rows of one coin share "
        "one price path, and coins move together, so passes on several coins are not "
        "independent confirmations. Each row's verdict stands alone; no pooled, averaged "
        "or counted verdict is given.",
        f"- **Run:** commit `{state.get('head', 'n/a')}`; frozen files dirty: "
        f"{state.get('frozen_files_dirty') or 'none'}; frozen files changed since the "
        f"freeze commit: {state.get('frozen_files_changed_since_freeze') or 'none'}; "
        f"Python {str(state.get('python', 'n/a')).split()[0]}; POWERTRADER_HOME "
        f"`{state.get('powertrader_home')}`.",
        f"- **Bootstrap:** B = {results['bootstrap_draws']:,} per statistic, seed "
        f"{results['seed']}.",
        "",
        "## Verdicts",
        "",
    ]
    for r in rows:
        lines.append(f"- {r['verdict_line']}")
        for s in st.STATISTICS:
            lines.append(f"  - {r['statistics'][s]['verdict_line']}")
    if superseded:
        lines += ["", "## Superseded results", ""]
        for old in superseded:
            lines.append(
                f"- {old.get('note', '')} (commit {old.get('commit', 'n/a')}):"
            )
            for r in old.get("rows", []):
                lines.append(f"  - earlier: {r['verdict_line']}")
    lines += ["", "## Rows", ""]
    for r in rows:
        c = r["counts"]
        dep = r["dependence"]
        k = r["key"]
        lines += [
            f"### {k['candidate']} {k['coin']} {k['timeframe']} ({k['exchange']})",
            "",
            f"- **Counts:** {c['window_pairs']:,} pairs in the window; skipped (data "
            f"gaps) {c['skipped_pairs']:,}; ties {c['ties']:,}; missing bars "
            f"{c['missing_bars']:,}; eligible {c['eligible_pairs']:,}; calls n = "
            f"{c['calls']:,}; abstentions {c['abstentions']:,}; coverage "
            f"{_pct(c['coverage'])}; q = {_pct(c['q'])}.",
            f"- **Comparators:** p_c = {_pct(c['p_c'])}; best constant b = "
            f"{_pct(c['best_constant'])} (always {c['constant'] or 'n/a'}); chance at "
            f"the mix {_pct(c['chance_at_mix'])}; up share on all eligible pairs "
            f"{_pct(c['up_share_all'])}.",
            f"- **Hit rate:** h = {_pct(c['h'])}"
            + (
                f"; m = {_int(c['m'])}, k = {_int(c['k'])}"
                if r["kind"] == st.TWO_SIDED
                else f"; table {c['table']}"
            )
            + ".",
        ]
        for s in st.STATISTICS:
            x = r["statistics"][s]
            b = x["bootstrap"] or {}
            bm = x["batch_means"] or {}
            bo = x["bootstrap_opposite"] or {}
            bmo = x["batch_means_opposite"] or {}
            lines.append(
                f"- **{STAT_NAMES[s].capitalize()}:** value {_num(x['value'])}; "
                f"forward: exact {_p(x['p_exact'])}, bootstrap {_p(b.get('p_upper'))} "
                f"(MC s.e. {_num(b.get('mcse_upper'), 2)}), batch means "
                f"{_p(bm.get('p_upper'))}, entering Holm {_p(x['p_holm'])}, "
                f"Holm-adjusted {_p(x['holm_adjusted'])}; opposite: exact "
                f"{_p(x['q_exact'])}, bootstrap {_p(bo.get('p_lower'))} (MC s.e. "
                f"{_num(bo.get('mcse_lower'), 2)}), batch means {_p(bmo.get('p_lower'))}, "
                f"entering Holm {_p(x['q_holm'])}, Holm-adjusted "
                f"{_p(x['holm_opposite_adjusted'])}; s.e. used {_num(x['se']['used'])} "
                f"(independent {_num(x['se']['independent'])}, bootstrap "
                f"{_num(x['se']['bootstrap'])}, batch means "
                f"{_num(x['se']['batch_means'])}); minimum detectable effect "
                f"{_num(x['mde'])}; 95% upper bound {_num(x['upper_95'])}; extra "
                f"condition {'met' if x['extra_condition_met'] else 'not met'} "
                f"({_num(x['extra_condition_value'])})"
                + (
                    f"; below floors: {'; '.join(x['below_floor'])}"
                    if x["below_floor"]
                    else ""
                )
                + "."
            )
        mc = r["magnitude_conditions"]
        lines += [
            f"- **Magnitude conditions:** raw mean c x r {_num(mc['raw_mean_c_r'])}; "
            f"called pairs' mean return {_num(mc['called_mean_return'])}; round-trip "
            f"cost {mc['round_trip_cost']:.2%} (information only).",
            f"- **Dependence:** tau {_taus(dep)}; L = {dep['L']}; K = {dep['K']}; pairs "
            f"dropped from batch means {dep['batch_means_dropped']}; mean call run "
            f"{_num(dep['mean_call_run'])}; "
            f"lag-1 autocorrelation of the hit series {_num(dep['hit_lag1_autocorrelation'])}.",
            f"- **Verdict:** {r['verdict']}.",
            "",
        ]
    text = "\n".join(lines) + "\n"
    check_report(text, results)
    return text


FORBIDDEN = (
    "overall verdict",
    "pooled verdict",
    "average verdict",
    "verdict overall",
    "across all rows the verdict",
    "counted verdict:",
)


def check_report(text: str, results: Mapping[str, Any]) -> None:
    """The report has a verdict line for every row and statistic, each verdict as the
    numbers give it, and no pooled, averaged or counted verdict."""
    low = text.lower()
    for phrase in FORBIDDEN:
        if phrase in low:
            raise NoPooling(f"the report would give a {phrase!r}")
    for r in results["rows"]:
        if r["verdict_line"] not in text:
            raise AssertionError(f"row {r['key']} has no verdict line")
        for s in st.STATISTICS:
            if r["statistics"][s]["verdict_line"] not in text:
                raise AssertionError(f"row {r['key']} {s} has no verdict line")
    if [r["verdict"] for r in results["rows"]] != list(results["rechecked_verdicts"]):
        raise AssertionError("a verdict differs from its independent re-derivation")
