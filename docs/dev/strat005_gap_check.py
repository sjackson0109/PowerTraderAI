"""STRAT-005's lookback fix, checked on E1's development candles. Not a trial.

It runs STRAT-005 at its defaults on the 1d, 12h and 4h series that E1 froze, and
reports for each:
- the weekly decisions in the development period, and why each one held;
- the trades and their figures at £10,000 with E1's costs;
- for the 12h and 4h robustness rows, REF-RANDOM with the seeds E1 used.

Run it once on the old code and once on the new, and compare the two outputs.

Before it scores anything, it checks the sealed record's SHA-256 and that the candles
match the record. It writes no trial. It reads nothing on or after 2025-05-06,
because E1's loader refuses the reserved months.

    python docs/dev/strat005_gap_check.py <app dir> <docs/dev/sr1-e1/experiment.json> <out.json>
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import Counter

RECORD_SHA256 = "9a095a5993295968b86d3ef7c12d9cf9b6a85ef12cd6468522fc547bfc1ad1b1"
ROWS = (
    ("STRAT-005 (deciding, 1d)", None),
    ("STRAT-005 on 12h candles", "STRAT-005 on 12h candles"),
    ("STRAT-005 on 4h candles", "STRAT-005 on 4h candles"),
)


def _setup(app: str) -> None:
    for name in ("POWERTRADER_HOME", "APPDATA", "LOCALAPPDATA"):
        if not os.environ.get(name):
            raise SystemExit(f"{name} is not set: run this only inside a sandbox")
    sys.path.insert(0, app)


def _plain(x):
    """JSON-ready: numpy scalars to Python numbers, tuples to lists."""
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if hasattr(x, "item"):
        return x.item()
    return x


def trades_sha256(trades) -> str:
    """One hash of every candidate trade's coin, times and prices."""
    rows = sorted(
        (
            t.coin,
            int(t.entry_s),
            int(t.exit_s),
            float(t.entry_price),
            float(t.exit_price),
        )
        for t in trades
    )
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def decisions(universe, timeframe: str, e1) -> dict:
    """Every weekly decision bar opening in the development period, by its reason."""
    from market_data.timeframes import timeframe_seconds
    from strategies.factory import build_runner

    bar_s = timeframe_seconds(timeframe)
    by_coin = {}
    for coin, frame in sorted(universe.frames.items()):
        runner = build_runner("STRAT-005")
        runner.set_timeframe(bar_s)
        strategy = runner.strategy
        reasons = Counter()
        times = frame["open_time"]
        for i in range(len(frame)):
            t = times.iloc[i]
            if not (e1.DEV_START <= t < e1.DEV_END):
                continue
            if not strategy.is_decision_bar(t):
                continue
            reasons[runner.evaluate(runner.window(frame, i), None, coin).reason] += 1
        by_coin[coin] = dict(sorted(reasons.items()))
    total = Counter()
    for reasons in by_coin.values():
        total.update(reasons)
    return {"total": dict(sorted(total.items())), "by_coin": by_coin}


def main(argv) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    _setup(os.path.abspath(argv[1]))
    from strategy_lab import e1

    with open(argv[2], "rb") as f:
        raw = f.read()
    if hashlib.sha256(raw).hexdigest() != RECORD_SHA256:
        raise SystemExit("the record is not E1's sealed record")
    record = json.loads(raw)
    started = time.time()
    loader = e1.development_loader()
    data = e1.load_data(loader, ["1d", "12h", "4h"])
    frozen = record["market"]["series_sha256"]
    now = data.series_sha256()
    moved = sorted(k for k in now if frozen.get(k) != now[k])
    if moved or not now:
        raise SystemExit(f"the candles differ from E1's: {moved[:5]}")
    costs = e1.costs_for(record)
    deciding = e1.accounts_for(record)[e1.DECIDING_GBP]
    gbp_usd = float(record["accounts"]["gbp_usd"])
    variants = {v.name: (i, v) for i, v in enumerate(e1.VARIANTS)}
    out = {
        "code": {
            name: digest
            for name, digest in e1.experiment.code_hashes().items()
            if name.startswith("strategies/momentum")
        },
        "series_checked": len(now),
        "rows": {},
    }
    for label, variant in ROWS:
        if variant is None:
            spec = e1.STRATEGIES["STRAT-005"]
        else:
            i, v = variants[variant]
            spec = v.spec()
        sim = data.sim(spec)
        trades = e1.scored(sim)
        path = sim.replay(trades, costs, deciding, detail=True)
        row = {
            "timeframe": spec.timeframe,
            "candidates": len(trades),
            "trades_sha256": trades_sha256(trades),
            "figures": e1.compact(e1.figures(trades, path, costs, deciding, gbp_usd)),
            "decisions": decisions(data.universes[spec.timeframe], spec.timeframe, e1),
        }
        if variant is not None:
            r = e1.random_test(
                sim,
                trades,
                path,
                costs,
                deciding,
                e1.VARIANT_SEED + 1000 * i,
                e1.SHOWN_PER_RUN,
                1,
            )
            row["ref_random"] = {
                k: r.get(k) for k in ("p", "median", "value", "draws", "assessable")
            }
        out["rows"][label] = row
        print(f"{label}: {len(trades)} candidates, {time.time() - started:.0f}s")
    out["seconds"] = round(time.time() - started, 1)
    with open(argv[3], "w", encoding="utf-8", newline="\n") as f:
        json.dump(_plain(out), f, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
