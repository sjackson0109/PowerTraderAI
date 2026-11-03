"""Exchanges are shown by the name they go by ("KuCoin"), and saved by their id
("kucoin") (owner, 2026-11-03: the Exchange line showed COINBASE).

No network, no files.
"""

import os
import sys

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from pt_exchange_abstraction import (  # noqa: E402
    EXCHANGE_NAMES,
    ExchangeType,
    exchange_id,
    exchange_name,
)


def test_an_exchange_is_shown_by_the_name_it_goes_by():
    assert exchange_name("coinbase") == "Coinbase"
    assert exchange_name("kucoin") == "KuCoin"
    assert exchange_name("crypto_com") == "Crypto.com"
    assert exchange_name("oneinch") == "1inch"
    assert exchange_name("yellow_card") == "Yellow Card"  # not listed: capitalised
    assert exchange_name(ExchangeType.DYDX) == "dYdX"
    assert exchange_name(" Kraken ") == "Kraken"
    assert exchange_name("") == exchange_name(None) == ""


def test_every_name_leads_back_to_its_exchange():
    names = [exchange_name(e) for e in ExchangeType]
    assert len(set(n.lower() for n in names)) == len(names)  # no two alike
    for exchange in ExchangeType:
        assert exchange_id(exchange_name(exchange)) == exchange.value
        assert exchange_id(exchange.value) == exchange.value  # an id stays an id
    assert exchange_id("") == ""


def test_the_table_lists_only_exchanges_that_exist():
    assert set(EXCHANGE_NAMES) <= {e.value for e in ExchangeType}
