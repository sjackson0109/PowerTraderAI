"""Market data through the exchange layer (FDS-MX-001 phase A): candles, market
status and quotes from Binance, Coinbase, Kraken and KuCoin, the primary exchange
first, and candle sizes an exchange does not serve built from smaller ones.

The payload shapes are the exchanges' public answers, checked on 2026-10-25. No test
touches the network; everything runs under the isolation guard (app/conftest.py).
"""

import os
import sys
from datetime import datetime, timezone
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_exchanges  # noqa: E402
from market_data.resample import build_candles, build_from  # noqa: E402
from pt_exchange_abstraction import (  # noqa: E402
    ExchangeManager,
    ExchangeType,
    MarketDataUnavailable,
    MarketNotFound,
    MarketStatus,
    PriceQuote,
    dollar_symbol,
)

H = 3_600_000  # an hour in ms
D = 24 * H
MONDAY = int(datetime(2026, 10, 12, tzinfo=timezone.utc).timestamp() * 1000)


def bar(t, o=1.0, h=2.0, lo=0.5, c=1.5, v=10.0):
    return [t, o, h, lo, c, v]


# --- symbols -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "given, wanted",
    [
        ("BTC", "BTC-USD"),
        ("btc", "BTC-USD"),
        ("BTC-USD", "BTC-USD"),
        ("BTCUSDT", "BTC-USD"),
        ("BTC-USDT", "BTC-USD"),
        ("BTC/USDC", "BTC-USD"),
        ("ETH-BTC", "ETH-BTC"),
    ],
)
def test_usd_usdt_and_usdc_are_the_same_dollar(given, wanted):
    assert dollar_symbol(given) == wanted


# --- building candle sizes -------------------------------------------------------------


def test_a_size_is_built_from_the_largest_smaller_size_that_divides_it():
    coinbase = {"1m", "5m", "15m", "1h", "6h", "1d"}
    assert build_from("4h", coinbase) == "1h"
    assert build_from("2h", coinbase) == "1h"
    assert build_from("12h", coinbase) == "6h"
    assert build_from("1w", coinbase) == "1d"
    kraken = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}
    assert build_from("8h", kraken) == "4h"
    assert build_from("1w", kraken) == "1d"
    assert build_from("1h", {"1d"}) is None


def test_four_hourly_bars_from_complete_hours_only():
    start = MONDAY  # 00:00 UTC
    hours = [bar(start + i * H, o=i, h=10 + i, lo=-i, c=i + 0.5, v=1) for i in range(8)]
    built = build_candles(hours, "1h", "4h")
    assert built == [
        [start, 0.0, 13.0, -3.0, 3.5, 4.0],
        [start + 4 * H, 4.0, 17.0, -7.0, 7.5, 4.0],
    ]
    del hours[5]  # a missing hour: that 4h bar is a gap, not a guess
    assert [b[0] for b in build_candles(hours, "1h", "4h")] == [start]


def test_weekly_bars_open_on_monday():
    days = [bar(MONDAY - 3 * D + i * D, c=i) for i in range(14)]  # Fri .. Thu
    built = build_candles(days, "1d", "1w")
    assert [b[0] for b in built] == [MONDAY]  # the part-weeks either side are gaps
    assert built[0][4] == 9.0  # the Sunday close (day index 3 + 6)


def test_sizes_that_do_not_divide_cannot_be_built():
    with pytest.raises(ValueError):
        build_candles([], "4h", "6h")


# --- the connectors --------------------------------------------------------------------


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


def test_binance_reads_klines_page_by_page(get):
    first = [[MONDAY + i * H, "1", "2", "0.5", "1.5", "10"] for i in range(1000)]
    rest = [[MONDAY + (1000 + i) * H, "1", "2", "0.5", "1.5", "10"] for i in range(3)]
    fake = get(klines=lambda p: _Response(first if p["startTime"] == MONDAY else rest))
    rows = connector("BinanceExchange").candles(
        "BTC-USD", "1h", MONDAY, MONDAY + 1100 * H
    )
    assert len(rows) == 1003 and rows[0] == bar(MONDAY)
    assert fake.calls[0][1]["symbol"] == "BTCUSDT"
    assert fake.calls[1][1]["startTime"] == MONDAY + 1000 * H


def test_binance_market_status_and_quote(get):
    binance = connector("BinanceExchange")
    get(exchangeInfo=_Response({"symbols": [{"status": "BREAK"}]}))
    assert binance.market_status("BTC-USD") == MarketStatus(
        True, False, "BREAK", "Binance BTCUSDT is BREAK"
    )
    get(exchangeInfo=_Response({"code": -1121, "msg": "Invalid symbol."}, 400))
    assert binance.market_status("NOPE-USD").listed is False
    get(klines=_Response({"code": -1121, "msg": "Invalid symbol."}, 400))
    with pytest.raises(MarketNotFound):
        binance.candles("NOPE-USD", "1h", MONDAY, MONDAY + H)
    date = {"Date": "Sun, 25 Oct 2026 23:08:46 GMT"}
    get(bookTicker=_Response({"bidPrice": "99", "askPrice": "101"}, headers=date))
    quote = binance.quote("BTC-USD")
    assert (quote.bid, quote.ask) == (99.0, 101.0)
    assert (
        quote.quote_ts
        == datetime(2026, 10, 25, 23, 8, 46, tzinfo=timezone.utc).timestamp()
    )


def test_coinbase_candles_are_reordered_oldest_first(get):
    def candles(params):
        # newest first: [time, low, high, open, close, volume]
        return _Response(
            [
                [MONDAY // 1000 + 3600, 0.5, 3.0, 2.0, 2.5, 7.0],
                [MONDAY // 1000, 0.4, 2.0, 1.0, 1.5, 5.0],
            ]
        )

    fake = get(candles=candles)
    rows = connector("CoinbaseExchange").candles("BTCUSDT", "1h", MONDAY, MONDAY + H)
    assert rows == [
        [MONDAY, 1.0, 2.0, 0.4, 1.5, 5.0],
        [MONDAY + H, 2.0, 3.0, 0.5, 2.5, 7.0],
    ]
    assert "/products/BTC-USD/candles" in fake.calls[0][0]
    assert fake.calls[0][1]["granularity"] == 3600


def test_coinbase_pages_cover_the_range_within_its_page_size():
    windows = list(pt_exchanges._paged_windows(MONDAY, MONDAY + 999 * H, 3600, 300))
    covered = set()
    for first, last in windows:
        assert (last - first) // 3600 + 1 <= 300
        covered.update(range(first, last + 1, 3600))
    assert all(MONDAY // 1000 + i * 3600 in covered for i in range(1000))


def test_coinbase_market_status_and_quote(get):
    coinbase = connector("CoinbaseExchange")
    get(
        products=_Response(
            {"id": "BTC-USD", "status": "online", "trading_disabled": False}
        )
    )
    assert coinbase.market_status("BTC-USD").trading is True
    get(
        products=_Response(
            {"id": "BTC-USD", "status": "online", "trading_disabled": True}
        )
    )
    status = coinbase.market_status("BTC-USD")
    assert (status.trading, status.reason) == (
        False,
        "Coinbase BTC-USD is online, trading_disabled",
    )
    get(products=_Response({"message": "NotFound"}, 404))
    assert coinbase.market_status("NOPE-USD").listed is False
    get(candles=_Response({"message": "NotFound"}, 404))
    with pytest.raises(MarketNotFound):
        coinbase.candles("NOPE-USD", "1h", MONDAY, MONDAY + H)
    with mock.patch.object(
        pt_exchanges.requests,
        "get",
        return_value=_Response(
            {"bid": "99.5", "ask": "99.6", "time": "2026-10-25T23:08:46.210719770Z"}
        ),
    ):
        quote = coinbase.quote("BTC-USD")
    assert (quote.bid, quote.ask) == (99.5, 99.6)
    # no Date header: the last trade's time is all there is
    assert quote.quote_ts == pytest.approx(
        datetime(2026, 10, 25, 23, 8, 46, 210719, tzinfo=timezone.utc).timestamp()
    )


def test_a_coinbase_quote_is_as_old_as_the_response_not_the_last_trade(get):
    # A quiet market's last trade can be minutes old while its bid and ask are
    # current; the quote must not look stale because nobody traded.
    get(
        ticker=_Response(
            {"bid": "99.5", "ask": "99.6", "time": "2026-10-25T23:06:46Z"},
            headers={"Date": "Sun, 25 Oct 2026 23:08:46 GMT"},
        )
    )
    quote = connector("CoinbaseExchange").quote("DASH-USD")
    assert (
        quote.quote_ts
        == datetime(2026, 10, 25, 23, 8, 46, tzinfo=timezone.utc).timestamp()
    )


def test_kraken_serves_its_latest_720_bars_and_no_weekly_bars(get):
    kraken = connector("KrakenExchange")
    assert kraken.max_history_bars("1h") == 720
    assert "1w" not in kraken.candle_timeframes()  # its weeks open on Thursday
    rows = [
        [MONDAY // 1000 + i * 3600, "1", "2", "0.5", "1.5", "1.4", "10", 5]
        for i in range(3)
    ]
    fake = get(OHLC=_Response({"error": [], "result": {"XXBTZUSD": rows, "last": 0}}))
    assert kraken.candles("BTC-USD", "1h", MONDAY, MONDAY + H) == [
        bar(MONDAY),
        bar(MONDAY + H),
    ]
    assert fake.calls[0][1] == {
        "pair": "XBTUSD",
        "interval": 60,
        "since": MONDAY // 1000 - 1,
    }
    get(OHLC=_Response({"error": ["EQuery:Unknown asset pair"]}))
    with pytest.raises(MarketNotFound):
        kraken.candles("NOPE-USD", "1h", MONDAY, MONDAY + H)


def test_kraken_market_status_and_quote(get):
    kraken = connector("KrakenExchange")
    get(
        AssetPairs=_Response(
            {"error": [], "result": {"XXBTZUSD": {"status": "cancel_only"}}}
        )
    )
    assert kraken.market_status("BTC-USD") == MarketStatus(
        True, False, "cancel_only", "Kraken XBTUSD is cancel_only"
    )
    get(AssetPairs=_Response({"error": ["EQuery:Unknown asset pair"]}))
    assert kraken.market_status("NOPE-USD").listed is False
    get(
        Ticker=_Response(
            {
                "error": [],
                "result": {"XXBTZUSD": {"a": ["101", "1", "1"], "b": ["99", "1", "1"]}},
            }
        )
    )
    quote = kraken.quote("BTC-USD")
    assert (quote.bid, quote.ask, quote.quote_ts) == (99.0, 101.0, None)


def test_kucoin_candles_are_reordered_oldest_first(get):
    kucoin = connector("KuCoinExchange")
    assert "1w" not in kucoin.candle_timeframes()  # its weeks open on Thursday
    # newest first: [time, open, close, high, low, volume, turnover]
    data = [
        [str(MONDAY // 1000 + 3600), "2", "2.5", "3", "0.5", "7", "1"],
        [str(MONDAY // 1000), "1", "1.5", "2", "0.4", "5", "1"],
    ]
    fake = get(**{"market__candles": _Response({"code": "200000", "data": data})})
    rows = kucoin.candles("BTC-USD", "1h", MONDAY, MONDAY + H)
    assert rows == [
        [MONDAY, 1.0, 2.0, 0.4, 1.5, 5.0],
        [MONDAY + H, 2.0, 3.0, 0.5, 2.5, 7.0],
    ]
    assert (
        fake.calls[0][1]["symbol"] == "BTC-USDT" and fake.calls[0][1]["type"] == "1hour"
    )
    get(
        **{
            "market__candles": _Response(
                {"code": "400100", "msg": "Unsupported trading pair."}
            )
        }
    )
    with pytest.raises(MarketNotFound):
        kucoin.candles("NOPE-USD", "1h", MONDAY, MONDAY + H)


def test_kucoin_market_status_and_quote(get):
    kucoin = connector("KuCoinExchange")
    get(symbols=_Response({"code": "200000", "data": {"enableTrading": False}}))
    assert kucoin.market_status("BTC-USD").trading is False
    get(
        symbols=_Response(
            {"code": "900001", "msg": "Trading pair NOPE-USDT does not exist."}
        )
    )
    assert kucoin.market_status("NOPE-USD").listed is False
    get(
        level1=_Response(
            {
                "code": "200000",
                "data": {"bestBid": "99", "bestAsk": "101", "time": 1792969721270},
            }
        )
    )
    quote = kucoin.quote("BTC-USD")
    # no Date header: the book's last change is all there is
    assert (quote.bid, quote.ask, quote.quote_ts) == (99.0, 101.0, 1792969721.27)


def test_a_kucoin_quote_is_as_old_as_the_response_not_the_last_book_change(get):
    get(
        level1=_Response(
            {
                "code": "200000",
                "data": {"bestBid": "99", "bestAsk": "101", "time": 1792969721270},
            },
            headers={"Date": "Sun, 25 Oct 2026 23:08:46 GMT"},
        )
    )
    quote = connector("KuCoinExchange").quote("DASH-USD")
    assert (
        quote.quote_ts
        == datetime(2026, 10, 25, 23, 8, 46, tzinfo=timezone.utc).timestamp()
    )


def test_a_rate_limited_request_is_tried_again(monkeypatch):
    answers = iter([_Response({}, 429, {"Retry-After": "2"}), _Response({"ok": 1})])
    monkeypatch.setattr(pt_exchanges.requests, "get", lambda *a, **k: next(answers))
    with mock.patch.object(pt_exchanges.time, "sleep") as sleep:
        assert pt_exchanges._public_get("https://example.invalid").json() == {"ok": 1}
    sleep.assert_called_once_with(2.0)


def test_an_exchange_that_cannot_be_asked_states_nothing(monkeypatch):
    monkeypatch.setattr(
        pt_exchanges.requests, "get", mock.Mock(side_effect=ConnectionError)
    )
    for name in (
        "BinanceExchange",
        "CoinbaseExchange",
        "KrakenExchange",
        "KuCoinExchange",
    ):
        exchange = connector(name)
        assert exchange.market_status("BTC-USD") is None, name
        assert exchange.quote("BTC-USD") is None, name


# --- the layer: primary first, never mixed -------------------------------------------


class FakeExchange:
    def __init__(
        self, name, timeframes=("1h", "1d"), rows=None, error=None, history=None
    ):
        self.name = name
        self.timeframes = frozenset(timeframes)
        self.rows = rows if rows is not None else []
        self.error = error
        self.history = history
        self.status = None
        self.price = None
        self.asked = []

    def market_symbol(self, symbol):
        return f"{self.name}:{symbol}"

    def candle_timeframes(self):
        return self.timeframes

    def max_history_bars(self, tf):
        return self.history

    def candles(self, symbol, tf, start_ms, end_ms):
        self.asked.append((symbol, tf, start_ms, end_ms))
        if self.error:
            raise self.error
        return [r for r in self.rows if start_ms <= r[0] <= end_ms]

    def market_status(self, symbol):
        self.asked.append(symbol)
        return self.status

    def quote(self, symbol):
        return self.price


def layer(primary, *exchanges):
    manager = ExchangeManager()
    for exchange in exchanges:
        manager.exchanges[ExchangeType(exchange.name)] = exchange
    manager.primary_exchange = ExchangeType(primary)
    return manager


NOW = MONDAY + 30 * D
HOURS = [bar(MONDAY + i * H) for i in range(30 * 24)]


def test_the_primary_exchange_serves_the_candles():
    kraken, coinbase = FakeExchange("kraken", rows=HOURS), FakeExchange(
        "coinbase", rows=HOURS
    )
    answer = layer("coinbase", kraken, coinbase).candles(
        "BTCUSDT", "1h", MONDAY, MONDAY + 2 * H, NOW
    )
    assert (answer.exchange, answer.pair, answer.primary) == (
        "coinbase",
        "coinbase:BTC-USD",
        True,
    )
    assert [r[0] for r in answer.value] == [MONDAY, MONDAY + H, MONDAY + 2 * H]
    assert kraken.asked == []


def test_a_size_the_exchange_lacks_is_built_from_a_smaller_one():
    coinbase = FakeExchange("coinbase", timeframes=("1h", "6h", "1d"), rows=HOURS)
    answer = layer("coinbase", coinbase).candles(
        "BTC", "4h", MONDAY, MONDAY + 4 * H, NOW
    )
    assert answer.built_from == "1h"
    assert [r[0] for r in answer.value] == [MONDAY, MONDAY + 4 * H]
    assert coinbase.asked == [("BTC-USD", "1h", MONDAY, MONDAY + 7 * H)]


def test_an_exchange_that_cannot_reach_back_is_passed_over():
    kraken = FakeExchange("kraken", rows=HOURS, history=720)
    kucoin = FakeExchange("kucoin", rows=HOURS)
    manager = layer("kraken", kraken, kucoin)
    long_ago = NOW - 1000 * H
    answer = manager.candles("BTC", "1h", long_ago, NOW - H, NOW)
    assert answer.exchange == "kucoin" and answer.primary is False
    assert kraken.asked == []
    recent = manager.candles("BTC", "1h", NOW - 10 * H, NOW - H, NOW)
    assert recent.exchange == "kraken"


def test_one_series_never_mixes_exchanges():
    gappy = [r for r in HOURS if r[0] != MONDAY + H]
    coinbase = FakeExchange("coinbase", rows=gappy)
    kucoin = FakeExchange("kucoin", rows=HOURS)
    answer = layer("coinbase", coinbase, kucoin).candles(
        "BTC", "1h", MONDAY, MONDAY + 2 * H, NOW
    )
    assert answer.exchange == "coinbase"
    assert [r[0] for r in answer.value] == [MONDAY, MONDAY + 2 * H]  # the gap stays
    assert kucoin.asked == []


def test_the_forming_bar_is_left_out():
    coinbase = FakeExchange("coinbase", rows=HOURS)
    now = MONDAY + 2 * H + 1  # the 02:00 bar is still forming
    answer = layer("coinbase", coinbase).candles(
        "BTC", "1h", MONDAY, MONDAY + 5 * H, now
    )
    assert [r[0] for r in answer.value] == [MONDAY, MONDAY + H]


def test_no_market_anywhere_is_market_not_found_and_failures_say_why():
    gone = MarketNotFound("no market")
    manager = layer(
        "coinbase",
        FakeExchange("coinbase", error=gone),
        FakeExchange("kraken", error=gone),
    )
    with pytest.raises(MarketNotFound):
        manager.candles("XMR", "1h", MONDAY, MONDAY + H, NOW)
    manager = layer(
        "coinbase",
        FakeExchange("coinbase", error=gone),
        FakeExchange("kraken", error=TimeoutError("slow")),
        FakeExchange("binance", timeframes=()),
    )
    with pytest.raises(MarketDataUnavailable) as caught:
        manager.candles("XMR", "1h", MONDAY, MONDAY + H, NOW)
    message = str(caught.value)
    assert "coinbase: no market" in message
    assert "kraken: TimeoutError: slow" in message
    assert "binance: no 1h candles" in message


def test_market_status_comes_from_the_primary_unless_it_does_not_list_the_coin():
    coinbase, kucoin = FakeExchange("coinbase"), FakeExchange("kucoin")
    manager = layer("coinbase", coinbase, kucoin)
    coinbase.status = MarketStatus(True, False, "delisted")
    kucoin.status = MarketStatus(True, True, "enableTrading")
    assert manager.market_status("BTC").exchange == "coinbase"
    coinbase.status = MarketStatus(False, False, "NOT_LISTED")
    answer = manager.market_status("XMR")
    assert (answer.exchange, answer.value.trading) == ("kucoin", True)
    kucoin.status = MarketStatus(False, False, "NOT_LISTED")
    assert manager.market_status("XMR").exchange == "coinbase"  # no one lists it
    coinbase.status = kucoin.status = None
    assert manager.market_status("XMR") is None  # no one could say


def test_the_quote_comes_from_the_first_exchange_that_gives_one():
    coinbase, kucoin = FakeExchange("coinbase"), FakeExchange("kucoin")
    manager = layer("coinbase", coinbase, kucoin)
    coinbase.price = PriceQuote(0.0, 101.0, None)  # no bid: not a quote
    kucoin.price = PriceQuote(99.0, 101.0, 1.0)
    answer = manager.quote("BTC")
    assert (answer.exchange, answer.value.bid) == ("kucoin", 99.0)
    coinbase.price = PriceQuote(98.0, 100.0, None)
    assert manager.quote("BTC").exchange == "coinbase"


def test_the_multi_exchange_manager_needs_connecting_first():
    from pt_multi_exchange import MultiExchangeManager

    multi = MultiExchangeManager.__new__(MultiExchangeManager)  # no config file
    multi.exchange_manager = layer("coinbase", FakeExchange("coinbase", rows=HOURS))
    multi.initialized = False
    for call in (
        lambda: multi.candles("BTC", "1h", MONDAY, MONDAY + H, NOW),
        lambda: multi.market_status("BTC"),
        lambda: multi.quote("BTC"),
    ):
        with pytest.raises(RuntimeError):
            call()
    multi.initialized = True
    assert multi.candles("BTC", "1h", MONDAY, MONDAY + H, NOW).exchange == "coinbase"


def test_enabled_exchanges_are_asked_in_preference_order():
    from pt_multi_exchange import ExchangeConfig, ExchangeConfigManager, TradingConfig

    manager = ExchangeConfigManager.__new__(ExchangeConfigManager)  # no config file
    manager.config = TradingConfig(
        user_region="GLOBAL",
        primary_exchange="kraken",
        exchanges=[
            ExchangeConfig("kucoin", True, 3),
            ExchangeConfig("binance", False, 1),
            ExchangeConfig("kraken", True, 1),
            ExchangeConfig("coinbase", True, 2),
        ],
    )
    assert [e.exchange_type for e in manager.get_enabled_exchanges()] == [
        "kraken",
        "coinbase",
        "kucoin",
    ]
