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

Then the model is published (FDS-MDL Phase 2): a copy of the 35 files with a manifest
goes to ``<data>/hub_data/strategy_models/<model_id>/`` (app/model_store.py). The
manifest records the window, the candles, the seed, the code and validation metrics: a
separate fit on the first 80% of the span the bars cover, scored frozen on the last 20%
(the published model itself is the whole-window fit). The neural runner uses a coin's
files only when a published manifest matches them.

Training follows upstream statement for statement, including its quirks (kept on
purpose, FDS-MDL owner decision; see docs/dev/RUN-LOG-model-1.md):

* weight updates are applied to lists re-read from disk on every step and are never
  saved, so every saved weight stays 1.0;
* the close-weight test multiplies a move that is already a percentage by 100;
* each step matches against the memories last flushed to disk (every 200 steps);
* pass 0 of every timeframe trains on 1-hour bars;
* a step whose predicted close is 0 (a last close of 0, or a predicted move of exactly
  -100%) learns nothing, because upstream's division by it raises inside its learning
  ``try`` (counted as ``unlearned_steps``).

Deviations from upstream, each with its reason:

1. Data: the candles of one exchange in Settings, the primary exchange first, through
   ``app/market_data/candles.py`` (cached per exchange; FDS-MX-001 phase F). An
   exchange that cannot reach back to train_start (Kraken serves its latest 720 bars)
   is passed over. The model records the exchange and its market.
   The window is ``[train_start, train_end)`` and only bars closed by ``train_end`` are
   read: every run reads the cache with ``now=train_end`` and checks the result, so no
   candle after ``train_end`` can be read (FDS-MDL 4.3). Upstream read up to the wall
   clock. Online, the cache is filled first (the wall clock decides which fetched bars
   are closed enough to cache, so the shared cache never gets a hole). Bars the exchange
   does not have at either end of the window (a pair listed later, a missing bar) are
   counted in the summary (``missing_at_start``, ``missing_at_end``) and printed; gaps
   inside the window are listed. Offline, the cache must reach both ends of the window,
   or the run fails. A pair listed after ``train_start`` reaches it once an online run
   has asked the exchange: the cache records that it has no bars before the listing
   (``<PAIR>_<TF>.start.json``); without that record, a short cache and an exchange
   that has no bars there look the same.
2. Row selection (with ``--upstream-rows`` only; see deviation 11): upstream kept the
   older ``L - int(L/2)`` of the ``L`` rows it fetched, which included KuCoin's
   still-forming bar, so the port keeps the oldest ``(n+1) - (n+1)//2`` of the ``n``
   closed bars. For passes 1-2 of ``1day``/``1week`` upstream dropped only the forming
   bar, so the port keeps all ``n``. Each count is printed and recorded in the summary
   (never a silent subsample, FDS-MDL 4.7). Upstream also counted a malformed row
   produced when its last page came back empty; the port has no pages.
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
10. The close weight's accuracy test (#150) compares a percentage with a percentage.
    ``moves`` already holds the predicted close move in percent (times the memory's
    weight), so it is no longer multiplied by 100. Upstream's
    ``var3 = moves[indy] * 100`` treated it like ``high_moves`` and ``low_moves``,
    which are divided by 100 when read.
11. Every bar, newest included (owner, 2026-11-03). Upstream trained on the older half
    of the history (deviation 2), walked passes 0-1 to its first quarter (pass 1 of the
    1-hour timeframe replaying pass 0's bars against the memories pass 0 had just
    stored) and pass 2 from its middle, so the newest half was never learned and the
    second quarter only seen. No reason for this is recorded upstream. Now every pass
    walks every bar of the window, from the 10th to the newest: pass 0 the 1-hour bars,
    then one pass the timeframe's own bars; the 1-hour timeframe walks its bars once.
    ``--upstream-rows`` (testing only) keeps upstream's rows and passes, so the oracle
    test can still compare the files with upstream's.
12. The same numbers, faster. Pass 0 is the same walk in every timeframe (no memories,
    the same 1-hour bars), so it is walked once and copied into each. A flush or
    threshold write keeps the file's text in memory, which matching reads (upstream
    re-read the files every step), and the files are written once each timeframe is
    trained. Each step uses its own bar rather than rebuilding the changes of every bar
    seen so far, and a memory's text is split once. The oracle test checks the files
    are byte-identical to upstream's with ``--upstream-rows``.
13. The entry gate (owner, 2026-11-05). Upstream used every model it trained; a model is
    now published only when its entries pass the gate (model_gate, entry_gate): on its
    held-out bars, the validation fit's entries replayed with the trader's rules must
    earn more per day held after fees than random entries made with the same waits and
    rules, and at least as much as the current model did on its own held-out bars
    (FDS-MH-001 §6). Otherwise the coin's current model (its
    newest published one) is copied back into the folder and stays in use; a coin with
    none keeps the new files unpublished, so the neural runner gives it no signals. The
    decision is printed, recorded in ``model_gate.json`` in the coin's folder and in the
    training summary, and, for a published model, in its manifest. ``--check-gate``
    runs the gate again on the coin's current model (its validation fit is refitted from
    the manifest) and changes nothing.

Inputs (command line, else environment, else default):

* ``coin`` (positional, default BTC);
* ``--window`` / ``POWERTRADER_TRAIN_WINDOW``: ``30d``, ``3m`` (90 days), ``6m`` (180),
  ``12m`` (365), ``3y`` (1,095, the default) or ``all`` (the coin's whole history on its
  exchange: from ``HISTORY_START``);
* ``--train-start`` / ``POWERTRADER_TRAIN_START`` (default: ``train_end`` minus the window;
  given, it overrides the window);
* ``--train-end`` / ``POWERTRADER_TRAIN_END`` (default: the last full hour, UTC);
* ``--seed`` / ``POWERTRADER_TRAIN_SEED`` (default 0);
* ``--offline`` / ``POWERTRADER_CANDLES_OFFLINE=1``: read the candle cache only, never the
  network;
* ``--check-gate``: run the entry gate on the coin's current model and report it; nothing
  is trained, published or written in the coin's folder.
"""

import argparse
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import pt_paths  # noqa: E402
import trainer_status  # noqa: E402

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
# the files of one timeframe's model, by prefix (``<prefix>_<timeframe>.txt``)
TIMEFRAME_FILES = (
    "memories",
    "memory_weights",
    "memory_weights_high",
    "memory_weights_low",
    "neural_perfect_threshold",
)
# The training windows (``--window``; Settings > Training), in days. "all" is the coin's
# whole history on the exchange its candles come from: from HISTORY_START, and the
# candle cache records where the exchange's bars begin.
WINDOWS = {"30d": 30, "3m": 90, "6m": 180, "12m": 365, "3y": 1095}
ALL_HISTORY = "all"
DEFAULT_WINDOW_NAME = "3y"
DEFAULT_WINDOW = timedelta(days=WINDOWS[DEFAULT_WINDOW_NAME])
HISTORY_START = datetime(2010, 7, 17, tzinfo=timezone.utc)  # bitcoin's first exchange
FLUSH_EVERY = (
    200  # upstream: flush memories/weights and write the threshold every 200 steps
)
PROGRESS_EVERY = 500

ENV_TRAIN_START = "POWERTRADER_TRAIN_START"
ENV_TRAIN_END = "POWERTRADER_TRAIN_END"
ENV_TRAIN_SEED = "POWERTRADER_TRAIN_SEED"
ENV_CANDLES_OFFLINE = "POWERTRADER_CANDLES_OFFLINE"
ENV_TRAIN_WINDOW = "POWERTRADER_TRAIN_WINDOW"
TRAINER_ENV = (
    ENV_TRAIN_START,
    ENV_TRAIN_END,
    ENV_TRAIN_SEED,
    ENV_CANDLES_OFFLINE,
    ENV_TRAIN_WINDOW,
)


class TrainerError(Exception):
    """Training cannot continue (data missing, lookahead, a failed write, ...)."""


class UsageError(TrainerError):
    """Bad arguments or a working folder the trainer refuses to use."""


class MarketClosedError(TrainerError):
    """The pair's bars stop well before a live run's train_end, or its market is not
    listed. ``confirmed``: the market status says it is not trading (or not listed),
    so the coin is recorded as not trading; otherwise (it says the market trades, or
    could not be asked) the run is refused but nothing is recorded."""

    def __init__(self, pair, reason, confirmed=True):
        if confirmed:
            advice = (
                "not training a coin that no longer trades. Remove it from Coins in "
                "Settings, or train it again once it trades"
            )
        else:
            advice = "not training on bars that stop early. Try again later"
        super().__init__(f"{reason}: {advice}.")
        self.pair = pair
        self.reason = reason
        self.confirmed = confirmed


# A run whose train_end is this close to now trains a model for live use; its bars
# must reach train_end. A run on an older window may end on a short tail.
LIVE_WINDOW = timedelta(days=2)
# Missing at the end of a live window that means "stopped trading", not a late bar.
STALE_TAIL = timedelta(hours=6)


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
    parser.add_argument(
        "--window",
        help=f"the window before train_end: one of {', '.join(WINDOWS)} or "
        f"{ALL_HISTORY} (default {DEFAULT_WINDOW_NAME}; --train-start overrides it)",
    )
    parser.add_argument("--seed")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--exchange",
        help="read this exchange's candles only (default: the exchanges in Settings, "
        "primary first)",
    )
    parser.add_argument(
        "--check-gate",
        action="store_true",
        help="run the entry gate on the coin's current model and report it; nothing is "
        "trained, published or changed",
    )
    parser.add_argument(
        "--upstream-flush-only",
        action="store_true",
        help="testing only: flush and write the threshold exactly as upstream did "
        "(every 200 steps, losing the rest), to compare output with upstream",
    )
    parser.add_argument(
        "--upstream-rows",
        action="store_true",
        help="testing only: upstream's rows and passes (the older half of the window, "
        "passes 0-1 to its first quarter, pass 2 from its middle), to compare output "
        "with upstream",
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
    window_raw, window_src = pick(args.window, ENV_TRAIN_WINDOW)
    window = str(window_raw or DEFAULT_WINDOW_NAME).strip().lower()
    if window != ALL_HISTORY and window not in WINDOWS:
        raise UsageError(
            f"window: {window_raw!r} is not one of {', '.join(WINDOWS)}, {ALL_HISTORY}"
        )
    start_raw, start_src = pick(args.train_start, ENV_TRAIN_START)
    if start_raw is not None:
        train_start = _parse_time(start_raw, "train_start")
    elif window == ALL_HISTORY:
        train_start, start_src = HISTORY_START, f"window {ALL_HISTORY}"
    else:
        train_start = train_end - timedelta(days=WINDOWS[window])
        start_src = f"window {window}" if window_raw is not None else "default"
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
        "exchanges": [str(args.exchange).strip().lower()] if args.exchange else None,
        "upstream_flush_only": bool(args.upstream_flush_only),
        "upstream_rows": bool(args.upstream_rows),
        "check_gate": bool(args.check_gate),
        "window": window,
        "sources": {
            "train_start": start_src,
            "train_end": end_src,
            "window": window_src,
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
    """Closed bars for one coin inside ``[train_start, train_end)``, from the candle
    cache of one exchange: the first in Settings order (``exchanges`` narrows or
    reorders them) that can serve the window, filled from that exchange unless
    offline. Every timeframe comes from that exchange. This is the only data
    source."""

    def __init__(
        self,
        coin,
        train_start,
        train_end,
        offline,
        cache_dir=None,
        status_of=None,
        exchanges=None,
        manager=None,
    ):
        from pt_exchange_abstraction import dollar_symbol

        self.market = dollar_symbol(coin)  # e.g. BTC-USD
        self.pair = self.market  # the chosen exchange's market, once known
        self.exchange = None
        self.exchanges = list(exchanges) if exchanges else None
        self._manager = manager
        self.train_start = train_start
        self.train_end = train_end
        self.offline = offline
        self.cache_dir = cache_dir
        self.status_of = status_of  # market -> listing.PairStatus; None: shared check
        self._bars = {}
        self.frames = {}
        self.reports = {}

    def _check_tail(self, tf, last_open, step, missing_end):
        """A live run whose bars stop well before train_end: the pair stopped trading.
        The market status is asked why; the run is refused either way."""
        if self.offline or missing_end == 0:
            return
        now = datetime.now(timezone.utc)
        if abs(now - self.train_end) > LIVE_WINDOW:
            return  # an older window: a short tail is reported, not refused
        if missing_end * step < max(3 * step, STALE_TAIL):
            return  # a late or missing bar or two, not a market that stopped
        try:
            if self.status_of is not None:
                status = self.status_of(self.market)
            else:
                from market_data import listing

                status = listing.pair_status(self.market)
        except Exception:
            status = None
        last_close = _iso(last_open + step)
        if status is not None and status.trading is False:
            reason = f"{status.describe()} (its {tf} bars stop at {last_close})"
            raise MarketClosedError(self.pair, reason, confirmed=True)
        said = (
            "status unknown" if status is None or status.trading is None else "trading"
        )
        reason = (
            f"{self.pair} has no {tf} bars after {last_close} (market status: {said})"
        )
        raise MarketClosedError(self.pair, reason, confirmed=False)

    def bars(self, tf_choice):
        if tf_choice not in self._bars:
            self._bars[tf_choice] = self._load(CANDLE_TF[tf_choice])
        return self._bars[tf_choice]

    def _load(self, tf):
        import pandas as pd

        from market_data.candles import CandleDataError, get_candles
        from market_data.timeframes import bar_open_floor, candle_timeframe_seconds
        from pt_exchange_abstraction import MarketNotFound

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
            if self.exchange is None:
                self._choose_exchange(tf, start, end_open)
            if not self.offline:
                # Fill the cache. get_candles' default now (the wall clock) decides
                # which fetched bars are closed enough to cache; a past now would drop
                # the bars between train_end and the cache's first bar and leave a
                # permanent hole in the shared cache.
                self._fill(tf, start, end_open)
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
                exchange=self.exchange,
            )
        except MarketNotFound as exc:  # no exchange in Settings has the coin
            raise MarketClosedError(self.market, str(exc)) from None
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
        self._check_tail(tf, last_open, step, missing_end)
        report = df.attrs.get("report")
        self.frames[tf] = df
        self.reports[tf] = {
            "bars": int(len(df)),
            "sha256": candle_sha256(df),
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

    def _manager_for_fetch(self):
        from market_data import candles

        return (
            self._manager if self._manager is not None else candles._exchange_manager()
        )

    def _choose_exchange(self, tf, start, end_open):
        """The exchange whose candles the whole run uses: the first that can serve
        ``tf`` over the window (offline: whose cache covers it)."""
        from market_data.candles import exchange_candles

        df = exchange_candles(
            self.market,
            tf,
            start,
            end_open,
            cache_dir=self.cache_dir,
            offline=self.offline,
            manager=self._manager if self.offline else self._manager_for_fetch(),
            exchanges=self.exchanges,
        )
        self.exchange, self.pair = df.attrs["exchange"], df.attrs["pair"]
        print(f"{self.market}: training bars from {self.exchange} {self.pair}")

    def _fill(self, tf, start, end_open):
        """Fill the cache with ``tf`` bars over the window from the chosen exchange
        only (one model, one exchange)."""
        from market_data.candles import ExchangeFetcher, get_candles

        fetcher = ExchangeFetcher(
            self._manager_for_fetch(), self.exchange, self.market, self.cache_dir
        )
        get_candles(
            self.pair,
            tf,
            start,
            end_open,
            cache_dir=self.cache_dir,
            fetcher=fetcher,
            exchange=self.exchange,
        )

    def _cached_range(self, tf):
        """(first, last) open time in the cache file, or None if it is empty."""
        from market_data.candles import cache_path, load_candles_csv

        path = cache_path(self.pair, tf, self.cache_dir, self.exchange)
        if not os.path.isfile(path):
            return None
        df = load_candles_csv(path, tf)
        if df.empty:
            return None
        return (
            df["open_time"].iloc[0].to_pydatetime(),
            df["open_time"].iloc[-1].to_pydatetime(),
        )


def candle_sha256(df) -> str:
    """SHA-256 of the bars actually read, in the candle cache's CSV format (the cache
    file itself is shared and grows, so its own hash would not identify them)."""
    open_ms = df["open_time"].map(lambda t: int(t.timestamp() * 1000))
    lines = ["open_time_ms,open,high,low,close,volume"]
    for row in zip(
        open_ms,
        df["open"].tolist(),
        df["high"].tolist(),
        df["low"].tolist(),
        df["close"].tolist(),
        df["volume"].tolist(),
    ):
        lines.append(",".join([str(row[0])] + [repr(float(v)) for v in row[1:]]))
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


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
    """Upstream's in-RAM memory cache per timeframe and its file writes, in one folder.

    Upstream wrote the files at every flush and threshold write, and re-read them on
    every step. Here a flush or threshold write sets the file's text in ``written``,
    and ``read_list`` reads that text: what matching sees is the same (the memories
    last flushed, not the newer ones in RAM), without the disk. ``persist`` writes a
    timeframe's files once it is trained. A file this run has not written is read
    from the folder, as upstream read it (a run's folder starts empty: deviation 6)."""

    def __init__(self, folder: str):
        self.folder = folder
        self.cache = {}
        self.threshold_written = {}
        self.written = {}  # file name -> its text, as the last flush or write left it
        self._split = {}  # (file name, separator) -> its cleaned-up, split text

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

    def _put(self, name: str, text: str) -> None:
        self.written[name] = text
        for key in [k for k in self._split if k[0] == name]:
            del self._split[key]

    def flush(self, tf_choice, force=False):
        data = self.cache.get(tf_choice)
        if not data:
            return
        if (not data.get("dirty")) and (not force):
            return
        self._put(
            f"memories_{tf_choice}.txt",
            "~".join([x for x in data["memory_list"] if str(x).strip() != ""]),
        )
        for name, key in (
            ("memory_weights", "weight_list"),
            ("memory_weights_high", "high_weight_list"),
            ("memory_weights_low", "low_weight_list"),
        ):
            self._put(
                f"{name}_{tf_choice}.txt",
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
        self._put(f"neural_perfect_threshold_{tf_choice}.txt", str(perfect_threshold))
        self.threshold_written[tf_choice] = perfect_threshold

    def read_list(self, name: str, separator: str):
        """The flushed file's cleaned-up text split at ``separator`` (a new list:
        callers change it). FileNotFoundError when there is no such file yet."""
        if name not in self.written:
            with open(self.path(name), "r", encoding="utf-8") as f:
                return _strip(f.read()).split(separator)
        key = (name, separator)
        if key not in self._split:
            self._split[key] = _strip(self.written[name]).split(separator)
        return list(self._split[key])

    def copy_timeframe(self, source_tf: str, target_tf: str) -> None:
        """Give ``target_tf`` everything ``source_tf`` has: its RAM cache, the text of
        its files and its last threshold. (Pass 0 is the same walk over 1-hour bars in
        every timeframe: it is walked once and copied.)"""
        self.cache[target_tf] = {
            k: list(v) if isinstance(v, list) else v
            for k, v in self.cache[source_tf].items()
        }
        for prefix in TIMEFRAME_FILES:
            name = f"{prefix}_{source_tf}.txt"
            if name in self.written:
                self._put(f"{prefix}_{target_tf}.txt", self.written[name])
        if source_tf in self.threshold_written:
            self.threshold_written[target_tf] = self.threshold_written[source_tf]

    def persist(self, tf_choice) -> None:
        """Write ``tf_choice``'s files as the run left them."""
        for prefix in TIMEFRAME_FILES:
            name = f"{prefix}_{tf_choice}.txt"
            if name in self.written:
                _write_text(self.path(name), self.written[name])


# --- training -------------------------------------------------------------------------


def _close_weight_update(predicted_move, realised_move, weight):
    """The close memory's new weight (#150). ``predicted_move`` is the memory's
    close move in percent times its weight (``moves[indy]``), and ``realised_move``
    the close move that followed, in percent: the same units as the high and low
    tests, whose moves are divided by 100 when read and multiplied back before they
    are compared. Upstream's rule, kept: +0.25 when the realised move is above the
    predicted move's 10% band, -0.25 below it, capped at 2.0 and, alone of the
    three tests, allowed to fall to -2.0."""
    if realised_move > predicted_move + (predicted_move * 0.1):
        return min(weight + 0.25, 2.0)
    if realised_move < predicted_move - (predicted_move * 0.1):
        return max(weight - 0.25, 0.0 - 2.0)
    return weight


def run_pass(files, tf_choice, restarted_yet, bars, log, upstream_rows=False):
    """One pass of one timeframe: upstream ``ba62130:pt_trainer.py:503-1625``.

    Each step learns from one bar the move of the bar after it. Every pass walks the
    bars from the 10th to the last (deviation 11); with ``upstream_rows``, as upstream
    did, passes 0-1 stop at the first quarter and pass 2 starts in the middle.

    The steps are upstream's, computed without its per-step copies: upstream rebuilt
    the candle changes of every bar seen so far to use the last one, and re-split
    every memory's text. The same numbers come out (the oracle test compares the
    files); a bar opening at 0, which upstream divided by, still raises.

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
    if upstream_rows:
        if restarted_yet < 2 and n < 10:
            stats["skipped"] = "fewer than 10 bars (upstream would loop for ever)"
            return stats, None
        if restarted_yet == 2 and n < 4:
            stats["skipped"] = "fewer than 4 bars (upstream would loop for ever)"
            return stats, None
    elif n < 10:
        stats["skipped"] = "fewer than 10 bars"
        return stats, None

    # upstream computed every bar's change up to the current one each step, so a bar
    # opening at 0 raised once the walk reached it
    first_zero_open = next((i for i, o in enumerate(open_price_list) if o == 0), None)
    pattern_of = {}  # memory text -> its pattern part, split (upstream re-split it)
    perfect_threshold = 1.0
    loop_i = 0
    if upstream_rows and restarted_yet == 2:
        price_list_length = int(len(price_list) * 0.5)
    else:
        price_list_length = 10
    stats["first_bar"] = price_list_length - 1
    while True:
        loop_i += 1
        # upstream's price_list2: the first price_list_length bars
        seen = price_list_length
        if first_zero_open is not None and seen > first_zero_open:
            raise ZeroDivisionError("float division by zero")
        last = seen - 1
        # the pattern: the last candle's body % (number_of_candles = [2])
        current_pattern = [
            100 * ((price_list[last] - open_price_list[last]) / open_price_list[last])
        ]

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
                text = memory_list[mem_ind]
                memory_pattern = pattern_of.get(text)
                if memory_pattern is None:
                    memory_pattern = _strip(text.split("{}")[0]).split(" ")
                    pattern_of[text] = memory_pattern
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

        # predict the next close, high and low from the matched memories (upstream
        # took the last of the last two closes seen: the current bar's close)
        start_price = price_list[last]
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
        if upstream_rows and seen >= int(len(price_list) * 0.25) and restarted_yet < 2:
            stats["last_bar"] = last
            return stats, perfect_threshold  # next pass (no learning on this step)
        if seen == len(price_list):
            stats["last_bar"] = last
            return stats, perfect_threshold  # timeframe done (no learning on this step)
        if new_y[1] == 0:
            # Upstream divides by the predicted close here (``this_differ``, a statistic
            # the port dropped). A zero (a last close of 0, or a predicted move of
            # exactly -100%) raises inside its learning ``try``, which skips learning
            # for this step: no memory, no weight change, no flush.
            stats["unlearned_steps"] += 1
            continue

        # the bar just revealed
        price2 = price_list[seen]
        high_price2 = high_price_list[seen]
        low_price2 = low_price_list[seen]
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
                new_weight = _close_weight_update(
                    moves[indy], perc_diff_now_actual, move_weights[indy]
                )
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
                f"{price_list_length}/{n}, memories {len(mem['memory_list'])}, "
                f"threshold {perfect_threshold:.3f}"
            )


def passes_for(tf_choice, upstream_rows=False):
    """``[(pass, bars it walks)]`` for one timeframe. Pass 0 walks the 1-hour bars in
    every timeframe (upstream's ``tf_list``); then the timeframe's own bars are
    walked once. The 1-hour timeframe walks its bars once: a second walk over the
    same bars would only replay them against the memories the first just stored
    (deviation 11). ``upstream_rows``: upstream's three passes."""
    if upstream_rows:
        return [(0, "1hour"), (1, tf_choice), (2, tf_choice)]
    if tf_choice == "1hour":
        return [(0, "1hour")]
    return [(0, "1hour"), (1, tf_choice)]


def describe_bars(pair, tf, report):
    """One line per timeframe of the bars a run trains on."""
    missing = report.get("missing_at_start") or 0
    note = f"; the window opens {missing} bar(s) earlier" if missing else ""
    return (
        f"{pair} {tf}: {report['bars']} bars, {report['first_open']} .. "
        f"{report['last_open']}{note}"
    )


SHARED_PASS_0 = "_pass0"  # where the one walk of pass 0 is kept for every timeframe


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
    exchanges=None,
    upstream_rows=False,
):
    """Train every timeframe into ``folder``; return the run summary, with the
    exchange and market its candles came from. Every pass walks every bar of the
    window (deviation 11), unless ``upstream_rows`` (testing only)."""
    random.seed(seed)
    loader = BarLoader(
        coin, train_start, train_end, offline, cache_dir, exchanges=exchanges
    )
    files = ModelFiles(folder)
    summary_tfs = {}
    described = set()
    shared = None  # pass 0's statistics and threshold, once it has been walked
    for tf_choice in TF_CHOICES:
        passes = []
        final_threshold = None
        for restarted_yet, data_tf in passes_for(tf_choice, upstream_rows):
            all_bars = loader.bars(data_tf)
            if data_tf not in described:
                described.add(data_tf)
                tf = CANDLE_TF[data_tf]
                log(describe_bars(loader.pair, tf, loader.reports[tf]))
            if upstream_rows:
                bars = select_rows(all_bars, data_tf, restarted_yet)
                log(
                    f"{tf_choice} pass {restarted_yet}: {data_tf} bars, using the "
                    f"oldest {len(bars[1])} of {len(all_bars[1])}"
                )
            else:
                bars = all_bars
                log(
                    f"{tf_choice} pass {restarted_yet}: {data_tf} bars, all "
                    f"{len(bars[1])}"
                )
            files.load(tf_choice)
            if restarted_yet == 0 and shared is not None:
                # pass 0 starts from no memories on the same bars in every timeframe:
                # the same walk, so it is copied rather than walked again
                files.copy_timeframe(SHARED_PASS_0, tf_choice)
                stats, threshold = dict(shared[0]), shared[1]
            else:
                stats, threshold = run_pass(
                    files, tf_choice, restarted_yet, bars, log, upstream_rows
                )
                if restarted_yet == 0:
                    files.copy_timeframe(tf_choice, SHARED_PASS_0)
                    shared = (dict(stats), threshold)
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
        files.persist(tf_choice)
        if not upstream_flush_only:
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
    return {
        "timeframes": summary_tfs,
        "candles": loader.reports,
        "exchange": loader.exchange,
        "pair": loader.pair,
    }


# --- provenance (FDS-MDL Phase 2) -------------------------------------------------------

VALIDATION_FRACTION = 0.2
VALIDATION_METHOD = (
    "a separate fit on the first 80% of the span the 1-hour bars cover (from train_start, "
    "or the first bar if later, to train_end, or the last bar's close if earlier), scored "
    "frozen on the last 20%; the published model is refit on the whole window"
)
# a validation folder no file of which changed for this long belongs to a stopped run
STALE_VALIDATION_SECONDS = 3600
# the code a model, its validation metrics and its gate decision come from (hashed into
# the manifest)
CODE_FILES = (
    "pt_pattern_trainer.py",
    "pattern_model.py",
    "model_store.py",
    "model_gate.py",
    "entry_gate.py",
)
# A model is published only when it passes the entry gate (deviation 13). Tests that
# are not about the gate switch this off for the session (app/conftest.py), since a
# model trained on their fixture candles has no reason to pass.
ENFORCE_GATE = True
# the gate's bars start this long before the held-out hours, so that every timeframe
# has the bar that closed last before the first held-out hour: a 1-week bar that closed
# just under a week before it opened up to 14 days before it
GATE_LOOKBACK = timedelta(days=15)
# the fee rates the gate uses (entry_gate.trading_fees; tests stand in for it)
gate_fees = None
# The trainer's fixed settings (it has no tunable parameters; FDS-MDL 7: nothing tuned).
TRAINER_PARAMS = {
    "flush_every_steps": FLUSH_EVERY,
    "row_selection": "every bar of the window, in every pass",
    "passes": "pass 0 on the 1-hour bars, then one on the timeframe's own bars (the "
    "1hour timeframe walks its bars once)",
    "pass_0_data": "1hour",
    "number_of_candles": 2,
    "validation_fraction": VALIDATION_FRACTION,
}


def _quiet(*_args, **_kwargs):
    pass


def validation_cut(train_start, train_end):
    """Start of the held-out slice: the last 20% of the window, floored to the hour."""
    cut = train_start + (train_end - train_start) * (1 - VALIDATION_FRACTION)
    cut = cut.replace(minute=0, second=0, microsecond=0)
    if not train_start < cut < train_end:
        raise TrainerError(
            f"the window {_iso(train_start)} .. {_iso(train_end)} is too short to hold "
            "out its last 20%"
        )
    return cut


def validate(
    coin,
    train_start,
    train_end,
    seed,
    offline,
    cache_dir=None,
    log=print,
    exchanges=None,
    fit=None,
):
    """FDS-MDL Phase 2 validation metrics: a separate fit on the first 80% of
    ``[train_start, train_end)``, scored, frozen, on the last 20%. The published model is
    the whole-window fit (owner decision, 2026-10-06), so the metrics describe this
    sibling fit, which never saw the held-out bars. Raises TrainerError when the fit
    cannot be trained. ``fit``, a dict, receives the fit itself (validation_fit's
    sibling: the entry gate replays its entries)."""
    window, metrics, sibling = validation_fit(
        coin, train_start, train_end, seed, offline, cache_dir, log, exchanges
    )
    if fit is not None:
        fit.update(sibling)
    return window, metrics


def validation_fit(
    coin,
    train_start,
    train_end,
    seed,
    offline,
    cache_dir=None,
    log=print,
    exchanges=None,
):
    """``validate``, and the fit itself: ``(window, metrics, sibling)``, where sibling
    holds the fitted ``model``, its window (``start``, ``cut``, ``end``), its
    ``exchange`` and its ``files``' SHA-256 (the entry gate replays its entries)."""
    from market_data.timeframes import candle_timeframe_seconds
    from pattern_model import PatternModel, model_file_names, score_timeframe

    cut = validation_cut(train_start, train_end)
    log(
        f"validation: fitting {_iso(train_start)} .. {_iso(cut)}, "
        f"scoring .. {_iso(train_end)}"
    )
    # a fresh folder per run under <cache>/pt-validation-<COIN>; a run the hub stopped
    # (terminated, so no clean-up) leaves its folder, cleared here once it is stale. The
    # parent stays (removing it could pull it from under another run of this coin).
    parent = os.path.join(pt_paths.cache_dir(), f"pt-validation-{coin}")
    os.makedirs(parent, exist_ok=True)
    _clear_stale(parent)
    work = tempfile.mkdtemp(dir=parent)
    try:
        fit = train(
            coin,
            work,
            train_start,
            cut,
            seed=seed,
            offline=offline,
            cache_dir=cache_dir,
            log=_quiet,
            exchanges=exchanges,
        )
        model = PatternModel.from_folder(work)
        fit_files = {n: _file_sha256(os.path.join(work, n)) for n in model_file_names()}
    finally:
        shutil.rmtree(work, ignore_errors=True)
    # the held-out bars come from the same exchange as the fit's
    holdout = BarLoader(
        coin, cut, train_end, offline, cache_dir, exchanges=[fit["exchange"]]
    )
    metrics = {}
    for tf_choice in TF_CHOICES:
        tf = CANDLE_TF[tf_choice]
        try:
            holdout.bars(tf_choice)
        except TrainerError as exc:
            metrics[tf_choice] = {"scored_pairs": 0, "error": str(exc)}
            continue
        metrics[tf_choice] = score_timeframe(
            model.timeframes[tf_choice],
            holdout.frames[tf],
            candle_timeframe_seconds(tf),
        )
    scored = any(m.get("scored_pairs") for m in metrics.values())
    window = {
        "status": "ok" if scored else "unavailable",
        **({} if scored else {"reason": "no held-out bar pair could be scored"}),
        "method": VALIDATION_METHOD,
        "fraction": VALIDATION_FRACTION,
        "fit_start": _iso(train_start),
        "fit_end": _iso(cut),
        "fit_candles": fit["candles"],
        "fit_files_sha256": fit_files,
        "holdout_start": _iso(cut),
        "holdout_end": _iso(train_end),
        "holdout_candles": holdout.reports,
    }
    sibling = {
        "model": model,
        "start": train_start,
        "cut": cut,
        "end": train_end,
        "exchange": fit["exchange"],
        "files": fit_files,
    }
    return window, metrics, sibling


def _clear_stale(parent, now=None):
    """Remove what in ``parent`` nothing changed in for STALE_VALIDATION_SECONDS: the
    folders of stopped runs (a live fit rewrites its files many times a second) and any
    loose files."""
    now = time.time() if now is None else now
    for name in os.listdir(parent):
        path = os.path.join(parent, name)
        try:
            newest = os.path.getmtime(path)
            for root, _dirs, files in os.walk(path):
                for f in files:
                    newest = max(newest, os.path.getmtime(os.path.join(root, f)))
        except OSError:  # removed meanwhile by its own run
            continue
        if now - newest <= STALE_VALIDATION_SECONDS:
            continue
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                pass


def _git(*args):
    """A local git command in the program folder (no network, and no optional index
    lock, so it never gets in the way of the user's own git): its output, or None."""
    try:
        out = subprocess.run(
            ["git", "--no-optional-locks", "-C", current_dir, *args],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def _own_checkout():
    """Whether the install folder is the top of the git checkout git finds (not, say, a
    copy of the program inside some other repository)."""
    top = (_git("rev-parse", "--show-toplevel") or "").strip()
    if not top:
        return False
    return os.path.normcase(os.path.realpath(top)) == os.path.normcase(
        os.path.realpath(pt_paths.install_dir())
    )


def _git_commit():
    """The program's git commit, when the install folder is a checkout (else None)."""
    if not _own_checkout():
        return None
    commit = (_git("rev-parse", "HEAD") or "").strip()
    return commit if len(commit) == 40 else None


def _git_dirty():
    """Whether CODE_FILES differ from that commit (None outside the program's own
    checkout)."""
    if not _own_checkout():
        return None
    out = _git("status", "--porcelain", "--", *CODE_FILES)
    return None if out is None else bool(out.strip())


def _file_sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _text_sha256(path):
    """SHA-256 of a text file with LF line endings: the same for a Windows (CRLF) and a
    POSIX checkout of one commit, and equal to the SHA-256 of what git stores."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


# --- the entry gate (deviation 13) ------------------------------------------------------

GATE_FILE = "model_gate.json"  # the coin folder's latest gate decision


def _empty_frame():
    import pandas as pd

    return pd.DataFrame(
        {
            "open_time": pd.Series([], dtype="datetime64[ns, UTC]"),
            "open": pd.Series([], dtype=float),
            "close": pd.Series([], dtype=float),
        }
    )


def gate_per_day(manifest):
    """A published model's own return per day held after fees on its held-out bars,
    from its manifest's gate record (None: none recorded, e.g. published before the
    gate, or judged by an earlier gate that scored the mean return per trade)."""
    gate = (manifest or {}).get("gate") or {}
    value = (gate.get("candidate") or {}).get("per_day")
    return float(value) if isinstance(value, (int, float)) else None


def check_gate(
    coin, sibling, offline, cache_dir=None, log=print, current=None, checking=False
):
    """The entry gate's decision on the validation fit ``sibling`` (validation_fit's;
    None when there was none), against ``current`` (the coin's current manifest).
    ``checking``: the fit is the model in use's own (``--check-gate``)."""
    import entry_gate
    import model_gate
    import training_settings

    settings = entry_gate.GateSettings.from_training(
        training_settings.read_training_settings()
    )
    rules = model_gate.read_trade_rules()
    current_score = None if checking else gate_per_day(current)
    notes = []
    if checking:
        notes.append("a check of the model in use (it is not compared with itself)")
        if current is not None and gate_per_day(current) is None:
            notes.append(
                no_per_day_note(current)
                + f": the next {coin} model trained is not compared with it"
            )
    elif current is None:
        notes.append("no current model, so it is not compared with one")
    elif current_score is None:
        notes.append(no_per_day_note(current) + ", so it is not compared with it")
    fees = (gate_fees or entry_gate.trading_fees)(coin)
    if sibling is None:
        notes.append("no validation fit: there are no held-out bars to judge it on")
        decision = entry_gate.decide(
            [],
            {},
            {},
            settings,
            fees,
            current=current_score,
            note="; ".join(notes),
            measure=entry_gate.PER_DAY,
        )
        return model_gate.ModelGateResult(decision, 0, 0, 0, rules)
    start = max(sibling["start"], sibling["cut"] - GATE_LOOKBACK)
    loader = BarLoader(
        coin, start, sibling["end"], offline, cache_dir, exchanges=[sibling["exchange"]]
    )
    frames = {}
    for tf_choice in TF_CHOICES:
        tf = CANDLE_TF[tf_choice]
        try:
            loader.bars(tf_choice)
            frames[tf] = loader.frames[tf]
        except TrainerError as exc:
            log(f"entry gate: no {tf} bars ({exc}); hours that need them are undecided")
            frames[tf] = _empty_frame()
    hours = model_gate.hourly_signals(
        sibling["model"],
        frames,
        int(sibling["cut"].timestamp()),
        int(sibling["end"].timestamp()),
    )
    return model_gate.evaluate(
        hours, rules, fees, settings, coin, current_score, note="; ".join(notes)
    )


def no_per_day_note(manifest):
    """Why the model in use is not compared with (rule f): it has no recorded return
    per day held."""
    gate = (manifest or {}).get("gate")
    why = (
        "it was published before the entry gate"
        if not gate
        else "an earlier version of the entry gate recorded its mean return per trade"
    )
    return (
        f"the model in use {manifest.get('model_id')} has no recorded return per day "
        f"held ({why})"
    )


def current_model(coin):
    """The coin's current model: its newest published one (manifest), or None."""
    import model_store

    try:
        return model_store.latest_published(coin)
    except model_store.ModelStoreError:
        return None


def _write_gate_file(folder, coin, gate, published_id, kept_id):
    record = {
        "coin": coin,
        "checked_at": int(time.time()),
        "published": published_id is not None,
        "model_id": published_id,
        "kept_model_id": kept_id,
        "gate": gate.to_dict(),
    }
    _write_text(os.path.join(folder, GATE_FILE), json.dumps(record, indent=2))
    return record


def provenance(coin, folder, cfg, result, log=print):
    """Publish the model just written to ``folder`` into the model store, with its
    manifest (FDS-MDL Phase 2), when it passes the entry gate. Returns ``(model_id,
    gate)``: model_id is None when it was not published (the gate's ``decision`` says
    why)."""
    import model_store
    from pattern_model import METRIC_DEFINITIONS, model_file_names

    start, end = cfg["train_start"], cfg["train_end"]
    # a pair listed after train_start, or whose bars stop before train_end: split the
    # span its 1-hour bars cover, not the window
    hourly = result["candles"]["1h"]
    first_bar = _parse_time(hourly["first_open"], "first_open")
    last_close = _parse_time(hourly["last_open"], "last_open") + timedelta(hours=1)
    data_start, data_end = max(start, first_bar), min(end, last_close)
    fit = {}
    try:
        validation, metrics = validate(
            coin,
            data_start,
            data_end,
            cfg["seed"],
            cfg["offline"],
            log=log,
            exchanges=[result["exchange"]],
            fit=fit,
        )
    except TrainerError as exc:
        # too little data before the cut for a fit: published without metrics, and
        # recorded as such (a consumer that needs metrics refuses the model)
        log(f"WARNING: no validation metrics for {coin}: {exc}")
        validation = {
            "status": "unavailable",
            "reason": str(exc),
            "method": VALIDATION_METHOD,
            "fraction": VALIDATION_FRACTION,
        }
        metrics = {
            tf: {"scored_pairs": 0, "error": f"no validation fit: {exc}"}
            for tf in TF_CHOICES
        }
    files = {n: _file_sha256(os.path.join(folder, n)) for n in model_file_names()}
    code = {n: _text_sha256(os.path.join(current_dir, n)) for n in CODE_FILES}
    candle_hashes = {tf: r["sha256"] for tf, r in result["candles"].items()}
    # everything the manifest records about the run except when and from which commit:
    # the same run gives the same id (and reuses the folder), any difference a new one
    identity = {
        "coin": coin,
        "window": [_iso(start), _iso(end)],
        "seed": cfg["seed"],
        "files": files,
        "candle_file_sha256": candle_hashes,
        "code_sha256": code,
        "params": TRAINER_PARAMS,
        "exchange": result["exchange"],
        "pair": result["pair"],
    }
    model_id = model_store.content_id(f"{coin}-{end:%Y%m%dT%H%MZ}", identity)
    trainer_file = os.path.abspath(__file__)
    manifest = {
        "manifest_version": model_store.MANIFEST_VERSION,
        "model_id": model_id,
        "kind": "pattern memories (pt_pattern_trainer.py)",
        "trainer_path": os.path.relpath(trainer_file, pt_paths.install_dir()).replace(
            os.sep, "/"
        ),
        "trainer_sha256": code["pt_pattern_trainer.py"],
        "code_sha256": code,
        "trainer_git_commit": _git_commit(),
        "trainer_git_dirty": _git_dirty(),
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream": {"repo": UPSTREAM_REPO, "blob": UPSTREAM_BLOB},
        # the market and exchange the candles came from (FDS-MX-001 phase F)
        "symbol": result["pair"],
        "exchange": result["exchange"],
        "coin": coin,
        "timeframes": list(TF_CHOICES),
        "candle_timeframes": dict(CANDLE_TF),
        "train_start": _iso(start),
        "train_end": _iso(end),
        "candle_file_sha256": candle_hashes,
        "candles": result["candles"],
        "params": TRAINER_PARAMS,
        "seed": cfg["seed"],
        "created_at": _iso(datetime.now(timezone.utc)),
        "validation": validation,
        "validation_metrics": metrics,
        "metric_definitions": METRIC_DEFINITIONS,
        "training": result["timeframes"],
        "files": files,
    }
    gate = check_gate(
        coin, fit or None, cfg["offline"], log=log, current=current_model(coin)
    )
    for line in gate.lines():
        log(f"entry gate for {coin}: {line}")
    manifest["gate"] = gate.to_dict()
    if not gate.decision.passed and ENFORCE_GATE:
        log(f"model not published: {coin}'s new model did not pass the entry gate")
        return None, gate
    model_store.publish(folder, manifest, trainer_root=None)
    log(f"model published: {model_id}")
    return model_id, gate


def keep_current_model(coin, folder, log=print):
    """After a model that did not pass: put the coin's current model's files back in
    ``folder`` (the hub deleted them before training). Returns its model_id, or None
    when the coin has no published model (the new files stay, unpublished, and the
    neural runner gives the coin no signals)."""
    import model_store

    current = current_model(coin)
    if current is None:
        log(
            f"{coin} has no published model: the new one is kept unpublished, and the "
            "neural runner gives it no signals until a model passes the gate"
        )
        return None
    model_store.restore(current["model_id"], folder)
    log(
        f"{coin}'s current model {current['model_id']} (trained to "
        f"{current.get('train_end')}) is put back and stays in use"
    )
    return current["model_id"]


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
    """trainer_status.json. ``TRAINING`` also records this process, so a reader can
    tell a trainer that was killed from one that still runs (trainer_status, #145)."""
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
    print(f"window: {cfg['window']} ({cfg['sources']['window']})")
    print(f"seed: {cfg['seed']} ({cfg['sources']['seed']})")
    print(f"offline: {cfg['offline']} ({cfg['sources']['offline']})")
    if cfg.get("check_gate"):
        return check_current_model(coin, cfg["offline"])
    existing = _existing_model_files(folder)
    if existing:
        print(
            f"ERROR: the working folder already holds model files ({', '.join(existing[:5])}"
            f"{', ...' if len(existing) > 5 else ''}); the trainer only starts from an "
            "empty folder"
        )
        return 2
    started_at = int(started)
    _write_status(folder, coin, "TRAINING", started_at, **trainer_status.this_process())
    try:
        result = train(
            coin,
            folder,
            cfg["train_start"],
            cfg["train_end"],
            seed=cfg["seed"],
            offline=cfg["offline"],
            upstream_flush_only=cfg["upstream_flush_only"],
            exchanges=cfg.get("exchanges"),
            upstream_rows=cfg.get("upstream_rows", False),
        )
        gate_record = None
        if cfg["upstream_flush_only"] or cfg.get("upstream_rows"):
            # test mode: the incomplete upstream files are not published
            model_id = None
        else:
            model_id, gate = provenance(coin, folder, cfg, result)
            kept_id = None if model_id else keep_current_model(coin, folder)
            if gate is not None:
                gate_record = _write_gate_file(folder, coin, gate, model_id, kept_id)
    except MarketClosedError as exc:
        # Not a crash: say why. A confirmed closure is recorded, so the
        # trader makes no buys in the coin; an unconfirmed one is only refused.
        if exc.confirmed:
            from market_data.listing import write_market_status

            write_market_status(folder, exc.pair, False, exc.reason)
        print(f"ERROR: training refused for {coin}: {exc}")
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
        "window": cfg["window"],
        "seed": cfg["seed"],
        "offline": cfg["offline"],
        "sources": cfg["sources"],
        "started_at": started_at,
        "finished_at": finished_at,
        "runtime_seconds": round(time.time() - started, 1),
        "model_id": model_id,
        **result,
    }
    if gate_record is not None:
        summary["gate"] = gate_record["gate"]
        summary["kept_model_id"] = gate_record["kept_model_id"]
    _write_text(
        pt_paths.data_file("training_results", f"{coin.lower()}_training_results.json"),
        json.dumps(summary, indent=2),
    )
    _write_status(folder, coin, "FINISHED", started_at, finished_at=finished_at)
    if (
        not cfg["offline"]
        and abs(datetime.now(timezone.utc) - cfg["train_end"]) <= LIVE_WINDOW
    ):
        # a live run's bars reached train_end: the market trades (this clears a
        # "not trading" record from an earlier refused run)
        from market_data.listing import write_market_status

        write_market_status(
            folder,
            f"{coin}-USD",
            True,
            "training bars reach train_end",
            result.get("exchange") or "",
        )
    _write_text(os.path.join(folder, "trainer_last_start_time.txt"), str(started_at))
    # last, so a coin only counts as trained once every file is in place
    _write_text(
        os.path.join(folder, "trainer_last_training_time.txt"), str(finished_at)
    )
    print(f"Training completed for {coin} in {summary['runtime_seconds']} s")
    if gate_record is not None and not gate_record["published"]:
        kept = gate_record["kept_model_id"]
        print(
            f"The new model was not published: it did not pass the entry gate. "
            + (
                f"The current model {kept} stays in use."
                if kept
                else f"{coin} has no model in use until one passes."
            )
        )
    return 0


def check_current_model(coin, offline, log=print):
    """``--check-gate``: the entry gate on the coin's current model. Its validation fit
    is trained again from its manifest (window, seed, exchange) in a scratch folder and
    replayed on its own held-out bars; nothing in the coin's folder or the model store
    changes. The result is printed and written to
    ``<data>/training_results/<coin>_gate_check.json``. Exit code 0 when the check ran
    (passed or not), 1 when it could not."""
    manifest = current_model(coin)
    if manifest is None:
        print(f"ERROR: {coin} has no published model to check")
        return 1
    model_id = manifest["model_id"]
    validation = manifest.get("validation") or {}
    record = {"coin": coin, "model_id": model_id, "checked_at": int(time.time())}
    try:
        if validation.get("status") != "ok":
            raise TrainerError(
                f"its manifest records no validation fit ({validation.get('reason')})"
            )
        fit_start = _parse_time(validation["fit_start"], "fit_start")
        holdout_end = _parse_time(validation["holdout_end"], "holdout_end")
        log(
            f"checking {coin}'s current model {model_id}: refitting its validation fit "
            f"{validation['fit_start']} .. {validation['fit_end']}"
        )
        _window, _metrics, sibling = validation_fit(
            coin,
            fit_start,
            holdout_end,
            int(manifest.get("seed", 0)),
            offline,
            log=log,
            exchanges=[manifest.get("exchange")] if manifest.get("exchange") else None,
        )
        recorded = validation.get("fit_files_sha256")
        same = recorded == sibling["files"] if recorded else None
        record["refit_matches_record"] = same
        if same is False:
            log(
                "WARNING: the refitted validation fit's files differ from the ones its "
                "manifest records (the code or the candles changed since)"
            )
        gate = check_gate(
            coin, sibling, offline, log=log, current=manifest, checking=True
        )
    except (TrainerError, OSError, KeyError, ValueError) as exc:
        print(f"ERROR: the entry gate could not be run on {coin}'s model: {exc}")
        record["error"] = str(exc)
        _write_text(
            pt_paths.data_file("training_results", f"{coin.lower()}_gate_check.json"),
            json.dumps(record, indent=2),
        )
        return 1
    for line in gate.lines():
        print(f"entry gate for {coin} ({model_id}): {line}")
    record["gate"] = gate.to_dict()
    _write_text(
        pt_paths.data_file("training_results", f"{coin.lower()}_gate_check.json"),
        json.dumps(record, indent=2),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
