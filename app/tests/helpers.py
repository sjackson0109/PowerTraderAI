"""Shared test helpers: fake exchange-layer quotes and minimum orders, and a
paper-trader harness.

Nothing here (or in any test using it) touches the network: the exchange layer's
quotes (``trading_mode._layer_quote``) and the trader's exchanges in Settings
(``pt_trader._market_exchanges``) are replaced for the duration of every test.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from typing import List, Optional
from unittest import mock

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pandas as pd  # noqa: E402

import trading_mode as tm  # noqa: E402
from pt_exchange_abstraction import PriceQuote, Sourced  # noqa: E402


def make_candles(closes, start="2026-01-01", tf_seconds=3600, opens=None, wick=0.001):
    """Deterministic SYNTHETIC candles for logic tests (never used to judge performance).

    open = previous close (or ``opens``), high/low = body +/- ``wick`` (relative).
    """
    import pandas as pd

    closes = [float(c) for c in closes]
    if opens is None:
        opens = [closes[0]] + closes[:-1]
    rows = []
    for i, (o, c) in enumerate(zip(opens, closes)):
        rows.append(
            {
                "open_time": pd.Timestamp(start, tz="UTC")
                + pd.Timedelta(seconds=tf_seconds * i),
                "open": float(o),
                "high": max(o, c) * (1 + wick),
                "low": min(o, c) * (1 - wick),
                "close": c,
                "volume": 100.0,
            }
        )
    return pd.DataFrame(rows)


HOUR = pd.Timedelta(hours=1)


class Feed:
    """A controllable clock plus a candle provider that only reveals closed bars."""

    def __init__(self, frame):
        self.frame = frame
        self.now = 0.0
        self.calls = 0
        self.fail = None

    def set_after_bar(self, k, seconds_after_close=10):
        close = self.frame["open_time"].iloc[k] + HOUR
        self.now = close.timestamp() + seconds_after_close

    def clock(self):
        return self.now

    def provider(self, symbol, tf, n, now):
        self.calls += 1
        if self.fail:
            raise self.fail
        closed = self.frame[self.frame["open_time"] + HOUR <= now]
        return closed.tail(n).reset_index(drop=True)


class FakeQuotes:
    """Stands in for the exchange layer's quotes (``trading_mode._layer_quote``):
    the exchanges in Settings, primary first. It answers as ``exchange`` with the
    pair ``<COIN>-USD``, and records every coin it was asked about.
    """

    def __init__(self) -> None:
        self.asked: List[str] = []
        self.bid = 99.0
        self.ask = 101.0
        self.reachable = True  # False: no exchange gives a quote
        self.age_s = 0.0  # the exchange's time for the quote = now - age_s
        self.send_date = True  # False: the exchange gives no time for the quote
        self.exchange = "coinbase"

    def layer_quote(self, base: str) -> Optional[Sourced]:
        self.asked.append(base)
        if not self.reachable:
            return None
        quote_ts = time.time() - self.age_s if self.send_date else None
        return Sourced(
            PriceQuote(self.bid, self.ask, quote_ts),
            exchange=self.exchange,
            pair=f"{base}-USD",
            primary=True,
        )


class FakeMarkets:
    """Stands in for the trader's exchanges in Settings (pt_trader._market_exchanges),
    so no trader test reaches a real exchange. States no minimum order unless a test
    sets ``minimum``; records the symbols it was asked about."""

    def __init__(self) -> None:
        self.minimum: Optional[float] = None
        self.asked: List[str] = []

    def min_order_usd(self, symbol: str) -> Optional[float]:
        self.asked.append(symbol)
        return self.minimum


class PaperTraderCase(unittest.TestCase):
    """A paper trader in a temp dir with fake exchange-layer quotes (FakeQuotes),
    fake exchanges in Settings (FakeMarkets) and no real network."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("POWERTRADER_ENV", "test")
        import pt_trader

        cls.pt_trader = pt_trader

    def setUp(self):
        tm.reset_paper_exchange()
        tm._quote_cache.clear()
        self.addCleanup(tm.reset_paper_exchange)
        self.addCleanup(tm._quote_cache.clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.quotes = FakeQuotes()
        self.markets = FakeMarkets()
        for p in (
            mock.patch.object(self.pt_trader, "HUB_DATA_DIR", self.tmp.name),
            mock.patch.object(tm, "_layer_quote", self.quotes.layer_quote),
            mock.patch.object(
                self.pt_trader, "_market_exchanges", lambda: self.markets
            ),
        ):
            p.start()
            self.addCleanup(p.stop)

        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)  # the trader drops <SYM>_current_price.txt in cwd
        self.addCleanup(os.chdir, self.cwd)

    def trader(self, settings: Optional[dict] = None, candle_provider=None):
        """A trader whose signal engine never touches the network: by default it
        has no candles (so the strategy sits on HOLD)."""
        import pandas as pd
        from signal_engine import SignalEngine

        settings = settings if settings is not None else {"trading": {"mode": "paper"}}
        engine = SignalEngine(
            settings_source=settings,
            candle_provider=candle_provider or (lambda *a, **k: pd.DataFrame()),
        )
        t = self.pt_trader.CryptoAPITrading(
            settings_source=settings, signal_engine=engine
        )
        t._order_poll_seconds = 0.0
        return t

    def ledger_rows(self, subdir: str = "paper") -> List[dict]:
        path = os.path.join(self.tmp.name, subdir, "trade_history.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
