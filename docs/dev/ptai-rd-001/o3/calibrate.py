"""
O3 calibration of the stationary-bootstrap test of return per capital-day
(PTAI-RD-001 work package 1.11; ``app/research_stats/resampling.py``).

Synthetic data only: no market data, no network. Run from the repository root:

    python docs/dev/ptai-rd-001/o3/calibrate.py            # the full grid, 6 workers
    python docs/dev/ptai-rd-001/o3/calibrate.py --quick --out <scratch file>

**Variants** (all through ``rpcd_test``):

* A: ``method="percentile", block_scale=1.0`` (the method of PR #266)
* B: ``method="studentised", block_scale=1.0`` (bootstrap-t, Bartlett HAC)
* C: ``method="percentile", block_scale=1.5``
* D: ``method="studentised", block_scale=1.5``

**Scenarios.** Null (no edge): AR(1) daily results with phi 0, 0.4 and 0.7; AR(0.4)
with Student-t(3) shocks; GARCH(1,1) (omega 0.05, alpha 0.1, beta 0.85); and marked
trades (a martingale random-walk price, random long-only trades of 20 to 60 days with
flat gaps of 30 to 120 days, marked by ``daily_marks``). Each at N = 750 and 1500 days.
Power: AR(0.4) plus 0.1 and plus 0.2 a day (in units of the shock's SD, as in the
earlier measurement), and marked trades with a positive drift. The drift is chosen by a
pilot that runs variant A only: the grid value whose power at N = 750 is closest to 50%.

**Replications** (the owner's rule): every simulation is 10 seeded runs, reported
pooled and per run. Size: 10 x 100 = 1000 replications per scenario, length and
variant. Power and pilot: 10 x 30 = 300. Each test uses 999 bootstrap draws, so
(B + 1) x 5% is a whole number. The four variants see the same data and the same
bootstrap seed in each replication.

**Decision rule, declared before the run** (the calibration brief, 2026-11-12): choose the
variant whose worst pooled null size at nominal 5%, across all null scenarios and both
lengths, is at most 6.0%. Among those, the one with the highest pooled power averaged
over the power cells (the three power scenarios at both lengths, equal weights). A tie
within 2 points of power goes to the simpler (A < C < B < D). If none is at most 6.0%,
choose the one with the lowest worst-case size, and say plainly that none met 6%.
"""

from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import json
import math
import multiprocessing as mp
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "app"))

from research_stats import resampling as rs  # noqa: E402

VARIANTS = {
    "A": ("percentile", 1.0),
    "B": ("studentised", 1.0),
    "C": ("percentile", 1.5),
    "D": ("studentised", 1.5),
}
SIMPLER_FIRST = ("A", "C", "B", "D")
ALPHAS = (0.01, 0.05, 0.10)
LENGTHS = (750, 1500)
DRAWS = 999
RUNS = 10
SIZE_REPS = 100
POWER_REPS = 30
BASE_SEED = 20261112
SIZE_LIMIT = 0.060
TIE_POINTS = 0.02
PILOT_DRIFTS = (0.001, 0.002, 0.003, 0.004, 0.005)
TRADE_SIGMA = 0.03  # the price's daily log-return SD

NULL_SCENARIOS = ("ar0.0", "ar0.4", "ar0.7", "t3-ar0.4", "garch", "trades")
POWER_SCENARIOS = ("ar0.4+0.1", "ar0.4+0.2", "trades+drift")
SCENARIO_IDS = {
    name: i for i, name in enumerate(NULL_SCENARIOS + POWER_SCENARIOS + ("pilot",))
}


# -- synthetic series ----------------------------------------------------------------------


def ar1(n, phi, rng, shocks="normal"):
    if shocks == "t3":
        e = rng.standard_t(3, n) / math.sqrt(3.0)  # unit variance
    else:
        e = rng.normal(0.0, 1.0, n)
    x = np.empty(n)
    x[0] = e[0] / math.sqrt(1.0 - phi**2)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + e[t]
    return x


def garch(n, rng, omega=0.05, alpha=0.10, beta=0.85, burn=500):
    """GARCH(1,1) with normal shocks; unconditional variance omega / (1 - alpha - beta) = 1."""
    e = rng.normal(0.0, 1.0, n + burn)
    r = np.empty(n + burn)
    h = omega / (1.0 - alpha - beta)
    prev = 0.0
    for t in range(n + burn):
        h = omega + alpha * prev**2 + beta * h
        prev = math.sqrt(h) * e[t]
        r[t] = prev
    return r[burn:]


def marked_trades(n, rng, drift=0.0, sigma=TRADE_SIGMA):
    """One coin. Its close is a geometric random walk whose daily gross return has mean
    exp(drift), so with drift 0 the price is a martingale and the strategy has no edge.
    Long-only trades of 20 to 60 days (entry at a day's close), separated by flat gaps
    of 30 to 120 days, each committing 50 to 150 USD; no costs. Marked by daily_marks, so
    most days carry no capital and no profit or loss."""
    lr = rng.normal(drift - 0.5 * sigma**2, sigma, n)
    close = 100.0 * np.exp(np.cumsum(lr))
    closes = {"X": {d: float(close[d]) for d in range(n)}}
    trades = []
    d0 = int(rng.integers(0, 121))
    while True:
        d1 = d0 + int(rng.integers(20, 61)) - 1  # the last day held
        if d1 >= n:
            break
        amount = float(rng.uniform(50.0, 150.0))
        units = amount / close[d0]
        trades.append(
            {
                "coin": "X",
                "entry_s": d0 * rs.DAY_S + 60,
                "exit_s": (d1 + 1) * rs.DAY_S,
                "amount": amount,
                "entry_price": float(close[d0]),
                "net": units * float(close[d1]) - amount,
            }
        )
        d0 = d1 + 1 + int(rng.integers(30, 121))
    return rs.daily_marks(trades, closes, 0, n)


def daily(x):
    return rs.DailyMarks(0, np.asarray(x, dtype=float), np.ones(len(x)))


def make(scenario, n, rng, drift):
    if scenario == "ar0.0":
        return daily(ar1(n, 0.0, rng))
    if scenario == "ar0.4":
        return daily(ar1(n, 0.4, rng))
    if scenario == "ar0.7":
        return daily(ar1(n, 0.7, rng))
    if scenario == "t3-ar0.4":
        return daily(ar1(n, 0.4, rng, shocks="t3"))
    if scenario == "garch":
        return daily(garch(n, rng))
    if scenario == "trades":
        return marked_trades(n, rng)
    if scenario == "ar0.4+0.1":
        return daily(ar1(n, 0.4, rng) + 0.1)
    if scenario == "ar0.4+0.2":
        return daily(ar1(n, 0.4, rng) + 0.2)
    if scenario in ("trades+drift", "pilot"):
        return marked_trades(n, rng, drift=drift)
    raise ValueError(scenario)


# -- one task: one run of one cell ---------------------------------------------------------


def run_cell(task):
    scenario, n, run, reps, variants, drift = task
    sid = SCENARIO_IDS[scenario]
    out = {
        v: {"rej": {str(a): 0 for a in ALPHAS}, "reps": 0, "block_sum": 0.0}
        for v in variants
    }
    held = 0.0
    t0 = time.perf_counter()
    for rep in range(reps):
        rng = np.random.default_rng([BASE_SEED, sid, n, run, rep])
        marks = make(scenario, n, rng, drift)
        held += float(np.mean(marks.capital > 0))
        seed = int(
            np.random.SeedSequence([BASE_SEED, 99, sid, n, run, rep]).generate_state(1)[
                0
            ]
        )
        for v in variants:
            method, scale = VARIANTS[v]
            res = rs.rpcd_test(
                marks, draws=DRAWS, seed=seed, method=method, block_scale=scale
            )
            cell = out[v]
            cell["reps"] += 1
            cell["block_sum"] += res.mean_block
            for a in ALPHAS:
                cell["rej"][str(a)] += int(res.p_value <= a)
    return {
        "scenario": scenario,
        "n": n,
        "run": run,
        "drift": drift,
        "held_share": held / max(1, reps),
        "seconds": time.perf_counter() - t0,
        "variants": out,
    }


def pool(rows, variants):
    """Per (scenario, n): each variant's per-run counts and the pooled rates."""
    cells = {}
    for r in rows:
        cells.setdefault((r["scenario"], r["n"]), []).append(r)
    table = []
    for (scenario, n), rs_ in sorted(cells.items(), key=lambda kv: kv[0]):
        rs_.sort(key=lambda r: r["run"])
        entry = {
            "scenario": scenario,
            "n": n,
            "drift": rs_[0]["drift"],
            "held_share": float(np.mean([r["held_share"] for r in rs_])),
            "variants": {},
        }
        for v in variants:
            per_run = []
            for r in rs_:
                c = r["variants"][v]
                per_run.append(
                    {
                        "run": r["run"],
                        "reps": c["reps"],
                        "rejections": c["rej"]["0.05"],
                        "rejections_by_alpha": c["rej"],
                        "mean_block": c["block_sum"] / max(1, c["reps"]),
                    }
                )
            reps = sum(p["reps"] for p in per_run)
            rej = {
                str(a): sum(p["rejections_by_alpha"][str(a)] for p in per_run)
                for a in ALPHAS
            }
            rates = [p["rejections"] / p["reps"] for p in per_run]
            entry["variants"][v] = {
                "runs": per_run,
                "pooled": {
                    "reps": reps,
                    "rejections": rej["0.05"],
                    "rate": rej["0.05"] / reps,
                    "rejections_by_alpha": rej,
                    "rate_by_alpha": {a: k / reps for a, k in rej.items()},
                    "per_run_min": min(rates),
                    "per_run_max": max(rates),
                    "mean_block": float(
                        np.sum([p["mean_block"] * p["reps"] for p in per_run]) / reps
                    ),
                },
            }
        table.append(entry)
    return table


def decide(size, power, variants):
    worst = {v: max(e["variants"][v]["pooled"]["rate"] for e in size) for v in variants}
    mean_power = {
        v: float(np.mean([e["variants"][v]["pooled"]["rate"] for e in power]))
        for v in variants
    }
    eligible = [v for v in variants if worst[v] <= SIZE_LIMIT]
    if eligible:
        best = max(mean_power[v] for v in eligible)
        near = [v for v in eligible if mean_power[v] >= best - TIE_POINTS]
        chosen = min(near, key=SIMPLER_FIRST.index)
        why = (
            f"worst null size {worst[chosen]:.3f} <= {SIZE_LIMIT}; mean power "
            f"{mean_power[chosen]:.3f} (best eligible {best:.3f}; within {TIE_POINTS} "
            "goes to the simpler)"
        )
    else:
        chosen = min(variants, key=lambda v: (worst[v], SIMPLER_FIRST.index(v)))
        why = f"none met {SIZE_LIMIT}; lowest worst-case size {worst[chosen]:.3f}"
    return {
        "worst_null_size": worst,
        "mean_power": mean_power,
        "eligible": eligible,
        "chosen": chosen,
        "why": why,
    }


def git_head():
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def run_tasks(pool_, tasks, label):
    rows, t0 = [], time.perf_counter()
    for i, row in enumerate(pool_.imap_unordered(run_cell, tasks, chunksize=1), 1):
        rows.append(row)
        if i % 10 == 0 or i == len(tasks):
            print(
                f"[{label}] {i}/{len(tasks)} tasks, {time.perf_counter() - t0:.0f}s",
                flush=True,
            )
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--quick", action="store_true", help="2 runs x 4 reps: a smoke run")
    ap.add_argument("--out", default=str(Path(__file__).with_name("results.json")))
    args = ap.parse_args()
    runs, size_reps, power_reps = (
        (2, 4, 4) if args.quick else (RUNS, SIZE_REPS, POWER_REPS)
    )
    variants = tuple(VARIANTS)
    started = time.perf_counter()
    ctx = mp.get_context("spawn")
    with ctx.Pool(min(6, args.workers)) as p:
        # 1. the pilot: variant A only, marked trades with drift, N = 750
        pilot_tasks = [
            ("pilot", 750, run, power_reps, ("A",), d)
            for d in PILOT_DRIFTS
            for run in range(runs)
        ]
        pilot_rows = run_tasks(p, pilot_tasks, "pilot")
        pilot = []
        for d in PILOT_DRIFTS:
            rows = [r for r in pilot_rows if r["drift"] == d]
            entry = pool(rows, ("A",))[0]
            pilot.append(entry)
        drift = min(
            PILOT_DRIFTS,
            key=lambda d: (
                abs(
                    next(e for e in pilot if e["drift"] == d)["variants"]["A"][
                        "pooled"
                    ]["rate"]
                    - 0.5
                ),
                d,
            ),
        )
        print(f"pilot: drift {drift} a day", flush=True)
        # 2. the grid: slowest first
        tasks = []
        for n in sorted(LENGTHS, reverse=True):
            for s in NULL_SCENARIOS:
                tasks += [(s, n, run, size_reps, variants, 0.0) for run in range(runs)]
            for s in POWER_SCENARIOS:
                dr = drift if s == "trades+drift" else 0.0
                tasks += [(s, n, run, power_reps, variants, dr) for run in range(runs)]
        rows = run_tasks(p, tasks, "grid")
    size = pool([r for r in rows if r["scenario"] in NULL_SCENARIOS], variants)
    power = pool([r for r in rows if r["scenario"] in POWER_SCENARIOS], variants)
    decision = decide(size, power, variants)
    result = {
        "meta": {
            "what": "O3 calibration of research_stats.resampling.rpcd_test",
            "git_head": git_head(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "draws": DRAWS,
            "runs": runs,
            "size_reps_per_run": size_reps,
            "power_reps_per_run": power_reps,
            "workers": min(6, args.workers),
            "base_seed": BASE_SEED,
            "variants": {
                v: {"method": m, "block_scale": s} for v, (m, s) in VARIANTS.items()
            },
            "null_scenarios": NULL_SCENARIOS,
            "power_scenarios": POWER_SCENARIOS,
            "lengths": LENGTHS,
            "pilot_drifts": PILOT_DRIFTS,
            "trades_drift": drift,
            "trade_sigma": TRADE_SIGMA,
            "rule": {
                "size_limit": SIZE_LIMIT,
                "tie_points": TIE_POINTS,
                "simpler_first": SIMPLER_FIRST,
            },
            "seconds": time.perf_counter() - started,
        },
        "pilot": pilot,
        "size": size,
        "power": power,
        "decision": decision,
    }
    Path(args.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print_tables(result)


def print_tables(result):
    vs = tuple(result["meta"]["variants"])
    print(
        f"\nruntime {result['meta']['seconds']:.0f}s; trades drift {result['meta']['trades_drift']}"
    )
    for title, table in (("size", result["size"]), ("power", result["power"])):
        print(f"\n{title}: pooled % (per-run min-max); mean block")
        for e in table:
            cells = []
            for v in vs:
                p = e["variants"][v]["pooled"]
                cells.append(
                    f"{v} {100 * p['rate']:.1f} ({100 * p['per_run_min']:.0f}-"
                    f"{100 * p['per_run_max']:.0f}) L={p['mean_block']:.1f}"
                )
            print(f"{e['scenario']:>13} N={e['n']:<5} " + " | ".join(cells))
    d = result["decision"]
    print(
        "\nworst null size:",
        {v: round(100 * x, 1) for v, x in d["worst_null_size"].items()},
    )
    print("mean power:", {v: round(100 * x, 1) for v, x in d["mean_power"].items()})
    print("chosen:", d["chosen"], "-", d["why"])


if __name__ == "__main__":
    main()
