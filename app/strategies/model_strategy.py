"""
STRAT-003: the trained pattern model as a catalogue strategy (FDS-MDL Phase 3).

The legacy neural runner's rule (``pt_thinker.step_coin``), reproduced, on a model
published by the pattern trainer, mapped to long-only:

* **Model.** Loaded once, at construction, by ``model_id`` through
  ``model_store.load``, which refuses a model without a matching manifest (and logs an
  ERROR). ``on_bar`` performs no I/O and never refits or updates the model.
* **Bars.** The model predicts from seven timeframes (1 hour to 1 week). At decision
  time *t* each timeframe uses its last bar that closed **strictly before** *t*, so a
  bar closing at *t* or later is never used (FDS-MDL 6.3). *t* is the close of the bar
  being decided on, and the current price is that bar's close: the runner's last
  evaluation just before the bar closes (owner decision, 2026-10-06). The bars are given
  by the caller (``use_bars({candle timeframe: frame})``: the backtest CLI loads them
  from the run's own data source); otherwise they are read from the default candle
  cache, for the model's own symbol, when the run's timeframe is set (never in
  ``on_bar``). A timeframe whose expected bar is missing makes the decision HOLD
  (``BARS_MISSING:<timeframe>``): no older bar is used instead. The backtester counts
  those decisions and reports them.
* **Rule.** ``pattern_model.thinker_decision``: the runner's bounds, gap pass, remap and
  LONG/SHORT comparison in steady state (the bounds come from the same predictions,
  as after two sweeps on the same bars).
* **Mapping** (owner decision, 2026-10-06: keep the legacy trader's short veto):
  ``EXIT_LONG`` when the primary timeframe (the run's own) is SHORT, whether or not it is
  counted (so a SHORT there never enters); otherwise ``ENTER_LONG`` when at least
  ``min_tf_agree`` of the counted ``timeframes`` are LONG and none is SHORT (the legacy
  entry gate, ``trade_start_level`` 3, counted over all seven); ``HOLD`` otherwise.

The run's timeframe comes from ``StrategyRunner.set_timeframe`` (the backtester and the
signal engine both call it); it must be one of the model's intraday or daily
timeframes. The model's ``train_end`` is ``model_train_end``, which the backtester
compares with the first scored bar (``LOOKAHEAD_MODEL``).

The runner's 14-day freshness gate (a coin trained more than 14 days ago is held) does
not apply here: a backtest scores a fixed model on later bars by design.
"""

from __future__ import annotations

import bisect
import logging
import os
from typing import Dict, List, Mapping, Optional, Tuple

import pandas as pd

import model_store
import pt_paths
from market_data.candles import CandleDataError, cache_path, load_candles_csv
from market_data.timeframes import bar_open_floor, candle_timeframe_seconds
from pattern_model import CANDLE_TF, TIMEFRAMES, GapPassStuck, thinker_decision
from strategies.base import Action, Signal, Strategy, StrategyError
from strategies.catalogue import register

logger = logging.getLogger("strategies.model")

# the run timeframes STRAT-003 can decide on: the model's timeframes below one week
PRIMARY_BY_SECONDS = {
    candle_timeframe_seconds(CANDLE_TF[tf]): tf for tf in TIMEFRAMES if tf != "1week"
}
SIDE_VALUE = {"long": 1.0, "short": -1.0, "none": 0.0}


class _Bars:
    """One timeframe's bars: open time (epoch seconds), open and close, oldest first."""

    def __init__(self, frame: Optional[pd.DataFrame], step: int) -> None:
        self.step = step
        if frame is None or frame.empty:
            self.open_s: List[int] = []
            self.open: List[float] = []
            self.close: List[float] = []
            return
        frame = frame.sort_values("open_time")
        self.open_s = [int(t.timestamp()) for t in frame["open_time"]]
        self.open = [float(x) for x in frame["open"].tolist()]
        self.close = [float(x) for x in frame["close"].tolist()]

    def last_closed_before(self, t_s: int) -> Optional[int]:
        """Index of the last bar that closed strictly before ``t_s`` (its open plus one
        bar is earlier than ``t_s``), or None."""
        i = bisect.bisect_left(self.open_s, t_s - self.step) - 1
        return i if i >= 0 else None


def cached_bars(symbol: str) -> Dict[str, pd.DataFrame]:
    """The candle cache's bars for ``symbol`` in the model's candle timeframes (read
    only; a missing file is simply absent)."""
    folder = os.path.join(pt_paths.cache_dir(create=False), "candles")
    frames = {}
    for tf in TIMEFRAMES:
        ctf = CANDLE_TF[tf]
        path = cache_path(symbol, ctf, folder)
        if not os.path.isfile(path):
            logger.warning("STRAT-003: no cached %s %s bars at %s", symbol, ctf, path)
            continue
        try:
            frames[ctf] = load_candles_csv(path, ctf)
        except (CandleDataError, OSError, ValueError) as exc:
            logger.error("STRAT-003: unreadable %s %s bars: %s", symbol, ctf, exc)
    return frames


def _utc_time(value, model_id) -> pd.Timestamp:
    """A manifest time as a UTC timestamp (naive means UTC, as in the trainer); a
    missing or unreadable one refuses the model."""
    try:
        ts = pd.Timestamp(value)
    except (TypeError, ValueError):
        ts = pd.NaT
    if pd.isna(ts):
        raise StrategyError(
            f"STRAT-003: model {model_id} has no readable train_end ({value!r})"
        )
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


@register("STRAT-003")
class TrainedModelStrategy(Strategy):
    # the candle timeframes it reads (the backtest CLI loads these for it), and the bar
    # lengths it can decide on (checked before any data is loaded)
    candle_timeframes = tuple(CANDLE_TF[tf] for tf in TIMEFRAMES)
    supported_bar_seconds = frozenset(PRIMARY_BY_SECONDS)

    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.timeframes: Tuple[str, ...] = tuple(self.params["timeframes"])
        self.min_tf_agree = int(self.params["min_tf_agree"])
        if self.min_tf_agree > len(self.timeframes):
            raise StrategyError(
                f"STRAT-003: min_tf_agree {self.min_tf_agree} is more than the "
                f"{len(self.timeframes)} counted timeframes; it could never enter"
            )
        loaded = model_store.load(self.params["model_id"])  # fails closed, logs ERROR
        self.model_id = loaded.model_id
        self.model = loaded.model
        self.symbol = loaded.manifest["symbol"]
        self.model_symbol = self.symbol  # the backtester refuses a run on another pair
        self.model_window = (loaded.manifest["train_start"], loaded.train_end)
        # read by the backtester: nothing that opens before this may be scored
        self.model_train_end = _utc_time(loaded.train_end, self.model_id)
        self._bars: Optional[Dict[str, _Bars]] = None
        self._predictions: Dict[Tuple[str, int], object] = {}

    def use_bars(self, frames: Mapping[str, pd.DataFrame]) -> None:
        """The bars to decide on: ``{candle timeframe: frame}`` (closed bars)."""
        self._bars = {
            tf: _Bars(
                frames.get(CANDLE_TF[tf]), candle_timeframe_seconds(CANDLE_TF[tf])
            )
            for tf in TIMEFRAMES
        }
        self._predictions = {}

    # -- sizing ----------------------------------------------------------------------------

    @property
    def warmup_bars(self) -> int:
        return 1  # the bar decided on; every other input comes from the model's bars

    @property
    def lookback_bars(self) -> int:
        return 1

    def set_timeframe(self, tf_seconds: int) -> None:
        if int(tf_seconds) not in PRIMARY_BY_SECONDS:
            raise StrategyError(
                f"STRAT-003 decides on one of the model's timeframes "
                f"{sorted(CANDLE_TF[t] for t in PRIMARY_BY_SECONDS.values())}; "
                f"got a {tf_seconds} s bar"
            )
        super().set_timeframe(tf_seconds)
        if self._bars is None:  # nobody gave it bars: the default candle cache, once
            self.use_bars(cached_bars(self.symbol))

    # -- the decision -------------------------------------------------------------------

    def _prediction(self, tf: str, i: int):
        key = (tf, i)
        if key not in self._predictions:
            b = self._bars[tf]
            self._predictions[key] = self.model.timeframes[tf].predict(
                b.open[i], b.close[i]
            )
        return self._predictions[key]

    def compute(self, candles: pd.DataFrame) -> Signal:
        if self.bar_seconds is None or self._bars is None:
            return Signal.hold("TIMEFRAME_UNKNOWN")
        primary = PRIMARY_BY_SECONDS[self.bar_seconds]
        last = candles.iloc[-1]
        t_s = int(pd.Timestamp(last["open_time"]).timestamp()) + self.bar_seconds
        price = float(last["close"])
        indicators: Dict[str, float] = {"price": price}
        predictions = []
        for tf in TIMEFRAMES:
            b = self._bars[tf]
            i = b.last_closed_before(t_s)
            # the bar that closed last before t: the one before the bar t falls in
            expected = bar_open_floor(t_s - 1, CANDLE_TF[tf]) - b.step
            if i is None or b.open_s[i] != expected:
                indicators[f"expected_{tf}"] = float(expected)
                return Signal.hold(f"BARS_MISSING:{tf}", indicators)
            indicators[f"bar_{tf}"] = float(b.open_s[i])
            predictions.append(self._prediction(tf, i))
        # which timeframes matched a memory (an inactive one carries the placeholder
        # bounds): reported with every decision that made all seven predictions
        for tf, prediction in zip(TIMEFRAMES, predictions):
            indicators[f"active_{tf}"] = 1.0 if prediction.active else 0.0
        try:
            sides, lows, highs = thinker_decision(predictions, price)
        except GapPassStuck:
            return Signal.hold("BOUNDS_NOT_CONVERGED", indicators)
        for tf, side in zip(TIMEFRAMES, sides):
            indicators[f"side_{tf}"] = SIDE_VALUE[side]
        counted = [sides[TIMEFRAMES.index(tf)] for tf in self.timeframes]
        longs, shorts = counted.count("long"), counted.count("short")
        p = TIMEFRAMES.index(primary)
        indicators.update(
            longs=float(longs),
            shorts=float(shorts),
            low_bound=float(lows[p]),
            high_bound=float(highs[p]),
        )
        if sides[p] == "short":
            return Signal(Action.EXIT_LONG, f"SHORT_ON_{primary}", indicators)
        if longs >= self.min_tf_agree and shorts == 0:
            return Signal(
                Action.ENTER_LONG,
                f"LONG_ON_{longs}_OF_{len(self.timeframes)}",
                indicators,
            )
        return Signal.hold(f"LONG_{longs}_SHORT_{shorts}", indicators)
