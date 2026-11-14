"""
The account drawdown stop's state, kept across restarts: the peak account value the
trader has seen, and whether trading is halted (since when, why, at what account
value).

Two files in the trader's books folder for the trading mode (next to
trader_status.json, so paper and each live broker keep their own), each with one
writer, so neither can undo the other's change:

* ``risk_state.json`` - the trader's: the peak, the halt, and the time of the last
  Settings > Risk request it has applied; also, for Settings > Risk, the holdings
  its last account value left out (``not_counted``: no usable USD price) and why
  buys wait, if they do (``buys_waiting``). A file without these shows neither.
* ``risk_requests.json`` - the hub's: "set the peak to this value" (Reset peak; no
  value clears the peak, so the next account value is the peak) and "resume
  trading" (Resume trading), each with the time it was asked for.

``apply_requests`` is the one rule both sides use: the trader to apply a request,
the hub to show what the trader will use (a request made while the trader is
stopped applies when it next starts). A resume clears a halt only when it was asked
for after that halt; nothing else clears a halt. A state file that exists but
cannot be read counts as a halt, so a damaged file cannot resume trading either.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

STATE_FILE = "risk_state.json"
REQUESTS_FILE = "risk_requests.json"
UNREADABLE_REASON = "The saved risk state could not be read"
HALT_KEYS = ("halted", "halt_reason", "halted_ts", "halt_value")


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
    """The trader's saved state ({} when there is none). A file that cannot be read
    is a halt since the file was last written (fail closed)."""
    path = state_path(folder)
    state = _read(path)
    if state is None:
        try:
            since = os.path.getmtime(path)
        except OSError:
            since = time.time()
        return {"halted": True, "halt_reason": UNREADABLE_REASON, "halted_ts": since}
    return state


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


def request_peak_reset(
    folder: str, value: Optional[float], now: Optional[float] = None
) -> None:
    """Reset peak: the peak becomes ``value`` (the account value the user saw);
    None clears it, so the trader's next account value is the peak."""
    if value is not None and not _number(value) > 0.0:
        raise ValueError("The peak must be an account value above 0.")
    ts = time.time() if now is None else float(now)
    entry = {"ts": ts, "value": None if value is None else float(value)}
    _request(folder, "reset_peak", entry)


def request_resume(folder: str, now: Optional[float] = None) -> None:
    """Resume trading: clears the halt there is now (not a later one)."""
    ts = time.time() if now is None else float(now)
    _request(folder, "resume", {"ts": ts})


def halted_state(
    state: Mapping[str, Any], reason: str, value: Optional[float], now: float
) -> Dict[str, Any]:
    """``state`` with trading halted at ``now`` (a new dict)."""
    out = dict(state)
    out.update(halted=True, halt_reason=str(reason), halted_ts=float(now))
    out["halt_value"] = None if value is None else float(value)
    return out


def apply_requests(
    state: Mapping[str, Any], requests: Mapping[str, Any]
) -> Dict[str, Any]:
    """``state`` with the requests not applied yet (a new dict). A reset applies
    once: its time is kept, so the peak can rise again after it. A resume clears
    the halt only when it was asked for after the halt began."""
    out = dict(state)
    reset = requests.get("reset_peak")
    if isinstance(reset, Mapping) and "value" in reset:
        ts, raw = _number(reset.get("ts")), reset["value"]
        value = _number(raw)
        if (raw is None or value > 0.0) and ts > _number(out.get("peak_reset_ts")):
            out.update(peak_value=value, peak_ts=ts if value else 0.0, peak_reset_ts=ts)
    resume = requests.get("resume")
    if isinstance(resume, Mapping) and out.get("halted"):
        ts = _number(resume.get("ts"))
        if ts > _number(out.get("halted_ts")):
            for key in HALT_KEYS:
                out.pop(key, None)
            out["resumed_ts"] = ts
    return out


@dataclass(frozen=True)
class RiskView:
    """What the hub shows: the state with the requests applied."""

    peak_value: float  # 0.0: no peak recorded yet
    peak_ts: float
    halted: bool = False
    halt_reason: str = ""
    halted_ts: float = 0.0
    halt_value: Optional[float] = None
    # held assets the trader's last account value left out: (asset, quantity, why)
    not_counted: Tuple[Tuple[str, float, str], ...] = ()
    buys_waiting: str = ""  # why buys wait ("" when they do not)
    buys_waiting_ts: float = 0.0


def _not_counted(entries: Any) -> Tuple[Tuple[str, float, str], ...]:
    """The saved ``not_counted`` list as (asset, quantity, why); entries without an
    asset are skipped."""
    out = []
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, Mapping) and str(entry.get("asset") or "").strip():
            out.append(
                (
                    str(entry["asset"]).strip(),
                    _number(entry.get("quantity")),
                    str(entry.get("why") or ""),
                )
            )
    return tuple(out)


def current(folder: Optional[str]) -> RiskView:
    """The state the trader runs with (or will start with) in ``folder``."""
    if not folder:
        return RiskView(0.0, 0.0)
    state = apply_requests(read_state(folder), read_requests(folder))
    value = _number(state.get("halt_value"))
    return RiskView(
        peak_value=max(0.0, _number(state.get("peak_value"))),
        peak_ts=_number(state.get("peak_ts")),
        halted=bool(state.get("halted")),
        halt_reason=str(state.get("halt_reason") or ""),
        halted_ts=_number(state.get("halted_ts")),
        halt_value=value if value > 0.0 else None,
        not_counted=_not_counted(state.get("not_counted")),
        buys_waiting=str(state.get("buys_waiting") or ""),
        buys_waiting_ts=_number(state.get("buys_waiting_ts")),
    )


def files_signature(folder: Optional[str]) -> tuple:
    """Changes when either file changes (the hub re-reads them only then)."""
    out = []
    for path in (state_path(folder or ""), requests_path(folder or "")):
        try:
            out.append(os.path.getmtime(path))
        except OSError:
            out.append(None)
    return (folder, *out)
