"""Returns by calendar period (PTAI-RD-001 WP 2.6), on hand-computed curves.

* Each UTC day, ISO week (Monday to Sunday), month and year: its last equity over the
  previous one's, the first over the curve's start; a period the curve does not cover
  from start to end is not whole and stays out of the summary.
* The summary over whole periods; the compound annual growth; the years at or above
  the 10% objective, counted and never passed or failed.
* An exploratory backtest's record carries the report."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from research_stats import periods

H = 3600.0
D = 86_400.0


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


def hourly(start, values_per_day):
    """24 hourly marks a day, each day's marks all at that day's value."""
    t0 = at(start)
    times, equity = [], []
    for d, value in enumerate(values_per_day):
        for h in range(24):
            times.append(t0 + d * D + h * H)
            equity.append(value)
    return times, equity


def test_daily_returns_are_each_days_last_over_the_one_before():
    times, equity = hourly("2024-01-01", [100.0, 110.0, 99.0])
    rows = periods.period_returns(times, equity, "day")
    assert [r["period"] for r in rows] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert [r["return"] for r in rows] == pytest.approx([0.0, 0.10, -0.10])
    assert all(r["whole"] for r in rows)


def test_weeks_are_iso_weeks_from_monday_and_a_part_week_is_not_whole():
    # Monday 2024-01-01 to Wednesday 2024-01-10: one whole week, and part of the next
    values = [100.0] * 7 + [120.0, 120.0, 90.0]
    times, equity = hourly("2024-01-01", values)
    rows = periods.period_returns(times, equity, "week")
    assert [(r["period"], r["whole"]) for r in rows] == [
        ("2024-W01", True),
        ("2024-W02", False),
    ]
    assert rows[1]["return"] == pytest.approx(-0.10)
    s = periods.summary(rows)
    assert s["whole_periods"] == 1 and s["mean"] == pytest.approx(0.0)


def test_months_start_part_way_are_not_whole():
    days = (datetime(2024, 3, 1) - datetime(2023, 12, 15)).days  # to 29 February
    values = [100.0 + i for i in range(days)]
    times, equity = hourly("2023-12-15", values)
    rows = periods.period_returns(times, equity, "month")
    assert [(r["period"], r["whole"]) for r in rows] == [
        ("2023-12", False),
        ("2024-01", True),
        ("2024-02", True),
    ]
    dec_end, jan_end, feb_end = 100.0 + 16, 100.0 + 16 + 31, 100.0 + 16 + 31 + 29
    assert rows[1]["return"] == pytest.approx(jan_end / dec_end - 1)
    assert rows[2]["return"] == pytest.approx(feb_end / jan_end - 1)


def test_the_years_and_the_objective_are_counted_not_passed():
    # three whole years: +20%, +5%, +10%, by daily marks on each year's last day
    times, equity = [], []
    for year, value in ((2021, 120.0), (2022, 126.0), (2023, 138.6)):
        times.append(at(f"{year}-01-01"))
        equity.append(equity[-1] if equity else 100.0)
        times.append(at(f"{year}-12-31") + 23 * H)
        equity.append(value)
    out = periods.report(times, equity)
    years = out["year"]["returns"]
    assert [r["return"] for r in years] == pytest.approx([0.20, 0.05, 0.10])
    assert out["target_annual"] == {
        "target": 0.10,
        "whole_years": 3,
        "years_at_or_above": 2,
    }
    assert out["year"]["summary"]["best"] == pytest.approx(0.20)
    span_years = (times[-1] - times[0]) / (365.25 * D)
    assert out["annual_growth"] == pytest.approx(1.386 ** (1 / span_years) - 1)


def test_no_whole_period_gives_no_figures():
    times, equity = [at("2024-01-01") + 12 * H], [100.0]
    rows = periods.period_returns(times, equity, "month")
    assert rows[0]["whole"] is False
    assert periods.summary(rows) == {
        "whole_periods": 0,
        "mean": None,
        "median": None,
        "share_above_zero": None,
        "best": None,
        "worst": None,
    }
    assert periods.annual_growth(times, equity) is None


def test_a_wrong_period_or_curve_is_refused():
    with pytest.raises(ValueError, match="period must be one of"):
        periods.period_returns([0.0], [1.0], "quarter")
    with pytest.raises(ValueError, match="same length"):
        periods.period_returns([0.0, 1.0], [1.0], "day")


def test_a_backtest_record_carries_the_report(lab):  # noqa: F811
    from test_strategy_backtest_window import config, loader, venue

    from strategy_lab import runs

    record = runs.run(config(), loader=loader, venue=venue, now=1_800_000_000)
    assert set(record["periods"]) == set(periods.PERIODS) | {
        "annual_growth",
        "target_annual",
    }
    days = record["periods"]["day"]["returns"]
    assert days and days[-1]["end_equity"] == pytest.approx(
        record["strategy_result"]["final_equity"]
    )


from test_strategy_backtest_window import lab  # noqa: E402,F401
