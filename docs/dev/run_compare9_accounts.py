"""
The nine-coin comparison's strategy half again at $500 and $50
(``docs/dev/COMPARISON-9-COINS-PLAN-accounts.md``), in the first comparison's sandbox.

Run it only with a sandbox's folders, as ``run_compare9.py``. Nothing here trades,
registers or enables anything, and nothing reads past 2025-05-06.

    python run_compare9_accounts.py <app dir> <first out dir> <out dir> [strategies]

Everything is ``run_compare9.py``'s except the account. Each strategy run's simulation is
built once and shared by the three account sizes: a strategy's trades, and its random
entries' trades, do not depend on the account. Before any new size, the shared
simulation must reproduce the first comparison's GBP 10,000 figures (``<first out
dir>/lines/``) exactly, every seed included. Each new size's seed-700000 run is then
``strategy_lab.runs.run``'s own, saved; the ten seeds are drawn as before.
``<out dir>/<dollars>/compare9.json`` holds every figure of one size.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_compare9 as base  # noqa: E402

# pounds, at base.GBP_USD; the app rounds the dollars to the cent: $500.00 and $50.00
ACCOUNTS_GBP = {500: 371.03, 50: 37.10}


def _norm(x):
    return json.loads(json.dumps(x, sort_keys=True, default=str))


def _simulation(runs, config):
    """The universe and simulation ``strategy_lab.runs.run`` would build for
    ``config``: they do not depend on the account."""
    from strategy_lab.simulate import Simulation

    a, b = runs.development_only(config.start, config.end)
    spec = config.spec()
    universe = runs.load_universe(
        list(config.coins),
        spec,
        runs._warmup_start(spec, a),
        b,
        loader=base.late_listing_loader,
    )
    return Simulation(universe, spec)


def _seeds_on(runs, config, sim):
    """``base.ten_seeds``'s figures for ``config``, on ``sim``: the strategy's record
    (as the saved run gives it), each seed's random entries, and the pooled draws."""
    import numpy as np

    from signal_fusion.evaluation.replay import Account, Costs
    from strategy_lab import baselines as bl

    a, _b = runs.development_only(config.start, config.end)
    start_s = runs._seconds(a)
    trades = [t for t in sim.candidates() if t.entry_s >= start_s]
    rules = runs.venue_rules(list(config.coins))
    costs = Costs(
        fee=float(config.fee),
        allowance=float(config.allowance),
        minimum_usd=rules.minimum_usd,
        base_increment=rules.base_increment,
    )
    usd = round(float(config.account_gbp) * float(config.gbp_usd), 2)
    account = Account(start=usd)
    path = sim.replay(trades, costs, account, detail=True)
    taken = [trades[i] for i, *_ in path.detail]
    hold = sim.replay(bl.hold_trades(sim, start_s), costs, account)
    per_coin = {}
    for i, _amount, net, _days in path.detail:
        row = per_coin.setdefault(trades[i].coin, {"trades": 0, "net_usd": 0.0})
        row["trades"] += 1
        row["net_usd"] += float(net)
    mine = float(path.rpcd[0])
    per_seed, nets, rpcds = [], [], []
    for seed in base.SEEDS:
        draws = bl.random_draws(sim, taken, seed, int(config.draws), start_s)
        rand = bl.replay_draws(sim, draws.draws, costs, account)
        per_seed.append({"seed": seed, **base._random_part(rand, draws, mine)})
        nets.append(np.asarray(rand.net, dtype=float))
        rpcds.append(np.asarray(rand.rpcd, dtype=float))
    record = {
        "strategy_result": runs._figures(path),
        "buy_and_hold": runs._figures(hold),
        "per_coin": per_coin,
        "random_entries": {k: v for k, v in per_seed[0].items() if k != "seed"},
    }
    net, rpcd = np.concatenate(nets), np.concatenate(rpcds)
    pooled = {
        "draws": int(len(net)),
        "median_net_usd": float(np.median(net)),
        "median_return_per_capital_day": float(np.median(rpcd)),
        "share_at_or_above": float(np.mean(rpcd >= mine)),
    }
    return _norm(record), _norm(per_seed), _norm(pooled)


def _config(runs, sid, params, tf, overlays, account_gbp):
    return runs.RunConfig(
        strategy_id=sid,
        params=params,
        overlays=overlays,
        timeframe=tf,
        coins=base.COINS,
        start=base.START,
        end=base.END,
        account_gbp=account_gbp,
        gbp_usd=base.GBP_USD,
        fee=base.FEE,
        allowance=base.ALLOWANCE,
        draws=base.DRAWS,
        seed=base.SEEDS[0],
    )


def main(argv) -> None:
    base._setup(argv[1])
    first, out = argv[2], argv[3]
    only = argv[4].split(",") if len(argv) > 4 else base.STRATEGIES
    from strategy_lab import runs

    base.naive_start(runs)
    shared = {}
    # ``runs.run`` builds its simulation here: it gets the shared one
    runs.Simulation = lambda universe, spec: shared["sim"]
    last_saved = 0
    for sid in base.STRATEGIES:
        params, tf = base._defaults(sid)
        for overlays in ([], [{"id": base.FILTER}]):
            label = sid + (f" + {base.FILTER}" if overlays else "")
            name = label.replace(" + ", "+") + ".json"
            todo = {
                usd: os.path.join(out, str(usd), "lines", name) for usd in ACCOUNTS_GBP
            }
            if sid not in only or all(os.path.exists(p) for p in todo.values()):
                continue
            t0 = time.time()
            with open(os.path.join(first, "lines", name), encoding="utf-8") as f:
                saved10k = json.load(f)
            config10k = _config(runs, sid, params, tf, overlays, base.ACCOUNT_GBP)
            shared["sim"] = _simulation(runs, config10k)
            record, per_seed, pooled = _seeds_on(runs, config10k, shared["sim"])
            if not (
                base._same(record, saved10k["run"])
                and per_seed == _norm(saved10k["random_runs"])
                and pooled == _norm(saved10k["random_pooled"])
            ):
                raise SystemExit(f"{label}: the shared simulation differs at £10,000")
            print(f"  {label}: £10,000 figures reproduced, every seed", flush=True)
            for usd, account_gbp in ACCOUNTS_GBP.items():
                if os.path.exists(todo[usd]):
                    continue
                config = _config(runs, sid, params, tf, overlays, account_gbp)
                saved = base._saved_run(runs, config)
                if saved is None:
                    while int(time.time()) <= last_saved:  # one run id a second
                        time.sleep(0.05)
                    saved = runs.run(config, loader=base.late_listing_loader, save=True)
                    last_saved = int(time.time())
                else:
                    print(
                        f"  {label} ${usd}: saved run {saved['id']} reused", flush=True
                    )
                if saved["account_usd"] != float(usd):
                    raise SystemExit(f"{label}: ${saved['account_usd']}, not ${usd}")
                record, per_seed, pooled = _seeds_on(runs, config, shared["sim"])
                if not base._same(record, saved):
                    raise SystemExit(f"{label} ${usd}: the seeds differ from the run")
                os.makedirs(os.path.dirname(todo[usd]), exist_ok=True)
                with open(todo[usd], "w", encoding="utf-8", newline="\n") as f:
                    json.dump(
                        {
                            "label": label,
                            "run": saved,
                            "random_runs": per_seed,
                            "random_pooled": pooled,
                        },
                        f,
                        indent=2,
                        sort_keys=True,
                        default=str,
                    )
                    f.write("\n")
            shared.clear()
            print(f"{label}: {time.time() - t0:.0f} s", flush=True)
    for usd in ACCOUNTS_GBP:
        folder = os.path.join(out, str(usd), "lines")
        names = [
            sid + (f"+{base.FILTER}" if o else "") + ".json"
            for sid in base.STRATEGIES
            for o in (False, True)
        ]
        missing = [n for n in names if not os.path.exists(os.path.join(folder, n))]
        if missing:
            print(f"${usd} not yet done: {', '.join(missing)}", flush=True)
            continue
        lines = []
        for n in names:
            with open(os.path.join(folder, n), encoding="utf-8") as f:
                lines.append(json.load(f))
        with open(
            os.path.join(out, str(usd), "compare9.json"),
            "w",
            encoding="utf-8",
            newline="\n",
        ) as f:
            json.dump(lines, f, indent=2, sort_keys=True, default=str)
            f.write("\n")


if __name__ == "__main__":
    main(sys.argv)
