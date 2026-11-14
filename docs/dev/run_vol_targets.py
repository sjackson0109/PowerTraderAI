"""
Volatility sizing at higher targets on the development months, in a sandbox, on public
candles (PTAI-RD-001 decision O18, 2026-11-13; exploration only).

At 25% a year (``run_compare_ensemble.py``) the sizing cut drawdowns no more than its own
sizes in random order did. A higher target keeps sizes nearer the account's own, which
shows whether the timing does anything beyond shrinking. The owner chose four runs:

* STRAT-004 at its catalogue defaults, targets 50% and 75% a year;
* STRAT-007 at its default with OVL-MIDLINE and the ensemble, targets 50% and 75%.

Everything else is as ``run_compare_ensemble.py``: the nine coins, a GBP 10,000 account at
0.50% + 0.05%, 2021-01-01 to 2025-05-06, EWMA (lambda 0.94), 10 seeded runs (seeds
700000 to 709000), seed 700000's run saved and logged as a trial, the ensemble once.

Run it only with a sandbox's folders, as ``run_compare_ensemble.py`` says.

    python run_vol_targets.py <app dir> <out dir> <compare9 driver> <compare-ensemble driver>
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

TARGETS = (0.50, 0.75)
STRATEGIES = [
    ("STRAT-004", {"entry_days": 55, "exit_days": 20}, [], False),
    ("STRAT-007", {"channel_days": 20}, [{"id": "OVL-MIDLINE"}], True),
]


def _module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def label(sid: str, ensemble: bool, target: float) -> str:
    return f"{sid}{' ensemble' if ensemble else ''} vol-target {round(target * 100)}%"


def main(argv) -> None:
    app, out, driver, ensemble_driver = argv[1], argv[2], argv[3], argv[4]
    c9 = _module("run_compare9", driver)
    ce = _module("run_compare_ensemble", ensemble_driver)
    c9._setup(app)  # refuses to run outside a sandbox
    from strategy_lab import runs

    done_dir = os.path.join(out, "lines")
    os.makedirs(done_dir, exist_ok=True)
    done_files = []
    for target in TARGETS:
        sizing = dict(ce.TARGET, target=target)
        for sid, params, overlays, ensemble in STRATEGIES:
            name = label(sid, ensemble, target)
            done = os.path.join(
                done_dir, name.replace(" ", "_").replace("%", "") + ".json"
            )
            done_files.append(done)
            if os.path.exists(done):
                continue
            per_seed = []
            for seed in ce.SEEDS:
                t0 = time.time()
                config = runs.RunConfig(
                    strategy_id=sid,
                    params=params,
                    overlays=overlays,
                    timeframe="1d",
                    coins=ce.COINS,
                    start=ce.START,
                    end=ce.END,
                    account_gbp=ce.ACCOUNT_GBP,
                    gbp_usd=ce.GBP_USD,
                    fee=ce.FEE,
                    allowance=ce.ALLOWANCE,
                    draws=ce.DRAWS,
                    seed=seed,
                    sizing=sizing,
                    ensemble=ensemble and seed == ce.SEEDS[0],
                )
                record = runs.run(
                    config, loader=c9.late_listing_loader, save=seed == ce.SEEDS[0]
                )
                print(f"{name} seed {seed}: {time.time() - t0:.0f} s", flush=True)
                per_seed.append(
                    record
                    if seed == ce.SEEDS[0]
                    else {
                        "seed": seed,
                        "strategy_result": record["strategy_result"],
                        "random_entries": record["random_entries"],
                        "sizing": record["sizing"],
                    }
                )
            with open(done, "w", encoding="utf-8", newline="\n") as f:
                json.dump(
                    {"label": name, "target": target, "runs": per_seed},
                    f,
                    indent=2,
                    sort_keys=True,
                    default=str,
                )
                f.write("\n")
    lines = []
    for path in done_files:
        with open(path, encoding="utf-8") as f:
            lines.append(json.load(f))
    with open(
        os.path.join(out, "vol_targets.json"), "w", encoding="utf-8", newline="\n"
    ) as f:
        json.dump(lines, f, indent=2, sort_keys=True, default=str)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv)
