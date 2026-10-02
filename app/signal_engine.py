"""
SignalEngine (FDS-121 section 7): the trader's source of rule-based decisions.

Each call to ``decide(base)`` returns the decision for the latest *closed* bar of
the active strategy (plus overlays), using the same ``StrategyRunner`` the
backtester uses. Candles are fetched only when a new bar should have closed, not
on every trader cycle.

Fail closed:

* unknown ``strategy.engine`` / ``strategy.active_id`` / bad settings  -> ``block_reason``
  is set and ``decide`` returns None (the trader then places no orders);
* last closed bar older than 2x the timeframe -> ``HOLD`` with reason
  ``STALE_CANDLES`` (and a WARNING);
* no candles at all -> ``HOLD`` with reason ``CANDLES_UNAVAILABLE``.

Every decision is logged once per bar with strategy_id, reason, indicators and
the bar time.
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Dict, Optional, Tuple

import pandas as pd

from market_data.candles import BinanceKlines, CandleDataError, get_candles
from market_data.timeframes import timeframe_seconds
from pt_logging import get_logger
from strategies.base import Action
from strategies.factory import build_runner
from strategies.runner import Decision, PositionState, StrategyRunner
from strategies.settings import StrategySettings, read_strategy_settings

logger = get_logger("signal_engine")

CandleProvider = Callable[[str, str, int, pd.Timestamp], pd.DataFrame]

STALE_FACTOR = 2  # last closed bar may be at most this many timeframes old
FETCH_RETRY_SECONDS = 30.0


def default_candle_provider(
    symbol: str, tf: str, n_bars: int, now: pd.Timestamp
) -> pd.DataFrame:
    """The ``n_bars`` most recent closed bars, via the cache + Binance public klines."""
    step = pd.Timedelta(seconds=timeframe_seconds(tf))
    forming_open = now.floor(step)  # the bar that is still forming opens here
    return get_candles(
        symbol,
        tf,
        forming_open - n_bars * step,
        forming_open,
        closed_only=True,
        fetcher=BinanceKlines(),
    )


def pair_for(base: str) -> str:
    """Trader coin ``BTC`` -> Binance pair ``BTCUSDT``."""
    return f"{str(base).upper().strip()}USDT"


class SignalEngine:
    def __init__(
        self,
        settings_source=None,
        candle_provider: Optional[CandleProvider] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._settings_source = settings_source
        self._provider = candle_provider or default_candle_provider
        self._clock = clock
        self._runner: Optional[StrategyRunner] = None
        self._runner_signature: Optional[tuple] = None
        self._positions: Dict[str, PositionState] = {}
        # per pair: (expected last-closed open_time, candles) and fetch bookkeeping
        self._candles: Dict[str, Tuple[pd.Timestamp, pd.DataFrame]] = {}
        self._last_fetch_attempt: Dict[str, float] = {}
        self._logged: Dict[str, tuple] = {}
        self._warned: Dict[str, float] = {}
        self.last_decisions: Dict[str, Decision] = {}
        # persistence of open positions + overlay state (stops, cooldowns) across restarts
        self._state_path: Optional[str] = None
        self._last_state_json: Optional[str] = None
        self._restored_overlays: Dict[str, dict] = {}

    # -- configuration --------------------------------------------------------------------

    @property
    def settings(self) -> StrategySettings:
        return read_strategy_settings(self._settings_source)

    def block_reason(self) -> Optional[str]:
        """Why orders must not be placed, or None. (Legacy engine: never blocked here.)"""
        return self.settings.problem

    def _runner_for(self, s: StrategySettings) -> StrategyRunner:
        if self._runner is None or self._runner_signature != s.signature:
            self._runner = build_runner(s.active_id, {}, list(s.overlays))
            self._runner.set_timeframe(timeframe_seconds(s.timeframe))
            self._runner.import_state(self._restored_overlays)
            self._runner_signature = s.signature
            self._candles.clear()
            logger.info(
                f"SignalEngine using {s.active_id} on {s.timeframe} "
                f"overlays={[o['id'] for o in s.overlays] or 'none'}"
            )
        return self._runner

    # -- positions (the strategy's view of what the trader holds) -------------------------

    def position(self, base: str) -> Optional[PositionState]:
        return self._positions.get(str(base).upper())

    def ensure_position(
        self, base: str, entry_price: float, bar_time: Optional[pd.Timestamp] = None
    ) -> PositionState:
        """The open position for ``base``, creating it (e.g. after a restart) if needed."""
        base = str(base).upper()
        pos = self._positions.get(base)
        if pos is None:
            s = self.settings
            runner = self._runner_for(s)
            candles = self._candles.get(pair_for(base), (None, pd.DataFrame()))[1]
            when = bar_time if bar_time is not None else pd.Timestamp.now(tz="UTC")
            pos = runner.open_position(base, entry_price, when, candles)
            self._positions[base] = pos
            self._persist()
        return pos

    def forget(self, base: str) -> None:
        """Drop the engine's record for ``base`` (the trader sees it is not held)."""
        if self._positions.pop(str(base).upper(), None) is not None:
            self._persist()

    def record_entry(self, base: str, fill_price: float, bar_time: pd.Timestamp) -> PositionState:
        base = str(base).upper()
        self._positions.pop(base, None)
        return self.ensure_position(base, fill_price, bar_time)

    def record_exit(self, base: str, fill_price: float, bar_time: pd.Timestamp) -> None:
        base = str(base).upper()
        pos = self._positions.pop(base, None)
        if pos is not None and self._runner is not None:
            self._runner.close_position(pos, bar_time, fill_price)
        self._persist()

    # -- persistence ---------------------------------------------------------------------------

    def attach_state(self, path: str) -> None:
        """
        Persist open positions and overlay state (stops, cooldowns) to ``path`` and
        restore whatever a previous run left there, so a restart mid-position keeps
        its stop instead of starting over.
        """
        self._state_path = path
        data: dict = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            pass
        for base, raw in (data.get("positions") or {}).items():
            try:
                self._positions[str(base).upper()] = PositionState.from_dict(raw)
            except (KeyError, TypeError, ValueError):
                logger.warning(f"Ignoring unreadable saved strategy position for {base}")
        overlays = data.get("overlays")
        self._restored_overlays = overlays if isinstance(overlays, dict) else {}
        if self._runner is not None:
            self._runner.import_state(self._restored_overlays)
        self._last_state_json = None
        if self._positions:
            logger.info(f"Restored strategy state for {sorted(self._positions)} from {path}")

    def _persist(self) -> None:
        if not self._state_path:
            return
        payload = {
            "positions": {b: p.to_dict() for b, p in self._positions.items()},
            "overlays": self._runner.export_state() if self._runner is not None else self._restored_overlays,
        }
        text = json.dumps(payload, sort_keys=True)
        if text == self._last_state_json:
            return
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            tmp = f"{self._state_path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, self._state_path)
            self._last_state_json = text
        except OSError as exc:
            self._warn_once("persist", f"Could not save strategy state: {exc}")

    # -- decisions ----------------------------------------------------------------------------

    def decide(self, base: str, position: Optional[PositionState] = None) -> Optional[Decision]:
        """
        Decision for the latest closed bar of ``base``'s pair. ``position`` defaults
        to the engine's own record. Returns None when blocked, when the engine is
        not ``catalogue``, or when ``base`` is not one of ``strategy.symbols``.
        """
        s = self.settings
        if s.problem:
            self._warn_once(
                "blocked", f"Strategy configuration invalid, no signals: {s.problem}", error=True
            )
            return None
        if not s.is_catalogue:
            return None
        pair = pair_for(base)
        if pair not in s.symbols:
            return None

        runner = self._runner_for(s)
        now = pd.Timestamp(self._clock(), unit="s", tz="UTC")
        tf_s = timeframe_seconds(s.timeframe)
        step = pd.Timedelta(seconds=tf_s)
        expected_last_open = now.floor(step) - step

        candles = self._get_candles(pair, s.timeframe, runner, now, expected_last_open)
        if candles is not None and not candles.empty:
            # never evaluate a bar that has not closed, whatever the provider returned
            candles = candles[candles["open_time"] + step <= now]
        if candles is None or candles.empty:
            return self._record(
                base,
                Decision(Action.HOLD, "CANDLES_UNAVAILABLE", {}, now, s.active_id),
                position=None,
                log_key=("CANDLES_UNAVAILABLE",),
            )

        last_open = candles["open_time"].iloc[-1]
        age = (now - (last_open + step)).total_seconds()
        if age > STALE_FACTOR * tf_s:
            self._warn_once(
                f"stale:{pair}",
                f"{pair} {s.timeframe} candles are stale: last closed bar {last_open} is "
                f"{age / 60:.0f} min old (limit {STALE_FACTOR * tf_s / 60:.0f} min); HOLD",
            )
            return self._record(
                base,
                Decision(Action.HOLD, "STALE_CANDLES", {}, last_open, s.active_id),
                position=None,
                log_key=("STALE", last_open),
            )

        pos = position if position is not None else self._positions.get(str(base).upper())
        decision = runner.evaluate(runner.window(candles, len(candles) - 1), pos, str(base).upper())
        if pos is not None:
            self._persist()  # the stop / overlay state may have moved
        return self._record(
            base, decision, position=pos, log_key=(decision.bar_time, pos is None, decision.action)
        )

    # -- internals --------------------------------------------------------------------------------

    def _get_candles(
        self,
        pair: str,
        tf: str,
        runner: StrategyRunner,
        now: pd.Timestamp,
        expected_last_open: pd.Timestamp,
    ) -> Optional[pd.DataFrame]:
        cached = self._candles.get(pair)
        if cached is not None and cached[0] == expected_last_open:
            return cached[1]
        mono = self._clock()
        last_attempt = self._last_fetch_attempt.get(pair)
        if last_attempt is not None and mono - last_attempt < FETCH_RETRY_SECONDS:
            # recently tried (it failed, or returned nothing new): don't hammer the exchange
            return cached[1] if cached is not None else None
        self._last_fetch_attempt[pair] = mono
        try:
            df = self._provider(pair, tf, runner.lookback_bars + 5, now)
        except (CandleDataError, OSError) as exc:
            self._warn_once(f"fetch:{pair}", f"Could not fetch {pair} {tf} candles: {exc}")
            return cached[1] if cached is not None else None
        if df is None or df.empty:
            return cached[1] if cached is not None else None
        self._candles[pair] = (expected_last_open, df)
        return df

    def _record(self, base: str, decision: Decision, position, log_key: tuple) -> Decision:
        base = str(base).upper()
        self.last_decisions[base] = decision
        if self._logged.get(base) != log_key:
            self._logged[base] = log_key
            logger.info(
                f"Decision {base}: strategy={decision.strategy_id} action={decision.action.value} "
                f"reason={decision.reason} bar={decision.bar_time} "
                f"indicators={ {k: round(v, 6) for k, v in decision.indicators.items()} }"
                + (
                    f" stop={decision.stop_price} stop_owner={decision.stop_owner}"
                    if decision.stop_price is not None
                    else ""
                )
                + (
                    f" overlay_state={position.overlay_state}"
                    if position is not None and position.overlay_state
                    else ""
                )
            )
        return decision

    def _warn_once(self, key: str, message: str, error: bool = False, every: float = 300.0) -> None:
        now = self._clock()
        last = self._warned.get(key)
        if last is None or now - last >= every:
            self._warned[key] = now
            (logger.error if error else logger.warning)(message)
