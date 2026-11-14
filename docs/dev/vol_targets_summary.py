"""
The tables of the exploration report's §4 (volatility sizing at 50% and 75% a year, O18),
beside the own-sizing and 25% runs: each strategy's own figures, the random orders of its
sizes pooled over the 10 seeds (with the range by seed), the random entries, and the
ensemble's book. The 25% and own-sizing books' intrabar figures come from the recheck on
the merged code (``ensemble_recheck.py``). Reads saved records only; nothing is run.

    python vol_targets_summary.py <25% lines dir> <O18 lines dir> <recheck json> <out json>
"""

from __future__ import annotations

import json
import os
import sys

FIRST = [
    ("STRAT-004", "own", "STRAT-004_own-sizing.json"),
    ("STRAT-004", "25%", "STRAT-004_vol-target.json"),
    ("STRAT-007", "own", "STRAT-007_ensemble_own-sizing.json"),
    ("STRAT-007", "25%", "STRAT-007_ensemble_vol-target.json"),
]
O18 = [
    ("STRAT-004", "50%", "STRAT-004_vol-target_50.json"),
    ("STRAT-004", "75%", "STRAT-004_vol-target_75.json"),
    ("STRAT-007", "50%", "STRAT-007_ensemble_vol-target_50.json"),
    ("STRAT-007", "75%", "STRAT-007_ensemble_vol-target_75.json"),
]
RECHECKED = {"own": "own-sizing", "25%": "vol-target"}


def _spread(values):
    return {"pooled": sum(values) / len(values), "min": min(values), "max": max(values)}


def row(sid: str, sizing: str, path: str, recheck) -> dict:
    with open(path, encoding="utf-8") as f:
        runs = json.load(f)["runs"]
    first = runs[0]
    own = first["strategy_result"]
    out = {
        "strategy": sid,
        "sizing": sizing,
        "seeds": len(runs),
        **{
            k: own[k]
            for k in (
                "net_usd",
                "max_drawdown",
                "intrabar_max_drawdown",
                "trades",
                "return_per_capital_day",
                "mean_committed",
            )
        },
        "random_entries_at_or_above": _spread(
            [r["random_entries"]["share_at_or_above"] for r in runs]
        ),
    }
    sized = first.get("sizing") or {}
    if sized.get("mean_scale") is not None:
        out["mean_scale"] = sized["mean_scale"]
        out["random_order_drawdown_at_or_below"] = _spread(
            [r["sizing"]["random_order"]["share_drawdown_at_or_below"] for r in runs]
        )
        out["random_order_net_at_or_above"] = _spread(
            [r["sizing"]["random_order"]["share_net_at_or_above"] for r in runs]
        )
    book = (first.get("ensemble") or {}).get("ensemble")
    if book:
        intrabar = book["intrabar_max_drawdown"]
        if sizing in RECHECKED:
            intrabar = recheck[RECHECKED[sizing]]["ensemble"]["intrabar_max_drawdown"]
        out["ensemble"] = {
            "net_usd": book["net_usd"],
            "max_drawdown": book["max_drawdown"],
            "intrabar_max_drawdown": intrabar,
            "trades": book["trades"],
            "skipped_cash": book["skipped_cash"],
            "mean_committed": book["mean_committed"],
            "halt_reached": book["halt_reached"],
            "net_per_point_of_fall": book["net_usd"] / (100 * book["max_drawdown"]),
        }
    return out


def main(argv) -> None:
    first_dir, o18_dir, recheck_path, out = argv[1:5]
    with open(recheck_path, encoding="utf-8") as f:
        recheck = json.load(f)
    rows = [row(s, z, os.path.join(first_dir, n), recheck) for s, z, n in FIRST]
    rows += [row(s, z, os.path.join(o18_dir, n), recheck) for s, z, n in O18]
    order = {"own": 0, "25%": 1, "50%": 2, "75%": 3}
    rows.sort(key=lambda r: (r["strategy"], order[r["sizing"]]))
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv)
