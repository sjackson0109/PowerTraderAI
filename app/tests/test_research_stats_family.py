"""The programme's one statistics module (PTAI-RD-001 WP 2.3): multiple testing,
overfitting and power, each checked on synthetic null data and on known skill.

* The shared versions agree exactly with the lab-specific copies that frozen records
  used (Holm, Benjamini-Hochberg, the resampling p-value, PBO, the smallest edge).
* Null fixtures: Holm and Romano-Wolf keep the family-wise error near alpha with
  correlated members; the best of 20 skill-less Sharpe ratios is rarely "significant"
  once deflated (and often is before); PBO is near 0.5 without skill.
* Skill fixtures: Romano-Wolf finds the skilled members, at least as often as Holm when
  members are correlated; PBO is near 0 with one reliably better member; a real Sharpe
  ratio survives deflation; a test at the minimum detectable effect has its power.

Seeded simulations; the limits allow three Monte Carlo standard errors."""

from __future__ import annotations

import math

import numpy as np
import pytest

from model_lab import stats as mls
from research_stats import multiple, overfitting, power
from signal_audit import stats as sas


def mc_limit(p: float, reps: int) -> float:
    return p + 3 * math.sqrt(p * (1 - p) / reps)


# --- agreement with the lab copies ------------------------------------------------------


def test_the_shared_tests_agree_with_the_lab_copies():
    rng = np.random.default_rng(1)
    for _ in range(200):
        k = int(rng.integers(1, 13))
        ps = list(np.round(rng.uniform(0, 0.2, k), 3))  # rounding makes ties
        assert multiple.holm_adjusted(ps) == sas.holm_adjusted(ps)
        assert multiple.holm(ps, 0.05) == mls.holm(ps, 0.05)
        assert multiple.benjamini_hochberg(ps, 0.1) == mls.benjamini_hochberg(ps, 0.1)
        draws = list(rng.normal(size=50))
        assert multiple.p_upper(0.3, draws) == pytest.approx(mls.p_upper(0.3, draws))


def test_pbo_agrees_with_the_model_lab_copy():
    rng = np.random.default_rng(2)
    for _ in range(20):
        net = rng.normal(size=(5, 6))
        held = rng.uniform(0, 3, size=(5, 6))
        held[rng.integers(0, 5), rng.integers(0, 6)] = 0.0
        assert overfitting.pbo(net, held) == mls.pbo(net, held)


def test_the_smallest_edge_agrees_with_the_model_lab_copy():
    for k in (1, 4, 20):
        assert power.minimum_detectable(0.7, 0.05 / k, 0.8) == pytest.approx(
            mls.smallest_edge(0.7, k, 0.05, 0.8)
        )


# --- multiple testing -------------------------------------------------------------------


def correlated(rng, n, k, rho, shift):
    common = rng.normal(size=(n, 1))
    own = rng.normal(size=(n, k))
    return math.sqrt(rho) * common + math.sqrt(1 - rho) * own + shift


def t_stats(x):
    return x.mean(axis=0) / x.std(axis=0, ddof=1) * math.sqrt(len(x))


def family(rng, x, draws=199):
    """Each member's t-statistic, its bootstrap draws (rows resampled together) and
    its own bootstrap p-value."""
    t = t_stats(x)
    idx = rng.integers(0, len(x), size=(draws, len(x)))
    boot = np.stack([t_stats(x[i]) for i in idx])
    null = boot - t
    ps = [(1 + np.sum(null[:, j] >= t[j])) / (draws + 1) for j in range(len(t))]
    return t, boot, ps


def test_no_skill_rarely_gives_any_rejection():
    rng = np.random.default_rng(3)
    reps, alpha = 200, 0.05
    rw_any = holm_any = 0
    for _ in range(reps):
        x = correlated(rng, 120, 8, 0.6, np.zeros(8))
        t, boot, ps = family(rng, x)
        rw_any += min(multiple.romano_wolf(t, boot)) <= alpha
        holm_any += any(multiple.holm(ps, alpha))
    assert rw_any / reps <= mc_limit(alpha, reps)
    assert holm_any / reps <= mc_limit(alpha, reps)


def test_romano_wolf_finds_skill_and_uses_the_correlation():
    rng = np.random.default_rng(4)
    shift = np.array([0.25, 0.25, 0.25, 0, 0, 0, 0, 0])
    reps, alpha = 100, 0.05
    rw_found = holm_found = false = 0
    for _ in range(reps):
        x = correlated(rng, 120, 8, 0.8, shift)
        t, boot, ps = family(rng, x)
        rw = [p <= alpha for p in multiple.romano_wolf(t, boot)]
        holm = multiple.holm(ps, alpha)
        rw_found += sum(rw[:3])
        holm_found += sum(holm[:3])
        false += any(rw[3:])
    assert rw_found / (3 * reps) > 0.5
    assert rw_found >= holm_found
    assert false / reps <= mc_limit(alpha, reps)


def test_romano_wolf_p_values_never_fall_down_the_steps():
    rng = np.random.default_rng(5)
    t = np.array([3.0, 0.5, 2.0])
    boot = t + rng.normal(size=(99, 3))
    adj = multiple.romano_wolf(t, boot)
    by_t = [adj[i] for i in np.argsort(-t)]
    assert by_t == sorted(by_t)
    with pytest.raises(ValueError, match="resamples, members"):
        multiple.romano_wolf(t, boot[:, :2])


# --- overfitting ------------------------------------------------------------------------


def test_the_expected_best_sharpe_grows_with_the_trials():
    assert overfitting.expected_max_sharpe(1.0, 1) == 0.0
    assert overfitting.expected_max_sharpe(1.0, 10) == pytest.approx(1.5745, abs=1e-3)
    values = [overfitting.expected_max_sharpe(0.01, n) for n in (2, 10, 100, 1000)]
    assert values == sorted(values)
    assert overfitting.probabilistic_sharpe(0.0, 100) == pytest.approx(0.5)


def test_the_best_of_many_skill_less_trials_is_deflated():
    rng = np.random.default_rng(6)
    reps = 200
    deflated = naive = 0
    for _ in range(reps):
        trials = rng.normal(size=(20, 250))
        sharpes = [overfitting.sharpe(r) for r in trials]
        best = trials[int(np.argmax(sharpes))]
        deflated += overfitting.deflated_sharpe(best, sharpes) > 0.95
        naive += overfitting.probabilistic_sharpe(max(sharpes), 250) > 0.95
    assert deflated / reps <= mc_limit(0.05, reps)
    assert naive / reps > 0.3  # without deflation the best of 20 often "passes"


def test_a_real_sharpe_ratio_survives_deflation():
    rng = np.random.default_rng(7)
    reps = 100
    kept = 0
    for _ in range(reps):
        trials = rng.normal(size=(20, 250))
        # one trial with a per-day Sharpe ratio of 0.4: its own ratio widens the
        # spread across trials and so raises the bar it must clear (at 0.3 it clears
        # it about two times in three)
        trials[0] += 0.4
        sharpes = [overfitting.sharpe(r) for r in trials]
        kept += overfitting.deflated_sharpe(trials[0], sharpes) > 0.95
    assert kept / reps > 0.8


def test_pbo_is_near_a_half_without_skill_and_near_zero_with_it():
    rng = np.random.default_rng(8)
    noise = [overfitting.pbo(rng.normal(size=(10, 8))) for _ in range(30)]
    assert 0.35 <= float(np.mean(noise)) <= 0.65
    skilled = []
    for _ in range(30):
        values = rng.normal(size=(10, 8))
        values[3] += 2.0
        skilled.append(overfitting.pbo(values))
    assert float(np.mean(skilled)) < 0.1
    assert overfitting.pbo([[1.0, 2.0]]) is None


# --- power and verdicts -----------------------------------------------------------------


@pytest.mark.parametrize("sides", [1, 2])
def test_the_minimum_detectable_effect_has_its_power(sides):
    mde = power.minimum_detectable(0.1, 0.05, 0.8, sides)
    assert power.power_at(mde, 0.1, 0.05, sides) == pytest.approx(0.8, abs=1e-3)
    assert power.power_at(0.0, 0.1, 0.05, sides) == pytest.approx(0.05)


def test_a_simulated_test_at_the_minimum_detectable_effect_has_its_power():
    rng = np.random.default_rng(9)
    n, reps = 100, 4000
    se = 1 / math.sqrt(n)
    mde = power.minimum_detectable(se)
    z = rng.normal(mde, 1.0, size=(reps, n)).mean(axis=1) / se
    found = float(np.mean(z > 1.6448536269514722))
    assert found == pytest.approx(0.8, abs=0.02)


def test_the_observations_needed_are_the_fewest_that_reach_the_power():
    n = power.observations_needed(0.05, 1.0)
    assert power.minimum_detectable(1 / math.sqrt(n)) <= 0.05
    assert power.minimum_detectable(1 / math.sqrt(n - 1)) > 0.05


def test_the_three_verdicts():
    assert power.verdict(0.3, 0.1, 0.001, 0.05, 0.1) == power.DETECTED
    # not significant, and an edge of 0.1 is ruled out: the bound is 0.0 + 0.0164
    assert power.verdict(0.0, 0.01, 0.5, 0.05, 0.1) == power.BELOW_SMALLEST
    # not significant, and too noisy to rule out 0.1: the data cannot tell
    assert power.verdict(0.0, 0.2, 0.5, 0.05, 0.1) == power.INCONCLUSIVE
    with pytest.raises(ValueError):
        power.minimum_detectable(0.1, alpha=1.5)
