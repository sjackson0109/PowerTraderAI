"""Order intents (the owner's decision of 2026-11-12; defect N5 in
docs/dev/ptai-rd-001/A2-defect-register.md).

An order is recorded in pnl_ledger.json (``order_intents``) before it is sent. When the
send raises (a timeout, a dropped connection) the order may have been made all the
same, so it is never sent again under a new client order id:

* On Coinbase, which answers a repeated client order id with the order it already made,
  the next order on that coin and side is the same order sent again: same id, same
  quantity. Coinbase made one order, and the trader records it once. Before, the next
  order went with a new id and Coinbase made a second.
* Where the exchange gives no such promise (here the paper exchange), no order is sent
  on that coin and side for ``UNKNOWN_ORDER_WAIT_SECONDS``; then the intent is given up
  with an error, and orders go on.
* An answer from the exchange (made, refused) ends the intent. An intent older than
  ``UNKNOWN_ORDER_RESEND_SECONDS`` is given up the same way.
* An order that cannot be recorded first is not sent.
* A restart reports every kept intent and goes on as above.

Coinbase is the recorded-HTTP fake of test_coinbase_live_trader.py; nothing leaves the
machine."""

import copy
import json
import os
import sys
import time
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(__file__))

import trading_mode as tm  # noqa: E402
from helpers import PaperTraderCase  # noqa: E402
from helpers_coinbase import recorded_http  # noqa: E402
from pt_exchange_abstraction import OrderResult  # noqa: E402
from test_coinbase_live_trader import REAL, FakeCoinbase, rows  # noqa: E402
from test_coinbase_paper_gate import CoinbaseGateBase  # noqa: E402


class LostAnswer(FakeCoinbase):
    """Coinbase makes the order, and its answer is lost on the way back (``lose``
    times). Each order is checked to have been on disk before it was sent."""

    def __init__(self, rec, ledger_path, lose=1, **kwargs):
        super().__init__(rec, **kwargs)
        self.ledger_path = ledger_path
        self.lose = lose
        self.recorded_first = []

    def create(self, kwargs):
        body = json.loads(kwargs["data"])
        with open(self.ledger_path, encoding="utf-8") as f:
            intents = json.load(f).get("order_intents", {})
        self.recorded_first.append(
            any(
                i.get("client_order_id") == body["client_order_id"]
                for i in intents.values()
            )
        )
        answer = super().create(kwargs)
        if self.lose:
            self.lose -= 1
            raise requests.exceptions.ReadTimeout("read timed out")
        return answer


class CoinbaseIntentTests(CoinbaseGateBase):
    def setUp(self):
        super().setUp()
        sleep = mock.patch("pt_trader.time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def books(self, *parts):
        return os.path.join(self.tmp.name, "live", "coinbase", *parts)

    def ledger(self):
        with open(self.books("pnl_ledger.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_a_lost_answer_is_sent_again_with_its_id_and_recorded_once(self):
        with recorded_http() as rec:
            cb = LostAnswer(rec, self.books("pnl_ledger.json"))
            trader = self.trader(copy.deepcopy(REAL))
            first = trader.place_buy_order("c-1", "buy", "market", "BTC-USD", 50.0)
            self.assertIsNone(first)  # the answer was lost
            kept = self.ledger()["order_intents"]["BTC-USD|buy"]
            self.assertEqual(kept["client_order_id"], "c-1")
            again = trader.place_buy_order("c-2", "buy", "market", "BTC-USD", 50.0)
        self.assertEqual(cb.recorded_first, [True, True])  # on disk before each send
        self.assertEqual([o["client_order_id"] for o in cb.order_calls()], ["c-1"] * 2)
        self.assertEqual(
            [o["order_configuration"] for o in cb.order_calls()][0],
            [o["order_configuration"] for o in cb.order_calls()][1],
        )  # the same order
        self.assertEqual(list(cb.orders), ["cb-1"])  # Coinbase made one
        self.assertEqual(again["state"], "filled")
        (row,) = rows(self.books("trade_history.jsonl"))
        self.assertEqual(row["order_id"], "cb-1")
        self.assertEqual(self.ledger()["order_intents"], {})

    def test_a_restart_reports_the_kept_order_and_sends_it_again(self):
        with recorded_http() as rec:
            cb = LostAnswer(rec, self.books("pnl_ledger.json"))
            first = self.trader(copy.deepcopy(REAL))
            self.assertIsNone(
                first.place_buy_order("c-1", "buy", "market", "BTC-USD", 50.0)
            )
            with mock.patch("builtins.print") as said:
                restarted = self.trader(copy.deepcopy(REAL))
            self.assertIn(
                "Order c-1 (BTC-USD buy) was being sent when the trader last stopped",
                str(said.call_args_list),
            )
            again = restarted.place_buy_order("c-9", "buy", "market", "BTC-USD", 50.0)
        self.assertEqual(again["state"], "filled")
        self.assertEqual(list(cb.orders), ["cb-1"])
        self.assertEqual(len(rows(self.books("trade_history.jsonl"))), 1)

    def test_an_intent_past_the_resend_time_is_given_up(self):
        with recorded_http() as rec:
            cb = LostAnswer(rec, self.books("pnl_ledger.json"))
            trader = self.trader(copy.deepcopy(REAL))
            trader.place_buy_order("c-1", "buy", "market", "BTC-USD", 50.0)
            intent = trader._pnl_ledger["order_intents"]["BTC-USD|buy"]
            intent["first_ts"] = time.time() - 16 * 60
            with mock.patch("builtins.print") as said:
                again = trader.place_buy_order("c-2", "buy", "market", "BTC-USD", 50.0)
        self.assertIn("its outcome is still unknown", str(said.call_args_list))
        self.assertEqual(
            [o["client_order_id"] for o in cb.order_calls()], ["c-1", "c-2"]
        )
        self.assertEqual(again["state"], "filled")

    def test_preview_mode_keeps_no_intent(self):
        with recorded_http() as rec:
            FakeCoinbase(rec)
            trader = self.trader(
                {"trading": {**REAL["trading"], "coinbase_preview": True}}
            )
            trader.place_buy_order("p-1", "buy", "market", "BTC-USD", 50.0)
        self.assertEqual(trader._pnl_ledger.get("order_intents"), {})


def rejected(symbol, side, amount, *a, **k):
    return OrderResult(
        "", symbol, side, amount, 0.0, "rejected", "paper", 0, reason="NO_PRICE"
    )


class PaperIntentTests(PaperTraderCase):
    """The paper exchange gives no promise about repeated ids: it waits instead."""

    def setUp(self):
        super().setUp()
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        tm.reset_paper_exchange()

    def test_after_a_lost_send_nothing_is_sent_until_the_wait_is_over(self):
        trader = self.trader()
        exchange = tm.get_paper_exchange()
        real = exchange.place_order
        calls = []

        def lost_once(*args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                raise ConnectionError("connection reset")
            return real(*args, **kwargs)

        with mock.patch.object(exchange, "place_order", side_effect=lost_once):
            self.assertIsNone(
                trader.place_buy_order("p-1", "buy", "market", "BTC-USD", 50.0)
            )
            self.assertIn("BTC-USD|buy", trader._pnl_ledger["order_intents"])
            self.assertIsNone(
                trader.place_buy_order("p-2", "buy", "market", "BTC-USD", 50.0)
            )
            self.assertEqual(len(calls), 1)  # nothing sent while it waits
            intent = trader._pnl_ledger["order_intents"]["BTC-USD|buy"]
            intent["first_ts"] = time.time() - 61
            with mock.patch("builtins.print") as said:
                done = trader.place_buy_order("p-3", "buy", "market", "BTC-USD", 50.0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(done["state"], "filled")
        self.assertIn("its outcome is still unknown", str(said.call_args_list))
        self.assertEqual(trader._pnl_ledger["order_intents"], {})

    def test_an_answer_ends_the_intent(self):
        trader = self.trader()
        exchange = tm.get_paper_exchange()
        with mock.patch.object(exchange, "place_order", side_effect=rejected):
            self.assertIsNone(
                trader.place_buy_order("p-1", "buy", "market", "BTC-USD", 50.0)
            )
        self.assertEqual(trader._pnl_ledger["order_intents"], {})

    def test_an_order_that_cannot_be_recorded_first_is_not_sent(self):
        trader = self.trader()
        exchange = tm.get_paper_exchange()
        with mock.patch.object(
            trader, "_atomic_write_json", side_effect=OSError("disk full")
        ), mock.patch.object(exchange, "place_order") as place, mock.patch(
            "builtins.print"
        ) as said:
            self.assertIsNone(
                trader.place_buy_order("p-1", "buy", "market", "BTC-USD", 50.0)
            )
        place.assert_not_called()
        self.assertIn("ORDER NOT SENT (BTC-USD buy)", str(said.call_args_list))


class ConnectorTests(unittest.TestCase):
    def test_only_coinbase_promises_a_repeated_id_gets_its_order(self):
        from pt_exchanges import BinanceExchange, CoinbaseExchange

        self.assertTrue(CoinbaseExchange.REPEATED_CLIENT_ORDER_ID_RETURNS_ORDER)
        self.assertFalse(
            getattr(BinanceExchange, "REPEATED_CLIENT_ORDER_ID_RETURNS_ORDER", False)
        )
        self.assertFalse(
            getattr(tm.PaperExchange, "REPEATED_CLIENT_ORDER_ID_RETURNS_ORDER", False)
        )


if __name__ == "__main__":
    unittest.main()
