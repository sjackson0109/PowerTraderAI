"""
Registered signal candidates (FDS-SIG-001 section 5): each is an exact rule from the
closed bars up to bar t to exactly one of up, down or abstain at bar t, with fixed
parameters, a kind (two-sided or one-sided) and a warm-up.

A candidate reads **bars**: one coin's candles on one timeframe, oldest first, as arrays
of open time (seconds), high, low, close and base-asset volume (``Bars``). Bar t's call
uses only bars that opened at or before bar t (so closed by its close): ``call_at``
never reads past index t, and ``calls`` gives the same values for every t at once.

Round one's rules, SIG-A and SIG-B (FDS-SIG-002 section 3), are in ``round_one``.

"Missing" is by time: the bars a rule reads are the ones opening exactly one timeframe
step apart, ending at bar t's open. A bar absent from the candles is missing.

Reference callers (``Constant``) exist for the tests: the constant callers of section 5
item 4, which are NOT ASSESSABLE under the block floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence

import numpy as np

from signal_audit.stats import DOWN_ONLY, TWO_SIDED, UP, UP_ONLY

TIMEFRAME_SECONDS = {"1h": 3600, "4h": 4 * 3600}


@dataclass(frozen=True, eq=False)
class Bars:
    """One coin's candles on one timeframe, oldest first."""

    coin: str
    timeframe: str
    open_s: np.ndarray  # int64
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray  # base-asset volume

    def __len__(self) -> int:
        return int(len(self.open_s))

    @property
    def step(self) -> int:
        return TIMEFRAME_SECONDS[self.timeframe]

    def index_at(self, open_s: int) -> int:
        """The position of the bar opening at ``open_s``, or -1."""
        k = int(np.searchsorted(self.open_s, int(open_s)))
        return k if k < len(self) and int(self.open_s[k]) == int(open_s) else -1

    def upto(self, t: int) -> "Bars":
        """The bars up to and including position t (what was closed by its close)."""
        return Bars(
            self.coin,
            self.timeframe,
            self.open_s[: t + 1],
            self.high[: t + 1],
            self.low[: t + 1],
            self.close[: t + 1],
            self.volume[: t + 1],
        )


class Candidate:
    key: str = ""
    name: str = ""
    kind: str = TWO_SIDED
    warmup: int = 0  # bars before the first call
    inputs: str = ""
    input_coins: Sequence[str] = ()
    parameters: Mapping[str, Any] = {}
    rule: str = ""

    def runs_on(self, coin: str) -> bool:
        return True

    def calls(self, bars: Bars, inputs: Mapping[str, Bars]) -> np.ndarray:
        """The call at every bar of ``bars`` (int8 UP, DOWN or ABSTAIN)."""
        return np.array(
            [self.call_at(bars, inputs, t) for t in range(len(bars))], dtype=np.int8
        )

    def call_at(self, bars: Bars, inputs: Mapping[str, Bars], t: int) -> int:
        raise NotImplementedError

    def registration(self) -> Dict[str, Any]:
        """The candidate as a rule (section 5), for the registration."""
        return {
            "key": self.key,
            "name": self.name,
            "inputs": self.inputs,
            "input_coins": list(self.input_coins),
            "parameters": dict(self.parameters),
            "rule": self.rule,
            "kind": self.kind,
            "warmup_bars": self.warmup,
            "coins": self.coins_text,
        }

    coins_text = "all audited coins"


def run_ending_at(bars: Bars, t: int, length: int) -> bool:
    """Whether the ``length`` bars ending at position t open exactly one step apart (no
    bar of them is missing)."""
    if t - length + 1 < 0:
        return False
    first = int(bars.open_s[t - length + 1])
    return int(bars.open_s[t]) - first == (length - 1) * bars.step


class Constant(Candidate):
    """A constant caller (section 5 item 4): registered as two-sided by convention."""

    kind = TWO_SIDED

    def __init__(self, direction: int):
        self.direction = int(direction)
        self.key = "always-up" if direction == UP else "always-down"
        self.name = "Always up" if direction == UP else "Always down"
        self.rule = f"{self.name.lower()} at every bar"

    def calls(self, bars: Bars, inputs: Mapping[str, Bars]) -> np.ndarray:
        return np.full(len(bars), self.direction, dtype=np.int8)

    def call_at(self, bars: Bars, inputs: Mapping[str, Bars], t: int) -> int:
        return self.direction


__all__ = ["Bars", "Candidate", "Constant", "run_ending_at", "UP_ONLY", "DOWN_ONLY"]
