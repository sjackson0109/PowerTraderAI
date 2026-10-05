"""Phase 0 trainer audit: the dynamic evidence behind docs/dev/TRAINER-AUDIT.md.

Not part of the suite: the file name does not match ``test_*.py``, so neither
run_suite.py nor CI collects it. Run it explicitly, under the guard that
app/tests/conftest.py loads, with the test venv, from a clone that nothing else
writes to while it runs (PowerShell):

    $env:PT_AUDIT_OUT = '<evidence.json>'
    $env:POWERTRADER_HOME = '<scratch>\\dev-home'
    $env:PYTHON_KEYRING_BACKEND = 'keyring.backends.fail.Keyring'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    python -m pytest app/tests/audit_trainer_evidence.py -p no:cacheprovider --timeout=900 -q

Every run starts the trainer the way the Trainers tab does: a hub built by its
real ``__init__`` calls ``start_trainer_for_selected_coin``. The guarded child
(helpers_trainer.CHILD_SITE) blocks the network and answers the Binance price
ticker from a recorded candle CSV (the last close of the chosen rows), so the
real DataProvider, MultiExchangeManager and BinanceExchange code runs and only
the HTTP response is replaced. Every run has PYTHONHASHSEED=0, so the only
difference between the paired runs is PT_TEST_SEED, which seeds Python's
``random`` before the trainer starts: instrumentation, because the trainer has
no seed of its own. The two candle-provider runs replace pt_data_provider with a
fixture provider (no exchange code runs); they are a counterfactual and do not
decide the verdict.

The evidence file has machine-specific path prefixes replaced (<pytest-tmp>,
<repo>, <venv>, <tmp>, <home>), and records the SHA-256 and git blob ID of this
file, helpers_trainer.py and pt_trainer.py, and which tests passed."""

import csv
import hashlib
import inspect
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for _path in (APP_DIR, TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import helpers_trainer as ht  # noqa: E402
import pt_paths  # noqa: E402

BTC_CSV = os.path.join(ht.FIXTURES_DIR, "BTCUSDT_1h.csv")
ETH_CSV = os.path.join(ht.FIXTURES_DIR, "ETHUSDT_1h.csv")
TICKER = "/api/v3/ticker/price?symbol="
EVIDENCE = {"runs": [], "checks": {}, "tests_passed": []}


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def git_blob(path):
    """The git blob ID the file would have if committed (None without git)."""
    try:
        out = subprocess.run(
            ["git", "hash-object", path],
            cwd=pt_paths.install_dir(),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except OSError:
        return None
    return out.stdout.strip() or None


def file_identity(path):
    return {
        "path": os.path.relpath(path, pt_paths.install_dir()).replace("\\", "/"),
        "sha256_working_tree": sha256_file(path),
        "git_blob": git_blob(path),
    }


def sanitiser(tmp_path_factory):
    """Replace machine-specific path prefixes (longest first) in a string."""
    prefixes = [
        (str(tmp_path_factory.getbasetemp()), "<pytest-tmp>"),
        (pt_paths.install_dir(), "<repo>"),
        (sys.prefix, "<venv>"),
        (tempfile.gettempdir(), "<tmp>"),
        (os.path.expanduser("~"), "<home>"),
    ]
    prefixes.sort(key=lambda p: len(p[0]), reverse=True)
    patterns = []
    for prefix, label in prefixes:
        variants = {prefix, prefix.replace("\\", "/"), prefix.replace("\\", "\\\\")}
        for variant in sorted(variants, key=len, reverse=True):
            patterns.append((re.compile(re.escape(variant), re.IGNORECASE), label))

    def fix(value):
        if isinstance(value, dict):
            return {fix(k): fix(v) for k, v in value.items()}
        if isinstance(value, list):
            return [fix(v) for v in value]
        if isinstance(value, str):
            for pattern, label in patterns:
                value = pattern.sub(label, value)
        return value

    return fix


def coin_free(line):
    """A trainer output line without the hub's "[COIN] " prefix."""
    return line.split("] ", 1)[1] if line.startswith("[") else line


@pytest.fixture(scope="module", autouse=True)
def evidence_file(tmp_path_factory):
    out = os.environ.get("PT_AUDIT_OUT")
    if not out:
        pytest.skip("set PT_AUDIT_OUT to the evidence JSON path")
    EVIDENCE["environment"] = {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "trainer": file_identity(os.path.join(pt_paths.program_dir(), "pt_trainer.py")),
        "harness": file_identity(os.path.abspath(__file__)),
        "helpers": file_identity(os.path.abspath(ht.__file__)),
        "child_site_sha256": hashlib.sha256(ht.CHILD_SITE.encode("utf-8")).hexdigest(),
        "fixtures": {os.path.basename(p): file_identity(p) for p in (BTC_CSV, ETH_CSV)},
    }
    yield
    runs = EVIDENCE["runs"]
    EVIDENCE["checks"]["reported_accuracy"] = {
        "runs": len(runs),
        "distinct_accuracy_line_sets_ignoring_coin_prefix": len(
            {
                tuple(coin_free(ln) for ln in r["stdout"] if "Accuracy" in ln)
                for r in runs
            }
        ),
        "final_accuracy_values": sorted(
            {(r["training_results"] or {}).get("final_accuracy") for r in runs},
            key=str,
        ),
    }
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
    yield hub
    ht.close_hub(hub)
    assert hub.test_callback_errors == []


def relative(paths, root):
    return [os.path.relpath(p, root).replace("\\", "/") for p in paths]


def train(
    hub,
    records,
    monkeypatch,
    label,
    coin,
    csv_path,
    window=None,
    seed=None,
    candles=False,
):
    """One training run through the hub; returns its evidence row."""
    monkeypatch.setenv("PT_TEST_TICKER_CSV", csv_path)
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    for key, value in (
        ("PT_TEST_TICKER_WINDOW", window),
        ("PT_TEST_SEED", seed),
        ("PT_TEST_CANDLES_PROVIDER", "1" if candles else None),
    ):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, str(value))

    home = os.environ["POWERTRADER_HOME"]
    home_before = ht.tree_snapshot(home)
    program_before = ht.program_folder_state()
    count = len(ht.child_records(records))
    started = time.time()
    lp = ht.launch(hub, coin)
    assert lp is not None, ht.child_errors(records) or "the hub did not keep it"
    code, lines = ht.wait(lp, timeout=240)
    seconds = round(time.time() - started, 1)
    new = [r for r in ht.child_records(records)[count:] if r.get("final")]
    assert len(new) == 1, new
    record = new[0]
    # this launch's process (a venv's python.exe on Windows is a launcher that
    # starts the interpreter as a child, so the PIDs differ)
    assert record["started"] >= started

    folder = hub.coin_folders[coin]
    contents = {}
    for kind in ht.MODEL_FILE_KINDS:
        path = os.path.join(folder, f"{kind}_1hour.txt")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                contents[os.path.basename(path)] = f.read()
    results_path = os.path.join(
        pt_paths.data_dir(), "training_results", f"{coin.lower()}_training_results.json"
    )
    results = None
    if os.path.isfile(results_path):
        with open(results_path, encoding="utf-8") as f:
            results = json.load(f)
        results.pop("timestamp", None)  # wall clock, excluded from comparisons
    added, changed, removed = ht.snapshot_changes(home_before, ht.tree_snapshot(home))
    keep = (
        "Accuracy",
        "price points",
        "Latest price data",
        "Data provider initialized",
        "SUCCESS",
        "FAILED",
        "ERROR",
    )
    row = {
        "label": label,
        "coin": coin,
        "exit_code": code,
        "seconds": seconds,
        "child": {
            k: record.get(k)
            for k in (
                "pid",
                "cwd_at_start",
                "orig_argv",
                "env",
                "credential_env",
                "seed",
                "ticker_csv",
                "ticker_window",
                "ticker_price",
                "candles_provider",
            )
        },
        "requests_served": record["served"],
        "network_blocked_attempts": record["blocked"],
        "model_files_sha256": ht.model_files(folder),
        "model_file_contents_1hour": contents,
        "training_results": results,
        "stdout": [ln for ln in lines if any(k in ln for k in keep)],
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
    assert record["seed"] == (None if seed is None else str(seed))
    assert record["env"]["PYTHONHASHSEED"] == "0"
    return row


def differing(a, b):
    fa, fb = a["model_files_sha256"], b["model_files_sha256"]
    return sorted(n for n in set(fa) | set(fb) if fa.get(n) != fb.get(n))


def kinds(names):
    return sorted({n.rsplit("_", 1)[0] for n in names})


def assert_real_provider_run(row):
    """The run went through the real DataProvider and BinanceExchange: 8 ticker
    requests (the 1-hour call and one per timeframe), and the trainer counted
    the characters of the provider's one-candle string as "price points"."""
    assert len(row["requests_served"]) == 8
    assert all(TICKER in url for url in row["requests_served"])
    price = float(row["child"]["ticker_price"])
    stamp = "1" * 13  # any 13-digit epoch-ms value has the same length
    n = len(f"[[{stamp}, {price}, {price}, {price}, {price}, 1000]]")
    assert any(f"Successfully retrieved {n} price points" in ln for ln in row["stdout"])
    assert any("Latest price data: ]" in ln for ln in row["stdout"])
    assert any("Multi-exchange (binance)" in ln for ln in row["stdout"])
    assert row["seconds"] >= 35  # 7 timeframes x 10 epochs x time.sleep(0.5)
    return n


def test_determinism_as_launched_and_with_a_seeded_rng(real_hub, records, monkeypatch):
    """FDS-MDL 3.3 determinism: the same fixture twice, as launched (the trainer
    has no seed) and with Python's random seeded from outside."""
    hub = real_hub
    u1 = train(hub, records, monkeypatch, "D1 unseeded", "BTC", BTC_CSV)
    u2 = train(hub, records, monkeypatch, "D2 unseeded", "BTC", BTC_CSV)
    s1 = train(hub, records, monkeypatch, "D3 seeded", "BTC", BTC_CSV, seed=0)
    s2 = train(hub, records, monkeypatch, "D4 seeded", "BTC", BTC_CSV, seed=0)

    unseeded_diff = differing(u1, u2)
    seeded_diff = differing(s1, s2)
    EVIDENCE["checks"]["determinism_as_launched"] = {
        "runs": ["D1 unseeded", "D2 unseeded"],
        "differing_files": len(unseeded_diff),
        "differing_kinds": kinds(unseeded_diff),
        "result": "FAIL: two runs on the same data differ; the trainer has no seed",
    }
    EVIDENCE["checks"]["determinism_fixed_seed_spec_check"] = {
        "runs": ["D3 seeded", "D4 seeded"],
        "differing_files": len(seeded_diff),
        "result": "identical only with Python's random seeded from outside the "
        "trainer, which exposes no seed of its own",
    }
    # memories and weights are random each run; thresholds are not
    assert kinds(unseeded_diff) == [
        "memories",
        "memory_weights",
        "memory_weights_high",
        "memory_weights_low",
    ]
    assert seeded_diff == []
    counts = {row["label"]: assert_real_provider_run(row) for row in (u1, u2, s1, s2)}
    EVIDENCE["checks"]["price_points_is_a_character_count"] = counts
    EVIDENCE["tests_passed"].append(
        "test_determinism_as_launched_and_with_a_seeded_rng"
    )


def test_data_dependence_with_a_seeded_rng(real_hub, records, monkeypatch):
    """FDS-MDL 3.3 data dependence: different data, same seed. Any difference
    would have to come from the data. The real provider passes the trainer one
    value per request (a price), so each run is fed a different price: the last
    close of the chosen fixture rows."""
    hub = real_hub
    half, end = 756, 1512  # X4 stops one bar early, so no two runs share a close
    runs = [
        train(hub, records, monkeypatch, "X1 BTC data", "BTC", BTC_CSV, seed=0),
        train(hub, records, monkeypatch, "X2 ETH data as BTC", "BTC", ETH_CSV, seed=0),
        train(
            hub,
            records,
            monkeypatch,
            "X3 BTC rows 0-755",
            "BTC",
            BTC_CSV,
            window=f":{half}",
            seed=0,
        ),
        train(
            hub,
            records,
            monkeypatch,
            "X4 BTC rows 756-1511",
            "BTC",
            BTC_CSV,
            window=f"{half}:{end}",
            seed=0,
        ),
        train(
            hub, records, monkeypatch, "X5 ETH coin, ETH data", "ETH", ETH_CSV, seed=0
        ),
    ]
    prices = [r["child"]["ticker_price"] for r in runs]
    # the BTC coin was fed four different prices; X5 differs from X1 in coin and data
    assert len(set(prices[:4])) == 4, prices
    assert prices[4] != prices[0], prices
    for row in runs:
        assert_real_provider_run(row)
    diffs = {r["label"]: differing(runs[0], r) for r in runs[1:]}
    EVIDENCE["checks"]["data_dependence"] = {
        "runs": [r["label"] for r in runs],
        "ticker_prices": prices,
        "differing_files_vs_X1": {k: len(v) for k, v in diffs.items()},
        "result": "FAIL" if not any(diffs.values()) else "PASS",
    }
    assert all(v == [] for v in diffs.values()), diffs
    EVIDENCE["tests_passed"].append("test_data_dependence_with_a_seeded_rng")


def expected_memories(csv_path):
    """The first 50 one-step % changes of the last 100 closes, as the trainer
    formats them (app/pt_trainer.py, _create_neural_files_for_timeframe)."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        closes = [float(r["close"]) for r in csv.DictReader(f)][-100:]
    return ",".join(
        f"{((closes[i] - closes[i - 1]) / closes[i - 1]) * 100:.6f}"
        for i in range(1, 51)
    )


def test_counterfactual_candle_provider(real_hub, records, monkeypatch):
    """Counterfactual (not the verdict): a fixture provider gives the trainer
    1-hour candles in the list form it parses (None for the other timeframes,
    so the trainer reuses the 1-hour candles for them). Memories then copy the
    data; weights and thresholds still do not depend on it."""
    hub = real_hub
    p = train(
        hub,
        records,
        monkeypatch,
        "C1 candles BTC",
        "BTC",
        BTC_CSV,
        seed=0,
        candles=True,
    )
    q = train(
        hub,
        records,
        monkeypatch,
        "C2 candles ETH as BTC",
        "BTC",
        ETH_CSV,
        seed=0,
        candles=True,
    )
    diff = differing(p, q)
    assert kinds(diff) == ["memories"], diff
    for row, csv_path in ((p, BTC_CSV), (q, ETH_CSV)):
        assert all(u.startswith("candles:") for u in row["requests_served"])
        memories = {
            h for n, h in row["model_files_sha256"].items() if n.startswith("memories_")
        }
        assert len(memories) == 1  # every timeframe got the same copy of the data
        expected = expected_memories(csv_path)
        assert row["model_file_contents_1hour"]["memories_1hour.txt"] == expected
    EVIDENCE["checks"]["counterfactual_candle_provider"] = {
        "runs": ["C1 candles BTC", "C2 candles ETH as BTC"],
        "differing_kinds": kinds(diff),
        "memories_equal_raw_pct_changes_of_last_100_closes": True,
        "memories_identical_across_the_7_timeframes": True,
    }
    EVIDENCE["tests_passed"].append("test_counterfactual_candle_provider")


# The thinker's own parse of these files, copied verbatim from app/pt_thinker.py
# (step_coin). test_thinker_cannot_parse_the_trainer_output checks that both the
# source and the function below contain these expressions.
THINKER_MEMORIES = """.replace("'", "")
            .replace(",", "")
            .replace('"', "")
            .replace("]", "")
            .replace("[", "")
            .split("~")"""
THINKER_PATTERN = """.split("{}")[0]
                .replace("'", "")
                .replace(",", "")
                .replace('"', "")
                .replace("]", "")
                .replace("[", "")
                .split(" ")"""
THINKER_CANDLE = "memory_candle = float(memory_pattern[check_dex])"


def thinker_first_memory_candle(memories_text):
    memory_list = (
        memories_text.replace("'", "")
        .replace(",", "")
        .replace('"', "")
        .replace("]", "")
        .replace("[", "")
        .split("~")
    )
    mem_ind = 0
    memory_pattern = (
        memory_list[mem_ind]
        .split("{}")[0]
        .replace("'", "")
        .replace(",", "")
        .replace('"', "")
        .replace("]", "")
        .replace("[", "")
        .split(" ")
    )
    check_dex = 0
    memory_candle = float(memory_pattern[check_dex])
    return memory_candle


def squash(text):
    return "".join(text.split())


def test_thinker_cannot_parse_the_trainer_output(real_hub, records, monkeypatch):
    """Reproduction (the thinker is not run): the thinker's parse expressions
    applied to the memories file the launched trainer writes."""
    with open(os.path.join(APP_DIR, "pt_thinker.py"), encoding="utf-8") as f:
        source = squash(f.read())
    copy = squash(inspect.getsource(thinker_first_memory_candle))
    for snippet in (THINKER_MEMORIES, THINKER_PATTERN, THINKER_CANDLE):
        assert squash(snippet) in source
        assert squash(snippet) in copy

    row = train(
        real_hub, records, monkeypatch, "T1 for the thinker parse", "BTC", BTC_CSV
    )
    memories = row["model_file_contents_1hour"]["memories_1hour.txt"]
    with pytest.raises(ValueError) as caught:
        thinker_first_memory_candle(memories)
    # the same first-memory parse accepts the upstream format
    # (pattern{}high{}low entries joined by ~)
    upstream = "0.5 0.25 -0.1{}1.2{}-0.8~0.3{}0.9{}-0.4"
    assert thinker_first_memory_candle(upstream) == 0.5
    EVIDENCE["checks"]["thinker_parse"] = {
        "run": "T1 for the thinker parse",
        "error": f"{type(caught.value).__name__}: {str(caught.value)[:120]}",
        "upstream_format_control": "parses",
    }
    EVIDENCE["tests_passed"].append("test_thinker_cannot_parse_the_trainer_output")
