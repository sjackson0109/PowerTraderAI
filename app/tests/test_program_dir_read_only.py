"""FDS-108a: with default paths, the components write nothing inside the
program/install folder; everything lands under the user folders."""

import os
import sys

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_paths  # noqa: E402

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv"}


def snapshot(root):
    state = {}
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            path = os.path.join(folder, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            state[os.path.relpath(path, root)] = (st.st_size, st.st_mtime_ns)
    return state


def user_files(home):
    found = []
    for folder, _, files in os.walk(home):
        found += [os.path.relpath(os.path.join(folder, f), home) for f in files]
    return found


@pytest.fixture
def install_snapshot(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith("POWERTRADER_") and name != "POWERTRADER_HOME":
            monkeypatch.delenv(name)
    monkeypatch.chdir(pt_paths.program_dir())  # worst case: started from app/
    before = snapshot(pt_paths.install_dir())
    yield
    after = snapshot(pt_paths.install_dir())
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    assert changed == [], f"written inside the program folder: {changed[:20]}"


def test_settings_and_exchange_config_live_in_the_user_config_folder(
    install_snapshot, isolated_user_dirs
):
    from pt_multi_exchange import ExchangeConfigManager
    from pt_settings_manager import SettingsManager
    from trading_mode import read_trading_settings

    sm = SettingsManager()
    assert sm.settings_path == pt_paths.settings_file()
    assert sm.set_trading_mode("paper", persist=True)
    assert not read_trading_settings().is_live

    ecm = ExchangeConfigManager()
    assert ecm.load_config() is not None  # shipped template, read-only
    ecm.update_exchange_credentials("binance", "k", "s")
    assert os.path.isfile(pt_paths.trading_config_file())

    from pt_exchange_abstraction import ExchangeFactory

    ExchangeFactory.load_credentials()
    names = user_files(isolated_user_dirs["home"])
    assert os.path.join("config", "pt_config.json") in names
    assert os.path.join("config", "trading_config.json") in names


def test_logs_audit_and_credentials_metadata(install_snapshot, isolated_user_dirs):
    from pt_credentials import KeyringCredentialManager, PermissionValidator
    from pt_logging_system import PowerTraderLogger

    PowerTraderLogger().main_logger.info("hello")
    KeyringCredentialManager().encrypt_credentials("rh.k", "c2VlZA==")
    PermissionValidator().validate(lambda: ["read_account", "read_positions"], require_trading=False)
    names = user_files(isolated_user_dirs["home"])
    assert any(n.startswith("logs" + os.sep) for n in names)
    assert os.path.join("logs", "credential_audit.jsonl") in names


def test_databases_and_candle_cache(install_snapshot, isolated_user_dirs):
    from market_data import candles

    assert candles.cache_dir_default().startswith(pt_paths.cache_dir())
    from long_term_holdings import HoldingsDatabase
    from portfolio_optimizer import PortfolioOptimizer
    from real_time_market_data import MarketDataAggregator, MarketDataManager

    HoldingsDatabase()
    PortfolioOptimizer()
    MarketDataAggregator()
    MarketDataManager()  # the hub's market data tab (found leaking by the hub smoke run)
    try:
        from order_management_db import OrderManagementDB
    except ImportError:  # SQLAlchemy not installed
        OrderManagementDB = None
    if OrderManagementDB is not None:
        db = OrderManagementDB()
        assert pt_paths.data_dir() in db.database_url
        db.engine.dispose()
    names = user_files(isolated_user_dirs["home"])
    assert os.path.join("data", "holdings.db") in names
    assert os.path.join("cache", "market_data.db") in names


def test_trader_hub_folders_default_to_user_data(install_snapshot):
    import pt_trader

    assert not pt_paths.is_inside_program_dir(pt_trader.HUB_DATA_DIR)
    assert not pt_paths.is_inside_program_dir(pt_trader.main_dir)


def test_folder_settings_inside_the_program_dir_are_refused(caplog):
    inside = os.path.join(pt_paths.program_dir(), "BTC")
    assert pt_paths.neural_dir(inside) == pt_paths.models_dir()
    assert pt_paths.hub_dir_for(pt_paths.program_dir()) == pt_paths.hub_dir()
    assert "read-only" in caplog.text
    elsewhere = os.path.join(pt_paths.data_dir(), "my_models")
    assert pt_paths.neural_dir(elsewhere) == elsewhere
    assert pt_paths.neural_dir("relative_models") == os.path.join(pt_paths.data_dir(), "relative_models")
