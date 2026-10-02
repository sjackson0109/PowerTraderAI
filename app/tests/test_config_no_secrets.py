"""FDS-108a phase 3: config files hold no secret fields. A credential found in a
loaded config is ignored, logged (by key, never by value) and never written back."""

import json
import logging
import os
import sys

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_paths  # noqa: E402
import pt_secrets  # noqa: E402


def test_strip_secret_fields_is_recursive_and_quiet_about_values(caplog):
    data = {
        "trading": {"mode": "paper"},
        "llm": {"openai_api_key": "sk-leak-1", "model": "x"},
        "exchanges": [{"name": "binance", "api_secret": "leak-2", "api_key_length": 32}],
        "security": {"webhook_secret": "leak-3", "key_rotation_days": 90},
        "smtp": {"password": "leak-4", "server": "smtp.example"},
    }
    with caplog.at_level(logging.WARNING, logger="pt_secrets"):
        clean = pt_secrets.strip_secret_fields(data, "x.json")
    assert clean == {
        "trading": {"mode": "paper"},
        "llm": {"model": "x"},
        "exchanges": [{"name": "binance", "api_key_length": 32}],
        "security": {"key_rotation_days": 90},
        "smtp": {"server": "smtp.example"},
    }
    for leak in ("sk-leak-1", "leak-2", "leak-3", "leak-4"):
        assert leak not in caplog.text
    assert "llm.openai_api_key" in caplog.text and "exchanges[0].api_secret" in caplog.text
    assert data["llm"]["openai_api_key"] == "sk-leak-1"  # input untouched


def test_settings_manager_ignores_and_never_writes_back_a_secret(caplog):
    from pt_settings_manager import SettingsManager

    path = pt_paths.settings_file()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"trading": {"mode": "paper"}, "broker": {"api_secret": "pt-config-leak"}}, f)
    with caplog.at_level(logging.WARNING):
        sm = SettingsManager()
    assert sm.get("broker.api_secret") is None
    assert "pt-config-leak" not in caplog.text
    assert sm.save_settings()
    with open(path, encoding="utf-8") as f:
        assert "pt-config-leak" not in f.read()
    sm.set("broker.api_secret", "set-at-runtime")  # even set in memory, never persisted
    sm.save_settings()
    with open(path, encoding="utf-8") as f:
        assert "set-at-runtime" not in f.read()


def test_settings_export_and_import_drop_secrets(tmp_path):
    from pt_settings_manager import SettingsManager

    sm = SettingsManager()
    out = tmp_path / "export.json"
    sm.set("broker.passphrase", "export-leak")
    assert sm.export_settings(str(out))
    assert "export-leak" not in out.read_text(encoding="utf-8")
    src = tmp_path / "import.json"
    src.write_text(json.dumps({"coins": ["BTC"], "x": {"private_key": "import-leak"}}), encoding="utf-8")
    sm.import_settings(str(src))
    assert sm.get("x.private_key") is None


def test_yaml_config_never_holds_credentials(tmp_path):
    pytest.importorskip("yaml")
    from pt_config import ConfigurationManager

    folder = tmp_path / "yaml"
    folder.mkdir()
    (folder / "exchange.yaml").write_text(
        "name: kraken\napi_key: yaml-key-leak\napi_secret: yaml-secret-leak\n", encoding="utf-8"
    )
    cm = ConfigurationManager(str(folder), enable_hot_reload=False)
    assert cm.exchange.name == "kraken"
    assert cm.exchange.api_key == "" and cm.exchange.api_secret == ""
    cm.exchange.api_key = "runtime-key"
    cm.security.webhook_secret = "runtime-hook"
    cm.save_current_config()
    for name in os.listdir(folder):
        text = (folder / name).read_text(encoding="utf-8")
        for leak in ("yaml-key-leak", "yaml-secret-leak", "runtime-key", "runtime-hook"):
            assert leak not in text, name


def test_default_yaml_folder_is_in_the_user_config_folder():
    pytest.importorskip("yaml")
    from pt_config import ConfigurationManager

    cm = ConfigurationManager(enable_hot_reload=False)
    assert str(cm.config_dir) == os.path.join(pt_paths.config_dir(), "yaml")


def test_monitoring_config_has_no_smtp_password(tmp_path, monkeypatch):
    pytest.importorskip("psutil")
    from pt_live_monitor import LiveMonitor

    monitor = LiveMonitor()
    assert monitor.config_path == pt_paths.config_file("monitoring.json")
    with open(monitor.config_path, encoding="utf-8") as f:
        saved = json.load(f)
    assert "password" not in saved["alerts"]["smtp_settings"]
    monkeypatch.setenv("POWERTRADER_SMTP_PASSWORD", "smtp-from-env")
    assert pt_secrets.get_secret("smtp", "password").reveal() == "smtp-from-env"


def test_shipped_template_installs_once_with_no_credentials():
    target = pt_paths.install_default("trading_config.example.json")
    assert target == pt_paths.trading_config_file()
    with open(target, encoding="utf-8") as f:
        data = json.load(f)
    for ex in data["exchanges"]:
        for key in ("api_key", "api_secret", "passphrase"):
            assert not ex.get(key)
    assert pt_paths.install_default("trading_config.example.json") is None
