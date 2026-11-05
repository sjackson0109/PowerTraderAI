"""24-hour tickers and order books through the exchange layer (the Market Data tab):
last price, bid, ask, and the last 24 hours' volume, high, low and change, from each
exchange's own 24-hour ticker; the change from the candle cache where the exchange's
ticker has none. A value the exchange does not give is None, never 0. Order books:
each exchange's public book, best price first.

The payloads follow each exchange's public API documentation (Coinbase Exchange
products ticker and stats, Coinbase Advanced Trade public product book, Binance spot
ticker/24hr and depth, Kraken Ticker and Depth, KuCoin market stats and part order
book); none was checked against the live exchanges here. No test touches
the network; everything runs under the isolation guard (app/conftest.py).
"""

import os
import sys
from datetime import datetime, timezone

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_exchanges  # noqa: E402
from pt_exchange_abstraction import (  # noqa: E402
    DAY_SECONDS,
    ExchangeManager,
    ExchangeType,
    MarketDataUnavailable,
    MarketNotFound,
    OrderBookSnapshot,
    PriceQuote,
    Ticker,
)
from market_data.timeframes import bar_open_floor  # noqa: E402

DATE = {"Date": "Sun, 25 Oct 2026 23:08:46 GMT"}
DATE_TS = datetime(2026, 10, 25, 23, 8, 46, tzinfo=timezone.utc).timestamp()


class _Response:
    def __init__(self, payload, status=200, headers=None):
        self._payload = payload
        self.status_code = status
        self.headers = headers or {}

    def json(self):
        return self._payload


class Routes:
    """A fake requests.get: the first route whose text is in the URL answers."""

    def __init__(self, **routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        for text, answer in self.routes.items():
            if text.replace("__", "/") in url:
                return answer(params or {}) if callable(answer) else answer
        raise AssertionError(f"unexpected request {url}")


@pytest.fixture
def get(monkeypatch):
    def install(**routes):
        fake = Routes(**routes)
        monkeypatch.setattr(pt_exchanges.requests, "get", fake)
        return fake

    return install


def connector(name):
    return getattr(pt_exchanges, name)("", "")


# --- the connectors --------------------------------------------------------------------


COINBASE_TICKER = {
    "ask": "6267.71",
    "bid": "6265.15",
    "volume": "53602.03940154",
    "trade_id": 86326522,
    "price": "6268.48",
    "size": "0.00698254",
    "time": "2020-03-20T00:22:57.833Z",
}
COINBASE_STATS = {
    "open": "6745.61000000",
    "high": "7292.11000000",
    "low": "6650.00000000",
    "volume": "26185.51325269",
    "last": "6813.19000000",
    "volume_30day": "1019451.11188405",
}


def test_coinbase_ticker_takes_the_change_from_its_24_hour_stats(get):
    fake = get(
        ticker=_Response(COINBASE_TICKER, headers=DATE),
        stats=_Response(COINBASE_STATS),
    )
    ticker = connector("CoinbaseExchange").ticker("BTCUSDT")
    assert (ticker.last, ticker.bid, ticker.ask) == (6268.48, 6265.15, 6267.71)
    assert ticker.volume_24h == 53602.03940154
    assert (ticker.high_24h, ticker.low_24h) == (7292.11, 6650.0)
    assert ticker.change_24h == pytest.approx(6268.48 - 6745.61)
    assert ticker.change_24h_pct == pytest.approx((6268.48 - 6745.61) / 6745.61 * 100)
    assert ticker.ticker_ts == DATE_TS
    assert [url.rsplit("/", 2)[-2:] for url, _ in fake.calls] == [
        ["BTC-USD", "ticker"],
        ["BTC-USD", "stats"],
    ]


def test_coinbase_asks_for_the_stats_at_most_every_30_seconds(get, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(pt_exchanges.time, "monotonic", lambda: clock[0])
    fake = get(ticker=_Response(COINBASE_TICKER), stats=_Response(COINBASE_STATS))
    coinbase = connector("CoinbaseExchange")
    coinbase.ticker("BTC-USD")
    clock[0] += 29
    assert coinbase.ticker("BTC-USD").change_24h is not None
    assert sum("stats" in url for url, _ in fake.calls) == 1
    clock[0] += 2
    coinbase.ticker("BTC-USD")
    assert sum("stats" in url for url, _ in fake.calls) == 2


def test_coinbase_without_its_stats_leaves_the_24_hour_fields_out(get):
    get(ticker=_Response(COINBASE_TICKER), stats=_Response({"message": "NotFound"}))
    ticker = connector("CoinbaseExchange").ticker("BTC-USD")
    assert ticker.volume_24h == 53602.03940154  # the ticker's own
    assert (ticker.high_24h, ticker.low_24h, ticker.change_24h) == (None, None, None)
    get(ticker=_Response({"message": "NotFound"}, 404))
    with pytest.raises(MarketNotFound):
        connector("CoinbaseExchange").ticker("NOPE-USD")


BINANCE_24HR = {
    "symbol": "BTCUSDT",
    "priceChange": "-94.99999800",
    "priceChangePercent": "-95.960",
    "weightedAvgPrice": "0.29628482",
    "prevClosePrice": "0.10002000",
    "lastPrice": "4.00000200",
    "lastQty": "200.00000000",
    "bidPrice": "4.00000000",
    "bidQty": "100.00000000",
    "askPrice": "4.00000200",
    "askQty": "100.00000000",
    "openPrice": "99.00000000",
    "highPrice": "100.00000000",
    "lowPrice": "0.10000000",
    "volume": "8913.30000000",
    "quoteVolume": "15.30000000",
    "openTime": 1499783499040,
    "closeTime": 1499869899040,
    "firstId": 28385,
    "lastId": 28460,
    "count": 76,
}


def test_binance_ticker_is_its_rolling_24_hour_ticker(get):
    fake = get(ticker__24hr=_Response(BINANCE_24HR, headers=DATE))
    ticker = connector("BinanceExchange").ticker("BTC-USD")
    assert fake.calls[0][1] == {"symbol": "BTCUSDT"}
    assert ticker == Ticker(
        last=4.000002,
        bid=4.0,
        ask=4.000002,
        volume_24h=8913.3,
        high_24h=100.0,
        low_24h=0.1,
        change_24h=-94.999998,
        change_24h_pct=-95.96,  # already in percent
        ticker_ts=DATE_TS,
    )
    get(ticker__24hr=_Response({"code": -1121, "msg": "Invalid symbol."}, 400))
    with pytest.raises(MarketNotFound):
        connector("BinanceExchange").ticker("NOPE-USD")


KRAKEN_TICKER = {
    "error": [],
    "result": {
        "XXBTZUSD": {
            "a": ["30300.10000", "1", "1.000"],
            "b": ["30300.00000", "1", "1.000"],
            "c": ["30303.20000", "0.00067643"],
            "v": ["4083.67001100", "4412.73601799"],
            "p": ["30706.77771", "30689.13205"],
            "t": [34619, 38907],
            "l": ["29868.30000", "29868.30000"],
            "h": ["31631.00000", "31631.00000"],
            "o": "30502.80000",
        }
    },
}


def test_kraken_ticker_gives_the_last_24_hours_but_no_change(get):
    fake = get(Ticker=_Response(KRAKEN_TICKER))
    ticker = connector("KrakenExchange").ticker("BTC-USD")
    assert fake.calls[0][1] == {"pair": "XBTUSD"}
    assert (ticker.last, ticker.bid, ticker.ask) == (30303.2, 30300.0, 30300.1)
    assert ticker.volume_24h == 4412.73601799  # the last 24 hours, not today's
    assert (ticker.high_24h, ticker.low_24h) == (31631.0, 29868.3)
    # its "o" is today's open (00:00 UTC), not the price 24 hours ago
    assert (ticker.change_24h, ticker.change_24h_pct) == (None, None)
    get(Ticker=_Response({"error": ["EQuery:Unknown asset pair"]}))
    with pytest.raises(MarketNotFound):
        connector("KrakenExchange").ticker("NOPE-USD")


KUCOIN_STATS = {
    "code": "200000",
    "data": {
        "time": 1602832092060,
        "symbol": "BTC-USDT",
        "buy": "11328.9",
        "sell": "11329",
        "changeRate": "-0.0055",
        "changePrice": "-63.6",
        "high": "11610",
        "low": "11200",
        "vol": "2282.70993217",
        "volValue": "25984946.157790431",
        "last": "11328.9",
        "averagePrice": "11360.66065903",
        "takerFeeRate": "0.001",
        "makerFeeRate": "0.001",
        "takerCoefficient": "1",
        "makerCoefficient": "1",
    },
}


def test_kucoin_ticker_change_rate_is_a_fraction(get):
    fake = get(market__stats=_Response(KUCOIN_STATS))
    ticker = connector("KuCoinExchange").ticker("BTC-USD")
    assert fake.calls[0][1] == {"symbol": "BTC-USDT"}
    assert (ticker.last, ticker.bid, ticker.ask) == (11328.9, 11328.9, 11329.0)
    assert (ticker.volume_24h, ticker.high_24h, ticker.low_24h) == (
        2282.70993217,
        11610.0,
        11200.0,
    )
    assert ticker.change_24h == -63.6
    assert ticker.change_24h_pct == pytest.approx(-0.55)
    assert ticker.ticker_ts == 1602832092.06  # no Date header: the stats' own time
    get(market__stats=_Response({"code": "900001", "msg": "symbol not exists"}))
    with pytest.raises(MarketNotFound):
        connector("KuCoinExchange").ticker("NOPE-USD")


def test_an_exchange_that_cannot_be_asked_raises_for_the_feed_to_count(monkeypatch):
    def down(*args, **kwargs):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(pt_exchanges.requests, "get", down)
    for name in (
        "BinanceExchange",
        "CoinbaseExchange",
        "KrakenExchange",
        "KuCoinExchange",
    ):
        with pytest.raises(ConnectionError):
            connector(name).ticker("BTC-USD")


def test_a_connector_without_a_ticker_gives_its_quote_alone(monkeypatch):
    class QuoteOnly(pt_exchanges.RobinhoodExchange):
        def quote(self, symbol):
            return PriceQuote(99.0, 101.0, 5.0)

    ticker = QuoteOnly("", "").ticker("BTC-USD")
    assert ticker == Ticker(None, 99.0, 101.0, ticker_ts=5.0)
    assert ticker.price == 100.0  # no last trade: the middle of bid and ask
    assert connector("RobinhoodExchange").ticker("BTC-USD") is None  # no quote


# --- order books ------------------------------------------------------------------------


def test_coinbase_order_book_is_its_public_product_book(get):
    fake = get(
        product_book=_Response(
            {
                "pricebook": {
                    "product_id": "BTC-USD",
                    "bids": [
                        {"price": "100.4", "size": "1.5"},
                        {"price": "100.5", "size": "2"},
                    ],
                    "asks": [
                        {"price": "100.7", "size": "3"},
                        {"price": "100.6", "size": "0.5"},
                    ],
                    "time": "2026-10-25T23:08:46Z",
                },
                "last": "100.55",
                "mid_market": "100.55",
                "spread_bps": "9.94",
                "spread_absolute": "0.1",
            }
        )
    )
    book = connector("CoinbaseExchange").order_book("BTCUSDT", 2)
    url, params = fake.calls[0]
    assert url == "https://api.coinbase.com/api/v3/brokerage/market/product_book"
    assert params == {"product_id": "BTC-USD", "limit": 2}
    assert book == OrderBookSnapshot(
        [(100.5, 2.0), (100.4, 1.5)], [(100.6, 0.5), (100.7, 3.0)], DATE_TS
    )
    get(
        product_book=_Response(
            {"error": "NOT_FOUND", "message": "ProductID is invalid"}, 404
        )
    )
    with pytest.raises(MarketNotFound):
        connector("CoinbaseExchange").order_book("NOPE-USD")


def test_binance_order_book_asks_for_a_documented_limit(get):
    fake = get(
        depth=_Response(
            {
                "lastUpdateId": 1027024,
                "bids": [["4.00000000", "431.00000000"], ["3.9", "0.00000000"]],
                "asks": [["4.00000200", "12.00000000"]],
            },
            headers=DATE,
        )
    )
    book = connector("BinanceExchange").order_book("BTC-USD", 25)
    assert fake.calls[0][1] == {"symbol": "BTCUSDT", "limit": 50}
    # a level with no quantity left is not a level
    assert book == OrderBookSnapshot([(4.0, 431.0)], [(4.000002, 12.0)], DATE_TS)
    get(depth=_Response({"code": -1121, "msg": "Invalid symbol."}, 400))
    with pytest.raises(MarketNotFound):
        connector("BinanceExchange").order_book("NOPE-USD")


def test_kraken_order_book_is_its_depth(get):
    fake = get(
        Depth=_Response(
            {
                "error": [],
                "result": {
                    "XXBTZUSD": {
                        "asks": [
                            ["30384.10000", "2.059", 1688671659],
                            ["30387.90000", "1.500", 1688671380],
                        ],
                        "bids": [
                            ["30297.00000", "1.115", 1688671636],
                            ["30296.70000", "2.002", 1688671674],
                        ],
                    }
                },
            }
        )
    )
    book = connector("KrakenExchange").order_book("BTC-USD", 2)
    assert fake.calls[0][1] == {"pair": "XBTUSD", "count": 2}
    assert book.bids == [(30297.0, 1.115), (30296.7, 2.002)]
    assert book.asks == [(30384.1, 2.059), (30387.9, 1.5)]
    get(Depth=_Response({"error": ["EQuery:Unknown asset pair"]}))
    with pytest.raises(MarketNotFound):
        connector("KrakenExchange").order_book("NOPE-USD")


def test_kucoin_order_book_is_its_part_order_book(get):
    data = {
        "code": "200000",
        "data": {
            "time": 1729176273859,
            "sequence": "14610502970",
            "bids": [["66976.4", "0.69109872"], ["66976.3", "0.14377"]],
            "asks": [["66976.5", "0.23432758"], ["66976.6", "0.0111"]],
        },
    }
    fake = get(level2_20=_Response(data), level2_100=_Response(data))
    book = connector("KuCoinExchange").order_book("BTC-USD", 20)
    assert "level2_20" in fake.calls[0][0] and fake.calls[0][1] == {
        "symbol": "BTC-USDT"
    }
    assert book.bids[0] == (66976.4, 0.69109872) and book.asks[0] == (
        66976.5,
        0.23432758,
    )
    assert book.book_ts == 1729176273.859
    connector("KuCoinExchange").order_book("BTC-USD", 50)
    assert "level2_100" in fake.calls[1][0]


def test_the_order_book_comes_from_the_primary_else_the_next():
    class Booked(FakeExchange):
        def __init__(self, name, book=None, error=None):
            super().__init__(name, error=error)
            self.book = book

        def order_book(self, symbol, depth=20):
            self.asked.append(("book", symbol, depth))
            if self.error:
                raise self.error
            return self.book

    book = OrderBookSnapshot([(99.0, 1.0)], [(101.0, 2.0)])
    coinbase = Booked("coinbase", error=MarketNotFound("no XMR-USD"))
    kraken = Booked("kraken", book)
    manager = layer("coinbase", coinbase, kraken)
    answer = manager.order_book("XMR", 10)
    assert (answer.exchange, answer.value) == ("kraken", book)
    assert kraken.asked == [("book", "XMR-USD", 10)]
    with pytest.raises(MarketNotFound):
        manager.order_book("XMR", only="coinbase")
    none = Booked("kraken", None)  # a connector that reads no order book
    with pytest.raises(MarketDataUnavailable, match="reads no order book"):
        layer("kraken", none).order_book("BTC")


# --- the layer: primary first; the change from the candle cache ------------------------

NOW = int(datetime(2026, 10, 22, 12, 2, tzinfo=timezone.utc).timestamp())
DAY_AGO_OPEN = bar_open_floor(NOW - DAY_SECONDS, "5m")


class FakeExchange:
    """A connector: its ticker, and 5-minute bars for the candle cache."""

    def __init__(self, name, ticker=None, error=None, bars=()):
        self.name = name
        self.value = ticker
        self.error = error
        self.bars = list(bars)
        self.asked = []

    def market_symbol(self, symbol):
        return symbol

    def ticker(self, symbol):
        self.asked.append(("ticker", symbol))
        if self.error:
            raise self.error
        return self.value

    def candle_timeframes(self):
        return frozenset({"5m"})

    def max_history_bars(self, tf):
        return None

    def candles(self, symbol, tf, start_ms, end_ms):
        self.asked.append(("candles", symbol, tf, start_ms, end_ms))
        return [b for b in self.bars if start_ms <= b[0] <= end_ms]


def layer(primary, *exchanges):
    manager = ExchangeManager()
    for exchange in exchanges:
        manager.exchanges[ExchangeType(exchange.name)] = exchange
    manager.primary_exchange = ExchangeType(primary)
    return manager


def test_the_ticker_comes_from_the_primary_else_the_next():
    coinbase = FakeExchange("coinbase", error=ConnectionError("down"))
    kraken = FakeExchange("kraken", Ticker(101.0, 100.0, 102.0, change_24h=1.0))
    manager = layer("coinbase", kraken, coinbase)
    answer = manager.ticker("BTCUSDT", now=NOW)
    assert (answer.exchange, answer.pair, answer.primary) == (
        "kraken",
        "BTC-USD",
        False,
    )
    assert answer.value.last == 101.0
    with pytest.raises(MarketDataUnavailable, match="coinbase: ConnectionError: down"):
        manager.ticker("BTC", only="coinbase", now=NOW)
    assert manager.ticker("BTC", only="kraken", now=NOW).exchange == "kraken"


def test_no_market_anywhere_is_market_not_found():
    coinbase = FakeExchange("coinbase", error=MarketNotFound("no XMR-USD"))
    kraken = FakeExchange("kraken", error=MarketNotFound("no XMRUSD"))
    with pytest.raises(MarketNotFound):
        layer("coinbase", coinbase, kraken).ticker("XMR", now=NOW)
    nothing = FakeExchange("kraken", None)  # a connector with no ticker at all
    with pytest.raises(MarketDataUnavailable, match="kraken: no ticker"):
        layer("kraken", nothing).ticker("XMR", now=NOW)


def test_a_ticker_without_the_change_gets_it_from_the_candle_cache():
    """The bar holding the moment 24 hours ago: its open is the price then."""
    bar = [DAY_AGO_OPEN * 1000, 80.0, 82.0, 79.0, 81.0, 5.0]
    kraken = FakeExchange(
        "kraken", Ticker(100.0, 99.5, 100.5, volume_24h=12.0), bars=[bar]
    )
    manager = layer("kraken", kraken)
    ticker = manager.ticker("BTC", now=NOW).value
    assert ticker.change_24h == pytest.approx(20.0)
    assert ticker.change_24h_pct == pytest.approx(25.0)
    assert ticker.volume_24h == 12.0
    fetched = [a for a in kraken.asked if a[0] == "candles"]
    assert fetched and fetched[0][2] == "5m"
    # within the same bar it is not looked up again
    kraken.value = Ticker(110.0, 109.5, 110.5)
    assert manager.ticker("BTC", now=NOW + 60).value.change_24h == pytest.approx(30.0)
    assert len([a for a in kraken.asked if a[0] == "candles"]) == len(fetched)


def test_without_that_bar_the_change_stays_none():
    kraken = FakeExchange("kraken", Ticker(100.0, 99.5, 100.5), bars=[])
    ticker = layer("kraken", kraken).ticker("BTC", now=NOW).value
    assert (ticker.change_24h, ticker.change_24h_pct) == (None, None)


def test_the_multi_exchange_manager_needs_connecting_first():
    from pt_multi_exchange import MultiExchangeManager

    multi = MultiExchangeManager.__new__(MultiExchangeManager)  # no config file
    multi.exchange_manager = layer(
        "coinbase", FakeExchange("coinbase", Ticker(1.0, 1.0, 1.0, change_24h=0.0))
    )
    multi.initialized = False
    with pytest.raises(RuntimeError):
        multi.ticker("BTC")
    multi.initialized = True
    assert multi.ticker("BTC").exchange == "coinbase"
