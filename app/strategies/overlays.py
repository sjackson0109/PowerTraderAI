"""
Composable risk overlays (FDS-129; covers issues #113-#116).

Each overlay attaches to any main strategy through ``StrategyRunner``; composition
(max stop, stops only move up, entry gates, which rule exited) lives in the runner,
so backtest and paper behave identically.

All ``*_pct`` parameters are percentages (``2.0`` = 2%), measured on **close vs the
entry fill price**. Gains use the highest close since entry (so a stage or step once
reached stays reached and a stop never lowers). Evaluation is on closed bars; an
exit fills at the next bar's open.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

import pandas as pd

from strategies.base import StrategyError
from strategies.catalogue import register
from strategies.indicators import atr
from strategies.runner import GateResult, Overlay, OverlayDecision, PositionState

_EPS = 1e-9  # float noise guard when a close lands exactly on a threshold


def _gain_pct(pos: PositionState) -> float:
    return (pos.highest_close / pos.entry_price - 1.0) * 100.0


@register("OVL-RATCHET")
class RatchetStop(Overlay):
    """
    Once the gain reaches ``trigger_pct`` the stop is ``entry * (1 + lock_pct)``; every
    further ``step_pct`` of gain raises it by ``step_pct``. Never lowers.
    """

    def __init__(self, **params):
        super().__init__(**params)
        if self.params["lock_pct"] >= self.params["trigger_pct"]:
            raise StrategyError("OVL-RATCHET: lock_pct must be below trigger_pct")

    def on_bar(self, pos: PositionState, candles: pd.DataFrame) -> OverlayDecision:
        p = self.params
        gain = _gain_pct(pos)
        state = pos.overlay_state.setdefault(self.overlay_id, {})
        state["max_gain_pct"] = gain
        if gain + _EPS < p["trigger_pct"]:
            state["armed"] = False
            return OverlayDecision()
        steps = int(math.floor((gain - p["trigger_pct"] + _EPS) / p["step_pct"]))
        stop = pos.entry_price * (1.0 + (p["lock_pct"] + steps * p["step_pct"]) / 100.0)
        state.update(armed=True, steps=steps, stop=stop)
        return OverlayDecision(stop_price=stop, reason=f"RATCHET_STEP_{steps}")


@register("OVL-ATR")
class AtrStop(Overlay):
    """Stop = highest close since entry - ``mult`` x ATR(``atr_len``)."""

    @property
    def lookback_bars(self) -> int:
        return 5 * self.params["atr_len"]  # Wilder smoothing needs room to settle

    def on_bar(self, pos: PositionState, candles: pd.DataFrame) -> OverlayDecision:
        p = self.params
        a = float(
            atr(candles["high"], candles["low"], candles["close"], p["atr_len"]).iloc[
                -1
            ]
        )
        state = pos.overlay_state.setdefault(self.overlay_id, {})
        if math.isnan(a):
            return (
                OverlayDecision()
            )  # not enough history yet: no stop rather than a guess
        stop = pos.highest_close - p["mult"] * a
        state.update(atr=a, stop=stop)
        return OverlayDecision(stop_price=stop, reason="ATR_TRAIL")


@register("OVL-PLOCK")
class ProgressiveLock(Overlay):
    """Staged locks ``[[gain_pct, lock_pct], ...]``: when the gain passes a stage the
    stop is at least ``entry * (1 + lock_pct)``."""

    def on_bar(self, pos: PositionState, candles: pd.DataFrame) -> OverlayDecision:
        gain = _gain_pct(pos)
        state = pos.overlay_state.setdefault(self.overlay_id, {})
        reached = 0
        lock = None
        for i, (stage_gain, stage_lock) in enumerate(self.params["stages"], start=1):
            if gain + _EPS >= stage_gain:
                reached, lock = i, stage_lock
        state["stage"] = reached
        if lock is None:
            return OverlayDecision()
        stop = pos.entry_price * (1.0 + lock / 100.0)
        state["stop"] = stop
        return OverlayDecision(stop_price=stop, reason=f"PLOCK_STAGE_{reached}")


@register("OVL-COOLDOWN")
class EntryCooldown(Overlay):
    """
    Blocks new entries for ``bars_after_exit`` bars after an exit, or ``bars_after_loss``
    bars after a losing exit (exit fill below the entry fill) - whichever is longer.
    With ``global`` true one exit pauses every symbol. Counting starts at the bar whose
    open the exit filled: with ``bars_after_exit = 3`` signals on that bar and the next
    two are blocked and the third bar after may enter.
    """

    def __init__(self, **params):
        super().__init__(**params)
        # key ("*" when global, else symbol) -> (bar time of the exit fill, was a loss)
        self._last: Dict[str, Tuple[pd.Timestamp, bool]] = {}

    def _key(self, symbol: str) -> str:
        return "*" if self.params["global"] else symbol

    def on_exit(
        self, pos: PositionState, bar_time: pd.Timestamp, exit_price: float
    ) -> None:
        loss = float(exit_price) < float(pos.entry_price)
        self._last[self._key(pos.symbol)] = (pd.Timestamp(bar_time), loss)
        pos.overlay_state.setdefault(self.overlay_id, {})["last_exit_loss"] = loss

    def allow_entry(self, symbol: str, now_bar_time: pd.Timestamp) -> GateResult:
        last = self._last.get(self._key(symbol))
        if last is None:
            return GateResult(True, "")
        if not self.bar_seconds:
            raise RuntimeError(
                "OVL-COOLDOWN needs the bar duration: call StrategyRunner.set_timeframe()"
            )
        exit_time, loss = last
        elapsed = int(
            (pd.Timestamp(now_bar_time) - exit_time)
            / pd.Timedelta(seconds=self.bar_seconds)
        )
        need = max(
            self.params["bars_after_exit"],
            self.params["bars_after_loss"] if loss else 0,
        )
        if elapsed < need:
            kind = "after a loss" if loss else "after an exit"
            return GateResult(False, f"{need - elapsed} bar(s) left {kind}")
        return GateResult(True, "")

    def export_state(self) -> dict:
        return {k: [t.isoformat(), bool(loss)] for k, (t, loss) in self._last.items()}

    def import_state(self, state: dict) -> None:
        self._last = {
            k: (pd.Timestamp(v[0]), bool(v[1]))
            for k, v in state.items()
            if isinstance(v, (list, tuple)) and len(v) == 2
        }
