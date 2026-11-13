"""STRAT-005: long-or-cash time-series momentum, decided weekly (FDS-SR-001 section
5.4.3).

On a decision day, it counts how many of three returns, ``close[t] / close[t - L] - 1``
over ``lookback_1``, ``lookback_2`` and ``lookback_3`` calendar days, are positive.
ENTER_LONG when at least ``min_agree`` are; EXIT_LONG when fewer are. Between decision
days it returns HOLD, so only an overlay can exit then. This is the 1-, 3- and 12-month
rule of Hurst, Ooi and Pedersen (2017), long or cash, with a vote in place of their
volatility-scaled sizes (sizing is not a strategy's in this app).

* **Decision days** are every ``rebalance_days`` days counted from Monday 2020-01-06
  (UTC), so the backtester and the live engine pick the same days, whatever the window.
  The decision is made on the bar that closes at 00:00 UTC at the end of a decision
  day: on daily bars, that day's bar.
* **Calendar days.** Each lookback's earlier close is the bar that opened exactly L
  days before the decision bar, found by its open time. If that bar is missing (a gap),
  it returns HOLD: no other bar stands in, earlier or later. A gap anywhere else in the
  window changes nothing.
* **Warm-up is by time.** It holds WARMUP until the candles reach back ``lookback_3``
  days, not until there are ``warmup_bars`` of them. A gap in a coin's first year then
  never holds a decision whose reference bars are all there. On a series with no gaps
  the two rules agree.
* **Defaults** (FDS-SR-001 E-D9): 30, 90 and 365 days, two of three, weekly. Not tuned.
"""

from __future__ import annotations

import math

import pandas as pd

from strategies.base import Action, Signal, Strategy, StrategyError, check_candles
from strategies.breakout import DAY_SECONDS, days_to_bars
from strategies.catalogue import register

# decision days are counted from this Monday
ANCHOR = pd.Timestamp("2020-01-06", tz="UTC")
LOOKBACKS = ("lookback_1", "lookback_2", "lookback_3")


@register("STRAT-005")
class TimeSeriesMomentum(Strategy):
    """At least ``min_agree`` of three past returns positive: long; else cash."""

    counts_bars = False  # each earlier close is found by its open time

    def __init__(self, **params):
        super().__init__(**params)
        days = [self.params[k] for k in LOOKBACKS]
        if not days[0] < days[1] < days[2]:
            raise StrategyError(
                f"STRAT-005: the lookbacks must increase strictly, got {days}"
            )

    def bars(self, days: int) -> int:
        """``days`` in this run's bars (daily until ``set_timeframe`` says otherwise)."""
        return days_to_bars(days, self.bar_seconds or DAY_SECONDS)

    @property
    def warmup_bars(self) -> int:
        return self.bars(self.params["lookback_3"]) + 1

    @property
    def lookback_bars(self) -> int:
        return self.warmup_bars

    def is_decision_bar(self, open_time) -> bool:
        """Whether the bar opening at ``open_time`` is the one that closes a decision
        day (at 00:00 UTC)."""
        bar = pd.Timedelta(seconds=self.bar_seconds or DAY_SECONDS)
        close = pd.Timestamp(open_time) + bar
        if close != close.floor("D"):
            return False  # it does not close at midnight
        day = (close - pd.Timedelta(days=1) - ANCHOR).days
        return day % self.params["rebalance_days"] == 0

    def on_bar(self, candles: pd.DataFrame) -> Signal:
        """As every strategy's, but the warm-up is by time (``compute``)."""
        check_candles(candles)
        return self.compute(candles)

    def compute(self, candles: pd.DataFrame) -> Signal:
        p = self.params
        times = candles["open_time"]
        last_time = times.iloc[-1] if len(times) else None
        if last_time is None or times.iloc[0] > last_time - pd.Timedelta(
            days=p["lookback_3"]
        ):
            return Signal.hold(
                "WARMUP",
                {"bars": float(len(candles)), "needed": float(self.warmup_bars)},
            )
        if not self.is_decision_bar(last_time):
            return Signal.hold("NOT_DECISION_DAY")
        close = candles["close"].to_numpy(dtype=float)
        last = float(close[-1])
        ind = {"close": last}
        votes = 0
        for key in LOOKBACKS:
            days = p[key]
            then_time = last_time - pd.Timedelta(days=days)
            j = int(
                times.searchsorted(then_time)
            )  # by time: a gap elsewhere is no matter
            if j >= len(close) - 1 or times.iloc[j] != then_time:
                return Signal.hold("BARS_MISSING", ind)
            then = float(close[j])
            if math.isnan(last) or math.isnan(then) or then <= 0:
                return Signal.hold("CLOSE_MISSING", ind)
            r = last / then - 1.0
            ind[f"return_{days}d"] = r
            votes += r > 0
        ind["positive"] = float(votes)
        ind["needed"] = float(p["min_agree"])
        if votes >= p["min_agree"]:
            return Signal(Action.ENTER_LONG, "MOMENTUM_UP", ind)
        return Signal(Action.EXIT_LONG, "MOMENTUM_DOWN", ind)
