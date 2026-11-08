"""
The summary tables of ``docs/dev/sr1-bootstrap-study/STUDY.md``, read from the study's
``results.json``. It reads only; it simulates nothing.

    "$PY" docs/dev/sr1_bootstrap_report_tables.py docs/dev/sr1-bootstrap-study/results.json
"""

from __future__ import annotations

import json
import sys
from typing import Dict, List

import numpy as np

KEY = (
    "E-rule", "E-rule-cap", "E-28", "E-112", "E-448", "E-PW", "E-SB",
    "M-1", "M-7", "M-14", "M-28", "M-56", "M-112", "M-448", "M-PW", "M-SB",
    "T-iid", "T-episode", "NW",
)  # fmt: skip


def pct(v, d=1) -> str:
    if v is None or not np.isfinite(v):
        return "–"
    return f"{100 * v:.{d}f}"


def rng(vals, d=1) -> str:
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    return f"{pct(min(vals), d)}–{pct(max(vals), d)}" if vals else "–"


def per_run(cells, fn, runs=10) -> List[float]:
    return [fn(cells, r) for r in range(runs)]


def main(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        res = json.load(fh)
    cells = res["cells"]
    methods = res["design"]["methods"]
    runs = res["design"]["runs"]
    sel = res["selection"]
    deciding = [c for c in cells if c["deciding"]]
    fwer = [c for c in cells if c["group"] == "fwer"]
    lam = str(res["design"]["lambda_decide"])
    out: List[str] = []

    # A. the summary over the deciding cells
    out += [
        f"### A. Every method over the {len(deciding)} deciding null cells",
        "",
        "Size at nominal 5% (one-sided); coverage of the two-sided 90% interval; power at λ = 2.5 (an ideal test has 80%). Pooled over 10 runs of 300 replications a cell; per-run ranges in brackets.",
        "",
        "| Method | Size: lowest – highest cell | Size: mean over cells (runs) | 90% coverage, worst cell: percentile / basic | Agreement of p ≤ 5% with “90% interval above 0”, worst cell: percentile (null / λ 2.5) · basic (null / λ 2.5) | Power at λ = 2.5: lowest cell (runs) | Power at λ = 2.5: mean | Holm FWER: highest cell | Units: fewest | Valid |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in methods:
        sizes = [c["methods"][m]["size"]["pooled"] for c in deciding]
        mean_runs = per_run(
            deciding,
            lambda cs, r: float(
                np.mean([c["methods"][m]["size"]["runs"][r] for c in cs])
            ),
            runs,
        )
        covp = [c["methods"][m]["coverage"]["pct90"]["pooled"] for c in deciding]
        covb = [c["methods"][m]["coverage"]["basic90"]["pooled"] for c in deciding]
        agp = [c["methods"][m]["agreement"]["pct_null"]["pooled"] for c in deciding]
        agb = [c["methods"][m]["agreement"]["basic_null"]["pooled"] for c in deciding]
        agpa = [c["methods"][m]["agreement"]["pct_alt"]["pooled"] for c in deciding]
        agba = [c["methods"][m]["agreement"]["basic_alt"]["pooled"] for c in deciding]
        agree = (
            f"{pct(min(agp))} / {pct(min(agpa))} · {pct(min(agb))} / {pct(min(agba))}"
        )
        pw = [c["methods"][m]["power_lambda"][lam]["pooled"] for c in deciding]
        pw_runs = per_run(
            deciding,
            lambda cs, r: float(
                min(c["methods"][m]["power_lambda"][lam]["runs"][r] for c in cs)
            ),
            runs,
        )
        fw = [c["fwer"][m]["pooled"] for c in fwer]
        units = [
            c["methods"][m]["units"]["min"]
            for c in deciding
            if c["methods"][m]["units"]
        ]
        worst = lambda v: v[int(np.argmax([abs(x - 0.9) for x in v]))]  # noqa: E731
        valid = sel["table"].get(m, {}).get("valid")
        out.append(
            f"| {m} | {pct(min(sizes))} – {pct(max(sizes))} | {pct(np.mean(sizes))} ({rng(mean_runs)}) | "
            f"{pct(worst(covp))} / {pct(worst(covb))} | {agree} | "
            f"{pct(min(pw), 0)} ({rng(pw_runs, 0)}) | {pct(np.mean(pw), 0)} | {pct(max(fw))} | "
            f"{min(units):.0f} | {'yes' if valid else ('reference' if m == 'NW' else 'no')} |"
            if units
            else f"| {m} | {pct(min(sizes))} – {pct(max(sizes))} | {pct(np.mean(sizes))} ({rng(mean_runs)}) | "
            f"{pct(worst(covp))} / {pct(worst(covb))} | {agree} | "
            f"{pct(min(pw), 0)} ({rng(pw_runs, 0)}) | {pct(np.mean(pw), 0)} | {pct(max(fw))} | – | "
            f"{'yes' if valid else ('reference' if m == 'NW' else 'no')} |"
        )
    out.append("")

    # B. size per cell, key methods
    out += [
        "### B. Size at nominal 5%, every null cell (pooled)",
        "",
        "| Cell | Trades | Hold p50 / p99 | §6.0 L | " + " | ".join(KEY) + " |",
        "|---|---|---|---|" + "---|" * len(KEY),
    ]
    for c in cells:
        if c["group"] in ("fwer", "floor"):
            continue
        s = c["oracle"]["A"]["stats"]
        tag = c["name"].replace("core:", "").replace("stress:", "stress ")
        if c["deciding"]:
            tag = f"**{tag}**"
        out.append(
            f"| {tag} | {s['trades']:.0f} | {s['hold_p50']:.0f} / {s['hold_p99']:.0f} | {s['rule_L_median']:.0f} | "
            + " | ".join(pct(c["methods"][m]["size"]["pooled"]) for m in KEY)
            + " |"
        )
    out += ["", "Bold: deciding cells.", ""]

    # C. size by number of blocks (fixed L), deciding cells
    out += [
        "### C. Size by block length at N = 1,586 days (deciding cells)",
        "",
        "| L (days) | Blocks | E: mean size | E: highest cell | M: mean size | M: highest cell |",
        "|---|---|---|---|---|---|",
    ]
    for L in (1, 7, 14, 28, 56, 112, 224, 448, 896):
        k = int(np.ceil(1586 / L))
        row = [str(L), str(k)]
        for fam in ("E", "M"):
            name = f"{fam}-{L}"
            if name in methods:
                v = [c["methods"][name]["size"]["pooled"] for c in deciding]
                row += [pct(np.mean(v)), pct(max(v))]
            else:
                row += ["–", "–"]
        out.append("| " + " | ".join(row) + " |")
    out.append("")

    # D. FWER
    out += [
        "### D. Family-wise error under Holm at 5%, four members, all null (pooled, runs)",
        "",
        "| Method | "
        + " | ".join(c["name"].replace("fwer:fwer ", "") for c in fwer)
        + " |",
        "|---|" + "---|" * len(fwer),
    ]
    for m in KEY:
        out.append(
            f"| {m} | "
            + " | ".join(
                f"{pct(c['fwer'][m]['pooled'])} ({rng(c['fwer'][m]['runs'])})"
                for c in fwer
            )
            + " |"
        )
    corr = [np.array(c["theta_correlation"]) for c in fwer]
    out += [
        "",
        "Correlation of the members' θ̂ (A, A-veto, B, B-veto order as in `members`): "
        + "; ".join(
            f"{c['name'].replace('fwer:fwer ', '')}: A/A-veto {k[c['members'].index('A'), c['members'].index('A-veto')]:.2f}, "
            f"A/B {k[c['members'].index('A'), c['members'].index('B')]:.2f}"
            for c, k in zip(fwer, corr)
        ),
        "",
    ]

    # E. power curves, mean over deciding cells
    out += [
        "### E. Power against the standardised effect λ (mean over deciding cells; the ideal one-sided 5% test in the last row)",
        "",
        "| Method | " + " | ".join(f"λ = {x}" for x in res["design"]["lambdas"]) + " |",
        "|---|" + "---|" * len(res["design"]["lambdas"]),
    ]
    for m in KEY:
        out.append(
            f"| {m} | "
            + " | ".join(
                pct(
                    np.mean(
                        [
                            c["methods"][m]["power_lambda"][str(x)]["pooled"]
                            for c in deciding
                        ]
                    ),
                    0,
                )
                for x in res["design"]["lambdas"]
            )
            + " |"
        )
    ideal = deciding[0]["ideal_power_lambda"]
    out.append(
        "| ideal | "
        + " | ".join(pct(ideal[str(x)], 0) for x in res["design"]["lambdas"])
        + " |"
    )
    out.append("")

    # F. absolute power for the selected method
    chosen = sel.get("selected")
    if chosen:
        out += [
            f"### F. Power of {chosen} against absolute effects (per capital-day), deciding cells",
            "",
            "| Cell | SD₀ | δ = 0.025% | δ = 0.05% | δ = 0.10% | δ = 0.20% | ideal at 0.10% |",
            "|---|---|---|---|---|---|---|",
        ]
        for c in deciding:
            m = c["methods"][chosen]
            out.append(
                f"| {c['name'].replace('core:', '')} | {100 * c['oracle']['A']['sd0']:.3f}% | "
                + " | ".join(
                    pct(m["power_delta"][str(d)]["pooled"], 0)
                    for d in res["design"]["deltas"]
                )
                + f" | {pct(c['ideal_power_delta'][str(0.001)], 0)} |"
            )
        out.append("")
        # G. the floor
        fl = sel.get("floor", {})
        out += [
            f"### G. The not-assessable floor: {chosen} over shorter windows (size at nominal 5%, pooled and runs)",
            "",
            "| Window (days) | Blocks | exo base | donchian base | exo bear | donchian bear |",
            "|---|---|---|---|---|---|",
        ]
        rows: Dict[int, Dict[str, str]] = {}
        units: Dict[int, float] = {}
        for c in cells:
            if c["group"] != "floor":
                continue
            m = c["methods"][chosen]
            key = f"{c['gen']} {c['market']}"
            rows.setdefault(c["days"], {})[
                key
            ] = f"{pct(m['size']['pooled'])} ({rng(m['size']['runs'])})"
            if m["units"]:
                units[c["days"]] = m["units"]["mean"]
        for days in sorted(rows):
            r = rows[days]
            out.append(
                f"| {days} | {units.get(days, float('nan')):.1f} | {r.get('exo base')} | {r.get('donchian base')} | "
                f"{r.get('exo bear')} | {r.get('donchian bear')} |"
            )
        out += [
            "",
            f"Floor chosen by the pre-stated rule: window {fl.get('window_days')} days, {fl.get('units')} blocks.",
            "",
        ]

    # J. per run, the selected method and the current rule
    for name in [n for n in (chosen, "E-rule") if n]:
        out += [
            f"### J. {name}, run by run (deciding cells and FWER cells)",
            "",
            "| Run | Mean size | Highest size | Cells outside [2.5%, 7.5%] | Lowest power at λ = 2.5 | Mean power at λ = 2.5 | Highest FWER |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in range(runs):
            sz = [c["methods"][name]["size"]["runs"][r] for c in deciding]
            pw = [c["methods"][name]["power_lambda"][lam]["runs"][r] for c in deciding]
            fw = [c["fwer"][name]["runs"][r] for c in fwer]
            outside = sum(1 for v in sz if not (0.025 <= v <= 0.075))
            out.append(
                f"| {r} | {pct(np.mean(sz))} | {pct(max(sz))} | {outside} of {len(sz)} | {pct(min(pw), 0)} | "
                f"{pct(np.mean(pw), 0)} | {pct(max(fw))} |"
            )
        out += [
            "",
            "With 300 replications a cell in one run, a size estimate has a standard error of about 1.3 points at 5%, so single runs stray outside the band by chance; the decision uses the pooled 3,000.",
            "",
        ]

    # H. the real-implementation check
    out += [
        "### H. The real-implementation check (`bootstrap.test_statistic`, 10 runs of 1,000, `random()`)",
        "",
        "| Cell | Replications | Method | Size, real | Size, fast | Same decision | Mean abs. p difference |",
        "|---|---|---|---|---|---|---|",
    ]
    for rc in res["real_check"]:
        for m, v in rc["methods"].items():
            out.append(
                f"| {rc['cell']} | {rc['reps']} | {m} | {pct(v['size_real'])} | {pct(v['size_fast'])} | "
                f"{pct(v['same_decision'])} | {v['mean_abs_p_diff']:.4f} |"
            )
    out.append("")

    # I. the selection
    out += [
        "### I. The selection rule's outcome",
        "",
        f"Valid methods: {', '.join(sel['valid']) or 'none'}.",
        f"Tied at the top (within 1 point of minimum power): {', '.join(sel.get('tied', [])) or '–'}.",
        f"Selected: {sel.get('selected')}. Fallback used: {sel.get('fallback')}.",
        "",
        "| Method | Highest size | Lowest size | Highest FWER | Lowest power at λ = 2.5 | Interval | Worst 90% coverage gap | Fewest units | Valid |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for m, t in sel["table"].items():
        out.append(
            f"| {m} | {pct(t['max_size'])} | {pct(t['min_size'])} | {pct(t['max_fwer'])} | {pct(t['min_power'], 0)} | "
            f"{t['interval']} | {pct(t['worst_coverage_gap'])} | {t['min_units']:.0f} | {'yes' if t['valid'] else 'no'} |"
        )
    out.append("")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
