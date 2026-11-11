"""
The research engine's persistent job queue: one SQLite file (``jobs.sqlite``) in the
engine's folder, ``<data dir>/research_engine`` by default.

**A job** is a kind (``jobs.job_kind``) run with JSON parameters and a seed. Its key is
the SHA-256 of ``{kind, kind version, parameters, seed}`` in canonical JSON, so the same
experiment is never queued twice: ``submit`` returns the existing job instead. A job
that failed or was cancelled runs again only through ``retry``.

**States.** queued -> running -> done | failed | cancelled; queued or running ->
paused -> queued (``resume``). A running job is asked to pause or cancel through its
``request``; it stops at its next check, keeping its checkpoint. A job left
``running`` by a scheduler that stopped (a crash, a restart) is queued again by
``recover``, with its checkpoint and one more attempt.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple

STATES = ("queued", "running", "paused", "done", "failed", "cancelled")
TERMINAL = ("done", "failed", "cancelled")
REQUESTS = ("pause", "cancel")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    kind_version INTEGER NOT NULL,
    params TEXT NOT NULL,
    seed INTEGER NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    label TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL,
    request TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    attempts INTEGER NOT NULL DEFAULT 0,
    checkpoint TEXT,
    progress REAL,
    progress_note TEXT,
    result TEXT,
    error TEXT,
    cpu_seconds REAL NOT NULL DEFAULT 0,
    wall_seconds REAL NOT NULL DEFAULT 0,
    peak_rss_bytes INTEGER NOT NULL DEFAULT 0,
    worker_pid INTEGER
);
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs (state, priority, id);
"""


def canonical(value: Any) -> str:
    """``value`` as canonical JSON: sorted keys, no spaces; NaN refused."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def job_key(kind: str, kind_version: int, params: Dict[str, Any], seed: int) -> str:
    text = canonical(
        {
            "kind": kind,
            "kind_version": int(kind_version),
            "params": params,
            "seed": int(seed),
        }
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Job:
    id: int
    key: str
    kind: str
    kind_version: int
    params: Dict[str, Any]
    seed: int
    priority: int
    label: str
    state: str
    request: Optional[str]
    created_at: float
    started_at: Optional[float]
    finished_at: Optional[float]
    attempts: int
    checkpoint: Any
    progress: Optional[float]
    progress_note: Optional[str]
    result: Any
    error: Optional[str]
    cpu_seconds: float
    wall_seconds: float
    peak_rss_bytes: int
    worker_pid: Optional[int]


def _job(row: sqlite3.Row) -> Job:
    d = dict(row)
    for name in ("params", "checkpoint", "result"):
        d[name] = json.loads(d[name]) if d[name] is not None else None
    return Job(**d)


def default_root() -> str:
    import pt_paths

    return os.path.join(pt_paths.data_dir(), "research_engine")


class JobStore:
    def __init__(self, root: Optional[str] = None, clock=time.time) -> None:
        self.root = root or default_root()
        os.makedirs(self.root, exist_ok=True)
        self.path = os.path.join(self.root, "jobs.sqlite")
        self._clock = clock
        with self._connect() as db:
            db.executescript(_SCHEMA)

    # -- plumbing ----------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _write(self, sql: str, args: Tuple = ()) -> int:
        db = self._connect()
        try:
            return db.execute(sql, args).rowcount
        finally:
            db.close()

    def job_dir(self, job_id: int) -> str:
        path = os.path.join(self.root, "jobs", str(int(job_id)))
        os.makedirs(path, exist_ok=True)
        return path

    # -- submitting --------------------------------------------------------------------

    def submit(
        self,
        kind: str,
        params: Dict[str, Any],
        seed: int,
        priority: int = 0,
        kind_version: int = 1,
        label: str = "",
    ) -> Tuple[Job, bool]:
        """Queue a job; ``(job, True)``, or ``(the existing job, False)`` when the same
        kind, version, parameters and seed were submitted before, whatever its state."""
        params = json.loads(canonical(params))  # JSON only, normalised
        key = job_key(kind, kind_version, params, seed)
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE key = ?", (key,)).fetchone()
            if row is not None:
                db.execute("COMMIT")
                return _job(row), False
            cur = db.execute(
                "INSERT INTO jobs (key, kind, kind_version, params, seed, priority, label,"
                " state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
                (
                    key,
                    kind,
                    int(kind_version),
                    canonical(params),
                    int(seed),
                    int(priority),
                    label,
                    self._clock(),
                ),
            )
            row = db.execute(
                "SELECT * FROM jobs WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            db.execute("COMMIT")
            return _job(row), True
        finally:
            db.close()

    # -- reading -----------------------------------------------------------------------

    def get(self, job_id: int) -> Job:
        db = self._connect()
        try:
            row = db.execute(
                "SELECT * FROM jobs WHERE id = ?", (int(job_id),)
            ).fetchone()
        finally:
            db.close()
        if row is None:
            raise KeyError(f"no job {job_id}")
        return _job(row)

    def jobs(self, states: Optional[Tuple[str, ...]] = None) -> List[Job]:
        db = self._connect()
        try:
            if states:
                marks = ",".join("?" * len(states))
                rows = db.execute(
                    f"SELECT * FROM jobs WHERE state IN ({marks}) ORDER BY id", states
                ).fetchall()
            else:
                rows = db.execute("SELECT * FROM jobs ORDER BY id").fetchall()
        finally:
            db.close()
        return [_job(r) for r in rows]

    def summary(self) -> Dict[str, Any]:
        """Counts by state, total CPU and wall time, and each failure's error."""
        jobs = self.jobs()
        counts = {s: 0 for s in STATES}
        for j in jobs:
            counts[j.state] += 1
        return {
            "jobs": len(jobs),
            "by_state": counts,
            "cpu_seconds": sum(j.cpu_seconds for j in jobs),
            "wall_seconds": sum(j.wall_seconds for j in jobs),
            "failures": [(j.id, j.kind, j.error) for j in jobs if j.state == "failed"],
        }

    # -- the scheduler's side ----------------------------------------------------------

    def claim_next(self, worker_pid: Optional[int] = None) -> Optional[Job]:
        """The queued job with the highest priority (then the oldest), now running."""
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM jobs WHERE state = 'queued'"
                " ORDER BY priority DESC, id ASC LIMIT 1"
            ).fetchone()
            if row is None:
                db.execute("COMMIT")
                return None
            db.execute(
                "UPDATE jobs SET state = 'running', request = NULL, started_at = ?,"
                " attempts = attempts + 1, worker_pid = ?, error = NULL WHERE id = ?",
                (self._clock(), worker_pid, row["id"]),
            )
            row = db.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],)).fetchone()
            db.execute("COMMIT")
            return _job(row)
        finally:
            db.close()

    def set_worker(self, job_id: int, pid: int) -> None:
        self._write(
            "UPDATE jobs SET worker_pid = ? WHERE id = ?", (int(pid), int(job_id))
        )

    def save_checkpoint(self, job_id: int, state: Any) -> None:
        self._write(
            "UPDATE jobs SET checkpoint = ? WHERE id = ?",
            (canonical(state), int(job_id)),
        )

    def set_progress(self, job_id: int, fraction: float, note: str = "") -> None:
        self._write(
            "UPDATE jobs SET progress = ?, progress_note = ? WHERE id = ?",
            (float(fraction), note, int(job_id)),
        )

    def request_of(self, job_id: int) -> Optional[str]:
        return self.get(job_id).request

    def _end(self, job_id: int, state: str, usage: Dict[str, float], **fields) -> None:
        sets = ["state = ?", "finished_at = ?", "worker_pid = NULL", "request = NULL"]
        args: List[Any] = [state, self._clock()]
        for name in ("cpu_seconds", "wall_seconds"):
            sets.append(f"{name} = {name} + ?")
            args.append(float(usage.get(name, 0.0)))
        sets.append("peak_rss_bytes = MAX(peak_rss_bytes, ?)")
        args.append(int(usage.get("peak_rss_bytes", 0)))
        for name, value in fields.items():
            sets.append(f"{name} = ?")
            args.append(value)
        args.append(int(job_id))
        self._write(
            f"UPDATE jobs SET {', '.join(sets)} WHERE id = ? AND state = 'running'",
            tuple(args),
        )

    def finish(self, job_id: int, result: Any, usage: Dict[str, float]) -> None:
        self._end(job_id, "done", usage, result=canonical(result), progress=1.0)

    def fail(self, job_id: int, error: str, usage: Dict[str, float]) -> None:
        self._end(job_id, "failed", usage, error=str(error))

    def stopped(self, job_id: int, how: str, usage: Dict[str, float]) -> None:
        """A running job stopped at its request: ``how`` is pause or cancel."""
        self._end(job_id, "paused" if how == "pause" else "cancelled", usage)

    def recover(self) -> List[int]:
        """Queue again every job left running by a scheduler that stopped."""
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            ids = [
                r["id"]
                for r in db.execute(
                    "SELECT id FROM jobs WHERE state = 'running'"
                ).fetchall()
            ]
            db.execute(
                "UPDATE jobs SET state = 'queued', worker_pid = NULL, request = NULL,"
                " error = 'interrupted: the scheduler stopped while it ran'"
                " WHERE state = 'running'"
            )
            db.execute("COMMIT")
            return ids
        finally:
            db.close()

    # -- the owner's side --------------------------------------------------------------

    def pause(self, job_id: int) -> str:
        """Pause a queued job at once, or ask a running one to pause; returns the state."""
        if self._write(
            "UPDATE jobs SET state = 'paused' WHERE id = ? AND state = 'queued'",
            (int(job_id),),
        ):
            return "paused"
        self._write(
            "UPDATE jobs SET request = 'pause' WHERE id = ? AND state = 'running'",
            (int(job_id),),
        )
        return self.get(job_id).state

    def resume(self, job_id: int) -> str:
        self._write(
            "UPDATE jobs SET state = 'queued' WHERE id = ? AND state = 'paused'",
            (int(job_id),),
        )
        return self.get(job_id).state

    def cancel(self, job_id: int) -> str:
        """Cancel a queued or paused job at once, or ask a running one to stop."""
        if self._write(
            "UPDATE jobs SET state = 'cancelled', finished_at = ?"
            " WHERE id = ? AND state IN ('queued', 'paused')",
            (self._clock(), int(job_id)),
        ):
            return "cancelled"
        self._write(
            "UPDATE jobs SET request = 'cancel' WHERE id = ? AND state = 'running'",
            (int(job_id),),
        )
        return self.get(job_id).state

    def retry(self, job_id: int) -> str:
        """Queue a failed or cancelled job again (its attempts are kept)."""
        self._write(
            "UPDATE jobs SET state = 'queued', finished_at = NULL"
            " WHERE id = ? AND state IN ('failed', 'cancelled')",
            (int(job_id),),
        )
        return self.get(job_id).state

    def iter_running(self) -> Iterator[Job]:
        yield from self.jobs(("running",))
