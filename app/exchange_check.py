"""Live exchange check (Settings > Check Exchanges): real requests to each
exchange's public market data and, when asked, its read-only API key check.

For each exchange and coin it reads the market status and the best bid and ask
(failing a quote older than the paper-trading limit); for each exchange, the last
day of hourly BTC candles and the minimum BTC order. Nothing here places, previews
or cancels an order.

The window is ``exchange_check_gui``; ``test_exchanges.py`` runs the same checks
from a terminal and, opted in, under pytest.
"""

import json
import time
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple

import pt_exchanges  # noqa: F401  (registers the connectors)
from pt_exchange_abstraction import (
    AbstractExchange,
    ExchangeFactory,
    ExchangeType,
    usable_minimum,
)
from pt_settings_manager import DEFAULT_MAX_QUOTE_AGE_S, DEFAULT_SETTINGS

CANDLE_TF = "1h"
CANDLE_STEP_MS = 3_600_000
NO_CONNECTOR = "this version of PowerTrader has no connector for it"


@dataclass
class Result:
    exchange: str
    check: str
    ok: Optional[bool]  # None: does not apply (coin not listed, not served)
    detail: str


Report = Optional[Callable[[Result], None]]


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

    try:
        outcome = MultiExchangeManager().test_exchange_connection(name)
    except Exception as exc:
        return Result(name, "API key", False, f"{type(exc).__name__}: {exc}")
    return Result(
        name, "API key", outcome.status == ConnectionStatus.OK, outcome.message
    )


def _failed(name: str, check: str, exc: Exception) -> Result:
    return Result(name, check, False, f"{type(exc).__name__}: {exc}")


def check_exchange(
    name: str, coins: Iterable[str], auth: bool = False, report: Report = None
) -> List[Result]:
    """Every check for one exchange; ``report(result)`` as each one arrives."""
    results: List[Result] = []

    def add(*items: Result) -> None:
        for item in items:
            results.append(item)
            if report is not None:
                report(item)

    try:
        exchange = connector(name)
    except Exception as exc:
        add(_failed(name, "exchange", exc))
        exchange = None
    if exchange is not None and not exchange.candle_timeframes():
        add(Result(name, "market data", None, "this connector reads none"))
    elif exchange is not None:
        for coin in coins:
            try:
                add(*check_coin(name, exchange, coin))
            except Exception as exc:
                add(_failed(name, f"{coin} quote", exc))
        add(check_candles(name, exchange), check_minimum(name, exchange))
    if auth:
        add(check_api_key(name))
    return results


def check(
    names: Iterable[str],
    coins: Iterable[str],
    auth: bool = False,
    report: Report = None,
    stopped: Callable[[], bool] = lambda: False,
) -> List[Result]:
    """Every check for the exchanges ``names``, in that order, and ``coins``.
    ``report(result)`` is called as each result arrives; ``stopped()`` is asked
    before each exchange."""
    coins = list(coins)
    results: List[Result] = []
    for name in names:
        if stopped():
            break
        try:
            known = ExchangeFactory.get_exchange_class(ExchangeType(name)) is not None
            detail = NO_CONNECTOR
        except ValueError:
            known, detail = False, "not an exchange"
        if not known:
            result = Result(name, "exchange", False, detail)
            results.append(result)
            if report is not None:
                report(result)
            continue
        results += check_exchange(name, coins, auth=auth, report=report)
    return results


def enabled_exchanges(config_manager=None) -> Tuple[List[str], Optional[str]]:
    """The exchanges enabled in Settings, primary first, then in their Settings
    order; and the primary exchange when it is one of them. Read from the file, so
    an exchange that cannot connect is still listed."""
    from pt_multi_exchange import ExchangeConfigManager

    manager = config_manager or ExchangeConfigManager()
    config = manager.load_config()
    if config is None:
        return [], None
    manager.config = config
    names = [ex.exchange_type for ex in manager.get_enabled_exchanges()]
    primary = config.primary_exchange if config.primary_exchange in names else None
    return sorted(names, key=lambda name: name != primary), primary


def settings_exchanges(config_manager=None) -> List[str]:
    """The exchanges enabled in Settings, primary first."""
    return enabled_exchanges(config_manager)[0]


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
