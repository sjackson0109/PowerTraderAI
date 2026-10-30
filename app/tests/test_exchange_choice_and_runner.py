"""The exchange choice made in Settings reaches the neural runner, and the runner
skips a coin whose data source has no market (e.g. XMR on Coinbase) instead of
retrying it for ever.

Everything runs under the isolation guard (app/conftest.py); no network.
"""

import os
import sys
import types
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_data_provider  # noqa: E402
import pt_hub  # noqa: E402
from pt_exchange_abstraction import MarketNotFound  # noqa: E402
from pt_multi_exchange import ExchangeConfigManager  # noqa: E402


class NoMarketProvider:
    """A data provider whose exchange lists no market for any coin."""

    def is_available(self):
        return True

    def get_provider_info(self):
        return "fake"

    def get_historical_data(self, coin, timeframe, **kwargs):
        base = coin.split("-")[0]
        raise MarketNotFound(f"Coinbase has no market {base}-USD (NotFound)")


def load_runner(provider):
    """Import pt_thinker fresh with ``provider`` as its data provider (inside the
    test, so the isolation guard is active for its module-level file writes)."""
    sys.modules.pop("pt_thinker", None)
    with mock.patch.object(
        pt_data_provider, "get_data_provider", return_value=provider
    ):
        import pt_thinker
    return pt_thinker


@pytest.fixture
def runner():
    cwd = os.getcwd()
    module = load_runner(NoMarketProvider())
    yield module
    os.chdir(cwd)
    sys.modules.pop("pt_thinker", None)


def test_a_coin_with_no_market_is_skipped_not_retried(runner):
    os.makedirs(runner.coin_folder("XMR"), exist_ok=True)
    with mock.patch.object(
        runner.time, "sleep", side_effect=AssertionError("retried a missing market")
    ):
        with pytest.raises(runner.CoinUnavailable) as exc:
            runner.init_coin("XMR")
    assert "no market XMR-USD" in str(exc.value)


def test_a_skipped_coin_does_not_hold_up_runner_ready(runner, capsys):
    runner.UNAVAILABLE_COINS.clear()
    runner._mark_unavailable("XMR", "Coinbase has no market XMR-USD (NotFound)")
    runner._mark_unavailable("XMR", "Coinbase has no market XMR-USD (NotFound)")
    out = capsys.readouterr().out
    assert out.count("Skipping XMR") == 1  # said once, not on every pass
    assert "Remove it from Coins in Settings" in out
    assert runner._coins_needed_for_ready(["BTC", "XMR", "ETH"]) == 2
    assert "SKIPPED" in runner.display_cache["XMR"]


def test_the_data_provider_passes_a_missing_market_through():
    provider = pt_data_provider.DataProvider.__new__(pt_data_provider.DataProvider)
    provider.initialized = True
    provider.multi_exchange = types.SimpleNamespace(
        initialized=True,
        get_current_price=mock.Mock(side_effect=MarketNotFound("no market XMR-USD")),
    )
    with pytest.raises(MarketNotFound):
        provider.get_kline_data("XMR-USDT", "1hour")
    # other failures are still reported as before
    provider.multi_exchange.get_current_price.side_effect = ValueError("timeout")
    with pytest.raises(RuntimeError, match="Multi-exchange system failed"):
        provider.get_kline_data("BTC-USDT", "1hour")


def test_settings_save_writes_the_exchange_choice_where_the_runner_reads_it():
    hub = types.SimpleNamespace(
        settings={"region": "eu", "primary_exchange": "coinbase"}
    )
    pt_hub.PowerTraderHub._sync_exchange_choice(hub)
    config = ExchangeConfigManager().load_config()
    assert (config.user_region, config.primary_exchange) == ("EU", "coinbase")
    # a second save with other values updates it again
    hub.settings = {"region": "uk", "primary_exchange": "kraken"}
    pt_hub.PowerTraderHub._sync_exchange_choice(hub)
    config = ExchangeConfigManager().load_config()
    assert (config.user_region, config.primary_exchange) == ("UK", "kraken")


def test_the_data_provider_takes_its_region_from_the_shared_config(monkeypatch):
    monkeypatch.delenv("POWERTRADER_USER_REGION", raising=False)
    hub = types.SimpleNamespace(
        settings={"region": "eu", "primary_exchange": "coinbase"}
    )
    pt_hub.PowerTraderHub._sync_exchange_choice(hub)
    seen = []

    def fake_initialize(self, user_region=None):
        seen.append(user_region)
        return False  # connect nothing: no network

    monkeypatch.setattr(
        "pt_multi_exchange.MultiExchangeManager.initialize", fake_initialize
    )
    pt_data_provider.DataProvider()
    assert seen == ["EU"]
    monkeypatch.setenv("POWERTRADER_USER_REGION", "US")
    pt_data_provider.DataProvider()
    assert seen[-1] == "US"  # the environment variable still wins


class FakeConnector:
    def __init__(self, price=None, error=None, live=False):
        self.price, self.error, self.SUPPORTS_LIVE_ORDERS = price, error, live

    def get_current_price(self, symbol):
        assert symbol == "BTC-USD"
        if self.error:
            raise self.error
        return self.price


def status_for(connector, primary="coinbase"):
    hub = types.SimpleNamespace()
    with mock.patch(
        "pt_exchange_abstraction.ExchangeFactory.get_exchange", return_value=connector
    ):
        return pt_hub.PowerTraderHub._exchange_status_once(hub, primary)


def test_the_exchange_status_is_a_real_price_check():
    # the old check used a manager that was never connected: always "not available"
    status, details = status_for(FakeConnector(price=81000.0))
    assert status == "✅ COINBASE (prices only)"
    assert "BTC $81,000.00" in details
    assert "cannot read balances or place live orders on coinbase" in details

    status, details = status_for(FakeConnector(price=81000.0, live=True), "binance")
    assert status == "✅ BINANCE" and "live orders supported" in details

    status, details = status_for(FakeConnector(error=ConnectionError("dns")))
    assert status == "❌ COINBASE" and "No price from coinbase: dns" in details


def test_the_exchange_status_check_reads_no_saved_credential(monkeypatch):
    # a public price needs no key; given none, the factory would read the saved ones
    import pt_exchanges  # noqa: F401
    import pt_secrets

    def no_reads(exchange):
        raise AssertionError(f"read the saved {exchange} credentials")

    monkeypatch.setattr(pt_secrets, "get_credentials", no_reads)
    with mock.patch("pt_exchanges.CoinbaseExchange.get_current_price") as price:
        price.return_value = 81000.0
        hub = types.SimpleNamespace()
        status, _ = pt_hub.PowerTraderHub._exchange_status_once(hub, "coinbase")
    assert status == "✅ COINBASE (prices only)"
    assert hub._status_exchanges["coinbase"].api_key == ""


def test_only_binance_claims_live_orders():
    import pt_exchanges  # noqa: F401
    from pt_exchange_abstraction import ExchangeFactory

    live = sorted(
        e.value
        for e in ExchangeFactory.get_available_exchanges()
        if getattr(ExchangeFactory.get_exchange_class(e), "SUPPORTS_LIVE_ORDERS", False)
    )
    assert live == ["binance"]
