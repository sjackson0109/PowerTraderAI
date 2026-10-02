"""STRAT-000: the trivial built-in EMA cross, so the signal path works end to end."""

from __future__ import annotations

import pandas as pd

from strategies.base import Action, Signal, Strategy, StrategyError
from strategies.catalogue import register
from strategies.indicators import ema


@register("STRAT-000")
class EmaCross(Strategy):
    """ENTER when the fast EMA crosses above the slow EMA on this bar; EXIT while
    the fast EMA is below the slow EMA."""

    def __init__(self, **params):
        super().__init__(**params)
        if self.params["slow_len"] <= self.params["fast_len"]:
            raise StrategyError("STRAT-000: slow_len must be greater than fast_len")

    @property
    def warmup_bars(self) -> int:
        return 3 * self.params["slow_len"]

    def compute(self, candles: pd.DataFrame) -> Signal:
        close = candles["close"]
        fast = ema(close, self.params["fast_len"])
        slow = ema(close, self.params["slow_len"])
        f, s = float(fast.iloc[-1]), float(slow.iloc[-1])
        f_prev, s_prev = float(fast.iloc[-2]), float(slow.iloc[-2])
        ind = {"fast": f, "slow": s}
        if f > s and f_prev <= s_prev:
            return Signal(Action.ENTER_LONG, "FAST_CROSSED_ABOVE_SLOW", ind)
        if f < s:
            return Signal(Action.EXIT_LONG, "FAST_BELOW_SLOW", ind)
        return Signal.hold("NO_CROSS", ind)
