"""Trading fees through the exchange layer (owner, 2026-11-04): ``trading_fees(symbol)``
gives the maker and taker rates for the selected exchange, primary first. A connector
reads its exchange's own rates where it can (Kraken's public fee schedule; Coinbase's
and Binance's account endpoints with an API key) and otherwise answers with the
exchange's published standard rates (DEFAULT_TRADING_FEES), logging a warning.

Everything runs under the isolation guard (app/conftest.py); the exchanges' answers
are fakes, so nothing here is checked against a live exchange.
"""

import logging
import math
from unittest import mock

import pytest

import pt_exchange_abstraction as pea
from pt_exchange_abstraction import (
    DEFAULT_TRADING_FEES,
    ExchangeManager,
    ExchangeType,
    TradingFees,
    default_trading_fees,
    usable_fees,
)


@pytest.fixture(autouse=True)
def _fresh_warnings():
    """The standard-rates warning is logged once an hour per exchange: each test
    starts with none logged."""
    pea._default_fees_warned.clear()
    yield
    pea._default_fees_warned.clear()


class _Json:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def connector(name, *args):
    import pt_exchanges

    return getattr(pt_exchanges, name)(*(args or ("", "")))


# --- the shape ---------------------------------------------------------------------


def test_fees_are_fractions_with_their_exchange_and_source():
    fees = TradingFees(maker=0.004, taker=0.006, exchange="kraken", source="exchange")
    assert fees.for_order("market") == ("taker", 0.006)
    assert fees.for_order("limit") == ("maker", 0.004)
    assert fees.for_order("LIMIT") == ("maker", 0.004)


@pytest.mark.parametrize(
    "value, usable",
    [
        (TradingFees(0.0, 0.001, "binance", "exchange"), True),  # a free maker side
        (TradingFees(0.006, 0.012, "coinbase", "default"), True),
        (TradingFees(-0.001, 0.001, "x", "exchange"), False),
        (TradingFees(0.001, 1.0, "x", "exchange"), False),  # 100% is not a rate
        (TradingFees(0.001, float("nan"), "x", "exchange"), False),
        (TradingFees(True, 0.001, "x", "exchange"), False),
        (TradingFees("0.001", 0.001, "x", "exchange"), False),
        ((0.001, 0.001), False),
        (None, False),
        (mock.Mock(), False),
    ],
)
def test_only_rates_from_zero_to_under_one_are_fees(value, usable):
    assert usable_fees(value) is (value if usable else None)


def test_every_market_data_exchange_has_standard_rates():
    """The exchanges that can price a paper fill (those that serve market data) each
    have their published standard rates stored, as (maker, taker) fractions."""
    from pt_exchange_abstraction import ExchangeFactory

    market_data = set(ExchangeFactory.market_data_exchanges())
    assert market_data == {"coinbase", "kraken", "binance", "kucoin"}
    assert market_data <= set(DEFAULT_TRADING_FEES)
    for maker, taker in DEFAULT_TRADING_FEES.values():
        assert 0.0 < maker <= taker < 0.02
        assert math.isfinite(maker) and math.isfinite(taker)


def test_the_standard_rates_are_used_with_a_warning_once_an_hour(caplog):
    with caplog.at_level(logging.WARNING, logger="pt_exchange_abstraction"):
        fees = default_trading_fees("coinbase")
        again = default_trading_fees(ExchangeType.COINBASE)
    assert fees == TradingFees(0.006, 0.012, "coinbase", "default")
    assert again == fees
    warnings = [r.getMessage() for r in caplog.records]
    assert warnings == [
        "Coinbase trading fees could not be read from the exchange; using its "
        "standard rates: maker 0.60%, taker 1.20%"
    ]
    assert default_trading_fees("robinhood") is None  # none stored
    assert default_trading_fees("") is None


# --- each connector ------------------------------------------------------------------


def test_kraken_reads_the_first_tier_of_its_public_fee_schedules(monkeypatch):
    import pt_exchanges

    asked = []
    pair = {
        "XXBTZUSD": {
            "altname": "XBTUSD",
            "fees": [[0, 0.4], [10000, 0.35]],
            "fees_maker": [[0, 0.25], [10000, 0.2]],
        }
    }

    def get(url, params=None, timeout=None):
        asked.append((url, params))
        return _Json({"error": [], "result": pair})

    monkeypatch.setattr(pt_exchanges.requests, "get", get)
    fees = connector("KrakenExchange").trading_fees("BTC-USD")
    assert fees == TradingFees(0.0025, 0.004, "kraken", "exchange")
    assert asked == [("https://api.kraken.com/0/public/AssetPairs", {"pair": "XBTUSD"})]
    # a pair with one schedule charges it either way
    del pair["XXBTZUSD"]["fees_maker"]
    assert connector("KrakenExchange").trading_fees("BTC-USD") == TradingFees(
        0.004, 0.004, "kraken", "exchange"
    )


@pytest.mark.parametrize(
    "answer",
    [
        ConnectionError("offline"),
        {"error": ["EQuery:Unknown asset pair"]},
        {"error": [], "result": {"XXBTZUSD": {"altname": "XBTUSD"}}},  # no schedule
    ],
)
def test_kraken_without_its_schedule_uses_the_standard_rates(monkeypatch, answer):
    import pt_exchanges

    def get(url, params=None, timeout=None):
        if isinstance(answer, Exception):
            raise answer
        return _Json(answer)

    monkeypatch.setattr(pt_exchanges.requests, "get", get)
    assert connector("KrakenExchange").trading_fees("BTC-USD") == TradingFees(
        0.0025, 0.004, "kraken", "default"
    )


def test_coinbase_reads_the_accounts_fee_tier_with_a_key():
    coinbase = connector("CoinbaseExchange", "organizations/o/apiKeys/k", "secret")
    answer = {"fee_tier": {"maker_fee_rate": "0.004", "taker_fee_rate": "0.006"}}
    with mock.patch.object(
        coinbase, "_brokerage_request", return_value=answer
    ) as request:
        fees = coinbase.trading_fees("ETH-USD")
    assert fees == TradingFees(0.004, 0.006, "coinbase", "exchange")
    request.assert_called_once_with(
        "GET", "/transaction_summary", params={"product_type": "SPOT"}
    )


@pytest.mark.parametrize(
    "answer",
    [
        RuntimeError("Coinbase GET /transaction_summary: HTTP 403"),
        {"fee_tier": {"maker_fee_rate": "", "taker_fee_rate": "0.006"}},
        {},
    ],
)
def test_coinbase_without_its_fee_tier_uses_the_standard_rates(answer):
    coinbase = connector("CoinbaseExchange", "organizations/o/apiKeys/k", "secret")
    effect = {"side_effect": answer} if isinstance(answer, Exception) else {}
    with mock.patch.object(
        coinbase, "_brokerage_request", return_value=answer, **effect
    ):
        assert coinbase.trading_fees("BTC-USD") == TradingFees(
            0.006, 0.012, "coinbase", "default"
        )


def test_coinbase_without_a_key_asks_nothing():
    coinbase = connector("CoinbaseExchange")
    with mock.patch.object(coinbase, "_brokerage_request") as request:
        assert coinbase.trading_fees("BTC-USD").source == "default"
    request.assert_not_called()


def test_binance_reads_the_accounts_commission_with_a_key():
    binance = connector("BinanceExchange", "key", "secret")
    answer = {
        "symbol": "BTCUSDT",
        "standardCommission": {"maker": "0.00075", "taker": "0.00100"},
        "taxCommission": {"maker": "0.00001", "taker": "0.00002"},
        "discount": {"discount": "0.75"},
    }
    with mock.patch.object(binance, "_signed_request", return_value=answer) as signed:
        fees = binance.trading_fees("BTC-USD")
    assert fees.maker == pytest.approx(0.00076)
    assert fees.taker == pytest.approx(0.00102)
    assert (fees.exchange, fees.source) == ("binance", "exchange")
    signed.assert_called_once_with(
        "GET", "/api/v3/account/commission", {"symbol": "BTCUSDT"}
    )


def test_binance_without_a_key_or_an_answer_uses_the_standard_rates():
    binance = connector("BinanceExchange")
    with mock.patch.object(binance, "_signed_request") as signed:
        assert binance.trading_fees("BTC-USD") == TradingFees(
            0.001, 0.001, "binance", "default"
        )
    signed.assert_not_called()
    keyed = connector("BinanceExchange", "key", "secret")
    for answer in (RuntimeError("Binance API error -2015"), {"symbol": "BTCUSDT"}):
        effect = {"side_effect": answer} if isinstance(answer, Exception) else {}
        with mock.patch.object(keyed, "_signed_request", return_value=answer, **effect):
            assert keyed.trading_fees("BTC-USD").source == "default"


def test_kucoin_answers_with_its_standard_rates_and_robinhood_with_none(monkeypatch):
    import pt_exchanges

    monkeypatch.setattr(
        pt_exchanges.requests, "get", mock.Mock(side_effect=AssertionError("no call"))
    )
    assert connector("KuCoinExchange").trading_fees("BTC-USD") == TradingFees(
        0.001, 0.001, "kucoin", "default"
    )
    assert connector("RobinhoodExchange").trading_fees("BTC-USD") is None


# --- the exchange layer: the primary exchange first ----------------------------------


class _Exchange:
    def __init__(self, name, fees):
        self.name = name
        self.fees = fees
        self.asked = []

    def trading_fees(self, symbol):
        self.asked.append(symbol)
        if isinstance(self.fees, Exception):
            raise self.fees
        return self.fees

    def market_symbol(self, symbol):
        return symbol


def exchange_manager(primary, *exchanges):
    manager = ExchangeManager()
    for exchange in exchanges:
        manager.exchanges[ExchangeType(exchange.name)] = exchange
    manager.primary_exchange = ExchangeType(primary)
    return manager


def test_the_primary_exchanges_rates_are_used():
    kraken = _Exchange("kraken", TradingFees(0.0025, 0.004, "kraken", "exchange"))
    coinbase = _Exchange("coinbase", TradingFees(0.006, 0.012, "coinbase", "default"))
    manager = exchange_manager("coinbase", kraken, coinbase)
    answer = manager.trading_fees("BTCUSDT")
    assert answer.value is coinbase.fees
    assert (answer.exchange, answer.pair, answer.primary) == (
        "coinbase",
        "BTC-USD",
        True,
    )
    assert kraken.asked == []


def test_one_exchange_can_be_asked_for_its_rates():
    kraken = _Exchange("kraken", TradingFees(0.0025, 0.004, "kraken", "exchange"))
    coinbase = _Exchange("coinbase", TradingFees(0.006, 0.012, "coinbase", "default"))
    manager = exchange_manager("coinbase", coinbase, kraken)
    answer = manager.trading_fees("BTC-USD", only="kraken")
    assert (answer.value, answer.primary) == (kraken.fees, False)
    assert coinbase.asked == []
    assert manager.trading_fees("BTC-USD", only="binance") is None  # not connected


def test_a_connector_that_fails_answers_with_its_standard_rates():
    coinbase = _Exchange("coinbase", RuntimeError("boom"))
    kraken = _Exchange("kraken", TradingFees(0.0025, 0.004, "kraken", "exchange"))
    manager = exchange_manager("coinbase", coinbase, kraken)
    answer = manager.trading_fees("BTC-USD")
    assert answer.value == TradingFees(0.006, 0.012, "coinbase", "default")
    assert kraken.asked == []  # the primary's own standard rates, not Kraken's
    coinbase.fees = mock.Mock()  # not fees at all
    assert manager.trading_fees("BTC-USD").value.source == "default"


def test_an_exchange_with_no_rates_at_all_passes_to_the_next():
    robinhood = _Exchange("robinhood", None)
    kraken = _Exchange("kraken", TradingFees(0.0025, 0.004, "kraken", "exchange"))
    manager = exchange_manager("robinhood", robinhood, kraken)
    assert manager.trading_fees("BTC-USD").value is kraken.fees
    kraken.fees = None
    with mock.patch.dict(DEFAULT_TRADING_FEES, clear=True):
        assert manager.trading_fees("BTC-USD") is None


def test_the_multi_exchange_manager_asks_its_connected_exchanges():
    from pt_multi_exchange import MultiExchangeManager

    kraken = _Exchange("kraken", TradingFees(0.0025, 0.004, "kraken", "exchange"))
    multi = MultiExchangeManager.__new__(MultiExchangeManager)  # no config file
    multi.exchange_manager = exchange_manager("kraken", kraken)
    multi.initialized = False
    with pytest.raises(RuntimeError):
        multi.trading_fees("BTC-USD")
    multi.initialized = True
    assert multi.trading_fees("BTC-USD").value is kraken.fees
    assert multi.trading_fees("BTC-USD", only="coinbase") is None
