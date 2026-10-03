"""FDS-108a review item 5: a missing package is named, with how to install it.

* ``platformdirs``: every folder lookup raises ``pt_paths.MissingDependency``
  (an ``ImportError``). The hub reports that, not "Multi-exchange support not
  available", and stops before its window opens: exit code 1, no traceback,
  and an error box when Tk can open one.
* ``keyring``: nothing changes about what is stored (nothing; paper mode, no
  plaintext file). The message names the package and how to install it instead
  of saying the OS has no credential store, and the cause is logged once.

A missing package is simulated with ``sys.modules[name] = None``; nothing is
uninstalled. Child processes block the package the same way; their legacy
folders are a temp folder and the hub window is never created.
"""

import logging
import os
import subprocess
import sys
import tkinter as tk

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for folder in (APP_DIR, TESTS_DIR):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import keyring  # noqa: E402
import keyring.backends.fail  # noqa: E402

import pt_hub  # noqa: E402
import pt_migrate  # noqa: E402
import pt_paths  # noqa: E402
import pt_secrets  # noqa: E402
from test_pt_migrate import entries, legacy, no_credential_env  # noqa: E402,F401
from test_pt_paths import fresh_pt_paths  # noqa: E402

INSTALL_ALL = "python -m pip install -r requirements.txt"
OLD_KEYRING_MESSAGE = "No secure credential store (OS keyring) is available on this system"


def missing(monkeypatch, *packages):
    """Make ``import <package>`` fail as if it were not installed."""
    for name in packages:
        monkeypatch.setitem(sys.modules, name, None)


def user_files(isolated_user_dirs):
    found = []
    for root, _, files in os.walk(isolated_user_dirs["home"]):
        found += [os.path.join(root, f) for f in files]
    return found


# --- pt_paths: platformdirs ------------------------------------------------------------------


def test_without_platformdirs_every_folder_lookup_names_the_package(monkeypatch):
    monkeypatch.delenv("POWERTRADER_HOME")
    missing(monkeypatch, "platformdirs")
    fresh = fresh_pt_paths()  # the real lookup (conftest blocks it on the shared module)
    lookups = [lambda kind=kind: fresh._platform_dir(kind) for kind in ("config", "data", "log", "cache")]
    lookups += [fresh.config_dir, fresh.data_dir, fresh.log_dir, fresh.cache_dir, fresh.describe,
                fresh.check_dependencies]
    for lookup in lookups:
        with pytest.raises(fresh.MissingDependency) as err:
            lookup()
        assert isinstance(err.value, ImportError) and err.value.name == "platformdirs"
        assert isinstance(err.value.__cause__, ImportError)
        message = str(err.value)
        assert "'platformdirs' is not installed" in message
        assert INSTALL_ALL in message and "pip install platformdirs" in message
    with pytest.raises(pt_paths.MissingDependency):
        pt_paths.check_dependencies()


def test_with_powertrader_home_platformdirs_is_not_needed(isolated_user_dirs, monkeypatch):
    missing(monkeypatch, "platformdirs")
    pt_paths.check_dependencies()
    fresh = fresh_pt_paths()
    fresh.check_dependencies()
    assert fresh.config_dir(create=False) == os.path.join(isolated_user_dirs["home"], "config")


def test_with_platformdirs_installed_the_check_passes(monkeypatch):
    monkeypatch.delenv("POWERTRADER_HOME")
    pt_paths.check_dependencies()  # imports platformdirs only; no folder is resolved


# --- the hub: platformdirs -------------------------------------------------------------------


class FakeRoot:
    """Stands in for tk.Tk behind the error box: no window in tests."""

    made = []

    def __init__(self):
        self.calls = []
        FakeRoot.made.append(self)

    def withdraw(self):
        self.calls.append("withdraw")

    def destroy(self):
        self.calls.append("destroy")


@pytest.fixture
def start(monkeypatch):
    """``pt_hub.main()`` with a fake hub window and a recorded error box.
    Returns what happened: hubs made, mainloop calls, error boxes shown."""
    seen = {"hubs": 0, "mainloops": 0, "boxes": []}

    class Hub:
        def __init__(self):
            seen["hubs"] += 1

        def mainloop(self):
            seen["mainloops"] += 1

    monkeypatch.setattr(pt_hub, "PowerTraderHub", Hub)
    monkeypatch.setattr(pt_hub.messagebox, "showerror",
                        lambda title, message, **kw: seen["boxes"].append((title, message)))
    monkeypatch.setattr(pt_hub.tk, "Tk", FakeRoot)
    FakeRoot.made = []
    return seen


def test_without_platformdirs_the_hub_stops_with_the_message_and_an_error_box(start, monkeypatch, capsys):
    monkeypatch.delenv("POWERTRADER_HOME")
    missing(monkeypatch, "platformdirs")
    with pytest.raises(SystemExit) as err:
        pt_hub.main()
    assert err.value.code == 1
    assert start["hubs"] == 0 and start["mainloops"] == 0  # stopped before the window
    [(title, message)] = start["boxes"]
    assert title == "PowerTraderAI cannot start"
    assert "'platformdirs' is not installed" in message
    assert INSTALL_ALL in message and "pip install platformdirs" in message
    [root] = FakeRoot.made
    assert root.calls == ["withdraw", "destroy"]
    stderr = capsys.readouterr().err
    assert stderr.startswith("PowerTraderAI cannot start.") and message in stderr


def test_without_a_usable_tk_the_hub_still_stops_cleanly(start, monkeypatch, capsys):
    monkeypatch.delenv("POWERTRADER_HOME")
    missing(monkeypatch, "platformdirs")

    def no_display():
        raise tk.TclError("no display name and no $DISPLAY environment variable")

    monkeypatch.setattr(pt_hub.tk, "Tk", no_display)
    with pytest.raises(SystemExit) as err:
        pt_hub.main()
    assert err.value.code == 1
    assert start["hubs"] == 0 and start["boxes"] == []
    stderr = capsys.readouterr().err
    assert "'platformdirs' is not installed" in stderr and "pip install platformdirs" in stderr


@pytest.mark.parametrize("case", ["platformdirs installed", "POWERTRADER_HOME set"])
def test_when_the_folders_can_be_found_the_hub_starts_as_before(start, monkeypatch, case):
    if case == "platformdirs installed":
        monkeypatch.delenv("POWERTRADER_HOME")
    else:
        missing(monkeypatch, "platformdirs")
    pt_hub.main()
    assert start["hubs"] == 1 and start["mainloops"] == 1
    assert start["boxes"] == [] and FakeRoot.made == []


# Runs in a child process: imports pt_hub from app/ with a package missing, then
# calls main(). The legacy folders are a temp folder, the hub class is replaced
# (it must never be reached here), and the error box prints instead of showing.
HUB_CHILD = r"""
import sys
app, legacy, blocked = sys.argv[1:4]
sys.modules[blocked] = None
sys.path.insert(0, app)
import pt_paths
pt_paths.legacy_dir = pt_paths.legacy_install_dir = lambda: legacy
import pt_hub

class Root:
    def withdraw(self): pass
    def destroy(self): pass

def started():
    raise SystemExit("HUB STARTED")

pt_hub.tk.Tk = Root
pt_hub.messagebox.showerror = lambda title, message, **kw: print("ERROR BOX:", title, "|", message)
pt_hub.PowerTraderHub = started
print("EXCHANGE_SUPPORT_AVAILABLE", pt_hub.EXCHANGE_SUPPORT_AVAILABLE)
if "--main" in sys.argv:
    pt_hub.main()
"""


def run_hub_child(tmp_path, blocked, home=None, main=False):
    legacy_dir = tmp_path / "child_legacy"
    legacy_dir.mkdir()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
               PYTHON_KEYRING_BACKEND="keyring.backends.fail.Keyring")
    env.pop("POWERTRADER_HOME", None)
    if home:
        env["POWERTRADER_HOME"] = home
    args = [sys.executable, "-c", HUB_CHILD, APP_DIR, str(legacy_dir), blocked] + (["--main"] if main else [])
    cwd = tmp_path / "child_cwd"
    cwd.mkdir()
    out = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=300, env=env, cwd=str(cwd))
    assert os.listdir(cwd) == [] and os.listdir(legacy_dir) == []
    return out


def test_the_hub_started_without_platformdirs_says_so_and_exits_without_a_traceback(tmp_path):
    out = run_hub_child(tmp_path, "platformdirs", main=True)
    text = out.stdout + out.stderr
    assert out.returncode == 1, text
    assert "Traceback" not in text and "HUB STARTED" not in text
    assert "Multi-exchange support not available" not in text
    # the import guard reports the real cause ...
    assert "Warning: The Python package 'platformdirs' is not installed" in out.stdout
    assert "EXCHANGE_SUPPORT_AVAILABLE False" in out.stdout
    # ... and main() stops with it, on the console and in the error box
    assert "PowerTraderAI cannot start. The Python package 'platformdirs' is not installed" in out.stderr
    assert INSTALL_ALL in out.stderr and "pip install platformdirs" in out.stderr
    assert "ERROR BOX: PowerTraderAI cannot start | The Python package 'platformdirs'" in out.stdout


def test_the_multi_exchange_guard_names_another_missing_package(tmp_path, isolated_user_dirs):
    out = run_hub_child(tmp_path, "requests", home=isolated_user_dirs["home"])
    text = out.stdout + out.stderr
    assert out.returncode == 0, text
    assert "Traceback" not in text
    warning = next(line for line in out.stdout.splitlines() if "Multi-exchange support not available" in line)
    assert "requests" in warning and INSTALL_ALL in warning
    assert "EXCHANGE_SUPPORT_AVAILABLE False" in out.stdout


# --- pt_secrets: keyring ----------------------------------------------------------------------


@pytest.fixture
def no_keyring_package(monkeypatch):
    """The keyring package is not installed; its cause has not been logged yet."""
    monkeypatch.setattr(pt_secrets, "_missing_package_logged", False)
    missing(monkeypatch, "keyring")


def test_a_missing_keyring_package_is_named_and_nothing_is_stored(
    no_keyring_package, memory_keyring, isolated_user_dirs, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    before = set(os.listdir(tmp_path))
    assert pt_secrets.keyring_package_missing()
    assert not pt_secrets.keyring_available() and pt_secrets.backend_name() == "none"
    with pytest.raises(pt_secrets.KeyringUnavailable) as err:
        pt_secrets.set_secret("coinbase", "private_key", "plaintext-must-not-land")
    message = str(err.value)
    assert "'keyring' is not installed" in message
    assert INSTALL_ALL in message and "pip install keyring" in message
    assert OLD_KEYRING_MESSAGE not in message
    assert "POWERTRADER_COINBASE_API_KEY" in message and "POWERTRADER_COINBASE_API_SECRET" in message
    assert "paper mode" in message and "plain file" in message
    assert "plaintext-must-not-land" not in message
    with pytest.raises(pt_secrets.KeyringUnavailable) as err:
        pt_secrets.set_credentials("binance", {"api_key": "k", "api_secret": "s"})
    assert "'keyring' is not installed" in str(err.value)
    assert "POWERTRADER_<EXCHANGE>_API_KEY" in pt_secrets.unavailable_message()
    # fail closed: nothing stored anywhere, nothing read back
    assert memory_keyring.entries == {}
    assert set(os.listdir(tmp_path)) == before
    assert user_files(isolated_user_dirs) == []
    assert pt_secrets.get_secret("coinbase", "private_key") is None
    assert pt_secrets.get_credentials("binance") is None
    assert pt_secrets.delete_secret("binance", "api_key") is False


def test_the_missing_keyring_package_is_logged_once(no_keyring_package, caplog):
    with caplog.at_level(logging.WARNING, logger="pt_secrets"):
        for _ in range(3):
            assert pt_secrets.get_credentials("kraken") is None
            with pytest.raises(pt_secrets.KeyringUnavailable):
                pt_secrets.set_secret("kraken", "api_key", "log-value-123")
    logged = [r.getMessage() for r in caplog.records if "'keyring' is not installed" in r.getMessage()]
    assert len(logged) == 1
    assert INSTALL_ALL in logged[0] and "pip install keyring" in logged[0]
    assert "log-value-123" not in caplog.text


def test_environment_credentials_still_work_without_the_keyring_package(no_keyring_package, monkeypatch):
    monkeypatch.setenv("POWERTRADER_KRAKEN_API_KEY", "k")
    monkeypatch.setenv("POWERTRADER_KRAKEN_API_SECRET", "s")
    creds = pt_secrets.get_credentials("kraken")
    assert creds.source == "environment" and dict(creds) == {"api_key": "k", "api_secret": "s"}


def test_without_a_usable_backend_the_message_is_unchanged(caplog):
    keyring.set_keyring(keyring.backends.fail.Keyring())
    with caplog.at_level(logging.WARNING, logger="pt_secrets"):
        assert not pt_secrets.keyring_package_missing()
        with pytest.raises(pt_secrets.KeyringUnavailable) as err:
            pt_secrets.set_secret("coinbase", "private_key", "x" * 8)
    message = str(err.value)
    assert message.startswith(OLD_KEYRING_MESSAGE)
    assert "pip install" not in message and "'keyring'" not in message
    assert "not installed" not in caplog.text


def test_the_migration_names_the_missing_keyring_package_and_retries_later(
    no_keyring_package, legacy, memory_keyring, monkeypatch
):
    report = pt_migrate.migrate()
    assert report.errors
    for _, msg in report.errors:
        assert "the Python package 'keyring' is not installed" in msg and INSTALL_ALL in msg
        assert "no OS keyring" not in msg
    assert memory_keyring.entries == {}
    with open(pt_paths.trading_config_file(), encoding="utf-8") as f:
        assert "bin-secret" not in f.read()  # settings moved, credentials not
    for name in ("trading_config.json", "exchange_config.json", "r_key.txt", "r_secret.txt"):
        assert os.path.join(legacy["app"], name) not in report.removable
    # once the package is installed, the next run moves them
    monkeypatch.setitem(sys.modules, "keyring", keyring)
    retry = pt_migrate.migrate()
    assert "coinbase:private_key" in {e for _, e in retry.secrets}
    assert entries(memory_keyring)["robinhood:api_key"] == "rh.legacy-key"
