"""
FDS-MDL Phase 4: the STRAT-003 backtest declared in docs/dev/BACKTEST-REPORT-model-1.md.

    python docs/dev/run_backtest_model1.py fetch    # candles, public Binance klines (network)
    python docs/dev/run_backtest_model1.py train    # the 20 models, offline from the cache
    python docs/dev/run_backtest_model1.py run      # Test A, the random baselines, Test B
    python docs/dev/run_backtest_model1.py report   # append the results under the header

Every command needs ``POWERTRADER_HOME`` set to one scratch folder outside the repo (and
outside every worktree of it), reused across the session, so the candle cache, the
trainer's working folders and the model store never touch the real per-user folders
(FDS-MDL-A section 4.3). In PowerShell:

    $env:POWERTRADER_HOME = 'C:\\scratch\\model1-home'
    python docs/dev/run_backtest_model1.py fetch

The script prints the folders it resolved before doing anything. ``fetch`` is the only
step that uses the network. Outputs go to ``docs/dev/backtest-model-1/``; ``report``
appends to ``docs/dev/BACKTEST-REPORT-model-1.md`` and never changes the header above its
"Results go below this line." marker. Nothing about the plan can be changed from the
command line.

The code rule (the header's "Code" section): every command refuses to run from frozen
files (``app/``, this script) that differ from the commit, and records that commit in
every JSON it writes. ``train`` and ``run`` refuse to replace earlier outputs unless
given ``--supersede "<what changed and why>"``: the earlier outputs then move to
``superseded/`` with that note, and ``report`` shows them and their verdict beside the
final ones. ``run`` refuses models whose code (``code_sha256``) is not the current
code's, so a change to the trainer, ``pattern_model.py`` or ``model_store.py`` means all
20 trainings again.

Everything in ``PLAN`` is the header's, declared before any result was seen. Phase 1
measured the trainer's runtime with this script's earlier defaults (2023-01-01 to
2026-01-01, one window per symbol; see commit 03f489e).
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(REPO, "app")
sys.path.insert(0, APP)

OUT = os.path.join(REPO, "docs", "dev", "backtest-model-1")
REPORT = os.path.join(REPO, "docs", "dev", "BACKTEST-REPORT-model-1.md")
REPORT_REL = "docs/dev/BACKTEST-REPORT-model-1.md"
FIRST_HEADER_COMMIT = "51e499e"
BATCH1 = os.path.join(REPO, "docs", "dev", "backtest-batch-1")
MARKER = "*Results go below this line.*"
TRAINER = os.path.join(APP, "pt_pattern_trainer.py")
FROZEN = ("app", "docs/dev/run_backtest_model1.py")
MODEL_CODE = ("pt_pattern_trainer.py", "pattern_model.py", "model_store.py")
# the code the trainer reads its bars through (a change there means training again)
TRAINER_DATA_CODE = ("market_data/candles.py", "market_data/timeframes.py")
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


@dataclass(frozen=True)
class Plan:
    """The declared settings (the header's), or a miniature of them in tests."""

    pairs: Tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    primary: Tuple[str, ...] = ("1h", "4h")
    model_tfs: Tuple[str, ...] = ("1h", "2h", "4h", "8h", "12h", "1d", "1w")
    start: str = "2023-01-01"
    end: str = "2026-10-01"  # exclusive: the last 1h bar opens 2026-09-30 23:00
    batch1_sha256: Mapping[str, str] = field(
        default_factory=lambda: {
            "BTCUSDT 1h": "7171bc667f3db6032a721770c6128545b2bc3f089432e8861181034493171893",
            "BTCUSDT 4h": "f58fee86fa7e7c6aa69096b75ddeb3156a592c9f55059383da7d95506266836f",
            "ETHUSDT 1h": "2bd3369c64bc6ce400ba5d91519c68524ae0cc4a41d8f139ad46eb256e3d4eb8",
            "ETHUSDT 4h": "11c6946a168f25bb96d2f6b6415db9990c3a53b70c1585864cd3ab8f5dce8722",
        }
    )
    # batch 1's records: bars per file, and the out-of-sample split (70% of the bars)
    candles: Mapping[str, int] = field(
        default_factory=lambda: {"1h": 32855, "4h": 8214}
    )
    in_sample_fraction: float = 0.7
    oos_start: Mapping[str, str] = field(
        default_factory=lambda: {
            "1h": "2025-08-16T07:00:00+00:00",
            "4h": "2025-08-16T04:00:00+00:00",
        }
    )
    oos_bars: Mapping[str, int] = field(
        default_factory=lambda: {"1h": 9857, "4h": 2465}
    )
    train_start: str = "2023-01-01T00:00:00Z"
    test_a_train_end: str = "2025-08-16T04:00:00Z"
    test_a_holdout: Tuple[str, str] = ("2025-02-05T12:00:00Z", "2025-08-16T04:00:00Z")
    test_b_ends: Tuple[str, ...] = (
        "2024-07-01T00:00:00Z",
        "2024-10-01T00:00:00Z",
        "2025-01-01T00:00:00Z",
        "2025-04-01T00:00:00Z",
        "2025-07-01T00:00:00Z",
        "2025-10-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
        "2026-04-01T00:00:00Z",
        "2026-07-01T00:00:00Z",
    )
    test_b_months: int = 3
    overlay_sets: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
        ("none", ()),
        ("OVL-ATR+OVL-COOLDOWN", ("OVL-ATR", "OVL-COOLDOWN")),
    )
    # one range per combination; a combination's two overlay sets share it (owner
    # decision, 2026-10-07: a departure from FDS-MDL section 7's "seeds 0 to 99")
    seed_ranges: Mapping[str, Tuple[int, int]] = field(
        default_factory=lambda: {
            "BTCUSDT 1h": (0, 100),
            "BTCUSDT 4h": (100, 200),
            "ETHUSDT 1h": (200, 300),
            "ETHUSDT 4h": (300, 400),
        }
    )
    seeds_per_run: int = 100
    trainer_seed: int = 0
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    size_fraction: float = 1.0
    initial_equity: float = 10_000.0

    @property
    def coins(self) -> Tuple[str, ...]:
        return tuple(p[:-4] if p.endswith("USDT") else p for p in self.pairs)

    def seeds(self, pair: str, tf: str) -> range:
        lo, hi = self.seed_ranges[f"{pair} {tf}"]
        return range(lo, hi)

    def trainings(self) -> List[Dict[str, str]]:
        """The training windows (Test A, then each Test B end), per coin."""
        out = []
        for coin in self.coins:
            out.append(
                {
                    "test": "A",
                    "coin": coin,
                    "train_start": self.train_start,
                    "train_end": self.test_a_train_end,
                }
            )
            for end in self.test_b_ends:
                out.append(
                    {
                        "test": "B",
                        "coin": coin,
                        "train_start": self.train_start,
                        "train_end": end,
                    }
                )
        return out

    def expected_test_b_windows(self) -> int:
        return len(self.pairs) * len(self.primary) * len(self.test_b_ends)


PLAN = Plan()


class Stop(RuntimeError):
    """Nothing is scored: a data, set-up or code check failed (the report records why)."""


# --- small helpers --------------------------------------------------------------------------


def _key(pair: str, tf: str) -> str:
    return f"{pair} {tf}"


def _ts(value):
    import pandas as pd

    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)
        f.write("\n")


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _git(*args: str) -> str:
    """Local git only (no network, no credentials)."""
    return subprocess.run(
        ["git", "--no-optional-locks", "-C", REPO, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


def code_state() -> Dict[str, Any]:
    """The commit the outputs come from, the frozen files that differ from it (untracked
    ones included; ignored ones such as __pycache__ not), the Python, POWERTRADER_HOME.
    """
    return {
        "commit": _git("rev-parse", "HEAD").strip(),
        "frozen_files_changed": _git(
            "status", "--porcelain", "--", *FROZEN
        ).splitlines(),
        "python": sys.version,
        "powertrader_home": os.environ.get("POWERTRADER_HOME"),
    }


def _state(state: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """``state`` (tests) or the repository's; refuses frozen files that differ from the
    commit: everything that produces results is committed first."""
    s = dict(state) if state is not None else code_state()
    if s["frozen_files_changed"]:
        raise Stop(
            "frozen files differ from the commit (commit them before any step): "
            f"{s['frozen_files_changed']}"
        )
    return s


def _text_sha256(path: str) -> str:
    """As the trainer hashes its code (LF line endings)."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()


def model_code_hashes() -> Dict[str, str]:
    return {name: _text_sha256(os.path.join(APP, name)) for name in MODEL_CODE}


def _inside(path: str, folder: str) -> bool:
    path, folder = _real(path), _real(folder)
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:  # another drive: outside
        return False


def _worktrees() -> List[str]:
    out = [REPO]
    try:
        for line in _git("worktree", "list", "--porcelain").splitlines():
            if line.startswith("worktree "):
                out.append(line[len("worktree ") :].strip())
    except (OSError, subprocess.CalledProcessError):
        pass
    return out


def sandbox() -> dict:
    """POWERTRADER_HOME must be set, absolute, outside the repo and every worktree of it
    (after resolving ``~`` and links, as the trainer children will), and clear of the
    real per-user folders; prints the folders this run uses."""
    raw = os.environ.get("POWERTRADER_HOME", "").strip()
    if not raw:
        sys.exit(
            "POWERTRADER_HOME is not set: this run would use the real per-user folders.\n"
            "Set it to a scratch folder outside the repo, e.g. in PowerShell:\n"
            "    $env:POWERTRADER_HOME = 'C:\\scratch\\model1-home'"
        )
    if not os.path.isabs(os.path.expanduser(raw)):
        sys.exit(
            f"POWERTRADER_HOME {raw} is not an absolute path: each trainer runs in its own "
            "folder and would resolve it elsewhere"
        )
    for tree in _worktrees():
        if _inside(raw, tree):
            sys.exit(
                f"POWERTRADER_HOME {raw} is inside {tree}; use a folder outside it"
            )

    import pt_paths

    home = os.path.expanduser(raw)  # as pt_paths reads it
    for kind in ("config", "data", "log", "cache"):
        try:
            real = pt_paths._platform_dir(kind)
        except pt_paths.MissingDependency:
            continue  # nothing can resolve to the real folders without platformdirs
        if pt_paths.paths_overlap(home, real):
            sys.exit(
                f"POWERTRADER_HOME {raw} overlaps the real per-user {kind} folder {real}; "
                "use a scratch folder"
            )

    from market_data.candles import cache_dir_default

    folders = {
        "POWERTRADER_HOME": raw,
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


def supersede(
    out_dir: str,
    names: Sequence[str],
    note: Optional[str],
    state: Mapping[str, Any],
    step: str,
) -> None:
    """The code rule: earlier outputs are never overwritten. With a note (what changed
    and why) they move to ``superseded/<n>-<step>-<their commit>/``; without one, Stop.
    A run that stopped before scoring anything (only its ``results.json``) is moved
    aside without a note. The note is written first and every move is a rename, undone
    if one fails, so a folder is never left half moved."""
    present = [n for n in names if os.path.exists(os.path.join(out_dir, n))]
    if not present:
        return
    if not (note and note.strip()):
        if not _unscored(out_dir, present):
            raise Stop(
                f"{step}: earlier outputs exist ({present}); a re-run after a result has "
                'been seen needs --supersede "<what changed and why>" (the earlier '
                "outputs are kept and reported beside the new ones)"
            )
        note = f"{step}: replaced a run that stopped before scoring anything"
    earlier = None
    for n in ("results.json", "train.json"):
        path = os.path.join(out_dir, n)
        if n in present and os.path.isfile(path):
            earlier = ((_read_json(path).get("code") or {}).get("commit") or "")[:7]
            break
    if earlier is None:
        commits = _run_file_commits(out_dir)
        earlier = commits[0][:7] if commits else None
    root = os.path.join(out_dir, "superseded")
    os.makedirs(root, exist_ok=True)
    dest = os.path.join(
        root, f"{len(os.listdir(root)) + 1:02d}-{step}-{earlier or 'unknown'}"
    )
    os.makedirs(dest)
    _write_json(
        os.path.join(dest, "note.json"),
        {
            "step": step,
            "note": note.strip(),
            "moved": present,
            "superseded_by": dict(state),
        },
    )
    done = []
    try:
        for n in present:
            os.rename(os.path.join(out_dir, n), os.path.join(dest, n))
            done.append(n)
    except OSError as exc:
        for n in reversed(done):
            os.rename(os.path.join(dest, n), os.path.join(out_dir, n))
        shutil.rmtree(dest, ignore_errors=True)
        raise Stop(f"could not move the earlier outputs aside ({exc}); nothing moved")


# --- fetch ------------------------------------------------------------------------------------


def _file_record(pair: str, tf: str, cache_dir: Optional[str]) -> Dict[str, Any]:
    from market_data.candles import cache_path, file_sha256, load_candles_csv

    path = cache_path(pair, tf, cache_dir)
    frame = load_candles_csv(path, tf)
    return {
        "path": path,
        "sha256": file_sha256(path),
        "bars": len(frame),
        "first": frame["open_time"].iloc[0].isoformat() if len(frame) else None,
        "last": frame["open_time"].iloc[-1].isoformat() if len(frame) else None,
        "missing_bars": frame.attrs["report"].missing_bars,
    }


def batch1_mismatches(plan: Plan, files: Mapping[str, Mapping[str, Any]]) -> List[dict]:
    """The 1h and 4h files must hash to batch 1's values."""
    out = []
    for key, expected in plan.batch1_sha256.items():
        got = (files.get(key) or {}).get("sha256")
        if got != expected:
            out.append({"file": key, "expected": expected, "got": got})
    return out


def fetch(
    plan: Plan,
    out_dir: str = OUT,
    cache_dir: Optional[str] = None,
    fetcher_factory: Optional[Callable] = None,
    state: Optional[Mapping[str, Any]] = None,
) -> int:
    """Fill an empty candle cache with the closed bars of the window, record every
    file's SHA-256 in ``data.json`` and check the 1h and 4h files against batch 1's."""
    import pandas as pd

    from market_data import candles
    from market_data.timeframes import bar_open_floor

    s = _state(state)
    targets = [(p, tf) for p in plan.pairs for tf in plan.model_tfs]
    present = [candles.cache_path(p, tf, cache_dir) for p, tf in targets]
    present = [path for path in present if os.path.exists(path)]
    if present:
        raise Stop(
            "the candle cache must be empty when fetch starts (so each file holds "
            f"exactly the window); found {present}. Use a fresh POWERTRADER_HOME."
        )
    make = fetcher_factory or candles.BinanceKlines
    end_ts = min(_ts(plan.end), pd.Timestamp.now(tz="UTC"))
    for pair, tf in targets:
        # bars that close by the end of the window
        end_open = pd.Timestamp(
            bar_open_floor(int(end_ts.timestamp()), tf), unit="s", tz="UTC"
        )
        candles.get_candles(
            pair, tf, plan.start, end_open, cache_dir=cache_dir, fetcher=make()
        )
    files = {_key(p, tf): _file_record(p, tf, cache_dir) for p, tf in targets}
    for key, rec in files.items():
        print(
            f"{key}: {rec['bars']} bars {rec['first']} -> {rec['last']} "
            f"missing={rec['missing_bars']} sha256={rec['sha256']}",
            flush=True,
        )
    mismatches = batch1_mismatches(plan, files)
    _write_json(
        os.path.join(out_dir, "data.json"),
        {
            "code": s,
            "window": [plan.start, plan.end],
            "files": files,
            "batch1_mismatches": mismatches,
        },
    )
    if mismatches:
        print(f"STOP: not batch 1's candles: {mismatches}", flush=True)
        return 1
    return 0


def check_data(
    plan: Plan, out_dir: str = OUT, cache_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Every cache file must still have the hash ``fetch`` recorded, and the 1h and 4h
    ones batch 1's; otherwise ``Stop``."""
    from market_data.candles import cache_path, file_sha256

    path = os.path.join(out_dir, "data.json")
    if not os.path.isfile(path):
        raise Stop("no data.json: run fetch first")
    data = _read_json(path)
    if data.get("batch1_mismatches") or batch1_mismatches(plan, data["files"]):
        raise Stop(f"not batch 1's candles: {batch1_mismatches(plan, data['files'])}")
    changed = []
    for pair in plan.pairs:
        for tf in plan.model_tfs:
            rec = data["files"].get(_key(pair, tf))
            file = cache_path(pair, tf, cache_dir)
            got = file_sha256(file) if os.path.isfile(file) else None
            if rec is None or got != rec["sha256"]:
                changed.append(
                    {
                        "file": _key(pair, tf),
                        "recorded": rec and rec["sha256"],
                        "now": got,
                    }
                )
    if changed:
        raise Stop(f"candle files changed since fetch: {changed}")
    return data


# --- train ------------------------------------------------------------------------------------


def published_model_id(coin: str) -> Optional[str]:
    """The model_id in the trainer's summary for ``coin`` (None if it has none)."""
    import pt_paths

    path = os.path.join(
        pt_paths.data_dir(), "training_results", f"{coin.lower()}_training_results.json"
    )
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("model_id")
    except (OSError, ValueError):
        return None


def manifest_summary(model_id: str) -> Dict[str, Any]:
    """What the run and the report need from a published model's manifest (verified on
    load), and the manifest itself."""
    import model_store

    m = model_store.load(model_id).manifest
    return {
        "model_id": model_id,
        "symbol": m["symbol"],
        "coin": m["coin"],
        "train_start": m["train_start"],
        "train_end": m["train_end"],
        "seed": m.get("seed"),
        "params": m.get("params"),
        "trainer_git_commit": m.get("trainer_git_commit"),
        "trainer_git_dirty": m.get("trainer_git_dirty"),
        "code_sha256": m.get("code_sha256"),
        "validation": m.get("validation")
        and {
            k: m["validation"].get(k)
            for k in ("status", "reason", "holdout_start", "holdout_end", "method")
        },
        "validation_metrics": {
            "1hour": (m.get("validation_metrics") or {}).get("1hour")
        },
        "manifest": m,
    }


def binding_errors(
    plan: Plan,
    job: Mapping[str, str],
    summary: Mapping[str, Any],
    train_commit: Optional[str],
) -> List[str]:
    """A published model must be the declared training: its pair, window, seed, the
    trainer's parameters, the current model code, and a clean trainer at a commit whose
    trainer files (model code and the code it reads bars through) are those of the
    commit ``train`` ran at. (The model store keeps an earlier manifest when a training
    gives the same content, so the commit itself may be an earlier one.)"""
    from pt_pattern_trainer import TRAINER_PARAMS

    errors = []
    pair = f"{job['coin']}USDT"
    if summary["symbol"] != pair or summary["coin"] != job["coin"]:
        errors.append(f"trained on {summary['symbol']}, not {pair}")
    if _ts(summary["train_start"]) != _ts(job["train_start"]) or _ts(
        summary["train_end"]
    ) != _ts(job["train_end"]):
        errors.append(
            f"the published window {summary['train_start']}..{summary['train_end']} "
            "is not the one asked for"
        )
    if summary["seed"] != plan.trainer_seed:
        errors.append(f"seed {summary['seed']}, not {plan.trainer_seed}")
    if summary["params"] != TRAINER_PARAMS:
        errors.append("not the trainer's default parameters")
    if summary["code_sha256"] != model_code_hashes():
        errors.append("trained with other model code than the current (train again)")
    commit = summary.get("trainer_git_commit")
    clean = (
        summary.get("trainer_git_dirty") is False
        and isinstance(commit, str)
        and len(commit) == 40
        and all(c in "0123456789abcdef" for c in commit)
        and bool(train_commit)
    )
    if clean and commit != train_commit:
        paths = [f"app/{n}" for n in MODEL_CODE + TRAINER_DATA_CODE]
        try:
            clean = not _changed_between(commit, train_commit, paths)
        except subprocess.CalledProcessError:  # a commit git does not know
            clean = False
    if not clean:
        errors.append(
            f"trained at commit {commit} (dirty: {summary.get('trainer_git_dirty')}), "
            f"not cleanly at {train_commit} or a commit with the same trainer files"
        )
    return errors


def train(
    plan: Plan,
    out_dir: str = OUT,
    trainer: str = TRAINER,
    cache_dir: Optional[str] = None,
    note: Optional[str] = None,
    state: Optional[Mapping[str, Any]] = None,
) -> int:
    """The trainings, offline, through the trainer as the hub runs it (the coin as its
    argument, a working folder of its own). Any failure: nothing is scored. A model whose
    validation is unavailable is not a failure (its verdict-line values read n/a). Earlier
    training outputs, and the run outputs that came from them, move aside together."""
    import pt_paths

    s = _state(state)
    data = check_data(plan, out_dir, cache_dir)
    supersede(
        out_dir,
        (
            "train.json",
            "manifests",
            "results.json",
            "runs",
            "baselines",
            "verdict.json",
        ),
        note,
        s,
        "train",
    )
    root = os.path.join(pt_paths.data_dir(), "backtest-model-1", "trainer")
    stamp = (
        f"{time.strftime('%Y%m%dT%H%M%S')}-{time.time_ns() % 10**9:09d}"  # never reused
    )
    runs = []
    for job in plan.trainings():
        coin = job["coin"]
        folder = os.path.join(root, coin)
        os.makedirs(folder, exist_ok=True)
        for pattern in TRAINER_FILES:  # the trainer refuses a folder with model files
            for path in glob.glob(os.path.join(folder, pattern)):
                os.remove(path)
        summary_path = os.path.join(
            pt_paths.data_dir(),
            "training_results",
            f"{coin.lower()}_training_results.json",
        )
        if os.path.exists(summary_path):
            os.remove(summary_path)  # so the id read below is this run's
        argv = [
            sys.executable, "-u", trainer, coin, "--offline",
            "--train-start", job["train_start"], "--train-end", job["train_end"],
            "--seed", str(plan.trainer_seed),
        ]  # fmt: skip
        print(f"== Test {job['test']} {coin} to {job['train_end']}", flush=True)
        log_path = os.path.join(
            root,
            f"{coin}-{job['train_end'][:10]}-{job['test']}-{s['commit'][:7]}-{stamp}.log",
        )
        started = time.time()
        with open(log_path, "x", encoding="utf-8") as log:
            proc = subprocess.run(
                argv, cwd=folder, stdout=log, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )  # fmt: skip
        seconds = round(time.time() - started, 1)
        model_id = published_model_id(coin) if proc.returncode == 0 else None
        record = dict(
            job,
            exit_code=proc.returncode,
            wall_seconds=seconds,
            log=log_path,
            model_id=model_id,
        )
        if model_id:
            summary = manifest_summary(model_id)
            errors = binding_errors(plan, job, summary, s["commit"])
            if errors:
                record["error"] = "; ".join(errors)
            _write_json(
                os.path.join(out_dir, "manifests", f"{model_id}.json"),
                summary["manifest"],
            )
        print(
            f"   exit {proc.returncode} after {seconds} s, model_id {model_id}",
            flush=True,
        )
        runs.append(record)
    _write_json(
        os.path.join(out_dir, "train.json"),
        {
            "code": s,
            "data_sha256": {k: r["sha256"] for k, r in data["files"].items()},
            "data_code_sha256": trainer_data_code_hashes(),
            "trainings": runs,
        },
    )
    failed = [
        r for r in runs if r["exit_code"] != 0 or not r["model_id"] or r.get("error")
    ]
    if failed:
        print(f"STOP: {len(failed)} training(s) failed: nothing is scored", flush=True)
        return 1
    return 0


def trained_models(
    plan: Plan, out_dir: str = OUT, data: Optional[Mapping[str, Any]] = None
) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """``{(test, coin, train_end): manifest summary}`` for every declared training,
    each checked against the declared window, the current code, the commit ``train`` ran
    at, and the candle files it read (``data``: ``data.json``); ``Stop`` otherwise."""
    import model_store

    path = os.path.join(out_dir, "train.json")
    if not os.path.isfile(path):
        raise Stop("no train.json: run train first")
    train_json = _read_json(path)
    train_commit = (train_json.get("code") or {}).get("commit")
    if data is not None:
        now = {k: r["sha256"] for k, r in data["files"].items()}
        if train_json.get("data_sha256") != now:
            raise Stop("the models were trained on other candle files than data.json's")
    if train_json.get("data_code_sha256") != trainer_data_code_hashes():
        raise Stop(
            "the code the trainer reads its bars through changed since train "
            f"({', '.join(TRAINER_DATA_CODE)}): train again"
        )
    by_job = {}
    for r in train_json["trainings"]:
        if r["exit_code"] != 0 or not r.get("model_id") or r.get("error"):
            raise Stop(f"training failed: {r}")
        by_job[(r["test"], r["coin"], r["train_end"])] = r["model_id"]
    out = {}
    for job in plan.trainings():
        key = (job["test"], job["coin"], job["train_end"])
        if key not in by_job:
            raise Stop(f"training missing: {job}")
        try:
            summary = manifest_summary(by_job[key])
        except model_store.ModelStoreError as exc:
            raise Stop(f"model {by_job[key]} for {job}: {exc}") from exc
        errors = binding_errors(plan, job, summary, train_commit)
        if errors:
            raise Stop(f"model {by_job[key]} for {job}: {'; '.join(errors)}")
        copy = os.path.join(out_dir, "manifests", f"{by_job[key]}.json")
        if not os.path.isfile(copy) or _read_json(copy) != json.loads(
            json.dumps(summary["manifest"], default=str)
        ):
            raise Stop(
                f"model {by_job[key]}: the manifest copy in {out_dir} is missing or "
                "differs from the store's"
            )
        out[key] = summary
    ids = [s["model_id"] for s in out.values()]
    if len(set(ids)) != len(ids):
        raise Stop(f"the trainings do not have distinct models: {ids}")
    return out


# --- run --------------------------------------------------------------------------------------


def _overlay_specs(ids: Sequence[str]) -> List[dict]:
    return [{"id": i} for i in ids]


def strat003_runner(model_id: str, overlay_ids: Sequence[str], frames: Mapping):
    """A fresh STRAT-003 runner that records its decisions and reads the run's own
    candle files for its seven timeframes."""
    from backtest.model_eval import RecordingRunner
    from strategies.factory import build_runner

    built = build_runner(
        "STRAT-003", {"model_id": model_id}, _overlay_specs(overlay_ids)
    )
    runner = RecordingRunner(built.strategy, built.overlays)
    runner.strategy.use_bars(frames)
    return runner


def _trades_csv(path: str, *results) -> None:
    import pandas as pd
    from dataclasses import asdict

    rows = []
    for series, result in results:
        for t in result.trades:
            row = asdict(t)
            row["series"] = series
            rows.append(row)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _cost(plan: Plan):
    from backtest.engine import CostModel

    return CostModel(plan.fee_bps, plan.slippage_bps, plan.size_fraction)


def _scored(
    candles, runner, pair: str, tf: str, a: int, b: int, plan: Plan
) -> Dict[str, Any]:
    """STRAT-003 and buy-and-hold on ``candles[a:b]`` (earlier bars are history only),
    with the decision counts."""
    from backtest.engine import buy_and_hold, run_backtest
    from backtest.model_eval import hold_counts, quirk_counts

    strat = run_backtest(
        candles, runner, pair, tf, a, b, _cost(plan), plan.initial_equity
    )
    bench = buy_and_hold(candles, tf, a, b, _cost(plan), plan.initial_equity)
    if len(runner.records) != strat.bars - 1:
        raise Stop(
            f"{pair} {tf}: {len(runner.records)} decisions for {strat.bars} bars (expected one per bar but the last)"
        )
    sk, bk = dict(strat.kpis), dict(bench.kpis)
    sk["vs_buy_hold_pct"] = sk["total_return_pct"] - bk["total_return_pct"]
    return {
        "window": [a, b],
        "from": strat.first_bar.isoformat(),
        "to": strat.last_bar.isoformat(),
        "bars": strat.bars,
        "strategy": sk,
        "buy_and_hold": bk,
        "holds": hold_counts(runner.records),
        "quirks": quirk_counts(runner.records),
        "_strat": strat,
        "_bench": bench,
    }


def _public(section: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in section.items() if not k.startswith("_")}


def _index_at(candles, when) -> int:
    """First bar that opens at or after ``when``."""
    return int(candles["open_time"].searchsorted(_ts(when), side="left"))


def run_baseline(
    candles, pair: str, tf: str, a: int, b: int, strat, overlay_ids, plan: Plan, state
) -> Dict[str, Any]:
    """The random-entry baseline of one run (Test A's out-of-sample window)."""
    from backtest.random_baseline import fit_hold, match, percentile_rank, run_seed

    n, h = match(strat.trades)
    out: Dict[str, Any] = {
        "code": state,
        "N": n,
        "H": h,
        "L": b - a,
        "seeds": [],
        "rank": None,
    }
    if n == 0:
        out["no_baseline"] = "STRAT-003 made no trade (N = 0)"
        return out
    used, reduced = fit_hold(n, h, b - a)
    out.update(H_used=used, H_reduced=reduced)
    if used is None:
        out["no_baseline"] = f"{n} trades do not fit in {b - a} bars even at H = 1"
        return out
    seeds = plan.seeds(pair, tf)
    if len(seeds) != plan.seeds_per_run:
        raise Stop(f"{pair} {tf}: {len(seeds)} seeds, not {plan.seeds_per_run}")
    for seed in seeds:
        record = run_seed(
            candles,
            a,
            b,
            pair,
            tf,
            seed,
            n,
            used,
            _overlay_specs(overlay_ids),
            _cost(plan),
            plan.initial_equity,
        )
        if not overlay_ids and (
            record["trade_count"] != n or record["bars_held"] != [used]
        ):
            raise Stop(
                f"{pair} {tf} seed {seed}: {record['trade_count']} trades of {record['bars_held']} bars, not {n} of {used}"
            )
        out["seeds"].append(record)
    returns = [s["total_return_pct"] for s in out["seeds"]]
    out["rank"] = percentile_rank(strat.kpis["total_return_pct"], returns)
    out["flagged_seeds"] = [
        s["seed"] for s in out["seeds"] if not 0.9 * n <= s["trade_count"] <= 1.1 * n
    ]
    return out


def run(
    plan: Plan,
    out_dir: str = OUT,
    cache_dir: Optional[str] = None,
    note: Optional[str] = None,
    state: Optional[Mapping[str, Any]] = None,
) -> int:
    """Test A, the random baselines and Test B; writes per-run JSON, trades CSVs, the
    baseline distributions and ``results.json`` (marked "running" until it finishes, so
    an interrupted run leaves a record). A failed check stops it (``results.json`` then
    records why, and anything already scored); so does any other error, which is
    recorded and raised."""
    from backtest.random_baseline import check_pins
    from market_data.candles import cache_path, load_candles_csv

    s = _state(state)
    supersede(
        out_dir, ("results.json", "runs", "baselines", "verdict.json"), note, s, "run"
    )
    _write_json(os.path.join(out_dir, "results.json"), {"status": "running", "code": s})
    results: Optional[Dict[str, Any]] = None

    def stopped(reason: str) -> None:
        record = {"status": "stopped", "reason": reason, "code": s}
        scored = _scored_summary(results)
        if scored:
            record["scored"] = scored
        _write_json(os.path.join(out_dir, "results.json"), record)

    try:
        data = check_data(plan, out_dir, cache_dir)
        models = trained_models(plan, out_dir, data)
        try:
            check_pins()  # the control's draws are the ones the header pins
        except ValueError as exc:
            raise Stop(str(exc)) from exc
        frames = {
            pair: {
                tf: load_candles_csv(cache_path(pair, tf, cache_dir), tf)
                for tf in plan.model_tfs
            }
            for pair in plan.pairs
        }
        results = {
            "status": "ok",
            "code": s,
            "data": data,
            "models": {"|".join(k): {**v, "manifest": None} for k, v in models.items()},
            "test_a": {},
            "test_b": [],
        }
        _score_all(plan, out_dir, frames, models, results, s)
    except Stop as exc:
        stopped(str(exc))
        print(f"STOP: {exc}", flush=True)
        return 1
    except Exception as exc:
        stopped(f"error: {type(exc).__name__}: {exc}")
        raise
    _write_json(os.path.join(out_dir, "results.json"), results)
    return 0


def _score_all(plan: Plan, out_dir: str, frames, models, results, state) -> None:
    from backtest.engine import LookaheadError, buy_and_hold, run_backtest, split_index

    cost = _cost(plan)
    for pair, coin in zip(plan.pairs, plan.coins):
        a_model = models[("A", coin, plan.test_a_train_end)]["model_id"]
        for tf in plan.primary:
            candles = frames[pair][tf]
            n = len(candles)
            cut = split_index(n, plan.in_sample_fraction)
            if (
                n != plan.candles[tf]
                or n - cut != plan.oos_bars[tf]
                or candles["open_time"].iloc[cut] != _ts(plan.oos_start[tf])
            ):
                raise Stop(
                    f"{pair} {tf}: {n} bars, out of sample from {candles['open_time'].iloc[cut]} "
                    f"({n - cut} bars); batch 1 had {plan.candles[tf]}, from {plan.oos_start[tf]} ({plan.oos_bars[tf]})"
                )
            for ov_name, ov_ids in plan.overlay_sets:
                tag = f"test-a_{pair}_{tf}_{ov_name.replace('+', '_')}"
                # in-sample: the lookahead guard refuses bars the model was trained on
                try:
                    run_backtest(
                        candles,
                        strat003_runner(a_model, ov_ids, frames[pair]),
                        pair,
                        tf,
                        0,
                        cut,
                        cost,
                        plan.initial_equity,
                    )
                    raise Stop(f"{tag}: the in-sample window was not refused")
                except LookaheadError as exc:
                    refused = str(exc)
                bench_is = buy_and_hold(candles, tf, 0, cut, cost, plan.initial_equity)
                runner = strat003_runner(a_model, ov_ids, frames[pair])
                oos = _scored(candles, runner, pair, tf, cut, n, plan)
                section = {
                    "pair": pair,
                    "timeframe": tf,
                    "overlays": ov_name,
                    "model_id": a_model,
                    "code": state,
                    "in_sample": {
                        "window": [0, cut],
                        "from": bench_is.first_bar.isoformat(),
                        "to": bench_is.last_bar.isoformat(),
                        "bars": bench_is.bars,
                        "refused": refused,
                        "buy_and_hold": dict(bench_is.kpis),
                    },
                    "out_of_sample": _public(oos),
                }
                section["baseline"] = run_baseline(
                    candles, pair, tf, cut, n, oos["_strat"], ov_ids, plan, state
                )
                _write_json(
                    os.path.join(out_dir, "runs", f"{tag}.json"),
                    {k: v for k, v in section.items() if k != "baseline"}
                    | {"baseline": f"baselines/{tag}.json"},
                )
                _trades_csv(
                    os.path.join(out_dir, "runs", f"{tag}_trades.csv"),
                    ("strategy", oos["_strat"]),
                    ("buy_and_hold", oos["_bench"]),
                )
                _write_json(
                    os.path.join(out_dir, "baselines", f"{tag}.json"),
                    section["baseline"],
                )
                results["test_a"][f"{pair}|{tf}|{ov_name}"] = section
                print(
                    f"{tag}: vs B&H {oos['strategy']['vs_buy_hold_pct']:+.2f} pp, rank {section['baseline']['rank']}",
                    flush=True,
                )
        for end in plan.test_b_ends:
            b_model = models[("B", coin, end)]["model_id"]
            for tf in plan.primary:
                candles = frames[pair][tf]
                window_end = min(_ts(end) + _months(plan.test_b_months), _ts(plan.end))
                a, b = _index_at(candles, end), _index_at(candles, window_end)
                step = (
                    candles["open_time"].iloc[1] - candles["open_time"].iloc[0]
                ).total_seconds()
                expected = int((window_end - _ts(end)).total_seconds() // step)
                if b - a != expected:
                    raise Stop(
                        f"{pair} {tf} Test B from {end}: {b - a} bars, not the full {expected}"
                    )
                for ov_name, ov_ids in plan.overlay_sets:
                    tag = f"test-b_{pair}_{tf}_{ov_name.replace('+', '_')}_{end[:10]}"
                    runner = strat003_runner(b_model, ov_ids, frames[pair])
                    window = _scored(candles, runner, pair, tf, a, b, plan)
                    section = {
                        "pair": pair, "timeframe": tf, "overlays": ov_name,
                        "model_id": b_model, "train_end": end, "code": state,
                    } | _public(window)  # fmt: skip
                    _write_json(os.path.join(out_dir, "runs", f"{tag}.json"), section)
                    _trades_csv(
                        os.path.join(out_dir, "runs", f"{tag}_trades.csv"),
                        ("strategy", window["_strat"]),
                        ("buy_and_hold", window["_bench"]),
                    )
                    results["test_b"].append(section)
                    print(
                        f"{tag}: vs B&H {window['strategy']['vs_buy_hold_pct']:+.2f} pp",
                        flush=True,
                    )


def _months(n: int):
    import pandas as pd

    return pd.DateOffset(months=n)


# --- report -----------------------------------------------------------------------------------


def split_header(text: str) -> Tuple[str, str]:
    """``(header, rest)``: the header ends with the marker line."""
    at = text.find(MARKER)
    if at < 0:
        raise Stop(f"the report has no '{MARKER}' marker")
    end = text.find("\n", at)
    end = len(text) if end < 0 else end + 1
    return text[:end], text[end:]


def header_commits(commit: str) -> List[str]:
    """The commits that changed the header (above the marker) up to ``commit``, from the
    first header commit on; each must change no frozen file (Stop otherwise). Commits
    that changed only the results below the marker are not header commits."""
    lines = _git(
        "log",
        "--format=%h %ad %s",
        "--date=short",
        f"{FIRST_HEADER_COMMIT}^..{commit}",
        "--",
        REPORT_REL,
    )
    out = []
    for line in lines.splitlines():
        if not line.strip():
            continue
        sha = line.split()[0]
        if _header_at(sha) == _header_at(f"{sha}^"):
            continue  # only the results changed
        touched = _git("show", "--name-only", "--format=", sha).splitlines()
        frozen = [
            p
            for p in touched
            if p.startswith("app/") or p == "docs/dev/run_backtest_model1.py"
        ]
        if frozen:
            raise Stop(f"header commit {sha} also changed frozen files: {frozen}")
        out.append(line)
    return out


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n")


def check_entries(baseline: Mapping[str, Any]) -> None:
    """Every seed's recorded entry bars must be what its seed draws now."""
    from backtest.random_baseline import placement

    for s in baseline.get("seeds", []):
        again = placement(s["seed"], baseline["L"], baseline["N"], baseline["H_used"])
        if again != s["entries"]:
            raise AssertionError(
                f"seed {s['seed']}: the recorded entry bars are not what it draws now "
                "(a change in Python's random?); the recorded ones are the control"
            )


def _fmt(v, digits: int = 2, pct: bool = False) -> str:
    if v is None:
        return "n/a"
    return f"{v:,.{digits}f}" + ("%" if pct else "")


HEAD = [
    "total ret",
    "CAGR",
    "max DD",
    "Sharpe",
    "Sortino",
    "trades",
    "win rate",
    "avg trade",
    "exposure",
    "fees",
]


def _cells(k: Mapping[str, Any]) -> List[str]:
    return [
        _fmt(k["total_return_pct"], pct=True), _fmt(k["cagr_pct"], pct=True), _fmt(k["max_drawdown_pct"], pct=True),
        _fmt(k["sharpe"]), _fmt(k["sortino"]), str(k["trade_count"]), _fmt(k["win_rate_pct"], pct=True),
        _fmt(k["avg_trade_pct"], pct=True), _fmt(k["exposure_pct"], 1, pct=True), "$" + _fmt(k["fees_paid"], 0),
    ]  # fmt: skip


def evaluate(plan: Plan, results: Mapping[str, Any]) -> Dict[str, Any]:
    """The verdict inputs (from the runs without overlays), the verdict (checked against
    an independent recheck) and the verdict line's notes: missing-bar holds per window,
    gap-pass limits per combination and test."""
    from backtest.model_eval import data_holds, recheck_verdict, verdict

    test_a, not_assessable, gap = {}, [], []
    for pair in plan.pairs:
        for tf in plan.primary:
            sec = results["test_a"][f"{pair}|{tf}|none"]
            oos = sec["out_of_sample"]
            holds = data_holds(oos["holds"])
            test_a[(pair, tf)] = {
                "vs_bh": oos["strategy"]["vs_buy_hold_pct"],
                "data_holds": holds,
                "rank": sec["baseline"]["rank"],
            }
            if holds:
                not_assessable.append((f"{pair} {tf}", "Test A out-of-sample", holds))
            if oos["quirks"]["e2"]:
                gap.append((f"{pair} {tf}", "Test A", oos["quirks"]["e2"]))
    test_b, b_gap = [], {}
    for w in results["test_b"]:
        if w["overlays"] != "none":
            continue
        holds = data_holds(w["holds"])
        combo = f"{w['pair']} {w['timeframe']}"
        test_b.append(
            {
                "combination": (w["pair"], w["timeframe"]),
                "vs_bh": w["strategy"]["vs_buy_hold_pct"],
                "data_holds": holds,
            }
        )
        if holds:
            not_assessable.append(
                (combo, f"Test B {w['from'][:10]}..{w['to'][:10]}", holds)
            )
        b_gap[combo] = b_gap.get(combo, 0) + w["quirks"]["e2"]
    gap.extend((combo, "Test B", n) for combo, n in b_gap.items() if n)
    v = verdict(test_a, test_b, plan.expected_test_b_windows())
    again = recheck_verdict(test_a, test_b)
    if v["verdict"] != again:
        raise Stop(f"the verdict does not recheck: {v['verdict']} vs {again}")
    return {
        "test_a": test_a,
        "test_b": test_b,
        "verdict": v,
        "not_assessable": not_assessable,
        "gap": gap,
    }


def _superseded(plan: Plan, out_dir: str) -> List[str]:
    """Earlier outputs moved aside under the code rule: what changed and why, the
    verdict they gave (as recorded when it was given) and their numbers, including what
    a stopped or interrupted run had already scored."""
    root = os.path.join(out_dir, "superseded")
    if not os.path.isdir(root):
        return []
    lines = []
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        note = _read_json(os.path.join(folder, "note.json"))
        res_path = os.path.join(folder, "results.json")
        res = _read_json(res_path) if os.path.isfile(res_path) else None
        status = res.get("status") if res else None
        if status == "ok":
            per = []
            for pair in plan.pairs:
                for tf in plan.primary:
                    sec = res["test_a"][f"{pair}|{tf}|none"]
                    vs = sec["out_of_sample"]["strategy"]["vs_buy_hold_pct"]
                    per.append(
                        f"{pair} {tf} Test A {_fmt(vs)} pp, rank "
                        f"{_fmt(sec['baseline']['rank'], 1)}"
                    )
            b = [
                w["strategy"]["vs_buy_hold_pct"]
                for w in res["test_b"]
                if w["overlays"] == "none"
            ]
            from backtest.model_eval import median

            numbers = "; ".join(per) + f"; Test B pooled median {_fmt(median(b))} pp"
            vpath = os.path.join(folder, "verdict.json")
            if os.path.isfile(vpath):
                given = _read_json(vpath)
                verdict_text = (
                    f"verdict given: {given['verdict']} (criteria 1-3: "
                    f"{_criteria_text(given)}; reported at "
                    f"`{given['reported_at_commit'][:7]}`)"
                )
            else:
                verdict_text = "no verdict was given (no report was made from them)"
            what = (
                f"{verdict_text}, from commit `{res['code']['commit'][:7]}`; {numbers}"
            )
        elif status == "stopped" and res.get("scored"):
            what = (
                f"stopped after scoring {len(res['scored'])} run(s), which do not count: "
                f"{res.get('reason')}; {_scored_lines(res['scored'])}"
            )
        elif status == "stopped":
            what = f"stopped, nothing scored: {res.get('reason')}"
        elif os.path.isdir(os.path.join(folder, "runs")):
            k, text = _run_files_summary(folder)
            what = f"interrupted after scoring {k} run(s), which do not count" + (
                f": {text}" if text else ""
            )
        elif status == "running":
            what = "interrupted before scoring anything"
        else:
            what = f"{note['step']} outputs only ({', '.join(note['moved'])})"
        lines.append(f"- `{name}`: {what}. What changed and why: {note['note']}")
    return lines


def render(
    plan: Plan,
    results: Mapping[str, Any],
    header_log: Sequence[str],
    superseded: Sequence[str] = (),
    code_log: Sequence[str] = (),
    report_commit: Optional[str] = None,
) -> str:
    """The results section (everything after the header)."""
    from backtest.model_eval import manifest_values, median, verdict_line

    L: List[str] = []
    w = L.append
    w("")
    w("## Results")
    w("")
    code = results["code"]
    w(
        f"- **Code:** commit `{code['commit']}`; frozen files changed from it: {code['frozen_files_changed'] or 'none'}. "
        f"Python {code['python'].split()[0]}. `POWERTRADER_HOME`: `{code.get('powertrader_home')}`. "
        f"Reported from commit `{report_commit or code['commit']}`."
    )
    w(
        "- **Frozen-code commits after the header** (the freeze commit, and any fix after it): "
        + ("; ".join(f"`{c}`" for c in code_log) or "none")
        + "."
    )
    w(
        "- **Header commits:** "
        + ("; ".join(f"`{c}`" for c in header_log) or "none")
        + "."
    )
    if superseded:
        w(
            "- **Superseded runs** (the code rule: earlier results, kept, with what changed and why):"
        )
        L.extend("  " + s for s in superseded)
    if results.get("status") != "ok":
        w("")
        if results.get("scored"):
            w(
                f"**Stopped after scoring {len(results['scored'])} run(s); nothing here "
                f"counts toward a verdict.** {results.get('reason')}"
            )
            w("")
            w("Scored before the stop: " + _scored_lines(results["scored"]) + ".")
        else:
            w(f"**Stopped: nothing was scored.** {results.get('reason')}")
        return "\n".join(L) + "\n"
    ev = evaluate(plan, results)
    manifests = {
        coin: results["models"][f"A|{coin}|{plan.test_a_train_end}"]
        for coin in plan.coins
    }
    v = ev["verdict"]
    w("")
    w("### Verdict")
    w("")
    w(
        verdict_line(
            v["verdict"],
            manifests,
            ev["not_assessable"],
            ev["gap"],
            plan.test_a_holdout,
        )
    )
    w("")
    w(
        f"- Criterion 1 (Test A, out of sample, no overlays, at least 3 of 4 beat buy-and-hold): "
        f"{'met' if v['criterion_1'] else 'not met'}; combinations: {', '.join(' '.join(c) for c in v['criterion_1_combinations']) or 'none'}."
    )
    w(
        "- Criterion 2 (each of those ranks at least 95 in its random baseline): "
        + (
            "not applicable (no combination meets criterion 1)"
            if not v["criterion_1_combinations"]
            else ("met" if v["criterion_2"] else "not met")
        )
        + (
            f"; failing: {', '.join(' '.join(c) for c in v['criterion_2_failing'])}"
            if v["criterion_2_failing"]
            else ""
        )
        + "."
    )
    w(
        f"- Criterion 3 (Test B, no overlays, median of all {plan.expected_test_b_windows()} windows above 0): "
        f"{'met' if v['criterion_3'] else 'not met'}; pooled median {_fmt(v['pooled_median'])} pp, worst window {_fmt(v['pooled_worst'])} pp."
    )
    w(
        "- For information only (not in the verdict), each combination's Test B median: "
        + "; ".join(
            f"{' '.join(c)} {_fmt(m)} pp"
            for c, m in sorted(v["combination_medians"].items())
        )
        + "."
    )
    w("")
    w("### Data")
    w("")
    w("| File | Bars | First | Last | Missing bars | SHA-256 | Batch 1 |")
    w("|---|---|---|---|---|---|---|")
    for key, rec in results["data"]["files"].items():
        b1 = plan.batch1_sha256.get(key)
        w(
            f"| {key} | {rec['bars']:,} | {rec['first']} | {rec['last']} | {rec['missing_bars']} | `{rec['sha256']}` | "
            f"{'same' if b1 == rec['sha256'] else ('—' if b1 is None else 'DIFFERENT')} |"
        )
    w("")
    w("### Models")
    w("")
    w("| Test | Model | Window | Held-out 1h hit rate | Up share | n | Validation |")
    w("|---|---|---|---|---|---|---|")
    for key, m in results["models"].items():
        mv = manifest_values(m)
        w(
            f"| {key.split('|')[0]} | `{m['model_id']}` | {m['train_start']} .. {m['train_end']} | {mv['hit']} | {mv['up']} | "
            f"{mv['n']} | {(m.get('validation') or {}).get('status')} |"
        )
    w("")
    w("### Test A: out of sample")
    w("")
    for pair in plan.pairs:
        for tf in plan.primary:
            first = results["test_a"][f"{pair}|{tf}|none"]
            oos = first["out_of_sample"]
            w(
                f"#### {pair} {tf}: {oos['from'][:16]} to {oos['to'][:16]} ({oos['bars']:,} bars)"
            )
            w("")
            w("| Run | " + " | ".join(HEAD) + " | vs B&H (pp) | Baseline rank |")
            w("|---|" + "---|" * (len(HEAD) + 2))
            for ov_name, _ in plan.overlay_sets:
                sec = results["test_a"][f"{pair}|{tf}|{ov_name}"]
                k = sec["out_of_sample"]["strategy"]
                label = "STRAT-003, " + (
                    "no overlays" if ov_name == "none" else ov_name.replace("+", " + ")
                )
                w(
                    f"| {label} | "
                    + " | ".join(_cells(k))
                    + f" | {_fmt(k['vs_buy_hold_pct'])} | {_fmt(sec['baseline']['rank'], 1)} |"
                )
            w(
                "| **Buy-and-hold** | "
                + " | ".join(_cells(oos["buy_and_hold"]))
                + " | — | — |"
            )
            w("")
            for ov_name, _ in plan.overlay_sets:
                bl = results["test_a"][f"{pair}|{tf}|{ov_name}"]["baseline"]
                counts = [s["trade_count"] for s in bl["seeds"]]
                w(
                    f"- Random baseline, {ov_name}: N = {bl['N']}, H = {bl['H']}"
                    + (
                        f" (used {bl.get('H_used')}, reduced)"
                        if bl.get("H_reduced")
                        else ""
                    )
                    + (
                        f"; no baseline: {bl['no_baseline']}."
                        if bl.get("no_baseline")
                        else f"; seeds {min(s['seed'] for s in bl['seeds'])}-{max(s['seed'] for s in bl['seeds'])}, trade counts "
                        f"{min(counts)}-{max(counts)}, flagged (outside N ± 10%): {bl['flagged_seeds'] or 'none'}."
                    )
                )
            hd, q = oos["holds"], oos["quirks"]
            w(
                f"- Without overlays: holds for missing bars {hd['BARS_MISSING']}, unknown timeframe {hd['TIMEFRAME_UNKNOWN']}, "
                f"gap-pass limit {hd['BOUNDS_NOT_CONVERGED']}; E1 {q['e1']} of {q['decisions']} decisions "
                f"({_fmt(100 * q['e1_share'] if q['e1_share'] is not None else None, 1, pct=True)}), E2 {q['e2']}."
            )
            isec = first["in_sample"]
            w(
                f"- In-sample {isec['from'][:10]} to {isec['to'][:10]} ({isec['bars']:,} bars): refused ({isec['refused']}); "
                f"buy-and-hold {_fmt(isec['buy_and_hold']['total_return_pct'], pct=True)}."
            )
            w("")
    w("### Test B: walk-forward")
    w("")
    w(
        "E1, E2 and missing bars are counted in the runs without overlays (STRAT-003's own signals do not depend on the overlay set)."
    )
    w("")
    w(
        "| Combination | Overlays | Model trained to | Window | vs B&H (pp) | STRAT-003 | Buy-and-hold | Trades | E1 | E2 | Missing bars |"
    )
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for x in results["test_b"]:
        q = x["quirks"]
        counts = (
            f"{q['e1']} of {q['decisions']} ({_fmt(100 * q['e1_share'] if q['e1_share'] is not None else None, 1, pct=True)}) | "
            f"{q['e2']} | {x['holds']['BARS_MISSING'] + x['holds']['TIMEFRAME_UNKNOWN']}"
            if x["overlays"] == "none"
            else "— | — | —"
        )
        w(
            f"| {x['pair']} {x['timeframe']} | {x['overlays']} | {x['train_end'][:10]} | {x['from'][:10]}..{x['to'][:10]} | "
            f"{_fmt(x['strategy']['vs_buy_hold_pct'])} | {_fmt(x['strategy']['total_return_pct'], pct=True)} | "
            f"{_fmt(x['buy_and_hold']['total_return_pct'], pct=True)} | {x['strategy']['trade_count']} | {counts} |"
        )
    w("")
    w(
        "| Combination | Overlays | Median vs B&H (pp) | Worst window (pp) | E1 (Test B) | E2 (Test B) |"
    )
    w("|---|---|---|---|---|---|")
    for pair in plan.pairs:
        for tf in plan.primary:
            for ov_name, _ in plan.overlay_sets:
                rows = [
                    x
                    for x in results["test_b"]
                    if x["pair"] == pair
                    and x["timeframe"] == tf
                    and x["overlays"] == ov_name
                ]
                vals = [x["strategy"]["vs_buy_hold_pct"] for x in rows]
                if ov_name == "none":
                    e1, dec, e2 = (
                        sum(x["quirks"][k] for x in rows)
                        for k in ("e1", "decisions", "e2")
                    )
                    q = f"{e1} of {dec} ({_fmt(100 * e1 / dec if dec else None, 1, pct=True)}) | {e2}"
                else:
                    q = "— | —"
                w(
                    f"| {pair} {tf} | {ov_name} | {_fmt(median(vals))} | {_fmt(min(vals))} | {q} |"
                )
    w("")
    w("### Batch 1 side by side (out of sample, no overlays; batch 1 not re-run)")
    w("")
    w(
        "| Combination | STRAT-001 vs B&H (pp) | STRAT-002 vs B&H (pp) | STRAT-003 vs B&H (pp) |"
    )
    w("|---|---|---|---|")
    for pair in plan.pairs:
        for tf in plan.primary:
            cells = [
                _fmt(
                    _read_json(os.path.join(BATCH1, f"{sid}_{pair}_{tf}_none.json"))[
                        "out_of_sample"
                    ]["strategy"]["vs_buy_hold_pct"]
                )
                for sid in ("STRAT-001", "STRAT-002")
            ]
            s3 = results["test_a"][f"{pair}|{tf}|none"]["out_of_sample"]["strategy"][
                "vs_buy_hold_pct"
            ]
            w(f"| {pair} {tf} | {cells[0]} | {cells[1]} | {_fmt(s3)} |")
    w("")
    return "\n".join(L) + "\n"


def report(
    plan: Plan,
    out_dir: str = OUT,
    report_path: str = REPORT,
    header_at: Optional[Callable[[str], Optional[str]]] = None,
    commits: Optional[Sequence[str]] = None,
    code_log: Optional[Sequence[str]] = None,
    state: Optional[Mapping[str, Any]] = None,
    frozen_changes: Optional[Callable[[str, str], List[str]]] = None,
) -> int:
    """Append the results to the report, below its header. The code must be the code
    the results came from (frozen files unchanged since their commit), and the header
    must be the one committed when they, and every earlier run that scored anything,
    were produced. ``header_at``, ``commits``, ``code_log`` and ``frozen_changes``
    default to the repository's (``git show``, ``git log``, ``git diff``)."""
    s = _state(state)
    path = os.path.join(out_dir, "results.json")
    if not os.path.isfile(path):
        raise Stop("no results.json: run first")
    results = _read_json(path)
    if results.get("status") == "running":
        raise Stop(
            "the last run did not finish (results.json says running): run again with "
            "--supersede"
        )
    code = results.get("code") or {}
    if code.get("frozen_files_changed"):
        raise Stop(
            "the results come from frozen files that differ from their commit: "
            f"{code['frozen_files_changed']}"
        )
    changed = (frozen_changes or _frozen_changes)(code["commit"], s["commit"])
    if changed:
        raise Stop(
            f"frozen files changed since the results' commit {code['commit'][:7]}: "
            f"{changed}; re-run from the first step the change affects (--supersede)"
        )
    with open(report_path, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    header, _ = split_header(text)
    at = header_at or _header_at
    if _norm(header) != _norm(at(code["commit"]) or ""):
        raise Stop(
            "the report's header differs from the one committed when the results were "
            "produced"
        )
    root = os.path.join(out_dir, "superseded")
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        folder = os.path.join(root, name)
        commits_seen = set(_run_file_commits(folder))  # anything scored, even if killed
        old = os.path.join(folder, "results.json")
        if os.path.isfile(old):
            res = _read_json(old)
            if res.get("status") == "ok" or res.get("scored"):
                commits_seen.add((res.get("code") or {}).get("commit"))
        for commit in sorted(c for c in commits_seen if c):
            if _norm(at(commit) or "") != _norm(header):
                raise Stop(
                    f"the header changed after an earlier run scored ({name}, commit "
                    f"{commit[:7]}): no change is made once Test A has started"
                )
    log = commits if commits is not None else header_commits(code["commit"])
    after = (
        code_log if code_log is not None else frozen_commits_after(log, code["commit"])
    )
    record = None
    if results.get("status") == "ok":
        for sec in results["test_a"].values():
            check_entries(sec["baseline"])
        record = _verdict_record(evaluate(plan, results), s)
    body = render(plan, results, log, _superseded(plan, out_dir), after, s["commit"])
    if "\r\n" in header:  # keep the file's line endings
        body = body.replace("\n", "\r\n")
    if record is not None:  # kept once the report that gives it is complete
        _write_json(os.path.join(out_dir, "verdict.json"), record)
    with open(report_path, "w", encoding="utf-8", newline="") as f:
        f.write(header + body)
    print(f"wrote {report_path}")
    return 0


def trainer_data_code_hashes() -> Dict[str, str]:
    """The code the trainer reads its bars through: a change there changes what a model
    learned from, so the models must be trained again."""
    return {
        name: _text_sha256(os.path.join(APP, *name.split("/")))
        for name in TRAINER_DATA_CODE
    }


def _real(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.expanduser(path)))


def _header_at(commit: str) -> Optional[str]:
    """The report's header (normalised) at ``commit``, or None if the file or its
    marker is absent there."""
    try:
        return _norm(split_header(_git("show", f"{commit}:{REPORT_REL}"))[0])
    except (subprocess.CalledProcessError, Stop):
        return None


def frozen_commits_after(header_log: Sequence[str], commit: str) -> List[str]:
    """The commits that changed frozen code after the first header commit, up to the
    results' commit: the freeze commit, and any fix after it (header commits never
    change frozen code, so later header amendments do not hide the freeze commit)."""
    if not header_log:
        return []
    return [
        line
        for line in _git(
            "log",
            "--format=%h %ad %s",
            "--date=short",
            f"{FIRST_HEADER_COMMIT}..{commit}",
            "--",
            *FROZEN,
        ).splitlines()
        if line.strip()
    ]


def _frozen_changes(old: str, new: str) -> List[str]:
    if old == new:
        return []
    return _git("diff", "--name-only", old, new, "--", *FROZEN).split()


def _verdict_record(ev: Mapping[str, Any], state: Mapping[str, Any]) -> Dict[str, Any]:
    """The verdict as given, kept beside the results (superseded runs show this)."""
    v = ev["verdict"]
    return {
        "verdict": v["verdict"],
        "criteria": [v["criterion_1"], v["criterion_2"], v["criterion_3"]],
        "criterion_1_combinations": [
            " ".join(c) for c in v["criterion_1_combinations"]
        ],
        "criterion_2_failing": [" ".join(c) for c in v["criterion_2_failing"]],
        "pooled_median": v["pooled_median"],
        "pooled_worst": v["pooled_worst"],
        "combination_medians": {
            " ".join(c): m for c, m in v["combination_medians"].items()
        },
        "test_a": {
            " ".join(c): {"vs_bh": a["vs_bh"], "rank": a["rank"]}
            for c, a in ev["test_a"].items()
        },
        "not_assessable": [list(x) for x in ev["not_assessable"]],
        "gap": [list(x) for x in ev["gap"]],
        "reported_at_commit": state["commit"],
        "code": dict(state),
    }


def _unscored(out_dir: str, present: Sequence[str]) -> bool:
    """Only a results.json from a run that stopped (or was killed) before scoring."""
    if list(present) != ["results.json"]:
        return False
    res = _read_json(os.path.join(out_dir, "results.json"))
    return res.get("status") in ("stopped", "running") and not res.get("scored")


def _run_file_commits(folder: str) -> List[str]:
    """The commits the run files in ``folder/runs`` were produced from (each records
    its code), in sorted order without repeats."""
    runs = os.path.join(folder, "runs")
    if not os.path.isdir(runs):
        return []
    commits = set()
    for name in os.listdir(runs):
        if name.endswith(".json"):
            commit = ((_read_json(os.path.join(runs, name)).get("code") or {})).get(
                "commit"
            )
            if commit:
                commits.add(commit)
    return sorted(commits)


def _changed_between(old: str, new: str, paths: Sequence[str]) -> List[str]:
    """Files among ``paths`` that differ between two commits (local git)."""
    if old == new:
        return []
    return _git("diff", "--name-only", old, new, "--", *paths).split()


def _scored_summary(results: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """What a run had already scored when it stopped: each run's tag and numbers."""
    if not results:
        return []
    out = []
    for key, sec in results.get("test_a", {}).items():
        out.append(
            {
                "run": f"Test A {key.replace('|', ' ')}",
                "vs_bh": sec["out_of_sample"]["strategy"]["vs_buy_hold_pct"],
                "rank": (sec.get("baseline") or {}).get("rank"),
            }
        )
    for w in results.get("test_b", []):
        out.append(
            {
                "run": f"Test B {w['pair']} {w['timeframe']} {w['overlays']} {w['train_end'][:10]}",
                "vs_bh": w["strategy"]["vs_buy_hold_pct"],
                "rank": None,
            }
        )
    return out


def _scored_lines(scored: Sequence[Mapping[str, Any]]) -> str:
    return "; ".join(
        f"{s['run']} {_fmt(s['vs_bh'])} pp"
        + (f", rank {_fmt(s['rank'], 1)}" if s.get("rank") is not None else "")
        for s in scored
    )


def _criteria_text(given: Mapping[str, Any]) -> str:
    crit = ["met" if c else "not met" for c in given["criteria"]]
    if not given.get("criterion_1_combinations"):
        crit[1] = "not applicable"
    return ", ".join(crit)


def _run_files_summary(folder: str) -> Tuple[int, str]:
    """``(count, text)`` of the run files left in ``folder/runs`` by an interrupted run."""
    runs = os.path.join(folder, "runs")
    items = []
    for name in sorted(os.listdir(runs)) if os.path.isdir(runs) else []:
        if not name.endswith(".json"):
            continue
        sec = _read_json(os.path.join(runs, name))
        if "out_of_sample" in sec:
            vs = sec["out_of_sample"]["strategy"]["vs_buy_hold_pct"]
            bl_path = os.path.join(folder, "baselines", name)
            rank = _read_json(bl_path).get("rank") if os.path.isfile(bl_path) else None
        else:
            vs, rank = sec["strategy"]["vs_buy_hold_pct"], None
        items.append({"run": name[:-5], "vs_bh": vs, "rank": rank})
    return len(items), _scored_lines(items)


# --- command line -----------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("fetch", "train", "run", "report"))
    parser.add_argument(
        "--supersede",
        metavar="NOTE",
        help="train and run only: move earlier outputs to superseded/ with this note (what changed and why)",
    )
    args = parser.parse_args(argv)
    if args.supersede and args.command not in ("train", "run"):
        parser.error("--supersede applies to train and run only")
    sandbox()
    try:
        if args.command == "fetch":
            return fetch(PLAN)
        if args.command == "train":
            return train(PLAN, note=args.supersede)
        if args.command == "run":
            return run(PLAN, note=args.supersede)
        return report(PLAN)
    except Stop as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
