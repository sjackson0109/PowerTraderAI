"""A scripted strategy / overlay for engine and runner tests (not registered in the catalogue)."""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from strategies.base import Action, Signal, Strategy
from strategies.runner import GateResult, Overlay, OverlayDecision, PositionState


class Scripted(Strategy):
    """Emits ``script[i]`` (an Action) when the last bar of the window is bar ``i`` of ``frame``."""

    strategy_id = "T-SCRIPT"

    def __init__(self, frame: pd.DataFrame, script: Dict[int, Action], warmup: int = 1):
        self.params = {}
        self._index = {t: i for i, t in enumerate(frame["open_time"])}
        self._script = script
        self._warmup = warmup

    @property
    def warmup_bars(self) -> int:
        return self._warmup

    @property
    def lookback_bars(self) -> int:
        return 50

    def compute(self, candles: pd.DataFrame) -> Signal:
        i = self._index[candles["open_time"].iloc[-1]]
        action = self._script.get(i, Action.HOLD)
        return Signal(action, f"SCRIPT@{i}", {"i": float(i)})


class StubOverlay(Overlay):
    """Overlay whose stop / exit / gate are scripted by bar index of ``frame``."""

    def __init__(
        self,
        overlay_id: str,
        frame: pd.DataFrame,
        stops: Optional[Dict[int, float]] = None,
        exit_now: Optional[Dict[int, str]] = None,
        blocked: Optional[Dict[int, str]] = None,
    ):
        self.overlay_id = overlay_id
        self.params = {}
        self._index = {t: i for i, t in enumerate(frame["open_time"])}
        self.stops = stops or {}
        self.exit_now = exit_now or {}
        self.blocked = blocked or {}
        self.exits_seen = []

    def on_bar(self, pos: PositionState, candles: pd.DataFrame) -> OverlayDecision:
        i = self._index[candles["open_time"].iloc[-1]]
        return OverlayDecision(
            stop_price=self.stops.get(i),
            exit_now=i in self.exit_now,
            reason=self.exit_now.get(i, ""),
        )

    def allow_entry(self, symbol: str, now_bar_time) -> GateResult:
        i = self._index[now_bar_time]
        if i in self.blocked:
            return GateResult(False, self.blocked[i])
        return GateResult(True, "")

    def on_exit(self, pos, bar_time, exit_price) -> None:
        self.exits_seen.append((bar_time, exit_price))
