"""
Returns by calendar period, from an equity curve (PTAI-RD-001 work package 2.6).

The programme brief asks for daily, weekly, monthly and annual returns, each reported
separately, and for its 10% target to be shown as a research objective, never as a pass
mark.

* ``period_returns(times_s, equity, period)``: each UTC calendar period's return, its
  last equity over the previous period's last (the first period's over the curve's
  first value), and whether the period is whole: the curve starts at or before the
  period's start and reaches its last mark. Periods: ``day``, ``week`` (ISO, Monday to
  Sunday), ``month`` and ``year``. A period with no mark is not listed; the next
  period's return then covers it.
* ``summary(rows)``: over whole periods only: how many, mean, median, the share above
  zero, best and worst. None of these exist with no whole period.
* ``report(times_s, equity)``: each period's rows and summary, the compound annual
  growth over the whole curve, and how many whole years reached ``TARGET_ANNUAL``.

Only the equity curve is used: the figures are after the costs the curve already holds.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

PERIODS = ("day", "week", "month", "year")
TARGET_ANNUAL = 0.10  # the brief's objective: reported against, never passed or failed
YEAR_DAYS = 365.25


def _start_of(day: date, period: str) -> date:
    if period == "day":
        return day
    if period == "week":
        return day - timedelta(days=day.weekday())  # ISO weeks start on Monday
    if period == "month":
        return day.replace(day=1)
    if period == "year":
        return day.replace(month=1, day=1)
    raise ValueError(f"period must be one of {PERIODS}, not {period!r}")


def _next(start: date, period: str) -> date:
    if period == "day":
        return start + timedelta(days=1)
    if period == "week":
        return start + timedelta(days=7)
    if period == "month":
        return (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start.replace(year=start.year + 1)


def _label(start: date, period: str) -> str:
    if period == "week":
        year, week, _ = start.isocalendar()
        return f"{year}-W{week:02d}"
    if period == "month":
        return start.strftime("%Y-%m")
    if period == "year":
        return str(start.year)
    return start.isoformat()


def _seconds(day: date) -> float:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp()


def period_returns(
    times_s: Sequence[float], equity: Sequence[float], period: str
) -> List[Dict[str, Any]]:
    """Each ``period``'s return (module docstring), oldest first."""
    t = np.asarray(times_s, dtype=float)
    e = np.asarray(equity, dtype=float)
    if len(t) != len(e):
        raise ValueError("times and equity must be the same length")
    if not len(t):
        return []
    step = float(np.median(np.diff(t))) if len(t) > 1 else 0.0
    groups: Dict[date, Tuple[int, int]] = {}
    order: List[date] = []
    for i, ts in enumerate(t):
        start = _start_of(datetime.fromtimestamp(ts, tz=timezone.utc).date(), period)
        if start not in groups:
            groups[start] = (i, i)
            order.append(start)
        else:
            groups[start] = (groups[start][0], i)
    rows: List[Dict[str, Any]] = []
    previous = e[0]
    for start in order:
        first, last = groups[start]
        end_s = _seconds(_next(start, period))
        whole = t[0] <= _seconds(start) and t[-1] + step >= end_s
        value = float(e[last])
        rows.append(
            {
                "period": _label(start, period),
                "start_equity": float(previous),
                "end_equity": value,
                "return": (value / previous - 1.0) if previous > 0 else None,
                "whole": bool(whole),
            }
        )
        previous = value
    return rows


def summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Over whole periods with a return: count, mean, median, share above zero, best,
    worst (None for each but the count when there is none)."""
    r = np.array(
        [x["return"] for x in rows if x["whole"] and x["return"] is not None],
        dtype=float,
    )
    if not len(r):
        return {
            "whole_periods": 0,
            "mean": None,
            "median": None,
            "share_above_zero": None,
            "best": None,
            "worst": None,
        }
    return {
        "whole_periods": int(len(r)),
        "mean": float(r.mean()),
        "median": float(np.median(r)),
        "share_above_zero": float(np.mean(r > 0)),
        "best": float(r.max()),
        "worst": float(r.min()),
    }


def annual_growth(times_s: Sequence[float], equity: Sequence[float]) -> Optional[float]:
    """The compound annual growth over the whole curve, or None (no time, or no
    positive start)."""
    t = np.asarray(times_s, dtype=float)
    e = np.asarray(equity, dtype=float)
    if len(t) < 2 or e[0] <= 0 or e[-1] <= 0:
        return None
    years = (t[-1] - t[0]) / (YEAR_DAYS * 86_400.0)
    if years <= 0:
        return None
    return float((e[-1] / e[0]) ** (1.0 / years) - 1.0)


def report(
    times_s: Sequence[float],
    equity: Sequence[float],
    target: float = TARGET_ANNUAL,
) -> Dict[str, Any]:
    """Every period's returns and summary, the compound annual growth, and the whole
    years at or above ``target`` (an objective reported against, not a pass mark)."""
    out: Dict[str, Any] = {}
    for period in PERIODS:
        rows = period_returns(times_s, equity, period)
        out[period] = {"returns": rows, "summary": summary(rows)}
    years = [
        x for x in out["year"]["returns"] if x["whole"] and x["return"] is not None
    ]
    out["annual_growth"] = annual_growth(times_s, equity)
    out["target_annual"] = {
        "target": float(target),
        "whole_years": len(years),
        # a year that made the target exactly counts, whatever the rounding
        "years_at_or_above": sum(1 for x in years if x["return"] >= target - 1e-12),
    }
    return out
