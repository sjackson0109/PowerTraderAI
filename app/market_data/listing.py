"""
Is a coin's market still trading?

The trainer and the runner take their candles from the exchanges in Settings, so a
coin whose market has stopped has no new bars. Its signals would be stale and its
model would describe a market that is gone. This module asks the exchange layer for
the market's status (``market_status``: the primary exchange, unless it does not
list the coin; FDS-MX-001 phase D):

- trading: the market is open;
- any other status the exchange reports (``BREAK``, ``delisted``, ``cancel_only``,
  ...): it is not trading;
- ``NOT_LISTED``: no exchange in Settings has a market for the coin.

A failed request gives an unknown status (``None``). Callers treat unknown as "no
verdict", never as "not trading", and fall back on their own checks (a coin with no
recent bars still gets no signals).

The verdict for each coin is also kept in ``market_status.json`` in the coin's folder.
The trainer and the runner write it, and the trader reads it, so a coin that is not
trading gets no buys even while no runner is running.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

TRADING = "TRADING"
NOT_LISTED = "NOT_LISTED"
MARKET_STATUS_FILE = "market_status.json"


@dataclass(frozen=True)
class PairStatus:
    pair: str  # the coin's market as asked about, e.g. "BTC-USD"
    status: Optional[str]  # the exchange's own word, NOT_LISTED, or None when unknown
    detail: str = ""
    exchange: str = ""  # the exchange that answered
    is_trading: Optional[bool] = None  # its verdict; None: TRADING means trading

    @property
    def trading(self) -> Optional[bool]:
        """True or False when an exchange answered; None when the status is unknown."""
        if self.status is None:
            return None
        if self.status == NOT_LISTED:
            return False
        if self.is_trading is not None:
            return self.is_trading
        return self.status == TRADING

    def describe(self) -> str:
        where = f" on {self.exchange}" if self.exchange else ""
        if self.status is None:
            return f"status of {self.pair} unknown ({self.detail})"
        if self.status == NOT_LISTED:
            return f"no exchange in Settings has a market for {self.pair}"
        if self.trading:
            return f"{self.pair}{where} is trading"
        return f"{self.pair}{where} is {self.status}, not trading"


def _layer_status(symbol: str):
    from pt_multi_exchange import market_exchanges

    return market_exchanges().market_status(symbol)


class ListingChecker:
    """Cached status lookups: a known status is kept for ``ttl`` seconds, an unknown
    one for ``retry_ttl`` seconds. ``source(symbol)`` is the exchange layer's answer
    (a ``Sourced`` ``MarketStatus``, or None); by default the exchanges in Settings."""

    def __init__(
        self,
        source: Optional[Callable] = None,
        clock: Callable[[], float] = time.time,
        ttl: float = 3600.0,
        retry_ttl: float = 300.0,
    ) -> None:
        self._source = source or _layer_status
        self._clock = clock
        self._ttl = ttl
        self._retry_ttl = retry_ttl
        self._cache: Dict[str, Tuple[float, PairStatus]] = {}
        self._lock = threading.Lock()

    def status(self, pair: str) -> PairStatus:
        from pt_exchange_abstraction import dollar_symbol

        symbol = dollar_symbol(pair)
        now = self._clock()
        with self._lock:
            hit = self._cache.get(symbol)
        if hit is not None and now < hit[0]:
            return hit[1]
        result = self._fetch(symbol)
        ttl = self._retry_ttl if result.status is None else self._ttl
        with self._lock:
            self._cache[symbol] = (now + ttl, result)
        return result

    def _fetch(self, symbol: str) -> PairStatus:
        try:
            answer = self._source(symbol)
        except Exception as exc:
            return PairStatus(symbol, None, str(exc) or type(exc).__name__)
        if answer is None:
            return PairStatus(symbol, None, "no exchange in Settings could say")
        market = answer.value
        if not market.listed:
            return PairStatus(symbol, NOT_LISTED, market.reason, answer.exchange)
        if market.trading is None:
            detail = market.reason or "an unclear answer"
            return PairStatus(symbol, None, detail, answer.exchange)
        word = market.status or ("trading" if market.trading else "not trading")
        return PairStatus(
            symbol, word, market.reason, answer.exchange, bool(market.trading)
        )


_shared: Optional[ListingChecker] = None
_shared_lock = threading.Lock()


def pair_status(pair: str) -> PairStatus:
    """The shared, cached status of a coin's market (``HYPE``, ``HYPE-USD`` or
    ``HYPEUSDT``)."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = ListingChecker()
        checker = _shared
    return checker.status(pair)


# --- the per-coin verdict file -----------------------------------------------------


def write_market_status(
    folder: str, pair: str, trading: bool, reason: str, exchange: str = ""
) -> bool:
    """Record whether the coin's market is trading, in ``folder``, and which exchange
    said so (when known). Returns whether the record was written; never raises. On
    Windows the replace fails while another process has the file open (the trader
    reads it every pass), so it is retried briefly, as the runner's signal files
    are."""
    record = {
        "pair": str(pair).upper(),
        "trading": bool(trading),
        "reason": str(reason),
        "exchange": str(exchange),
        "checked_at": int(time.time()),
    }
    path = os.path.join(folder, MARKET_STATUS_FILE)
    tmp = f"{path}.writing"
    try:
        os.makedirs(folder, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(record, f)
    except Exception:
        return False
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            time.sleep(0.1)
        except Exception:
            break
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False


def read_market_status(folder: str) -> Optional[dict]:
    """The recorded verdict, or None if there is none (or it is unreadable)."""
    try:
        with open(os.path.join(folder, MARKET_STATUS_FILE), encoding="utf-8") as f:
            record = json.load(f)
        return record if isinstance(record, dict) and "trading" in record else None
    except Exception:
        return None


def not_trading_reason(folder: str) -> Optional[str]:
    """Why the coin in ``folder`` must not be traded, or None if nothing says so."""
    record = read_market_status(folder)
    if record is None or record.get("trading") is not False:
        return None
    return str(record.get("reason") or "its market is not trading")
