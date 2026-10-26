"""Candles from the exchanges in Settings, cached per exchange (FDS-MX-001 phase E):
the strategies' signal engine and the chart's pattern labels read them.

Everything runs under the isolation guard (app/conftest.py); no network: the
exchanges are fakes behind a real ExchangeManager.
"""

import os
import sys
from datetime import datetime, timezone

import pandas as pd
import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_chart_patterns  # noqa: E402
from market_data import candles  # noqa: E402
from pt_exchange_abstraction import (  # noqa: E402
    ExchangeManager,
    ExchangeType,
    MarketNotFound,
)

# the real one: the isolation guard replaces it in every test
REAL_CLOSED_BARS = pt_chart_patterns.closed_bars

H = 3_600_000
START = datetime(2026, 10, 12, tzinfo=timezone.utc)  # a Monday
START_MS = int(START.timestamp() * 1000)
NOW = pd.Timestamp(START) + pd.Timedelta(hours=48)


class FakeExchange:
    """A connector serving hourly bars from ``rows`` (or raising ``error``)."""

    def __init__(self, name, pair_format="{}-USD", rows=None, error=None, history=None):
        self.name, self.pair_format = name, pair_format
        self.rows = rows if rows is not None else []
        self.error, self.history = error, history
        self.asked = []

    def market_symbol(self, symbol):
        return self.pair_format.format(symbol.split("-")[0])

    def candle_timeframes(self):
        return frozenset({"1h", "1d"})

    def max_history_bars(self, tf):
        return self.history

    def candles(self, symbol, tf, start_ms, end_ms):
        self.asked.append((symbol, tf, start_ms, end_ms))
        if self.error:
            raise self.error
        return [r for r in self.rows if start_ms <= r[0] <= end_ms]


def hours(n, close=100.0):
    return [
        [START_MS + i * H, close, close + 1, close - 1, close + 0.5, 1.0]
        for i in range(n)
    ]


def layer(primary, *exchanges):
    manager = ExchangeManager()
    for exchange in exchanges:
        manager.exchanges[ExchangeType(exchange.name)] = exchange
    manager.primary_exchange = ExchangeType(primary)
    return manager


def read(manager, cache_dir, symbol="BTC", n=10, **kwargs):
    return candles.exchange_candles(
        symbol,
        "1h",
        START,
        pd.Timestamp(START) + pd.Timedelta(hours=n),
        cache_dir=str(cache_dir),
        manager=manager,
        **kwargs,
    )


def test_each_exchange_has_its_own_cache_folder(tmp_path):
    assert candles.cache_path("BTC-USD", "1h", str(tmp_path), "Coinbase") == str(
        tmp_path / "coinbase" / "BTC-USD_1h.csv"
    )
    assert candles.cache_path("BTCUSDT", "1h", str(tmp_path)) == str(
        tmp_path / "BTCUSDT_1h.csv"
    )


def test_the_primary_exchange_serves_the_series_from_its_own_cache(tmp_path):
    coinbase = FakeExchange("coinbase", rows=hours(48))
    kraken = FakeExchange("kraken", pair_format="X{}USD", rows=hours(48))
    manager = layer("coinbase", kraken, coinbase)
    df = read(manager, tmp_path)
    assert (df.attrs["exchange"], df.attrs["pair"]) == ("coinbase", "BTC-USD")
    assert len(df) == 10 and kraken.asked == []
    assert os.path.isfile(
        candles.cache_path("BTC-USD", "1h", str(tmp_path), "coinbase")
    )
    asked = len(coinbase.asked)
    read(manager, tmp_path)  # the cache covers it now: nothing more is fetched
    assert len(coinbase.asked) == asked


def test_without_a_market_on_the_primary_the_next_exchange_serves_it(tmp_path):
    coinbase = FakeExchange("coinbase", error=MarketNotFound("no XMR"))
    kraken = FakeExchange("kraken", pair_format="X{}USD", rows=hours(48))
    df = read(layer("coinbase", coinbase, kraken), tmp_path, symbol="XMRUSDT")
    assert (df.attrs["exchange"], df.attrs["pair"]) == ("kraken", "XXMRUSD")
    assert os.path.isfile(candles.cache_path("XXMRUSD", "1h", str(tmp_path), "kraken"))
    assert not os.path.exists(tmp_path / "coinbase" / "XMR-USD_1h.csv")


def test_a_series_is_only_topped_up_from_the_exchange_it_came_from(tmp_path):
    coinbase = FakeExchange("coinbase", rows=hours(48))
    kraken = FakeExchange("kraken", rows=hours(48, close=200.0))
    manager = layer("coinbase", coinbase, kraken)
    read(manager, tmp_path, n=5)
    longer = read(manager, tmp_path, n=10)
    assert longer["close"].tolist() == [100.5] * 10  # all Coinbase's
    assert kraken.asked == []


def test_offline_the_first_exchange_whose_cache_covers_the_range(tmp_path):
    coinbase = FakeExchange("coinbase", rows=hours(48))
    kucoin = FakeExchange("kucoin", pair_format="{}-USDT", rows=hours(48))
    read(layer("kucoin", coinbase, kucoin), tmp_path)  # fills kucoin's cache
    coinbase.rows = []
    offline = read(layer("coinbase", coinbase, kucoin), tmp_path, offline=True)
    assert offline.attrs["exchange"] == "kucoin"  # coinbase has no cache for it
    assert coinbase.asked == []  # and nothing is fetched offline


def test_no_market_anywhere_and_other_failures(tmp_path):
    gone = MarketNotFound("no market")
    manager = layer(
        "coinbase",
        FakeExchange("coinbase", error=gone),
        FakeExchange("kraken", error=gone),
    )
    with pytest.raises(MarketNotFound):
        read(manager, tmp_path, symbol="NOPE")
    manager = layer(
        "coinbase",
        FakeExchange("coinbase", error=gone),
        FakeExchange("kraken", error=TimeoutError("slow")),
    )
    with pytest.raises(candles.CandleDataError) as caught:
        read(manager, tmp_path, symbol="NOPE")
    assert "coinbase: no market" in str(caught.value)
    assert "kraken" in str(caught.value)


def test_the_signal_engine_reads_the_exchanges_in_settings(monkeypatch):
    import signal_engine

    asked = []

    def fake(symbol, tf, start, end, closed_only=True):
        asked.append((symbol, tf, start, end, closed_only))
        return pd.DataFrame()

    monkeypatch.setattr(signal_engine, "exchange_candles", fake)
    signal_engine.default_candle_provider("BTC-USD", "1h", 3, NOW)
    assert asked == [("BTC-USD", "1h", NOW - pd.Timedelta(hours=3), NOW, True)]
    assert signal_engine.market_for("btc") == "BTC-USD"


def test_the_chart_labels_read_the_exchanges_in_settings(monkeypatch):
    frame = candles._frame_from_klines(hours(3))
    monkeypatch.setattr(candles, "exchange_candles", lambda *a, **k: frame)
    bars = REAL_CLOSED_BARS("BTC", "1h", START_MS // 1000, START_MS // 1000 + 7200)
    assert [b.ts for b in bars] == [START_MS // 1000 + i * 3600 for i in range(3)]
