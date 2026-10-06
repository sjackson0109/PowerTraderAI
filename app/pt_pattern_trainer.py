#!/usr/bin/env python3
"""
Pattern-matching trainer for PowerTrader AI+ (FDS-MDL Phase 1).

A port of the upstream PowerTrader_AI trainer (github.com/garagesteve1155/PowerTrader_AI,
``pt_trainer.py`` at commit ``ba62130``, 2026-01-09, git blob ``0369182``; on 2026-10-06
that blob was still upstream main's ``pt_trainer.py``). The hub runs it for every coin
with the coin's neural folder as the working directory, exactly like the old stub:
``python pt_pattern_trainer.py <COIN>``.

What it learns, per timeframe (``1hour`` ... ``1week``), into the working folder: a list
of memories (``memories_<tf>.txt``: the body % of a candle and the close move % to the
next candle, then that next candle's high and low move %), one weight per memory for the
close, high and low moves (``memory_weights[_high|_low]_<tf>.txt``) and a match
threshold (``neural_perfect_threshold_<tf>.txt``). The neural runner (pt_thinker.py)
reads these files. A training summary goes to ``<data>/training_results/``.

Training follows upstream statement for statement, including its quirks (kept on
purpose, FDS-MDL owner decision; see docs/dev/RUN-LOG-model-1.md):

* weight updates are applied to lists re-read from disk on every step and are never
  saved, so every saved weight stays 1.0;
* the close-weight test multiplies a move that is already a percentage by 100;
* each step matches against the memories last flushed to disk (every 200 steps);
* pass 0 of every timeframe trains on 1-hour bars;
* intraday timeframes, and pass 0 of every timeframe, train on the older half of the
  history (see deviation 2 for the exact count);
* a step whose predicted close is 0 (a last close of 0, or a predicted move of exactly
  -100%) learns nothing, because upstream's division by it raises inside its learning
  ``try`` (counted as ``unlearned_steps``).

Deviations from upstream, each with its reason:

1. Data: Binance klines through ``app/market_data/candles.py`` (cached), not KuCoin.
   The window is ``[train_start, train_end)`` and only bars closed by ``train_end`` are
   read: every run reads the cache with ``now=train_end`` and checks the result, so no
   candle after ``train_end`` can be read (FDS-MDL 4.3). Upstream read up to the wall
   clock. Online, the cache is filled first (the wall clock decides which fetched bars
   are closed enough to cache, so the shared cache never gets a hole). Bars the exchange
   does not have at either end of the window (a pair listed later, a missing bar) are
   counted in the summary (``missing_at_start``, ``missing_at_end``) and printed; gaps
   inside the window are listed. Offline, the cache must reach both ends of the window,
   or the run fails: offline, a short cache and an exchange that has no bars there look
   the same, so a pair listed after ``train_start`` is trained online, or offline
   from a later ``train_start``.
2. Row selection: upstream kept the older ``L - int(L/2)`` of the ``L`` rows it fetched,
   which included KuCoin's still-forming bar, so the port keeps the oldest
   ``(n+1) - (n+1)//2`` of the ``n`` closed bars. For passes 1-2 of ``1day``/``1week``
   upstream dropped only the forming bar, so the port keeps all ``n``. Each count is
   printed and recorded in the summary (never a silent subsample, FDS-MDL 4.7).
   Upstream also counted a malformed row produced when its last page came back empty;
   the port has no pages.
3. Upstream re-fetched its data for every pass; the port loads each timeframe once.
4. A pass upstream could never finish (fewer than 10 bars in passes 0-1, fewer than 4 in
   pass 2: upstream loops for ever) is skipped and recorded.
5. Output completeness: at the end of each timeframe the memories and weights are
   flushed and the exact final threshold is written (upstream flushed only every 200
   steps and lost the rest). Files are written atomically, and a failed write is an
   error (upstream ignored it).
6. The working folder must not already hold model files: upstream resumed from them,
   which would carry in data from another window. A run always starts empty.
7. Removed: the KuCoin ticker call (its value was never used), the ``killer.txt`` stop
   file (nothing writes it), dead code, the "Bounce Accuracy" statistic (printed only,
   never used, and not a held-out figure) and the per-step printing (progress lines
   instead).
8. An error ends the run with ``trainer_status.json`` state ``ERROR`` and exit code 1
   (upstream could hang or leave ``TRAINING``); bad arguments exit 2.
9. ``--seed`` (default 0) is recorded and applied to Python's ``random``; upstream uses no
   randomness, so it changes nothing.

Inputs (command line, else environment, else default):

* ``coin`` (positional, default BTC);
* ``--train-start`` / ``POWERTRADER_TRAIN_START`` (default: ``train_end`` minus 1,095 days);
* ``--train-end`` / ``POWERTRADER_TRAIN_END`` (default: the last full hour, UTC);
* ``--seed`` / ``POWERTRADER_TRAIN_SEED`` (default 0);
* ``--offline`` / ``POWERTRADER_CANDLES_OFFLINE=1``: read the candle cache only, never the
  network.
"""

import argparse
import json
import os
import random
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import pt_paths  # noqa: E402

UPSTREAM_REPO = "github.com/garagesteve1155/PowerTrader_AI"
UPSTREAM_COMMIT = "ba62130"
UPSTREAM_BLOB = "0369182e5685f599ec593600f82e2ecc74dc9384"

TF_CHOICES = ["1hour", "2hour", "4hour", "8hour", "12hour", "1day", "1week"]
CANDLE_TF = {
    "1hour": "1h",
    "2hour": "2h",
    "4hour": "4h",
    "8hour": "8h",
    "12hour": "12h",
    "1day": "1d",
    "1week": "1w",
}
MODEL_FILE_PREFIXES = ("memories_", "memory_weights_", "neural_perfect_threshold_")
DEFAULT_WINDOW = timedelta(days=1095)
FLUSH_EVERY = (
    200  # upstream: flush memories/weights and write the threshold every 200 steps
)
PROGRESS_EVERY = 500

ENV_TRAIN_START = "POWERTRADER_TRAIN_START"
ENV_TRAIN_END = "POWERTRADER_TRAIN_END"
ENV_TRAIN_SEED = "POWERTRADER_TRAIN_SEED"
ENV_CANDLES_OFFLINE = "POWERTRADER_CANDLES_OFFLINE"
TRAINER_ENV = (ENV_TRAIN_START, ENV_TRAIN_END, ENV_TRAIN_SEED, ENV_CANDLES_OFFLINE)


class TrainerError(Exception):
    """Training cannot continue (data missing, lookahead, a failed write, ...)."""


class UsageError(TrainerError):
    """Bad arguments or a working folder the trainer refuses to use."""


# --- inputs ---------------------------------------------------------------------------


def _parse_time(value: str, name: str) -> datetime:
    """ISO date or date-time; naive values are UTC."""
    try:
        ts = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        raise UsageError(f"{name}: not an ISO date or date-time: {value!r}") from None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _flag(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def parse_args(argv=None, environ=None, now=None):
    """Resolve the run's inputs. Each value records where it came from."""
    environ = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(
        prog="pt_pattern_trainer.py",
        description="Train the pattern-matching model for one coin (FDS-MDL).",
    )
    parser.add_argument("coin", nargs="?", default="BTC")
    parser.add_argument("--train-start")
    parser.add_argument("--train-end")
    parser.add_argument("--seed")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--upstream-flush-only",
        action="store_true",
        help="testing only: flush and write the threshold exactly as upstream did "
        "(every 200 steps, losing the rest), to compare output with upstream",
    )
    args = parser.parse_args(argv)

    def pick(cli, env_name):
        if cli is not None:
            return cli, "command line"
        if str(environ.get(env_name, "")).strip():
            return environ[env_name], env_name
        return None, "default"

    now = now or datetime.now(timezone.utc)
    end_raw, end_src = pick(args.train_end, ENV_TRAIN_END)
    if end_raw is None:
        train_end = now.replace(minute=0, second=0, microsecond=0)
    else:
        train_end = _parse_time(end_raw, "train_end")
    start_raw, start_src = pick(args.train_start, ENV_TRAIN_START)
    if start_raw is None:
        train_start = train_end - DEFAULT_WINDOW
    else:
        train_start = _parse_time(start_raw, "train_start")
    seed_raw, seed_src = pick(args.seed, ENV_TRAIN_SEED)
    try:
        seed = 0 if seed_raw is None else int(seed_raw)
    except ValueError:
        raise UsageError(f"seed: not an integer: {seed_raw!r}") from None
    offline = bool(args.offline)
    offline_src = "command line" if offline else "default"
    if not offline and _flag(environ.get(ENV_CANDLES_OFFLINE, "")):
        offline, offline_src = True, ENV_CANDLES_OFFLINE

    if train_start >= train_end:
        raise UsageError(
            f"train_start {train_start} is not before train_end {train_end}"
        )
    if train_end > now:
        # a bar that closes after "now" is still forming: never train on it
        raise UsageError(f"train_end {train_end} is in the future (now {now})")
    coin = str(args.coin).strip().upper() or "BTC"
    return {
        "coin": coin,
        "train_start": train_start,
        "train_end": train_end,
        "seed": seed,
        "offline": offline,
        "upstream_flush_only": bool(args.upstream_flush_only),
        "sources": {
            "train_start": start_src,
            "train_end": end_src,
            "seed": seed_src,
            "offline": offline_src,
        },
    }


# --- data -----------------------------------------------------------------------------


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc(epoch_seconds: int) -> datetime:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)


class BarLoader:
    """Closed bars for one pair inside ``[train_start, train_end)``, from the candle
    cache (filled from Binance unless offline). This is the only data source."""

    def __init__(self, pair, train_start, train_end, offline, cache_dir=None):
        self.pair = pair
        self.train_start = train_start
        self.train_end = train_end
        self.offline = offline
        self.cache_dir = cache_dir
        self._bars = {}
        self.reports = {}

    def bars(self, tf_choice):
        if tf_choice not in self._bars:
            self._bars[tf_choice] = self._load(CANDLE_TF[tf_choice])
        return self._bars[tf_choice]

    def _load(self, tf):
        import pandas as pd

        from market_data.candles import CandleDataError, get_candles
        from market_data.timeframes import bar_open_floor, candle_timeframe_seconds

        step = timedelta(seconds=candle_timeframe_seconds(tf))
        start, end = self.train_start, self.train_end
        # the window's bars: from the first that opens at or after train_start to the
        # last that closes by train_end (compared exactly: train_start may have
        # fractions of a second)
        floor_start = _utc(bar_open_floor(int(start.timestamp()), tf))
        first_expected = floor_start if floor_start >= start else floor_start + step
        end_open = _utc(bar_open_floor(int(end.timestamp()), tf))
        last_expected = end_open - step
        if last_expected < first_expected:
            raise TrainerError(
                f"{self.pair} {tf}: no whole bar between {_iso(start)} and {_iso(end)}"
            )
        read_start, read_end = start, end_open
        try:
            if not self.offline:
                # Fill the cache. get_candles' default now (the wall clock) decides
                # which fetched bars are closed enough to cache; a past now would drop
                # the bars between train_end and the cache's first bar and leave a
                # permanent hole in the shared cache.
                get_candles(self.pair, tf, start, end_open, cache_dir=self.cache_dir)
                cached = self._cached_range(tf)
                if cached is None:
                    raise TrainerError(
                        f"{self.pair} {tf}: the exchange returned no bars for "
                        f"{_iso(start)} .. {_iso(end)}"
                    )
                # Bars the exchange does not have (a pair listed later, a missing bar
                # at either end) are missing from the cache too: read what is there
                # and report the shortfall below.
                read_start = max(start, cached[0])
                read_end = min(end_open, cached[1] + step)
            # Every run reads through the cache file with now=train_end, so no bar that
            # closes after train_end can be returned. Offline, a cache that does not
            # reach both ends of the window is an error.
            df = get_candles(
                self.pair,
                tf,
                read_start,
                read_end,
                closed_only=True,
                cache_dir=self.cache_dir,
                offline=True,
                now=end,
            )
        except CandleDataError as exc:
            raise TrainerError(f"candles {self.pair} {tf}: {exc}") from exc
        if df.empty:
            raise TrainerError(
                f"{self.pair} {tf}: no closed bars in {_iso(start)} .. {_iso(end)}"
            )
        first_open = df["open_time"].iloc[0].to_pydatetime()
        last_open = df["open_time"].iloc[-1].to_pydatetime()
        if last_open + step > end:
            raise TrainerError(
                f"lookahead: {self.pair} {tf} bar closing {last_open + step} is after "
                f"train_end {end}"
            )
        if first_open < start:
            raise TrainerError(
                f"{self.pair} {tf} bar {first_open} is before train_start"
            )
        missing_start = int((first_open - first_expected) // step)
        missing_end = int((last_expected - last_open) // step)
        report = df.attrs.get("report")
        self.reports[tf] = {
            "bars": int(len(df)),
            "first_open": _iso(first_open),
            "last_open": _iso(last_open),
            "window_first_open": _iso(first_expected),
            "window_last_open": _iso(last_expected),
            "missing_at_start": missing_start,
            "missing_at_end": missing_end,
            "gaps": [] if report is None else [list(map(str, g)) for g in report.gaps],
        }
        if missing_start or missing_end:
            print(
                f"{self.pair} {tf}: no bars for the first {missing_start} and the last "
                f"{missing_end} bar(s) of the window (listed later, or missing on the "
                f"exchange); using {_iso(first_open)} .. {_iso(last_open)}"
            )
        # plain Python floats: str() of a numpy float would corrupt the memory format
        return (
            df["open"].tolist(),
            df["close"].tolist(),
            df["high"].tolist(),
            df["low"].tolist(),
        )

    def _cached_range(self, tf):
        """(first, last) open time in the cache file, or None if it is empty."""
        from market_data.candles import cache_path, load_candles_csv

        path = cache_path(self.pair, tf, self.cache_dir)
        if not os.path.isfile(path):
            return None
        df = load_candles_csv(path, tf)
        if df.empty:
            return None
        return (
            df["open_time"].iloc[0].to_pydatetime(),
            df["open_time"].iloc[-1].to_pydatetime(),
        )


def select_rows(bars, data_tf, restarted_yet):
    """Upstream's row choice (``ba62130:pt_trainer.py:452-458``) on closed bars."""
    opens, closes, highs, lows = bars
    n = len(closes)
    if data_tf in ("1day", "1week") and restarted_yet != 0:
        keep = n  # upstream: index = 1, i.e. everything except the forming bar
    else:
        keep = (n + 1) - (
            n + 1
        ) // 2  # upstream: the older half of n closed + 1 forming
    return opens[:keep], closes[:keep], highs[:keep], lows[:keep]


# --- model files (upstream load_memory / flush_memory / write_threshold_sometimes) ----


def _strip(text: str) -> str:
    """Upstream's clean-up chain, applied before every split."""
    return (
        text.replace("'", "")
        .replace(",", "")
        .replace('"', "")
        .replace("]", "")
        .replace("[", "")
    )


def _write_text(path: str, text: str) -> None:
    """Atomic write; retried briefly if Windows briefly locks the file."""
    for attempt in range(5):
        try:
            pt_paths.write_private_text(path, text)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2)


class ModelFiles:
    """Upstream's in-RAM memory cache per timeframe and its file writes, in one folder."""

    def __init__(self, folder: str):
        self.folder = folder
        self.cache = {}
        self.threshold_written = {}

    def path(self, name: str) -> str:
        return os.path.join(self.folder, name)

    def load(self, tf_choice):
        # upstream read existing files here; the folder starts empty (deviation 6)
        if tf_choice not in self.cache:
            self.cache[tf_choice] = {
                "memory_list": [],
                "weight_list": [],
                "high_weight_list": [],
                "low_weight_list": [],
                "dirty": False,
            }
        return self.cache[tf_choice]

    def flush(self, tf_choice, force=False):
        data = self.cache.get(tf_choice)
        if not data:
            return
        if (not data.get("dirty")) and (not force):
            return
        _write_text(
            self.path(f"memories_{tf_choice}.txt"),
            "~".join([x for x in data["memory_list"] if str(x).strip() != ""]),
        )
        for name, key in (
            ("memory_weights", "weight_list"),
            ("memory_weights_high", "high_weight_list"),
            ("memory_weights_low", "low_weight_list"),
        ):
            _write_text(
                self.path(f"{name}_{tf_choice}.txt"),
                " ".join([str(x) for x in data[key] if str(x).strip() != ""]),
            )
        data["dirty"] = False

    def write_threshold_sometimes(self, tf_choice, perfect_threshold, loop_i):
        last = self.threshold_written.get(tf_choice)
        if (
            (loop_i % FLUSH_EVERY != 0)
            and (last is not None)
            and (abs(perfect_threshold - last) < 0.05)
        ):
            return
        self.write_threshold(tf_choice, perfect_threshold)

    def write_threshold(self, tf_choice, perfect_threshold):
        _write_text(
            self.path(f"neural_perfect_threshold_{tf_choice}.txt"),
            str(perfect_threshold),
        )
        self.threshold_written[tf_choice] = perfect_threshold

    def read_list(self, name: str, separator: str):
        """Upstream re-reads the flushed files on every step; so does the port."""
        with open(self.path(name), "r", encoding="utf-8") as f:
            return _strip(f.read()).split(separator)


# --- training -------------------------------------------------------------------------


def run_pass(files, tf_choice, restarted_yet, bars, log):
    """One pass of one timeframe: upstream ``ba62130:pt_trainer.py:503-1625``.

    Returns the pass statistics and the final threshold (None if skipped)."""
    open_price_list, price_list, high_price_list, low_price_list = bars
    n = len(price_list)
    stats = {
        "bars_used": n,
        "steps": 0,
        "new_memories": 0,
        "matched_steps": 0,
        "unlearned_steps": 0,
    }
    if restarted_yet < 2 and n < 10:
        stats["skipped"] = "fewer than 10 bars (upstream would loop for ever)"
        return stats, None
    if restarted_yet == 2 and n < 4:
        stats["skipped"] = "fewer than 4 bars (upstream would loop for ever)"
        return stats, None

    perfect_threshold = 1.0
    loop_i = 0
    price_list_length = 10 if restarted_yet < 2 else int(len(price_list) * 0.5)
    while True:
        loop_i += 1
        open_price_list2 = open_price_list[:price_list_length]
        price_list2 = price_list[:price_list_length]
        high_price_list2 = high_price_list[:price_list_length]
        low_price_list2 = low_price_list[:price_list_length]
        price_change_list = [
            100 * ((price_list2[i] - open_price_list2[i]) / open_price_list2[i])
            for i in range(len(price_list2))
        ]

        # the pattern: the last candle's body % (number_of_candles = [2])
        current_pattern = [price_change_list[len(price_change_list) - 1]]

        # match against the memories last flushed to disk
        moves, high_moves, low_moves = [], [], []
        move_weights, high_move_weights, low_move_weights = [], [], []
        unweighted, perfect_dexs = [], []
        weight_list, high_weight_list, low_weight_list = [], [], []
        final_moves = high_final_moves = low_final_moves = 0.0
        try:
            memory_list = files.read_list(f"memories_{tf_choice}.txt", "~")
            weight_list = files.read_list(f"memory_weights_{tf_choice}.txt", " ")
            high_weight_list = files.read_list(
                f"memory_weights_high_{tf_choice}.txt", " "
            )
            low_weight_list = files.read_list(
                f"memory_weights_low_{tf_choice}.txt", " "
            )
            for mem_ind in range(len(memory_list)):
                memory_pattern = _strip(memory_list[mem_ind].split("{}")[0]).split(" ")
                checks = []
                for check_dex in range(len(current_pattern)):
                    current_candle = float(current_pattern[check_dex])
                    memory_candle = float(memory_pattern[check_dex])
                    if current_candle + memory_candle == 0.0:
                        difference = 0.0
                    else:
                        try:
                            difference = abs(
                                (
                                    abs(current_candle - memory_candle)
                                    / ((current_candle + memory_candle) / 2)
                                )
                                * 100
                            )
                        except Exception:
                            difference = 0.0
                    checks.append(difference)
                diff_avg = sum(checks) / len(checks)
                if diff_avg <= perfect_threshold:
                    parts = memory_list[mem_ind].split("{}")
                    high_diff = float(_strip(parts[1]).replace(" ", "")) / 100
                    low_diff = float(_strip(parts[2]).replace(" ", "")) / 100
                    move = float(memory_pattern[len(memory_pattern) - 1])
                    unweighted.append(move)
                    move_weights.append(float(weight_list[mem_ind]))
                    high_move_weights.append(float(high_weight_list[mem_ind]))
                    low_move_weights.append(float(low_weight_list[mem_ind]))
                    moves.append(move * float(weight_list[mem_ind]))
                    high_moves.append(high_diff * float(high_weight_list[mem_ind]))
                    low_moves.append(low_diff * float(low_weight_list[mem_ind]))
                    perfect_dexs.append(mem_ind)
            if perfect_dexs:
                final_moves = sum(moves) / len(moves)
                high_final_moves = sum(high_moves) / len(high_moves)
                low_final_moves = sum(low_moves) / len(low_moves)
        except Exception:
            # upstream: no memory file yet, or one it cannot parse -> no match
            moves, high_moves, low_moves = [], [], []
            move_weights, high_move_weights, low_move_weights = [], [], []
            unweighted, perfect_dexs = [], []
            weight_list, high_weight_list, low_weight_list = [], [], []
            final_moves = high_final_moves = low_final_moves = 0.0
        if perfect_dexs:
            stats["matched_steps"] += 1

        # the match threshold moves towards about 20 matches per step
        if len(unweighted) > 20:
            if perfect_threshold < 0.1:
                perfect_threshold -= 0.001
            else:
                perfect_threshold -= 0.01
            if perfect_threshold < 0.0:
                perfect_threshold = 0.0
        else:
            if perfect_threshold < 0.1:
                perfect_threshold += 0.001
            else:
                perfect_threshold += 0.01
            if perfect_threshold > 100.0:
                perfect_threshold = 100.0
        files.write_threshold_sometimes(tf_choice, perfect_threshold, loop_i)

        # predict the next close, high and low from the matched memories
        index = len(price_list2) - 2
        last_closes = []
        while True:
            last_closes.append(price_list2[index])
            if len(last_closes) >= 2:
                break
            index += 1
            if index >= len(price_list2):
                break
        start_price = last_closes[len(last_closes) - 1]
        c_diff = final_moves / 100
        new_price = start_price + (start_price * c_diff)
        high_new_price = start_price + (start_price * high_final_moves)
        low_new_price = start_price + (start_price * low_final_moves)
        new_y = [start_price, new_price]
        high_new_y = [start_price, high_new_price]  # noqa: F841 (upstream statistics)
        low_new_y = [start_price, low_new_price]  # noqa: F841 (upstream statistics)

        # reveal the next candle
        price_list_length += 1
        stats["steps"] += 1
        if len(price_list2) >= int(len(price_list) * 0.25) and restarted_yet < 2:
            return stats, perfect_threshold  # next pass (no learning on this step)
        if len(price_list2) == len(price_list):
            return stats, perfect_threshold  # timeframe done (no learning on this step)
        if new_y[1] == 0:
            # Upstream divides by the predicted close here (``this_differ``, a statistic
            # the port dropped). A zero (a last close of 0, or a predicted move of
            # exactly -100%) raises inside its learning ``try``, which skips learning
            # for this step: no memory, no weight change, no flush.
            stats["unlearned_steps"] += 1
            continue

        price_list2 = price_list[:price_list_length]
        high_price_list2 = high_price_list[:price_list_length]
        low_price_list2 = low_price_list[:price_list_length]
        price2 = price_list2[len(price_list2) - 1]
        high_price2 = high_price_list2[len(high_price_list2) - 1]
        low_price2 = low_price_list2[len(low_price_list2) - 1]
        this_diff = ((price2 - new_y[0]) / abs(new_y[0])) * 100
        high_this_diff = ((high_price2 - new_y[0]) / abs(new_y[0])) * 100
        low_this_diff = ((low_price2 - new_y[0]) / abs(new_y[0])) * 100
        perc_diff_now_actual = ((price2 - new_y[0]) / abs(new_y[0])) * 100
        high_perc_diff_now_actual = ((high_price2 - new_y[0]) / abs(new_y[0])) * 100
        low_perc_diff_now_actual = ((low_price2 - new_y[0]) / abs(new_y[0])) * 100

        mem = files.load(tf_choice)
        if moves:
            # adjust the matched memories' weights. Upstream applies these updates to
            # the lists it re-read from disk this step, which are then discarded, so
            # they never reach the files (kept on purpose).
            for indy in range(len(unweighted)):
                var3 = moves[indy] * 100
                high_var3 = high_moves[indy] * 100
                low_var3 = low_moves[indy] * 100
                if high_perc_diff_now_actual > high_var3 + (high_var3 * 0.1):
                    high_new_weight = min(high_move_weights[indy] + 0.25, 2.0)
                elif high_perc_diff_now_actual < high_var3 - (high_var3 * 0.1):
                    high_new_weight = max(high_move_weights[indy] - 0.25, 0.0)
                else:
                    high_new_weight = high_move_weights[indy]
                if low_perc_diff_now_actual < low_var3 - (low_var3 * 0.1):
                    low_new_weight = min(low_move_weights[indy] + 0.25, 2.0)
                elif low_perc_diff_now_actual > low_var3 + (low_var3 * 0.1):
                    low_new_weight = max(low_move_weights[indy] - 0.25, 0.0)
                else:
                    low_new_weight = low_move_weights[indy]
                if perc_diff_now_actual > var3 + (var3 * 0.1):
                    new_weight = min(move_weights[indy] + 0.25, 2.0)
                elif perc_diff_now_actual < var3 - (var3 * 0.1):
                    new_weight = max(move_weights[indy] - 0.25, 0.0 - 2.0)
                else:
                    new_weight = move_weights[indy]
                del weight_list[perfect_dexs[indy]]
                weight_list.insert(perfect_dexs[indy], new_weight)
                del high_weight_list[perfect_dexs[indy]]
                high_weight_list.insert(perfect_dexs[indy], high_new_weight)
                del low_weight_list[perfect_dexs[indy]]
                low_weight_list.insert(perfect_dexs[indy], low_new_weight)
            mem["dirty"] = True
        else:
            # nothing matched: remember this pattern and what followed it
            pattern = list(current_pattern) + [this_diff]
            mem_entry = (
                _strip(str(pattern))
                + "{}"
                + str(high_this_diff)
                + "{}"
                + str(low_this_diff)
            )
            mem["memory_list"].append(mem_entry)
            mem["weight_list"].append("1.0")
            mem["high_weight_list"].append("1.0")
            mem["low_weight_list"].append("1.0")
            mem["dirty"] = True
            stats["new_memories"] += 1
        if loop_i % FLUSH_EVERY == 0:
            files.flush(tf_choice)
        if loop_i % PROGRESS_EVERY == 0:
            log(
                f"  {tf_choice} pass {restarted_yet}: step {loop_i}, window "
                f"{len(price_list2)}/{n}, memories {len(mem['memory_list'])}, "
                f"threshold {perfect_threshold:.3f}"
            )


def train(
    coin,
    folder,
    train_start,
    train_end,
    seed=0,
    offline=False,
    cache_dir=None,
    upstream_flush_only=False,
    log=print,
):
    """Train every timeframe into ``folder``; return the run summary."""
    random.seed(seed)
    pair = f"{coin}USDT"
    loader = BarLoader(pair, train_start, train_end, offline, cache_dir)
    files = ModelFiles(folder)
    summary_tfs = {}
    for tf_choice in TF_CHOICES:
        passes = []
        final_threshold = None
        for restarted_yet in (0, 1, 2):
            data_tf = "1hour" if restarted_yet == 0 else tf_choice
            all_bars = loader.bars(data_tf)
            bars = select_rows(all_bars, data_tf, restarted_yet)
            log(
                f"{tf_choice} pass {restarted_yet}: {data_tf} bars, using the oldest "
                f"{len(bars[1])} of {len(all_bars[1])}"
            )
            files.load(tf_choice)
            stats, threshold = run_pass(files, tf_choice, restarted_yet, bars, log)
            stats.update(
                {
                    "pass": restarted_yet,
                    "data_tf": data_tf,
                    "bars_in_window": len(all_bars[1]),
                }
            )
            if stats.get("skipped"):
                log(f"{tf_choice} pass {restarted_yet}: skipped, {stats['skipped']}")
            if threshold is not None:
                final_threshold = threshold
            passes.append(stats)
        mem = files.load(tf_choice)
        if not upstream_flush_only:
            files.flush(tf_choice, force=True)
            if final_threshold is not None:
                files.write_threshold(tf_choice, final_threshold)
            for name in (
                f"neural_perfect_threshold_{tf_choice}.txt",
                f"memories_{tf_choice}.txt",
            ):
                if not os.path.isfile(files.path(name)):
                    raise TrainerError(
                        f"{tf_choice}: no {name} after training (too few bars?)"
                    )
        summary_tfs[tf_choice] = {
            "passes": passes,
            "memories": len(mem["memory_list"]),
            "final_threshold": final_threshold,
        }
        log(f"{tf_choice} done: {len(mem['memory_list'])} memories")
    return {"timeframes": summary_tfs, "candles": loader.reports}


# --- process --------------------------------------------------------------------------


def _leave_program_dir(coin: str) -> None:
    """Started from a terminal inside the read-only program folder, move to the
    coin's neural folder first (BTC: the root; other coins: <root>/<SYM>)."""
    if pt_paths.is_inside_program_dir(os.getcwd()):
        folder = pt_paths.neural_dir()
        folder = folder if coin == "BTC" else os.path.join(folder, coin)
        os.makedirs(folder, exist_ok=True)
        os.chdir(folder)


def _existing_model_files(folder: str):
    return sorted(
        name
        for name in os.listdir(folder)
        if name.startswith(MODEL_FILE_PREFIXES)
        and os.path.isfile(os.path.join(folder, name))
    )


def _write_status(folder, coin, state, started_at, **extra):
    status = {"coin": coin, "state": state, "started_at": started_at, **extra}
    status["timestamp"] = extra.get("finished_at", int(time.time()))
    _write_text(os.path.join(folder, "trainer_status.json"), json.dumps(status))


def main(argv=None) -> int:
    started = time.time()
    try:
        cfg = parse_args(argv)
    except UsageError as exc:
        print(f"ERROR: {exc}")
        return 2
    coin = cfg["coin"]
    _leave_program_dir(coin)
    folder = os.getcwd()
    print(
        f"PowerTrader AI+ pattern trainer (port of {UPSTREAM_REPO} {UPSTREAM_COMMIT})"
    )
    print(f"Coin: {coin}   Working folder: {folder}")
    for key in ("train_start", "train_end"):
        print(f"{key}: {_iso(cfg[key])} ({cfg['sources'][key]})")
    print(f"seed: {cfg['seed']} ({cfg['sources']['seed']})")
    print(f"offline: {cfg['offline']} ({cfg['sources']['offline']})")
    existing = _existing_model_files(folder)
    if existing:
        print(
            f"ERROR: the working folder already holds model files ({', '.join(existing[:5])}"
            f"{', ...' if len(existing) > 5 else ''}); the trainer only starts from an "
            "empty folder"
        )
        return 2
    started_at = int(started)
    _write_status(folder, coin, "TRAINING", started_at)
    try:
        result = train(
            coin,
            folder,
            cfg["train_start"],
            cfg["train_end"],
            seed=cfg["seed"],
            offline=cfg["offline"],
            upstream_flush_only=cfg["upstream_flush_only"],
        )
    except Exception as exc:
        traceback.print_exc()
        print(f"ERROR: training failed for {coin}: {exc}")
        try:
            _write_status(
                folder,
                coin,
                "ERROR",
                started_at,
                error=str(exc),
                finished_at=int(time.time()),
            )
        except OSError:
            pass
        return 1

    finished_at = int(time.time())
    summary = {
        "coin": coin,
        "trainer": "pt_pattern_trainer.py",
        "upstream": {
            "repo": UPSTREAM_REPO,
            "commit": UPSTREAM_COMMIT,
            "blob": UPSTREAM_BLOB,
        },
        "train_start": _iso(cfg["train_start"]),
        "train_end": _iso(cfg["train_end"]),
        "seed": cfg["seed"],
        "offline": cfg["offline"],
        "sources": cfg["sources"],
        "started_at": started_at,
        "finished_at": finished_at,
        "runtime_seconds": round(time.time() - started, 1),
        **result,
    }
    _write_text(
        pt_paths.data_file("training_results", f"{coin.lower()}_training_results.json"),
        json.dumps(summary, indent=2),
    )
    _write_status(folder, coin, "FINISHED", started_at, finished_at=finished_at)
    _write_text(os.path.join(folder, "trainer_last_start_time.txt"), str(started_at))
    # last, so a coin only counts as trained once every file is in place
    _write_text(
        os.path.join(folder, "trainer_last_training_time.txt"), str(finished_at)
    )
    print(f"Training completed for {coin} in {summary['runtime_seconds']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
