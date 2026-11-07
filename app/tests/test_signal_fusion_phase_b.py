"""FDS-SIG-004 phase B: blocks S and L, M and its payoff model, the expected value, and the
assessment's rules (sections 5.2, 5.3, 5.6 to 5.8 and 12).

* The dollar-volume approximation: section 12 item 5's hand-worked cases A to H, the bound
  with the true value as denominator, zero volume and invalid bars.
* The volatility candidates use only bars closed by each hour; the shrink only shrinks.
* m(f, e) equals the backtester's net return on every trade, and a fee enters the
  expected value only through m.
* Every row of section 5.8.3's table: Off, Log only, the predictive veto failing open, an
  enabled protective part failing closed, an error in each part, and the minimum check.
* Calibration is strictly out of fold; the climatology comes from training rows; a forced
  trade is never a label.
* The venue compatibility test, and the registered artifact the live hook may load.

No candles are read: every input is built here."""

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

from signal_fusion import assessment as asm  # noqa: E402
from signal_fusion import labels as lb  # noqa: E402
from signal_fusion import liquidity as lq  # noqa: E402
from signal_fusion import volatility as vol  # noqa: E402

DAY = 86400
HOUR = 3600
T0 = int(pd.Timestamp("2024-01-01", tz="UTC").timestamp())

# section 12 item 5: (H, L, C, V, VWAP) and the expected values to 4 significant figures:
# (TP, DV, DV̂, e, ē, error over DV̂, its bound)
CASES = {
    "A": (
        (102, 98, 100, 10, 100.5),
        (100.0, 1005, 1000, 0.004975, 0.02041, 0.005, 0.02),
    ),
    "B": ((120, 80, 118, 50, 82), (106.0, 4100, 5300, 0.2927, 0.325, 0.2264, 0.2453)),
    "C": ((200, 100, 200, 3, 101), (166.67, 303, 500, 0.6502, 0.6667, 0.394, 0.4)),
    "D": ((50, 40, 41, 6, 49.5), (43.667, 297, 262, 0.1178, 0.1267, 0.1336, 0.145)),
    "E": ((10, 10, 10, 7, 10), (10.0, 70, 70, 0.0, 0.0, 0.0, 0.0)),
}


def sig(x, y, figures=4):
    if y == 0:
        return abs(x) < 1e-12
    return math.isclose(x, y, rel_tol=0.5 * 10 ** (1 - figures))


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_hand_worked_approximation_cases(name):
    (h, lo, c, v, vwap), (tp, dv, dv_hat, e, e_bar, err_est, bound_est) = CASES[name]
    o = c  # the open plays no part
    assert sig(float(lq.typical_price(h, lo, c)), tp)
    got = float(lq.dollar_volume(o, h, lo, c, v))
    assert sig(got, dv_hat)
    assert sig(v * vwap, dv)
    assert sig(float(lq.relative_error(got, v * vwap)), e)
    bound = float(lq.error_bound(o, h, lo, c, v)) if v > 0 and h > lo else 0.0
    assert sig(bound, e_bar)
    assert float(lq.relative_error(got, v * vwap)) <= bound + 1e-12
    # the estimate-denominator form, for contrast only
    assert sig(abs(got - v * vwap) / got, err_est)
    assert sig(max(tp - lo, h - tp) / tp if h > lo else 0.0, bound_est)


def test_revision_2s_bound_fails_against_the_true_value_in_case_c():
    h, lo, c, v, vwap = CASES["C"][0]
    tp = float(lq.typical_price(h, lo, c))
    revision_2 = (h - lo) / tp
    true_error = float(lq.relative_error(lq.dollar_volume(c, h, lo, c, v), v * vwap))
    assert sig(revision_2, 0.6) and true_error > revision_2
    # case D: the high-side term binds
    h, lo, c, v, _ = CASES["D"][0]
    tp = float(lq.typical_price(h, lo, c))
    assert (h - tp) / h > (tp - lo) / lo


def test_zero_volume_and_invalid_bars():
    # F: zero volume counts as 0, with no bound
    assert float(lq.dollar_volume(10, 10.5, 9.5, 10, 0)) == 0.0
    assert math.isnan(float(lq.error_bound(10, 10.5, 9.5, 10, 0)))
    # G: every kind of invalid bar has a missing estimate, never 0
    bad = [
        (10, 10.5, 0.0, 10, 1),  # L = 0
        (10, 10.5, -1.0, 10, 1),  # L < 0
        (9.5, 9.0, 10.0, 9.5, 1),  # H < L
        (10, 10.5, 9.5, 11.0, 1),  # C above H
        (12.0, 10.5, 9.5, 10, 1),  # O outside [L, H]
        (10, 10.5, 9.5, 10, -1.0),  # V < 0
        (10, float("nan"), 9.5, 10, 1),
        (10, 10.5, 9.5, 10, float("inf")),
    ]
    for o, h, lo, c, v in bad:
        assert math.isnan(float(lq.dollar_volume(o, h, lo, c, v))), (o, h, lo, c, v)


def _bars(days=25, start=T0, volume=1.0, price=100.0):
    n = days * 24
    t = start + HOUR * np.arange(n)
    o = np.full(n, price)
    return t, o, o * 1.001, o * 0.999, o, np.full(n, volume)


def test_the_hourly_median_and_the_participation_bound():
    # H: three hours with (DV̂, ē) of (100, 10%), (200, 20%) and (300, 5%)
    median = lq.Median(200.0, 0.20, 3, 0)
    check = lq.participation(2.0, median, pi=0.01)
    assert check.ok and math.isclose(check.value, 0.01)
    assert math.isclose(check.bound, 0.012)  # 2 / (200 / 1.2)
    # from bars: 20 complete days before the decision's day
    t, o, h, lo, c, v = _bars()
    at = T0 + 22 * DAY + 5 * HOUR
    m = lq.hourly_median(t, o, h, lo, c, v, at)
    assert m.value == pytest.approx(100.0 * 1.0) and m.hours == 480
    # an invalid hour is left out and counted; a missing hour counts as zero volume
    v2 = v.copy()
    v2[(2 * DAY) // HOUR] = -1.0
    keep = np.ones(len(t), dtype=bool)
    keep[(3 * DAY) // HOUR : (3 * DAY) // HOUR + 5] = False
    m2 = lq.hourly_median(t[keep], o[keep], h[keep], lo[keep], c[keep], v2[keep], at)
    assert m2.invalid == 1 and m2.hours == 479
    # fewer than 20 complete days: missing, never a pass
    short = lq.hourly_median(t, o, h, lo, c, v, T0 + 10 * DAY)
    assert short.value is None
    assert lq.participation(1.0, short).ok is None
    # zero volume throughout: the median is zero, so the input is missing
    zero = lq.hourly_median(t, o, h, lo, c, np.zeros(len(t)), at)
    assert zero.value is None


def test_the_spread_cap_and_an_unusable_quote():
    assert lq.spread(99.9, 100.1, 5.0).ok is True
    assert lq.spread(99.0, 101.0, 5.0).ok is False  # 2% against 0.5%
    for bid, ask, age in (
        (None, 100, 1),
        (100, 99, 1),
        (100, 100.1, 61),
        (100, 100.1, None),
    ):
        assert lq.spread(bid, ask, age).ok is None, (bid, ask, age)


# --- volatility -------------------------------------------------------------------------------


def _walk(n, seed=0):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    return c * 1.003, c * 0.997, c


def test_the_volatility_candidates_use_only_bars_closed_by_each_hour():
    h, lo, c = _walk(1000)
    full = vol.variances(h, lo, c)
    for k in (300, 500, 999):
        cut = vol.variances(h[: k + 1], lo[: k + 1], c[: k + 1])
        for name in vol.CANDIDATES:
            a, b = full[name][k], cut[name][k]
            assert (np.isnan(a) and np.isnan(b)) or math.isclose(a, b), (name, k)
    assert np.isnan(full["ewma"][: vol.BURN_IN]).all()
    assert np.isfinite(full["ewma"][vol.BURN_IN + 1 :]).all()
    truth = vol.realised(c)
    assert np.isnan(truth[-vol.HOURS :]).all()
    name, losses = vol.choose(full, truth, np.arange(200, 900))
    assert name in vol.CANDIDATES and set(losses) == set(vol.CANDIDATES)


def test_the_shrink_only_ever_shrinks():
    s = vol.shrink(np.array([0.5, 1.0, 2.0, np.nan]), 1.0)
    assert s[0] == 1.0 and s[1] == 1.0 and s[2] == 0.5 and np.isnan(s[3])


# --- M and the expected value -----------------------------------------------------------------


def _candles(n=24 * 150, seed=4):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.01, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC"),
            "open": open_,
            "high": np.maximum(open_, close) * 1.002,
            "low": np.minimum(open_, close) * 0.998,
            "close": close,
            "volume": rng.uniform(1, 100, n),
        }
    )


def test_m_f_e_equals_the_backtesters_net_return_on_every_trade():
    from backtest.engine import CostModel, run_backtest
    from strategies import create
    from strategies.runner import StrategyRunner

    candles = _candles()
    trades = lb.opportunities(candles, "X")
    assert len(trades) >= 5 and trades[-1].exit_s >= trades[-1].signal_s
    for fee_bps, slip_bps in ((50.0, 5.0), (120.0, 5.0), (0.0, 0.0)):
        cost = CostModel(fee_bps=fee_bps, slippage_bps=slip_bps, size_fraction=1.0)
        paid = run_backtest(
            candles, StrategyRunner(create("STRAT-001")), "X", "1h", cost=cost
        )
        assert len(paid.trades) == len(trades)
        for t, p in zip(trades, paid.trades):
            net = float(lb.net_return(t.gross, fee_bps / 1e4, slip_bps / 1e4))
            # the backtester's pnl_pct is a percentage
            assert math.isclose(100.0 * net, p.pnl_pct, rel_tol=1e-9, abs_tol=1e-10)
    # M at the evaluated fee is the sign of that net return
    g, m = lb.label_rows(trades, 0.005)
    forced = np.array([t.forced for t in trades])
    assert np.all(m[forced] == -1)
    be = lb.break_even(0.005, 0.0005)
    assert np.array_equal(m[~forced], (g[~forced] > be).astype(int))


def test_a_fee_enters_the_expected_value_only_through_m():
    p, w, lo = 0.3, 0.06, -0.02
    for fee in (0.0, 0.005, 0.012):
        for e in (0.0005, 0.002):
            ev = float(lb.expected_value(p, w, lo, fee, e))
            mu = p * w + (1 - p) * lo
            assert math.isclose(ev, (1 + mu) * lb.multiplier(fee, e) - 1)
    # the veto acts exactly when the gross mean is at or below break-even
    mu = p * w + (1 - p) * lo
    for fee in (0.001, 0.005, 0.01):
        ev = float(lb.expected_value(p, w, lo, fee, 0.0005))
        assert (ev <= 0) == (mu <= lb.break_even(fee, 0.0005))
    # the spread and the allowance are never both charged
    assert lb.decision_allowance(0.004) == 0.002
    assert lb.decision_allowance(0.0002) == 0.0005
    assert lb.decision_allowance(None) == 0.0005


def test_the_payoff_tables_pool_a_small_cell():
    rng = np.random.default_rng(2)
    g = rng.normal(0, 0.05, 400)
    m = (g > 0.01).astype(int)
    t = np.where(
        np.arange(400) < 390, rng.integers(0, 2, 400), 2
    )  # tercile 2: 10 trades
    tables = lb.payoffs(g, m, t)
    assert tables.counts[2][0] + tables.counts[2][1] == 10
    assert tables.at(2) == tables.pooled
    assert tables.at(-1) == tables.pooled
    assert tables.win[0] == pytest.approx(g[(t == 0) & (m == 1)].mean())


# --- the assessment's rules (section 5.8.3) ----------------------------------------------------


def ok_spread():
    return True, 0.001, ""


def ok_part(amount):
    return True, amount / 10_000.0, ""


def _protective(
    settings,
    shrink=lambda: 1.0,
    spread=ok_spread,
    part=ok_part,
    minimum=50.0,
    amount=100.0,
):
    return asm.protective(settings, amount, minimum, shrink, spread, part)


def test_off_computes_nothing_and_log_only_never_changes_an_entry():
    def boom():
        raise AssertionError("a part that is Off computes nothing")

    off = asm.Settings()
    assert off.all_off()
    assert asm.predictive(off, boom).effect == "allow"
    assert (
        _protective(off, shrink=boom, spread=boom, part=lambda a: boom()).effect
        == "allow"
    )
    log = asm.Settings("log_only", "log_only", "log_only", "log_only")

    def fail():
        raise RuntimeError("no data")

    r = asm.predictive(log, lambda: -0.01)
    assert r.effect == "allow" and r.parts[0].would == "veto"
    r = _protective(
        log,
        shrink=fail,
        spread=lambda: (False, 0.02, "too wide"),
        part=lambda a: (None, None, "missing"),
    )
    assert r.effect == "allow"
    assert [p.would for p in r.parts] == ["skip", "skip", "skip"]


def test_the_predictive_veto_fails_open():
    on = asm.Settings(entry_assessment="veto")
    assert asm.predictive(on, lambda: -0.001).effect == "skip"
    assert asm.predictive(on, lambda: 0.0).effect == "skip"  # EV <= 0
    assert asm.predictive(on, lambda: 0.002).effect == "allow"
    for unavailable in (
        lambda: None,
        lambda: (_ for _ in ()).throw(ValueError("hash")),
    ):
        r = asm.predictive(on, unavailable)
        assert r.effect == "allow" and not r.parts[0].available and r.parts[0].reason


def test_an_enabled_protective_part_fails_closed():
    def fail():
        raise RuntimeError("calculation error")

    shrink_on = asm.Settings(volatility_shrink="on")
    for bad in (lambda: None, fail, lambda: float("nan"), lambda: 1.5):
        r = _protective(shrink_on, shrink=bad)
        assert r.effect == "skip" and r.part == "volatility_shrink", bad
    spread_on = asm.Settings(spread_cap="on")
    for bad in (lambda: (None, None, "the quote is too old"), fail):
        r = _protective(spread_on, spread=bad)
        assert r.effect == "skip" and r.part == "spread_cap"
    assert (
        _protective(spread_on, spread=lambda: (False, 0.02, "too wide")).effect
        == "skip"
    )
    cap_on = asm.Settings(participation_cap="on")
    for bad in (
        lambda a: (None, None, "fewer than 20 complete days"),
        lambda a: fail(),
    ):
        r = _protective(cap_on, part=bad)
        assert r.effect == "skip" and r.part == "participation_cap"
    assert _protective(cap_on).effect == "allow"


def test_a_shrunk_entry_below_the_minimum_is_skipped_never_raised():
    on = asm.Settings(volatility_shrink="on")
    r = _protective(on, shrink=lambda: 0.4, amount=100.0, minimum=50.0)
    assert r.effect == "skip" and r.part == "minimum"
    r = _protective(on, shrink=lambda: 0.8, amount=100.0, minimum=50.0)
    assert r.effect == "scale" and r.scale == 0.8
    # the participation cap sees the shrunk amount
    seen = []
    cap = asm.Settings(volatility_shrink="on", participation_cap="on")
    _protective(
        cap, shrink=lambda: 0.8, part=lambda a: (seen.append(a), (True, 0.0, ""))[1]
    )
    assert seen == [80.0]


def test_the_result_is_only_allow_skip_or_a_scale_of_at_most_1():
    with pytest.raises(ValueError):
        asm.Result("enter")
    with pytest.raises(ValueError):
        asm.Result("scale", 1.2)
    with pytest.raises(ValueError):
        asm.Result("scale", 0.0)
    with pytest.raises(ValueError):
        asm.Settings(entry_assessment="on")


# --- calibration out of fold, the compatibility test and the artifact -------------------------


def _meta_rows(n=3000, seed=5):
    rng = np.random.default_rng(seed)
    signal = np.sort(T0 + rng.integers(0, 400 * DAY, n))
    exit_s = signal + rng.integers(1, 5 * DAY, n)
    x = rng.normal(size=(n, 3))
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-(x[:, 0] - 0.5)))).astype(int)
    folds = [(T0 + k * 100 * DAY, T0 + (k + 1) * 100 * DAY) for k in range(4)]
    return x, y, signal, exit_s, folds


def test_calibration_is_strictly_out_of_fold():
    pytest.importorskip("sklearn")
    from signal_fusion import meta

    x, y, signal, exit_s, folds = _meta_rows()
    wf = meta.walk_forward(x, y, signal, exit_s, folds)
    first = wf.fold == 0
    assert np.isnan(wf.calibrated[first]).all()  # fold 1: no calibration
    later = wf.fold == 3
    assert np.isfinite(wf.calibrated[later]).all()
    # changing fold 4's own labels changes neither its probabilities nor its climatology
    y2 = y.copy()
    y2[later] = 1 - y2[later]
    wf2 = meta.walk_forward(x, y2, signal, exit_s, folds)
    assert np.allclose(wf.calibrated[later], wf2.calibrated[later])
    assert np.allclose(wf.climatology[later], wf2.climatology[later])
    # the climatology is the base rate of the fold's training rows
    a = folds[3][0]
    train = exit_s <= a
    assert math.isclose(wf.climatology[later][0], y[train].mean())
    # a trade the bars forced closed (-1) is never a training label
    y3 = y.copy()
    y3[:200] = -1
    wf3 = meta.walk_forward(x, y3, signal, exit_s, folds)
    assert wf3.fits[1]["training_rows"] == int(
        ((exit_s <= folds[1][0]) & (y3 >= 0)).sum()
    )


def test_the_venue_compatibility_test():
    from signal_fusion import compat

    rng = np.random.default_rng(0)
    a = {"r24": rng.normal(size=600), "v2": rng.normal(size=600)}
    p = rng.uniform(0.1, 0.5, 600)
    ev = rng.normal(size=600)
    same = compat.compatibility(a, a, p, p, ev, ev)
    assert same["passes"] and same["median_dp"] == 0.0
    noisy = {k: v + rng.normal(0, 1.0, 600) for k, v in a.items()}
    other = compat.compatibility(a, noisy, p, p + rng.normal(0, 0.1, 600), ev, -ev)
    assert not other["passes"]
    assert other["checks"] == {
        "spearman": False,
        "median_dp": False,
        "p95_dp": False,
        "ev_sign": False,
    }


def test_the_live_hook_loads_only_the_registered_artifact(tmp_path, monkeypatch):
    from signal_fusion import artifact

    body = artifact.seal({"models": {"F_PV": [0.1, 0.2]}, "sigma_ref": 0.03})
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    data, why = artifact.load(str(path), body["sha256"])
    assert data is not None and why == ""
    assert artifact.load(None, body["sha256"])[1] == "no registered model"
    assert artifact.load(str(path), "0" * 64)[1] == "this is not the registered model"
    changed = dict(body, sigma_ref=0.05)
    path.write_text(json.dumps(changed), encoding="utf-8")
    assert artifact.load(str(path), body["sha256"])[1] == (
        "the registered model's file has changed"
    )
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(artifact, "code_hash", lambda: "f" * 64)
    assert artifact.load(str(path), body["sha256"])[1] == (
        "the assessment's code has changed since registration"
    )
    assert "model_lab/features.py" in artifact.code_files()
