"""
FDS-SIG-004 phase C: the development run (section 8.3), in a sandbox, on public candles.

Run it only with a sandbox's folders (POWERTRADER_HOME, APPDATA and LOCALAPPDATA pointed
at scratch folders, a keyring that fails, no keys): it reads candles from that sandbox's
cache only (offline) and writes into its data folder and ``out``. Nothing here trades,
registers or enables anything.

    python run_sig4_dev.py <app dir> <out dir> freeze
    python run_sig4_dev.py <app dir> <out dir> run <PV-1 batch id>
    python run_sig4_dev.py <app dir> <out dir> analyse <PV-1 batch id>

* ``freeze`` freezes batch PV-1 as FDS-MH-001 section 7a declares it (13 coins from
  2020-01-01, walk-forward to 2025-05-06, 0.50% + 0.05%), declared "pv-1".
* ``run`` runs it: Q1's trading level, and the probabilities F1 is scored on.
* ``analyse`` scores the development family (section 6.5) on the development period
  (2021-01-01 to 2025-05-06; nothing from 2025-05-06 on): F1 from PV-1's probabilities,
  and on STRAT-001 1h at its defaults F2, F3, Q2 and Q3, at 0.50% (deciding) and 1.20%,
  at $10,000 (deciding) and $100. It writes ``analysis.json`` and ``SIG4-REPORT-dev.md``.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List

COINS = [
    "BTC", "ETH", "XRP", "BNB", "DOGE", "SOL", "ZEC", "DASH", "HYPE",
    "ADA", "AVAX", "LINK", "LTC",
]
START = "2020-01-01T00:00:00Z"
END = "2026-11-06T00:00:00Z"  # so that the lockbox, never read, starts on 2025-05-06
DEV_END = "2025-05-06T00:00:00Z"
SEEN_FROM = "2023-11-06T00:00:00Z"  # the volume research's look (X1)
FEE = 0.005
FEE_HIGH = 0.012
ALLOWANCE = 0.0005
SEEDS = {"r1": 500000, "r2": 600000, "fits": 0}
TEST_SEEDS = {"f1": 810000, "f2": 820000, "q2": 830000, "q3": 840000, "f3": 850000,
              "r3": 860000, "r3s": 870000, "rule": 880000}
ACCOUNTS = (10_000.0, 100.0)
EXCHANGE = "coinbase"


def _setup(app: str) -> None:
    if app not in sys.path:
        sys.path.insert(0, app)
    for name in ("POWERTRADER_HOME", "APPDATA", "LOCALAPPDATA"):
        if not os.environ.get(name):
            raise SystemExit(f"{name} is not set: run this only inside a sandbox")


def _fees():
    import entry_gate

    return {c: entry_gate.Fees(FEE, "taker", EXCHANGE, "account", ALLOWANCE) for c in COINS}


def freeze() -> str:
    from model_lab import batch, catalogue

    return batch.freeze(
        COINS,
        START,
        catalogue.BATCH_PV_1,
        end=END,
        fees=_fees(),
        offline=True,
        exchanges=[EXCHANGE],
        seeds=SEEDS,
        why={c: "batch PV-1's coins (FDS-MH-001 section 7a)" for c in COINS},
        declared="pv-1",
    )


def run(batch_id: str) -> None:
    from model_lab import batch

    def progress(stage, n, total):
        print(f"{time.strftime('%H:%M:%S')} {stage} {n}/{total}", flush=True)

    t0 = time.time()
    batch.run(batch_id, progress=progress)
    print(f"done in {time.time() - t0:.0f} s", flush=True)


# --- analysis ------------------------------------------------------------------------------


def analyse(batch_id: str, out: str) -> Dict[str, Any]:
    from sig4_dev_analysis import analyse as go  # the analysis, beside this file

    return go(batch_id, out)


def main(argv: List[str]) -> int:
    app, out, step = argv[1], argv[2], argv[3]
    _setup(app)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(out, exist_ok=True)
    if step == "freeze":
        print(freeze())
    elif step == "run":
        run(argv[4])
    elif step == "analyse":
        result = analyse(argv[4], out)
        print(json.dumps(result.get("verdicts", {}), indent=1))
    else:
        raise SystemExit(f"unknown step {step!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
