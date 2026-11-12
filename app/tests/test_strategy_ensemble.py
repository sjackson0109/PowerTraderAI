"""PTAI-RD-001 backlog 3.1: the Donchian ensemble of Zarattini, Pagani and Barbon (2025).

* STRAT-007: a new closing high of the channel days enters, a close below the channel's
  midline exits; the warm-up; calendar days; no look-ahead; the live engine agrees.
* OVL-MIDLINE: the stop is the midline, it never moves down, and a close below it
  exits; it can exit earlier than STRAT-007 alone, never later.
* The ensemble: each member holds 1/M of a coin's 1/N, scaled by the sizing policy; the
  book never holds more than the account; a slice below the venue's minimum is
  skipped; each member alone and an equal-weight buy-and-hold are reported.
* Research only, described, not enabled for research by default.

Synthetic candles only: no network, nothing about performance."""

from __future__ import annotations

import numpy as np
import pytest
from test_strategy_breakout import DailyFeed, daily, random_walk, signal
from test_strategy_backtest_window import (  # noqa: F401
    BANNED,
    config,
    lab,
    loader,
    open_window,
    venue,
)
from test_strategy_settings_ui import root  # noqa: F401
from test_strategy_lab import FREE, frame_for

from signal_engine import SignalEngine
from signal_fusion.evaluation.replay import Costs
from strategies import ParamError, create
from strategies import descriptions as words
from strategies.base import Action
from strategies.catalogue import CATALOGUE
from strategies.factory import build_runner
from strategies.settings import read_research_enabled, read_strategy_settings
from strategy_lab import ensemble as en
from strategy_lab import sizing
from strategy_lab.candidates import RunnerSpec
from strategy_lab.simulate import Simulation, Universe

DAY = 86_400


# -- STRAT-007 ----------------------------------------------------------------------------


def test_a_new_high_enters_and_a_close_below_the_midline_exits():
    s = create("STRAT-007", channel_days=20)
    base = [10.0] * 10 + [20.0] * 10  # previous 20 closes: high 20, low 10, mid 15
    assert signal(s, daily(base + [21.0])) == (Action.ENTER_LONG, "NEW_CLOSING_HIGH")
    assert signal(s, daily(base + [14.0])) == (Action.EXIT_LONG, "BELOW_MIDLINE")
    assert signal(s, daily(base + [15.0])) == (Action.HOLD, "INSIDE_CHANNEL")
    assert signal(s, daily(base + [20.0])) == (Action.HOLD, "INSIDE_CHANNEL")
    ind = s.on_bar(daily(base + [17.0])).indicators
    assert (ind["channel_high"], ind["channel_low"], ind["midline"]) == (20, 10, 15)


def test_the_warm_up_the_days_and_the_bounds():
    s = create("STRAT-007")
    assert s.params == {"channel_days": 20}
    assert (s.warmup_bars, s.lookback_bars) == (21, 21)
    assert signal(s, daily([10.0] * 20))[1] == "WARMUP"
    s.set_timeframe(4 * 3600)
    assert s.warmup_bars == 121
    for bad in (19, 366):
        with pytest.raises(ParamError):
            create("STRAT-007", channel_days=bad)
    with pytest.raises(ParamError):
        create("OVL-MIDLINE", days=10)


def test_appending_bars_never_changes_an_earlier_decision():
    frame = daily(random_walk(300, seed=5))
    runner = build_runner("STRAT-007", {"channel_days": 30})
    runner.set_timeframe(DAY)
    decisions = [
        runner.evaluate(runner.window(frame, i), None, "X").action
        for i in range(len(frame))
    ]
    for cut in (60, 200):
        short = frame.iloc[: cut + 1].reset_index(drop=True)
        for i in range(cut + 1):
            got = runner.evaluate(runner.window(short, i), None, "X").action
            assert got == decisions[i], (cut, i)
    assert Action.ENTER_LONG in decisions


def test_the_signal_engine_and_a_replayed_runner_agree_on_every_bar():
    frame = daily(random_walk(200, seed=13))
    settings = {"strategy": {"active_id": "STRAT-007", "timeframe": "1d"}}
    feed = DailyFeed(frame)
    engine = SignalEngine(settings, feed.provider, feed.clock)
    replay = build_runner("STRAT-007")
    replay.set_timeframe(DAY)
    for k in range(21, len(frame)):
        feed.set_after_bar(k)
        got = engine.decide("BTC", None)
        want = replay.evaluate(replay.window(frame, k), None, "BTC")
        assert (got.action, got.reason) == (want.action, want.reason), k


# -- OVL-MIDLINE ----------------------------------------------------------------------------


def _by_hand(closes, n, ratchet):
    """The trades by the rule, written out: (entry bar, exit bar), filled at opens."""
    out, entry, stop = [], None, None
    for k in range(n, len(closes) - 1):
        prev = closes[k - n : k]
        mid = (max(prev) + min(prev)) / 2
        if entry is None:
            if closes[k] > max(prev):
                entry, stop = k + 1, None
            continue
        if k < entry:
            continue
        stop = mid if (stop is None or not ratchet) else max(stop, mid)
        if closes[k] < stop:
            out.append((entry, k + 1))
            entry = None
    return out


def _trades(closes, n, overlay):
    spec = RunnerSpec(
        "STRAT-007",
        {"channel_days": n},
        ({"id": "OVL-MIDLINE", "params": {"days": n}},) if overlay else (),
        "1d",
    )
    sim = Simulation(Universe("1d", {"X": daily(closes)}), spec)
    # the candidates are every bar's possible entry; one coin holds one trade at a
    # time, and an entry filling at an exit's open is not taken (the replay's rule)
    out, last_exit = [], -1
    for t in sim.candidates():
        if t.entry_i > last_exit:
            if not t.forced:
                out.append((t.entry_i, t.exit_i))
            last_exit = t.exit_i
    return out


def test_the_midline_stop_follows_the_rule_on_a_random_walk():
    closes = random_walk(500, seed=21)
    with_stop = _trades(closes, 20, overlay=True)
    alone = _trades(closes, 20, overlay=False)
    assert with_stop == _by_hand(closes, 20, ratchet=True)
    assert alone == _by_hand(closes, 20, ratchet=False)
    # on a random walk the ratchet seldom changes an exit (in 400 paths it never
    # did): a close above the day's midline is usually above the earlier ones too


# each level held for 10 days: the midline rises, then falls while the close stays
# above the day's midline but below the earlier one
STEPS = [10, 17, 15, 13, 12, 19, 15, 10, 19, 15, 17, 16, 11, 17]
STEPPED = [float(v) for v in STEPS for _ in range(10)]


def test_the_ratchet_exits_where_a_falling_midline_would_not():
    assert _trades(STEPPED, 20, overlay=True) == [(51, 61), (81, 111)]
    assert _trades(STEPPED, 20, overlay=False) == [(51, 61), (81, 121)]
    assert _by_hand(STEPPED, 20, ratchet=True) == [(51, 61), (81, 111)]


def test_the_stop_never_moves_down():
    frame = daily(STEPPED)
    runner = build_runner("STRAT-007", {"channel_days": 20}, [{"id": "OVL-MIDLINE"}])
    runner.set_timeframe(DAY)
    pos = runner.open_position(
        "X",
        frame["open"].iloc[81],
        frame["open_time"].iloc[81],
        runner.window(frame, 81),
    )
    stops, mids = [], []
    for k in range(81, len(STEPPED)):
        d = runner.evaluate(runner.window(frame, k), pos, "X")
        stops.append(pos.current_stop)
        mids.append(pos.overlay_state["OVL-MIDLINE"]["midline"])
        if d.action is Action.EXIT_LONG:
            break
    assert all(b >= a for a, b in zip(stops, stops[1:]))  # never down
    assert any(b < a for a, b in zip(mids, mids[1:]))  # though the midline fell
    assert k == 110 and "STOP:OVL-MIDLINE" in d.reason


# -- the ensemble ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ens():
    frames = {
        "AAA": frame_for("1d", 900, seed=51),
        "BBB": frame_for("1d", 900, seed=52, phase=1.0),
    }
    return en.Ensemble(Universe("1d", frames), lookbacks=(20, 60, 150))


def test_each_member_holds_its_slice_of_a_coins_allocation(ens):
    book = ens.replay(FREE, 10_000.0, detail=True)
    assert book.trades[0] > 0
    # the first entry is 1/N (2 coins) x 1/M (3 members) of the account
    first_amount = book.detail[0][1] if book.detail else None
    assert first_amount == pytest.approx(10_000.0 / 2 / 3)
    assert book.peak_committed[0] <= 1.0 + 1e-9  # never more than the account
    # a member alone has the coin's whole allocation
    alone = ens.replay(FREE, 10_000.0, detail=True, members=[60])
    assert alone.detail[0][1] == pytest.approx(10_000.0 / 2)
    assert alone.trades[0] > 0


def test_the_sizing_policy_scales_each_slice(ens):
    policy = sizing.VolatilityTarget(target=0.25)
    plain = ens.replay(FREE, 10_000.0, detail=True)
    sized = ens.replay(FREE, 10_000.0, policy, detail=True)
    (i, amount, *_), (j, base, *_) = sized.detail[0], plain.detail[0]
    assert i == j and base == pytest.approx(10_000.0 / 6)
    # a slice is 1/6 times its scale, at most 1 (1 in the estimator's warm-up)
    assert amount <= base + 1e-9
    assert sized.net[0] != plain.net[0]


def test_a_slice_below_the_venues_minimum_is_skipped(ens):
    dear = Costs(fee=0.0, allowance=0.0, minimum_usd={"AAA": 300.0, "BBB": 300.0})
    # a £1,000-sized book: slices of 1000 / 2 / 3 = 167 are below 300 and skipped;
    # a member alone (500 a coin) is not
    book = ens.replay(dear, 1_000.0)
    alone = ens.replay(dear, 1_000.0, members=[60])
    assert book.trades[0] == 0 and book.skipped_minimum[0] > 0
    assert alone.trades[0] > 0


def test_the_report_has_the_book_each_member_and_the_hold(ens):
    costs = Costs(fee=0.005, allowance=0.0005)
    r = en.report(ens, costs, 10_000.0)
    assert r["lookbacks"] == [20, 60, 150] and r["coins"] == ["AAA", "BBB"]
    assert set(r["members"]) == {"20", "60", "150"}
    assert r["ensemble"]["trades"] > 0
    assert all(m["trades"] > 0 for m in r["members"].values())
    assert r["equal_weight_hold"]["trades"] == 2
    rates = [r["members"][k]["trades_per_coin_year"] for k in ("20", "60", "150")]
    assert rates[0] > rates[1] > rates[2] > 0  # longer channels trade less


def test_members_under_20_days_and_other_candles_are_refused():
    frames = {"AAA": frame_for("1d", 100, seed=1)}
    with pytest.raises(ValueError, match="20 days or more"):
        en.Ensemble(Universe("1d", frames), lookbacks=(10, 20))
    with pytest.raises(ValueError, match="daily"):
        en.Ensemble(Universe("4h", frames))
    assert en.member_spec(90).overlays == (
        {"id": "OVL-MIDLINE", "params": {"days": 90}},
    )
    assert en.warmup_days() == 362


# -- the catalogue ----------------------------------------------------------------------------


def test_both_are_research_only_described_and_off_by_default():
    for sid in ("STRAT-007", "OVL-MIDLINE"):
        e = CATALOGUE[sid]
        assert e["authorisation"] == "research"
        assert e["timeframe_primary"] == "1d"
        assert sid not in read_research_enabled({})
        d = words.DESCRIPTIONS[sid]
        assert set(d.params) == set(e["default_params"])
        assert all(p.label and p.help for p in d.params.values())
    assert CATALOGUE["STRAT-007"]["family"] == "breakout"
    settings = {"strategy": {"active_id": "STRAT-007", "timeframe": "1d"}}
    for mode in ("paper", "live"):
        problem = read_strategy_settings(settings, mode).problem
        assert "STRAT-007 can be used for research only" in problem


# -- from the backtest window ---------------------------------------------------------------


def test_a_run_replays_the_ensemble_when_asked(lab):  # noqa: F811
    import strategy_lab_ui as ui
    from strategy_lab import runs

    cfg = config(strategy_id="STRAT-007", params={"channel_days": 20}, ensemble=True)
    record = runs.run(cfg, loader=loader, venue=venue, save=False)
    group = record["ensemble"]
    assert group["lookbacks"] == list(en.LOOKBACKS)
    assert set(group["members"]) == {str(n) for n in en.LOOKBACKS}
    assert group["ensemble"]["trades"] > 0
    labels = [row[0] for row in ui.summary_rows(record)]
    assert "Ensemble of 7 channels" in labels
    assert "Buy and hold, equal weights" in labels
    text = ui.notes(record)
    assert "20 channel days alone" in text and "360 channel days alone" in text
    for t in ui.ensemble_lines(group) + labels + [ui.ENSEMBLE_TEXT]:
        for banned in BANNED:
            assert banned not in str(t), (banned, t)
    # without it, nothing is recorded; and it is STRAT-007's only
    plain = runs.run(
        config(strategy_id="STRAT-007", params={"channel_days": 20}),
        loader=loader,
        venue=venue,
        save=False,
    )
    assert plain["ensemble"] is None and ui.ensemble_lines(None) == []
    with pytest.raises(ValueError, match="STRAT-007"):
        runs.run(config(ensemble=True), loader=loader, venue=venue, save=False)


def test_the_window_offers_the_ensemble_with_strat_007_only(root, lab):  # noqa: F811
    import strategy_lab_ui as ui
    from strategy_lab.runs import RunConfig  # noqa: F401

    win = open_window(
        root, settings={"strategy": {"research_enabled": ["STRAT-004", "STRAT-007"]}}
    )
    win.end_var.set("2025-01-01")
    win.strategy_var.set(words.name_of("STRAT-007"))
    win.update()
    texts = [str(w.cget("text")) for w in win.params_frame.winfo_children()]
    assert ui.ENSEMBLE_TEXT in texts
    win.ensemble_on.set(True)
    assert win.config().ensemble is True
    win.strategy_var.set(words.name_of("STRAT-004"))
    win.update()
    texts = [str(w.cget("text")) for w in win.params_frame.winfo_children()]
    assert ui.ENSEMBLE_TEXT not in texts
    assert win.config().ensemble is False
    win.destroy()


def test_the_book_reports_the_intrabar_drawdown_from_the_earlier_highs(ens):
    book = ens.replay(FREE, 10_000.0)
    assert book.intrabar_max_drawdown[0] >= book.max_drawdown[0]
    hold = ens.hold(FREE, 10_000.0, None)
    assert hold.intrabar_max_drawdown is not None
