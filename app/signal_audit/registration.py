"""
A round's registration and the run's refusals (FDS-SIG-001 sections 11 and 12).

**Files.** Round N lives in ``docs/dev/sig-audit/round-<N>/``:

* ``registration.json`` (section 12, step 1), committed in its own commit, dated before
  the window starts;
* ``freeze.json`` (step 2), committed in its own commit: the frozen paths (at least
  ``app/`` and the audit script). The commit that first added it is the freeze commit,
  and it never changes afterwards;
* the ranking and history evidence (step 0) and, after the window, the candle records,
  results and evidence series (steps 3 to 5).

**The run refuses** (step 4), logging an ERROR, when:

1. the registration file is missing, uncommitted, or changed since its registration
   commit (the last commit that changed it);
2. the registration commit is not dated before the window start, or the window starts
   before the earliest start: the later of 2026-10-01 00:00 UTC and the first 00:00 UTC
   after the registration commit (section 11);
3. a commit that changes the registration also touches a frozen path;
4. any frozen path is dirty (``git status --porcelain`` over the frozen paths);
5. the registration commit is not an ancestor of the freeze commit, or the freeze
   record changed after its freeze commit (a second freeze would move the freeze point);
6. a frozen path changed in any commit after the freeze commit (step 2's code freeze).
   The one exception is step 6's: after results, a defect fix through ``--supersede``
   ("<what changed and why>"), and only when results exist; the changed files and the
   note are then recorded, and the earlier verdict stays beside the new one;
7. the window's end has not yet passed;
8. a registered trained model's ``train_end`` is after the window start.

Steps 2 and 6 together allow changed code only as a superseding defect fix after
results; step 4 lists dirty frozen paths, and committed changes after the freeze are
refused on the same footing (the PR #228 review, finding 2). Step 4's own list names
neither refusal 6 nor a changed freeze record (refusal 5): that wording awaits the owner
(``docs/dev/RUN-LOG-sig-1.md``).

Git is local only: no network, no credentials.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

LOG = logging.getLogger("signal_audit")

SPEC = "FDS-SIG-001"
CANDIDATES_SPEC = "FDS-SIG-002"
FROZEN_PATHS = ("app", "docs/dev/run_signal_audit.py")
EARLIEST_START = "2026-10-01T00:00:00Z"
TIMEFRAMES = ("1h", "4h")


class Refused(RuntimeError):
    """The audit script refuses to run (section 12, step 4)."""


def round_dir(repo: str, n: int) -> str:
    return os.path.join(repo, "docs", "dev", "sig-audit", f"round-{int(n)}")


def rel_round_dir(n: int) -> str:
    return f"docs/dev/sig-audit/round-{int(n)}"


def parse_time(text: str) -> datetime:
    t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_midnight(t: datetime) -> datetime:
    """The first 00:00 UTC strictly after ``t``."""
    t = t.astimezone(timezone.utc)
    day = t.replace(hour=0, minute=0, second=0, microsecond=0)
    return day + timedelta(days=1)


def earliest_start(registration_commit_time: datetime) -> datetime:
    return max(parse_time(EARLIEST_START), next_midnight(registration_commit_time))


def file_sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def canonical_sha256(record: Mapping[str, Any]) -> str:
    text = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- the rows and the family ------------------------------------------------------------


def family_rows(
    candidates: Sequence[Any],
    coins: Sequence[str],
    timeframes: Sequence[str],
    exchange: str,
):
    """Every registered row, in registration order: each candidate, then each coin it
    runs on (in rank order), then each timeframe."""
    from signal_audit.engine import RowKey

    rows = []
    for c in candidates:
        for coin in coins:
            if not c.runs_on(coin):
                continue
            for tf in timeframes:
                rows.append(RowKey(c.key, exchange, coin, tf))
    return rows


def family_size(rows: Sequence[Any]) -> int:
    """F = 2 statistics x the registered rows (section 8.1)."""
    return 2 * len(rows)


# --- git (local only) -------------------------------------------------------------------


def git(repo: str, *args: str) -> str:
    return subprocess.run(
        ["git", "--no-optional-locks", "-C", repo, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


def _last_commit(repo: str, rel: str) -> Optional[str]:
    out = git(repo, "log", "-1", "--format=%H", "--", rel).strip()
    return out or None


def _commits_touching(repo: str, rel: str) -> List[str]:
    return [c for c in git(repo, "log", "--format=%H", "--", rel).split() if c]


def _commit_time(repo: str, commit: str) -> datetime:
    return parse_time(git(repo, "show", "-s", "--format=%cI", commit).strip())


def _changed(repo: str, commit: str) -> List[str]:
    return [
        p
        for p in git(repo, "show", "--name-only", "--format=", commit).splitlines()
        if p.strip()
    ]


def _is_frozen(path: str, frozen: Sequence[str]) -> bool:
    path = path.replace("\\", "/")
    return any(path == f or path.startswith(f.rstrip("/") + "/") for f in frozen)


@dataclass(frozen=True)
class RunState:
    head: str
    registration_commit: str
    registration_sha256: str
    freeze_commit: str
    frozen_files_dirty: List[str]
    frozen_files_changed_since_freeze: List[str]
    python: str
    powertrader_home: Optional[str]
    supersede: Optional[str] = None  # the defect fix's note, when one is run

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def refuse(message: str) -> None:
    LOG.error("signal audit refused: %s", message)
    raise Refused(message)


def check_can_run(
    repo: str,
    n: int,
    now: Optional[datetime] = None,
    frozen: Sequence[str] = FROZEN_PATHS,
    supersede: Optional[str] = None,
    results_exist: bool = False,
) -> RunState:
    """Every refusal of section 12, step 4 (module docstring), in order; the state the
    outputs record (step 5) when none applies. ``supersede`` is the note of a defect fix
    after results (step 6), and ``results_exist`` whether the round has results."""
    now = now or datetime.now(timezone.utc)
    rel_reg = f"{rel_round_dir(n)}/registration.json"
    rel_freeze = f"{rel_round_dir(n)}/freeze.json"
    path = os.path.join(repo, rel_reg)
    # 1. present, committed, unchanged since its registration commit
    if not os.path.isfile(path):
        refuse(f"no registration file {rel_reg}")
    tracked = git(repo, "ls-files", "--", rel_reg).strip()
    if not tracked:
        refuse(f"the registration file {rel_reg} is not committed")
    if git(repo, "status", "--porcelain", "--", rel_reg).strip():
        refuse(f"the registration file {rel_reg} has uncommitted changes")
    reg_commit = _last_commit(repo, rel_reg)
    committed = git(repo, "show", f"{reg_commit}:{rel_reg}")
    with open(path, "r", encoding="utf-8") as f:
        on_disk = f.read()
    if committed.replace("\r\n", "\n") != on_disk.replace("\r\n", "\n"):
        refuse(
            f"the registration file differs from its registration commit {reg_commit[:7]}"
        )
    record = json.loads(on_disk)
    start = parse_time(record["window"]["start"])
    end = parse_time(record["window"]["end"])
    # 2. dated before the window start, which is no earlier than the earliest start
    reg_time = _commit_time(repo, reg_commit)
    if not reg_time < start:
        refuse(
            f"the registration commit {reg_commit[:7]} ({iso(reg_time)}) is not dated "
            f"before the window start {iso(start)}"
        )
    if start < earliest_start(reg_time):
        refuse(
            f"the window starts {iso(start)}, before the earliest start "
            f"{iso(earliest_start(reg_time))}"
        )
    # 3. no commit that changed the registration touched a frozen path
    for c in _commits_touching(repo, rel_reg):
        touched = [p for p in _changed(repo, c) if _is_frozen(p, frozen)]
        if touched:
            refuse(
                f"commit {c[:7]} changed the registration and frozen paths {touched}"
            )
    # 4. no frozen path dirty
    dirty = git(repo, "status", "--porcelain", "--", *frozen).splitlines()
    if dirty:
        refuse(f"frozen paths have uncommitted changes: {dirty}")
    # 5. the registration commit is an ancestor of the freeze commit, which is the one
    # that first added the freeze record; the record never changes afterwards
    freeze_commits = _commits_touching(repo, rel_freeze)
    if not freeze_commits:
        refuse(f"no code freeze committed ({rel_freeze})")
    freeze_commit = freeze_commits[-1]
    if len(freeze_commits) > 1:
        refuse(
            f"the freeze record {rel_freeze} changed after its freeze commit "
            f"{freeze_commit[:7]} (in {[c[:7] for c in freeze_commits[:-1]]})"
        )
    if git(repo, "status", "--porcelain", "--", rel_freeze).strip():
        refuse(f"the freeze record {rel_freeze} has uncommitted changes")
    ancestor = subprocess.run(
        ["git", "-C", repo, "merge-base", "--is-ancestor", reg_commit, freeze_commit],
        capture_output=True,
    )
    if ancestor.returncode != 0:
        refuse(
            f"the registration commit {reg_commit[:7]} is not an ancestor of the freeze "
            f"commit {freeze_commit[:7]}"
        )
    # 6. no frozen path changed since the freeze, but a defect fix after results
    changed = [
        p
        for p in git(
            repo, "diff", "--name-only", freeze_commit, "HEAD", "--", *frozen
        ).splitlines()
        if p.strip()
    ]
    note = (supersede or "").strip() or None
    if changed and not (note and results_exist):
        why = (
            'a defect fix after results needs --supersede "<what changed and why>"'
            if results_exist
            else "no results exist, and section 12 allows changed code only as a "
            "defect fix after results, through --supersede"
        )
        refuse(
            f"frozen paths changed since the freeze commit {freeze_commit[:7]}: "
            f"{changed}; {why}"
        )
    # 7. the window has ended
    if not now >= end:
        refuse(f"the window ends {iso(end)}: no scoring before then ({iso(now)} now)")
    # 8. trained models end their training by the window start
    for c in record.get("candidates", []):
        train_end = (c.get("model") or {}).get("train_end")
        if train_end and parse_time(train_end) > start:
            refuse(
                f"{c['key']}: its model's train_end {train_end} is after the window start"
            )
    head = git(repo, "rev-parse", "HEAD").strip()
    return RunState(
        head,
        reg_commit,
        file_sha256(path),
        freeze_commit,
        dirty,
        changed,
        sys.version,
        os.environ.get("POWERTRADER_HOME"),
        note if changed else None,
    )


# --- confirmation (section 8.3) ---------------------------------------------------------


def windows_overlap(a: Mapping[str, str], b: Mapping[str, str]) -> bool:
    """Whether [a.start, a.end] and [b.start, b.end] share any time."""
    return parse_time(a["start"]) < parse_time(b["end"]) and parse_time(
        b["start"]
    ) < parse_time(a["end"])


def check_confirmation(
    confirmation: Mapping[str, Any],
    earlier: Mapping[str, Any],
    earlier_results: Mapping[str, Any],
    every_window: Sequence[Mapping[str, str]],
) -> None:
    """Refuse a confirmation round whose members are not exactly the earlier round's
    provisional (row, statistic) members, unchanged (candidate, parameters, rule,
    direction, statistic, model), or whose window overlaps any registered earlier
    window."""
    for w in every_window:
        if windows_overlap(confirmation["window"], w):
            refuse(
                f"the confirmation window {confirmation['window']} overlaps an earlier "
                f"registered window {w}"
            )
    by_key = {c["key"]: c for c in earlier["candidates"]}
    provisional = {
        (m["candidate"], m["exchange"], m["coin"], m["timeframe"], m["statistic"])
        for m in earlier_results.get("provisional", [])
    }
    members = confirmation.get("members") or []
    keys = {
        (m["candidate"], m["exchange"], m["coin"], m["timeframe"], m["statistic"])
        for m in members
    }
    if keys != provisional:
        refuse(
            "a confirmation round takes exactly the provisional (row, statistic) members: "
            f"missing {sorted(provisional - keys)}, extra {sorted(keys - provisional)}"
        )
    for m in members:
        was = by_key.get(m["candidate"])
        if was is None:
            refuse(f"{m['candidate']} was not registered in the earlier round")
        for field_name in ("rule", "parameters", "kind", "inputs", "input_coins"):
            if m["registration"].get(field_name) != was.get(field_name):
                refuse(
                    f"{m['candidate']}: its {field_name} differs from the earlier round"
                )
        if (m["registration"].get("model") or None) != (was.get("model") or None):
            refuse(f"{m['candidate']}: its model differs from the earlier round")
