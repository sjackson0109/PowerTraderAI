"""
The account drawdown stop's state, kept across restarts: the peak account value the
trader has seen, and when it was seen.

Two files in the trader's books folder for the trading mode (next to
trader_status.json, so paper and each live broker keep their own), each with one
writer, so neither can undo the other's change:

* ``risk_state.json`` - the trader's: the peak, and the time of the last Settings >
  Risk request it has applied.
* ``risk_requests.json`` - the hub's: "set the peak to this value" (Reset peak), with
  the time it was asked for.

``apply_requests`` is the one rule both sides use: the trader to apply a request,
the hub to show what the trader will use (a request made while the trader is
stopped applies when it next starts).
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

STATE_FILE = "risk_state.json"
REQUESTS_FILE = "risk_requests.json"


def state_path(folder: str) -> str:
    return os.path.join(folder, STATE_FILE)


def requests_path(folder: str) -> str:
    return os.path.join(folder, REQUESTS_FILE)


def _number(value: Any) -> float:
    """A finite number, else 0.0."""
    if isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _read(path: str) -> Optional[Dict[str, Any]]:
    """The file's object; {} when there is no file; None when it cannot be read."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write(path: str, data: Mapping[str, Any]) -> None:
    """Atomic: a reader never sees a half-written file."""
    import pt_paths

    pt_paths.write_private_text(path, json.dumps(dict(data), indent=2))


def read_state(folder: str) -> Dict[str, Any]:
    """The trader's saved state ({} when there is none, or it cannot be read)."""
    return _read(state_path(folder)) or {}


def write_state(folder: str, state: Mapping[str, Any]) -> None:
    """The trader saves its state (OSError when it cannot)."""
    _write(state_path(folder), state)


def read_requests(folder: str) -> Dict[str, Any]:
    """The hub's requests; a file that cannot be read asks for nothing."""
    return _read(requests_path(folder)) or {}


def _request(folder: str, name: str, entry: Dict[str, Any]) -> None:
    requests = read_requests(folder)
    requests[name] = entry
    _write(requests_path(folder), requests)


def request_peak_reset(folder: str, value: float, now: Optional[float] = None) -> None:
    """Reset peak: the peak becomes ``value`` (the account value the user saw)."""
    if not _number(value) > 0.0:
        raise ValueError("The peak must be an account value above 0.")
    ts = time.time() if now is None else float(now)
    _request(folder, "reset_peak", {"ts": ts, "value": float(value)})


def apply_requests(
    state: Mapping[str, Any], requests: Mapping[str, Any]
) -> Dict[str, Any]:
    """``state`` with the requests not applied yet (a new dict). A reset applies
    once: its time is kept, so the peak can rise again after it."""
    out = dict(state)
    reset = requests.get("reset_peak")
    if isinstance(reset, Mapping):
        ts, value = _number(reset.get("ts")), _number(reset.get("value"))
        if value > 0.0 and ts > _number(out.get("peak_reset_ts")):
            out.update(peak_value=value, peak_ts=ts, peak_reset_ts=ts)
    return out


@dataclass(frozen=True)
class RiskView:
    """What the hub shows: the state with the requests applied."""

    peak_value: float  # 0.0: no peak recorded yet
    peak_ts: float


def current(folder: Optional[str]) -> RiskView:
    """The state the trader runs with (or will start with) in ``folder``."""
    if not folder:
        return RiskView(0.0, 0.0)
    state = apply_requests(read_state(folder), read_requests(folder))
    return RiskView(
        peak_value=max(0.0, _number(state.get("peak_value"))),
        peak_ts=_number(state.get("peak_ts")),
    )
