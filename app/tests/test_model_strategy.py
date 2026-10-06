"""FDS-MDL Phase 3: STRAT-003, the trained pattern model as a catalogue strategy.

* The catalogue entry (family ``model``, a closed family enum), its parameters, and
  ``strategy.active_id`` staying STRAT-001.
* Loaders refuse a model without a matching manifest: the strategy, the backtest CLI and
  the signal engine (which fails closed: no signals, an ERROR).
* A decision at *t* never uses a bar that closes at or after *t* (acceptance 6); a
  missing bar holds instead of using an older one.
* STRAT-003 reproduces the legacy runner's LONG/SHORT decisions bar for bar
  (acceptance 7): on the recorded fixture (app/tests/fixtures/strat003_thinker_record.json,
  from app/tests/record_strat003_fixture.py) and live against the real
  ``pt_thinker.step_coin`` on a trained model.
* The backtester refuses ``LOOKAHEAD_MODEL`` when the model's training window ends after
  the first scored bar (acceptance 5), and a model trained on another pair.
* ``on_bar`` does no I/O and is deterministic.

All candles are synthetic; the network is blocked here and in every child."""

import builtins
import json
import logging
import os
import shutil
import sys
from datetime import timedelta

import pandas as pd
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for _path in (APP_DIR, TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import helpers_candles as hc  # noqa: E402
import helpers_strat003 as h3  # noqa: E402
import helpers_thinker as hth  # noqa: E402
import helpers_trainer as ht  # noqa: E402
import model_store  # noqa: E402
import pattern_model  # noqa: E402
import pt_paths  # noqa: E402
import pt_pattern_trainer as ppt  # noqa: E402
from backtest import cli as bt_cli  # noqa: E402
from backtest.engine import (  # noqa: E402
    LookaheadError,
    evaluate_split,
    run_backtest,
)
from market_data import candles  # noqa: E402
from market_data.timeframes import candle_timeframe_seconds  # noqa: E402
from signal_engine import SignalEngine  # noqa: E402
from strategies import catalogue  # noqa: E402
from strategies.base import Action, StrategyError  # noqa: E402
from strategies.factory import build_runner  # noqa: E402
from strategies.model_strategy import TrainedModelStrategy  # noqa: E402
from strategies.runner import StrategyRunner  # noqa: E402

FIXTURE = os.path.join(TESTS_DIR, "fixtures", "strat003_thinker_record.json")
TFS = pattern_model.TIMEFRAMES
HOUR = 3600


@pytest.fixture(autouse=True)
def guarded(monkeypatch, tmp_path, isolated_user_dirs):
    monkeypatch.chdir(tmp_path)
    return ht.guard_trainer_children(monkeypatch, tmp_path)


@pytest.fixture(scope="module")
def record():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def publish_scenario(record, index, folder, model_id=None, train_end=None):
    """Publish the fixture's model ``index`` from ``folder``; returns its model_id."""
    scenario = record["scenarios"][index]
    os.makedirs(folder, exist_ok=True)
    for name, text in scenario["model_files"].items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(text)
    model_id = model_id or scenario["model_id"]
    kwargs = {"train_end": train_end} if train_end else {}
    h3.publish_files(str(folder), model_id, **kwargs)
    return model_id


@pytest.fixture
def crafted(record, tmp_path):
    """The fixture's first model published in the per-test store, and its bars (seeded
    into the candle cache too): (model_id, hourly frame, frames by candle timeframe)."""
    model_id = publish_scenario(record, 0, str(tmp_path / "crafted-model"))
    hourly = h3.hourly_from_rows(record["hourly"])
    frames = hc.all_timeframes(hourly)
    hc.seed_cache(candles.cache_dir_default(), "BTCUSDT", frames)
    return model_id, hourly, frames


def strategy(model_id, frames=None, **params):
    strat = TrainedModelStrategy(model_id=model_id, **params)
    if frames is not None:
        strat.use_bars(frames)
    return strat


def decisions_of(record, index=0):
    """The scenario's decisions, each with the bars the runner was served."""
    return [
        dict(d, served=served)
        for d, served in zip(record["scenarios"][index]["decisions"], record["served"])
    ]


# --- the catalogue -------------------------------------------------------------------------


def test_strat003_is_a_main_strategy_of_the_model_family():
    entry = catalogue.get_entry("STRAT-003")
    assert entry["family"] == "model" and entry["class_type"] == "main"
    assert entry["default_params"] == {
        "model_id": "",
        "min_tf_agree": 3,
        "timeframes": list(TFS),
    }
    assert "min_tf_agree" in entry["entry_logic_summary"]
    assert "primary timeframe" in entry["exit_logic_summary"]
    assert catalogue.FAMILIES == ("trend", "risk_overlay", "model")
    assert "STRAT-003" in catalogue.list_ids("main")


def test_a_family_outside_the_enum_is_refused():
    entry = dict(catalogue.get_entry("STRAT-000"), family="exotic")
    with pytest.raises(catalogue.CatalogueError, match="family must be one of"):
        catalogue.build_catalogue([entry], {"STRAT-000": object})


def test_the_default_strategy_stays_strat_001():
    import pt_settings_manager
    from strategies.settings import DEFAULT_ACTIVE_ID, read_strategy_settings

    assert DEFAULT_ACTIVE_ID == "STRAT-001"
    assert read_strategy_settings({}).active_id == "STRAT-001"
    with open(pt_settings_manager.__file__, encoding="utf-8") as f:
        assert '"active_id": "STRAT-001"' in f.read()


@pytest.mark.parametrize(
    "params",
    [
        {"model_id": "a/b"},
        {"model_id": 7},
        {"timeframes": []},
        {"timeframes": ["1hour", "1hour"]},
        {"timeframes": ["5min"]},
        {"timeframes": "1hour"},
        {"timeframes": [["1hour"]]},
        {"timeframes": [{"tf": "1hour"}]},
        {"bars": {}},
        {"min_tf_agree": 0},
        {"min_tf_agree": 8},
        {"min_tf_agree": 2.0},
    ],
)
def test_bad_parameters_are_refused(params):
    with pytest.raises(catalogue.ParamError):
        catalogue.resolve_params("STRAT-003", params)


def test_more_agreement_than_counted_timeframes_is_refused(crafted):
    model_id, _, frames = crafted
    with pytest.raises(StrategyError, match="could never enter"):
        strategy(model_id, frames, timeframes=["1hour", "2hour"], min_tf_agree=3)


# --- loaders refuse (acceptance 4) -----------------------------------------------------------


def test_strat003_without_a_model_is_refused(caplog):
    with caplog.at_level(logging.ERROR, logger="model_store"):
        with pytest.raises(model_store.ModelStoreError, match="no model_id"):
            catalogue.create("STRAT-003")
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def _damage(model_id):
    folder = model_store.model_dir(model_id)
    with open(os.path.join(folder, "memories_1hour.txt"), "a", encoding="utf-8") as f:
        f.write("~1 2{}3{}4")


@pytest.mark.parametrize("case", ["unknown", "changed-file"])
def test_a_model_without_a_matching_manifest_is_refused(crafted, case, caplog):
    model_id, _, frames = crafted
    if case == "unknown":
        model_id = "BTC-20240101T0000Z-000000000000"
    else:
        _damage(model_id)
    with caplog.at_level(logging.ERROR, logger="model_store"):
        with pytest.raises(model_store.ModelStoreError):
            strategy(model_id, frames)
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def _candles_file(tmp_path, hourly):
    path = tmp_path / "BTCUSDT_1h.csv"
    candles._write_cache(str(path), hourly)
    return str(path)


def test_the_backtest_cli_refuses_a_model_without_a_matching_manifest(
    crafted, tmp_path, capsys
):
    model_id, hourly, _ = crafted
    _damage(model_id)
    out = tmp_path / "out" / "result.json"
    code = bt_cli.main(
        ["--strategy", "STRAT-003", "--params", json.dumps({"model_id": model_id}),
         "--candles-file", _candles_file(tmp_path, hourly), "--offline",
         "--out", str(out)]
    )  # fmt: skip
    assert code == 2
    assert "does not match its manifest" in capsys.readouterr().err
    assert not out.exists()


UNPUBLISHED = "BTC-20240101T0000Z-000000000000"


def test_strat003_as_the_active_strategy_is_a_settings_problem():
    """The engine runs strategies with their default parameters, which name no model
    for STRAT-003: the settings say so, and the hub strip shows SIGNALS: BLOCKED."""
    from strategies.settings import read_strategy_settings

    s = read_strategy_settings({"strategy": {"active_id": "STRAT-003"}})
    assert "needs a trained model" in s.problem
    assert s.note == "SIGNALS: BLOCKED"
    engine = SignalEngine(settings_source={"strategy": {"active_id": "STRAT-003"}})
    assert engine.decide("BTC") is None
    assert "needs a trained model" in engine.block_reason()


def test_the_signal_engine_fails_closed_without_a_model(monkeypatch, caplog):
    """Were STRAT-003's default model one that is not published (or whose manifest does
    not match), the engine would refuse it: no signals, an ERROR."""
    monkeypatch.setitem(
        catalogue.get_entry("STRAT-003")["default_params"], "model_id", UNPUBLISHED
    )
    engine = SignalEngine(settings_source={"strategy": {"active_id": "STRAT-003"}})
    with caplog.at_level(logging.ERROR):
        assert engine.decide("BTC") is None
        assert engine.decide("BTC") is None
    assert "STRAT-003 cannot be used" in engine.block_reason()
    assert "not found" in engine.block_reason()
    assert any(
        r.levelno == logging.ERROR and "STRAT-003 cannot be used" in r.getMessage()
        for r in caplog.records
    )
    # the trader's position bookkeeping still works; it just gets no signals
    pos = engine.ensure_position("BTC", 100.0)
    assert pos.entry_price == 100.0 and pos.overlay_state == {}
    engine._settings_source = {"strategy": {"active_id": "STRAT-000"}}
    assert engine.block_reason() is None


# --- the bars a decision may use (acceptance 6) ------------------------------------------------


def _signal_at(strat, frame, close_s, bar_seconds=HOUR):
    return h3.strategy_signals(strat, frame, [close_s], bar_seconds)[0]


def test_a_decision_never_uses_a_bar_that_closes_at_or_after_t(crafted):
    model_id, hourly, frames = crafted
    # Monday 00:00 of week 4: every timeframe's current bar closes exactly at t
    t = pd.Timestamp(hourly["open_time"].iloc[0]) + pd.Timedelta(weeks=3)
    t_s = int(t.timestamp())
    clean = _signal_at(strategy(model_id, frames), frames["1h"], t_s)
    assert not clean.reason.startswith("BARS_MISSING")
    for tf in TFS:
        step = pd.Timedelta(
            seconds=candle_timeframe_seconds(pattern_model.CANDLE_TF[tf])
        )
        # the bar it uses closed one bar before t; the bar closing at t is not used
        assert clean.indicators[f"bar_{tf}"] == (t - 2 * step).timestamp(), tf
    poisoned = {}
    for ctf, frame in frames.items():
        frame = frame.copy()
        step = pd.Timedelta(seconds=candle_timeframe_seconds(ctf))
        late = frame["open_time"] + step >= t  # closes at or after t
        if ctf == "1h":  # except the bar decided on: its close is the price
            late &= frame["open_time"] != t - step
        frame.loc[late, ["open", "high", "low", "close"]] *= 1.5
        poisoned[ctf] = frame
    again = _signal_at(strategy(model_id, poisoned), poisoned["1h"], t_s)
    assert (again.action, again.reason, again.indicators) == (
        clean.action,
        clean.reason,
        clean.indicators,
    )


def test_a_missing_bar_holds_instead_of_using_an_older_one(crafted):
    model_id, hourly, frames = crafted
    t_s = int(pd.Timestamp(hourly["open_time"].iloc[-1]).timestamp()) + HOUR
    used = _signal_at(strategy(model_id, frames), frames["1h"], t_s).indicators
    frames = dict(frames)
    eight = frames["8h"]
    used_open = pd.Timestamp(int(used["bar_8hour"]), unit="s", tz="UTC")
    frames["8h"] = eight[eight["open_time"] != used_open].reset_index(drop=True)
    signal = _signal_at(strategy(model_id, frames), frames["1h"], t_s)
    assert signal.action is Action.HOLD and signal.reason == "BARS_MISSING:8hour"
    assert signal.indicators["expected_8hour"] == used["bar_8hour"]


# --- the runner's rule, bar for bar (acceptance 7) ----------------------------------------------


@pytest.mark.parametrize("index", [0, 1], ids=["two-inactive", "all-active"])
def test_strat003_reproduces_the_recorded_runner_bar_for_bar(
    crafted, record, index, tmp_path
):
    _, _, frames = crafted
    model_id = publish_scenario(record, index, str(tmp_path / f"scenario-{index}"))
    decisions = decisions_of(record, index)
    strat = strategy(model_id, frames)
    signals = h3.strategy_signals(
        strat, frames["1h"], [d["time"] for d in decisions], HOUR
    )
    model = model_store.load(model_id).model
    for d, s in zip(decisions, signals):
        assert not s.reason.startswith("BARS_MISSING"), (d["time"], s.reason)
        # the same bars as the runner was served
        for tf in TFS:
            assert s.indicators[f"bar_{tf}"] == d["served"][tf][0], (d["time"], tf)
        assert h3.sides_of(s) == d["tf_sides"], d["time"]
        assert (s.indicators["longs"], s.indicators["shorts"]) == (
            d["longs"],
            d["shorts"],
        )
        # the bounds the runner kept, from the same predictions
        predictions = [
            model.timeframes[tf].predict(d["served"][tf][1], d["served"][tf][4])
            for tf in TFS
        ]
        lows, highs = pattern_model.thinker_bounds(predictions)
        assert (lows, highs) == (d["low_bound_prices"], d["high_bound_prices"]), d[
            "time"
        ]
        # and the primary timeframe's bounds STRAT-003 reports: the padded ones it used
        padded_low = (d["low_bound_prices"] + [pattern_model.LOW_PLACEHOLDER] * 7)[0]
        padded_high = (d["high_bound_prices"] + [pattern_model.HIGH_PLACEHOLDER] * 7)[0]
        assert s.indicators["low_bound"] == float(padded_low), d["time"]
        assert s.indicators["high_bound"] == float(padded_high), d["time"]
        # the long-only mapping, with the short veto
        if d["tf_sides"][0] == "short":
            expected = Action.EXIT_LONG
        elif d["longs"] >= 3 and d["shorts"] == 0:
            expected = Action.ENTER_LONG
        else:
            expected = Action.HOLD
        assert s.action is expected, d["time"]
    actions = [s.action for s in signals]
    assert Action.ENTER_LONG in actions and Action.EXIT_LONG in actions
    lengths = {len(d["low_bound_prices"]) for d in decisions}
    if index == 0:  # the remap's dropped repeats: two and three inactive timeframes
        assert lengths == {5, 6}
    else:  # all seven kept: the gap pass's last pairs, and 1week on its own bound
        assert lengths == {7}
        assert {d["tf_sides"][6] for d in decisions} == {"long", "short", "none"}


def test_the_mapping_counts_the_chosen_timeframes(crafted, record):
    model_id, _, frames = crafted
    chosen = ["1hour", "2hour"]
    strat = strategy(model_id, frames, timeframes=chosen, min_tf_agree=1)
    decisions = decisions_of(record)
    signals = h3.strategy_signals(
        strat, frames["1h"], [d["time"] for d in decisions], HOUR
    )
    for d, s in zip(decisions, signals):
        counted = [d["tf_sides"][TFS.index(tf)] for tf in chosen]
        if d["tf_sides"][0] == "short":
            expected = Action.EXIT_LONG
        elif counted.count("long") >= 1 and counted.count("short") == 0:
            expected = Action.ENTER_LONG
        else:
            expected = Action.HOLD
        assert s.action is expected, d["time"]


def test_the_exit_follows_the_primary_timeframe(crafted, record):
    """On an 8-hour run the exit is SHORT on 8hour, not on 1hour."""
    model_id, hourly, frames = crafted
    strat = strategy(model_id, frames)
    eight = frames["8h"]
    closes = [int(t.timestamp()) + 8 * HOUR for t in eight["open_time"]][3:]
    signals = h3.strategy_signals(strat, eight, closes, 8 * HOUR)
    exits = 0
    for s in signals:
        if s.reason.startswith("BARS_MISSING"):
            continue
        is_exit = s.indicators["side_8hour"] == -1.0
        assert (s.action is Action.EXIT_LONG) == is_exit
        exits += is_exit
    assert exits > 0


def test_strat003_reproduces_the_live_runner_on_a_trained_model(tmp_path):
    """The real pt_thinker.step_coin on a model the trainer published, at 48 hourly
    closes after its training window, two sweeps each: the same sides, bounds and
    counts as STRAT-003, bar for bar."""
    start = pd.Timestamp("2024-01-01", tz="UTC")
    hours = 1680
    hourly = hc.synthetic_hourly(hours + 200, start, seed=5)
    frames = hc.all_timeframes(hourly)
    hc.seed_cache(candles.cache_dir_default(), "BTCUSDT", frames)
    folder = pt_paths.neural_dir()
    os.makedirs(folder, exist_ok=True)
    end = start + pd.Timedelta(hours=hours)
    cwd = os.getcwd()
    os.chdir(folder)
    try:
        assert ppt.main(["BTC", "--offline", "--train-start", start.isoformat(),
                         "--train-end", end.isoformat()]) == 0  # fmt: skip
    finally:
        os.chdir(cwd)
    with open(pt_paths.data_file("training_results", "btc_training_results.json"),
              encoding="utf-8") as f:  # fmt: skip
        model_id = json.load(f)["model_id"]
    closes = [int((end + pd.Timedelta(hours=k)).timestamp()) for k in range(1, 49)]
    records, out, code = hth.run_thinker(
        str(tmp_path / "drive"),
        "BTC",
        hth.bars_from_frames(frames),
        h3.thinker_decisions_at(hourly, closes),
    )
    assert code == 0, out[-3000:]
    strat = strategy(model_id, frames)
    signals = h3.strategy_signals(strat, frames["1h"], closes, HOUR)
    model = model_store.load(model_id).model
    for r, s in zip(records, signals):
        assert h3.sides_of(s) == r["tf_sides"], r["time"]
        assert s.indicators["longs"] == int(r["signals_dca_spread.txt"])
        assert s.indicators["shorts"] == int(r["signals_dca_single.txt"])
        for tf in TFS:
            assert s.indicators[f"bar_{tf}"] == r["served"][tf][0], (r["time"], tf)
        predictions = [
            model.timeframes[tf].predict(r["served"][tf][1], r["served"][tf][4])
            for tf in TFS
        ]
        assert pattern_model.thinker_bounds(predictions) == (
            r["low_bound_prices"],
            r["high_bound_prices"],
        ), r["time"]
    sides = [x for r in records for x in r["tf_sides"]]
    assert sides.count("long") > 0 and sides.count("short") > 0


# --- the rule's pieces ---------------------------------------------------------------------------


def _prediction(low, high, active=True):
    close = (low + high) / 2
    return pattern_model.Prediction(
        active=active,
        training_issue=False,
        move_pct=0.0,
        high_frac=0.0,
        low_frac=0.0,
        start_price=close,
        high_price=high if active else close,
        low_price=low if active else close,
        matched=1 if active else 0,
    )


def test_the_remap_drops_repeated_placeholders_and_shifts_later_bounds_left():
    """Timeframes 0 and 2 inactive, the others far enough apart that the gap pass
    moves nothing: the kept lists lose the second placeholder, so 2 is compared with
    3's bound, 3 with 4's, and 6 with a padded placeholder."""
    lows = {1: 100.0, 3: 97.0, 4: 94.0, 5: 91.0, 6: 88.0}
    highs = {1: 110.0, 3: 113.0, 4: 116.0, 5: 119.0, 6: 122.0}
    predictions = [
        _prediction(lows.get(i, 50.0), highs.get(i, 50.0), active=i in lows)
        for i in range(7)
    ]
    kept_low, kept_high = pattern_model.thinker_bounds(predictions)
    low_bound = {i: v - v * 0.005 for i, v in lows.items()}
    high_bound = {i: v + v * 0.005 for i, v in highs.items()}
    assert kept_low == [0.01] + [low_bound[i] for i in (1, 3, 4, 5, 6)]
    assert kept_high == [pattern_model.HIGH_PLACEHOLDER] + [
        high_bound[i] for i in (1, 3, 4, 5, 6)
    ]
    sides, padded_low, _ = pattern_model.thinker_sides(
        predictions, kept_low, kept_high, 95.0
    )
    assert padded_low == kept_low + [0.01]
    # 95 is below 1's own bound (99.5): long. It is also below 3's own bound (96.515),
    # but 3 is compared with 4's (93.53): none
    assert sides == ["none", "long", "none", "none", "none", "none", "none"]


def test_the_gap_pass_spreads_close_bounds():
    predictions = [_prediction(100.0 - 0.01 * i, 110.0 + 0.01 * i) for i in range(7)]
    kept_low, kept_high = pattern_model.thinker_bounds(predictions)
    ordered_low = sorted(kept_low, reverse=True)
    ordered_high = sorted(kept_high)
    for k in range(6):  # each neighbouring pair at least 0.25% + 0.25% * k apart
        a, b = ordered_low[k], ordered_low[k + 1]
        assert abs(a - b) / ((a + b) / 2) * 100 >= 0.25 + 0.25 * k
        a, b = ordered_high[k], ordered_high[k + 1]
        assert abs(a - b) / ((a + b) / 2) * 100 >= 0.25 + 0.25 * k
    assert kept_low[0] == 100.0 - 100.0 * 0.005  # the first never moves


def test_the_gap_pass_skips_a_pair_where_either_list_has_placeholders():
    """The runner skips a pair when the low list OR the high list has a placeholder
    there. With two inactive timeframes and two zero lows (which sort below the 0.01
    placeholders), the zero pair lines up with the high placeholders: skipped, so the
    pass ends (judging by the low list alone, it would loop for ever on 0, 0)."""
    lows = {0: 0.0, 1: 0.0, 3: 100.0, 5: 97.0, 6: 94.0}
    highs = {0: 110.0, 1: 111.0, 3: 113.0, 5: 116.0, 6: 119.0}
    predictions = [
        _prediction(lows.get(i, 50.0), highs.get(i, 50.0), active=i in lows)
        for i in range(7)
    ]
    kept_low, kept_high = pattern_model.thinker_bounds(predictions)  # it ends
    # the zero bounds are left as they were (and, being repeats, kept once by the remap)
    assert kept_low.count(0.0) == 1 and min(kept_low) == 0.0
    assert pattern_model.HIGH_PLACEHOLDER in kept_high


def test_short_is_checked_before_long():
    """A band upside down (predicted low above high) puts the price above the high
    bound and below the low one at once: the runner says SHORT."""
    inverted = _prediction(105.0, 95.0)  # low_price 105, high_price 95
    predictions = [inverted] + [_prediction(50.0, 50.0, active=False)] * 6
    lows, highs = pattern_model.thinker_bounds(predictions)
    sides, _, _ = pattern_model.thinker_sides(predictions, lows, highs, 100.0)
    assert sides[0] == "short"


def test_a_gap_pass_that_never_ends_holds(crafted, record, tmp_path):
    """Two active zero bounds loop the runner's gap pass for ever (when no placeholder
    sits at the same place in the other list, which makes the pass skip the pair);
    STRAT-003 holds."""
    predictions = [_prediction(0.0, 110.0 + i) for i in range(7)]
    with pytest.raises(pattern_model.GapPassStuck):
        pattern_model.thinker_bounds(predictions)
    folder = tmp_path / "zero-low"
    # every timeframe active (no placeholders); 1hour and 2hour predict a -100% low
    model = {tf: h3._tf("1000000000.0", f"0.0 0.0{{}}{1 + i}.0{{}}-{1 + i}.0")
             for i, tf in enumerate(TFS)}  # fmt: skip
    model["1hour"] = h3._tf("1000000000.0", "0.0 0.1{}0.3{}-100.0")
    model["2hour"] = h3._tf("1000000000.0", "0.0 0.1{}0.5{}-100.0")
    h3.write_files(str(folder), model)
    h3.publish_files(str(folder), "zero-low")
    _, hourly, frames = crafted
    t = int(pd.Timestamp(hourly["open_time"].iloc[-1]).timestamp()) + HOUR
    signal = _signal_at(strategy("zero-low", frames), frames["1h"], t)
    assert signal.action is Action.HOLD and signal.reason == "BOUNDS_NOT_CONVERGED"


# --- the backtester ----------------------------------------------------------------------------


def _model_with_end(record, tmp_path, train_end, model_id):
    return publish_scenario(record, 0, str(tmp_path / model_id), model_id, train_end)


def test_the_backtester_refuses_a_model_trained_on_scored_bars(
    crafted, record, tmp_path
):
    _, hourly, frames = crafted
    first = pd.Timestamp(hourly["open_time"].iloc[300])
    late = _model_with_end(
        record, tmp_path, (first + pd.Timedelta(hours=1)).isoformat(), "late"
    )
    exact = _model_with_end(record, tmp_path, first.isoformat(), "exact")
    runner = StrategyRunner(strategy(late, frames))
    with pytest.raises(LookaheadError, match="LOOKAHEAD_MODEL"):
        run_backtest(hourly, runner, "BTCUSDT", "1h", start_index=300)
    # a model whose window ends at the first scored bar's open is fine
    result = run_backtest(
        hourly,
        StrategyRunner(strategy(exact, frames)),
        "BTCUSDT",
        "1h",
        start_index=300,
    )
    assert result.first_bar == first


def test_the_lookahead_guard_applies_to_any_strategy_with_a_model():
    runner = build_runner("STRAT-000")
    hourly = hc.synthetic_hourly(400, pd.Timestamp("2024-01-01", tz="UTC"), seed=2)
    runner.strategy.model_train_end = hourly["open_time"].iloc[10]
    with pytest.raises(LookaheadError, match="LOOKAHEAD_MODEL"):
        run_backtest(hourly, runner, "BTCUSDT", "1h", start_index=5)
    run_backtest(hourly, runner, "BTCUSDT", "1h", start_index=10)


def test_a_split_reports_a_refused_in_sample_window(crafted, record, tmp_path):
    _, hourly, frames = crafted
    n = len(hourly)
    cut = int(n * 0.7)
    split_open = pd.Timestamp(hourly["open_time"].iloc[cut])
    ok = _model_with_end(record, tmp_path, split_open.isoformat(), "before-split")
    split = evaluate_split(
        hourly, lambda: StrategyRunner(strategy(ok, frames)), "BTCUSDT", "1h"
    )
    assert "LOOKAHEAD_MODEL" in split["in_sample"]["refused"]
    assert split["out_of_sample"]["strategy"].first_bar == split_open
    bad = _model_with_end(
        record,
        tmp_path,
        (split_open + pd.Timedelta(hours=1)).isoformat(),
        "after-split",
    )
    with pytest.raises(LookaheadError):
        evaluate_split(
            hourly, lambda: StrategyRunner(strategy(bad, frames)), "BTCUSDT", "1h"
        )


def test_the_cli_backtests_strat003_out_of_sample_only(
    crafted, record, tmp_path, capsys
):
    _, hourly, _ = crafted
    cut = int(len(hourly) * 0.7)
    split_open = pd.Timestamp(hourly["open_time"].iloc[cut])
    model_id = _model_with_end(record, tmp_path, split_open.isoformat(), "cli-model")
    out = tmp_path / "out" / "result.json"
    path = _candles_file(tmp_path, hourly)
    code = bt_cli.main(
        ["--strategy", "STRAT-003", "--params", json.dumps({"model_id": model_id}),
         "--candles-file", path, "--offline", "--out", str(out)]
    )  # fmt: skip
    assert code == 0, capsys.readouterr().err
    result = json.loads(out.read_text(encoding="utf-8"))
    assert "LOOKAHEAD_MODEL" in result["in_sample"]["refused"]
    assert result["in_sample"]["strategy"] is None
    # the out-of-sample run decided on its bars: the same as a run given them directly
    _, _, frames = crafted
    direct = _direct_oos(model_id, frames, hourly)
    assert result["out_of_sample"]["bars_missing"] == {}
    assert result["out_of_sample"]["strategy"]["trade_count"] == (
        direct.kpis["trade_count"]
    )
    assert direct.kpis["trade_count"] > 0
    assert result["model"]["model_id"] == model_id
    assert result["model"]["train_end"] == split_open.isoformat()
    later = _model_with_end(
        record, tmp_path, (split_open + pd.Timedelta(hours=1)).isoformat(), "cli-late"
    )
    code = bt_cli.main(
        ["--strategy", "STRAT-003", "--params", json.dumps({"model_id": later}),
         "--candles-file", path, "--offline"]
    )  # fmt: skip
    assert code == 2 and "LOOKAHEAD_MODEL" in capsys.readouterr().err


def test_a_model_trained_on_another_pair_is_refused(crafted):
    model_id, hourly, frames = crafted
    with pytest.raises(ValueError, match="trained on BTCUSDT"):
        run_backtest(
            hourly, StrategyRunner(strategy(model_id, frames)), "ETHUSDT", "1h"
        )


def test_the_runner_tells_the_strategy_its_timeframe(crafted):
    model_id, _, frames = crafted
    runner = StrategyRunner(strategy(model_id, frames))
    with pytest.raises(StrategyError, match="model's timeframes"):
        runner.set_timeframe(900)
    runner.set_timeframe(4 * HOUR)
    assert runner.strategy.bar_seconds == 4 * HOUR
    plain = build_runner("STRAT-000")
    plain.set_timeframe(HOUR)
    assert plain.strategy.bar_seconds == HOUR


# --- purity ---------------------------------------------------------------------------------------


def test_on_bar_does_no_io_and_is_deterministic(crafted, record, monkeypatch):
    model_id, _, frames = crafted
    times = [d["time"] for d in decisions_of(record)][:60]
    first = h3.strategy_signals(strategy(model_id, frames), frames["1h"], times, HOUR)
    strat = strategy(model_id, frames)
    strat.set_timeframe(HOUR)

    def no_io(*args, **kwargs):
        raise AssertionError("on_bar opened a file")

    opens = {int(t.timestamp()): i for i, t in enumerate(frames["1h"]["open_time"])}
    with monkeypatch.context() as m:
        m.setattr(builtins, "open", no_io)
        m.setattr(os, "stat", no_io)
        m.setattr(os, "listdir", no_io)
        second = [strat.on_bar(frames["1h"].iloc[: opens[t - HOUR] + 1]) for t in times]
    assert [(s.action, s.reason, s.indicators) for s in first] == [
        (s.action, s.reason, s.indicators) for s in second
    ]


def test_a_short_on_an_uncounted_primary_timeframe_still_exits_and_never_enters(
    crafted, record
):
    """EXIT on the primary timeframe comes first, even when it is not counted."""
    model_id, _, frames = crafted
    chosen = ["2hour", "8hour"]
    strat = strategy(model_id, frames, timeframes=chosen, min_tf_agree=1)
    decisions = decisions_of(record)
    signals = h3.strategy_signals(
        strat, frames["1h"], [d["time"] for d in decisions], HOUR
    )
    cases = 0
    for d, s in zip(decisions, signals):
        counted = [d["tf_sides"][TFS.index(tf)] for tf in chosen]
        enters_on_counted = counted.count("long") >= 1 and counted.count("short") == 0
        if d["tf_sides"][0] == "short" and enters_on_counted:
            assert s.action is Action.EXIT_LONG, d["time"]
            cases += 1
    assert cases > 0  # the record has such bars


def test_an_unreadable_train_end_is_refused_and_a_naive_one_is_utc(record, tmp_path):
    bad = publish_scenario(record, 0, str(tmp_path / "bad"), "bad-end", "not a time")
    with pytest.raises(StrategyError, match="no readable train_end"):
        strategy(bad)
    naive = publish_scenario(
        record, 0, str(tmp_path / "naive"), "naive-end", "2024-01-20T00:00:00"
    )
    assert strategy(naive).model_train_end == pd.Timestamp("2024-01-20", tz="UTC")


def test_an_unknown_end_of_training_refuses_every_run():
    runner = build_runner("STRAT-000")
    hourly = hc.synthetic_hourly(400, pd.Timestamp("2024-01-01", tz="UTC"), seed=2)
    for unknown in (pd.NaT, "", "never"):
        runner.strategy.model_train_end = unknown
        with pytest.raises(LookaheadError, match="no readable end of training"):
            run_backtest(hourly, runner, "BTCUSDT", "1h", start_index=200)
    runner.strategy.model_train_end = "2024-01-01T10:00:00"  # naive: UTC
    with pytest.raises(LookaheadError, match="LOOKAHEAD_MODEL"):
        run_backtest(hourly, runner, "BTCUSDT", "1h", start_index=9)  # opens 09:00
    run_backtest(hourly, runner, "BTCUSDT", "1h", start_index=10)  # opens 10:00 UTC


def _direct_oos(model_id, frames, hourly):
    """STRAT-003 on the out-of-sample window with the bars given directly."""
    cut = int(len(hourly) * 0.7)
    return run_backtest(
        hourly, StrategyRunner(strategy(model_id, frames)), "BTCUSDT", "1h", cut
    )


def test_the_cli_feeds_strat003_the_bars_of_the_runs_own_cache(
    record, tmp_path, capsys
):
    """With --cache-dir, STRAT-003's seven timeframes come from that folder (the default
    cache is empty), and the out-of-sample run is the same as one given the bars."""
    hourly = h3.hourly_from_rows(record["hourly"])
    frames = hc.all_timeframes(hourly)
    other = tmp_path / "other-cache"
    hc.seed_cache(str(other), "BTCUSDT", frames)
    split_open = pd.Timestamp(hourly["open_time"].iloc[int(len(hourly) * 0.7)])
    model_id = publish_scenario(
        record, 0, str(tmp_path / "m"), "cache-dir-model", split_open.isoformat()
    )
    start = hourly["open_time"].iloc[0].strftime("%Y-%m-%d")
    end = (hourly["open_time"].iloc[-1] + pd.Timedelta(hours=1)).strftime("%Y-%m-%d")
    out = tmp_path / "out" / "result.json"
    code = bt_cli.main(
        ["--strategy", "STRAT-003", "--params", json.dumps({"model_id": model_id}),
         "--cache-dir", str(other), "--start", start, "--end", end, "--offline",
         "--out", str(out)]
    )  # fmt: skip
    assert code == 0, capsys.readouterr().err
    result = json.loads(out.read_text(encoding="utf-8"))
    direct = _direct_oos(model_id, frames, hourly)
    oos = result["out_of_sample"]
    assert oos["bars_missing"] == {} and direct.bars_missing == {}
    assert oos["strategy"]["trade_count"] == direct.kpis["trade_count"] > 0
    assert oos["strategy"]["total_return_pct"] == pytest.approx(
        direct.kpis["total_return_pct"]
    )
    bars_source = result["data"]["source"]["strategy_bars"]
    assert set(bars_source) == set(TrainedModelStrategy.candle_timeframes)
    for tf, info in bars_source.items():
        assert info["sha256"] == candles.file_sha256(
            candles.cache_path("BTCUSDT", tf, str(other))
        )
    # the default cache holds other prices: had the CLI read it, the result would differ
    poisoned = {}
    for tf, frame in frames.items():
        frame = frame.copy()
        frame[["open", "high", "low", "close"]] *= 1.5
        poisoned[tf] = frame
    hc.seed_cache(candles.cache_dir_default(), "BTCUSDT", poisoned)
    again = tmp_path / "out" / "again.json"
    assert bt_cli.main(
        ["--strategy", "STRAT-003", "--params", json.dumps({"model_id": model_id}),
         "--cache-dir", str(other), "--start", start, "--end", end, "--offline",
         "--out", str(again)]
    ) == 0  # fmt: skip
    rerun = json.loads(again.read_text(encoding="utf-8"))["out_of_sample"]
    assert rerun["strategy"] == oos["strategy"]


def test_the_cli_reports_decisions_held_for_missing_bars(
    crafted, record, tmp_path, capsys
):
    """A timeframe the cache does not have: every out-of-sample decision holds, and the
    report says so instead of showing a strategy that chose to stay out."""
    _, hourly, _ = crafted
    os.remove(candles.cache_path("BTCUSDT", "2h"))
    split_open = pd.Timestamp(hourly["open_time"].iloc[int(len(hourly) * 0.7)])
    model_id = publish_scenario(
        record, 0, str(tmp_path / "m"), "missing-2h", split_open.isoformat()
    )
    out = tmp_path / "out" / "result.json"
    code = bt_cli.main(
        ["--strategy", "STRAT-003", "--params", json.dumps({"model_id": model_id}),
         "--candles-file", _candles_file(tmp_path, hourly), "--offline",
         "--out", str(out)]
    )  # fmt: skip
    assert code == 0
    printed = capsys.readouterr().out
    result = json.loads(out.read_text(encoding="utf-8"))
    oos = result["out_of_sample"]
    decided = oos["bars"] - 1  # the last bar is never decided on
    assert oos["bars_missing"] == {"BARS_MISSING:2hour": decided}
    assert oos["strategy"]["trade_count"] == 0
    assert "WARNING: decisions held for missing bars" in printed


def test_the_signal_engine_logs_each_unusable_model_and_repeats_it(monkeypatch, caplog):
    monkeypatch.setitem(
        catalogue.get_entry("STRAT-003")["default_params"], "model_id", UNPUBLISHED
    )
    now = {"t": 1_700_000_000.0}
    engine = SignalEngine(
        settings_source={"strategy": {"active_id": "STRAT-003"}},
        clock=lambda: now["t"],
    )
    with caplog.at_level(logging.ERROR):
        engine.decide("BTC")
        engine.decide("BTC")  # within the repeat interval: once
        assert (
            sum("STRAT-003 cannot be used" in r.getMessage() for r in caplog.records)
            == 1
        )
        now["t"] += 301
        engine.decide("BTC")  # logged again a few minutes later
        assert (
            sum("STRAT-003 cannot be used" in r.getMessage() for r in caplog.records)
            == 2
        )
        # another failing configuration is logged at once, not swallowed by the interval
        engine._settings_source = {
            "strategy": {"active_id": "STRAT-003", "timeframe": "4h"}
        }
        engine.decide("BTC")
        assert (
            sum("STRAT-003 cannot be used" in r.getMessage() for r in caplog.records)
            == 3
        )


def test_other_strategy_build_errors_still_surface(caplog):
    """Only an unusable model fails closed quietly; bad parameters propagate as before."""
    settings = {
        "strategy": {
            "active_id": "STRAT-001",
            "overlays": [
                {"id": "OVL-RATCHET", "params": {"trigger_pct": 2.0, "lock_pct": 3.0}}
            ],
        }
    }
    engine = SignalEngine(settings_source=settings)
    with pytest.raises((StrategyError, catalogue.ParamError, catalogue.CatalogueError)):
        engine.decide("BTC")


def test_without_given_bars_it_reads_the_default_cache_once_outside_on_bar(
    crafted, record, monkeypatch
):
    model_id, _, frames = crafted  # the crafted fixture seeds the default cache
    times = [d["time"] for d in decisions_of(record)][:40]
    given = h3.strategy_signals(strategy(model_id, frames), frames["1h"], times, HOUR)
    strat = strategy(model_id)  # no bars given
    strat.set_timeframe(HOUR)  # reads the default cache here
    opens = {int(t.timestamp()): i for i, t in enumerate(frames["1h"]["open_time"])}

    def no_io(*args, **kwargs):
        raise AssertionError("on_bar opened a file")

    with monkeypatch.context() as m:
        m.setattr(builtins, "open", no_io)
        m.setattr(os, "stat", no_io)
        m.setattr(os.path, "isfile", no_io)
        cached = [strat.on_bar(frames["1h"].iloc[: opens[t - HOUR] + 1]) for t in times]
    assert [(s.action, s.reason, s.indicators) for s in cached] == [
        (s.action, s.reason, s.indicators) for s in given
    ]


def test_a_candles_file_that_is_not_the_caches_series_is_refused(
    crafted, record, tmp_path, capsys
):
    """--candles-file trades the file's bars while STRAT-003 reads the cache: a file of
    another series (here prices 20 times higher, as an ETH file under the BTCUSDT
    label would be) is refused instead of mixing the two."""
    _, hourly, _ = crafted
    split_open = pd.Timestamp(hourly["open_time"].iloc[int(len(hourly) * 0.7)])
    model_id = publish_scenario(
        record, 0, str(tmp_path / "m"), "mixed", split_open.isoformat()
    )
    other = hourly.copy()
    other[["open", "high", "low", "close"]] *= 20
    path = tmp_path / "files" / "ETHUSDT_1h.csv"
    candles._write_cache(str(path), other)
    code = bt_cli.main(
        ["--strategy", "STRAT-003", "--params", json.dumps({"model_id": model_id}),
         "--candles-file", str(path), "--offline"]
    )  # fmt: skip
    assert code == 2
    assert "are not the bars of" in capsys.readouterr().err


@pytest.mark.parametrize(
    "extra, message",
    [
        (["--tf", "6h"], "cannot decide on 6h bars"),
        (["--symbol", "ETHUSDT"], "trained on BTCUSDT"),
    ],
    ids=["timeframe", "symbol"],
)
def test_the_cli_refuses_a_wrong_timeframe_or_pair_before_loading_data(
    crafted, extra, message, capsys
):
    model_id, _, _ = crafted
    code = bt_cli.main(
        ["--strategy", "STRAT-003", "--params", json.dumps({"model_id": model_id}),
         "--start", "2024-01-01", "--end", "2024-02-01", "--offline", *extra]
    )  # fmt: skip
    assert code == 2
    assert message in capsys.readouterr().err


def test_online_the_recorded_hash_is_of_the_file_the_run_leaves(
    record, tmp_path, monkeypatch, capsys
):
    """Online, loading the history before the window extends the run's own cache file;
    the hash in the report is the one of the file as it is after the run."""
    from test_pattern_trainer import FakeKlines

    hourly = h3.hourly_from_rows(record["hourly"])
    fake = FakeKlines({"BTCUSDT": hc.all_timeframes(hourly)})
    monkeypatch.setattr(bt_cli, "BinanceKlines", lambda *a, **k: fake)
    split_open = pd.Timestamp(hourly["open_time"].iloc[int(len(hourly) * 0.7)])
    model_id = publish_scenario(
        record, 0, str(tmp_path / "m"), "online-model", split_open.isoformat()
    )
    out = tmp_path / "out" / "result.json"
    code = bt_cli.main(
        ["--strategy", "STRAT-003", "--params", json.dumps({"model_id": model_id}),
         "--start", "2024-01-08", "--end", "2024-01-29", "--out", str(out)]
    )  # fmt: skip
    assert code == 0, capsys.readouterr().err
    source = json.loads(out.read_text(encoding="utf-8"))["data"]["source"]
    path = candles.cache_path("BTCUSDT", "1h")
    first_cached = candles.load_candles_csv(path, "1h")["open_time"].iloc[0]
    assert first_cached < pd.Timestamp("2024-01-08", tz="UTC")  # it was extended
    assert source["sha256"] == candles.file_sha256(path)
    assert source["strategy_bars"]["1h"]["sha256"] == source["sha256"]
