"""Each decision names the exchange whose bars decided it (defect N15 in
docs/dev/ptai-rd-001/A2-defect-register.md).

Candles come from the first exchange in Settings that serves them
(``market_data.candles.exchange_candles``, which names it in ``df.attrs``). When the
primary fails, another exchange's bars decide, and before this the decision log did not
say so. Now:

* the decision log line carries ``exchange=<name>`` (``none`` with no bars);
* ``SignalEngine.last_exchanges`` keeps it per coin, and the trader's status file
  (``signals.last_decisions``) shows it;
* with the real ``exchange_candles`` and the primary failing, the second exchange is
  named.

Nothing about trading changes. Synthetic candles; no network."""

from __future__ import annotations

import copy
import os
import sys
import unittest
from unittest import mock

import pandas as pd
from helpers import Feed, PaperTraderCase, make_candles
from test_signal_engine import PAPER, trend_series

import signal_engine as se
from market_data import candles
from market_data.candles import CandleDataError
from signal_engine import SignalEngine

sys.path.insert(0, os.path.dirname(__file__))
from test_exchange_candles import NOW, FakeExchange, hours, layer  # noqa: E402


class Labelled:
    """The feed's bars, labelled as ``exchange_candles`` labels them."""

    def __init__(self, feed: Feed, exchange: str = "coinbase"):
        self.feed, self.exchange = feed, exchange

    def provider(self, symbol, tf, n, now):
        df = self.feed.provider(symbol, tf, n, now)
        df.attrs["exchange"] = self.exchange
        return df


def decision_lines(info):
    return [str(c) for c in info.call_args_list if "Decision BTC" in str(c)]


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.feed = Feed(make_candles(trend_series()))
        self.source = Labelled(self.feed)
        self.engine = SignalEngine(
            copy.deepcopy(PAPER), self.source.provider, self.feed.clock
        )

    def test_the_decision_names_its_exchange(self):
        self.feed.set_after_bar(200)
        with mock.patch.object(se.logger, "info") as info:
            self.engine.decide("BTC")
        self.assertEqual(self.engine.last_exchanges["BTC"], "coinbase")
        (line,) = decision_lines(info)
        self.assertIn(" exchange=coinbase ", line)

    def test_a_fallback_exchange_is_named(self):
        self.feed.set_after_bar(200)
        self.engine.decide("BTC")
        self.source.exchange = "kraken"  # the primary failed: another serves
        self.feed.set_after_bar(201)
        with mock.patch.object(se.logger, "info") as info:
            self.engine.decide("BTC")
        self.assertEqual(self.engine.last_exchanges["BTC"], "kraken")
        self.assertIn(" exchange=kraken ", decision_lines(info)[0])

    def test_without_bars_the_exchange_is_none(self):
        self.feed.fail = CandleDataError("every exchange failed")
        self.feed.set_after_bar(200)
        with mock.patch.object(se.logger, "info") as info:
            decision = self.engine.decide("BTC")
        self.assertEqual(decision.reason, "CANDLES_UNAVAILABLE")
        self.assertIsNone(self.engine.last_exchanges["BTC"])
        self.assertIn(" exchange=none ", decision_lines(info)[0])


class ExchangeLayerTests(unittest.TestCase):
    def test_with_the_primary_failing_the_second_exchange_is_named(self):
        import tempfile

        coinbase = FakeExchange("coinbase", error=RuntimeError("503"))
        kraken = FakeExchange("kraken", pair_format="X{}USD", rows=hours(48))
        manager = layer("coinbase", coinbase, kraken)
        with tempfile.TemporaryDirectory() as cache:

            def provider(pair, tf, n, now):
                return candles.exchange_candles(
                    pair,
                    tf,
                    now - pd.Timedelta(hours=n),
                    now,
                    cache_dir=cache,
                    manager=manager,
                )

            engine = SignalEngine(
                copy.deepcopy(PAPER), provider, lambda: NOW.timestamp()
            )
            engine.decide("BTC")
        self.assertTrue(coinbase.asked)  # the primary was tried first
        self.assertEqual(engine.last_exchanges["BTC"], "kraken")


class TraderStatusTests(PaperTraderCase):
    def test_the_status_file_shows_each_decisions_exchange(self):
        feed = Feed(make_candles(trend_series()))
        settings = copy.deepcopy(PAPER)
        engine = SignalEngine(settings, Labelled(feed).provider, feed.clock)
        feed.set_after_bar(200)
        with mock.patch.object(self.pt_trader.time, "sleep"), mock.patch.object(
            self.pt_trader, "crypto_symbols", ["BTC"]
        ):
            trader = self.pt_trader.CryptoAPITrading(
                settings_source=settings, signal_engine=engine
            )
            trader.manage_trades()
        status = trader._signals_status()
        self.assertEqual(status["last_decisions"]["BTC"]["exchange"], "coinbase")


if __name__ == "__main__":
    unittest.main()
