"""KPI set (FDS-121 section 6). Undefined values are ``None`` (JSON null), never 0."""

from __future__ import annotations

import math
from typing import Dict, Optional, Sequence

import numpy as np

SECONDS_PER_YEAR = 365.25 * 24 * 3600

KPI_KEYS = (
    "total_return_pct",
    "cagr_pct",
    "max_drawdown_pct",
    "sharpe",
    "sortino",
    "trade_count",
    "win_rate_pct",
    "avg_trade_pct",
    "exposure_pct",
    "fees_paid",
    "vs_buy_hold_pct",
)


def _num(x: float) -> Optional[float]:
    return None if x is None or not math.isfinite(x) else float(x)


def compute_kpis(
    equity: Sequence[float],
    initial_equity: float,
    tf_seconds: int,
    trade_returns_pct: Sequence[float],
    bars_in_position: int,
    fees_paid: float,
) -> Dict[str, Optional[float]]:
    """
    ``equity`` is the per-bar mark-to-market curve (one value per bar close) and
    the base for returns is ``initial_equity`` (the capital before the first bar).

    * Sharpe / Sortino: per-bar returns, annualised with ``sqrt(bars_per_year)``,
      risk-free rate 0. Sortino uses the root-mean-square of negative returns.
    * CAGR: from the window length in calendar time.
    * exposure: share of bars holding a position at the bar close.
    """
    eq = np.asarray([float(initial_equity)] + [float(x) for x in equity], dtype=float)
    n_bars = len(eq) - 1
    out: Dict[str, Optional[float]] = {k: None for k in KPI_KEYS}
    out["trade_count"] = len(trade_returns_pct)
    out["fees_paid"] = _num(fees_paid)
    if n_bars < 1:
        return out

    final = eq[-1]
    out["total_return_pct"] = _num((final / initial_equity - 1.0) * 100.0)

    years = n_bars * tf_seconds / SECONDS_PER_YEAR
    if years > 0 and final > 0 and initial_equity > 0:
        out["cagr_pct"] = _num(
            ((final / initial_equity) ** (1.0 / years) - 1.0) * 100.0
        )

    peaks = np.maximum.accumulate(eq)
    out["max_drawdown_pct"] = _num(float(np.min(eq / peaks - 1.0)) * 100.0)

    rets = eq[1:] / eq[:-1] - 1.0
    bars_per_year = SECONDS_PER_YEAR / tf_seconds
    if len(rets) >= 2:
        std = float(np.std(rets, ddof=1))
        if std > 0:
            out["sharpe"] = _num(float(np.mean(rets)) / std * math.sqrt(bars_per_year))
        downside = float(np.sqrt(np.mean(np.minimum(rets, 0.0) ** 2)))
        if downside > 0:
            out["sortino"] = _num(
                float(np.mean(rets)) / downside * math.sqrt(bars_per_year)
            )

    if trade_returns_pct:
        wins = sum(1 for r in trade_returns_pct if r > 0)
        out["win_rate_pct"] = _num(100.0 * wins / len(trade_returns_pct))
        out["avg_trade_pct"] = _num(float(np.mean(trade_returns_pct)))
    out["exposure_pct"] = _num(100.0 * bars_in_position / n_bars)
    return out
