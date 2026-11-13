"""FDS-SIG-004 phase A: the evaluation tools (section 8.3).

* The scoring rules match hand-worked values and scikit-learn's ``log_loss`` and
  ``brier_score_loss``; the calibration intercept and slope recover known values.
* The bootstrap is reproducible from its seed, keeps pairs on the same days, covers N days
  a draw, pools its 10 runs exactly, and applies the block-length rule.
* R3 keeps the filter's per-coin veto counts, on assessable, eligible opportunities only;
  R3s gives the same scales in a random order.
* The portfolio replay reproduces ``run_backtest``'s trades for one coin at 100%, and keeps
  one trade per coin, free cash, the minimum check and the halt report.
* Within the bar: with the lows, the drawdown and the halt are also measured at each
  interval's lowest low (several coins summed, a coin without lows at its close), and
  no other figure changes; F3 shows them beside requirement 5, which they never decide.
* F3 and the wording rules on constructed paths (section 12, item 10).

No candles are read: every input is built here."""

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

from signal_fusion.evaluation import baselines as bl  # noqa: E402
from signal_fusion.evaluation import bootstrap as bs  # noqa: E402
from signal_fusion.evaluation import findings as fd  # noqa: E402
from signal_fusion.evaluation import scoring as sc  # noqa: E402
from signal_fusion.evaluation.replay import (  # noqa: E402
    Account,
    Costs,
    Opportunity,
    replay,
)

DAY = 86400
HOUR = 3600
T0 = int(pd.Timestamp("2024-01-01", tz="UTC").timestamp())


# --- scoring -----------------------------------------------------------------------------------


def test_the_scoring_rules_match_hand_worked_values_and_scikit_learn():
    y = np.array([1, 0, 1, 1])
    p = np.array([0.9, 0.2, 0.6, 0.4])
    hand_ll = -(math.log(0.9) + math.log(0.8) + math.log(0.6) + math.log(0.4)) / 4
    assert math.isclose(sc.log_loss(y, p), hand_ll, rel_tol=1e-12)
    assert math.isclose(sc.brier(y, p), (0.01 + 0.04 + 0.16 + 0.36) / 4, rel_tol=1e-12)
    sklearn = pytest.importorskip("sklearn.metrics")
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 500)
    p = rng.uniform(0.01, 0.99, 500)
    assert math.isclose(sc.log_loss(y, p), sklearn.log_loss(y, p), rel_tol=1e-10)
    assert math.isclose(sc.brier(y, p), sklearn.brier_score_loss(y, p), rel_tol=1e-12)
    # the decomposition's parts add up to the Brier score
    m = sc.murphy(y, p)
    assert math.isclose(
        m["reliability"] - m["resolution"] + m["uncertainty"] + m["within"], m["brier"]
    )
    # clipping: a probability of 0 for an event is a large, finite loss
    assert math.isclose(sc.log_loss([1], [0.0]), -math.log(1e-6))


def test_the_skill_score_and_the_calibration_measures_recover_known_values():
    y = np.array([1, 0, 0, 0] * 50)
    clim = np.full(len(y), 0.25)
    assert math.isclose(sc.brier_skill(y, clim, clim), 0.0, abs_tol=1e-15)
    # a constant 0.5 forecast for a 0.25 base rate: a = logit(0.25)
    a = sc.calibration_intercept(y, np.full(len(y), 0.5))
    assert math.isclose(a, math.log(0.25 / 0.75), rel_tol=1e-9)
    # outcomes drawn with logit(P) = 0.5 logit(p): the slope is about 0.5
    rng = np.random.default_rng(1)
    p = rng.uniform(0.05, 0.95, 200_000)
    truth = sc.sigmoid(0.5 * sc.logit(p))
    y = (rng.uniform(size=len(p)) < truth).astype(float)
    alpha, b = sc.calibration_slope(y, p)
    assert abs(b - 0.5) < 0.02 and abs(alpha) < 0.02
    assert sc.sharpness(np.array([0.2, 0.4]))["std"] == pytest.approx(0.1)
    assert sc.qlike([2.0], [2.0])[0] == pytest.approx(0.0)
    assert sc.qlike([1.0], [2.0])[0] == pytest.approx(2.0 - math.log(2.0) - 1.0)


# --- the bootstrap -----------------------------------------------------------------------------


def _sums(n_days=200, seed=0, m=2):
    rng = np.random.default_rng(seed)
    t = T0 + rng.integers(0, n_days * DAY, 5000)
    cols = [rng.normal(size=5000) for _ in range(m)]
    return bs.day_sums(t, cols, T0, T0 + (n_days - 1) * DAY)


def test_the_bootstrap_is_reproducible_and_keeps_pairs_on_the_same_days():
    sums = _sums()
    a = bs.Bootstrap(sums.days, 77)
    b = bs.Bootstrap(sums.days, 77)
    assert np.array_equal(a.starts(3), b.starts(3))
    assert not np.array_equal(a.starts(3), bs.Bootstrap(sums.days, 78).starts(3))
    # one statistic over both columns equals each column resampled on the same days
    both = a.resampled(sums, 0)
    one = a.resampled(bs.DaySums(sums.first_day, sums.sums[:, :1]), 0)
    two = a.resampled(bs.DaySums(sums.first_day, sums.sums[:, 1:]), 0)
    assert np.allclose(both, np.hstack([one, two]))
    # every draw covers exactly N days
    counts = a.day_counts(0)
    assert np.all(counts.sum(axis=1) == sums.days)
    # the day counts and the block sums agree
    assert np.allclose(counts @ sums.sums, both)


def test_the_centred_p_value_pools_its_ten_runs_exactly():
    draws = np.arange(-50, 50, dtype=float).reshape(10, 10) / 100.0
    theta = 0.2
    hand = (1 + np.sum(draws - theta >= theta)) / (draws.size + 1)
    assert bs.centred_p(theta, draws) == hand
    report = bs.ten_runs(theta, draws)
    assert len(report["runs"]) == 10 and report["p"] == hand
    sums = _sums()
    out = bs.test_statistic(sums, bs.mean_of(0, 1), seed=5)
    assert out["draws"] == bs.RUNS * bs.DRAWS_PER_RUN
    assert len(out["runs"]) == 10


def test_the_block_length_rule():
    assert bs.block_length([1.0] * 99 + [20.0]) == 28  # exactly 1% long: not more
    assert bs.block_length([1.0] * 98 + [20.0, 20.0]) == 56
    assert bs.block_length(None) == 28


# --- R3 and R3s --------------------------------------------------------------------------------


def test_r3_keeps_the_filters_per_coin_veto_counts_on_its_candidates_only():
    coins = ["BTC"] * 10 + ["ETH"] * 10
    candidates = [0, 1, 2, 3, 4, 5, 10, 11, 12]  # 6..9 and 13..19 not assessable
    vetoed = [0, 1, 7, 10]  # 7 is not a candidate
    counts = bl.veto_counts(coins, candidates, vetoed)
    assert counts == {"BTC": 2, "ETH": 1}
    v = bl.r3(coins, candidates, counts, len(coins), seed=9, run=0, draws=200)
    assert np.array_equal(v, bl.r3(coins, candidates, counts, 20, 9, 0, 200))
    for row in v:
        chosen = np.nonzero(row)[0].tolist()
        assert set(chosen) <= set(candidates)
        assert sum(1 for i in chosen if coins[i] == "BTC") == 2
        assert sum(1 for i in chosen if coins[i] == "ETH") == 1
    # every candidate is drawn about equally often
    freq = v[:, [0, 1, 2, 3, 4, 5]].mean(axis=0)
    assert np.all(np.abs(freq - 2 / 6) < 0.12)
    flat = bl.r3(coins, candidates, counts, 20, 9, 0, 50, stratified=False)
    assert np.all(flat.sum(axis=1) == 3)


def test_r3s_gives_the_same_scales_in_a_random_order():
    coins = ["BTC", "BTC", "ETH", "ETH", "ETH"]
    scales = [0.5, 1.0, 0.8, 0.3, 1.0]
    s = bl.r3s(coins, [0, 2, 3], scales, 5, seed=3, run=1, draws=100)
    for row in s:
        assert sorted(row[[0, 2, 3]].tolist()) == [0.3, 0.5, 0.8]
        assert row[1] == 1.0 and row[4] == 1.0


# --- the portfolio replay ----------------------------------------------------------------------


def _candles(n=24 * 200, seed=4):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.01, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, n)))
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.uniform(1, 100, n),
        }
    )


def test_the_replay_reproduces_run_backtest_for_one_coin_at_100_percent():
    from backtest.engine import CostModel, run_backtest
    from strategies import create
    from strategies.runner import StrategyRunner

    candles = _candles()
    cost = CostModel(fee_bps=50.0, slippage_bps=5.0, size_fraction=1.0)
    result = run_backtest(
        candles, StrategyRunner(create("STRAT-001")), "X", "1h", cost=cost
    )
    assert len(result.trades) >= 5
    slip = 0.0005
    opps = [
        Opportunity(
            "X",
            int(t.entry_time.timestamp()),
            int(t.exit_time.timestamp()),
            t.entry_price / (1 + slip),
            t.exit_price / (1 - slip),
        )
        for t in result.trades
    ]
    times = [int(x.timestamp()) for x in candles["open_time"]]
    prices = {"X": (times, candles["close"].tolist())}
    costs = Costs(fee=0.005, allowance=slip)
    paths = replay(opps, prices, costs, size_fraction=1.0, detail=True)
    assert len(paths.detail) == len(result.trades)
    for (i, amount, net, _days), t in zip(paths.detail, result.trades):
        # the backtester's pnl_pct is a percentage
        assert math.isclose(100.0 * net / amount, t.pnl_pct, rel_tol=1e-9), i
        assert math.isclose(
            net / amount,
            opps[i].gross * costs.multiplier() + costs.multiplier() - 1.0,
            rel_tol=1e-9,
        )
    assert math.isclose(paths.final_equity[0], result.equity[-1], rel_tol=1e-9)


def _opp(coin, day, days, gross, price=100.0):
    entry = T0 + day * DAY
    return Opportunity(coin, entry, entry + days * DAY, price, price * (1 + gross))


def _flat_prices(opps, end_day=400):
    hours = list(range(T0, T0 + end_day * DAY, HOUR))
    return {c: (hours, [100.0] * len(hours)) for c in {o.coin for o in opps}}


def test_the_replay_keeps_one_trade_per_coin_free_cash_and_the_minimum_check():
    opps = [
        _opp("BTC", 0, 5, 0.02),
        _opp("BTC", 2, 5, 0.02),  # BTC is not flat: not entered
        _opp("ETH", 1, 3, -0.01),
    ]
    costs = Costs(fee=0.005, minimum_usd={"BTC": 50.0, "ETH": 50.0})
    out = replay(opps, _flat_prices(opps), costs, Account(start=10_000.0), detail=True)
    assert out.trades[0] == 2
    assert [row[0] for row in out.detail] == [2, 0]  # ETH exits first
    assert out.status == ["taken", "not_flat", "taken"]
    assert out.eligible() == [0, 2]
    # 1% of 10,000 is 100, above the 50 minimum: a 0.4 shrink takes 40 below it: skipped,
    # never raised; BTC is then flat for its next opportunity
    scale = np.array([[0.4, 1.0, 1.0]])
    shrunk = replay(opps, _flat_prices(opps), costs, scale=scale, detail=True)
    assert shrunk.skipped_minimum[0] == 1 and shrunk.trades[0] == 2
    assert shrunk.status == ["below_minimum", "taken", "taken"]
    with pytest.raises(ValueError, match="at most 1"):
        replay(opps, _flat_prices(opps), costs, scale=np.array([[1.2, 1, 1]]))
    # a small account: 1% is below the minimum, so every entry is the minimum entry
    small = replay(opps, _flat_prices(opps), costs, Account(start=100.0), detail=True)
    floor = costs.floor("BTC", Account().margin_pct)
    assert all(math.isclose(row[1], floor) for row in small.detail)
    # not enough cash: skipped and counted
    poor = replay(opps, _flat_prices(opps), costs, Account(start=60.0), detail=True)
    assert poor.skipped_cash[0] >= 1 and poor.status[2] == "no_cash"
    # vetoes are counted and leave the coin flat
    veto = np.array([[True, False, False]])
    v = replay(opps, _flat_prices(opps), costs, veto=veto, detail=True)
    assert v.vetoed[0] == 1 and sorted(r[0] for r in v.detail) == [1, 2]
    assert v.status == ["vetoed", "taken", "taken"] and v.eligible() == [0, 1, 2]


def test_the_halt_level_is_reported_and_can_end_a_path():
    opps = [_opp("BTC", 0, 30, -0.5)]
    hours = list(range(T0, T0 + 60 * DAY, HOUR))
    falling = [100.0 * (1 - 0.5 * min(1.0, i / (30 * 24))) for i in range(len(hours))]
    prices = {"BTC": (hours, falling)}
    acct = Account(start=10_000.0, start_pct=10.0, max_coin_pct=10.0)
    costs = Costs(fee=0.0, allowance=0.0)
    out = replay(opps, prices, costs, acct)
    assert out.halt_s[0] == -1  # 10% of the account falling by half: a 5% drawdown
    acct = Account(start=10_000.0, start_pct=10.0, max_coin_pct=100.0, halt_pct=4.0)
    reported = replay(opps, prices, costs, acct)
    assert reported.halt_s[0] > 0 and reported.trades[0] == 1
    ended = replay(opps, prices, costs, acct, halt_ends=True)
    assert ended.halt_s[0] == reported.halt_s[0]
    assert (
        ended.net[0] > reported.net[0]
    )  # marked at the halt, before the rest of the fall


# --- within the bar (A2 N18) -------------------------------------------------------------------


def _dip(closes=(100, 100, 93, 97, 100, 103, 105, 105, 105, 105, 105, 105)):
    """One coin bought with the whole account at 100 on day 0 and sold at 105 on day 10,
    on daily bars closing at T0 + k days. The closes fall 7% from the peak on day 2;
    that day's low is 91, 9% below it. Every other low is 0.5% under its close."""
    times = [T0 + k * DAY for k in range(len(closes))]
    lows = [c * 0.995 for c in closes]
    lows[2] = 91.0
    opps = [Opportunity("BTC", T0, T0 + 10 * DAY, 100.0, 105.0)]
    return opps, {"BTC": (times, list(closes))}, {"BTC": (times, lows)}


def test_a_dip_within_the_bar_reaches_the_halt_that_the_closes_do_not():
    opps, prices, lows = _dip()
    free = Costs(fee=0.0, allowance=0.0)
    kw = dict(size_fraction=1.0, mark_s=DAY)
    closes_only = replay(opps, prices, free, Account(start=10_000.0), **kw)
    out = replay(opps, prices, free, Account(start=10_000.0), lows=lows, **kw)
    # at the closes: a 7% drawdown, below the 8% halt level
    assert out.max_drawdown[0] == pytest.approx(0.07)
    assert out.halt_s[0] == -1
    # within the bar: 9%, so the halt is reported, at the end of the day of the dip
    assert out.intrabar_max_drawdown[0] == pytest.approx(0.09)
    assert out.intrabar_max_drawdown_usd[0] == pytest.approx(900.0)
    assert out.intrabar_halt_s[0] == T0 + 2 * DAY
    # without lows the figures are absent, and nothing else differs
    assert closes_only.intrabar_max_drawdown is None
    assert closes_only.intrabar_halt_s is None
    assert closes_only.max_drawdown[0] == out.max_drawdown[0]
    assert closes_only.net[0] == out.net[0] == pytest.approx(500.0)
    # a halt level above the dip is not reached either way
    high = replay(
        opps, prices, free, Account(start=10_000.0, halt_pct=10.0), lows=lows, **kw
    )
    assert high.intrabar_halt_s[0] == -1


def test_the_lows_of_every_bar_in_a_marking_interval_count():
    # hourly bars, daily marks: the day's lowest hourly low is the one used
    hours = list(range(T0, T0 + 6 * DAY + HOUR, HOUR))
    closes = [100.0] * len(hours)
    lows = [99.9] * len(hours)
    lows[24 + 30] = 90.0  # 06:00 on day 2: an hour, not a close
    opps = [Opportunity("BTC", T0, T0 + 5 * DAY, 100.0, 100.0)]
    out = replay(
        opps,
        {"BTC": (hours, closes)},
        Costs(fee=0.0, allowance=0.0),
        Account(start=10_000.0),
        size_fraction=1.0,
        mark_s=DAY,
        lows={"BTC": (hours, lows)},
    )
    assert out.max_drawdown[0] == 0.0 and out.halt_s[0] == -1
    assert out.intrabar_max_drawdown[0] == pytest.approx(0.10)
    assert out.intrabar_halt_s[0] == T0 + 3 * DAY  # the day from T0 + 2 days


def test_several_coins_are_valued_at_their_lows_together():
    # half the account in each coin; each dips 10% within the same daily bar. The two
    # lows may have come at different hours, so the summed 10% is a bound, not a path
    times = [T0 + k * DAY for k in range(8)]
    closes = [100.0] * 8
    lows = [100.0] * 8
    lows[3] = 90.0
    opps = [
        Opportunity("BTC", T0, T0 + 6 * DAY, 100.0, 100.0),
        Opportunity("ETH", T0, T0 + 6 * DAY, 100.0, 100.0),
    ]
    out = replay(
        opps,
        {c: (times, closes) for c in ("BTC", "ETH")},
        Costs(fee=0.0, allowance=0.0),
        Account(start=10_000.0, start_pct=50.0, max_coin_pct=50.0),
        mark_s=DAY,
        lows={c: (times, lows) for c in ("BTC", "ETH")},
    )
    assert out.trades[0] == 2 and out.max_drawdown[0] == 0.0
    assert out.intrabar_max_drawdown[0] == pytest.approx(0.10)
    # a coin given no lows is valued at its close
    one = replay(
        opps,
        {c: (times, closes) for c in ("BTC", "ETH")},
        Costs(fee=0.0, allowance=0.0),
        Account(start=10_000.0, start_pct=50.0, max_coin_pct=50.0),
        mark_s=DAY,
        lows={"BTC": (times, lows)},
    )
    assert one.intrabar_max_drawdown[0] == pytest.approx(0.05)
    assert one.intrabar_halt_s[0] == -1


def _paths_fields(p):
    names = [f for f in p.__dataclass_fields__ if not f.startswith("intrabar_")]
    return {name: getattr(p, name) for name in names}


@pytest.mark.parametrize("halt_ends", [False, True])
def test_the_lows_change_no_other_figure(halt_ends):
    from signal_fusion.evaluation.replay import Cooldown

    rng = np.random.default_rng(21)
    coins = ("BTC", "ETH", "SOL")
    prices, lows = {}, {}
    for k, coin in enumerate(coins):
        c = _candles(n=24 * 120, seed=30 + k)
        t = [int(x.timestamp()) + HOUR for x in c["open_time"]]
        prices[coin] = (t, c["close"].tolist())
        lows[coin] = (t, c["low"].tolist())
    opps = []
    for _ in range(60):
        coin = coins[int(rng.integers(len(coins)))]
        t, p = prices[coin]
        a = int(rng.integers(0, len(t) - 200))
        b = a + int(rng.integers(5, 150))
        opps.append(Opportunity(coin, t[a], t[b], p[a], p[b]))
    veto = rng.uniform(size=(6, len(opps))) < 0.3
    scale = np.where(rng.uniform(size=(6, len(opps))) < 0.5, 1.0, 0.6)
    costs = Costs(
        fee=0.005,
        allowance=0.0005,
        minimum_usd={c: 5.0 for c in coins},
        base_increment={"BTC": 0.001},
    )
    acct = Account(start=2_000.0, start_pct=25.0, max_coin_pct=60.0, halt_pct=3.0)
    kw = dict(
        veto=veto,
        scale=scale,
        detail=True,
        halt_ends=halt_ends,
        cooldown=Cooldown(3, 6, False, HOUR),
    )
    plain = replay(opps, prices, costs, acct, **kw)
    low = replay(opps, prices, costs, acct, lows=lows, **kw)
    a, b = _paths_fields(plain), _paths_fields(low)
    assert a.keys() == b.keys()
    for name in a:
        if isinstance(a[name], np.ndarray):
            np.testing.assert_array_equal(a[name], b[name], err_msg=name)
        elif name == "curve":
            np.testing.assert_array_equal(a[name][0], b[name][0])
            np.testing.assert_array_equal(a[name][1], b[name][1])
        else:
            assert a[name] == b[name], name
    # the intrabar figures are never below the close-based ones, and never later
    assert np.all(low.intrabar_max_drawdown >= low.max_drawdown)
    assert np.all(low.intrabar_max_drawdown_usd >= low.max_drawdown_usd)
    halted = low.halt_s >= 0
    assert halted.any() and (low.intrabar_max_drawdown > low.max_drawdown).any()
    assert np.all(low.intrabar_halt_s[halted] >= 0)
    assert np.all(low.intrabar_halt_s[halted] <= low.halt_s[halted])


# --- F1 and Q2 on constructed forecasts --------------------------------------------------------


def _forecast_rows(n=20_000, days=400, seed=11):
    rng = np.random.default_rng(seed)
    t = np.sort(T0 + rng.integers(0, days * DAY, n))
    signal = rng.normal(size=n)
    truth = sc.sigmoid(-0.7 + 0.9 * signal)
    y = (rng.uniform(size=n) < truth).astype(float)
    return t, signal, truth, y


def test_f1_on_constructed_forecasts():
    t, signal, truth, y = _forecast_rows()
    base = np.full(len(y), y.mean())
    rng = np.random.default_rng(3)
    placebos = [
        np.clip(base + rng.normal(0, 0.01, len(y)), 0.01, 0.99) for _ in range(5)
    ]
    r = fd.f1(y, base, truth, placebos, t, seed=4, k=5)
    assert r["test"]["theta"] > 0 and r["test"]["p"] < 0.01
    assert r["conditions"] == {"placebo": True, "stability": True}
    assert fd.f1_passes(r, holm_pass=True)
    assert fd.f1_line(r, True).startswith("Volume improves forecasts over price alone")
    # no information: no improvement, and the line says so
    r = fd.f1(y, base, base, placebos, t, seed=4, k=5)
    assert r["test"]["p"] > 0.05
    assert fd.f1_line(r, False).startswith("No forecast improvement detected")


def test_the_three_calibration_outcomes():
    t, signal, truth, y = _forecast_rows()
    clim = np.full(len(y), y.mean())
    small = dict(runs=2, per_run=100)
    # a large, calibrated sample: within tolerance, with skill
    r = fd.calibration(y, truth, clim, t, seed=6, k=5, **small)
    assert r["outcome"] == "calibrated" and r["enough"]
    assert r["skill"]["theta"] > 0 and r["skill"]["p"] < 0.05
    assert fd.calibration_passes(r, holm_pass=True)
    # a miscalibrated one: forecasts too extreme (slope well below 1)
    extreme = sc.sigmoid(2.5 * sc.logit(truth))
    r = fd.calibration(y, extreme, clim, t, seed=6, k=5, **small)
    assert r["outcome"] == "miscalibrated" and r["slope"]["value"] < 0.6
    assert not fd.calibration_passes(r, holm_pass=True)
    # a small one: fewer than 200 events, and intervals too wide to fit their bands
    r = fd.calibration(y[:300], truth[:300], clim[:300], t[:300], seed=6, k=5, **small)
    assert not r["enough"] and r["outcome"] != "calibrated"
    assert not fd.calibration_passes(r, holm_pass=True)


# --- F3 and the wording rules ------------------------------------------------------------------


def _path(opps, account=Account(start=10_000.0), prices=None):
    prices = prices or _flat_prices(opps, end_day=420)
    return replay(opps, prices, Costs(fee=0.0, allowance=0.0), account, detail=True)


def _many(n, gross_of, coins=("BTC", "ETH", "SOL")):
    out = []
    for k in range(n):
        out.append(_opp(coins[k % len(coins)], 2 * k, 1, gross_of(k)))
    return out


def test_f3_on_constructed_paths():
    first, last = T0, T0 + 400 * DAY
    entries = lambda opps: [o.entry_s for o in opps]  # noqa: E731
    coins = lambda opps: [o.coin for o in opps]  # noqa: E731
    # profitable, stable, spread over coins, small drawdown: every requirement holds
    good = _many(180, lambda k: 0.01 if k % 4 else -0.005)
    r = fd.f3(_path(good), entries(good), coins(good), first, last, seed=1)
    assert r["requirements"]["trades"] and r["requirements"]["stable"]
    assert r["requirements"]["not_one_coin"] and r["requirements"]["within_halt"]
    assert r["test"]["p"] < 0.05
    assert fd.f3_passes(r, holm_pass=True)
    assert fd.f3_line(r, True, None).startswith("Profitable after fees")
    # profitable only through one coin: requirement 4 fails
    one = _many(180, lambda k: 0.03 if k % 3 == 0 else -0.004)
    r = fd.f3(_path(one), entries(one), coins(one), first, last, seed=1)
    assert not r["requirements"]["not_one_coin"]
    assert fd.f3_failed(r, True) == "a profit without the most profitable coin"
    line = fd.f3_line(r, False, fd.f3_failed(r, True))
    assert line.startswith(
        "Not shown to be profitable after fees. It failed the requirement for a "
        "positive net profit without its most profitable coin ($"
    )
    # the bootstrap passed, and the line says that is not the pass
    assert "passed Holm" in line and "a pass needs all five" in line
    # 99 trades: not assessable
    few = _many(99, lambda k: 0.01)
    r = fd.f3(_path(few), entries(few), coins(few), first, last, seed=1)
    assert not r["requirements"]["trades"]
    assert fd.f3_line(r, False, "too few trades").startswith("Not assessable")
    # a path that reaches the halt level fails requirement 5
    big = Account(start=10_000.0, start_pct=60.0, max_coin_pct=100.0)
    crash = [_opp("BTC", 0, 1, -0.5)] + _many(150, lambda k: 0.02)[1:]
    r = fd.f3(_path(crash, big), entries(crash), coins(crash), first, last, seed=1)
    assert not r["requirements"]["within_halt"]
    assert r["report"]["halt_pct"] == 8.0
    failures = fd.f3_failures(r, True)
    assert failures[-1] == (
        "exceeded the permitted 8% maximum drawdown, reaching "
        f"{r['report']['max_drawdown']:.2%}"
    )
    assert "exceeded the permitted 8% maximum drawdown" in fd.f3_line(
        r, False, fd.f3_failed(r, True)
    )


def test_f3_shows_the_intrabar_drawdown_beside_requirement_5_and_decides_nothing():
    opps, prices, lows = _dip()
    free = Costs(fee=0.0, allowance=0.0)
    kw = dict(size_fraction=1.0, mark_s=DAY, detail=True)
    first, last = T0, T0 + 11 * DAY
    entries, coins = [o.entry_s for o in opps], [o.coin for o in opps]
    with_lows = fd.f3(
        replay(opps, prices, free, lows=lows, **kw), entries, coins, first, last, 1
    )
    closes_only = fd.f3(
        replay(opps, prices, free, **kw), entries, coins, first, last, 1
    )
    # requirement 5 is measured at the closes, as declared: 7% is within the 8% level
    assert with_lows["requirements"] == closes_only["requirements"]
    assert with_lows["requirements"]["within_halt"]
    assert fd.f3_failures(with_lows, True) == fd.f3_failures(closes_only, True)
    rep = with_lows["report"]
    assert rep["max_drawdown"] == pytest.approx(0.07) and rep["halt_reached_s"] == -1
    assert rep["intrabar_max_drawdown"] == pytest.approx(0.09)
    assert rep["intrabar_halt_reached_s"] == T0 + 2 * DAY
    assert rep["intrabar_within_halt"] is False
    for key in ("intrabar_max_drawdown", "intrabar_halt_reached_s"):
        assert closes_only["report"][key] is None
    assert closes_only["report"]["intrabar_within_halt"] is None


def test_losing_less_is_reducing_losses_and_never_profitable():
    first, last = T0, T0 + 400 * DAY
    line = fd.f2_line({}, True, path_net=-120.0, trades=150, edge=0.0)
    assert line.startswith("Volume reduces losses") and "still loses money" in line
    assert "profitable" not in line.lower()
    for text in ("This filter is profitable", "It makes money"):
        with pytest.raises(ValueError):
            fd.check_wording(text, f3_line=False)
    assert fd.check_wording("Profitable after fees: ...", f3_line=True)
    # the F2 test itself: a filter that loses less than another, both losing money
    worse = [(T0 + k * DAY, -2.0, 10.0) for k in range(100)]
    better = [(T0 + k * DAY, -1.0, 10.0) for k in range(100)]
    test = fd.paired_paths(better, worse, first, last, seed=2)
    assert test["theta"] > 0 and test["p"] < 0.05
