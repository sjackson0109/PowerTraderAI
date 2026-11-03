"""
Keep each exchange's requests under the limit it publishes, across every PowerTrader
process on this computer.

The exchanges count requests per IP address, and the hub, the neural runner, the
trader and each trainer share one. So each exchange has a small state file in
``<cache>/rate_limits/``: the times of its latest requests. ``wait(exchange,
per_second)`` takes the file's lock, drops the times older than the window, and
either records this request or sleeps until the oldest one leaves the window. A
limit below one a second allows one request every ``1 / per_second`` seconds.

The limit is the exchange connector's own figure (``requests_per_second``, from the
exchange's documentation), unless ``trading_config.json`` sets another for that
exchange (Settings > Configure Exchange APIs: Requests per second).

When the state file cannot be used (the folder cannot be written, or the lock is
held for longer than ``LOCK_TIMEOUT``), the process paces its own requests instead,
so they are still kept to the limit within it.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

# Tests switch pacing off (app/conftest.py) and back on where they test it.
ENABLED = True
LOCK_TIMEOUT = 5.0  # seconds to wait for another process's lock before pacing alone
# Added to every window: a request leaves a few milliseconds after its slot is
# taken, and reaches the exchange later still, so slots are spaced a little wider
# than the limit itself.
MARGIN = 0.05
_OVERRIDES_TTL = 5.0  # seconds between looks at trading_config.json

_thread_lock = threading.Lock()
_local: Dict[str, List[float]] = {}  # exchange -> request times (fallback)
_overrides: Dict[str, float] = {}
_overrides_read: Tuple[float, Optional[float]] = (0.0, None)  # (when, file mtime)


def window(per_second: float) -> Tuple[int, float]:
    """``(requests, seconds)``: 10 a second -> (10, 1.0); 0.5 a second -> (1, 2.0)."""
    if per_second >= 1:
        return int(math.floor(per_second)), 1.0
    return 1, 1.0 / per_second


def state_dir() -> str:
    import pt_paths

    return os.path.join(pt_paths.cache_dir(), "rate_limits")


def _config_path() -> str:
    import pt_paths

    return os.path.join(pt_paths.config_dir(create=False), pt_paths.TRADING_CONFIG_FILE)


def overrides(clock: Callable[[], float] = time.time) -> Dict[str, float]:
    """``{exchange: requests a second}`` set in ``trading_config.json``; re-read when
    the file changes, at most every few seconds."""
    global _overrides, _overrides_read
    now = clock()
    if now - _overrides_read[0] < _OVERRIDES_TTL:
        return _overrides
    path = _config_path()
    try:
        mtime: Optional[float] = os.path.getmtime(path)
    except OSError:
        mtime = None
    if mtime != _overrides_read[1]:
        found: Dict[str, float] = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for ex in data.get("exchanges") or []:
                value = valid_rate(ex.get("requests_per_second"))
                if value is not None and ex.get("exchange_type"):
                    found[str(ex["exchange_type"]).lower()] = value
        except (OSError, ValueError, AttributeError, TypeError):
            found = {}
        _overrides = found
    _overrides_read = (now, mtime)
    return _overrides


def valid_rate(value) -> Optional[float]:
    """A usable requests-a-second figure (above 0, at most 1,000), else None."""
    if isinstance(value, bool):
        return None
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return None
    return rate if 0 < rate <= 1000 and rate == rate else None


def published_rate(exchange: str) -> Tuple[float, bool]:
    """``(requests a second, documented)``: the exchange connector's own figure,
    and whether it comes from the exchange's documentation (False: the default for
    a connector that gives none)."""
    from pt_exchange_abstraction import AbstractExchange, ExchangeFactory, ExchangeType

    try:
        cls = ExchangeFactory.get_exchange_class(ExchangeType(str(exchange).lower()))
    except ValueError:
        cls = None
    if cls is None:
        return AbstractExchange.requests_per_second, False
    documented = any(
        "requests_per_second" in vars(k)
        for k in cls.__mro__[:-1]
        if k is not AbstractExchange
    )
    return float(cls.requests_per_second), documented


def limit_for(exchange: str, default: Optional[float]) -> Optional[float]:
    """The requests a second ``exchange`` is kept to: the figure in
    ``trading_config.json``, else ``default`` (the connector's)."""
    return overrides().get(str(exchange).lower(), default)


def wait(
    exchange: str,
    per_second: Optional[float],
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Return once a request to ``exchange`` keeps it within its limit."""
    if not ENABLED:
        return
    rate = limit_for(exchange, per_second)
    if not rate or rate <= 0:
        return
    allowed, seconds = window(rate)
    name = str(exchange).lower()
    while True:
        delay = _take(name, allowed, seconds, clock)
        if delay <= 0:
            return
        sleep(delay)


def _take(name: str, allowed: int, seconds: float, clock) -> float:
    """Record a request now and return 0, or return how long to wait first."""
    with _thread_lock:
        try:
            with _Locked(os.path.join(state_dir(), f"{name}.lock"), clock):
                path = os.path.join(state_dir(), f"{name}.json")
                times = _read_times(path)
                delay = _admit(times, allowed, seconds, clock())
                if delay <= 0:
                    _write_times(path, times)
                return delay
        except OSError:
            times = _local.setdefault(name, [])
            return _admit(times, allowed, seconds, clock())


def _admit(times: List[float], allowed: int, seconds: float, now: float) -> float:
    """Drop ``times`` outside the window ending ``now``; append ``now`` and return 0
    when there is room, else return the wait until the oldest leaves the window."""
    span = seconds + MARGIN
    # a time in the future is another process's clock jump: it is dropped too
    times[:] = [t for t in times if now - span < t <= now]
    if len(times) < allowed:
        times.append(now)
        return 0.0
    return max(times[-allowed] + span - now, 0.001)


def _read_times(path: str) -> List[float]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [float(t) for t in data if isinstance(t, (int, float))]
    except (OSError, ValueError, TypeError):
        return []


def _write_times(path: str, times: List[float]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(times, f)


class _Locked:
    """An exclusive lock on ``path`` shared by every process (one byte of the file);
    OSError when it cannot be had within ``LOCK_TIMEOUT``."""

    def __init__(self, path: str, clock) -> None:
        self.path = path
        self.clock = clock
        self.fd: Optional[int] = None

    def __enter__(self) -> "_Locked":
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            try:
                _lock(self.fd)
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(self.fd)
                    self.fd = None
                    raise
                time.sleep(0.002)

    def __exit__(self, *exc) -> None:
        if self.fd is not None:
            try:
                _unlock(self.fd)
            finally:
                os.close(self.fd)
                self.fd = None


if os.name == "nt":
    import msvcrt

    def _lock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
