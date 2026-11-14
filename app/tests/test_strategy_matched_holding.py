"""The matched-holding baseline (PTAI-RD-001 backlog 2.4, defect register N23): random
entries held as long as the strategy's own trades, reported beside the random entries
and scored by nothing (the owner's decision of 2026-11-13).

* Each draw places a trade for each of the strategy's trades: on the same coin, held for
  the same number of bars, entering inside the window, with no two of a draw's trades
  sharing a bar of one coin; a trade with no room is dropped and counted.
* The draws repeat for a seed and differ between seeds; a batch of them replays as each
  draw alone, sized by the run's sizing policy at each trade's own decision.
* A run records them under "matched_holding"; its random entries, and E1's, are the
  figures the code gave before the baseline existed.
* The window states them as facts, and a run saved without them still shows its notes.

Synthetic candles and a fake venue: no network, nothing about performance."""

from __future__ import annotations

import numpy as np
import pytest
from test_e1 import COSTS as E1_COSTS
from test_e1 import daily_universe
from test_strategy_backtest_window import (  # noqa: F401
    BANNED,
    config,
    lab,
    loader,
    open_window,
    pump,
    venue,
)
from test_strategy_lab import FREE, frame_for
from test_strategy_settings_ui import root  # noqa: F401

import strategy_lab_ui as ui
from signal_fusion.evaluation.replay import Account, Costs
from strategy_lab import baselines as bl
from strategy_lab import e1, runs, sizing
from strategy_lab.candidates import RunnerSpec
from strategy_lab.simulate import Simulation, Universe

DAY = 86_400
SPEC = RunnerSpec("STRAT-004", {"entry_days": 20, "exit_days": 10}, (), "1d")
COSTS = Costs(fee=0.005, allowance=0.0005)
TARGET = {"id": "volatility-target", "target": 0.25, "feature": "volatility.ewma"}
# (decided, entry, exit, forced) by hand: AAA holds 5, 30 and 12 bars, BBB 7 bars and
# 20 to the last close (bar 599 of 600)
HAND = {
    "AAA": [(99, 100, 105, False), (199, 200, 230, False), (300, 301, 313, False)],
    "BBB": [(149, 150, 157, False), (579, 580, 599, True)],
}
LENGTHS = {"AAA": [5, 12, 30], "BBB": [7, 20]}

# what the unchanged code (9fd0ee1) recorded for these runs' random entries, and E1's
# REF-RANDOM test of test_e1's universe
OWN_RANDOM = {
    "draws": 30,
    "median_net_usd": 23.080684586320174,
    "median_return_per_capital_day": 0.008348626627540916,
    "share_at_or_above": 0.06666666666666667,
    "entries_wanted": 18,
    "entries_reached_median": 18.0,
}
SIZED_RANDOM = {
    "draws": 30,
    "median_net_usd": 18.65152064222741,
    "median_return_per_capital_day": 0.008306907485952177,
    "share_at_or_above": 0.06666666666666667,
    "entries_wanted": 18,
    "entries_reached_median": 18.0,
}
E1_RANDOM = {
    "value": -0.0023995861691961246,
    "p": 0.0784313725490196,
    "runs": [1 / 6, 1 / 6, 1 / 6, 1 / 3, 1 / 6, 1 / 3, 1 / 6, 1 / 6, 1 / 3, 1 / 6],
    "spread": 0.16666666666666666,
    "median": -0.002511468160746456,
    "percentiles": [
        -0.002537644482844506,
        -0.0025249505207556007,
        -0.0024966390861191276,
        -0.002419873524257848,
    ],
    "share_at_or_above": 0.06,
    "smallest_detectable": 0.00022915805146784578,
    "too_few": False,
    "draws": 50,
    "k": 4,
    "assessable": True,
    "seed": 5000,
    "trades": 54,
    "net_usd": -221.9097220127402,
    "median_net_usd": -220.19453412950458,
    "entries_wanted": 54,
    "entries_reached_median": 54.0,
}


@pytest.fixture(scope="module")
def sim():
    frames = {
        "AAA": frame_for("1d", 600, seed=11),
        "BBB": frame_for("1d", 600, seed=12, phase=2.0),
    }
    return Simulation(Universe("1d", frames), SPEC)


def hand_trades(sim, hand=HAND):
    return [
        sim.tables[coin]._trade(d, e, x, "strategy", forced)
        for coin, rows in hand.items()
        for d, e, x, forced in rows
    ]


def bars(t):
    return t.exit_i - t.entry_i + (1 if t.forced else 0)


def assert_as_before(got, want):
    """The same keys, and the same figures to 12 significant digits."""
    assert set(got) == set(want)
    for key, value in want.items():
        if isinstance(value, bool) or not isinstance(value, (int, float, list)):
            assert got[key] == value, key
        else:
            assert got[key] == pytest.approx(value, rel=1e-12, abs=0), key


def check_draw(sim, trades, first_decision):
    """Each trade a real one on its coin's candles, inside the window, held for whole
    bars, and none sharing a bar of its coin with another."""
    for coin, table in sim.tables.items():
        mine = sorted((t for t in trades if t.coin == coin), key=lambda t: t.entry_i)
        for t in mine:
            assert t.decided >= first_decision[coin] and t.entry_i == t.decided + 1
            assert t.exit_i <= table.n - 1
            assert t.forced == (t.entry_i + bars(t) == table.n)
            assert t.exit_s - t.entry_s == bars(t) * DAY
            assert t == table._trade(
                t.decided, t.entry_i, t.exit_i, t.exit_rule, t.forced
            )
        for a, b in zip(mine, mine[1:]):
            assert b.entry_i > a.exit_i  # entering after the bar the last exit filled


class TestDraws:
    def test_each_draw_holds_the_strategys_lengths_on_its_coins(self, sim):
        taken = hand_trades(sim)
        assert sorted(bars(t) for t in taken) == [5, 7, 12, 20, 30]
        got = bl.matched_draws(sim, taken, seed=900_000, count=40)
        assert got.wanted == 5 and got.dropped == [0] * 40
        first = {c: t.first_decision for c, t in sim.tables.items()}
        for trades in got.draws:
            for coin, lengths in LENGTHS.items():
                assert sorted(bars(t) for t in trades if t.coin == coin) == lengths
            check_draw(sim, trades, first)
            assert trades == sorted(trades, key=lambda t: (t.entry_s, t.coin))
        entries = {t.entry_i for trades in got.draws for t in trades}
        assert len(entries) > 100  # spread over the window, not the strategy's own bars

    def test_the_window_starts_at_its_first_decision_and_a_hold_too_long_is_dropped(
        self, sim
    ):
        table = sim.tables["AAA"]
        from_i = 450  # the last 150 bars: room for 5, 12 and 30, not for 200
        from_s = int(table.candles["open_time"].iloc[from_i].timestamp())
        hand = {"AAA": HAND["AAA"] + [(39, 40, 240, False)], "BBB": HAND["BBB"]}
        taken = hand_trades(sim, hand)
        got = bl.matched_draws(sim, taken, seed=900_000, count=40, from_s=from_s)
        assert got.wanted == 6 and got.dropped == [1] * 40
        first = {"AAA": from_i, "BBB": from_i}
        for trades in got.draws:
            assert sorted(bars(t) for t in trades if t.coin == "AAA") == [5, 12, 30]
            assert sorted(bars(t) for t in trades if t.coin == "BBB") == [7, 20]
            assert all(t.entry_s > from_s for t in trades)
            check_draw(sim, trades, first)

    def test_a_coin_too_short_for_its_holds_drops_what_does_not_fit(self, sim):
        # entries from bar 461 of 600: four holds of 40 bars (each with its exit's bar,
        # 41) cannot all fit in 139 bars, and three can; after the first, a second
        # always fits, so a draw drops one or two
        table = sim.tables["AAA"]
        from_s = int(table.candles["open_time"].iloc[460].timestamp())
        hand = {"AAA": [(d, d + 1, d + 41, False) for d in (50, 100, 150, 200)]}
        got = bl.matched_draws(sim, hand_trades(sim, hand), 900_000, 60, from_s)
        assert got.wanted == 4 and all(1 <= d <= 2 for d in got.dropped)
        for trades, dropped in zip(got.draws, got.dropped):
            assert len(trades) + dropped == 4
            check_draw(sim, trades, {"AAA": 460, "BBB": 460})

    def test_draws_repeat_for_a_seed_and_differ_between_seeds(self, sim):
        taken = hand_trades(sim)
        a = bl.matched_draws(sim, taken, seed=900_000, count=5)
        b = bl.matched_draws(sim, taken, seed=900_000, count=5)
        c = bl.matched_draws(sim, taken, seed=910_000, count=5)
        assert a.draws == b.draws and a.dropped == b.dropped
        assert a.draws != c.draws
        # draw b is seeded seed + b, as the random entries' draws are
        one = bl.matched_draws(sim, taken, seed=900_003, count=1)
        assert one.draws[0] == a.draws[3]


class TestReplay:
    def test_holds_from_one_bar_of_different_lengths_replay_as_their_own(self, sim):
        table = sim.tables["AAA"]
        short = table._trade(99, 100, 105, "strategy", False)
        long = table._trade(99, 100, 160, "strategy", False)
        batch = bl.replay_draws(sim, [[short], [long]], COSTS, Account())
        for p, trade in enumerate((short, long)):
            alone = sim.replay([trade], COSTS, Account())
            assert float(batch.net[p]) == pytest.approx(float(alone.net[0]), abs=1e-9)
            assert float(batch.capital_days[p]) == pytest.approx(
                float(alone.capital_days[0]), abs=1e-9
            )

    def test_a_batch_of_draws_replays_as_each_draw_alone(self, sim):
        paths = sim.replay(sim.candidates(), FREE, Account(), detail=True)
        cands = sim.candidates()
        taken = [cands[i] for i, *_ in paths.detail]
        draws = bl.matched_draws(sim, taken, seed=900_000, count=7).draws
        batch = bl.replay_draws(sim, draws, COSTS, Account(), chunk=3)
        assert len(batch.net) == 7
        for p, trades in enumerate(draws):
            alone = sim.replay(trades, COSTS, Account())
            assert float(batch.net[p]) == pytest.approx(float(alone.net[0]), abs=1e-9)
            assert float(batch.max_drawdown[p]) == pytest.approx(
                float(alone.max_drawdown[0]), abs=1e-12
            )

    def test_the_sizing_policy_scales_each_draw_at_its_own_decisions(self, sim):
        policy = sizing.VolatilityTarget(target=0.25)
        draws = bl.matched_draws(sim, hand_trades(sim), seed=900_000, count=5).draws
        batch = bl.replay_draws(sim, draws, COSTS, Account(), chunk=2, policy=policy)
        plain = bl.replay_draws(sim, draws, COSTS, Account(), chunk=2)
        assert not np.allclose(batch.net, plain.net)
        for p, trades in enumerate(draws):
            scale = policy.scales(sim, trades).scale[None, :]
            alone = sim.replay(trades, COSTS, Account(), scale=scale)
            assert float(batch.net[p]) == pytest.approx(float(alone.net[0]), abs=1e-9)


@pytest.fixture(scope="module")
def records():
    """A run with the account's own sizing and one with a volatility target (saved
    nowhere)."""
    own = runs.run(config(), loader=loader, venue=venue, save=False)
    sized = runs.run(config(sizing=TARGET), loader=loader, venue=venue, save=False)
    return own, sized


class TestRun:
    def test_a_run_records_the_matched_holding_draws(self, records):
        own, sized = records
        for record in (own, sized):
            part = record["matched_holding"]
            assert part["draws"] == 30 and part["seed"] == 700_000 + 30
            assert part["trades_wanted"] == record["strategy_result"]["trades"] == 18
            assert 0 <= part["trades_dropped"] and 0 <= part["draws_short"] <= 30
            assert 0.0 <= part["share_at_or_above"] <= 1.0
            assert 0.0 <= part["share_drawdown_at_or_below"] <= 1.0
            assert part["median_max_drawdown"] >= 0.0
        # sized like the strategy's own trades
        assert (
            sized["matched_holding"]["median_net_usd"]
            != own["matched_holding"]["median_net_usd"]
        )

    def test_the_random_entries_are_as_before(self, records):
        own, sized = records
        assert_as_before(own["random_entries"], OWN_RANDOM)
        assert_as_before(sized["random_entries"], SIZED_RANDOM)

    def test_e1s_random_entries_are_as_before(self):
        sim = Simulation(daily_universe(), e1.STRATEGIES["STRAT-004"])
        trades = e1.scored(sim)
        acct = Account(start=10_000.0)
        path = sim.replay(trades, E1_COSTS, acct, detail=True)
        got = e1.random_test(sim, trades, path, E1_COSTS, acct, 5_000, 5, 4)
        assert_as_before(got, E1_RANDOM)

    def test_no_draws_records_none(self, lab):  # noqa: F811
        record = runs.run(config(draws=0), loader=loader, venue=venue, save=False)
        assert record["matched_holding"] is None and record["random_entries"] is None


class TestWindow:
    def test_the_notes_state_the_matched_holding_figures(self, records):
        own, _ = records
        part = own["matched_holding"]
        text = ui.notes(own)
        assert (
            "Random entries held as long as this strategy's trades (30 draws): return "
            f"per capital-day at or above this strategy's in "
            f"{part['share_at_or_above'] * 100:.1f}%; largest drawdown at or below "
            f"this strategy's in {part['share_drawdown_at_or_below'] * 100:.1f}%."
        ) in text
        dropped = {**part, "trades_dropped": 7, "draws_short": 5}
        lines = ui.matched_lines(dropped)
        assert lines[-1] == (
            "Trades left out of those draws, with no free bars on their coin for the "
            "whole hold: 7 of 540, in 5 draws."
        )
        assert len(ui.matched_lines({**part, "trades_dropped": 0})) == 1
        for t in lines + [text]:
            for banned in BANNED:
                assert banned not in t, (banned, t)

    def test_a_run_saved_without_them_still_shows(self, root, records):  # noqa: F811
        own, _ = records
        old = {k: v for k, v in own.items() if k != "matched_holding"}
        assert ui.matched_lines(None) == [] and ui.matched_lines({}) == []
        assert "held as long" not in ui.notes(old)
        assert ui.summary_rows(old) == ui.summary_rows(own)
        assert ui.compare_row(old) == ui.compare_row(own)
        win = open_window(root, run_fn=lambda c, stop=None, progress=None: old)
        win.end_var.set("2025-01-01")
        assert win.start()
        assert pump(win, lambda: win.result is not None)
        assert win.status_var.get() == "Done."
        notes = win.notes_var.get()
        assert "Logged as an exploratory run." in notes and "held as long" not in notes
        win.destroy()
