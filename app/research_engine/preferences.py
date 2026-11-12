"""
The research engine's own choices, kept beside its queue (``<root>/engine.json``):
the operating mode and the owner's energy figures. They decide nothing about
trading. A missing or unreadable file gives the defaults: balanced mode, and no
energy figures, so no energy or cost is estimated.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from typing import Optional

from research_engine.resources import DEFAULT_MODE, MODES, EnergyModel

FILE_NAME = "engine.json"


@dataclass(frozen=True)
class Preferences:
    mode: str = DEFAULT_MODE
    watts_per_busy_core: Optional[float] = None
    tariff_per_kwh: Optional[float] = None
    currency: str = ""

    def energy(self) -> EnergyModel:
        return EnergyModel(self.watts_per_busy_core, self.tariff_per_kwh, self.currency)


def _figure(value) -> Optional[float]:
    """A positive finite number, or None (blank, zero, negative or not a number)."""
    if value is None or value == "":
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x > 0 else None


def checked(mode: str, watts=None, tariff=None, currency: str = "") -> Preferences:
    """Preferences from typed values; a wrong mode is refused, a blank figure is None."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    return Preferences(
        mode, _figure(watts), _figure(tariff), str(currency or "").strip()
    )


def load(root: str) -> Preferences:
    try:
        with open(os.path.join(root, FILE_NAME), encoding="utf-8") as f:
            data = json.load(f)
        return checked(
            data.get("mode", DEFAULT_MODE),
            data.get("watts_per_busy_core"),
            data.get("tariff_per_kwh"),
            data.get("currency", ""),
        )
    except (OSError, ValueError, AttributeError):
        return Preferences()


def save(root: str, prefs: Preferences) -> None:
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, FILE_NAME)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(asdict(prefs), f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)
