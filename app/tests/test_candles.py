"""FDS-121 section 8: candle data layer (pagination, backoff, cache, validation)."""

from __future__ import annotations

import http.client
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.parse

import pandas as pd

from market_data import candles as cd

HOUR_MS = 3_600_000
T0 = pd.Timestamp("2026-01-01", tz="UTC")
T0_MS = int(T0.timestamp() * 1000)


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, retry_after=None):
    headers = http.client.HTTPMessage()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("http://x", code, "err", headers, None)


class FakeKlines:
    """A fake Binance klines endpoint over ``bars`` hourly bars starting at T0.
    ``script`` is a list of exceptions to raise on the first requests."""

    def __init__(self, bars=5000, script=None, skip=()):
        self.bars = bars
        self.script = list(script or [])
        self.skip = set(skip)  # bar indexes missing from the exchange data (gaps)
        self.calls = []

    def row(self, i):
        o = 100.0 + i
        return [
            T0_MS + i * HOUR_MS,
            f"{o}",
            f"{o + 1}",
            f"{o - 1}",
            f"{o + 0.5}",
            "10.0",
            T0_MS + (i + 1) * HOUR_MS - 1,
            "0",
            0,
            "0",
            "0",
            "0",
        ]

    def __call__(self, url, timeout=None):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        self.calls.append(q)
        if self.script:
            exc = self.script.pop(0)
            if exc is not None:
                raise exc
        start = int(q["startTime"])
        end = int(q["endTime"]) if "endTime" in q else None
        limit = int(q["limit"])
        out = []
        i = max(0, -(-(start - T0_MS) // HOUR_MS))
        while i < self.bars and len(out) < limit:
            ts = T0_MS + i * HOUR_MS
            if end is not None and ts > end:
                break
            if i not in self.skip:
                out.append(self.row(i))
            i += 1
        return FakeResponse(out)


def fetcher_for(server, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return cd.BinanceKlines(opener=server, sleep=sleeps.append, max_retries=3), sleeps


def at(hours):
    return T0 + pd.Timedelta(hours=hours)


class FetchTests(unittest.TestCase):
    def test_paginates_at_1000_rows_per_request(self):
        server = FakeKlines(bars=2500)
        f, _ = fetcher_for(server)
        rows = f.fetch("BTCUSDT", "1h", T0_MS, T0_MS + 2499 * HOUR_MS)
        self.assertEqual(len(rows), 2500)
        self.assertEqual(f.requests_made, 3)
        self.assertEqual([c["limit"] for c in server.calls], ["1000"] * 3)
        times = [int(r[0]) for r in rows]
        self.assertEqual(times, sorted(set(times)))  # no duplicate across pages

    def test_only_the_public_klines_endpoint_is_used(self):
        server = FakeKlines(bars=10)
        f, _ = fetcher_for(server)
        f.fetch("BTCUSDT", "1h", T0_MS, None)
        self.assertEqual(server.calls[0]["symbol"], "BTCUSDT")
        self.assertEqual(server.calls[0]["interval"], "1h")

    def test_rate_limit_honours_retry_after(self):
        server = FakeKlines(bars=5, script=[http_error(429, retry_after=7)])
        f, sleeps = fetcher_for(server)
        rows = f.fetch("BTCUSDT", "1h", T0_MS, T0_MS + 4 * HOUR_MS)
        self.assertEqual(len(rows), 5)
        self.assertEqual(sleeps, [7.0])

    def test_server_errors_back_off_exponentially_then_succeed(self):
        server = FakeKlines(bars=5, script=[http_error(503), OSError("reset"), None])
        f, sleeps = fetcher_for(server)
        self.assertEqual(len(f.fetch("BTCUSDT", "1h", T0_MS, T0_MS + 4 * HOUR_MS)), 5)
        self.assertEqual(sleeps, [1.0, 2.0])

    def test_gives_up_after_max_retries_with_a_clear_error(self):
        server = FakeKlines(script=[http_error(500)] * 10)
        f, sleeps = fetcher_for(server)
        with self.assertRaises(cd.CandleFetchError):
            f.fetch("BTCUSDT", "1h", T0_MS, None)
        self.assertEqual(f.requests_made, 4)  # first try + 3 retries

    def test_client_errors_are_not_retried(self):
        server = FakeKlines(script=[http_error(400)])
        f, sleeps = fetcher_for(server)
        with self.assertRaises(cd.CandleFetchError):
            f.fetch("BTCUSDT", "1h", T0_MS, None)
        self.assertEqual((f.requests_made, sleeps), (1, []))


class GetCandlesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = at(5000)  # everything in FakeKlines(5000) has closed

    def get(self, server, start, end, **kw):
        f, _ = fetcher_for(server)
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
        first, f1 = self.get(server, at(0), at(100))
        self.assertGreaterEqual(f1.requests_made, 1)
        second, f2 = self.get(server, at(0), at(100))
        self.assertEqual(f2.requests_made, 0)
        pd.testing.assert_frame_equal(first, second)
        self.assertTrue(os.path.isfile(cd.cache_path("BTCUSDT", "1h", self.tmp.name)))

    def test_only_missing_ranges_are_fetched(self):
        server = FakeKlines()
        self.get(server, at(100), at(200))
        server.calls.clear()
        df, f = self.get(server, at(50), at(250))  # extend both sides
        self.assertEqual(len(df), 200)
        starts = sorted(int(c["startTime"]) for c in server.calls)
        self.assertEqual(
            starts, [int(at(50).timestamp() * 1000), int(at(200).timestamp() * 1000)]
        )
        # nothing in the middle was re-requested
        for c in server.calls:
            self.assertFalse(
                at(100).timestamp() * 1000
                <= int(c["startTime"])
                < at(200).timestamp() * 1000
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
                fetcher=cd.BinanceKlines(opener=FakeKlines()),
                now=self.now,
            )

    def test_cache_file_sha256_is_stable(self):
        server = FakeKlines()
        self.get(server, at(0), at(10))
        path = cd.cache_path("BTCUSDT", "1h", self.tmp.name)
        self.assertEqual(cd.file_sha256(path), cd.file_sha256(path))
        self.assertEqual(len(cd.file_sha256(path)), 64)


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
