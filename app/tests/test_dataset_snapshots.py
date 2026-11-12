"""PTAI-RD-001 work package 2.2: dataset snapshots and the one bar hash.

* The same bars give the same bar hash and the same snapshot id, whatever frame holds
  them (row order, dtypes, extra columns, column order, index, time zone) and in
  whatever order the coins are given.
* A revised bar gives a new bar hash and a new id, and ``verify`` names the coin.
* Gaps are recorded as exact runs of missing bars on the timeframe's step.
* Snapshots are written once; a different file under an id is refused and kept.
* The earlier bar hashes are unchanged (pinned), and three of them are the new hash.

Synthetic frames and temporary folders only: no network, no user folders."""

from __future__ import annotations

import decimal
import hashlib
import json
import os

import numpy as np
import pandas as pd
import pytest

from market_data import snapshots as sn
from market_data.timeframes import candle_timeframe_seconds

START = pd.Timestamp("2024-03-01", tz="UTC")
H = pd.Timedelta(hours=1)


def bars(n, seed=0, start=START, step=H, exchange="coinbase", pair="BTC-USD"):
    """``n`` bars from ``start``, as ``exchange_candles`` returns them."""
    rng = np.random.default_rng(seed)
    close = np.round(100 + np.cumsum(rng.normal(0, 1, n)), 2)
    open_ = np.r_[100.0, close[:-1]]
    df = pd.DataFrame(
        {
            "open_time": [start + k * step for k in range(n)],
            "open": open_,
            "high": np.maximum(open_, close) + 0.5,
            "low": np.minimum(open_, close) - 0.5,
            "close": close,
            "volume": rng.integers(1, 1000, n).astype(float),
        }
    )
    df.attrs.update(exchange=exchange, pair=pair)
    return df


def requested(n=48, step=H):
    return START, START + n * step


def snap(frames, tf="1h", n=48, **kw):
    start, end = requested(n, pd.Timedelta(seconds=candle_timeframe_seconds(tf)))
    return sn.build(frames, tf, start, end, **kw)


def the_same_bars_held_otherwise(df):
    """The same bars in another frame: rows shuffled, columns reversed, an extra
    column, a new index, integer volume, object prices, Decimal lows, millisecond
    naive open times."""
    other = df.sample(frac=1.0, random_state=7)
    other = other[list(reversed(other.columns))].copy()
    other["trades"] = np.arange(len(other))
    other.index = [f"r{k}" for k in range(len(other))]
    other["volume"] = other["volume"].astype(np.int64)
    other["close"] = other["close"].astype(object)
    other["low"] = [decimal.Decimal(repr(v)) for v in other["low"]]
    other["open_time"] = (
        pd.to_datetime(other["open_time"], utc=True)
        .dt.tz_localize(None)
        .astype("datetime64[ms]")
    )
    other.attrs.update(df.attrs)
    return other


# -- the bar hash ---------------------------------------------------------------------


def test_the_same_bars_give_the_same_bar_hash_however_the_frame_holds_them():
    df = bars(48, seed=1)
    other = the_same_bars_held_otherwise(df)
    assert other["volume"].dtype == np.int64 and other["close"].dtype == object
    assert list(other.columns) != list(df.columns)
    assert sn.bar_hash(other) == sn.bar_hash(df)
    london = df.copy()
    london["open_time"] = london["open_time"].dt.tz_convert("Europe/London")
    assert sn.bar_hash(london) == sn.bar_hash(df)
    text = df.copy()
    text["open_time"] = [t.isoformat() for t in df["open_time"]]
    assert sn.bar_hash(text) == sn.bar_hash(df)
    negative_zero = df.copy()
    negative_zero.loc[3, "volume"] = -0.0
    zero = df.copy()
    zero.loc[3, "volume"] = 0.0
    assert sn.bar_hash(negative_zero) == sn.bar_hash(zero)


def test_a_revised_bar_gives_another_bar_hash():
    df = bars(48, seed=1)
    revised = df.copy()
    revised.loc[20, "close"] = revised.loc[20, "close"] + 0.01
    assert sn.bar_hash(revised) != sn.bar_hash(df)
    later = df.copy()
    later.loc[47, "open_time"] = later.loc[47, "open_time"] + H
    assert sn.bar_hash(later) != sn.bar_hash(df)


def test_the_canonical_encoding_is_the_candle_csv_form():
    df = bars(2, seed=3)
    text = sn.canonical_bar_bytes(df).decode("ascii")
    lines = text.split("\n")
    assert lines[0] == "open_time_ms,open,high,low,close,volume"
    assert text.endswith("\n") and lines[-1] == "" and len(lines) == 4
    first = lines[1].split(",")
    assert first[0] == str(int(START.timestamp()) * 1000)
    assert first[1:] == [repr(float(df.loc[0, c])) for c in sn.VALUES]
    empty = df.iloc[0:0]
    assert sn.canonical_bar_bytes(empty) == b"open_time_ms,open,high,low,close,volume\n"


@pytest.mark.parametrize(
    "spoil, words",
    [
        (lambda df: df.drop(columns=["volume"]), "no volume column"),
        (
            lambda df: df.assign(open_time=df["open_time"].iloc[[0, 0, 2]].tolist()),
            "two bars",
        ),
        (lambda df: df.assign(close=[1.0, np.nan, 2.0]), "not finite"),
        (lambda df: df.assign(high=[1.0, np.inf, 2.0]), "not finite"),
        (lambda df: df.assign(open_time=[1, 2, 3]), "not times"),
        (
            lambda df: df.assign(open_time=[None, *df["open_time"].iloc[1:]]),
            "no open time",
        ),
        (lambda df: df.assign(low=["a", "b", "c"]), "not numbers"),
    ],
)
def test_bars_that_cannot_be_hashed_are_refused(spoil, words):
    with pytest.raises(sn.BarDataError, match=words):
        sn.bar_hash(spoil(bars(3)))


# -- the snapshot ---------------------------------------------------------------------


def test_the_same_bars_give_the_same_snapshot_id_in_any_frame_and_coin_order():
    btc, eth = bars(48, seed=1), bars(48, seed=2, pair="ETH-USD")
    one = snap({"BTC": btc, "ETH": eth})
    two = snap(
        {
            "eth": the_same_bars_held_otherwise(eth),
            "btc": the_same_bars_held_otherwise(btc),
        }
    )
    assert one.id == two.id and one.text == two.text
    assert one.coins == ("BTC", "ETH")
    assert one.manifest["coins"] == ["BTC", "ETH"]
    assert len(one.id) == 64 and int(one.id, 16) >= 0
    assert one.id == hashlib.sha256(one.text.encode("utf-8")).hexdigest()


def test_a_revised_bar_gives_a_new_snapshot_id():
    btc, eth = bars(48, seed=1), bars(48, seed=2, pair="ETH-USD")
    before = snap({"BTC": btc, "ETH": eth})
    revised = eth.copy()
    revised.loc[30, "close"] = revised.loc[30, "close"] * 1.001
    after = snap({"BTC": btc, "ETH": revised})
    assert after.id != before.id
    assert after.series("BTC") == before.series("BTC")
    assert after.series("ETH")["bar_hash"] != before.series("ETH")["bar_hash"]
    assert after.series("ETH")["bar_hash"] == sn.bar_hash(revised)


def test_another_exchange_or_range_gives_another_id():
    btc = bars(48, seed=1)
    base = snap({"BTC": btc})
    elsewhere = btc.copy()
    elsewhere.attrs.update(exchange="kraken")
    assert snap({"BTC": elsewhere}).id != base.id
    assert snap({"BTC": btc}, n=49).id != base.id


def test_the_manifest_records_the_series_and_the_ranges():
    btc = bars(48, seed=1)
    late = bars(10, seed=2, start=START + 30 * H, exchange="kraken", pair="XETHZUSD")
    s = sn.build({"BTC": btc, "ETH": late}, "1h", START, START + 48 * H)
    m = s.manifest
    assert m["kind"] == "dataset_snapshot" and m["version"] == 1
    assert m["bar_encoding"] == "candle-csv-v1"
    assert m["timeframe"] == "1h" and m["step_s"] == 3600
    assert m["requested"] == {
        "start": "2024-03-01T00:00:00Z",
        "end": "2024-03-03T00:00:00Z",
    }
    assert m["actual"] == {
        "first_open": "2024-03-01T00:00:00Z",
        "last_open": "2024-03-02T23:00:00Z",
        "last_close": "2024-03-03T00:00:00Z",
    }
    eth = s.series("ETH")
    assert eth["exchange"] == "kraken" and eth["pair"] == "XETHZUSD"
    assert eth["bars"] == 10 and eth["bar_hash"] == sn.bar_hash(late)
    assert eth["first_open"] == "2024-03-02T06:00:00Z"
    assert eth["last_open"] == "2024-03-02T15:00:00Z"
    # listed 30 bars after the requested start; 8 bars short of its end
    assert eth["listing"] == {
        "missing_at_start": 30,
        "missing_at_end": 8,
        "market_status": None,
    }
    assert s.series("BTC")["listing"]["missing_at_start"] == 0
    assert s.series("BTC")["listing"]["missing_at_end"] == 0


def test_gaps_are_recorded_as_exact_runs_of_missing_bars():
    df = bars(48, seed=1)
    holed = df.drop(index=[5, 6, 7, 20]).reset_index(drop=True)
    holed.attrs.update(df.attrs)
    s = snap({"BTC": holed})
    entry = s.series("BTC")
    assert entry["gaps"] == [
        {
            "from": "2024-03-01T05:00:00Z",
            "to": "2024-03-01T07:00:00Z",
            "missing_bars": 3,
        },
        {
            "from": "2024-03-01T20:00:00Z",
            "to": "2024-03-01T20:00:00Z",
            "missing_bars": 1,
        },
    ]
    assert entry["missing_bars"] == 4 and entry["bars"] == 44
    assert snap({"BTC": df}).series("BTC")["gaps"] == []


def test_gaps_follow_the_timeframe_step():
    day = pd.Timedelta(days=1)
    df = bars(30, seed=1, step=day)
    holed = df.drop(index=list(range(10, 17))).reset_index(drop=True)
    holed.attrs.update(df.attrs)
    entry = snap({"BTC": holed}, tf="1d", n=30).series("BTC")
    assert entry["gaps"] == [
        {
            "from": "2024-03-11T00:00:00Z",
            "to": "2024-03-17T00:00:00Z",
            "missing_bars": 7,
        }
    ]


def test_market_status_is_listing_evidence_without_its_check_time():
    btc = bars(48, seed=1)
    status = {
        "pair": "BTC-USD",
        "trading": True,
        "reason": "",
        "exchange": "coinbase",
        "checked_at": 1,
    }
    a = snap({"BTC": btc}, market_status={"BTC": status})
    b = snap({"BTC": btc}, market_status={"btc": {**status, "checked_at": 2}})
    assert a.id == b.id
    assert a.series("BTC")["listing"]["market_status"] == {
        "pair": "BTC-USD",
        "trading": True,
        "reason": "",
        "exchange": "coinbase",
    }
    stopped = snap(
        {"BTC": btc},
        market_status={"BTC": {**status, "trading": False, "reason": "delisted"}},
    )
    assert stopped.id != a.id
    assert snap({"BTC": btc}).id != a.id
    with pytest.raises(ValueError, match="coins not given"):
        snap({"BTC": btc}, market_status={"ETH": status})


def test_a_snapshot_refuses_what_it_cannot_record():
    btc = bars(48, seed=1)
    with pytest.raises(sn.BarDataError, match="BTC: .*outside the requested range"):
        snap({"BTC": btc}, n=40)
    off = btc.copy()
    off.loc[10:, "open_time"] = off.loc[10:, "open_time"] + pd.Timedelta(minutes=30)
    off = off.iloc[:-1]
    with pytest.raises(sn.BarDataError, match="not a whole number of bars apart"):
        snap({"BTC": off})
    nameless = btc.copy()
    nameless.attrs.clear()
    with pytest.raises(sn.BarDataError, match="does not name its exchange"):
        snap({"BTC": nameless})
    with pytest.raises(ValueError, match="given twice"):
        snap({"BTC": btc, "btc": btc})
    with pytest.raises(ValueError, match="no coins"):
        snap({})
    with pytest.raises(ValueError, match="empty"):
        sn.build({"BTC": btc}, "1h", START, START)
    with pytest.raises(ValueError, match="Unsupported"):
        sn.build({"BTC": btc}, "7h", START, START + 48 * H)


def test_a_coin_without_bars_is_recorded_as_such():
    empty = bars(5).iloc[0:0]
    empty.attrs.update(exchange="coinbase", pair="NEW-USD")
    s = snap({"BTC": bars(48, seed=1), "NEW": empty})
    entry = s.series("NEW")
    assert entry["bars"] == 0 and entry["first_open"] is None
    assert entry["listing"]["missing_at_start"] is None
    assert (
        entry["bar_hash"]
        == hashlib.sha256(b"open_time_ms,open,high,low,close,volume\n").hexdigest()
    )


def test_a_manifest_must_be_canonical():
    s = snap({"BTC": bars(48, seed=1)})
    pretty = json.dumps(s.manifest, indent=2, sort_keys=True)
    with pytest.raises(sn.SnapshotError, match="canonical"):
        sn.DatasetSnapshot(pretty)
    with pytest.raises(sn.SnapshotError, match="not a snapshot"):
        sn.DatasetSnapshot(sn.canonical({"kind": "other"}))
    copy = s.manifest
    copy["coins"].append("XRP")
    assert s.coins == ("BTC",)  # the manifest given out is a copy


# -- storage --------------------------------------------------------------------------


def test_a_snapshot_is_saved_once_under_its_id(tmp_path):
    root = str(tmp_path / "research_engine")
    s = snap({"BTC": bars(48, seed=1)})
    path = sn.save(s, root)
    assert path == os.path.join(root, "datasets", f"{s.id}.json")
    with open(path, "rb") as f:
        data = f.read()
    assert hashlib.sha256(data).hexdigest() == s.id  # the file's hash is its id
    before = os.stat(path).st_mtime_ns
    assert sn.save(s, root) == path  # the same snapshot again: nothing changes
    assert os.stat(path).st_mtime_ns == before
    assert sn.load(s.id, root) == s
    assert [n for n in os.listdir(os.path.dirname(path))] == [f"{s.id}.json"]


def test_another_manifest_under_an_id_is_refused_and_kept(tmp_path):
    root = str(tmp_path)
    s = snap({"BTC": bars(48, seed=1)})
    path = sn.save(s, root)
    other = snap({"BTC": bars(48, seed=2)})
    with open(path, "wb") as f:
        f.write(other.text.encode("utf-8"))
    with pytest.raises(sn.SnapshotError, match="holds another manifest"):
        sn.save(s, root)
    with open(path, "rb") as f:
        assert f.read() == other.text.encode("utf-8")  # kept, not replaced
    with pytest.raises(sn.SnapshotError, match="has changed"):
        sn.load(s.id, root)


def test_storage_needs_an_absolute_root_and_a_real_id(tmp_path):
    s = snap({"BTC": bars(48, seed=1)})
    with pytest.raises(ValueError, match="absolute"):
        sn.save(s, "relative/folder")
    with pytest.raises(ValueError, match="not a snapshot id"):
        sn.load("../../" + "0" * 58, str(tmp_path))
    with pytest.raises(sn.SnapshotError, match="cannot be read"):
        sn.load("0" * 64, str(tmp_path))


# -- verification ---------------------------------------------------------------------


def test_verify_finds_nothing_when_the_bars_are_the_same():
    btc, eth = bars(48, seed=1), bars(48, seed=2, pair="ETH-USD")
    s = snap({"BTC": btc, "ETH": eth})
    result = sn.verify(s, {"ETH": the_same_bars_held_otherwise(eth), "BTC": btc})
    assert result.ok and result.differences == {}
    assert result.now is not None and result.now.id == s.id


def test_verify_names_the_coin_whose_bar_was_revised():
    btc, eth = bars(48, seed=1), bars(48, seed=2, pair="ETH-USD")
    s = snap({"BTC": btc, "ETH": eth})
    revised = eth.copy()
    revised.loc[30, "high"] = revised.loc[30, "high"] + 1.0
    result = sn.verify(s, {"BTC": btc, "ETH": revised})
    assert not result.ok
    assert list(result.differences) == ["ETH"]
    (what,) = result.differences["ETH"]
    assert what.startswith("bar hash: ") and "a revised bar" in what
    assert result.now is not None and result.now.id != s.id
    assert result.now.id == snap({"BTC": btc, "ETH": revised}).id


def test_verify_reports_each_kind_of_change_per_coin():
    btc, eth, sol = bars(48, seed=1), bars(48, seed=2), bars(48, seed=3)
    s = snap({"BTC": btc, "ETH": eth, "SOL": sol})
    shorter = btc.iloc[:-1].copy()
    shorter.attrs.update(btc.attrs)
    moved = eth.copy()
    moved.attrs.update(exchange="kraken")
    result = sn.verify(s, {"BTC": shorter, "ETH": moved, "XRP": bars(48)})
    d = result.differences
    assert sorted(d) == ["BTC", "ETH", "SOL", "XRP"]
    assert "bars: 48 -> 47" in d["BTC"]
    assert "last bar: 2024-03-02T23:00:00Z -> 2024-03-02T22:00:00Z" in d["BTC"]
    assert not any("revised" in line for line in d["BTC"])
    assert d["ETH"] == ("exchange: coinbase -> kraken",)
    assert d["SOL"] == ("no bars given",)
    assert d["XRP"] == ("not in the snapshot",)
    assert result.now is None


def test_verify_reads_each_coin_from_its_recorded_exchange():
    btc = bars(48, seed=1)
    eth = bars(48, seed=2, exchange="kraken", pair="XETHZUSD")
    s = snap({"BTC": btc, "ETH": eth})
    asked = []

    def loader(coin, timeframe, start, end, exchange):
        asked.append((coin, timeframe, start, end, exchange))
        if coin == "ETH":
            raise OSError("offline")
        return btc

    result = sn.verify(s, loader=loader)
    assert asked == [
        ("BTC", "1h", START, START + 48 * H, "coinbase"),
        ("ETH", "1h", START, START + 48 * H, "kraken"),
    ]
    assert result.differences == {"ETH": ("could not be read (OSError: offline)",)}
    with pytest.raises(ValueError, match="frames or a loader"):
        sn.verify(s)


def test_the_exchange_loader_asks_the_recorded_exchange_only(monkeypatch):
    from market_data import candles

    seen = {}

    def fake(symbol, tf, start, end, **kw):
        seen.update(symbol=symbol, tf=tf, start=start, end=end, **kw)
        return bars(48, seed=1)

    monkeypatch.setattr(candles, "exchange_candles", fake)
    load = sn.exchange_loader(cache_dir="cache-folder", offline=True, manager="m")
    s = snap({"BTC": bars(48, seed=1)})
    assert sn.verify(s, loader=load).ok
    assert seen["exchanges"] == ["coinbase"] and seen["offline"] is True
    assert seen["cache_dir"] == "cache-folder" and seen["manager"] == "m"
    assert (seen["symbol"], seen["tf"]) == ("BTC", "1h")


# -- the earlier hashes ---------------------------------------------------------------

# Hand-written bars: awkward floats (0.1, 1e-07, 17 significant digits, 2.5e16).
PINNED = [
    (0, 100.0, 101.5, 99.25, 100.75, 12.0),
    (1, 100.75, 102.0, 100.5, 101.1, 0.1),
    (2, 101.1, 101.2, 100.9, 101.0, 1e-07),
    (3, 101.0, 12345.678901234567, 100.0, 105.3, 2.5e16),
    (4, 105.3, 106.0, 104.0, 104.5, 7.0),
    (5, 104.5, 104.9, 103.3, 103.3, 3.0),
]
# candle-CSV encoding: bar_hash, pt_pattern_trainer.candle_sha256,
# model_lab.series.bars_sha256 and signal_audit.evidence.bars_sha256
CANDLE_CSV_SHA256 = "516f99311fc46ad1c699c3549fc31b01732a1f2c15cff8513f9adca7fdfad9a3"
# strategy_lab.e1.frame_sha256 (to_csv, 12 significant digits)
E1_FRAME_SHA256 = "ce3652751f9988b521cd58d18d60d9c64fc300cdf4dbcc8ba1447162309a7f38"


def pinned_frame():
    df = pd.DataFrame(
        {
            "open_time": [START + r[0] * H for r in PINNED],
            **{c: [r[k + 1] for r in PINNED] for k, c in enumerate(sn.VALUES)},
        }
    )
    df.attrs.update(exchange="coinbase", pair="BTC-USD")
    return df


def test_the_earlier_bar_hashes_are_unchanged():
    import pt_pattern_trainer as ppt
    from model_lab import series as series_mod
    from signal_audit import evidence
    from strategy_lab import e1

    df = pinned_frame()
    assert ppt.candle_sha256(df) == CANDLE_CSV_SHA256
    assert evidence.bars_sha256(evidence.rows_of(df)) == CANDLE_CSV_SHA256
    series = series_mod.from_frame("BTC", "coinbase", "BTC-USD", df)
    assert series_mod.bars_sha256(series) == CANDLE_CSV_SHA256 == series.sha256
    assert e1.frame_sha256(df) == E1_FRAME_SHA256


def test_the_new_bar_hash_is_the_candle_csv_digest_and_not_e1s():
    df = pinned_frame()
    assert sn.bar_hash(df) == CANDLE_CSV_SHA256
    assert sn.bar_hash(df.iloc[::-1]) == CANDLE_CSV_SHA256  # any row order
    assert sn.bar_hash(df) != E1_FRAME_SHA256
    assert snap({"BTC": df}, n=6).series("BTC")["bar_hash"] == CANDLE_CSV_SHA256


def test_a_cache_file_hash_is_the_bar_hash_only_when_it_holds_exactly_those_bars(
    tmp_path,
):
    from market_data import candles

    df = pinned_frame()
    path = tmp_path / "bars.csv"
    path.write_bytes(sn.canonical_bar_bytes(df))
    assert candles.file_sha256(str(path)) == CANDLE_CSV_SHA256
    path.write_bytes(
        sn.canonical_bar_bytes(df) + b"1709272800000,1.0,1.0,1.0,1.0,1.0\n"
    )
    assert candles.file_sha256(str(path)) != CANDLE_CSV_SHA256  # the file grew
