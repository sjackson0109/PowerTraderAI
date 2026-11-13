"""PTAI-RD-001 WP 5.4: model-lab batches as research engine jobs (``model_lab.batch``).

* The job runs a frozen batch as ``model_lab.batch.run`` does, with its results and
  report, and brings the batch's trials into the programme trial ledger.
* Its progress is the batch's stage; asked to stop, the batch stops and the job says
  so; a batch whose code changed since it was frozen is refused.
* Every engine kind is known in a process that imported none of their modules.

A small frozen batch on synthetic cached candles (test_model_lab.frozen_batch): no
network."""

from __future__ import annotations

import pytest
from test_model_lab import frozen_batch, layer  # noqa: F401

from model_lab import batch
from research_engine import jobs, ledger, model_batches
from research_engine.jobs import JobContext, StopRequested
from research_engine.store import JobStore

KEYS = ["rule.sma20", "rule.sma50"]


def claimed(tmp_path, params):
    store = JobStore(str(tmp_path / "engine"))
    job, _ = store.submit("model_lab.batch", params, 0)
    store.claim_next()
    return store, JobContext(store, job.id, 0, None)


def test_a_job_runs_the_frozen_batch_and_ledgers_its_trials(tmp_path):
    batch_id = frozen_batch(keys=KEYS, draws=50)
    store, ctx = claimed(tmp_path, {"batch_id": batch_id})
    result = model_batches.run_job({"batch_id": batch_id}, ctx)
    assert batch.read_status(batch_id)["state"] == "done"
    assert result["batch_id"] == batch_id
    assert result["contestants"] == len(batch.read_results(batch_id)["contestants"])
    assert sum(result["verdicts"].values()) == result["contestants"]
    trials = [e for e in ledger.entries(store.root) if e["source"] == "model_lab"]
    assert result["ledger_trials_added"] == len(trials) > 0
    assert {e["experiment_id"] for e in trials} == {batch_id}
    assert all(e["kind"] == "declared" for e in trials)
    job = store.get(ctx.job_id)
    assert job.progress > 0 and job.progress_note


def test_a_job_asked_to_stop_stops_the_batch(tmp_path):
    batch_id = frozen_batch(keys=KEYS, draws=50)
    store, ctx = claimed(tmp_path, {"batch_id": batch_id})
    calls = {"n": 0}

    def should_stop():
        calls["n"] += 1
        return calls["n"] > 30

    ctx.should_stop = should_stop
    with pytest.raises(StopRequested):
        model_batches.run_job({"batch_id": batch_id}, ctx)
    assert batch.read_status(batch_id)["state"] == "stopped"
    assert batch.read_results(batch_id) is None
    assert ledger.entries(store.root) == []


def test_a_batch_whose_code_changed_is_refused(tmp_path, monkeypatch):
    batch_id = frozen_batch(keys=KEYS, draws=50)
    store, ctx = claimed(tmp_path, {"batch_id": batch_id})
    monkeypatch.setattr(batch, "code_hashes", lambda: {"changed": "yes"})
    with pytest.raises(batch.BatchError, match="the code it runs has changed"):
        model_batches.run_job({"batch_id": batch_id}, ctx)


@pytest.mark.parametrize("params", [{}, {"batch_id": ""}, {"batch_id": "b", "x": 1}])
def test_the_one_parameter_is_the_batch_id(tmp_path, params):
    store, ctx = claimed(tmp_path, {"batch_id": "b"})
    with pytest.raises(ValueError, match="one parameter, batch_id"):
        model_batches.run_job(params, ctx)


def test_every_engine_kind_is_known_without_importing_its_module(monkeypatch):
    import sys

    for name in ("engine.selftest", "strategy_lab.run", "model_lab.batch"):
        # as in a fresh process: no kind registered, none of their modules imported
        monkeypatch.setattr(jobs, "_KINDS", {})
        for module in jobs.KIND_MODULES:
            monkeypatch.delitem(sys.modules, module, raising=False)
        assert jobs.kind(name).name == name
