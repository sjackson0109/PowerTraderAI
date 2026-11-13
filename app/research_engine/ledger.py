"""
The programme trial ledger (PTAI-RD-001 C section 5, schema v1; work package 2.1).

One JSON line per trial in ``<engine root>/ledger.jsonl`` (``research_engine.store.
default_root``), so that every look at the data, by any tool, counts against a budget.

* ``append`` writes one entry; a trial already in the ledger is not written again.
  Appends from several engine workers take a short lock file, so lines never mix.
* ``sync`` brings in the strategy lab's and the model lab's own trial logs through
  adapters (``from_strategy_lab``, ``from_model_lab``). It only reads them: nothing old
  is rewritten, and a trial is brought in once.
* An engine backtest job (``strategy_lab.run``) writes its own entry when it finishes,
  with its job key, under the same id as its strategy-lab trial, so ``sync`` does not
  count it twice.
* ``counts`` gives the distinct trials per budget (``counted_in``).

Each entry has every field of schema v1 (``FIELDS``); what a source does not record is
None or empty, never guessed. ``kind`` is one of ``KINDS``: an exploratory run is
``exploration``; a trial of a frozen experiment or batch is ``declared``.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pt_paths

VERSION = 1
FILE = "ledger.jsonl"
KINDS = ("exploration", "declared", "unseen_check", "paper_observation")
FIELDS = (
    "ledger_version",
    "trial_id",
    "source",
    "source_trial",
    "job",
    "experiment_id",
    "member",
    "kind",
    "analysis",
    "family",
    "hypothesis_id",
    "candidates",
    "snapshot_id",
    "months",
    "coins",
    "exchange",
    "seeds",
    "code_hash",
    "earlier_exposures",
    "outcome",
    "counted_in",
    "logged_at",
)
LOCK_WAIT_SECONDS = 10.0
LOCK_STALE_SECONDS = 30.0  # a lock this old was left by a process that died


class LedgerError(RuntimeError):
    """An entry that cannot be written."""


def _root(root: Optional[str]) -> str:
    if root is None:
        from research_engine.store import default_root

        root = default_root()
    return os.path.abspath(root)


def path(root: Optional[str] = None) -> str:
    return pt_paths.file_in(_root(root), FILE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def entry(**fields: Any) -> Dict[str, Any]:
    """A schema-v1 entry: ``fields`` over every field's empty value."""
    unknown = sorted(set(fields) - set(FIELDS))
    if unknown:
        raise LedgerError(f"unknown ledger fields {unknown}")
    out: Dict[str, Any] = {name: None for name in FIELDS}
    out.update(candidates=[], coins=[], seeds=[], earlier_exposures=[], outcome={})
    out.update(fields)
    out["ledger_version"] = VERSION
    if not out.get("logged_at"):
        out["logged_at"] = _now()
    return out


def _check(item: Mapping[str, Any]) -> None:
    missing = [k for k in FIELDS if k not in item]
    if missing:
        raise LedgerError(f"a ledger entry needs {missing}")
    for name in ("trial_id", "source", "counted_in"):
        if not isinstance(item.get(name), str) or not item[name].strip():
            raise LedgerError(f"a ledger entry needs a {name}")
    if item.get("kind") not in KINDS:
        raise LedgerError(f"unknown trial kind {item.get('kind')!r} (one of {KINDS})")


def entries(root: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every entry, oldest first."""
    try:
        with open(path(root), encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


class _Lock:
    """A lock file next to the ledger, for one append at a time across processes."""

    def __init__(self, root: str) -> None:
        self.path = pt_paths.file_in(root, FILE + ".lock")

    def __enter__(self) -> "_Lock":
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except (FileExistsError, PermissionError):
                # another append holds it; on Windows a lock file its holder is
                # deleting refuses the create with PermissionError instead
                try:
                    stale = (
                        time.time() - os.path.getmtime(self.path) > LOCK_STALE_SECONDS
                    )
                except OSError:
                    stale = False  # gone, or going, since: try again
                if stale:
                    try:
                        os.remove(self.path)
                    except OSError:
                        pass
                    continue
                if time.monotonic() > deadline:
                    raise LedgerError(
                        f"the ledger is locked, or its folder cannot be written "
                        f"({self.path})"
                    ) from None
                time.sleep(0.05)

    def __exit__(self, *exc: Any) -> None:
        try:
            os.remove(self.path)
        except OSError:
            pass


def append(item: Mapping[str, Any], root: Optional[str] = None) -> bool:
    """Write ``item`` (an ``entry``); False when its trial is already in the ledger."""
    _check(item)
    root = _root(root)
    line = json.dumps(dict(item), sort_keys=True, ensure_ascii=False, default=str)
    with _Lock(root):
        if any(e.get("trial_id") == item["trial_id"] for e in entries(root)):
            return False
        with open(path(root), "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
    return True


def counts(root: Optional[str] = None) -> Dict[str, int]:
    """Distinct trials per budget (``counted_in``)."""
    seen: Dict[str, set] = {}
    for e in entries(root):
        seen.setdefault(str(e.get("counted_in")), set()).add(e.get("trial_id"))
    return {k: len(v) for k, v in sorted(seen.items())}


# --- adapters ------------------------------------------------------------------------


def _params_sha256(params: Mapping[str, Any]) -> str:
    text = json.dumps(dict(params), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_json(file: str) -> Optional[Dict[str, Any]]:
    try:
        with open(file, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _exchanges(sources: Any) -> Optional[str]:
    """The exchanges a run's series came from (its ``sources``), or None."""
    names = set()
    if isinstance(sources, Mapping):
        for value in sources.values():
            if isinstance(value, Mapping) and value.get("exchange"):
                names.add(str(value["exchange"]))
    return ", ".join(sorted(names)) or None


def _run_parts(record: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """What a strategy-lab run record says about its candidate and data."""
    if not record:
        return {}
    strategy = record.get("strategy") or {}
    candidates = []
    if strategy.get("id"):
        candidates.append(
            {
                "id": strategy.get("id"),
                "version": strategy.get("version"),
                "params_sha256": strategy.get("params_sha256"),
                "timeframe": strategy.get("timeframe"),
                "overlays": [
                    {
                        "id": o.get("id"),
                        "version": o.get("version"),
                        "params_sha256": _params_sha256(o.get("params") or {}),
                    }
                    for o in strategy.get("overlays") or []
                ],
            }
        )
    seed = (record.get("config") or {}).get("seed")
    return {
        "candidates": candidates,
        "seeds": [seed] if seed is not None else [],
        "exchange": _exchanges(record.get("sources")),
    }


def from_strategy_lab(
    line: Mapping[str, Any],
    record: Optional[Mapping[str, Any]] = None,
    job: Optional[str] = None,
) -> Dict[str, Any]:
    """A strategy-lab trial line (``strategy_lab.experiment.log_trial``) as an entry.
    ``record``: its run's ``run.json``, when there is one (an exploratory run)."""
    trial = str(line["trial"])
    experiment_id, _, member = trial.partition("/")
    analysis = str(line.get("kind") or "strategy")
    exploring = analysis == "exploration"
    return entry(
        trial_id=f"strategy_lab:{trial}",
        source="strategy_lab",
        source_trial=trial,
        job=job,
        experiment_id="exploration" if exploring else experiment_id,
        member=experiment_id if exploring else member,
        kind="exploration" if exploring else "declared",
        analysis=analysis,
        months={"start": line.get("start"), "end": line.get("end")},
        coins=list(line.get("coins") or []),
        outcome={"summary": dict(line.get("summary") or {})},
        counted_in="exploration" if exploring else experiment_id,
        logged_at=line.get("logged_at") or _now(),
        **_run_parts(record),
    )


def from_model_lab(line: Mapping[str, Any]) -> Dict[str, Any]:
    """A model-lab trial line (``model_lab.batch.log_trial``) as an entry: a trial of
    a frozen batch, so ``declared``."""
    trial = str(line["trial"])
    batch, _, member = trial.partition("/")
    params = line.get("params")
    candidates = []
    if line.get("contestant"):
        candidates.append(
            {
                "id": line.get("contestant"),
                "version": None,
                "params_sha256": (
                    _params_sha256(params) if isinstance(params, Mapping) else None
                ),
            }
        )
    outcome = {
        k: line.get(k) for k in ("trades", "per_day", "p_r1", "p_r2", "p") if k in line
    }
    return entry(
        trial_id=f"model_lab:{trial}",
        source="model_lab",
        source_trial=trial,
        experiment_id=line.get("batch") or batch,
        member=line.get("contestant") or member,
        kind="declared",
        analysis=str(line.get("kind") or "trading"),
        family=line.get("family"),
        candidates=candidates,
        code_hash=line.get("batch_sha256"),
        outcome={"summary": outcome},
        counted_in=str(line.get("batch") or batch),
        logged_at=line.get("logged_at") or _now(),
    )


def _lines(file: str) -> Iterable[Dict[str, Any]]:
    try:
        with open(file, encoding="utf-8") as f:
            for raw in f:
                if raw.strip():
                    try:
                        line = json.loads(raw)
                    except ValueError:
                        continue
                    if isinstance(line, dict) and line.get("trial"):
                        yield line
    except FileNotFoundError:
        return


def sync(root: Optional[str] = None) -> int:
    """Bring in every strategy-lab and model-lab trial not in the ledger yet; the
    number brought in. The source logs are only read."""
    from model_lab import batch
    from strategy_lab import experiment, runs

    added = 0
    for line in _lines(experiment.trials_path()):
        record = None
        if line.get("kind") == "exploration":
            run_id = str(line["trial"]).partition("/")[0]
            record = _read_json(os.path.join(runs.runs_dir(), run_id, "run.json"))
        added += append(from_strategy_lab(line, record), root)
    for line in _lines(batch.trials_path()):
        added += append(from_model_lab(line), root)
    return added
