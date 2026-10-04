"""STRAT-002: long-only Supertrend with an ATR trailing exit (FDS-123)."""

from __future__ import annotations

import pandas as pd

from strategies.base import Action, Signal, Strategy
from strategies.catalogue import register
from strategies.indicators import supertrend


@register("STRAT-002")
class SupertrendAtr(Strategy):
    """
    ENTER_LONG when the Supertrend direction flips from down to up and then stays
    up for ``confirm_bars`` further closed bars (``confirm_bars=0`` = the flip bar).
    It fires once per flip.

    EXIT_LONG while the direction is down, i.e. on the bar whose close falls below
    the trailing Supertrend line. That line *is* the strategy's ATR trailing exit;
    overlays (FDS-129) may exit earlier but never later.

    Note: the Supertrend state carries forward bar to bar, so the signal depends on
    the window of bars it is given. The backtester and the live engine feed the same
    ``lookback_bars`` window, so both see identical signals.
    """

    @property
    def warmup_bars(self) -> int:
        return self.params["atr_len"] * 3

    def compute(self, candles: pd.DataFrame) -> Signal:
        p = self.params
        st = supertrend(candles, p["atr_len"], p["mult"])
        direction = st["direction"].to_numpy()
        n = len(direction)
        line = float(st["line"].iloc[-1])
        close = float(candles["close"].iloc[-1])
        ind = {"line": line, "direction": float(direction[-1]), "close": close}
        atr_now = st["atr"].iloc[-1]
        ind["atr"] = float(atr_now)

        if direction[-1] < 0:
            return Signal(Action.EXIT_LONG, "SUPERTREND_DOWN", ind)

        c = p["confirm_bars"]
        flip = n - 1 - c  # the bar on which direction turned up
        if flip >= 1 and direction[flip - 1] < 0 and (direction[flip:] > 0).all():
            return Signal(Action.ENTER_LONG, "SUPERTREND_FLIPPED_UP", ind)
        return Signal.hold("NO_FRESH_FLIP", ind)
