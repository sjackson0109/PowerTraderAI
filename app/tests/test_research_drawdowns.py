"""Drawdowns and recovery from an equity curve (PTAI-RD-001 WP 2.6), on hand-computed
curves.

* Each spell below a previous high: its depth, its low, when the curve got back to the
  high (equal counts), its days to recover and under water; a spell still open at the
  end has no recovery and runs to the curve's end.
* The report: the deepest and the longest spell, how many, and the share of the time
  spent under water."""

from __future__ import annotations

import pytest

from research_stats import drawdowns

D = 86_400.0


def days(values):
    return [i * D for i in range(len(values))], list(values)


def test_each_spell_below_a_previous_high():
    times, equity = days([100, 120, 90, 110, 120, 130, 117])
    found = drawdowns.spells(times, equity)
    assert [(s["high"], s["low"], s["recovered_s"]) for s in found] == [
        (120, 90, 4 * D),
        (130, 117, None),
    ]
    first, last = found
    assert first["depth"] == pytest.approx(0.25)
    assert first["days_to_recover"] == pytest.approx(2.0)  # low on day 2, back on 4
    assert first["days_under_water"] == pytest.approx(3.0)  # high on day 1
    assert last["depth"] == pytest.approx(0.10)
    assert last["days_to_recover"] is None
    assert last["days_under_water"] == pytest.approx(1.0)  # to the curve's end


def test_the_report_names_the_deepest_and_the_longest():
    times, equity = days([100, 80, 100, 130, 125, 120, 121, 122, 129])
    out = drawdowns.report(times, equity)
    assert out["spells"] == 2
    assert out["max_drawdown"] == pytest.approx(0.20)
    assert out["deepest"]["depth"] == pytest.approx(0.20)
    assert out["deepest"]["recovered_at"] == "1970-01-03T00:00:00+00:00"
    longest = out["longest"]
    assert longest["high"] == 130 and longest["recovered_at"] is None
    assert longest["days_under_water"] == pytest.approx(5.0)
    assert out["share_under_water"] == pytest.approx((2 + 5) / 8)


def test_a_curve_that_never_falls_has_no_spell():
    times, equity = days([100, 100, 101, 105])
    out = drawdowns.report(times, equity)
    assert out == {
        "max_drawdown": 0.0,
        "deepest": None,
        "longest": None,
        "spells": 0,
        "share_under_water": 0.0,
    }
    assert drawdowns.report([0.0], [100.0])["share_under_water"] is None
    assert drawdowns.report([], [])["spells"] == 0


def test_a_wrong_curve_is_refused():
    with pytest.raises(ValueError, match="same length"):
        drawdowns.spells([0.0, 1.0], [1.0])
