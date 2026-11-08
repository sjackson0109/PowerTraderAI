"""STRAT-004 paper-observation readiness (docs/dev/STRAT-004-paper-readiness.md).

These tests pin existing behaviour that the readiness assessment relies on. They change
no setting and nothing on disk. Where a test needs the proposed ``paper``
authorisation, it patches the loaded catalogue in memory for that test only, as
``test_strategy_lifecycle.py`` does. STRAT-004 stays ``research`` in ``catalogue.json``.

* Today STRAT-004 is research-only. It is refused in paper and live by the settings
  check and by the trader's order gate, and a replayed paper session places no orders.
* An authorisation or a trading mode the catalogue does not know is refused.
* At its defaults (55/20), STRAT-004's parameters hash to ``PARAMS_SHA256``. Each trade
  record carries that hash.
* The proposed observation's frozen settings hash to ``SNAPSHOT_SHA256`` with
  ``strategy_lab.observation``'s own snapshot. The settings defaults the hash assumes
  are pinned too.
* With ``paper`` authorisation (in memory only), a replayed daily paper session places
  its orders on the bars where the backtester trades. Each order is 1% of the account,
  and each sell is the whole quantity bought. Reconcile matches every trade. The same
  settings are refused in live mode.

Synthetic candles only: no network, nothing about performance."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import unittest
from unittest import mock

import numpy as np
import pandas as pd
from helpers import PaperTraderCase
from test_strategy_breakout import DailyFeed, daily

import trading_mode as tm
from backtest.engine import CostModel, run_backtest
from signal_engine import SignalEngine
from strategies import catalogue as cat
from strategies import settings as ss
from strategies.factory import build_runner
from strategy_lab import observation as obs

DAY = 86_400

# The proposed observation (docs/dev/STRAT-004-paper-readiness.md, section 6)
COINS = [
    "BTC",
    "ETH",
    "XRP",
    "DOGE",
    "SOL",
    "ZEC",
    "DASH",
    "ADA",
    "AVAX",
    "LINK",
    "LTC",
]
STRATEGY = {
    "engine": "catalogue",
    "active_id": "STRAT-004",
    "timeframe": "1d",
    "params": {},
    "overlays": [],
}
PROPOSED_CONFIG = {
    "trading": {"mode": "paper", "active_broker": None, "binance_testnet": True},
    "strategy": STRATEGY,
    "risk": {
        "drawdown_warning_pct": 3.0,
        "drawdown_critical_pct": 5.0,
        "emergency_drawdown_pct": 8.0,
    },
    "paper": {"price_fallback_policy": "pause", "max_quote_age_s": 30},
    "llm": {"signal_mode": "off"},
}
PROPOSED_GUI = {
    "coins": COINS,
    "paper_coins_mode": "inherit",
    "paper_coins": [],
    "start_allocation_pct": 1.0,
    "max_coin_allocation_pct": 10.0,
    "min_order_margin_pct": 2.0,
    "trade_start_level": 3,
    "dca_levels": [-2.5, -5.0, -10.0, -20.0, -30.0, -40.0, -50.0],
    "dca_multiplier": 2.0,
    "max_dca_buys_per_24h": 2,
    "pm_start_pct_no_dca": 5.0,
    "pm_start_pct_with_dca": 2.5,
    "trailing_gap_pct": 0.5,
}
SNAPSHOT_SHA256 = "b0e54cdfdd2a1615b0cf779d6f819101dd035a0b11ff2814830736a1efe1cc70"
# the same, with the entry assessment's section saved by Settings > Strategy (all Off)
SNAPSHOT_SHA256_FUSION_SAVED = (
    "a446295996744388dc4379c5c481559452b62881cb94191636f237db404f344f"
)
PARAMS_SHA256 = "89579608ee854d67afce197674141a23848b1adb3bcca6b5096d72dcfd726265"
FIELDS = {
    "strategy_id": "STRAT-004",
    "strategy_version": "1.0.0",
    "strategy_params_sha256": PARAMS_SHA256,
    "strategy_timeframe": "1d",
    "strategy_overlays": [],
}


def paper_authorised():
    """The proposed change, in memory for one test: STRAT-004 at ``paper``."""
    return mock.patch.dict(
        cat.CATALOGUE,
        {"STRAT-004": dict(cat.CATALOGUE["STRAT-004"], authorisation="paper")},
    )


class TodayTests(unittest.TestCase):
    def test_it_is_research_only_in_the_catalogue_file(self):
        raw = {e["strategy_id"]: e for e in cat.load_entries()}
        self.assertEqual(raw["STRAT-004"]["authorisation"], "research")
        self.assertEqual(cat.CATALOGUE["STRAT-004"]["authorisation"], "research")

    def test_the_proposed_settings_are_refused_in_every_mode(self):
        settings = {"strategy": dict(STRATEGY)}
        self.assertIsNone(ss.read_strategy_settings(settings).problem)  # research
        for mode in ("paper", "live", tm.TradingMode.PAPER, tm.TradingMode.LIVE):
            with self.subTest(mode=mode):
                problem = ss.read_strategy_settings(settings, mode).problem
                self.assertIn("STRAT-004 can be used for research only", problem)

    def test_an_unknown_authorisation_or_mode_is_refused(self):
        settings = {"strategy": dict(STRATEGY)}
        unknown = dict(cat.CATALOGUE["STRAT-004"], authorisation="beta")
        with mock.patch.dict(cat.CATALOGUE, {"STRAT-004": unknown}):
            for mode in ("paper", "live"):
                self.assertFalse(cat.allowed_in_mode("STRAT-004", mode))
                self.assertIsNotNone(ss.read_strategy_settings(settings, mode).problem)
        with paper_authorised():
            for mode in ("demo", "Paper", ""):
                with self.subTest(mode=mode):
                    self.assertFalse(cat.allowed_in_mode("STRAT-004", mode))
                    self.assertIsNotNone(
                        ss.read_strategy_settings(settings, mode).problem
                    )

    def test_with_paper_authorisation_it_is_still_refused_in_live(self):
        settings = {"strategy": dict(STRATEGY)}
        with paper_authorised():
            self.assertIsNone(ss.read_strategy_settings(settings, "paper").problem)
            problem = ss.read_strategy_settings(settings, "live").problem
            self.assertIn("paper trading, not live trading", problem)

    def test_its_default_parameters_hash(self):
        params = dict(cat.create("STRAT-004").params)
        self.assertEqual(params, {"entry_days": 55, "exit_days": 20})
        text = json.dumps(params, sort_keys=True, separators=(",", ":"))
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), PARAMS_SHA256)


class SnapshotTests(unittest.TestCase):
    def test_the_proposed_settings_hash(self):
        snap = obs.snapshot(PROPOSED_CONFIG, PROPOSED_GUI)
        self.assertEqual(obs.digest(snap), SNAPSHOT_SHA256)
        self.assertEqual(snap["config"]["strategy"], STRATEGY)
        self.assertIsNone(snap["config"]["signal_fusion"])
        from signal_fusion import settings as fs

        saved = {**PROPOSED_CONFIG, "signal_fusion": fs.normalise({})}
        self.assertEqual(
            obs.digest(obs.snapshot(saved, PROPOSED_GUI)), SNAPSHOT_SHA256_FUSION_SAVED
        )

    def test_the_hash_assumes_todays_defaults(self):
        import pt_hub
        from pt_settings_manager import DEFAULT_SETTINGS

        for section in ("risk", "paper"):
            self.assertEqual(DEFAULT_SETTINGS[section], PROPOSED_CONFIG[section])
        self.assertEqual(DEFAULT_SETTINGS["trading"]["mode"], "paper")
        for key, value in PROPOSED_GUI.items():
            if key != "coins":
                self.assertEqual(pt_hub.DEFAULT_SETTINGS[key], value, key)

    def test_reconcile_replays_the_frozen_strategy_at_its_defaults(self):
        spec = obs.spec_of(obs.snapshot(PROPOSED_CONFIG, PROPOSED_GUI))
        self.assertEqual(
            (spec.strategy_id, spec.params, spec.overlays, spec.timeframe),
            ("STRAT-004", {}, (), "1d"),
        )


def two_breakouts():
    """Flat, a rise to a new 55-day high, a fall to a new 20-day low, then again."""
    return np.concatenate(
        [
            np.full(60, 100.0),
            np.linspace(101, 130, 20),
            np.linspace(129, 95, 25),
            np.full(15, 95.0),
            np.linspace(96, 140, 30),
            np.linspace(139, 100, 30),
            np.full(10, 100.0),
        ]
    )


class PaperSessionTests(PaperTraderCase):
    """A replayed daily paper session (the FDS-SIG-004 phase E method), the trader
    seeing each bar 10 s after it closes. Paper fills at a quote 0.05% either side
    of the next bar's open, paying a 0.50% taker fee."""

    HALF_SPREAD = 0.0005
    TAKER = 0.005

    def setUp(self):
        super().setUp()
        self.frame = daily(two_breakouts())
        self.fees.maker = self.fees.taker = self.TAKER
        for p in (
            mock.patch.object(self.pt_trader.time, "sleep"),
            mock.patch.object(self.pt_trader, "crypto_symbols", ["BTC"]),
        ):
            p.start()
            self.addCleanup(p.stop)

    def settings(self):
        out = copy.deepcopy(PROPOSED_CONFIG)
        return {k: out[k] for k in ("trading", "strategy", "risk", "paper", "llm")}

    def session(self, settings):
        """Run the trader over every bar; returns (paper orders, trade rows with the
        session's own clock as their time)."""
        feed = DailyFeed(self.frame)
        engine = SignalEngine(settings, feed.provider, feed.clock)
        trader = self.pt_trader.CryptoAPITrading(
            settings_source=settings, signal_engine=engine
        )
        trader._order_poll_seconds = 0.0
        rows = []
        for k in range(55, len(self.frame) - 1):
            feed.set_after_bar(k)
            nxt = float(self.frame["open"].iloc[k + 1])
            self.quotes.ask = nxt * (1 + self.HALF_SPREAD)
            self.quotes.bid = nxt * (1 - self.HALF_SPREAD)
            tm._quote_cache.clear()
            trader.manage_trades()
            for row in self.ledger_rows()[len(rows) :]:
                rows.append(dict(row, ts=feed.now))
        orders = list(tm.get_paper_exchange().account.orders.values())
        return orders, rows, trader

    def backtest(self):
        runner = build_runner("STRAT-004")
        result = run_backtest(self.frame, runner, "BTC", "1d", cost=CostModel(0, 0))
        last = self.frame["open_time"].iloc[-1]
        return [t for t in result.trades if t.exit_time < last]

    def test_today_a_paper_session_places_no_orders(self):
        orders, rows, _ = self.session(self.settings())
        self.assertEqual(orders, [])
        self.assertEqual(rows, [])

    def test_with_paper_authorisation_paper_trades_where_the_backtest_does(self):
        expected = self.backtest()
        self.assertGreaterEqual(len(expected), 2)
        with paper_authorised():
            orders, rows, trader = self.session(self.settings())
        buys = [r for r in rows if r["side"] == "buy"]
        sells = [r for r in rows if r["side"] == "sell"]
        self.assertEqual([r["tag"] for r in buys], ["ENTRY"] * len(expected))
        self.assertEqual([r["tag"] for r in sells], ["EXIT:strategy"] * len(expected))
        # each fill is the first pass after the decision bar closed: the backtest's
        # next open, 10 s later
        self.assertEqual(
            [r["ts"] - 10 for r in buys],
            [t.entry_time.timestamp() for t in expected],
        )
        self.assertEqual(
            [r["ts"] - 10 for r in sells],
            [t.exit_time.timestamp() for t in expected],
        )
        for row in rows:
            for key, value in FIELDS.items():
                self.assertEqual(row[key], value, key)
            self.assertAlmostEqual(row["fee_rate"], self.TAKER)
        # 1% of a $10,000 paper account, and each sell is the whole quantity bought
        self.assertAlmostEqual(buys[0]["qty"] * buys[0]["price"], 100.0, places=2)
        for buy, sell in zip(buys, sells):
            self.assertEqual(sell["qty"], buy["qty"])
            self.assertIs(sell["closes_position"], True)
        self.assertEqual(len(orders), 2 * len(expected))
        self.assertEqual(trader.signal_engine.position("BTC"), None)

    def test_reconcile_matches_every_trade_with_its_fill_and_fee(self):
        expected = self.backtest()
        with paper_authorised():
            _, rows, _ = self.session(self.settings())
        segment = {
            "started_s": int(self.frame["open_time"].iloc[55].timestamp()),
            "snapshot": obs.snapshot(self.settings(), {"coins": ["BTC"]}),
        }
        end_s = int(self.frame["open_time"].iloc[-1].timestamp()) + DAY
        out = obs.reconcile(segment, rows, {"BTC": self.frame}, end_s)
        self.assertEqual(
            obs.summary(out),
            {"matched": len(expected), "timing": 0, "missed": 0, "extra": 0},
        )
        for row in out:
            self.assertAlmostEqual(row.fill_vs_open, self.HALF_SPREAD, places=9)
            self.assertAlmostEqual(row.fee_rate_paid, self.TAKER, places=9)

    def test_with_paper_authorisation_a_research_overlay_is_still_refused(self):
        settings = self.settings()
        settings["strategy"]["overlays"] = [{"id": "OVL-REGIME"}]
        with paper_authorised():
            problem = ss.read_strategy_settings(settings, "paper").problem
            self.assertIn("OVL-REGIME can be used for research only", problem)
            orders, rows, _ = self.session(settings)
        self.assertEqual((orders, rows), ([], []))


if __name__ == "__main__":
    unittest.main()
