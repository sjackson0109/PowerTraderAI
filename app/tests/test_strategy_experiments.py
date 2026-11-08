"""FDS-SR-001 milestone M4b: experiment records, the trial log, strategy looks and the
reserved months (sections 5.9, 6.1 and 12).

* A research run may read only the development period: the lockbox and every month
  after it are refused.
* The strategy looks: STRAT-001's and STRAT-002's earlier reads cover the lockbox; the
  new strategies have none, only related entry signals.
* A frozen experiment holds every parameter, the code's hashes and the libraries, and is
  refused once its record, code, libraries or candles change; it is never overwritten.
* The trial log counts distinct trials by kind and refuses an unknown kind.

No candles, no network: records only."""

from __future__ import annotations

import json
import os

import pytest

from strategy_lab import experiment as ex
from strategy_lab import looks
from strategy_lab.windows import DEVELOPMENT, LOCKBOX, ReservedPeriod, development_only


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "lab_dir", lambda: str(tmp_path / "strategy_lab"))
    return tmp_path / "strategy_lab"


def declaration(**changes):
    d = {
        "family": "S",
        "members": ["S1"],
        "strategy": ex.strategy_record(
            "STRAT-004", {"entry_days": 30}, [{"id": "OVL-ATR"}]
        ),
        "market": {
            "exchanges": ["coinbase", "kraken"],
            "coins": ["BTC", "ETH"],
            "series_sha256": {"BTC:1d": "aa", "ETH:1d": "bb"},
        },
        "windows": {"development": [str(DEVELOPMENT[0]), str(DEVELOPMENT[1])]},
        "costs": {"taker": 0.005, "allowance": 0.0005, "source": "stated"},
        "accounts": {"gbp": [50, 500, 10000], "gbp_usd": 1.25},
        "baselines": {"REF-RANDOM": {"seed": 300000, "draws": 10000}},
        "tests": {
            "S1": "return per capital-day against REF-RANDOM",
            "correction": "Holm",
        },
    }
    d.update(changes)
    return d


class TestWindows:
    def test_development_is_allowed_and_the_reserved_months_are_not(self):
        a, b = development_only("2021-01-01", "2025-05-06")
        assert (a, b) == DEVELOPMENT
        with pytest.raises(ReservedPeriod, match="reserved months begin"):
            development_only("2024-01-01", "2025-05-07")
        with pytest.raises(ReservedPeriod):
            development_only(LOCKBOX[0], LOCKBOX[1])
        with pytest.raises(ValueError):
            development_only("2024-01-01", "2023-01-01")
        with pytest.raises(ValueError):
            development_only("2019-06-01", "2021-01-01")


class TestLooks:
    def test_the_existing_strategies_have_seen_the_lockbox(self):
        for sid in ("STRAT-001", "STRAT-002"):
            assert looks.seen(sid, LOCKBOX[0], LOCKBOX[1]), sid
        assert len(looks.seen("STRAT-001", DEVELOPMENT[0], DEVELOPMENT[1])) == 2

    def test_the_new_strategies_have_no_looks_only_related_signals(self):
        for sid, rule in (("STRAT-004", "rule.high20"), ("STRAT-005", "rule.mom14")):
            assert looks.seen(sid, DEVELOPMENT[0], LOCKBOX[1]) == []
            related = looks.related(sid)
            assert [r.key for r in related] == [rule]
            assert related[0].end == "2025-05-06"  # the walk-forward only


class TestRecords:
    def test_a_strategy_record_holds_every_parameter_and_its_hash(self):
        rec = ex.strategy_record("STRAT-004", {"entry_days": 30}, [{"id": "OVL-ATR"}])
        assert rec["params"] == {"entry_days": 30, "exit_days": 20}
        assert rec["version"] == "1.0.0"
        assert rec["overlays"] == [
            {
                "id": "OVL-ATR",
                "version": "1.0.0",
                "params": {"atr_len": 14, "mult": 2.5},
            }
        ]
        same = ex.strategy_record("STRAT-004", {"entry_days": 30, "exit_days": 20})
        assert same["params_sha256"] == rec["params_sha256"]
        assert ex.strategy_record("STRAT-004")["params_sha256"] != rec["params_sha256"]

    def test_the_code_hash_covers_the_strategy_packages(self):
        names = ex.code_hashes()
        for name in (
            "strategies/breakout.py",
            "strategy_lab/candidates.py",
            "signal_fusion/evaluation/replay.py",
            "backtest/engine.py",
            "position_sizing.py",
        ):
            assert name in names


class TestFreezing:
    def test_freeze_writes_a_sealed_record_once(self, lab):
        record = ex.freeze("e1", declaration(), now=1_800_000_000)
        path = lab / "experiments" / "e1" / "experiment.json"
        assert path.exists()
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk == record
        assert record["spec"] == "FDS-SR-001" and record["spec_version"] == "1"
        assert record["code"] and "numpy" in record["libraries"]
        with pytest.raises(ex.ExperimentError, match="already frozen"):
            ex.freeze("e1", declaration())

    def test_an_incomplete_declaration_is_refused(self, lab):
        d = declaration()
        del d["baselines"]
        with pytest.raises(ex.ExperimentError, match="missing"):
            ex.freeze("e2", d)
        with pytest.raises(ex.ExperimentError, match="usable experiment id"):
            ex.freeze("a/b", declaration())

    def test_verify_refuses_any_change(self, lab, monkeypatch):
        ex.freeze("e3", declaration())
        series = {"BTC:1d": "aa", "ETH:1d": "bb"}
        assert ex.verify("e3", series)["id"] == "e3"
        with pytest.raises(ex.ExperimentError, match="candles changed"):
            ex.verify("e3", {"BTC:1d": "aa", "ETH:1d": "cc"})

        path = lab / "experiments" / "e3" / "experiment.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        edited = dict(data, members=["S1", "S9"])
        path.write_text(json.dumps(edited), encoding="utf-8")
        with pytest.raises(ex.ExperimentError, match="record has been edited"):
            ex.verify("e3")
        path.write_text(json.dumps(data), encoding="utf-8")

        real = ex.code_hashes()
        monkeypatch.setattr(
            ex, "code_hashes", lambda: {**real, "strategies/breakout.py": "0" * 64}
        )
        with pytest.raises(ex.ExperimentError, match="code changed .*breakout"):
            ex.verify("e3")
        monkeypatch.setattr(ex, "code_hashes", lambda: real)
        monkeypatch.setattr(ex, "library_versions", lambda: {"numpy": "0.0"})
        with pytest.raises(ex.ExperimentError, match="libraries changed"):
            ex.verify("e3")


class TestTrials:
    def test_trials_are_counted_by_kind_once_each(self, lab):
        ex.log_trial("e1", "S1", "strategy", "2021-01-01", "2025-05-06", ["ETH", "BTC"])
        ex.log_trial("e1", "S1", "strategy", "2021-01-01", "2025-05-06", ["BTC"])
        ex.log_trial("run-7", "run", "exploration", "2022-01-01", "2023-01-01", ["BTC"])
        counts = ex.trial_counts()
        assert counts["strategy"] == 1 and counts["exploration"] == 1
        assert counts["model"] == 0
        lines = ex.trials()
        assert lines[0]["coins"] == ["BTC", "ETH"]
        assert os.path.basename(ex.trials_path()) == "trials.jsonl"

    def test_an_unknown_kind_is_refused(self, lab):
        with pytest.raises(ex.ExperimentError, match="unknown trial kind"):
            ex.log_trial("e1", "S1", "trading", "2021-01-01", "2025-05-06", ["BTC"])
