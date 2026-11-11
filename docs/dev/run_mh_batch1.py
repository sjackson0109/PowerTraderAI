"""
FDS-MH-001 phase E: batch 1's walk-forward (section 7), in a sandbox, on public candles.

Run it only with a sandbox's folders (POWERTRADER_HOME, APPDATA and LOCALAPPDATA pointed
at scratch folders, a keyring that fails, no keys): it reads candles from that sandbox's
cache only (offline) and writes into its data folder. Nothing here trades, registers or
enables anything, and nothing reads the lockbox.

    python run_mh_batch1.py <app dir> freeze
    python run_mh_batch1.py <app dir> run <batch id>

* ``freeze`` freezes batch 1 as section 7 declares it: 13 coins from 2020-01-01, its 14
  contestants and the reference, 0.50% + 0.05% (the report run cannot read the account),
  seeds from 300000, 400000 and 0, declared "batch-1". It ends on 2026-11-06, as the
  window does and as PV-1 did, so the walk-forward ends at 2025-05-06 and the last 18
  months are locked.
* ``run`` runs it. The harness writes ``results.json``, ``runs.json`` and ``report.md``.
"""

from __future__ import annotations

import os
import sys
import time

COINS = [
    "BTC",
    "ETH",
    "XRP",
    "BNB",
    "DOGE",
    "SOL",
    "ZEC",
    "DASH",
    "HYPE",
    "ADA",
    "AVAX",
    "LINK",
    "LTC",
]
START = "2020-01-01T00:00:00Z"
END = "2026-11-06T00:00:00Z"  # so that the lockbox, never read, starts on 2025-05-06
FEE = 0.005  # the owner's account rate, from the check window on 2026-11-05
ALLOWANCE = 0.0005
EXCHANGE = "coinbase"


def _setup(app: str) -> None:
    if app not in sys.path:
        sys.path.insert(0, app)
    for name in ("POWERTRADER_HOME", "APPDATA", "LOCALAPPDATA"):
        if not os.environ.get(name):
            raise SystemExit(f"{name} is not set: run this only inside a sandbox")


def freeze() -> str:
    import entry_gate
    import model_gate
    from model_lab import batch, catalogue

    fees = {
        c: entry_gate.Fees(FEE, "taker", EXCHANGE, "account", ALLOWANCE) for c in COINS
    }
    return batch.freeze(
        COINS,
        START,
        catalogue.BATCH_1,
        end=END,
        fees=fees,
        rules=model_gate.trade_rules({}),
        offline=True,
        exchanges=[EXCHANGE],
        why={c: "batch 1's coins (FDS-MH-001 section 7)" for c in COINS},
        declared="batch-1",
    )


def run(batch_id: str) -> None:
    from model_lab import batch

    last = {}

    def progress(stage, n, total):
        now = time.time()
        if stage != last.get("stage") or n == total or now - last.get("t", 0) > 60:
            print(f"{time.strftime('%H:%M:%S')} {stage} {n}/{total}", flush=True)
            last.update(stage=stage, t=now)

    t0 = time.time()
    batch.run(batch_id, progress=progress)
    print(f"done in {time.time() - t0:.0f} s", flush=True)


def main(argv) -> None:
    _setup(argv[1])
    if argv[2] == "freeze":
        print(freeze())
    elif argv[2] == "run":
        run(argv[3])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
