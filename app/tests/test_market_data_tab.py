"""The hub's Market Data tab reads the exchanges in Settings, primary first
(FDS-MX-001 phase G2): a feed per exchange polls its public quote for the coins
subscribed to it.

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
    PriceQuote,
)


class Connector:
    def __init__(self, bid, ask):
        self.bid, self.ask, self.asked = bid, ask, []

    def quote(self, symbol):
        self.asked.append(symbol)
        return PriceQuote(self.bid, self.ask, 1_800_000_000.0)


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
