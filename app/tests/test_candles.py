"""FDS-121 section 8: candle data layer (cache, validation). Fetching is the exchange
connectors' (tests/test_exchange_market_data.py); here a fake fetcher stands in for
the exchange layer (FDS-MX-001 phase F)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import unittest
from unittest import mock

import pandas as pd

from market_data import candles as cd

HOUR_MS = 3_600_000
T0 = pd.Timestamp("2026-01-01", tz="UTC")
T0_MS = int(T0.timestamp() * 1000)


class FakeKlines:
    """A fake fetcher (``get_candles``' ``fetcher``) over ``bars`` hourly bars starting
    at T0, as one exchange serves them through the exchange layer."""

    def __init__(self, bars=5000, skip=()):
        self.bars = bars
        self.skip = set(skip)  # bar indexes missing from the exchange data (gaps)
        self.calls = []

    @property
    def requests_made(self):
        return len(self.calls)

    def row(self, i):
        o = 100.0 + i
        return [
            T0_MS + i * HOUR_MS,
            f"{o}",
            f"{o + 1}",
            f"{o - 1}",
            f"{o + 0.5}",
            "10.0",
        ]

    def fetch(self, symbol, tf, start_ms, end_ms=None):
        self.calls.append({"startTime": int(start_ms), "endTime": end_ms})
        out = []
        i = max(0, -(-(int(start_ms) - T0_MS) // HOUR_MS))
        while i < self.bars:
            ts = T0_MS + i * HOUR_MS
            if end_ms is not None and ts > end_ms:
                break
            if i not in self.skip:
                out.append(self.row(i))
            i += 1
        return out


def at(hours):
    return T0 + pd.Timedelta(hours=hours)


class GetCandlesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = at(5000)  # everything in FakeKlines(5000) has closed

    def get(self, server, start, end, **kw):
        server.calls_before = len(server.calls)
        f = server
        df = cd.get_candles(
            "BTCUSDT",
            "1h",
            start,
            end,
            cache_dir=self.tmp.name,
            fetcher=f,
            now=kw.pop("now", self.now),
            **kw,
        )
        return df, f

    def test_frame_has_the_strategy_columns_in_utc_ascending_order(self):
        df, _ = self.get(FakeKlines(), at(0), at(48))
        self.assertEqual(list(df.columns), cd.CANDLE_COLUMNS)
        self.assertEqual(len(df), 48)
        self.assertEqual(str(df["open_time"].dt.tz), "UTC")
        self.assertTrue(df["open_time"].is_monotonic_increasing)
        self.assertEqual(df["open_time"].iloc[0], at(0))
        self.assertEqual(df["open_time"].iloc[-1], at(47))  # end is exclusive

    def test_second_call_is_served_from_the_cache(self):
        server = FakeKlines()
        first, _ = self.get(server, at(0), at(100))
        self.assertGreaterEqual(server.requests_made, 1)
        asked = server.requests_made
        second, _ = self.get(server, at(0), at(100))
        self.assertEqual(server.requests_made, asked)
        pd.testing.assert_frame_equal(first, second)
        self.assertTrue(os.path.isfile(cd.cache_path("BTCUSDT", "1h", self.tmp.name)))

    def test_a_cache_that_cannot_be_replaced_still_returns_the_bars(self):
        """Another process reading the cache (on Windows) makes replacing it fail:
        the fetched bars are returned, no temporary file is left, and the next call
        fetches again and caches them."""
        server = FakeKlines()
        path = cd.cache_path("BTCUSDT", "1h", self.tmp.name)
        with mock.patch.object(cd.os, "replace", side_effect=PermissionError("in use")):
            df, _ = self.get(server, at(0), at(48))
        self.assertEqual(len(df), 48)
        self.assertFalse(os.path.exists(path))
        self.assertEqual(
            [n for n in os.listdir(os.path.dirname(path)) if n.endswith(".tmp")], []
        )
        asked = server.requests_made
        again, _ = self.get(server, at(0), at(48))
        self.assertGreater(server.requests_made, asked)
        pd.testing.assert_frame_equal(df, again)
        self.assertTrue(os.path.isfile(path))

    def test_only_missing_ranges_are_fetched(self):
        """...and the last cached bars, in the same request as the new ones."""
        server = FakeKlines()
        self.get(server, at(100), at(200))
        server.calls.clear()
        df, f = self.get(server, at(50), at(250))  # extend both sides
        self.assertEqual(len(df), 200)
        starts = sorted(int(c["startTime"]) for c in server.calls)
        tail = at(200 - cd.REFETCH_TAIL_BARS)
        self.assertEqual(
            starts, [int(at(50).timestamp() * 1000), int(tail.timestamp() * 1000)]
        )
        # nothing in the middle was re-requested
        for c in server.calls:
            self.assertFalse(
                at(100).timestamp() * 1000
                <= int(c["startTime"])
                < tail.timestamp() * 1000
            )

    def test_forming_bar_is_never_returned_or_cached(self):
        server = FakeKlines()
        now = at(10) + pd.Timedelta(minutes=30)  # bar 10 opened but has not closed
        df, _ = self.get(server, at(0), at(20), now=now)
        self.assertEqual(df["open_time"].iloc[-1], at(9))
        cached = cd._read_cache(cd.cache_path("BTCUSDT", "1h", self.tmp.name))
        self.assertEqual(cached["open_time"].iloc[-1], at(9))
        # an hour later bar 10 has closed and is picked up
        df2, _ = self.get(server, at(0), at(20), now=at(11) + pd.Timedelta(minutes=1))
        self.assertEqual(df2["open_time"].iloc[-1], at(10))

    def test_duplicates_in_the_cache_are_an_error_not_silently_fixed(self):
        server = FakeKlines()
        self.get(server, at(0), at(10))
        path = cd.cache_path("BTCUSDT", "1h", self.tmp.name)
        with open(path, "a", encoding="utf-8") as f:
            f.write(open(path, encoding="utf-8").read().splitlines()[1] + "\n")
        with self.assertRaises(cd.CandleDataError):
            self.get(server, at(0), at(10))

    def test_out_of_order_cache_is_an_error(self):
        server = FakeKlines()
        self.get(server, at(0), at(10))
        path = cd.cache_path("BTCUSDT", "1h", self.tmp.name)
        lines = open(path, encoding="utf-8").read().splitlines()
        lines[3], lines[4] = lines[4], lines[3]
        open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        with self.assertRaises(cd.CandleDataError):
            self.get(server, at(0), at(10))

    def test_gaps_are_reported_not_filled(self):
        server = FakeKlines(skip={10, 11, 12, 30})
        df, _ = self.get(server, at(0), at(40))
        report = df.attrs["report"]
        self.assertEqual(len(df), 36)
        self.assertEqual(report.missing_bars, 4)
        self.assertEqual([g[2] for g in report.gaps], [3, 1])
        self.assertEqual(report.gaps[0][0], at(10))
        self.assertEqual(report.gaps[0][1], at(12))
        self.assertNotIn(at(11), list(df["open_time"]))
        self.assertEqual(report.to_dict()["missing_bars"], 4)

    def test_offline_never_touches_the_network(self):
        server = FakeKlines()
        self.get(server, at(0), at(50))
        server.calls.clear()
        df, f = self.get(server, at(0), at(50), offline=True)
        self.assertEqual((len(df), len(server.calls)), (50, 0))
        with self.assertRaises(cd.CandleDataError):
            self.get(server, at(0), at(500), offline=True)
        self.assertEqual(len(server.calls), 0)

    def test_closed_only_false_still_excludes_nothing_extra_from_cache(self):
        df, _ = self.get(FakeKlines(), at(0), at(24), closed_only=False)
        self.assertEqual(len(df), 24)

    def test_unsupported_timeframe_is_rejected(self):
        with self.assertRaises(ValueError):
            cd.get_candles(
                "BTCUSDT",
                "7m",
                at(0),
                at(5),
                cache_dir=self.tmp.name,
                fetcher=FakeKlines(),
                now=self.now,
            )

    def test_missing_bars_without_a_fetcher_are_an_error(self):
        """Only the exchange layer fills the cache (exchange_candles passes a fetcher
        for the exchange it reads); there is no default source."""
        with self.assertRaises(cd.CandleDataError):
            cd.get_candles(
                "BTCUSDT", "1h", at(0), at(5), cache_dir=self.tmp.name, now=self.now
            )

    def test_cache_file_sha256_is_stable(self):
        server = FakeKlines()
        self.get(server, at(0), at(10))
        path = cd.cache_path("BTCUSDT", "1h", self.tmp.name)
        self.assertEqual(cd.file_sha256(path), cd.file_sha256(path))
        self.assertEqual(len(cd.file_sha256(path)), 64)


class RevisingKlines(FakeKlines):
    """``FakeKlines`` whose exchange can change a bar's close after it was served."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.closes = {}  # bar index -> the close the exchange gives for it now

    def row(self, i):
        r = super().row(i)
        if i in self.closes:
            r[4] = f"{self.closes[i]}"
        return r


def starts_in(calls, first, last):
    """The requests that start in ``first`` .. ``last`` (inclusive)."""
    lo, hi = int(first.timestamp() * 1000), int(last.timestamp() * 1000)
    return [c for c in calls if lo <= int(c["startTime"]) <= hi]


class SettledBarsTests(unittest.TestCase):
    """What the exchange changes after the first fetch reaches the cache (A2 N16): bars
    count as closed only a short delay after their close, the last cached bars are
    asked for again with every extension, and gaps inside the cache are asked for
    again, but not on every update."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = cd.cache_path("BTCUSDT", "1h", self.tmp.name)
        # the candle layer's own log (it may not have one yet on unfixed code)
        self.log = logging.getLogger("market_data.candles")

    def get(self, server, start, end, now):
        return cd.get_candles(
            "BTCUSDT",
            "1h",
            start,
            end,
            cache_dir=self.tmp.name,
            fetcher=server,
            now=now,
        )

    def close_of(self, df, hour):
        return float(df.loc[df["open_time"] == at(hour), "close"].iloc[0])

    def test_a_bar_the_exchange_revises_is_replaced_in_the_cache_and_logged_once(self):
        server = RevisingKlines()
        server.closes[9] = 50.0  # provisional: the bar as first served
        self.get(server, at(0), at(10), now=at(10))
        server.closes[9] = 109.25  # the exchange's final bar
        server.calls.clear()
        with mock.patch.object(self.log, "warning") as warn:
            df = self.get(server, at(0), at(11), now=at(11))
            self.get(server, at(0), at(12), now=at(12))
        self.assertEqual(self.close_of(df, 9), 109.25)
        self.assertEqual(self.close_of(cd._read_cache(self.path), 9), 109.25)
        # the last cached bars ride along in the request made for the new bar
        self.assertEqual(len(server.calls), 2)
        revised = [str(c) for c in warn.call_args_list if "revised" in str(c)]
        self.assertEqual(len(revised), 1, revised)
        for part in ("BTCUSDT", "1h", str(at(9)), "50.0", "109.25"):
            self.assertIn(part, revised[0])

    def test_a_bar_inside_the_settling_delay_is_not_closed_yet(self):
        """By the wall clock (no ``now`` given): a bar that closed 5 s ago is neither
        returned nor cached; once the delay has passed it is."""
        server = FakeKlines()
        closed_at = at(10)  # bar 9's close

        def wall(seconds_after_close):
            return (closed_at + pd.Timedelta(seconds=seconds_after_close)).timestamp()

        with mock.patch.object(cd.time, "time", return_value=wall(5)):
            df = self.get(server, at(0), at(10), now=None)
        self.assertEqual(df["open_time"].iloc[-1], at(8))
        self.assertEqual(cd._read_cache(self.path)["open_time"].iloc[-1], at(8))
        with mock.patch.object(cd.time, "time", return_value=wall(cd.SETTLE_SECONDS)):
            df = self.get(server, at(0), at(10), now=None)
        self.assertEqual(df["open_time"].iloc[-1], at(9))

    def test_an_interior_gap_is_refilled_when_the_exchange_has_the_bars(self):
        server = FakeKlines(skip={20, 21})  # missing when the cache was filled
        first = self.get(server, at(0), at(48), now=at(48))
        self.assertEqual(first.attrs["report"].missing_bars, 2)
        server.skip.clear()  # the exchange has them now
        server.calls.clear()
        df = self.get(server, at(0), at(48), now=at(48))
        self.assertEqual(len(df), 48)
        self.assertEqual(df.attrs["report"].missing_bars, 0)
        self.assertIn(at(20), list(cd._read_cache(self.path)["open_time"]))
        self.assertEqual(len(server.calls), 1)  # the gap only, in one request
        self.assertEqual(
            int(server.calls[0]["startTime"]), int(at(20).timestamp() * 1000)
        )

    def test_a_gap_the_exchange_confirms_empty_is_not_asked_for_on_every_update(self):
        """A halt (as Coinbase's XRP halt): the gap is asked for again once; the empty
        answer is recorded, so neither the next updates nor another process ask again.
        """
        halt = set(range(100, 400))
        server = FakeKlines(skip=halt)
        self.get(server, at(0), at(500), now=at(500))
        for hour in range(501, 506):  # the trader's hourly updates
            df = self.get(server, at(0), at(hour), now=at(hour))
        self.assertEqual(len(starts_in(server.calls, at(100), at(399))), 1)
        self.assertEqual(df.attrs["report"].missing_bars, 300)  # still reported
        cd._gaps_asked.clear()  # as in a new process
        self.get(server, at(0), at(506), now=at(506))
        self.assertEqual(len(starts_in(server.calls, at(100), at(399))), 1)
        self.assertTrue(os.path.isfile(cd.gap_record_path(self.path)))

    def test_an_old_empty_gap_record_is_checked_again(self):
        server = FakeKlines(skip={20, 21})
        for _ in range(2):  # filled, then the gap asked for once and recorded empty
            self.get(server, at(0), at(48), now=at(48))
        self.assertEqual(len(starts_in(server.calls, at(20), at(21))), 1)
        record_path = cd.gap_record_path(self.path)
        with open(record_path, encoding="utf-8") as f:
            record = json.load(f)
        old = (
            pd.Timestamp.now(tz="UTC")
            - cd.NO_BARS_IN_GAP_MAX_AGE
            - pd.Timedelta(hours=1)
        )
        for stretch in record["empty"]:
            stretch["checked_at"] = old.isoformat()
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump(record, f)
        cd._gaps_asked.clear()  # a new process
        self.get(server, at(0), at(48), now=at(48))
        self.assertEqual(len(starts_in(server.calls, at(20), at(21))), 2)

    def test_a_gap_refill_that_fails_is_logged_and_the_cached_bars_are_used(self):
        server = FakeKlines(skip={20, 21})
        cached = self.get(server, at(0), at(48), now=at(48))
        original = server.fetch

        def failing(symbol, tf, start_ms, end_ms=None):
            server.calls.append({"startTime": int(start_ms), "endTime": end_ms})
            raise cd.CandleFetchError("exchange down")

        server.fetch = failing
        with mock.patch.object(self.log, "warning") as warn:
            df = self.get(server, at(0), at(48), now=at(48))
            again = self.get(server, at(0), at(48), now=at(48))
        pd.testing.assert_frame_equal(df, cached)
        pd.testing.assert_frame_equal(again, cached)
        # asked once in this process, and the failure logged
        self.assertEqual(len(starts_in(server.calls, at(20), at(21))), 1)
        self.assertIn("exchange down", str(warn.call_args_list))
        server.fetch = original
        self.assertFalse(os.path.exists(cd.gap_record_path(self.path)))


class ValidationTests(unittest.TestCase):
    def frame(self, hours):
        return pd.DataFrame(
            {
                "open_time": [at(h) for h in hours],
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 1.0,
            }
        )

    def test_clean_frame_has_no_gaps(self):
        r = cd.validate_candles(self.frame(range(10)), "1h")
        self.assertEqual((r.rows, r.missing_bars), (10, 0))

    def test_duplicate_timestamps_raise(self):
        with self.assertRaises(cd.CandleDataError):
            cd.validate_candles(self.frame([0, 1, 1, 2]), "1h")

    def test_descending_timestamps_raise(self):
        with self.assertRaises(cd.CandleDataError):
            cd.validate_candles(self.frame([0, 2, 1]), "1h")

    def test_empty_frame_is_valid(self):
        self.assertEqual(cd.validate_candles(self.frame([]), "1h").rows, 0)


class FixtureTests(unittest.TestCase):
    def test_recorded_real_fixture_loads_clean(self):
        path = os.path.join(os.path.dirname(__file__), "fixtures", "BTCUSDT_1h.csv")
        df = cd.load_candles_csv(path, "1h")
        self.assertGreaterEqual(len(df), 1500)
        self.assertEqual(df.attrs["report"].missing_bars, 0)
        self.assertTrue((df["high"] >= df["low"]).all())


if __name__ == "__main__":
    unittest.main()
