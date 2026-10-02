"""
Strategy catalogue (lite) and registry (FDS-121 section 5).

``catalogue.json`` describes every strategy / overlay; the registry maps
``strategy_id`` -> class. They are cross-checked when the package is imported and
loading **fails loudly** if an entry has no class, a class has no entry, a
required field is missing, or a default parameter is outside its bounds.

Field names are identical to issue #121 so the full schema can be added later.
(JSON, not YAML: PyYAML is not in requirements.txt.)
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Mapping, Optional

REQUIRED_FIELDS = (
    "strategy_id",
    "strategy_name",
    "family",
    "class_type",
    "long_short_mode",
    "timeframe_primary",
    "entry_logic_summary",
    "exit_logic_summary",
    "dependencies_indicators",
    "default_params",
    "param_bounds",
    "version",
)
CLASS_TYPES = ("main", "risk_overlay")
CATALOGUE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalogue.json")


class CatalogueError(RuntimeError):
    """The catalogue and the registry disagree, or an entry is malformed."""


class ParamError(ValueError):
    """Strategy parameters are unknown, mistyped or out of bounds."""


_REGISTRY: Dict[str, type] = {}


def register(strategy_id: str) -> Callable[[type], type]:
    """Class decorator: ``@register("STRAT-001")``."""

    def deco(cls: type) -> type:
        if strategy_id in _REGISTRY and _REGISTRY[strategy_id] is not cls:
            raise CatalogueError(f"{strategy_id} is registered twice")
        _REGISTRY[strategy_id] = cls
        cls.strategy_id = strategy_id  # type: ignore[attr-defined]
        return cls

    return deco


# --- parameter bounds ------------------------------------------------------------

_BOUND_KINDS = {"min", "max", "values", "type"}


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_bound_spec(strategy_id: str, name: str, spec: Any, default: Any) -> None:
    where = f"{strategy_id}.param_bounds.{name}"
    if not isinstance(spec, dict) or not spec:
        raise CatalogueError(f"{where} must be a non-empty object")
    unknown = set(spec) - _BOUND_KINDS
    if unknown:
        raise CatalogueError(f"{where} has unknown keys {sorted(unknown)}")
    try:
        check_value(strategy_id, name, default, spec)
    except ParamError as exc:
        raise CatalogueError(f"default for {where} is invalid: {exc}") from exc


def check_value(strategy_id: str, name: str, value: Any, spec: Mapping[str, Any]) -> None:
    """Raise ParamError if ``value`` violates ``spec`` (min/max, values, type)."""
    where = f"{strategy_id}.{name}"
    kind = spec.get("type")
    if kind == "bool":
        if not isinstance(value, bool):
            raise ParamError(f"{where} must be true/false, got {value!r}")
        return
    if "values" in spec:
        if value not in spec["values"]:
            raise ParamError(f"{where}={value!r} is not one of {spec['values']}")
        return
    if kind == "stages":
        _check_stages(where, value)
        return
    if "min" in spec or "max" in spec:
        if not _is_number(value):
            raise ParamError(f"{where} must be a number, got {value!r}")
        if value != value:
            raise ParamError(f"{where} must not be NaN")
        if "min" in spec and value < spec["min"]:
            raise ParamError(f"{where}={value} is below the minimum {spec['min']}")
        if "max" in spec and value > spec["max"]:
            raise ParamError(f"{where}={value} is above the maximum {spec['max']}")
        return
    raise CatalogueError(f"{where}: bound spec {dict(spec)} defines no constraint")


def _check_stages(where: str, value: Any) -> None:
    """``[[gain_pct, lock_pct], ...]``: positive, gains strictly increasing, lock < gain."""
    if not isinstance(value, (list, tuple)) or not value:
        raise ParamError(f"{where} must be a non-empty list of [gain_pct, lock_pct]")
    last_gain = 0.0
    for stage in value:
        if (
            not isinstance(stage, (list, tuple))
            or len(stage) != 2
            or not all(_is_number(x) for x in stage)
        ):
            raise ParamError(f"{where}: each stage must be [gain_pct, lock_pct], got {stage!r}")
        gain, lock = float(stage[0]), float(stage[1])
        if gain <= last_gain:
            raise ParamError(f"{where}: stage gains must be positive and strictly increasing")
        if lock < 0 or lock >= gain:
            raise ParamError(f"{where}: lock_pct must be >= 0 and below gain_pct ({stage!r})")
        last_gain = gain


# --- building and validating -------------------------------------------------------


def build_catalogue(
    entries: List[dict], registry: Mapping[str, type]
) -> Dict[str, dict]:
    """Validate ``entries`` against ``registry``; returns ``{strategy_id: entry}``."""
    if not isinstance(entries, list):
        raise CatalogueError("catalogue must be a list of entries")
    out: Dict[str, dict] = {}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise CatalogueError(f"entry #{i} is not an object")
        sid = entry.get("strategy_id", f"<entry #{i}>")
        missing = [f for f in REQUIRED_FIELDS if f not in entry]
        if missing:
            raise CatalogueError(f"{sid}: missing required fields {missing}")
        if sid in out:
            raise CatalogueError(f"{sid}: duplicate strategy_id")
        if entry["class_type"] not in CLASS_TYPES:
            raise CatalogueError(f"{sid}: class_type must be one of {CLASS_TYPES}")
        if entry["long_short_mode"] != "long_only":
            raise CatalogueError(f"{sid}: only long_only is supported in this batch")
        from market_data.timeframes import TIMEFRAME_SECONDS

        if entry["timeframe_primary"] not in TIMEFRAME_SECONDS:
            raise CatalogueError(f"{sid}: unsupported timeframe_primary {entry['timeframe_primary']!r}")
        for key in ("default_params", "param_bounds"):
            if not isinstance(entry[key], dict):
                raise CatalogueError(f"{sid}: {key} must be an object")
        if not isinstance(entry["dependencies_indicators"], list):
            raise CatalogueError(f"{sid}: dependencies_indicators must be a list")
        if set(entry["default_params"]) != set(entry["param_bounds"]):
            raise CatalogueError(
                f"{sid}: default_params and param_bounds must name the same parameters"
            )
        for name, spec in entry["param_bounds"].items():
            _check_bound_spec(sid, name, spec, entry["default_params"][name])
        out[sid] = entry

    for sid in out:
        if sid not in registry:
            raise CatalogueError(f"{sid}: catalogue entry has no registered class")
    for sid in registry:
        if sid not in out:
            raise CatalogueError(f"{sid}: registered class has no catalogue entry")
    return out


def load_entries(path: str = CATALOGUE_PATH) -> List[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        raise CatalogueError(f"cannot read catalogue {path}: {exc}") from exc


# Import the modules that register strategy / overlay classes, then validate.
from strategies import builtin as _builtin  # noqa: E402,F401

CATALOGUE: Dict[str, dict] = build_catalogue(load_entries(), _REGISTRY)


# --- lookup / construction -------------------------------------------------------------


def get_entry(strategy_id: str) -> dict:
    try:
        return CATALOGUE[strategy_id]
    except KeyError:
        raise CatalogueError(f"unknown strategy id {strategy_id!r}") from None


def list_ids(class_type: Optional[str] = None) -> List[str]:
    return sorted(
        sid for sid, e in CATALOGUE.items() if class_type is None or e["class_type"] == class_type
    )


def resolve_params(strategy_id: str, overrides: Mapping[str, Any]) -> Dict[str, Any]:
    """Defaults + ``overrides``, rejecting unknown names and out-of-bounds values."""
    entry = get_entry(strategy_id)
    params = dict(entry["default_params"])
    for name, value in overrides.items():
        if name not in params:
            raise ParamError(f"{strategy_id}: unknown parameter {name!r}")
        params[name] = value
    for name, value in params.items():
        check_value(strategy_id, name, value, entry["param_bounds"][name])
    return params


def create(strategy_id: str, **params: Any):
    """Instantiate a registered strategy / overlay with validated parameters."""
    get_entry(strategy_id)
    return _REGISTRY[strategy_id](**params)
