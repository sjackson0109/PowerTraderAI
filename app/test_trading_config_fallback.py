"""trading_config.json is git-ignored (it holds API keys in plain text), so a fresh
clone has only trading_config.example.json. ExchangeConfigManager must work from it."""

import json
import os
import shutil
import tempfile
import unittest

from pt_multi_exchange import (
    EXAMPLE_CONFIG_NAME,
    ExchangeConfigManager,
    MultiExchangeManager,
)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(APP_DIR)
CREDENTIAL_FIELDS = ("api_key", "api_secret", "passphrase")


class TestShippedExample(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(APP_DIR, EXAMPLE_CONFIG_NAME), encoding="utf-8") as f:
            self.data = json.load(f)

    def test_every_credential_field_is_empty(self):
        for ex in self.data["exchanges"]:
            for field in CREDENTIAL_FIELDS:
                self.assertEqual(
                    ex.get(field, ""), "", f"{ex['exchange_type']}.{field}"
                )

    def test_has_the_structure_the_loader_expects(self):
        self.assertTrue(self.data["exchanges"])
        for key in ("user_region", "primary_exchange", "exchanges"):
            self.assertIn(key, self.data)

    def test_real_config_is_git_ignored(self):
        with open(os.path.join(REPO_DIR, ".gitignore"), encoding="utf-8") as f:
            lines = [line.strip() for line in f]
        self.assertIn("app/trading_config.json", lines)


class TestFreshCloneFallback(unittest.TestCase):
    """A directory that has the example and no trading_config.json."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        shutil.copy(os.path.join(APP_DIR, EXAMPLE_CONFIG_NAME), self.tmp.name)
        self.manager = ExchangeConfigManager(self.tmp.name)
        self.real = os.path.join(self.tmp.name, "trading_config.json")

    def test_load_uses_the_example_and_does_not_create_the_real_file(self):
        config = self.manager.load_config()
        self.assertIsNotNone(config)
        self.assertTrue(config.exchanges)
        self.assertFalse(os.path.exists(self.real))
        self.assertTrue(all(not ex.api_key for ex in config.exchanges))

    def test_saving_credentials_works_on_a_fresh_clone(self):
        # Without the fallback config was None and this silently saved nothing.
        self.manager.load_config()
        name = self.manager.config.exchanges[0].exchange_type
        self.manager.update_exchange_credentials(name, "KEY-NAME", "SECRET-VALUE")
        self.assertTrue(os.path.exists(self.real))

        fresh = ExchangeConfigManager(self.tmp.name)
        fresh.load_config()
        saved = fresh.get_exchange_config(name)
        self.assertEqual(
            (saved.api_key, saved.api_secret), ("KEY-NAME", "SECRET-VALUE")
        )

    def test_real_file_wins_over_the_example_once_it_exists(self):
        self.manager.load_config()
        self.manager.config.primary_exchange = "kraken"
        self.manager.save_config(self.manager.config)
        fresh = ExchangeConfigManager(self.tmp.name)
        self.assertEqual(fresh.load_config().primary_exchange, "kraken")

    def test_unreadable_real_file_is_not_hidden_by_the_example(self):
        with open(self.real, "w") as f:
            f.write("{ not json")
        self.assertIsNone(self.manager.load_config())
        with open(self.real) as f:
            self.assertEqual(f.read(), "{ not json")  # left untouched

    def test_manager_initialises_from_the_example(self):
        multi = MultiExchangeManager(self.manager)
        multi.config_manager.load_config()
        self.assertIsInstance(multi.config_manager.get_enabled_exchanges(), list)


class TestNothingAtAll(unittest.TestCase):
    def test_no_real_file_and_no_example_is_none_not_a_crash(self):
        with tempfile.TemporaryDirectory() as empty:
            manager = ExchangeConfigManager(empty)
            self.assertIsNone(manager.load_config())
            self.assertEqual(manager.get_enabled_exchanges(), [])


if __name__ == "__main__":
    unittest.main()
