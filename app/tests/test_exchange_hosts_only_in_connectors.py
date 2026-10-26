"""Only the connectors talk to an exchange (FDS-MX-001 section 5.6).

The product uses multiple exchanges, with the user's primary exchange preferred
(owner, 2026-10-25). An exchange's API host, and helpers named after one exchange's
data, belong in its connector (``pt_exchanges.py``). Everything else reads market
data through the exchange layer, primary exchange first.

KNOWN_BYPASSES lists the places that still call one exchange directly. Each
FDS-MX-001 phase removes its own entries, and phase H leaves the list empty. A host
or helper anywhere else fails this test, and so does an entry that is no longer
there, so the list only ever shrinks.
"""

import os
import re

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# The connector module, and the Coinbase authentication helper it uses.
CONNECTOR_FILES = {"pt_exchanges.py", "coinbase_auth.py"}

DIRECT = re.compile(
    r"api\.binance\.com|stream\.binance\.com|testnet\.binance\.vision"
    r"|api\.kucoin\.com|kucoin\.client|api\.kraken\.com"
    r"|api\.exchange\.coinbase\.com|ws-feed\.exchange\.coinbase\.com|api\.coinbase\.com"
    r"|trading\.robinhood\.com|ccxt\.\w+\("
    r"|\bBinanceKlines\b|\bbinance_closed_bars\b|\bHUB_TO_BINANCE\b"
    r"|\bfetch_binance_btc_price\b|\bkucoin_text\b|\bbinance_pair\b|\bbinance_interval\b"
)

# file (relative to app/, forward slashes) -> what it still uses directly
KNOWN_BYPASSES = {
    # phase E: strategy candles, backtests, chart pattern labels
    "market_data/candles.py": {"BinanceKlines", "api.binance.com"},
    "signal_engine.py": {"BinanceKlines"},
    "backtest/cli.py": {"BinanceKlines"},
    "candlestick_patterns.py": {"HUB_TO_BINANCE"},
    "pt_chart_patterns.py": {"HUB_TO_BINANCE", "binance_closed_bars"},
    # phase G: hub chart, Market Data tab, unused module
    "pt_hub.py": {"api.kucoin.com", "kucoin.client"},
    "real_time_market_data.py": {
        "ccxt.binance(",
        "ccxt.coinbase(",
        "ccxt.kraken(",
        "stream.binance.com",
        "ws-feed.exchange.coinbase.com",
    },
    "pt_async_patterns.py": {"api.binance.com"},
}


def app_sources():
    """Every app module outside the connectors and the tests."""
    for root, dirs, files in os.walk(APP_DIR):
        dirs[:] = [
            d for d in dirs if d not in {".venv", "venv", "tests", "__pycache__"}
        ]
        for name in files:
            if not name.endswith(".py") or name.startswith("test_"):
                continue
            rel = os.path.relpath(os.path.join(root, name), APP_DIR).replace("\\", "/")
            if rel not in CONNECTOR_FILES:
                yield rel


def direct_uses():
    found = {}
    for rel in app_sources():
        with open(os.path.join(APP_DIR, rel), encoding="utf-8", errors="replace") as f:
            hits = set(DIRECT.findall(f.read()))
        if hits:
            found[rel] = hits
    return found


def test_only_the_connectors_talk_to_an_exchange():
    found = direct_uses()
    new = {
        rel: sorted(hits - KNOWN_BYPASSES.get(rel, set()))
        for rel, hits in found.items()
        if hits - KNOWN_BYPASSES.get(rel, set())
    }
    assert not new, (
        "These modules call one exchange directly. Read market data through the "
        f"exchange layer (pt_multi_exchange.shared_manager()) instead: {new}"
    )


def test_the_list_of_known_bypasses_only_shrinks():
    found = direct_uses()
    gone = {
        rel: sorted(allowed - found.get(rel, set()))
        for rel, allowed in KNOWN_BYPASSES.items()
        if allowed - found.get(rel, set())
    }
    assert not gone, f"No longer used: remove them from KNOWN_BYPASSES: {gone}"
