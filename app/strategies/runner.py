"""
The decision core shared by the backtester and the live/paper trader.

``StrategyRunner`` turns "a main strategy + zero or more risk overlays + the
current position" into one ``Decision`` per closed bar, so a backtest and a paper
run can never disagree about composition.

Composition rules (FDS-129 section 2):

1. The effective stop is the **max** of all overlay stops (tightest wins, long-only).
2. A stop only ever moves **up** for an open long, whichever overlay set it.
3. Exit if any overlay says ``exit_now``, or close < effective stop, or the main
   strategy says EXIT. The rule that triggered is recorded (``exit_rule``).
4. Entry needs the strategy's ENTER **and** every overlay's ``allow_entry``.
5. Everything is evaluated on **closed bars**; exits fill at the next bar's open.
   (Intrabar stop simulation is out of scope.)
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from strategies.base import Action, Signal, Strategy

# --- overlay contract -----------------------------------------------------------------


@dataclass
class PositionState:
    """One open long. ``overlay_state`` is keyed by overlay_id."""

    symbol: str
    entry_price: float
    entry_bar_time: pd.Timestamp
    highest_close: float
    current_stop: Optional[float] = None
    stop_owner: Optional[str] = None
    overlay_state: Dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """JSON-safe form, so a position (and its overlay state) survives a restart."""
        return {
            "symbol": self.symbol,
            "entry_price": float(self.entry_price),
            "entry_bar_time": pd.Timestamp(self.entry_bar_time).isoformat(),
            "highest_close": float(self.highest_close),
            "current_stop": (
                None if self.current_stop is None else float(self.current_stop)
            ),
            "stop_owner": self.stop_owner,
            "overlay_state": {k: dict(v) for k, v in self.overlay_state.items()},
        }

    @staticmethod
    def from_dict(d: dict) -> "PositionState":
        return PositionState(
            symbol=str(d["symbol"]),
            entry_price=float(d["entry_price"]),
            entry_bar_time=pd.Timestamp(d["entry_bar_time"]),
            highest_close=float(d["highest_close"]),
            current_stop=(
                None if d.get("current_stop") is None else float(d["current_stop"])
            ),
            stop_owner=d.get("stop_owner"),
            overlay_state={
                k: dict(v) for k, v in (d.get("overlay_state") or {}).items()
            },
        )


@dataclass(frozen=True)
class OverlayDecision:
    stop_price: Optional[float] = None
    exit_now: bool = False
    reason: str = ""


@dataclass(frozen=True)
class GateResult:
    allowed: bool = True
    reason: str = ""


class Overlay(ABC):
    """A risk overlay. Subclasses set ``overlay_id`` and override what they need."""

    overlay_id: str = ""
    params: Dict[str, Any]
    # Seconds per bar; set by StrategyRunner.set_timeframe (overlays that count bars need it).
    bar_seconds: Optional[int] = None

    def __init__(self, **params: Any) -> None:
        # Imported here: the catalogue imports overlay modules to register them.
        from strategies.catalogue import resolve_params

        self.params = resolve_params(self.overlay_id, params)

    def export_state(self) -> dict:
        """State that is not tied to one position (e.g. cooldown timers); JSON-safe."""
        return {}

    def import_state(self, state: dict) -> None:
        return None

    @property
    def lookback_bars(self) -> int:
        """Bars of history the overlay needs (e.g. ATR length); 0 if none."""
        return 0

    def on_entry(self, pos: PositionState, candles: pd.DataFrame) -> None:
        return None

    def on_bar(self, pos: PositionState, candles: pd.DataFrame) -> OverlayDecision:
        return OverlayDecision()

    def allow_entry(self, symbol: str, now_bar_time: pd.Timestamp) -> GateResult:
        return GateResult(True, "")

    def on_exit(
        self, pos: PositionState, bar_time: pd.Timestamp, exit_price: float
    ) -> None:
        """Called when the position is closed (cooldowns need to know)."""
        return None


# --- the decision ---------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    indicators: Dict[str, float]
    bar_time: pd.Timestamp
    strategy_id: str
    exit_rule: Optional[str] = None  # "strategy" | overlay id | "stop:<overlay id>"
    stop_price: Optional[float] = None
    stop_owner: Optional[str] = None


class StrategyRunner:
    def __init__(self, strategy: Strategy, overlays: Sequence[Overlay] = ()) -> None:
        self.strategy = strategy
        self.overlays: List[Overlay] = list(overlays)

    @property
    def lookback_bars(self) -> int:
        return max(
            [self.strategy.lookback_bars] + [o.lookback_bars for o in self.overlays]
        )

    def set_timeframe(self, tf_seconds: int) -> None:
        """Tell the strategy and the overlays how long a bar is (cooldowns count bars;
        STRAT-003 decides on the model's timeframe of that length)."""
        self.strategy.set_timeframe(tf_seconds)
        for overlay in self.overlays:
            overlay.bar_seconds = int(tf_seconds)

    def export_state(self) -> Dict[str, dict]:
        return {o.overlay_id: o.export_state() for o in self.overlays}

    def import_state(self, state: Dict[str, dict]) -> None:
        for overlay in self.overlays:
            if isinstance(state.get(overlay.overlay_id), dict):
                overlay.import_state(state[overlay.overlay_id])

    def window(self, candles: pd.DataFrame, end_index: int) -> pd.DataFrame:
        """The bars the decision at ``end_index`` (inclusive) may see."""
        start = max(0, end_index + 1 - self.lookback_bars)
        return candles.iloc[start : end_index + 1]

    # -- lifecycle ---------------------------------------------------------------------

    def open_position(
        self,
        symbol: str,
        entry_price: float,
        entry_bar_time: pd.Timestamp,
        candles: pd.DataFrame,
    ) -> PositionState:
        pos = PositionState(
            symbol=symbol,
            entry_price=float(entry_price),
            entry_bar_time=entry_bar_time,
            highest_close=float(entry_price),
        )
        for overlay in self.overlays:
            pos.overlay_state.setdefault(overlay.overlay_id, {})
            overlay.on_entry(pos, candles)
        return pos

    def close_position(
        self, pos: PositionState, bar_time: pd.Timestamp, exit_price: float
    ) -> None:
        for overlay in self.overlays:
            overlay.on_exit(pos, bar_time, float(exit_price))

    # -- evaluation ----------------------------------------------------------------------

    def evaluate(
        self,
        candles: pd.DataFrame,
        position: Optional[PositionState],
        symbol: str,
    ) -> Decision:
        """Decision at the close of the last bar of ``candles`` (a closed bar)."""
        bar_time = candles["open_time"].iloc[-1]
        sid = self.strategy.strategy_id
        signal: Signal = self.strategy.on_bar(candles)
        indicators = dict(signal.indicators)

        if position is None:
            if signal.action is not Action.ENTER_LONG:
                reason = (
                    signal.reason
                    if signal.action is Action.HOLD
                    else f"FLAT:{signal.reason}"
                )
                return Decision(Action.HOLD, reason, indicators, bar_time, sid)
            for overlay in self.overlays:
                gate = overlay.allow_entry(symbol, bar_time)
                if not gate.allowed:
                    return Decision(
                        Action.HOLD,
                        f"ENTRY_BLOCKED:{overlay.overlay_id}:{gate.reason}",
                        indicators,
                        bar_time,
                        sid,
                    )
            return Decision(Action.ENTER_LONG, signal.reason, indicators, bar_time, sid)

        # --- open long ---
        close = float(candles["close"].iloc[-1])
        position.highest_close = max(position.highest_close, close)

        overlay_exits: List[str] = []
        for overlay in self.overlays:
            od = overlay.on_bar(position, candles)
            if od.exit_now:
                overlay_exits.append(f"{overlay.overlay_id}:{od.reason}")
            if od.stop_price is not None and (
                position.current_stop is None or od.stop_price > position.current_stop
            ):
                # a stop only ever moves up, whichever overlay sets it
                position.current_stop = float(od.stop_price)
                position.stop_owner = overlay.overlay_id

        stop = position.current_stop
        indicators["close"] = close
        if stop is not None:
            indicators["stop"] = stop

        triggered: List[str] = []
        exit_rule: Optional[str] = None
        if overlay_exits:
            triggered.extend(overlay_exits)
            exit_rule = overlay_exits[0].split(":", 1)[0]
        if stop is not None and close < stop:
            triggered.append(f"STOP:{position.stop_owner}")
            exit_rule = exit_rule or f"stop:{position.stop_owner}"
        if signal.action is Action.EXIT_LONG:
            triggered.append(f"STRATEGY:{signal.reason}")
            exit_rule = exit_rule or "strategy"

        if triggered:
            return Decision(
                Action.EXIT_LONG,
                " | ".join(triggered),
                indicators,
                bar_time,
                sid,
                exit_rule=exit_rule,
                stop_price=stop,
                stop_owner=position.stop_owner,
            )
        return Decision(
            Action.HOLD,
            "HOLDING" if signal.action is Action.ENTER_LONG else signal.reason,
            indicators,
            bar_time,
            sid,
            stop_price=stop,
            stop_owner=position.stop_owner,
        )
