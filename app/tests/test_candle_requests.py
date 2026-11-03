"""The candle cache asks each exchange only for bars it does not have:

* a size the exchange does not serve is built from the smaller bars in the cache,
  so they are downloaded once, not once per size built from them;
* a stretch the exchange has no bars in (before a pair was listed) is recorded and
  not asked for again until the record is ``NO_BARS_BEFORE_MAX_AGE`` old.

Everything runs under the isolation guard (app/conftest.py); no network: the
exchange is a fake behind a real ExchangeManager.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from market_data import candles  # noqa: E402
from market_data.resample import build_candles  # noqa: E402
from pt_exchange_abstraction import ExchangeManager, ExchangeType  # noqa: E402

H = 3_600_000
LISTED = datetime(2026, 9, 7, tzinfo=timezone.utc)  # a Monday
LISTED_MS = int(LISTED.timestamp() * 1000)


class OneHourExchange:
    """Serves 1h and 1d bars only (like Coinbase, which has no 2h/4h/8h/12h)."""

    def __init__(self, rows):
        self.rows = rows
        self.asked = []

    def market_symbol(self, symbol):
        return symbol

    def candle_timeframes(self):
        return frozenset({"1h", "1d"})

    def max_history_bars(self, tf):
        return None

    def candles(self, symbol, tf, start_ms, end_ms):
        self.asked.append((tf, start_ms, end_ms))
        assert tf == "1h", f"asked for {tf}: only 1h is fetched here"
        return [r for r in self.rows if start_ms <= r[0] <= end_ms]


def hourly(n):
    return [
        [LISTED_MS + i * H, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 1.0 + i]
        for i in range(n)
    ]


def layer(exchange):
    manager = ExchangeManager()
    manager.exchanges[ExchangeType("coinbase")] = exchange
    manager.primary_exchange = ExchangeType("coinbase")
    return manager


def read(manager, cache_dir, tf, start, hours):
    return candles.exchange_candles(
        "BTC-USD",
        tf,
        start,
        pd.Timestamp(LISTED) + pd.Timedelta(hours=hours),
        cache_dir=str(cache_dir),
        manager=manager,
    )


def rows_of(df):
    return [
        [int(t.timestamp() * 1000), o, h, lo, c, v]
        for t, o, h, lo, c, v in df[
            ["open_time", "open", "high", "low", "close", "volume"]
        ].itertuples(index=False)
    ]


# --- sizes built from the cache --------------------------------------------------------


def test_sizes_built_from_one_hour_bars_download_them_once(tmp_path):
    source = hourly(96)
    exchange = OneHourExchange(source)
    manager = layer(exchange)
    built = {
        tf: read(manager, tmp_path, tf, LISTED, 96) for tf in ("2h", "4h", "8h", "12h")
    }
    assert len(exchange.asked) == 1  # one 1h download for all four sizes
    for tf, df in built.items():
        assert rows_of(df) == build_candles(source, "1h", tf), tf
    # the 1h bars are in the cache, where the next reader finds them
    assert len(read(manager, tmp_path, "1h", LISTED, 96)) == 96
    assert len(exchange.asked) == 1


def test_a_built_size_still_forming_is_not_built(tmp_path):
    exchange = OneHourExchange(hourly(10))  # 10 hours: two whole 4h bars and a part
    df = read(layer(exchange), tmp_path, "4h", LISTED, 12)
    assert len(df) == 2
    assert rows_of(df) == build_candles(hourly(8), "1h", "4h")


# --- where an exchange's bars begin ----------------------------------------------------


def start_record(cache_dir, tf="1h"):
    path = candles.start_record_path(
        candles.cache_path("BTC-USD", tf, str(cache_dir), "coinbase")
    )
    with open(path, encoding="utf-8") as f:
        return path, json.load(f)


def test_a_stretch_before_the_listing_is_asked_for_once(tmp_path):
    exchange = OneHourExchange(hourly(48))
    manager = layer(exchange)
    before = LISTED - timedelta(days=30)
    first = read(manager, tmp_path, "1h", before, 48)
    assert len(first) == 48 and len(exchange.asked) == 1
    _, record = start_record(tmp_path)
    assert pd.Timestamp(record["empty_from"]) == pd.Timestamp(before)
    assert pd.Timestamp(record["first_open"]) == pd.Timestamp(LISTED)

    again = read(manager, tmp_path, "1h", before, 48)
    pd.testing.assert_frame_equal(first, again)
    assert len(exchange.asked) == 1  # nothing asked again


def test_an_earlier_start_asks_only_for_the_stretch_not_yet_asked(tmp_path):
    exchange = OneHourExchange(hourly(48))
    manager = layer(exchange)
    read(manager, tmp_path, "1h", LISTED - timedelta(days=30), 48)
    earlier = LISTED - timedelta(days=90)
    read(manager, tmp_path, "1h", earlier, 48)
    tf, start_ms, end_ms = exchange.asked[-1]
    assert start_ms == int(earlier.timestamp() * 1000)
    assert end_ms == int((LISTED - timedelta(days=30, hours=1)).timestamp() * 1000)
    _, record = start_record(tmp_path)
    assert pd.Timestamp(record["empty_from"]) == pd.Timestamp(earlier)


def test_an_old_record_is_checked_again(tmp_path):
    exchange = OneHourExchange(hourly(48))
    manager = layer(exchange)
    before = LISTED - timedelta(days=30)
    read(manager, tmp_path, "1h", before, 48)
    path, record = start_record(tmp_path)
    old = (
        pd.Timestamp.now(tz="UTC")
        - candles.NO_BARS_BEFORE_MAX_AGE
        - pd.Timedelta(hours=1)
    )
    record["checked_at"] = old.isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f)
    read(manager, tmp_path, "1h", before, 48)
    assert len(exchange.asked) == 2
    assert pd.Timestamp(start_record(tmp_path)[1]["checked_at"]) > old


def test_a_record_about_another_first_bar_is_not_used(tmp_path):
    """The record belongs to the series it was made for: when the cache's first bar is
    not the one recorded (the file was replaced), the stretch is asked for again."""
    exchange = OneHourExchange(hourly(48))
    manager = layer(exchange)
    before = LISTED - timedelta(days=30)
    read(manager, tmp_path, "1h", before, 48)
    path, record = start_record(tmp_path)
    record["first_open"] = (pd.Timestamp(LISTED) + pd.Timedelta(hours=5)).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f)
    read(manager, tmp_path, "1h", before, 48)
    assert len(exchange.asked) == 2


def test_a_failed_download_records_nothing(tmp_path):
    class Failing(OneHourExchange):
        def candles(self, symbol, tf, start_ms, end_ms):
            raise RuntimeError("timeout")

    try:
        read(layer(Failing([])), tmp_path, "1h", LISTED - timedelta(days=30), 48)
    except Exception:
        pass
    path = candles.start_record_path(
        candles.cache_path("BTC-USD", "1h", str(tmp_path), "coinbase")
    )
    assert not os.path.exists(path)


def test_offline_reads_a_pair_listed_later_once_the_record_says_so(tmp_path):
    exchange = OneHourExchange(hourly(48))
    before = LISTED - timedelta(days=30)
    online = read(layer(exchange), tmp_path, "1h", before, 48)
    offline = candles.get_candles(
        "BTC-USD",
        "1h",
        before,
        pd.Timestamp(LISTED) + pd.Timedelta(hours=48),
        cache_dir=str(tmp_path),
        offline=True,
        exchange="coinbase",
    )
    pd.testing.assert_frame_equal(online.reset_index(drop=True), offline)
