"""The emergency halt refuses buys and keeps managing what is held (the owner's
decision of 2026-11-12, defect N1 in docs/dev/ptai-rd-001/A2-defect-register.md).

* A replayed paper session halted after its entry still sells at the strategy's exit,
  on the same bar and for the same quantity as without the halt, and buys nothing more.
* Halted before any entry, it buys nothing. No entry decision, LLM check or entry
  assessment is made while halted.
* The order gate refuses a buy and lets a sell through; so does the risk adapter.
* After an emergency stop the loop goes on managing trades: it no longer ends.
* The risk manager's emergency stop logs only what it does (no "Closing all
  positions" or "Cancelling all pending orders" it never did).

No network: the trader runs on the test helpers' fake quotes, fees and candles."""

from __future__ import annotations

import copy
import logging
import os
import unittest
from unittest import mock

import numpy as np
from helpers import Feed, PaperTraderCase, make_candles

import trading_mode as tm
from pt_risk import RiskLimits, RiskManager
from signal_engine import SignalEngine

PAPER = {"trading": {"mode": "paper"}, "strategy": {"active_id": "STRAT-000"}}
# what an order is compared by (as in test_strategy_lifecycle.py, without times)
ORDER_FIELDS = (
    "symbol",
    "side",
    "order_type",
    "quantity",
    "price",
    "status",
    "filled_quantity",
    "commission",
    "commission_rate",
)


def trend_series():
    """Down, up, then down: STRAT-000 buys on the way up and sells on the way down."""
    down = np.linspace(200, 150, 150)
    up = np.linspace(150, 240, 40)
    fall = np.linspace(240, 110, 70)
    return np.concatenate([down, up, fall])


class StopRun(BaseException):
    """Ends the trader's endless loop in a test (run() catches Exception)."""


class HaltedSessionTests(PaperTraderCase):
    """A replayed paper session (the method of test_strategy_lifecycle.py)."""

    def setUp(self):
        super().setUp()
        self.frame = make_candles(trend_series())
        for p in (
            mock.patch.object(self.pt_trader.time, "sleep"),
            mock.patch.object(self.pt_trader, "crypto_symbols", ["BTC"]),
        ):
            p.start()
            self.addCleanup(p.stop)

    def session(self, halt_at=None):
        """The orders of a session; ``halt_at``: "start", "after entry" or None."""
        tm.reset_paper_exchange()
        tm._quote_cache.clear()
        self.sessions = getattr(self, "sessions", 0) + 1
        folder = os.path.join(self.tmp.name, f"session{self.sessions}")
        os.makedirs(folder)
        settings = copy.deepcopy(PAPER)
        feed = Feed(self.frame)
        engine = SignalEngine(settings, feed.provider, feed.clock)
        feed.set_after_bar(150)
        exchange = None
        with mock.patch.object(self.pt_trader, "HUB_DATA_DIR", folder):
            trader = self.pt_trader.CryptoAPITrading(
                settings_source=settings, signal_engine=engine
            )
            trader._order_poll_seconds = 0.0
            self.trader_seen = trader
            if halt_at == "start":
                trader.risk_manager.emergency_stop("test halt", 1000.0)
            for k in range(150, len(self.frame)):
                feed.set_after_bar(k)
                trader.manage_trades()
                exchange = tm.get_paper_exchange()
                buys = [
                    o for o in exchange.account.orders.values() if o.side.value == "buy"
                ]
                if halt_at == "after entry" and buys:
                    if not trader.risk_manager.is_trading_halted():
                        trader.risk_manager.emergency_stop("test halt", 1000.0)
        orders = list(tm.get_paper_exchange().account.orders.values())
        return [
            tuple(str(getattr(o, name, None)) for name in ORDER_FIELDS) for o in orders
        ]

    def test_a_halt_after_the_entry_still_sells_at_the_exit(self):
        plain = self.session()
        self.assertEqual([o[1] for o in plain], ["OrderSide.BUY", "OrderSide.SELL"])
        halted = self.session(halt_at="after entry")
        self.assertTrue(self.trader_seen.risk_manager.is_trading_halted())
        # the same sell (its price says the bar), the same quantity, no other buy
        self.assertEqual(halted, plain)

    def test_a_session_s_own_fills_explain_every_balance_change(self):
        # the drawdown stop compares its balances with the fills recorded: a
        # paper session's own buy and sell leave nothing unexplained, so no buy
        # waits and nothing is counted as a deposit or a loss
        import risk_state

        self.assertEqual(
            [o[1] for o in self.session()], ["OrderSide.BUY", "OrderSide.SELL"]
        )
        trader = self.trader_seen
        self.assertIsNone(trader._balance_change)
        self.assertEqual(risk_state.current(trader.data_dir).balance_changes, ())
        self.assertIn("last_balances", risk_state.read_state(trader.data_dir))

    def test_halted_from_the_start_it_buys_nothing(self):
        self.assertEqual(self.session(halt_at="start"), [])

    def test_no_entry_work_is_done_while_halted(self):
        tm.reset_paper_exchange()
        trader = self.trader()
        trader.risk_manager.emergency_stop("test halt", 1000.0)
        with mock.patch.object(trader, "_llm_entry_allowed") as llm, mock.patch.object(
            trader, "_entry_assessment_capture"
        ) as assess, mock.patch.object(trader.signal_engine, "decide") as decide:
            trader.manage_trades()
        self.assertFalse(llm.called or assess.called or decide.called)


class GateTests(PaperTraderCase):
    def test_the_gate_refuses_a_buy_and_lets_a_sell_through(self):
        trader = self.trader()
        trader._last_good_account_snapshot["total_account_value"] = 1000.0
        self.assertTrue(trader._risk_check("BTC-USD", "buy", 0.0001, 100.0))
        trader.risk_manager.emergency_stop("test halt", 1000.0)
        with mock.patch("builtins.print") as said:
            self.assertFalse(trader._risk_check("BTC-USD", "buy", 0.0001, 100.0))
        self.assertIn("buying is halted", str(said.call_args_list))
        self.assertTrue(trader._risk_check("BTC-USD", "sell", 5.0, 100.0))

    def test_the_adapter_approves_sells_only_while_halted(self):
        adapter = self.pt_trader._TraderRiskAdapter()
        adapter.emergency_stop("why")
        order = {"symbol": "BTC-USD", "quantity": 1.0, "price": 10.0}
        buy = adapter.validate_order(dict(order, side="buy"), 1000.0, 100.0)
        sell = adapter.validate_order(dict(order, side="sell"), 1000.0, 100.0)
        self.assertEqual(
            buy,
            {
                "approved": False,
                "reason": "Buying is halted by risk controls (sells still go through)",
            },
        )
        self.assertTrue(sell["approved"])


class LoopTests(PaperTraderCase):
    def test_after_an_emergency_stop_the_loop_still_manages_trades(self):
        trader = self.trader()
        trader._last_good_account_snapshot["total_account_value"] = 900.0
        trader.risk_manager.update_portfolio_value(1000.0)  # the peak
        with mock.patch.object(
            trader, "manage_trades", side_effect=StopRun
        ) as manage, mock.patch.object(self.pt_trader.time, "sleep"), mock.patch(
            "builtins.print"
        ) as said:
            with self.assertRaises(StopRun):
                trader.run()
        self.assertTrue(manage.called)
        self.assertTrue(trader.risk_manager.is_trading_halted())
        text = str(said.call_args_list)
        self.assertIn("EMERGENCY STOP: Account drawdown 10.0%", text)
        self.assertIn("BUYING HALTED", text)
        self.assertIn("Exits, stops and the trailing margin still sell", text)


class RiskManagerTests(unittest.TestCase):
    def test_the_emergency_stop_logs_only_what_it_does(self):
        manager = RiskManager(RiskLimits())
        with self.assertLogs(manager.logger, level=logging.DEBUG) as logs, mock.patch(
            "pt_paths.log_file", side_effect=OSError("no folder")
        ):
            manager.emergency_stop()
        self.assertTrue(manager.is_trading_halted)
        self.assertTrue(manager.emergency_stop_triggered)
        said = "\n".join(logs.output)
        self.assertIn("EMERGENCY STOP: buying halted", said)
        for claim in (
            "Closing all positions",
            "Cancelling all pending orders",
            "Halting all trading strategies",
            "Disconnecting",
            "notifications sent",
        ):
            self.assertNotIn(claim, said)


if __name__ == "__main__":
    unittest.main()
