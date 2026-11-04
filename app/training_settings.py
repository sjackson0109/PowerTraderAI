"""
Trainer settings that decide whether something has earned its place in trading
(``pt_config.json``'s ``training`` section; Settings, Training).

``holdout_min_signals``   the fewest scored signals a source needs (20)
``holdout_min_hit_rate``  the share of them that must win after fees (0.55)

The LLM signal gate (llm_gate) reads them now; the planned model gate is to read the
same two. The defaults are the figures in the owner's model-gate design of
2026-11-03, kept until the owner decides otherwise: note that 11 hits in 20 (55%) is
not enough to tell a source from a coin toss, so a stricter pair (more signals) is
the safer choice. Other keys of the section are kept as they are.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping

SECTION = "training"
DEFAULTS: Dict[str, Any] = {"holdout_min_signals": 20, "holdout_min_hit_rate": 0.55}
BOUNDS = {"holdout_min_signals": (1, 100000), "holdout_min_hit_rate": (0.0, 1.0)}


def _bounded(value: Any, name: str):
    if isinstance(value, bool):
        return DEFAULTS[name]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return DEFAULTS[name]
    if not math.isfinite(number):
        return DEFAULTS[name]
    low, high = BOUNDS[name]
    number = min(high, max(low, number))
    return int(number) if name == "holdout_min_signals" else number


def normalise(raw: Any) -> Dict[str, Any]:
    """The section with both settings usable (others kept as they are)."""
    out = dict(raw) if isinstance(raw, Mapping) else {}
    for name in DEFAULTS:
        out[name] = _bounded(out.get(name, DEFAULTS[name]), name)
    return out


def read_training_settings(source: Any = None) -> Dict[str, Any]:
    """``source`` None reads pt_config.json fresh (as trading_mode reads it)."""
    from trading_mode import lookup_setting, settings_mapping

    try:
        raw = lookup_setting(settings_mapping(source), SECTION)
    except Exception:
        raw = None
    return normalise(raw)


def save_training_settings(values: Mapping[str, Any], manager: Any = None) -> bool:
    """Write the two settings, keeping the section's other keys."""
    if manager is None:
        from pt_settings_manager import SettingsManager

        manager = SettingsManager()
    current = manager.get(SECTION) or {}
    merged = dict(current) if isinstance(current, Mapping) else {}
    merged.update({k: values[k] for k in DEFAULTS if k in values})
    return bool(manager.set_section(SECTION, normalise(merged)))
