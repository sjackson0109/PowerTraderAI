"""Port verdict: the four Phase 0 checks (FDS-MDL 3.3) re-run against the ported trainer,
``app/pt_pattern_trainer.py``, through the hub's real launch path, with the Phase 0
isolation. The evidence behind the "Port verdict" section of docs/dev/TRAINER-AUDIT.md.

Not part of the suite: the file name does not match ``test_*.py``, so neither
run_suite.py nor CI collects it. Run it explicitly, under the guard that
app/tests/conftest.py loads, with the test venv, from a clone that nothing else
writes to while it runs (PowerShell):

    $env:PT_AUDIT_OUT = '<evidence.json>'
    $env:PT_AUDIT_LONG_CACHE = '<scratch>\\model1-home\\cache\\candles'
    $env:POWERTRADER_HOME = '<scratch>\\dev-home'
    $env:PYTHON_KEYRING_BACKEND = 'keyring.backends.fail.Keyring'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    python -m pytest app/tests/audit_port_evidence.py -p no:cacheprovider --timeout=3600 -q

Every run starts the trainer the way the Trainers tab does: a hub built by its real
``__init__`` calls ``start_trainer_for_selected_coin``, which launches the default
trainer, pt_pattern_trainer.py, in the coin's folder. The guarded child
(helpers_trainer.CHILD_SITE) blocks the network and records what it saw.

Data: the D, X and T runs use the recorded Binance 1-hour fixtures (BTCUSDT_1h.csv,
ETHUSDT_1h.csv), resampled to the trainer's other timeframes (helpers_candles.resample:
complete bars only). The two L runs use three years of Binance bars for all 7 timeframes
from the candle cache that ``docs/dev/run_backtest_model1.py fetch`` writes
(PT_AUDIT_LONG_CACHE; without it they are skipped, and the evidence says so). Either
way the bars are written to the candle cache under the per-test POWERTRADER_HOME and the
trainer reads them offline (POWERTRADER_CANDLES_OFFLINE=1, set by the guard) over the
window in POWERTRADER_TRAIN_START/END. Every run has PYTHONHASHSEED=0 unless it says
otherwise.

The evidence file has machine-specific path prefixes replaced, and records the SHA-256
and git blob ID of this file, the helpers, the trainer and the fixtures, and which
harness tests passed.

Since FDS-MDL Phase 2 every run also publishes its model with a manifest
(app/model_store.py); each run's row then records the model_id, the validation window
and the held-out metrics from the manifest, and the reported-metrics check tests those
instead of finding none. The trainer as of 28dbe0f (no manifest) still gives the
original FAIL."""

import ast
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import time

import pandas as pd
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for _path in (APP_DIR, TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import helpers_candles as hc  # noqa: E402
import helpers_trainer as ht  # noqa: E402
import model_store  # noqa: E402
import pt_hub  # noqa: E402
import pt_paths  # noqa: E402
import pt_pattern_trainer as ppt  # noqa: E402
from audit_trainer_evidence import (  # noqa: E402
    differing,
    file_identity,
    kinds,
    relative,
    sanitiser,
)
from market_data import candles  # noqa: E402
from market_data.timeframes import (
    bar_open_floor,
    candle_timeframe_seconds,
)  # noqa: E402

TRAINER = os.path.join(pt_paths.program_dir(), "pt_pattern_trainer.py")
BTC_CSV = os.path.join(ht.FIXTURES_DIR, "BTCUSDT_1h.csv")
ETH_CSV = os.path.join(ht.FIXTURES_DIR, "ETHUSDT_1h.csv")
EVIDENCE = {"runs": [], "checks": {}, "tests_passed": []}
MEMORY_ENTRIES = {}  # run label -> {timeframe: memory entries}; compared, not stored
SEED = 7  # the fixed seed of the spec's determinism check
LONG_CACHE = os.environ.get("PT_AUDIT_LONG_CACHE")
LONG_WINDOW = (
    pd.Timestamp("2023-01-01", tz="UTC"),
    pd.Timestamp("2026-01-01", tz="UTC"),
)
WALL_CLOCK_KEYS = ("started_at", "finished_at", "runtime_seconds")
METRIC_PATTERN = re.compile(
    r"accura|valid|held|metric|score|loss|test_|hit.?rate|win.?rate|precision|recall"
    r"|sharpe|\bmae\b|\bmse\b|rmse|\bauc\b|\bf1\b|\bacc\b",
    re.IGNORECASE,
)
# the same words for printed output, without "test_" (pytest's folders contain it)
OUTPUT_PATTERN = re.compile(METRIC_PATTERN.pattern.replace("|test_", ""), re.IGNORECASE)


@pytest.fixture(scope="module", autouse=True)
def evidence_file(tmp_path_factory):
    out = os.environ.get("PT_AUDIT_OUT")
    if not out:
        pytest.skip("set PT_AUDIT_OUT to the evidence JSON path")
    EVIDENCE["environment"] = {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "trainer": file_identity(TRAINER),
        "harness": file_identity(os.path.abspath(__file__)),
        "helpers_trainer": file_identity(os.path.abspath(ht.__file__)),
        "helpers_candles": file_identity(os.path.abspath(hc.__file__)),
        "child_site_sha256": hashlib.sha256(ht.CHILD_SITE.encode("utf-8")).hexdigest(),
        "fixtures": {os.path.basename(p): file_identity(p) for p in (BTC_CSV, ETH_CSV)},
        "hub_default_trainer": pt_hub.DEFAULT_SETTINGS["script_neural_trainer"],
    }
    yield
    EVIDENCE["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    data = sanitiser(tmp_path_factory)(EVIDENCE)
    text = json.dumps(data, indent=1, sort_keys=True) + "\n"
    leaks = re.findall(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\"]+", text)
    assert not leaks, f"user-specific paths left in the evidence: {leaks[:3]}"
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, out)


@pytest.fixture
def records(monkeypatch, tmp_path, isolated_user_dirs):
    monkeypatch.chdir(tmp_path)
    return ht.guard_trainer_children(monkeypatch, tmp_path)


@pytest.fixture
def real_hub(monkeypatch, records):
    hub = ht.build_real_hub(monkeypatch)
    assert hub.proc_trainer_path == TRAINER  # the default, no settings file
    yield hub
    ht.close_hub(hub)
    assert hub.test_callback_errors == []


def fixture_hourly(csv_path, rows=None):
    """The recorded 1-hour bars (optionally a slice of rows), as the candle layer reads
    them."""
    frame = candles.load_candles_csv(csv_path, "1h")
    if rows is not None:
        frame = frame.iloc[rows[0] : rows[1]]
    return frame.reset_index(drop=True)


def window(hourly):
    start = hourly["open_time"].iloc[0]
    end = hourly["open_time"].iloc[-1] + pd.Timedelta(hours=1)
    return start, end


def memory_from(bars, i):
    """The memory upstream stores when the window ends at bar ``i`` and bar ``i + 1`` is
    revealed with no memory matching: the body % of bar ``i``, then the close, high and
    low moves % from bar ``i``'s close to bar ``i + 1``."""
    o, c = bars["open"].tolist(), bars["close"].tolist()
    h, lo = bars["high"].tolist(), bars["low"].tolist()
    body = 100 * ((c[i] - o[i]) / o[i])
    move = ((c[i + 1] - c[i]) / abs(c[i])) * 100
    high = ((h[i + 1] - c[i]) / abs(c[i])) * 100
    low = ((lo[i + 1] - c[i]) / abs(c[i])) * 100
    return f"{body} {move}{{}}{high}{{}}{low}"


def older_half(n):
    return (n + 1) - (n + 1) // 2


def window_bars(pair, tf, start, end):
    """The bars of ``tf`` the trainer can use: from the cache file, opening at or after
    ``start`` and closing by ``end``."""
    frame = candles.load_candles_csv(candles.cache_path(pair, tf), tf)
    step = pd.Timedelta(seconds=candle_timeframe_seconds(tf))
    end_open = pd.Timestamp(
        bar_open_floor(int(end.timestamp()), tf), unit="s", tz="UTC"
    )
    keep = (frame["open_time"] >= start) & (frame["open_time"] < end_open)
    keep &= frame["open_time"] + step <= end
    return frame[keep].reset_index(drop=True)


def expectations(pair, start, end):
    """What the harness predicts from the cache files alone, before the run: the bars per
    timeframe, the 1-hour older half, the first memory every timeframe stores (the
    1-hour pass-0 walk, bars 9 and 10), and the first memory pass 2 stores from each
    timeframe's own bars (used only when nothing can have matched before it)."""
    out = {"bars": {}, "pass2_first_memory": {}}
    for choice, tf in ppt.CANDLE_TF.items():
        bars = window_bars(pair, tf, start, end)
        out["bars"][tf] = len(bars)
        keep = len(bars) if choice in ("1day", "1week") else older_half(len(bars))
        length = int(keep * 0.5)
        if 1 <= length < keep:
            out["pass2_first_memory"][choice] = memory_from(
                bars.iloc[:keep], length - 1
            )
    hourly = window_bars(pair, "1h", start, end)
    out["older_half_1h"] = older_half(len(hourly))
    out["first_memory"] = memory_from(hourly.iloc[: out["older_half_1h"]], 9)
    return out


STDOUT_KEEP = (" pass ", " done:", "train_", "seed:", "offline:", "ERROR", "completed")


def step_counter(steps):
    """The threshold a pass ends on if no step ever had more than 20 matches: 1.0 plus
    0.01 per step (the trainer's rule, replayed float for float)."""
    t = 1.0
    for _ in range(steps):
        t += 0.001 if t < 0.1 else 0.01
        t = min(t, 100.0)
    return t


def threshold_vs_step_counter(summary):
    """Per timeframe: the final (written) threshold and the step-counter value of the
    pass it came from (the last pass that ran)."""
    out = {}
    for tf, v in summary["timeframes"].items():
        ran = [p for p in v["passes"] if not p.get("skipped")]
        counter = step_counter(ran[-1]["steps"]) if ran else None
        out[tf] = {
            "final": v["final_threshold"],
            "step_counter": counter,
            "fell_below_counter": counter is not None
            and v["final_threshold"] != counter,
        }
    return out


def learned_matches(p):
    """Steps of a pass that matched and so stored no memory. Every step but the last
    learns: it either matches or stores one memory (or, with a zero close, learns
    nothing)."""
    if p.get("skipped") or not p["steps"]:
        return 0
    return p["steps"] - 1 - p["new_memories"] - p["unlearned_steps"]


def pass2_trace(summary, entries, expected):
    """The memory pass 2 stores first, against the harness's own computation from the
    timeframe's bars. Applicable only when passes 0 and 1 stayed under the 200-step
    flush (so no memory file existed and the first step could not match) and pass 2
    ran at least two steps."""
    out = {}
    for tf, v in summary["timeframes"].items():
        p0, p1, p2 = v["passes"]
        ok = (
            tf in expected
            and not p2.get("skipped")
            and p2["steps"] >= 2
            and all(p.get("skipped") or p["steps"] < ppt.FLUSH_EVERY for p in (p0, p1))
        )
        index = p0["new_memories"] + p1["new_memories"]
        out[tf] = {
            "applicable": ok,
            "index": index,
            "expected": expected.get(tf),
            "actual": entries[tf][index] if ok and index < len(entries[tf]) else None,
        }
    return out


def train(
    hub,
    records,
    monkeypatch,
    label,
    coin,
    data,
    hourly=None,
    cache_files=None,
    span=None,
    seed=None,
    hash_seed="0",
    timeout=600,
):
    """Put bars in the cache for ``coin`` (``hourly`` resampled to every timeframe, or
    ``cache_files`` copied as they are), then train ``coin`` through the hub over the
    bars' window (or ``span``). Returns the run's evidence row."""
    pair = f"{coin}USDT"
    if hourly is not None:
        hc.seed_cache(candles.cache_dir_default(), pair, hc.all_timeframes(hourly))
        start, end = window(hourly)
    else:
        os.makedirs(candles.cache_dir_default(), exist_ok=True)
        for tf, path in cache_files.items():
            shutil.copyfile(path, candles.cache_path(pair, tf))
        start, end = span
    expected = expectations(pair, start, end)
    monkeypatch.setenv(ppt.ENV_TRAIN_START, start.isoformat())
    monkeypatch.setenv(ppt.ENV_TRAIN_END, end.isoformat())
    monkeypatch.setenv("PYTHONHASHSEED", hash_seed)
    if seed is None:
        monkeypatch.delenv(ppt.ENV_TRAIN_SEED, raising=False)
    else:
        monkeypatch.setenv(ppt.ENV_TRAIN_SEED, str(seed))

    home = os.environ["POWERTRADER_HOME"]
    home_before = ht.tree_snapshot(home)
    program_before = ht.program_folder_state()
    count = len(ht.child_records(records))
    started = time.time()
    lp = ht.launch(hub, coin)
    assert lp is not None, ht.child_errors(records) or "the hub did not keep it"
    code, lines = ht.wait(lp, timeout=timeout)
    seconds = round(time.time() - started, 1)
    new = [r for r in ht.child_records(records)[count:] if r.get("final")]
    assert len(new) == 1, new
    record = new[0]
    assert record["started"] >= started

    folder = hub.coin_folders[coin]
    entries = {}
    for tf in ht.TIMEFRAMES:
        with open(os.path.join(folder, f"memories_{tf}.txt"), encoding="utf-8") as f:
            entries[tf] = f.read().split("~")
    MEMORY_ENTRIES[label] = entries
    memories = {tf: {"count": len(e), "first": e[0]} for tf, e in entries.items()}
    weights_all_one = True
    for tf in ht.TIMEFRAMES:
        for kind in ("memory_weights", "memory_weights_high", "memory_weights_low"):
            with open(os.path.join(folder, f"{kind}_{tf}.txt"), encoding="utf-8") as f:
                text = f.read()
            weights_all_one &= text == " ".join(["1.0"] * memories[tf]["count"])
    thresholds = {}
    for tf in ht.TIMEFRAMES:
        name = f"neural_perfect_threshold_{tf}.txt"
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            thresholds[tf] = f.read()
    results_path = pt_paths.data_file(
        "training_results", f"{coin.lower()}_training_results.json"
    )
    with open(results_path, encoding="utf-8") as f:
        summary = json.load(f)
    dropped = [k for k in WALL_CLOCK_KEYS if summary.pop(k, None) is not None]
    # since FDS-MDL Phase 2: the published model's manifest, verified like a loader does
    model_id = summary.get("model_id")
    manifest = (
        model_store.verify_folder(model_store.model_dir(model_id), model_id)
        if model_id
        else None
    )
    with open(os.path.join(folder, "trainer_status.json"), encoding="utf-8") as f:
        status = json.load(f)
    added, changed, removed = ht.snapshot_changes(home_before, ht.tree_snapshot(home))
    timeframes = summary["timeframes"]
    row = {
        "label": label,
        "coin": coin,
        "data": data,
        "window": [start.isoformat(), end.isoformat()],
        "exit_code": code,
        "seconds": seconds,
        "child": {
            k: record.get(k)
            for k in ("cwd_at_start", "orig_argv", "env", "credential_env")
        },
        "network_blocked_attempts": record["blocked"],
        "model_files_sha256": ht.model_files(folder),
        "memories": memories,
        "expected": {
            "bars_per_timeframe": expected["bars"],
            "older_half_1h": expected["older_half_1h"],
            "first_memory": expected["first_memory"],
        },
        "pass2_first_memory": pass2_trace(
            summary, entries, expected["pass2_first_memory"]
        ),
        "learned_matches_per_pass": {
            tf: [learned_matches(p) for p in v["passes"]]
            for tf, v in timeframes.items()
        },
        "thresholds": thresholds,
        "threshold_vs_step_counter": threshold_vs_step_counter(summary),
        "weights_all_1.0": weights_all_one,
        "status_state": status.get("state"),
        "stamp_written": os.path.isfile(
            os.path.join(folder, "trainer_last_training_time.txt")
        ),
        "training_results": summary,
        "wall_clock_keys_dropped": dropped,
        "model_id": model_id,
        "validation": manifest and manifest["validation"],
        "validation_metrics": manifest and manifest["validation_metrics"],
        "stdout": [ln for ln in lines if any(k in ln for k in STDOUT_KEEP)],
        "stdout_lines": len(lines),
        "metric_like_output_lines": [ln for ln in lines if OUTPUT_PATTERN.search(ln)],
        "home_files_added": relative(added, home),
        "home_files_changed": relative(changed, home),
        "home_files_removed": relative(removed, home),
        "program_folder_unchanged": ht.program_folder_state() == program_before,
    }
    EVIDENCE["runs"].append(row)
    assert code == 0, lines[-20:]
    assert row["network_blocked_attempts"] == []
    assert row["program_folder_unchanged"]
    assert sorted(row["model_files_sha256"]) == ht.expected_model_file_names()
    assert row["status_state"] == "FINISHED" and row["stamp_written"]
    assert record["orig_argv"][1:] == ["-u", "-W", "ignore", TRAINER, coin]
    assert record["env"]["PYTHONHASHSEED"] == hash_seed
    assert record["env"][ppt.ENV_TRAIN_SEED] == (None if seed is None else str(seed))
    assert record["env"][ppt.ENV_CANDLES_OFFLINE] == "1"
    assert record["credential_env"] == []
    assert summary["seed"] == (0 if seed is None else seed)
    # each timeframe trained on its own bars, as many as the cache holds for the window
    assert {tf: summary["candles"][tf]["bars"] for tf in hc.TRAINER_TFS} == expected[
        "bars"
    ]
    # the 1-hour older half, computed here, is what the trainer used
    assert [p["bars_used"] for p in timeframes["1hour"]["passes"]] == [
        expected["older_half_1h"]
    ] * 3
    # every stored memory is accounted for; no zero close in real or fixture bars
    for tf, v in timeframes.items():
        assert memories[tf]["count"] == sum(p["new_memories"] for p in v["passes"]), tf
        assert sum(p["unlearned_steps"] for p in v["passes"]) == 0, tf
    return row


# --- static (FDS-MDL 3.3: sleep in epoch loops, random weights or memories, literal accuracy)


def parents_of(tree):
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[id(child)] = node
    return out


def enclosing(node, parents, kinds_):
    while id(node) in parents:
        node = parents[id(node)]
        if isinstance(node, kinds_):
            return node
    return None


def catches_permission_error(handler):
    if handler is None:
        return False
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(n, ast.Name) and n.id == "PermissionError" for n in names)


def test_static_checks():
    with open(TRAINER, encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    parents = parents_of(tree)
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)
    sleeps, random_uses, accuracy_names, accuracy_strings = [], [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            func = enclosing(node, parents, functions)
            where = {"line": node.lineno, "function": func.name if func else None}
            if node.value.id == "time" and node.attr == "sleep":
                handler = enclosing(node, parents, ast.ExceptHandler)
                where["in_permission_error_handler"] = catches_permission_error(handler)
                sleeps.append(where)
            if node.value.id == "random":
                random_uses.append({**where, "attr": node.attr})
        if isinstance(node, ast.Name) and "accura" in node.id.lower():
            accuracy_names.append({"line": node.lineno, "name": node.id})
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "accura" in node.value.lower()
        ):
            # strings that mention accuracy (docstrings included): reported, not code
            i = node.value.lower().index("accura")
            accuracy_strings.append(
                {"line": node.lineno, "text": node.value[max(0, i - 40) : i + 40]}
            )
    numeric_accuracy = [
        ln
        for ln in source.splitlines()
        if re.search(r"accura\w*\W*[:=]\s*-?\d", ln, re.IGNORECASE)
    ]
    epoch_loops = [
        ln for ln in source.splitlines() if re.search(r"\bepochs?\b", ln, re.I)
    ]
    imports = sorted(
        {
            n.module if isinstance(n, ast.ImportFrom) else a.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in (n.names if isinstance(n, ast.Import) else [n])
        }
    )
    EVIDENCE["checks"]["static"] = {
        "time_sleep": sleeps,
        "random": random_uses,
        "accuracy_names": accuracy_names,
        "accuracy_strings": accuracy_strings,
        "numeric_accuracy_assignments": numeric_accuracy,
        "epoch_mentions": epoch_loops,
        "imports": imports,
    }
    # the only sleep is the retry in the PermissionError handler of the file writer
    assert sleeps and all(
        s["function"] == "_write_text" and s["in_permission_error_handler"]
        for s in sleeps
    ), sleeps
    # random is only seeded (deviation 9); nothing draws from it
    assert {r["attr"] for r in random_uses} == {"seed"}, random_uses
    assert numeric_accuracy == [] and epoch_loops == []
    assert accuracy_names == [], accuracy_names
    assert "market_data.candles" in imports and "pt_data_provider" not in imports
    EVIDENCE["checks"]["static"]["result"] = "PASS"
    EVIDENCE["tests_passed"].append("test_static_checks")


# --- determinism (FDS-MDL 3.3: the same fixture twice with a fixed seed) -----------------


def test_determinism_with_a_fixed_seed(real_hub, records, monkeypatch):
    hub = real_hub
    btc = fixture_hourly(BTC_CSV)

    def run(label, **kw):
        return train(
            hub, records, monkeypatch, label, "BTC", "BTC all", hourly=btc, **kw
        )

    d1 = run("D1 seed 7", seed=SEED)
    d2 = run("D2 seed 7", seed=SEED)
    d3 = run("D3 seed 7, PYTHONHASHSEED 12345", seed=SEED, hash_seed="12345")
    d4 = run("D4 as launched (no seed set)")
    spec = differing(d1, d2)
    EVIDENCE["checks"]["determinism"] = {
        "spec_check": {
            "runs": [d1["label"], d2["label"]],
            "differing_files": len(spec),
        },
        "other_process_hash_seed": {
            "runs": [d1["label"], d3["label"]],
            "differing_files": len(differing(d1, d3)),
        },
        "as_launched_default_seed_0": {
            "runs": [d1["label"], d4["label"]],
            "differing_files": len(differing(d1, d4)),
        },
        "summaries_identical": d1["training_results"]["timeframes"]
        == d2["training_results"]["timeframes"],
    }
    assert spec == [] and differing(d1, d3) == [] and differing(d1, d4) == []
    assert EVIDENCE["checks"]["determinism"]["summaries_identical"]
    EVIDENCE["checks"]["determinism"]["result"] = "PASS"
    EVIDENCE["tests_passed"].append("test_determinism_with_a_fixed_seed")


# --- data dependence (FDS-MDL 3.3: different fixtures; differences trace to the data) -----


def matched_steps(row, tf):
    passes = row["training_results"]["timeframes"][tf]["passes"]
    return [p["matched_steps"] for p in passes]


def bars_used(row, tf):
    return [p["bars_used"] for p in row["training_results"]["timeframes"][tf]["passes"]]


def test_data_dependence(real_hub, records, monkeypatch):
    hub = real_hub
    btc, eth = fixture_hourly(BTC_CSV), fixture_hourly(ETH_CSV)
    half = len(btc) // 2
    early = fixture_hourly(BTC_CSV, (0, half))
    late = fixture_hourly(BTC_CSV, (half, len(btc)))
    assert early["open_time"].iloc[-1] < late["open_time"].iloc[0]  # no overlap
    cases = [
        ("X1 BTC data", "BTC", btc, "BTC all"),
        ("X2 ETH data as BTC", "BTC", eth, "ETH all"),
        ("X3 BTC first half", "BTC", early, f"BTC rows 0-{half - 1}"),
        ("X4 BTC second half", "BTC", late, f"BTC rows {half}-{len(btc) - 1}"),
        ("X5 ETH coin, ETH data", "ETH", eth, "ETH all"),
    ]
    runs = [
        train(hub, records, monkeypatch, label, coin, name, hourly=data, seed=SEED)
        for label, coin, data, name in cases
    ]
    x1, x2, x3, x4, x5 = runs
    pairwise = {}
    for i, a in enumerate(runs):
        for b in runs[i + 1 :]:
            pairwise[f"{a['label']} vs {b['label']}"] = sorted(differing(a, b))
    traced = {}
    for row in runs:
        expected = row["expected"]["first_memory"]
        traced[row["label"]] = {
            "expected_first_memory": expected,
            "every_timeframe_starts_with_it": all(
                m["first"] == expected for m in row["memories"].values()
            ),
            "pass2_first_memory_matches_in": sorted(
                tf
                for tf, t in row["pass2_first_memory"].items()
                if t["applicable"] and t["actual"] == t["expected"]
            ),
            "pass2_first_memory_applicable_in": sorted(
                tf for tf, t in row["pass2_first_memory"].items() if t["applicable"]
            ),
        }
    by_position = {}
    for a, b in ((x1, x2), (x3, x4)):
        per_tf = {}
        for tf in ht.TIMEFRAMES:
            ea, eb = MEMORY_ENTRIES[a["label"]][tf], MEMORY_ENTRIES[b["label"]][tf]
            compared = min(len(ea), len(eb))
            per_tf[tf] = {
                "counts": [len(ea), len(eb)],
                "compared": compared,
                "differ": sum(x != y for x, y in zip(ea, eb)),
            }
        by_position[f"{a['label']} vs {b['label']}"] = per_tf
    matching = {
        tf: {
            "X1 matched_steps per pass": matched_steps(x1, tf),
            "X2 matched_steps per pass": matched_steps(x2, tf),
            "X1 learned matches per pass": x1["learned_matches_per_pass"][tf],
            "X2 learned matches per pass": x2["learned_matches_per_pass"][tf],
            "bars_used equal": bars_used(x1, tf) == bars_used(x2, tf),
            "memories": [x1["memories"][tf]["count"], x2["memories"][tf]["count"]],
        }
        for tf in ht.TIMEFRAMES
    }
    EVIDENCE["checks"]["data_dependence"] = {
        "runs": [r["label"] for r in runs],
        "differing_files_pairwise": {k: len(v) for k, v in pairwise.items()},
        "differing_files_X1_vs_X2": pairwise[f"{x1['label']} vs {x2['label']}"],
        "differing_files_X3_vs_X4": pairwise[f"{x3['label']} vs {x4['label']}"],
        "memory_entries_that_differ_by_position": by_position,
        "memories_traced_to_the_data": traced,
        "matching_X1_vs_X2": matching,
        "weights_all_1.0_in_every_run": all(r["weights_all_1.0"] for r in runs),
        "thresholds_equal_to_the_step_counter_in_every_run": all(
            not t["fell_below_counter"]
            for r in runs
            for t in r["threshold_vs_step_counter"].values()
        ),
    }
    # the same bars give the same model whatever the coin is called
    assert differing(x2, x5) == []
    # different bars, different model files
    assert all(v for k, v in pairwise.items() if k != f"{x2['label']} vs {x5['label']}")
    # the memories carry the data: every compared entry differs, in every timeframe
    for pair in by_position.values():
        assert all(t["differ"] == t["compared"] > 0 for t in pair.values()), pair
    # they trace to the bars: the shared 1-hour pass-0 memory, and the first memory pass
    # 2 stores from each timeframe's own bars, wherever nothing could have matched first
    for t in traced.values():
        assert t["every_timeframe_starts_with_it"], t
        assert (
            t["pass2_first_memory_matches_in"] == t["pass2_first_memory_applicable_in"]
        )
    assert len(traced["X1 BTC data"]["pass2_first_memory_applicable_in"]) == 7
    # beyond copying the bars: on the same 1-hour bar count, the number of steps that
    # matched instead of storing a memory differs between the two coins' data
    one_hour = matching["1hour"]
    assert one_hour["bars_used equal"]
    assert one_hour["X1 learned matches per pass"][2] > 0
    assert (
        one_hour["X1 learned matches per pass"]
        != one_hour["X2 learned matches per pass"]
    )
    assert one_hour["memories"][0] != one_hour["memories"][1]
    EVIDENCE["checks"]["data_dependence"]["result"] = "PASS"
    EVIDENCE["tests_passed"].append("test_data_dependence")


def long_cache_files(pair):
    files = {tf: os.path.join(LONG_CACHE, f"{pair}_{tf}.csv") for tf in hc.TRAINER_TFS}
    missing = [p for p in files.values() if not os.path.isfile(p)]
    assert not missing, missing
    return files


def sha256_of(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_fitted_quantities_on_three_years_of_real_bars(real_hub, records, monkeypatch):
    """L1, L2: BTC and ETH, 2023-01-01 to 2026-01-01, real Binance bars from the candle
    cache that run_backtest_model1.py fetch writes (copied into the per-test home).
    Skipped, and recorded as skipped, without PT_AUDIT_LONG_CACHE."""
    if not LONG_CACHE:
        EVIDENCE["checks"]["three_years"] = "skipped: PT_AUDIT_LONG_CACHE not set"
        pytest.skip("set PT_AUDIT_LONG_CACHE to a fetched candle cache folder")
    rows = []
    sources = {}
    for label, coin in (("L1 BTC, 3 years", "BTC"), ("L2 ETH, 3 years", "ETH")):
        files = long_cache_files(f"{coin}USDT")
        sources[coin] = {os.path.basename(p): sha256_of(p) for p in files.values()}
        rows.append(
            train(
                real_hub,
                records,
                monkeypatch,
                label,
                coin,
                f"{coin}USDT Binance bars, fetched cache",
                cache_files=files,
                span=LONG_WINDOW,
                seed=SEED,
                timeout=1800,
            )
        )
    l1, l2 = rows
    per_tf = {
        tf: {
            "BTC": l1["threshold_vs_step_counter"][tf],
            "ETH": l2["threshold_vs_step_counter"][tf],
            "BTC matched_steps per pass": matched_steps(l1, tf),
            "ETH matched_steps per pass": matched_steps(l2, tf),
            "memories": [l1["memories"][tf]["count"], l2["memories"][tf]["count"]],
        }
        for tf in ht.TIMEFRAMES
    }
    fell = sorted(
        tf
        for tf, v in per_tf.items()
        if v["BTC"]["fell_below_counter"] or v["ETH"]["fell_below_counter"]
    )
    differ = sorted(
        tf for tf, v in per_tf.items() if v["BTC"]["final"] != v["ETH"]["final"]
    )
    EVIDENCE["checks"]["three_years"] = {
        "runs": [r["label"] for r in rows],
        "window": [t.isoformat() for t in LONG_WINDOW],
        "cache_file_sha256": sources,
        "per_timeframe": per_tf,
        "final_thresholds_fell_below_the_step_counter_in": fell,
        "final_thresholds_differ_between_BTC_and_ETH_in": differ,
        "model_files_differing_L1_vs_L2": len(differing(l1, l2)),
        "weights_all_1.0": l1["weights_all_1.0"] and l2["weights_all_1.0"],
    }
    # passes 1-2 run on each timeframe's own bars (pass 0 is the shared 1-hour walk):
    # matching acts there in every timeframe, for both coins
    for tf, v in per_tf.items():
        assert sum(v["BTC matched_steps per pass"][1:]) > 0, tf
        assert sum(v["ETH matched_steps per pass"][1:]) > 0, tf
    # a written threshold responds to the data somewhere, differently for the two coins
    assert set(fell) & set(differ)
    EVIDENCE["tests_passed"].append(
        "test_fitted_quantities_on_three_years_of_real_bars"
    )


# --- reported metrics (FDS-MDL 3.3: held out, or constant across inputs?) ----------------


def key_paths(value, prefix=""):
    """Every key in a JSON value, as a dotted path; list items share one path ([]) and
    timeframe keys are shown as <tf>."""
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ht.TIMEFRAMES or k in hc.TRAINER_TFS:
                k = "<tf>"
            yield f"{prefix}{k}"
            yield from key_paths(v, f"{prefix}{k}.")
    elif isinstance(value, list):
        for v in value:
            yield from key_paths(v, f"{prefix}[].")


def test_reported_metrics():
    """Uses the runs above (they must run first; pytest keeps file order)."""
    runs = [r for r in EVIDENCE["runs"] if r["label"][:1] in "XL"]
    assert len([r for r in runs if r["label"].startswith("X")]) == 5, "run X1-X5 first"
    keys = sorted({k for r in runs for k in key_paths(r["training_results"])})
    metric_keys = [k for k in keys if METRIC_PATTERN.search(k.rsplit(".", 1)[-1])]
    printed = [ln for r in runs for ln in r["metric_like_output_lines"]]
    reported = {
        r["label"]: {
            tf: [v["final_threshold"], v["memories"]]
            for tf, v in r["training_results"]["timeframes"].items()
        }
        for r in runs
        if r["label"].startswith("X")
    }
    distinct = len({json.dumps(v, sort_keys=True) for v in reported.values()})
    result = {
        "every_key_in_the_summary": keys,
        "wall_clock_keys_also_written": list(WALL_CLOCK_KEYS),
        "metric_like_keys": metric_keys,
        "metric_like_output_lines (full output searched)": printed,
        "reported_quantities_per_run (final threshold, memories)": reported,
        "distinct_reported_sets": distinct,
    }
    EVIDENCE["checks"]["reported_metrics"] = result
    # X2 and X5 are the same bars; the other four inputs give four different summaries
    assert distinct == 4, reported
    if not any(r["model_id"] for r in runs):
        # the trainer before FDS-MDL Phase 2 (28dbe0f): nothing is computed
        assert metric_keys == [] and printed == []
        result["result"] = (
            "FAIL: no metric is computed or reported, held out or otherwise"
        )
        EVIDENCE["tests_passed"].append("test_reported_metrics")
        return
    result.update(held_out_metrics(runs))
    result["result"] = (
        "PASS (since FDS-MDL Phase 2): every run publishes metrics scored on the last "
        "20% of its window by a separate fit on the first 80%, whose bars all close by "
        "the cut; they differ between different inputs and repeat for the same bars"
    )
    EVIDENCE["tests_passed"].append("test_reported_metrics")


def held_out_metrics(runs):
    """The Phase 2 metrics of every run: held out by construction, and dependent on the
    data. Asserts both; returns the evidence."""
    windows = {}
    for r in runs:
        assert r["model_id"] and r["validation_metrics"], r["label"]
        v = r["validation"]
        start, end = (pd.Timestamp(t) for t in r["window"])
        cut = pd.Timestamp(v["fit_end"])
        assert (
            pd.Timestamp(v["fit_start"]) == start and v["holdout_start"] == v["fit_end"]
        )
        assert pd.Timestamp(v["holdout_end"]) == end
        # the last 20% of the window, the cut floored to the hour
        assert cut == (start + (end - start) * 0.8).floor("h"), r["label"]
        last_fit_close = max(
            pd.Timestamp(c["last_open"])
            + pd.Timedelta(seconds=candle_timeframe_seconds(tf))
            for tf, c in v["fit_candles"].items()
        )
        first_scored = min(
            pd.Timestamp(c["first_open"]) for c in v["holdout_candles"].values()
        )
        assert last_fit_close <= cut <= first_scored, r["label"]
        assert r["validation_metrics"]["1hour"]["scored_pairs"] > 0, r["label"]
        windows[r["label"]] = {
            "fit": [v["fit_start"], v["fit_end"]],
            "held_out": [v["holdout_start"], v["holdout_end"]],
            "last_fit_bar_closes": last_fit_close.isoformat(),
            "first_scored_bar_opens": first_scored.isoformat(),
            "scored_pairs_1hour": r["validation_metrics"]["1hour"]["scored_pairs"],
        }
    x = {r["label"]: r for r in runs if r["label"].startswith("X")}
    sets = {
        label: json.dumps(r["validation_metrics"], sort_keys=True)
        for label, r in x.items()
    }
    same_bars = sets["X2 ETH data as BTC"] == sets["X5 ETH coin, ETH data"]
    assert same_bars
    assert len(set(sets.values())) == 4
    return {
        "validation_windows": windows,
        "metrics_1hour": {r["label"]: r["validation_metrics"]["1hour"] for r in runs},
        "distinct_metric_sets_X1_X5": len(set(sets.values())),
        "X2_and_X5_metrics_equal (same bars)": same_bars,
    }


# --- the thinker's parse (FDS-MDL 4.5) ----------------------------------------------------

# Expressions of the thinker's parse (app/pt_thinker.py, step_coin) that thinker_reads
# copies; the test checks the thinker still contains them.
THINKER_EXPRESSIONS = (
    "perfect_threshold = float(file.read())",
    '.replace("[", "")\n            .split("~")',
    'memory_list[mem_ind]\n                .split("{}")[0]',
    "memory_candle = float(memory_pattern[check_dex])",
    'memory_list[mem_ind]\n                        .split("{}")[1]',
    'memory_list[mem_ind]\n                        .split("{}")[2]',
    "float(memory_pattern[len(memory_pattern) - 1])",
    "float(weight_list[mem_ind])",
    "float(high_weight_list[mem_ind])",
    "float(low_weight_list[mem_ind])",
)


def squash(text):
    return "".join(text.split())


def test_thinker_parses_the_port_output(real_hub, records, monkeypatch):
    """The thinker's own parse expressions (see test_pattern_trainer.thinker_reads)
    applied to every timeframe the launched trainer wrote. The thinker is not run."""
    from test_pattern_trainer import thinker_reads

    with open(os.path.join(APP_DIR, "pt_thinker.py"), encoding="utf-8") as f:
        thinker = squash(f.read())
    missing = [e for e in THINKER_EXPRESSIONS if squash(e) not in thinker]
    assert missing == [], missing
    row = train(
        real_hub,
        records,
        monkeypatch,
        "T1 for the thinker parse",
        "BTC",
        "BTC all",
        hourly=fixture_hourly(BTC_CSV),
        seed=SEED,
    )
    folder = real_hub.coin_folders["BTC"]
    parsed = {}
    for tf in ht.TIMEFRAMES:
        threshold, memories, weights = thinker_reads(folder, tf)
        assert all(len(w) == len(memories) for w in weights), tf
        parsed[tf] = {"threshold": threshold, "memories": len(memories)}
    EVIDENCE["checks"]["thinker_parse"] = {
        "run": row["label"],
        "thinker_still_contains_the_copied_expressions": True,
        "parsed": parsed,
        "result": "every timeframe parses with the thinker's expressions",
    }
    EVIDENCE["tests_passed"].append("test_thinker_parses_the_port_output")
