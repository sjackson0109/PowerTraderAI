"""
Drawdowns and recovery from an equity curve (PTAI-RD-001 work package 2.6).

* ``spells(times_s, equity)``: each spell below a previous high, oldest first: the high
  it fell from and when, its lowest point and when, how deep it went (a fraction of the
  high), and when the curve first got back to the high (None if it had not by the
  curve's end, which then ends the spell's time under water).
* ``report(times_s, equity)``: the deepest spell and the longest, how many there were,
  and the share of the curve's time spent below a previous high.

Only the curve's own marks are seen (a replay marks equity at every close of the
strategy's timeframe): a fall and recovery between two marks is not.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

DAY_S = 86_400.0


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


def spells(times_s: Sequence[float], equity: Sequence[float]) -> List[Dict[str, Any]]:
    """Each spell below a previous high (module docstring), oldest first."""
    t = np.asarray(times_s, dtype=float)
    e = np.asarray(equity, dtype=float)
    if len(t) != len(e):
        raise ValueError("times and equity must be the same length")
    out: List[Dict[str, Any]] = []
    if not len(t):
        return out
    high, high_t = e[0], t[0]
    spell: Optional[Dict[str, Any]] = None
    for ts, value in zip(t[1:], e[1:]):
        if value >= high:
            if spell is not None:
                spell["recovered_s"] = ts
                out.append(spell)
                spell = None
            high, high_t = value, ts
            continue
        if spell is None:
            spell = {"high": high, "high_s": high_t, "low": value, "low_s": ts}
        elif value < spell["low"]:
            spell["low"], spell["low_s"] = value, ts
    if spell is not None:
        spell["recovered_s"] = None
        out.append(spell)
    end = t[-1]
    for s in out:
        back = s["recovered_s"]
        s["depth"] = (1.0 - s["low"] / s["high"]) if s["high"] > 0 else None
        s["days_to_recover"] = None if back is None else (back - s["low_s"]) / DAY_S
        s["days_under_water"] = ((end if back is None else back) - s["high_s"]) / DAY_S
    return out


def _public(s: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if s is None:
        return None
    return {
        "high": float(s["high"]),
        "high_at": _iso(s["high_s"]),
        "low": float(s["low"]),
        "low_at": _iso(s["low_s"]),
        "depth": None if s["depth"] is None else float(s["depth"]),
        "recovered_at": _iso(s["recovered_s"]),
        "days_to_recover": s["days_to_recover"],
        "days_under_water": float(s["days_under_water"]),
    }


def report(times_s: Sequence[float], equity: Sequence[float]) -> Dict[str, Any]:
    """The deepest and the longest spell below a previous high, the number of spells,
    and the share of the curve's time spent in one (None for a curve with no time)."""
    found = spells(times_s, equity)
    t = np.asarray(times_s, dtype=float)
    span = float(t[-1] - t[0]) if len(t) > 1 else 0.0
    deepest = max(found, key=lambda s: s["depth"] or 0.0, default=None)
    longest = max(found, key=lambda s: s["days_under_water"], default=None)
    under = sum(s["days_under_water"] for s in found) * DAY_S
    return {
        "max_drawdown": float(deepest["depth"] or 0.0) if deepest else 0.0,
        "deepest": _public(deepest),
        "longest": _public(longest),
        "spells": len(found),
        "share_under_water": (under / span) if span > 0 else None,
    }
