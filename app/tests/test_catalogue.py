"""FDS-121 acceptance 5: the catalogue and the registry must agree, loudly."""

from __future__ import annotations

import copy
import unittest

import strategies
from strategies import catalogue as cat
from strategies.base import Strategy
from strategies.catalogue import CatalogueError, ParamError, build_catalogue


def good_entry(**overrides):
    entry = {
        "strategy_id": "T-001",
        "strategy_name": "Test",
        "family": "trend",
        "class_type": "main",
        "long_short_mode": "long_only",
        "timeframe_primary": "1h",
        "entry_logic_summary": "e",
        "exit_logic_summary": "x",
        "dependencies_indicators": ["EMA"],
        "default_params": {"fast": 5, "mode": "A"},
        "param_bounds": {"fast": {"min": 1, "max": 10}, "mode": {"values": ["A", "B"]}},
        "version": "1.0.0",
    }
    entry.update(overrides)
    return entry


class Dummy:  # a registered "class"
    pass


class BuildCatalogueTests(unittest.TestCase):
    def test_valid_catalogue_loads(self):
        out = build_catalogue([good_entry()], {"T-001": Dummy})
        self.assertIn("T-001", out)

    def test_every_required_field_is_enforced(self):
        for field in cat.REQUIRED_FIELDS:
            with self.subTest(field=field):
                entry = good_entry()
                del entry[field]
                with self.assertRaises(CatalogueError) as ctx:
                    build_catalogue([entry], {"T-001": Dummy})
                self.assertIn(field, str(ctx.exception))

    def test_entry_without_a_class_fails(self):  # orphan entry
        with self.assertRaises(CatalogueError) as ctx:
            build_catalogue([good_entry()], {})
        self.assertIn("no registered class", str(ctx.exception))

    def test_class_without_an_entry_fails(self):  # orphan class
        with self.assertRaises(CatalogueError) as ctx:
            build_catalogue([good_entry()], {"T-001": Dummy, "T-002": Dummy})
        self.assertIn("T-002", str(ctx.exception))
        self.assertIn("no catalogue entry", str(ctx.exception))

    def test_duplicate_ids_fail(self):
        with self.assertRaises(CatalogueError):
            build_catalogue([good_entry(), good_entry()], {"T-001": Dummy})

    def test_bad_class_type_and_mode_and_timeframe_fail(self):
        for bad in (
            {"class_type": "exotic"},
            {"long_short_mode": "long_short"},
            {"timeframe_primary": "7m"},
        ):
            with self.subTest(bad=bad), self.assertRaises(CatalogueError):
                build_catalogue([good_entry(**bad)], {"T-001": Dummy})

    def test_defaults_must_sit_inside_their_bounds(self):
        entry = good_entry(default_params={"fast": 99, "mode": "A"})
        with self.assertRaises(CatalogueError) as ctx:
            build_catalogue([entry], {"T-001": Dummy})
        self.assertIn("fast", str(ctx.exception))
        entry = good_entry(default_params={"fast": 5, "mode": "Z"})
        with self.assertRaises(CatalogueError):
            build_catalogue([entry], {"T-001": Dummy})

    def test_params_and_bounds_must_name_the_same_parameters(self):
        entry = good_entry(default_params={"fast": 5})
        with self.assertRaises(CatalogueError):
            build_catalogue([entry], {"T-001": Dummy})

    def test_unknown_bound_keys_fail(self):
        entry = good_entry(param_bounds={"fast": {"minimum": 1}, "mode": {"values": ["A"]}})
        with self.assertRaises(CatalogueError):
            build_catalogue([entry], {"T-001": Dummy})

    def test_non_list_catalogue_fails(self):
        with self.assertRaises(CatalogueError):
            build_catalogue({"T-001": good_entry()}, {"T-001": Dummy})


class LiveCatalogueTests(unittest.TestCase):
    def test_the_shipped_catalogue_and_registry_agree(self):
        self.assertEqual(set(cat.CATALOGUE), set(cat._REGISTRY))
        self.assertIn("STRAT-000", cat.CATALOGUE)

    def test_catalogue_json_has_every_required_field(self):
        for sid, entry in cat.CATALOGUE.items():
            for field in cat.REQUIRED_FIELDS:
                self.assertIn(field, entry, f"{sid}.{field}")

    def test_loading_a_broken_file_fails(self):
        import json
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "catalogue.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{ not json")
            with self.assertRaises(CatalogueError):
                cat.load_entries(path)

    def test_double_registration_of_an_id_fails(self):
        with self.assertRaises(CatalogueError):
            cat.register("STRAT-000")(type("Impostor", (), {}))
        self.assertEqual(cat._REGISTRY["STRAT-000"].__name__, "EmaCross")

    def test_create_validates_parameters(self):
        s = strategies.create("STRAT-000", fast_len=10, slow_len=30)
        self.assertEqual(s.params, {"fast_len": 10, "slow_len": 30})
        self.assertEqual(strategies.create("STRAT-000").params, {"fast_len": 20, "slow_len": 50})
        with self.assertRaises(ParamError):
            strategies.create("STRAT-000", fast_len=1)  # below min
        with self.assertRaises(ParamError):
            strategies.create("STRAT-000", fast_len="10")  # wrong type
        with self.assertRaises(ParamError):
            strategies.create("STRAT-000", bogus=1)  # unknown name
        with self.assertRaises(strategies.StrategyError):
            strategies.create("STRAT-000", fast_len=50, slow_len=20)  # slow <= fast
        with self.assertRaises(CatalogueError):
            strategies.create("STRAT-404")

    def test_whole_number_parameters_reject_floats_but_float_parameters_accept_ints(self):
        for bad in (10.5, 10.0):  # a float length would break the indicators downstream
            with self.assertRaises(ParamError):
                strategies.create("STRAT-000", fast_len=bad)
        self.assertEqual(strategies.create("STRAT-001", adx_min=22.5).params["adx_min"], 22.5)
        self.assertEqual(strategies.create("STRAT-001", adx_min=25).params["adx_min"], 25)
        with self.assertRaises(ParamError):
            strategies.create("STRAT-002", atr_len=10.5)
        self.assertEqual(strategies.create("STRAT-002", mult=2).params["mult"], 2)

    def test_bool_is_not_a_number(self):
        with self.assertRaises(ParamError):
            strategies.create("STRAT-000", fast_len=True)

    def test_stage_bounds_validate(self):
        spec = {"type": "stages"}
        cat.check_value("X", "stages", [[3, 1], [6, 3]], spec)
        for bad in ([], [[3]], [[3, 1], [2, 1]], [[3, 3]], [[3, -1]], "x", [[3, "a"]]):
            with self.subTest(bad=bad), self.assertRaises(ParamError):
                cat.check_value("X", "stages", bad, spec)

    def test_list_ids_filters_by_class_type(self):
        self.assertIn("STRAT-000", cat.list_ids("main"))
        self.assertNotIn("STRAT-000", cat.list_ids("risk_overlay"))


if __name__ == "__main__":
    unittest.main()
