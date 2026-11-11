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

It resumes: a finished run's figures are kept in ``<out dir>/lines/``, and a run saved by
an earlier launch is reused once the same config, replayed again, gives the same figures.
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
    lines = []
    for sid in STRATEGIES:
        params, tf = _defaults(sid)
        for overlays in ([], [{"id": FILTER}]):
            label = sid + (f" + {FILTER}" if overlays else "")
            done = os.path.join(done_dir, label.replace(" + ", "+") + ".json")
            if os.path.exists(done):
                with open(done, encoding="utf-8") as f:
                    lines.append(json.load(f))
                continue
            per_seed = []
            saved = None
            t0 = time.time()
            for k, seed in enumerate(SEEDS):
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
                    seed=seed,
                )
                earlier = _saved_run(runs, config) if k == 0 else None
                record = runs.run(
                    config, loader=late_listing_loader, save=(k == 0 and not earlier)
                )
                if earlier is not None:
                    if not _same(record, earlier):
                        raise SystemExit(f"{label}: differs from its saved run")
                    print(f"  {label}: saved run {earlier['id']} reused", flush=True)
                    record = earlier
                if k == 0:
                    saved = record
                elif record["strategy_result"] != saved["strategy_result"]:
                    raise SystemExit(
                        f"{label}: the strategy's trades changed with the seed"
                    )
                per_seed.append({"seed": seed, **(record["random_entries"] or {})})
            print(f"{label}: {time.time() - t0:.0f} s", flush=True)
            line = {"label": label, "run": saved, "random_runs": per_seed}
            with open(done, "w", encoding="utf-8", newline="\n") as f:
                json.dump(line, f, indent=2, sort_keys=True, default=str)
                f.write("\n")
            lines.append(line)
    with open(
        os.path.join(out, "compare9.json"), "w", encoding="utf-8", newline="\n"
    ) as f:
        json.dump(lines, f, indent=2, sort_keys=True, default=str)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv)
