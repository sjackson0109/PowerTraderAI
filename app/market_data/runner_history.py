"""
Recent candles for the legacy neural runner (pt_thinker), from the exchanges in
Settings: the primary exchange first, then the other enabled exchanges
(``pt_multi_exchange.market_exchanges``; FDS-MX-001 phase C). Public data, no keys.

pt_thinker parses KuCoin-style kline text, so ``history_text`` returns rows
newest first, each ``[open_time_s, open, close, high, low, volume, 0.0]``. Row 1 is
the last closed bar, the one the runner reads. Row 0 stands for the bar still
forming: a flat placeholder at the last close (the runner takes current prices
from the exchanges' quotes, not from candles).

Nothing is written to disk (the trainer owns the candle cache files); results are
kept in memory for up to ``ttl`` seconds, and never past the forming bar's close,
because the runner asks for the same coin and timeframe several times per pass.
``last_source`` says which exchange served each coin and timeframe.

When the bar before the forming one is missing, the coin's market status is asked
(market_data.listing). A market that no longer trades is reported as missing, so
the runner skips the coin; otherwise CandleDataError says the bar has not arrived.
Either way no signals are computed from bars that stopped.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Callable, Dict, Optional, Tuple

from market_data.candles import CandleDataError
from market_data.timeframes import bar_open_floor, candle_timeframe_seconds

# The runner's timeframe names (pt_thinker.tf_choices) -> candle sizes.
RUNNER_TIMEFRAMES = {
    "1hour": "1h",
    "2hour": "2h",
    "4hour": "4h",
    "8hour": "8h",
    "12hour": "12h",
    "1day": "1d",
    "1week": "1w",
}


def candle_interval(timeframe: str) -> str:
    """'1hour' -> '1h'; candle names ('4h', '1w') pass through."""
    tf = timeframe.strip()
    tf = RUNNER_TIMEFRAMES.get(tf, tf)
    candle_timeframe_seconds(tf)  # raises ValueError for an unknown timeframe
    return tf


def _layer_candles(symbol: str, tf: str, start_ms: int, end_ms: int, now_ms: int):
    from pt_multi_exchange import market_exchanges

    return market_exchanges().candles(symbol, tf, start_ms, end_ms, now_ms)


class RecentCandles:
    """The last few candles per (coin, interval), fetched at most once per ``ttl``.

    ``source(symbol, tf, start_ms, end_ms, now_ms)`` returns the exchange layer's
    answer (``Sourced`` closed bars); by default the exchanges in Settings."""

    def __init__(
        self,
        source: Optional[Callable] = None,
        ttl: float = 30.0,
        closed_bars: int = 3,
        clock: Callable[[], float] = time.time,
        listing: Optional[Callable[[str], object]] = None,
    ) -> None:
        self._source = source or _layer_candles
        self._ttl = ttl
        self._closed_bars = closed_bars
        self._clock = clock
        self._listing = listing  # pair -> listing.PairStatus; None: the shared check
        self._cache: Dict[Tuple[str, str], Tuple[float, str]] = {}
        self._lock = threading.Lock()
        self.last_source: Dict[Tuple[str, str], str] = {}  # (symbol, tf) -> exchange

    def history_text(self, coin: str, timeframe: str) -> str:
        from pt_exchange_abstraction import dollar_symbol

        symbol, tf = dollar_symbol(coin), candle_interval(timeframe)
        now = self._clock()
        with self._lock:
            hit = self._cache.get((symbol, tf))
        if hit is not None and now < hit[0]:  # (expiry, text)
            return hit[1]

        step = candle_timeframe_seconds(tf)
        forming_open = bar_open_floor(int(now), tf)
        start = forming_open - self._closed_bars * step
        answer = self._source(
            symbol, tf, start * 1000, (forming_open - step) * 1000, int(now * 1000)
        )  # MarketNotFound passes through: no exchange has the coin

        closed = sorted(
            (
                [
                    int(r[0]) // 1000,
                    float(r[1]),  # open
                    float(r[4]),  # close
                    float(r[2]),  # high
                    float(r[3]),  # low
                    float(r[5]),  # volume
                    0.0,
                ]
                for r in answer.value
            ),
            key=lambda row: row[0],
            reverse=True,
        )
        if not closed or closed[0][0] < forming_open - step:
            # The last closed bar is missing: is the market still trading at all? If
            # not, it is a missing market; otherwise wait for the bar (no signals
            # are computed from bars that stopped arriving).
            from pt_exchange_abstraction import MarketNotFound

            status = self._market_status(symbol)
            if status is not None and status.trading is False:
                raise MarketNotFound(status.describe())
            where = f"{symbol} on {answer.exchange}"
            if not closed:
                raise CandleDataError(f"no closed {tf} candle for {where}")
            raise CandleDataError(
                f"no {tf} candle for {where} since the one opening at {closed[0][0]}"
            )
        last_close = closed[0][2]
        forming = [forming_open, last_close, last_close, last_close, last_close]
        forming += [0.0, 0.0]
        text = json.dumps([forming] + closed)
        # never served past the forming bar's close: row 1 must be the last closed bar
        expiry = min(now + self._ttl, forming_open + step)
        with self._lock:
            self._cache[(symbol, tf)] = (expiry, text)
            self.last_source[(symbol, tf)] = answer.exchange
        return text

    def _market_status(self, symbol: str):
        """The market's status, or None if the check itself failed. The check still
        takes a USDT pair name; FDS-MX-001 phase D moves it onto the exchange
        layer."""
        pair = f"{symbol.split('-')[0]}USDT"
        try:
            if self._listing is not None:
                return self._listing(pair)
            from market_data import listing

            return listing.pair_status(pair)
        except Exception:
            return None


_shared: Optional[RecentCandles] = None


def history_text(coin: str, timeframe: str) -> str:
    """``RecentCandles.history_text`` on one shared instance per process."""
    global _shared
    if _shared is None:
        _shared = RecentCandles()
    return _shared.history_text(coin, timeframe)
