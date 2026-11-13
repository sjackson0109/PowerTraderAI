"""
The ensemble books of the 25% exploration, recomputed on the code merged as #290, whose
replay passes the bars' highs as well as their lows. The runs behind
``ENSEMBLE-SIZING-EXPLORATION-dev.md`` used a tree from before that commit, so the
ensemble book's intrabar drawdown took its peak at the closes, while its members and
the equal-weight hold took theirs at the earlier highs. Everything else in the replay is
unchanged, so every other figure must come out the same: this checks that, and reports
the intrabar figures afresh. Nothing is saved or logged as a trial.

    python ensemble_recheck.py <app dir> <out file> <compare9 driver> <compare-ensemble driver> <saved lines dir>
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import sys


def _module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv) -> None:
    app, out, driver, ensemble_driver, saved = argv[1:6]
    c9 = _module("run_compare9", driver)
    ce = _module("run_compare_ensemble", ensemble_driver)
    c9._setup(app)  # refuses to run outside a sandbox
    import pandas as pd

    from signal_fusion.evaluation.replay import Costs
    from strategy_lab import ensemble, runs, sizing

    a, b = runs.development_only(ce.START, ce.END)
    spec7 = runs.RunConfig(
        strategy_id="STRAT-007",
        params={"channel_days": 20},
        overlays=[{"id": "OVL-MIDLINE"}],
        timeframe="1d",
        coins=ce.COINS,
        start=ce.START,
        end=ce.END,
        account_gbp=ce.ACCOUNT_GBP,
        gbp_usd=ce.GBP_USD,
        fee=ce.FEE,
        allowance=ce.ALLOWANCE,
    ).spec()
    first = max(
        runs.HISTORY_START,
        min(
            runs._warmup_start(spec7, a), a - pd.Timedelta(days=ensemble.warmup_days())
        ),
    )
    universe = runs.load_universe(
        list(ce.COINS), spec7, first, b, loader=c9.late_listing_loader
    )
    rules = runs.venue_rules(list(ce.COINS))
    costs = Costs(
        fee=ce.FEE,
        allowance=ce.ALLOWANCE,
        minimum_usd=rules.minimum_usd,
        base_increment=rules.base_increment,
    )
    usd = round(ce.ACCOUNT_GBP * ce.GBP_USD, 2)
    start_s = runs._seconds(a)
    group = ensemble.Ensemble(universe)
    result = {}
    for name, policy, line in (
        ("own-sizing", sizing.Fixed(), "STRAT-007_ensemble_own-sizing.json"),
        (
            "vol-target",
            sizing.from_record(ce.TARGET),
            "STRAT-007_ensemble_vol-target.json",
        ),
    ):
        fresh = ensemble.report(group, costs, usd, policy, start_s)
        with open(os.path.join(saved, line), encoding="utf-8") as f:
            old = json.load(f)["runs"][0]["ensemble"]
        changed = {}
        for part in ("ensemble", "equal_weight_hold"):
            for key, was in old[part].items():
                now = fresh[part].get(key)
                same = (
                    math.isclose(was, now, rel_tol=1e-9, abs_tol=1e-9)
                    if isinstance(was, float) and isinstance(now, float)
                    else was == now
                )
                if not same:
                    changed[f"{part}.{key}"] = {"saved": was, "recomputed": now}
        for n, member in old["members"].items():
            for key, was in member.items():
                now = fresh["members"][n].get(key)
                if isinstance(was, float) and isinstance(now, float):
                    same = math.isclose(was, now, rel_tol=1e-9, abs_tol=1e-9)
                else:
                    same = was == now
                if not same:
                    changed[f"members.{n}.{key}"] = {"saved": was, "recomputed": now}
        result[name] = {
            "changed": changed,
            "ensemble": fresh["ensemble"],
            "equal_weight_hold": fresh["equal_weight_hold"],
        }
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2, sort_keys=True, default=str)
        f.write("\n")
    for name, part in result.items():
        print(name, json.dumps(part["changed"], default=str))


if __name__ == "__main__":
    main(sys.argv)
