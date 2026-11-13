"""STRAT-007: long-only Donchian breakout with a midline exit, on daily closes
(PTAI-RD-001 backlog 3.1; research catalogue entry ``breakout.zarattini-ensemble``).

One member of Zarattini, Pagani and Barbon's (2025) ensemble. ENTER_LONG on the closed
bar t when its close is above every close of the previous ``channel_days`` days: a new
closing high, as STRAT-004 enters. EXIT_LONG when its close is below the midline of that
channel, halfway between the highest and the lowest of those closes.

* **The ratchet is OVL-MIDLINE's.** In the paper the stop starts at the midline and never
  moves down. A strategy here sees only candles, not its position, so the stop that
  never moves down is the overlay OVL-MIDLINE with the same days: the runner keeps the
  highest stop any overlay has set since the entry. Without it, this exits below the
  midline of the day, which can fall.
* **The ensemble** (``strategy_lab.ensemble``) runs several members, each with its own
  share of a coin's allocation. Members under 20 days are left out: at this account's
  fees their 15 to 29 round trips a year cost more than the paper's edge (B §3).
* **Days, not bars; closes only; ties; exactly its window**: as STRAT-004.
* **Default** 20 days, the shortest member kept. Not tuned.
"""

from __future__ import annotations

import math

import pandas as pd

from strategies.base import Action, Signal, Strategy
from strategies.breakout import DAY_SECONDS, days_to_bars
from strategies.catalogue import register
from strategies.runner import Overlay, OverlayDecision, PositionState


def midline(close, n: int) -> tuple:
    """The previous ``n`` closes' highest, lowest and midline, the last close excluded."""
    window = close[-n - 1 : -1]
    high, low = float(window.max()), float(window.min())
    return high, low, (high + low) / 2.0


@register("STRAT-007")
class DonchianMidline(Strategy):
    """New ``channel_days`` closing high in; a close below the channel's midline out."""

    def bars(self, days: int) -> int:
        """``days`` in this run's bars (daily until ``set_timeframe`` says otherwise)."""
        return days_to_bars(days, self.bar_seconds or DAY_SECONDS)

    @property
    def warmup_bars(self) -> int:
        # the decision bar plus the previous channel_days of closes
        return self.bars(self.params["channel_days"]) + 1

    @property
    def lookback_bars(self) -> int:
        return self.warmup_bars

    def compute(self, candles: pd.DataFrame) -> Signal:
        close = candles["close"].to_numpy(dtype=float)
        last = float(close[-1])
        high, low, mid = midline(close, self.bars(self.params["channel_days"]))
        ind = {"close": last, "channel_high": high, "channel_low": low, "midline": mid}
        if math.isnan(last) or math.isnan(high) or math.isnan(low):
            return Signal.hold("CLOSE_MISSING", ind)
        if last > high:
            return Signal(Action.ENTER_LONG, "NEW_CLOSING_HIGH", ind)
        if last < mid:
            return Signal(Action.EXIT_LONG, "BELOW_MIDLINE", ind)
        return Signal.hold("INSIDE_CHANNEL", ind)


@register("OVL-MIDLINE")
class MidlineStop(Overlay):
    """The stop at the midline of the previous ``days`` closes, set on every bar a
    position is open. The runner keeps the highest stop since the entry, so the stop
    starts at the midline and never moves down (Zarattini, Pagani and Barbon 2025);
    a close below it exits. With STRAT-007, give it the strategy's channel days."""

    def bars(self) -> int:
        return days_to_bars(self.params["days"], self.bar_seconds or DAY_SECONDS)

    @property
    def lookback_bars(self) -> int:
        return self.bars() + 1

    def on_bar(self, pos: PositionState, candles: pd.DataFrame) -> OverlayDecision:
        close = candles["close"].to_numpy(dtype=float)
        n = self.bars()
        state = pos.overlay_state.setdefault(self.overlay_id, {})
        if len(close) < n + 1:
            return (
                OverlayDecision()
            )  # not enough closes yet: no stop rather than a guess
        _high, _low, mid = midline(close, n)
        if math.isnan(mid):
            return OverlayDecision()
        state["midline"] = mid
        return OverlayDecision(stop_price=mid, reason="MIDLINE")
