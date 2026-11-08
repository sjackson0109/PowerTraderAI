"""STRAT-004: long-only Donchian breakout on daily closes (FDS-SR-001 section 5.4.3).

ENTER_LONG on the closed bar t when its close is above every close of the previous
``entry_days`` days: a new closing high. EXIT_LONG when its close is below every close
of the previous ``exit_days`` days: a new closing low. Overlays may exit earlier, never
later.

* **Days, not bars.** The lookbacks are calendar days, turned into bars by the run's bar
  length (``set_timeframe``), so a 4-hour run spans the same time as a daily one. On
  daily bars, 55 days is 55 bars.
* **Closes only.** The channel is built from closes, as in Zarattini, Pagani and
  Barbon (2025), so the decision is made on closed bars and never on an intrabar high.
* **Ties.** A close equal to the previous high is not a breakout, and one equal to the
  previous low is not a new low.
* **Exactly its window.** Rolling maxima and minima need no warm-up beyond their own
  span, so the window the runner feeds is the rule's own span plus the decision bar.
  The backtester and the live engine feed the same window.
* **Defaults** are the Turtle System 2 rule, 55/20 (FDS-SR-001 E-D9): not tuned.
"""

from __future__ import annotations

import math

import pandas as pd

from strategies.base import Action, Signal, Strategy, StrategyError
from strategies.catalogue import register

DAY_SECONDS = 86_400


def days_to_bars(days: int, bar_seconds: int) -> int:
    """Whole bars covering ``days`` calendar days (at least 1)."""
    return max(1, math.ceil(days * DAY_SECONDS / int(bar_seconds)))


@register("STRAT-004")
class DonchianBreakout(Strategy):
    """New ``entry_days`` closing high in, new ``exit_days`` closing low out."""

    def __init__(self, **params):
        super().__init__(**params)
        if self.params["exit_days"] >= self.params["entry_days"]:
            raise StrategyError(
                f"STRAT-004: exit_days ({self.params['exit_days']}) must be less than "
                f"entry_days ({self.params['entry_days']})"
            )

    def bars(self, days: int) -> int:
        """``days`` in this run's bars (daily until ``set_timeframe`` says otherwise)."""
        return days_to_bars(days, self.bar_seconds or DAY_SECONDS)

    @property
    def warmup_bars(self) -> int:
        # the decision bar plus the previous entry_days of closes
        return self.bars(self.params["entry_days"]) + 1

    @property
    def lookback_bars(self) -> int:
        return self.warmup_bars

    def compute(self, candles: pd.DataFrame) -> Signal:
        close = candles["close"].to_numpy(dtype=float)
        n = self.bars(self.params["entry_days"])
        m = self.bars(self.params["exit_days"])
        last = float(close[-1])
        high = float(close[-n - 1 : -1].max())
        low = float(close[-m - 1 : -1].min())
        ind = {"close": last, "channel_high": high, "channel_low": low}
        if math.isnan(last) or math.isnan(high) or math.isnan(low):
            return Signal.hold("CLOSE_MISSING", ind)
        if last < low:
            return Signal(Action.EXIT_LONG, "NEW_CLOSING_LOW", ind)
        if last > high:
            return Signal(Action.ENTER_LONG, "NEW_CLOSING_HIGH", ind)
        return Signal.hold("INSIDE_CHANNEL", ind)
