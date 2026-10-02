"""FDS-096b: every paper fill's price has explicit, recorded provenance."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from helpers import FakeBinance, PaperTraderCase

import pt_settings_manager as psm
import trading_mode as tm
from pt_settings_manager import SettingsManager
from trading_mode_ui import price_note

PAUSE = {"trading": {"mode": "paper"}}  # policy absent -> default "pause"
SIM = {"trading": {"mode": "paper"}, "paper": {"price_fallback_policy": "simulate_and_flag"}}


def spy_warnings():
    """Capture WARNING-level log calls made by trading_mode and pt_trader."""
    import pt_trader

    return mock.patch.object(tm.logger, "warning"), mock.patch.object(
        pt_trader.logger, "warning"
    )


class QuoteClassificationTests(unittest.TestCase):
    def quote(self, age):
        now = time.time()
        return tm.Quote(bid=1.0, ask=2.0, quote_ts=now - age, fetched_ts=now)

    def test_fresh_quote_is_live(self):
        self.assertEqual(tm.classify_quote(self.quote(1.0), 30, time.time()), "live")

    def test_quote_older_than_max_age_is_stale(self):
        self.assertEqual(tm.classify_quote(self.quote(31.0), 30, time.time()), "stale")

    def test_quote_exactly_at_max_age_is_still_live(self):
        q = tm.Quote(bid=1, ask=2, quote_ts=100.0, fetched_ts=130.0)
        self.assertEqual(tm.classify_quote(q, 30, 130.0), "live")

    def test_unknown_age_is_stale_and_no_quote_is_simulated(self):
        q = tm.Quote(bid=1, ask=2, quote_ts=None, fetched_ts=time.time())
        self.assertEqual(tm.classify_quote(q, 30, time.time()), "stale")
        self.assertEqual(tm.classify_quote(None, 30, time.time()), "simulated")

    def test_quote_fetched_long_ago_is_stale_even_if_its_own_age_was_small(self):
        q = tm.Quote(bid=1, ask=2, quote_ts=1000.0, fetched_ts=1000.0)
        self.assertEqual(tm.classify_quote(q, 30, 1100.0), "stale")

    def test_age_s_is_fetched_minus_quote_ts(self):
        q = tm.Quote(bid=1, ask=2, quote_ts=100.0, fetched_ts=107.5)
        self.assertEqual(q.age_s, 7.5)


class PolicySettingTests(unittest.TestCase):
    def test_default_and_explicit_values(self):
        self.assertEqual(tm.read_paper_settings({}).price_fallback_policy, "pause")
        self.assertEqual(tm.read_paper_settings({}).max_quote_age_s, 30.0)
        self.assertEqual(
            tm.read_paper_settings(SIM).price_fallback_policy, "simulate_and_flag"
        )

    def test_invalid_policy_resolves_to_pause_and_is_logged(self):
        for bad in ("SIMULATE", "simulate", "", "true", 1, True, ["pause"], "pause "):
            with self.subTest(bad=bad), mock.patch.object(tm.logger, "warning") as warn:
                got = tm.read_paper_settings({"paper": {"price_fallback_policy": bad}})
                self.assertEqual(got.price_fallback_policy, "pause")
                warn.assert_called()

    def test_invalid_max_age_resolves_to_default(self):
        for bad in (0, -5, "30", None, True, float("nan"), 99999):
            got = tm.read_paper_settings({"paper": {"max_quote_age_s": bad}})
            self.assertEqual(got.max_quote_age_s, 30.0, bad)
        self.assertEqual(
            tm.read_paper_settings({"paper": {"max_quote_age_s": 5}}).max_quote_age_s, 5.0
        )

    def test_settings_manager_persists_and_repairs_the_new_keys(self):
        with tempfile.TemporaryDirectory() as d:
            m = SettingsManager("pt_config.json", d)
            self.assertEqual(m.get_price_fallback_policy(), "pause")
            self.assertTrue(m.set_price_fallback_policy("simulate_and_flag"))
            self.assertEqual(
                SettingsManager("pt_config.json", d).get_price_fallback_policy(),
                "simulate_and_flag",
            )
            self.assertFalse(m.set_price_fallback_policy("yolo"))

            with open(os.path.join(d, "pt_config.json"), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "paper": {"price_fallback_policy": "yolo", "max_quote_age_s": -1},
                        "risk": {"emergency_drawdown_pct": 500},
                    },
                    f,
                )
            repaired = SettingsManager("pt_config.json", d)
            self.assertEqual(repaired.get(psm.PAPER_POLICY_KEY), "pause")
            self.assertEqual(repaired.get(psm.PAPER_MAX_QUOTE_AGE_KEY), 30.0)
            self.assertEqual(repaired.get(psm.EMERGENCY_DRAWDOWN_KEY), 8.0)

    def test_defaults_in_the_settings_manager(self):
        with tempfile.TemporaryDirectory() as d:
            m = SettingsManager("pt_config.json", d)
            self.assertEqual(m.get("paper.price_fallback_policy"), "pause")
            self.assertEqual(m.get("paper.max_quote_age_s"), 30)
            self.assertEqual(m.get("risk.emergency_drawdown_pct"), 8.0)


class PaperExchangePolicyTests(unittest.TestCase):
    """The adapter itself, with injected feeds and clock."""

    def exchange(self, quote, settings):
        return tm.PaperExchange(price_feed=lambda base: quote, settings_source=settings)

    def live_quote(self):
        now = time.time()
        return tm.Quote(bid=99.0, ask=101.0, quote_ts=now, fetched_ts=now)

    def test_live_quote_fills_marked_live_with_provenance(self):
        q = self.live_quote()
        fill = self.exchange(q, PAUSE).place_order("BTC-USD", "buy", 0.01)
        self.assertEqual(fill.status, "filled")
        self.assertEqual(fill.price_source, "live")
        self.assertEqual(fill.quote_ts, q.quote_ts)
        self.assertEqual(fill.age_s, 0.0)
        self.assertEqual(fill.price, 101.0)

    def test_unreachable_with_pause_rejects_and_warns(self):
        ex = self.exchange(None, PAUSE)
        with mock.patch.object(tm.logger, "warning") as warn:
            result = ex.place_order("BTC-USD", "buy", 0.01)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reason, "PRICE_UNAVAILABLE")
        self.assertEqual(ex.get_balance(), {"USD": 10000.0})  # nothing filled
        self.assertEqual(len(ex.account.orders), 0)
        self.assertIn("PRICE_UNAVAILABLE", str(warn.call_args_list))

    def test_rejected_order_can_still_be_looked_up(self):
        ex = self.exchange(None, PAUSE)
        result = ex.place_order("BTC-USD", "buy", 0.01)
        self.assertEqual(ex.get_order_status(result.order_id).reason, "PRICE_UNAVAILABLE")

    def test_price_reads_raise_under_pause(self):
        ex = self.exchange(None, PAUSE)
        with self.assertRaises(tm.PriceUnavailable):
            ex.get_market_data("BTC-USD")

    def test_unreachable_with_simulate_and_flag_fills_marked_simulated(self):
        ex = self.exchange(None, SIM)
        with mock.patch.object(tm.logger, "warning") as warn:
            fill = ex.place_order("BTC-USD", "buy", 0.01)
        self.assertEqual((fill.status, fill.price_source), ("filled", "simulated"))
        self.assertIsNone(fill.quote_ts)
        self.assertIsNone(fill.age_s)
        self.assertIn("SIMULATED", str(warn.call_args_list))

    def test_stale_quote_with_pause_is_rejected(self):
        now = time.time()
        stale = tm.Quote(bid=99, ask=101, quote_ts=now - 120, fetched_ts=now)
        result = self.exchange(stale, PAUSE).place_order("BTC-USD", "buy", 0.01)
        self.assertEqual((result.status, result.reason), ("rejected", "PRICE_UNAVAILABLE"))

    def test_stale_quote_with_simulate_and_flag_fills_marked_stale_with_its_age(self):
        now = time.time()
        stale = tm.Quote(bid=99, ask=101, quote_ts=now - 120, fetched_ts=now)
        fill = self.exchange(stale, SIM).place_order("BTC-USD", "buy", 0.01)
        self.assertEqual((fill.status, fill.price_source), ("filled", "stale"))
        self.assertAlmostEqual(fill.age_s, 120.0, delta=1.0)
        self.assertEqual(fill.price, 101.0)

    def test_max_quote_age_is_configurable(self):
        now = time.time()
        quote = tm.Quote(bid=99, ask=101, quote_ts=now - 10, fetched_ts=now)
        strict = {"paper": {"max_quote_age_s": 5}}
        lax = {"paper": {"max_quote_age_s": 60}}
        self.assertEqual(
            self.exchange(quote, strict).place_order("BTC-USD", "buy", 0.01).status,
            "rejected",
        )
        self.assertEqual(
            self.exchange(quote, lax).place_order("BTC-USD", "buy", 0.01).price_source,
            "live",
        )

    def test_invalid_policy_behaves_as_pause(self):
        ex = self.exchange(None, {"paper": {"price_fallback_policy": "fake_it"}})
        self.assertEqual(ex.place_order("BTC-USD", "buy", 0.01).status, "rejected")

    def test_provenance_is_stamped_on_the_paper_account_records(self):
        ex = self.exchange(self.live_quote(), PAUSE)
        buy = ex.place_order("BTC-USD", "buy", 0.01)
        sell = ex.place_order("BTC-USD", "sell", 0.01)
        self.assertEqual(ex.account.orders[buy.order_id].price_source, "live")
        self.assertEqual(ex.account.trade_history[-1].price_source, "live")
        self.assertEqual(sell.price_source, "live")

    def test_limit_orders_do_not_depend_on_the_feed(self):
        ex = self.exchange(None, PAUSE)
        fill = ex.place_order("BTC-USD", "buy", 0.01, price=50_000.0)
        # 0.01 BTC @ 50k is $500, inside the paper account's 10% order limit
        self.assertEqual(fill.price_source, "n/a")

    def test_settings_source_is_followed_at_each_use(self):
        settings = {"paper": {"price_fallback_policy": "pause"}}
        ex = self.exchange(None, settings)
        self.assertEqual(ex.place_order("BTC-USD", "buy", 0.01).status, "rejected")
        settings["paper"]["price_fallback_policy"] = "simulate_and_flag"
        self.assertEqual(ex.place_order("BTC-USD", "buy", 0.01).status, "filled")

    def test_gate_binds_the_callers_settings_to_the_paper_exchange(self):
        tm.reset_paper_exchange()
        self.addCleanup(tm.reset_paper_exchange)
        target = tm.resolve_order_target(SIM)
        self.assertIs(target.exchange.settings_source, SIM)


class PublicQuoteFeedTests(PaperTraderCase):
    def test_quote_ts_comes_from_the_response_date_header(self):
        self.binance.age_s = 4.0
        q = tm.fetch_public_quote("BTC")
        self.assertAlmostEqual(q.age_s, 4.0, delta=1.5)
        self.assertEqual((q.bid, q.ask), (99.0, 101.0))
        self.assertTrue(self.binance.urls[0].startswith("https://api.binance.com/api/v3/ticker/bookTicker"))

    def test_missing_date_header_means_stale_not_live(self):
        self.binance.send_date = False
        q = tm.fetch_public_quote("BTC")
        self.assertIsNone(q.quote_ts)
        self.assertEqual(tm.classify_quote(q, 30, time.time()), "stale")

    def test_unreachable_feed_returns_none(self):
        self.binance.reachable = False
        self.assertIsNone(tm.fetch_public_quote("BTC"))


class TraderLedgerTests(PaperTraderCase):
    def test_live_feed_fill_is_recorded_with_price_source_live(self):
        trader = self.trader(copy.deepcopy(PAUSE))
        response = trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        self.assertEqual(response["state"], "filled")
        (row,) = self.ledger_rows()
        self.assertEqual(row["price_source"], "live")
        self.assertIsNotNone(row["quote_ts"])
        self.assertLess(row["age_s"], 5.0)

    def test_unreachable_feed_with_pause_places_no_fill_and_warns(self):
        self.binance.reachable = False
        trader = self.trader(copy.deepcopy(PAUSE))
        w_tm, w_trader = spy_warnings()
        with w_tm, w_trader as trader_warn:
            response = trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        self.assertIsNone(response)
        self.assertEqual(self.ledger_rows(), [])
        self.assertEqual(len(tm.get_paper_exchange().account.orders), 0)
        self.assertGreaterEqual(trader_warn.call_count, 1)
        self.assertEqual(trader._pnl_ledger.get("pending_orders"), {})

    def test_trader_retries_next_cycle_once_the_feed_returns(self):
        self.binance.reachable = False
        trader = self.trader(copy.deepcopy(PAUSE))
        self.assertIsNone(trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0))
        self.binance.reachable = True
        tm._quote_cache.clear()
        self.assertEqual(
            trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)["state"],
            "filled",
        )

    def test_unreachable_feed_with_simulate_and_flag_records_simulated(self):
        self.binance.reachable = False
        trader = self.trader(copy.deepcopy(SIM))
        response = trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        self.assertIsNotNone(response)
        (row,) = self.ledger_rows()
        self.assertEqual(row["price_source"], "simulated")
        self.assertIsNone(row["quote_ts"])

    def test_stale_feed_is_treated_as_stale(self):
        self.binance.age_s = 90.0  # Binance's own Date header is 90 s old
        trader = self.trader(copy.deepcopy(SIM))
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        (row,) = self.ledger_rows()
        self.assertEqual(row["price_source"], "stale")
        self.assertGreater(row["age_s"], 60.0)

    def test_stale_feed_with_pause_places_no_order(self):
        self.binance.age_s = 90.0
        trader = self.trader(copy.deepcopy(PAUSE))
        self.assertIsNone(trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0))
        self.assertEqual(self.ledger_rows(), [])

    def test_legacy_ledger_without_new_columns_loads_as_unknown_and_is_not_rewritten(self):
        paper_dir = os.path.join(self.tmp.name, "paper")
        os.makedirs(paper_dir)
        path = os.path.join(paper_dir, "trade_history.jsonl")
        legacy = [
            {"ts": time.time() - 100, "side": "buy", "tag": None, "symbol": "BTC-USD",
             "qty": 0.01, "price": 100.0, "order_id": "old-1"},
            {"ts": time.time() - 50, "side": "sell", "tag": None, "symbol": "BTC-USD",
             "qty": 0.01, "price": 101.0, "order_id": "old-2"},
        ]
        with open(path, "w", encoding="utf-8") as f:
            for row in legacy:
                f.write(json.dumps(row) + "\n")
        before = open(path, "rb").read()

        trader = self.trader(copy.deepcopy(PAUSE))  # loads + seeds from history
        rows = trader._read_trade_history()
        self.assertEqual([r["price_source"] for r in rows], ["unknown", "unknown"])
        self.assertEqual(trader._fills_by_source(), {"unknown": 2})
        self.assertEqual(open(path, "rb").read(), before)  # historic rows untouched

        # new fills append alongside, with provenance
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        self.assertEqual(self.ledger_rows()[-1]["price_source"], "live")
        self.assertEqual(len(self.ledger_rows()), 3)

    def test_ledger_row_provenance_survives_a_restart(self):
        trader = self.trader(copy.deepcopy(SIM))
        self.binance.reachable = False
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        restarted = self.trader(copy.deepcopy(SIM))
        self.assertEqual(restarted._fills_by_source(), {"simulated": 1})
        self.assertEqual(restarted._degraded_last_hour(), 1)  # seeded from the ledger


class VisibilityTests(PaperTraderCase):
    def test_status_reports_live_when_all_prices_are_live(self):
        trader = self.trader(copy.deepcopy(PAUSE))
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        status = trader._price_integrity_status()
        self.assertEqual(status["state"], "live")
        self.assertEqual(status["degraded_last_hour"], 0)
        self.assertEqual(status["fills_by_source"], {"live": 1})
        self.assertEqual(status["policy"], "pause")

    def test_status_counts_degraded_events_in_the_last_hour(self):
        self.binance.reachable = False
        trader = self.trader(copy.deepcopy(PAUSE))
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)  # no price
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        status = trader._price_integrity_status()
        self.assertEqual(status["state"], "degraded")
        self.assertGreaterEqual(status["degraded_last_hour"], 2)

    def test_events_older_than_an_hour_drop_out(self):
        trader = self.trader(copy.deepcopy(PAUSE))
        trader._degraded_events = [time.time() - 7200, time.time() - 10]
        self.assertEqual(trader._degraded_last_hour(), 1)

    def test_manage_trades_writes_the_status_block_for_the_hub(self):
        trader = self.trader(copy.deepcopy(PAUSE))
        trader.manage_trades()
        with open(os.path.join(self.tmp.name, "paper", "trader_status.json")) as f:
            status = json.load(f)
        self.assertIn("price_integrity", status)
        self.assertEqual(status["price_integrity"]["policy"], "pause")

    def test_startup_and_hourly_summary_lines_are_logged(self):
        trader = self.trader(copy.deepcopy(PAUSE))
        with mock.patch.object(self.pt_trader.logger, "info") as info:
            trader._log_price_summary()
        self.assertIn("Paper fills by price_source", str(info.call_args_list))
        trader._last_price_summary_ts = time.time() - 4000
        with mock.patch.object(self.pt_trader.logger, "info") as info:
            trader.manage_trades()
        self.assertIn("Paper fills by price_source", str(info.call_args_list))

    def test_price_note_text(self):
        self.assertEqual(price_note(None), "")
        self.assertEqual(
            price_note({"state": "live", "degraded_last_hour": 0}), " · PRICES: LIVE"
        )
        self.assertEqual(
            price_note({"state": "degraded", "degraded_last_hour": 3}),
            " · PRICES: DEGRADED (3 in last hour)",
        )

    def test_indicator_shows_the_note_in_paper_but_never_in_live(self):
        import tkinter as tk

        from trading_mode_ui import TradingModeIndicator

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display available")
        self.addCleanup(root.destroy)
        root.withdraw()
        paper = tm.read_trading_settings({"trading": {"mode": "paper"}})
        indicator = TradingModeIndicator(root, paper)
        indicator.update_price_integrity({"state": "live", "degraded_last_hour": 0})
        self.assertEqual(indicator.cget("text"), "MODE: PAPER · PRICES: LIVE")
        indicator.update_price_integrity({"state": "degraded", "degraded_last_hour": 2})
        self.assertEqual(
            indicator.cget("text"), "MODE: PAPER · PRICES: DEGRADED (2 in last hour)"
        )
        live = tm.read_trading_settings(
            {"trading": {"mode": "live", "active_broker": "kraken"}}
        )
        indicator.update_settings(live)
        indicator.update_price_integrity({"state": "live", "degraded_last_hour": 0})
        self.assertEqual(indicator.cget("text"), "MODE: LIVE — kraken")


class EmergencyDrawdownTests(PaperTraderCase):
    def adapter(self, settings):
        return self.pt_trader._TraderRiskAdapter(settings_source=settings)

    def check(self, adapter, value, peak=1000.0):
        adapter.peak_value = peak
        return adapter.check_emergency_conditions(value)

    def test_default_is_eight_percent(self):
        a = self.adapter({})
        self.assertFalse(self.check(a, 930.0)["emergency_stop"])  # 7%
        self.assertTrue(self.check(a, 919.0)["emergency_stop"])  # 8.1%

    def test_setting_is_respected(self):
        tight = self.adapter({"risk": {"emergency_drawdown_pct": 3}})
        self.assertTrue(self.check(tight, 960.0)["emergency_stop"])  # 4% > 3%
        loose = self.adapter({"risk": {"emergency_drawdown_pct": 20}})
        self.assertFalse(self.check(loose, 850.0)["emergency_stop"])  # 15% < 20%
        self.assertTrue(self.check(loose, 790.0)["emergency_stop"])

    def test_invalid_values_fall_back_to_eight_and_are_logged(self):
        for bad in ("abc", 0, 0.5, 51, -4, None, True, float("nan"), [8]):
            with self.subTest(bad=bad), mock.patch.object(tm.logger, "warning") as warn:
                self.assertEqual(
                    tm.read_emergency_drawdown_pct({"risk": {"emergency_drawdown_pct": bad}}),
                    8.0,
                )
                if bad is not None:
                    warn.assert_called()

    def test_bounds_are_inclusive(self):
        for ok in (1, 1.0, 50, 25.5):
            self.assertEqual(
                tm.read_emergency_drawdown_pct({"risk": {"emergency_drawdown_pct": ok}}),
                float(ok),
            )

    def test_trader_picks_the_setting_up_without_restart(self):
        settings = {"trading": {"mode": "paper"}}
        trader = self.trader(settings)
        trader.risk_manager.peak_value = 1000.0
        self.assertFalse(trader.risk_manager.check_emergency_conditions(950.0)["emergency_stop"])
        settings["risk"] = {"emergency_drawdown_pct": 4}
        self.assertTrue(trader.risk_manager.check_emergency_conditions(950.0)["emergency_stop"])


class NoNetworkTests(PaperTraderCase):
    def test_only_the_public_ticker_was_ever_requested(self):
        trader = self.trader(copy.deepcopy(PAUSE))
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0)
        trader.manage_trades()
        self.assertTrue(self.binance.urls)
        for url in self.binance.urls:
            self.assertTrue(
                url.startswith("https://api.binance.com/api/v3/ticker/bookTicker?symbol="), url
            )


if __name__ == "__main__":
    unittest.main()
