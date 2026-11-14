"""
The exploration's books against the equal-weight hold as the owner defined it on
2026-11-14 (each coin bought with its own 1/N of the starting account at its first
decision bar, held to the last close; ``strategy_lab.ensemble.Ensemble.hold``). The
exploration's first hold sized late coins from the grown account and so skipped two of
them. Same universe, costs and account as ``run_compare_ensemble.py``; the books are
replayed again to check they are unchanged. Writes the same structure as
``ensemble_periods.py``, so ``ensemble_difference.py`` runs on it as it is. Reported
only: nothing is saved in the sandbox or logged as a trial.

    python hold_correction.py <app dir> <out file> <compare9 driver> <compare-ensemble driver>
"""

from __future__ import annotations

import importlib.util
import json
import sys


def _module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv) -> None:
    app, out, driver, ensemble_driver = argv[1:5]
    c9 = _module("run_compare9", driver)
    ce = _module("run_compare_ensemble", ensemble_driver)
    c9._setup(app)
    import pandas as pd

    from research_stats import drawdowns, periods
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
    plan = group.hold_plan(costs, usd, start_s)
    hold = group.hold(costs, usd, start_s, detail=True)
    held = {
        "net_usd": float(hold.net[0]),
        "trades": int(hold.trades[0]),
        "skipped_cash": int(hold.skipped_cash[0]),
        "max_drawdown": float(hold.max_drawdown[0]),
        "intrabar_max_drawdown": (
            float(hold.intrabar_max_drawdown[0])
            if hold.intrabar_max_drawdown is not None
            else None
        ),
        "plan": plan,
        "periods": periods.report(*hold.curve),
        "drawdowns": drawdowns.report(*hold.curve),
    }
    result = {}
    for name, policy in (
        ("own-sizing", sizing.Fixed()),
        ("vol-target", sizing.from_record(ce.TARGET)),
    ):
        book = group.replay(costs, usd, policy, start_s, detail=True)
        members = {
            str(n): float(group.replay(costs, usd, policy, start_s, members=[n]).net[0])
            for n in group.lookbacks
        }
        result[name] = {
            "book": {
                "net_usd": float(book.net[0]),
                "max_drawdown": float(book.max_drawdown[0]),
                "periods": periods.report(*book.curve),
                "drawdowns": drawdowns.report(*book.curve),
            },
            "members_net_usd": members,
            "equal_weight_hold": held,
        }
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2, sort_keys=True, default=str)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv)
