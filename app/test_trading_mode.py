"""
Tests for the trading-mode gate (issue #96).

Covers the three gate branches, fail-closed parsing, persistence through the
settings manager, the paper adapter, and the trader end-to-end: in paper mode
no live venue is touched, in live mode without a broker every order is
refused, and in live mode with a broker orders route through
ExchangeFactory.get_exchange(...).
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import time
import unittest
from unittest import mock

import requests

import pt_settings_manager
import trading_mode as tm
from pt_exchange_abstraction import ExchangeType, MarketData, OrderResult
from pt_settings_manager import SettingsManager

PAPER = {"trading": {"mode": "paper", "active_broker": None}}
LIVE_NO_BROKER = {"trading": {"mode": "live", "active_broker": None}}
LIVE_KRAKEN = {"trading": {"mode": "live", "active_broker": "kraken"}}


class HttpSpy:
    """Fails the test if anything reaches `requests` (all live REST goes there)."""

    def __enter__(self):
        self.request = mock.patch.object(
            requests.Session, "request", side_effect=AssertionError("live HTTP call")
        )
        self.get = mock.patch.object(
            requests, "get", side_effect=AssertionError("live HTTP call")
        )
        self.post = mock.patch.object(
            requests, "post", side_effect=AssertionError("live HTTP call")
        )
        self.mocks = [p.start() for p in (self.request, self.get, self.post)]
        return self

    def __exit__(self, *exc):
        for p in (self.request, self.get, self.post):
            p.stop()

    @property
    def calls(self):
        return sum(m.call_count for m in self.mocks)


class GateTests(unittest.TestCase):
    """resolve_order_target: the three branches of FDS-096 section 5.1."""

    def setUp(self):
        tm.reset_paper_exchange()
        self.addCleanup(tm.reset_paper_exchange)

    def test_paper_mode_returns_paper_target_and_never_builds_a_live_exchange(self):
        with mock.patch.object(tm.ExchangeFactory, "get_exchange") as get_exchange:
            target = tm.resolve_order_target(PAPER)
        get_exchange.assert_not_called()
        self.assertFalse(target.is_live)
        self.assertEqual(target.key, "paper")
        self.assertIsInstance(target.exchange, tm.PaperExchange)

    def test_live_without_broker_is_refused_before_any_exchange_is_built(self):
        with mock.patch.object(tm.ExchangeFactory, "get_exchange") as get_exchange:
            with self.assertRaises(tm.LiveTradingRefused) as ctx:
                tm.resolve_order_target(LIVE_NO_BROKER)
        get_exchange.assert_not_called()
        self.assertIn("no active broker", str(ctx.exception))

    def test_live_with_broker_routes_through_exchange_factory(self):
        fake = mock.MagicMock(name="kraken")
        with mock.patch.object(
            tm.ExchangeFactory, "get_exchange", return_value=fake
        ) as get_exchange:
            target = tm.resolve_order_target(LIVE_KRAKEN)
        get_exchange.assert_called_once_with(ExchangeType.KRAKEN)
        self.assertTrue(target.is_live)
        self.assertEqual(target.broker, "kraken")
        self.assertIs(target.exchange, fake)

    def test_live_target_delegates_the_abstract_exchange_calls(self):
        fake = mock.MagicMock()
        with mock.patch.object(tm.ExchangeFactory, "get_exchange", return_value=fake):
            target = tm.resolve_order_target(LIVE_KRAKEN)
        target.place_order("BTC-USD", "buy", 0.1)
        target.get_balance()
        target.get_order_status("x")
        target.cancel_order("x")
        fake.place_order.assert_called_once_with("BTC-USD", "buy", 0.1, None)
        fake.get_balance.assert_called_once_with()
        fake.get_order_status.assert_called_once_with("x")
        fake.cancel_order.assert_called_once_with("x")

    def test_broker_that_cannot_be_built_is_refused_not_downgraded(self):
        with mock.patch.object(
            tm.ExchangeFactory, "get_exchange", side_effect=ValueError("not registered")
        ):
            with self.assertRaises(tm.LiveTradingRefused):
                tm.resolve_order_target(LIVE_KRAKEN)

    def test_testnet_flag_is_forwarded_only_to_brokers_that_support_it(self):
        with mock.patch.object(tm.ExchangeFactory, "get_exchange") as get_exchange:
            tm.resolve_order_target(
                {"trading": {"mode": "live", "active_broker": "binance"}}
            )
            get_exchange.assert_called_with(ExchangeType.BINANCE, testnet=True)
            tm.resolve_order_target(
                {
                    "trading": {
                        "mode": "live",
                        "active_broker": "binance",
                        "binance_testnet": False,
                    }
                }
            )
            get_exchange.assert_called_with(ExchangeType.BINANCE, testnet=False)
            tm.resolve_order_target(LIVE_KRAKEN)
            get_exchange.assert_called_with(ExchangeType.KRAKEN)


class FailClosedTests(unittest.TestCase):
    def test_anything_but_live_is_paper(self):
        for settings in (
            {},
            {"trading": {}},
            {"trading": {"mode": None}},
            {"trading": {"mode": ""}},
            {"trading": {"mode": "paper"}},
            {"trading": {"mode": "liv"}},
            {"trading": {"mode": "yes"}},
            {"trading": {"mode": True}},
            {"trading": {"mode": 1}},
            {"trading": "live"},
            "not-a-mapping",
        ):
            with self.subTest(settings=settings):
                self.assertFalse(tm.read_trading_settings(settings).is_live)

    def test_live_is_case_and_whitespace_insensitive_but_nothing_looser(self):
        for raw in ("live", "LIVE", " Live "):
            self.assertTrue(
                tm.read_trading_settings({"trading": {"mode": raw}}).is_live, raw
            )

    def test_flat_dotted_keys_are_understood(self):
        ts = tm.read_trading_settings(
            {"trading.mode": "live", "trading.active_broker": "kraken"}
        )
        self.assertTrue(ts.is_live)
        self.assertEqual(ts.active_broker, "kraken")

    def test_unknown_broker_counts_as_no_broker(self):
        ts = tm.read_trading_settings(
            {"trading": {"mode": "live", "active_broker": "robinhood-ish"}}
        )
        self.assertIsNone(ts.active_broker)
        with self.assertRaises(tm.LiveTradingRefused):
            tm.resolve_order_target(
                {"trading": {"mode": "live", "active_broker": "robinhood-ish"}}
            )

    def test_missing_unreadable_or_corrupt_file_means_paper(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(
                tm.read_trading_settings(os.path.join(d, "none.json")).is_live
            )
            bad = os.path.join(d, "bad.json")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("{ truncated")
            self.assertFalse(tm.read_trading_settings(bad).is_live)
            arr = os.path.join(d, "arr.json")
            with open(arr, "w", encoding="utf-8") as f:
                json.dump(["live"], f)
            self.assertFalse(tm.read_trading_settings(arr).is_live)

    def test_label_and_data_subdir(self):
        paper = tm.read_trading_settings(PAPER)
        self.assertEqual(paper.label, "MODE: PAPER")
        self.assertEqual(paper.data_subdir, "paper")
        live = tm.read_trading_settings(LIVE_KRAKEN)
        self.assertEqual(live.label, "MODE: LIVE — kraken")
        self.assertEqual(live.data_subdir, "")
        testnet = tm.read_trading_settings(
            {"trading": {"mode": "live", "active_broker": "binance"}}
        )
        self.assertEqual(testnet.data_subdir, "testnet")
        blocked = tm.read_trading_settings(LIVE_NO_BROKER)
        self.assertIn("blocked", blocked.label)
        self.assertEqual(blocked.data_subdir, "paper")


class SettingsPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def manager(self):
        return SettingsManager("pt_config.json", self.tmp.name)

    def test_defaults_are_paper_no_broker_testnet_on(self):
        m = self.manager()
        self.assertEqual(m.get("trading.mode"), "paper")
        self.assertIsNone(m.get("trading.active_broker"))
        self.assertTrue(m.get_testnet("binance"))
        self.assertTrue(m.get_testnet("kraken"))  # absent key -> safe default

    def test_mode_and_broker_persist_across_restart(self):
        m = self.manager()
        self.assertTrue(m.set_trading_mode("live", broker="kraken"))
        self.assertTrue(m.set_testnet("binance", False))

        restarted = self.manager()
        self.assertEqual(restarted.get_trading_mode(), "live")
        self.assertEqual(restarted.get_active_broker(), "kraken")
        self.assertFalse(restarted.get_testnet("binance"))
        # ...and the gate reads the same thing straight off disk
        ts = tm.read_trading_settings(restarted.settings_path)
        self.assertTrue(ts.is_live)
        self.assertEqual(ts.active_broker, "kraken")

    def test_live_is_refused_without_a_broker(self):
        m = self.manager()
        self.assertFalse(m.set_trading_mode("live"))
        self.assertEqual(m.get_trading_mode(), "paper")
        self.assertEqual(self.manager().get_trading_mode(), "paper")

    def test_clearing_the_broker_while_live_falls_back_to_paper(self):
        m = self.manager()
        m.set_trading_mode("live", broker="kraken")
        self.assertTrue(m.set_active_broker(None))
        self.assertEqual(self.manager().get_trading_mode(), "paper")

    def test_invalid_values_are_rejected(self):
        m = self.manager()
        self.assertFalse(m.set_trading_mode("yolo"))
        self.assertFalse(m.set_trading_mode("paper", broker="not-a-broker"))
        self.assertFalse(m.set("trading.mode", "yolo"))
        self.assertEqual(m.get_trading_mode(), "paper")

    def test_corrupt_values_on_disk_are_repaired_to_paper(self):
        path = os.path.join(self.tmp.name, "pt_config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"trading": {"mode": "YOLO", "active_broker": "nope"}}, f)
        m = self.manager()
        self.assertEqual(m.get_trading_mode(), "paper")
        self.assertIsNone(m.get_active_broker())

    def test_changing_a_setting_never_rewrites_the_shared_defaults(self):
        before = copy.deepcopy(pt_settings_manager.DEFAULT_SETTINGS)
        m = self.manager()
        m.set_trading_mode("live", broker="kraken", persist=False)
        self.assertEqual(pt_settings_manager.DEFAULT_SETTINGS, before)
        self.assertEqual(
            pt_settings_manager.DEFAULT_SETTINGS["trading"]["mode"], "paper"
        )

    def test_saved_file_is_complete_json(self):
        m = self.manager()
        m.set_trading_mode("live", broker="kraken")
        with open(m.settings_path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["trading"]["mode"], "live")
        self.assertFalse(os.path.exists(m.settings_path + ".tmp"))


class ApplyModeTests(unittest.TestCase):
    """Live needs a broker AND the explicit confirmation - enforced outside the UI too."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager = SettingsManager("pt_config.json", self.tmp.name)

    def test_can_apply_truth_table(self):
        self.assertTrue(tm.can_apply("paper", None, False))
        self.assertFalse(tm.can_apply("live", None, True))
        self.assertFalse(tm.can_apply("live", "kraken", False))
        self.assertFalse(tm.can_apply("live", "bogus", True))
        self.assertTrue(tm.can_apply("live", "kraken", True))

    def test_live_without_confirmation_is_refused_and_changes_nothing(self):
        with self.assertRaises(tm.TradingModeError):
            tm.apply_trading_mode(
                "live", broker="kraken", live_confirmed=False, manager=self.manager
            )
        self.assertEqual(
            tm.read_trading_settings(self.manager.settings_path).key, "paper"
        )

    def test_live_without_broker_is_refused(self):
        with self.assertRaises(tm.TradingModeError):
            tm.apply_trading_mode("live", live_confirmed=True, manager=self.manager)

    def test_confirmed_live_is_persisted_and_returned(self):
        result = tm.apply_trading_mode(
            "live",
            broker="kraken",
            live_confirmed=True,
            manager=self.manager,
        )
        self.assertEqual(result.label, "MODE: LIVE — kraken")
        self.assertEqual(
            tm.read_trading_settings(self.manager.settings_path).key, "live:kraken"
        )

    def test_going_back_to_paper_needs_no_confirmation(self):
        tm.apply_trading_mode(
            "live", broker="kraken", live_confirmed=True, manager=self.manager
        )
        result = tm.apply_trading_mode("paper", manager=self.manager)
        self.assertFalse(result.is_live)

    def test_testnet_choice_is_saved(self):
        tm.apply_trading_mode(
            "live",
            broker="binance",
            testnet=False,
            live_confirmed=True,
            manager=self.manager,
        )
        self.assertFalse(self.manager.get_testnet("binance"))


def fresh_quote(bid=99.0, ask=101.0):
    now = time.time()
    return tm.Quote(bid=bid, ask=ask, quote_ts=now, fetched_ts=now)


SIMULATE = {"paper": {"price_fallback_policy": "simulate_and_flag"}}


class PaperExchangeTests(unittest.TestCase):
    def make(self, **kwargs):
        return tm.PaperExchange(price_feed=lambda base: fresh_quote(), **kwargs)

    def test_buy_fills_at_ask_and_sell_at_bid(self):
        ex = self.make()
        buy = ex.place_order("BTC-USD", "buy", 1.0)
        self.assertEqual(
            (buy.status, buy.price, buy.exchange), ("filled", 101.0, "paper")
        )
        sell = ex.place_order("BTC-USD", "sell", 1.0)
        self.assertEqual((sell.status, sell.price), ("filled", 99.0))

    def test_balance_reports_cash_and_positions(self):
        ex = self.make()
        ex.place_order("ETH-USD", "buy", 2.0)
        bal = ex.get_balance()
        self.assertEqual(bal["ETH"], 2.0)
        self.assertLess(bal["USD"], 10000.0)

    def test_order_status_and_cancel(self):
        ex = self.make()
        order = ex.place_order("BTC-USD", "buy", 1.0)
        self.assertEqual(ex.get_order_status(order.order_id).status, "filled")
        self.assertFalse(ex.cancel_order(order.order_id))  # already filled
        with self.assertRaises(LookupError):
            ex.get_order_status("nope")

    def test_rejections_are_reported_not_raised(self):
        ex = self.make()
        result = ex.place_order("BTC-USD", "sell", 1.0)  # nothing to sell
        self.assertEqual(result.status, "rejected")

    def test_invalid_side_raises(self):
        with self.assertRaises(ValueError):
            self.make().place_order("BTC-USD", "hold", 1.0)

    def test_needs_no_credentials_and_can_simulate_when_explicitly_allowed(self):
        ex = tm.PaperExchange(settings_source=SIMULATE)  # no feed: simulator prices
        md = ex.get_market_data("BTC-USD")
        self.assertGreater(md.ask, md.bid)
        fill = ex.place_order("BTC-USD", "buy", 0.01)
        self.assertEqual((fill.status, fill.price_source), ("filled", "simulated"))

    def test_without_a_feed_nothing_fills_by_default(self):
        ex = tm.PaperExchange(settings_source={})  # default policy: pause
        result = ex.place_order("BTC-USD", "buy", 0.01)
        self.assertEqual(
            (result.status, result.reason), ("rejected", "PRICE_UNAVAILABLE")
        )

    def test_state_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "paper_account.json")
            first = self.make(state_path=path)
            first.place_order("BTC-USD", "buy", 1.0)
            cash = first.get_balance()["USD"]

            second = self.make(state_path=path)
            self.assertEqual(second.get_balance()["BTC"], 1.0)
            self.assertAlmostEqual(second.get_balance()["USD"], cash)

    def test_quote_feed_failure_is_never_silently_simulated(self):
        ex = tm.PaperExchange(price_feed=lambda base: None, settings_source={})
        self.assertEqual(ex.place_order("BTC-USD", "buy", 0.01).status, "rejected")


class TraderGateTests(unittest.TestCase):
    """The trader end-to-end, with every live HTTP path spied on."""

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

        patches = [
            mock.patch.object(self.pt_trader, "HUB_DATA_DIR", self.tmp.name),
            # nothing in these tests may use the network, public quotes included
            mock.patch.object(
                tm.urllib.request, "urlopen", side_effect=OSError("no network")
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

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

    def use_fake_quotes(self, bid=99.0, ask=101.0):
        tm.get_paper_exchange()._price_feed = lambda base: fresh_quote(bid, ask)

    # --- paper -------------------------------------------------------------

    def test_paper_mode_places_zero_live_calls_and_hits_the_paper_account(self):
        settings = copy.deepcopy(PAPER)
        with HttpSpy() as spy, mock.patch.object(
            tm.ExchangeFactory, "get_exchange"
        ) as get_exchange:
            trader = self.trader(settings)
            self.use_fake_quotes()
            response = trader.place_buy_order(
                "id", "buy", "market", "BTC-USD", 50.0, tag="TEST"
            )
            sell = trader.place_sell_order(
                "id", "sell", "market", "BTC-USD", response["quantity"], tag="TEST"
            )

        self.assertEqual(spy.calls, 0)
        get_exchange.assert_not_called()
        self.assertEqual(response["mode"], "paper")
        self.assertEqual(response["state"], "filled")
        self.assertEqual(sell["state"], "filled")
        account = tm.get_paper_exchange().account
        self.assertEqual(len(account.orders), 2)
        # paper books live in their own directory, never next to the live ones
        paper_dir = os.path.join(self.tmp.name, "paper")
        self.assertTrue(os.path.isfile(os.path.join(paper_dir, "trade_history.jsonl")))
        self.assertFalse(
            os.path.exists(os.path.join(self.tmp.name, "trade_history.jsonl"))
        )

    def test_paper_trades_update_the_ledger_and_cost_basis(self):
        trader = self.trader(copy.deepcopy(PAPER))
        self.use_fake_quotes()
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        basis = trader.calculate_cost_basis()
        self.assertAlmostEqual(basis["BTC"], 101.0 * 1.001, places=2)  # ask + 0.1% fee

    def test_manage_trades_runs_end_to_end_in_paper_mode(self):
        trader = self.trader(copy.deepcopy(PAPER))
        self.use_fake_quotes()
        with HttpSpy() as spy:
            trader.manage_trades()
        self.assertEqual(spy.calls, 0)
        status_path = os.path.join(self.tmp.name, "paper", "trader_status.json")
        with open(status_path, "r", encoding="utf-8") as f:
            status = json.load(f)
        self.assertEqual(status["trading_mode"], "paper")
        self.assertEqual(status["account"]["buying_power"], 10000.0)

    # --- refusal -----------------------------------------------------------

    def test_trader_does_not_start_in_live_mode_without_a_broker(self):
        with HttpSpy() as spy:
            with self.assertRaises(tm.LiveTradingRefused):
                self.trader(copy.deepcopy(LIVE_NO_BROKER))
        self.assertEqual(spy.calls, 0)

    def test_order_is_refused_if_settings_flip_to_live_without_a_broker(self):
        settings = copy.deepcopy(PAPER)
        trader = self.trader(settings)
        self.use_fake_quotes()
        paper_orders = tm.get_paper_exchange().account.orders
        settings["trading"].update(mode="live", active_broker=None)

        with HttpSpy() as spy, mock.patch.object(
            tm.ExchangeFactory, "get_exchange"
        ) as get_exchange, mock.patch.object(tm.urllib.request, "urlopen") as urlopen:
            buy = trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
            sell = trader.place_sell_order("id", "sell", "market", "BTC-USD", 1.0)

        self.assertIsNone(buy)
        self.assertIsNone(sell)
        self.assertEqual(spy.calls, 0)
        urlopen.assert_not_called()
        get_exchange.assert_not_called()
        self.assertEqual(len(paper_orders), 0)

    def test_order_is_refused_if_mode_changes_after_the_trader_started(self):
        settings = copy.deepcopy(PAPER)
        trader = self.trader(settings)
        self.use_fake_quotes()
        settings["trading"].update(mode="live", active_broker="kraken")
        fake_kraken = mock.MagicMock()

        with mock.patch.object(
            tm.ExchangeFactory, "get_exchange", return_value=fake_kraken
        ):
            result = trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)

        self.assertIsNone(result)
        fake_kraken.place_order.assert_not_called()  # live venue untouched
        self.assertEqual(len(tm.get_paper_exchange().account.orders), 0)

    def test_manage_trades_stands_down_when_the_mode_changed(self):
        settings = copy.deepcopy(PAPER)
        trader = self.trader(settings)
        settings["trading"].update(mode="live", active_broker="kraken")
        with mock.patch.object(self.pt_trader.time, "sleep"), mock.patch.object(
            tm.ExchangeFactory, "get_exchange"
        ) as get_exchange:
            trader.manage_trades()
        get_exchange.assert_not_called()
        self.assertFalse(
            os.path.exists(os.path.join(self.tmp.name, "paper", "trader_status.json"))
        )

    # --- live via the factory ---------------------------------------------

    def fake_kraken(self):
        balances = {"USD": 10000.0}  # keeps a $50 order inside the 1% risk limit
        exchange = mock.MagicMock(name="kraken")
        exchange.get_balance.side_effect = lambda: dict(balances)
        exchange.get_market_data.return_value = MarketData(
            symbol="BTC-USD",
            price=100.0,
            bid=99.0,
            ask=101.0,
            volume=0.0,
            timestamp=time.time(),
            exchange="kraken",
        )

        def place_order(symbol, side, amount, price=None):
            balances["USD"] -= amount * 101.0
            return OrderResult(
                order_id="k-1",
                symbol=symbol,
                side=side,
                amount=amount,
                price=101.0,
                status="filled",
                exchange="kraken",
                timestamp=time.time(),
            )

        exchange.place_order.side_effect = place_order
        return exchange

    def test_live_kraken_orders_route_through_the_exchange_factory(self):
        exchange = self.fake_kraken()
        with mock.patch.object(
            tm.ExchangeFactory, "get_exchange", return_value=exchange
        ) as get_exchange, HttpSpy() as spy:
            trader = self.trader(copy.deepcopy(LIVE_KRAKEN))
            response = trader.place_buy_order(
                "id", "buy", "market", "BTC-USD", 50.0, tag="TEST"
            )

        get_exchange.assert_called_with(ExchangeType.KRAKEN)
        self.assertEqual(spy.calls, 0)
        exchange.place_order.assert_called_once()
        args = exchange.place_order.call_args[0]
        self.assertEqual(args[:2], ("BTC-USD", "buy"))
        self.assertEqual(response["mode"], "live:kraken")
        # live books are in the base directory, not paper/
        self.assertTrue(
            os.path.isfile(os.path.join(self.tmp.name, "trade_history.jsonl"))
        )
        self.assertFalse(os.path.isdir(os.path.join(self.tmp.name, "paper")))

    def test_broker_without_order_support_fails_cleanly_with_no_trade_recorded(self):
        exchange = self.fake_kraken()
        exchange.place_order.side_effect = NotImplementedError("not yet")
        with mock.patch.object(
            tm.ExchangeFactory, "get_exchange", return_value=exchange
        ):
            trader = self.trader(copy.deepcopy(LIVE_KRAKEN))
            result = trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        self.assertIsNone(result)
        self.assertFalse(
            os.path.exists(os.path.join(self.tmp.name, "trade_history.jsonl"))
        )

    def test_unconfirmed_order_stays_pending_for_reconciliation(self):
        exchange = self.fake_kraken()

        def place_order(symbol, side, amount, price=None):
            return OrderResult("k-2", symbol, side, 0.0, 0.0, "new", "kraken", 0.0)

        exchange.place_order.side_effect = place_order
        exchange.get_order_status.side_effect = lambda oid: OrderResult(
            oid, "BTC-USD", "buy", 0.0, 0.0, "new", "kraken", 0.0
        )
        with mock.patch.object(
            tm.ExchangeFactory, "get_exchange", return_value=exchange
        ):
            trader = self.trader(copy.deepcopy(LIVE_KRAKEN))
            trader._order_wait_seconds = 0.05
            result = trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        self.assertIsNone(result)
        self.assertIn("k-2", trader._pnl_ledger["pending_orders"])

    # --- local-history helpers --------------------------------------------

    def test_dca_stages_are_rebuilt_from_local_history(self):
        trader = self.trader(copy.deepcopy(PAPER))
        self.use_fake_quotes()
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)  # entry
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0, tag="DCA")
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0, tag="DCA")
        trader.dca_levels_triggered = {}
        trader.initialize_dca_levels()
        self.assertEqual(trader.dca_levels_triggered["BTC"], [0, 1])

    # --- no direct broker access ------------------------------------------

    def test_no_direct_broker_rest_calls_remain_in_the_trader(self):
        with open(self.pt_trader.__file__, "r", encoding="utf-8") as f:
            source = f.read().lower()
        for needle in (
            "robinhood",
            "/api/v1/crypto",
            "import requests",
            "requests.get",
            "requests.post",
            "make_api_request",
            "x-signature",
        ):
            self.assertNotIn(needle, source, needle)


class UiHelperTests(unittest.TestCase):
    def test_pack_at_top_ignores_the_unpacked_menu_bar(self):
        import tkinter as tk

        from trading_mode_ui import pack_at_top

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display available")
        self.addCleanup(root.destroy)
        root.withdraw()
        root.config(menu=tk.Menu(root))  # first child, never packed
        body = tk.Frame(root)
        body.pack(fill="both", expand=True)
        strip = tk.Frame(root)
        pack_at_top(strip, root)
        self.assertEqual(root.pack_slaves()[0], strip)

    def test_live_cannot_be_applied_until_broker_chosen_and_risk_confirmed(self):
        import tkinter as tk

        from trading_mode_ui import TradingModeDialog

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display available")
        self.addCleanup(root.destroy)
        root.withdraw()

        applied = []

        def fake_apply(mode, broker=None, testnet=None, live_confirmed=False):
            applied.append((mode, broker, live_confirmed))
            return tm.read_trading_settings(LIVE_KRAKEN)

        dialog = TradingModeDialog(
            root,
            current=tm.read_trading_settings(PAPER),
            brokers=["kraken", "binance"],
            on_applied=lambda s: applied.append(("applied", s.label)),
            apply_fn=fake_apply,
        )
        self.assertEqual(str(dialog.apply_btn.cget("state")), "normal")  # paper

        dialog.mode_var.set("live")
        dialog._refresh()
        self.assertEqual(str(dialog.apply_btn.cget("state")), "disabled")  # no broker

        dialog.broker_var.set("kraken")
        dialog._refresh()
        self.assertEqual(str(dialog.apply_btn.cget("state")), "disabled")  # unconfirmed
        self.assertEqual(dialog.confirm_cb.cget("text"), tm.LIVE_CONFIRM_TEXT)

        dialog.confirm_var.set(True)
        dialog._refresh()
        self.assertEqual(str(dialog.apply_btn.cget("state")), "normal")
        dialog._apply()
        self.assertEqual(applied[0], ("live", "kraken", True))
        self.assertEqual(applied[1], ("applied", "MODE: LIVE — kraken"))

        # flipping back to paper clears the confirmation again
        dialog2 = TradingModeDialog(
            root,
            current=tm.read_trading_settings(LIVE_KRAKEN),
            brokers=["kraken"],
            on_applied=lambda s: None,
            apply_fn=fake_apply,
        )
        self.assertFalse(dialog2.confirm_var.get())
        self.assertEqual(str(dialog2.apply_btn.cget("state")), "disabled")
        dialog2.destroy()

    def test_indicator_text_follows_the_settings(self):
        import tkinter as tk

        from trading_mode_ui import TradingModeIndicator

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display available")
        self.addCleanup(root.destroy)
        root.withdraw()
        indicator = TradingModeIndicator(root, tm.read_trading_settings(PAPER))
        self.assertEqual(indicator.cget("text"), "MODE: PAPER")
        indicator.update_settings(tm.read_trading_settings(LIVE_KRAKEN))
        self.assertEqual(indicator.cget("text"), "MODE: LIVE — kraken")


if __name__ == "__main__":
    unittest.main()
