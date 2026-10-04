"""pt_paths: one place that knows where config, data, logs and cache live (FDS-108a)."""

import importlib.util
import os
import stat
import sys
import unittest
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_paths  # noqa: E402


def fresh_pt_paths():
    """A private copy of pt_paths with the real platform lookup (conftest blocks
    it on the shared module). Only path strings are computed; nothing is created."""
    spec = importlib.util.spec_from_file_location("pt_paths_fresh", pt_paths.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def home(isolated_user_dirs):
    return isolated_user_dirs["home"]


def test_home_override_puts_everything_under_it(home):
    assert pt_paths.config_dir() == os.path.join(home, "config")
    assert pt_paths.data_dir() == os.path.join(home, "data")
    assert pt_paths.log_dir() == os.path.join(home, "logs")
    assert pt_paths.cache_dir() == os.path.join(home, "cache")
    assert pt_paths.hub_dir() == os.path.join(home, "data", "hub_data")
    assert pt_paths.models_dir() == os.path.join(home, "data", "hub_data", "models")


def test_directories_are_created_lazily(home):
    described = pt_paths.describe()
    assert not os.path.exists(home)
    assert described["config"] == os.path.join(home, "config")
    path = pt_paths.config_dir()
    assert os.path.isdir(path)
    assert not os.path.exists(os.path.join(home, "data"))
    assert not os.path.exists(pt_paths.log_dir(create=False))


def test_ensure_dirs_creates_every_folder(home):
    made = pt_paths.ensure_dirs()
    assert set(made) == {"config", "data", "logs", "cache", "hub_data", "models"}
    for path in made.values():
        assert os.path.isdir(path)
        assert path.startswith(home)


def test_named_files_live_in_config_dir(home):
    config = os.path.join(home, "config")
    assert pt_paths.settings_file() == os.path.join(config, "pt_config.json")
    assert pt_paths.gui_settings_file() == os.path.join(config, "gui_settings.json")
    assert pt_paths.trading_config_file() == os.path.join(config, "trading_config.json")
    assert pt_paths.exchange_config_file() == os.path.join(
        config, "exchange_config.json"
    )


def test_program_dir_is_the_app_folder():
    assert os.path.normcase(pt_paths.program_dir()) == os.path.normcase(APP_DIR)
    assert pt_paths.is_inside_program_dir(os.path.join(APP_DIR, "x.json"))
    assert not pt_paths.is_inside_program_dir(pt_paths.config_dir())


def test_without_override_the_platform_folders_are_used(monkeypatch, tmp_path):
    monkeypatch.delenv("POWERTRADER_HOME")
    fake = {
        k: str(tmp_path / f"platform_{k}") for k in ("config", "data", "log", "cache")
    }
    monkeypatch.setattr(pt_paths, "_platform_dir", lambda kind: fake[kind])
    assert pt_paths.config_dir() == fake["config"]
    assert pt_paths.data_dir() == fake["data"]
    assert pt_paths.log_dir() == fake["log"]
    assert pt_paths.cache_dir() == fake["cache"]
    assert pt_paths.hub_dir() == os.path.join(fake["data"], "hub_data")


def test_platformdirs_is_asked_with_the_spec_names_and_roaming_flags():
    fresh = fresh_pt_paths()
    import platformdirs

    calls = {}

    def recorder(name):
        def f(*args, **kwargs):
            calls[name] = (args, kwargs)
            return f"/fake/{name}"

        return f

    with mock.patch.multiple(
        platformdirs,
        user_config_dir=recorder("config"),
        user_data_dir=recorder("data"),
        user_log_dir=recorder("log"),
        user_cache_dir=recorder("cache"),
    ):
        for kind in ("config", "data", "log", "cache"):
            fresh._platform_dir(kind)
    assert calls["config"] == (("PowerTraderAI", "SJackson"), {"roaming": True})
    assert calls["data"] == (("PowerTraderAI", "SJackson"), {"roaming": False})
    assert calls["log"] == (("PowerTraderAI", "SJackson"), {})
    assert calls["cache"] == (("PowerTraderAI", "SJackson"), {})


@pytest.mark.skipif(os.name != "nt", reason="Windows folder layout")
def test_windows_layout_matches_the_spec():
    # Computes the strings only (platformdirs does not create folders here).
    fresh = fresh_pt_paths()
    appdata = os.environ["APPDATA"]
    local = os.environ["LOCALAPPDATA"]
    norm = os.path.normcase
    assert norm(fresh._platform_dir("config")) == norm(
        os.path.join(appdata, "SJackson", "PowerTraderAI")
    )
    assert norm(fresh._platform_dir("data")) == norm(
        os.path.join(local, "SJackson", "PowerTraderAI")
    )
    assert norm(fresh._platform_dir("log")) == norm(
        os.path.join(local, "SJackson", "PowerTraderAI", "Logs")
    )
    assert norm(fresh._platform_dir("cache")) == norm(
        os.path.join(local, "SJackson", "PowerTraderAI", "Cache")
    )


def test_bare_names_and_no_escape(home):
    with pytest.raises(ValueError):
        pt_paths.config_file("../evil.json")
    with pytest.raises(ValueError):
        pt_paths.config_file(os.path.join("sub", "x.json"))
    with pytest.raises(ValueError):
        pt_paths.data_file("..", "..", "outside.txt")
    path = pt_paths.data_file("hub_data", "paper", "trader_status.json")
    assert os.path.isdir(os.path.dirname(path))


def test_install_default_copies_once_and_never_overwrites(home, tmp_path, monkeypatch):
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    (shipped / "thing.example.json").write_text('{"v": 1}', encoding="utf-8")
    monkeypatch.setattr(pt_paths, "program_dir", lambda: str(shipped))
    target = pt_paths.install_default("thing.example.json")
    assert target == pt_paths.config_file("thing.json")
    with open(target, encoding="utf-8") as f:
        assert f.read() == '{"v": 1}'
    with open(target, "w", encoding="utf-8") as f:
        f.write('{"v": 2}')
    assert pt_paths.install_default("thing.example.json") is None
    with open(target, encoding="utf-8") as f:
        assert f.read() == '{"v": 2}'
    assert pt_paths.install_default("missing.example.json") is None


def test_write_private_text_is_atomic_and_leaves_no_temp(home):
    path = pt_paths.config_file("x.json")
    pt_paths.write_private_text(path, "one")
    pt_paths.write_private_text(path, "two")
    with open(path, encoding="utf-8") as f:
        assert f.read() == "two"
    assert os.listdir(os.path.dirname(path)) == ["x.json"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
def test_posix_modes_are_private(home):
    path = pt_paths.config_file("x.json")
    pt_paths.write_private_text(path, "{}")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(pt_paths.config_dir()).st_mode) == 0o700


if __name__ == "__main__":
    unittest.main()
