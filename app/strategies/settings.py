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

**Authorisation** (FDS-SR-001 section 5.3). Given the trading ``mode``, a strategy or
overlay that may not trade in it is a problem too. A strategy's timeframe must be one
of its ``timeframes_permitted``.

Whether an entry may trade in a mode is the owner's switch for it, where Settings >
Strategy saved one, and otherwise its catalogue ``authorisation`` (a research-only
entry never trades, a paper-only one never trades live). The switches are
``strategy.trading_allowed``: ``{id: {"paper"|"live": true|false}}``, holding only the
entries and modes the owner set differently from the catalogue. A switch setting
that is not that shape allows nothing, and is a problem.

``strategy.research_enabled`` (``read_research_enabled``) lists the strategies and
overlays the research windows offer. It never affects trading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from market_data.timeframes import TIMEFRAME_SECONDS
from strategies.base import StrategyError
from strategies.catalogue import (
    CATALOGUE,
    CatalogueError,
    ParamError,
    allowed_in_mode,
    create,
)
from trading_mode import lookup_setting, settings_mapping

ENGINES = ("catalogue", "legacy_neural")
DEFAULT_ENGINE = "catalogue"
DEFAULT_ACTIVE_ID = "STRAT-001"
DEFAULT_TIMEFRAME = "1h"
# enabled for research unless the settings say otherwise: the strategies and overlays
# that existed before FDS-SR-001, so they stay usable; every later one starts disabled
DEFAULT_RESEARCH_ENABLED = (
    "STRAT-000",
    "STRAT-001",
    "STRAT-002",
    "OVL-RATCHET",
    "OVL-ATR",
    "OVL-PLOCK",
    "OVL-COOLDOWN",
)
USES = {"research": "research only", "paper": "paper trading", "live": "live trading"}
TRADING_MODES = ("paper", "live")
Switches = Dict[str, Dict[str, bool]]


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


def _mode_name(mode: Any) -> str:
    return str(getattr(mode, "value", mode))


def parse_switches(raw: Any) -> Tuple[Switches, Optional[str]]:
    """``strategy.trading_allowed`` as ``{id: {mode: on}}``, and None; or ``{}`` and
    why it cannot be read (then nothing may trade). Missing (None) is ``{}``."""
    if raw is None:
        return {}, None
    if isinstance(raw, Mapping) and all(
        isinstance(k, str)
        and isinstance(v, Mapping)
        and all(m in TRADING_MODES and isinstance(on, bool) for m, on in v.items())
        for k, v in raw.items()
    ):
        return {k: dict(v) for k, v in raw.items()}, None
    return {}, f"invalid strategy.trading_allowed {raw!r}"


def read_trading_switches(settings: Any = None) -> Tuple[Switches, Optional[str]]:
    """The owner's trading switches (``parse_switches`` of ``strategy.trading_allowed``)."""
    src = settings_mapping(settings)
    return parse_switches(lookup_setting(src, "strategy.trading_allowed", None))


def allowed_for_trading(
    entry_id: Any, mode: Any, switches: Optional[Mapping[str, Mapping]] = None
) -> bool:
    """Whether ``entry_id`` may trade in ``mode`` ("paper" or "live"): the owner's switch
    for it in ``switches`` where there is one, otherwise its catalogue authorisation. An
    unknown id or mode is never allowed."""
    if not isinstance(entry_id, str) or entry_id not in CATALOGUE:
        return False
    name = _mode_name(mode)
    if name not in TRADING_MODES:
        return False
    on = (switches or {}).get(entry_id, {}).get(name)
    if isinstance(on, bool):
        return on
    return allowed_in_mode(entry_id, name)


def authorisation_problem(
    entry_id: Any, mode: Any, switches: Optional[Mapping[str, Mapping]] = None
) -> Optional[str]:
    """Why ``entry_id`` (a strategy or overlay) may not be selected in ``mode``
    ("paper" or "live"), or None (FDS-SR-001 section 5.3). ``switches``: the owner's
    (``read_trading_switches``); without them, the catalogue alone decides."""
    if allowed_for_trading(entry_id, mode, switches):
        return None
    entry = CATALOGUE.get(entry_id) if isinstance(entry_id, str) else None
    if entry is None:
        return f"unknown id {entry_id!r}"
    name = _mode_name(mode)
    if (switches or {}).get(entry_id, {}).get(name) is False:
        return f"{entry_id} is switched off for {name} trading in Settings > Strategy"
    use = USES.get(entry["authorisation"], entry["authorisation"])
    return f"{entry_id} can be used for {use}, not {name} trading"


def read_strategy_settings(settings: Any = None, mode: Any = None) -> StrategySettings:
    """The strategy settings. With ``mode`` (the trading mode the caller trades in),
    an entry whose authorisation does not cover it is a problem as well."""
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
    elif engine == "catalogue":
        entry = CATALOGUE.get(active_id) if isinstance(active_id, str) else None
        if entry is not None and timeframe not in entry["timeframes_permitted"]:
            problems.append(
                f"strategy.timeframe {timeframe!r} is not one {active_id} can trade on "
                f"({', '.join(entry['timeframes_permitted'])})"
            )

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

    if engine == "catalogue" and mode is not None:
        switches, problem = parse_switches(
            lookup_setting(src, "strategy.trading_allowed", None)
        )
        if problem:
            problems.append(problem)
        for entry_id in [active_id] + [o["id"] for o in overlays]:
            if isinstance(entry_id, str) and entry_id in CATALOGUE:
                problem = authorisation_problem(entry_id, mode, switches)
                if problem:
                    problems.append(problem)

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


def read_research_enabled(settings: Any = None) -> Tuple[str, ...]:
    """The strategies and overlays enabled for research (``strategy.research_enabled``),
    in catalogue order. Missing, or not a list: ``DEFAULT_RESEARCH_ENABLED``. Unknown ids
    are ignored. This setting never affects trading."""
    src = settings_mapping(settings)
    raw = lookup_setting(src, "strategy.research_enabled", None)
    if raw is None:
        wanted = set(DEFAULT_RESEARCH_ENABLED)
    elif isinstance(raw, (list, tuple)):
        wanted = {x for x in raw if isinstance(x, str)}
    else:
        wanted = set(DEFAULT_RESEARCH_ENABLED)
    return tuple(sid for sid in CATALOGUE if sid in wanted)
