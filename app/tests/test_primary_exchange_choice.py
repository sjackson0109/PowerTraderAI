"""The primary exchange is the user's choice, and nothing else takes its place.

PowerTrader uses several exchanges, with the one chosen in Settings preferred. Before
this, a new install had Binance as its only exchange; the Settings window filled in
Binance whenever no primary was saved; a primary whose entry was disabled was not
connected; and the first exchange to connect was then marked primary in its place.

No network: the connectors are fakes. Everything runs under the isolation guard.
"""

import json
import os
import pathlib
import re
import sys
import types
from tkinter import ttk
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.dirname(__file__))

import exchange_config_gui  # noqa: E402
import pt_hub  # noqa: E402
import pt_paths  # noqa: E402
from pt_exchange_abstraction import (  # noqa: E402
    ExchangeFactory,
    ExchangeType,
    PriceQuote,
)
from pt_multi_exchange import (  # noqa: E402
    DEFAULT_PRIMARY_EXCHANGE,
    ExchangeConfigManager,
    MultiExchangeManager,
)


class FakeExchange:
    def __init__(self, name):
        self.name = name

    def market_symbol(self, symbol):
        return symbol

    def quote(self, symbol):
        return PriceQuote(bid=99.0, ask=101.0, quote_ts=None)

    def get_current_price(self, symbol):
        return 100.0


@pytest.fixture
def connectors(monkeypatch):
    """Fake connectors for every exchange; the names in ``down`` fail to connect."""
    down = set()

    def get_exchange(exchange_type, **kwargs):
        if exchange_type.value in down:
            raise ConnectionError(f"{exchange_type.value} is down")
        return FakeExchange(exchange_type.value)

    monkeypatch.setattr(ExchangeFactory, "get_exchange", get_exchange)
    return down


def write_config(folder, primary, exchanges):
    folder.mkdir(exist_ok=True)
    config = {
        "user_region": "GLOBAL",
        "primary_exchange": primary,
        "exchanges": [
            {"exchange_type": name, "enabled": enabled, "region_preference": rank}
            for name, enabled, rank in exchanges
        ],
    }
    (folder / "trading_config.json").write_text(json.dumps(config), encoding="utf-8")
    return ExchangeConfigManager(str(folder))


def test_a_new_install_has_the_default_primary_and_fallbacks():
    with open(
        os.path.join(APP_DIR, "trading_config.example.json"), encoding="utf-8"
    ) as f:
        template = json.load(f)
    enabled = [ex["exchange_type"] for ex in template["exchanges"] if ex["enabled"]]
    assert template["primary_exchange"] == DEFAULT_PRIMARY_EXCHANGE
    assert enabled[0] == DEFAULT_PRIMARY_EXCHANGE
    market_data = ExchangeFactory.market_data_exchanges()
    assert len([name for name in enabled if name in market_data]) >= 3, enabled

    # the global default, used when there is no file at all, is the same
    default = ExchangeConfigManager.__new__(ExchangeConfigManager)
    default.config = None
    config = default.create_default_config("GLOBAL", save=False)
    assert config.primary_exchange == DEFAULT_PRIMARY_EXCHANGE
    assert [ex.exchange_type for ex in default.get_enabled_exchanges()] == enabled


def test_the_chosen_primary_is_connected_first_even_when_its_entry_is_disabled(
    tmp_path, connectors
):
    manager = write_config(
        tmp_path / "config",
        "kraken",
        [("binance", True, 1), ("kucoin", True, 2), ("kraken", False, 3)],
    )
    multi = MultiExchangeManager(manager)
    assert multi.initialize("GLOBAL")
    assert multi.exchange_manager.exchange_names() == ["kraken", "binance", "kucoin"]
    assert multi.exchange_manager.primary_exchange is ExchangeType.KRAKEN
    assert multi.quote("BTC").exchange == "kraken"


def test_a_primary_that_cannot_connect_is_not_replaced_by_another_exchange(
    tmp_path, connectors, capsys
):
    connectors.add("coinbase")
    manager = write_config(
        tmp_path / "config",
        "coinbase",
        [("coinbase", True, 1), ("binance", True, 2), ("kraken", True, 3)],
    )
    multi = MultiExchangeManager(manager)
    assert multi.initialize("GLOBAL")
    layer = multi.exchange_manager
    assert layer.primary_exchange is None  # binance is not marked primary
    answer = multi.quote("BTC")
    assert (answer.exchange, answer.primary) == ("binance", False)
    assert multi.get_current_price("BTC") == 100.0  # from the next, in Settings order
    with pytest.raises(ValueError, match="No primary exchange"):
        layer.place_order("BTC-USD", "buy", 1.0)  # never on another exchange
    out = capsys.readouterr().out
    assert "Primary exchange coinbase is not connected" in out
    assert "binance, kraken" in out


def test_saving_settings_enables_the_chosen_primary(tmp_path):
    manager = write_config(
        tmp_path / "config",
        "binance",
        [("binance", True, 1), ("coinbase", False, 2)],
    )
    manager.load_config()
    assert manager.set_primary_exchange("coinbase")
    assert manager.config.primary_exchange == "coinbase"
    assert manager.get_exchange_config("coinbase").enabled
    assert not manager.set_primary_exchange("coinbase")  # nothing left to change
    # an exchange missing from the list is added, enabled
    assert manager.set_primary_exchange("kucoin")
    assert manager.get_exchange_config("kucoin").enabled
    assert manager.get_enabled_exchanges()[0].exchange_type == "kucoin"


def test_the_hub_saves_the_primary_enabled_where_the_runner_reads_it():
    # Robinhood is disabled in the shipped template, which is read when no
    # trading_config.json exists yet
    hub = types.SimpleNamespace(
        settings={"region": "us", "primary_exchange": "robinhood"}
    )
    pt_hub.PowerTraderHub._sync_exchange_choice(hub)
    manager = ExchangeConfigManager()
    manager.load_config()
    assert manager.config.primary_exchange == "robinhood"
    assert manager.get_exchange_config("robinhood").enabled
    assert manager.get_enabled_exchanges()[0].exchange_type == "robinhood"


def test_the_hub_reports_the_primary_the_runner_uses_when_none_is_saved_in_the_hub():
    hub = types.SimpleNamespace(settings={"region": "eu", "primary_exchange": "kucoin"})
    pt_hub.PowerTraderHub._sync_exchange_choice(hub)
    unsaved = types.SimpleNamespace(settings={"primary_exchange": ""})
    assert pt_hub.PowerTraderHub._primary_exchange(unsaved) == "kucoin"
    saved = types.SimpleNamespace(settings={"primary_exchange": "Kraken "})
    assert pt_hub.PowerTraderHub._primary_exchange(saved) == "kraken"


def test_settings_offers_the_exchanges_that_serve_prices_and_keeps_the_choice():
    market_data = ExchangeFactory.market_data_exchanges()
    assert market_data == sorted(market_data)
    assert {"binance", "coinbase", "kraken", "kucoin"} <= set(market_data)
    assert "bybit" not in market_data and "okx" not in market_data  # no connector
    choices = pt_hub.PowerTraderHub._primary_exchange_choices
    assert choices("kraken") == market_data
    assert choices("bitstamp") == market_data + ["bitstamp"]  # kept, not replaced
    assert choices("") == market_data


@pytest.fixture
def root_hub(monkeypatch):
    import helpers_trainer as ht

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    yield hub
    ht.close_hub(hub)


def primary_combo(win):
    from test_trainer_launch import widgets

    label = next(
        w
        for w in widgets(win)
        if isinstance(w, ttk.Label) and str(w.cget("text")) == "Primary exchange:"
    )
    row = int(label.grid_info()["row"])
    return next(
        w
        for w in label.master.winfo_children()
        if isinstance(w, ttk.Combobox) and int(w.grid_info().get("row", -1)) == row
    )


@pytest.mark.parametrize("region", ["us", "eu", "global"])
def test_the_settings_window_shows_the_users_primary_and_saves_it_unchanged(
    root_hub, monkeypatch, region
):
    from test_trainer_launch import open_settings, press

    monkeypatch.setattr(pt_hub, "EXCHANGE_SUPPORT_AVAILABLE", True)
    hub = root_hub
    hub.settings["region"] = region
    hub.settings["primary_exchange"] = "kraken"
    win = open_settings(hub)
    combo = primary_combo(win)
    assert combo.get() == "kraken"
    assert list(combo.cget("values")) == ExchangeFactory.market_data_exchanges()
    press(win, "Save")
    assert hub.settings["primary_exchange"] == "kraken"
    manager = ExchangeConfigManager()
    manager.load_config()
    assert manager.config.primary_exchange == "kraken"
    assert manager.get_exchange_config("kraken").enabled


def test_the_settings_window_never_fills_in_a_primary(root_hub, monkeypatch):
    """With no primary saved anywhere, the window shows none and saves none."""
    from test_trainer_launch import open_settings, press

    monkeypatch.setattr(pt_hub, "EXCHANGE_SUPPORT_AVAILABLE", True)
    write_config(
        pathlib.Path(pt_paths.config_dir()),
        "",
        [("kraken", True, 1), ("binance", True, 2)],
    )
    hub = root_hub
    hub.settings["primary_exchange"] = ""
    win = open_settings(hub)
    assert primary_combo(win).get() == ""
    press(win, "Save")
    assert hub.settings["primary_exchange"] == ""
    assert ExchangeConfigManager().load_config().primary_exchange == ""


def test_the_setup_window_will_not_disable_the_primary_exchange(monkeypatch):
    warnings = []
    monkeypatch.setattr(
        exchange_config_gui.messagebox,
        "showwarning",
        lambda title, text, **k: warnings.append(text),
    )
    config_manager = mock.Mock()
    config_manager.config = types.SimpleNamespace(primary_exchange="coinbase")
    window = types.SimpleNamespace(
        exchange_tree=mock.Mock(),
        all_exchanges=[
            ("coinbase", "US/EU", "CEX", "Coinbase", "TIER1"),
            ("kraken", "Global", "CEX", "Kraken", "TIER1"),
        ],
        config_manager=config_manager,
        refresh_exchange_list=mock.Mock(),
        status_var=mock.Mock(),
    )
    window.exchange_tree.selection.return_value = ["row"]

    window.exchange_tree.item.return_value = {"text": "Coinbase"}
    exchange_config_gui.ExchangeConfigGUI.disable_selected_exchange(window)
    config_manager.enable_exchange.assert_not_called()
    assert warnings == [
        "Coinbase is your primary exchange. Choose another primary exchange in "
        "Settings first."
    ]

    window.exchange_tree.item.return_value = {"text": "Kraken"}
    exchange_config_gui.ExchangeConfigGUI.disable_selected_exchange(window)
    config_manager.enable_exchange.assert_called_once_with("kraken", False)


# Code that names an exchange as a default or a primary. Only the exchange
# configuration may: it holds the default for a new install, which the user's
# choice in Settings replaces.
DEFAULT_NAMED = re.compile(
    r"(?i)\b\w*(?:primary|default|exchange)\w*[\"']?\s*(?::\s*[\w\[\]., ]+)?[:=]\s*"
    r"[\"'](" + "|".join(t.value for t in ExchangeType) + r")[\"']"
)
ALLOWED = {
    "pt_multi_exchange.py": "the default for a new install, and the region defaults",
    "pt_exchanges.py": "each connector names its own exchange",
    os.path.join("market_data", "candles.py"): (
        "candles cached before FDS-MX-001 phase F came from Binance (provenance)"
    ),
    "pt_credentials.py": "the Robinhood credential store names its exchange",
}


def production_files():
    for folder, dirs, files in os.walk(APP_DIR):
        dirs[:] = [
            d for d in dirs if d not in {".venv", "venv", "tests", "__pycache__"}
        ]
        for name in files:
            if not name.endswith(".py") or name.startswith("test_"):
                continue
            if name == "conftest.py":
                continue
            path = os.path.join(folder, name)
            yield os.path.relpath(path, APP_DIR), path


def test_no_other_code_names_a_default_or_primary_exchange():
    found = []
    for rel, path in production_files():
        if rel in ALLOWED:
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            for number, line in enumerate(f, 1):
                if DEFAULT_NAMED.search(line):
                    found.append(f"{rel}:{number}: {line.strip()}")
    assert found == []
