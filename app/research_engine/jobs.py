"""
Job kinds, the context a job runs with, and the worker process's entry point.

A kind is a function ``run(params, ctx) -> result`` registered with ``@job_kind``.
It must be importable by module name, because each job runs in its own process
(spawned, as on Windows). The result must be JSON. A kind's ``version`` is part of
the job's key: raise it when the kind's behaviour changes, so earlier results are
not mistaken for the new kind's.

``JobContext`` gives a job:
* ``seed`` and ``rng()``: the job's seed (Python's and numpy's global generators are
  seeded with it as well, for code that uses them);
* ``checkpoint`` and ``save_checkpoint``: the state a paused or interrupted job
  resumes from;
* ``progress``: a fraction and a note, shown in the queue;
* ``should_stop``: True once the job was asked to pause or cancel. A long job checks
  it, saves its checkpoint and returns; the scheduler stops one that does not.
* ``out_dir``: the job's own folder for result files.
"""

from __future__ import annotations

import importlib
import os
import random
import sys
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from research_engine.store import JobStore

_KINDS: Dict[str, "Kind"] = {}
STOP_CHECK_SECONDS = 1.0
# numerical libraries' thread pools, limited per worker before they are imported
_THREAD_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


@dataclass(frozen=True)
class Kind:
    name: str
    version: int
    module: str
    function: str


def job_kind(name: str, version: int = 1) -> Callable:
    """Register ``fn(params, ctx)`` as job kind ``name``."""

    def deco(fn: Callable) -> Callable:
        if "." in fn.__qualname__ or fn.__module__ == "__main__":
            raise ValueError(
                f"job kind {name!r} must be a module-level function of an importable "
                "module: each job runs in its own process"
            )
        kind = Kind(name, int(version), fn.__module__, fn.__qualname__)
        known = _KINDS.get(name)
        if known is not None and (known.module, known.function) != (
            kind.module,
            kind.function,
        ):
            raise ValueError(f"job kind {name!r} is registered twice")
        _KINDS[name] = kind
        return fn

    return deco


def kind(name: str) -> Kind:
    try:
        return _KINDS[name]
    except KeyError:
        raise KeyError(f"unknown job kind {name!r}") from None


def kinds() -> Dict[str, Kind]:
    return dict(_KINDS)


class StopRequested(Exception):
    """Raised by ``JobContext.stop_if_asked``: the job was asked to pause or cancel."""


class JobContext:
    def __init__(
        self, store: JobStore, job_id: int, seed: int, checkpoint: Any
    ) -> None:
        self.store = store
        self.job_id = int(job_id)
        self.seed = int(seed)
        self.checkpoint = checkpoint
        self.out_dir = store.job_dir(job_id)
        self._request: Optional[str] = None
        self._checked = 0.0

    def rng(self):
        import numpy as np

        return np.random.default_rng(self.seed)

    def save_checkpoint(self, state: Any) -> None:
        self.checkpoint = state
        self.store.save_checkpoint(self.job_id, state)

    def progress(self, fraction: float, note: str = "") -> None:
        self.store.set_progress(self.job_id, fraction, note)

    def should_stop(self) -> bool:
        """True once the job was asked to pause or cancel (read from the queue at most
        every ``STOP_CHECK_SECONDS``)."""
        if self._request is None:
            now = time.monotonic()
            if now - self._checked >= STOP_CHECK_SECONDS:
                self._checked = now
                self._request = self.store.request_of(self.job_id)
        return self._request is not None

    def stop_if_asked(self) -> None:
        if self.should_stop():
            raise StopRequested(self._request)

    @property
    def request(self) -> Optional[str]:
        return self._request


def _usage(started: float) -> Dict[str, float]:
    import psutil

    proc = psutil.Process()
    times = proc.cpu_times()
    mem = proc.memory_info()
    peak = getattr(mem, "peak_wset", None) or getattr(mem, "rss", 0)
    if sys.platform != "win32":
        try:
            import resource

            # ru_maxrss is in KiB on Linux, bytes on macOS
            scale = 1 if sys.platform == "darwin" else 1024
            peak = max(peak, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale)
        except (ImportError, OSError):
            pass
    return {
        "cpu_seconds": float(times.user + times.system),
        "wall_seconds": time.time() - started,
        "peak_rss_bytes": int(peak),
    }


def _lower_priority(priority: str) -> None:
    import psutil

    proc = psutil.Process()
    if sys.platform == "win32":
        proc.nice(
            psutil.IDLE_PRIORITY_CLASS
            if priority == "idle"
            else psutil.BELOW_NORMAL_PRIORITY_CLASS
        )
    else:
        proc.nice(19 if priority == "idle" else 10)


def worker_main(
    root: str, job_id: int, module: str, function: str, threads: int, priority: str
) -> None:
    """A worker process: run one claimed job and record its outcome."""
    started = time.time()
    for var in _THREAD_VARS:
        os.environ[var] = str(int(threads))
    store = JobStore(root)
    try:
        _lower_priority(priority)
    except Exception:  # noqa: BLE001 - running at normal priority is not fatal
        pass
    job = store.get(job_id)
    random.seed(job.seed)
    try:
        import numpy as np

        np.random.seed(job.seed % (2**32))
    except ImportError:
        pass
    ctx = JobContext(store, job.id, job.seed, job.checkpoint)
    try:
        fn = getattr(importlib.import_module(module), function)
        result = fn(job.params, ctx)
    except StopRequested as stop:
        store.stopped(job.id, str(stop), _usage(started))
        return
    except BaseException:  # noqa: BLE001 - every failure is recorded
        store.fail(job.id, traceback.format_exc(limit=20), _usage(started))
        return
    usage = _usage(started)
    if ctx.request is not None:
        # it returned after a request: a pause keeps the checkpoint, a cancel ends it
        store.stopped(job.id, ctx.request, usage)
        return
    try:
        store.finish(job.id, result, usage)
    except (TypeError, ValueError) as exc:
        store.fail(job.id, f"the job's result is not plain JSON: {exc}", usage)
