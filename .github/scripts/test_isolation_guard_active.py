"""FDS-108a review item 6: the tests under .github/scripts run inside the same
isolation guard as the tests under app/ (app/tests/isolation.py, loaded by
.github/scripts/conftest.py), so they can never reach the real per-user
folders or the real credential store."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

import pt_paths  # noqa: E402
import pt_trader  # noqa: E402  (resolves its folders at import time)


def _inside(path, folder):
    path, folder = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:
        return False


def _session_home():
    return sys.modules["powertrader_test_isolation"]._SESSION_HOME


def test_the_guard_was_loaded_before_test_modules_resolved_folders():
    assert os.path.basename(_session_home()).startswith("pt_test_home_")
    assert _inside(pt_trader.main_dir, _session_home())


def test_powertrader_home_is_a_fresh_temp_folder(isolated_user_dirs, tmp_path):
    assert os.environ["POWERTRADER_HOME"] == isolated_user_dirs["home"]
    assert _inside(os.environ["POWERTRADER_HOME"], str(tmp_path))


def test_resolving_the_real_folders_fails(monkeypatch):
    # _resolve only names the folder (config_dir() would also create it), so
    # this test cannot create the real folder even if the guard were missing.
    monkeypatch.delenv("POWERTRADER_HOME")
    with pytest.raises(AssertionError, match="POWERTRADER_HOME"):
        pt_paths._resolve("config")


def test_the_keyring_is_in_memory_and_children_get_the_fail_backend(memory_keyring):
    import keyring

    assert keyring.get_keyring() is memory_keyring
    assert os.environ["PYTHON_KEYRING_BACKEND"] == "keyring.backends.fail.Keyring"
