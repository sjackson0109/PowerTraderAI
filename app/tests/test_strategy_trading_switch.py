"""The owner's trading switch (``strategy.trading_allowed``), as the settings read it.

* An entry may trade in a mode when the owner's switch for it says so, and otherwise
  when its catalogue authorisation covers the mode. A switch works both ways: on for a
  research-only entry, off for a live one.
* A switch for one mode says nothing about the other.
* A switch setting that is not ``{id: {"paper"|"live": bool}}`` allows nothing and is
  a settings problem, so the trader places no orders.
* Without switches, everything reads as before.
* The settings manager refuses a malformed switch setting.

The window that sets them is tested in ``test_strategy_catalogue_view.py``; the
trader's order gate in ``test_strategy_lifecycle.py``."""

from __future__ import annotations

import unittest
from unittest import mock

import trading_mode as tm
from strategies import catalogue as cat
from strategies import settings as ss


def settings_with(active="STRAT-001", switches=None, overlays=()):
    strategy = {"active_id": active, "overlays": [{"id": o} for o in overlays]}
    if switches is not None:
        strategy["trading_allowed"] = switches
    return {"strategy": strategy}


class AllowedTests(unittest.TestCase):
    def test_without_switches_the_catalogue_decides(self):
        for sid in cat.CATALOGUE:
            for mode in ("paper", "live", tm.TradingMode.PAPER, tm.TradingMode.LIVE):
                with self.subTest(sid=sid, mode=mode):
                    self.assertEqual(
                        ss.allowed_for_trading(sid, mode),
                        cat.allowed_in_mode(sid, mode),
                    )

    def test_a_switch_overrides_the_catalogue_both_ways(self):
        switches = {"STRAT-001": {"paper": False}, "STRAT-005": {"paper": True}}
        self.assertFalse(ss.allowed_for_trading("STRAT-001", "paper", switches))
        self.assertTrue(ss.allowed_for_trading("STRAT-001", "live", switches))
        self.assertTrue(ss.allowed_for_trading("STRAT-005", "paper", switches))
        self.assertTrue(
            ss.allowed_for_trading("STRAT-005", tm.TradingMode.PAPER, switches)
        )
        self.assertFalse(ss.allowed_for_trading("STRAT-005", "live", switches))

    def test_unknown_ids_and_modes_are_never_allowed(self):
        switches = {"NOPE": {"paper": True}, "STRAT-001": {"paper": True}}
        self.assertFalse(ss.allowed_for_trading("NOPE", "paper", switches))
        for mode in ("demo", "Paper", ""):
            self.assertFalse(ss.allowed_for_trading("STRAT-001", mode, switches))

    def test_malformed_switches_are_refused(self):
        for raw in (
            ["STRAT-001"],
            {"STRAT-001": True},
            {"STRAT-001": {"demo": True}},
            {"STRAT-001": {"paper": "yes"}},
            {"STRAT-001": {"paper": 1}},
            {1: {"paper": True}},
        ):
            with self.subTest(raw=raw):
                switches, problem = ss.parse_switches(raw)
                self.assertEqual(switches, {})
                self.assertIn("invalid strategy.trading_allowed", problem)
        self.assertEqual(ss.parse_switches(None), ({}, None))
        self.assertEqual(ss.parse_switches({}), ({}, None))


class SettingsTests(unittest.TestCase):
    def test_a_strategy_switched_off_is_refused_in_that_mode_only(self):
        s = settings_with(switches={"STRAT-001": {"paper": False}})
        self.assertEqual(
            ss.read_strategy_settings(s, "paper").problem,
            "STRAT-001 is switched off for paper trading in Settings > Strategy",
        )
        self.assertIsNone(ss.read_strategy_settings(s, "live").problem)
        self.assertIsNone(ss.read_strategy_settings(s).problem)  # research use

    def test_a_research_strategy_switched_on_reads_like_a_cleared_one(self):
        s = settings_with("STRAT-005", {"STRAT-005": {"paper": True}})
        s["strategy"]["timeframe"] = "1d"
        self.assertIsNone(ss.read_strategy_settings(s, "paper").problem)
        self.assertIn(
            "STRAT-005 can be used for research only, not live trading",
            ss.read_strategy_settings(s, "live").problem,
        )

    def test_an_overlay_switched_off_is_refused(self):
        s = settings_with(switches={"OVL-ATR": {"paper": False}}, overlays=("OVL-ATR",))
        self.assertEqual(
            ss.read_strategy_settings(s, "paper").problem,
            "OVL-ATR is switched off for paper trading in Settings > Strategy",
        )

    def test_malformed_switches_allow_nothing(self):
        s = settings_with(switches={"STRAT-001": {"paper": "on"}})
        problem = ss.read_strategy_settings(s, "paper").problem
        self.assertIn("invalid strategy.trading_allowed", problem)
        self.assertIsNone(ss.read_strategy_settings(s).problem)  # research use

    def test_switches_for_other_entries_change_nothing(self):
        plain = settings_with()
        switched = settings_with(
            switches={"STRAT-002": {"paper": False}, "OVL-ATR": {"live": False}}
        )
        for mode in ("paper", "live"):
            self.assertEqual(
                ss.read_strategy_settings(plain, mode),
                ss.read_strategy_settings(switched, mode),
            )

    def test_the_legacy_engine_ignores_the_switches(self):
        s = settings_with(switches={"STRAT-001": {"paper": "on"}})
        s["strategy"]["engine"] = "legacy_neural"
        self.assertIsNone(ss.read_strategy_settings(s, "paper").problem)

    def test_a_catalogue_change_shows_through_where_no_switch_is_set(self):
        s = settings_with("STRAT-002", {"STRAT-001": {"paper": False}})
        research = dict(cat.CATALOGUE["STRAT-002"], authorisation="research")
        with mock.patch.dict(cat.CATALOGUE, {"STRAT-002": research}):
            self.assertIn(
                "STRAT-002 can be used for research only",
                ss.read_strategy_settings(s, "paper").problem,
            )


class ManagerTests(unittest.TestCase):
    def test_the_settings_manager_refuses_malformed_switches(self):
        import tempfile

        from pt_settings_manager import SettingsManager

        with tempfile.TemporaryDirectory() as folder:
            manager = SettingsManager("pt_config.json", folder)
            self.assertFalse(
                manager.set_strategy({"trading_allowed": {"STRAT-001": "off"}})
            )
            self.assertTrue(
                manager.set_strategy(
                    {"trading_allowed": {"STRAT-001": {"paper": False}}}
                )
            )
            self.assertEqual(
                manager.get("strategy")["trading_allowed"],
                {"STRAT-001": {"paper": False}},
            )


if __name__ == "__main__":
    unittest.main()
