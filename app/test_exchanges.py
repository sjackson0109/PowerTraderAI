#!/usr/bin/env python3
"""Live exchange check: real requests to the exchanges' public market data.

    python test_exchanges.py                      the exchanges in Settings, primary first
    python test_exchanges.py --exchange coinbase  one exchange (repeat for more)
    python test_exchanges.py --coin DASH          one coin (default: the coins in Settings)
    python test_exchanges.py --auth               also check the saved API keys

For each exchange and coin it reads the market status and the best bid and ask
(failing a quote older than the paper-trading limit), and for BTC the last day of
hourly candles and the minimum order. ``--auth`` makes each exchange's read-only key
check with the credentials saved in PowerTrader. Nothing here places, previews or
cancels an order. The exit code is 0 when every check passes, 1 otherwise.

Under pytest these tests call the real exchanges only when
``POWERTRADER_LIVE_EXCHANGES=1`` is set, and are skipped otherwise (and in CI). They
check every connector that reads market data, without credentials, for the default
coins in Settings.
"""

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

import requests

import pt_exchanges  # noqa: F401  (registers the connectors)
from pt_exchange_abstraction import (
    AbstractExchange,
    ExchangeFactory,
    ExchangeType,
    usable_minimum,
)
from pt_settings_manager import DEFAULT_MAX_QUOTE_AGE_S, DEFAULT_SETTINGS

try:
    import pytest
except ImportError:  # the script needs no pytest
    pytest = None

LIVE_ENV = "POWERTRADER_LIVE_EXCHANGES"
CANDLE_TF = "1h"
CANDLE_STEP_MS = 3_600_000
# Session.request before the test guard replaces it for each test (tests/isolation.py)
_REAL_REQUEST = requests.sessions.Session.request


@dataclass
class Result:
    exchange: str
    check: str
    ok: Optional[bool]  # None: does not apply (coin not listed, not served)
    detail: str


def market_data_exchanges() -> List[str]:
    """The exchanges whose connector reads public market data."""
    names = []
    for exchange_type in ExchangeType:
        cls = ExchangeFactory.get_exchange_class(exchange_type)
        if (
            cls is not None
            and cls.candle_timeframes is not AbstractExchange.candle_timeframes
        ):
            names.append(exchange_type.value)
    return names


def connector(name: str) -> AbstractExchange:
    """``name``'s connector, without credentials (given none, the factory would read
    the saved ones)."""
    return ExchangeFactory.get_exchange(ExchangeType(name), api_key="", api_secret="")


def check_coin(name: str, exchange, coin: str, now: Optional[float] = None):
    """The market status and the best bid and ask of ``coin`` on one exchange."""
    symbol = f"{coin}-USD"
    status = exchange.market_status(symbol)
    if status is None:
        return [Result(name, f"{coin} status", False, "no answer")]
    if not status.listed:
        return [Result(name, f"{coin} status", None, f"not listed ({status.reason})")]
    results = [Result(name, f"{coin} status", status.trading, status.reason)]
    quote = exchange.quote(symbol)
    if quote is None:
        return results + [Result(name, f"{coin} quote", False, "no quote")]
    now = time.time() if now is None else now
    if not (0 < quote.bid <= quote.ask):
        ok, detail = False, f"bid {quote.bid:g} ask {quote.ask:g}"
    elif quote.quote_ts is None:
        ok, detail = False, f"bid {quote.bid:g} ask {quote.ask:g}, age unknown"
    else:
        # a second either way: the exchange's Date header is in whole seconds
        age = now - quote.quote_ts
        ok = -1.0 <= age <= DEFAULT_MAX_QUOTE_AGE_S
        detail = f"bid {quote.bid:g} ask {quote.ask:g}, {age:.1f} s old"
    return results + [Result(name, f"{coin} quote", ok, detail)]


def check_candles(name: str, exchange, now: Optional[float] = None) -> Result:
    """The last day of closed hourly BTC candles."""
    if CANDLE_TF not in exchange.candle_timeframes():
        return Result(name, "candles", None, f"serves no {CANDLE_TF} candles")
    now_ms = int((time.time() if now is None else now) * 1000)
    last_open = now_ms // CANDLE_STEP_MS * CANDLE_STEP_MS - CANDLE_STEP_MS
    start = last_open - 23 * CANDLE_STEP_MS
    try:
        rows = exchange.candles("BTC-USD", CANDLE_TF, start, last_open)
    except Exception as exc:
        return Result(name, "candles", False, f"{type(exc).__name__}: {exc}")
    rows = [r for r in rows if start <= int(r[0]) <= last_open]
    opens = [int(r[0]) for r in rows]
    problems = []
    if len(rows) < 20:
        problems.append(f"{len(rows)} of 24 bars")
    if opens != sorted(set(opens)):
        problems.append("not oldest first")
    if any(
        not (float(r[3]) <= min(float(r[1]), float(r[4])) <= float(r[2])) for r in rows
    ):
        problems.append("a bar's low or high does not contain its open and close")
    if opens and opens[-1] < last_open - CANDLE_STEP_MS:
        problems.append("the last bar is more than an hour behind")
    detail = "; ".join(problems) or f"{len(rows)} closed {CANDLE_TF} bars of BTC"
    return Result(name, "candles", not problems, detail)


def check_minimum(name: str, exchange) -> Result:
    """The minimum order for BTC: a positive amount, or not stated."""
    try:
        minimum = exchange.min_order_usd("BTC-USD")
    except Exception as exc:
        return Result(name, "min order", False, f"{type(exc).__name__}: {exc}")
    if minimum is None:
        return Result(name, "min order", True, "not stated")
    if usable_minimum(minimum) is None:
        return Result(name, "min order", False, f"unusable: {minimum!r}")
    return Result(name, "min order", True, f"${float(minimum):,.2f}")


def check_api_key(name: str) -> Result:
    """The exchange's read-only key check with the credentials saved in PowerTrader."""
    from pt_exchange_abstraction import ConnectionStatus
    from pt_multi_exchange import MultiExchangeManager

    outcome = MultiExchangeManager().test_exchange_connection(name)
    return Result(
        name, "API key", outcome.status == ConnectionStatus.OK, outcome.message
    )


def check_exchange(name: str, coins, auth: bool = False) -> List[Result]:
    exchange = connector(name)
    if not exchange.candle_timeframes():
        results = [Result(name, "market data", None, "this connector reads none")]
    else:
        results = []
        for coin in coins:
            results += check_coin(name, exchange, coin)
        results += [check_candles(name, exchange), check_minimum(name, exchange)]
    if auth:
        results.append(check_api_key(name))
    return results


def settings_exchanges() -> List[str]:
    """The exchanges in Settings, primary first."""
    from pt_multi_exchange import market_exchanges

    return market_exchanges().exchange_manager.exchange_names()


def settings_coins() -> List[str]:
    """The coins in Settings (read only), or the default coins."""
    try:
        import pt_paths

        with open(pt_paths.gui_settings_file(), encoding="utf-8") as f:
            coins = json.load(f).get("coins") or []
        coins = [str(c).strip().upper() for c in coins if str(c).strip()]
    except (OSError, ValueError, AttributeError):
        coins = []
    return coins or list(DEFAULT_SETTINGS["coins"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--exchange", action="append", help="default: Settings")
    parser.add_argument("--coin", action="append", help="default: Settings")
    parser.add_argument("--auth", action="store_true", help="check saved API keys")
    args = parser.parse_args(argv)

    names = [n.strip().lower() for n in args.exchange or []] or settings_exchanges()
    coins = [c.strip().upper() for c in args.coin or []] or settings_coins()
    if not names:
        print("No exchanges in Settings.")
        return 1
    print(f"Exchanges: {', '.join(names)}    Coins: {', '.join(coins)}")
    results = []
    for name in names:
        try:
            exchange_type = ExchangeType(name)
        except ValueError:
            results.append(Result(name, "exchange", False, "not an exchange"))
            continue
        if ExchangeFactory.get_exchange_class(exchange_type) is None:
            detail = "this version of PowerTrader has no connector for it"
            results.append(Result(name, "exchange", False, detail))
            continue
        results += check_exchange(name, coins, auth=args.auth)
    for r in results:
        mark = {True: "PASS", False: "FAIL", None: " -- "}[r.ok]
        print(f"{r.exchange:10} {r.check:14} {mark}  {r.detail}")
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
