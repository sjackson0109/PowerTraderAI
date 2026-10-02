"""FDS-121 acceptance 1: EMA/DEMA/TEMA/ATR/ADX match independent references (1e-6)."""

from __future__ import annotations

import math
import unittest

import numpy as np
import pandas as pd

from strategies import indicators as ind

TOL = 1e-6

# 40 closes (the classic Wilder/StockCharts example series)
CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
    45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
    46.21, 46.25, 45.71, 46.45, 45.78, 45.35, 44.03, 44.18, 44.22, 44.57,
    43.42, 42.66, 43.13, 43.70, 44.50, 45.20, 45.60, 46.10, 46.55, 46.30,
]
# deterministic, irregular wicks so true range and directional movement vary
HIGHS = [c + 0.25 + 0.05 * (i % 5) for i, c in enumerate(CLOSES)]
LOWS = [c - 0.30 - 0.04 * (i % 3) for i, c in enumerate(CLOSES)]


# --- independent scalar reference implementations ------------------------------------


def ref_ema(xs, n):
    a = 2.0 / (n + 1)
    out = [xs[0]]
    for x in xs[1:]:
        out.append(a * x + (1 - a) * out[-1])
    return out


def ref_dema(xs, n):
    e1 = ref_ema(xs, n)
    e2 = ref_ema(e1, n)
    return [2 * a - b for a, b in zip(e1, e2)]


def ref_tema(xs, n):
    e1 = ref_ema(xs, n)
    e2 = ref_ema(e1, n)
    e3 = ref_ema(e2, n)
    return [3 * a - 3 * b + c for a, b, c in zip(e1, e2, e3)]


def ref_tr(h, l, c):
    return [h[0] - l[0]] + [
        max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))
    ]


def ref_atr(h, l, c, n):
    tr = ref_tr(h, l, c)
    out = [math.nan] * (n - 1) + [sum(tr[:n]) / n]
    for i in range(n, len(c)):
        out.append((out[-1] * (n - 1) + tr[i]) / n)
    return out


def ref_adx(h, l, c, n):
    """Wilder's DMI/ADX straight from the definition."""
    size = len(c)
    tr = ref_tr(h, l, c)
    pdm, mdm = [0.0] * size, [0.0] * size
    for i in range(1, size):
        up, down = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm[i] = up if (up > down and up > 0) else 0.0
        mdm[i] = down if (down > up and down > 0) else 0.0
    s_tr = sum(tr[1 : n + 1])
    s_p = sum(pdm[1 : n + 1])
    s_m = sum(mdm[1 : n + 1])
    dx = {}
    for i in range(n, size):
        if i > n:
            s_tr = s_tr - s_tr / n + tr[i]
            s_p = s_p - s_p / n + pdm[i]
            s_m = s_m - s_m / n + mdm[i]
        pdi, mdi = 100 * s_p / s_tr, 100 * s_m / s_tr
        dx[i] = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0
    out = [math.nan] * size
    first = 2 * n - 1
    out[first] = sum(dx[i] for i in range(n, 2 * n)) / n
    for i in range(first + 1, size):
        out[i] = (out[i - 1] * (n - 1) + dx[i]) / n
    return out


def assert_series_close(testcase, got: pd.Series, want, tol=TOL):
    got = got.to_numpy(dtype=float)
    want = np.asarray(want, dtype=float)
    testcase.assertEqual(len(got), len(want))
    testcase.assertTrue(
        np.array_equal(np.isnan(got), np.isnan(want)),
        f"NaN positions differ: {np.flatnonzero(np.isnan(got))} vs {np.flatnonzero(np.isnan(want))}",
    )
    mask = ~np.isnan(want)
    np.testing.assert_allclose(got[mask], want[mask], rtol=0, atol=tol)


class MovingAverageTests(unittest.TestCase):
    def setUp(self):
        self.close = pd.Series(CLOSES)

    def test_ema_hand_values(self):
        # span 3 -> alpha 0.5, seeded with the first value
        got = ind.ema(pd.Series([1.0, 2.0, 3.0, 4.0]), 3)
        np.testing.assert_allclose(got, [1.0, 1.5, 2.25, 3.125], atol=1e-12)

    def test_ema_matches_reference_for_several_lengths(self):
        for n in (3, 5, 12, 26):
            with self.subTest(n=n):
                assert_series_close(self, ind.ema(self.close, n), ref_ema(CLOSES, n))

    def test_dema_matches_reference(self):
        for n in (3, 8, 14):
            with self.subTest(n=n):
                assert_series_close(self, ind.dema(self.close, n), ref_dema(CLOSES, n))

    def test_tema_matches_reference(self):
        for n in (3, 8, 14):
            with self.subTest(n=n):
                assert_series_close(self, ind.tema(self.close, n), ref_tema(CLOSES, n))

    def test_all_three_are_exact_on_a_constant_series(self):
        flat = pd.Series([7.5] * 30)
        for fn in (ind.ema, ind.dema, ind.tema):
            np.testing.assert_allclose(fn(flat, 9), 7.5, atol=1e-12)

    def test_dema_and_tema_track_a_trend_with_less_lag_than_ema(self):
        trend = pd.Series(np.arange(100, dtype=float))
        e, d, t = ind.ema(trend, 10).iloc[-1], ind.dema(trend, 10).iloc[-1], ind.tema(trend, 10).iloc[-1]
        # on a straight line the EMA lags by (n-1)/2 = 4.5 bars; DEMA/TEMA remove it
        self.assertGreater(99 - e, 4.0)
        self.assertLess(abs(99 - d), 0.01)
        self.assertLess(abs(99 - t), 0.01)

    def test_invalid_length_is_rejected(self):
        with self.assertRaises(ValueError):
            ind.ema(self.close, 0)

    def test_does_not_use_future_bars(self):
        full = ind.tema(self.close, 6)
        for cut in (10, 20, 35):
            partial = ind.tema(self.close.iloc[:cut], 6)
            np.testing.assert_allclose(partial, full.iloc[:cut], atol=1e-12)


class AtrTests(unittest.TestCase):
    def setUp(self):
        self.h, self.l, self.c = pd.Series(HIGHS), pd.Series(LOWS), pd.Series(CLOSES)

    def test_atr_hand_computed(self):
        # n=3 on four bars: TR = [2.0, max(2,|11-9|,|9-9|)=2.0... computed by hand below
        h = pd.Series([10.0, 12.0, 11.0, 13.0])
        l = pd.Series([8.0, 9.0, 9.5, 10.0])
        c = pd.Series([9.0, 11.0, 10.0, 12.0])
        # TR0 = 10-8 = 2 ; TR1 = max(3, |12-9|, |9-9|) = 3 ; TR2 = max(1.5, |11-11|, |9.5-11|) = 1.5
        # TR3 = max(3, |13-10|, |10-10|) = 3 ; ATR2 = (2+3+1.5)/3 ; ATR3 = (ATR2*2 + 3)/3
        atr2 = (2 + 3 + 1.5) / 3
        got = ind.atr(h, l, c, 3)
        self.assertTrue(np.isnan(got.iloc[0]) and np.isnan(got.iloc[1]))
        self.assertAlmostEqual(got.iloc[2], atr2, places=12)
        self.assertAlmostEqual(got.iloc[3], (atr2 * 2 + 3) / 3, places=12)

    def test_atr_matches_reference(self):
        for n in (3, 7, 14):
            with self.subTest(n=n):
                assert_series_close(self, ind.atr(self.h, self.l, self.c, n), ref_atr(HIGHS, LOWS, CLOSES, n))

    def test_true_range_uses_the_gap_to_the_previous_close(self):
        h = pd.Series([10.0, 20.0]); l = pd.Series([9.0, 19.0]); c = pd.Series([9.5, 19.5])
        tr = ind.true_range(h, l, c)
        self.assertEqual(tr.iloc[0], 1.0)
        self.assertAlmostEqual(tr.iloc[1], 10.5)  # |20 - 9.5|, not the 1.0 bar range

    def test_atr_is_nan_before_n_bars(self):
        got = ind.atr(self.h, self.l, self.c, 14)
        self.assertEqual(int(got.isna().sum()), 13)


class AdxTests(unittest.TestCase):
    def setUp(self):
        self.h, self.l, self.c = pd.Series(HIGHS), pd.Series(LOWS), pd.Series(CLOSES)

    def test_adx_matches_reference(self):
        for n in (3, 5, 10, 14):
            with self.subTest(n=n):
                assert_series_close(self, ind.adx(self.h, self.l, self.c, n), ref_adx(HIGHS, LOWS, CLOSES, n))

    def test_adx_warmup_is_two_n_minus_one_bars(self):
        got = ind.adx(self.h, self.l, self.c, 10)
        self.assertEqual(int(got.isna().sum()), 2 * 10 - 1)

    def test_adx_is_bounded(self):
        got = ind.adx(self.h, self.l, self.c, 7).dropna()
        self.assertTrue(((got >= 0) & (got <= 100)).all())

    def test_a_clean_trend_has_a_high_adx_and_noise_a_low_one(self):
        n = 120
        up = pd.Series(np.arange(n, dtype=float) + 100)
        trend = ind.adx(up + 0.5, up - 0.5, up, 14).iloc[-1]
        rng = np.random.default_rng(7)  # synthetic noise: only used to compare against a trend
        noise = pd.Series(100 + rng.normal(0, 1, n))
        chop = ind.adx(noise + 0.5, noise - 0.5, noise, 14).iloc[-1]
        self.assertGreater(trend, 80)
        self.assertLess(chop, trend)

    def test_does_not_use_future_bars(self):
        full = ind.adx(self.h, self.l, self.c, 5)
        for cut in (15, 25, 38):
            partial = ind.adx(self.h.iloc[:cut], self.l.iloc[:cut], self.c.iloc[:cut], 5)
            a, b = partial.to_numpy(), full.iloc[:cut].to_numpy()
            self.assertTrue(np.allclose(a, b, equal_nan=True, atol=1e-12))


if __name__ == "__main__":
    unittest.main()
