"""FDS-SIG-004 phase E: the log-only entry assessment (sections 5.8, 5.10, 6.6 and 12).

* Invariant 3: with every new setting Off, and with every one in Log only, the trader
  places byte-identical orders on a replayed session; Off computes and writes nothing.
* Log only records one assessment per entry the strategy wanted, after the order: the
  predictive part and the shrink unavailable without a registered model, the spread and
  participation figures, what each part would have done, and no outcome.
* The settings: Off by default; only Off and Log only can be saved; a saved value this
  version does not offer reads as Off.

No network: the trader runs on the test helpers' fake quotes, fees and candles."""

from __future__ import annotations

import copy
import json
import os
import unittest
from unittest import mock

import numpy as np
import pandas as pd
from helpers import Feed, PaperTraderCase, make_candles

import trading_mode as tm
from signal_engine import SignalEngine
from signal_fusion import assessment as asm
from signal_fusion import live
from signal_fusion import settings as fs

PAPER = {
    "trading": {"mode": "paper"},
    "strategy": {"active_id": "STRAT-000"},
}
LOG_ONLY = {
    "entry_assessment": "log_only",
    "volatility_shrink": "log_only",
    "participation_cap": "log_only",
    "spread_cap": "log_only",
}
ORDER_FIELDS = (
    "symbol",
    "side",
    "order_type",
    "quantity",
    "price",
    "status",
    "filled_quantity",
    "average_fill_price",
    "commission",
    "commission_rate",
)
OUTCOME_WORDS = ("profit", "pnl", "net", "fill_price", "result", "outcome")


def trend_series():
    down = np.linspace(200, 150, 150)
    up = np.linspace(150, 240, 40)
    fall = np.linspace(240, 110, 70)
    return np.concatenate([down, up, fall])


def fake_candles(coin, at_s):
    """21 days of hourly bars before ``at_s``: volume 10 at a typical price of 100."""
    end = (int(at_s) // 3600) * 3600
    t = list(range(end - 22 * 86400, end, 3600))
    n = len(t)
    o = np.full(n, 100.0)
    return "fake", t, (o, o * 1.001, o * 0.999, o, np.full(n, 10.0))


class LogOnlyTraderTests(PaperTraderCase):
    def setUp(self):
        super().setUp()
        self.frame = make_candles(trend_series())
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        coins = mock.patch.object(self.pt_trader, "crypto_symbols", ["BTC"])
        coins.start()
        self.addCleanup(coins.stop)
        self.records = os.path.join(self.tmp.name, "assessments.jsonl")
        for p in (
            mock.patch.object(live, "records_path", lambda: self.records),
            mock.patch.object(live, "hourly_candles", fake_candles),
        ):
            p.start()
            self.addCleanup(p.stop)

    def session(self, settings):
        """The scripted session's orders, as their recorded fields, from a fresh paper
        account in a data folder of its own."""
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
        return [
            tuple(str(getattr(o, name, None)) for name in ORDER_FIELDS) for o in orders
        ]

    def read_records(self):
        if not os.path.exists(self.records):
            return []
        with open(self.records, encoding="utf-8") as f:
            return [json.loads(line) for line in f]

    def test_off_and_log_only_place_byte_identical_orders(self):
        off = self.session(copy.deepcopy(PAPER))
        self.assertEqual([o[1] for o in off], ["OrderSide.BUY", "OrderSide.SELL"])
        self.assertEqual(self.read_records(), [])  # Off: nothing computed or written
        self.assertEqual(self.session(copy.deepcopy(PAPER)), off)  # the control
        logging = copy.deepcopy(PAPER)
        logging["signal_fusion"] = dict(LOG_ONLY)
        on_log = self.session(logging)
        self.assertEqual(off, on_log)
        records = self.read_records()
        self.assertEqual(len(records), 1)  # one entry wanted: one assessment
        r = records[0]
        self.assertEqual(r["effect"], "allow")
        self.assertEqual(r["coin"], "BTC")
        self.assertEqual(r["source"], "strategy")
        parts = {p["name"]: p for p in r["parts"]}
        self.assertFalse(parts["entry_assessment"]["available"])
        self.assertIn("no registered model", parts["entry_assessment"]["reason"])
        self.assertEqual(parts["volatility_shrink"]["would"], "skip")
        self.assertTrue(parts["spread_cap"]["available"])
        self.assertTrue(parts["participation_cap"]["available"])
        self.assertAlmostEqual(r["hourly_median_usd"], 1000.0)
        for p in r["parts"]:
            self.assertEqual(p["mode"], "log_only")
        flat = json.dumps(r).lower()
        for word in OUTCOME_WORDS:
            self.assertNotIn(f'"{word}', flat)

    def test_a_failure_in_the_log_never_reaches_the_trader(self):
        logging = copy.deepcopy(PAPER)
        logging["signal_fusion"] = dict(LOG_ONLY)

        def broken(*_a, **_k):
            raise RuntimeError("the record could not be made")

        with mock.patch.object(live, "evaluate", broken):
            orders = self.session(logging)
        self.assertEqual(len(orders), 2)
        records = self.read_records()
        self.assertEqual(len(records), 1)
        self.assertIn("could not be made", records[0]["error"])
        self.assertEqual(records[0]["effect"], "allow")


class SettingsTests(unittest.TestCase):
    def test_every_setting_is_off_by_default(self):
        s = fs.read({})
        self.assertTrue(s.all_off())
        self.assertEqual(fs.normalise(None), {**fs.DEFAULTS, **fs.NUMBERS})

    def test_a_value_this_version_does_not_offer_reads_as_off(self):
        raw = {
            "signal_fusion": {
                "entry_assessment": "veto",
                "volatility_shrink": "on",
                "participation_cap": "on",
                "spread_cap": "log_only",
                "participation_pi": 7,
            }
        }
        s = fs.read(raw)
        self.assertEqual(
            (
                s.entry_assessment,
                s.volatility_shrink,
                s.participation_cap,
                s.spread_cap,
            ),
            ("off", "off", "off", "log_only"),
        )
        self.assertEqual(s.participation_pi, 0.01)  # out of range: the default

    def test_only_off_and_log_only_can_be_saved(self):
        class Manager:
            def __init__(self):
                self.saved = {}

            def get(self, name):
                return self.saved.get(name)

            def set_section(self, name, values):
                self.saved[name] = values
                return True

        m = Manager()
        self.assertTrue(fs.save({"entry_assessment": "log_only"}, m))
        self.assertEqual(m.saved["signal_fusion"]["entry_assessment"], "log_only")
        self.assertEqual(m.saved["signal_fusion"]["spread_cap"], "off")
        for key, value in (("entry_assessment", "veto"), ("spread_cap", "on")):
            self.assertFalse(fs.save({key: value}, m))
        self.assertEqual(m.saved["signal_fusion"]["spread_cap"], "off")


class RecordTests(unittest.TestCase):
    def test_a_stale_quote_and_missing_candles_are_recorded_and_change_nothing(self):
        s = asm.Settings(*(["log_only"] * 4))
        c = live.capture(
            s, "ETH", "ETH-USD", "thinker", 100.0, 10.3, 100.1, 99.9, 1.0, now=1000.0
        )

        def no_candles(coin, at_s):
            raise ConnectionError("no candles")

        r = live.evaluate(c, candles=no_candles)
        self.assertEqual(r["effect"], "allow")
        parts = {p["name"]: p for p in r["parts"]}
        self.assertEqual(parts["spread_cap"]["would"], "skip")  # 999 s old
        self.assertIn("too old", parts["spread_cap"]["reason"])
        self.assertEqual(parts["participation_cap"]["would"], "skip")
        self.assertIn("no candles", parts["participation_cap"]["reason"])

    def test_the_participation_figures_and_their_bound(self):
        s = asm.Settings(*(["log_only"] * 4))
        now = pd.Timestamp("2026-11-07 12:00", tz="UTC").timestamp()
        c = live.capture(
            s, "ETH", "ETH-USD", "strategy", 5.0, None, 100.1, 99.9, now - 2, now=now
        )
        r = live.evaluate(c, candles=fake_candles)
        self.assertAlmostEqual(r["hourly_median_usd"], 1000.0)
        self.assertAlmostEqual(r["participation"], 0.005)
        self.assertGreaterEqual(r["participation_bound"], r["participation"])
        parts = {p["name"]: p for p in r["parts"]}
        self.assertEqual(parts["participation_cap"]["would"], "allow")
        self.assertEqual(parts["spread_cap"]["would"], "allow")
        self.assertEqual(r["venues"]["candles"], "fake")
