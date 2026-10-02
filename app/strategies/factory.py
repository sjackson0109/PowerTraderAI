"""Build a ``StrategyRunner`` from catalogue ids (used by the CLI and the live engine)."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from strategies.catalogue import CatalogueError, create, get_entry
from strategies.runner import StrategyRunner


def build_runner(
    strategy_id: str,
    params: Optional[Mapping[str, Any]] = None,
    overlays: Sequence[Mapping[str, Any]] = (),
) -> StrategyRunner:
    """
    ``overlays`` is ``[{"id": "OVL-ATR", "params": {...}}, ...]``. Raises
    ``CatalogueError`` / ``ParamError`` for unknown ids, a wrong class_type, or
    bad parameters - nothing is guessed.
    """
    if get_entry(strategy_id)["class_type"] != "main":
        raise CatalogueError(f"{strategy_id} is not a main strategy")
    strategy = create(strategy_id, **dict(params or {}))
    built = []
    for spec in overlays:
        oid = spec.get("id") if isinstance(spec, Mapping) else None
        if not oid:
            raise CatalogueError(f"overlay spec needs an 'id': {spec!r}")
        if get_entry(oid)["class_type"] != "risk_overlay":
            raise CatalogueError(f"{oid} is not a risk overlay")
        built.append(create(oid, **dict(spec.get("params") or {})))
    return StrategyRunner(strategy, built)


def parse_overlay_ids(text: Optional[str]) -> list:
    """``"OVL-ATR,OVL-COOLDOWN"`` -> ``[{"id": "OVL-ATR"}, {"id": "OVL-COOLDOWN"}]``."""
    return [{"id": part.strip()} for part in (text or "").split(",") if part.strip()]
