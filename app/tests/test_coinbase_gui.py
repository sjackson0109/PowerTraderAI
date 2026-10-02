"""Exchange-setup window behaviour for Coinbase: labels, multi-line private key,
validation on Save, and the Test button end-to-end (HTTP mocked)."""

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

import coinbase_auth  # noqa: E402
from helpers_coinbase import KEY_NAME, make_ec_pem, recorded_http  # noqa: E402

import tkinter as tk  # noqa: E402


class TestCoinbaseSetupWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # One Tk root for the whole class (initialising Tk repeatedly is slow and,
        # on some Windows setups, intermittently fails to find init.tcl).
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
        from pt_multi_exchange import ExchangeConfigManager

        self.gui_mod = exchange_config_gui
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager = ExchangeConfigManager(self.tmp.name)
        self.manager.create_default_config("EU")  # includes coinbase, enabled
        env = {k: v for k, v in os.environ.items() if not k.startswith("POWERTRADER_")}
        env_patch = mock.patch.dict(os.environ, env, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)

        self.dialogs = mock.MagicMock()
        for name in ("showerror", "showinfo", "showwarning", "askyesno"):
            p = mock.patch.object(exchange_config_gui.messagebox, name, getattr(self.dialogs, name))
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(exchange_config_gui, "ExchangeConfigManager", lambda: self.manager)
        p.start()
        self.addCleanup(p.stop)

        self.gui = exchange_config_gui.ExchangeConfigGUI(self.root)
        self.addCleanup(self.gui.window.destroy)
        self.gui.window.withdraw()

    # -- helpers --
    def select(self, name):
        self.gui.exchange_var.set(name)
        self.gui.on_exchange_selected()
        self.gui.window.update()

    def type_credentials(self, key, secret):
        self.gui.api_key_var.set(key)
        self.gui.api_secret_text.delete("1.0", tk.END)
        self.gui.api_secret_text.insert("1.0", secret)

    def saved(self):
        self.manager.load_config()
        return self.manager.get_exchange_config("coinbase")

    def results(self):
        return self.gui.results_text.get("1.0", tk.END)

    def wait_for(self, text, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            self.gui.window.update()
            if text in self.results():
                return True
            time.sleep(0.01)
        return False

    # -- labels and widgets --
    def test_coinbase_shows_key_name_and_multiline_private_key(self):
        self.select("coinbase")
        self.assertEqual(self.gui.api_key_label.cget("text"), "Key name:")
        self.assertEqual(self.gui.api_secret_label.cget("text"), "Private key (PEM):")
        self.assertEqual(self.gui.api_secret_text.winfo_manager(), "grid")
        self.assertEqual(self.gui.api_secret_entry.winfo_manager(), "")

    def test_other_exchanges_keep_the_plain_fields(self):
        self.select("coinbase")
        self.select("binance")
        self.assertEqual(self.gui.api_key_label.cget("text"), "API Key:")
        self.assertEqual(self.gui.api_secret_label.cget("text"), "API Secret:")
        self.assertEqual(self.gui.api_secret_entry.winfo_manager(), "grid")
        self.assertEqual(self.gui.api_secret_text.winfo_manager(), "")

    def test_instructions_describe_the_current_scheme(self):
        self.select("coinbase")
        text = self.gui.instructions_text.get("1.0", tk.END)
        for needle in ("ECDSA", "Key name", "BEGIN EC PRIVATE KEY", "Test Connection", "Transfer"):
            self.assertIn(needle, text)
        self.assertNotIn("Copy API Key and Secret", text)
        self.assertNotIn("Coinbase Pro API", text)

    def test_exchange_list_no_longer_calls_it_coinbase_pro(self):
        names = [display for _, _, _, display, _ in self.gui.all_exchanges]
        self.assertNotIn("Coinbase Pro", names)
        self.assertIn("Coinbase", names)

    # -- save --
    def test_save_rejects_malformed_credentials_and_stores_nothing(self):
        self.select("coinbase")
        for key, secret in (
            ("abcdef123456", make_ec_pem()),
            (KEY_NAME, "not a key"),
            (KEY_NAME, "".join(make_ec_pem().splitlines()[1:-1])),
        ):
            with self.subTest(key=key[:12]):
                self.dialogs.showerror.reset_mock()
                self.type_credentials(key, secret)
                self.gui.save_exchange_config()
                self.dialogs.showerror.assert_called_once()
                self.assertEqual(self.saved().api_key, "")
                self.assertEqual(self.saved().api_secret, "")

    def test_save_stores_normalised_key_and_clears_the_box(self):
        self.select("coinbase")
        pem = make_ec_pem()
        self.type_credentials(f"  {KEY_NAME} ", pem.strip().replace("\n", "\\n"))
        self.gui.save_exchange_config()
        stored = self.saved()
        self.assertEqual(stored.api_key, KEY_NAME)
        self.assertEqual(stored.api_secret, coinbase_auth.normalise_private_key(pem))
        self.assertTrue(stored.enabled)
        self.assertEqual(self.gui.api_secret_text.get("1.0", tk.END).strip(), "")
        self.assertIn("already saved", self.gui.secret_hint_var.get())

    def test_reselecting_never_echoes_the_saved_private_key(self):
        self.select("coinbase")
        self.type_credentials(KEY_NAME, make_ec_pem())
        self.gui.save_exchange_config()
        self.select("binance")
        self.select("coinbase")
        self.assertEqual(self.gui.api_key_var.get(), KEY_NAME)
        self.assertEqual(self.gui.api_secret_text.get("1.0", tk.END).strip(), "")
        self.assertIn("already saved", self.gui.secret_hint_var.get())

    # -- test button, end to end --
    def test_test_button_uses_typed_credentials_without_saving(self):
        self.select("coinbase")
        self.type_credentials(KEY_NAME, make_ec_pem())
        with recorded_http() as http:
            http.respond_with(200, {"can_view": True, "can_trade": True, "can_transfer": False})
            self.gui.test_exchange_connection()
            self.assertTrue(self.wait_for("Connected to Coinbase"))
        self.assertEqual(http.methods, ["GET"])
        self.assertEqual(http.order_like(), [])
        self.assertEqual(self.saved().api_key, "")  # nothing saved by testing

    def test_test_button_reports_each_failure_in_plain_words(self):
        self.select("coinbase")
        expectations = {
            401: "authentication failed",
            403: "permission denied",
            500: "unexpected response",
        }
        for code, headline in expectations.items():
            with self.subTest(code=code):
                self.type_credentials(KEY_NAME, make_ec_pem())
                with recorded_http() as http:
                    http.respond_with(code, {})
                    self.gui.test_exchange_connection()
                    self.assertTrue(self.wait_for(headline))
                self.assertEqual(len(http.calls), 1)

    def test_malformed_credentials_are_reported_without_any_request(self):
        self.select("coinbase")
        self.type_credentials("abcdef123456", "garbage")
        with recorded_http() as http:
            self.gui.test_exchange_connection()
            self.assertTrue(self.wait_for("credentials not valid"))
        self.assertEqual(http.calls, [])

    def test_saved_key_name_plus_blank_box_uses_the_saved_private_key(self):
        self.select("coinbase")
        self.type_credentials(KEY_NAME, make_ec_pem())
        self.gui.save_exchange_config()
        self.select("coinbase")  # box is now blank, key name is shown
        with recorded_http() as http:
            http.respond_with(200, {"can_view": True, "can_trade": False, "can_transfer": False})
            self.gui.test_exchange_connection()
            self.assertTrue(self.wait_for("Connected to Coinbase"))
        self.assertEqual(len(http.calls), 1)

    def test_test_all_uses_the_repaired_path(self):
        self.select("coinbase")
        self.type_credentials(KEY_NAME, make_ec_pem())
        self.gui.save_exchange_config()
        with recorded_http() as http:
            http.respond_with(200, {"can_view": True, "can_trade": True, "can_transfer": False})
            self.gui.test_all_exchanges()
            self.assertTrue(self.wait_for("1/1 exchanges tested successfully"))
        self.assertEqual(http.methods, ["GET"])


if __name__ == "__main__":
    unittest.main()
