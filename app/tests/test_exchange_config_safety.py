"""trading_config.json and credentials (#144).

Market data (prices and candles from public endpoints) reads no credential; a
connection made with credentials reads only its own exchange's; importing
pt_multi_exchange creates no folder; and a trading_config.json that cannot be read
is left as it is, never replaced by defaults.

Everything runs under the isolation guard (app/conftest.py): an in-memory keyring and
a scratch home; no network.
"""

import json
import os
import subprocess
import sys
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_secrets  # noqa: E402
from pt_exchange_abstraction import ExchangeFactory, ExchangeManager  # noqa: E402
from pt_multi_exchange import ExchangeConfigManager, MultiExchangeManager  # noqa: E402

CONFIG = {
    "user_region": "GLOBAL",
    "primary_exchange": "binance",
    "exchanges": [
        {"exchange_type": "binance", "enabled": True, "region_preference": 1},
        {"exchange_type": "kraken", "enabled": False, "region_preference": 2},
    ],
}


@pytest.fixture(autouse=True)
def no_credential_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith("POWERTRADER_") and name != "POWERTRADER_HOME":
            monkeypatch.delenv(name)
    monkeypatch.setattr(pt_secrets, "_warned_both", set())
    monkeypatch.setattr(ExchangeFactory, "_credentials", {})


@pytest.fixture
def manager(tmp_path, memory_keyring):
    """A config with Binance enabled and Kraken disabled, and keys stored for both."""
    folder = tmp_path / "config"
    folder.mkdir()
    (folder / "trading_config.json").write_text(json.dumps(CONFIG), encoding="utf-8")
    m = ExchangeConfigManager(str(folder))
    m.load_config()
    m.update_exchange_credentials("binance", "binance-key", "binance-secret")
    m.update_exchange_credentials("kraken", "kraken-key", "kraken-secret")
    return ExchangeConfigManager(str(folder))  # a fresh manager, nothing loaded


@pytest.fixture
def reads(monkeypatch):
    """The exchanges whose credentials were read."""
    calls = []
    real = pt_secrets.get_credentials

    def spy(exchange):
        calls.append(exchange)
        return real(exchange)

    monkeypatch.setattr(pt_secrets, "get_credentials", spy)
    return calls


@pytest.fixture
def connects(monkeypatch):
    """The exchanges connected, with the keyword arguments they got."""
    calls = []

    def add_exchange(self, exchange_type, **kwargs):
        calls.append((exchange_type.value, kwargs))
        return True

    monkeypatch.setattr(ExchangeManager, "add_exchange", add_exchange)
    monkeypatch.setattr(ExchangeManager, "set_primary_exchange", lambda self, t: None)
    return calls


# --- credentials ------------------------------------------------------------------------


def test_loading_the_config_reads_no_credential(manager, reads):
    config = manager.load_config()
    assert reads == []
    assert all(ex.api_key == "" and ex.api_secret == "" for ex in config.exchanges)


def test_market_data_connects_without_reading_a_credential(manager, reads, connects):
    """DataProvider's path: every stored key (enabled or not) used to be loaded into
    the runner and trainer processes, which only need public prices."""
    assert MultiExchangeManager(manager).initialize("GLOBAL")
    assert reads == []
    assert connects == [("binance", {"api_key": "", "api_secret": ""})]


def test_the_market_data_connectors_are_made_without_a_credential(manager, reads):
    """The connectors themselves, not only the manager's request: the exchange
    factory looks credentials up whenever it is given none."""
    multi = MultiExchangeManager(manager)
    assert multi.initialize("GLOBAL")
    assert reads == []
    (binance,) = multi.exchange_manager.exchanges.values()
    assert (binance.api_key, binance.api_secret) == ("", "")


def test_exchanges_with_no_saved_keys_still_connect_for_market_data(tmp_path, reads):
    """Coinbase, Kraken and KuCoin take their keys as required arguments. Given no
    credentials and finding none saved, the factory built them with no arguments
    at all, which raised, so an exchange with no saved keys gave no market data."""
    folder = tmp_path / "keyless"
    folder.mkdir()
    names = ["coinbase", "kraken", "kucoin"]
    config = {
        "user_region": "GLOBAL",
        "primary_exchange": "coinbase",
        "exchanges": [
            {"exchange_type": name, "enabled": True, "region_preference": i + 1}
            for i, name in enumerate(names)
        ],
    }
    (folder / "trading_config.json").write_text(json.dumps(config), encoding="utf-8")
    multi = MultiExchangeManager(ExchangeConfigManager(str(folder)))
    assert multi.initialize("GLOBAL")
    assert reads == []
    assert sorted(t.value for t in multi.exchange_manager.exchanges) == names


def test_a_connection_with_credentials_reads_only_its_own_exchanges(
    manager, reads, connects
):
    assert MultiExchangeManager(manager).initialize("GLOBAL", with_credentials=True)
    assert reads == ["binance"]  # Kraken is disabled: its keys are never read
    ((name, kwargs),) = connects
    assert name == "binance" and kwargs["api_key"] == "binance-key"


def test_the_setup_windows_still_see_every_exchanges_credentials(manager):
    config = manager.load_config(credentials=True)
    keys = {
        ex.exchange_type: (ex.api_key, ex.credential_source) for ex in config.exchanges
    }
    assert keys == {
        "binance": ("binance-key", "keyring"),
        "kraken": ("kraken-key", "keyring"),
    }


# --- an unreadable file -----------------------------------------------------------------


@pytest.fixture
def broken(tmp_path):
    folder = tmp_path / "config"
    folder.mkdir()
    path = folder / "trading_config.json"
    path.write_bytes(b'{"user_region": "EU", "exchanges": [')  # cut off mid-save
    return path


def test_an_unreadable_config_is_left_alone_and_initialisation_fails(
    broken, connects, capsys
):
    """It used to be replaced by region defaults, losing the user's exchanges."""
    original = broken.read_bytes()
    manager = ExchangeConfigManager(str(broken.parent))
    assert not MultiExchangeManager(manager).initialize("GLOBAL")
    assert broken.read_bytes() == original
    assert sorted(os.listdir(broken.parent)) == ["trading_config.json"]
    assert connects == []
    assert manager.load_error and str(broken) in manager.load_error
    assert str(broken) in capsys.readouterr().out


def test_defaults_written_over_a_file_keep_the_original(broken):
    """The interactive setup still offers defaults when the file cannot be read; the
    original is kept next to it."""
    original = broken.read_bytes()
    manager = ExchangeConfigManager(str(broken.parent))
    manager.create_default_config("EU")
    backup = broken.parent / "trading_config.json.bak"
    assert backup.read_bytes() == original
    assert (
        json.loads(broken.read_text(encoding="utf-8"))["primary_exchange"] == "kraken"
    )
    manager.create_default_config("UK")  # a second time: a second backup
    assert (broken.parent / "trading_config.json.bak-2").is_file()
    assert backup.read_bytes() == original


# --- no side effects --------------------------------------------------------------------


def test_importing_and_reading_create_no_folder(tmp_path):
    """The module built an ExchangeConfigManager at import, which created the user
    config folder in every process that imported it."""
    home = tmp_path / "no-home-yet"
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import pt_multi_exchange; "
        "pt_multi_exchange.ExchangeConfigManager().load_config()"
    )
    env = dict(os.environ, POWERTRADER_HOME=str(home))
    result = subprocess.run(
        [sys.executable, "-c", code, APP_DIR],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert not home.exists()
