"""
Experiment records, frozen before any result exists (FDS-SR-001 sections 5.9 and 6).

An **experiment** is one declared comparison: a strategy (with its version, full
parameters and their SHA-256, timeframe and overlays), an optional model and sizing
policy, the market (exchange order, coins, series SHA-256s), the windows, the costs, the
accounts, the baselines with their seeds, the tests and the family they belong to.

* ``freeze`` writes it, sealed with its own SHA-256, with the code's hashes and the
  libraries' versions, under ``<data dir>/strategy_lab/experiments/<id>/`` and refuses
  to overwrite one. Nothing is scored by freezing.
* ``verify`` refuses a frozen experiment whose record, code, libraries or candles have
  changed since: such a run would not be the declared one.
* ``log_trial`` appends one line per scored member to ``<data dir>/strategy_lab/
  trials.jsonl``, with its kind and the months it read, as soon as it is scored; an
  exploratory run from Settings is a trial of kind "exploration". ``trial_counts``
  counts the distinct trials of each kind.

Registering and running a declared experiment is the owner's decision (FDS-SR-001 M5c);
nothing in this module does either on its own.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional

from model_lab.batch import _canonical, _seal, _write_json
from strategies.catalogue import create, get_entry

SPEC = "FDS-SR-001"
SPEC_VERSION = "1"
TRIAL_KINDS = (
    "strategy",
    "gate",
    "model",
    "forecast",
    "calibration",
    "sizing",
    "exploration",
)
REQUIRED = (
    "family",
    "members",
    "strategy",
    "market",
    "windows",
    "costs",
    "accounts",
    "baselines",
    "tests",
)
CODE_PACKAGES = ("strategies", "strategy_lab", "backtest", "signal_fusion", "model_lab")
LIBRARIES = ("numpy", "pandas", "sklearn")


class ExperimentError(RuntimeError):
    """An experiment cannot be frozen, or has changed since it was."""


# --- files ------------------------------------------------------------------------------


def lab_dir() -> str:
    import pt_paths

    return os.path.join(pt_paths.data_dir(), "strategy_lab")


def experiment_dir(experiment_id: str) -> str:
    return os.path.join(lab_dir(), "experiments", experiment_id)


def trials_path() -> str:
    return os.path.join(lab_dir(), "trials.jsonl")


# --- what a record holds -------------------------------------------------------------------


def strategy_record(
    strategy_id: str,
    params: Optional[Mapping[str, Any]] = None,
    overlays: Iterable[Mapping[str, Any]] = (),
    timeframe: str = "1d",
) -> Dict[str, Any]:
    """A strategy as a record holds it: every parameter (defaults filled in), their
    SHA-256, and each overlay's version and parameters."""
    full = dict(create(strategy_id, **dict(params or {})).params)
    shown = []
    for spec in overlays:
        oid = spec["id"]
        shown.append(
            {
                "id": oid,
                "version": get_entry(oid)["version"],
                "params": dict(create(oid, **dict(spec.get("params") or {})).params),
            }
        )
    return {
        "id": strategy_id,
        "version": get_entry(strategy_id)["version"],
        "timeframe": timeframe,
        "params": full,
        "params_sha256": hashlib.sha256(_canonical(full)).hexdigest(),
        "overlays": shown,
    }


def code_hashes(app: Optional[str] = None) -> Dict[str, str]:
    """SHA-256 (LF line endings) of every module a strategy experiment runs."""
    app = app or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out: Dict[str, str] = {}
    for package in CODE_PACKAGES:
        for path in sorted(
            glob.glob(os.path.join(app, package, "**", "*.py"), recursive=True)
        ):
            name = os.path.relpath(path, app).replace("\\", "/")
            with open(path, "rb") as f:
                out[name] = hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()
    for extra in (
        "position_sizing.py",
        "market_data/candles.py",
        "market_data/gaps.py",
        "market_data/timeframes.py",
    ):
        path = os.path.join(app, extra)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                out[extra] = hashlib.sha256(
                    f.read().replace(b"\r\n", b"\n")
                ).hexdigest()
    return out


def library_versions() -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for name in LIBRARIES:
        try:
            module = __import__(name)
            out[name] = str(getattr(module, "__version__", None))
        except ImportError:
            out[name] = None
    return out


# --- freezing and checking -------------------------------------------------------------------


def freeze(
    experiment_id: str, declaration: Mapping[str, Any], now: Optional[float] = None
) -> Dict[str, Any]:
    """Seal and write the declaration (see the module docstring); returns the record."""
    missing = [k for k in REQUIRED if k not in declaration]
    if missing:
        raise ExperimentError(f"the declaration is missing {missing}")
    if (
        not str(experiment_id).strip()
        or os.sep in experiment_id
        or "/" in experiment_id
    ):
        raise ExperimentError(f"not a usable experiment id: {experiment_id!r}")
    folder = experiment_dir(experiment_id)
    path = os.path.join(folder, "experiment.json")
    if os.path.exists(path):
        raise ExperimentError(f"experiment {experiment_id} is already frozen")
    frozen_at = datetime.fromtimestamp(now or time.time(), tz=timezone.utc)
    record = _seal(
        {
            **json.loads(json.dumps(dict(declaration), default=str)),
            "id": experiment_id,
            "spec": SPEC,
            "spec_version": SPEC_VERSION,
            "frozen_at": frozen_at.isoformat(),
            "code": code_hashes(),
            "libraries": library_versions(),
        }
    )
    _write_json(path, record)
    return record


def read(experiment_id: str) -> Dict[str, Any]:
    path = os.path.join(experiment_dir(experiment_id), "experiment.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        raise ExperimentError(
            f"experiment {experiment_id}: cannot read it ({exc})"
        ) from exc


def verify(
    experiment_id: str, series_sha256: Optional[Mapping[str, str]] = None
) -> Dict[str, Any]:
    """The frozen record, if nothing it depends on has changed; ExperimentError
    otherwise, naming what changed."""
    record = read(experiment_id)
    if _seal({k: v for k, v in record.items() if k != "sha256"})[
        "sha256"
    ] != record.get("sha256"):
        raise ExperimentError(f"experiment {experiment_id}: its record has been edited")
    now_code = code_hashes()
    changed = sorted(
        name
        for name in set(record["code"]) | set(now_code)
        if record["code"].get(name) != now_code.get(name)
    )
    if changed:
        raise ExperimentError(
            f"experiment {experiment_id}: the code changed since it was frozen "
            f"({', '.join(changed[:5])}{'...' if len(changed) > 5 else ''})"
        )
    if record["libraries"] != library_versions():
        raise ExperimentError(f"experiment {experiment_id}: the libraries changed")
    frozen_series = (record.get("market") or {}).get("series_sha256") or {}
    if series_sha256 is not None:
        moved = sorted(
            k for k in frozen_series if series_sha256.get(k) != frozen_series[k]
        )
        if moved:
            raise ExperimentError(
                f"experiment {experiment_id}: the candles changed ({', '.join(moved)})"
            )
    return record


# --- the trial log ------------------------------------------------------------------------------


def log_trial(
    experiment_id: str,
    member: str,
    kind: str,
    start: str,
    end: str,
    coins: Iterable[str],
    summary: Optional[Mapping[str, Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Append one scored trial: ``<experiment>/<member>``, its kind and its months."""
    if kind not in TRIAL_KINDS:
        raise ExperimentError(f"unknown trial kind {kind!r} (one of {TRIAL_KINDS})")
    line = {
        "trial": f"{experiment_id}/{member}",
        "kind": kind,
        "start": str(start),
        "end": str(end),
        "coins": sorted(coins),
        "summary": dict(summary or {}),
        "logged_at": datetime.fromtimestamp(
            now or time.time(), tz=timezone.utc
        ).isoformat(),
    }
    path = trials_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n")
    return line


def trials() -> list:
    path = trials_path()
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def trial_counts() -> Dict[str, int]:
    """Distinct trials of each kind (a trial logged twice counts once)."""
    seen: Dict[str, set] = {k: set() for k in TRIAL_KINDS}
    for line in trials():
        seen.setdefault(line.get("kind", "strategy"), set()).add(line["trial"])
    return {k: len(v) for k, v in seen.items()}
