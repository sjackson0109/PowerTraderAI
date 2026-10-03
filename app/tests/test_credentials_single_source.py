"""FDS-108a phase 2: the setup windows and the live gate read credentials from
one place (pt_secrets), nothing writes a credential to a file, and credentials
supplied in two places no longer drop the exchange."""

import copy
import json
import logging
import os
import sys
import tempfile
import unittest
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(__file__))

import keyring  # noqa: E402
import keyring.backends.fail  # noqa: E402

import pt_secrets  # noqa: E402
import trading_mode as tm  # noqa: E402
from helpers_coinbase import KEY_NAME, make_ec_pem, recorded_http  # noqa: E402
from pt_exchange_abstraction import ExchangeFactory, ExchangeManager, ExchangeType  # noqa: E402
from pt_exchanges import BinanceExchange, CoinbaseExchange  # noqa: E402
from pt_multi_exchange import (  # noqa: E402
    ExchangeConfig,
    ExchangeConfigManager,
    MultiExchangeManager,
    TradingConfig,
)

LIVE_COINBASE = {"trading": {"mode": "live", "active_broker": "coinbase"}}
PAPER = {"trading": {"mode": "paper", "active_broker": "coinbase"}}


@pytest.fixture(autouse=True)
def no_credential_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith("POWERTRADER_") and name != "POWERTRADER_HOME":
            monkeypatch.delenv(name)
    monkeypatch.setattr(pt_secrets, "_warned_both", set())
    monkeypatch.setattr(ExchangeFactory, "_credentials", {})
    tm.reset_paper_exchange()
    yield
    tm.reset_paper_exchange()


@pytest.fixture
def config_dir(tmp_path):
    return str(tmp_path / "cfg_dir_for_manager")


@pytest.fixture
def manager(config_dir):
    os.makedirs(config_dir)
    m = ExchangeConfigManager(config_dir)
    m.create_default_config("EU")
    return m


def file_text(manager):
    with open(manager.config_file, encoding="utf-8") as f:
        return f.read()


# --- one store -------------------------------------------------------------------------


def test_gui_saved_coinbase_key_is_what_the_live_gate_builds_with(manager, memory_keyring):
    pem = make_ec_pem()
    manager.update_exchange_credentials("coinbase", KEY_NAME, pem)
    assert memory_keyring.entries[("SJackson.PowerTraderAI", "coinbase:key_name")] == KEY_NAME
    assert memory_keyring.entries[("SJackson.PowerTraderAI", "coinbase:private_key")] == pem
    with recorded_http() as http:
        target = tm.resolve_order_target(copy.deepcopy(LIVE_COINBASE))
    assert http.calls == []
    assert target.is_live and isinstance(target.exchange, CoinbaseExchange)
    assert target.exchange.api_key == KEY_NAME
    assert target.exchange.api_secret == pem


def test_paper_mode_still_never_builds_the_exchange(manager):
    manager.update_exchange_credentials("coinbase", KEY_NAME, make_ec_pem())
    with mock.patch.object(ExchangeFactory, "get_exchange") as get_exchange:
        target = tm.resolve_order_target(copy.deepcopy(PAPER))
    assert not target.is_live and isinstance(target.exchange, tm.PaperExchange)
    get_exchange.assert_not_called()


def test_config_file_holds_no_credential(manager):
    manager.update_exchange_credentials("binance", "binance-key-value", "binance-secret-value")
    manager.update_exchange_credentials("kucoin", "ku-key", "ku-secret", "ku-pass")
    text = file_text(manager)
    for value in ("binance-key-value", "binance-secret-value", "ku-key", "ku-secret", "ku-pass"):
        assert value not in text
    data = json.loads(text)
    for ex in data["exchanges"]:
        assert not set(ex) & {"api_key", "api_secret", "passphrase"}
    reloaded = ExchangeConfigManager(os.path.dirname(manager.config_file))
    reloaded.load_config()
    binance = reloaded.get_exchange_config("binance")
    assert (binance.api_key, binance.api_secret) == ("binance-key-value", "binance-secret-value")
    assert binance.credential_source == "keyring"
    assert reloaded.get_exchange_config("kucoin").passphrase == "ku-pass"


def test_repr_of_a_loaded_config_shows_no_credential(manager):
    manager.update_exchange_credentials("binance", "repr-key-1234", "repr-secret-5678")
    ex = manager.get_exchange_config("binance")
    assert "repr-key-1234" not in repr(ex) and "repr-secret-5678" not in repr(ex)
    assert "repr-secret-5678" not in repr(manager.config)


def test_removing_credentials_deletes_them_from_the_keyring(manager, memory_keyring):
    manager.update_exchange_credentials("binance", "k", "s")
    manager.update_exchange_credentials("binance", "", "", "")
    assert not any(user.startswith("binance:") for _, user in memory_keyring.entries)
    assert manager.get_exchange_config("binance").api_key == ""


def test_a_legacy_plaintext_config_is_ignored_and_never_written_back(config_dir, caplog):
    os.makedirs(config_dir)
    legacy = {
        "user_region": "EU",
        "primary_exchange": "binance",
        "exchanges": [
            {
                "exchange_type": "binance",
                "enabled": True,
                "region_preference": 1,
                "api_key": "legacy-plain-key",
                "api_secret": "legacy-plain-secret",
                "passphrase": "",
                "sandbox": False,
            }
        ],
    }
    with open(os.path.join(config_dir, "trading_config.json"), "w", encoding="utf-8") as f:
        json.dump(legacy, f)
    m = ExchangeConfigManager(config_dir)
    with caplog.at_level(logging.WARNING):
        config = m.load_config()
    ex = config.exchanges[0]
    assert ex.enabled and ex.api_key == "" and ex.api_secret == ""
    assert "binance.api_key" in caplog.text and "legacy-plain-key" not in caplog.text
    assert MultiExchangeManager(m)._get_exchange_credentials(ex) is None
    m.save_config(config)
    assert "legacy-plain" not in file_text(m)


def test_exchange_config_json_never_supplies_credentials(tmp_path, caplog):
    path = tmp_path / "exchange_config.json"
    path.write_text(
        json.dumps({"binance": {"api_key": "file-key", "api_secret": "file-secret", "testnet": True}}),
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        ExchangeFactory.load_credentials(str(path))
    assert ExchangeFactory._credentials == {"binance": {"testnet": True}}
    assert "file-key" not in caplog.text and "file-secret" not in caplog.text
    assert ExchangeFactory._get_credentials(ExchangeType.BINANCE) is None


# --- credentials in two places (the latent bug) -------------------------------------------


def test_env_and_keyring_both_set_no_longer_drop_the_exchange(manager, monkeypatch, caplog):
    manager.update_exchange_credentials("coinbase", KEY_NAME, make_ec_pem())
    env_pem = make_ec_pem()
    monkeypatch.setenv("POWERTRADER_COINBASE_API_KEY", KEY_NAME + "-env")
    monkeypatch.setenv("POWERTRADER_COINBASE_API_SECRET", env_pem)
    multi = MultiExchangeManager(manager)
    with caplog.at_level(logging.WARNING, logger="pt_secrets"), recorded_http() as http:
        assert multi.initialize()
    assert http.calls == []
    assert "coinbase" in multi.get_available_exchanges()
    built = multi.exchange_manager.exchanges[ExchangeType.COINBASE]
    # environment values are used trimmed of surrounding whitespace
    assert built.api_key == KEY_NAME + "-env" and built.api_secret == env_pem.strip()
    assert "environment" in caplog.text
    assert env_pem not in caplog.text and KEY_NAME not in caplog.text


def test_explicit_credentials_and_stored_ones_do_not_collide(monkeypatch):
    # Before FDS-108a: exchange_class(**stored, **kwargs) -> TypeError -> "Failed to add".
    monkeypatch.setenv("POWERTRADER_BINANCE_API_KEY", "env-k")
    monkeypatch.setenv("POWERTRADER_BINANCE_API_SECRET", "env-s")
    em = ExchangeManager()
    assert em.add_exchange(ExchangeType.BINANCE, api_key="given-k", api_secret="given-s")
    built = em.exchanges[ExchangeType.BINANCE]
    assert isinstance(built, BinanceExchange)
    assert (built.api_key, built.api_secret) == ("given-k", "given-s")
    stored = ExchangeFactory.get_exchange(ExchangeType.BINANCE, testnet=True)
    assert (stored.api_key, stored.api_secret) == ("env-k", "env-s")


# --- Robinhood ---------------------------------------------------------------------------


def test_robinhood_credentials_live_in_the_keyring_not_in_files(memory_keyring, isolated_user_dirs):
    import base64

    from pt_credentials import KeyringCredentialManager, get_credentials

    seed = base64.b64encode(os.urandom(32)).decode()
    mgr = KeyringCredentialManager()
    assert mgr.encrypt_credentials("rh.test-key", seed)
    assert memory_keyring.entries[("SJackson.PowerTraderAI", "robinhood:api_key")] == "rh.test-key"
    assert memory_keyring.entries[("SJackson.PowerTraderAI", "robinhood:private_key")] == seed
    assert get_credentials() == ("rh.test-key", seed)
    assert mgr.has_encrypted_credentials() and not mgr.has_plaintext_credentials()
    assert mgr.check_rotation_warning() is None
    for root, _, files in os.walk(isolated_user_dirs["home"]):
        for name in files:
            with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as f:
                body = f.read()
            assert seed not in body and "rh.test-key" not in body
    mgr.delete_credentials()
    assert get_credentials() is None


def test_robinhood_env_wins_over_keyring(monkeypatch):
    from pt_credentials import KeyringCredentialManager, get_credentials

    KeyringCredentialManager().encrypt_credentials("rh.keyring", "a2V5cmluZw==")
    monkeypatch.setenv("POWERTRADER_ROBINHOOD_API_KEY", "rh.env")
    monkeypatch.setenv("POWERTRADER_ROBINHOOD_PRIVATE_KEY", "ZW52")
    assert get_credentials() == ("rh.env", "ZW52")


def test_robinhood_does_not_read_the_old_plaintext_or_vault_files(isolated_user_dirs, monkeypatch):
    from pt_credentials import get_credentials

    legacy = isolated_user_dirs["legacy"]
    for name, value in (("r_key.txt", "plain-key"), ("r_secret.txt", "cGxhaW4=")):
        with open(os.path.join(legacy, name), "w", encoding="utf-8") as f:
            f.write(value)
    monkeypatch.chdir(legacy)
    assert get_credentials() is None
    assert sorted(os.listdir(legacy)) == ["r_key.txt", "r_secret.txt"]  # untouched


# --- no usable keyring -------------------------------------------------------------------


def test_without_a_keyring_nothing_is_stored_and_trading_stays_paper(manager):
    keyring.set_keyring(keyring.backends.fail.Keyring())
    with pytest.raises(pt_secrets.KeyringUnavailable) as err:
        manager.update_exchange_credentials("coinbase", KEY_NAME, make_ec_pem())
    assert "POWERTRADER_COINBASE_API_KEY" in str(err.value)
    assert KEY_NAME not in file_text(manager) and "PRIVATE KEY" not in file_text(manager)
    target = tm.resolve_order_target(copy.deepcopy(PAPER))
    assert not target.is_live


# --- setup window never echoes a saved secret ------------------------------------------------


class TestSetupWindowEcho(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk

        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk not available: {exc}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        import exchange_config_gui

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager = ExchangeConfigManager(self.tmp.name)
        self.manager.create_default_config("EU")
        for name in ("showerror", "showinfo", "showwarning", "askyesno"):
            p = mock.patch.object(exchange_config_gui.messagebox, name)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(exchange_config_gui, "ExchangeConfigManager", lambda: self.manager)
        p.start()
        self.addCleanup(p.stop)
        self.gui = exchange_config_gui.ExchangeConfigGUI(self.root)
        self.addCleanup(self.gui.window.destroy)
        self.gui.window.withdraw()

    def select(self, name):
        self.gui.exchange_var.set(name)
        self.gui.on_exchange_selected()

    def test_saved_api_secret_and_passphrase_are_never_shown(self):
        self.select("kucoin")
        self.gui.api_key_var.set("ku-key")
        self.gui.api_secret_var.set("ku-secret-value")
        self.gui.passphrase_var.set("ku-pass-value")
        self.gui.save_exchange_config()
        self.assertEqual(self.gui.api_secret_var.get(), "")
        self.assertEqual(self.gui.passphrase_var.get(), "")
        self.select("binance")
        self.select("kucoin")
        self.assertEqual(self.gui.api_key_var.get(), "ku-key")
        self.assertEqual(self.gui.api_secret_var.get(), "")
        self.assertEqual(self.gui.passphrase_var.get(), "")
        self.assertIn("already saved", self.gui.secret_hint_var.get())
        # a blank secret next to the shown key keeps the saved values
        self.assertEqual(self.gui._form_credentials(), ("ku-key", "ku-secret-value", "ku-pass-value"))

    def test_no_keyring_shows_the_environment_variable_alternative(self):
        import exchange_config_gui

        keyring.set_keyring(keyring.backends.fail.Keyring())
        self.select("binance")
        self.gui.api_key_var.set("k")
        self.gui.api_secret_var.set("s")
        self.gui.save_exchange_config()
        exchange_config_gui.messagebox.showerror.assert_called_once()
        title, message = exchange_config_gui.messagebox.showerror.call_args[0]
        self.assertIn("POWERTRADER_BINANCE_API_KEY", message)
        self.assertIn("paper mode", message)

    def test_the_error_title_names_the_missing_keyring_package(self):
        """FDS-108a review item 5: with the keyring package missing the error
        box names the package, not the OS; with the package there but no
        usable backend it still says there is no credential store."""
        import exchange_config_gui

        showerror = exchange_config_gui.messagebox.showerror
        self.select("binance")
        self.gui.api_key_var.set("k")
        self.gui.api_secret_var.set("s")
        with mock.patch.dict(sys.modules, {"keyring": None}):
            self.gui.save_exchange_config()
        title, message = showerror.call_args[0]
        self.assertEqual(title, "The 'keyring' package is not installed")
        self.assertIn("'keyring' is not installed", message)

        keyring.set_keyring(keyring.backends.fail.Keyring())
        self.gui.api_secret_var.set("s")
        self.gui.save_exchange_config()
        title, _ = showerror.call_args[0]
        self.assertEqual(title, "No secure credential store")
