"""STRAT-006: long or cash by the price against its moving average, on daily closes
(PTAI-RD-001 backlog 3.2; research catalogue entry ``trend.price-above-ma``).

ENTER_LONG on the closed bar t when its close is above the simple average of the last
``average_days`` closes, bar t's included; EXIT_LONG when it is below. A close equal to
the average holds. This is the 20-day price-against-average rule of Grobys, Ahmed and
Sapkota (2020), the sign of the price-to-average ratio that Detzel et al. (2021) found
to forecast daily Bitcoin returns. It is declared in the momentum family, so its trials
are counted with STRAT-005's when a family is corrected for multiple testing.

* **Days, not bars.** The average spans calendar days, turned into bars by the run's
  bar length (``set_timeframe``), as STRAT-004's channels do. On daily bars, 20 days is
  20 bars.
* **Every close decides.** It says ENTER on every close above the average and EXIT on
  every close below; the runner ignores ENTER while long and EXIT while flat. After a
  stop's exit, the next close above the average enters again.
* **Exactly its window**: the average's own span; the backtester and the live engine
  feed the same window.
* **Defaults**: 20 days, the published rule. Not tuned.
"""

from __future__ import annotations

import math

import pandas as pd

from strategies.base import Action, Signal, Strategy
from strategies.breakout import DAY_SECONDS, days_to_bars
from strategies.catalogue import register


@register("STRAT-006")
class PriceAboveAverage(Strategy):
    """Close above its ``average_days`` simple average: long; below: cash."""

    def bars(self, days: int) -> int:
        """``days`` in this run's bars (daily until ``set_timeframe`` says otherwise)."""
        return days_to_bars(days, self.bar_seconds or DAY_SECONDS)

    @property
    def warmup_bars(self) -> int:
        return self.bars(self.params["average_days"])

    @property
    def lookback_bars(self) -> int:
        return self.warmup_bars

    def compute(self, candles: pd.DataFrame) -> Signal:
        close = candles["close"].to_numpy(dtype=float)
        n = self.bars(self.params["average_days"])
        last = float(close[-1])
        average = float(close[-n:].mean())
        ind = {"close": last, "average": average}
        if math.isnan(last) or math.isnan(average):
            return Signal.hold("CLOSE_MISSING", ind)
        if last > average:
            return Signal(Action.ENTER_LONG, "ABOVE_AVERAGE", ind)
        if last < average:
            return Signal(Action.EXIT_LONG, "BELOW_AVERAGE", ind)
        return Signal.hold("AT_AVERAGE", ind)
