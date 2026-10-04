"""FDS-108a phase 5: users can see where their files are, the shipped template
holds no credential field, and stale legacy files cannot be committed."""

import json
import os
import sys
from unittest import mock

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO_DIR = os.path.dirname(APP_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_paths  # noqa: E402


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_readme_explains_where_data_lives():
    text = read(os.path.join(REPO_DIR, "README.md"))
    assert "## Where your data lives" in text
    for needle in (
        r"%APPDATA%\SJackson\PowerTraderAI",
        r"%LOCALAPPDATA%\SJackson\PowerTraderAI",
        r"%LOCALAPPDATA%\SJackson\PowerTraderAI\Logs",
        r"%LOCALAPPDATA%\SJackson\PowerTraderAI\Cache",
        "~/Library/Application Support/PowerTraderAI/",
        "~/Library/Logs/PowerTraderAI/",
        "~/.config/PowerTraderAI/",
        "~/.local/share/PowerTraderAI/",
        "~/.local/state/PowerTraderAI/log/",
        "~/.cache/PowerTraderAI/",
        "Windows Credential Manager",
        "Keychain",
        "Secret Service",
        "POWERTRADER_HOME",
        "pt_migrate.py --from",
    ):
        assert needle in text, needle


def test_shipped_template_has_no_credential_fields_and_points_to_the_setup_window():
    data = json.loads(read(os.path.join(APP_DIR, "trading_config.example.json")))
    assert "Configure exchange APIs" in data["_note"]
    for ex in data["exchanges"]:
        assert not {"api_key", "api_secret", "passphrase"} & set(ex), ex[
            "exchange_type"
        ]


def test_settings_window_lists_config_data_and_log_folders():
    import pt_hub

    rows = pt_hub.PowerTraderHub._user_folder_rows()
    assert rows == [
        ("Config folder:", pt_paths.config_dir()),
        ("Data folder:", pt_paths.data_dir()),
        ("Log folder:", pt_paths.log_dir()),
    ]
    folder = pt_paths.log_dir()
    if os.name == "nt":
        with mock.patch.object(pt_hub.os, "startfile", create=True) as start:
            pt_hub.PowerTraderHub._open_user_folder(object(), folder)
        start.assert_called_once_with(folder)
    else:
        with mock.patch.object(pt_hub.subprocess, "Popen") as popen:
            pt_hub.PowerTraderHub._open_user_folder(object(), folder)
        assert popen.call_args[0][0][-1] == folder


def test_gitignore_covers_the_legacy_runtime_files():
    lines = {
        line.strip() for line in read(os.path.join(REPO_DIR, ".gitignore")).splitlines()
    }
    for pattern in (
        "app/pt_config.json",
        "app/gui_settings.json",
        "app/trading_config.json",
        "app/exchange_config.json",
        "hub_data/",
        "app/r_key*",
        "app/r_secret*",
        "app/.pt_salt",
        "app/.pt_cred_meta*",
        "app/credential_audit.jsonl",
        "*.db",
        "logs/",
        "cache/",
        "emergency_snapshot_*.json",
    ):
        assert pattern in lines, pattern


def test_user_docs_no_longer_send_people_to_files_under_app():
    docs = [
        "docs/exchanges/coinbase-setup.md",
        "docs/setup/CREDENTIAL_SETUP.md",
        "docs/reference/QUICK_REFERENCE.md",
        "docs/user-guide/README.md",
    ]
    for rel in docs:
        text = read(os.path.join(REPO_DIR, rel))
        assert "written to `app/trading_config.json`" not in text, rel
        assert "Create `credentials/exchange_config.json`" not in text, rel
        assert "Create secure files: `r_key.enc`" not in text, rel
        assert "holds your API keys in plain text" not in text, rel
