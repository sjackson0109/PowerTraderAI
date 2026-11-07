"""
A round's registration and the run's refusals (FDS-SIG-001 sections 11 and 12).

**Files.** Round N lives in ``docs/dev/sig-audit/round-<N>/``:

* ``registration.json`` (section 12, step 1), committed in its own commit, dated before
  the window starts;
* ``freeze.json`` (step 2), committed in its own commit: the frozen paths (at least
  ``app/`` and the audit script). The commit that first added it is the freeze commit,
  and it never changes afterwards;
* the ranking and history evidence (step 0) and, after the window, the candle records,
  results and evidence series (steps 3 to 5);
* ``cancellation.json`` (step 6), when a material defect found before results cancels
  the registration (``cancellation_record``); a cancelled round is never run;
* ``superseded/<k>-<commit>/`` (step 6), the earlier results of a defect fix after
  results (``supersede_results``), with their series, report and SHA-256.

**The run refuses** (step 4), logging an ERROR, when:

0. the round's registration was cancelled (a ``cancellation.json`` exists), or the
   registration replaces a cancelled round whose cancellation record is not committed,
   differs from the SHA-256 it records, or was not committed before it;
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

Refusal 6 and the changed freeze record (refusal 5) are in step 4's list since the
owner's decision D8 (2026-11-07). **A defect found before results** is never fixed in
place and never run as frozen to be superseded later (owner, D9): the registration is
cancelled (refusal 0), and a new registration in a later round, with a window that
starts after its own registration commit, replaces it.

**A confirmation round** (section 8.3, ``check_confirmation``) is refused when its
members are not exactly the earlier round's provisional ones, unchanged, or when it
would reuse evaluated observations (owner, A6): its window overlaps a registered
round's window, unless that round was cancelled before results (``round_windows``), or
it does not start after its own registration commit. An unexamined cancelled window
alone does not bar it, as it does not bar a replacement (A3).

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

CANCELLATION = "cancellation.json"
SUPERSEDED = "superseded"
PACKAGES = ("numpy", "scipy", "pandas")

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


def _at_head(repo: str, rel: str) -> bool:
    return bool(git(repo, "ls-tree", "--name-only", "HEAD", "--", rel).strip())


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
    packages: Optional[Dict[str, str]] = None  # the numerical packages' versions

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
    # 0. not cancelled (step 6: a defect found before results)
    cancelled = os.path.join(repo, rel_round_dir(n), CANCELLATION)
    if os.path.exists(cancelled):
        try:
            with open(cancelled, "r", encoding="utf-8") as f:
                defect = json.load(f).get("defect", "")
        except (OSError, ValueError):
            defect = "the record cannot be read"
        refuse(
            f"round {n}'s registration was cancelled ({defect}): a cancelled round is "
            "never run; a new registration in a later round replaces it"
        )
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
    # 0. a replacement names a cancelled round whose committed record came first
    if record.get("replaces"):
        _check_replacement(repo, n, record["replaces"], reg_commit)
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
        package_versions(),
    )


def package_versions() -> Dict[str, str]:
    """The versions of the packages the statistics depend on (the run records them)."""
    from importlib import metadata

    out = {}
    for name in PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "not installed"
    return out


# --- a defect found before results: cancellation (section 12, step 6; owner D9) ---------


def has_results(folder: str) -> bool:
    """Whether the round has results: ``results.json``, or earlier results kept by a
    defect fix (``superseded/*/results.json``)."""
    if os.path.exists(os.path.join(folder, "results.json")):
        return True
    old = os.path.join(folder, SUPERSEDED)
    return os.path.isdir(old) and any(
        os.path.exists(os.path.join(old, name, "results.json"))
        for name in os.listdir(old)
    )


def cancellation_record(
    repo: str,
    n: int,
    defect: str,
    now: Optional[datetime] = None,
    frozen: Sequence[str] = FROZEN_PATHS,
) -> Dict[str, Any]:
    """The record that cancels round ``n``'s registration for a material defect found
    before results (section 12, step 6). It is committed on its own as
    ``cancellation.json`` in the round's folder; the round is then never run
    (refusal 0), and a new registration in a later round, with a window that starts
    after its own registration commit, replaces it. It records the defect, the
    registration's commit and SHA-256, the freeze commit, the code at cancellation,
    and whether the window had started or ended.

    Refused when there is no committed registration, when the round is already
    cancelled, or when results exist (a defect found after results is corrected
    through ``--supersede``)."""
    now = now or datetime.now(timezone.utc)
    folder = round_dir(repo, n)
    rel = rel_round_dir(n)
    rel_reg = f"{rel}/registration.json"
    note = (defect or "").strip()
    if not note:
        refuse('a cancellation states the defect: --defect "<what is wrong and why>"')
    if os.path.exists(os.path.join(folder, CANCELLATION)):
        refuse(f"round {n} is already cancelled")
    if has_results(folder):
        refuse(
            f"round {n} has results: a defect found after results is corrected through "
            "--supersede, which keeps the earlier results; it is not cancelled"
        )
    reg_commit = _last_commit(repo, rel_reg)
    if not reg_commit:
        refuse(f"round {n} has no committed registration to cancel")
    if git(repo, "status", "--porcelain", "--", rel_reg).strip():
        refuse(f"the registration file {rel_reg} has uncommitted changes")
    path = os.path.join(repo, rel_reg)
    with open(path, "r", encoding="utf-8") as f:
        record = json.load(f)
    start = parse_time(record["window"]["start"])
    end = parse_time(record["window"]["end"])
    freezes = _commits_touching(repo, f"{rel}/freeze.json")
    freeze_commit = freezes[-1] if freezes else None
    changed = []
    if freeze_commit:
        changed = [
            p
            for p in git(
                repo, "diff", "--name-only", freeze_commit, "HEAD", "--", *frozen
            ).splitlines()
            if p.strip()
        ]
    dirty = git(repo, "status", "--porcelain", "--", *frozen).splitlines()
    return {
        "round": int(n),
        "spec": SPEC,
        "kind": "cancellation",
        "cancelled_at": iso(now),
        "defect": note,
        "registration": {
            "file": rel_reg,
            "commit": reg_commit,
            "sha256": file_sha256(path),
            "window": dict(record["window"]),
        },
        "freeze_commit": freeze_commit,
        "head": git(repo, "rev-parse", "HEAD").strip(),
        "frozen_files_changed_since_freeze": changed,
        "frozen_files_dirty": dirty,
        "window_started": now >= start,
        "window_ended": now >= end,
        "results": None,
        "replacement": "a new registration in a later round, with a window that starts "
        "after its own registration commit (section 12, step 6)",
    }


def replacement_record(repo: str, cancelled: int) -> Dict[str, Any]:
    """What a new registration records of the cancelled round it replaces (its
    ``replaces``): refused unless that round's cancellation record is committed and
    unchanged since."""
    rel = f"{rel_round_dir(cancelled)}/{CANCELLATION}"
    path = os.path.join(repo, rel)
    commit = _last_commit(repo, rel)
    if not os.path.isfile(path) or not commit:
        refuse(f"round {cancelled} has no committed cancellation record ({rel})")
    if git(repo, "status", "--porcelain", "--", rel).strip():
        refuse(f"the cancellation record {rel} has uncommitted changes")
    with open(path, "r", encoding="utf-8") as f:
        record = json.load(f)
    return {
        "round": int(cancelled),
        "cancellation": rel,
        "cancellation_commit": commit,
        "cancellation_sha256": file_sha256(path),
        "cancelled_window": record["registration"]["window"],
        "window_started_when_cancelled": bool(record.get("window_started")),
        "defect": record.get("defect", ""),
    }


def _check_replacement(
    repo: str, n: int, replaces: Mapping[str, Any], reg_commit: str
) -> None:
    cancelled = int(replaces.get("round", -1))
    if cancelled == int(n):
        refuse(f"round {n} cannot replace itself")
    rec = replacement_record(repo, cancelled)
    if rec["cancellation_sha256"] != replaces.get("cancellation_sha256"):
        refuse(
            f"round {cancelled}'s cancellation record differs from the SHA-256 round "
            f"{n}'s registration records"
        )
    ancestor = subprocess.run(
        [
            "git",
            "-C",
            repo,
            "merge-base",
            "--is-ancestor",
            rec["cancellation_commit"],
            reg_commit,
        ],
        capture_output=True,
    )
    if ancestor.returncode != 0 or rec["cancellation_commit"] == reg_commit:
        refuse(
            f"round {cancelled}'s cancellation was not committed before round {n}'s "
            "registration"
        )


# --- a defect found after results: supersession (section 12, step 6) --------------------


def supersede_results(
    folder: str, note: Optional[str], report_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Before a defect fix's run after results: the earlier results, their evidence
    series and their report move to ``superseded/<k>-<commit>/``, with the note, the
    time and each file's SHA-256, and stay beside the new verdicts. Returns every
    earlier result, oldest first, with its note and commit, for the report. Without
    results there is nothing to supersede; with results, a re-run needs the note."""
    import shutil

    path = os.path.join(folder, "results.json")
    old_dir = os.path.join(folder, SUPERSEDED)
    earlier = []
    if os.path.isdir(old_dir):
        for name in sorted(os.listdir(old_dir), key=lambda x: int(x.split("-")[0])):
            p = os.path.join(old_dir, name, "results.json")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    old = json.load(f)
                with open(
                    os.path.join(old_dir, name, "note.json"), encoding="utf-8"
                ) as f:
                    old["note"] = json.load(f)["note"]
                old["commit"] = (old.get("state") or {}).get("head")
                earlier.append(old)
    if not os.path.exists(path):
        return earlier
    text = (note or "").strip()
    if not text:
        refuse('results exist: a re-run needs --supersede "<what changed and why>"')
    with open(path, "r", encoding="utf-8") as f:
        old = json.load(f)
    head = (old.get("state") or {}).get("head") or "unknown"
    target = os.path.join(old_dir, f"{len(earlier) + 1}-{head[:7]}")
    os.makedirs(target)
    files = {"results.json": file_sha256(path)}
    shutil.move(path, os.path.join(target, "results.json"))
    series = os.path.join(folder, "series")
    if os.path.isdir(series):
        for name in sorted(os.listdir(series)):
            files[f"series/{name}"] = file_sha256(os.path.join(series, name))
        shutil.move(series, os.path.join(target, "series"))
    if report_path and os.path.exists(report_path):
        files["report.md"] = file_sha256(report_path)
        shutil.copyfile(report_path, os.path.join(target, "report.md"))
    with open(
        os.path.join(target, "note.json"), "w", encoding="utf-8", newline="\n"
    ) as f:
        json.dump(
            {
                "note": text,
                "superseded_at": iso(datetime.now(timezone.utc)),
                "results_commit": head,
                "files_sha256": files,
            },
            f,
            indent=1,
            sort_keys=True,
        )
        f.write("\n")
    old["note"] = text
    old["commit"] = head
    return earlier + [old]


# --- confirmation (section 8.3) ---------------------------------------------------------


def windows_overlap(a: Mapping[str, str], b: Mapping[str, str]) -> bool:
    """Whether [a.start, a.end] and [b.start, b.end] share any time."""
    return parse_time(a["start"]) < parse_time(b["end"]) and parse_time(
        b["start"]
    ) < parse_time(a["end"])


CANCELLED_UNEXAMINED = "cancelled before results"


def round_windows(repo: str, exclude: Sequence[int] = ()) -> List[Dict[str, Any]]:
    """Every round with a committed registration, with its committed window and its
    status (owner, A6): ``results`` when it has results, CANCELLED_UNEXAMINED when a
    committed, unchanged cancellation record cancelled it before results, otherwise
    ``registered`` (its observations are still to be evaluated). A cancellation that is
    not committed, has changed, or sits beside results does not count: the window then
    stays as ``registered`` or ``results``."""
    base = os.path.join(repo, "docs", "dev", "sig-audit")
    found = []
    names = os.listdir(base) if os.path.isdir(base) else []
    for name in names:
        if not name.startswith("round-") or not name[6:].isdigit():
            continue
        k = int(name[6:])
        rel_reg = f"{rel_round_dir(k)}/registration.json"
        if k in exclude or not _at_head(repo, rel_reg):
            continue
        record = json.loads(git(repo, "show", f"HEAD:{rel_reg}"))
        folder = round_dir(repo, k)
        status = "results" if has_results(folder) else "registered"
        rel_cancel = f"{rel_round_dir(k)}/{CANCELLATION}"
        if (
            status == "registered"
            and _at_head(repo, rel_cancel)
            and not git(repo, "status", "--porcelain", "--", rel_cancel).strip()
            and json.loads(git(repo, "show", f"HEAD:{rel_cancel}")).get("round") == k
        ):
            status = CANCELLED_UNEXAMINED
        found.append({"round": k, "window": dict(record["window"]), "status": status})
    return sorted(found, key=lambda w: w["round"])


def check_confirmation(
    confirmation: Mapping[str, Any],
    earlier: Mapping[str, Any],
    earlier_results: Mapping[str, Any],
    windows: Sequence[Mapping[str, Any]],
    registration_time: datetime,
) -> None:
    """Refuse a confirmation round whose members are not exactly the earlier round's
    provisional (row, statistic) members, unchanged (candidate, parameters, rule,
    direction, statistic, model), or that would reuse evaluated observations (owner,
    A6): its window overlaps a round's window in ``windows`` (``round_windows``) other
    than one cancelled before results, or it does not start after its own registration
    commit at ``registration_time``, as section 11 requires of every round."""
    start = parse_time(confirmation["window"]["start"])
    if not registration_time < start or start < earliest_start(registration_time):
        refuse(
            f"the confirmation window starts {iso(start)}, not after its registration "
            f"commit ({iso(registration_time)}) at the earliest start "
            f"{iso(earliest_start(registration_time))}"
        )
    for w in windows:
        if w["status"] == CANCELLED_UNEXAMINED:
            continue
        if windows_overlap(confirmation["window"], w["window"]):
            refuse(
                f"the confirmation window {confirmation['window']} overlaps round "
                f"{w['round']}'s window {w['window']} ({w['status']})"
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
