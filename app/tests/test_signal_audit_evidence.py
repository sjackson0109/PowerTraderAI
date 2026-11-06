"""FDS-SIG-001 section 12, steps 3 and 4: the candles a round is evaluated on (the PR
#228 review, finding 3).

The run reads window-scoped snapshots, never the shared cache, so the cache can grow;
a historical correction, a tampered snapshot or a series that is not the registered
one stops the fetch or the run; and repeated runs give identical results.

Everything runs under the isolation guard; no network: the exchange is a fake behind a
real ExchangeManager.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from market_data import candles  # noqa: E402
from pt_exchange_abstraction import ExchangeManager, ExchangeType  # noqa: E402
from signal_audit import engine, evidence, round_one  # noqa: E402
from signal_audit import report as rp  # noqa: E402
from signal_audit.pairs import row_pairs  # noqa: E402

UTC = timezone.utc


# --- candle snapshots --------------------------------------------------------

H = 3_600_000
START = datetime(2026, 1, 5, tzinfo=UTC)  # a Monday
END = datetime(2026, 1, 12, tzinfo=UTC)
START_MS = int(START.timestamp() * 1000)
END_MS = int(END.timestamp() * 1000)


def hourly(first_ms, last_ms, seed):
    rng = np.random.default_rng(seed)
    n = (last_ms - first_ms) // H
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    rows = []
    for i in range(n):
        c = float(close[i])
        o = float(close[i - 1]) if i else c
        rows.append(
            [
                first_ms + i * H,
                o,
                max(o, c) * 1.002,
                min(o, c) * 0.998,
                c,
                float(rng.uniform(1, 9)),
            ]
        )
    return rows


class FakeExchange:
    """Serves 1h bars only, so the 4h bars are built (both through the cache and
    without it)."""

    name = "kucoin"

    def __init__(self):
        self.rows = {
            coin: hourly(START_MS - 10 * 24 * H, END_MS + 2 * 24 * H, seed)
            for seed, coin in enumerate(("AAA", "BTC"))
        }

    def market_symbol(self, symbol):
        return symbol.split("-")[0] + "-USDT"

    def candle_timeframes(self):
        return frozenset({"1h"})

    def max_history_bars(self, tf):
        return None

    def candles(self, symbol, tf, start_ms, end_ms):
        assert tf == "1h"
        rows = self.rows[symbol.split("-")[0]]
        return [list(r) for r in rows if start_ms <= r[0] <= end_ms]


@pytest.fixture
def layer():
    fake = FakeExchange()
    manager = ExchangeManager()
    manager.exchanges[ExchangeType("kucoin")] = fake
    manager.primary_exchange = ExchangeType("kucoin")
    return fake, manager


def registration(**changes):
    record = {
        "exchange": "kucoin",
        "coins": ["AAA"],
        "input_coins": [round_one.INPUT_COIN],
        "timeframes": ["1h", "4h"],
        "window": {"start": "2026-01-05T00:00:00Z", "end": "2026-01-12T00:00:00Z"},
        "candidates": [c.registration() for c in round_one.candidates()],
    }
    record.update(changes)
    return record


def fetched(tmp_path, manager, record=None, earlier=None, cache="cache"):
    return evidence.fetch_round(
        record or registration(),
        manager,
        str(tmp_path / "snapshots"),
        earlier,
        cache_dir=str(tmp_path / cache),
    )


def file_sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_the_snapshot_is_the_registered_span_with_its_provenance(tmp_path, layer):
    _fake, manager = layer
    record = registration()
    data = fetched(tmp_path, manager, record)
    assert data["exchange"] == "kucoin"
    assert set(data["files"]) == {"AAA/1h", "AAA/4h", "BTC/1h", "BTC/4h"}
    f = data["files"]["AAA/1h"]
    start_s, end_s = evidence.span(record, "1h")
    assert (f["exchange"], f["pair"]) == ("kucoin", "AAA-USDT")
    assert f["span"] == [start_s, end_s] and f["first_open_ms"] == start_s * 1000
    assert f["last_open_ms"] == END_MS - H  # the last bar closing by the window end
    path = tmp_path / "snapshots" / f["snapshot"]
    assert file_sha256(path) == f["sha256"]  # the file's hash is the bars' hash
    bars = evidence.load_round(record, data, str(tmp_path / "snapshots"))
    assert len(bars[("AAA", "1h")]) == f["bars"]
    assert len(bars[("AAA", "4h")]) == data["files"]["AAA/4h"]["bars"]


def test_cache_growth_leaves_the_evidence_unchanged(tmp_path, layer):
    """The review's case: the cache file's own SHA-256 changes as later bars are
    appended, and the run stopped though the window's bars were the same."""
    fake, manager = layer
    record = registration()
    data = fetched(tmp_path, manager, record)
    before = evidence.load_round(record, data, str(tmp_path / "snapshots"))
    cache_file = candles.cache_path("AAA-USDT", "1h", str(tmp_path / "cache"), "kucoin")
    sha_before = file_sha256(cache_file)
    # later bars appear at the exchange, and something reads them into the cache
    fake.rows["AAA"] = fake.rows["AAA"] + hourly(
        END_MS + 2 * 24 * H, END_MS + 9 * 24 * H, 7
    )
    candles.exchange_candles(
        "AAA",
        "1h",
        pd.Timestamp(END_MS + 3 * 24 * H, unit="ms", tz="UTC"),
        pd.Timestamp(END_MS + 8 * 24 * H, unit="ms", tz="UTC"),
        cache_dir=str(tmp_path / "cache"),
        manager=manager,
        exchanges=["kucoin"],
    )
    assert file_sha256(cache_file) != sha_before  # the cache grew
    again = fetched(tmp_path, manager, record, earlier=data)  # a re-fetch agrees
    assert again["files"] == data["files"]
    after = evidence.load_round(record, again, str(tmp_path / "snapshots"))
    for key in before:
        for field in ("open_s", "high", "low", "close", "volume"):
            assert np.array_equal(
                getattr(before[key], field), getattr(after[key], field)
            )


def test_a_historical_correction_stops_the_fetch(tmp_path, layer):
    fake, manager = layer
    record = registration()
    data = fetched(tmp_path, manager, record)
    i = next(k for k, r in enumerate(fake.rows["AAA"]) if r[0] == START_MS + 30 * H)
    fake.rows["AAA"][i] = fake.rows["AAA"][i][:4] + [fake.rows["AAA"][i][4] * 1.01, 5.0]
    # the cache still holds the bar as first served; the exchange serves it corrected
    with pytest.raises(evidence.EvidenceError, match="historical correction"):
        fetched(tmp_path, manager, record, earlier=data)
    # read afresh (a new cache), the corrected series differs from the earlier record
    with pytest.raises(evidence.EvidenceError, match="differs from its earlier record"):
        fetched(tmp_path, manager, record, earlier=data, cache="cache2")
    # and a snapshot already written is never overwritten with other bars
    with pytest.raises(evidence.EvidenceError, match="already exists"):
        evidence.fetch_round(
            record,
            manager,
            str(tmp_path / "snapshots"),
            None,
            cache_dir=str(tmp_path / "cache3"),
        )


def test_a_changed_snapshot_or_record_stops_the_run(tmp_path, layer):
    _fake, manager = layer
    record = registration()
    data = fetched(tmp_path, manager, record)
    snaps = str(tmp_path / "snapshots")
    path = os.path.join(snaps, data["files"]["AAA/1h"]["snapshot"])
    text = open(path, encoding="utf-8").read()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.replace(",", ";", 7).replace(";", ",", 6))  # one byte changed
    with pytest.raises(evidence.EvidenceError, match="differs from its record"):
        evidence.load_round(record, data, snaps)
    os.remove(path)
    with pytest.raises(evidence.EvidenceError, match="cannot be read"):
        evidence.load_round(record, data, snaps)
    data = fetched(tmp_path, manager, record)  # written again: the same bars
    assert evidence.load_round(record, data, snaps)
    # a record from another exchange, or not the registered series, is refused
    with pytest.raises(evidence.EvidenceError, match="not the registered kucoin"):
        evidence.load_round(record, dict(data, exchange="kraken"), snaps)
    with pytest.raises(evidence.EvidenceError, match="does not hold the registered"):
        evidence.load_round(registration(coins=["AAA", "BBB"]), data, snaps)
    moved = dict(record["window"], start="2026-01-06T00:00:00Z")
    with pytest.raises(evidence.EvidenceError, match="span is not the round's"):
        evidence.load_round(registration(window=moved), data, snaps)
    forged = json.loads(json.dumps(data))
    forged["files"]["AAA/1h"]["exchange"] = "kraken"
    with pytest.raises(evidence.EvidenceError, match="from kraken, not kucoin"):
        evidence.load_round(record, forged, snaps)


def test_repeated_runs_give_identical_results(tmp_path, layer):
    _fake, manager = layer
    record = registration()
    data = fetched(tmp_path, manager, record)
    snaps = str(tmp_path / "snapshots")
    start = int(START.timestamp())
    end = int(END.timestamp())

    def run_once():
        bars = evidence.load_round(record, data, snaps)
        rows = []
        for c in round_one.candidates():
            for tf in record["timeframes"]:
                inputs = {ic: bars[(ic, tf)] for ic in c.input_coins}
                key = engine.RowKey(c.key, "kucoin", "AAA", tf)
                rows.append((key, row_pairs(c, bars[("AAA", tf)], inputs, start, end)))
        result = engine.evaluate_round(
            rows, draws=200, seed=3, family_error=0.05, mde_sims=20, mde_replicates=2
        )
        return json.dumps(rp.results_record(result, 1, "0" * 64, {}), sort_keys=True)

    assert run_once() == run_once()
