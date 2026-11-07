"""The model lab's trained contestants (FDS-MH-001 phase C, as amended by amendment 1).

Phase C's tests (section 8):
* feature look-ahead: a feature at an hour from bars cut there equals it from all bars;
* T1 on hand-built paths: up first, down first, both in one bar, neither;
* the purge removes exactly the rows whose label crosses the fold;
* thresholds come from training rows only: changing a held-out bar changes neither the
  fit nor the threshold.

Amendment 1's tests (section 8, phase C):
* ``BATCH_1`` is section 7's list, whatever the catalogue holds;
* the seven rules and the pattern model give the same results as before amendment 1
  (``fixtures/model_lab_phase_b_golden.json``, made with main's code at e0d837a);
* a trial line without ``kind`` reads as "trading";
* the placebo's timing: encoded source hours, poisoning at the boundaries, the missing
  span at a series' start and after a long gap, the declared lags;
* PV-1's contestants use identical row sets; the look-ahead test passes for the placebo;
* P has 25 features, P with v1 is batch 1's 26, and no block holds a round-one candidate;
* the 10-run report's runs pool to the batch's p-value exactly.

All candles are synthetic and read offline (no network)."""

import json
import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for _path in (APP_DIR, TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

pytest.importorskip("sklearn")

import model_gate  # noqa: E402
from model_lab import batch, catalogue, contestants  # noqa: E402
from model_lab import features as ft  # noqa: E402
from model_lab import series as series_mod  # noqa: E402
from model_lab import targets as tg  # noqa: E402
from model_lab import walkforward  # noqa: E402
from test_model_lab import (  # noqa: E402,F401  (layer: the autouse fixture)
    FEES,
    START,
    candles,
    frozen_batch,
    hc,
    layer,
    seed_1h,
    walk,
    with_gaps,
)

HOUR = 3600
GOLDEN = os.path.join(TESTS_DIR, "fixtures", "model_lab_phase_b_golden.json")


def series_of(coin, df):
    return series_mod.from_frame(coin, "binance", f"{coin}USDT", df)


def data_of(frames, start=START):
    data = walkforward.LabData(
        {c: series_of(c, df) for c, df in frames.items()},
        model_gate.trade_rules({}),
        int(start.timestamp()),
    )
    data.fees = {c: FEES for c in frames}
    return data


# --- the declared batches ---------------------------------------------------------------


def test_batch_1_is_section_7s_list_whatever_the_catalogue_holds(monkeypatch):
    assert catalogue.BATCH_1 == [
        "ref.always",
        "rule.sma20",
        "rule.sma50",
        "rule.sma100",
        "rule.mom14",
        "rule.high20",
        "rule.btc50",
        "rule.dip24",
        "pattern",
        "linear.t1.q50",
        "linear.t1.q20",
        "trees.t1.q50",
        "trees.t1.q20",
        "trees.t2.q50",
        "trees.t2.q20",
    ]
    known = catalogue.by_key()
    assert all(k in known for k in catalogue.BATCH_1 + catalogue.BATCH_PV_1)
    tested = [k for k in catalogue.BATCH_1 if known[k].tested]
    assert len(tested) == 14  # K = 14
    # a contestant added to the catalogue joins no declared batch
    before = list(catalogue.BATCH_1), list(catalogue.BATCH_PV_1)
    extra = contestants.Model("linear", "t1", 0.3)
    original = catalogue.catalogue
    monkeypatch.setattr(catalogue, "catalogue", lambda: original() + [extra])
    assert "linear.t1.q30" in catalogue.by_key()
    assert (catalogue.BATCH_1, catalogue.BATCH_PV_1) == before
    assert catalogue.DECLARED["batch-1"] == ("1", catalogue.BATCH_1)
    assert catalogue.DECLARED["pv-1"] == ("1.1", catalogue.BATCH_PV_1)


def test_pv_1_is_section_7as_three_and_the_placebos_variants():
    known = catalogue.by_key()
    tested = [k for k in catalogue.BATCH_PV_1 if known[k].tested]
    assert tested == [
        "pv.linear.t1.P.q50",
        "pv.linear.t1.PV.q50",
        "pv.linear.t1.PVp.q50",
    ]  # K = 3
    for key in catalogue.BATCH_PV_1:
        c = known[key]
        assert (c.family, c.target, c.q, c.common_rows) == ("linear", "t1", 0.5, True)
        assert c.forecast_only == (key not in tested)
    assert known["pv.linear.t1.P.q50"].names == ft.P
    assert known["pv.linear.t1.PV.q50"].names == ft.P + ft.V
    lag = ft.PLACEBO_LAGS[0]
    assert known["pv.linear.t1.PVp.q50"].names == ft.P + ft.placebo_names(lag)
    # the look at v2 is recorded for the contestants that use it, and only them
    for key in catalogue.BATCH_PV_1:
        seen = [look.start for look in catalogue.looks(key)]
        assert seen == (["2023-11-06"] if key in tested[1:] else []), key
    for key in catalogue.BATCH_1:
        assert all(look.start != "2023-11-06" for look in catalogue.looks(key))


def test_a_declared_batch_must_be_frozen_with_its_own_contestants():
    with pytest.raises(batch.BatchError, match="declared"):
        frozen_batch_for(["pv.linear.t1.P.q50"], declared="pv-1")
    with pytest.raises(batch.BatchError, match="no declared batch"):
        frozen_batch_for(["rule.sma20"], declared="batch-9")


def frozen_batch_for(keys, declared=None, days=420, coins=("BTC", "ETH"), draws=20):
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
        months=(8, 2, 2),
        min_shift_days=30,
        now=START + pd.Timedelta(days=days, hours=5),
        declared=declared,
    )


# --- batch 1 unchanged --------------------------------------------------------------------


def _close(a, b, path=""):
    if isinstance(a, dict):
        assert isinstance(b, dict) and sorted(a) == sorted(b), path
        for k in a:
            _close(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            _close(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and isinstance(b, float):
        assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12), (path, a, b)
    else:
        assert a == b, (path, a, b)


def test_the_rules_and_the_pattern_model_give_the_results_they_gave_before(
    monkeypatch,
):
    """The phase B fixture batches against their results from main's code (before
    amendment 1). On the machine that made the fixture the bytes are identical
    (RUN-LOG-mh-1.md, phase C); here floats may differ in their last bits across
    platforms, so they are compared to 1e-9."""
    golden = json.load(open(GOLDEN, encoding="utf-8"))
    strip = ("batch", "batch_sha256")

    rules_id = frozen_batch()
    rules = batch.run(rules_id)
    _close(golden["rules_only"], {k: v for k, v in rules.items() if k not in strip})
    assert "probabilities" not in rules  # no new key for an old contestant

    hourly = hc.synthetic_hourly(24 * 150, START, seed=1, tick=0.5)
    hc.seed_cache(candles.cache_dir_default(), "BTCUSDT", hc.all_timeframes(hourly))
    monkeypatch.setattr(contestants.Pattern, "history_days", 30)
    monkeypatch.setattr(walkforward, "RULE_HISTORY_DAYS", 30)
    pattern_id = batch.freeze(
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
    pattern = batch.run(pattern_id)
    _close(golden["pattern"], {k: v for k, v in pattern.items() if k not in strip})


def test_a_trial_line_without_a_kind_is_a_trading_trial():
    os.makedirs(batch.lab_dir(), exist_ok=True)
    with open(batch.trials_path(), "w", encoding="utf-8") as f:
        f.write(json.dumps({"trial": "old/rule.sma20", "p": 0.5}) + "\n")
        f.write(json.dumps({"trial": "x/pv", "kind": "forecast"}) + "\n")
        f.write(json.dumps({"trial": "x/pv", "kind": "forecast"}) + "\n")
    assert batch.trial_counts() == {"trading": 1, "forecast": 1}
    assert batch.trial_count() == 2
    batch.log_trial({"trial": "y/m", "kind": "decision"})
    assert batch.trial_counts()["decision"] == 1
    with pytest.raises(ValueError):
        batch.log_trial({"trial": "z", "kind": "guess"})


def test_the_ten_runs_pool_to_the_batchs_p_value_exactly():
    batch_id = frozen_batch(keys=["rule.sma20", "rule.sma50"], draws=200)
    results = batch.run(batch_id)
    runs = json.load(
        open(os.path.join(batch.batch_dir(batch_id), "runs.json"), encoding="utf-8")
    )
    for key in ("rule.sma20", "rule.sma50"):
        r = results["contestants"][key]
        for name, p in (("r1", r["p_r1"]), ("r2", r["p_r2"])):
            split = runs[key][name]
            assert len(split["runs"]) == 10
            assert sum(x["draws"] for x in split["runs"]) == r[name]["runs"]
            assert split["pooled_p"] == p
            exceed = sum(x["exceed"] for x in split["runs"])
            assert (1 + exceed) / (r[name]["runs"] + 1) == p
    report = open(
        os.path.join(batch.batch_dir(batch_id), "report.md"), encoding="utf-8"
    ).read()
    assert "R1 as 10 runs of 20 draws" in report
    assert "Spec version 1.1." in report


# --- features ------------------------------------------------------------------------------


def test_the_blocks_p_has_25_p_with_v1_is_batch_1s_26_and_no_round_one_candidate():
    assert len(ft.P) == 25 and len(ft.FEATURES_26) == 26
    assert set(ft.P) | {"v1"} == set(ft.FEATURES_26)
    assert ft.block_names(["P", "V"]) == ft.P + ("v1", "v2")
    assert catalogue.get("linear.t1.q50").names == ft.FEATURES_26
    names = set(ft.FEATURES_26) | set(ft.V)
    for lag in ft.PLACEBO_LAGS:
        names |= set(ft.placebo_names(lag))
    assert not [n for n in names if "cmf" in n.lower() or "money" in n.lower()]
    assert "btc_r1" not in names  # BTC's one-hour return (round one's SIG-B)


def test_every_feature_from_bars_cut_at_an_hour_equals_it_from_all_bars():
    hours = 24 * 120
    eth = with_gaps(walk(hours, seed=2), (1500, 1), (2000, 6), (2600, 20))
    full = {"BTC": series_of("BTC", walk(hours, seed=1)), "ETH": series_of("ETH", eth)}
    whole = ft.build(full["ETH"], full["BTC"])
    rng = np.random.default_rng(5)
    picks = sorted(rng.choice(np.nonzero(whole.grid.present)[0], 40, replace=False))
    picks += [1500, 1501, 2006, 2007, 2626, 2627, len(whole.grid) - 1]
    names = list(ft.FEATURES_26) + ["v2"] + list(ft.placebo_names(ft.PLACEBO_LAGS[2]))
    for k in picks:
        if not whole.grid.present[k]:
            continue
        t = int(whole.grid.close_s[k])
        cut = ft.build(full["ETH"].cut(t), full["BTC"].cut(t))
        assert int(cut.grid.close_s[-1]) == t
        a = whole.matrix(names)[k]
        b = cut.matrix(names)[-1]
        assert np.array_equal(np.isnan(a), np.isnan(b)), (k, t)
        assert np.allclose(a[~np.isnan(a)], b[~np.isnan(b)], rtol=0, atol=1e-12), k
    # once the longest look-back has passed, every feature exists on a series with no
    # gap, and most do on one with gaps (a return is missing when its earlier bar is)
    btc = ft.build(full["BTC"], full["BTC"]).complete(ft.FEATURES_26 + ("v2",))
    assert btc[1200:].all()
    late = whole.complete(ft.FEATURES_26 + ("v2",))
    assert late[1300:].mean() > 0.8


def test_constant_volume_gives_zero_volume_features_and_a_flat_bar_zero_wicks():
    df = walk(24 * 60, seed=3)
    df["volume"] = 5.0
    df.loc[1000, ["open", "high", "low", "close"]] = df.loc[999, "close"]
    t = ft.build(series_of("ETH", df), None)
    v1, v2 = t.column("v1"), t.column("v2")
    assert np.nanmax(np.abs(v1)) < 1e-12 and np.nanmax(np.abs(v2)) < 1e-12
    # v1 needs 30 completed days: the close at 00:00 that ends day 30 is hour 719
    assert np.isnan(v1[:719]).all() and np.isfinite(v1[719:]).all()
    assert np.isnan(v2[:480]).all() and np.isfinite(v2[480:]).all()
    assert [t.column(n)[1000] for n in ("body", "wick_up", "wick_down")] == [0, 0, 0]


def test_an_invalid_bar_is_a_missing_hour():
    df = walk(24 * 30, seed=4)
    df.loc[100, "low"] = 0.0
    df.loc[200, "high"] = df.loc[200, "low"] * 0.9
    df.loc[300, "close"] = df.loc[300, "high"] * 1.1
    df.loc[400, "volume"] = -1.0
    g = ft.grid(series_of("ETH", df))
    assert not g.present[[100, 200, 300, 400]].any()
    assert g.present.sum() == len(df) - 4


# --- the placebo ----------------------------------------------------------------------------


def test_the_declared_lags_come_from_their_seeds():
    assert ft.PLACEBO_LAGS == (3930, 4076, 3850, 4062, 3857)
    for lag in ft.PLACEBO_LAGS:
        assert 3841 <= lag <= 4079 and lag % 24 != 0
    assert ft.placebo_lags() == ft.PLACEBO_LAGS


def _encoded(n, start=START):
    """A table whose V values are each hour's own close time (an encoded source)."""
    s = series_of("ETH", walk(n, start=start, seed=6))
    t = ft.build(s, None)
    stamp = t.grid.close_s.astype(float)
    t.values["v1"] = np.where(t.grid.present, stamp, np.nan)
    t.values["v2"] = np.where(t.grid.present, stamp, np.nan)
    return t


def test_with_encoded_sources_every_placebo_value_is_its_own_hour_minus_its_lag():
    t = _encoded(24 * 200)
    close = t.grid.close_s
    for lag in ft.PLACEBO_LAGS:
        for name in ft.placebo_names(lag):
            col = t.column(name)
            assert np.isnan(col[:lag]).all()  # the series' start: missing, no wrap
            got = col[lag:]
            assert np.array_equal(got, (close[lag:] - lag * HOUR).astype(float))
            assert (got < close[lag:]).all()  # never at or after the row's own hour
            assert (close[lag:] - got >= 160 * 24 * HOUR).all()  # at least D earlier


def test_the_placebo_is_missing_after_a_long_gap_and_never_read_across_it():
    """A gap longer than 24 hours ends the earlier part of a series (series): the
    placebo starts again, lag hours after the gap, from bars after it only."""
    before = walk(24 * 100, seed=7)
    after = walk(24 * 260, start=START + pd.Timedelta(days=101, hours=6), seed=8)
    df = pd.concat([before, after], ignore_index=True)
    s = series_of("ETH", df)
    assert s.first_open_s == int(after["open_time"].iloc[0].timestamp())
    t = ft.build(s, None)
    for lag in ft.PLACEBO_LAGS:
        col = t.column(f"v1@{lag}h")
        assert np.isnan(col[:lag]).all()
    # the first common row is the longest lag after V's own first hour, which comes
    # after the gap: nothing from before the gap is read
    common = ft.common_mask(t)
    first = int(np.nonzero(common)[0][0])
    v_ok = np.isfinite(t.column("v1")) & np.isfinite(t.column("v2"))
    first_v = int(np.nonzero(v_ok)[0][0])
    assert 719 <= first_v <= 743  # v1's 30 completed days, from the series' start
    assert first == first_v + max(ft.PLACEBO_LAGS)


def test_corrupting_every_bar_after_an_hour_changes_no_placebo_value_up_to_it():
    hours = 24 * 230
    base = walk(hours, seed=9)
    s = series_of("ETH", base)
    whole = ft.build(s, None)
    names = [n for lag in ft.PLACEBO_LAGS for n in ft.placebo_names(lag)]
    first_common = int(np.nonzero(ft.common_mask(whole))[0][0])
    rng = np.random.default_rng(1)
    for k in (first_common, first_common + 1, hours // 2, hours - 2):
        poisoned = base.copy()
        tail = slice(k + 1, None)
        for col in ("open", "high", "low", "close"):
            poisoned.loc[poisoned.index[tail], col] *= rng.uniform(
                0.5, 2.0, hours - k - 1
            )
        poisoned.loc[poisoned.index[tail], "high"] = poisoned.loc[
            poisoned.index[tail], ["open", "high", "low", "close"]
        ].max(axis=1)
        poisoned.loc[poisoned.index[tail], "low"] = poisoned.loc[
            poisoned.index[tail], ["open", "high", "low", "close"]
        ].min(axis=1)
        poisoned.loc[poisoned.index[tail], "volume"] *= 1000.0
        other = ft.build(series_of("ETH", poisoned), None)
        a = whole.matrix(names)[: k + 1]
        b = other.matrix(names)[: k + 1]
        assert np.array_equal(np.isnan(a), np.isnan(b)), k
        assert np.array_equal(a[~np.isnan(a)], b[~np.isnan(b)]), k


# --- targets ---------------------------------------------------------------------------------


def _path_grid(prices_hl, start_price=100.0):
    """A grid from (high, low) pairs after an entry bar closing at ``start_price``."""
    n = len(prices_hl) + 1
    rows = {
        "open_time": pd.date_range(START, periods=n, freq="h", tz="UTC"),
        "open": [start_price] * n,
        "high": [start_price] + [h for h, _ in prices_hl],
        "low": [start_price] + [lo for _, lo in prices_hl],
        "close": [start_price] + [(h + lo) / 2 for h, lo in prices_hl],
        "volume": [1.0] * n,
    }
    for i in range(1, n):
        rows["open"][i] = rows["close"][i - 1]
        rows["high"][i] = max(rows["high"][i], rows["open"][i])
        rows["low"][i] = min(rows["low"][i], rows["open"][i])
    return ft.grid(series_of("ETH", pd.DataFrame(rows)))


def test_t1_on_hand_built_paths():
    rules = model_gate.trade_rules({})
    up, down = tg.t1_barriers(np.array([100.0]), rules, FEES)
    u, d = float(up[0]), float(down[0])
    assert math.isclose(u, 100 * 1.0005 / 0.995 * 1.05)
    assert math.isclose(d, 100 * 1.0005 / 0.995 * 0.975)
    flat = (100.2, 99.9)
    cases = {
        "up first": [flat] * 5 + [(u + 0.1, 100.0)] + [(100.0, d - 1)] * 3,
        "down first": [flat] * 5 + [(100.0, d - 0.1)] + [(u + 1, 100.0)] * 3,
        "both in one bar": [flat] * 5 + [(u + 0.1, d - 0.1)] + [(u + 1, 100.0)] * 3,
        "neither": [flat] * 400,
    }
    expected = {
        "up first": 1.0,
        "down first": 0.0,
        "both in one bar": 0.0,
        "neither": 0.0,
    }
    for name, path in cases.items():
        g = _path_grid(path)
        label, end = tg.t1(g, rules, FEES)
        assert label[0] == expected[name], name
        assert end[0] == (336 if name == "neither" else 6), name
    # not enough hours left and no hit: unresolved
    label, end = tg.t1(_path_grid([flat] * 100), rules, FEES)
    assert np.isnan(label[0]) and end[0] == -1


def test_t2_is_the_replayed_trade_on_the_next_720_hours():
    rules = model_gate.trade_rules({})
    df = walk(24 * 60, seed=12, vol=0.01)
    g = ft.grid(series_of("ETH", df))
    label, end = tg.t2(g, rules, FEES)
    k = 100
    sub = model_gate.Hours(
        tuple(int(x) for x in g.close_s[k : k + 721]),
        tuple(float(x) for x in g.close[k : k + 721]),
        (None,) * 721,
        (None,) * 721,
    )
    trade = model_gate.replay(0, sub, rules, FEES)
    assert math.isclose(label[k], trade.net / trade.capital_days)
    assert end[k] == k + trade.end
    # the last hours, whose trades are still open when the grid ends, are unresolved
    assert np.isnan(label[-5:]).any()


def test_the_purge_removes_exactly_the_rows_whose_label_crosses_the_fold():
    g = ft.grid(series_of("ETH", walk(24 * 60, seed=13)))
    label = np.zeros(len(g))
    until = int(g.close_s[1000])
    for target, h in (("t1", 336), ("t2", 720)):
        ok = tg.usable(g, label, until, target)
        assert ok[: 1000 - h + 1].all() and not ok[1000 - h + 1 :].any()


def test_uniqueness_on_a_hand_checked_case():
    # spans [0, 3] and [2, 5]: hours 2 and 3 are shared
    rows = np.array([0, 2])
    end = np.array([3, 0, 5, 0, 0, 0])
    u = tg.uniqueness(rows, end, 6)
    assert np.allclose(u, [(1 + 1 + 0.5 + 0.5) / 4, (0.5 + 0.5 + 1 + 1) / 4])


# --- fits -------------------------------------------------------------------------------------


def _frames(days, seeds=(21, 22)):
    return {
        coin: walk(24 * days, seed=s, vol=0.008)
        for coin, s in zip(("BTC", "ETH"), seeds)
    }


def test_thresholds_come_from_training_rows_only():
    frames = _frames(150)
    data = data_of(frames)
    until = int((START + pd.Timedelta(days=120)).timestamp())
    poisoned = {}
    for coin, df in frames.items():
        df = df.copy()
        late = df["open_time"] >= pd.Timestamp(until, unit="s", tz="UTC")
        df.loc[late, ["open", "high", "low", "close"]] *= 3.0
        df.loc[late, "volume"] *= 50.0
        poisoned[coin] = df
    other = data_of(poisoned)
    for key in ("linear.t1.q50", "trees.t1.q20"):
        c = catalogue.get(key)
        a, b = c.fit(data, until), c.fit(other, until)
        assert a.rows > 0 and a.rows == b.rows and a.rows_sha256 == b.rows_sha256
        assert a.threshold == b.threshold, key
        x = c.matrix(data, "ETH")[c.rows_mask(data, "ETH")][:50]
        assert np.array_equal(c.score(a, x), c.score(b, x)), key


def test_a_fit_reads_its_features_only_up_to_each_hour():
    """The phase B look-ahead test for a trained contestant: a frozen fit's entries at an
    hour, with its data cut there, equal its entries with all the data."""
    frames = _frames(150)
    data = data_of(frames)
    until = int((START + pd.Timedelta(days=100)).timestamp())
    fit = catalogue.get("linear.t1.q50").fit(data, until)
    close_s = data.series["ETH"].close_s
    full = fit.entries("ETH", close_s)
    assert {0, 1} <= set(full.tolist())
    for p in (2600, 2800, 3000, len(close_s) - 1):
        t = int(close_s[p])
        cut = walkforward.LabData(
            {c: s.cut(t) for c, s in data.series.items()}, data.rules, data.start_s
        )
        cut.fees = data.fees
        fit.data = cut
        assert fit.entries("ETH", [t])[0] == full[p], p
        fit.data = data


# --- batch PV-1, end to end -------------------------------------------------------------------


def test_a_pv_1_batch_runs_end_to_end_on_common_rows():
    batch_id = frozen_batch_for(catalogue.BATCH_PV_1, declared="pv-1", draws=50)
    record = batch.read_batch(batch_id)
    assert (record["declared"], record["spec_version"]) == ("pv-1", "1.1")
    assert record["libraries"]["scikit-learn"]
    results = batch.run(batch_id)
    assert results["k"] == 3
    assert results["tested"] == catalogue.BATCH_PV_1[:3]
    for key in catalogue.BATCH_PV_1[3:]:
        r = results["contestants"][key]
        assert r["verdict"] == "forecast_only" and "score" not in r
    # every PV-1 contestant fitted on the same rows in every fold
    by_fold = {}
    for key in catalogue.BATCH_PV_1:
        for coin, fits in results["contestants"][key]["fits"].items():
            for f in fits:
                by_fold.setdefault((coin, f["fold"]), set()).add(f["rows_sha256"])
                assert f["training_rows"] > 0
    assert by_fold and all(len(v) == 1 for v in by_fold.values())
    # probabilities are saved for every contestant, on the same common hours
    assert results["probabilities"] == catalogue.BATCH_PV_1
    decided = None
    for key in catalogue.BATCH_PV_1:
        probs = batch.read_probabilities(batch_id, key)
        here = {c: np.isfinite(p) for c, (_t, p) in probs.items()}
        for c, (_t, p) in probs.items():
            assert ((p[here[c]] > 0) & (p[here[c]] < 1)).all()
        if decided is None:
            decided = here
        for c in here:
            assert np.array_equal(here[c], decided[c]), (key, c)
    assert any(v.any() for v in decided.values())
    # a coin joins at its first decided hour: here the stream's first, because the
    # fixture's common rows start (about day 200) before fold 1 (month 8)
    r = results["contestants"]["pv.linear.t1.P.q50"]
    assert r["coins"]["ETH"]["joined"] == results["streams"]["ETH"]["first"]
    with open(batch.trials_path(), encoding="utf-8") as f:
        lines = [json.loads(x) for x in f]
    assert {x["kind"] for x in lines} == {"trading"}
    assert len(lines) == 3


def test_a_batch_with_batch_1s_trained_contestants_runs():
    batch_id = frozen_batch_for(
        ["rule.sma20", "linear.t1.q50", "trees.t1.q50", "trees.t2.q50"],
        days=330,
        coins=("BTC",),
        draws=20,
    )
    results = batch.run(batch_id)
    for key in ("linear.t1.q50", "trees.t1.q50", "trees.t2.q50"):
        r = results["contestants"][key]
        assert r["verdict"] in batch.VERDICTS
        assert r["fits"]["BTC"] and r["fits"]["BTC"][0]["training_rows"] > 0
        assert r["best_rule"]["key"] == "rule.sma20"
    # T1's contestants give probabilities; T2's do not
    assert set(results["probabilities"]) == {"linear.t1.q50", "trees.t1.q50"}


def test_a_trained_batch_is_refused_when_scikit_learn_has_changed(monkeypatch):
    batch_id = frozen_batch_for(["linear.t1.q50"], days=330, coins=("BTC",))
    real = batch.libraries()
    monkeypatch.setattr(batch, "libraries", lambda: {**real, "scikit-learn": "0.0"})
    with pytest.raises(batch.BatchError, match="scikit-learn has changed"):
        batch.run(batch_id)
