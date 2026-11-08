"""FDS-SR-001 milestone M6a: each trade record names the strategy that made it (sections
5.11 and 12).

* A replayed paper session places byte-identical orders with and without the new
  fields: they are records only.
* Each trade row carries the strategy's id, version, the SHA-256 of its full parameters,
  its timeframe and its overlays; a legacy-engine row says so; an error leaves the row
  as it was.

No network: the trader runs on the test helpers' fake quotes, fees and candles."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import unittest
from unittest import mock

from helpers import Feed, PaperTraderCase, make_candles
from test_strategy_lifecycle import ORDER_FIELDS, trend_series

import trading_mode as tm
from signal_engine import SignalEngine

PAPER = {
    "trading": {"mode": "paper"},
    "strategy": {
        "active_id": "STRAT-000",
        "params": {"STRAT-000": {"fast_len": 20}},
        "overlays": [{"id": "OVL-ATR", "params": {}}],
    },
}


class TradeFieldTests(PaperTraderCase):
    def setUp(self):
        super().setUp()
        self.frame = make_candles(trend_series())
        for p in (
            mock.patch.object(self.pt_trader.time, "sleep"),
            mock.patch.object(self.pt_trader, "crypto_symbols", ["BTC"]),
        ):
            p.start()
            self.addCleanup(p.stop)

    def session(self, settings):
        tm.reset_paper_exchange()
        tm._quote_cache.clear()
        self.sessions = getattr(self, "sessions", 0) + 1
        folder = os.path.join(self.tmp.name, f"session{self.sessions}")
        os.makedirs(folder)
        feed = Feed(self.frame)
        engine = SignalEngine(settings, feed.provider, feed.clock)
        feed.set_after_bar(150)
        with mock.patch.object(self.pt_trader, "HUB_DATA_DIR", folder):
            trader = self.pt_trader.CryptoAPITrading(
                settings_source=settings, signal_engine=engine
            )
            trader._order_poll_seconds = 0.0
            for k in range(150, len(self.frame)):
                feed.set_after_bar(k)
                trader.manage_trades()
        orders = list(tm.get_paper_exchange().account.orders.values())
        rows = []
        if os.path.exists(trader.trade_history_path):
            with open(trader.trade_history_path, encoding="utf-8") as f:
                rows = [json.loads(line) for line in f if line.strip()]
        return [
            tuple(str(getattr(o, n, None)) for n in ORDER_FIELDS) for o in orders
        ], rows

    def test_the_fields_change_no_order(self):
        with_fields, rows = self.session(copy.deepcopy(PAPER))
        self.assertEqual(
            [o[1] for o in with_fields], ["OrderSide.BUY", "OrderSide.SELL"]
        )
        with mock.patch.object(
            self.pt_trader.CryptoAPITrading, "_strategy_fields", lambda self: {}
        ):
            without, plain_rows = self.session(copy.deepcopy(PAPER))
        self.assertEqual(with_fields, without)
        self.assertTrue(rows and plain_rows)
        self.assertNotIn("strategy_id", plain_rows[0])

    def test_each_row_names_the_strategy(self):
        _orders, rows = self.session(copy.deepcopy(PAPER))
        self.assertEqual({r["side"] for r in rows}, {"buy", "sell"})
        params = {"fast_len": 20, "slow_len": 50}
        digest = hashlib.sha256(
            json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        for row in rows:
            self.assertEqual(row["strategy_id"], "STRAT-000")
            self.assertEqual(row["strategy_version"], "1.0.0")
            self.assertEqual(row["strategy_params_sha256"], digest)
            self.assertEqual(row["strategy_timeframe"], "1h")
            self.assertEqual(
                row["strategy_overlays"], [{"id": "OVL-ATR", "version": "1.0.0"}]
            )

    def test_the_legacy_engine_and_errors(self):
        trader = self.pt_trader.CryptoAPITrading.__new__(
            self.pt_trader.CryptoAPITrading
        )
        trader._settings_source = {"strategy": {"engine": "legacy_neural"}}
        self.assertEqual(trader._strategy_fields(), {"strategy_id": "legacy_neural"})
        trader._settings_source = {"strategy": {"active_id": "nope"}}
        self.assertEqual(trader._strategy_fields(), {})


if __name__ == "__main__":
    unittest.main()
