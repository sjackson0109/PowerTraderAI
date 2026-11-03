"""
Strategy settings reader (FDS-121 section 7), fail-closed.

Keys (all under ``strategy.``): ``engine`` (``catalogue`` | ``legacy_neural``,
default ``catalogue``), ``active_id`` (default ``STRAT-001``), ``timeframe``
(default ``1h``), ``params`` (``{strategy_id: {name: value}}``: each strategy's
parameters that differ from its catalogue defaults, default none) and ``overlays``
(``[{"id", "params"}]``, default none). Settings > Strategy writes all of them.

The coins traded are not a strategy setting: they are the coins in Settings, and in
paper mode the paper-trading coins (``paper_coins.py``). A ``strategy.symbols`` left
in an older settings file is ignored.

Missing keys take their defaults. A value that is present but wrong (unknown
engine, unknown strategy id, bad timeframe, bad overlay spec, a parameter that is
unknown, out of bounds or breaks a rule between two of them) is *not* replaced:
it is reported in ``problem`` and the trader places no orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from market_data.timeframes import TIMEFRAME_SECONDS
from strategies.base import StrategyError
from strategies.catalogue import CATALOGUE, CatalogueError, ParamError, create
from trading_mode import lookup_setting, settings_mapping

ENGINES = ("catalogue", "legacy_neural")
DEFAULT_ENGINE = "catalogue"
DEFAULT_ACTIVE_ID = "STRAT-001"
DEFAULT_TIMEFRAME = "1h"


@dataclass(frozen=True)
class StrategySettings:
    engine: Any
    active_id: Any
    timeframe: Any
    overlays: Tuple[dict, ...]
    problem: Optional[str]  # None when the configuration is usable
    # the active strategy's parameters that differ from its defaults
    params: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_catalogue(self) -> bool:
        return self.engine == "catalogue"

    @property
    def is_legacy(self) -> bool:
        return self.engine == "legacy_neural"

    @property
    def signature(self) -> tuple:
        """Changes whenever the active strategy / its parameters / overlays /
        timeframe change."""
        return (
            self.engine,
            self.active_id,
            self.timeframe,
            repr(sorted(self.params.items())),
            tuple(repr(sorted(o.items(), key=lambda kv: kv[0])) for o in self.overlays),
        )

    @property
    def note(self) -> str:
        """Text for the hub strip's SIGNALS indicator."""
        if self.problem:
            return "SIGNALS: BLOCKED"
        if self.is_legacy:
            return "SIGNALS: LEGACY (UNTRAINED)"
        return f"SIGNALS: {self.active_id} {self.timeframe}"


def params_problem(strategy_id: str, params: Mapping[str, Any]) -> Optional[str]:
    """Why ``params`` cannot be used for ``strategy_id`` (a main strategy or an
    overlay), or None. Builds it, so the rules between two parameters (a slow length
    above the fast one, a first stop below the gain that sets it) are checked as
    well as each parameter's bounds. Not for a strategy that needs a trained model:
    building one loads the model."""
    try:
        create(strategy_id, **dict(params))
    except (CatalogueError, ParamError, StrategyError, TypeError) as exc:
        return str(exc)
    return None


def read_strategy_settings(settings: Any = None) -> StrategySettings:
    src = settings_mapping(settings)
    problems = []

    engine = lookup_setting(src, "strategy.engine", DEFAULT_ENGINE)
    if engine not in ENGINES:
        problems.append(f"unknown strategy.engine {engine!r} (use one of {ENGINES})")

    raw_params = lookup_setting(src, "strategy.params", {})
    if not isinstance(raw_params, Mapping) or not all(
        isinstance(v, Mapping) for v in raw_params.values()
    ):
        problems.append(f"invalid strategy.params {raw_params!r}")
        raw_params = {}

    active_id = lookup_setting(src, "strategy.active_id", DEFAULT_ACTIVE_ID)
    params: Dict[str, Any] = {}
    if engine == "catalogue":
        entry = CATALOGUE.get(active_id) if isinstance(active_id, str) else None
        if entry is None or entry["class_type"] != "main":
            problems.append(f"unknown strategy.active_id {active_id!r}")
        elif entry["family"] == "model":
            # the engine runs one model for every coin, and a model is trained on one
            # coin's market: strategy.params is not read for it, and its defaults
            # name no model, so it could never trade (FDS-MDL Phase 3)
            if not entry["default_params"].get("model_id"):
                problems.append(
                    f"strategy.active_id {active_id!r} needs a trained model, and "
                    "the signal engine runs it with its default parameters, which "
                    "name none"
                )
        else:
            params = dict(raw_params.get(active_id) or {})
            problem = params_problem(active_id, params)
            if problem:
                problems.append(f"strategy.params for {active_id}: {problem}")

    timeframe = lookup_setting(src, "strategy.timeframe", DEFAULT_TIMEFRAME)
    if timeframe not in TIMEFRAME_SECONDS:
        problems.append(f"unsupported strategy.timeframe {timeframe!r}")

    raw_overlays = lookup_setting(src, "strategy.overlays", [])
    overlays: Tuple[dict, ...] = ()
    if isinstance(raw_overlays, (list, tuple)) and all(
        isinstance(o, dict)
        and isinstance(o.get("id"), str)
        and isinstance(o.get("params") or {}, Mapping)
        for o in raw_overlays
    ):
        overlays = tuple(dict(o) for o in raw_overlays)
        for o in overlays:
            entry = CATALOGUE.get(o["id"])
            if engine != "catalogue":
                continue
            if entry is None or entry["class_type"] != "risk_overlay":
                problems.append(f"unknown overlay id {o['id']!r}")
                continue
            problem = params_problem(o["id"], o.get("params") or {})
            if problem:
                problems.append(f"overlay {o['id']}: {problem}")
    else:
        problems.append(f"invalid strategy.overlays {raw_overlays!r}")

    if engine == "legacy_neural":
        problems = []  # the catalogue settings are not used by the legacy engine

    return StrategySettings(
        engine=engine,
        active_id=active_id,
        timeframe=timeframe,
        overlays=overlays,
        problem="; ".join(problems) if problems else None,
        params=params,
    )
