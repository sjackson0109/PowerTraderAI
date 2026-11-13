"""
The Donchian ensemble and volatility sizing on the development months, in a sandbox, on
public candles (PTAI-RD-001 backlog 3.1 and work package 4.2; exploration only).

Run it only with a sandbox's folders (POWERTRADER_HOME, APPDATA and LOCALAPPDATA pointed
at scratch folders, a keyring that fails, no keys). Nothing here trades, registers or
enables anything, and nothing reads past 2025-05-06 (``strategy_lab.runs`` refuses it).

    python run_compare_ensemble.py <app dir> <out dir> <compare9 driver>

Four exploratory runs over the nine coins of the nine-coin comparison, one GBP 10,000
account at 0.50% + 0.05%, 2021-01-01 to 2025-05-06:

* STRAT-004 at its catalogue defaults, the account's own sizing (the comparison's best);
* the same with a volatility target of 25% a year (EWMA, lambda 0.94);
* STRAT-007 at its default with OVL-MIDLINE, and the ensemble of 20 to 360 days;
* the same with the volatility target.

Each is run as 10 seeded runs (seeds 700000 to 709000): the random entries and the
random orders of the sizes are drawn afresh per seed; everything else is the same in
each. Seed 700000's run is saved (and logged as a trial), as the app saves a run; the
other nine are reported only. ``<out dir>/compare_ensemble.json`` holds every figure.

It resumes: a finished config's figures are kept in ``<out dir>/lines/``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

COINS = ["BTC", "ETH", "XRP", "BNB", "DOGE", "SOL", "ZEC", "DASH", "HYPE"]
START = "2021-01-01"
END = "2025-05-06"
FEE = 0.005  # the owner's account rate, from the check window on 2026-11-05
ALLOWANCE = 0.0005
ACCOUNT_GBP = 10_000.0
GBP_USD = 1.3476  # BoE XUDLUSS for 2026-11-05, as E1 and the comparison used
DRAWS = 200
SEEDS = [700_000 + 1000 * k for k in range(10)]
TARGET = {"id": "volatility-target", "target": 0.25, "feature": "volatility.ewma"}
CONFIGS = [
    ("STRAT-004", {"entry_days": 55, "exit_days": 20}, [], False, None),
    ("STRAT-004", {"entry_days": 55, "exit_days": 20}, [], False, TARGET),
    ("STRAT-007", {"channel_days": 20}, [{"id": "OVL-MIDLINE"}], True, None),
    ("STRAT-007", {"channel_days": 20}, [{"id": "OVL-MIDLINE"}], True, TARGET),
]


def _label(sid, sizing, ensemble) -> str:
    return (
        sid
        + (" ensemble" if ensemble else "")
        + (" vol-target" if sizing else " own-sizing")
    )


def _compare9(path: str):
    spec = importlib.util.spec_from_file_location("run_compare9", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv) -> None:
    app, out, driver = argv[1], argv[2], argv[3]
    c9 = _compare9(driver)
    c9._setup(app)  # refuses to run outside a sandbox
    from strategy_lab import runs

    done_dir = os.path.join(out, "lines")
    os.makedirs(done_dir, exist_ok=True)
    done_files = []
    for sid, params, overlays, ensemble, sizing in CONFIGS:
        label = _label(sid, sizing, ensemble)
        done = os.path.join(done_dir, label.replace(" ", "_") + ".json")
        done_files.append(done)
        if os.path.exists(done):
            continue
        per_seed = []
        for seed in SEEDS:
            t0 = time.time()
            config = runs.RunConfig(
                strategy_id=sid,
                params=params,
                overlays=overlays,
                timeframe="1d",
                coins=COINS,
                start=START,
                end=END,
                account_gbp=ACCOUNT_GBP,
                gbp_usd=GBP_USD,
                fee=FEE,
                allowance=ALLOWANCE,
                draws=DRAWS,
                seed=seed,
                sizing=sizing,
                # the ensemble has no random part: once, with the saved seed
                ensemble=ensemble and seed == SEEDS[0],
            )
            record = runs.run(
                config, loader=c9.late_listing_loader, save=seed == SEEDS[0]
            )
            print(f"{label} seed {seed}: {time.time() - t0:.0f} s", flush=True)
            per_seed.append(
                record
                if seed == SEEDS[0]
                else {
                    "seed": seed,
                    "strategy_result": record["strategy_result"],
                    "random_entries": record["random_entries"],
                    "sizing": record["sizing"],
                }
            )
        with open(done, "w", encoding="utf-8", newline="\n") as f:
            json.dump(
                {"label": label, "runs": per_seed},
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
        os.path.join(out, "compare_ensemble.json"), "w", encoding="utf-8", newline="\n"
    ) as f:
        json.dump(lines, f, indent=2, sort_keys=True, default=str)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv)
