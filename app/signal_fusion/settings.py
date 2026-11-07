"""
The entry assessment's settings (FDS-SIG-004 sections 5.8.3 and 5.10): ``pt_config.json``'s
``signal_fusion`` section, saved from Settings > Strategy (the entry assessment) and
Settings > Risk (the volatility size reduction and the two entry limits).

Every setting is Off by default. In this version only Off and Log only can be chosen:

* the entry assessment's Veto and the volatility size reduction's On need their evidence
  from a confirmation window and the owner's decision (section 6.7);
* the two limits' On waits for their log-only counts to be reviewed (D11).

Log only changes no decision: it records, for every entry, what each part would have done.
A saved value this version does not offer is read as Off, so an entry is never changed by
a setting this version cannot show.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

from signal_fusion import assessment as asm

SECTION = "signal_fusion"
KEYS = ("entry_assessment", "volatility_shrink", "participation_cap", "spread_cap")
DEFAULTS: Dict[str, Any] = {key: asm.OFF for key in KEYS}
NUMBERS: Dict[str, float] = {"participation_pi": 0.01, "spread_max": 0.005}
# what this version offers
AVAILABLE: Dict[str, tuple] = {key: (asm.OFF, asm.LOG_ONLY) for key in KEYS}
# what each setting offers once its evidence and the owner's decision allow
LATER = {
    "entry_assessment": asm.VETO,
    "volatility_shrink": asm.ON,
    "participation_cap": asm.ON,
    "spread_cap": asm.ON,
}


def normalise(raw: Any) -> Dict[str, Any]:
    """The section with every setting usable (others kept as they are)."""
    out = dict(raw) if isinstance(raw, Mapping) else {}
    for key in KEYS:
        value = out.get(key, DEFAULTS[key])
        out[key] = value if value in AVAILABLE[key] else asm.OFF
    for key, default in NUMBERS.items():
        try:
            number = float(out.get(key, default))
        except (TypeError, ValueError):
            number = default
        out[key] = number if 0 < number < 1 else default
    return out


def read(source: Any = None) -> asm.Settings:
    """``source`` None reads pt_config.json fresh (as trading_mode reads it)."""
    from trading_mode import lookup_setting, settings_mapping

    try:
        raw = lookup_setting(settings_mapping(source), SECTION)
    except Exception:
        raw = None
    values = normalise(raw)
    return asm.Settings(
        values["entry_assessment"],
        values["volatility_shrink"],
        values["participation_cap"],
        values["spread_cap"],
        values["participation_pi"],
        values["spread_max"],
    )


def save(values: Mapping[str, Any], manager: Any = None) -> bool:
    """Write the settings, keeping the section's other keys. A value this version does
    not offer is refused (False)."""
    for key in KEYS:
        if key in values and values[key] not in AVAILABLE[key]:
            return False
    if manager is None:
        from pt_settings_manager import SettingsManager

        manager = SettingsManager()
    current = manager.get(SECTION) or {}
    merged = dict(current) if isinstance(current, Mapping) else {}
    merged.update({k: values[k] for k in KEYS if k in values})
    return bool(manager.set_section(SECTION, normalise(merged)))
