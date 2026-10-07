"""
FDS-MDL Phase 4 code (docs/dev/BACKTEST-REPORT-model-1.md): the random-entry baseline,
the evaluation rules, STRAT-003's activity indicators and the run script.

Fixtures only: synthetic bars and crafted models in the per-test store; no network, no
real trainer, no backtest of real data.
"""

import importlib.util
import json
import math
import os
import random
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
REPO = os.path.dirname(APP_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

import helpers_candles as hc  # noqa: E402
import helpers_strat003 as h3  # noqa: E402
import helpers_trainer as ht  # noqa: E402
import pattern_model  # noqa: E402
from backtest import model_eval as me  # noqa: E402
from backtest import random_baseline as rb  # noqa: E402
from backtest.engine import CostModel, run_backtest  # noqa: E402
from market_data import candles  # noqa: E402

SCRIPT = os.path.join(REPO, "docs", "dev", "run_backtest_model1.py")
BATCH1 = os.path.join(REPO, "docs", "dev", "backtest-batch-1")
TFS = pattern_model.TIMEFRAMES
START = "2024-01-01"  # a Monday: weekly bars are whole from the start


@pytest.fixture(autouse=True)
def guarded(monkeypatch, tmp_path, isolated_user_dirs):
    monkeypatch.chdir(tmp_path)
    return ht.guard_trainer_children(monkeypatch, tmp_path)


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("run_backtest_model1", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclass looks itself up there
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[spec.name]
        raise
    yield module
    sys.modules.pop(spec.name, None)


def _setsize(k):
    """CPython's threshold between random.sample's pool and set paths."""
    size = 21
    if k > 5:
        size += 4 ** math.ceil(math.log(k * 3, 4))
    return size


def _hourly(hours=24 * 7 * 6, seed=1):
    return hc.synthetic_hourly(hours, START, seed=seed)


# --- placement ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "seed, shape, path, first, last, digest",
    [
        (
            0,
            (9857, 100, 20),
            "set",
            [10, 136, 372, 571, 596, 705],
            [9453, 9483, 9505],
            "6e1c38ca2d11f12a79d058752298d7c4daf078105ed717d455984e404fb6a13a",
        ),
        (
            100,
            (2465, 500, 3),
            "pool",
            [3, 7, 12, 17, 22, 27],
            [2451, 2455, 2459],
            "7c4e0c320a343cb51715d0bba41d78660e27cae19fe8a47d04e30ea6a0b3fcb8",
        ),
    ],
    ids=["seed-0-set-path", "seed-100-pool-path"],
)
def test_pinned_placements_on_both_sample_paths(seed, shape, path, first, last, digest):
    """Acceptance 8 (reproducible by seed), pinned on each of random.sample's code
    paths: a change in Python's random fails here instead of changing the control."""
    import hashlib

    length, n, h = shape
    population = length - 1 - n * (h + 1) + n
    assert ("pool" if population <= _setsize(n) else "set") == path
    entries = rb.placement(seed, length, n, h)
    assert len(entries) == n and entries[:6] == first and entries[-3:] == last
    assert hashlib.sha256(json.dumps(entries).encode()).hexdigest() == digest


def test_placements_fit_and_never_overlap():
    rng = random.Random(7)
    for _ in range(300):
        h = rng.randint(1, 6)
        n = rng.randint(1, 12)
        length = n * (h + 1) + 1 + rng.randint(0, 30)
        entries = rb.placement(rng.randint(0, 10_000), length, n, h)
        assert len(entries) == n and entries[0] >= 1  # no decision before bar 0
        assert all(b - a >= h + 1 for a, b in zip(entries, entries[1:]))
        assert entries[-1] + h <= length - 1  # every exit fills by the last bar


def test_every_placement_is_reachable_and_about_equally_likely():
    length, n, h = 9, 2, 2  # slack 2: C(4, 2) = 6 placements
    counts = {}
    for seed in range(6000):
        key = tuple(rb.placement(seed, length, n, h))
        counts[key] = counts.get(key, 0) + 1
    assert len(counts) == 6
    assert all(850 <= c <= 1150 for c in counts.values()), counts


def test_a_placement_that_cannot_fit_is_refused():
    with pytest.raises(ValueError):
        rb.placement(0, 10, 5, 1)  # 5 x 2 > 9


def _trades(*held):
    return [SimpleNamespace(bars_held=b) for b in held]


def test_match_counts_every_trade_and_rounds_halves_up():
    assert rb.match([]) == (0, None)
    assert rb.match(_trades(2, 3)) == (2, 3)  # 2.5 -> 3 (round() would give 2)
    assert rb.match(_trades(1, 2, 2, 2)) == (4, 2)  # 1.75 -> 2
    assert rb.match(_trades(0)) == (1, 1)  # a trade closed on its entry bar: at least 1


def test_fit_hold_lowers_h_until_the_trades_fit_or_gives_up():
    assert rb.fit_hold(3, 2, 12) == (2, False)
    assert rb.fit_hold(3, 5, 12) == (2, True)  # 3 x 6 > 11 ... 3 x 3 <= 11
    assert rb.fit_hold(6, 1, 12) == (None, True)  # 6 x 2 > 11 even at H = 1


def test_percentile_rank_counts_ties_half():
    assert rb.percentile_rank(5.0, [1.0, 5.0, 5.0, 9.0]) == 50.0
    assert rb.percentile_rank(10.0, [1.0] * 100) == 100.0
    assert rb.percentile_rank(1.0, [1.0] * 100) == 50.0
    assert rb.percentile_rank(0.0, [1.0, 2.0]) == 0.0


# --- the random strategy through the engine ---------------------------------------------------


def test_without_overlays_a_seed_makes_exactly_n_trades_of_h_bars():
    hourly = _hourly(400)
    start, end, n, h = 50, 350, 10, 7
    entries = rb.placement(3, end - start, n, h)
    runner = rb.random_runner(hourly, start, entries, h)
    result = run_backtest(hourly, runner, "BTCUSDT", "1h", start, end, CostModel())
    times = hourly["open_time"]
    assert [t.entry_time for t in result.trades] == [
        times.iloc[start + e] for e in entries
    ]
    assert all(t.bars_held == h for t in result.trades)
    assert not any(t.forced_close for t in result.trades)
    record = rb.run_seed(hourly, start, end, "BTCUSDT", "1h", 3, n, h)
    assert record["trade_count"] == n and record["skipped"] == []
    assert record["entries"] == entries


def test_a_seed_reproduces_and_another_differs():
    hourly = _hourly(400)
    one = rb.run_seed(hourly, 20, 380, "BTCUSDT", "1h", 11, 15, 5)
    again = rb.run_seed(hourly, 20, 380, "BTCUSDT", "1h", 11, 15, 5)
    other = rb.run_seed(hourly, 20, 380, "BTCUSDT", "1h", 12, 15, 5)
    assert one == again
    assert one["entries"] != other["entries"]


OVERLAYS = [{"id": "OVL-ATR"}, {"id": "OVL-COOLDOWN"}]


def test_acceptance_8_trade_counts_within_ten_percent():
    """Without overlays every seed matches N exactly; with overlays a blocked entry is
    skipped, so the count is N minus the skipped entries (flagged when outside 10%)."""
    hourly = _hourly(600)
    n, h = 20, 6
    for seed in range(10):
        plain = rb.run_seed(hourly, 100, 600, "BTCUSDT", "1h", seed, n, h)
        assert plain["trade_count"] == n
        assert 0.9 * n <= plain["trade_count"] <= 1.1 * n
        with_ov = rb.run_seed(hourly, 100, 600, "BTCUSDT", "1h", seed, n, h, OVERLAYS)
        assert with_ov["entries"] == plain["entries"]  # the same draw
        assert with_ov["trade_count"] + len(with_ov["skipped"]) == n


def test_a_blocked_entry_is_skipped_not_deferred():
    hourly = _hourly(200)
    start, h = 20, 1
    entries = [1, 3, 5, 7]  # each entry right after the previous exit: cooldown blocks
    runner = rb.random_runner(hourly, start, entries, h, [{"id": "OVL-COOLDOWN"}])
    result = run_backtest(hourly, runner, "BTCUSDT", "1h", start, 40, CostModel())
    times = hourly["open_time"]
    entered = [t.entry_time for t in result.trades]
    assert entered and set(entered) < {times.iloc[start + e] for e in entries}
    assert all(
        t.entry_time in {times.iloc[start + e] for e in entries} for t in result.trades
    )


def test_the_random_strategy_is_not_a_catalogue_strategy():
    strategy = rb.RandomEntryStrategy([], [])
    assert strategy.strategy_id == rb.RANDOM_ENTRY_ID and strategy.params == {}
    with pytest.raises(ValueError):
        rb.RandomEntryStrategy(
            [pd.Timestamp(START, tz="UTC")], [pd.Timestamp(START, tz="UTC")]
        )


# --- the verdict --------------------------------------------------------------------------------


def _a(vs, rank, holds=0):
    return {"vs_bh": vs, "rank": rank, "data_holds": holds}


COMBOS = [("BTCUSDT", "1h"), ("BTCUSDT", "4h"), ("ETHUSDT", "1h"), ("ETHUSDT", "4h")]


def _b(values, holds=0):
    return [
        {"combination": COMBOS[i % 4], "vs_bh": v, "data_holds": holds if i == 0 else 0}
        for i, v in enumerate(values)
    ]


def test_three_beating_ranked_combinations_and_a_positive_median_is_an_edge():
    test_a = dict(zip(COMBOS, [_a(5, 99), _a(1, 95), _a(2, 97), _a(-3, 10)]))
    v = me.verdict(test_a, _b([1.0] * 36), 36)
    assert (
        v["verdict"] == me.EDGE
        and v["criterion_1"]
        and v["criterion_2"]
        and v["criterion_3"]
    )
    assert me.recheck_verdict(test_a, _b([1.0] * 36)) == me.EDGE


def test_criterion_2_is_read_literally():
    """Every combination that beats buy-and-hold must also rank at least 95: four
    beat it and only three rank, so no edge (a "3 of 4 pass both" reading would say
    edge)."""
    test_a = dict(zip(COMBOS, [_a(5, 99), _a(1, 95), _a(2, 97), _a(3, 94.5)]))
    v = me.verdict(test_a, _b([1.0] * 36), 36)
    assert v["criterion_1"] and not v["criterion_2"] and v["verdict"] == me.NO_EDGE
    assert v["criterion_2_failing"] == [("ETHUSDT", "4h")]


def test_beats_means_strictly_greater_and_no_baseline_fails_criterion_2():
    test_a = dict(zip(COMBOS, [_a(0.0, 99), _a(1, 99), _a(2, 99), _a(3, None)]))
    v = me.verdict(test_a, _b([1.0] * 36), 36)
    assert v["criterion_1_combinations"] == COMBOS[1:]
    assert not v["criterion_2"] and v["criterion_2_failing"] == [("ETHUSDT", "4h")]


def test_the_pooled_median_of_36_is_the_mean_of_the_middle_two():
    # the 18th value is below 0 and the 19th above: their mean (0.5) decides
    values = [-1.0] * 17 + [-0.5, 1.5] + [5.0] * 17
    random.Random(1).shuffle(values)
    assert me.median(values) == 0.5
    test_a = dict(zip(COMBOS, [_a(5, 99)] * 4))
    v = me.verdict(test_a, _b(values), 36)
    assert v["pooled_median"] == 0.5 and v["criterion_3"] and v["verdict"] == me.EDGE
    assert v["pooled_worst"] == -1.0
    assert set(v["combination_medians"]) == set(COMBOS)
    lower = [-1.0] * 17 + [-0.5, 0.4] + [5.0] * 17  # mean of the middle two: -0.05
    assert not me.verdict(test_a, _b(lower), 36)["criterion_3"]


def test_missing_bars_fail_the_criterion_their_window_feeds():
    test_a = dict(zip(COMBOS, [_a(5, 99, holds=2), _a(1, 99), _a(2, 99), _a(3, 99)]))
    v = me.verdict(test_a, _b([1.0] * 36), 36)
    assert ("BTCUSDT", "1h") not in v["criterion_1_combinations"]
    assert v["test_a_not_assessable"] == [("BTCUSDT", "1h")]
    v = me.verdict(dict(zip(COMBOS, [_a(5, 99)] * 4)), _b([1.0] * 36, holds=1), 36)
    assert not v["criterion_3"] and v["verdict"] == me.NO_EDGE


def test_the_verdict_needs_every_window_and_every_number():
    test_a = dict(zip(COMBOS, [_a(5, 99)] * 4))
    with pytest.raises(ValueError):
        me.verdict(test_a, _b([1.0] * 35), 36)
    with pytest.raises(ValueError):
        me.verdict(test_a, _b([None] + [1.0] * 35), 36)


def test_the_recheck_agrees_with_the_verdict():
    rng = random.Random(3)
    for _ in range(500):
        test_a = {
            c: _a(
                rng.uniform(-5, 5),
                rng.choice([None, 90.0, 95.0, 99.0]),
                rng.choice([0, 0, 0, 1]),
            )
            for c in COMBOS
        }
        test_b = _b(
            [rng.uniform(-2, 2) for _ in range(36)], holds=rng.choice([0, 0, 1])
        )
        assert me.verdict(test_a, test_b, 36)["verdict"] == me.recheck_verdict(
            test_a, test_b
        )


def _manifest(hit=0.503, up=0.504, n=5257, status="ok", start=me.TEST_A_HOLDOUT[0]):
    return {
        "model_id": "M",
        "validation": {
            "status": status,
            "holdout_start": start,
            "holdout_end": me.TEST_A_HOLDOUT[1],
        }
        | ({} if status == "ok" else {"reason": "too few bars"}),
        "validation_metrics": {
            "1hour": {
                "direction_hit_rate": hit,
                "up_share_of_considered": up,
                "direction_considered": n,
            }
        },
    }


def test_the_verdict_line_carries_11_8_and_test_a_s_values():
    line = me.verdict_line(
        me.NO_EDGE, {"BTC": _manifest(), "ETH": _manifest(0.5131, 0.5099, 5000)}
    )
    assert line == (
        "***No evidence of an edge*; in TRAINER-AUDIT 11.8 the trainer's held-out direction calls "
        "showed no skill above the up-rate base rate:** 1-hour hit rate vs share of closes that "
        "rose, BTC 50.3% vs 50.4% and ETH 51.3% vs 51.0% (n = 5,257 pairs each). Held-out metrics "
        "in Test A's manifests (a separate fit on the first 80% of each training window, scored on "
        "the last 20%, 2025-02-05 12:00 to 2025-08-16 04:00): BTC 50.3% vs 50.4% (n = 5,257), "
        "ETH 51.3% vs 51.0% (n = 5,000)."
    )
    assert me.verdict_line(
        me.EDGE, {"BTC": _manifest(), "ETH": _manifest()}
    ).startswith("***Evidence of an edge*; in TRAINER-AUDIT 11.8")


def test_a_missing_value_reads_n_a_with_its_reason_and_the_notes_come_in_order():
    line = me.verdict_line(
        me.NO_EDGE,
        {"BTC": _manifest(status="unavailable"), "ETH": _manifest(hit=None)},
        not_assessable=[("BTCUSDT 1h", "Test A out-of-sample", 2)],
        gap_limit=[("ETHUSDT 4h", "Test A", 1)],
    )
    assert (
        "BTC n/a (too few bars) vs n/a (too few bars) (n = n/a (too few bars))" in line
    )
    assert "ETH n/a (no value) vs 50.4% (n = 5,257)" in line
    na = line.index(
        "(not assessable: 2 decisions held for missing bars or an unknown timeframe: "
        "BTCUSDT 1h, Test A out-of-sample, 2)"
    )
    gap = line.index("(gap-pass limit reached on 1 decisions: ETHUSDT 4h, Test A, 1)")
    assert na < gap


def test_the_verdict_line_refuses_another_held_out_slice():
    with pytest.raises(ValueError):
        me.verdict_line(
            me.NO_EDGE,
            {"BTC": _manifest(start="2025-01-01T00:00:00Z"), "ETH": _manifest()},
        )


def _rec(action="HOLD", reason="LONG_0_SHORT_0", inactive=(), all_seven=True):
    active = {}
    if all_seven:
        active = {f"active_{tf}": (0.0 if tf in inactive else 1.0) for tf in TFS}
    return {"bar_time": None, "action": action, "reason": reason, "active": active}


def test_e1_and_e2_counts():
    records = [
        _rec(inactive=("4hour", "12hour")),  # E1
        _rec(inactive=("4hour", "1week")),  # one before 1week: not E1
        _rec(inactive=("1hour", "2hour", "8hour")),  # E1
        _rec(reason="BARS_MISSING:1week", all_seven=False),  # a decision, never E1
        _rec(reason="BOUNDS_NOT_CONVERGED", inactive=("2hour", "1day")),  # E1 and E2
        _rec(action="ENTER_LONG", reason="LONG_ON_3_OF_7"),
    ]
    q = me.quirk_counts(records)
    assert q == {"decisions": 6, "e1": 3, "e1_share": 0.5, "e2": 1}
    h = me.hold_counts(records)
    assert (h["BARS_MISSING"], h["TIMEFRAME_UNKNOWN"], h["BOUNDS_NOT_CONVERGED"]) == (
        1,
        0,
        1,
    )
    assert me.data_holds(h) == 1


# --- STRAT-003's activity indicators ----------------------------------------------------------


def _publish(
    folder, model_id, model, coin="BTC", train_end="2024-01-01T00:00:00Z", **fields
):
    h3.write_files(str(folder), model)
    h3.publish_files(str(folder), model_id, coin=coin, train_end=train_end, **fields)
    return model_id


def _recorded(model_id, frames, start, end):
    from backtest.model_eval import RecordingRunner
    from strategies.factory import build_runner

    built = build_runner("STRAT-003", {"model_id": model_id})
    runner = RecordingRunner(built.strategy, built.overlays)
    runner.strategy.use_bars(frames)
    result = run_backtest(
        frames["1h"], runner, "BTCUSDT", "1h", start, end, CostModel()
    )
    return runner.records, result


def test_strat003_reports_each_timeframe_s_activity(tmp_path):
    frames = hc.all_timeframes(_hourly())
    model_id = _publish(tmp_path / "crafted", "crafted", h3.CRAFTED)
    records, result = _recorded(model_id, frames, 24 * 7 * 3, 24 * 7 * 3 + 100)
    assert len(records) == result.bars - 1
    full = [r for r in records if not r["reason"].startswith("BARS_MISSING")]
    assert full
    for r in full:
        assert (
            r["active"]["active_4hour"] == 0.0 and r["active"]["active_12hour"] == 0.0
        )
        assert r["active"]["active_1hour"] == 1.0 and r["active"]["active_1week"] == 1.0
    assert me.quirk_counts(records)["e1"] == len(full)


def test_a_missing_bar_hold_has_no_activity_and_a_gap_pass_hold_has_all_of_it(tmp_path):
    frames = hc.all_timeframes(_hourly())
    model_id = _publish(tmp_path / "crafted", "crafted", h3.CRAFTED)
    early, _ = _recorded(model_id, frames, 10, 30)  # no weekly bar has closed yet
    assert all(
        r["reason"].startswith("BARS_MISSING") and r["active"] == {} for r in early
    )
    zero = {
        tf: h3._tf("1000000000.0", f"0.0 0.0{{}}{1 + i}.0{{}}-{1 + i}.0")
        for i, tf in enumerate(TFS)
    }
    zero["1hour"] = h3._tf("1000000000.0", "0.0 0.1{}0.3{}-100.0")
    zero["2hour"] = h3._tf("1000000000.0", "0.0 0.1{}0.5{}-100.0")
    zero_id = _publish(tmp_path / "zero", "zero-low", zero)
    stuck, _ = _recorded(zero_id, frames, 24 * 7 * 3, 24 * 7 * 3 + 5)
    assert all(r["reason"] == "BOUNDS_NOT_CONVERGED" for r in stuck)
    assert all(len(r["active"]) == 7 for r in stuck)
    assert me.quirk_counts(stuck)["e2"] == len(stuck)


# --- the run script -----------------------------------------------------------------------------

COMMIT = "f" * 40


def _fake_state(**changes):
    state = {
        "commit": COMMIT,
        "frozen_files_changed": [],
        "python": sys.version,
        "powertrader_home": os.environ.get("POWERTRADER_HOME"),
    }
    state.update(changes)
    return state


def test_the_declared_plan_is_the_header_s(script):
    plan = script.PLAN
    assert plan.pairs == ("BTCUSDT", "ETHUSDT") and plan.primary == ("1h", "4h")
    assert plan.model_tfs == ("1h", "2h", "4h", "8h", "12h", "1d", "1w")
    assert plan.start == "2023-01-01" and plan.end == "2026-10-01"
    assert dict(plan.seed_ranges) == {
        "BTCUSDT 1h": (0, 100),
        "BTCUSDT 4h": (100, 200),
        "ETHUSDT 1h": (200, 300),
        "ETHUSDT 4h": (300, 400),
    }
    assert plan.seeds_per_run == 100
    assert all(len(plan.seeds(p, tf)) == 100 for p in plan.pairs for tf in plan.primary)
    assert list(plan.seeds("ETHUSDT", "4h")) == list(range(300, 400))
    assert plan.test_a_train_end == "2025-08-16T04:00:00Z"
    assert tuple(plan.test_a_holdout) == me.TEST_A_HOLDOUT
    assert [e[:10] for e in plan.test_b_ends] == [
        "2024-07-01", "2024-10-01", "2025-01-01", "2025-04-01", "2025-07-01",
        "2025-10-01", "2026-01-01", "2026-04-01", "2026-07-01",
    ]  # fmt: skip
    assert plan.test_b_months == 3 and plan.expected_test_b_windows() == 36
    trainings = plan.trainings()
    assert len(trainings) == 20
    assert all(t["train_start"] == "2023-01-01T00:00:00Z" for t in trainings)
    assert dict(plan.overlay_sets) == {
        "none": (),
        "OVL-ATR+OVL-COOLDOWN": ("OVL-ATR", "OVL-COOLDOWN"),
    }
    assert (
        plan.fee_bps,
        plan.slippage_bps,
        plan.size_fraction,
        plan.initial_equity,
    ) == (10.0, 5.0, 1.0, 10_000.0)
    assert plan.trainer_seed == 0 and plan.in_sample_fraction == 0.7
    # batch 1's own records: the same hashes, bar counts and out-of-sample split
    for pair in plan.pairs:
        for tf in plan.primary:
            with open(
                os.path.join(BATCH1, f"STRAT-001_{pair}_{tf}_none.json"),
                encoding="utf-8",
            ) as f:
                b1 = json.load(f)
            assert plan.batch1_sha256[f"{pair} {tf}"] == b1["data"]["source"]["sha256"]
            assert plan.candles[tf] == b1["data"]["candles"]
            assert plan.oos_start[tf] == b1["split"]["out_of_sample_starts"]
            assert plan.oos_bars[tf] == b1["out_of_sample"]["bars"]
    # the pins run checks are the header's two cases
    assert [p[:4] for p in rb.PINNED] == [(0, 9857, 100, 20), (100, 2465, 500, 3)]
    rb.check_pins()


def _mini(script, sources, overrides=None):
    """A miniature plan over synthetic bars: two pairs, both primary timeframes, two
    Test B windows of one month, five seeds per combination."""
    oos, counts, oos_bars = {}, {}, {}
    for tf, hours in (("1h", 1), ("4h", 4)):
        n = len(pd.read_csv(sources[f"BTCUSDT {tf}"]))  # no gaps: bar i opens i bars in
        cut = int(n * 0.7)
        oos[tf] = pd.Timestamp(START, tz="UTC") + pd.Timedelta(hours=hours * cut)
        counts[tf], oos_bars[tf] = n, n - cut
    batch1 = {}
    for key, path in sources.items():
        if key.split()[1] in ("1h", "4h"):
            batch1[key] = candles.file_sha256(path)
    fields = dict(
        start=START,
        end="2024-02-12",
        batch1_sha256=batch1,
        candles=counts,
        oos_start={tf: t.isoformat() for tf, t in oos.items()},
        oos_bars=oos_bars,
        train_start="2024-01-01T00:00:00Z",
        # the earlier of the two starts, as in the declared plan
        test_a_train_end=min(oos.values()).strftime("%Y-%m-%dT%H:%M:%SZ"),
        test_a_holdout=(
            "2024-01-24T00:00:00Z",
            min(oos.values()).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
        test_b_ends=("2024-01-22T00:00:00Z", "2024-01-29T00:00:00Z"),
        test_b_months=1,
        seed_ranges={
            "BTCUSDT 1h": (0, 5),
            "BTCUSDT 4h": (100, 105),
            "ETHUSDT 1h": (200, 205),
            "ETHUSDT 4h": (300, 305),
        },
        seeds_per_run=5,
    )
    fields.update(overrides or {})
    return script.Plan(**fields)


@pytest.fixture
def world(tmp_path, script, monkeypatch):
    """Synthetic bars for both pairs written as a source, and a fake fetcher that copies
    the source into the cache (and records what it was asked for)."""
    src = tmp_path / "source"
    sources = {}
    for pair, seed in (("BTCUSDT", 1), ("ETHUSDT", 2)):
        frames = hc.all_timeframes(hc.synthetic_hourly(24 * 7 * 6, START, seed=seed))
        hc.seed_cache(str(src), pair, frames)
        for tf in frames:
            sources[f"{pair} {tf}"] = candles.cache_path(pair, tf, str(src))
    cache = str(tmp_path / "cache")
    calls = []

    def fake_get_candles(symbol, tf, start, end, cache_dir=None, fetcher=None, **kw):
        calls.append((symbol, tf, start, end))
        os.makedirs(cache_dir, exist_ok=True)
        with open(sources[f"{symbol} {tf}"], "rb") as f:
            data = f.read()
        with open(candles.cache_path(symbol, tf, cache_dir), "wb") as f:
            f.write(data)

    monkeypatch.setattr(candles, "get_candles", fake_get_candles)
    return SimpleNamespace(
        tmp=tmp_path, sources=sources, cache=cache, calls=calls,
        plan=_mini(script, sources), out=str(tmp_path / "out"),
    )  # fmt: skip


def _manifest_fields(script, plan, job, **changes):
    """What a model published by the real trainer for ``job`` would carry."""
    from pt_pattern_trainer import TRAINER_PARAMS

    fields = {
        "train_start": plan.train_start,
        "params": TRAINER_PARAMS,
        "seed": 0,
        "code_sha256": script.model_code_hashes(),
        "trainer_git_commit": COMMIT,
        "trainer_git_dirty": False,
        "validation": (
            {
                "status": "ok",
                "holdout_start": plan.test_a_holdout[0],
                "holdout_end": plan.test_a_holdout[1],
            }
            if job["test"] == "A"
            else {"status": "unavailable", "reason": "too few bars"}
        ),
        "validation_metrics": {
            "1hour": {
                "direction_hit_rate": 0.5,
                "up_share_of_considered": 0.49,
                "direction_considered": 321,
            }
        },
    }
    fields.update(changes)
    return fields


def _publish_all(world, script, a_end=None, **changes):
    """Crafted models for every training window (as the trainer would publish them),
    their manifest copies, and train.json."""
    import model_store

    os.makedirs(world.out, exist_ok=True)
    runs = []
    for job in world.plan.trainings():
        end = a_end if (job["test"] == "A" and a_end) else job["train_end"]
        model_id = f"{job['coin']}-{job['test']}-{job['train_end'][:10]}"
        model = h3.CRAFTED if job["coin"] == "BTC" else h3.CRAFTED_ALL_ACTIVE
        if not os.path.isdir(os.path.join(world.tmp, "models", model_id)):
            _publish(world.tmp / "models" / model_id, model_id, model, job["coin"], end,
                     **_manifest_fields(script, world.plan, job, **changes))  # fmt: skip
        script._write_json(
            os.path.join(world.out, "manifests", f"{model_id}.json"),
            model_store.load(model_id).manifest,
        )
        runs.append(dict(job, exit_code=0, model_id=model_id))
    with open(os.path.join(world.out, "data.json"), encoding="utf-8") as f:
        data = json.load(f)
    script._write_json(
        os.path.join(world.out, "train.json"),
        {
            "code": _fake_state(),
            "data_sha256": {k: r["sha256"] for k, r in data["files"].items()},
            "data_code_sha256": script.trainer_data_code_hashes(),
            "trainings": runs,
        },
    )


HEADER = "# Mini report\n\nDeclared things.\n\n---\n\n*Results go below this line.*\n"


def _fetched(world, script):
    assert (
        script.fetch(
            world.plan,
            world.out,
            world.cache,
            fetcher_factory=lambda: None,
            state=_fake_state(),
        )
        == 0
    )


def _results(world):
    with open(os.path.join(world.out, "results.json"), encoding="utf-8") as f:
        return json.load(f)


def _call_report(world, script, report, header=HEADER, **kw):
    args = dict(
        header_at=lambda commit: header,
        commits=["abc1234 2026-10-07 header"],
        code_log=["def5678 2026-10-07 freeze"],
        state=_fake_state(),
        frozen_changes=lambda old, new: [],
    )
    args.update(kw)
    return script.report(world.plan, world.out, str(report), **args)


def _report(world, script, header=HEADER, **kw):
    report = world.tmp / "report.md"
    report.write_bytes(header.encode("utf-8"))
    assert _call_report(world, script, report, header, **kw) == 0
    return report.read_bytes().decode("utf-8")


def _scored_world(world, script):
    _fetched(world, script)
    _publish_all(world, script)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 0
    return _results(world)


def test_every_step_refuses_frozen_files_that_differ_from_the_commit(world, script):
    dirty = _fake_state(frozen_files_changed=["?? app/backtest/new.py"])
    with pytest.raises(script.Stop, match="frozen files differ"):
        script.fetch(
            world.plan,
            world.out,
            world.cache,
            fetcher_factory=lambda: None,
            state=dirty,
        )
    with pytest.raises(script.Stop, match="frozen files differ"):
        script.train(world.plan, world.out, cache_dir=world.cache, state=dirty)
    with pytest.raises(script.Stop, match="frozen files differ"):
        script.run(world.plan, world.out, world.cache, state=dirty)
    with pytest.raises(script.Stop, match="frozen files differ"):
        _call_report(world, script, world.tmp / "r.md", state=dirty)


def test_fetch_refuses_a_cache_that_is_not_empty(world, script):
    os.makedirs(world.cache, exist_ok=True)
    open(candles.cache_path("BTCUSDT", "2h", world.cache), "w").close()
    with pytest.raises(script.Stop, match="must be empty"):
        script.fetch(
            world.plan,
            world.out,
            world.cache,
            fetcher_factory=lambda: None,
            state=_fake_state(),
        )


def test_fetch_asks_for_the_window_s_closed_bars_and_records_every_hash(world, script):
    from market_data.timeframes import bar_open_floor

    _fetched(world, script)
    plan = world.plan
    assert sorted((s, tf) for s, tf, _, _ in world.calls) == sorted(
        (p, tf) for p in plan.pairs for tf in plan.model_tfs
    )
    for symbol, tf, start, end in world.calls:
        end_ts = int(pd.Timestamp(plan.end, tz="UTC").timestamp())
        assert start == plan.start
        assert end == pd.Timestamp(
            bar_open_floor(end_ts, tf), unit="s", tz="UTC"
        )  # closed by the end
    with open(os.path.join(world.out, "data.json"), encoding="utf-8") as f:
        data = json.load(f)
    assert set(data["files"]) == {
        f"{p} {tf}" for p in plan.pairs for tf in plan.model_tfs
    }
    for key, rec in data["files"].items():
        assert rec["sha256"] == candles.file_sha256(world.sources[key])
    assert data["batch1_mismatches"] == [] and data["code"]["commit"] == COMMIT
    wrong = script.Plan(**{**plan.__dict__, "batch1_sha256": {"BTCUSDT 1h": "0" * 64}})
    other_cache = str(world.tmp / "cache2")
    assert (
        script.fetch(
            wrong,
            world.out,
            other_cache,
            fetcher_factory=lambda: None,
            state=_fake_state(),
        )
        == 1
    )
    # and nothing goes on from a data.json that records the mismatch
    with pytest.raises(script.Stop, match="not batch 1's candles"):
        script.check_data(wrong, world.out, other_cache)
    assert script.run(wrong, world.out, other_cache, state=_fake_state()) == 1
    assert _results(world)["status"] == "stopped"


def test_run_stops_when_a_candle_file_changed_since_fetch(world, script):
    _fetched(world, script)
    _publish_all(world, script)
    with open(
        candles.cache_path("ETHUSDT", "1w", world.cache), "a", encoding="utf-8"
    ) as f:
        f.write("\n")
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    results = _results(world)
    assert results["status"] == "stopped" and "changed since fetch" in results["reason"]
    text = _report(world, script)
    assert text.startswith(HEADER) and "**Stopped: nothing was scored.**" in text


def test_a_stopped_run_is_replaced_without_a_note_and_kept(world, script):
    _fetched(world, script)
    assert (
        script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    )  # no train.json
    assert "no train.json" in _results(world)["reason"]
    _publish_all(world, script)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 0
    (only,) = os.listdir(os.path.join(world.out, "superseded"))
    with open(
        os.path.join(world.out, "superseded", only, "note.json"), encoding="utf-8"
    ) as f:
        assert (
            json.load(f)["note"]
            == "run: replaced a run that stopped before scoring anything"
        )
    body = _report(world, script)
    assert "stopped, nothing scored: no train.json" in body


@pytest.mark.parametrize(
    "edit, message",
    [
        (
            lambda t, out: t["trainings"].__setitem__(
                1, {**t["trainings"][1], "exit_code": 3}
            ),
            "training failed",
        ),
        (lambda t, out: t["trainings"].pop(1), "training missing"),
        (
            lambda t, out: t.__setitem__(
                "data_sha256", {**t["data_sha256"], "BTCUSDT 2h": "0" * 64}
            ),
            "other candle files",
        ),
        (
            lambda t, out: t.__setitem__(
                "data_code_sha256", {"market_data/candles.py": "0" * 64}
            ),
            "reads its bars through",
        ),
        (lambda t, out: t["code"].__setitem__("commit", "e" * 40), "not cleanly at"),
    ],
    ids=["failed", "missing", "data", "data-code", "train-commit"],
)
def test_run_stops_unless_every_declared_training_is_bound(
    world, script, edit, message
):
    _fetched(world, script)
    _publish_all(world, script)
    path = os.path.join(world.out, "train.json")
    with open(path, encoding="utf-8") as f:
        train = json.load(f)
    edit(train, world.out)
    script._write_json(path, train)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    assert message in _results(world)["reason"]


def test_run_stops_on_a_changed_manifest_copy_or_a_shared_model(world, script):
    _fetched(world, script)
    _publish_all(world, script)
    copy = os.path.join(
        world.out, "manifests", "BTC-A-" + world.plan.test_a_train_end[:10] + ".json"
    )
    with open(copy, encoding="utf-8") as f:
        manifest = json.load(f)
    manifest["seed"] = 1
    script._write_json(copy, manifest)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    assert "manifest copy" in _results(world)["reason"]
    # two trainings of one window may not share a model
    world.plan = script.Plan(
        **{**world.plan.__dict__, "test_b_ends": (world.plan.test_a_train_end,)}
    )
    _publish_all(world, script)
    path = os.path.join(world.out, "train.json")
    with open(path, encoding="utf-8") as f:
        train = json.load(f)
    for coin in world.plan.coins:
        a = next(
            r for r in train["trainings"] if r["coin"] == coin and r["test"] == "A"
        )
        b = next(
            r for r in train["trainings"] if r["coin"] == coin and r["test"] == "B"
        )
        b["model_id"] = a["model_id"]
    script._write_json(path, train)
    assert (
        script.run(
            world.plan, world.out, world.cache, note="shared", state=_fake_state()
        )
        == 1
    )
    assert "distinct models" in _results(world)["reason"]


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"seed": 7}, "seed 7"),
        ({"params": {"passes": 1}}, "default parameters"),
        ({"code_sha256": {"pt_pattern_trainer.py": "0" * 64}}, "other model code"),
        ({"train_start": "2023-06-01T00:00:00Z"}, "not the one asked for"),
        ({"trainer_git_dirty": True}, "not cleanly at"),
    ],
    ids=["seed", "params", "code", "window", "dirty-trainer"],
)
def test_run_refuses_a_model_that_is_not_the_declared_training(
    world, script, changes, message
):
    _fetched(world, script)
    _publish_all(world, script, **changes)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    assert message in _results(world)["reason"]


def test_run_refuses_a_model_of_another_window(world, script):
    _fetched(world, script)
    _publish_all(world, script)
    path = os.path.join(world.out, "train.json")
    with open(path, encoding="utf-8") as f:
        train = json.load(f)
    a, b = train["trainings"][0], train["trainings"][1]  # BTC's Test A and first Test B
    a["model_id"], b["model_id"] = b["model_id"], a["model_id"]
    script._write_json(path, train)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    assert "not the one asked for" in _results(world)["reason"]


def test_run_stops_if_the_in_sample_window_is_not_refused(world, script):
    _fetched(world, script)
    world.plan = script.Plan(
        **{**world.plan.__dict__, "test_a_train_end": "2024-01-01T00:00:00Z"}
    )
    _publish_all(world, script)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    assert "was not refused" in _results(world)["reason"]


def test_run_stops_on_a_shortened_test_b_window(world, script):
    path = world.sources["BTCUSDT 1h"]
    frame = pd.read_csv(path)
    # one hour missing after Test A's split, inside both Test B windows
    gap = int(pd.Timestamp("2024-02-05T05:00:00Z").timestamp() * 1000)
    frame[frame["open_time_ms"] != gap].to_csv(path, index=False)
    world.plan = _mini(script, world.sources)
    assert pd.Timestamp(world.plan.oos_start["1h"]) < pd.Timestamp(
        gap, unit="ms", tz="UTC"
    )
    _fetched(world, script)
    _publish_all(world, script)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    reason = _results(world)["reason"]
    assert (
        "BTCUSDT 1h Test B from 2024-01-22T00:00:00Z: 503 bars, not the full 504"
        in reason
    )


def test_run_will_not_draw_on_a_python_that_draws_differently(
    world, script, monkeypatch
):
    _fetched(world, script)
    _publish_all(world, script)
    monkeypatch.setattr(rb, "PINNED", ((0, 9857, 100, 20, "0" * 64),))
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    assert "no longer gives the pinned placement" in _results(world)["reason"]


def test_any_other_error_is_recorded_and_raised(world, script, monkeypatch):
    _fetched(world, script)
    _publish_all(world, script)

    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(script, "_score_all", broken)
    with pytest.raises(RuntimeError):
        script.run(world.plan, world.out, world.cache, state=_fake_state())
    assert _results(world) == {
        "status": "stopped",
        "reason": "error: RuntimeError: disk full",
        "code": _fake_state(),
    }


def test_run_and_report_end_to_end(world, script):
    results = _scored_world(world, script)
    assert results["status"] == "ok" and results["code"] == _fake_state()
    assert (
        len(results["test_a"]) == 2 * 2 * 2 and len(results["test_b"]) == 2 * 2 * 2 * 2
    )
    files = results["data"]["files"]
    assert set(files) == {
        f"{p} {tf}" for p in world.plan.pairs for tf in world.plan.model_tfs
    }
    assert all(
        rec["sha256"] == candles.file_sha256(world.sources[key])
        for key, rec in files.items()
    )
    for key, sec in results["test_a"].items():
        pair, tf, ov = key.split("|")
        oos = sec["out_of_sample"]
        assert sec["model_id"] == f"{pair[:3]}-A-{world.plan.test_a_train_end[:10]}"
        assert "LOOKAHEAD_MODEL" in sec["in_sample"]["refused"]
        assert (
            oos["from"] == world.plan.oos_start[tf]
            and oos["bars"] == world.plan.oos_bars[tf]
        )
        assert oos["quirks"]["decisions"] == oos["bars"] - 1
        assert oos["quirks"]["e2"] == 0
        if pair == "BTCUSDT":  # CRAFTED: 4hour and 12hour never active
            assert (
                oos["quirks"]["e1"]
                == oos["quirks"]["decisions"] - oos["holds"]["BARS_MISSING"]
            )
        else:
            assert oos["quirks"]["e1"] == 0
        bl = sec["baseline"]
        assert bl["code"] == _fake_state() and not bl.get("no_baseline")
        assert [s["seed"] for s in bl["seeds"]] == list(world.plan.seeds(pair, tf))
        # criterion 2's input: STRAT-003's own return ranked among this run's seeds
        assert bl["rank"] == rb.percentile_rank(
            oos["strategy"]["total_return_pct"],
            [s["total_return_pct"] for s in bl["seeds"]],
        )
        if ov == "none":
            assert all(
                s["trade_count"] == bl["N"] and s["bars_held"] == [bl["H_used"]]
                for s in bl["seeds"]
            )
        tag = f"test-a_{pair}_{tf}_{ov.replace('+', '_')}"
        with open(
            os.path.join(world.out, "runs", f"{tag}.json"), encoding="utf-8"
        ) as f:
            assert (
                json.load(f)["baseline"] == f"baselines/{tag}.json"
            )  # the seeds are kept once
        with open(
            os.path.join(world.out, "baselines", f"{tag}.json"), encoding="utf-8"
        ) as f:
            assert json.load(f) == bl
    for w in results["test_b"]:
        # each window is scored with the model trained to its start
        assert w["model_id"] == f"{w['pair'][:3]}-B-{w['train_end'][:10]}"
        assert pd.Timestamp(w["from"]) == pd.Timestamp(w["train_end"])
        assert w["quirks"]["decisions"] == w["bars"] - 1
    text = _report(world, script)
    assert text.startswith(HEADER)
    body = text[len(HEADER) :]
    assert (
        "### Verdict" in body
        and "in TRAINER-AUDIT 11.8 the trainer's held-out direction calls" in body
    )
    assert "scored on the last 20%, 2024-01-24 00:00 to" in body
    assert "BTC 50.0% vs 49.0% (n = 321), ETH 50.0% vs 49.0% (n = 321)" in body
    assert (
        "`abc1234 2026-10-07 header`" in body and "`def5678 2026-10-07 freeze`" in body
    )
    assert f"Reported from commit `{COMMIT}`" in body
    assert "### Data" in body and all(
        f"`{rec['sha256']}`" in body for rec in files.values()
    )
    assert "### Test B: walk-forward" in body and "### Batch 1 side by side" in body
    assert "Superseded" not in body
    with open(os.path.join(world.out, "verdict.json"), encoding="utf-8") as f:
        given = json.load(f)
    assert (
        given["verdict"] in (me.EDGE, me.NO_EDGE)
        and given["reported_at_commit"] == COMMIT
    )
    assert given["code"] == _fake_state()
    # the owner's additions as the report prints them: the per-combination Test B medians
    # (information only) and the E1/E2 counts, from the runs without overlays
    ev = script.evaluate(world.plan, results)
    medians = sorted(ev["verdict"]["combination_medians"].items())
    assert (
        "- For information only (not in the verdict), each combination's Test B median: "
        + "; ".join(f"{p} {tf} {script._fmt(m)} pp" for (p, tf), m in medians)
        + "."
    ) in body
    for pair, tf in COMBOS:
        q = results["test_a"][f"{pair}|{tf}|none"]["out_of_sample"]["quirks"]
        share = script._fmt(100 * q["e1_share"], 1, pct=True)
        assert (
            f"E1 {q['e1']} of {q['decisions']} decisions ({share}), E2 {q['e2']}."
            in body
        )
        rows = [
            x
            for x in results["test_b"]
            if (x["pair"], x["timeframe"], x["overlays"]) == (pair, tf, "none")
        ]
        e1, dec, e2 = (
            sum(x["quirks"][k] for x in rows) for k in ("e1", "decisions", "e2")
        )
        summary = f"{e1} of {dec} ({script._fmt(100 * e1 / dec, 1, pct=True)}) | {e2} |"
        assert f"| {pair} {tf} | none |" in body and summary in body
        assert f"| {pair} {tf} | OVL-ATR+OVL-COOLDOWN |" in body
    assert body.count("| — | — | — |") == len(
        [x for x in results["test_b"] if x["overlays"] != "none"]
    )
    assert (
        given["verdict"] == script.evaluate(world.plan, results)["verdict"]["verdict"]
    )
    # a header that differs from the committed one is refused
    report = world.tmp / "report.md"
    report.write_text(HEADER.replace("Declared", "Changed") + body, encoding="utf-8")
    with pytest.raises(script.Stop, match="differs from the one committed"):
        _call_report(world, script, report)
    # so is frozen code that changed since the results' commit
    report.write_text(HEADER, encoding="utf-8")
    with pytest.raises(
        script.Stop, match="frozen files changed since the results' commit"
    ):
        _call_report(
            world,
            script,
            report,
            frozen_changes=lambda old, new: ["app/backtest/model_eval.py"],
        )


def test_report_rederives_every_recorded_draw(world, script):
    results = _scored_world(world, script)
    key = next(iter(results["test_a"]))
    results["test_a"][key]["baseline"]["seeds"][0]["entries"][0] += 1
    script._write_json(os.path.join(world.out, "results.json"), results)
    report = world.tmp / "report.md"
    report.write_text(HEADER, encoding="utf-8")
    with pytest.raises(AssertionError, match="recorded entry bars"):
        _call_report(world, script, report)
    assert report.read_text(encoding="utf-8") == HEADER  # nothing written


def test_a_rerun_needs_a_note_and_keeps_the_earlier_results_and_verdict(world, script):
    _scored_world(world, script)
    with pytest.raises(script.Stop, match="--supersede"):
        script.run(world.plan, world.out, world.cache, state=_fake_state())
    assert (
        script.run(
            world.plan,
            world.out,
            world.cache,
            note="fixed a defect in X",
            state=_fake_state(),
        )
        == 0
    )
    superseded = os.path.join(world.out, "superseded")
    (first,) = os.listdir(superseded)
    assert first == "01-run-fffffff"
    assert sorted(os.listdir(os.path.join(superseded, first))) == [
        "baselines",
        "note.json",
        "results.json",
        "runs",
    ]
    body = _report(world, script)
    assert "**Superseded runs**" in body and "fixed a defect in X" in body
    assert "no verdict was given (no report was made from them)" in body
    assert "BTCUSDT 1h Test A" in body  # the earlier numbers, beside the final ones
    # once a verdict has been given, a later re-run keeps it as given
    assert (
        script.run(
            world.plan, world.out, world.cache, note="fixed Y", state=_fake_state()
        )
        == 0
    )
    second = sorted(os.listdir(superseded))[1]
    assert "verdict.json" in os.listdir(os.path.join(superseded, second))
    body = _report(world, script)
    assert "verdict given: " in body and "fixed Y" in body


def test_a_header_changed_after_an_earlier_run_is_refused(world, script):
    _scored_world(world, script)
    assert (
        script.run(
            world.plan,
            world.out,
            world.cache,
            note="fix",
            state=_fake_state(commit="a" * 40),
        )
        == 0
    )
    old = os.path.join(world.out, "superseded", "01-run-fffffff", "results.json")
    assert os.path.isfile(old)
    report = world.tmp / "report.md"
    report.write_text(HEADER, encoding="utf-8")
    headers = {COMMIT: HEADER.replace("Declared", "Earlier"), "a" * 40: HEADER}
    with pytest.raises(script.Stop, match="header changed after an earlier run"):
        _call_report(
            world,
            script,
            report,
            header_at=lambda c: headers[c],
            state=_fake_state(commit="a" * 40),
        )


def test_training_again_moves_the_run_outputs_aside_too(world, script):
    _scored_world(world, script)
    ids = {
        f"{j['coin']}|{j['train_end']}": f"{j['coin']}-{j['test']}-{j['train_end'][:10]}"
        for j in world.plan.trainings()
    }
    stub = _stub_trainer(world.tmp, {"ids": ids, "fail": []}, "again")
    assert (
        script.train(
            world.plan,
            world.out,
            stub,
            cache_dir=world.cache,
            note="trainer fix",
            state=_fake_state(),
        )
        == 0
    )
    (moved,) = os.listdir(os.path.join(world.out, "superseded"))
    assert {"train.json", "manifests", "results.json", "runs", "baselines"} <= set(
        os.listdir(os.path.join(world.out, "superseded", moved))
    )
    report = world.tmp / "report.md"
    report.write_text(HEADER, encoding="utf-8")
    with pytest.raises(script.Stop, match="no results.json"):
        _call_report(world, script, report)


def test_report_keeps_the_file_s_line_endings(world, script):
    _scored_world(world, script)
    crlf = HEADER.replace("\n", "\r\n")
    text = _report(world, script, header=crlf)
    assert text.startswith(crlf) and "\n" not in text.replace("\r\n", "")


def test_report_refuses_results_from_uncommitted_code(world, script):
    results = _scored_world(world, script)
    results["code"]["frozen_files_changed"] = [" M app/x.py"]
    script._write_json(os.path.join(world.out, "results.json"), results)
    with pytest.raises(script.Stop, match="differ from their commit"):
        _report(world, script)


def test_report_renders_runs_without_a_baseline_and_with_a_reduced_hold(world, script):
    results = _scored_world(world, script)
    none = results["test_a"]["BTCUSDT|4h|none"]["baseline"]
    results["test_a"]["BTCUSDT|4h|none"]["baseline"] = {
        **none, "N": 0, "H": None, "seeds": [], "rank": None, "no_baseline": "STRAT-003 made no trade (N = 0)",
    }  # fmt: skip
    reduced = results["test_a"]["ETHUSDT|1h|none"]["baseline"]
    reduced["H"], reduced["H_reduced"] = reduced["H_used"] + 4, True
    script._write_json(os.path.join(world.out, "results.json"), results)
    body = _report(world, script)
    assert (
        "Random baseline, none: N = 0, H = None; no baseline: STRAT-003 made no trade (N = 0)."
        in body
    )
    assert f"(used {reduced['H_used']}, reduced)" in body


def _stub_trainer(tmp_path, mapping, name):
    path = tmp_path / f"{name}.py"
    mapping_path = tmp_path / f"{name}.json"
    calls = tmp_path / f"{name}.calls.jsonl"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    path.write_text(
        "import json, os, sys\n"
        f"sys.path.insert(0, {APP_DIR!r})\n"
        "import pt_paths\n"
        "args = sys.argv[1:]\n"
        f"with open({str(calls)!r}, 'a') as f:\n"
        "    f.write(json.dumps({'argv': args, 'cwd': os.getcwd(),\n"
        "                        'stale': os.path.exists('memories_1hour.txt')}) + '\\n')\n"
        "open('memories_1hour.txt', 'w').close()  # what a real trainer leaves behind\n"
        "coin, end = args[0], args[args.index('--train-end') + 1]\n"
        f"mapping = json.load(open({str(mapping_path)!r}))\n"
        "if end in mapping['fail']:\n"
        "    sys.exit(3)\n"
        "folder = os.path.join(pt_paths.data_dir(), 'training_results')\n"
        "os.makedirs(folder, exist_ok=True)\n"
        "with open(os.path.join(folder, coin.lower() + '_training_results.json'), 'w') as f:\n"
        "    json.dump({'model_id': mapping['ids'][coin + '|' + end]}, f)\n",
        encoding="utf-8",
    )
    return str(path)


def test_train_runs_every_window_and_records_what_was_published(world, script):
    _fetched(world, script)
    ids = {}
    for job in world.plan.trainings():
        model_id = f"stub-{job['coin']}-{job['test']}-{job['train_end'][:10]}"
        _publish(world.tmp / model_id, model_id, h3.CRAFTED, job["coin"], job["train_end"],
                 **_manifest_fields(script, world.plan, job))  # fmt: skip
        ids[f"{job['coin']}|{job['train_end']}"] = model_id
    stub = _stub_trainer(world.tmp, {"ids": ids, "fail": []}, "good")
    assert (
        script.train(
            world.plan, world.out, stub, cache_dir=world.cache, state=_fake_state()
        )
        == 0
    )
    # the command line the hub's way: the coin, offline, the window, seed 0, its own folder
    with open(world.tmp / "good.calls.jsonl", encoding="utf-8") as f:
        calls = [json.loads(line) for line in f]
    assert len(calls) == len(world.plan.trainings())
    for call, job in zip(calls, world.plan.trainings()):
        assert call["argv"] == [
            job["coin"], "--offline", "--train-start", job["train_start"], "--train-end", job["train_end"], "--seed", "0",
        ]  # fmt: skip
        assert os.path.basename(call["cwd"]) == job["coin"] and not call["stale"]
    with open(os.path.join(world.out, "train.json"), encoding="utf-8") as f:
        train = json.load(f)
    runs = train["trainings"]
    assert [r["model_id"] for r in runs] == [
        ids[f"{j['coin']}|{j['train_end']}"] for j in world.plan.trainings()
    ]
    assert all(r["exit_code"] == 0 and not r.get("error") for r in runs)
    assert all(
        os.path.isfile(os.path.join(world.out, "manifests", f"{r['model_id']}.json"))
        for r in runs
    )
    assert train["data_code_sha256"] == script.trainer_data_code_hashes()
    # the run accepts what train recorded
    assert len(
        script.trained_models(
            world.plan, world.out, script.check_data(world.plan, world.out, world.cache)
        )
    ) == len(runs)
    # a second train needs a note, and keeps the first one's outputs
    with pytest.raises(script.Stop, match="--supersede"):
        script.train(
            world.plan, world.out, stub, cache_dir=world.cache, state=_fake_state()
        )
    failing = _stub_trainer(
        world.tmp, {"ids": ids, "fail": [world.plan.test_b_ends[0]]}, "failing"
    )
    assert (
        script.train(
            world.plan,
            world.out,
            failing,
            cache_dir=world.cache,
            note="retry",
            state=_fake_state(),
        )
        == 1
    )
    swapped = _stub_trainer(
        world.tmp,
        {"ids": {k: next(iter(ids.values())) for k in ids}, "fail": []},
        "swapped",
    )
    assert (
        script.train(
            world.plan,
            world.out,
            swapped,
            cache_dir=world.cache,
            note="again",
            state=_fake_state(),
        )
        == 1
    )
    with open(os.path.join(world.out, "train.json"), encoding="utf-8") as f:
        assert "not the one asked for" in json.load(f)["trainings"][1]["error"]
    assert len(os.listdir(os.path.join(world.out, "superseded"))) == 2


def _fail_past_the_sandbox(script, monkeypatch):
    """Anything past sandbox()'s refusal fails loudly before it can create a folder."""
    import pt_paths

    def leaked(*a, **k):
        raise AssertionError("sandbox() let the command through")

    for name in ("fetch", "train", "run", "report"):
        monkeypatch.setattr(script, name, leaked)
    monkeypatch.setattr(pt_paths, "data_dir", leaked)
    monkeypatch.setattr(pt_paths, "cache_dir", leaked)


def test_every_command_refuses_without_a_sandbox_home(script, monkeypatch):
    _fail_past_the_sandbox(script, monkeypatch)
    inside = os.path.join(REPO, "docs", "scratch-home")
    for command in ("fetch", "train", "run", "report"):
        for value in (None, inside, "relative-home"):
            with monkeypatch.context() as m:
                if value is None:
                    m.delenv("POWERTRADER_HOME", raising=False)
                else:
                    m.setenv("POWERTRADER_HOME", value)
                with pytest.raises(SystemExit):
                    script.main([command])
    assert not os.path.exists(inside) and not os.path.exists("relative-home")
    with pytest.raises(SystemExit):
        script.main(["fetch", "--supersede", "why"])  # train and run only


def test_the_header_split_keeps_everything_up_to_the_marker(script):
    header, rest = script.split_header(HEADER + "old results\n")
    assert header == HEADER and rest == "old results\n"
    with pytest.raises(script.Stop):
        script.split_header("no marker here\n")


def _section(vs, rank, holds=0, e2=0):
    counts = {
        "BARS_MISSING": holds,
        "TIMEFRAME_UNKNOWN": 0,
        "BOUNDS_NOT_CONVERGED": e2,
        "by_reason": {},
    }
    return {
        "out_of_sample": {
            "strategy": {"vs_buy_hold_pct": vs},
            "holds": counts,
            "quirks": {"decisions": 10, "e1": 0, "e1_share": 0.0, "e2": e2},
        },
        "baseline": {"rank": rank},
    }


def _b_window(pair, tf, ov, end, vs, holds=0, e2=0):
    return {
        "pair": pair, "timeframe": tf, "overlays": ov, "from": end, "to": end, "train_end": end,
        "strategy": {"vs_buy_hold_pct": vs},
        "holds": {"BARS_MISSING": holds, "TIMEFRAME_UNKNOWN": 0, "BOUNDS_NOT_CONVERGED": e2},
        "quirks": {"decisions": 10, "e1": 0, "e1_share": 0.0, "e2": e2},
    }  # fmt: skip


def _synthetic_results(
    plan,
    none=(5.0, 99.0),
    overlay=(-5.0, 1.0, 3, 2),
    b_none=(1.0, 0, 0),
    b_overlay=(-9.0, 4, 0),
):
    results = {"test_a": {}, "test_b": []}
    for pair in plan.pairs:
        for tf in plan.primary:
            results["test_a"][f"{pair}|{tf}|none"] = _section(*none)
            results["test_a"][f"{pair}|{tf}|OVL-ATR+OVL-COOLDOWN"] = _section(*overlay)
            for end in plan.test_b_ends:
                results["test_b"].append(_b_window(pair, tf, "none", end, *b_none))
                results["test_b"].append(
                    _b_window(pair, tf, "OVL-ATR+OVL-COOLDOWN", end, *b_overlay)
                )
    return results


def test_the_verdict_comes_from_the_runs_without_overlays_only(script):
    """Test A and Test B inputs, holds and notes are taken from the runs without
    overlays; the overlay runs (here all losing, with holds) change nothing."""
    ev = script.evaluate(script.PLAN, _synthetic_results(script.PLAN))
    assert ev["verdict"]["verdict"] == me.EDGE
    assert ev["not_assessable"] == [] and ev["gap"] == []
    assert len(ev["test_b"]) == 36 and all(w["vs_bh"] == 1.0 for w in ev["test_b"])


def test_the_gap_pass_note_counts_test_b_per_combination(script):
    plan = script.PLAN
    results = _synthetic_results(
        plan, b_none=(1.0, 0, 1)
    )  # one limit hit in every Test B window
    results["test_a"]["BTCUSDT|1h|none"] = _section(5.0, 99.0, e2=2)
    ev = script.evaluate(plan, results)
    assert ev["gap"][0] == ("BTCUSDT 1h", "Test A", 2)
    assert sorted(ev["gap"][1:]) == sorted(
        (f"{p} {tf}", "Test B", 9) for p in plan.pairs for tf in plan.primary
    )


def test_a_verdict_that_does_not_recheck_stops(script, monkeypatch):
    monkeypatch.setattr(me, "recheck_verdict", lambda a, b: "something else")
    with pytest.raises(script.Stop, match="does not recheck"):
        script.evaluate(script.PLAN, _synthetic_results(script.PLAN))


def test_a_run_needs_its_declared_number_of_seeds_and_exact_matches(
    script, monkeypatch
):
    hourly = _hourly(400)
    strat = SimpleNamespace(trades=_trades(5, 5, 5), kpis={"total_return_pct": 1.0})
    plan = script.Plan(seed_ranges={"BTCUSDT 1h": (0, 4)}, seeds_per_run=5)
    with pytest.raises(script.Stop, match="4 seeds, not 5"):
        script.run_baseline(hourly, "BTCUSDT", "1h", 50, 350, strat, (), plan, {})
    plan = script.Plan(seed_ranges={"BTCUSDT 1h": (0, 5)}, seeds_per_run=5)
    out = script.run_baseline(hourly, "BTCUSDT", "1h", 50, 350, strat, (), plan, {})
    assert (out["N"], out["H_used"], len(out["seeds"]), out["flagged_seeds"]) == (
        3,
        5,
        5,
        [],
    )
    # without overlays a seed that does not make exactly N trades of H bars stops the run
    real = rb.run_seed
    monkeypatch.setattr(
        rb, "run_seed", lambda *a, **k: {**real(*a, **k), "trade_count": 2}
    )
    with pytest.raises(script.Stop, match="trades of"):
        script.run_baseline(hourly, "BTCUSDT", "1h", 50, 350, strat, (), plan, {})


def test_no_trade_no_fit_and_a_reduced_hold(script):
    hourly = _hourly(400)
    plan = script.Plan(seed_ranges={"BTCUSDT 1h": (0, 5)}, seeds_per_run=5)
    none = script.run_baseline(
        hourly,
        "BTCUSDT",
        "1h",
        50,
        350,
        SimpleNamespace(trades=[], kpis={}),
        (),
        plan,
        {},
    )
    assert (
        none["no_baseline"] == "STRAT-003 made no trade (N = 0)"
        and none["rank"] is None
    )
    assert none["seeds"] == [] and "H_used" not in none
    crowded = SimpleNamespace(
        trades=_trades(*[1] * 160), kpis={"total_return_pct": 0.0}
    )
    full = script.run_baseline(hourly, "BTCUSDT", "1h", 50, 350, crowded, (), plan, {})
    assert (
        full["H_used"] is None
        and full["H_reduced"]
        and "do not fit" in full["no_baseline"]
    )
    long_holds = SimpleNamespace(
        trades=_trades(*[40] * 20), kpis={"total_return_pct": 0.0}
    )
    reduced = script.run_baseline(
        hourly, "BTCUSDT", "1h", 50, 350, long_holds, (), plan, {}
    )
    assert (
        reduced["H"] == 40 and reduced["H_reduced"] and reduced["H_used"] == 13
    )  # 20 x 14 <= 299
    assert all(s["bars_held"] == [13] for s in reduced["seeds"])


def test_seeds_outside_ten_percent_of_n_are_flagged_and_kept(script, monkeypatch):
    hourly = _hourly(400)
    strat = SimpleNamespace(trades=_trades(*[4] * 20), kpis={"total_return_pct": 1.0})
    counts = iter(
        [20, 18, 17, 22, 23]
    )  # 18 and 22 are within 10% of 20; 17 and 23 are not
    real = rb.run_seed
    monkeypatch.setattr(
        rb, "run_seed", lambda *a, **k: {**real(*a, **k), "trade_count": next(counts)}
    )
    plan = script.Plan(seed_ranges={"BTCUSDT 1h": (0, 5)}, seeds_per_run=5)
    out = script.run_baseline(
        hourly, "BTCUSDT", "1h", 50, 350, strat, ("OVL-COOLDOWN",), plan, {}
    )
    assert out["flagged_seeds"] == [2, 4] and len(out["seeds"]) == 5


def test_a_window_whose_decisions_were_not_all_recorded_stops(tmp_path, script):
    """One decision per bar but the window's last, or the counts would be wrong."""
    frames = hc.all_timeframes(_hourly())
    model_id = _publish(tmp_path / "crafted", "crafted", h3.CRAFTED)
    runner = script.strat003_runner(model_id, (), frames)
    real = type(runner).evaluate

    def forgetful(self, *args, **kwargs):
        decision = real(self, *args, **kwargs)
        if len(self.records) == 3:
            self.records.pop()  # one decision goes unrecorded
        return decision

    runner.evaluate = forgetful.__get__(runner)
    start = 24 * 7 * 3
    with pytest.raises(script.Stop, match="decisions for"):
        script._scored(
            frames["1h"], runner, "BTCUSDT", "1h", start, start + 50, script.PLAN
        )


def test_two_beating_combinations_are_not_enough():
    test_a = dict(zip(COMBOS, [_a(5, 99), _a(1, 99), _a(-1, 99), _a(-2, 99)]))
    v = me.verdict(test_a, _b([1.0] * 36), 36)
    assert not v["criterion_1"] and v["criterion_2"] and v["criterion_3"]
    assert v["verdict"] == me.NO_EDGE
    assert me.recheck_verdict(test_a, _b([1.0] * 36)) == me.NO_EDGE


def test_an_unknown_timeframe_hold_is_a_data_hold_and_never_e1():
    records = [
        _rec(reason="TIMEFRAME_UNKNOWN", all_seven=False),
        _rec(reason="BARS_MISSING:1hour", all_seven=False),
        _rec(),
    ]
    h = me.hold_counts(records)
    assert (h["TIMEFRAME_UNKNOWN"], h["BARS_MISSING"], me.data_holds(h)) == (1, 1, 2)
    assert me.quirk_counts(records) == {
        "decisions": 3,
        "e1": 0,
        "e1_share": 0.0,
        "e2": 0,
    }


def test_the_boundaries_a_zero_median_and_a_hold_that_just_fits():
    test_a = dict(zip(COMBOS, [_a(5, 99)] * 4))
    zero = [-1.0] * 17 + [-0.5, 0.5] + [5.0] * 17  # the mean of the middle two is 0
    v = me.verdict(test_a, _b(zero), 36)
    assert (
        v["pooled_median"] == 0.0
        and not v["criterion_3"]
        and v["verdict"] == me.NO_EDGE
    )
    assert me.recheck_verdict(test_a, _b(zero)) == me.NO_EDGE
    assert rb.fit_hold(3, 3, 13) == (3, False)  # 3 x 4 == 12 == L - 1: fits exactly
    assert rb.fit_hold(3, 4, 13) == (3, True)
    entries = rb.placement(5, 13, 3, 3)
    assert entries == [1, 5, 9] and entries[-1] + 3 == 12


def test_the_holdout_is_checked_whenever_the_trainer_wrote_it():
    unavailable = _manifest(status="unavailable", start="2025-01-01T00:00:00Z")
    with pytest.raises(ValueError):
        me.check_test_a_holdout(unavailable)
    blank = {"validation": {"status": "unavailable", "reason": "no fit"}}
    me.check_test_a_holdout(blank)  # the trainer wrote no dates: nothing to compare


def test_a_model_the_store_cannot_load_stops_the_run(world, script):
    _fetched(world, script)
    _publish_all(world, script)
    path = os.path.join(world.out, "train.json")
    with open(path, encoding="utf-8") as f:
        train = json.load(f)
    train["trainings"][0]["model_id"] = "missing-model"
    script._write_json(path, train)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    assert (
        "missing-model" in _results(world)["reason"]
        and "not found" in _results(world)["reason"]
    )


# --- second review round ----------------------------------------------------------------------


def test_the_not_assessable_note_lists_each_window_without_overlays(script):
    plan = script.PLAN
    results = _synthetic_results(
        plan
    )  # the overlay runs keep their own holds (3 and 4)
    results["test_a"]["BTCUSDT|1h|none"] = _section(5.0, 99.0, holds=2)
    eth4 = [
        w
        for w in results["test_b"]
        if (w["pair"], w["timeframe"], w["overlays"]) == ("ETHUSDT", "4h", "none")
    ]
    eth4[0]["holds"]["TIMEFRAME_UNKNOWN"] = 1
    eth4[3]["holds"]["BARS_MISSING"] = 4
    eth4[0]["from"], eth4[0]["to"] = (
        "2024-07-01T00:00:00+00:00",
        "2024-09-30T20:00:00+00:00",
    )
    eth4[3]["from"], eth4[3]["to"] = (
        "2025-04-01T00:00:00+00:00",
        "2025-06-30T20:00:00+00:00",
    )
    ev = script.evaluate(plan, results)
    assert ev["not_assessable"] == [
        ("BTCUSDT 1h", "Test A out-of-sample", 2),
        ("ETHUSDT 4h", "Test B 2024-07-01..2024-09-30", 1),
        ("ETHUSDT 4h", "Test B 2025-04-01..2025-06-30", 4),
    ]
    assert not ev["verdict"]["criterion_3"] and ev["verdict"]["verdict"] == me.NO_EDGE
    line = me.verdict_line(
        ev["verdict"]["verdict"],
        {"BTC": _manifest(), "ETH": _manifest()},
        ev["not_assessable"],
    )
    assert line.endswith(
        " (not assessable: 7 decisions held for missing bars or an unknown timeframe: "
        "BTCUSDT 1h, Test A out-of-sample, 2; ETHUSDT 4h, Test B 2024-07-01..2024-09-30, 1; "
        "ETHUSDT 4h, Test B 2025-04-01..2025-06-30, 4)"
    )


def test_fetch_of_the_declared_plan_asks_for_its_closed_bars(world, script):
    # the synthetic files are not batch 1's, so it stops after fetching: only the calls matter
    script.fetch(
        script.PLAN,
        world.out,
        str(world.tmp / "plan-cache"),
        fetcher_factory=lambda: None,
        state=_fake_state(),
    )
    ends = {(s, tf): end for s, tf, _, end in world.calls}
    assert len(world.calls) == 14 and all(
        start == "2023-01-01" for _, _, start, _ in world.calls
    )
    for pair in script.PLAN.pairs:
        for tf in ("1h", "2h", "4h", "8h", "12h", "1d"):
            assert ends[(pair, tf)] == pd.Timestamp("2026-10-01", tz="UTC")
        assert ends[(pair, "1w")] == pd.Timestamp(
            "2026-09-28", tz="UTC"
        )  # Monday: the week ending by the end


def test_a_run_that_stopped_after_scoring_keeps_its_outputs_until_a_note(world, script):
    path = world.sources["BTCUSDT 1h"]
    frame = pd.read_csv(path)
    gap = int(pd.Timestamp("2024-02-05T05:00:00Z").timestamp() * 1000)
    frame[frame["open_time_ms"] != gap].to_csv(path, index=False)
    world.plan = _mini(script, world.sources)
    _fetched(world, script)
    _publish_all(world, script)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    results = _results(world)
    assert results["scored"] and os.path.isdir(os.path.join(world.out, "runs"))
    with pytest.raises(script.Stop, match="--supersede"):
        script.run(world.plan, world.out, world.cache, state=_fake_state())
    assert os.path.isdir(os.path.join(world.out, "runs")) and not os.path.exists(
        os.path.join(world.out, "superseded")
    )
    body = _report(world, script)
    assert (
        f"**Stopped after scoring {len(results['scored'])} run(s); nothing here counts"
        in body
    )
    assert "Scored before the stop: Test A BTCUSDT 1h none" in body
    assert (
        script.run(
            world.plan,
            world.out,
            world.cache,
            note="fixed the data",
            state=_fake_state(),
        )
        == 1
    )
    assert "stopped after scoring" in _report(world, script)


def test_a_failed_move_leaves_everything_in_place(world, script, monkeypatch):
    _scored_world(world, script)
    real = os.rename
    calls = []

    def flaky(a, b):
        calls.append(a)
        if len(calls) == 2:
            raise OSError("locked")
        return real(a, b)

    monkeypatch.setattr(os, "rename", flaky)
    with pytest.raises(script.Stop, match="nothing moved"):
        script.run(world.plan, world.out, world.cache, note="x", state=_fake_state())
    monkeypatch.setattr(os, "rename", real)
    for name in ("results.json", "runs", "baselines"):
        assert os.path.exists(os.path.join(world.out, name))
    assert os.listdir(os.path.join(world.out, "superseded")) == []


def test_header_commits_skip_results_only_commits_and_refuse_frozen_ones(
    script, monkeypatch
):
    log = "aaa1111 2026-10-07 results\nbbb2222 2026-10-07 header\n"
    touched = {
        "aaa1111": "docs/dev/BACKTEST-REPORT-model-1.md\napp/x.py\n",
        "bbb2222": "docs/dev/BACKTEST-REPORT-model-1.md\n",
    }

    def fake_git(*args):
        if args[0] == "log":
            return log
        if args[0] == "show":
            return touched[args[-1]]
        raise AssertionError(args)

    headers = {"aaa1111": "H2", "aaa1111^": "H2", "bbb2222": "H2", "bbb2222^": "H1"}
    monkeypatch.setattr(script, "_git", fake_git)
    monkeypatch.setattr(script, "_header_at", lambda c: headers[c])
    assert script.header_commits("c" * 40) == ["bbb2222 2026-10-07 header"]
    headers["aaa1111^"] = "H1"  # now aaa1111 changes the header, and it touched app/
    with pytest.raises(script.Stop, match="also changed frozen files"):
        script.header_commits("c" * 40)


def test_criterion_2_reads_not_applicable_when_nothing_meets_criterion_1(
    world, script, monkeypatch
):
    _scored_world(world, script)
    real = script.evaluate

    def none_meet(plan, results):
        ev = real(plan, results)
        ev["verdict"] = {
            **ev["verdict"],
            "criterion_1": False,
            "criterion_1_combinations": [],
            "criterion_2_failing": [],
        }
        return ev

    monkeypatch.setattr(script, "evaluate", none_meet)
    body = _report(world, script)
    assert "random baseline): not applicable (no combination meets criterion 1)" in body
    # and so in a superseded run's line, from the verdict it gave
    assert (
        script.run(
            world.plan, world.out, world.cache, note="again", state=_fake_state()
        )
        == 0
    )
    assert "criteria 1-3: not met, not applicable," in _report(world, script)


def test_a_superseded_train_shows_as_train_outputs_only(world, script):
    _fetched(world, script)
    ids = {}
    for job in world.plan.trainings():
        model_id = f"stub-{job['coin']}-{job['test']}-{job['train_end'][:10]}"
        _publish(world.tmp / model_id, model_id, h3.CRAFTED, job["coin"], job["train_end"],
                 **_manifest_fields(script, world.plan, job))  # fmt: skip
        ids[f"{job['coin']}|{job['train_end']}"] = model_id
    stub = _stub_trainer(world.tmp, {"ids": ids, "fail": []}, "only")
    assert (
        script.train(
            world.plan, world.out, stub, cache_dir=world.cache, state=_fake_state()
        )
        == 0
    )
    assert (
        script.train(
            world.plan,
            world.out,
            stub,
            cache_dir=world.cache,
            note="re-trained",
            state=_fake_state(),
        )
        == 0
    )
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 0
    assert (
        "train outputs only (train.json, manifests). What changed and why: re-trained"
        in _report(world, script)
    )


def test_train_after_a_run_that_stopped_before_scoring_needs_no_note(world, script):
    _fetched(world, script)
    assert (
        script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    )  # no train.json yet
    ids = {}
    for job in world.plan.trainings():
        model_id = f"stub-{job['coin']}-{job['test']}-{job['train_end'][:10]}"
        _publish(world.tmp / model_id, model_id, h3.CRAFTED, job["coin"], job["train_end"],
                 **_manifest_fields(script, world.plan, job))  # fmt: skip
        ids[f"{job['coin']}|{job['train_end']}"] = model_id
    stub = _stub_trainer(world.tmp, {"ids": ids, "fail": []}, "after-stop")
    assert (
        script.train(
            world.plan, world.out, stub, cache_dir=world.cache, state=_fake_state()
        )
        == 0
    )
    (only,) = os.listdir(os.path.join(world.out, "superseded"))
    with open(
        os.path.join(world.out, "superseded", only, "note.json"), encoding="utf-8"
    ) as f:
        assert (
            json.load(f)["note"]
            == "train: replaced a run that stopped before scoring anything"
        )


def test_an_interrupted_run_is_kept_and_its_commit_holds_the_header(world, script):
    _scored_world(world, script)
    os.remove(
        os.path.join(world.out, "results.json")
    )  # killed: no record but its run files
    assert (
        script.run(
            world.plan,
            world.out,
            world.cache,
            note="interrupted",
            state=_fake_state(commit="a" * 40),
        )
        == 0
    )
    (moved,) = os.listdir(os.path.join(world.out, "superseded"))
    assert moved == "01-run-fffffff"  # named after the commit its run files record
    body = _report(world, script, state=_fake_state(commit="a" * 40))
    assert "interrupted after scoring 24 run(s), which do not count" in body
    report = world.tmp / "report.md"
    report.write_text(HEADER, encoding="utf-8")
    headers = {COMMIT: HEADER.replace("Declared", "Earlier"), "a" * 40: HEADER}
    with pytest.raises(script.Stop, match="header changed after an earlier run scored"):
        _call_report(
            world,
            script,
            report,
            header_at=lambda c: headers[c],
            state=_fake_state(commit="a" * 40),
        )


def test_a_run_still_marked_running_is_not_reported(world, script, monkeypatch):
    _fetched(world, script)
    _publish_all(world, script)

    def killed(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(script, "_score_all", killed)
    with pytest.raises(KeyboardInterrupt):
        script.run(world.plan, world.out, world.cache, state=_fake_state())
    assert _results(world) == {"status": "running", "code": _fake_state()}
    report = world.tmp / "report.md"
    report.write_text(HEADER, encoding="utf-8")
    with pytest.raises(script.Stop, match="did not finish"):
        _call_report(world, script, report)


def test_the_trainer_commit_may_be_an_earlier_one_with_the_same_trainer_files(
    world, script, monkeypatch
):
    _fetched(world, script)
    earlier = "a" * 40
    _publish_all(world, script, trainer_git_commit=earlier)
    calls = []

    def same(old, new, paths):
        calls.append((old, new, tuple(paths)))
        return []

    monkeypatch.setattr(script, "_changed_between", same)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 0
    assert calls and calls[0][:2] == (earlier, COMMIT)
    assert set(calls[0][2]) == {
        f"app/{n}" for n in script.MODEL_CODE + script.TRAINER_DATA_CODE
    }
    monkeypatch.setattr(
        script,
        "_changed_between",
        lambda old, new, paths: ["app/market_data/candles.py"],
    )
    assert (
        script.run(
            world.plan, world.out, world.cache, note="again", state=_fake_state()
        )
        == 1
    )
    assert "or a commit with the same trainer files" in _results(world)["reason"]


def test_a_trainer_commit_that_is_not_a_full_hash_is_refused(world, script):
    _fetched(world, script)
    _publish_all(world, script, trainer_git_commit=None)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 1
    assert "not cleanly at" in _results(world)["reason"]


def test_a_home_overlapping_the_real_per_user_folders_is_refused(
    script, monkeypatch, tmp_path
):
    import pt_paths

    def leaked(*a, **k):
        raise AssertionError("sandbox() let the command through")

    for name in ("fetch", "train", "run", "report"):
        monkeypatch.setattr(script, name, leaked)
    monkeypatch.setattr(pt_paths, "data_dir", leaked)
    monkeypatch.setattr(pt_paths, "cache_dir", leaked)
    real = tmp_path / "real-data"
    monkeypatch.setattr(
        pt_paths,
        "_platform_dir",
        lambda kind: str(real) if kind == "data" else str(tmp_path / kind),
    )
    for home in (real / "inside", real, "~/real-data/inside"):
        with monkeypatch.context() as m:
            m.setenv("POWERTRADER_HOME", str(home))
            m.setenv("HOME", str(tmp_path))  # "~" is tmp_path here (POSIX)
            m.setenv("USERPROFILE", str(tmp_path))  # and on Windows
            with pytest.raises(SystemExit):
                script.main(["fetch"])
    assert not real.exists()


def test_the_frozen_code_log_starts_at_the_first_header_commit(script, monkeypatch):
    seen = []

    def fake_git(*args):
        seen.append(args)
        return "ccc3333 2026-10-07 freeze\n"

    monkeypatch.setattr(script, "_git", fake_git)
    log = script.frozen_commits_after(["ddd4444 2026-10-08 header amended"], "e" * 40)
    assert log == ["ccc3333 2026-10-07 freeze"]
    (args,) = seen
    assert f"{script.FIRST_HEADER_COMMIT}..{'e' * 40}" in args
    assert args[args.index("--") + 1 :] == script.FROZEN
    assert script.frozen_commits_after([], "e" * 40) == []


def test_every_training_keeps_its_own_log(world, script):
    import pt_paths

    _fetched(world, script)
    ids = {}
    for job in world.plan.trainings():
        model_id = f"stub-{job['coin']}-{job['test']}-{job['train_end'][:10]}"
        _publish(world.tmp / model_id, model_id, h3.CRAFTED, job["coin"], job["train_end"],
                 **_manifest_fields(script, world.plan, job))  # fmt: skip
        ids[f"{job['coin']}|{job['train_end']}"] = model_id
    stub = _stub_trainer(world.tmp, {"ids": ids, "fail": []}, "logs")
    assert (
        script.train(
            world.plan, world.out, stub, cache_dir=world.cache, state=_fake_state()
        )
        == 0
    )
    assert (
        script.train(
            world.plan,
            world.out,
            stub,
            cache_dir=world.cache,
            note="again",
            state=_fake_state(),
        )
        == 0
    )
    root = os.path.join(pt_paths.data_dir(), "backtest-model-1", "trainer")
    logs = [f for f in os.listdir(root) if f.endswith(".log")]
    assert len(logs) == 2 * len(world.plan.trainings())


def test_an_unscored_stop_at_another_header_does_not_block_the_report(world, script):
    """A header amendment is allowed before Test A: a run that stopped before scoring,
    under the earlier header, does not hold the header."""
    _fetched(world, script)
    assert (
        script.run(
            world.plan, world.out, world.cache, state=_fake_state(commit="b" * 40)
        )
        == 1
    )
    _publish_all(world, script)
    assert script.run(world.plan, world.out, world.cache, state=_fake_state()) == 0
    headers = {"b" * 40: HEADER.replace("Declared", "Earlier"), COMMIT: HEADER}
    body = _report(world, script, header_at=lambda c: headers[c])
    assert "stopped, nothing scored: no train.json" in body
