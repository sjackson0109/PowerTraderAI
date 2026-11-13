"""FDS-121 section 7: SignalEngine and the trader's catalogue integration (no network)."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd
from helpers import Feed, PaperTraderCase, make_candles

import signal_engine as se
import trading_mode as tm
from market_data.candles import CandleDataError
from pt_settings_manager import SettingsManager
from signal_engine import SignalEngine
from strategies.base import Action
from strategies.factory import build_runner
from strategies.settings import ENGINES, read_strategy_settings

HOUR = pd.Timedelta(hours=1)
PAPER = {
    "trading": {"mode": "paper"},
    "strategy": {"active_id": "STRAT-000"},
}  # engine/trader tests pin the simple baseline strategy


def trend_series():
    """down 150 bars, sharp rally 40, long fall 70 -> one golden cross, later one death cross (SYNTHETIC)."""
    down = np.linspace(200, 150, 150)
    up = np.linspace(150, 240, 40)
    fall = np.linspace(240, 110, 70)
    return np.concatenate([down, up, fall])


def expected_actions(frame, active="STRAT-000"):
    """Decisions of the same runner replayed bar by bar (flat -> long -> flat)."""
    runner = build_runner(active)
    pos, out = None, []
    for i in range(len(frame)):
        d = runner.evaluate(runner.window(frame, i), pos, "BTC")
        if d.action is Action.ENTER_LONG and pos is None:
            pos = runner.open_position("BTC", frame["close"].iloc[i], d.bar_time, frame)
            out.append((i, "ENTER"))
        elif d.action is Action.EXIT_LONG and pos is not None:
            pos = None
            out.append((i, "EXIT"))
    return out


class SettingsReaderTests(unittest.TestCase):
    def test_defaults(self):
        s = read_strategy_settings({})
        self.assertEqual(
            (s.engine, s.active_id, s.timeframe),
            ("catalogue", "STRAT-001", "1h"),
        )
        self.assertIsNone(s.problem)
        self.assertEqual(s.note, "SIGNALS: STRAT-001 1h")

    def test_unknown_engine_is_a_problem_not_a_fallback(self):
        s = read_strategy_settings({"strategy": {"engine": "magic"}})
        self.assertIn("unknown strategy.engine", s.problem)
        self.assertEqual(s.engine, "magic")
        self.assertEqual(s.note, "SIGNALS: BLOCKED")

    def test_unknown_strategy_id_is_a_problem(self):
        for bad in ("STRAT-999", "", None, 5, ["STRAT-000"]):
            s = read_strategy_settings({"strategy": {"active_id": bad}})
            self.assertIn("unknown strategy.active_id", s.problem, bad)

    def test_bad_timeframe_and_overlays_are_problems(self):
        self.assertIn(
            "timeframe",
            read_strategy_settings({"strategy": {"timeframe": "7m"}}).problem,
        )
        self.assertIn(
            "overlay",
            read_strategy_settings(
                {"strategy": {"overlays": [{"id": "OVL-NOPE"}]}}
            ).problem,
        )
        self.assertIn(
            "overlays", read_strategy_settings({"strategy": {"overlays": "x"}}).problem
        )

    def test_a_main_strategy_id_is_not_an_overlay(self):
        s = read_strategy_settings({"strategy": {"overlays": [{"id": "STRAT-000"}]}})
        self.assertIn("unknown overlay", s.problem)

    def test_legacy_engine_ignores_catalogue_settings(self):
        s = read_strategy_settings(
            {
                "strategy": {
                    "engine": "legacy_neural",
                    "active_id": "nope",
                    "timeframe": "7m",
                }
            }
        )
        self.assertIsNone(s.problem)
        self.assertEqual(s.note, "SIGNALS: LEGACY (UNTRAINED)")

    def test_a_strategy_symbols_left_in_an_older_file_is_ignored(self):
        # the coins traded are the coins in Settings (paper: the paper-trading
        # coins), not a strategy setting; an old BTC-only list must not block or
        # limit anything
        for old in (["BTC"], [], [1], "BTC"):
            s = read_strategy_settings({"strategy": {"symbols": old}})
            self.assertIsNone(s.problem, old)
            self.assertFalse(hasattr(s, "symbols"))

    def test_signature_changes_with_strategy_overlays_and_timeframe(self):
        a = read_strategy_settings({}).signature
        self.assertNotEqual(
            a, read_strategy_settings({"strategy": {"timeframe": "4h"}}).signature
        )
        self.assertEqual(a, read_strategy_settings({}).signature)

    def test_engines_constant(self):
        self.assertEqual(ENGINES, ("catalogue", "legacy_neural"))


class SettingsManagerTests(unittest.TestCase):
    def test_defaults_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            m = SettingsManager("pt_config.json", d)
            self.assertEqual(m.get("strategy.engine"), "catalogue")
            self.assertEqual(m.get("strategy.active_id"), "STRAT-001")
            self.assertIsNone(m.get("strategy.symbols"))  # no longer a setting
            self.assertEqual(m.get("strategy.timeframe"), "1h")
            self.assertEqual(m.get("strategy.overlays"), [])
            self.assertTrue(m.set("strategy.engine", "legacy_neural"))
            m.save_settings()
            self.assertEqual(
                SettingsManager("pt_config.json", d).get("strategy.engine"),
                "legacy_neural",
            )
            self.assertEqual(
                read_strategy_settings(m.settings_path).engine, "legacy_neural"
            )

    def test_invalid_values_are_rejected_on_set(self):
        with tempfile.TemporaryDirectory() as d:
            m = SettingsManager("pt_config.json", d)
            self.assertFalse(m.set("strategy.engine", "magic"))
            self.assertFalse(m.set("strategy.timeframe", "7m"))
            self.assertEqual(m.get("strategy.engine"), "catalogue")

    def test_a_bad_value_on_disk_is_kept_and_blocks_trading_rather_than_being_fixed(
        self,
    ):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "pt_config.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"strategy": {"engine": "magic"}}, f)
            m = SettingsManager("pt_config.json", d)
            self.assertEqual(m.get("strategy.engine"), "magic")
            self.assertIn(
                "unknown strategy.engine", read_strategy_settings(path).problem
            )


class LateFeed(Feed):
    """``Feed`` whose exchange publishes each bar in ``late`` only ``delay`` seconds
    after it closes (every bar when ``late`` is None)."""

    def __init__(self, frame, delay, late=None):
        super().__init__(frame)
        self.delay = pd.Timedelta(seconds=delay)
        self.late = late

    def provider(self, symbol, tf, n, now):
        self.calls += 1
        close = self.frame["open_time"] + HOUR
        is_late = (
            pd.Series(True, index=self.frame.index)
            if self.late is None
            else self.frame.index.to_series().isin(self.late)
        )
        published = close.where(~is_late, close + self.delay)
        return self.frame[published <= now].tail(n).reset_index(drop=True)


class LateBarTests(unittest.TestCase):
    """An exchange that publishes the bar that just closed a few seconds late
    (STRAT-004 paper readiness, D1): the engine fetches again after
    ``FETCH_RETRY_SECONDS`` and decides that bar, instead of keeping the frame
    without it as current until the next bar closes."""

    def setUp(self):
        self.frame = make_candles(trend_series())

    def index_of(self, bar_time):
        return int(self.frame.index[self.frame["open_time"] == bar_time][0])

    def test_a_late_bar_is_decided_within_the_retry_interval(self):
        feed = LateFeed(self.frame, delay=20)
        engine = SignalEngine(PAPER, feed.provider, feed.clock)
        feed.set_after_bar(200)  # 10 s after the close: bar 200 is not published yet
        self.assertEqual(self.index_of(engine.decide("BTC").bar_time), 199)
        feed.now += se.FETCH_RETRY_SECONDS + 1
        self.assertEqual(self.index_of(engine.decide("BTC").bar_time), 200)
        self.assertEqual(feed.calls, 2)
        for _ in range(5):  # current now: no more fetches until bar 201 closes
            engine.decide("BTC")
        self.assertEqual(feed.calls, 2)

    def test_an_exchange_that_never_publishes_is_asked_at_most_every_interval(self):
        feed = LateFeed(self.frame, delay=10**9, late=[200])
        engine = SignalEngine(PAPER, feed.provider, feed.clock)
        feed.set_after_bar(200)
        for _ in range(5):
            engine.decide("BTC")
        self.assertEqual(feed.calls, 1)
        feed.now += se.FETCH_RETRY_SECONDS - 1
        engine.decide("BTC")
        self.assertEqual(feed.calls, 1)
        feed.now += 2
        self.assertEqual(self.index_of(engine.decide("BTC").bar_time), 199)
        self.assertEqual(feed.calls, 2)

    def test_a_bar_late_once_is_still_decided_as_the_backtester_would(self):
        want = expected_actions(self.frame)
        enter = want[0][0]
        feed = LateFeed(self.frame, delay=20, late=[enter])
        engine = SignalEngine(PAPER, feed.provider, feed.clock)
        seen, pos = [], None
        for k in range(len(self.frame)):
            feed.set_after_bar(k)
            for wait in (0, se.FETCH_RETRY_SECONDS + 1):
                feed.now += wait
                d = engine.decide("BTC", pos)
                if d.action is Action.ENTER_LONG and pos is None:
                    i = self.index_of(d.bar_time)
                    pos = engine.record_entry(
                        "BTC", self.frame["close"].iloc[i], d.bar_time
                    )
                    seen.append((i, "ENTER"))
                elif d.action is Action.EXIT_LONG and pos is not None:
                    i = self.index_of(d.bar_time)
                    engine.record_exit("BTC", self.frame["close"].iloc[i], d.bar_time)
                    pos = None
                    seen.append((i, "EXIT"))
        self.assertEqual(seen, want)

    def test_an_entry_gates_late_context_bar_is_fetched_again(self):
        feed = LateFeed(self.frame, delay=20)
        engine = SignalEngine(PAPER, feed.provider, feed.clock)
        feed.set_after_bar(200)
        now = pd.Timestamp(feed.now, unit="s", tz="UTC")
        first = engine._context_candles("BTC-USD", "1h", 50, now)
        self.assertEqual(self.index_of(first["open_time"].iloc[-1]), 199)
        later = now + pd.Timedelta(seconds=se.FETCH_RETRY_SECONDS + 1)
        feed.now = later.timestamp()
        second = engine._context_candles("BTC-USD", "1h", 50, later)
        self.assertEqual(self.index_of(second["open_time"].iloc[-1]), 200)
        self.assertEqual(feed.calls, 2)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.frame = make_candles(trend_series())
        self.feed = Feed(self.frame)
        self.engine = SignalEngine(PAPER, self.feed.provider, self.feed.clock)

    def test_decision_is_for_the_latest_closed_bar_and_is_logged_once(self):
        self.feed.set_after_bar(200)
        with mock.patch.object(se.logger, "info") as info:
            d1 = self.engine.decide("BTC")
            d2 = self.engine.decide("BTC")
        self.assertEqual(d1.bar_time, self.frame["open_time"].iloc[200])
        self.assertEqual(d1, d2)
        decision_logs = [c for c in info.call_args_list if "Decision BTC" in str(c)]
        self.assertEqual(len(decision_logs), 1)
        text = str(decision_logs[0])
        for part in ("strategy=STRAT-000", "reason=", "bar=", "indicators=", "action="):
            self.assertIn(part, text)

    def test_candles_are_fetched_only_when_a_new_bar_has_closed(self):
        self.feed.set_after_bar(200)
        for _ in range(5):
            self.engine.decide("BTC")
        self.assertEqual(self.feed.calls, 1)
        self.feed.set_after_bar(201)
        self.engine.decide("BTC")
        self.assertEqual(self.feed.calls, 2)

    def test_forming_bar_is_never_evaluated_even_if_a_provider_returns_it(self):
        def greedy(symbol, tf, n, now):
            return self.frame.iloc[:211]  # includes a bar that has not closed yet

        engine = SignalEngine(PAPER, greedy, self.feed.clock)
        self.feed.set_after_bar(209)  # bars up to 209 are closed; 210 is still forming
        d = engine.decide("BTC")
        self.assertEqual(d.bar_time, self.frame["open_time"].iloc[209])

    def stuck_engine(self, hours_behind):
        """A feed that stopped updating at bar 200 while the clock moved on."""
        old = self.frame.iloc[:201]
        feed = Feed(self.frame)
        feed.set_after_bar(200, seconds_after_close=0)
        feed.now += hours_behind * 3600
        return SignalEngine(PAPER, lambda s, tf, n, now: old, feed.clock)

    def test_stale_candles_hold_and_warn(self):
        engine = self.stuck_engine(
            hours_behind=3
        )  # last closed bar is 3 h old > 2x the 1 h timeframe
        with mock.patch.object(se.logger, "warning") as warn:
            d = engine.decide("BTC")
        self.assertEqual((d.action, d.reason), (Action.HOLD, "STALE_CANDLES"))
        self.assertIn("stale", str(warn.call_args_list))

    def test_candles_up_to_two_timeframes_old_are_still_used(self):
        engine = self.stuck_engine(hours_behind=2)  # exactly 2x: allowed
        self.assertNotEqual(engine.decide("BTC").reason, "STALE_CANDLES")
        just_over = self.stuck_engine(hours_behind=2.01)
        self.assertEqual(just_over.decide("BTC").reason, "STALE_CANDLES")

    def test_no_candles_means_hold(self):
        self.feed.set_after_bar(200)
        engine = SignalEngine(PAPER, lambda *a: pd.DataFrame(), self.feed.clock)
        d = engine.decide("BTC")
        self.assertEqual((d.action, d.reason), (Action.HOLD, "CANDLES_UNAVAILABLE"))

    def test_fetch_failures_hold_warn_and_recover(self):
        self.feed.set_after_bar(200)
        self.feed.fail = CandleDataError("exchange down")
        with mock.patch.object(se.logger, "warning") as warn:
            d = self.engine.decide("BTC")
        self.assertEqual(d.reason, "CANDLES_UNAVAILABLE")
        self.assertIn("exchange down", str(warn.call_args_list))
        self.feed.fail = None
        self.feed.now += se.FETCH_RETRY_SECONDS + 1
        self.assertNotEqual(self.engine.decide("BTC").reason, "CANDLES_UNAVAILABLE")

    def test_retries_are_rate_limited(self):
        self.feed.set_after_bar(200)
        self.feed.fail = CandleDataError("down")
        self.engine.decide("BTC")
        self.engine.decide("BTC")
        self.assertEqual(self.feed.calls, 1)

    def test_every_coin_gets_a_decision_whatever_an_old_strategy_symbols_says(self):
        engine = SignalEngine(
            {**PAPER, "strategy": {"active_id": "STRAT-000", "symbols": ["BTC"]}},
            self.feed.provider,
            self.feed.clock,
        )
        self.feed.set_after_bar(200)
        self.assertIsNotNone(engine.decide("ETH"))
        self.assertEqual(self.feed.calls, 1)

    def test_legacy_engine_makes_no_decisions(self):
        engine = SignalEngine(
            {"strategy": {"engine": "legacy_neural"}},
            self.feed.provider,
            self.feed.clock,
        )
        self.feed.set_after_bar(200)
        self.assertIsNone(engine.decide("BTC"))
        self.assertIsNone(engine.block_reason())

    def test_unknown_strategy_blocks_and_logs_an_error(self):
        engine = SignalEngine(
            {"strategy": {"active_id": "STRAT-999"}},
            self.feed.provider,
            self.feed.clock,
        )
        with mock.patch.object(se.logger, "error") as err:
            self.assertIsNone(engine.decide("BTC"))
        self.assertIn("STRAT-999", str(err.call_args_list))
        self.assertIn("STRAT-999", engine.block_reason())
        self.assertEqual(self.feed.calls, 0)

    def test_the_engine_replays_exactly_what_the_backtester_would_decide(self):
        want = expected_actions(self.frame)
        self.assertEqual(
            [a for _, a in want], ["ENTER", "EXIT"], "fixture must cross up then down"
        )
        seen, pos = [], None
        for k in range(len(self.frame)):
            self.feed.set_after_bar(k)
            d = self.engine.decide("BTC", pos)
            if d.action is Action.ENTER_LONG and pos is None:
                pos = self.engine.record_entry(
                    "BTC", self.frame["close"].iloc[k], d.bar_time
                )
                seen.append((k, "ENTER"))
            elif d.action is Action.EXIT_LONG and pos is not None:
                self.engine.record_exit("BTC", self.frame["close"].iloc[k], d.bar_time)
                pos = None
                seen.append((k, "EXIT"))
        self.assertEqual(seen, want)

    def test_settings_change_rebuilds_the_runner(self):
        settings = {"strategy": {"timeframe": "1h"}}
        engine = SignalEngine(settings, self.feed.provider, self.feed.clock)
        self.feed.set_after_bar(200)
        engine.decide("BTC")
        first = engine._runner
        engine.decide("BTC")
        self.assertIs(engine._runner, first)
        settings["strategy"]["timeframe"] = "4h"
        engine.decide("BTC")
        self.assertIsNot(engine._runner, first)

    def test_position_bookkeeping(self):
        self.feed.set_after_bar(200)
        self.engine.decide("BTC")
        pos = self.engine.record_entry("btc", 150.0, self.frame["open_time"].iloc[200])
        self.assertIs(self.engine.position("BTC"), pos)
        self.assertIs(self.engine.ensure_position("BTC", 1.0), pos)
        self.engine.forget("BTC")
        self.assertIsNone(self.engine.position("BTC"))
        self.engine.record_entry("BTC", 150.0, self.frame["open_time"].iloc[200])
        self.engine.record_exit("BTC", 151.0, self.frame["open_time"].iloc[201])
        self.assertIsNone(self.engine.position("BTC"))


class TraderIntegrationTests(PaperTraderCase):
    def setUp(self):
        super().setUp()
        self.frame = make_candles(trend_series())
        self.feed = Feed(self.frame)
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        # one coin in Settings: these tests follow one coin through the trader
        coins = mock.patch.object(self.pt_trader, "crypto_symbols", ["BTC"])
        coins.start()
        self.addCleanup(coins.stop)

    def catalogue_trader(self, settings=None):
        settings = settings if settings is not None else copy.deepcopy(PAPER)
        engine = SignalEngine(settings, self.feed.provider, self.feed.clock)
        self.feed.set_after_bar(150)
        trader = self.pt_trader.CryptoAPITrading(
            settings_source=settings, signal_engine=engine
        )
        trader._order_poll_seconds = 0.0
        return trader

    def orders(self):
        return list(tm.get_paper_exchange().account.orders.values())

    def test_scripted_candles_drive_one_enter_and_one_exit_through_the_trader_into_paper(
        self,
    ):
        want = expected_actions(self.frame)
        (enter_bar, _), (exit_bar, _) = want
        trader = self.catalogue_trader()
        acted = {}
        for k in range(150, len(self.frame)):
            self.feed.set_after_bar(k)
            before = len(self.orders())
            trader.manage_trades()
            if len(self.orders()) > before:
                acted[k] = self.orders()[-1].side.value

        self.assertEqual(acted, {enter_bar: "buy", exit_bar: "sell"})
        orders = self.orders()
        self.assertEqual([o.side.value for o in orders], ["buy", "sell"])
        self.assertEqual({o.symbol for o in orders}, {"BTC"})
        self.assertEqual([o.status.value for o in orders], ["filled", "filled"])
        rows = self.ledger_rows()
        self.assertEqual([r["tag"] for r in rows], ["ENTRY", "EXIT:strategy"])
        self.assertIsNone(trader.signal_engine.position("BTC"))
        self.assertNotIn("BTC", tm.get_paper_exchange().get_balance())  # flat again
        self.assertEqual(trader._pnl_ledger["open_positions"], {})

    def test_every_decision_is_logged_with_strategy_reason_indicators_and_bar_time(
        self,
    ):
        trader = self.catalogue_trader()
        with mock.patch.object(se.logger, "info") as info:
            for k in range(150, 200):
                self.feed.set_after_bar(k)
                trader.manage_trades()
        decisions = [str(c) for c in info.call_args_list if "Decision BTC" in str(c)]
        self.assertGreaterEqual(len(decisions), 40)
        self.assertTrue(
            all(
                "strategy=STRAT-000" in d
                and "bar=" in d
                and "indicators=" in d
                and "reason=" in d
                for d in decisions
            )
        )

    def test_legacy_dca_and_trailing_pm_are_off_in_catalogue_mode(self):
        trader = self.catalogue_trader()
        for k in range(150, len(self.frame)):
            self.feed.set_after_bar(k)
            trader.manage_trades()
        tags = {r["tag"] for r in self.ledger_rows()}
        self.assertEqual(tags, {"ENTRY", "EXIT:strategy"})  # no DCA / TRAIL_SELL

    def test_unknown_strategy_id_places_no_orders_and_logs_an_error(self):
        settings = {
            "trading": {"mode": "paper"},
            "strategy": {"active_id": "STRAT-999"},
        }
        trader = self.catalogue_trader(settings)
        with mock.patch.object(se.logger, "error") as engine_err, mock.patch.object(
            self.pt_trader.logger, "error"
        ) as trader_err:
            for k in range(150, 230):
                self.feed.set_after_bar(k)
                trader.manage_trades()
            direct_buy = trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
            direct_sell = trader.place_sell_order(
                "id", "sell", "market", "BTC-USD", 0.01
            )
        self.assertEqual(self.orders(), [])
        self.assertIsNone(direct_buy)
        self.assertIsNone(direct_sell)
        self.assertEqual(self.ledger_rows(), [])
        self.assertTrue(engine_err.called or trader_err.called)
        self.assertIn(
            "STRAT-999", str(engine_err.call_args_list) + str(trader_err.call_args_list)
        )

    def test_unknown_engine_places_no_orders_and_logs_an_error(self):
        settings = {"trading": {"mode": "paper"}, "strategy": {"engine": "skynet"}}
        trader = self.catalogue_trader(settings)
        with mock.patch.object(
            self.pt_trader.logger, "error"
        ) as trader_err, mock.patch.object(
            self.pt_trader.logger, "warning"
        ) as trader_warn:
            for k in range(150, 230):
                self.feed.set_after_bar(k)
                trader.manage_trades()
            self.assertIsNone(
                trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
            )
        self.assertEqual(self.orders(), [])
        self.assertIn(
            "skynet", str(trader_err.call_args_list) + str(trader_warn.call_args_list)
        )

    def test_legacy_engine_does_not_use_the_catalogue(self):
        settings = {
            "trading": {"mode": "paper"},
            "strategy": {"engine": "legacy_neural"},
        }
        trader = self.catalogue_trader(settings)
        for k in range(150, 230):
            self.feed.set_after_bar(k)
            trader.manage_trades()
        self.assertEqual(self.feed.calls, 0)  # no candles requested for signals
        self.assertEqual(
            self.orders(), []
        )  # no neural signal files -> legacy start gate stays shut
        with open(os.path.join(self.tmp.name, "paper", "trader_status.json")) as f:
            signals = json.load(f)["signals"]
        self.assertEqual(signals["engine"], "legacy_neural")
        self.assertEqual(signals["note"], "SIGNALS: LEGACY (UNTRAINED)")

    def test_a_position_the_trader_did_not_open_is_never_sold_by_the_strategy(self):
        trader = self.catalogue_trader()
        # BTC bought outside the trader (no ledger entry)
        self.feed.set_after_bar(150)
        tm.get_paper_exchange()._price_feed = lambda base: tm.Quote(
            99.0, 101.0, __import__("time").time(), __import__("time").time()
        )
        tm.get_paper_exchange().place_order("BTC-USD", "buy", 0.01)
        before = len(self.orders())
        for k in range(150, len(self.frame)):
            self.feed.set_after_bar(k)
            trader.manage_trades()
        self.assertEqual(
            len(self.orders()), before
        )  # only the outside buy; no strategy sell

    def test_exit_sells_only_what_the_ledger_says_the_trader_bought(self):
        trader = self.catalogue_trader()
        trader._pnl_ledger["open_positions"] = {"BTC": {"usd_cost": 100.0, "qty": 0.5}}
        self.assertEqual(trader._catalogue_exit_quantity("BTC", 2.0), 0.5)
        self.assertEqual(trader._catalogue_exit_quantity("BTC", 0.25), 0.25)
        self.assertEqual(trader._catalogue_exit_quantity("ETH", 2.0), 0.0)

    def test_the_cooldown_counts_from_the_bar_the_sale_filled_in(self):
        """As the backtester counts it: a sale decided at bar k's close fills at bar
        k + 1's open, so with 3 bars after an exit, decisions on bars k + 1 to k + 3
        are blocked and bar k + 4's may enter (not bar k + 3's)."""
        settings = copy.deepcopy(PAPER)
        settings["strategy"]["overlays"] = [
            {
                "id": "OVL-COOLDOWN",
                "params": {"bars_after_exit": 3, "bars_after_loss": 0},
            }
        ]
        (_, _), (exit_bar, _) = expected_actions(self.frame)
        trader = self.catalogue_trader(settings)
        for k in range(150, exit_bar + 1):
            self.feed.set_after_bar(k)
            trader.manage_trades()
        self.assertEqual([o.side.value for o in self.orders()], ["buy", "sell"])
        (cooldown,) = [
            o
            for o in trader.signal_engine._runner.overlays
            if o.overlay_id == "OVL-COOLDOWN"
        ]
        times = self.frame["open_time"]
        self.assertEqual(cooldown._last["BTC"][0], times.iloc[exit_bar + 1])
        self.assertFalse(cooldown.allow_entry("BTC", times.iloc[exit_bar + 3]).allowed)
        self.assertTrue(cooldown.allow_entry("BTC", times.iloc[exit_bar + 4]).allowed)

    def test_status_reports_the_signal_source_and_last_decision(self):
        trader = self.catalogue_trader()
        self.feed.set_after_bar(200)
        trader.manage_trades()
        with open(os.path.join(self.tmp.name, "paper", "trader_status.json")) as f:
            signals = json.load(f)["signals"]
        self.assertEqual(
            (signals["engine"], signals["strategy_id"], signals["timeframe"]),
            ("catalogue", "STRAT-000", "1h"),
        )
        self.assertIsNone(signals["blocked"])
        self.assertIn("BTC", signals["last_decisions"])

    def test_status_shows_a_strategy_that_cannot_trade(self):
        """STRAT-003 with no model (FDS-MDL Phase 3): no orders, and the status says
        why instead of showing the signals as active."""
        settings = copy.deepcopy(PAPER)
        settings["strategy"]["active_id"] = "STRAT-003"
        trader = self.catalogue_trader(settings)
        self.feed.set_after_bar(200)
        trader.manage_trades()
        with open(os.path.join(self.tmp.name, "paper", "trader_status.json")) as f:
            signals = json.load(f)["signals"]
        self.assertIn("needs a trained model", signals["blocked"])
        self.assertEqual(signals["note"], "SIGNALS: BLOCKED")
        self.assertEqual(self.orders(), [])

    def test_status_shows_a_strategy_not_cleared_for_the_trading_mode(self):
        """A research-only strategy in paper: every order is refused, and the status
        says so instead of reporting nothing blocked."""
        settings = copy.deepcopy(PAPER)
        settings["strategy"]["active_id"] = "STRAT-005"
        settings["strategy"]["timeframe"] = "1d"  # its own: only the mode is wrong
        trader = self.catalogue_trader(settings)
        self.feed.set_after_bar(200)
        trader.manage_trades()
        with open(os.path.join(self.tmp.name, "paper", "trader_status.json")) as f:
            signals = json.load(f)["signals"]
        self.assertIsNotNone(signals["blocked"])
        self.assertIn("STRAT-005", signals["blocked"])
        self.assertIn("paper", signals["blocked"])
        self.assertEqual(signals["note"], "SIGNALS: BLOCKED")
        self.assertEqual(self.orders(), [])

    def test_the_strategy_config_is_rechecked_on_every_order(self):
        settings = copy.deepcopy(PAPER)
        trader = self.catalogue_trader(settings)
        self.assertIsNotNone(
            trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        )
        settings["strategy"] = {"active_id": "STRAT-999"}  # edited while running
        self.assertIsNone(
            trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        )
        self.assertEqual(len(self.orders()), 1)


class HubNoteTests(unittest.TestCase):
    def test_indicator_shows_the_signal_source(self):
        import tkinter as tk

        from trading_mode_ui import TradingModeIndicator

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display available")
        self.addCleanup(root.destroy)
        root.withdraw()
        ind = TradingModeIndicator(root, tm.read_trading_settings(PAPER))
        ind.update_signals_note(
            read_strategy_settings({"strategy": {"engine": "legacy_neural"}}).note
        )
        self.assertEqual(ind.cget("text"), "SIGNALS: LEGACY (UNTRAINED)")
        ind.update_signals_note(read_strategy_settings({}).note)
        self.assertEqual(ind.cget("text"), "SIGNALS: STRAT-001 1h")
        live = tm.read_trading_settings(
            {"trading": {"mode": "live", "active_broker": "kraken"}}
        )
        ind.update_settings(live)
        ind.update_signals_note("SIGNALS: LEGACY (UNTRAINED)")
        self.assertEqual(
            ind.cget("text"), "MODE: LIVE — Kraken · SIGNALS: LEGACY (UNTRAINED)"
        )


if __name__ == "__main__":
    unittest.main()
