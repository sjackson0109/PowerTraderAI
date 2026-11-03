"""Strategy parameters in Settings (``strategy.params``): read fail-closed, used by the
signal engine, and saved by ``SettingsManager.set_strategy`` (no network)."""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import pytest
from helpers import Feed, make_candles

import signal_engine as se
from pt_settings_manager import SettingsManager
from signal_engine import SignalEngine
from strategies.base import Action, StrategyError
from strategies.factory import build_runner
from strategies.settings import read_strategy_settings


def strategy(**keys):
    return {"strategy": keys}


# --- the reader ------------------------------------------------------------------------


def test_the_active_strategys_parameters_are_read():
    s = read_strategy_settings(
        strategy(params={"STRAT-001": {"fast_len": 10, "ma_type": "DEMA"}})
    )
    assert s.problem is None
    assert s.params == {"fast_len": 10, "ma_type": "DEMA"}


def test_another_strategys_parameters_are_not_used_or_checked():
    s = read_strategy_settings(
        strategy(params={"STRAT-002": {"mult": 99}}, active_id="STRAT-001")
    )
    assert (s.problem, s.params) == (None, {})


@pytest.mark.parametrize(
    "params, words",
    [
        ({"fast_len": 60}, "above the maximum"),
        ({"fast_len": 12.5}, "whole number"),
        ({"speed": 3}, "unknown parameter 'speed'"),
        ({"ma_type": "SMA"}, "is not one of"),
        ({"fast_len": 30, "slow_len": 25}, "must be greater than fast_len"),
    ],
)
def test_a_wrong_parameter_blocks_trading(params, words):
    s = read_strategy_settings(strategy(params={"STRAT-001": params}))
    assert s.problem and "strategy.params for STRAT-001" in s.problem
    assert words in s.problem, s.problem
    assert s.note == "SIGNALS: BLOCKED"


@pytest.mark.parametrize("raw", [[], "fast", {"STRAT-001": [10]}])
def test_parameters_that_are_not_an_object_per_strategy_block_trading(raw):
    s = read_strategy_settings(strategy(params=raw))
    assert s.problem and "invalid strategy.params" in s.problem


def test_overlay_parameters_are_checked():
    ok = read_strategy_settings(
        strategy(overlays=[{"id": "OVL-RATCHET", "params": {"trigger_pct": 3.0}}])
    )
    assert ok.problem is None
    for params, words in (
        ({"trigger_pct": 0.0}, "below the minimum"),
        ({"trigger_pct": 1.0, "lock_pct": 1.0}, "lock_pct must be below"),
    ):
        s = read_strategy_settings(
            strategy(overlays=[{"id": "OVL-RATCHET", "params": params}])
        )
        assert s.problem and "overlay OVL-RATCHET" in s.problem and words in s.problem
    bad = read_strategy_settings(strategy(overlays=[{"id": "OVL-ATR", "params": 3}]))
    assert bad.problem and "invalid strategy.overlays" in bad.problem


def test_the_legacy_engine_ignores_strategy_parameters():
    s = read_strategy_settings(
        strategy(engine="legacy_neural", params={"STRAT-001": {"fast_len": 999}})
    )
    assert s.problem is None


def test_a_model_strategy_still_needs_a_trained_model_whatever_the_parameters():
    s = read_strategy_settings(
        strategy(active_id="STRAT-003", params={"STRAT-003": {"model_id": "m1"}})
    )
    assert s.problem and "needs a trained model" in s.problem
    assert s.params == {}


def test_the_signature_changes_with_the_parameters():
    a = read_strategy_settings({}).signature
    b = read_strategy_settings(strategy(params={"STRAT-001": {"fast_len": 10}}))
    assert a != b.signature
    assert a == read_strategy_settings(strategy(params={})).signature


# --- the signal engine -----------------------------------------------------------------


def trend_series():
    """down 150 bars, sharp rally 40, long fall 70 (SYNTHETIC)."""
    return np.concatenate(
        [
            np.linspace(200, 150, 150),
            np.linspace(150, 240, 40),
            np.linspace(240, 110, 70),
        ]
    )


def replay(decide, frame, record_entry, record_exit):
    """Bar by bar: flat -> long -> flat, as the trader does."""
    seen, pos = [], None
    for k in range(len(frame)):
        d = decide(k, pos)
        if d.action is Action.ENTER_LONG and pos is None:
            pos = record_entry(k, d)
            seen.append((k, "ENTER"))
        elif d.action is Action.EXIT_LONG and pos is not None:
            record_exit(k, d)
            pos = None
            seen.append((k, "EXIT"))
    return seen


def test_the_engine_decides_with_the_saved_parameters():
    """The signal engine's decisions are exactly those of the strategy built with
    the parameters in Settings, and differ from its defaults'."""
    frame = make_candles(trend_series())
    params = {"fast_len": 5, "slow_len": 30}

    def backtest(p):
        runner = build_runner("STRAT-000", p)
        return replay(
            lambda k, pos: runner.evaluate(runner.window(frame, k), pos, "BTC"),
            frame,
            lambda k, d: runner.open_position(
                "BTC", frame["close"].iloc[k], d.bar_time, frame
            ),
            lambda k, d: None,
        )

    want = backtest(params)
    assert want and want != backtest({}), "the fixture must tell the two apart"

    feed = Feed(frame)
    engine = SignalEngine(
        strategy(active_id="STRAT-000", params={"STRAT-000": params}),
        feed.provider,
        feed.clock,
    )

    def decide(k, pos):
        feed.set_after_bar(k)
        return engine.decide("BTC", pos)

    seen = replay(
        decide,
        frame,
        lambda k, d: engine.record_entry("BTC", frame["close"].iloc[k], d.bar_time),
        lambda k, d: engine.record_exit("BTC", frame["close"].iloc[k], d.bar_time),
    )
    assert seen == want
    assert engine._runner.strategy.params["fast_len"] == 5


def test_a_strategy_that_cannot_be_built_blocks_signals(monkeypatch, caplog):
    def refuse(*_a, **_k):
        raise StrategyError("slow_len must be greater than fast_len")

    monkeypatch.setattr(se, "build_runner", refuse)
    engine = SignalEngine({}, Feed(make_candles(trend_series())).provider)
    assert engine.decide("BTC") is None
    assert "slow_len must be greater than fast_len" in engine.block_reason()
    assert any("No signals" in r.getMessage() for r in caplog.records)


def test_a_settings_change_keeps_the_overlays_timers():
    """A cooldown running when the parameters change is still running after."""
    src = strategy(overlays=[{"id": "OVL-COOLDOWN"}])
    engine = SignalEngine(src)
    first = engine._runner_for(engine.settings)
    exit_time = pd.Timestamp("2026-11-01T10:00", tz="UTC")
    first.overlays[0]._last["BTC"] = (exit_time, True)
    src["strategy"]["params"] = {"STRAT-001": {"fast_len": 10}}
    second = engine._runner_for(engine.settings)
    assert second is not first
    assert second.export_state()["OVL-COOLDOWN"] == {
        "BTC": [exit_time.isoformat(), True]
    }
    # unticked, then ticked again: the same timer
    src["strategy"]["overlays"] = []
    assert engine._runner_for(engine.settings).overlays == []
    src["strategy"]["overlays"] = [{"id": "OVL-COOLDOWN"}]
    third = engine._runner_for(engine.settings)
    assert third.export_state()["OVL-COOLDOWN"] == {
        "BTC": [exit_time.isoformat(), True]
    }


# --- saving ----------------------------------------------------------------------------


def test_set_strategy_saves_the_strategy_keys(tmp_path):
    manager = SettingsManager("pt_config.json", str(tmp_path))
    values = {
        "engine": "catalogue",
        "active_id": "STRAT-002",
        "timeframe": "4h",
        "params": {"STRAT-002": {"mult": 2.5}},
        "overlays": [{"id": "OVL-ATR", "params": {}}],
    }
    assert manager.set_strategy(values)
    with open(os.path.join(tmp_path, "pt_config.json"), encoding="utf-8") as f:
        on_disk = json.load(f)["strategy"]
    assert on_disk == values
    s = read_strategy_settings(SettingsManager("pt_config.json", str(tmp_path)))
    assert (s.problem, s.active_id, s.timeframe, s.params) == (
        None,
        "STRAT-002",
        "4h",
        {"mult": 2.5},
    )


def test_set_strategy_replaces_parameters_rather_than_merging(tmp_path):
    manager = SettingsManager("pt_config.json", str(tmp_path))
    assert manager.set_strategy({"params": {"STRAT-001": {"fast_len": 10}}})
    assert manager.set_strategy({"params": {}})
    assert SettingsManager("pt_config.json", str(tmp_path)).get("strategy.params") == {}


def test_set_strategy_refuses_a_bad_value_and_changes_nothing(tmp_path):
    manager = SettingsManager("pt_config.json", str(tmp_path))
    assert manager.set_strategy({"timeframe": "4h"})
    assert not manager.set_strategy({"timeframe": "7m", "active_id": "STRAT-002"})
    assert not manager.set_strategy({"params": {"STRAT-001": 3}})
    again = SettingsManager("pt_config.json", str(tmp_path))
    assert (again.get("strategy.timeframe"), again.get("strategy.active_id")) == (
        "4h",
        "STRAT-001",
    )


def test_a_problem_elsewhere_in_the_settings_does_not_stop_a_strategy_save(tmp_path):
    manager = SettingsManager("pt_config.json", str(tmp_path))
    manager._settings["neural_config"]["training_epochs"] = "many"
    assert not manager.set("ui_config.font_size", 10)  # set() checks every rule
    assert manager.set_strategy({"timeframe": "2h"})
    again = SettingsManager("pt_config.json", str(tmp_path))
    assert again.get("strategy.timeframe") == "2h"
