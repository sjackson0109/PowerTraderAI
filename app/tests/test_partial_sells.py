"""A sell that fills only in part (a market IOC order can stop part-way on a live
broker such as Coinbase) leaves the rest of the position managed: its strategy
position, trailing line and DCA window stay, and the next cycle sells the rest.

The paper exchange always fills in full, so the first sell here is sent for half
the quantity and its result marked ``partial``, as the trader reports a live
order that stopped part-way.
"""

from __future__ import annotations

import copy
import os
from unittest import mock

from helpers import Feed, PaperTraderCase, make_candles

import trading_mode as tm
from signal_engine import SignalEngine
from test_signal_engine import PAPER, expected_actions, trend_series


def half_filled_once(trader):
    """The trader's first sell fills half of what was asked and says so; later
    sells fill in full. Returns the quantities the trader asked to sell."""
    real = trader.place_sell_order
    asked = []

    def sell(client_order_id, side, order_type, symbol, quantity, **kwargs):
        asked.append(quantity)
        if len(asked) > 1:
            return real(client_order_id, side, order_type, symbol, quantity, **kwargs)
        response = real(
            client_order_id, side, order_type, symbol, quantity / 2, **kwargs
        )
        response["partial"] = True
        return response

    trader.place_sell_order = sell
    return asked


def btc_held() -> float:
    return float(tm.get_paper_exchange().get_balance().get("BTC", 0.0))


class TrailingStopPartialSell(PaperTraderCase):
    """Legacy mode: the trailing profit-margin line sells the position."""

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

    def test_a_trailing_stop_sell_that_filled_in_part_keeps_the_line_and_sells_the_rest(
        self,
    ):
        trader = self.trader(dict(self.SETTINGS))
        self.signal(7)
        trader.manage_trades()  # the entry
        bought = btc_held()
        self.assertGreater(bought, 0.0)
        self.signal(0)

        # the price rose to 121 and fell back to ~100: the trailing line is crossed
        trader.trailing_pm["BTC"] = {
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
        asked = half_filled_once(trader)
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

        asked = half_filled_once(trader)
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
