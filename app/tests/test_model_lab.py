"""The model lab's core (FDS-MH-001 phase B, section 8).

* Every rule decided from the bars cut at an hour equals the same rule from all bars
  (no look-ahead), and the lockbox is never read.
* R2 never moves a signal less than D, and wraps round each coin's stream.
* On random-walk prices, R1 and R2 pass a no-skill contestant at about the nominal rate.
* A batch run twice gives identical results; a frozen batch whose file, code or candles
  have changed is refused.
* The pattern contestant's fold-1 entries equal the trainer's sibling fit on the same
  window.
* Holm, Benjamini-Hochberg, the p-values and the probability of backtest overfitting
  on hand-checked cases; the fold calendar; the gap rules.

All candles are synthetic and read offline from the candle cache (no network)."""

import json
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for _path in (APP_DIR, TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import entry_gate  # noqa: E402
import helpers_candles as hc  # noqa: E402
import model_gate  # noqa: E402
from market_data import candles  # noqa: E402
from model_lab import baselines, batch, catalogue, contestants, stats  # noqa: E402
from model_lab import series as series_mod  # noqa: E402
from model_lab import walkforward  # noqa: E402
from model_lab.replay import TradeTable, schedule  # noqa: E402

START = pd.Timestamp("2024-01-01", tz="UTC")  # a Monday
FEES = entry_gate.Fees(0.005, "taker", "binance", "exchange", 0.0005)


class NoFetch:
    def fetch(self, *args, **kwargs):
        raise AssertionError("the model lab tests read the candle cache only")


@pytest.fixture(autouse=True)
def layer(monkeypatch, isolated_user_dirs):
    """One exchange in Settings, serving only what the cache holds."""
    return hc.fake_layer(monkeypatch, NoFetch())


def walk(n, start=START, seed=0, vol=0.004, drift=0.00005, price=100.0):
    """``n`` hourly bars from ``start``: a seeded random walk."""
    rng = np.random.default_rng(seed)
    close = price * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    open_ = np.concatenate([[price], close[:-1]])
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, vol / 2, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, vol / 2, n)))
    return pd.DataFrame(
        {
            "open_time": pd.date_range(start, periods=n, freq="h", tz="UTC"),
            "open": np.round(open_, 6),
            "high": np.round(high, 6),
            "low": np.round(low, 6),
            "close": np.round(close, 6),
            "volume": np.round(rng.uniform(1, 100, n), 3),
        }
    )


def with_gaps(df, *spans):
    """``df`` without the bars at the given (first, count) positions."""
    drop = [i for first, count in spans for i in range(first, first + count)]
    return df.drop(index=drop).reset_index(drop=True)


def seed_1h(coin, df):
    hc.seed_cache(candles.cache_dir_default(), f"{coin}USDT", {"1h": df})


def lab_data(frames, rules=None, start=START):
    series = {
        coin: series_mod.from_frame(coin, "binance", f"{coin}USDT", df)
        for coin, df in frames.items()
    }
    return walkforward.LabData(
        series, rules or model_gate.trade_rules({}), int(start.timestamp())
    )


def cut_data(data, until):
    return walkforward.LabData(
        {c: s.cut(until) for c, s in data.series.items()},
        data.rules,
        data.start_s,
    )


# --- no look-ahead ---------------------------------------------------------------------


def test_every_rule_decided_from_bars_cut_at_an_hour_equals_it_from_all_bars():
    hours = 24 * 400
    # a missing hour (its day is not built), a 6-hour gap, and a day's gap
    eth = with_gaps(walk(hours, seed=2), (3000, 1), (5000, 6), (7000, 20))
    data = lab_data({"BTC": walk(hours, seed=1), "ETH": eth})
    rules = [c for c in catalogue.catalogue() if not c.trained]
    assert {r.key for r in rules} >= {
        "ref.always",
        "rule.sma20",
        "rule.sma50",
        "rule.sma100",
        "rule.mom14",
        "rule.high20",
        "rule.btc50",
        "rule.dip24",
    }
    rng = random.Random(5)
    for coin in ("BTC", "ETH"):
        close_s = data.series[coin].close_s
        picks = sorted(rng.sample(range(24 * 101, len(close_s)), 60))
        # hours just after each gap, and the day after the missing hour
        picks += [2999, 3000, 3001, 3024, 4994, 4995, 4996, 6980, 6981, 6990]
        for rule in rules:
            full = rule.fit(data, 0).entries(coin, close_s)
            assert set(np.unique(full).tolist()) <= {-1, 0, 1}
            if rule.key != "ref.always":
                assert {0, 1} <= set(full[24 * 101 :].tolist()), rule.key
            for p in picks:
                t = int(close_s[p])
                alone = rule.fit(cut_data(data, t), 0).entries(coin, [t])
                assert alone[0] == full[p], (rule.key, coin, p)


def test_a_daily_rule_is_undecided_the_day_after_a_day_that_was_not_built():
    eth = with_gaps(walk(24 * 200, seed=2), (24 * 150 + 5, 1))  # day 150 is incomplete
    data = lab_data({"BTC": walk(24 * 200, seed=1), "ETH": eth})
    s = data.series["ETH"]
    values = catalogue.get("rule.sma20").fit(data, 0).entries("ETH", s.close_s)
    day = s.close_s // 86400 * 86400 - 86400  # the last completed day at each hour
    first_day = int(START.timestamp()) // 86400
    on_151 = (day // 86400 - first_day) == 150
    assert on_151.sum() == 24 and (values[on_151] == -1).all()
    assert (values[(day // 86400 - first_day) == 151] != -1).all()


def test_the_lockbox_is_never_read(tmp_path):
    frames = {"BTC": walk(24 * 300, seed=1), "ETH": walk(24 * 300, seed=2)}
    for coin, df in frames.items():
        seed_1h(coin, df)
    batch_id = batch.freeze(
        ["ETH"],
        START,
        ["rule.sma20"],
        end=START + pd.Timedelta(days=300),
        fees={"ETH": FEES},
        offline=True,
        draws=20,
        months=(4, 2, 2),
        min_shift_days=20,
        now=START + pd.Timedelta(days=301),
    )
    seen = []
    original = contestants.DailyAboveAverage.decide

    def spy(self, data, coin, close_s):
        seen.append(max(int(s.close_s[-1]) for s in data.series.values()))
        seen.append(int(np.max(close_s)))
        return original(self, data, coin, close_s)

    contestants.DailyAboveAverage.decide = spy
    try:
        results = batch.run(batch_id)
    finally:
        contestants.DailyAboveAverage.decide = original
    lock = series_mod.epoch(batch.read_batch(batch_id)["calendar"]["lockbox"][0])
    assert seen and max(seen) <= lock
    assert series_mod.epoch(results["streams"]["ETH"]["last"]) == lock


# --- R2 ---------------------------------------------------------------------------------


def test_r2_never_moves_a_signal_less_than_d_and_wraps_round_the_stream():
    rng = random.Random(3)
    d = baselines.min_shift_hours(160)
    assert d == 160 * 24
    for _ in range(2000):
        length = rng.randrange(2 * d, 6 * d)
        u = rng.random()
        delta = baselines.shift(u, length, d)
        assert d <= delta <= length - d
        start = rng.randrange(0, 50)
        ones = sorted(rng.sample(range(start, start + length), 20))
        moved = baselines.moved(ones, start, length, delta)
        assert moved == sorted(moved)
        assert sorted((i - start + delta) % length + start for i in ones) == moved
        for i in ones:
            m = (i - start + delta) % length + start
            gap = abs(m - i)
            assert min(gap, length - gap) >= d
    # both ends of the range are reached
    assert baselines.shift(0.0, 3 * d, d) == d
    assert baselines.shift(0.999999999, 3 * d, d) == 2 * d


def test_a_coin_whose_stream_is_shorter_than_2d_takes_no_part_in_r2():
    d = 100
    long_ = baselines.Plan("BTC", 0, 2 * d, None, [], [], [], [])
    short = baselines.Plan("ETH", 0, 2 * d - 1, None, [], [], [], [])
    assert baselines.r2_coins([long_, short], d) == (["BTC"], ["ETH"])


# --- the random baselines' false-pass rate -----------------------------------------------


class HoldTable:
    """A stand-in trade table on a price path: an entry at hour i holds ``hold`` hours
    (to the path's end at most) and makes the price change on 1 unit, after fees."""

    def __init__(self, price, hold=48, fee=0.0055):
        self.price, self.hold, self.fee = price, hold, fee
        self.cache = {}

    def __len__(self):
        return len(self.price)

    def trade(self, i):
        if i not in self.cache:
            end = min(i + self.hold, len(self.price) - 1)
            ret = self.price[end] / self.price[i] * (1 - self.fee) ** 2 - 1
            path = self.price[i : end + 1] / self.price[i] - 1
            self.cache[i] = entry_gate.Trade(
                ret,
                1.0,
                float(min(0.0, path.min())),
                ret > 0,
                end,
                (end - i) / 24 or 1 / 24,
            )
        return self.cache[i]


def test_r1_and_r2_pass_a_no_skill_contestant_at_about_the_nominal_rate():
    trials, runs, hours, d = 200, 99, 24 * 120, 24 * 30
    passed = {baselines.R1: 0, baselines.R2: 0}
    for k in range(trials):
        rng = np.random.default_rng(1000 + k)
        plans = []
        for coin in ("BTC", "ETH"):
            price = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, hours)))
            table = HoldTable(price)
            signal = (rng.random(hours) < 0.01).astype(np.int8)  # no skill
            plans.append(baselines.plan(walkforward.Decisions(coin, 0, signal), table))
        value = entry_gate.score(baselines.own_trades(plans)).per_day
        for kind, seed in ((baselines.R1, 10**6 * k), (baselines.R2, 10**6 * k + 5000)):
            b = baselines.draws(kind, plans, runs, seed, d)
            if stats.p_upper(value, b.values) <= 0.05:
                passed[kind] += 1
    # 5% of 200 is 10; the binomial 99.9% range is about 2..22
    assert 2 <= passed[baselines.R1] <= 22, passed
    assert 2 <= passed[baselines.R2] <= 22, passed


def test_r1_holds_one_trade_at_a_time_with_the_contestants_own_waits():
    price = np.linspace(100, 120, 400)
    table = HoldTable(price, hold=10)
    values = np.full(400, -1, dtype=np.int8)
    values[50:] = 0
    values[[60, 65, 90, 200]] = 1  # 65 falls inside the trade from 60
    plan = baselines.plan(walkforward.Decisions("BTC", 50, values), table)
    assert [i for i, _t in plan.entries] == [60, 90, 200]
    assert plan.waits == [10, 20, 100]  # from 50, then from each trade's end

    class Picks:
        def __init__(self, picks):
            self.picks = list(picks)

        def random(self):
            return (self.picks.pop(0) + 0.5) / 3

    picks = Picks([2, 0, 1, 1, 2, 2])
    trades = baselines.r1_run([plan], picks)
    # free at 50: wait 100 -> 150; free at 160: wait 10 -> 170; then 20 -> 200 and
    # 230; 100 -> 340; 100 -> 450, past the stream's end
    assert [t.end - 10 for t in trades] == [150, 170, 200, 230, 340]
    assert picks.picks == []


# --- p-values, Holm, Benjamini-Hochberg, PBO, the edge ---------------------------------


def test_the_p_values_count_the_draws_at_least_and_at_most_the_score():
    draws = [0.1, 0.2, 0.2, 0.3]
    assert stats.p_upper(0.2, draws) == (1 + 3) / 5
    assert stats.p_lower(0.2, draws) == (1 + 3) / 5
    assert stats.p_upper(0.5, draws) == 1 / 5


def test_holm_and_benjamini_hochberg_on_a_hand_checked_case():
    ps = [0.01, 0.04, 0.03, 0.005, 0.2]
    # Holm at 5%: 0.005 <= 0.01, 0.01 <= 0.0125, 0.03 > 0.0167 stops
    assert stats.holm(ps, 0.05) == [True, False, False, True, False]
    # BH at 10%: ranks 1..5 -> limits .02 .04 .06 .08 .10; the largest p under its
    # limit is 0.04 (rank 4), so the four smallest pass
    assert stats.benjamini_hochberg(ps, 0.10) == [True, True, True, True, False]


def test_the_smallest_detectable_edge_is_at_the_holm_level():
    z = 2.5758293035489004 + 0.8416212335729143  # z(1 - 0.05/10) + z(0.8)
    assert stats.smallest_edge(0.001, 10) == pytest.approx(z * 0.001, rel=1e-12)


def test_pbo_is_0_for_a_contestant_best_everywhere_and_about_half_for_noise():
    blocks = 8
    held = [[1.0] * blocks for _ in range(5)]
    net = [[0.0] * blocks for _ in range(5)]
    net[2] = [1.0] * blocks  # best on every block
    for k in (0, 1, 3, 4):
        net[k] = [0.1 * ((k * 7 + s * 3) % 5) for s in range(blocks)]
    assert stats.pbo(net, held) == 0.0
    # ten contestants of pure noise: one batch's PBO varies widely (its blocks are
    # one draw), but over many batches the best on half the blocks is at or below the
    # median on the other half about half the time
    values = []
    for seed in range(40):
        rng = random.Random(seed)
        noise = [[rng.gauss(0, 1) for _ in range(blocks)] for _ in range(10)]
        values.append(stats.pbo(noise, [[1.0] * blocks for _ in range(10)]))
    assert 0.4 < sum(values) / len(values) < 0.7
    assert stats.pbo([[1.0, 2.0]], [[1.0, 1.0]]) is None  # one contestant


# --- the calendar and the series ---------------------------------------------------------


def test_the_calendar_of_batch_1():
    cal = walkforward.make_calendar(
        datetime(2020, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 11, 6, 13, 30, tzinfo=timezone.utc),
    )
    folds = [(series_mod.iso(a), series_mod.iso(b)) for a, b in cal.folds]
    assert folds[0] == ("2021-01-01T00:00:00Z", "2021-04-01T00:00:00Z")
    assert folds[-1] == ("2025-04-01T00:00:00Z", "2025-05-06T13:00:00Z")
    assert len(folds) == 18
    assert all(b == a2 for (_a, b), (a2, _b) in zip(cal.folds, cal.folds[1:]))
    # the last 18 months are locked: long enough for R2 to be drawn on them
    assert series_mod.iso(cal.lockbox[0]) == "2025-05-06T13:00:00Z"
    assert series_mod.iso(cal.lockbox[1]) == "2026-11-06T13:00:00Z"
    d = baselines.min_shift_hours() * 3600
    assert cal.lockbox[1] - cal.lockbox[0] >= 2 * d
    assert walkforward.Calendar.from_dict(cal.to_dict()) == cal


def test_a_short_gap_is_kept_and_a_long_one_ends_the_earlier_part():
    df = with_gaps(walk(24 * 20, seed=1), (30, 24), (100, 3))
    s = series_mod.from_frame("BTC", "binance", "BTCUSDT", df)
    assert s.dropped is None and len(s) == 24 * 20 - 27
    assert [g[2] for g in s.gaps] == [24, 3]
    df = with_gaps(walk(24 * 20, seed=1), (30, 25), (100, 3))
    s = series_mod.from_frame("BTC", "binance", "BTCUSDT", df)
    assert s.first_open_s == int((START + pd.Timedelta(hours=55)).timestamp())
    assert [g[2] for g in s.gaps] == [3]
    assert s.sha256 == series_mod.bars_sha256(s)


def test_a_series_hash_is_the_trainers_candle_hash_of_the_same_bars():
    import pt_pattern_trainer as ppt

    df = walk(500, seed=4)
    s = series_mod.from_frame("BTC", "binance", "BTCUSDT", df)
    assert s.sha256 == ppt.candle_sha256(df)


def test_the_trade_table_is_the_gate_replay_from_every_hour():
    df = walk(24 * 60, seed=6, vol=0.01)
    s = series_mod.from_frame("BTC", "binance", "BTCUSDT", df)
    rules = model_gate.trade_rules({})
    table = TradeTable(s.close_s, s.close, rules, FEES)
    hours = model_gate.Hours(
        tuple(int(t) for t in s.close_s),
        tuple(float(p) for p in s.close),
        (None,) * len(s),
        (None,) * len(s),
    )
    assert table.fill() == len(s)
    for i in range(0, len(s), 7):
        assert table.trade(i) == model_gate.replay(i, hours, rules, FEES)
    ones = list(range(0, len(s), 5))
    entries = schedule(ones, table)
    free = 0
    for i, t in entries:
        assert i >= free
        free = max(t.end, i + 1)


# --- batches ----------------------------------------------------------------------------

RULES_ONLY = [c.key for c in catalogue.catalogue() if not c.trained]


def frozen_batch(days=420, coins=("BTC", "ETH"), keys=RULES_ONLY, draws=200):
    for k, coin in enumerate(coins):
        seed_1h(coin, walk(24 * days, seed=10 + k))
    return batch.freeze(
        list(coins),
        START,
        keys,
        end=START + pd.Timedelta(days=days),
        fees={c: FEES for c in coins},
        offline=True,
        draws=draws,
        months=(4, 2, 2),
        min_shift_days=30,
        now=START + pd.Timedelta(days=days, hours=5),
    )


def results_bytes(batch_id):
    with open(os.path.join(batch.batch_dir(batch_id), "results.json"), "rb") as f:
        return f.read()


def test_a_batch_run_twice_gives_identical_results():
    batch_id = frozen_batch()
    first = batch.run(batch_id)
    once = results_bytes(batch_id)
    second = batch.run(batch_id)
    assert results_bytes(batch_id) == once
    assert first == second
    assert batch.read_status(batch_id)["state"] == "done"
    assert set(first["contestants"]) == set(RULES_ONLY)
    always = first["contestants"]["ref.always"]
    assert always["verdict"] == "reference" and always["p"] is None
    for key in RULES_ONLY:
        r = first["contestants"][key]
        assert r["score"]["trades"] > 0, key
        if key != "ref.always":
            assert r["r1"]["runs"] == 200 and r["r2"]["runs"] == 200
            assert r["r2"]["coins"] == ["BTC", "ETH"]
            assert 0 < r["p"] <= 1 and r["p"] == max(r["p_r1"], r["p_r2"])
            assert r["verdict"] in batch.VERDICTS
    assert first["k"] == len(RULES_ONLY) - 1
    assert 0.0 <= first["pbo"] <= 1.0
    # every tested contestant is logged as a trial, once per run
    with open(batch.trials_path(), encoding="utf-8") as f:
        lines = [json.loads(x) for x in f]
    assert len(lines) == 2 * first["k"]
    assert batch.trial_count() == first["k"]
    assert {x["batch_sha256"] for x in lines} == {batch.read_batch(batch_id)["sha256"]}
    report = open(
        os.path.join(batch.batch_dir(batch_id), "report.md"), encoding="utf-8"
    ).read()
    assert "Daily close above its 20-day average (`rule.sma20`)" in report


def test_a_coin_listed_after_the_lockbox_starts_never_joins():
    """As BNB and HYPE on Coinbase in batch 1: no bar before the lockbox."""
    days = 420
    seed_1h("BTC", walk(24 * days, seed=10))
    late = walk(24 * 20, start=START + pd.Timedelta(days=days - 20), seed=11)
    seed_1h("BNB", late)
    # what an online read records for a pair listed late: no bars before its first
    candles._record_empty_from(
        candles.cache_path("BNBUSDT", "1h", candles.cache_dir_default(), "binance"),
        START,
        late["open_time"].iloc[0],
    )
    batch_id = batch.freeze(
        ["BTC", "BNB"],
        START,
        ["ref.always", "rule.sma20"],
        end=START + pd.Timedelta(days=days),
        fees={"BTC": FEES, "BNB": FEES},
        offline=True,
        draws=20,
        months=(4, 2, 2),
        min_shift_days=30,
        now=START + pd.Timedelta(days=days, hours=5),
    )
    record = batch.read_batch(batch_id)
    assert series_mod.epoch(record["series"]["BNB"]["first_open"]) > series_mod.epoch(
        record["calendar"]["lockbox"][0]
    )
    results = batch.run(batch_id)
    assert results["streams"]["BNB"] == {"hours": 0, "first": None, "last": None}
    for key in ("ref.always", "rule.sma20"):
        bnb = results["contestants"][key]["coins"]["BNB"]
        assert bnb["joined"] is None and bnb["trades"] == 0
        assert results["contestants"][key]["coins"]["BTC"]["trades"] > 0
    assert results["contestants"]["rule.sma20"]["r2_left_out"] == ["BNB"]
    report = open(
        os.path.join(batch.batch_dir(batch_id), "report.md"), encoding="utf-8"
    ).read()
    assert "| BNB | never | 0 |" in report
    # a trained contestant has no fold to fit it on either
    cal = walkforward.Calendar.from_dict(record["calendar"])
    empty = walkforward.make_stream(
        series_mod.from_frame("BNB", "binance", "BNBUSDT", late).cut(cal.lockbox[0]),
        cal,
        int(late["open_time"].iloc[0].timestamp()),
    )
    assert len(empty) == 0
    data = walkforward.LabData({}, model_gate.trade_rules({}), cal.start_s)
    d = walkforward.decide(contestants.Pattern(), data, cal, {"BNB": empty})["BNB"]
    assert (d.join, len(d.values), d.fits) == (0, 0, [])


def test_a_frozen_batch_whose_file_has_changed_is_refused():
    batch_id = frozen_batch(keys=["rule.sma20"], draws=20)
    path = os.path.join(batch.batch_dir(batch_id), "batch.json")
    record = json.load(open(path, encoding="utf-8"))
    record["draws"] = 10
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f)
    with pytest.raises(batch.BatchError, match="its file has changed"):
        batch.run(batch_id)
    assert not os.path.exists(os.path.join(batch.batch_dir(batch_id), "results.json"))
    assert batch.trial_count() == 0


def test_a_frozen_batch_whose_candles_or_code_changed_is_refused(monkeypatch):
    batch_id = frozen_batch(keys=["rule.sma20"], draws=20)
    path = candles.cache_path("ETHUSDT", "1h", candles.cache_dir_default(), "binance")
    df = pd.read_csv(path)
    df.loc[500, "close"] = df.loc[500, "close"] * 1.01
    df.to_csv(path, index=False)
    with pytest.raises(
        batch.BatchError, match="not the ones the batch was frozen with"
    ):
        batch.run(batch_id)
    assert batch.read_status(batch_id)["state"] == "refused"
    monkeypatch.setattr(batch, "code_hashes", lambda: {"model_lab/batch.py": "0"})
    with pytest.raises(batch.BatchError, match="code it runs has changed"):
        batch.run(batch_id)


def test_a_stopped_batch_keeps_its_record_and_says_so():
    batch_id = frozen_batch(keys=["rule.sma20", "rule.sma50"], draws=50)
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 30

    assert batch.run(batch_id, stop=stop) is None
    assert batch.read_status(batch_id)["state"] == "stopped"
    assert batch.read_batch(batch_id)["id"] == batch_id
    assert batch.read_results(batch_id) is None


def test_freezing_records_the_series_fees_seeds_and_pass_rule():
    batch_id = frozen_batch(keys=["rule.sma20"], draws=20)
    record = batch.read_batch(batch_id)
    assert record["coins"] == ["BTC", "ETH"]
    eth = record["series"]["ETH"]
    assert (eth["exchange"], eth["pair"]) == ("binance", "ETHUSDT")
    assert eth["why"] == "chosen for the batch"
    assert len(eth["sha256"]) == 64
    assert record["fees"]["ETH"] == FEES.to_dict()
    assert record["seeds"] == batch.SEEDS
    assert record["pass_rule"] == batch.PASS_RULE
    assert record["rules"] == model_gate.trade_rules({}).to_dict()
    assert set(record["code"]) >= {"model_lab/batch.py", "model_gate.py"}


def test_earlier_looks_mark_a_lockbox_seen_before():
    """The pattern model's results were looked at in FDS-MDL, the volume research, the
    gate diagnostic and the entry gate itself (section 5.7). With batch 1's calendar
    they cover its lockbox; nothing covers the rules' lockbox."""
    cal = walkforward.make_calendar(
        datetime(2020, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 11, 6, 13, 30, tzinfo=timezone.utc),
    )
    seen = catalogue.seen_in("pattern", *cal.lockbox)
    assert [look.start for look in seen] == [
        "2024-07-01",
        "2026-03-31",
        "2026-04-01",
        "2026-04-05",
    ]
    for key in RULES_ONLY:
        assert catalogue.seen_in(key, *cal.lockbox) == [], key
    # the phase B timing run read the walk-forward only: it ends where batch 1's
    # lockbox starts, and covers an earlier lockbox
    phase_b = [look for look in catalogue.looks("rule.btc50")]
    assert [(look.start, look.end) for look in phase_b] == [
        ("2021-01-01", "2025-05-06")
    ]
    earlier = (series_mod.epoch("2024-01-01"), series_mod.epoch("2024-07-01"))
    assert catalogue.seen_in("rule.btc50", *earlier) == phase_b
    # every look is a contestant in the catalogue, with dates in order
    known = catalogue.by_key()
    for look in catalogue.LOOKS:
        assert look.key in known
        assert series_mod.epoch(look.start) < series_mod.epoch(look.end)


def test_a_contestant_whose_lockbox_was_seen_is_never_a_plain_finalist():
    assert batch.verdict_code(False, True, False, True, False) == "passed"
    assert batch.verdict_code(False, True, True, True, False) == "passed_seen"
    assert batch.VERDICTS["passed_seen"] == (
        "Passed; its lockbox was seen before, so a final check would not be unseen "
        "evidence"
    )
    assert batch.verdict_code(True, True, True, True, True) == "worse"
    assert batch.verdict_code(False, False, True, True, True) == "screen"
    assert batch.verdict_code(False, False, True, False, True) == "too_few"
    assert batch.verdict_code(False, False, False, False, False) == "no_better"


def test_a_frozen_batch_records_each_contestants_earlier_looks():
    batch_id = frozen_batch(keys=["rule.sma20", "pattern"], draws=20)
    record = batch.read_batch(batch_id)
    by_key = {c["key"]: c for c in record["contestants"]}
    assert by_key["pattern"]["looks"] == [
        look.to_dict() for look in catalogue.looks("pattern")
    ]
    lock = [series_mod.epoch(t) for t in record["calendar"]["lockbox"]]
    for key in ("rule.sma20", "pattern"):
        assert by_key[key]["lockbox_seen"] == [
            look.to_dict() for look in catalogue.seen_in(key, *lock)
        ]
    assert by_key["pattern"]["lockbox_seen"]  # the fixture's lockbox is in 2024-25


def test_no_harness_file_names_an_exchange():
    folder = os.path.join(APP_DIR, "model_lab")
    names = re.compile(r"binance|coinbase|kraken|kucoin|robinhood", re.IGNORECASE)
    for name in os.listdir(folder):
        if name.endswith(".py"):
            text = open(os.path.join(folder, name), encoding="utf-8").read()
            assert not names.search(text), name


# --- the pattern contestant ----------------------------------------------------------------


def test_the_pattern_contestants_fold_1_entries_equal_the_trainers_sibling_fit():
    import pt_pattern_trainer as ppt

    hours = 1680
    start = START.to_pydatetime()
    end = start + timedelta(hours=hours)
    hourly = hc.synthetic_hourly(hours, START, seed=1, tick=0.5)
    hc.seed_cache(candles.cache_dir_default(), "BTCUSDT", hc.all_timeframes(hourly))
    _window, _metrics, sibling = ppt.validation_fit("BTC", start, end, 0, True)
    cut = sibling["cut"]
    loader = ppt.BarLoader(
        "BTC", max(start, cut - ppt.GATE_LOOKBACK), end, True, exchanges=["binance"]
    )
    frames = {}
    for tf_choice in ppt.TF_CHOICES:
        loader.bars(tf_choice)
        frames[ppt.CANDLE_TF[tf_choice]] = loader.frames[ppt.CANDLE_TF[tf_choice]]
    hours_ = model_gate.hourly_signals(
        sibling["model"], frames, int(cut.timestamp()), int(end.timestamp())
    )
    rules = model_gate.trade_rules({})
    expected = [
        -1 if n is None else int(n >= rules.trade_start_level and m == 0)
        for n, m in zip(hours_.longs, hours_.shorts)
    ]
    assert expected.count(1) > 0 and expected.count(0) > 0

    data = walkforward.LabData(
        {"BTC": series_mod.load("BTC", start, end, offline=True)},
        rules,
        int(start.timestamp()),
        offline=True,
        seed=0,
    )
    cut_s, end_s = int(cut.timestamp()), int(end.timestamp())
    cal = walkforward.Calendar(
        int(start.timestamp()), end_s, ((cut_s, end_s),), (end_s, end_s), 0, 0, 0
    )
    stream = walkforward.make_stream(data.series["BTC"], cal)
    assert list(stream.close_s) == list(hours_.close_s)
    pattern = contestants.Pattern()
    pattern.history_days = 0  # the fixture is ten weeks long
    decided = walkforward.decide(pattern, data, cal, {"BTC": stream})["BTC"]
    assert decided.values.tolist() == expected
    assert decided.longs == list(hours_.longs)
    assert decided.fits[0]["files_sha256"] == sibling["files"]
    assert decided.fits[0]["fit_end"] == series_mod.iso(cut_s)


def test_a_batch_with_the_pattern_model_runs_end_to_end(monkeypatch):
    hourly = hc.synthetic_hourly(24 * 150, START, seed=1, tick=0.5)
    hc.seed_cache(candles.cache_dir_default(), "BTCUSDT", hc.all_timeframes(hourly))
    # the fixture is five months long: shorter histories than batch 1's
    monkeypatch.setattr(contestants.Pattern, "history_days", 30)
    monkeypatch.setattr(walkforward, "RULE_HISTORY_DAYS", 30)
    batch_id = batch.freeze(
        ["BTC"],
        START,
        ["rule.sma20", "pattern"],
        end=START + pd.Timedelta(days=150),
        fees={"BTC": FEES},
        offline=True,
        draws=50,
        months=(2, 1, 1),
        min_shift_days=10,
        now=START + pd.Timedelta(days=151),
    )
    results = batch.run(batch_id)
    r = results["contestants"]["pattern"]
    cal = batch.read_batch(batch_id)["calendar"]
    assert [f["fit_end"] for f in r["fits"]["BTC"]] == [a for a, _b in cal["folds"]]
    assert [f["fold"] for f in r["fits"]["BTC"]] == [1, 2]
    assert r["score"]["trades"] > 0
    assert r["neural_dca"]["r1"]["runs"] == batch.NEURAL_DCA_DRAWS
    assert r["best_rule"]["key"] == "rule.sma20"
    assert set(r["conditions"]) == {
        "profit_above_0",
        "trades",
        "drawdown",
        "pbo",
        "above_best_rule",
    }
    assert r["verdict"] in batch.VERDICTS
    assert results["tested"] == ["rule.sma20", "pattern"]


def test_a_coin_joins_the_pattern_stream_once_it_has_12_months_of_bars():
    cal = walkforward.make_calendar(
        datetime(2020, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 11, 6, tzinfo=timezone.utc),
    )
    late = int(datetime(2025, 10, 22, tzinfo=timezone.utc).timestamp())
    early = int(datetime(2019, 6, 1, tzinfo=timezone.utc).timestamp())
    stream = walkforward.Stream("BNB", np.array([]), np.array([]), np.array([]), late)
    assert walkforward.usable_folds(stream, cal, 365) == []
    stream = walkforward.Stream("BTC", np.array([]), np.array([]), np.array([]), early)
    assert walkforward.usable_folds(stream, cal, 365) == list(range(len(cal.folds)))
    mid = int(datetime(2020, 6, 1, tzinfo=timezone.utc).timestamp())
    stream = walkforward.Stream("SOL", np.array([]), np.array([]), np.array([]), mid)
    first = walkforward.usable_folds(stream, cal, 365)[0]
    assert series_mod.iso(cal.folds[first][0]) == "2021-07-01T00:00:00Z"
