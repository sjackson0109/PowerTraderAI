"""PTAI-RD-001 M5: the local research engine's resources, job queue and scheduler.

The scheduler tests start real worker processes (spawned, as on Windows) running the
``engine.selftest`` job, which reads no market data.
"""

from __future__ import annotations

import math
import sys
import time

import psutil
import pytest

from research_engine import jobs, resources, selftest  # noqa: F401 - registers the kind
from research_engine.resources import GIB, EnergyModel, Inventory, Limits, limits_for
from research_engine.scheduler import Scheduler
from research_engine.store import JobStore, job_key

MIB = 1024**2


def machine(**changes) -> Inventory:
    """The owner's workstation as measured on 2026-11-11: 8 cores, 16 threads, 32 GiB."""
    values = dict(
        cpu_name="AMD Ryzen 7 8845HS w/ Radeon 780M Graphics",
        physical_cores=8,
        logical_cores=16,
        memory_total_bytes=32 * GIB,
        memory_available_bytes=12 * GIB,
        gpus=("AMD Radeon 780M Graphics",),
        accelerators=(),
        disk_free_bytes=1000 * GIB,
        python="3.13",
        platform="Windows-11",
    )
    values.update(changes)
    return Inventory(**values)


def limits(workers=2, per_job=0, reserve=0, priority="below_normal") -> Limits:
    return Limits("balanced", workers, 1, reserve, per_job, priority)


# -- resources --------------------------------------------------------------------------


def test_the_modes_on_the_owners_workstation():
    inv = machine()
    top, mid, low = (limits_for(m, inv) for m in resources.MODES)
    assert (top.workers, top.threads_per_worker, top.priority) == (7, 2, "below_normal")
    assert (mid.workers, mid.threads_per_worker, mid.priority) == (4, 3, "below_normal")
    assert (low.workers, low.threads_per_worker, low.priority) == (1, 1, "idle")
    assert mid.memory_reserve_bytes == 8 * GIB  # 25% of 32 GiB
    assert mid.memory_per_job_bytes == 6 * GIB  # (32 - 8) / 4
    assert top.memory_reserve_bytes == max(4 * GIB, int(32 * GIB * 0.15))
    assert low.memory_reserve_bytes == int(32 * GIB * 0.40)
    # every mode leaves a core and some memory to the trader
    for lim in (top, mid, low):
        assert lim.workers < inv.physical_cores
        assert lim.workers * lim.threads_per_worker <= inv.logical_cores - 2


def test_a_small_machine_still_gets_one_worker_and_keeps_4_gib_free():
    inv = machine(physical_cores=1, logical_cores=2, memory_total_bytes=8 * GIB)
    for mode in resources.MODES:
        lim = limits_for(mode, inv)
        assert lim.workers == 1
        assert lim.threads_per_worker >= 1
        assert lim.memory_reserve_bytes >= 4 * GIB


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="unknown mode"):
        limits_for("turbo", machine())


def test_the_inventory_reports_what_the_os_reports(tmp_path):
    inv = resources.inventory(
        str(tmp_path),
        names=lambda: {"cpu": "Test CPU", "gpus": ["Test GPU"]},
        accelerator_probe=lambda: (),
    )
    assert inv.cpu_name == "Test CPU"
    assert inv.gpus == ("Test GPU",)
    assert inv.accelerators == ()
    assert inv.logical_cores >= inv.physical_cores >= 1
    assert inv.memory_total_bytes >= inv.memory_available_bytes > 0
    assert inv.disk_free_bytes > 0


def test_no_energy_or_cost_is_reported_without_the_owners_figures():
    assert EnergyModel().energy_wh(3600) is None
    assert EnergyModel(watts_per_busy_core=15).cost(3600) is None
    model = EnergyModel(watts_per_busy_core=15, tariff_per_kwh=0.25, currency="GBP")
    assert model.energy_wh(3600) == pytest.approx(15.0)
    assert model.cost(3600) == pytest.approx(0.00375)
    assert "estimate" in EnergyModel.METHOD


# -- the queue ----------------------------------------------------------------------------


def test_an_identical_job_is_queued_once(tmp_path):
    store = JobStore(str(tmp_path))
    a, created_a = store.submit("engine.selftest", {"steps": 2, "sleep": 0.1}, seed=7)
    b, created_b = store.submit("engine.selftest", {"sleep": 0.1, "steps": 2}, seed=7)
    assert (created_a, created_b) == (True, False)
    assert a.id == b.id
    assert a.key == job_key("engine.selftest", 1, {"steps": 2, "sleep": 0.1}, 7)
    c, created_c = store.submit("engine.selftest", {"steps": 2, "sleep": 0.1}, seed=8)
    d, created_d = store.submit(
        "engine.selftest", {"steps": 2, "sleep": 0.1}, seed=7, kind_version=2
    )
    assert created_c and created_d
    assert len({a.id, c.id, d.id}) == 3


def test_parameters_must_be_json_without_nan(tmp_path):
    store = JobStore(str(tmp_path))
    with pytest.raises(ValueError):
        store.submit("engine.selftest", {"x": math.nan}, seed=1)


def test_the_highest_priority_runs_first_then_the_oldest(tmp_path):
    store = JobStore(str(tmp_path))
    low, _ = store.submit("k", {"n": 1}, 1, priority=0)
    high_old, _ = store.submit("k", {"n": 2}, 1, priority=5)
    high_new, _ = store.submit("k", {"n": 3}, 1, priority=5)
    order = [store.claim_next().id for _ in range(3)]
    assert order == [high_old.id, high_new.id, low.id]
    assert store.claim_next() is None
    assert store.get(low.id).attempts == 1


def test_queued_jobs_can_be_paused_resumed_cancelled_and_retried(tmp_path):
    store = JobStore(str(tmp_path))
    job, _ = store.submit("k", {"n": 1}, 1)
    assert store.pause(job.id) == "paused"
    assert store.claim_next() is None  # a paused job is not started
    assert store.resume(job.id) == "queued"
    assert store.cancel(job.id) == "cancelled"
    assert store.claim_next() is None
    assert store.retry(job.id) == "queued"
    assert store.claim_next().id == job.id


def test_a_job_left_running_is_queued_again_with_its_checkpoint(tmp_path):
    store = JobStore(str(tmp_path))
    job, _ = store.submit("k", {"n": 1}, 1)
    store.claim_next()
    store.save_checkpoint(job.id, {"step": 4})
    assert store.recover() == [job.id]
    again = store.get(job.id)
    assert again.state == "queued"
    assert again.checkpoint == {"step": 4}
    assert "interrupted" in again.error
    assert store.claim_next().attempts == 2


# -- the scheduler (real worker processes) --------------------------------------------------


def run(sched: Scheduler, timeout: float = 120.0) -> None:
    sched.run_until_idle(timeout=timeout)


def step_until(sched: Scheduler, condition, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError("condition not reached")
        sched.step()
        time.sleep(0.1)


def test_jobs_run_in_workers_never_more_at_once_than_the_limit(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(store, limits(workers=2), poll_seconds=0.05)
    ids = [
        sched.submit("engine.selftest", {"steps": 3, "sleep": 0.3, "n": n}, seed=n)[
            0
        ].id
        for n in range(4)
    ]
    run(sched)
    done = [store.get(i) for i in ids]
    assert [j.state for j in done] == ["done"] * 4, [j.error for j in done]
    spans = [(j.result["started"], j.result["ended"]) for j in done]
    most = max(sum(1 for a, b in spans if a <= t < b) for t, _ in spans)
    assert 1 <= most <= 2
    assert len({j.result["pid"] for j in done}) == 4  # a process per job
    for j in done:
        assert j.cpu_seconds > 0 and j.wall_seconds > 0 and j.peak_rss_bytes > 0
        assert j.progress == 1.0


def test_the_same_seed_gives_the_same_numbers(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(store, limits(workers=3), poll_seconds=0.05)
    a = sched.submit("engine.selftest", {"steps": 4, "tag": "a"}, seed=11)[0].id
    b = sched.submit("engine.selftest", {"steps": 4, "tag": "b"}, seed=11)[0].id
    c = sched.submit("engine.selftest", {"steps": 4, "tag": "c"}, seed=12)[0].id
    run(sched)
    draws = [store.get(i).result["draws"] for i in (a, b, c)]
    assert draws[0] == draws[1]
    assert draws[0] != draws[2]


def test_a_failure_is_recorded_and_the_other_jobs_still_run(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(store, limits(workers=2), poll_seconds=0.05)
    bad = sched.submit("engine.selftest", {"steps": 1, "fail": True}, seed=1)[0].id
    good = sched.submit("engine.selftest", {"steps": 1}, seed=2)[0].id
    run(sched)
    assert store.get(bad).state == "failed"
    assert "asked to fail" in store.get(bad).error
    assert store.get(good).state == "done"
    assert store.summary()["failures"][0][0] == bad


def test_a_result_that_is_not_plain_json_fails_the_job(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(store, limits(workers=1), poll_seconds=0.05)
    job = sched.submit("engine.selftest", {"steps": 1, "nan_result": True}, seed=1)[
        0
    ].id
    run(sched)
    assert store.get(job).state == "failed"
    assert "not plain JSON" in store.get(job).error


def test_a_worker_that_dies_fails_its_job_with_the_exit_code(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(store, limits(workers=1), poll_seconds=0.05)
    job = sched.submit("engine.selftest", {"exit_code": 3}, seed=1)[0].id
    run(sched)
    assert store.get(job).state == "failed"
    assert "exit code 3" in store.get(job).error


def test_an_unknown_kind_fails_its_job(tmp_path):
    store = JobStore(str(tmp_path))
    job, _ = store.submit("no.such.kind", {}, seed=1)
    sched = Scheduler(store, limits(workers=1), poll_seconds=0.05)
    run(sched)
    assert store.get(job.id).state == "failed"
    assert "unknown job kind" in store.get(job.id).error


def test_a_paused_job_resumes_from_its_checkpoint_with_the_same_numbers(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(store, limits(workers=2), poll_seconds=0.05)
    paused = sched.submit(
        "engine.selftest", {"steps": 12, "sleep": 0.25, "tag": "paused"}, seed=5
    )[0].id
    step_until(sched, lambda: (store.get(paused).progress or 0) >= 0.25)
    store.pause(paused)
    step_until(sched, lambda: store.get(paused).state == "paused")
    at = store.get(paused).checkpoint["step"]
    assert 0 < at < 12
    assert store.resume(paused) == "queued"
    whole = sched.submit("engine.selftest", {"steps": 12, "tag": "whole"}, seed=5)[0].id
    run(sched)
    resumed = store.get(paused)
    assert resumed.state == "done"
    assert resumed.result["resumed"] == 1
    assert resumed.attempts == 2
    assert resumed.result["draws"] == store.get(whole).result["draws"]


def test_a_running_job_can_be_cancelled(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(store, limits(workers=1), poll_seconds=0.05)
    job = sched.submit("engine.selftest", {"steps": 100, "sleep": 0.2}, seed=1)[0].id
    step_until(sched, lambda: (store.get(job).progress or 0) > 0)
    assert store.cancel(job) == "running"  # asked; it stops at its next check
    run(sched)
    assert store.get(job).state == "cancelled"


def test_a_job_that_ignores_a_request_is_stopped_after_the_grace_period(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(
        store, limits(workers=1), poll_seconds=0.05, stop_grace_seconds=1.0
    )
    job = sched.submit(
        "engine.selftest", {"steps": 200, "sleep": 0.2, "ignore_stop": True}, seed=1
    )[0].id
    step_until(sched, lambda: (store.get(job).progress or 0) > 0)
    store.cancel(job)
    started = time.monotonic()
    run(sched, timeout=30)
    assert store.get(job).state == "cancelled"
    assert time.monotonic() - started < 15  # far sooner than its 40 s of steps


def test_a_job_over_its_memory_share_is_stopped(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(store, limits(workers=1, per_job=200 * MIB), poll_seconds=0.05)
    job = sched.submit(
        "engine.selftest", {"allocate_mib": 500, "hold_seconds": 20}, seed=1
    )[0].id
    run(sched, timeout=60)
    record = store.get(job)
    assert record.state == "failed"
    assert "memory limit" in record.error
    assert record.peak_rss_bytes > 200 * MIB


def test_no_job_starts_while_the_machine_is_short_of_memory(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(
        store,
        limits(workers=2, reserve=4 * GIB),
        available_memory=lambda: 3 * GIB,
    )
    job = sched.submit("engine.selftest", {"steps": 1}, seed=1)[0].id
    sched.step()
    assert store.get(job).state == "queued"
    assert sched.running == []
    assert "keeps 4096 MiB free" in sched.notes[-1]


def test_paused_dispatch_starts_nothing(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(store, limits(workers=2))
    job = sched.submit("engine.selftest", {"steps": 1}, seed=1)[0].id
    sched.pause_dispatch()
    sched.step()
    assert store.get(job).state == "queued"
    sched.resume_dispatch()
    run(sched)
    assert store.get(job).state == "done"


def test_workers_run_below_normal_priority(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(store, limits(workers=2), poll_seconds=0.05)
    normal = sched.submit(
        "engine.selftest", {"steps": 2, "sleep": 0.5, "p": 1}, seed=1
    )[0].id
    sched.step()  # starts with below-normal priority
    sched.limits = limits(workers=2, priority="idle")
    idle = sched.submit("engine.selftest", {"steps": 1, "p": 2}, seed=1)[0].id
    sched.step()  # starts with the low-resource mode's idle priority
    run(sched)
    got = (store.get(normal).result["nice"], store.get(idle).result["nice"])
    if sys.platform == "win32":
        assert got == (psutil.BELOW_NORMAL_PRIORITY_CLASS, psutil.IDLE_PRIORITY_CLASS)
    else:
        assert got == (10, 19)


def test_stopping_the_scheduler_pauses_running_jobs_for_the_next_start(tmp_path):
    store = JobStore(str(tmp_path))
    sched = Scheduler(store, limits(workers=1), poll_seconds=0.05)
    job = sched.submit("engine.selftest", {"steps": 40, "sleep": 0.2}, seed=3)[0].id
    sched.start()
    deadline = time.monotonic() + 60
    while (store.get(job).progress or 0) <= 0 and time.monotonic() < deadline:
        time.sleep(0.1)
    sched.stop(grace_seconds=15)
    assert store.get(job).state == "paused"
    assert store.get(job).checkpoint["step"] > 0
    store.resume(job)
    again = Scheduler(store, limits(workers=1), poll_seconds=0.05)
    again.start()
    deadline = time.monotonic() + 60
    while store.get(job).state != "done" and time.monotonic() < deadline:
        time.sleep(0.2)
    again.stop()
    assert store.get(job).state == "done"
    assert store.get(job).result["resumed"] == 1


def test_a_kind_must_be_a_module_level_function():
    with pytest.raises(ValueError, match="module-level"):

        @jobs.job_kind("engine.nested")
        def nested(params, ctx):  # pragma: no cover - never registered
            return {}
