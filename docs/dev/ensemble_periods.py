"""
The ensemble books' period returns and drawdown spells for the exploration's report:
the same universe, costs and account as ``run_compare_ensemble.py``'s saved runs, through
``strategy_lab.ensemble`` with ``detail=True``. Reported only: nothing is saved or logged
(the runs were logged as trials when they ran).

    python ensemble_periods.py <app dir> <out file> <compare9 driver>
"""

from __future__ import annotations

import importlib.util
import json
import sys


def main(argv) -> None:
    app, out, driver = argv[1], argv[2], argv[3]
    spec = importlib.util.spec_from_file_location("run_compare9", driver)
    c9 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c9)
    c9._setup(app)
    import pandas as pd

    from research_stats import drawdowns, periods
    from signal_fusion.evaluation.replay import Costs
    from strategy_lab import ensemble, runs, sizing

    here = importlib.util.spec_from_file_location(
        "run_compare_ensemble",
        argv[0].replace("ensemble_periods.py", "run_compare_ensemble.py"),
    )
    ce = importlib.util.module_from_spec(here)
    here.loader.exec_module(ce)

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
    for name, policy in (
        ("own-sizing", sizing.Fixed()),
        ("vol-target", sizing.from_record(ce.TARGET)),
    ):
        book = group.replay(costs, usd, policy, start_s, detail=True)
        hold = group.hold(costs, usd, start_s)
        result[name] = {
            "book": {
                "net_usd": float(book.net[0]),
                "max_drawdown": float(book.max_drawdown[0]),
                "periods": periods.report(*book.curve),
                "drawdowns": drawdowns.report(*book.curve),
            },
        }
        held = group.sims[group.lookbacks[0]].replay(
            ensemble.bl.hold_trades(group.sims[group.lookbacks[0]], start_s),
            costs,
            ensemble.Account(
                start=usd,
                start_pct=100.0 / len(group.coins),
                max_coin_pct=100.0 / len(group.coins),
            ),
            detail=True,
        )
        result[name]["equal_weight_hold"] = {
            "net_usd": float(held.net[0]),
            "check_net_usd": float(hold.net[0]),
            "periods": periods.report(*held.curve),
            "drawdowns": drawdowns.report(*held.curve),
        }
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2, sort_keys=True, default=str)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv)
