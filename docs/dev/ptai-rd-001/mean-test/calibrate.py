"""
Calibration of the stationary-bootstrap test of a daily series' mean
(``research_stats.resampling.mean_test``), for SR1-E2's comparison with an equal-weight
hold (``docs/dev/ptai-rd-001/E2-ensemble-registration-draft.md``, §8 item 2). It mirrors
O3's calibration of ``rpcd_test`` (``docs/dev/ptai-rd-001/o3/calibrate.py``).

Synthetic data only: no market data, no network. Run from the repository root:

    python docs/dev/ptai-rd-001/mean-test/calibrate.py            # the full grid, 6 workers
    python docs/dev/ptai-rd-001/mean-test/calibrate.py --quick --out <scratch file>

**Variants** (all through ``mean_test``), lettered as in O3:

* A: ``method="percentile", block_scale=1.0``
* B: ``method="studentised", block_scale=1.0``
* C: ``method="percentile", block_scale=1.5``
* D: ``method="studentised", block_scale=1.5`` (the default: O3's choice)

**Null scenarios** (mean 0, shocks of unit variance): independent days with normal and
with Student-t(3) values; AR(1) with phi 0.4 and 0.7, each with normal and with t(3)
shocks; and a volatility cluster, GARCH(1,1) with normal shocks (omega 0.05, alpha 0.1,
beta 0.85, so an unconditional variance of 1). Each at N = 750 and 1580 days (the
development period is about 1,586).

**Power scenarios:** independent normal days, AR(0.4) with t(3) shocks, and the GARCH
series, each with a mean of 0.5, 1.0 and 2.5 standard errors added. The standard error
is the sample mean's exact one for that process and N. A one-sided z-test at 5% that
knew the standard error would have power 12.6%, 26.0% and 80.4% at those means.

**Replications** (the owner's rule): every cell is 10 seeded runs of 100 replications,
1000 in all, reported pooled and per run. Each test uses 999 bootstrap draws, so
(B + 1) x 5% is a whole number. In each replication the four variants see the same data
and the same bootstrap seed, so the comparisons between variants are paired. Each
interval is at 95%; its coverage of the true mean is counted too.

**This run chooses nothing** (declared before it ran). SR1-E2's draft names variant D,
O3's default. The write-up reports D's worst pooled null size at nominal 5%, across every
null scenario and both lengths, against O3's limit of 6.0%, and says plainly if it is
above it. No default of ``rpcd_test`` or ``mean_test`` changes with this run.
"""

from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import hashlib
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

RESAMPLING = "app/research_stats/resampling.py"
VARIANTS = {
    "A": ("percentile", 1.0),
    "B": ("studentised", 1.0),
    "C": ("percentile", 1.5),
    "D": ("studentised", 1.5),
}
NAMED = "D"  # the variant SR1-E2's draft names
ALPHAS = (0.01, 0.05, 0.10)
LEVEL = 0.95
LENGTHS = (750, 1580)
DRAWS = 999
RUNS = 10
REPS = 100
BASE_SEED = 20261114
SIZE_LIMIT = 0.060  # O3's limit, reported against, deciding nothing here

# process: (AR phi, shocks); "garch" is the volatility cluster
PROCESSES = {
    "iid": (0.0, "normal"),
    "t3": (0.0, "t3"),
    "ar0.4": (0.4, "normal"),
    "t3-ar0.4": (0.4, "t3"),
    "ar0.7": (0.7, "normal"),
    "t3-ar0.7": (0.7, "t3"),
    "garch": None,
}
NULL_PROCESSES = tuple(PROCESSES)
POWER_PROCESSES = ("iid", "t3-ar0.4", "garch")
EFFECTS = (0.5, 1.0, 2.5)  # in standard errors of the sample mean
# every cell: (process, effect); its index seeds its data
CELLS = tuple((p, 0.0) for p in NULL_PROCESSES) + tuple(
    (p, e) for e in EFFECTS for p in POWER_PROCESSES
)


def cell_name(process, effect):
    return process if effect == 0 else f"{process}+{effect:g}se"


# -- synthetic series ----------------------------------------------------------------------


def shocks(n, kind, rng):
    if kind == "t3":
        return rng.standard_t(3, n) / math.sqrt(3.0)  # unit variance
    return rng.normal(0.0, 1.0, n)


def ar1(n, phi, kind, rng):
    e = shocks(n, kind, rng)
    x = np.empty(n)
    x[0] = e[0] / math.sqrt(1.0 - phi**2)  # stationary from the first day
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


def series(process, n, rng):
    if process == "garch":
        return garch(n, rng)
    phi, kind = PROCESSES[process]
    return ar1(n, phi, kind, rng)


def phi_of(process):
    """The AR coefficient; GARCH days are uncorrelated."""
    return 0.0 if process == "garch" else PROCESSES[process][0]


def mean_se(process, n):
    """The sample mean's exact standard error over n days. GARCH days are uncorrelated
    with variance 1; an AR(1) with unit shocks has R(k) = phi^k / (1 - phi^2), so
    Var(mean) = R(0) / n x (1 + 2 sum_{k<n} (1 - k/n) phi^k)."""
    phi = phi_of(process)
    if phi == 0.0:
        return 1.0 / math.sqrt(n)
    k = np.arange(1, n)
    var = (1.0 / (1.0 - phi**2)) / n * (1.0 + 2.0 * np.sum((1.0 - k / n) * phi**k))
    return math.sqrt(var)


def z_power(effect, alpha=0.05):
    """A one-sided z-test's power at ``effect`` standard errors, the standard error known."""
    lo, hi = -10.0, 10.0  # the normal quantile 1 - alpha, by bisection
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if 0.5 * math.erfc(mid / math.sqrt(2.0)) > alpha:
            lo = mid
        else:
            hi = mid
    return 0.5 * math.erfc((lo - effect) / math.sqrt(2.0))


def worst_of_exact(cells, reps, alpha=0.05, limit=SIZE_LIMIT):
    """For a test of exactly ``alpha``: the expected worst of ``cells`` independent
    pooled rates of ``reps`` replications, and the chance that the worst is above
    ``limit`` (exact binomial)."""

    def pmf(k):
        return math.exp(
            math.lgamma(reps + 1)
            - math.lgamma(k + 1)
            - math.lgamma(reps - k + 1)
            + k * math.log(alpha)
            + (reps - k) * math.log(1.0 - alpha)
        )

    cdf, total, expected = [], 0.0, 0.0
    for k in range(reps + 1):
        total += pmf(k)
        cdf.append(min(1.0, total))
    prev = 0.0
    for k in range(reps + 1):
        now = cdf[k] ** cells
        expected += k / reps * (now - prev)
        prev = now
    above = 1.0 - cdf[int(math.floor(limit * reps + 1e-9))] ** cells
    return {"expected_worst": expected, "chance_worst_above_limit": above}


# -- one task: one run of one cell ---------------------------------------------------------


def run_cell(task):
    cid, n, run, reps = task
    process, effect = CELLS[cid]
    true_mean = effect * mean_se(process, n)
    out = {
        v: {
            "rej": {str(a): 0 for a in ALPHAS},
            "covered": 0,
            "interval_above": 0,
            "interval_below": 0,
            "reps": 0,
            "block_sum": 0.0,
        }
        for v in VARIANTS
    }
    t0 = time.perf_counter()
    for rep in range(reps):
        rng = np.random.default_rng([BASE_SEED, cid, n, run, rep])
        x = series(process, n, rng) + true_mean
        seed = int(
            np.random.SeedSequence([BASE_SEED, 99, cid, n, run, rep]).generate_state(1)[
                0
            ]
        )
        for v, (method, scale) in VARIANTS.items():
            res = rs.mean_test(
                x, draws=DRAWS, seed=seed, level=LEVEL, method=method, block_scale=scale
            )
            c = out[v]
            c["reps"] += 1
            c["block_sum"] += res.mean_block
            for a in ALPHAS:
                c["rej"][str(a)] += int(res.p_value <= a)
            lo, hi = res.interval
            if lo > true_mean:
                c["interval_above"] += 1
            elif hi < true_mean:
                c["interval_below"] += 1
            else:
                c["covered"] += 1
    return {
        "cell": cell_name(process, effect),
        "process": process,
        "effect_se": effect,
        "true_mean": true_mean,
        "n": n,
        "run": run,
        "seconds": time.perf_counter() - t0,
        "variants": out,
    }


def pool(rows):
    """Per (cell, n): each variant's per-run counts and the pooled rates."""
    cells = {}
    for r in rows:
        cells.setdefault((r["cell"], r["n"]), []).append(r)
    order = [cell_name(p, e) for p, e in CELLS]
    table = []
    for (cell, n), rs_ in sorted(
        cells.items(), key=lambda kv: (order.index(kv[0][0]), kv[0][1])
    ):
        rs_.sort(key=lambda r: r["run"])
        entry = {
            "cell": cell,
            "process": rs_[0]["process"],
            "effect_se": rs_[0]["effect_se"],
            "true_mean": rs_[0]["true_mean"],
            "n": n,
            "variants": {},
        }
        for v in VARIANTS:
            per_run = []
            for r in rs_:
                c = r["variants"][v]
                per_run.append(
                    {
                        "run": r["run"],
                        "reps": c["reps"],
                        "rejections": c["rej"]["0.05"],
                        "rejections_by_alpha": c["rej"],
                        "covered": c["covered"],
                        "interval_above": c["interval_above"],
                        "interval_below": c["interval_below"],
                        "mean_block": c["block_sum"] / max(1, c["reps"]),
                    }
                )
            reps = sum(p["reps"] for p in per_run)
            rej = {
                str(a): sum(p["rejections_by_alpha"][str(a)] for p in per_run)
                for a in ALPHAS
            }
            rate = rej["0.05"] / reps
            rates = [p["rejections"] / p["reps"] for p in per_run]
            entry["variants"][v] = {
                "runs": per_run,
                "pooled": {
                    "reps": reps,
                    "rejections": rej["0.05"],
                    "rate": rate,
                    "mc_se": math.sqrt(rate * (1.0 - rate) / reps),
                    "rejections_by_alpha": rej,
                    "rate_by_alpha": {a: k / reps for a, k in rej.items()},
                    "per_run_min": min(rates),
                    "per_run_max": max(rates),
                    "coverage": sum(p["covered"] for p in per_run) / reps,
                    "interval_above": sum(p["interval_above"] for p in per_run) / reps,
                    "interval_below": sum(p["interval_below"] for p in per_run) / reps,
                    "mean_block": float(
                        np.sum([p["mean_block"] * p["reps"] for p in per_run]) / reps
                    ),
                },
            }
        table.append(entry)
    return table


def summarise(size, power, reps):
    summary = {"named_variant": NAMED, "variants": {}}
    for v in VARIANTS:
        worst = max(size, key=lambda e: e["variants"][v]["pooled"]["rate"])
        cover = min(size, key=lambda e: e["variants"][v]["pooled"]["coverage"])
        by_effect = {
            str(eff): float(
                np.mean(
                    [
                        e["variants"][v]["pooled"]["rate"]
                        for e in power
                        if e["effect_se"] == eff
                    ]
                )
            )
            for eff in EFFECTS
        }
        summary["variants"][v] = {
            "worst_null_size": worst["variants"][v]["pooled"]["rate"],
            "worst_null_cell": f"{worst['cell']} N={worst['n']}",
            "mean_null_size": float(
                np.mean([e["variants"][v]["pooled"]["rate"] for e in size])
            ),
            "lowest_null_coverage": cover["variants"][v]["pooled"]["coverage"],
            "lowest_null_coverage_cell": f"{cover['cell']} N={cover['n']}",
            "mean_null_coverage": float(
                np.mean([e["variants"][v]["pooled"]["coverage"] for e in size])
            ),
            "mean_power_by_effect": by_effect,
            "mean_power": float(np.mean(list(by_effect.values()))),
        }
    d = summary["variants"][NAMED]
    summary["named_worst_above_limit"] = d["worst_null_size"] > SIZE_LIMIT
    summary["z_test_power_by_effect"] = {str(e): z_power(e) for e in EFFECTS}
    summary["chance"] = worst_of_exact(len(size), reps)
    summary["chance"]["cells"] = len(size)
    summary["chance"]["reps"] = reps
    return summary


# -- provenance ----------------------------------------------------------------------------


def git(*args):
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, timeout=30
        ).stdout
    except Exception:  # noqa: BLE001
        return b""


def sha256_lf(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def provenance():
    here = (ROOT / RESAMPLING).read_bytes()
    committed = git("show", f"HEAD:{RESAMPLING}")
    return {
        "git_head": git("rev-parse", "HEAD").decode().strip(),
        "resampling_sha256_lf": sha256_lf(here),
        "resampling_matches_head": bool(committed)
        and sha256_lf(committed) == sha256_lf(here),
        "calibrate_sha256_lf": sha256_lf(Path(__file__).read_bytes()),
    }


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
    runs, reps = (2, 4) if args.quick else (RUNS, REPS)
    started = time.perf_counter()
    prov = provenance()
    # the slowest first: the longer series, then the most dependent
    tasks = [
        (cid, n, run, reps)
        for n in sorted(LENGTHS, reverse=True)
        for cid in sorted(range(len(CELLS)), key=lambda c: -phi_of(CELLS[c][0]))
        for run in range(runs)
    ]
    ctx = mp.get_context("spawn")
    with ctx.Pool(min(6, args.workers)) as p:
        rows = run_tasks(p, tasks, "grid")
    size = pool([r for r in rows if r["effect_se"] == 0])
    power = pool([r for r in rows if r["effect_se"] != 0])
    result = {
        "meta": {
            "what": "Calibration of research_stats.resampling.mean_test (SR1-E2)",
            **prov,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "draws": DRAWS,
            "level": LEVEL,
            "runs": runs,
            "reps_per_run": reps,
            "workers": min(6, args.workers),
            "base_seed": BASE_SEED,
            "variants": {
                v: {"method": m, "block_scale": s} for v, (m, s) in VARIANTS.items()
            },
            "named_variant": NAMED,
            "null_processes": NULL_PROCESSES,
            "power_processes": POWER_PROCESSES,
            "effects_se": EFFECTS,
            "lengths": LENGTHS,
            "block_cap": {str(n): rs.block_cap(n) for n in LENGTHS},
            "mean_se": {p: {str(n): mean_se(p, n) for n in LENGTHS} for p in PROCESSES},
            "size_limit_reported_against": SIZE_LIMIT,
            "seconds": time.perf_counter() - started,
            "task_seconds": float(sum(r["seconds"] for r in rows)),
        },
        "size": size,
        "power": power,
        "summary": summarise(size, power, runs * reps),
    }
    Path(args.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print_tables(result)


def print_tables(result):
    meta = result["meta"]
    print(
        f"\nruntime {meta['seconds']:.0f}s ({meta['task_seconds']:.0f}s of work); "
        f"head {meta['git_head'][:7]}, module matches head: {meta['resampling_matches_head']}"
    )
    for title, table in (("size", result["size"]), ("power", result["power"])):
        print(f"\n{title}: pooled % at 5% (per-run min-max) cov% L")
        for e in table:
            cells = []
            for v in VARIANTS:
                p = e["variants"][v]["pooled"]
                cells.append(
                    f"{v} {100 * p['rate']:.1f} ({100 * p['per_run_min']:.0f}-"
                    f"{100 * p['per_run_max']:.0f}) {100 * p['coverage']:.1f} "
                    f"L={p['mean_block']:.1f}"
                )
            print(f"{e['cell']:>16} N={e['n']:<5} " + " | ".join(cells))
    s = result["summary"]
    for v, d in s["variants"].items():
        print(
            f"\n{v}: worst null size {100 * d['worst_null_size']:.1f} ({d['worst_null_cell']}), "
            f"mean {100 * d['mean_null_size']:.2f}; lowest coverage "
            f"{100 * d['lowest_null_coverage']:.1f} ({d['lowest_null_coverage_cell']}); "
            "power by effect "
            + ", ".join(
                f"{k}: {100 * x:.1f}" for k, x in d["mean_power_by_effect"].items()
            )
        )
    print(
        "\nz-test power:",
        {k: round(100 * x, 1) for k, x in s["z_test_power_by_effect"].items()},
    )
    print("chance (exact 5%):", s["chance"])
    print(f"{NAMED}'s worst above {SIZE_LIMIT}:", s["named_worst_above_limit"])


if __name__ == "__main__":
    main()
