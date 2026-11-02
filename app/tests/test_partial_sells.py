"""A sell that fills only in part (a market IOC order can stop part-way on a live
broker such as Coinbase) leaves the rest of the position managed: its strategy
position, trailing line, DCA stages and DCA window stay, before and after a
restart, and the next cycle sells the rest.

The paper exchange always fills in full, so here it fills the first sell in half
and reports it as stopped part-way (``OrderResult.partial``), as Coinbase does.

Also here: a remainder worth less than the smallest order (what a sell rounded down
to the exchange's step can leave) is not a position and does not stop a new entry.
"""

from __future__ import annotations

import copy
import os
import uuid
from unittest import mock

from helpers import Feed, PaperTraderCase, make_candles

import trading_mode as tm
from signal_engine import SignalEngine
from test_signal_engine import PAPER, expected_actions, trend_series


def half_filled_once():
    """The paper exchange fills the next sell in half and reports it as partial;
    later sells fill in full. Returns the quantities the trader asked to sell."""
    exchange = tm.get_paper_exchange()
    real = exchange.place_order
    asked = []

    def place_order(symbol, side, amount, price=None):
        if str(side).lower() != "sell":
            return real(symbol, side, amount, price)
        asked.append(amount)
        if len(asked) > 1:
            return real(symbol, side, amount, price)
        result = real(symbol, side, amount / 2, price)
        result.partial = True  # the rest of the order was cancelled
        return result

    exchange.place_order = place_order
    return asked


def crossed_trailing_line(trader) -> dict:
    """Trailing state for a price that rose to 121 and fell back to ~100: the
    trailing line (~120) is crossed from above, so the trader sells."""
    return {
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


def btc_held() -> float:
    return float(tm.get_paper_exchange().get_balance().get("BTC", 0.0))


class LegacyPaperTrader(PaperTraderCase):
    """A legacy-mode paper trader on BTC at ~100, with neural signal files."""

    SETTINGS = {"trading": {"mode": "paper"}, "strategy": {"engine": "legacy_neural"}}

    def setUp(self):
        super().setUp()
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.one_coin("BTC")
        self.folder = os.path.join(self.tmp.name, "neural")
        os.makedirs(self.folder)
        for p in (
            mock.patch.object(self.pt_trader, "base_paths", {"BTC": self.folder}),
            mock.patch.object(self.pt_trader, "main_dir", self.folder),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.quotes.bid, self.quotes.ask = 99.95, 100.05

    def signal(self, long_level: int) -> None:
        for name, value in (
            ("long_dca_signal.txt", str(long_level)),
            ("short_dca_signal.txt", "0"),
        ):
            with open(os.path.join(self.folder, name), "w") as f:
                f.write(value)


class DustLeftBySell(LegacyPaperTrader):
    """A sell rounded down to the exchange's step can leave a remainder worth less
    than the smallest order: it cannot be sold, so it is not a position."""

    def test_a_remainder_too_small_to_sell_does_not_stop_a_new_entry(self):
        self.markets.minimum = 1.0  # the smallest order the exchanges take: $1
        trader = self.trader(dict(self.SETTINGS))
        exchange = tm.get_paper_exchange()
        exchange.place_order("BTC-USD", "buy", 0.000001)  # ~$0.0001 of BTC
        self.signal(7)
        with mock.patch.object(trader, "place_sell_order") as sell:
            trader.manage_trades()
        sell.assert_not_called()  # the remainder is left alone
        buys = [o for o in exchange.account.orders.values() if o.side.value == "buy"]
        self.assertEqual(len(buys), 2)  # the remainder, then the trader's entry
        self.assertGreater(btc_held(), 0.5)  # ~1% of $10,000 at ~100

    def test_a_holding_worth_an_order_still_counts_as_held(self):
        self.markets.minimum = 1.0
        trader = self.trader(dict(self.SETTINGS))
        exchange = tm.get_paper_exchange()
        exchange.place_order("BTC-USD", "buy", 0.05)  # ~$5 of BTC
        self.signal(7)
        trader.manage_trades()
        buys = [o for o in exchange.account.orders.values() if o.side.value == "buy"]
        self.assertEqual(len(buys), 1)  # held: no new entry


class TrailingStopPartialSell(LegacyPaperTrader):
    """Legacy mode: the trailing profit-margin line sells the position."""

    def test_a_trailing_stop_sell_that_filled_in_part_keeps_the_line_and_sells_the_rest(
        self,
    ):
        trader = self.trader(dict(self.SETTINGS))
        self.signal(7)
        trader.manage_trades()  # the entry
        bought = btc_held()
        self.assertGreater(bought, 0.0)
        self.signal(0)

        trader.trailing_pm["BTC"] = crossed_trailing_line(trader)
        asked = half_filled_once()
        with mock.patch.object(
            trader,
            "_reset_dca_window_for_trade",
            wraps=trader._reset_dca_window_for_trade,
        ) as reset_dca:
            trader.manage_trades()
            self.assertEqual(len(asked), 1)
            self.assertAlmostEqual(btc_held(), bought / 2, places=8)
            self.assertIn("BTC", trader.trailing_pm)  # the line is kept...
            self.assertTrue(trader.trailing_pm["BTC"]["was_above"])  # ...and crossed
            reset_dca.assert_not_called()

            trader.manage_trades()  # the next cycle sells the rest
        self.assertEqual(len(asked), 2)
        self.assertAlmostEqual(asked[1], bought / 2, places=8)
        self.assertAlmostEqual(btc_held(), 0.0, places=8)
        self.assertNotIn("BTC", trader.trailing_pm)
        reset_dca.assert_called_once()
        sells = [r for r in self.ledger_rows() if r["side"] == "sell"]
        self.assertEqual([r["closes_position"] for r in sells], [False, True])

    def test_a_partial_sell_keeps_the_dca_stages_before_and_after_a_restart(self):
        trader = self.trader(dict(self.SETTINGS))
        self.signal(7)
        trader.manage_trades()  # the entry
        self.signal(0)
        trader.place_buy_order(
            str(uuid.uuid4()), "buy", "market", "BTC-USD", 50.0, tag="DCA"
        )
        trader._note_dca_buy("BTC")
        trader.initialize_dca_levels()
        self.assertEqual(trader.dca_levels_triggered["BTC"], [0])  # one DCA stage
        self.assertEqual(trader._dca_window_count("BTC"), 1)

        trader.trailing_pm["BTC"] = crossed_trailing_line(trader)
        half_filled_once()
        trader.manage_trades()  # half is sold: the trade goes on
        self.assertGreater(btc_held(), 0.0)
        self.assertEqual(trader.dca_levels_triggered["BTC"], [0])
        self.assertEqual(trader._dca_window_count("BTC"), 1)

        restarted = self.trader(dict(self.SETTINGS))  # rebuilt from the books
        self.assertEqual(restarted.dca_levels_triggered["BTC"], [0])
        self.assertEqual(restarted._dca_window_count("BTC"), 1)


class StrategyExitPartialSell(PaperTraderCase):
    """Catalogue mode: the strategy's exit sells the position."""

    def setUp(self):
        super().setUp()
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.one_coin("BTC")
        self.frame = make_candles(trend_series())
        self.feed = Feed(self.frame)

    def test_a_strategy_exit_that_filled_in_part_keeps_the_position_and_sells_the_rest(
        self,
    ):
        (_enter_bar, _), (exit_bar, _) = expected_actions(self.frame)
        settings = copy.deepcopy(PAPER)
        engine = SignalEngine(settings, self.feed.provider, self.feed.clock)
        self.feed.set_after_bar(150)
        trader = self.pt_trader.CryptoAPITrading(
            settings_source=settings, signal_engine=engine
        )
        trader._order_poll_seconds = 0.0
        for k in range(150, exit_bar):
            self.feed.set_after_bar(k)
            trader.manage_trades()
        bought = btc_held()
        self.assertGreater(bought, 0.0)

        asked = half_filled_once()
        self.feed.set_after_bar(exit_bar)
        trader.manage_trades()
        self.assertEqual(len(asked), 1)
        self.assertAlmostEqual(btc_held(), bought / 2, places=8)
        self.assertIsNotNone(trader.signal_engine.position("BTC"))  # still open

        trader.manage_trades()  # the exit still stands: the rest is sold
        self.assertEqual(len(asked), 2)
        self.assertAlmostEqual(asked[1], bought / 2, places=8)
        self.assertAlmostEqual(btc_held(), 0.0, places=8)
        self.assertIsNone(trader.signal_engine.position("BTC"))
