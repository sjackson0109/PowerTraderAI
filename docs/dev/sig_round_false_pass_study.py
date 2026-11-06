"""
FDS-SIG-001 section 16 item 2 at round scale (the PR #228 review, finding 4): the
false-pass rate of whole simulated rounds with no skill in them, F = 76 as round one's
draft registers (SIG-A on ten coins and SIG-B on nine, on 1h and 4h), dependent between
coins, timeframes and statistics (``signal_audit.nullsim``, its module docstring), with
the full bootstrap (B >= 100 / alpha_1 = 152,000). Every simulation runs locally in 10
independent runs (owner, 2026-11-06). Verification on simulated data only: no market
data, no network, no verdict.

    python docs/dev/sig_round_false_pass_study.py [--rounds 300] [--runs 10] [--jobs 10]

Run r is seeded ``--seed + r`` and gives the same figures however many jobs share the
work. Writes ``docs/dev/sig-audit/verification/round-false-pass-study.json``. A check
with real skill (``--lead``: one coin's return follows BTC's previous return) runs
after it, to show a pass is still found. The unit tests
(``app/tests/test_signal_audit_false_pass.py``) check the simulation and that the
study's shortcut reaches the engine's own decisions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "app"))

from signal_audit import nullsim  # noqa: E402


def one_run(job):
    rounds, seed, r, lead, days = job
    t0 = time.time()
    res = nullsim.round_false_passes(
        rounds, 1, seed, days=days, lead=lead, run_numbers=[r]
    )
    run = res["runs"][0]
    run["seconds"] = round(time.time() - t0, 1)
    print(
        f"run {r} (seed {seed + r}): {run['rounds_with_pass']} of {run['rounds']} "
        f"rounds with a PASS, {run['rounds_with_worse']} with a WORSE; per test "
        f"{run['per_test_passes']} of {run['assessable']}; {run['seconds']}s",
        flush=True,
    )
    return run


def study(rounds, runs, seed, jobs, lead=None, days=270):
    work = [(rounds, seed, r, lead, days) for r in range(runs)]
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            out = list(pool.map(one_run, work))
    else:
        out = [one_run(w) for w in work]
    return nullsim.combine_round_runs(
        out,
        {
            "bootstrap_draws": nullsim.st.min_bootstrap_draws(out[0]["family_size"]),
            "coins": 10,
            "days": days,
            "timeframes": ["1h", "4h"],
            "screen": nullsim.st.FAMILY_ERROR,
            "lead": lead or {},
        },
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=300, help="rounds per run")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--jobs", type=int, default=10)
    parser.add_argument("--days", type=int, default=270)  # the draft's window
    parser.add_argument("--seed", type=int, default=8_000_000)
    parser.add_argument("--lead-rounds", type=int, default=5)
    parser.add_argument("--lead-seed", type=int, default=8_100_000)
    parser.add_argument(
        "--out",
        default=os.path.join(
            REPO,
            "docs",
            "dev",
            "sig-audit",
            "verification",
            "round-false-pass-study.json",
        ),
    )
    args = parser.parse_args(argv)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(name, "1")
    t0 = time.time()
    null = study(args.rounds, args.runs, args.seed, args.jobs, days=args.days)
    null["seconds"] = round(time.time() - t0, 1)
    print(
        f"no skill: {null['rounds']} rounds, PASS in {null['family_rate']:.4f} of them "
        f"(5%, MC s.e. {null['family_mc_se']:.4f}), WORSE in "
        f"{null['family_rate_worse']:.4f}; per test {null['per_test_rate']:.6f} "
        f"(alpha_1 {null['alpha_1']:.6f}, MC s.e. {null['per_test_mc_se']:.6f})",
        flush=True,
    )
    lead = None
    if args.lead_rounds:
        t0 = time.time()
        lead = study(
            args.lead_rounds, args.runs, args.lead_seed, args.jobs, {3: 0.15}, args.days
        )
        lead["seconds"] = round(time.time() - t0, 1)
        found = sum(
            sum("SIG-B C03 1h" in p for p in run["pass_rows"]) for run in lead["runs"]
        )
        lead["rounds_finding_the_lead"] = found
        print(
            f"real skill (C03 follows BTC): PASS in {found} of {lead['rounds']} rounds",
            flush=True,
        )
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(
            {
                "what": "FDS-SIG-001 section 16 item 2 at round scale: false-pass rates "
                "of whole simulated rounds with no skill, F = 76, dependent rows "
                "(verification, no market data, no verdict)",
                "rounds_per_run": args.rounds,
                "runs": args.runs,
                "no_skill": null,
                "with_a_lead": lead,
            },
            f,
            indent=1,
            sort_keys=True,
        )
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
