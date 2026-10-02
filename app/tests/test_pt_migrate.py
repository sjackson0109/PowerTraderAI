"""FDS-108a phase 4: migration of legacy files out of the program folder.
Fixture legacy files only (conftest points the legacy folders at temp dirs)."""

import base64
import hashlib
import json
import os
import sys
import unittest
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(__file__))

import keyring  # noqa: E402
import keyring.backends.fail  # noqa: E402

import pt_migrate  # noqa: E402
import pt_paths  # noqa: E402
import pt_secrets  # noqa: E402
from helpers_coinbase import KEY_NAME, make_ec_pem  # noqa: E402

SERVICE = "SJackson.PowerTraderAI"


@pytest.fixture(autouse=True)
def no_credential_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith("POWERTRADER_") and name != "POWERTRADER_HOME":
            monkeypatch.delenv(name)


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    with open(path, mode, **({} if isinstance(content, bytes) else {"encoding": "utf-8"})) as f:
        f.write(content if isinstance(content, (str, bytes)) else json.dumps(content))
    return path


def digest_tree(*roots):
    out = {}
    for root in roots:
        for folder, _, files in os.walk(root):
            for name in files:
                path = os.path.join(folder, name)
                with open(path, "rb") as f:
                    out[path] = (hashlib.sha256(f.read()).hexdigest(), os.stat(path).st_mtime_ns)
    return out


@pytest.fixture
def legacy(isolated_user_dirs):
    """A pre-FDS-108a install: app/ (legacy) and the install root."""
    app = isolated_user_dirs["legacy"]
    root = isolated_user_dirs["legacy_root"]
    pem = make_ec_pem()
    write(os.path.join(app, "pt_config.json"), {"trading": {"mode": "paper"}, "coins": ["BTC"]})
    write(
        os.path.join(app, "gui_settings.json"),
        {"coins": ["BTC", "ETH"], "main_neural_dir": app, "hub_data_dir": os.path.join(app, "hub_data"),
         "trade_start_level": 4},
    )
    write(
        os.path.join(app, "trading_config.json"),
        {"user_region": "EU", "primary_exchange": "coinbase", "exchanges": [
            {"exchange_type": "coinbase", "enabled": True, "region_preference": 1,
             "api_key": KEY_NAME, "api_secret": pem, "passphrase": "", "sandbox": False},
            {"exchange_type": "binance", "enabled": False, "region_preference": 2,
             "api_key": "bin-key-legacy", "api_secret": "bin-secret-legacy", "passphrase": "", "sandbox": False},
        ]},
    )
    write(os.path.join(app, "exchange_config.json"),
          {"kraken": {"api_key": "kr-key-legacy", "api_secret": "kr-secret-legacy", "timeout": 5}})
    write(os.path.join(app, "r_key.txt"), "rh.legacy-key")
    seed = base64.b64encode(b"s" * 32).decode()
    write(os.path.join(app, "r_secret.txt"), seed)
    write(os.path.join(app, "r_key.txt.bak_20260101_000000"), "rh.older-key")
    write(os.path.join(app, "hub_data", "paper", "trader_status.json"), {"account": 1})
    write(os.path.join(app, "hub_data", "runner_ready.json"), {"ready": True})
    write(os.path.join(app, "hub_data", "candles", "BTCUSDT_1h.csv"), "open_time,open\n1,2\n")
    write(os.path.join(app, "memories_1hour.txt"), "btc memories")
    write(os.path.join(app, "low_bound_prices.html"), "<p>1</p>")
    write(os.path.join(app, "ETH", "memories_1hour.txt"), "eth memories")
    write(os.path.join(app, "ETH", "pt_trainer.py"), "# code, not migrated")
    write(os.path.join(app, "order_management.db"), b"SQLite format 3\x00orders")
    write(os.path.join(app, "order_management.db-wal"), b"wal")
    write(os.path.join(app, "credential_audit.jsonl"), '{"a": 1}\n')
    write(os.path.join(root, "market_data.db"), b"SQLite format 3\x00ticks")
    write(os.path.join(root, "data", "holdings.db"), b"SQLite format 3\x00holdings")
    write(os.path.join(root, "logs", "powertrader.log"), "old log line\n")
    return {"app": app, "root": root, "pem": pem, "seed": seed}


def entries(memory_keyring):
    return {user: value for (service, user), value in memory_keyring.entries.items() if service == SERVICE}


# --- fresh migration -------------------------------------------------------------------


def test_fresh_migration_moves_everything_and_touches_no_legacy_file(legacy, memory_keyring):
    before = digest_tree(legacy["app"], legacy["root"])
    report = pt_migrate.migrate()
    assert digest_tree(legacy["app"], legacy["root"]) == before  # nothing changed or deleted

    # credentials: keyring, by the spec's entry names
    assert entries(memory_keyring) == {
        "coinbase:key_name": KEY_NAME,
        "coinbase:private_key": legacy["pem"].strip(),  # stored trimmed
        "binance:api_key": "bin-key-legacy",
        "binance:api_secret": "bin-secret-legacy",
        "kraken:api_key": "kr-key-legacy",
        "kraken:api_secret": "kr-secret-legacy",
        "robinhood:api_key": "rh.legacy-key",
        "robinhood:private_key": legacy["seed"],
    }
    # config: copied without any credential field
    config = pt_paths.config_dir()
    for name in ("pt_config.json", "gui_settings.json", "trading_config.json", "exchange_config.json"):
        with open(os.path.join(config, name), encoding="utf-8") as f:
            text = f.read()
        for leak in ("bin-secret", "kr-secret", "BEGIN EC", KEY_NAME, "rh.legacy"):
            assert leak not in text, name
    with open(os.path.join(config, "exchange_config.json"), encoding="utf-8") as f:
        assert json.load(f) == {"kraken": {"timeout": 5}}
    with open(os.path.join(config, "gui_settings.json"), encoding="utf-8") as f:
        gui = json.load(f)
    assert gui["main_neural_dir"] == "" and gui["hub_data_dir"] == ""  # pointed into app/
    assert gui["trade_start_level"] == 4
    # data, cache, logs, models
    assert os.path.isfile(os.path.join(pt_paths.hub_dir(), "paper", "trader_status.json"))
    assert os.path.isfile(os.path.join(pt_paths.hub_dir(), "runner_ready.json"))
    assert os.path.isfile(os.path.join(pt_paths.cache_dir(), "candles", "BTCUSDT_1h.csv"))
    assert not os.path.exists(os.path.join(pt_paths.hub_dir(), "candles"))
    assert os.path.isfile(os.path.join(pt_paths.models_dir(), "memories_1hour.txt"))
    assert os.path.isfile(os.path.join(pt_paths.models_dir(), "low_bound_prices.html"))
    assert os.path.isfile(os.path.join(pt_paths.models_dir(), "ETH", "memories_1hour.txt"))
    assert not os.path.exists(os.path.join(pt_paths.models_dir(), "ETH", "pt_trainer.py"))
    assert os.path.isfile(os.path.join(pt_paths.data_dir(), "order_management.db"))
    assert os.path.isfile(os.path.join(pt_paths.data_dir(), "order_management.db-wal"))
    assert os.path.isfile(os.path.join(pt_paths.data_dir(), "holdings.db"))
    assert os.path.isfile(os.path.join(pt_paths.cache_dir(), "market_data.db"))
    assert os.path.isfile(os.path.join(pt_paths.log_dir(), "credential_audit.jsonl"))
    assert os.path.isfile(os.path.join(pt_paths.log_dir(), "legacy", "powertrader.log"))
    # report
    assert report.changed and not report.conflicts and not report.errors
    with open(report.report_path, encoding="utf-8") as f:
        text = f.read()
    assert report.report_path == pt_paths.config_file("migration-report.md")
    for entry in ("coinbase:private_key", "binance:api_secret", "kraken:api_key", "robinhood:private_key"):
        assert entry in text
    for leak in ("bin-secret-legacy", "kr-secret-legacy", "BEGIN EC", legacy["seed"], "rh.legacy-key"):
        assert leak not in text
    assert "trader_status.json" in text and "r_key.txt.bak_20260101_000000" in text
    # removable = migrated legacy copies (incl. the old plaintext .bak copy), never code
    removable = set(report.removable)
    for rel in ("trading_config.json", "r_key.txt", "r_secret.txt", "r_key.txt.bak_20260101_000000",
                os.path.join("hub_data", "paper", "trader_status.json"), "memories_1hour.txt"):
        assert os.path.join(legacy["app"], rel) in removable, rel
    assert os.path.join(legacy["app"], "ETH", "pt_trainer.py") not in removable


def test_migrated_settings_are_what_the_app_reads(legacy):
    pt_migrate.migrate()
    from pt_multi_exchange import ExchangeConfigManager
    from trading_mode import read_trading_settings

    assert not read_trading_settings().is_live
    m = ExchangeConfigManager()
    cb = m.load_config() and m.get_exchange_config("coinbase")
    assert (cb.api_key, cb.api_secret, cb.credential_source) == (KEY_NAME, legacy["pem"].strip(), "keyring")


# --- conflicts ----------------------------------------------------------------------------


def test_conflicts_keep_the_new_location_and_are_reported(legacy, memory_keyring):
    new_config = pt_paths.settings_file()
    write(new_config, {"trading": {"mode": "paper"}, "kept": True})
    pt_secrets.set_secret("binance", "api_secret", "already-in-keyring")
    write(os.path.join(pt_paths.hub_dir(), "runner_ready.json"), {"ready": False, "new": True})
    report = pt_migrate.migrate()
    with open(new_config, encoding="utf-8") as f:
        assert json.load(f)["kept"] is True
    with open(os.path.join(pt_paths.hub_dir(), "runner_ready.json"), encoding="utf-8") as f:
        assert json.load(f)["new"] is True
    assert entries(memory_keyring)["binance:api_secret"] == "already-in-keyring"
    conflicted = {src for src, _ in report.conflicts}
    assert os.path.join(legacy["app"], "pt_config.json") in conflicted
    assert os.path.join(legacy["app"], "hub_data", "runner_ready.json") in conflicted
    assert (os.path.join(legacy["app"], "trading_config.json"), "binance:api_secret") in report.secret_conflicts
    # a conflicted legacy file is never offered for removal
    for path in conflicted | {os.path.join(legacy["app"], "trading_config.json")}:
        assert path not in report.removable
    with open(report.report_path, encoding="utf-8") as f:
        text = f.read()
    assert "Conflicts" in text and "already-in-keyring" not in text and "bin-secret-legacy" not in text


# --- idempotent -----------------------------------------------------------------------------


def test_second_run_with_nothing_new_does_nothing(legacy, memory_keyring):
    first = pt_migrate.migrate()
    assert first.changed
    state = pt_paths.config_file(pt_migrate.STATE_FILE)
    stamps = {p: os.stat(p).st_mtime_ns for p in (state, first.report_path)}
    keyring_before = dict(memory_keyring.entries)
    user_before = digest_tree(pt_paths.config_dir(), pt_paths.data_dir(), pt_paths.cache_dir(), pt_paths.log_dir())
    second = pt_migrate.migrate()
    assert not second.changed
    assert second.copied == second.secrets == second.conflicts == second.errors == []
    assert {p: os.stat(p).st_mtime_ns for p in stamps} == stamps
    assert memory_keyring.entries == keyring_before
    assert digest_tree(pt_paths.config_dir(), pt_paths.data_dir(), pt_paths.cache_dir(), pt_paths.log_dir()) == user_before
    assert pt_migrate.run_startup_migration() is None
    assert sorted(second.removable) == sorted(first.removable)


def test_a_legacy_file_changed_later_is_reported_once_as_a_conflict(legacy):
    pt_migrate.migrate()
    path = os.path.join(legacy["app"], "pt_config.json")
    write(path, {"trading": {"mode": "paper"}, "edited_by_old_version": True})
    os.utime(path, ns=(os.stat(path).st_atime_ns, os.stat(path).st_mtime_ns + 10_000_000))
    again = pt_migrate.migrate()
    assert [s for s, _ in again.conflicts] == [path]
    assert not pt_migrate.migrate().changed


# --- no keyring ------------------------------------------------------------------------------


def test_without_a_keyring_secrets_stay_put_and_are_retried(legacy, memory_keyring):
    keyring.set_keyring(keyring.backends.fail.Keyring())
    report = pt_migrate.migrate()
    assert report.errors and all("keyring" in msg for _, msg in report.errors)
    assert os.path.isfile(pt_paths.trading_config_file())  # settings still moved, without secrets
    with open(pt_paths.trading_config_file(), encoding="utf-8") as f:
        assert "bin-secret" not in f.read()
    for name in ("trading_config.json", "exchange_config.json", "r_key.txt", "r_secret.txt"):
        assert os.path.join(legacy["app"], name) not in report.removable
    # later, with a keyring: the credentials are moved on the next run
    keyring.set_keyring(memory_keyring)
    retry = pt_migrate.migrate()
    assert ("coinbase:private_key" in {e for _, e in retry.secrets})
    assert entries(memory_keyring)["robinhood:api_key"] == "rh.legacy-key"
    assert os.path.join(legacy["app"], "trading_config.json") in retry.removable


# --- Robinhood vault -------------------------------------------------------------------------


def test_robinhood_vault_is_decrypted_into_the_keyring(isolated_user_dirs, memory_keyring):
    from pt_credentials import SecureCredentialManager

    app = isolated_user_dirs["legacy"]
    seed = base64.b64encode(b"v" * 32).decode()
    assert SecureCredentialManager(app).encrypt_credentials("rh.vault-key", seed)
    before = digest_tree(app)
    report = pt_migrate.migrate()
    assert digest_tree(app) == before
    assert entries(memory_keyring) == {"robinhood:api_key": "rh.vault-key", "robinhood:private_key": seed}
    for name in ("r_key.enc", "r_secret.enc", ".pt_salt", ".pt_cred_meta"):
        assert os.path.join(app, name) in report.removable
    assert os.path.isfile(pt_paths.config_file("robinhood_rotation.json"))


# --- import from a path ----------------------------------------------------------------------


def test_import_a_backup_config_from_anywhere(tmp_path, memory_keyring):
    backup = write(
        str(tmp_path / "backups" / "trading_config.backup.json"),
        {"user_region": "UK", "primary_exchange": "kraken", "exchanges": [
            {"exchange_type": "kraken", "enabled": True, "region_preference": 1,
             "api_key": "backup-key", "api_secret": "backup-secret", "passphrase": "", "sandbox": False}]},
    )
    before = digest_tree(str(tmp_path / "backups"))
    assert pt_migrate.main(["--from", backup]) == 0
    assert digest_tree(str(tmp_path / "backups")) == before  # nothing deleted or changed
    assert entries(memory_keyring) == {"kraken:api_key": "backup-key", "kraken:api_secret": "backup-secret"}
    with open(pt_paths.trading_config_file(), encoding="utf-8") as f:
        data = json.load(f)
    assert data["primary_exchange"] == "kraken" and "api_secret" not in data["exchanges"][0]
    with open(pt_paths.config_file("migration-report.md"), encoding="utf-8") as f:
        assert "kraken:api_secret" in f.read()


def test_import_detects_kind_by_content_and_never_overwrites(tmp_path):
    write(pt_paths.settings_file(), {"trading": {"mode": "paper"}, "mine": 1})
    other = write(str(tmp_path / "old-settings.json"), {"trading": {"mode": "live"}, "strategy": {}})
    report = pt_migrate.import_config_file(other)
    assert [t for _, t in report.conflicts] == [pt_paths.settings_file()]
    with open(pt_paths.settings_file(), encoding="utf-8") as f:
        assert json.load(f)["mine"] == 1
    bad = write(str(tmp_path / "notes.json"), [1, 2, 3])
    assert pt_migrate.import_config_file(bad).errors
    assert pt_migrate.import_config_file(str(tmp_path / "missing.json")).errors


# --- removing old files ------------------------------------------------------------------------


def test_old_files_are_removed_only_after_confirmation(legacy):
    report = pt_migrate.migrate()
    target = os.path.join(legacy["app"], "trading_config.json")
    assert target in report.removable
    assert pt_migrate.remove_legacy_files(confirmed=False) == []
    assert os.path.exists(target)
    # a file the migration did not record is never deleted, even when asked
    code = os.path.join(legacy["app"], "ETH", "pt_trainer.py")
    assert pt_migrate.remove_legacy_files([code, target], confirmed=True) == [target]
    assert os.path.exists(code) and not os.path.exists(target)
    removed = pt_migrate.remove_legacy_files(confirmed=True)
    assert os.path.join(legacy["app"], "r_secret.txt") in removed
    assert not os.path.exists(os.path.join(legacy["app"], "hub_data"))  # emptied folders pruned
    assert os.path.isdir(legacy["app"])  # never the program folder itself


def test_cli_remove_old_files_asks_first(legacy, monkeypatch):
    pt_migrate.migrate()
    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    assert pt_migrate.main(["--remove-old-files"]) == 1
    assert os.path.exists(os.path.join(legacy["app"], "r_key.txt"))
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    assert pt_migrate.main(["--remove-old-files"]) == 0
    assert not os.path.exists(os.path.join(legacy["app"], "r_key.txt"))


class TestMigrationDialog(unittest.TestCase):
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

    @pytest.fixture(autouse=True)
    def _legacy(self, legacy):
        self.legacy = legacy

    def test_remove_button_deletes_only_after_yes(self):
        report = pt_migrate.migrate()
        box = mock.MagicMock()
        box.askyesno.return_value = False
        win = pt_migrate.show_migration_dialog(self.root, report, messagebox=box)
        self.addCleanup(win.destroy)
        win.remove_old_files()
        box.askyesno.assert_called_once()
        warning = box.askyesno.call_args[0][1]
        self.assertIn("plain text", warning)
        self.assertTrue(os.path.exists(os.path.join(self.legacy["app"], "r_key.txt")))
        box.askyesno.return_value = True
        win.remove_old_files()
        self.assertFalse(os.path.exists(os.path.join(self.legacy["app"], "r_key.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.legacy["app"], "ETH", "pt_trainer.py")))
