"""The hub's Market Data tab reads the exchanges in Settings, primary first
(FDS-MX-001 phase G2): a feed per exchange polls its public 24-hour ticker for the
coins subscribed to it, through the exchange layer.

Everything runs under the isolation guard (app/conftest.py); no network.
"""

import os
import sys

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import real_time_market_data as rtmd  # noqa: E402
from pt_exchange_abstraction import (  # noqa: E402
    ExchangeManager,
    ExchangeType,
    Ticker,
)


class Connector:
    """A connector whose ticker has no last price (the middle of bid and ask
    stands in) and the 24-hour fields given as ``day``."""

    def __init__(self, bid, ask, **day):
        self.bid, self.ask, self.asked = bid, ask, []
        self.day = day or {"change_24h": 1.0, "change_24h_pct": 1.0}

    def market_symbol(self, symbol):
        return symbol

    def ticker(self, symbol):
        self.asked.append(symbol)
        return Ticker(None, self.bid, self.ask, ticker_ts=1_800_000_000.0, **self.day)


def layer():
    manager = ExchangeManager()
    manager.exchanges[ExchangeType("kraken")] = Connector(99.0, 101.0)
    manager.exchanges[ExchangeType("coinbase")] = Connector(100.0, 102.0)
    manager.primary_exchange = ExchangeType("coinbase")
    return manager


def manager(tmp_path):
    m = rtmd.MarketDataManager(db_path=str(tmp_path / "market.db"))
    m.aggregator._layer = layer()
    m.aggregator.poll_seconds = 3600  # the test polls by hand
    return m


def test_the_exchanges_are_the_ones_in_settings_primary_first(tmp_path):
    m = manager(tmp_path)
    assert m.exchange_names() == ["coinbase", "kraken"]


def test_a_coin_is_subscribed_on_the_primary_by_default_and_polled(tmp_path):
    m = manager(tmp_path)
    seen = []
    m.add_update_callback(lambda kind, ticker: seen.append(ticker))
    try:
        m.subscribe_symbol("btcusdt")
        assert m.active_subscriptions["BTC-USD"]["exchanges"] == ["coinbase"]
        assert m.aggregator.poll_once("coinbase") == 1
    finally:
        m.stop()
    ticker = seen[-1]
    assert (ticker.symbol, ticker.exchange, ticker.bid, ticker.ask) == (
        "BTC-USD",
        "coinbase",
        100.0,
        102.0,
    )
    assert m.get_current_price("BTC", "coinbase") == 101.0


def test_two_exchanges_give_a_spread_across_them(tmp_path):
    m = manager(tmp_path)
    try:
        m.subscribe_symbol("ETH", ["coinbase", "kraken"])
        m.aggregator.poll_once("coinbase")
        m.aggregator.poll_once("kraken")
    finally:
        m.stop()
    analysis = m.aggregator.get_spread_analysis("ETH")
    assert set(analysis["exchanges"]) == {"coinbase", "kraken"}
    assert analysis["best_ask"] == {"price": 101.0, "exchange": "kraken"}


def test_an_exchange_not_in_settings_gets_no_feed(tmp_path):
    m = manager(tmp_path)
    try:
        m.aggregator.start_feed("bitstamp")
        assert m.aggregator.active_feeds["bitstamp"] is False
    finally:
        m.stop()


def test_the_feed_fills_every_field_of_the_exchanges_ticker(tmp_path):
    """BTC-USD on Coinbase: change, change percent and volume come from its ticker
    (they were hard-coded to 0.0)."""
    m = manager(tmp_path)
    coinbase = m.aggregator.layer().exchanges[ExchangeType("coinbase")]
    coinbase.day = dict(
        volume_24h=8913.3,
        high_24h=103.0,
        low_24h=97.0,
        change_24h=-2.5,
        change_24h_pct=-2.42,
    )
    try:
        m.subscribe_symbol("BTC")
        assert m.aggregator.poll_once("coinbase") == 1
    finally:
        m.stop()
    ticker = m.aggregator.get_latest_ticker("BTC-USD", "coinbase")
    assert (ticker.volume, ticker.high_24h, ticker.low_24h) == (8913.3, 103.0, 97.0)
    assert (ticker.change_24h, ticker.change_24h_pct) == (-2.5, -2.42)
    assert ticker.spread == 2.0 and ticker.spread_pct == 2.0 / 102.0 * 100


def test_a_value_the_exchange_does_not_give_is_none_and_shown_as_n_a(tmp_path):
    from real_time_market_data_gui import NA, _amount, _percent, _price

    m = manager(tmp_path)
    coinbase = m.aggregator.layer().exchanges[ExchangeType("coinbase")]
    coinbase.day = {"change_24h": 0.5}  # no volume, high, low or percent
    try:
        m.subscribe_symbol("BTC")
        m.aggregator.poll_once("coinbase")
    finally:
        m.stop()
    ticker = m.aggregator.get_latest_ticker("BTC")
    assert (ticker.volume, ticker.high_24h, ticker.change_24h_pct) == (None,) * 3
    assert _amount(ticker.volume) == _price(ticker.high_24h) == NA == "n/a"
    assert _percent(ticker.change_24h_pct, signed=True) == "n/a"
    assert _price(0.0) == "0.00000000"  # a real zero is shown as one
    assert _price(-2.5, signed=True) == "-2.5000"
    assert _percent(1.234, signed=True) == "+1.23%"
    assert _amount(53602.0394) == "53,602.04"


class NotListed(Connector):
    """An exchange with no market for these coins."""

    def __init__(self, bid, ask, coins):
        super().__init__(bid, ask)
        self.coins = set(coins)

    def ticker(self, symbol):
        from pt_exchange_abstraction import MarketNotFound

        if symbol.split("-")[0] in self.coins:
            self.asked.append(symbol)
            raise MarketNotFound(f"no market {symbol}")
        return super().ticker(symbol)


def test_a_coin_the_primary_does_not_list_moves_to_the_next_exchange(tmp_path):
    """Subscribed without naming an exchange: the primary, else the next exchange
    in Settings order that has a market for the coin."""
    m = manager(tmp_path)
    m.aggregator.layer().exchanges[ExchangeType("coinbase")] = NotListed(
        100.0, 102.0, {"XMR"}
    )
    try:
        m.subscribe_symbol("XMR")
        m.subscribe_symbol("BTC")
        m.aggregator.poll_once("coinbase")  # (its feed may have asked already)
        assert m.aggregator.subscribed()["XMR-USD"] == ["kraken"]
        assert m.aggregator.active_feeds["kraken"] is True
        assert m.aggregator.poll_once("kraken") == 1
        # named on an exchange that has no market: it is not moved anywhere
        m.subscribe_symbol("XMR", ["coinbase"])
        m.aggregator.not_listed.clear()
        m.aggregator.poll_once("coinbase")
        assert m.aggregator.subscribed()["XMR-USD"] == ["kraken"]
    finally:
        m.stop()
    assert m.get_current_price("XMR", "kraken") == 100.0


def test_a_feed_left_with_no_coin_stops_and_starts_again(tmp_path):
    m = manager(tmp_path)
    try:
        m.subscribe_symbol("ETH", ["kraken"])
        assert m.aggregator.active_feeds["kraken"] is True
        m.unsubscribe_symbol("ETH")
        assert m.aggregator.active_feeds["kraken"] is False
        m.subscribe_symbol("ETH", ["kraken"])  # a stopped feed starts again
        assert m.aggregator.active_feeds["kraken"] is True
    finally:
        m.stop()
