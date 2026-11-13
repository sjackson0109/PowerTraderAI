"""
The research engine's scheduler: starts queued jobs in worker processes, within an
operating mode's limits (``resources.limits_for``).

Each cycle (``step``):
1. **reap**: a worker that ended is joined. If it left its job running (it crashed,
   or was killed), the job fails with the exit code.
2. **enforce**: a job whose worker uses more memory than its share is stopped and
   fails with the figures. A job asked to pause or cancel that has not stopped
   within ``stop_grace_seconds`` is stopped, and paused or cancelled as asked; a
   paused job keeps its last checkpoint.
3. **start**: while fewer than ``limits.workers`` jobs run, dispatch is not paused,
   and the machine has more memory available than the mode keeps free, the queued
   job with the highest priority (then the oldest) is started.

Workers are spawned processes running below normal priority (idle in low-resource
mode), with their numerical libraries' threads limited. They never share memory
with the hub or the trader. ``start`` queues again any job a previous scheduler
left running (``JobStore.recover``), from its last checkpoint.
"""

from __future__ import annotations

import multiprocessing
import threading
import time
from typing import Callable, Dict, List, Optional

from research_engine import jobs as jobs_mod
from research_engine.resources import Limits
from research_engine.store import Job, JobStore

MIB = 1024**2


def _rss(pid: int) -> int:
    import psutil

    try:
        return int(psutil.Process(pid).memory_info().rss)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0


def _available_memory() -> int:
    import psutil

    return int(psutil.virtual_memory().available)


class Scheduler:
    def __init__(
        self,
        store: JobStore,
        limits: Limits,
        poll_seconds: float = 0.25,
        stop_grace_seconds: float = 10.0,
        available_memory: Callable[[], int] = _available_memory,
        process_memory: Callable[[int], int] = _rss,
    ) -> None:
        self.store = store
        self.limits = limits
        self.poll_seconds = float(poll_seconds)
        self.stop_grace_seconds = float(stop_grace_seconds)
        self._available_memory = available_memory
        self._process_memory = process_memory
        self._mp = multiprocessing.get_context("spawn")
        self._workers: Dict[int, multiprocessing.process.BaseProcess] = {}
        self._asked: Dict[int, float] = {}
        self._dispatch_paused = False
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.notes: List[str] = (
            []
        )  # why a cycle started nothing, for the window and log

    # -- submitting --------------------------------------------------------------------

    def submit(
        self, kind: str, params: dict, seed: int, priority: int = 0, label: str = ""
    ):
        """Queue a job of a registered kind: ``(job, created)`` (``JobStore.submit``)."""
        k = jobs_mod.kind(kind)
        return self.store.submit(
            kind, params, seed, priority=priority, kind_version=k.version, label=label
        )

    # -- dispatch control --------------------------------------------------------------

    def pause_dispatch(self) -> None:
        """Start no new job; running jobs go on."""
        self._dispatch_paused = True

    def resume_dispatch(self) -> None:
        self._dispatch_paused = False

    @property
    def running(self) -> List[int]:
        return sorted(self._workers)

    # -- one cycle ---------------------------------------------------------------------

    def step(self) -> None:
        self._reap()
        self._enforce()
        self._start_new()

    def _reap(self) -> None:
        for job_id, proc in list(self._workers.items()):
            if proc.is_alive():
                continue
            proc.join()
            del self._workers[job_id]
            self._asked.pop(job_id, None)
            if self.store.get(job_id).state == "running":
                self.store.fail(
                    job_id,
                    f"the worker ended without a result (exit code {proc.exitcode})",
                    {},
                )

    def _kill(self, job_id: int) -> None:
        proc = self._workers.pop(job_id)
        proc.terminate()
        proc.join(timeout=10)
        self._asked.pop(job_id, None)

    def _enforce(self) -> None:
        now = time.monotonic()
        cap = self.limits.memory_per_job_bytes
        for job_id, proc in list(self._workers.items()):
            used = self._process_memory(proc.pid) if proc.pid else 0
            if cap and used > cap:
                self._kill(job_id)
                self.store.fail(
                    job_id,
                    f"memory limit: the job used {used / MIB:.0f} MiB, its share in "
                    f"{self.limits.mode} mode is {cap / MIB:.0f} MiB",
                    {"peak_rss_bytes": used},
                )
                continue
            request = self.store.request_of(job_id)
            if request is None:
                continue
            first = self._asked.setdefault(job_id, now)
            if now - first > self.stop_grace_seconds:
                self._kill(job_id)
                self.store.stopped(job_id, request, {})

    def _start_new(self) -> None:
        while len(self._workers) < self.limits.workers and not self._dispatch_paused:
            free = self._available_memory()
            if free <= self.limits.memory_reserve_bytes:
                self._note(
                    f"waiting: {free / MIB:.0f} MiB available, {self.limits.mode} mode "
                    f"keeps {self.limits.memory_reserve_bytes / MIB:.0f} MiB free"
                )
                return
            job = self.store.claim_next()
            if job is None:
                return
            self._launch(job)

    def _launch(self, job: Job) -> None:
        try:
            k = jobs_mod.kind(job.kind)
        except KeyError as exc:
            self.store.fail(job.id, str(exc), {})
            return
        proc = self._mp.Process(
            target=jobs_mod.worker_main,
            args=(
                self.store.root,
                job.id,
                k.module,
                k.function,
                self.limits.threads_per_worker,
                self.limits.priority,
            ),
            name=f"research-job-{job.id}",
            daemon=True,
        )
        proc.start()
        self.store.set_worker(job.id, proc.pid)
        self._workers[job.id] = proc

    def _note(self, text: str) -> None:
        if not self.notes or self.notes[-1] != text:
            self.notes.append(text)
            del self.notes[:-50]

    # -- running -----------------------------------------------------------------------

    def recover(self) -> List[int]:
        """Queue again the jobs a previous scheduler left running."""
        return self.store.recover()

    def run_until_idle(self, timeout: Optional[float] = None) -> None:
        """Run cycles until no job is queued or running (paused jobs wait)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            self.step()
            if not self._workers and not self.store.jobs(("queued",)):
                return
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f"jobs still running: {self.running}")
            time.sleep(self.poll_seconds)

    def start(self) -> None:
        """Run cycles in a background thread until ``stop``."""
        if self._thread is not None and self._thread.is_alive():
            return
        self.recover()
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                self.step()
                self._stop.wait(self.poll_seconds)

        self._thread = threading.Thread(
            target=loop, name="research-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self, grace_seconds: Optional[float] = None) -> None:
        """Stop the cycles. Running jobs are asked to pause (keeping their checkpoint);
        any still running after ``grace_seconds`` are stopped and stay ``running`` in
        the queue, so the next ``start`` queues them again."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=30)
            self._thread = None
        for job_id in list(self._workers):
            self.store.pause(job_id)
        deadline = time.monotonic() + (
            self.stop_grace_seconds if grace_seconds is None else grace_seconds
        )
        while self._workers and time.monotonic() < deadline:
            self._reap()
            time.sleep(0.05)
        for job_id in list(self._workers):
            self._kill(job_id)
