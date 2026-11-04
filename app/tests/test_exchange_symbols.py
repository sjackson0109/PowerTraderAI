"""The shared symbol conversion (exchange_symbols): coins in, the connected
exchange's own market names out, primary exchange first. Real connectors, built
offline under the isolation guard (app/conftest.py)."""

import json
import os
import sys
import types

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import exchange_symbols as xs  # noqa: E402
import pt_exchanges  # noqa: E402,F401  (registers the connectors)
import pt_paths  # noqa: E402
from pt_exchange_abstraction import ExchangeFactory, ExchangeType  # noqa: E402


def layer_of(*names):
    """A stand-in for pt_multi_exchange.market_exchanges(): these exchanges
    connected, the first one primary."""
    exchanges = {
        ExchangeType(n): ExchangeFactory.get_exchange(
            ExchangeType(n), api_key="", api_secret=""
        )
        for n in names
    }
    manager = types.SimpleNamespace(
        exchange_manager=types.SimpleNamespace(
            exchanges=exchanges, exchange_names=lambda: list(names)
        )
    )
    return lambda: manager


@pytest.mark.parametrize(
    "names, pair, quote",
    [
        (("coinbase", "binance"), "BTC-USD", "USD"),
        (("binance", "coinbase"), "BTCUSDT", "USDT"),
    ],
)
def test_a_coin_is_shown_in_the_primary_exchanges_format(names, pair, quote):
    found = xs.market_pair("BTC", layer_of(*names))
    assert (found.coin, found.pair, found.exchange, found.quote) == (
        "BTC",
        pair,
        names[0],
        quote,
    )


def test_with_no_exchange_the_layers_common_form_is_used():
    def none():
        raise RuntimeError("no exchange connected")

    found = xs.market_pairs(["eth", "SOL"], none)
    assert [(p.coin, p.pair, p.exchange) for p in found] == [
        ("ETH", "ETH-USD", ""),
        ("SOL", "SOL-USD", ""),
    ]


def test_symbols_read_back_as_coins():
    assert [xs.coin_of(s) for s in ("btc", "BTC-USD", "BTCUSDT", "eth/usdc", "")] == [
        "BTC",
        "BTC",
        "BTC",
        "ETH",
        "",
    ]
    # a name the exchange uses for a coin reads back as the coin it was shown for
    known = {"XBTUSD": "BTC"}
    assert xs.parse_symbols("xbtusd, ETH-USD ETH  ,doge", known) == [
        "BTC",
        "ETH",
        "DOGE",
    ]


def test_the_coins_come_from_settings():
    path = pt_paths.gui_settings_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"coins": ["zec", "XRP", "HYPE"]}, f)
    assert xs.settings_coins() == ["ZEC", "XRP", "HYPE"]
