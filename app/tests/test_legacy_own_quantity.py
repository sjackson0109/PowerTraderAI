"""The legacy engine (``strategy.engine`` "legacy_neural") manages only what this
trader bought: of each coin the exchange holds, the quantity its ledger says it
bought, capped by the exchange's balance, as the catalogue engine's exits do. The
balance can include coins the user bought outside the trader: the trailing margin
never sells them, DCA is not sized from them, and a coin the trader holds none of
(or only a remainder of too small to sell) gets no order at all.

Live: a fake broker behind the calls the trader makes (FakeBroker), nothing leaves
the machine. Paper: the paper account, whose coins are the trader's own, so a
trailing exit there still sells the whole holding.

Everything runs under the isolation guard (app/conftest.py); no network.
"""

from __future__ import annotations

import copy
import json
import os
import time
import uuid
from unittest import mock

from helpers import PaperTraderCase

import trading_mode as tm
from pt_exchange_abstraction import (
    ConnectionStatus,
    ConnectionTestResult,
    MarketData,
    OrderResult,
)
from test_partial_sells import LegacyPaperTrader, btc_held, crossed_trailing_line

LIVE_LEGACY = {
    "trading": {"mode": "live", "active_broker": "coinbase", "coinbase_preview": False},
    "strategy": {"engine": "legacy_neural"},
}

# (bid, ask) paths for a position that cost $100 a coin. Up through the +5% line
# (105), the trailing line follows the peak of 110 (to 109.45), and 109 crosses it:
TRAILING_EXIT = [(106.0, 106.1), (110.0, 110.1), (109.0, 109.1)]
DCA_DROP = [(96.9, 97.0)]  # -3% at the ask: the first DCA stage is -2.5%
# both, then on down to -20%
EVERYTHING = TRAILING_EXIT + [(108.0, 108.1)] + DCA_DROP + [(80.0, 80.1)]


class FakeBroker:
    """A live broker's account as the trader reaches it (the AbstractExchange calls):
    USD and coin balances, a bid and ask per coin, and market orders that fill at once,
    in full, at the quote, with no fee. Every order is recorded."""

    def __init__(self, usd: float = 10000.0, **coins: float) -> None:
        self.balances = {"USD": float(usd)}
        self.balances.update({coin: float(qty) for coin, qty in coins.items()})
        self.quotes = {}
        self.orders = []  # (coin, side, quantity)
        self._made = {}

    def quote(self, coin: str, bid: float, ask: float) -> None:
        self.quotes[coin] = (float(bid), float(ask))

    def check_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            "fake", ConnectionStatus.UNSUPPORTED, "no key check"
        )

    def get_balance(self) -> dict:
        return dict(self.balances)

    def get_market_data(self, symbol: str) -> MarketData:
        bid, ask = self.quotes[symbol.split("-")[0]]
        return MarketData(symbol, (bid + ask) / 2, bid, ask, 0.0, time.time(), "fake")

    def place_order(self, symbol, side, amount, price=None) -> OrderResult:
        coin = symbol.split("-")[0]
        bid, ask = self.quotes[coin]
        fill = ask if side == "buy" else bid
        qty = float(amount)
        sign = 1.0 if side == "buy" else -1.0
        self.balances[coin] = self.balances.get(coin, 0.0) + sign * qty
        self.balances["USD"] -= sign * qty * fill
        self.orders.append((coin, side, qty))
        result = OrderResult(
            order_id=f"fake-{len(self.orders)}",
            symbol=symbol,
            side=side,
            amount=qty,
            price=fill,
            status="filled",
            exchange="fake",
            timestamp=time.time(),
            fee=0.0,
            filled_value=qty * fill,
        )
        self._made[result.order_id] = result
        return result

    def get_order_status(self, order_id: str) -> OrderResult:
        return self._made[order_id]

    def min_order_usd(self, symbol: str) -> float:
        return 1.0

    def trading_fees(self, symbol: str):
        return None


class LiveLegacyTrader(PaperTraderCase):
    """A legacy-mode trader trading live on FakeBroker, ETH only, no neural signals."""

    def setUp(self):
        super().setUp()
        self.broker = FakeBroker()
        target = tm.OrderTarget(
            tm.TradingMode.LIVE,
            "coinbase",
            self.broker,
            tm.read_trading_settings(LIVE_LEGACY).key,
        )
        self.one_coin("ETH")
        folder = os.path.join(self.tmp.name, "neural")
        os.makedirs(folder)
        for p in (
            mock.patch.object(self.pt_trader.time, "sleep"),
            mock.patch.object(self.pt_trader, "resolve_order_target", lambda s: target),
            mock.patch.object(self.pt_trader, "base_paths", {"ETH": folder}),
            mock.patch.object(self.pt_trader, "main_dir", folder),
        ):
            p.start()
            self.addCleanup(p.stop)

    def live_trader(self):
        trader = self.trader(copy.deepcopy(LIVE_LEGACY))
        self.assertTrue(trader._target.is_live)
        return trader

    def traders_own_buy(self, trader, usd: float) -> None:
        """The trader buys ``usd`` of ETH at $100 (its ledger records it)."""
        self.broker.quote("ETH", 99.9, 100.0)
        trader.place_buy_order(str(uuid.uuid4()), "buy", "market", "ETH-USD", usd)
        trader.cost_basis = trader.calculate_cost_basis()  # as its next pass would

    def run_through(self, trader, path) -> None:
        for bid, ask in path:
            self.broker.quote("ETH", bid, ask)
            trader.manage_trades()

    def orders_after(self, count: int) -> list:
        return self.broker.orders[count:]


class TheTradersOwnQuantity(LiveLegacyTrader):
    def test_the_trailing_margin_sells_only_the_traders_own_quantity(self):
        trader = self.live_trader()
        self.traders_own_buy(trader, 30.0)  # 0.3 ETH at $100
        self.broker.balances["ETH"] += 0.7  # the user's own, bought outside the trader
        self.assertAlmostEqual(self.broker.balances["ETH"], 1.0)

        self.run_through(trader, TRAILING_EXIT)
        sells = [o for o in self.orders_after(1) if o[1] == "sell"]
        self.assertEqual(len(sells), 1)
        self.assertAlmostEqual(sells[0][2], 0.3)  # not the 1.0 the exchange holds
        self.assertAlmostEqual(self.broker.balances["ETH"], 0.7)  # the user's is kept
        self.assertNotIn("ETH", trader._pnl_ledger.get("open_positions", {}))

        # what is left is the user's: no order on it, whatever the price does
        done = len(self.broker.orders)
        self.run_through(trader, EVERYTHING)
        self.assertEqual(self.orders_after(done), [])
        self.assertAlmostEqual(self.broker.balances["ETH"], 0.7)
        # and the trader shows no cost basis or trailing (sell) line on it
        with open(trader.trader_status_path, encoding="utf-8") as f:
            eth = json.load(f)["positions"]["ETH"]
        self.assertAlmostEqual(eth["quantity"], 0.7)  # the exchange's balance
        self.assertEqual((eth["avg_cost_basis"], eth["trail_line"]), (0, 0.0))

    def test_dca_is_sized_from_the_traders_own_quantity(self):
        trader = self.live_trader()
        self.traders_own_buy(trader, 30.0)  # 0.3 ETH at $100
        self.broker.balances["ETH"] += 0.7  # the user's own

        self.run_through(trader, DCA_DROP)
        (dca,) = self.orders_after(1)
        self.assertEqual(dca[1], "buy")
        # DCA multiplier x the value of the trader's 0.3 at the bid, bought at the ask
        bid, ask = DCA_DROP[0]
        expected = round(0.3 * bid * self.pt_trader.DCA_MULTIPLIER / ask, 8)
        self.assertAlmostEqual(dca[2], expected, places=8)
        self.assertAlmostEqual(self.broker.balances["ETH"], 1.0 + expected)
        books = os.path.relpath(trader.data_dir, self.tmp.name)
        self.assertEqual([r["tag"] for r in self.ledger_rows(books)], [None, "DCA"])


class CoinsTheTraderDidNotBuy(LiveLegacyTrader):
    def test_a_coin_the_trader_never_bought_gets_no_order(self):
        self.broker.balances["ETH"] = 1.0  # the user's own, bought outside the trader
        trader = self.live_trader()
        self.run_through(trader, EVERYTHING)
        self.assertEqual(self.broker.orders, [])
        self.assertNotIn("ETH", trader.trailing_pm)  # no trailing line on it
        self.assertAlmostEqual(self.broker.balances["ETH"], 1.0)

    def test_a_remainder_of_the_traders_own_too_small_to_sell_gets_no_order(self):
        """The trader's sell, rounded down to the exchange's step, left 0.00001 ETH
        (worth $0.001, under the $1 minimum order) in its ledger; the user then
        bought 1 ETH outside the trader."""
        trader = self.live_trader()
        self.traders_own_buy(trader, 30.0)  # 0.3 ETH at $100
        trader.place_sell_order(str(uuid.uuid4()), "sell", "market", "ETH-USD", 0.29999)
        trader.cost_basis = trader.calculate_cost_basis()
        self.assertAlmostEqual(trader._pnl_ledger["open_positions"]["ETH"]["qty"], 1e-5)
        self.broker.balances["ETH"] += 1.0  # the user's own

        done = len(self.broker.orders)
        self.run_through(trader, EVERYTHING)
        self.assertEqual(self.orders_after(done), [])
        self.assertAlmostEqual(self.broker.balances["ETH"], 1.00001)


class PaperTrailingExitSellsTheWholeHolding(LegacyPaperTrader):
    """Paper: the account's coins are the trader's own, so its trailing exit sells
    the whole holding, as before. The ledger adds up the fills in floats and the
    paper account in decimals: 0.7 + 0.1 is 0.7999999999999999 in the ledger and 0.8
    in the account, and the exit must still leave nothing behind."""

    def test_the_trailing_exit_leaves_nothing_of_an_entry_and_a_dca_buy(self):
        self.quotes.bid, self.quotes.ask = 99.9, 100.0
        trader = self.trader(dict(self.SETTINGS))
        for usd, tag in ((70.0, None), (10.0, "DCA")):
            trader.place_buy_order(
                str(uuid.uuid4()), "buy", "market", "BTC-USD", usd, tag=tag
            )
        self.assertNotEqual(trader._pnl_ledger["open_positions"]["BTC"]["qty"], 0.8)
        self.assertEqual(btc_held(), 0.8)
        trader.cost_basis = trader.calculate_cost_basis()
        trader.initialize_dca_levels()

        trader.trailing_pm["BTC"] = crossed_trailing_line(trader)
        trader.manage_trades()
        self.assertEqual(btc_held(), 0.0)
        (sell,) = [r for r in self.ledger_rows() if r["side"] == "sell"]
        self.assertEqual((sell["tag"], sell["qty"]), ("TRAIL_SELL", 0.8))
