"""
Write ``SIG4-REPORT-dev.md`` from the development analysis (``analysis.json``) and batch
PV-1's results (``results.json``), facts only.

    python sig4_dev_report.py <analysis.json> <PV-1 results.json> <PV-1 batch.json> <out.md>
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


def iso(t):
    if t is None or t < 0:
        return "never"
    return datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def pct(x, d=2):
    return "n/a" if x is None else f"{x:+.{d}%}"


def num(x, d=4):
    return "n/a" if x is None else f"{x:.{d}f}"


def money(x):
    return "n/a" if x is None else f"{x:+,.2f}"


def yes(b):
    return "yes" if b else "no"


def main(argv):
    a = json.load(open(argv[1], encoding="utf-8"))
    pv1 = json.load(open(argv[2], encoding="utf-8"))
    batch = json.load(open(argv[3], encoding="utf-8"))
    out = []
    w = out.append
    fam = a["family"]
    first, last = a["development"]
    w("# SIG4-REPORT-dev: FDS-SIG-004's development run")
    w("")
    w(
        "**What this is.** The development run of FDS-SIG-004 phase C (spec §8.3). It ran "
        "in a sandbox on public Coinbase candles, read offline from a cache. It scores the "
        f"development period only: PV-1's walk-forward, {iso(first)} to {iso(last)} UTC, in "
        f"{a['folds']} folds. No bar from 2025-05-06 on was read."
    )
    w("")
    w(
        "**What it decides** (spec §6.4.2): only whether a forward confirmation is worth "
        "registering, and what it would register. A development pass is never evidence for "
        "enabling anything. The volume rows from 2023-11-06 on were seen by the volume "
        "research (exposure X1), so they are not unseen evidence for volume."
    )
    w("")
    w("## Verdicts (development family, Holm over K = 5, at 0.50% and $10,000)")
    w("")
    v = a["verdicts"]
    for name, label in (
        ("F1", "F1, forecast value"),
        ("F2", "F2, relative trading value"),
        ("F3", "F3, economic viability"),
        ("Q2", "Q2, calibration of F_PV"),
        ("Q3", "Q3, the volatility shrink"),
    ):
        w(
            f"- **{label}:** {v[name]}. Development only: not evidence for enabling "
            "anything."
        )
    w("")
    w("| Test | p (pooled, 10 runs) | Holm at 5% | Conditions | Passes |")
    w("|---|---|---|---|---|")
    d = a["STRAT-001"]["0.0050"]["account_10000"]
    conds = {
        "F1": a["F1"]["conditions"],
        "F2": d["F2"]["conditions"],
        "Q2": {"calibrated": d["Q2"]["outcome"] == "calibrated", "enough": d["Q2"]["enough"]},
        "Q3": {"non_inferiority": d["Q3"]["non_inferiority"]["passes"]},
        "F3": {k: v for k, v in d["F3"]["requirements"].items() if k != "profit"},
    }
    for name in ("F1", "F2", "Q2", "Q3", "F3"):
        c = ", ".join(f"{k} {yes(x)}" for k, x in conds[name].items())
        w(
            f"| {name} | {num(fam['p'][name])} | {yes(fam['holm'][name])} | {c} | "
            f"{yes(fam['passes'][name])} |"
        )
    w("")

    # F1 ------------------------------------------------------------------------------------
    f1 = a["F1"]
    t = f1["test"]
    w("## F1: does volume improve T1 forecasts over price alone?")
    w("")
    w(
        f"- **Rows:** {f1['rows']:,} common rows (all seven models present, T1 resolved), "
        f"base rate {num(f1['base_rate'], 3)}."
    )
    w(
        f"- **Log loss:** price only {num(f1['log_loss']['price'], 5)}, price and volume "
        f"{num(f1['log_loss']['volume'], 5)}."
    )
    w(
        f"- **D̄ = ll(P) − ll(PV):** {t['theta']:+.6f}; p = {num(t['p'])} (runs from "
        f"{num(min(t['runs']))} to {num(max(t['runs']))}); 90% interval "
        f"[{t['interval'][0]:+.6f}, {t['interval'][1]:+.6f}]; blocks of {t['block_days']} days "
        f"over {t['days']} days."
    )
    w(f"- **Smallest detectable D̄** (at the Holm level, 80% power): {num(f1['smallest_detectable'], 6)}.")
    pl = f1["placebo"]
    w(
        f"- **Placebo condition** (mean of 5 lagged placebos minus PV): Ē = {pl['theta']:+.6f}, "
        f"p = {num(pl['p'])}: {yes(f1['conditions']['placebo'])}."
    )
    w(
        f"- **Stability:** D̄ by half of the scored days: {f1['halves'][0]:+.6f} and "
        f"{f1['halves'][1]:+.6f}: {yes(f1['conditions']['stability'])}."
    )
    w(
        "- **Each placebo against price only** (expected at most 0): "
        + ", ".join(f"{x:+.6f}" for x in f1["per_placebo"])
        + "."
    )
    for name, label in (("before_look", "before 2023-11-06 (no recorded look)"), ("seen", "from 2023-11-06 (seen by the volume research)")):
        if name in f1["by_exposure"]:
            e = f1["by_exposure"][name]
            w(f"- **D̄ {label}:** {e['theta']:+.6f}, p = {num(e['p'])}.")
    w(
        "- **D̄ by coin:** "
        + ", ".join(f"{c} {x:+.6f}" for c, x in sorted(f1["by_coin"].items()))
        + "."
    )
    w("")

    # trading level ------------------------------------------------------------------------------
    w("## Q1's trading level: batch PV-1 under FDS-MH-001's fixed strategy (shown)")
    w("")
    w(
        f"Batch `{batch['id']}` (declared PV-1, spec version {batch['spec_version']}), file "
        f"SHA-256 `{batch['sha256'][:16]}…`; K = {pv1['k']}; probability of backtest "
        f"overfitting {num(pv1['pbo'], 3)}. A relative finding of F2's kind under the legacy "
        "exits; never F3."
    )
    w("")
    w("| Contestant | Trades | Return per day held | Total profit | p | Verdict |")
    w("|---|---|---|---|---|---|")
    for k in pv1["tested"]:
        c = pv1["contestants"][k]
        s = c["score"]
        w(
            f"| `{k}` | {s['trades']} | {pct(s['per_day'], 4)} | {num(s['profit'], 2)} | "
            f"{num(c['p'])} | {c['verdict_text']} |"
        )
    w("")

    # STRAT-001 ------------------------------------------------------------------------------------
    w("## STRAT-001 1h at its defaults: the decision level")
    w("")
    sg = a["sigma"]
    w(
        f"- **σ̂:** {sg['chosen']} (QLIKE: "
        + ", ".join(f"{k} {v:.4f}" for k, v in sg["qlike"].items())
        + ")."
    )
    w(
        "- **Venue minimums** (today's, from the public product endpoint; past ones are not "
        "recorded anywhere): "
        + ", ".join(f"{c} {m}" for c, m in sorted(a["minimums"].items()))
        + "."
    )
    for fee_key, fee_label in (("0.0050", "0.50% (deciding)"), ("0.0120", "1.20% (shown)")):
        per = a["STRAT-001"][fee_key]
        w("")
        w(f"### At {fee_label}")
        w("")
        w(f"{per['opportunities']} opportunities in the development period; blocks of {per['block_days']} days.")
        w("")
        w("| Account | Path | Trades | Vetoed | Net | Return per capital-day | Max drawdown | Halt level reached |")
        w("|---|---|---|---|---|---|---|---|")
        for acct in ("account_10000", "account_100"):
            for name, p in per[acct]["paths"].items():
                w(
                    f"| ${acct.split('_')[1]} | {name} | {p['trades']} | {p['vetoed']} | "
                    f"{money(p['net'])} | {pct(p['rpcd'], 4)} | {pct(p['max_drawdown'])} | "
                    f"{iso(p['halt_s'])} |"
                )
        e = per["account_10000"]
        if "F2" not in e:
            continue
        f2 = e["F2"]
        w("")
        w(
            f"- **F2:** Δ RPCD (F_PV − F_P) = {f2['test']['theta']:+.6f}, p = "
            f"{num(f2['test']['p'])}; against R3, p = {num(f2['r3']['p'])} (R3's median "
            f"{pct(f2['r3']['median'], 4)}). Veto counts per coin: {f2['veto_counts']}."
        )
        f3 = e["F3"]
        r = f3["report"]
        req = f3["requirements"]
        w(
            f"- **F3 (F_PV's path):** trades {r['trades']} ({r['trades_by_half']} by half), "
            f"net {money(r['net_usd'])} ({pct(r['return_on_equity'])} of equity, "
            f"{pct(r['annualised'])} a year), return per capital-day {pct(r['rpcd'], 4)} "
            f"(p = {num(f3['test']['p'])}); net by half {[round(x, 2) for x in r['net_by_half']]}; "
            f"without the best coin {money(r['without_best_coin'])}; maximum drawdown "
            f"{pct(r.get('max_drawdown'))}; time in the market {pct(r['time_in_market'], 1)}; "
            f"mean committed {pct(r['mean_committed'], 2)} of equity, peak "
            f"{pct(r['peak_committed'], 2)}; win rate {pct(r['win_rate'], 1)}; largest single "
            f"loss {money(r['largest_loss_usd'])}. Requirements: trades {yes(req['trades'])}, "
            f"stable {yes(req['stable'])}, not one coin {yes(req['not_one_coin'])}, within "
            f"the halt level {yes(req['within_halt'])}."
        )
        q2 = e["Q2"]
        w(
            f"- **Q2 (F_PV):** BSS {q2['skill']['theta']:+.4f} (p = {num(q2['skill']['p'])}); "
            f"intercept a = {num(q2['intercept']['value'], 3)}, 90% interval "
            f"{[round(x, 3) for x in q2['intercept']['interval_90']]} against "
            f"{q2['intercept']['band']}; slope b = {num(q2['slope']['value'], 3)}, 90% "
            f"interval {[round(x, 3) for x in q2['slope']['interval_90']]} against "
            f"{q2['slope']['band']}; {q2['events']} events and {q2['non_events']} non-events: "
            f"**{q2['outcome'].replace('_', ' ')}**."
        )
        q3 = e["Q3"]
        ni = q3["non_inferiority"]
        w(
            f"- **Q3:** the shrink's maximum drawdown {pct(q3['max_drawdown'])} against R3s' "
            f"median {pct(q3['r3s_median'])} (p = {num(q3['p'])}); non-inferiority lower bound "
            f"{ni['lower_95']:+.6f} against −{ni['margin']}: {yes(ni['passes'])}; "
            f"{q3['skipped_minimum']} entries skipped below the minimum."
        )
        rule = e["rule_1_5x"]
        w(
            f"- **The research's 1.5× rule** (before 2023-11-06 only, shown): "
            f"{rule['opportunities']} opportunities, {rule['vetoed']} vetoed, return per "
            f"capital-day {pct(rule['rpcd'], 4)} against R3's median "
            f"{pct(rule['r3_median'], 4)} (p = {num(rule['p_r3'])})."
        )
    w("")
    w("## Limits")
    w("")
    w("- One market history (2021 to 2025) on one venue; survivorship: the coins are those listed today.")
    w("- Past exchange minimums and spreads are not recorded anywhere: the replays use today's minimums and 0.05% a fill.")
    w("- The drawdown halt is reported, not modelled (spec §6.0).")
    w("- Volume's rows from 2023-11-06 were seen by the volume research; only a forward window can confirm volume.")
    w("")
    open(argv[4], "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main(sys.argv)
