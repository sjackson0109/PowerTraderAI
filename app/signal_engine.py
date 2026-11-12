"""
SignalEngine (FDS-121 section 7): the trader's source of rule-based decisions.

Each call to ``decide(base)`` returns the decision for the latest *closed* bar of
the active strategy (plus overlays), using the same ``StrategyRunner`` the
backtester uses. Candles are fetched only when a new bar should have closed, not
on every trader cycle.

Fail closed:

* unknown ``strategy.engine`` / ``strategy.active_id`` / bad settings  -> ``block_reason``
  is set and ``decide`` returns None (the trader then places no orders);
* a strategy whose model cannot be used (STRAT-003 without a published model whose
  manifest matches it) -> the same, with an ERROR logged;
* last closed bar older than 2x the timeframe -> ``HOLD`` with reason
  ``STALE_CANDLES`` (and a WARNING);
* no candles at all -> ``HOLD`` with reason ``CANDLES_UNAVAILABLE``.

An entry is acted on only within ``ENTRY_WINDOW_S`` (15 minutes) of its bar's close, the
moment the backtester fills it (at the next bar's open), so a refused entry is retried
within that time only. Later, the ``ENTER_LONG`` becomes ``HOLD`` with reason
``ENTRY_MISSED:<the entry's reason>``, logged once per coin and bar with how late it
was: a trader started after a close does not buy on that bar. Exits are never late.

Every decision is logged once per bar with strategy_id, reason, indicators and
the bar time.
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Dict, Optional, Tuple

import pandas as pd

from market_data.candles import CandleDataError, exchange_candles
from market_data.timeframes import candle_timeframe_seconds, timeframe_seconds
from pt_exchange_abstraction import MarketNotFound
from pt_logging import get_logger
from model_store import ModelStoreError
from strategies.base import Action, StrategyError
from strategies.catalogue import CatalogueError, ParamError
from strategies.factory import build_runner
from strategies.runner import Decision, PositionState, StrategyRunner, slice_context
from strategies.settings import StrategySettings, read_strategy_settings

logger = get_logger("signal_engine")

CandleProvider = Callable[[str, str, int, pd.Timestamp], pd.DataFrame]

STALE_FACTOR = 2  # last closed bar may be at most this many timeframes old
# an entry is acted on at most this long after its bar's close, where the backtester
# fills it (the next bar's open); later it is missed (N12)
ENTRY_WINDOW_S = 15 * 60
ENTRY_MISSED = "ENTRY_MISSED"
FETCH_RETRY_SECONDS = 30.0


def default_candle_provider(
    symbol: str, tf: str, n_bars: int, now: pd.Timestamp
) -> pd.DataFrame:
    """The ``n_bars`` most recent closed bars of a coin's market, from the exchanges
    in Settings, primary first, through the per-exchange candle cache
    (``exchange_candles``; FDS-MX-001 phase E)."""
    step = pd.Timedelta(seconds=timeframe_seconds(tf))
    forming_open = now.floor(step)  # the bar that is still forming opens here
    return exchange_candles(
        symbol, tf, forming_open - n_bars * step, forming_open, closed_only=True
    )


def _frame_key(
    df: pd.DataFrame,
    expected_last_open: pd.Timestamp,
    step: pd.Timedelta,
    now: pd.Timestamp,
) -> Optional[pd.Timestamp]:
    """The key a fetched frame is kept under. ``expected_last_open`` when the frame
    holds that bar, so it is current until the next bar closes. Otherwise the open
    of its last closed bar (None if it has none): the exchange has not published the
    bar yet, so the frame is only a fallback, and the next call fetches again after
    ``FETCH_RETRY_SECONDS``. A late bar is then decided within that interval,
    instead of a bar later or never (STRAT-004 paper readiness, D1)."""
    closed = df["open_time"][df["open_time"] + step <= now]
    if closed.empty:
        return None
    last = closed.iloc[-1]
    return expected_last_open if last >= expected_last_open else last


def market_for(base: str) -> str:
    """Trader coin ``BTC`` -> its market ``BTC-USD`` (USD, USDT and USDC count as the
    same dollar)."""
    from pt_exchange_abstraction import dollar_symbol

    return dollar_symbol(base)


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
        # why the configured strategy could not be built (cleared when settings change)
        self._build_error: Optional[Tuple[tuple, str]] = None
        self._positions: Dict[str, PositionState] = {}
        # per pair: (the frame's key, ``_frame_key``; candles) and fetch bookkeeping
        self._candles: Dict[str, Tuple[Optional[pd.Timestamp], pd.DataFrame]] = {}
        self._last_fetch_attempt: Dict[str, float] = {}
        # an entry gate's market context (FDS-SR-001 5.6), per (pair, timeframe)
        self._context: Dict[
            Tuple[str, str], Tuple[Optional[pd.Timestamp], pd.DataFrame]
        ] = {}
        self._context_attempt: Dict[Tuple[str, str], float] = {}
        self._logged: Dict[str, tuple] = {}
        self._warned: Dict[str, float] = {}
        self.last_decisions: Dict[str, Decision] = {}
        # <COIN> -> the exchange whose bars its last decision used (None: none)
        self.last_exchanges: Dict[str, Optional[str]] = {}
        # <pair> -> the exchange that served its cached bars (df.attrs)
        self._sources: Dict[str, Optional[str]] = {}
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
        s = self.settings
        if s.problem:
            return s.problem
        if self._build_error is not None and self._build_error[0] == s.signature:
            return self._build_error[1]
        return None

    def _runner_for(self, s: StrategySettings) -> Optional[StrategyRunner]:
        """The runner for settings ``s`` (its strategy built with the parameters in
        Settings > Strategy), or None when it cannot be built: the strategy's model
        cannot be used (no published model whose manifest matches it), or the
        parameters are refused. Then there are no signals, the reason is logged as an
        ERROR (every few minutes) and returned by ``block_reason``."""
        if self._runner is None or self._runner_signature != s.signature:
            if self._build_error is not None and self._build_error[0] == s.signature:
                self._warn_once(
                    f"build:{s.signature}", f"No signals: {self._build_error[1]}", True
                )
                return None
            try:
                runner = build_runner(s.active_id, s.params, list(s.overlays))
                runner.set_timeframe(timeframe_seconds(s.timeframe))
            except (ModelStoreError, CatalogueError, ParamError, StrategyError) as exc:
                self._keep_overlay_state()
                self._runner, self._runner_signature = None, None
                reason = f"{s.active_id} cannot be used: {exc}"
                self._build_error = (s.signature, reason)
                self._warn_once(f"build:{s.signature}", f"No signals: {reason}", True)
                return None
            self._keep_overlay_state()
            self._build_error = None
            self._runner = runner
            self._runner.import_state(self._restored_overlays)
            self._runner_signature = s.signature
            self._candles.clear()
            logger.info(
                f"SignalEngine using {s.active_id} on {s.timeframe} "
                f"params={s.params or 'defaults'} "
                f"overlays={[o['id'] for o in s.overlays] or 'none'}"
            )
        return self._runner

    def _keep_overlay_state(self) -> None:
        """Before the runner is replaced: keep its overlays' timers (e.g. a running
        cooldown), so a settings change does not reset them. An overlay that is
        unticked keeps its last state, for when it is ticked again."""
        if self._runner is not None:
            self._restored_overlays = {
                **self._restored_overlays,
                **self._runner.export_state(),
            }

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
            candles = self._candles.get(market_for(base), (None, pd.DataFrame()))[1]
            when = bar_time if bar_time is not None else pd.Timestamp.now(tz="UTC")
            if runner is None:
                # no strategy to manage it (decide() returns None): keep the record only
                pos = PositionState(base, float(entry_price), when, float(entry_price))
            else:
                pos = runner.open_position(base, entry_price, when, candles)
            self._positions[base] = pos
            self._persist()
        return pos

    def forget(self, base: str) -> None:
        """Drop the engine's record for ``base`` (the trader sees it is not held)."""
        if self._positions.pop(str(base).upper(), None) is not None:
            self._persist()

    def record_entry(
        self, base: str, fill_price: float, bar_time: pd.Timestamp
    ) -> PositionState:
        base = str(base).upper()
        self._positions.pop(base, None)
        return self.ensure_position(base, fill_price, bar_time)

    def fill_bar(self, bar_time: pd.Timestamp) -> pd.Timestamp:
        """The bar an order decided at the close of ``bar_time``'s bar fills in: the
        next bar, as the backtester fills it at that bar's open. ``bar_time`` itself
        when the timeframe cannot be read (the order has been placed by then)."""
        try:
            step = pd.Timedelta(seconds=timeframe_seconds(self.settings.timeframe))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"fill bar for {bar_time}: timeframe unknown ({exc})")
            return pd.Timestamp(bar_time)
        return pd.Timestamp(bar_time) + step

    def record_exit(self, base: str, fill_price: float, bar_time: pd.Timestamp) -> None:
        """The position in ``base`` was sold; ``bar_time`` is the bar the sale filled
        in (``fill_bar``), from which OVL-COOLDOWN counts."""
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
                logger.warning(
                    f"Ignoring unreadable saved strategy position for {base}"
                )
        overlays = data.get("overlays")
        self._restored_overlays = overlays if isinstance(overlays, dict) else {}
        if self._runner is not None:
            self._runner.import_state(self._restored_overlays)
        self._last_state_json = None
        if self._positions:
            logger.info(
                f"Restored strategy state for {sorted(self._positions)} from {path}"
            )

    def _persist(self) -> None:
        if not self._state_path:
            return
        payload = {
            "positions": {b: p.to_dict() for b, p in self._positions.items()},
            "overlays": (
                self._runner.export_state()
                if self._runner is not None
                else self._restored_overlays
            ),
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

    def decide(
        self, base: str, position: Optional[PositionState] = None
    ) -> Optional[Decision]:
        """
        Decision for the latest closed bar of ``base``'s pair. ``position`` defaults
        to the engine's own record. Returns None when blocked or when the engine is
        not ``catalogue``. Which coins may open a trade is the trader's choice (the
        coins in Settings; in paper mode, the paper-trading coins).
        """
        s = self.settings
        if s.problem:
            self._warn_once(
                "blocked",
                f"Strategy configuration invalid, no signals: {s.problem}",
                error=True,
            )
            return None
        if not s.is_catalogue:
            return None
        pair = market_for(base)

        runner = self._runner_for(s)
        if runner is None:
            return None  # cannot be built: no signals (ERROR logged in _runner_for)
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
                exchange=None,
            )
        exchange = self._sources.get(pair)

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
                exchange=exchange,
            )

        pos = (
            position if position is not None else self._positions.get(str(base).upper())
        )
        window = runner.window(candles, len(candles) - 1)
        needs = runner.context_needs()
        if needs:  # an entry gate's context; other runners are called as before
            context = self._context_for(str(base).upper(), needs, last_open + step, now)
            decision = runner.evaluate(window, pos, str(base).upper(), context)
        else:
            decision = runner.evaluate(window, pos, str(base).upper())
        if pos is not None:
            self._persist()  # the stop / overlay state may have moved
        missed = decision.action is Action.ENTER_LONG and age > ENTRY_WINDOW_S
        if missed:  # too long after the close to fill as a backtest does: no buy
            decision = Decision(
                Action.HOLD,
                f"{ENTRY_MISSED}:{decision.reason}",
                decision.indicators,
                decision.bar_time,
                decision.strategy_id,
            )
        return self._record(
            base,
            decision,
            position=pos,
            log_key=(
                decision.bar_time,
                pos is None,
                ENTRY_MISSED if missed else decision.action,
            ),
            exchange=exchange,
            note=(
                f" missed={age / 60:.0f} min after the bar's close "
                f"(entries within {ENTRY_WINDOW_S // 60} min)"
                if missed
                else ""
            ),
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
        except (CandleDataError, OSError, MarketNotFound) as exc:
            # MarketNotFound: no exchange in Settings lists the coin; it holds
            self._warn_once(
                f"fetch:{pair}", f"Could not fetch {pair} {tf} candles: {exc}"
            )
            return cached[1] if cached is not None else None
        if df is None or df.empty:
            return cached[1] if cached is not None else None
        step = pd.Timedelta(seconds=timeframe_seconds(tf))
        self._candles[pair] = (_frame_key(df, expected_last_open, step, now), df)
        self._sources[pair] = df.attrs.get("exchange")
        return df

    def _context_for(
        self, base: str, needs, decision_close: pd.Timestamp, now: pd.Timestamp
    ) -> Dict[Tuple[str, str], pd.DataFrame]:
        """The bars the overlays' entry gates declared, closed by the decision bar's
        close. A series that cannot be fetched is left out: the gate blocks."""
        frames: Dict[Tuple[str, str], pd.DataFrame] = {}
        for reference, tf, bars in needs:
            coin = base if reference == "self" else reference
            frame = self._context_candles(market_for(coin), tf, int(bars), now)
            if frame is not None:
                frames[(reference, tf)] = frame
        return slice_context(frames, needs, decision_close)

    def _context_candles(
        self, pair: str, tf: str, bars: int, now: pd.Timestamp
    ) -> Optional[pd.DataFrame]:
        """``pair``'s closed ``tf`` bars, fetched once per new bar through the same
        provider and retry rule as the decision's own candles."""
        key = (pair, tf)
        step = pd.Timedelta(seconds=candle_timeframe_seconds(tf))
        expected_last_open = now.floor(step) - step
        cached = self._context.get(key)
        if cached is not None and cached[0] == expected_last_open:
            return cached[1]
        mono = self._clock()
        last_attempt = self._context_attempt.get(key)
        if last_attempt is not None and mono - last_attempt < FETCH_RETRY_SECONDS:
            return cached[1] if cached is not None else None
        self._context_attempt[key] = mono
        try:
            df = self._provider(pair, tf, bars + 5, now)
        except (CandleDataError, OSError, MarketNotFound) as exc:
            # MarketNotFound: no exchange in Settings lists the coin; it holds
            self._warn_once(
                f"fetch:{pair}:{tf}", f"Could not fetch {pair} {tf} candles: {exc}"
            )
            return cached[1] if cached is not None else None
        if df is None or df.empty:
            return cached[1] if cached is not None else None
        df = df[df["open_time"] + step <= now].reset_index(drop=True)
        self._context[key] = (_frame_key(df, expected_last_open, step, now), df)
        return df

    def _record(
        self,
        base: str,
        decision: Decision,
        position,
        log_key: tuple,
        exchange: Optional[str] = None,
        note: str = "",
    ) -> Decision:
        """Keep ``decision`` as ``base``'s last, with ``exchange``, the exchange whose
        bars decided it (None when there were none), and log it, with ``note`` at the
        end, when it is new."""
        base = str(base).upper()
        self.last_decisions[base] = decision
        self.last_exchanges[base] = exchange
        if self._logged.get(base) != log_key:
            self._logged[base] = log_key
            logger.info(
                f"Decision {base}: strategy={decision.strategy_id} action={decision.action.value} "
                f"reason={decision.reason} bar={decision.bar_time} "
                f"exchange={exchange or 'none'} "
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
                + note
            )
        return decision

    def _warn_once(
        self, key: str, message: str, error: bool = False, every: float = 300.0
    ) -> None:
        now = self._clock()
        last = self._warned.get(key)
        if last is None or now - last >= every:
            self._warned[key] = now
            (logger.error if error else logger.warning)(message)
