"""Guard: no test may touch the real per-user config, data or credential
locations (FDS-108a). The isolation itself lives in app/conftest.py; these
tests prove it is in force."""

import os
import subprocess
import sys

import pytest

import pt_paths


def _real_dirs():
    import importlib.util

    spec = importlib.util.spec_from_file_location("pt_paths_real", pt_paths.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {k: module._platform_dir(k) for k in ("config", "data", "log", "cache")}


def _inside(path, folder):
    path, folder = os.path.normcase(os.path.abspath(path)), os.path.normcase(
        os.path.abspath(folder)
    )
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:
        return False


def test_home_override_is_a_temp_folder(isolated_user_dirs, tmp_path):
    home = os.environ["POWERTRADER_HOME"]
    assert home == isolated_user_dirs["home"]
    assert _inside(home, str(tmp_path))


def test_no_resolved_folder_is_a_real_user_folder(isolated_user_dirs):
    real = _real_dirs()
    for kind, path in pt_paths.ensure_dirs().items():
        for real_path in real.values():
            assert not _inside(path, real_path), f"{kind} resolved to a real folder"


def test_resolving_the_real_folders_fails_inside_tests(monkeypatch):
    monkeypatch.delenv("POWERTRADER_HOME")
    with pytest.raises(AssertionError, match="POWERTRADER_HOME"):
        pt_paths.config_dir()


def test_legacy_folder_is_empty_temp_not_the_program_dir(isolated_user_dirs):
    legacy = pt_paths.legacy_dir()
    assert legacy == isolated_user_dirs["legacy"]
    assert os.listdir(legacy) == []
    assert not pt_paths.is_inside_program_dir(legacy)


def test_keyring_is_in_memory(memory_keyring):
    import keyring
    import pt_secrets

    assert keyring.get_keyring() is memory_keyring
    assert pt_secrets._backend() is memory_keyring
    pt_secrets.set_secret("binance", "api_key", "guard-test-key")
    assert memory_keyring.entries == {
        ("SJackson.PowerTraderAI", "binance:api_key"): "guard-test-key"
    }


def test_child_processes_cannot_reach_the_real_keyring():
    code = (
        "import keyring, sys; b = keyring.get_keyring(); "
        "sys.stdout.write(type(b).__module__ + '.' + type(b).__name__)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        env=os.environ.copy(),
    )
    assert out.stdout.strip() == "keyring.backends.fail.Keyring", out.stderr


@pytest.mark.parametrize("start", ["repo root", "app/tests"])
def test_the_guard_is_in_force_wherever_pytest_is_started(start):
    """The safety audit's finding: pytest started inside app/tests takes that
    folder as its root and never read app/conftest.py, so no test there was
    isolated. Only the set-up plan is printed: no test body runs."""
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(tests_dir))
    cwd, target = (
        (repo, os.path.join("app", "tests", "test_pt_paths.py"))
        if start == "repo root"
        else (tests_dir, "test_pt_paths.py")
    )
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--setup-plan",
            "-p",
            "no:cacheprovider",
            target,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        env=os.environ.copy(),
    )
    assert out.returncode == 0, out.stdout + out.stderr
    lines = out.stdout.splitlines()
    tests = [line for line in lines if "test_pt_paths.py::" in line]
    setups = [
        line
        for line in lines
        if line.split()[:3] == ["SETUP", "F", "isolated_user_dirs"]
    ]
    assert tests and len(setups) == len(tests), out.stdout
