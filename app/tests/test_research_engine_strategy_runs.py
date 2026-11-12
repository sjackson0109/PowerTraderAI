"""PTAI-RD-001 M5: strategy backtests as research engine jobs (``strategy_lab.run``).

* The job runs ``strategy_lab.runs.run`` under its rules: the reserved months are
  refused before anything is read, and every run is logged as an exploratory trial.
* Two runs of one strategy saved in the same second get their own folders.
* A job asked to stop saves nothing.

Synthetic candles and a fake venue (test_strategy_backtest_window): no network.
"""

from __future__ import annotations

import pytest
from test_strategy_backtest_window import config, lab, loader, venue  # noqa: F401

from research_engine import strategy_runs
from research_engine.jobs import JobContext, StopRequested
from research_engine.resources import Limits
from research_engine.scheduler import Scheduler
from research_engine.store import JobStore
from strategy_lab import experiment, runs


def params(**changes):
    """``config()``'s settings, as a job's parameters (without the seed)."""
    out = {k: v for k, v in config(**changes).__dict__.items() if k not in ("seed",)}
    out["coins"] = list(out["coins"])
    out["params"] = dict(out["params"])
    return out


def claimed(tmp_path, job_params, seed=700_000):
    store = JobStore(str(tmp_path / "engine"))
    job, _ = store.submit("strategy_lab.run", job_params, seed)
    store.claim_next()
    return store, JobContext(store, job.id, seed, None)


def test_the_settings_are_run_config_fields_and_the_seed_is_the_jobs():
    made = strategy_runs.config_from(params(), seed=42)
    assert made == config(seed=42)
    with pytest.raises(ValueError, match="the seed is the job's own"):
        strategy_runs.config_from({**params(), "seed": 1}, seed=42)
    with pytest.raises(ValueError, match="unknown backtest settings"):
        strategy_runs.config_from({**params(), "leverage": 3}, seed=42)


def test_a_job_runs_the_backtest_and_logs_its_trial(tmp_path, lab):  # noqa: F811
    store, ctx = claimed(tmp_path, params())
    result = strategy_runs.run_job(params(), ctx, loader=loader, venue=venue)
    saved = runs.list_runs()
    assert [r["id"] for r in saved] == [result["run_id"]]
    assert result["strategy_result"] == saved[0]["strategy_result"]
    assert result["random_entries"]["draws"] == 30
    assert "curve" not in result
    trial = experiment.trials()[-1]
    assert (trial["trial"], trial["kind"]) == (f"{result['run_id']}/run", "exploration")
    assert store.get(ctx.job_id).progress > 0


def test_the_same_seed_gives_the_same_figures(tmp_path, lab):  # noqa: F811
    _, a = claimed(tmp_path / "a", params(), seed=5)
    _, b = claimed(tmp_path / "b", params(), seed=5)
    first = strategy_runs.run_job(params(), a, loader=loader, venue=venue)
    second = strategy_runs.run_job(params(), b, loader=loader, venue=venue)
    assert first["random_entries"] == second["random_entries"]
    assert first["run_id"] != second["run_id"]


def test_a_job_asked_to_stop_saves_nothing(tmp_path, lab):  # noqa: F811
    store, ctx = claimed(tmp_path, params())
    store.cancel(ctx.job_id)  # running: asked to stop
    with pytest.raises(StopRequested):
        strategy_runs.run_job(params(), ctx, loader=loader, venue=venue)
    assert runs.list_runs() == [] and experiment.trials() == []


def test_two_runs_saved_in_the_same_second_get_their_own_folders(lab):  # noqa: F811
    first = runs.run(config(), loader=loader, venue=venue, now=1_800_000_000)
    second = runs.run(config(), loader=loader, venue=venue, now=1_800_000_000)
    assert second["id"] == f"{first['id']}-2"
    assert sorted(r["id"] for r in runs.list_runs()) == sorted(
        [first["id"], second["id"]]
    )
    assert [t["trial"] for t in experiment.trials()] == [
        f"{first['id']}/run",
        f"{second['id']}/run",
    ]


def test_a_spawned_job_for_the_reserved_months_fails_before_reading_anything(
    tmp_path, lab  # noqa: F811
):
    store = JobStore(str(tmp_path / "engine"))
    sched = Scheduler(store, Limits("balanced", 1, 1, 0, 0, "below_normal"), 0.05)
    job = sched.submit("strategy_lab.run", params(end="2025-06-01"), seed=1)[0].id
    sched.run_until_idle(timeout=120)
    record = store.get(job)
    assert record.state == "failed"
    assert "reserved months" in record.error
    assert runs.list_runs() == [] and experiment.trials() == []
