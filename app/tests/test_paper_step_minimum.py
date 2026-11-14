"""Paper fills follow the exchange's sell step and minimum order (owner, 2026-11-12;
defect register N28, decision O14).

A live sell on Coinbase is sized in coins, rounded down to the product's
``base_increment``, and an order worth less than the minimum is refused before it is
sent (``CoinbaseExchange._market_order``); the replay rounds a sell the same way
(``replay.Costs.base_increment``). The paper exchange now does too, with the figures
the exchange layer gives (the exchanges in Settings, primary first, from public
product data: ``lot_increment`` and ``min_order_usd``), the same minimum the paper
trader sizes its entries with and tells dust by:

* a sell is rounded down to the step; what is left stays in the paper book;
* a buy is not rounded (Coinbase sizes a market buy in dollars);
* an order worth less than the minimum, or a sell smaller than one step, is refused
  with a reason (``BELOW_MINIMUM: ...``), as live reports a refused order, and the
  book is unchanged;
* where no exchange states a step or a minimum (offline, say), nothing is rounded or
  refused, as before.

The fee convention is unchanged (paper charges the fee on top of the amount).

Everything runs under the isolation guard (app/conftest.py); no network.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import time
import unittest
from decimal import Decimal
from unittest import mock

from helpers import PaperTraderCase

import trading_mode as tm
from pt_exchange_abstraction import TradingFees

FEES = TradingFees(maker=0.004, taker=0.006, exchange="coinbase", source="exchange")


def quote(bid=0.25, ask=0.2502, exchange="coinbase"):
    now = time.time()
    return tm.Quote(bid=bid, ask=ask, quote_ts=now, fetched_ts=now, exchange=exchange)


class PaperSellStepAndMinimum(unittest.TestCase):
    """The paper exchange on DOGE at bid 0.25 / ask 0.2502, Coinbase's fees."""

    def make(self, step=None, minimum=None, answer=None, **kwargs):
        """A paper exchange whose venue feed states ``step`` and ``minimum`` (or
        gives ``answer``, or raises it); records the coins it was asked about."""
        self.asked = []

        def venue(base):
            self.asked.append(base)
            if isinstance(answer, Exception):
                raise answer
            if answer is not None:
                return answer
            return tm.VenueRules(sell_step=step, minimum_usd=minimum)

        return tm.PaperExchange(
            price_feed=lambda base: quote(),
            fee_feed=lambda base, exchange: FEES,
            venue_feed=venue,
            **kwargs,
        )

    def test_a_paper_sell_is_rounded_down_to_the_exchanges_step(self):
        """The register's case: 0.123456789 DOGE with a step of 0.1 sells 0.1."""
        ex = self.make(step=0.1)
        ex.place_order("DOGE-USD", "buy", 0.123456789)
        cash = ex.get_balance()["USD"]

        result = ex.place_order("DOGE-USD", "sell", 0.123456789)

        self.assertEqual(result.status, "filled")
        self.assertEqual(result.amount, 0.1)
        self.assertAlmostEqual(result.filled_value, 0.1 * 0.25)
        self.assertFalse(result.partial)  # the whole (rounded) order filled
        # the remainder is still held, and only what was sold was paid for
        self.assertEqual(ex.account.positions["DOGE"].quantity, Decimal("0.023456789"))
        self.assertAlmostEqual(ex.get_balance()["DOGE"], 0.023456789)
        self.assertAlmostEqual(ex.get_balance()["USD"], cash + 0.1 * 0.25 * 0.994)
        (trade,) = ex.account.trade_history
        self.assertEqual(trade.quantity, Decimal("0.1"))
        self.assertEqual(ex.account.orders[result.order_id].quantity, Decimal("0.1"))

    def test_a_buy_is_not_rounded(self):
        """Coinbase sizes a market buy in dollars, not in steps of the coin."""
        ex = self.make(step=0.1)
        result = ex.place_order("DOGE-USD", "buy", 0.123456789)
        self.assertEqual(result.amount, 0.123456789)

    def test_the_remainder_stays_in_the_saved_book(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "paper_account.json")
            ex = self.make(step=0.1, minimum=1.0, state_path=path)
            ex.place_order("DOGE-USD", "buy", 400.0123)
            ex.place_order("DOGE-USD", "sell", 400.0123)
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved["positions"]["DOGE"]["quantity"], "0.0123")
            book = tm.read_paper_book(path)
            self.assertEqual(book.positions["DOGE"][0], Decimal("0.0123"))
            self.assertEqual(Decimal(saved["cash_balance"]), ex.account.cash_balance)

    def test_an_order_worth_less_than_the_minimum_is_refused_with_a_reason(self):
        ex = self.make(step=0.1, minimum=1.0)
        result = ex.place_order("DOGE-USD", "buy", 3.0)  # $0.75 at the ask
        self.assertEqual((result.status, result.amount), ("rejected", 0.0))
        self.assertEqual(
            result.reason,
            "BELOW_MINIMUM: 3 DOGE is worth about $0.75, below the exchange's "
            "minimum order of $1 for DOGE-USD",
        )
        self.assertEqual(ex.get_order_status(result.order_id), result)
        # nothing was placed and nothing changed in the book
        self.assertEqual(ex.account.orders, {})
        self.assertEqual(ex.get_balance(), {"USD": 10_000.0})

    def test_a_sell_worth_less_than_the_minimum_is_refused_and_the_coins_kept(self):
        ex = self.make(step=0.1, minimum=1.0)
        ex.place_order("DOGE-USD", "buy", 10.0)  # $2.50
        cash = ex.get_balance()["USD"]
        result = ex.place_order("DOGE-USD", "sell", 3.0)  # $0.75 at the bid
        self.assertEqual(result.status, "rejected")
        self.assertTrue(result.reason.startswith("BELOW_MINIMUM: 3 DOGE is worth"))
        self.assertEqual(ex.get_balance(), {"USD": cash, "DOGE": 10.0})
        # worth the minimum once rounded down (4.05 -> 4.0, $1.00 at the bid): sold
        self.assertEqual(ex.place_order("DOGE-USD", "sell", 4.05).amount, 4.0)

    def test_a_sell_smaller_than_one_step_is_refused(self):
        ex = self.make(step=0.1)
        ex.place_order("DOGE-USD", "buy", 0.05)
        result = ex.place_order("DOGE-USD", "sell", 0.05)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(
            result.reason,
            "BELOW_MINIMUM: 0.05 DOGE is less than the exchange's sell step of "
            "0.1 DOGE",
        )
        self.assertAlmostEqual(ex.get_balance()["DOGE"], 0.05)

    def test_with_no_step_or_minimum_known_nothing_is_rounded_or_refused(self):
        """Offline, or no exchange in Settings states them: as before."""
        answers = [
            None,  # the step and minimum are both unknown
            RuntimeError("offline"),
            tm.VenueRules(sell_step=-1.0, minimum_usd=float("nan")),
            tm.VenueRules(sell_step=mock.Mock(), minimum_usd="1"),
            mock.Mock(),  # an answer that is not venue rules at all
        ]
        for answer in answers:
            with self.subTest(answer=answer):
                ex = self.make(answer=answer)
                self.assertEqual(
                    ex.place_order("DOGE-USD", "buy", 0.2).status, "filled"
                )
                sold = ex.place_order("DOGE-USD", "sell", 0.123456789)
                self.assertEqual((sold.status, sold.amount), ("filled", 0.123456789))
        no_feed = tm.PaperExchange(
            price_feed=lambda base: quote(), fee_feed=lambda base, exchange: FEES
        )
        no_feed.place_order("DOGE-USD", "buy", 0.123456789)
        self.assertEqual(
            no_feed.place_order("DOGE-USD", "sell", 0.123456789).amount, 0.123456789
        )
        self.assertNotIn("DOGE", no_feed.get_balance())

    def test_a_limit_order_is_rounded_and_checked_at_its_own_price(self):
        ex = self.make(step=0.1, minimum=1.0)
        ex.place_order("DOGE-USD", "buy", 20.0)
        filled = ex.fill_limit_order("DOGE-USD", "sell", 4.123, 0.26)
        self.assertEqual(
            (filled.status, filled.amount, filled.price), ("filled", 4.1, 0.26)
        )
        waiting = ex.place_order("DOGE-USD", "sell", 4.123, price=0.3)
        self.assertEqual(ex.account.orders[waiting.order_id].quantity, Decimal("4.1"))
        refused = ex.fill_limit_order("DOGE-USD", "sell", 3.0, 0.3)  # $0.90
        self.assertEqual(refused.status, "rejected")
        self.assertTrue(refused.reason.startswith("BELOW_MINIMUM: "))

    def test_the_rules_are_reused_for_an_hour(self):
        now = [1_000_000.0]
        ex = self.make(step=0.1, clock=lambda: now[0], settings_source={})
        with mock.patch.object(tm, "classify_quote", return_value="live"):
            ex.place_order("DOGE-USD", "buy", 1.0)
            ex.place_order("DOGE-USD", "sell", 0.5)
            self.assertEqual(self.asked, ["DOGE"])
            now[0] += 3_601.0
            ex.place_order("DOGE-USD", "sell", 0.2)
        self.assertEqual(self.asked, ["DOGE", "DOGE"])


class VenueRulesFromTheExchangeLayer(unittest.TestCase):
    def test_the_exchanges_in_settings_are_asked_for_the_coins_dollar_market(self):
        manager = mock.Mock()
        manager.lot_increment.return_value = 0.1
        manager.min_order_usd.return_value = 1.0
        with mock.patch("pt_multi_exchange.market_exchanges", return_value=manager):
            self.assertEqual(
                tm.fetch_venue_rules("DOGE"),
                tm.VenueRules(sell_step=0.1, minimum_usd=1.0),
            )
        manager.lot_increment.assert_called_once_with("DOGE-USD")
        manager.min_order_usd.assert_called_once_with("DOGE-USD")

    def test_when_the_layer_cannot_be_asked_nothing_is_known(self):
        with mock.patch.object(tm, "_layer_venue_rules", side_effect=OSError("down")):
            self.assertEqual(tm.fetch_venue_rules("DOGE"), tm.VenueRules())

    def test_every_paper_account_asks_the_exchange_layer(self):
        tm.reset_paper_exchange()
        self.addCleanup(tm.reset_paper_exchange)
        self.assertIs(tm.get_paper_exchange()._venue_feed, tm.fetch_venue_rules)
        ex = tm.configure_paper_exchange(price_feed=None)
        self.assertIs(ex._venue_feed, tm.fetch_venue_rules)


class TraderOnSteppedPaper(PaperTraderCase):
    """A legacy-mode paper trader on DOGE at bid 0.25 / ask 0.2501; the exchanges in
    Settings state a sell step of 0.1 DOGE and a $1 minimum order."""

    SETTINGS = {"trading": {"mode": "paper"}, "strategy": {"engine": "legacy_neural"}}

    def setUp(self):
        super().setUp()
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.one_coin("DOGE")
        self.folder = os.path.join(self.tmp.name, "neural")
        os.makedirs(self.folder)
        for p in (
            mock.patch.object(self.pt_trader, "base_paths", {"DOGE": self.folder}),
            mock.patch.object(self.pt_trader, "main_dir", self.folder),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.quotes.bid, self.quotes.ask = 0.25, 0.2501
        self.markets.step = 0.1
        self.markets.minimum = 1.0

    def signal(self, long_level: int) -> None:
        for name, value in (
            ("long_dca_signal.txt", str(long_level)),
            ("short_dca_signal.txt", "0"),
        ):
            with open(os.path.join(self.folder, name), "w") as f:
                f.write(value)

    def doge_held(self) -> float:
        return float(tm.get_paper_exchange().get_balance().get("DOGE", 0.0))

    def orders(self, side: str) -> list:
        book = tm.get_paper_exchange().account
        return [o for o in book.orders.values() if o.side.value == side]

    def test_a_dust_remainder_is_not_sold_again(self):
        """The trailing line's sell is rounded down to the step; the remainder, worth
        less than the minimum, is left alone: no sell is tried on it again."""
        trader = self.trader(dict(self.SETTINGS))
        self.signal(3)
        trader.manage_trades()  # the entry: about $100 of DOGE
        bought = self.doge_held()
        sold = math.floor(round(bought / 0.1, 6)) * 0.1
        self.assertGreater(bought - sold, 0.0)  # $100 at the ask is not whole steps
        self.signal(0)
        trader.trailing_pm["DOGE"] = {
            "active": True,
            "line": 120.0,
            "peak": 121.0,
            "was_above": True,
            "settings_sig": (
                float(trader.trailing_gap_pct),
                float(trader.pm_start_pct_no_dca),
                float(trader.pm_start_pct_with_dca),
            ),
        }
        trader.manage_trades()  # the sell
        self.assertAlmostEqual(self.doge_held(), bought - sold, places=8)
        (sell,) = [r for r in self.ledger_rows() if r["side"] == "sell"]
        self.assertAlmostEqual(sell["qty"], sold, places=8)
        self.assertTrue(sell["closes_position"])

        with mock.patch("builtins.print") as printed:
            with self.assertLogs("pt_trader", level="WARNING") as logs:
                for _ in range(5):
                    trader.manage_trades()
        self.assertEqual(len(self.orders("sell")), 1)  # never tried again
        self.assertEqual(len(self.orders("buy")), 1)
        said = " ".join(str(c) for c in printed.call_args_list)
        self.assertNotIn("ORDER REJECTED", said)
        dust = [m for m in logs.output if "worth less than the smallest order" in m]
        self.assertEqual(len(dust), 1)  # said once, not every cycle

    def test_an_exit_worth_less_than_the_minimum_is_refused_and_said_once(self):
        """An open trade the price took below the minimum: its sell is refused as the
        exchange would refuse it. Each try is reported once an hour, not every cycle,
        and is not counted as a missing price."""
        trader = self.trader(dict(self.SETTINGS))
        bought = trader.place_buy_order("id", "buy", "market", "DOGE-USD", 1.5)
        self.assertIsNotNone(bought)
        self.quotes.bid, self.quotes.ask = 0.1, 0.1001  # now worth about $0.60
        tm._quote_cache.clear()
        with mock.patch("builtins.print") as printed:
            with self.assertLogs("pt_trader", level="WARNING") as logs:
                # the paper exchange says nothing of its own (not "rounded down")
                with self.assertNoLogs("trading_mode", level="INFO"):
                    for _ in range(3):
                        result = trader.place_sell_order(
                            "x", "sell", "market", "DOGE-USD", bought["quantity"]
                        )
                        self.assertIsNone(result)
        self.assertEqual(self.orders("sell"), [])
        self.assertAlmostEqual(self.doge_held(), bought["quantity"], places=8)
        said = [str(c) for c in printed.call_args_list if "ORDER REJECTED" in str(c)]
        self.assertEqual(len(said), 1)
        self.assertIn("BELOW_MINIMUM", said[0])
        rejected = [m for m in logs.output if "Order rejected" in m]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(trader._degraded_last_hour(), 0)
