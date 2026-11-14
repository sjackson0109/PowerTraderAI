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


# -- random entries for the book (REF-RANDOM-E) and matched holding --------------------------

COSTS = Costs(fee=0.005, allowance=0.0005)


def _book(ens, costs=FREE, usd=10_000.0):
    by = ens.trades()
    path = ens.replay(costs, usd, detail=True)
    return by, path, ens.taken(by, path)


def _exit_by_hand(closes, n, entry):
    """The exit fill of a trade entered at bar ``entry``'s open: the first close below
    the midline stop, which starts at the midline and never moves down; None when it
    is still open at the last bar (closed there, at the end of the data)."""
    stop = None
    for k in range(entry, len(closes) - 1):
        prev = closes[k - n : k]
        mid = (max(prev) + min(prev)) / 2
        stop = mid if stop is None else max(stop, mid)
        if closes[k] < stop:
            return k + 1
    return None


def test_the_book_replays_its_slices_in_one_order(ens):
    by, path, taken = _book(ens)
    order = ens.slices(by)
    assert [n for n, _t in order] == sorted(n for n, _t in order)
    assert len(order) == sum(len(v) for v in by.values())
    # the taken trades are path 0's, by member, and each slice holds one at a time
    rows = [order[i] for i, *_ in path.detail]
    assert sum(len(v) for v in taken.values()) == len(rows) == int(path.trades[0])
    for n, trades in taken.items():
        for coin in ens.coins:
            mine = sorted(
                (t for t in trades if t.coin == coin), key=lambda t: t.entry_s
            )
            assert all(a.exit_s <= b.entry_s for a, b in zip(mine, mine[1:]))
    # replaying the same trades directly is the same book
    again = ens.replay_trades(by, FREE, 10_000.0, detail=True)
    assert again.net[0] == path.net[0] and again.detail == path.detail


def test_random_entries_match_each_slices_entries(ens):
    _by, _path, taken = _book(ens)
    draws = ens.random_draws(taken, seed=40, count=6)
    wanted = {
        en._key(c, n): sum(t.coin == c for t in taken[n])
        for n in taken
        for c in ens.coins
    }
    assert draws.wanted == wanted and sum(wanted.values()) > 0
    full = 0
    for b, d in enumerate(draws.draws):
        assert set(d) == set(taken)
        got = {
            en._key(c, n): sum(t.coin == c for t in d[n]) for n in d for c in ens.coins
        }
        assert all(got[k] <= wanted[k] for k in wanted)  # fewer only when out of bars
        assert draws.reached[b] == sum(got.values())
        full += got == wanted
    assert full >= 1


def test_each_random_entry_exits_by_its_members_own_rule(ens):
    _by, _path, taken = _book(ens)
    draws = ens.random_draws(taken, seed=41, count=4)
    checked = 0
    for d in draws.draws:
        for n, trades in d.items():
            for t in trades:
                table = ens.sims[n].tables[t.coin]
                assert t == table.trade_from(t.decided)
                assert t.exit_rule in ("strategy", "stop:OVL-MIDLINE", "end_of_data")
                closes = list(ens.universe.frames[t.coin]["close"])
                by_hand = _exit_by_hand(closes, n, t.entry_i)
                if by_hand is None:
                    assert t.forced
                else:
                    assert (t.exit_i, t.forced) == (by_hand, False)
                checked += 1
    assert checked > 20


def test_random_entries_repeat_for_a_seed_and_each_member_has_its_own(ens):
    from strategy_lab import baselines as bl

    _by, _path, taken = _book(ens)
    one = ens.random_draws(taken, seed=500, count=3)
    two = ens.random_draws(taken, seed=500, count=3)
    other = ens.random_draws(taken, seed=501, count=3)
    assert one.draws == two.draws and one.draws != other.draws
    # member k's draw b is drawn with seed + k * count + b
    for k, n in enumerate(ens.lookbacks):
        alone = bl.random_draws(ens.sims[n], taken[n], 500 + k * 3, 3)
        assert [d[n] for d in one.draws] == alone.draws


def test_random_entries_go_through_the_same_book(ens):
    _by, _path, taken = _book(ens, COSTS)
    draws = ens.random_draws(taken, seed=42, count=5)
    many = ens.replay_draws(draws.draws, COSTS, 10_000.0)
    chunked = ens.replay_draws(draws.draws, COSTS, 10_000.0, chunk=2)
    for p, d in enumerate(draws.draws):
        one = ens.replay_trades(d, COSTS, 10_000.0)
        # (not ``skipped_cash``: with many paths the replay counts the cash before a
        # path's veto, so it counts other draws' entries too)
        for name in (
            "net",
            "capital_days",
            "trades",
            "skipped_minimum",
            "max_drawdown",
        ):
            assert getattr(many, name)[p] == pytest.approx(getattr(one, name)[0])
            assert getattr(chunked, name)[p] == pytest.approx(getattr(one, name)[0])
        # the same cash: no path ever holds more than the account
        assert many.peak_committed[p] <= 1.0 + 1e-9
    # the same slices and minimums: where the book's slices are below the minimum,
    # every random entry is skipped too
    dear = Costs(fee=0.0, allowance=0.0, minimum_usd={"AAA": 300.0, "BBB": 300.0})
    small = ens.replay_draws(draws.draws, dear, 1_000.0)
    assert small.trades.sum() == 0 and (small.skipped_minimum > 0).all()


def test_the_book_skips_entries_it_cannot_fund_and_so_do_random_ones():
    # one coin rising: both members enter and gain; a dip stops the 20-day member out
    # but not the 30-day one, and on the next highs the 20-day member's share of the
    # grown account is more than the cash its exit left (the 30-day slice holds more)
    closes = (
        [100.0] * 400
        + list(np.linspace(101, 300, 200))
        + [296.0, 292.0, 288.0]
        + list(np.linspace(289, 400, 100))
        + [400.0] * 60
    )
    frames = {"AAA": daily(closes, start="2021-01-01")}
    group = en.Ensemble(Universe("1d", frames), lookbacks=(20, 30))
    by, path, taken = _book(group)
    assert path.skipped_cash[0] > 0
    # the book's own trades, as one draw, are the book: the same trades and skips
    own = group.replay_draws([by], FREE, 10_000.0)
    assert (own.net[0], own.trades[0], own.skipped_cash[0]) == (
        path.net[0], path.trades[0], path.skipped_cash[0],
    )  # fmt: skip
    draws = group.random_draws(taken, seed=7, count=8)
    rp = group.replay_draws(draws.draws, FREE, 10_000.0)
    # each draw is replayed by the same book, so its entries meet the same rule
    for p, d in enumerate(draws.draws):
        one = group.replay_trades(d, FREE, 10_000.0)
        assert (rp.net[p], rp.trades[p]) == (pytest.approx(one.net[0]), one.trades[0])


def test_matched_holds_keep_each_slices_holds(ens):
    from strategy_lab import baselines as bl

    _by, _path, taken = _book(ens)
    draws = ens.matched_draws(taken, seed=60, count=4)
    for b, d in enumerate(draws.draws):
        missing = 0
        for n in taken:
            for c in ens.coins:
                want = sorted(bl.held_bars(t) for t in taken[n] if t.coin == c)
                got = sorted(bl.held_bars(t) for t in d[n] if t.coin == c)
                assert len(got) <= len(want)
                missing += len(want) - len(got)
                # within a slice no two holds share a bar
                spans = sorted((t.entry_i, t.exit_i) for t in d[n] if t.coin == c)
                assert all(a[1] < b[0] for a, b in zip(spans, spans[1:]))
        assert missing == draws.dropped[b]
    for k, n in enumerate(ens.lookbacks):
        alone = bl.matched_draws(ens.sims[n], taken[n], 60 + k * 4, 4)
        assert [d[n] for d in draws.draws] == alone.draws


def test_the_hold_on_some_coins(ens):
    both = ens.hold(FREE, 10_000.0, None, detail=True)
    one = ens.hold(FREE, 10_000.0, None, coins=["AAA"], detail=True)
    assert both.trades[0] == 2 and one.trades[0] == 1
    assert one.detail[0][1] == pytest.approx(10_000.0)  # the one coin has it all
    assert one.curve is not None
    sub = ens.replay(FREE, 10_000.0, detail=True, coins=["AAA"])
    order = ens.slices(
        {n: [t for t in v if t.coin == "AAA"] for n, v in ens.trades().items()}
    )
    assert {order[i][1].coin for i, *_ in sub.detail} == {"AAA"}
    assert sub.detail[0][1] == pytest.approx(10_000.0 / 3)  # 1/1 coin x 1/3 members
    with pytest.raises(ValueError, match="ZZZ"):
        ens.hold(FREE, 10_000.0, None, coins=["ZZZ"])


# -- the equal-weight hold funds every coin (the owner's decision of 2026-11-14) -----------


def _late_listing():
    """AAA and BBB from 2021-01-01, doubling after their first month; CCC listed on day
    350, when the other two have doubled, and doubling after its own first month."""
    early = [100.0] * 30 + list(np.linspace(100, 200, 300)) + [200.0] * 170
    frames = {
        "AAA": daily(early, start="2021-01-01"),
        "BBB": daily(early, start="2021-01-01"),
        "CCC": daily([50.0] * 30 + list(np.linspace(50, 100, 120)), start="2021-12-17"),
    }
    return en.Ensemble(Universe("1d", frames), lookbacks=(20,))


def test_the_hold_buys_a_late_coin_with_its_own_share_of_the_start():
    group = _late_listing()
    hold = group.hold(FREE, 9_000.0, None, detail=True)
    # every coin is bought, each with 1/N of the starting account, not of the grown one
    assert int(hold.trades[0]) == 3 and int(hold.skipped_cash[0]) == 0
    trades = group.hold_trades(None)
    amounts = {trades[i].coin: amount for i, amount, *_ in hold.detail}
    assert amounts == pytest.approx({"AAA": 3_000.0, "BBB": 3_000.0, "CCC": 3_000.0})
    assert hold.intrabar_max_drawdown is not None  # lows and highs still marked


def test_a_late_coins_share_waits_idle_until_its_first_bar():
    group = _late_listing()
    hold = group.hold(FREE, 9_000.0, None, detail=True)
    times, equity = hold.curve
    ccc = next(t for t in group.hold_trades(None) if t.coin == "CCC")
    frame = group.universe.frames["AAA"]
    close_s = frame["open_time"].map(lambda t: int(t.timestamp())) + DAY
    before = np.flatnonzero(times < ccc.entry_s)[-1]
    k = int(np.searchsorted(close_s.to_numpy(), times[before], side="right")) - 1
    price = float(frame["close"].iloc[k])  # AAA and BBB are the same series
    # the two positions at their close, and CCC's share as cash
    assert equity[before] == pytest.approx(2 * 3_000.0 * price / 100.0 + 3_000.0)
    # from its first bar that share is in CCC, which doubles
    assert float(hold.final_equity[0]) == pytest.approx(2 * 6_000.0 + 6_000.0)


def test_a_coin_whose_share_is_below_its_minimum_is_named_not_skipped_silently():
    group = _late_listing()
    dear = Costs(fee=0.0, allowance=0.0, minimum_usd={"CCC": 5_000.0})
    plan = group.hold_plan(dear, 9_000.0, None)
    assert [t.coin for t in plan.trades] == ["AAA", "BBB"]
    assert "below its minimum entry" in plan.not_bought["CCC"]
    hold = group.hold(dear, 9_000.0, None, detail=True)
    assert int(hold.trades[0]) == 2 and int(hold.skipped_cash[0]) == 0
    # its share stays cash to the end
    assert float(hold.final_equity[0]) == pytest.approx(2 * 6_000.0 + 3_000.0)
