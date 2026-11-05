"""
The entry gate's settings: what a source of trade entries (a trained model, an LLM
provider/model/prompt version, an entry filter) must show before it is used in trading
(``pt_config.json``'s ``training`` section; Settings, Training). entry_gate applies them.

``holdout_min_signals``         the fewest entries it must have made (20)
``gate_min_return_after_fees``  its mean return after fees per trade must be above this,
                                a fraction (0.0)
``gate_baseline_runs``          random-entry baselines to compare it with (1000)
``gate_baseline_percentile``    its mean return after fees must be above this percentile
                                of the baselines' (95)

A hit rate decides nothing (random entries with the trader's exits win about 91% of the
time), so ``holdout_min_hit_rate``, which an earlier release saved, is no longer read;
it is kept in the file as it is, like the section's other keys.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping

SECTION = "training"
DEFAULTS: Dict[str, Any] = {
    "holdout_min_signals": 20,
    "gate_min_return_after_fees": 0.0,
    "gate_baseline_runs": 1000,
    "gate_baseline_percentile": 95.0,
}
BOUNDS = {
    "holdout_min_signals": (1, 100000),
    "gate_min_return_after_fees": (-1.0, 1.0),
    "gate_baseline_runs": (100, 100000),
    "gate_baseline_percentile": (50.0, 99.9),
}
WHOLE = ("holdout_min_signals", "gate_baseline_runs")


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
    return int(number) if name in WHOLE else number


def problem(name: str, value: Any) -> str:
    """Why ``value`` cannot be saved as ``name`` ("" when it can): Settings refuses
    such a value instead of clamping it."""
    low, high = BOUNDS[name]
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "not a number"
    if not math.isfinite(number):
        return "not a number"
    if name in WHOLE and not number.is_integer():
        return "not a whole number"
    if not low <= number <= high:
        return f"outside {low:g} .. {high:g}"
    return ""


def normalise(raw: Any) -> Dict[str, Any]:
    """The section with every gate setting usable (others kept as they are)."""
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
    """Write the gate settings, keeping the section's other keys."""
    if manager is None:
        from pt_settings_manager import SettingsManager

        manager = SettingsManager()
    current = manager.get(SECTION) or {}
    merged = dict(current) if isinstance(current, Mapping) else {}
    merged.update({k: values[k] for k in DEFAULTS if k in values})
    return bool(manager.set_section(SECTION, normalise(merged)))
