"""
FDS-SIG-001 section 16 item 2 at full scale: the false-pass rates of no-skill rules,
every simulation run locally in 10 independent runs (owner, 2026-11-06), with the full
bootstrap (B >= 100 / alpha_1). Verification on simulated data only: no market data, no
network, no verdict.

    python docs/dev/sig_false_pass_study.py [--trials 400] [--runs 10] [--F 4]

Writes ``docs/dev/sig-audit/verification/false-pass-study.json``. The unit tests
(``app/tests/test_signal_audit_false_pass.py``) run the same scenarios at a smaller
scale.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "app"))

from signal_audit import nullsim  # noqa: E402
from signal_audit import stats as st  # noqa: E402

SCENARIOS = [
    ("random", st.HIT, {}),
    ("random", st.MAGNITUDE, {}),
    ("near_constant", st.HIT, {"up_share": 0.53}),
    ("near_constant", st.HIT, {"up_share": 0.47}),
    ("near_constant", st.MAGNITUDE, {"up_share": 0.53}),
    ("persistent", st.HIT, {}),
    ("persistent", st.MAGNITUDE, {}),
    ("drift", st.HIT, {"amplitude": 0.15, "kind": st.UP_ONLY}),
    ("drift", st.HIT, {"amplitude": 0.30, "kind": st.UP_ONLY}),
    ("drift", st.MAGNITUDE, {"amplitude": 0.15, "kind": st.TWO_SIDED}),
    ("drift", st.MAGNITUDE, {"amplitude": 0.30, "kind": st.TWO_SIDED}),
    # a cycle of exactly a month: its autocorrelations cancel in the Bartlett window,
    # so the block length stays at one day (the worst case for section 7.4's rule)
    ("drift", st.HIT, {"amplitude": 0.30, "kind": st.UP_ONLY, "period_days": 30}),
    (
        "drift",
        st.MAGNITUDE,
        {"amplitude": 0.30, "kind": st.TWO_SIDED, "period_days": 30},
    ),
    ("drift", st.HIT, {"amplitude": 0.15, "kind": st.UP_ONLY, "period_days": 30}),
    (
        "drift",
        st.MAGNITUDE,
        {"amplitude": 0.15, "kind": st.TWO_SIDED, "period_days": 30},
    ),
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=400)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--F", type=int, default=4)
    parser.add_argument("--E", type=int, default=4380)  # six months of 1h pairs
    parser.add_argument("--seed", type=int, default=7_000_000)
    parser.add_argument(
        "--only", type=int, nargs="*", help="run these scenario numbers only"
    )
    parser.add_argument(
        "--out",
        default=os.path.join(
            REPO, "docs", "dev", "sig-audit", "verification", "false-pass-study.json"
        ),
    )
    args = parser.parse_args(argv)
    results = []
    for i, (name, stat, kw) in enumerate(SCENARIOS):
        if args.only and i not in args.only:
            continue
        t0 = time.time()
        r = nullsim.false_pass_rates(
            name,
            stat,
            args.trials,
            args.runs,
            args.F,
            args.E,
            args.seed + 1000 * i,
            **kw,
        )
        r["seconds"] = round(time.time() - t0, 1)
        results.append(r)
        print(
            f"{name} {stat} {kw}: per test {r['per_test_rate']:.4f} (alpha/F "
            f"{r['alpha_1']:.4f}, MC s.e. {r['per_test_mc_se']:.4f}); per family "
            f"{r['family_rate']:.3f} (5%, MC s.e. {r['family_mc_se']:.3f}); "
            f"{r['seconds']}s",
            flush=True,
        )
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(
            {
                "what": "FDS-SIG-001 section 16 item 2: false-pass rates of no-skill "
                "rules on simulated data (verification, no market data, no verdict)",
                "trials_per_run": args.trials,
                "runs": args.runs,
                "family_size": args.F,
                "eligible_pairs": args.E,
                "scenarios": results,
            },
            f,
            indent=1,
            sort_keys=True,
        )
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
