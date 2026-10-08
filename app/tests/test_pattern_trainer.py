"""FDS-MDL Phase 1: the pattern trainer (``app/pt_pattern_trainer.py``), a port of the
upstream trainer at ``ba62130`` that reads candles only through
``app/market_data/candles.py``.

* Acceptance 2: no candle after ``train_end`` can be read (poisoned later bars change
  nothing; a ``train_end`` inside a bar; a refusal if the data layer returns one).
* Acceptance 3: deterministic for the same seed and data; different data, different
  output.
* The thinker's file contract, the run's status and stamp files, refusals and errors.
* Equivalence: on the same bars the port writes byte-identical model files to the
  vendored upstream trainer (run in a child process with a fake KuCoin client).

All candles are synthetic (helpers_candles) and read from the cache offline; the
network is blocked in this process and in every child (helpers_trainer)."""

import ast
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for _path in (APP_DIR, TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import helpers_candles as hc  # noqa: E402
import helpers_trainer as ht  # noqa: E402
import helpers_upstream as hu  # noqa: E402
import pt_paths  # noqa: E402
import pt_pattern_trainer as ppt  # noqa: E402
from market_data import candles  # noqa: E402
from market_data.timeframes import (  # noqa: E402
    TIMEFRAME_SECONDS,
    bar_open_floor,
    candle_timeframe_seconds,
    timeframe_seconds,
)

TRAINER = os.path.join(APP_DIR, "pt_pattern_trainer.py")
START = datetime(2024, 1, 1, tzinfo=timezone.utc)  # a Monday
HOURS = 1680  # ten weeks
END = START + timedelta(hours=HOURS)  # also a Monday, 00:00 UTC
PAIR = "BTCUSDT"


@pytest.fixture(autouse=True)
def guarded(monkeypatch, tmp_path, isolated_user_dirs):
    """Network blocked here and in children; no POWERTRADER_* variable but the
    per-test POWERTRADER_HOME reaches a child unless a test sets it."""
    monkeypatch.chdir(tmp_path)
    return ht.guard_trainer_children(monkeypatch, tmp_path)


def seed_cache(hourly=None, n=HOURS, seed=1, frames=None):
    if frames is None:
        if hourly is None:
            hourly = hc.synthetic_hourly(n, START, seed=seed)
        frames = hc.all_timeframes(hourly)
    hc.seed_cache(candles.cache_dir_default(), PAIR, frames)
    return frames


def train_into(folder, start=START, end=END, **kwargs):
    os.makedirs(str(folder), exist_ok=True)
    return ppt.train(
        "BTC", str(folder), start, end, offline=True, log=lambda *a: None, **kwargs
    )


def model_bytes(folder):
    out = {}
    for name in ht.expected_model_file_names():
        path = os.path.join(str(folder), name)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                out[name] = f.read()
    return out


def window_args(start=START, end=END):
    return ["--train-start", start.isoformat(), "--train-end", end.isoformat()]


# --- timeframes ---------------------------------------------------------------------------


def test_weekly_bars_are_a_candle_timeframe_but_not_a_strategy_timeframe():
    from strategies.settings import read_strategy_settings

    assert candle_timeframe_seconds("1w") == 7 * 86400
    assert "1w" not in TIMEFRAME_SECONDS
    with pytest.raises(ValueError):
        timeframe_seconds("1w")  # strategies, signal engine, backtester
    problem = read_strategy_settings({"strategy": {"timeframe": "1w"}}).problem
    assert problem and "unsupported strategy.timeframe '1w'" in problem, problem
    with pytest.raises(ValueError):
        candle_timeframe_seconds("3w")


def test_bar_open_floor_uses_monday_weeks_and_epoch_multiples():
    wed = int(datetime(2024, 1, 3, 15, 30, tzinfo=timezone.utc).timestamp())
    monday = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
    assert bar_open_floor(wed, "1w") == monday
    assert bar_open_floor(monday, "1w") == monday
    assert bar_open_floor(monday - 1, "1w") == monday - 7 * 86400
    assert bar_open_floor(wed, "1d") == wed - 15 * 3600 - 1800
    assert bar_open_floor(wed, "4h") == wed - 3 * 3600 - 1800
    assert bar_open_floor(wed, "1h") == wed - 1800


def test_resampled_fixture_bars_are_complete_and_aligned():
    frames = hc.all_timeframes(hc.synthetic_hourly(HOURS, START, seed=1))
    for tf, frame in frames.items():
        step = candle_timeframe_seconds(tf)
        assert len(frame) == HOURS * 3600 // step, tf
        for t in frame["open_time"]:
            assert bar_open_floor(int(t.timestamp()), tf) == int(t.timestamp())


# --- acceptance 2: nothing after train_end ------------------------------------------------


def poisoned(frames, cut):
    """Copies of ``frames`` with every bar that closes after ``cut`` replaced by
    extreme prices."""
    out = {}
    for tf, frame in frames.items():
        frame = frame.copy()
        closes = frame["open_time"] + pd.Timedelta(seconds=candle_timeframe_seconds(tf))
        late = closes > pd.Timestamp(cut)
        assert late.any(), f"fixture has no bar after {cut} for {tf}"
        for i, column in enumerate(("open", "high", "low", "close")):
            frame.loc[late, column] = 1e6 + 1000.0 * i + frame.loc[late, "volume"]
        out[tf] = frame
    return out


@pytest.mark.parametrize(
    "train_end",
    [END, END + timedelta(hours=13, minutes=30)],
    ids=["on-a-week-boundary", "inside-a-bar"],
)
def test_bars_closing_after_train_end_cannot_change_the_output(tmp_path, train_end):
    later_end = train_end + timedelta(days=7)
    frames = seed_cache(n=HOURS + 200)
    train_into(tmp_path / "clean", end=train_end)
    train_into(tmp_path / "clean_later", end=later_end)

    seed_cache(frames=poisoned(frames, train_end))
    train_into(tmp_path / "dirty", end=train_end)
    train_into(tmp_path / "dirty_later", end=later_end)

    clean = model_bytes(tmp_path / "clean")
    assert sorted(clean) == ht.expected_model_file_names()
    assert model_bytes(tmp_path / "dirty") == clean
    # control: once inside the window, the poisoned bars are read and change the output
    assert model_bytes(tmp_path / "dirty_later") != model_bytes(
        tmp_path / "clean_later"
    )


def test_the_loader_reads_only_bars_closed_by_train_end():
    seed_cache(n=HOURS + 200)
    train_end = END + timedelta(hours=13, minutes=30)  # Monday 13:30
    loader = ppt.BarLoader(PAIR, START, train_end, offline=True)
    expected_last_open = {
        "1hour": END + timedelta(hours=12),
        "2hour": END + timedelta(hours=10),
        "4hour": END + timedelta(hours=8),
        "8hour": END,
        "12hour": END,
        "1day": END - timedelta(days=1),
        "1week": END - timedelta(days=7),
    }
    for choice, last_open in expected_last_open.items():
        tf = ppt.CANDLE_TF[choice]
        loader.bars(choice)
        report = loader.reports[tf]
        assert pd.Timestamp(report["last_open"]) == pd.Timestamp(last_open), choice
        assert pd.Timestamp(report["first_open"]) == pd.Timestamp(START), choice
        assert (report["missing_at_start"], report["missing_at_end"]) == (0, 0), choice
        close = last_open + timedelta(seconds=candle_timeframe_seconds(tf))
        assert (
            close <= train_end < close + timedelta(seconds=candle_timeframe_seconds(tf))
        )


def test_a_train_start_with_fractions_of_a_second_starts_at_the_next_bar():
    seed_cache()
    start = START + timedelta(milliseconds=500)
    loader = ppt.BarLoader(PAIR, start, END, offline=True)
    for choice in ppt.TF_CHOICES:
        loader.bars(choice)
    for tf, report in loader.reports.items():
        step = pd.Timedelta(seconds=candle_timeframe_seconds(tf))
        assert pd.Timestamp(report["window_first_open"]) == pd.Timestamp(START) + step
        assert report["first_open"] == report["window_first_open"], tf
        assert report["missing_at_start"] == 0, tf


def test_a_bar_after_train_end_from_the_data_layer_is_refused(monkeypatch):
    seed_cache()
    real = candles.get_candles

    def leaky(symbol, tf, start, end, **kwargs):
        df = real(symbol, tf, start, end, **kwargs)
        extra = df.iloc[[-1]].copy()
        extra["open_time"] = extra["open_time"] + pd.Timedelta(
            seconds=candle_timeframe_seconds(tf)
        )
        return pd.concat([df, extra], ignore_index=True)

    monkeypatch.setattr(candles, "get_candles", leaky)
    with pytest.raises(ppt.TrainerError, match="lookahead"):
        ppt.BarLoader(PAIR, START, END, offline=True).bars("1hour")


def test_the_trainer_reads_candles_only_through_the_candle_layer():
    """AST check: no import of the old data provider, the exchange layer, settings,
    credentials or a network library."""
    with open(TRAINER, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    forbidden = {
        "pt_data_provider",
        "pt_multi_exchange",
        "trading_mode",
        "pt_secrets",
        "keyring",
        "kucoin",
        "requests",
        "urllib",
        "http",
        "socket",
    }
    assert not {m for m in imported if m.split(".")[0] in forbidden}, imported
    assert "market_data.candles" in imported


# --- the online data path (what the hub runs) --------------------------------------------

EPOCH = pd.Timestamp("1970-01-01", tz="UTC")


class FakeKlines:
    """Stands in for ``candles.BinanceKlines``: serves fixture frames the way the
    public endpoint does (open time in ``[start_ms, end_ms]``, oldest first, Binance
    column order) and records every request. Nothing touches the network."""

    def __init__(self, frames_by_pair):
        self.frames = frames_by_pair
        self.calls = []
        self.requests_made = 0

    def fetch(self, symbol, tf, start_ms, end_ms=None):
        self.requests_made += 1
        self.calls.append((symbol, tf, start_ms, end_ms))
        frame = self.frames.get(symbol, {}).get(tf)
        if frame is None:
            return []
        ms = (frame["open_time"] - EPOCH) // pd.Timedelta(milliseconds=1)
        keep = ms >= start_ms
        if end_ms is not None:
            keep &= ms <= end_ms
        rows = frame[keep]
        return [
            [int(t), o, h, lo, c, v]
            for t, o, h, lo, c, v in zip(
                ms[keep],
                rows["open"].tolist(),
                rows["high"].tolist(),
                rows["low"].tolist(),
                rows["close"].tolist(),
                rows["volume"].tolist(),
            )
        ]


@pytest.fixture
def exchange(monkeypatch):
    """Install a FakeKlines serving ``{pair: {tf: frame}}``; returns it."""

    def install(frames_by_pair):
        fake = FakeKlines(frames_by_pair)
        monkeypatch.setattr(candles, "BinanceKlines", lambda *a, **k: fake)
        return fake

    return install


def load_all(loader):
    for choice in ppt.TF_CHOICES:
        loader.bars(choice)
    return loader.reports


def test_an_online_run_trains_on_the_bars_an_offline_run_reads(tmp_path, exchange):
    """Online (the hub's default): the cache is filled from the exchange, then read
    with now=train_end. Same files as an offline run on that cache; a train_start
    that is not on a bar boundary is not reported as missing data; no request asks
    for a bar that opens at or after the last bar the window can use."""
    hourly = hc.synthetic_hourly(HOURS + 200, START, seed=1)
    fake = exchange({PAIR: hc.all_timeframes(hourly)})
    start = START + timedelta(hours=13)  # off the boundary of every timeframe above 1h
    os.makedirs(tmp_path / "online")
    summary = ppt.train(
        "BTC", str(tmp_path / "online"), start, END, offline=False, log=lambda *a: None
    )
    train_into(tmp_path / "offline", start=start)

    assert sorted(model_bytes(tmp_path / "online")) == ht.expected_model_file_names()
    assert model_bytes(tmp_path / "online") == model_bytes(tmp_path / "offline")
    for tf, report in summary["candles"].items():
        assert (report["missing_at_start"], report["missing_at_end"]) == (0, 0), tf
        assert report["first_open"] == report["window_first_open"], tf
    end_ms = (pd.Timestamp(END) - EPOCH) // pd.Timedelta(milliseconds=1)
    assert fake.calls and all(c[3] is not None and c[3] < end_ms for c in fake.calls)


def test_an_older_window_after_a_newer_one_leaves_no_hole_in_the_cache(exchange):
    """A newer window fills the cache first; an older one then fills the head. The
    bars between the older window's end and the cache's first bar must be cached
    too, or a later window across them trains on part of its data, unreported."""
    weeks = timedelta(weeks=1)
    hourly = hc.synthetic_hourly(40 * 168, START, seed=1)
    exchange({PAIR: hc.all_timeframes(hourly)})
    load_all(ppt.BarLoader(PAIR, START + 20 * weeks, START + 30 * weeks, offline=False))
    load_all(ppt.BarLoader(PAIR, START, START + 10 * weeks, offline=False))

    for tf in hc.TRAINER_TFS:
        cached = candles.load_candles_csv(candles.cache_path(PAIR, tf), tf)
        assert cached.attrs["report"].gaps == [], tf
    reports = load_all(
        ppt.BarLoader(PAIR, START + 5 * weeks, START + 25 * weeks, offline=True)
    )
    for tf, report in reports.items():
        assert report["bars"] == 20 * 7 * 86400 // candle_timeframe_seconds(tf), tf
        assert report["gaps"] == [] and report["missing_at_start"] == 0, tf


def test_a_pair_listed_after_train_start_is_reported_online_and_refused_offline(
    exchange, capsys
):
    listed = START + timedelta(weeks=4)
    hourly = hc.synthetic_hourly(HOURS - 4 * 168, listed, seed=3)
    exchange({"NEWUSDT": hc.all_timeframes(hourly)})

    reports = load_all(ppt.BarLoader("NEWUSDT", START, END, offline=False))
    for tf, report in reports.items():
        step = candle_timeframe_seconds(tf)
        assert report["missing_at_start"] == 4 * 7 * 86400 // step, tf
        assert report["missing_at_end"] == 0, tf
        assert pd.Timestamp(report["first_open"]) == pd.Timestamp(listed), tf
    assert (
        "NEWUSDT 1h: no bars for the first 672 and the last 0"
        in capsys.readouterr().out
    )

    with pytest.raises(ppt.TrainerError, match="does not cover"):
        ppt.BarLoader("NEWUSDT", START, END, offline=True).bars("1hour")


def test_a_bar_missing_at_the_end_is_reported_the_same_whatever_the_cache_holds(
    exchange,
):
    """The exchange has no bar for the window's last hour. A fresh cache and one that
    already reaches past the window give the same bars and the same report."""
    hourly = hc.synthetic_hourly(HOURS + 200, START, seed=1)
    hourly = hourly[hourly["open_time"] != pd.Timestamp(END) - pd.Timedelta(hours=1)]
    exchange({PAIR: hc.all_timeframes(hourly.reset_index(drop=True))})

    fresh = load_all(ppt.BarLoader(PAIR, START, END, offline=False))
    load_all(ppt.BarLoader(PAIR, START, END + timedelta(weeks=1), offline=False))
    longer = load_all(ppt.BarLoader(PAIR, START, END, offline=False))

    assert fresh == longer
    for tf, report in fresh.items():
        # the missing hour also leaves every higher timeframe's last bar incomplete
        assert report["missing_at_end"] == 1, tf
        assert report["missing_at_start"] == 0, tf


# --- acceptance 3: deterministic; data-dependent ------------------------------------------


def run_main(folder, *argv, env=None, hash_seed="0"):
    """``pt_pattern_trainer.py`` as a guarded child process in ``folder``."""
    os.makedirs(str(folder), exist_ok=True)
    child_env = dict(os.environ, PYTHONHASHSEED=hash_seed, **(env or {}))
    return subprocess.run(
        [sys.executable, "-u", TRAINER, *argv],
        cwd=str(folder),
        env=child_env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def test_training_is_deterministic_for_the_same_seed_and_data(tmp_path, guarded):
    seed_cache()
    train_into(tmp_path / "a")
    train_into(tmp_path / "b")
    proc = run_main(
        tmp_path / "c", "BTC", "--offline", *window_args(), hash_seed="12345"
    )
    assert proc.returncode == 0, proc.stdout[-2000:]
    assert ht.child_errors(guarded) == []

    first = model_bytes(tmp_path / "a")
    assert sorted(first) == ht.expected_model_file_names()
    assert model_bytes(tmp_path / "b") == first
    assert model_bytes(tmp_path / "c") == first


def test_different_data_gives_different_output(tmp_path):
    seed_cache(seed=1)
    train_into(tmp_path / "one")
    seed_cache(seed=2)
    train_into(tmp_path / "two")
    one, two = model_bytes(tmp_path / "one"), model_bytes(tmp_path / "two")
    assert sorted(one) == sorted(two) == ht.expected_model_file_names()
    for tf in ht.TIMEFRAMES:
        assert one[f"memories_{tf}.txt"] != two[f"memories_{tf}.txt"], tf


def test_the_seed_is_recorded_and_changes_nothing(tmp_path):
    """Upstream uses no randomness; the seed is applied and recorded anyway."""
    seed_cache()
    train_into(tmp_path / "zero", seed=0)
    train_into(tmp_path / "seven", seed=7)
    assert model_bytes(tmp_path / "seven") == model_bytes(tmp_path / "zero")


# --- equivalence with upstream ba62130 ----------------------------------------------------


def upstream_klines(end):
    """What upstream's KuCoin calls return: the cached bars, plus one still-forming
    bar opening at ``end``."""
    out = {}
    for choice, tf in ppt.CANDLE_TF.items():
        frame = candles.load_candles_csv(candles.cache_path(PAIR, tf), tf)
        out[choice] = hu.kucoin_rows(frame, end.timestamp())
    return out


def run_both(tmp_path, hourly):
    seed_cache(hourly=hourly)
    end = START + timedelta(hours=len(hourly))
    code, record, upstream_dir, log = hu.run_upstream(
        tmp_path / "upstream", upstream_klines(end), end.timestamp() + 1
    )
    with open(log, encoding="utf-8", errors="replace") as f:
        tail = f.read()[-3000:]
    assert code == 0 and record and "error" not in record, (record, tail)
    port_dir = tmp_path / "port"
    summary = train_into(port_dir, end=end, upstream_flush_only=True)
    return record, model_bytes(upstream_dir), model_bytes(port_dir), summary


def test_the_vendored_upstream_trainer_is_upstreams_blob():
    assert hu.upstream_blob_ok(ppt.UPSTREAM_BLOB)
    assert ppt.UPSTREAM_COMMIT == "ba62130"


def zero_closes():
    """A random walk with a close of 0 on eight hours (the next hour opens where the
    walk was). Upstream skips learning on a step whose last close is 0; so must the
    port. Some of the hours end a 2h-1d bar, so those timeframes see it too."""
    hourly = hc.synthetic_hourly(HOURS, START, seed=5)
    for i in (100, 150, 215, 311, 383, 431, 503, 575):
        hourly.loc[i, ["close", "low"]] = 0.0
    return hourly


def total(summary, key):
    return sum(p[key] for v in summary["timeframes"].values() for p in v["passes"])


# data, and what the run must show it exercised: ten and twenty weeks of a random
# walk; coarse ticks, where most candles have no body, so more than 20 memories match
# and the threshold falls to its floor (the 0.01 and 0.001 steps down and the clamp
# run); near-identical bodies, where it settles below 0.1 (the 0.001 steps decide
# which memories match); and zero closes (steps that learn nothing).
ORACLE_DATA = {
    "10-weeks": (lambda: hc.synthetic_hourly(HOURS, START, seed=1), None),
    "20-weeks": (lambda: hc.synthetic_hourly(2 * HOURS, START, seed=3), None),
    "coarse-ticks": (
        lambda: hc.synthetic_hourly(HOURS, START, seed=4, tick=0.5, vol=0.002),
        lambda s: s["timeframes"]["1hour"]["final_threshold"] == 0.0,
    ),
    "alike-bodies": (
        lambda: hc.alike_hourly(HOURS, START, seed=7),
        lambda s: 0.0 < s["timeframes"]["1hour"]["final_threshold"] < 0.1,
    ),
    "zero-closes": (zero_closes, lambda s: total(s, "unlearned_steps") > 0),
}


@pytest.mark.parametrize("data", sorted(ORACLE_DATA))
def test_the_port_writes_the_same_model_files_as_upstream(tmp_path, data):
    """Same bars in, byte-identical memories, weights and thresholds out (in
    ``--upstream-flush-only`` mode, which keeps upstream's flush schedule). The
    data is chosen so no KuCoin page comes back empty (see the next test)."""
    make, exercised = ORACLE_DATA[data]
    record, upstream, port, summary = run_both(tmp_path, make())
    pages = [c for c in record["calls"] if c[0] == "kline"]
    assert pages and all(c[5] > 0 for c in pages), pages
    assert sorted(upstream) == ht.expected_model_file_names()
    assert port == upstream
    if exercised:
        assert exercised(summary)


def test_the_only_difference_from_upstream_is_its_empty_page_row(tmp_path, monkeypatch):
    """Deviation 2: when upstream's last page held 1,000 rows or more it fetched one
    more page, and an empty page added a malformed row that it counted before
    halving. With 12 weeks of data that happens for ``2hour`` (1,008 closed bars plus
    the forming one). Keeping one bar fewer there makes the port match upstream."""
    n = 2016
    real_select = ppt.select_rows

    def upstream_count(bars, data_tf, restarted_yet):
        rows = real_select(bars, data_tf, restarted_yet)
        if data_tf == "2hour" and restarted_yet > 0:
            rows = tuple(r[:-1] for r in rows)
        return rows

    monkeypatch.setattr(ppt, "select_rows", upstream_count)
    record, upstream, port, _ = run_both(
        tmp_path, hc.synthetic_hourly(n, START, seed=2)
    )
    empty = {c[2] for c in record["calls"] if c[0] == "kline" and c[5] == 0}
    assert empty == {"2hour"}
    assert port == upstream


def test_default_mode_keeps_upstreams_output_and_adds_the_unflushed_tail(tmp_path):
    seed_cache()
    train_into(tmp_path / "upstream_mode", upstream_flush_only=True)
    summary = train_into(tmp_path / "default")
    flushed = model_bytes(tmp_path / "upstream_mode")
    full = model_bytes(tmp_path / "default")
    assert sorted(full) == ht.expected_model_file_names()
    for tf in ht.TIMEFRAMES:
        memories = full[f"memories_{tf}.txt"].decode()
        prefix = flushed[f"memories_{tf}.txt"].decode()
        assert memories == prefix or memories.startswith(prefix + "~"), tf
        count = len(memories.split("~"))
        assert count == summary["timeframes"][tf]["memories"]
        for kind in ("memory_weights", "memory_weights_high", "memory_weights_low"):
            assert full[f"{kind}_{tf}.txt"].decode().split(" ") == ["1.0"] * count
        threshold = full[f"neural_perfect_threshold_{tf}.txt"].decode()
        assert float(threshold) == summary["timeframes"][tf]["final_threshold"]


# --- the thinker's file contract and the run's files --------------------------------------


def thinker_reads(folder, tf):
    """The thinker's own parse expressions (pt_thinker.py, the per-timeframe step:
    threshold, memories, the three weight files, then every memory's fields)."""

    def strip(text):
        return (
            text.replace("'", "")
            .replace(",", "")
            .replace('"', "")
            .replace("]", "")
            .replace("[", "")
        )

    def read(name):
        with open(os.path.join(folder, name), "r") as f:
            return f.read()

    threshold = float(read(f"neural_perfect_threshold_{tf}.txt"))
    memory_list = strip(read(f"memories_{tf}.txt")).split("~")
    weights = [
        [float(w) for w in strip(read(f"{kind}_{tf}.txt")).split(" ")]
        for kind in ("memory_weights", "memory_weights_high", "memory_weights_low")
    ]
    for entry in memory_list:
        memory_pattern = strip(entry.split("{}")[0]).split(" ")
        float(memory_pattern[0])
        float(memory_pattern[len(memory_pattern) - 1])
        float(strip(entry.split("{}")[1]).replace(" ", ""))
        float(strip(entry.split("{}")[2]).replace(" ", ""))
        assert len(memory_pattern) == 2 and entry.count("{}") == 2, entry
    return threshold, memory_list, weights


def test_the_output_is_what_the_thinker_reads(tmp_path):
    seed_cache()
    folder = tmp_path / "coin"
    train_into(folder)
    for tf in ht.TIMEFRAMES:
        threshold, memories, weights = thinker_reads(str(folder), tf)
        assert memories and all(m.strip() for m in memories), tf
        assert all(len(w) == len(memories) for w in weights), tf
        # the thinker rewrites the threshold as str(float(...)): byte-stable
        with open(folder / f"neural_perfect_threshold_{tf}.txt") as f:
            assert str(threshold) == f.read()
        assert "np.float64" not in (folder / f"memories_{tf}.txt").read_text()


def test_a_run_writes_status_summary_and_the_stamp_last(tmp_path, monkeypatch):
    seed_cache()
    folder = tmp_path / "coin"
    folder.mkdir()
    monkeypatch.chdir(folder)
    # --offline alone must keep the run offline (the guard also sets the variable)
    monkeypatch.delenv(ppt.ENV_CANDLES_OFFLINE)
    written = []
    real_write = ppt._write_text
    monkeypatch.setattr(
        ppt,
        "_write_text",
        lambda path, text: (
            written.append(os.path.abspath(path)),
            real_write(path, text),
        ),
    )

    assert ppt.main(["BTC", "--offline", "--seed", "3", *window_args()]) == 0

    written = [os.path.normcase(p) for p in written]
    stamp = os.path.join(str(folder), "trainer_last_training_time.txt")
    status_path = os.path.join(str(folder), "trainer_status.json")
    assert written[-1] == os.path.normcase(stamp)
    assert written[0] == os.path.normcase(status_path)  # TRAINING, before model files
    assert sorted(ht.model_files(str(folder))) == ht.expected_model_file_names()
    with open(status_path, encoding="utf-8") as f:
        status = json.load(f)
    assert status["state"] == "FINISHED" and status["coin"] == "BTC"
    with open(stamp, encoding="utf-8") as f:
        assert float(f.read()) == status["finished_at"]

    results = pt_paths.data_file("training_results", "btc_training_results.json")
    assert written[-4] == os.path.normcase(os.path.abspath(results))
    with open(results, encoding="utf-8") as f:
        summary = json.load(f)
    assert summary["upstream"] == {
        "repo": ppt.UPSTREAM_REPO,
        "commit": "ba62130",
        "blob": ppt.UPSTREAM_BLOB,
    }
    assert summary["train_start"] == "2024-01-01T00:00:00Z"
    assert summary["train_end"] == "2024-03-11T00:00:00Z"
    assert summary["seed"] == 3 and summary["offline"] is True
    assert summary["sources"]["offline"] == "command line"
    assert summary["candles"]["1h"]["bars"] == HOURS
    assert summary["candles"]["1w"]["bars"] == 10
    passes = summary["timeframes"]["1hour"]["passes"]
    # the older-half rule, recorded: 1,680 closed bars -> the oldest 841
    assert [p["bars_used"] for p in passes] == [841, 841, 841]
    day = summary["timeframes"]["1day"]["passes"]
    assert [(p["data_tf"], p["bars_used"]) for p in day] == [
        ("1hour", 841),
        ("1day", 70),
        ("1day", 70),
    ]


def test_a_folder_with_model_files_is_refused(tmp_path, monkeypatch):
    seed_cache()
    folder = tmp_path / "coin"
    folder.mkdir()
    (folder / "memories_1hour.txt").write_text("old", encoding="utf-8")
    monkeypatch.chdir(folder)
    assert ppt.main(["BTC", "--offline", *window_args()]) == 2
    assert sorted(os.listdir(folder)) == ["memories_1hour.txt"]
    assert (folder / "memories_1hour.txt").read_text(encoding="utf-8") == "old"


def test_missing_candles_end_the_run_with_an_error_and_no_stamp(tmp_path, monkeypatch):
    folder = tmp_path / "coin"
    folder.mkdir()
    monkeypatch.chdir(folder)
    assert ppt.main(["ETH", "--offline", *window_args()]) == 1
    with open(folder / "trainer_status.json", encoding="utf-8") as f:
        status = json.load(f)
    assert status["state"] == "ERROR" and "offline" in status["error"]
    assert not (folder / "trainer_last_training_time.txt").exists()
    assert ht.model_files(str(folder)) == {}


@pytest.mark.parametrize(
    "argv",
    [
        ["BTC", "--train-end", "2999-01-01"],
        ["BTC", "--train-start", "2024-02-01", "--train-end", "2024-01-01"],
        ["BTC", "--seed", "x"],
        ["BTC", "--train-end", "yesterday"],
    ],
    ids=["future-end", "start-after-end", "bad-seed", "bad-date"],
)
def test_bad_arguments_exit_2_without_writing(tmp_path, monkeypatch, argv):
    folder = tmp_path / "coin"
    folder.mkdir()
    monkeypatch.chdir(folder)
    assert ppt.main(argv) == 2
    assert os.listdir(folder) == []


def test_inputs_come_from_the_command_line_then_the_environment_then_defaults():
    now = datetime(2026, 10, 6, 14, 25, 7, tzinfo=timezone.utc)
    cfg = ppt.parse_args(["eth"], environ={}, now=now)
    assert cfg["coin"] == "ETH"
    assert cfg["train_end"] == datetime(2026, 10, 6, 14, tzinfo=timezone.utc)
    assert cfg["train_start"] == cfg["train_end"] - timedelta(days=1095)
    assert cfg["seed"] == 0 and cfg["offline"] is False
    assert set(cfg["sources"].values()) == {"default"}

    env = {
        ppt.ENV_TRAIN_START: "2023-01-01",
        ppt.ENV_TRAIN_END: "2026-01-01T00:00:00Z",
        ppt.ENV_TRAIN_SEED: "5",
        ppt.ENV_CANDLES_OFFLINE: "1",
    }
    cfg = ppt.parse_args(["BTC"], environ=env, now=now)
    assert cfg["train_start"] == datetime(2023, 1, 1, tzinfo=timezone.utc)
    assert cfg["train_end"] == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert (cfg["seed"], cfg["offline"]) == (5, True)
    assert cfg["sources"]["train_end"] == ppt.ENV_TRAIN_END
    cfg = ppt.parse_args(["BTC", "--offline"], environ={}, now=now)
    assert cfg["offline"] is True and cfg["sources"]["offline"] == "command line"

    cfg = ppt.parse_args(
        ["BTC", "--train-end", "2025-06-01T12:00:00+02:00", "--seed", "9"],
        environ=env,
        now=now,
    )
    assert cfg["train_end"] == datetime(2025, 6, 1, 10, tzinfo=timezone.utc)
    assert cfg["seed"] == 9 and cfg["sources"]["seed"] == "command line"


def test_importing_the_trainer_does_nothing(tmp_path, guarded):
    folder = tmp_path / "empty"
    folder.mkdir()
    home = os.environ["POWERTRADER_HOME"]
    before = ht.tree_snapshot(home) if os.path.isdir(home) else {}
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {APP_DIR!r}); import pt_pattern_trainer",
        ],
        cwd=str(folder),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    assert os.listdir(folder) == []
    assert (ht.tree_snapshot(home) if os.path.isdir(home) else {}) == before
    assert ht.child_errors(guarded) == []


def test_a_run_writes_nothing_in_the_program_folder(tmp_path, guarded):
    seed_cache()
    before = ht.program_folder_state()
    proc = run_main(tmp_path / "coin", "BTC", "--offline", *window_args())
    assert proc.returncode == 0, proc.stdout[-2000:]
    assert ht.program_folder_state() == before
    (record,) = [r for r in ht.child_records(guarded) if r.get("final")]
    assert record["blocked"] == []


@pytest.mark.parametrize("coin, sub", [("BTC", ()), ("ETH", ("ETH",))])
def test_started_inside_the_program_folder_it_trains_in_the_coin_folder(
    guarded, coin, sub
):
    """Run from a terminal in app/ (the worst case): the model files go to the coin's
    neural folder under the user data folder (BTC: the root; others: <root>/<SYM>),
    and nothing in the program folder changes."""
    hourly = hc.synthetic_hourly(HOURS, START, seed=1)
    hc.seed_cache(candles.cache_dir_default(), f"{coin}USDT", hc.all_timeframes(hourly))
    before = ht.program_folder_state()
    proc = run_main(pt_paths.program_dir(), coin, "--offline", *window_args())
    assert proc.returncode == 0, proc.stdout[-2000:]
    assert ht.program_folder_state() == before
    folder = os.path.join(pt_paths.neural_dir(), *sub)
    assert sorted(ht.model_files(folder)) == ht.expected_model_file_names()
    (record,) = [r for r in ht.child_records(guarded) if r.get("final")]
    assert os.path.normcase(record["cwd_at_exit"]) == os.path.normcase(folder)


def test_the_backtest_cli_rejects_weekly_bars_before_touching_data(monkeypatch, capsys):
    """1w is a candle-only timeframe: the backtester refuses it before any fetch."""
    from backtest import cli

    calls = []
    monkeypatch.setattr(cli, "get_candles", lambda *a, **k: calls.append(a))
    argv = ["--strategy", "STRAT-001", "--symbol", PAIR, "--tf", "1w"]
    argv += ["--start", "2025-01-01", "--end", "2025-11-01"]
    assert cli.main(argv) == 2
    assert calls == []
    assert "Unsupported timeframe '1w'" in capsys.readouterr().err
