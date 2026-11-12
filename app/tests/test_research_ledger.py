"""The programme trial ledger (PTAI-RD-001 C section 5, schema v1; WP 2.1).

* An entry has every schema-v1 field; a trial is written once; a wrong kind, an unknown
  field or a missing id is refused.
* ``sync`` brings in the strategy lab's and the model lab's trial logs once each, and
  leaves both logs byte for byte as they were.
* An engine backtest job writes its own entry, with its job key and its candidate,
  under the same id as its strategy-lab trial, so ``sync`` does not count it again.
* ``counts`` gives the distinct trials per budget; appends from many threads at once
  give one whole line each.

Under the isolation guard (app/conftest.py): every file is in a temporary home.
Synthetic candles and a fake venue (test_strategy_backtest_window): no network."""

from __future__ import annotations

import hashlib
import json
import os
import threading

import pytest
from test_research_engine_strategy_runs import claimed, params
from test_strategy_backtest_window import lab, loader, venue  # noqa: F401

from model_lab import batch
from research_engine import ledger, strategy_runs
from strategy_lab import experiment


def digest(file):
    with open(file, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_an_entry_has_every_field_and_a_trial_is_written_once(tmp_path):
    root = str(tmp_path)
    item = ledger.entry(trial_id="t-1", source="test", kind="exploration")
    item["counted_in"] = "exploration"
    assert set(item) == set(ledger.FIELDS)
    assert item["ledger_version"] == 1 and item["logged_at"]
    assert ledger.append(item, root)
    assert not ledger.append(item, root)  # already there
    assert [e["trial_id"] for e in ledger.entries(root)] == ["t-1"]
    assert ledger.counts(root) == {"exploration": 1}


@pytest.mark.parametrize(
    "change, why",
    [
        ({"kind": "guess"}, "unknown trial kind"),
        ({"trial_id": ""}, "needs a trial_id"),
        ({"counted_in": None}, "needs a counted_in"),
    ],
)
def test_a_wrong_entry_is_refused(tmp_path, change, why):
    item = ledger.entry(
        trial_id="t-1", source="test", kind="exploration", counted_in="exploration"
    )
    item.update(change)
    with pytest.raises(ledger.LedgerError, match=why):
        ledger.append(item, str(tmp_path))
    with pytest.raises(ledger.LedgerError, match="unknown ledger fields"):
        ledger.entry(score=1)


def test_sync_brings_each_trial_in_once_and_leaves_the_logs_as_they_were(
    tmp_path, lab  # noqa: F811
):
    root = str(tmp_path / "engine")
    # an exploratory run (with its run.json), a declared experiment's trial and a
    # model-lab batch trial
    from strategy_lab import runs
    from test_strategy_backtest_window import config

    run = runs.run(config(), loader=loader, venue=venue, now=1_800_000_000)
    experiment.log_trial(
        "SR1-E1", "S1", "strategy", "2021-01-01", "2025-05-06", ["BTC"]
    )
    batch.log_trial(
        {
            "trial": "B-1/trees.q2",
            "batch": "B-1",
            "batch_sha256": "ab" * 32,
            "contestant": "trees.q2",
            "family": "trees",
            "params": {"depth": 3},
            "trades": 12,
            "p": 0.4,
        }
    )
    sources = [experiment.trials_path(), batch.trials_path()]
    before = [digest(f) for f in sources]

    assert ledger.sync(root) == 3
    assert ledger.sync(root) == 0  # each is brought in once
    assert [digest(f) for f in sources] == before  # read only

    by_id = {e["trial_id"]: e for e in ledger.entries(root)}
    explored = by_id[f"strategy_lab:{run['id']}/run"]
    assert (explored["kind"], explored["experiment_id"], explored["member"]) == (
        "exploration",
        "exploration",
        run["id"],
    )
    assert explored["candidates"][0]["id"] == run["strategy"]["id"]
    assert (
        explored["candidates"][0]["params_sha256"] == run["strategy"]["params_sha256"]
    )
    assert explored["seeds"] == [run["config"]["seed"]]
    declared = by_id["strategy_lab:SR1-E1/S1"]
    assert (declared["kind"], declared["counted_in"], declared["analysis"]) == (
        "declared",
        "SR1-E1",
        "strategy",
    )
    assert declared["months"] == {"start": "2021-01-01", "end": "2025-05-06"}
    model = by_id["model_lab:B-1/trees.q2"]
    assert (model["kind"], model["counted_in"], model["family"]) == (
        "declared",
        "B-1",
        "trees",
    )
    assert model["outcome"]["summary"] == {"trades": 12, "p": 0.4}
    assert ledger.counts(root) == {"B-1": 1, "SR1-E1": 1, "exploration": 1}


def test_an_engine_job_writes_its_entry_with_its_key(tmp_path, lab):  # noqa: F811
    store, ctx = claimed(tmp_path, params())
    result = strategy_runs.run_job(params(), ctx, loader=loader, venue=venue)
    (item,) = ledger.entries(store.root)
    assert item["trial_id"] == f"strategy_lab:{result['run_id']}/run"
    assert item["job"] == store.get(ctx.job_id).key
    assert item["kind"] == "exploration" and item["candidates"][0]["id"]
    assert ledger.sync(store.root) == 0  # its strategy-lab trial is the same trial


def test_appends_from_many_threads_are_whole_lines(tmp_path):
    root = str(tmp_path)

    def write(i):
        ledger.append(
            ledger.entry(
                trial_id=f"t-{i}",
                source="test",
                kind="exploration",
                counted_in="exploration",
                outcome={"summary": {"text": "x" * 2000}},
            ),
            root,
        )

    threads = [threading.Thread(target=write, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with open(ledger.path(root), encoding="utf-8") as f:
        lines = [json.loads(line) for line in f]
    assert sorted(e["trial_id"] for e in lines) == sorted(f"t-{i}" for i in range(20))
    assert not os.path.exists(ledger.path(root) + ".lock")
