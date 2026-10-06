"""
FDS-MDL (trained-model strategy STRAT-003): candles and training for the model-1
backtest. Phase 1 adds ``fetch`` and ``train``; ``run`` and ``report`` come with the
backtest phase.

    python docs/dev/run_backtest_model1.py fetch   # download + cache candles (public Binance klines)
    python docs/dev/run_backtest_model1.py train   # train the pattern trainer offline, from the cache

Every run needs ``POWERTRADER_HOME`` set to one scratch folder outside the repo, reused
across the session, so the candle cache, training output and summaries never touch
the real per-user folders (FDS-MDL-A section 4.3). In PowerShell:

    $env:POWERTRADER_HOME = 'C:\\scratch\\model1-home'
    python docs/dev/run_backtest_model1.py fetch

The script prints the folders it resolved before doing anything. ``fetch`` is the only
step that uses the network. ``train`` runs ``app/pt_pattern_trainer.py`` once per
symbol, the way the hub does (the coin as its argument, a working folder of its own),
with ``--offline`` and an explicit window, and records each run's wall-clock time and
the model_id it published (FDS-MDL Phase 2: ``<data>/hub_data/strategy_models/<id>/``).
It never subsamples: the trainer prints and records every bar count it uses.

Declared defaults (FDS-MDL section 4.7: runtime on 1h data from 2023 to 2025):

* symbols: BTC and ETH (``<SYM>USDT`` on Binance);
* window: 2023-01-01 to 2026-01-01 (UTC, end exclusive);
* timeframes: the trainer's seven (1h, 2h, 4h, 8h, 12h, 1d, 1w);
* seed: 0.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(REPO, "app")
sys.path.insert(0, APP)

SYMBOLS = ("BTC", "ETH")
START, END = "2023-01-01", "2026-01-01"  # END is exclusive
TIMEFRAMES = ("1h", "2h", "4h", "8h", "12h", "1d", "1w")
SEED = 0
TRAINER = os.path.join(APP, "pt_pattern_trainer.py")
# what the hub clears from a coin folder before training (pt_hub.start_trainer_for_selected_coin)
TRAINER_FILES = (
    "trainer_last_training_time.txt",
    "trainer_status.json",
    "trainer_last_start_time.txt",
    "killer.txt",
    "memories_*.txt",
    "memory_weights_*.txt",
    "neural_perfect_threshold_*.txt",
)


def _inside(path: str, folder: str) -> bool:
    path, folder = os.path.normcase(os.path.abspath(path)), os.path.normcase(folder)
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:  # another drive: outside
        return False


def sandbox(use_real_folders: bool) -> dict:
    """Check POWERTRADER_HOME and print the folders this run uses."""
    home = os.environ.get("POWERTRADER_HOME", "").strip()
    if not home and not use_real_folders:
        sys.exit(
            "POWERTRADER_HOME is not set: this run would use the real per-user folders.\n"
            "Set it to a scratch folder outside the repo, e.g. in PowerShell:\n"
            "    $env:POWERTRADER_HOME = 'C:\\scratch\\model1-home'\n"
            "or pass --use-real-folders to use the real folders on purpose."
        )
    if home and _inside(home, REPO):
        sys.exit(f"POWERTRADER_HOME {home} is inside the repo; use a folder outside it")

    import pt_paths
    from market_data.candles import cache_dir_default

    folders = {
        "POWERTRADER_HOME": home or "(not set: the real per-user folders)",
        "candle cache": cache_dir_default(),
        "data": pt_paths.data_dir(),
        "trainer working folders": os.path.join(
            pt_paths.data_dir(), "backtest-model-1", "trainer"
        ),
        "strategy models": pt_paths.strategy_models_dir(create=False),
    }
    for name, path in folders.items():
        print(f"{name}: {path}")
    print(flush=True)
    return folders


def fetch(symbols, start, end, timeframes):
    """Fill the candle cache with closed bars in [start, end) (network)."""
    import pandas as pd

    from market_data.candles import BinanceKlines, cache_path, file_sha256, get_candles
    from market_data.timeframes import bar_open_floor

    end_ts = min(pd.Timestamp(end, tz="UTC"), pd.Timestamp.now(tz="UTC"))
    for sym in symbols:
        pair = f"{sym}USDT"
        for tf in timeframes:
            # bars that close by ``end``; get_candles' own now (the wall clock) decides
            # what is closed enough to cache, so the cache never gets a hole
            end_open = pd.Timestamp(
                bar_open_floor(int(end_ts.timestamp()), tf), unit="s", tz="UTC"
            )
            fetcher = BinanceKlines()
            df = get_candles(pair, tf, start, end_open, fetcher=fetcher)
            report = df.attrs["report"]
            print(
                f"{pair} {tf}: {len(df)} bars {df['open_time'].iloc[0]} -> "
                f"{df['open_time'].iloc[-1]} missing={report.missing_bars} "
                f"requests={fetcher.requests_made} "
                f"sha256={file_sha256(cache_path(pair, tf))[:16]}",
                flush=True,
            )


def published_model_id(sym):
    """The model_id in the trainer's summary for ``sym`` (None if it has none)."""
    import pt_paths

    path = os.path.join(
        pt_paths.data_dir(), "training_results", f"{sym.lower()}_training_results.json"
    )
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("model_id")
    except (OSError, ValueError):
        return None


def train(symbols, start, end, seed):
    """Run the trainer once per symbol, offline; record each run's wall-clock time and
    the model_id it published."""
    import pt_paths

    root = os.path.join(pt_paths.data_dir(), "backtest-model-1", "trainer")
    runs = []
    for sym in symbols:
        folder = os.path.join(root, sym)
        os.makedirs(folder, exist_ok=True)
        for pattern in TRAINER_FILES:
            for path in glob.glob(os.path.join(folder, pattern)):
                os.remove(path)
        argv = [
            sys.executable,
            "-u",
            TRAINER,
            sym,
            "--offline",
            "--train-start",
            start,
            "--train-end",
            end,
            "--seed",
            str(seed),
        ]
        print(
            f"== {sym}: {' '.join(argv[2:])}\n   working folder: {folder}", flush=True
        )
        log_path = os.path.join(root, f"{sym}.log")
        started = time.time()
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.Popen(
                argv,
                cwd=folder,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in proc.stdout:
                log.write(line)
                if not line.startswith("  "):  # progress lines go to the log only
                    print(f"   {line.rstrip()}", flush=True)
            code = proc.wait()
        seconds = round(time.time() - started, 1)
        model_id = published_model_id(sym) if code == 0 else None
        print(
            f"== {sym}: exit {code} after {seconds} s ({seconds / 60:.1f} min), "
            f"model_id {model_id}\n",
            flush=True,
        )
        runs.append(
            {
                "symbol": sym,
                "exit_code": code,
                "wall_seconds": seconds,
                "model_id": model_id,
                "log": log_path,
            }
        )
    out = os.path.join(root, "train-runtimes.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(
            {
                "start": start,
                "end": end,
                "seed": seed,
                "python": sys.version,
                "runs": runs,
            },
            f,
            indent=2,
        )
    print(f"runtimes: {out}")
    return 0 if all(r["exit_code"] == 0 and r["model_id"] for r in runs) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("fetch", "train"))
    parser.add_argument("--symbols", default=",".join(SYMBOLS))
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    parser.add_argument("--timeframes", default=",".join(TIMEFRAMES))
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--use-real-folders", action="store_true")
    args = parser.parse_args(argv)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    sandbox(args.use_real_folders)
    if args.command == "fetch":
        fetch(
            symbols,
            args.start,
            args.end,
            [t.strip() for t in args.timeframes.split(",")],
        )
        return 0
    return train(symbols, args.start, args.end, args.seed)


if __name__ == "__main__":
    sys.exit(main())
