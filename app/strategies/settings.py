"""
Strategy settings reader (FDS-121 section 7), fail-closed.

Keys (all under ``strategy.``): ``engine`` (``catalogue`` | ``legacy_neural``,
default ``catalogue``), ``active_id`` (default ``STRAT-000``; ``STRAT-001`` once
that strategy exists), ``symbols`` (default ``["BTCUSDT"]``), ``timeframe``
(default ``1h``) and ``overlays`` (``[{"id", "params"}]``, default none).

Missing keys take their defaults. A value that is present but wrong (unknown
engine, unknown strategy id, bad timeframe, bad overlay spec) is *not* replaced:
it is reported in ``problem`` and the trader places no orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from market_data.timeframes import TIMEFRAME_SECONDS
from strategies.catalogue import CATALOGUE
from trading_mode import lookup_setting, settings_mapping

ENGINES = ("catalogue", "legacy_neural")
DEFAULT_ENGINE = "catalogue"
DEFAULT_ACTIVE_ID = "STRAT-001"
DEFAULT_SYMBOLS = ("BTCUSDT",)
DEFAULT_TIMEFRAME = "1h"


@dataclass(frozen=True)
class StrategySettings:
    engine: Any
    active_id: Any
    symbols: Tuple[str, ...]
    timeframe: Any
    overlays: Tuple[dict, ...]
    problem: Optional[str]  # None when the configuration is usable

    @property
    def is_catalogue(self) -> bool:
        return self.engine == "catalogue"

    @property
    def is_legacy(self) -> bool:
        return self.engine == "legacy_neural"

    @property
    def signature(self) -> tuple:
        """Changes whenever the active strategy / overlays / timeframe change."""
        return (
            self.engine,
            self.active_id,
            self.timeframe,
            tuple(repr(sorted(o.items(), key=lambda kv: kv[0])) for o in self.overlays),
        )

    def traded_pairs(self) -> Tuple[str, ...]:
        return self.symbols

    @property
    def note(self) -> str:
        """Text for the hub strip's SIGNALS indicator."""
        if self.problem:
            return "SIGNALS: BLOCKED"
        if self.is_legacy:
            return "SIGNALS: LEGACY (UNTRAINED)"
        return f"SIGNALS: {self.active_id} {self.timeframe}"


def read_strategy_settings(settings: Any = None) -> StrategySettings:
    src = settings_mapping(settings)
    problems = []

    engine = lookup_setting(src, "strategy.engine", DEFAULT_ENGINE)
    if engine not in ENGINES:
        problems.append(f"unknown strategy.engine {engine!r} (use one of {ENGINES})")

    active_id = lookup_setting(src, "strategy.active_id", DEFAULT_ACTIVE_ID)
    if engine == "catalogue":
        entry = CATALOGUE.get(active_id) if isinstance(active_id, str) else None
        if entry is None or entry["class_type"] != "main":
            problems.append(f"unknown strategy.active_id {active_id!r}")

    raw_symbols = lookup_setting(src, "strategy.symbols", list(DEFAULT_SYMBOLS))
    if (
        isinstance(raw_symbols, (list, tuple))
        and raw_symbols
        and all(isinstance(s, str) and s.strip() for s in raw_symbols)
    ):
        symbols = tuple(s.strip().upper() for s in raw_symbols)
    else:
        symbols = ()
        problems.append(f"invalid strategy.symbols {raw_symbols!r}")

    timeframe = lookup_setting(src, "strategy.timeframe", DEFAULT_TIMEFRAME)
    if timeframe not in TIMEFRAME_SECONDS:
        problems.append(f"unsupported strategy.timeframe {timeframe!r}")

    raw_overlays = lookup_setting(src, "strategy.overlays", [])
    overlays: Tuple[dict, ...] = ()
    if isinstance(raw_overlays, (list, tuple)) and all(
        isinstance(o, dict) and isinstance(o.get("id"), str) for o in raw_overlays
    ):
        overlays = tuple(dict(o) for o in raw_overlays)
        for o in overlays:
            entry = CATALOGUE.get(o["id"])
            if engine == "catalogue" and (
                entry is None or entry["class_type"] != "risk_overlay"
            ):
                problems.append(f"unknown overlay id {o['id']!r}")
    else:
        problems.append(f"invalid strategy.overlays {raw_overlays!r}")

    if engine == "legacy_neural":
        problems = []  # the catalogue settings are not used by the legacy engine

    return StrategySettings(
        engine=engine,
        active_id=active_id,
        symbols=symbols,
        timeframe=timeframe,
        overlays=overlays,
        problem="; ".join(problems) if problems else None,
    )
