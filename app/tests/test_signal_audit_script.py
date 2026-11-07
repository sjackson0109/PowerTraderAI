"""The audit script end to end (FDS-SIG-001 section 12; the PR #228 follow-up review):
register, freeze, fetch, run, verify, a defect fix after results, and a cancellation
and its replacement before results, on a throwaway git repository with a fake
exchange. The script is ``docs/dev/run_signal_audit.py``, loaded with its repository
pointed at the throwaway one; the code it runs is this checkout's.

No network: the exchange is a fake behind a real ExchangeManager.
"""

import gzip
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
REPO_DIR = os.path.dirname(APP_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from pt_exchange_abstraction import ExchangeManager, ExchangeType  # noqa: E402
from signal_audit import evidence, round_one  # noqa: E402
from signal_audit import registration as reg  # noqa: E402
from signal_audit import stats as st  # noqa: E402

UTC = timezone.utc
H = 3_600_000
START = datetime(2026, 10, 5, tzinfo=UTC)  # after the earliest start, ended by now
END = datetime(2026, 10, 12, tzinfo=UTC)
START_MS = int(START.timestamp() * 1000)
END_MS = int(END.timestamp() * 1000)


def _git(repo, *args, when=None):
    env = dict(os.environ)
    if when is not None:
        stamp = when.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout


def _commit(repo, when, msg):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg, when=when)


def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


class FakeExchange:
    name = "kucoin"

    def __init__(self):
        self.rows = {}
        for seed, coin in enumerate(("AAA", "BTC")):
            rng = np.random.default_rng(seed)
            first = START_MS - 10 * 24 * H
            n = (END_MS + 2 * 24 * H - first) // H
            close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
            rows = []
            for i in range(n):
                c = float(close[i])
                o = float(close[i - 1]) if i else c
                hi, lo = max(o, c) * 1.002, min(o, c) * 0.998
                rows.append([first + i * H, o, hi, lo, c, float(rng.uniform(1, 9))])
            self.rows[coin] = rows

    def market_symbol(self, symbol):
        return symbol.split("-")[0] + "-USDT"

    def candle_timeframes(self):
        return frozenset({"1h"})

    def max_history_bars(self, tf):
        return None

    def candles(self, symbol, tf, start_ms, end_ms):
        return [
            list(r)
            for r in self.rows[symbol.split("-")[0]]
            if start_ms <= r[0] <= end_ms
        ]


@pytest.fixture
def audit(tmp_path, monkeypatch):
    """The script, run against a throwaway repository, with a sandboxed home."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "audit@example.invalid")
    _git(repo, "config", "user.name", "audit test")
    _git(repo, "config", "commit.gpgsign", "false")
    _write(repo / "app" / "code.py", "x = 1\n")
    _write(repo / "docs" / "dev" / "run_signal_audit.py", "# the script\n")
    _commit(repo, datetime(2026, 10, 1, tzinfo=UTC), "code")
    spec = importlib.util.spec_from_file_location(
        "run_signal_audit_under_test",
        os.path.join(REPO_DIR, "docs", "dev", "run_signal_audit.py"),
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    monkeypatch.setattr(script, "REPO", str(repo))
    monkeypatch.setenv("POWERTRADER_HOME", str(tmp_path / "home"))
    fake = FakeExchange()
    manager = ExchangeManager()
    manager.exchanges[ExchangeType("kucoin")] = fake
    manager.primary_exchange = ExchangeType("kucoin")
    monkeypatch.setattr(script, "_manager", lambda: manager)
    return script, repo, fake


def registration(n=1, start=START, end=END, **extra):
    cands = round_one.candidates()
    rows = reg.family_rows(cands, ["AAA"], ["1h", "4h"], "kucoin")
    record = {
        "round": n,
        "exchange": "kucoin",
        "coins": ["AAA"],
        "input_coins": [round_one.INPUT_COIN],
        "timeframes": ["1h", "4h"],
        "window": {"start": reg.iso(start), "end": reg.iso(end)},
        "candidates": [c.registration() for c in cands],
        "rows": [k.to_dict() for k in rows],
        "family": {"size": reg.family_size(rows), "error": st.FAMILY_ERROR},
        "dependence": {"bootstrap_draws": 300, "seed": 7},
        "power": {"mde_sims_per_run": 0, "mde_runs": 0},
    }
    record.update(extra)
    return record


def register_and_freeze(repo, n, record, when):
    rel = repo / "docs" / "dev" / "sig-audit" / f"round-{n}"
    _write(rel / "registration.json", json.dumps(record, indent=1) + "\n")
    _commit(repo, when, f"round {n}: registration")
    _write(rel / "freeze.json", json.dumps({"round": n}) + "\n")
    _commit(repo, when + timedelta(hours=1), f"round {n}: freeze")


def test_fetch_run_and_verify_from_committed_snapshots(audit):
    script, repo, fake = audit
    register_and_freeze(repo, 1, registration(), datetime(2026, 10, 2, tzinfo=UTC))
    data = script.fetch(1)
    folder = repo / "docs" / "dev" / "sig-audit" / "round-1"
    # D11: compressed snapshots in the round's folder, for the results commit
    snaps = sorted(os.listdir(folder / "candles"))
    assert snaps == ["AAA_1h.csv.gz", "AAA_4h.csv.gz", "BTC_1h.csv.gz", "BTC_4h.csv.gz"]
    assert data["snapshots"] == "docs/dev/sig-audit/round-1/candles"
    for f in data["files"].values():
        with open(folder / "candles" / f["snapshot"], "rb") as fh:
            packed = fh.read()
        assert (
            reg.file_sha256(str(folder / "candles" / f["snapshot"])) == f["file_sha256"]
        )
        assert (
            evidence.bars_sha256(
                [
                    tuple([int(x[0])] + [float(v) for v in x[1:]])
                    for x in (
                        line.split(",")
                        for line in gzip.decompress(packed).decode().splitlines()[1:]
                    )
                ]
            )
            == f["sha256"]
        )
    results = script.run(1)
    assert results["state"]["packages"]["numpy"]
    _commit(repo, datetime(2026, 11, 1, tzinfo=UTC), "round 1: results")
    # anyone with the repo re-derives the results from the committed snapshots
    report = script.verify(1)
    assert report["results"] == "re-derived from the snapshots: identical"
    assert script.verify(1, refetch=True)["exchange"].startswith(
        "every snapshot agrees"
    )
    # a later correction at the exchange is found, not hidden
    i = next(k for k, r in enumerate(fake.rows["AAA"]) if r[0] == START_MS + 5 * H)
    fake.rows["AAA"][i][4] *= 1.01
    with pytest.raises(script.Stop, match="differ from the snapshots"):
        script.verify(1, refetch=True)
    # a tampered snapshot is found without the exchange
    path = folder / "candles" / "BTC_4h.csv.gz"
    packed = path.read_bytes()
    path.write_bytes(packed[:-9] + bytes([packed[-9] ^ 1]) + packed[-8:])
    with pytest.raises(script.Stop, match="differs from its record"):
        script.verify(1)


def test_a_defect_fix_after_results_keeps_the_earlier_results(audit):
    script, repo, _fake = audit
    register_and_freeze(repo, 1, registration(), datetime(2026, 10, 2, tzinfo=UTC))
    script.fetch(1)
    first = script.run(1)
    _commit(repo, datetime(2026, 11, 1, tzinfo=UTC), "round 1: results")
    # the defect fix, committed after results
    _write(repo / "app" / "code.py", "x = 2  # the fix\n")
    _commit(repo, datetime(2026, 11, 2, tzinfo=UTC), "fix")
    with pytest.raises(reg.Refused, match="needs --supersede"):
        script.run(1)
    second = script.run(1, supersede="the fix: what changed and why")
    folder = repo / "docs" / "dev" / "sig-audit" / "round-1"
    kept = [d for d in os.listdir(folder / "superseded")]
    assert len(kept) == 1 and kept[0].startswith("1-")
    old = json.loads((folder / "superseded" / kept[0] / "results.json").read_text())
    assert old["state"]["head"] == first["state"]["head"]
    assert (folder / "superseded" / kept[0] / "series").is_dir()
    assert second["state"]["supersede"] == "the fix: what changed and why"
    assert second["state"]["frozen_files_changed_since_freeze"] == ["app/code.py"]
    # the report shows the earlier verdict beside the new one
    text = (repo / "docs" / "dev" / "SIG-AUDIT-REPORT-round-1.md").read_text(
        encoding="utf-8"
    )
    assert "the fix: what changed and why" in text
    # the fixed results re-derive with the fixed code, and only with it
    assert script.verify(1)["results"] == "re-derived from the snapshots: identical"
    _write(repo / "app" / "code.py", "x = 3  # later work\n")
    _commit(repo, datetime(2026, 11, 4, tzinfo=UTC), "later work")
    with pytest.raises(script.Stop, match="not the code that produced"):
        script.verify(1)


def test_cancel_then_replace_before_results(audit):
    script, repo, _fake = audit
    window_start = datetime(2026, 12, 1, tzinfo=UTC)  # not started
    register_and_freeze(
        repo,
        1,
        registration(start=window_start, end=window_start + timedelta(days=200)),
        datetime(2026, 11, 2, tzinfo=UTC),
    )
    with pytest.raises(script.Stop, match="already has a committed registration"):
        script.draft(1, "2027-08-01T00:00:00Z")
    record = script.cancel(1, "SIG-A reads the high and low swapped")
    assert record["window_started"] is False and record["results"] is None
    _commit(repo, datetime(2026, 11, 3, tzinfo=UTC), "round 1: cancellation")
    with pytest.raises(reg.Refused, match="was cancelled"):
        script.run(1)
    with pytest.raises(reg.Refused, match="already cancelled"):
        script.cancel(1, "again")
    # the replacement: a new round, its own ranking, naming the cancelled one
    ranking = {
        "coins": ["AAA"],
        "exchange": "kucoin",
        "exchanges_considered": [{"exchange": "kucoin", "answer": "chosen"}],
        "ranking_date": "2026-11-05",
        "fetched_at": "2026-11-06T09:00:00Z",
        "measure": "turnover",
        "universe": "every spot market kucoin lists against USDT, any status",
        "exclusions": {},
        "raw_answers": {"file_sha256": "0" * 64},
        "replacements": [],
    }
    _write(
        repo / "docs" / "dev" / "sig-audit" / "round-2" / "ranking" / "ranking.json",
        json.dumps(ranking),
    )
    drafted = script.draft(2, "2027-08-01T00:00:00Z", replaces=1)
    assert drafted["replaces"]["round"] == 1
    assert drafted["replaces"]["cancellation_sha256"] == reg.file_sha256(
        str(repo / "docs" / "dev" / "sig-audit" / "round-1" / "cancellation.json")
    )
    assert drafted["replaces"]["window_started_when_cancelled"] is False
    assert reg.parse_time(drafted["window"]["start"]) > datetime.now(UTC)
    with pytest.raises(script.Stop, match="round 1 is cancelled"):
        script.draft(1, "2027-08-01T00:00:00Z")
