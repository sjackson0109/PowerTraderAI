"""The feature library (PTAI-RD-001 WP 4.1; architecture layer L2).

* Every feature, as of each bar: computing on the candles up to t never changes a
  value up to t; the warm-up bars carry no value and every later one does; a
  window-local feature does not depend on where the candles start.
* Hand-worked values for each family, and the shared indicators agree with the
  strategies' own (ATR, EMA, Wilder's smoothing).
* Parameters: defaults, bounds, unknown names refused; the key is canonical; missing
  columns refused.

Synthetic candles only."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

import feature_library as fl
from strategies.indicators import atr, ema


def candles(n=300, seed=3):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.01, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.01, n))
    volume = rng.uniform(100, 1000, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


def frame(**cols):
    n = len(next(iter(cols.values())))
    base = {k: np.full(n, 1.0) for k in ("open", "high", "low", "close", "volume")}
    base.update({k: np.asarray(v, dtype=float) for k, v in cols.items()})
    return pd.DataFrame(base)


ALL = sorted(fl.FEATURES)


def test_the_library_has_each_family():
    assert {fl.get(f).family for f in ALL} == {"price", "volatility", "volume"}
    assert len(ALL) >= 13


@pytest.mark.parametrize("fid", ALL)
def test_no_value_looks_ahead(fid):
    assert fl.as_of_problems(fid, candles(), [30, 61, 150, 299]) == []


@pytest.mark.parametrize("fid", ALL)
def test_the_warm_up_bars_carry_no_value_and_every_later_one_does(fid):
    f = fl.get(fid)
    values = fl.compute(fid, candles()).to_numpy()
    w = f.warmup(f.params())
    assert np.isnan(values[:w]).all()
    assert np.isfinite(values[w:]).all(), np.flatnonzero(~np.isfinite(values[w:]))


@pytest.mark.parametrize("fid", [f for f in ALL if fl.get(f).window_local])
def test_a_window_local_feature_does_not_depend_on_where_the_candles_start(fid):
    f = fl.get(fid)
    c = candles()
    w = f.warmup(f.params())
    full = fl.compute(fid, c).to_numpy()
    for start in (17, 90):
        late = fl.compute(fid, c.iloc[start:].reset_index(drop=True)).to_numpy()
        np.testing.assert_allclose(late[w:], full[start + w :], rtol=1e-12)


# -- hand-worked values -------------------------------------------------------------------


def test_price_features():
    c = frame(close=[10, 11, 12, 13, 14, 12])
    assert fl.compute("price.return", c, n=2).iloc[-1] == pytest.approx(12 / 13 - 1)
    sma = fl.compute("price.sma_ratio", c, n=3)
    assert sma.iloc[-1] == pytest.approx(12 / np.mean([13, 14, 12]) - 1)
    pos = fl.compute("price.channel_position", c, n=3)
    assert pos.iloc[-1] == pytest.approx(0.0)  # 12 is the lowest of 13, 14, 12
    assert pos.iloc[-2] == pytest.approx(1.0)
    flat = fl.compute("price.channel_position", frame(close=[5, 5, 5]), n=3)
    assert flat.iloc[-1] == 0.5
    rising = fl.compute("price.rsi", frame(close=np.arange(1, 30)), n=14)
    assert rising.iloc[-1] == 100.0


def test_volatility_features():
    close = [100, 101, 99, 102, 103, 101]
    c = frame(
        close=close, high=[x * 1.02 for x in close], low=[x * 0.99 for x in close]
    )
    r = np.diff(np.log(close))[-4:]
    assert fl.compute("volatility.realised", c, n=4).iloc[-1] == pytest.approx(
        np.std(r, ddof=1)
    )
    park = math.sqrt(math.log(1.02 / 0.99) ** 2 / (4 * math.log(2)))
    assert fl.compute("volatility.parkinson", c, n=3).iloc[-1] == pytest.approx(park)
    lam = 0.9
    r_all = np.diff(np.log(close))
    s2 = r_all[0] ** 2
    for x in r_all[1:]:
        s2 = lam * s2 + (1 - lam) * x**2
    got = fl.compute("volatility.ewma", c, lam=lam, burn_in=1).iloc[-1]
    assert got == pytest.approx(math.sqrt(s2))


def test_yang_zhang():
    o = [100.0, 101.0, 99.5, 102.0, 103.0]
    h = [102.0, 103.0, 101.0, 104.0, 105.0]
    lo = [99.0, 100.0, 98.0, 101.0, 102.0]
    cl = [101.0, 100.0, 101.5, 103.0, 102.5]
    c = frame(open=o, high=h, low=lo, close=cl)
    n = 3
    jump = [math.log(o[i] / cl[i - 1]) for i in range(2, 5)]
    body = [math.log(cl[i] / o[i]) for i in range(2, 5)]
    rs = [
        math.log(h[i] / cl[i]) * math.log(h[i] / o[i])
        + math.log(lo[i] / cl[i]) * math.log(lo[i] / o[i])
        for i in range(2, 5)
    ]
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    var = np.var(jump, ddof=1) + k * np.var(body, ddof=1) + (1 - k) * np.mean(rs)
    got = fl.compute("volatility.yang_zhang", c, n=n)
    assert got.iloc[-1] == pytest.approx(math.sqrt(var))
    assert got.iloc[:n].isna().all() and np.isfinite(got.iloc[n:]).all()


def test_volume_features():
    c = frame(
        close=[10, 11, 10, 10, 12],
        high=[11, 12, 11, 11, 13],
        low=[9, 10, 9, 9, 11],
        volume=[100, 200, 300, 400, 600],
    )
    rel = fl.compute("volume.relative", c, n=2)
    assert rel.iloc[-1] == pytest.approx(600 / 350)
    share = fl.compute("volume.signed_share", c, n=3)
    assert share.iloc[-1] == pytest.approx((-300 + 0 + 600) / 1300)
    cmf = fl.compute("volume.cmf", c, n=2)
    mult = [((10 - 9) - (11 - 10)) / 2, ((12 - 11) - (13 - 12)) / 2]
    assert cmf.iloc[-1] == pytest.approx((mult[0] * 400 + mult[1] * 600) / 1000)
    tp = [(h + lo + cl) / 3 for h, lo, cl in zip(c["high"], c["low"], c["close"])]
    flows = [tp[i] * c["volume"][i] for i in range(5)]
    pos = flows[3] * (tp[3] > tp[2]) + flows[4] * (tp[4] > tp[3])
    neg = flows[3] * (tp[3] < tp[2]) + flows[4] * (tp[4] < tp[3])
    mfi = fl.compute("volume.mfi", c, n=2).iloc[-1]
    assert mfi == pytest.approx(100 if neg == 0 else 100 - 100 / (1 + pos / neg))


def test_the_shared_indicators_agree_with_the_strategies():
    c = candles()
    got = fl.compute("volatility.atr_ratio", c, n=14) * c["close"]
    want = atr(c["high"], c["low"], c["close"], 14)
    np.testing.assert_allclose(got[13:], want[13:], rtol=1e-12)
    got = (fl.compute("price.ema_ratio", c, n=20) + 1) * ema(c["close"], 20)
    np.testing.assert_allclose(got[19:], c["close"][19:], rtol=1e-12)


# -- parameters ---------------------------------------------------------------------------


def test_parameters_and_keys():
    assert fl.key("price.sma_ratio", {}) == 'price.sma_ratio@1{"n":20}'
    assert fl.key("price.sma_ratio", {"n": 20}) == fl.key("price.sma_ratio", {})
    with pytest.raises(ValueError, match="unknown parameter"):
        fl.compute("price.sma_ratio", candles(), m=3)
    with pytest.raises(ValueError, match="must be from"):
        fl.compute("price.sma_ratio", candles(), n=1)
    with pytest.raises(ValueError, match="have no"):
        fl.compute("volume.cmf", candles()[["close"]])
    with pytest.raises(KeyError):
        fl.get("price.nope")


def test_the_as_of_check_catches_a_feature_that_looks_ahead(monkeypatch):
    peek = fl.Feature(
        "price.peek",
        1,
        "Tomorrow's close (a deliberate look-ahead).",
        ("close",),
        {},
        lambda c, p: c["close"].shift(-1),
        lambda p: 0,
    )
    monkeypatch.setitem(fl.FEATURES, "price.peek", peek)
    assert fl.as_of_problems("price.peek", candles(), [30, 150]) == [30, 150]
