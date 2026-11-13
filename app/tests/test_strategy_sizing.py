"""Sizing policies for research replays (PTAI-RD-001 WP 4.2).

* The account's own sizing scales nothing, and a run without a policy is as before.
* A volatility target sizes each trade once, at its decision: min(cap, target / sigma),
  sigma as of the deciding close, annualised over 365 days; a trade before the
  estimator's warm-up keeps its size and is counted.
* Targets, caps and estimators outside their bounds are refused; a policy is rebuilt
  from its record.
* The replay spends the account's own amount times the scale; the random orders are
  permutations of the same scales.
* A run records the policy, the same trades at the account's own size, and the same
  scales in random orders; random entries are sized by the same policy.
* The window offers the choice, explains a wrong target, and states facts only.

Synthetic candles and a fake venue: no network."""

from __future__ import annotations

import math

import numpy as np
import pytest
from test_strategy_backtest_window import (  # noqa: F401
    BANNED,
    config,
    lab,
    loader,
    open_window,
    pump,
    venue,
)
from test_strategy_lab import FREE, frame_for, one_coin
from test_strategy_settings_ui import root  # noqa: F401

import feature_library as fl
import strategy_lab_ui as ui
from signal_fusion.evaluation.replay import Account
from strategy_lab import runs, sizing
from strategy_lab.candidates import RunnerSpec

SPEC = RunnerSpec("STRAT-004", {"entry_days": 20, "exit_days": 10}, (), "1d")


@pytest.fixture(scope="module")
def sim():
    return one_coin(frame_for("1d", 700, seed=41), SPEC)


def test_the_accounts_own_sizing_scales_nothing(sim):
    trades = sim.candidates()
    s = sizing.Fixed().scales(sim, trades)
    assert len(trades) > 5 and (s.scale == 1.0).all() and s.unsized == 0
    assert sizing.from_record(None) == sizing.Fixed()
    assert sizing.from_record({"id": "fixed"}) == sizing.Fixed()


def test_a_volatility_target_sizes_each_trade_at_its_decision(sim):
    trades = sim.candidates()
    policy = sizing.VolatilityTarget(target=0.25)
    s = policy.scales(sim, trades)
    candles = sim.tables["X"].candles
    sized = 0
    for k, t in enumerate(trades):
        # as of the deciding close: the candles up to it give the same value
        per_bar = fl.compute("volatility.ewma", candles.iloc[: t.decided + 1]).iloc[-1]
        sigma = per_bar * math.sqrt(365)
        if not np.isfinite(sigma):  # decided in the 30-bar burn-in
            assert s.scale[k] == 1.0 and np.isnan(s.sigma[k])
            continue
        sized += 1
        assert s.sigma[k] == pytest.approx(sigma, rel=1e-12)
        assert s.scale[k] == pytest.approx(min(1.0, 0.25 / sigma), rel=1e-12)
    assert sized >= 5
    assert 0.0 < s.scale.min() and s.scale.max() <= 1.0
    assert (s.scale < 1.0).any()  # the synthetic waves are more volatile than 25%
    summary = s.summary()
    assert summary["trades"] == len(trades)
    assert summary["unsized"] == len(trades) - sized
    assert summary["mean_scale"] == pytest.approx(float(np.mean(s.scale)))


def test_a_trade_before_the_warm_up_keeps_its_size_and_is_counted(sim):
    trades = sim.candidates()
    policy = sizing.VolatilityTarget(feature="volatility.realised", params={"n": 300})
    s = policy.scales(sim, trades)
    early = np.array([t.decided < 300 for t in trades])
    assert early.any() and (~early).any()
    assert (s.scale[early] == 1.0).all() and np.isnan(s.sigma[early]).all()
    assert s.unsized == int(early.sum())


def test_bounds_are_refused_and_a_policy_is_rebuilt_from_its_record():
    for bad in (
        dict(target=0.01),
        dict(target=3.0),
        dict(cap=1.5),
        dict(cap=0.0),
        dict(feature="price.rsi"),
        dict(feature="volatility.realised", params={"n": 1}),
    ):
        with pytest.raises(ValueError):
            sizing.VolatilityTarget(**bad)
    with pytest.raises(ValueError, match="no sizing policy"):
        sizing.from_record({"id": "kelly"})
    policy = sizing.VolatilityTarget(
        target=0.4, feature="volatility.parkinson", params={"n": 30}, cap=0.8
    )
    again = sizing.from_record(policy.record())
    assert again.record() == policy.record()
    assert again.record()["feature"] == 'volatility.parkinson@1{"n":30}'


def test_the_replay_spends_the_accounts_amount_times_the_scale(sim):
    trades = sim.candidates()
    s = sizing.VolatilityTarget(target=0.25).scales(sim, trades)
    acct = Account(start=10_000.0, start_pct=10.0, max_coin_pct=100.0)
    plain = sim.replay(trades, FREE, acct, detail=True)
    sized = sim.replay(trades, FREE, acct, detail=True, scale=s.scale[None, :])
    assert [i for i, *_ in sized.detail] == [i for i, *_ in plain.detail]
    # the first entry's base is 10% of the starting account; later ones follow each
    # account's own value, which the sizing changes
    (first_i, first_amount, *_), (_, base, *_) = sized.detail[0], plain.detail[0]
    assert base == pytest.approx(1_000.0)
    assert first_amount == pytest.approx(1_000.0 * s.scale[first_i])


def test_random_orders_are_permutations_of_the_same_scales():
    scale = np.array([1.0, 0.5, 0.25, 0.8])
    a = sizing.random_orders(scale, 50, seed=7)
    assert a.shape == (50, 4)
    for row in a:
        np.testing.assert_array_equal(np.sort(row), np.sort(scale))
    np.testing.assert_array_equal(a, sizing.random_orders(scale, 50, seed=7))
    assert len({tuple(r) for r in a}) > 1
    assert sizing.random_orders(np.zeros(0), 3, seed=1).shape == (3, 0)


class TestRun:
    def test_a_run_without_a_policy_records_the_accounts_own(self, lab):  # noqa: F811
        record = runs.run(config(), loader=loader, venue=venue, save=False)
        assert record["sizing"] == {"policy": {"id": "fixed"}}
        assert record["config"]["sizing"] is None

    def test_a_run_with_a_volatility_target_records_its_checks(self, lab):  # noqa: F811
        target = {
            "id": "volatility-target",
            "target": 0.25,
            "feature": "volatility.ewma",
        }
        own = runs.run(config(), loader=loader, venue=venue, save=False)
        record = runs.run(config(sizing=target), loader=loader, venue=venue, save=False)
        part = record["sizing"]
        assert part["policy"]["id"] == "volatility-target"
        assert part["policy"]["feature"].startswith("volatility.ewma@1")
        assert 0.0 < part["mean_scale"] <= 1.0
        # the same trades at the account's own size are the run without a policy
        assert part["fixed_result"]["net_usd"] == pytest.approx(
            own["strategy_result"]["net_usd"]
        )
        assert part["fixed_result"]["max_drawdown"] == pytest.approx(
            own["strategy_result"]["max_drawdown"]
        )
        rand = part["random_order"]
        assert rand["draws"] == 30
        assert 0.0 <= rand["share_drawdown_at_or_below"] <= 1.0
        assert 0.0 <= rand["share_net_at_or_above"] <= 1.0
        # the random entries are sized too: their results differ from the unsized ones
        assert (
            record["random_entries"]["median_net_usd"]
            != own["random_entries"]["median_net_usd"]
        )
        # and every account size uses the policy
        assert record["accounts"][-1]["strategy_result"]["net_usd"] != pytest.approx(
            own["accounts"][-1]["strategy_result"]["net_usd"]
        )


class TestWindow:
    def test_the_window_offers_the_sizing_and_explains_a_wrong_target(
        self, root, lab  # noqa: F811
    ):
        calls = []
        win = open_window(root, run_fn=lambda c, **kw: calls.append(c) or {})
        win.end_var.set("2025-01-01")
        assert win.config().sizing is None
        win.sizing_var.set(ui.SIZING_TARGET)
        win.target_var.set("30")
        win.estimator_var.set(ui.ESTIMATOR_NAMES["volatility.yang_zhang"])
        assert win.config().sizing == {
            "id": "volatility-target",
            "target": 0.30,
            "feature": "volatility.yang_zhang",
        }
        win.target_var.set("1")
        assert not win.start()
        assert "from 5% to 200% a year" in win.status_var.get()
        win.target_var.set("many")
        assert not win.start() and "volatility target" in win.status_var.get()
        assert calls == []
        win.destroy()

    def test_the_sizing_words_state_facts_only(self, lab):  # noqa: F811
        target = {
            "id": "volatility-target",
            "target": 0.25,
            "feature": "volatility.ewma",
        }
        record = runs.run(config(sizing=target), loader=loader, venue=venue, save=False)
        text = ui.notes(record)
        assert "sized at its decision to a volatility of 25% a year" in text
        assert "The same trades at the account's own size" in text
        assert "The same sizes in 30 random orders" in text
        texts = ui.sizing_lines(record["sizing"]) + [ui.SIZING_OWN, ui.SIZING_TARGET]
        texts += list(ui.ESTIMATOR_NAMES.values())
        for t in texts:
            for banned in BANNED:
                assert banned not in t, (banned, t)
        # a run without a policy, or saved before sizing was recorded, says nothing
        assert ui.sizing_lines({"policy": {"id": "fixed"}}) == []
        assert ui.sizing_lines(None) == []
