"""
The nine-coin comparison's strategy half (``docs/dev/COMPARISON-9-COINS-PLAN.md``), in a
sandbox, on public candles.

Run it only with a sandbox's folders (POWERTRADER_HOME, APPDATA and LOCALAPPDATA pointed
at scratch folders, a keyring that fails, no keys). Nothing here trades, registers or
enables anything, and nothing reads past 2025-05-06 (``strategy_lab.runs`` refuses it).

    python run_compare9.py <app dir> <out dir>

Ten exploratory runs (plan section 4): STRAT-000, 001, 002, 004 and 005 at their
catalogue defaults, each alone and with OVL-REGIME at its defaults, over the nine coins
in one GBP 10,000 account at 0.50% + 0.05% (plan section 6). Each run's random entries
are drawn as 10 seeded runs of 200 draws (plan section 7): seed 700000 is saved as the
app saves a run, and seeds 701000 to 709000 are reported only. ``<out dir>/compare9.json``
holds every figure the report uses.

Seed 700000's run is ``strategy_lab.runs.run``'s own, saved. The ten seeds are then drawn
on one simulation of the same config (``ten_seeds``), which must reproduce that run's
figures exactly; the pooled 2,000 draws are reported too.

It resumes: a finished run's figures are kept in ``<out dir>/lines/``, and a run saved by
an earlier launch is reused, checked by the same reproduction.
``naive_start`` works around a bug in ``strategy_lab.simulate.load_universe`` that stops
every run with OVL-REGIME; it changes no candle and no figure.
"""

from __future__ import annotations

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
GBP_USD = 1.3476  # BoE XUDLUSS for 2026-11-05, as E1 used
DRAWS = 200
SEEDS = [700_000 + 1000 * k for k in range(10)]
STRATEGIES = ["STRAT-000", "STRAT-001", "STRAT-002", "STRAT-004", "STRAT-005"]
FILTER = "OVL-REGIME"
_CHOSEN = {}  # (symbol, timeframe) -> (exchanges to read, exchanges passed over)


def _setup(app: str) -> None:
    if app not in sys.path:
        sys.path.insert(0, app)
    for name in ("POWERTRADER_HOME", "APPDATA", "LOCALAPPDATA"):
        if not os.environ.get(name):
            raise SystemExit(f"{name} is not set: run this only inside a sandbox")


def late_listing_loader(symbol, tf, start, end, **kw):
    """The exchange layer's series, except that an exchange whose series starts after
    the period ends is passed over for the next one in Settings order (plan section 5).
    """
    import pandas as pd

    from market_data.candles import exchange_candles
    from pt_multi_exchange import market_exchanges

    limit = pd.Timestamp(END, tz="UTC")

    def early(frame) -> bool:
        return len(frame) > 0 and frame["open_time"].iloc[0] < limit

    if (symbol, tf) in _CHOSEN:
        name, passed = _CHOSEN[symbol, tf]
        frame = exchange_candles(symbol, tf, start, end, exchanges=name, **kw)
        if passed:
            frame.attrs["passed_over"] = list(passed)
        return frame
    first = exchange_candles(symbol, tf, start, end, **kw)
    if early(first):
        _CHOSEN[symbol, tf] = (None, [])
        return first
    passed = [first.attrs.get("exchange")]
    for name in market_exchanges().exchange_manager.exchange_names():
        if name in passed:
            continue
        try:
            frame = exchange_candles(symbol, tf, start, end, exchanges=[name], **kw)
        except Exception as exc:  # no market, or no history: the next one
            print(f"  {symbol} {tf}: {name} passed over ({exc})", flush=True)
            passed.append(name)
            continue
        if early(frame):
            print(f"  {symbol} {tf}: from {name}; passed over {passed}", flush=True)
            _CHOSEN[symbol, tf] = ([name], list(passed))
            frame.attrs["passed_over"] = list(passed)
            return frame
        passed.append(name)
    print(f"  {symbol} {tf}: no exchange starts before {END}", flush=True)
    _CHOSEN[symbol, tf] = (None, [])
    return first


def _defaults(strategy_id: str):
    from strategies.catalogue import get_entry

    entry = get_entry(strategy_id)
    return dict(entry["default_params"]), entry["timeframe_primary"]


def naive_start(runs) -> None:
    """Pass the run's start to ``load_universe`` as the same instant without a time zone.

    ``strategy_lab.runs.run`` passes a tz-aware start, and ``load_universe`` computes a
    context series' start with ``pd.Timestamp(start, tz="UTC")``, which refuses one: any
    run with OVL-REGIME stops there. The candle layer reads a naive time as UTC
    (``market_data.candles.to_utc``), so this changes no candle and no figure; it is what
    that line would compute if it took a tz-aware start."""
    import pandas as pd

    original = runs.load_universe

    def load(coins, spec, start, end, **kw):
        start = pd.Timestamp(start)
        if start.tzinfo is not None:
            start = start.tz_convert("UTC").tz_localize(None)
        return original(coins, spec, start, end, **kw)

    runs.load_universe = load


COMPARED = ("strategy_result", "buy_and_hold", "per_coin", "random_entries")


def _same(a, b) -> bool:
    def norm(r):
        return json.dumps({k: r.get(k) for k in COMPARED}, sort_keys=True, default=str)

    return norm(a) == norm(b)


def _random_part(rand, draws, mine):
    """The random-entry figures, as ``strategy_lab.runs.run`` records them."""
    import numpy as np

    return {
        "draws": int(len(rand.net)),
        "median_net_usd": float(np.median(rand.net)),
        "median_return_per_capital_day": float(np.median(rand.rpcd)),
        "share_at_or_above": float(np.mean(rand.rpcd >= mine)),
        "entries_wanted": draws.wanted,
        "entries_reached_median": float(np.median(draws.reached)),
    }


def ten_seeds(runs, config, saved):
    """Every seed's random entries on one simulation of ``config``.

    ``strategy_lab.runs.run`` builds a new simulation for each run, so each seed would
    replay every random trade again (with an overlay, bar by bar). Here the simulation is
    built once, as ``run`` builds it, and its trades are reused by every seed. Seed
    ``SEEDS[0]``'s figures, and the strategy's own, must equal the saved run's, which
    ``run`` made: so this route computes what ten runs would."""
    import numpy as np

    from signal_fusion.evaluation.replay import Account, Costs
    from strategy_lab import baselines as bl
    from strategy_lab.simulate import Simulation

    a, b = runs.development_only(config.start, config.end)
    spec = config.spec()
    universe = runs.load_universe(
        list(config.coins),
        spec,
        runs._warmup_start(spec, a),
        b,
        loader=late_listing_loader,
    )
    sim = Simulation(universe, spec)
    start_s = runs._seconds(a)
    trades = [t for t in sim.candidates() if t.entry_s >= start_s]
    rules = runs.venue_rules(list(config.coins))
    costs = Costs(
        fee=float(config.fee),
        allowance=float(config.allowance),
        minimum_usd=rules.minimum_usd,
        base_increment=rules.base_increment,
    )
    account = Account(start=round(float(config.account_gbp) * float(config.gbp_usd), 2))
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
    for seed in SEEDS:
        draws = bl.random_draws(sim, taken, seed, int(config.draws), start_s)
        rand = bl.replay_draws(sim, draws.draws, costs, account)
        per_seed.append({"seed": seed, **_random_part(rand, draws, mine)})
        nets.append(np.asarray(rand.net, dtype=float))
        rpcds.append(np.asarray(rand.rpcd, dtype=float))
    mine_record = {
        "strategy_result": runs._figures(path),
        "buy_and_hold": runs._figures(hold),
        "per_coin": per_coin,
        "random_entries": {k: v for k, v in per_seed[0].items() if k != "seed"},
    }
    if not _same(json.loads(json.dumps(mine_record, default=str)), saved):
        raise SystemExit(f"{config.strategy_id}: one simulation differs from the run")
    net, rpcd = np.concatenate(nets), np.concatenate(rpcds)
    pooled = {
        "draws": int(len(net)),
        "median_net_usd": float(np.median(net)),
        "median_return_per_capital_day": float(np.median(rpcd)),
        "share_at_or_above": float(np.mean(rpcd >= mine)),
    }
    return per_seed, pooled


def _saved_run(runs, config):
    """The run already saved for this config (an earlier launch), or None."""
    from dataclasses import asdict

    want = json.loads(
        json.dumps({**asdict(config), "params": dict(config.params)}, default=str)
    )
    for record in runs.list_runs():
        if record.get("config") == want:
            return record
    return None


def main(argv) -> None:
    _setup(argv[1])
    out = argv[2]
    done_dir = os.path.join(out, "lines")
    os.makedirs(done_dir, exist_ok=True)
    from strategy_lab import runs

    naive_start(runs)
    # an optional list of strategies, so that two processes can share the runs
    only = argv[3].split(",") if len(argv) > 3 else STRATEGIES
    done_files = []
    for sid in STRATEGIES:
        params, tf = _defaults(sid)
        for overlays in ([], [{"id": FILTER}]):
            label = sid + (f" + {FILTER}" if overlays else "")
            done = os.path.join(done_dir, label.replace(" + ", "+") + ".json")
            done_files.append(done)
            if os.path.exists(done) or sid not in only:
                continue
            t0 = time.time()
            config = runs.RunConfig(
                strategy_id=sid,
                params=params,
                overlays=overlays,
                timeframe=tf,
                coins=COINS,
                start=START,
                end=END,
                account_gbp=ACCOUNT_GBP,
                gbp_usd=GBP_USD,
                fee=FEE,
                allowance=ALLOWANCE,
                draws=DRAWS,
                seed=SEEDS[0],
            )
            saved = _saved_run(runs, config)
            if saved is None:
                saved = runs.run(config, loader=late_listing_loader, save=True)
            else:
                print(f"  {label}: saved run {saved['id']} reused", flush=True)
            per_seed, pooled = ten_seeds(runs, config, saved)
            print(f"{label}: {time.time() - t0:.0f} s", flush=True)
            line = {
                "label": label,
                "run": saved,
                "random_runs": per_seed,
                "random_pooled": pooled,
            }
            with open(done, "w", encoding="utf-8", newline="\n") as f:
                json.dump(line, f, indent=2, sort_keys=True, default=str)
                f.write("\n")
    missing = [os.path.basename(p) for p in done_files if not os.path.exists(p)]
    if missing:
        print(f"not yet done: {', '.join(missing)}", flush=True)
        return
    lines = []
    for path in done_files:
        with open(path, encoding="utf-8") as f:
            lines.append(json.load(f))
    with open(
        os.path.join(out, "compare9.json"), "w", encoding="utf-8", newline="\n"
    ) as f:
        json.dump(lines, f, indent=2, sort_keys=True, default=str)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv)
