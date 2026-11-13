"""
A strategy's trades on one coin, as the backtester's rules make them (FDS-SR-001
section 5.10).

``TradeTable`` holds one coin's closed candles and a strategy with its overlays
(``RunnerSpec``). For a bar i on which an entry is decided, ``trade_from(i)`` is the trade
``backtest.engine.run_backtest`` would make from it at zero cost:

* the entry fills at bar i + 1's open;
* from that bar's close on, the runner decides with the position open (the strategy's
  EXIT, an overlay's exit or stop), and the exit fills at the next bar's open;
* the last bar decides nothing: a trade still open is closed at its close (``forced``),
  and its exit time is that close (the backtester labels it with the bar's open; a
  trade entering on the last bar would otherwise open and close at the same instant).

Costs are applied later, by the portfolio replay, once (FDS-SIG-004 section 5.8.1).

``candidates()`` are the trades from every bar on which the runner, flat, says
ENTER_LONG: the strategy's signal and every entry gate that depends only on the market
(OVL-REGIME's context included). A gate that depends on the path (OVL-COOLDOWN, which
counts from the path's own last exit) is left to the replay (``RunnerSpec.cooldown``).

Each bar's strategy signal is computed once; the runner then evaluates positions with
those signals (``_Signals``), so a trade costs its overlays' work only. A trade from a
bar is computed once and kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

from market_data.timeframes import timeframe_seconds
from signal_fusion.evaluation.replay import Cooldown, Opportunity
from strategies.base import Action, Signal
from strategies.catalogue import create
from strategies.factory import build_runner
from strategies.runner import StrategyRunner, slice_context


@dataclass(frozen=True)
class RunnerSpec:
    """A catalogue strategy, its parameters and overlays, on a timeframe."""

    strategy_id: str
    params: Mapping[str, Any] = field(default_factory=dict)
    overlays: Tuple[Mapping[str, Any], ...] = ()
    timeframe: str = "1d"

    @property
    def bar_seconds(self) -> int:
        return timeframe_seconds(self.timeframe)

    def build(self) -> StrategyRunner:
        runner = build_runner(
            self.strategy_id, dict(self.params), [dict(o) for o in self.overlays]
        )
        runner.set_timeframe(self.bar_seconds)
        return runner

    def cooldown(self) -> Optional[Cooldown]:
        """OVL-COOLDOWN's rule, for the replay, when the spec has it."""
        for spec in self.overlays:
            if spec.get("id") == "OVL-COOLDOWN":
                p = create("OVL-COOLDOWN", **dict(spec.get("params") or {})).params
                return Cooldown(
                    int(p["bars_after_exit"]),
                    int(p["bars_after_loss"]),
                    bool(p["global"]),
                    self.bar_seconds,
                )
        return None


@dataclass(frozen=True)
class Trade:
    coin: str
    decided: int  # the bar whose close decided the entry
    entry_i: int
    exit_i: int
    entry_s: int  # the entry fill's time: bar entry_i's open
    exit_s: int  # the exit fill's time: bar exit_i's open (its close, if forced)
    entry_price: float  # raw, before slippage
    exit_price: float
    exit_rule: str
    forced: bool

    def opportunity(self) -> Opportunity:
        return Opportunity(
            coin=self.coin,
            entry_s=self.entry_s,
            exit_s=self.exit_s,
            entry_price=self.entry_price,
            exit_price=self.exit_price,
        )


class _Signals:
    """Stands in for the strategy inside the runner: the signal it gave each bar."""

    def __init__(self, strategy, by_time: Dict[pd.Timestamp, Signal]) -> None:
        self._strategy = strategy
        self._by_time = by_time
        self.strategy_id = strategy.strategy_id

    @property
    def lookback_bars(self) -> int:
        return self._strategy.lookback_bars

    @property
    def warmup_bars(self) -> int:
        return self._strategy.warmup_bars

    def set_timeframe(self, tf_seconds: int) -> None:
        self._strategy.set_timeframe(tf_seconds)

    def on_bar(self, candles: pd.DataFrame) -> Signal:
        return self._by_time[candles["open_time"].iloc[-1]]


def _seconds(t: pd.Timestamp) -> int:
    return int(pd.Timestamp(t).timestamp())


class TradeTable:
    """One coin's trades under one ``RunnerSpec`` (see the module docstring)."""

    def __init__(
        self,
        coin: str,
        candles: pd.DataFrame,
        spec: RunnerSpec,
        context_frames: Optional[Mapping[Tuple[str, str], pd.DataFrame]] = None,
    ) -> None:
        self.coin = coin
        self.spec = spec
        self.candles = candles.reset_index(drop=True)
        self.n = len(self.candles)
        self._open = self.candles["open"].to_numpy(dtype=float)
        self._close = self.candles["close"].to_numpy(dtype=float)
        self._times = self.candles["open_time"]
        self._step = pd.Timedelta(seconds=spec.bar_seconds)
        runner = spec.build()
        self._needs = runner.context_needs()
        self._frames = dict(context_frames or {})
        strategy = runner.strategy
        signals = {
            self._times.iloc[i]: strategy.on_bar(runner.window(self.candles, i))
            for i in range(self.n)
        }
        runner.strategy = _Signals(strategy, signals)
        self._runner = runner
        self._exit_signal = np.array(
            [
                signals[self._times.iloc[i]].action is Action.EXIT_LONG
                for i in range(self.n)
            ]
        )
        # the runner, flat, at every bar that can still be followed by an entry fill
        self.enters = np.zeros(self.n, dtype=bool)
        for i in range(self.n - 1):
            if signals[self._times.iloc[i]].action is not Action.ENTER_LONG:
                continue
            d = self._evaluate(i, None)
            self.enters[i] = d.action is Action.ENTER_LONG
        self._trades: Dict[int, Trade] = {}
        # with no overlays, an open position exits on the first EXIT signal
        self._fast = not runner.overlays
        if self._fast:
            nxt = np.full(self.n + 1, self.n - 1, dtype=np.int64)
            for k in range(self.n - 2, -1, -1):
                nxt[k] = k if self._exit_signal[k] else nxt[k + 1]
            self._next_exit = nxt

    def _context(self, i: int):
        if not self._needs:
            return None
        return slice_context(
            self._frames, self._needs, self._times.iloc[i] + self._step
        )

    def _evaluate(self, i: int, pos):
        window = self._runner.window(self.candles, i)
        context = self._context(i)
        if context is None:
            return self._runner.evaluate(window, pos, self.coin)
        return self._runner.evaluate(window, pos, self.coin, context)

    @property
    def first_decision(self) -> int:
        """The first bar the strategy can decide on (its warm-up met)."""
        return max(0, self._runner.strategy.warmup_bars - 1)

    def trade_from(self, i: int) -> Trade:
        """The trade an entry decided on bar ``i`` makes (``i`` <= n - 2)."""
        if not 0 <= i <= self.n - 2:
            raise IndexError(f"no entry can follow bar {i} of {self.n}")
        cached = self._trades.get(i)
        if cached is not None:
            return cached
        entry = i + 1
        last = self.n - 1
        if self._fast:
            k = int(self._next_exit[entry])
            if k <= last - 1 and self._exit_signal[k]:
                trade = self._trade(i, entry, k + 1, "strategy", False)
            else:
                trade = self._trade(i, entry, last, "end_of_data", True)
        else:
            pos = self._runner.open_position(
                self.coin,
                self._open[entry],
                self._times.iloc[entry],
                self._runner.window(self.candles, entry),
            )
            trade = None
            for k in range(entry, last):
                d = self._evaluate(k, pos)
                if d.action is Action.EXIT_LONG:
                    trade = self._trade(
                        i, entry, k + 1, d.exit_rule or "strategy", False
                    )
                    break
            if trade is None:
                trade = self._trade(i, entry, last, "end_of_data", True)
        self._trades[i] = trade
        return trade

    def _trade(self, decided, entry, exit_i, rule, forced) -> Trade:
        return Trade(
            coin=self.coin,
            decided=decided,
            entry_i=entry,
            exit_i=exit_i,
            entry_s=_seconds(self._times.iloc[entry]),
            exit_s=_seconds(
                self._times.iloc[exit_i] + (self._step if forced else pd.Timedelta(0))
            ),
            entry_price=float(self._open[entry]),
            exit_price=float(self._close[exit_i] if forced else self._open[exit_i]),
            exit_rule=rule,
            forced=forced,
        )

    def candidates(self) -> List[Trade]:
        """The trades from every bar the runner, flat, enters on."""
        return [self.trade_from(i) for i in np.flatnonzero(self.enters).tolist()]

    def prices(self) -> Tuple[np.ndarray, np.ndarray]:
        """(close times in seconds, closes), to mark positions at each close."""
        closes_at = (self._times + self._step).map(_seconds).to_numpy(dtype=np.int64)
        return closes_at, self._close.copy()

    def lows(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """(close times in seconds, lows), for the replay's intrabar figures; None
        when the candles have no lows."""
        return self._column("low")

    def highs(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """(close times in seconds, highs), for the intrabar figures' peak; None when
        the candles have no highs."""
        return self._column("high")

    def _column(self, name: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        if name not in self.candles:
            return None
        closes_at = (self._times + self._step).map(_seconds).to_numpy(dtype=np.int64)
        return closes_at, self.candles[name].to_numpy(dtype=float, copy=True)
