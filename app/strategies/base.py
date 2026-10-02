"""
Strategy interface (FDS-121 section 4).

One interface, used identically by the backtester and the live/paper trader:

* ``on_bar(candles) -> Signal`` receives *closed bars only* (columns
  ``open_time, open, high, low, close, volume``; UTC, ascending) and must never
  see the forming bar.
* Strategies are pure: same input -> same output; no I/O, randomness or clock.
* Long-only spot: ``ENTER_LONG`` / ``EXIT_LONG`` / ``HOLD``. A strategy does not
  know whether a position is open; the runner ignores an ENTER while long and an
  EXIT while flat.
* ``warmup_bars`` is the number of bars needed before the first valid signal.
  ``lookback_bars`` is how many of the most recent bars the runner feeds
  ``on_bar``. Both the backtester and the live trader use the same window, so a
  signal depends only on those bars and is reproducible in either place.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping

import pandas as pd

CANDLE_COLUMNS = ("open_time", "open", "high", "low", "close", "volume")


class Action(str, Enum):
    ENTER_LONG = "ENTER_LONG"
    EXIT_LONG = "EXIT_LONG"
    HOLD = "HOLD"


@dataclass(frozen=True)
class Signal:
    action: Action
    reason: str
    # the indicator values the decision used, for logging / telemetry
    indicators: Mapping[str, float] = field(default_factory=dict)

    @staticmethod
    def hold(reason: str, indicators: Mapping[str, float] | None = None) -> "Signal":
        return Signal(Action.HOLD, reason, dict(indicators or {}))


class StrategyError(ValueError):
    """Bad strategy parameters or inputs."""


def check_candles(candles: pd.DataFrame) -> None:
    missing = [c for c in CANDLE_COLUMNS if c not in candles.columns]
    if missing:
        raise StrategyError(f"candles are missing columns: {missing}")


class Strategy(ABC):
    """Base class. Subclasses set ``strategy_id`` and implement ``compute``."""

    strategy_id: str = ""

    def __init__(self, **params: Any) -> None:
        # Imported here: the catalogue imports strategy modules to register them.
        from strategies.catalogue import resolve_params

        self.params: Dict[str, Any] = resolve_params(self.strategy_id, params)

    # -- sizing of the window the strategy needs ---------------------------------

    @property
    @abstractmethod
    def warmup_bars(self) -> int:
        """Bars required before the first valid signal."""

    @property
    def lookback_bars(self) -> int:
        """Bars the runner feeds ``on_bar``: enough for recursive indicators
        (EMA, Wilder) to converge, and identical in backtest and live."""
        return max(5 * self.warmup_bars, self.warmup_bars + 200)

    # -- the interface -------------------------------------------------------------

    def on_bar(self, candles: pd.DataFrame) -> Signal:
        check_candles(candles)
        if len(candles) < self.warmup_bars:
            return Signal.hold(
                "WARMUP", {"bars": float(len(candles)), "needed": float(self.warmup_bars)}
            )
        return self.compute(candles)

    @abstractmethod
    def compute(self, candles: pd.DataFrame) -> Signal:
        """Signal on the last (closed) bar of ``candles``; ``len >= warmup_bars``."""
