"""The hub chart's candles come from the exchanges in Settings, primary first
(FDS-MX-001 phase G), with the bar still forming, and the chart says which exchange
and market they came from.

Everything runs under the isolation guard (app/conftest.py); no network.
"""

import os
import sys

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_hub  # noqa: E402
from pt_exchange_abstraction import (  # noqa: E402
    ExchangeManager,
    ExchangeType,
    MarketNotFound,
)

H = 3_600_000


class Connector:
    def __init__(self, rows=None, error=None, pair_format="{}-USD"):
        self.rows, self.error, self.pair_format = rows or [], error, pair_format
        self.asked = []

    def market_symbol(self, symbol):
        return self.pair_format.format(symbol.split("-")[0])

    def candle_timeframes(self):
        return frozenset({"1h", "1d"})

    def max_history_bars(self, tf):
        return None

    def candles(self, symbol, tf, start_ms, end_ms):
        self.asked.append((symbol, tf))
        if self.error:
            raise self.error
        return [r for r in self.rows if start_ms <= r[0] <= end_ms]


def layer(primary, **connectors):
    manager = ExchangeManager()
    for name, connector in connectors.items():
        manager.exchanges[ExchangeType(name)] = connector
    manager.primary_exchange = ExchangeType(primary)
    return manager


def hours_until_now(n):
    import time

    forming = int(time.time() * 1000) // H * H
    return [[forming - i * H, 1.0 + i, 2.0 + i, 0.5, 1.5 + i, 1.0] for i in range(n)][
        ::-1
    ]


def test_the_chart_reads_the_primary_exchange_with_the_forming_bar():
    rows = hours_until_now(5)
    fetcher = pt_hub.CandleFetcher(
        manager=layer("coinbase", coinbase=Connector(rows), kraken=Connector(rows))
    )
    candles = fetcher.get_klines("btc", "1hour", limit=3)
    assert [c["ts"] for c in candles] == [r[0] // 1000 for r in rows[-3:]]
    assert candles[-1]["ts"] == rows[-1][0] // 1000  # the bar still forming
    assert fetcher.last_source[("BTC", "1hour")] == "coinbase BTC-USD"


def test_without_a_market_on_the_primary_the_next_exchange_draws_the_chart():
    rows = hours_until_now(5)
    kraken = Connector(rows, pair_format="X{}USD")
    fetcher = pt_hub.CandleFetcher(
        manager=layer(
            "coinbase",
            coinbase=Connector(error=MarketNotFound("no XMR")),
            kraken=kraken,
        )
    )
    assert len(fetcher.get_klines("XMR", "1hour", limit=5)) == 5
    assert fetcher.last_source[("XMR", "1hour")] == "kraken XXMRUSD"


def test_no_exchange_with_the_coin_is_an_empty_chart_not_a_crash():
    gone = Connector(error=MarketNotFound("no market"))
    fetcher = pt_hub.CandleFetcher(manager=layer("coinbase", coinbase=gone))
    assert fetcher.get_klines("NOPE", "1hour") == []
    assert fetcher.get_klines("BTC", "7min") == []  # a size the chart has no name for


def test_candles_are_reused_for_ten_seconds():
    connector = Connector(hours_until_now(3))
    fetcher = pt_hub.CandleFetcher(manager=layer("coinbase", coinbase=connector))
    fetcher.get_klines("BTC", "1hour", limit=3)
    fetcher.get_klines("BTC", "1hour", limit=3)
    assert len(connector.asked) == 1
