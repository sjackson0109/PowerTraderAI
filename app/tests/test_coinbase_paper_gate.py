"""The paper/live gate (FDS-096) holds when Coinbase is the selected broker and
credentials are loaded.

Every test runs under ``recorded_http()``: all requests go through a recording
fake at the requests-Session layer and raw sockets are blocked, so "never sends
an order request" is asserted on the HTTP traffic itself, not on a mock of our
own code. Keys are synthetic.
"""

from __future__ import annotations

import copy
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(__file__))

import trading_mode as tm  # noqa: E402
from helpers_coinbase import KEY_NAME, make_ec_pem, recorded_http  # noqa: E402
from pt_exchange_abstraction import ExchangeFactory, ExchangeType  # noqa: E402
from pt_exchanges import CoinbaseExchange  # noqa: E402
from pt_multi_exchange import (  # noqa: E402
    ExchangeConfig,
    ExchangeConfigManager,
    MultiExchangeManager,
    TradingConfig,
)
from pt_settings_manager import SettingsManager  # noqa: E402

PAPER_COINBASE = {"trading": {"mode": "paper", "active_broker": "coinbase"}}
LIVE_NO_BROKER = {"trading": {"mode": "live", "active_broker": None}}
LIVE_COINBASE = {"trading": {"mode": "live", "active_broker": "coinbase"}}


def fresh_quote(bid=99.0, ask=101.0):
    now = time.time()
    return tm.Quote(bid=bid, ask=ask, quote_ts=now, fetched_ts=now)


class CoinbaseGateBase(unittest.TestCase):
    """Coinbase credentials are loaded (env, the path the live gate reads) and the
    paper exchange has an injected price feed, so nothing needs the network."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("POWERTRADER_ENV", "test")
        import pt_trader

        cls.pt_trader = pt_trader

    def setUp(self):
        tm.reset_paper_exchange()
        self.addCleanup(tm.reset_paper_exchange)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("POWERTRADER_COINBASE")
        }
        env["POWERTRADER_COINBASE_API_KEY"] = KEY_NAME
        env["POWERTRADER_COINBASE_API_SECRET"] = make_ec_pem()
        for patch in (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(self.pt_trader, "HUB_DATA_DIR", self.tmp.name),
            mock.patch.object(
                tm.urllib.request, "urlopen", side_effect=OSError("no network")
            ),
            # a stored credentials file must not leak into these tests
            mock.patch.object(ExchangeFactory, "_credentials", {}),
            mock.patch.object(ExchangeFactory, "load_credentials"),
        ):
            patch.start()
            self.addCleanup(patch.stop)

        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)  # the trader drops <SYM>_current_price.txt in cwd
        self.addCleanup(os.chdir, self.cwd)

    def trader(self, settings):
        import pandas as pd
        from signal_engine import SignalEngine

        engine = SignalEngine(
            settings_source=settings, candle_provider=lambda *a, **k: pd.DataFrame()
        )
        t = self.pt_trader.CryptoAPITrading(
            settings_source=settings, signal_engine=engine
        )
        t._order_poll_seconds = 0.0
        return t

    def use_fake_quotes(self):
        tm.get_paper_exchange()._price_feed = lambda base: fresh_quote()

    def assertNoHttp(self, http):
        self.assertEqual(http.calls, [], f"unexpected HTTP: {http.calls}")


class TestPaperModeNeverReachesCoinbase(CoinbaseGateBase):
    def test_credentials_really_are_loaded(self):
        # Guards the premise: with these env vars the factory *would* build Coinbase.
        exchange = ExchangeFactory.get_exchange(ExchangeType.COINBASE)
        self.assertIsInstance(exchange, CoinbaseExchange)
        self.assertEqual(exchange.api_key, KEY_NAME)
        self.assertIn("BEGIN EC PRIVATE KEY", exchange.api_secret)

    def test_paper_target_is_the_paper_account_not_coinbase(self):
        with recorded_http() as http, mock.patch.object(
            ExchangeFactory, "get_exchange"
        ) as get_exchange:
            target = tm.resolve_order_target(copy.deepcopy(PAPER_COINBASE))
        self.assertFalse(target.is_live)
        self.assertIsNone(target.broker)
        self.assertIsInstance(target.exchange, tm.PaperExchange)
        self.assertNotIsInstance(target.exchange, CoinbaseExchange)
        get_exchange.assert_not_called()
        self.assertNoHttp(http)

    def test_trader_orders_in_paper_mode_send_no_http_at_all(self):
        with recorded_http() as http, mock.patch.object(
            ExchangeFactory, "get_exchange"
        ) as get_exchange, mock.patch.object(
            CoinbaseExchange, "place_order"
        ) as cb_place:
            trader = self.trader(copy.deepcopy(PAPER_COINBASE))
            self.use_fake_quotes()
            buy = trader.place_buy_order(
                "id", "buy", "market", "BTC-USD", 50.0, tag="T"
            )
            sell = trader.place_sell_order(
                "id", "sell", "market", "BTC-USD", buy["quantity"], tag="T"
            )
        self.assertNoHttp(http)
        self.assertEqual(http.order_like(), [])
        get_exchange.assert_not_called()
        cb_place.assert_not_called()
        self.assertEqual(buy["mode"], "paper")
        self.assertEqual(buy["state"], "filled")
        self.assertEqual(sell["state"], "filled")
        self.assertEqual(len(tm.get_paper_exchange().account.orders), 2)

    def test_limit_orders_cancel_status_balance_and_quotes_are_also_local(self):
        with recorded_http() as http:
            target = tm.resolve_order_target(copy.deepcopy(PAPER_COINBASE))
            self.use_fake_quotes()
            limit = target.place_order("BTC-USD", "buy", 0.001, price=50.0)
            target.get_order_status(limit.order_id)
            target.cancel_order(limit.order_id)
            target.get_balance()
            target.get_market_data("BTC-USD")
            target.place_order("BTC-USD", "buy", 0.001)  # market
        self.assertNoHttp(http)

    def test_manage_trades_loop_in_paper_mode_sends_no_http(self):
        with recorded_http() as http:
            trader = self.trader(copy.deepcopy(PAPER_COINBASE))
            self.use_fake_quotes()
            trader.manage_trades()
        self.assertNoHttp(http)

    def test_anything_that_is_not_exactly_live_stays_paper(self):
        for mode in (
            None,
            "",
            "paper",
            "liv",
            "livee",
            "true",
            "1",
            1,
            True,
            "paper-live",
            [],
            {},
        ):
            with self.subTest(mode=mode):
                settings = {"trading": {"mode": mode, "active_broker": "coinbase"}}
                with recorded_http() as http, mock.patch.object(
                    ExchangeFactory, "get_exchange"
                ) as get_exchange:
                    target = tm.resolve_order_target(settings)
                    self.use_fake_quotes()
                    target.place_order("BTC-USD", "buy", 0.001)
                self.assertFalse(target.is_live)
                self.assertIsInstance(target.exchange, tm.PaperExchange)
                get_exchange.assert_not_called()
                self.assertNoHttp(http)

    def test_stored_credentials_via_the_manager_do_not_change_that(self):
        # "Credentials loaded" the other way: saved through the GUI's config store
        # and connected by MultiExchangeManager.initialize().
        config_manager = ExchangeConfigManager(self.tmp.name)
        config_manager.save_config(
            TradingConfig(
                "EU",
                "coinbase",
                [ExchangeConfig("coinbase", True, 1, KEY_NAME, make_ec_pem())],
            )
        )
        manager = MultiExchangeManager(config_manager)
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("POWERTRADER_COINBASE")
        }
        with mock.patch.dict(os.environ, env, clear=True), recorded_http() as http:
            self.assertTrue(manager.initialize())
            self.assertIn("coinbase", manager.get_available_exchanges())
            target = tm.resolve_order_target(copy.deepcopy(PAPER_COINBASE))
            self.use_fake_quotes()
            target.place_order("BTC-USD", "buy", 0.001)
        self.assertNoHttp(http)
        self.assertEqual(len(tm.get_paper_exchange().account.orders), 1)

    def test_the_test_button_is_allowed_in_paper_mode_and_is_read_only(self):
        manager = MultiExchangeManager(ExchangeConfigManager(self.tmp.name))
        with recorded_http() as http:
            http.respond_with(
                200, {"can_view": True, "can_trade": True, "can_transfer": False}
            )
            result = manager.test_exchange_connection(
                "coinbase", KEY_NAME, make_ec_pem()
            )
        self.assertTrue(result.ok)
        self.assertEqual(http.methods, ["GET"])
        self.assertEqual(http.order_like(), [])
        self.assertEqual(len(tm.get_paper_exchange().account.orders), 0)


class TestLiveModeStillNeedsBrokerAndConfirmation(CoinbaseGateBase):
    def test_live_without_a_broker_is_refused_even_with_credentials_loaded(self):
        with recorded_http() as http, mock.patch.object(
            ExchangeFactory, "get_exchange"
        ) as get_exchange:
            with self.assertRaises(tm.LiveTradingRefused):
                tm.resolve_order_target(copy.deepcopy(LIVE_NO_BROKER))
            with self.assertRaises(tm.LiveTradingRefused):
                self.trader(copy.deepcopy(LIVE_NO_BROKER))
        get_exchange.assert_not_called()
        self.assertNoHttp(http)

    def test_flipping_to_live_without_a_broker_mid_run_refuses_orders(self):
        settings = copy.deepcopy(PAPER_COINBASE)
        trader = self.trader(settings)
        self.use_fake_quotes()
        settings["trading"].update(mode="live", active_broker=None)
        with recorded_http() as http:
            self.assertIsNone(
                trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
            )
            self.assertIsNone(
                trader.place_sell_order("id", "sell", "market", "BTC-USD", 1.0)
            )
        self.assertNoHttp(http)
        self.assertEqual(len(tm.get_paper_exchange().account.orders), 0)

    def test_switching_to_live_coinbase_requires_confirmation_and_a_broker(self):
        manager = SettingsManager("pt_config.json", self.tmp.name)
        self.assertFalse(tm.can_apply("live", "coinbase", False))
        self.assertFalse(tm.can_apply("live", None, True))
        self.assertTrue(tm.can_apply("live", "coinbase", True))
        self.assertTrue(tm.can_apply("paper", "coinbase", False))

        with self.assertRaises(tm.TradingModeError):
            tm.apply_trading_mode(
                "live", broker="coinbase", live_confirmed=False, manager=manager
            )
        with self.assertRaises(tm.TradingModeError):
            tm.apply_trading_mode(
                "live", broker=None, live_confirmed=True, manager=manager
            )
        # nothing above changed the effective mode
        self.assertEqual(tm.read_trading_settings(manager.settings_path).key, "paper")

        applied = tm.apply_trading_mode(
            "live", broker="coinbase", live_confirmed=True, manager=manager
        )
        self.assertEqual(applied.key, "live:coinbase")
        self.assertEqual(applied.label, "MODE: LIVE — coinbase")

    def test_there_is_no_coinbase_testnet_so_live_coinbase_is_real_money(self):
        # pt_config.json carries a "coinbase_testnet" flag; the gate only honours
        # testnet for brokers in TESTNET_BROKERS, and Coinbase is not one of them.
        self.assertNotIn("coinbase", tm.TESTNET_BROKERS)
        self.assertFalse(tm.read_trading_settings(LIVE_COINBASE).uses_testnet)
        self.assertNotIn("testnet", tm.read_trading_settings(LIVE_COINBASE).label)

    def test_live_coinbase_cannot_send_an_order_today(self):
        # The gate lets a confirmed live+coinbase target through, but the connector
        # has no order placement: it raises before any request is built.
        with recorded_http() as http:
            target = tm.resolve_order_target(copy.deepcopy(LIVE_COINBASE))
            self.assertTrue(target.is_live)
            self.assertIsInstance(target.exchange, CoinbaseExchange)
            with self.assertRaises(NotImplementedError):
                target.place_order("BTC-USD", "buy", 0.001)
            with self.assertRaises(NotImplementedError):
                target.cancel_order("x")
        self.assertNoHttp(http)

    def test_live_coinbase_through_the_trader_places_no_order_and_records_nothing(self):
        with recorded_http() as http:
            try:
                trader = self.trader(copy.deepcopy(LIVE_COINBASE))
            except (
                Exception
            ) as exc:  # trader may refuse to start on a broker without balances
                self.assertNoHttp(http)
                self.skipTest(
                    f"trader does not start on live coinbase: {type(exc).__name__}"
                )
            result = trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        self.assertIsNone(result)
        self.assertEqual(http.order_like(), [])
        self.assertFalse(
            os.path.exists(os.path.join(self.tmp.name, "trade_history.jsonl"))
        )


class TestTheHarnessCanSeeOrders(unittest.TestCase):
    """Guards the guard: the zero-HTTP assertions above are only meaningful if
    this recorder would have caught an order request."""

    def test_recorder_flags_order_post_and_preview_and_blocks_sockets(self):
        import socket

        import requests

        with recorded_http() as http:
            requests.post("https://api.coinbase.com/api/v3/brokerage/orders", json={})
            requests.get("https://api.coinbase.com/api/v3/brokerage/orders/preview")
            requests.delete("https://api.coinbase.com/api/v3/brokerage/orders/x")
            self.assertEqual(len(http.order_like()), 3)
            with self.assertRaises(AssertionError):
                socket.create_connection(("api.coinbase.com", 443), 1)


if __name__ == "__main__":
    unittest.main()
