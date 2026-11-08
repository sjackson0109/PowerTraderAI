"""FDS-SR-001 milestone M2a: the catalogue lifecycle (sections 5.2, 5.3 and 12).

* Every catalogue entry states its authorisation. Today's strategies and overlays are
  ``live``, so they behave as before; STRAT-003 is ``research``. The optional fields
  default, and malformed ones are refused when the catalogue loads.
* Given the trading mode, a strategy or overlay whose authorisation does not cover it is
  a settings problem, so the trader places no orders. Without a mode nothing changes.
* For every existing strategy with every combination of the existing overlays, the
  settings read the same with and without the mode, and a replayed trader session places
  byte-identical orders with and without the check.
* ``strategy.research_enabled`` defaults to the entries that existed before FDS-SR-001.

No network: the trader runs on the test helpers' fake quotes, fees and candles."""

from __future__ import annotations

import copy
import itertools
import os
import unittest
from unittest import mock

import numpy as np
from helpers import Feed, PaperTraderCase, make_candles

import trading_mode as tm
from market_data.timeframes import TIMEFRAME_SECONDS
from signal_engine import SignalEngine
from strategies import catalogue as cat
from strategies import settings as ss

APPROVED = {  # E-D3, 2026-11-07
    "STRAT-000": "live",
    "STRAT-001": "live",
    "STRAT-002": "live",
    "STRAT-003": "research",
    "OVL-RATCHET": "live",
    "OVL-ATR": "live",
    "OVL-PLOCK": "live",
    "OVL-COOLDOWN": "live",
}
EXISTING_MAIN = ("STRAT-000", "STRAT-001", "STRAT-002")
EXISTING_OVERLAYS = ("OVL-RATCHET", "OVL-ATR", "OVL-PLOCK", "OVL-COOLDOWN")
MODES = ("paper", "live", tm.TradingMode.PAPER, tm.TradingMode.LIVE)


def entry_with(sid, **changes):
    return {sid: dict(cat.CATALOGUE[sid], **changes)}


def good_entry(**overrides):
    entry = {
        "strategy_id": "T-001",
        "strategy_name": "Test",
        "family": "breakout",
        "class_type": "main",
        "long_short_mode": "long_only",
        "timeframe_primary": "1d",
        "entry_logic_summary": "e",
        "exit_logic_summary": "x",
        "dependencies_indicators": [],
        "default_params": {"n": 5},
        "param_bounds": {"n": {"min": 1, "max": 10}},
        "version": "1.0.0",
        "authorisation": "research",
    }
    entry.update(overrides)
    return entry


class CatalogueFieldTests(unittest.TestCase):
    def build(self, **overrides):
        return cat.build_catalogue([good_entry(**overrides)], {"T-001": object})

    def test_every_entry_states_its_approved_authorisation(self):
        for sid, auth in APPROVED.items():
            self.assertEqual(cat.CATALOGUE[sid]["authorisation"], auth, sid)
        for sid, entry in cat.CATALOGUE.items():
            self.assertIn(entry["authorisation"], cat.AUTHORISATIONS, sid)

    def test_the_optional_fields_take_their_defaults(self):
        for sid in EXISTING_MAIN + EXISTING_OVERLAYS:
            e = cat.CATALOGUE[sid]
            self.assertEqual(e["timeframes_permitted"], list(TIMEFRAME_SECONDS), sid)
            self.assertIs(e["deterministic"], True)
            self.assertEqual(e["data_requirements"], {"coins": "own"})
            self.assertEqual(e["research_refs"], [])
        self.assertIs(cat.CATALOGUE["STRAT-003"]["deterministic"], False)
        # the defaults live in the loaded catalogue, not in the file
        raw = {e["strategy_id"]: e for e in cat.load_entries()}
        self.assertNotIn("timeframes_permitted", raw["STRAT-001"])

    def test_a_valid_new_entry_loads(self):
        out = self.build(timeframes_permitted=["1d", "4h"], research_refs=["A §4"])
        self.assertEqual(out["T-001"]["timeframes_permitted"], ["1d", "4h"])

    def test_malformed_lifecycle_fields_are_refused(self):
        bad = [
            ({"authorisation": "beta"}, "authorisation must be one of"),
            ({"family": "exotic"}, "family must be one of"),
            ({"timeframes_permitted": ["4h"]}, "is not in timeframes_permitted"),
            ({"timeframes_permitted": ["1d", "9h"]}, "distinct supported timeframes"),
            ({"timeframes_permitted": ["1d", "1d"]}, "distinct supported timeframes"),
            ({"timeframes_permitted": []}, "distinct supported timeframes"),
            ({"deterministic": "yes"}, "deterministic must be"),
            ({"data_requirements": {"coins": "some"}}, "data_requirements must be"),
            ({"research_refs": [1]}, "research_refs must be"),
        ]
        for overrides, message in bad:
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(cat.CatalogueError, message):
                    self.build(**overrides)

    def test_an_entry_without_an_authorisation_is_refused(self):
        entry = good_entry()
        del entry["authorisation"]
        with self.assertRaisesRegex(cat.CatalogueError, "authorisation"):
            cat.build_catalogue([entry], {"T-001": object})


class ModeTests(unittest.TestCase):
    def test_each_authorisation_allows_the_modes_it_covers(self):
        cases = {"research": (), "paper": ("paper",), "live": ("paper", "live")}
        for auth, allowed in cases.items():
            with mock.patch.dict(
                cat.CATALOGUE, entry_with("STRAT-000", authorisation=auth)
            ):
                for mode in ("paper", "live"):
                    self.assertEqual(
                        cat.allowed_in_mode("STRAT-000", mode),
                        mode in allowed,
                        (auth, mode),
                    )
                    enum = tm.TradingMode(mode)
                    self.assertEqual(
                        cat.allowed_in_mode("STRAT-000", enum), mode in allowed
                    )

    def test_unknown_ids_and_modes_are_never_allowed(self):
        self.assertFalse(cat.allowed_in_mode("STRAT-999", "paper"))
        self.assertFalse(cat.allowed_in_mode(None, "paper"))
        self.assertFalse(cat.allowed_in_mode("STRAT-001", "demo"))
        self.assertFalse(cat.allowed_in_mode("STRAT-001", None))


class SettingsTests(unittest.TestCase):
    def test_existing_strategies_and_overlays_read_the_same_in_every_mode(self):
        for sid in EXISTING_MAIN:
            tf = cat.CATALOGUE[sid]["timeframe_primary"]
            for r in range(len(EXISTING_OVERLAYS) + 1):
                for combo in itertools.combinations(EXISTING_OVERLAYS, r):
                    settings = {
                        "strategy": {
                            "active_id": sid,
                            "timeframe": tf,
                            "overlays": [{"id": o} for o in combo],
                        }
                    }
                    base = ss.read_strategy_settings(settings)
                    self.assertIsNone(base.problem, (sid, combo))
                    for mode in MODES:
                        with self.subTest(sid=sid, combo=combo, mode=mode):
                            self.assertEqual(
                                ss.read_strategy_settings(settings, mode), base
                            )

    def test_the_default_settings_are_unchanged_in_both_modes(self):
        base = ss.read_strategy_settings({})
        self.assertIsNone(base.problem)
        for mode in MODES:
            self.assertEqual(ss.read_strategy_settings({}, mode), base)

    def test_the_legacy_engine_ignores_the_catalogue_checks(self):
        settings = {"strategy": {"engine": "legacy_neural", "active_id": "STRAT-003"}}
        for mode in MODES:
            self.assertIsNone(ss.read_strategy_settings(settings, mode).problem)

    def test_a_research_strategy_is_refused_in_both_modes(self):
        settings = {"strategy": {"active_id": "STRAT-002", "timeframe": "4h"}}
        with mock.patch.dict(
            cat.CATALOGUE, entry_with("STRAT-002", authorisation="research")
        ):
            self.assertIsNone(ss.read_strategy_settings(settings).problem)
            for mode in MODES:
                problem = ss.read_strategy_settings(settings, mode).problem
                self.assertIn("STRAT-002 can be used for research only", problem)

    def test_a_paper_strategy_is_refused_only_in_live(self):
        settings = {"strategy": {"active_id": "STRAT-002", "timeframe": "4h"}}
        with mock.patch.dict(
            cat.CATALOGUE, entry_with("STRAT-002", authorisation="paper")
        ):
            self.assertIsNone(ss.read_strategy_settings(settings, "paper").problem)
            problem = ss.read_strategy_settings(settings, "live").problem
            self.assertIn("paper trading, not live trading", problem)

    def test_a_research_overlay_is_refused(self):
        settings = {"strategy": {"overlays": [{"id": "OVL-ATR"}]}}
        with mock.patch.dict(
            cat.CATALOGUE, entry_with("OVL-ATR", authorisation="research")
        ):
            self.assertIn(
                "OVL-ATR", ss.read_strategy_settings(settings, "paper").problem
            )

    def test_a_timeframe_the_strategy_may_not_trade_on_is_refused(self):
        settings = {"strategy": {"active_id": "STRAT-002", "timeframe": "1h"}}
        with mock.patch.dict(
            cat.CATALOGUE, entry_with("STRAT-002", timeframes_permitted=["4h"])
        ):
            problem = ss.read_strategy_settings(settings).problem
            self.assertIn("not one STRAT-002 can trade on (4h)", problem)

    def test_research_enabled_defaults_to_the_entries_before_fds_sr_001(self):
        self.assertEqual(ss.read_research_enabled({}), ss.DEFAULT_RESEARCH_ENABLED)
        self.assertNotIn("STRAT-003", ss.read_research_enabled({}))
        for bad in ("STRAT-001", 3, {"a": 1}):
            setting = {"strategy": {"research_enabled": bad}}
            self.assertEqual(
                ss.read_research_enabled(setting), ss.DEFAULT_RESEARCH_ENABLED
            )
        setting = {
            "strategy": {"research_enabled": ["OVL-ATR", "STRAT-999", 7, "STRAT-002"]}
        }
        self.assertEqual(ss.read_research_enabled(setting), ("STRAT-002", "OVL-ATR"))
        self.assertEqual(
            ss.read_research_enabled({"strategy": {"research_enabled": []}}), ()
        )


def trend_series():
    down = np.linspace(200, 150, 150)
    up = np.linspace(150, 240, 40)
    fall = np.linspace(240, 110, 70)
    return np.concatenate([down, up, fall])


ORDER_FIELDS = (
    "symbol",
    "side",
    "order_type",
    "quantity",
    "price",
    "status",
    "filled_quantity",
    "average_fill_price",
    "commission",
    "commission_rate",
)
PAPER = {"trading": {"mode": "paper"}, "strategy": {"active_id": "STRAT-000"}}


class TraderTests(PaperTraderCase):
    """A replayed paper session (the FDS-SIG-004 phase E method)."""

    def setUp(self):
        super().setUp()
        self.frame = make_candles(trend_series())
        for p in (
            mock.patch.object(self.pt_trader.time, "sleep"),
            mock.patch.object(self.pt_trader, "crypto_symbols", ["BTC"]),
        ):
            p.start()
            self.addCleanup(p.stop)

    def session(self, settings):
        tm.reset_paper_exchange()
        tm._quote_cache.clear()
        self.sessions = getattr(self, "sessions", 0) + 1
        folder = os.path.join(self.tmp.name, f"session{self.sessions}")
        os.makedirs(folder)
        feed = Feed(self.frame)
        engine = SignalEngine(settings, feed.provider, feed.clock)
        feed.set_after_bar(150)
        with mock.patch.object(self.pt_trader, "HUB_DATA_DIR", folder):
            trader = self.pt_trader.CryptoAPITrading(
                settings_source=settings, signal_engine=engine
            )
            trader._order_poll_seconds = 0.0
            for k in range(150, len(self.frame)):
                feed.set_after_bar(k)
                trader.manage_trades()
        orders = list(tm.get_paper_exchange().account.orders.values())
        return [
            tuple(str(getattr(o, name, None)) for name in ORDER_FIELDS) for o in orders
        ]

    def test_orders_are_byte_identical_with_and_without_the_check(self):
        checked = self.session(copy.deepcopy(PAPER))
        self.assertEqual([o[1] for o in checked], ["OrderSide.BUY", "OrderSide.SELL"])
        with mock.patch.object(ss, "allowed_in_mode", lambda *_a: True):
            unchecked = self.session(copy.deepcopy(PAPER))
        self.assertEqual(checked, unchecked)

    def test_a_research_strategy_places_no_orders(self):
        with mock.patch.dict(
            cat.CATALOGUE, entry_with("STRAT-000", authorisation="research")
        ):
            self.assertEqual(self.session(copy.deepcopy(PAPER)), [])

    def test_a_paper_strategy_trades_in_paper_as_before(self):
        before = self.session(copy.deepcopy(PAPER))
        with mock.patch.dict(
            cat.CATALOGUE, entry_with("STRAT-000", authorisation="paper")
        ):
            self.assertEqual(self.session(copy.deepcopy(PAPER)), before)


if __name__ == "__main__":
    unittest.main()
