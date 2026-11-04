#!/usr/bin/env python3
"""Live exchange check, for developers: the checks behind Settings > Check
Exchanges (``exchange_check``), run from a terminal or under pytest.

    python test_exchanges.py

checks the exchanges enabled in Settings, primary first, for the coins in Settings,
and exits with 1 if any check fails. Nothing here places, previews or cancels an
order. Users run the same checks from Settings > Check Exchanges.

Under pytest these tests call the real exchanges only when
``POWERTRADER_LIVE_EXCHANGES=1`` is set, and are skipped otherwise (and in CI). They
check every connector that reads market data, without credentials, for the default
coins in Settings.
"""

import os
import sys
import time

import requests

from exchange_check import (
    check,
    check_exchange,
    market_data_exchanges,
    settings_coins,
    settings_exchanges,
)
from pt_settings_manager import DEFAULT_MAX_QUOTE_AGE_S, DEFAULT_SETTINGS

try:
    import pytest
except ImportError:  # the script needs no pytest
    pytest = None

LIVE_ENV = "POWERTRADER_LIVE_EXCHANGES"
# Session.request before the test guard replaces it for each test (tests/isolation.py)
_REAL_REQUEST = requests.sessions.Session.request


def main() -> int:
    names, coins = settings_exchanges(), settings_coins()
    if not names:
        print("No exchanges are enabled in Settings.")
        return 1
    print(f"Exchanges: {', '.join(names)}    Coins: {', '.join(coins)}")

    def show(r):
        mark = {True: "PASS", False: "FAIL", None: " -- "}[r.ok]
        print(f"{r.exchange:10} {r.check:14} {mark}  {r.detail}")

    results = check(names, coins, report=show)
    failed = sum(r.ok is False for r in results)
    passed = sum(r.ok is True for r in results)
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


# --- pytest: opt-in, against the real exchanges ----------------------------------------

if pytest is not None:
    live = pytest.mark.skipif(
        os.environ.get(LIVE_ENV) != "1",
        reason=f"calls the real exchanges: set {LIVE_ENV}=1 to run",
    )

    @pytest.fixture
    def real_network(isolated_user_dirs, monkeypatch):
        """The real network, in place of the test guard's refusal."""
        monkeypatch.setattr(requests.sessions.Session, "request", _REAL_REQUEST)

    def _assert_passed(results):
        failed = [r for r in results if r.ok is False]
        assert not failed, "\n".join(f"{r.check}: {r.detail}" for r in failed)

    @live
    @pytest.mark.parametrize("name", market_data_exchanges())
    def test_live_market_data(name, real_network):
        results = check_exchange(name, DEFAULT_SETTINGS["coins"])
        assert any(r.check == "BTC quote" and r.ok for r in results), results
        _assert_passed(results)

    @live
    def test_live_quote_through_the_exchange_layer(real_network):
        from pt_multi_exchange import market_exchanges

        manager = market_exchanges()
        sourced = manager.quote("BTC")
        assert sourced is not None
        assert sourced.exchange in manager.exchange_manager.exchange_names()
        assert time.time() - sourced.value.quote_ts <= DEFAULT_MAX_QUOTE_AGE_S


if __name__ == "__main__":
    sys.exit(main())
