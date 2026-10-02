#!/usr/bin/env python3
"""
PowerTrader AI+ - end-to-end paper trading demo (FDS-087).

Zero setup: no GUI, no config file, no API keys. It drives the *real* paper path:

    resolve_order_target(settings)  ->  PaperExchange  ->  PaperTradingAccount

with live BTCUSDT bid/ask from Binance's public ticker. It never reads or writes
the user's pt_config.json (settings are built in memory) and keeps its paper
book in a throw-away temp directory.

There is deliberately NO simulated-price fallback here: a demo that quietly
trades on made-up prices proves nothing. If no live price is available it says
so and exits 2.

Exit codes: 0 operational, 1 failed (e.g. gate did not return paper), 2 degraded
(no live price).
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from decimal import Decimal
from typing import Callable, Optional

import trading_mode as tm

SYMBOL = "BTC-USD"
QUANTITY = 0.01
STARTING_BALANCE = Decimal("10000")

# Built in memory - the user's pt_config.json is never touched.
DEMO_SETTINGS = {
    "trading": {"mode": "paper", "active_broker": None},
    "paper": {"price_fallback_policy": "pause"},
}

EXIT_OK, EXIT_FAILED, EXIT_DEGRADED = 0, 1, 2


def _money(value: float) -> str:
    rounded = round(value, 2)
    sign = "-" if rounded < 0 else ""
    return f"{sign}${abs(rounded):,.2f}"


def run_demo(
    out: Callable[[str], None] = print,
    workdir: Optional[str] = None,
    settings: Optional[dict] = None,
) -> int:
    """Run the demo, writing lines via ``out``. Returns the process exit code."""
    settings = settings if settings is not None else DEMO_SETTINGS
    own_tmp = None
    if workdir is None:
        own_tmp = tempfile.TemporaryDirectory(prefix="pt_paper_demo_")
        workdir = own_tmp.name
    try:
        return _run(out, workdir, settings)
    finally:
        tm.reset_paper_exchange()
        if own_tmp is not None:
            own_tmp.cleanup()


def _run(out: Callable[[str], None], workdir: str, settings: dict) -> int:
    out("PowerTrader AI+ - Paper Trading Demo")
    out("=====================================")

    # 1-2. The real gate, on in-memory settings; the paper book lives in a temp dir.
    tm.configure_paper_exchange(
        state_path=os.path.join(workdir, "paper_account.json"),
        initial_balance=STARTING_BALANCE,
        settings_source=settings,
    )
    target = tm.resolve_order_target(settings)
    if target.is_live or target.key != "paper":
        out("FAILED: gate did not return paper")
        return EXIT_FAILED
    out("Order target     : PAPER (via trading-mode gate)")

    exchange = target.exchange
    start_cash = exchange.get_balance()["USD"]
    out(f"Starting balance : {_money(start_cash)}")

    # 3. Live BTCUSDT bid/ask from Binance's public API.
    quote = tm.fetch_public_quote("BTC")
    paper = tm.read_paper_settings(settings)
    source = tm.classify_quote(quote, paper.max_quote_age_s, time.time())
    if quote is None or source != "live":
        out("Live BTC price   : unavailable" + (f" (feed is {source})" if quote else ""))
        out("")
        out("Paper trading system: DEGRADED (no live price)")
        return EXIT_DEGRADED
    mid = (quote.bid + quote.ask) / 2
    out(f"Live BTC price   : {_money(mid)}  (Binance public feed, source={source})")
    out("")

    # 4. BUY through the gate's target.
    buy = target.place_order(SYMBOL, "buy", QUANTITY)
    if buy.status != "filled":
        return _degraded(out, "BUY", buy)
    out(f"BUY  {QUANTITY:g} BTC @ {_money(buy.price)}  -> {buy.status}"
        f"  (price_source={buy.price_source})")
    position = exchange.account.positions.get("BTC")
    marked = tm.fetch_public_quote("BTC") or quote
    unrealized = float(position.quantity) * (marked.bid - float(position.average_price))
    out(f"Position         : {float(position.quantity):g} BTC @ avg {_money(float(position.average_price))}")
    out(f"Unrealized PnL   : {_money(unrealized)}  (marked at bid {_money(marked.bid)})")
    out("")

    # 5. SELL.
    sell = target.place_order(SYMBOL, "sell", QUANTITY)
    if sell.status != "filled":
        return _degraded(out, "SELL", sell)
    out(f"SELL {QUANTITY:g} BTC @ {_money(sell.price)}  -> {sell.status}"
        f"  (price_source={sell.price_source})")
    final_cash = exchange.get_balance()["USD"]
    fees = float(exchange.account.total_commission_paid)
    out(f"Realized PnL     : {_money(final_cash - start_cash)}  (fees {_money(fees)})")
    out(f"Final balance    : {_money(final_cash)}")
    out("")

    # 6. Summary.
    out("Paper trading system: OPERATIONAL")
    return EXIT_OK


def _degraded(out: Callable[[str], None], side: str, result) -> int:
    reason = result.reason or result.status
    out(f"{side} not filled: {reason}")
    out("")
    out("Paper trading system: DEGRADED (no live price)")
    return EXIT_DEGRADED


def main() -> int:
    try:
        return run_demo()
    except Exception as exc:  # a demo should say what broke, not dump a traceback
        print(f"FAILED: {type(exc).__name__}: {exc}")
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
