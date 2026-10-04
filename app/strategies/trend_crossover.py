"""STRAT-001: long-only trend crossover on fast/slow DEMA or TEMA (FDS-122)."""

from __future__ import annotations

import math

import pandas as pd

from strategies.base import Action, Signal, Strategy, StrategyError
from strategies.catalogue import register
from strategies.indicators import adx, dema, tema


@register("STRAT-001")
class TrendCrossover(Strategy):
    """
    ENTER_LONG when, on the current closed bar, fast > slow and

    * fast has been above slow on each of the previous ``persistence_bars`` bars,
    * the cross happened within the last ``persistence_bars + 1`` bars (the bar
      just before that run had fast <= slow), so it fires **once**, on the first
      bar where persistence is satisfied, never on a stale state, and
    * (``regime_filter == "adx"``) ADX >= ``adx_min``.

    EXIT_LONG when fast < slow on the current closed bar (no persistence on exit).
    Overlays (FDS-129) may exit earlier, never later.
    """

    def __init__(self, **params):
        super().__init__(**params)
        if self.params["slow_len"] <= self.params["fast_len"]:
            raise StrategyError(
                f"STRAT-001: slow_len ({self.params['slow_len']}) must be greater than "
                f"fast_len ({self.params['fast_len']})"
            )

    @property
    def warmup_bars(self) -> int:
        # TEMA needs about 3x its length to settle; ADX needs 2*adx_len bars.
        return 3 * self.params["slow_len"] + self.params["adx_len"]

    def compute(self, candles: pd.DataFrame) -> Signal:
        p = self.params
        ma = tema if p["ma_type"] == "TEMA" else dema
        close = candles["close"]
        fast = ma(close, p["fast_len"])
        slow = ma(close, p["slow_len"])
        f, s = float(fast.iloc[-1]), float(slow.iloc[-1])
        ind = {"fast": f, "slow": s}

        if f < s:
            return Signal(Action.EXIT_LONG, "FAST_BELOW_SLOW", ind)
        if f == s:
            return Signal.hold("FAST_EQUALS_SLOW", ind)

        k = p["persistence_bars"]
        above = (fast > slow).to_numpy()
        # the last k+1 bars are all above, and the bar before them was not
        confirmed = bool(above[-(k + 1) :].all()) and not bool(above[-(k + 2)])
        if not confirmed:
            return Signal.hold("NO_FRESH_CROSS", ind)

        if p["regime_filter"] == "adx":
            value = float(
                adx(candles["high"], candles["low"], close, p["adx_len"]).iloc[-1]
            )
            ind["adx"] = value
            ind["adx_min"] = float(p["adx_min"])
            if math.isnan(value):
                return Signal.hold("ADX_UNAVAILABLE", ind)
            if value < p["adx_min"]:
                return Signal.hold("ADX_BELOW_MIN", ind)
        return Signal(Action.ENTER_LONG, "TREND_CROSS_CONFIRMED", ind)
