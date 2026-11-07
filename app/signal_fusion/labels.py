"""
M, the strategy's profit, its payoff model and the expected value (FDS-SIG-004 sections
5.3 and 5.8.1).

**Opportunities** come from the backtester's own logic per coin
(``backtest.engine.run_backtest`` with no costs, so its fills are the raw opens): a signal
on bar t's close fills at bar t + 1's open, and the trade exits on the strategy's own EXIT,
at the next open. A trade still open when the bars end is closed there by the backtester
(``forced``): its true exit is unknown, so it is never a training label.

**Gross return:** r_g = P_exit / P_entry - 1, from the raw opens, before slippage and fees.
**Net return:** with fee f a side and allowance e a fill, the backtester's accounting gives
exactly net = (1 + r_g) m(f, e) - 1, m(f, e) = (1 - f)^2 (1 - e) / (1 + e).

**M = 1** when net > 0 at the evaluated fee f0 and e0 = 0.05%, that is r_g > 1 / m(f0, e0) - 1.
The strategy's key, parameters, timeframe and overlays are part of M's definition.

**The payoff model** (``Payoffs``), gross, from the same strategy's training trades:
W_g(τ), the mean r_g of trades with M = 1 in volatility tercile τ, and Λ_g(τ), that of
trades with M = 0. A cell with fewer than 30 trades pools over terciles.

**Expected value** at the decision's own costs: μ̂_g = p̂ W_g(τ) + (1 - p̂) Λ_g(τ) and
EV = (1 + μ̂_g) m(f, e) - 1; the veto acts when EV <= 0. The costs enter once, through m:
p̂ and the payoff means describe gross returns, and the evaluated fee only sets where M is
cut. T1, whose barrier already holds the fees, never enters an expected value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

STRATEGY = "STRAT-001"
EVALUATED_ALLOWANCE = 0.0005
MIN_CELL = 30


def multiplier(fee: float, allowance: float) -> float:
    """m(f, e)."""
    return (1.0 - fee) ** 2 * (1.0 - allowance) / (1.0 + allowance)


def net_return(gross, fee: float, allowance: float):
    return (1.0 + np.asarray(gross, dtype=float)) * multiplier(fee, allowance) - 1.0


def break_even(fee: float, allowance: float) -> float:
    """The gross return at which the net return is 0."""
    return 1.0 / multiplier(fee, allowance) - 1.0


def m_label(gross, fee: float, allowance: float = EVALUATED_ALLOWANCE) -> np.ndarray:
    """M: 1 when the trade's net return at (fee, allowance) is above 0."""
    return (net_return(gross, fee, allowance) > 0).astype(int)


@dataclass(frozen=True)
class Trade:
    coin: str
    signal_s: int  # the signal bar's close: the decision hour (= the entry fill time)
    exit_s: int  # the exit fill time
    entry_price: float  # raw
    exit_price: float  # raw
    forced: bool  # closed only because the bars ended

    @property
    def gross(self) -> float:
        return self.exit_price / self.entry_price - 1.0


def strategy_config(params: Optional[Dict[str, Any]] = None, timeframe: str = "1h"):
    """The configuration M belongs to: the strategy, its parameters, timeframe and
    overlays (none)."""
    from strategies.catalogue import get_entry

    defaults = dict(get_entry(STRATEGY)["default_params"])
    return {
        "strategy": STRATEGY,
        "params": {**defaults, **(params or {})},
        "timeframe": timeframe,
        "overlays": [],
    }


def opportunities(
    candles, coin: str, params: Optional[Dict[str, Any]] = None
) -> List[Trade]:
    """The strategy's trades on one coin's 1-hour candles (a frame with open_time, open,
    high, low, close, volume), from the backtester with no costs."""
    from backtest.engine import CostModel, run_backtest
    from strategies import create
    from strategies.runner import StrategyRunner

    config = strategy_config(params)
    runner = StrategyRunner(create(STRATEGY, **config["params"]))
    zero = CostModel(fee_bps=0.0, slippage_bps=0.0, size_fraction=1.0)
    result = run_backtest(candles, runner, coin, "1h", cost=zero)
    return [
        Trade(
            coin,
            int(t.entry_time.timestamp()),
            int(t.exit_time.timestamp()),
            float(t.entry_price),
            float(t.exit_price),
            bool(t.forced_close),
        )
        for t in result.trades
    ]


@dataclass(frozen=True)
class Payoffs:
    """W_g and Λ_g per volatility tercile (index 0 to 2), and the pooled means."""

    win: Tuple[float, float, float]
    loss: Tuple[float, float, float]
    pooled: Tuple[float, float]
    counts: Tuple[Tuple[int, int], ...]

    def at(self, tercile: int) -> Tuple[float, float]:
        if 0 <= tercile <= 2:
            return self.win[tercile], self.loss[tercile]
        return self.pooled

    def to_dict(self) -> Dict[str, Any]:
        return {
            "win": list(self.win),
            "loss": list(self.loss),
            "pooled": list(self.pooled),
            "counts": [list(c) for c in self.counts],
        }


def payoffs(gross, label, tercile) -> Payoffs:
    """The payoff tables from training trades (gross returns, M, σ̂ terciles)."""
    g = np.asarray(gross, dtype=float)
    m = np.asarray(label, dtype=int)
    t = np.asarray(tercile, dtype=int)
    pooled_w = float(g[m == 1].mean()) if np.any(m == 1) else 0.0
    pooled_l = float(g[m == 0].mean()) if np.any(m == 0) else 0.0
    wins, losses, counts = [], [], []
    for k in range(3):
        w = g[(t == k) & (m == 1)]
        lo = g[(t == k) & (m == 0)]
        counts.append((int(len(w)), int(len(lo))))
        wins.append(float(w.mean()) if len(w) >= MIN_CELL else pooled_w)
        losses.append(float(lo.mean()) if len(lo) >= MIN_CELL else pooled_l)
    return Payoffs(tuple(wins), tuple(losses), (pooled_w, pooled_l), tuple(counts))


def expected_value(p, win, loss, fee: float, allowance: float):
    """EV = (1 + p W + (1 - p) Λ) m(f, e) - 1."""
    p = np.asarray(p, dtype=float)
    mu = p * np.asarray(win, dtype=float) + (1.0 - p) * np.asarray(loss, dtype=float)
    return (1.0 + mu) * multiplier(fee, allowance) - 1.0


def decision_allowance(
    live_spread: Optional[float], floor: float = EVALUATED_ALLOWANCE
):
    """e = max(half the live spread, 0.05%): the spread and the allowance are never both
    charged (section 5.7)."""
    if live_spread is None or not np.isfinite(live_spread):
        return floor
    return max(0.5 * float(live_spread), floor)


def payoff_calibration(ev_pred, net_real, groups: int = 5) -> List[Dict[str, float]]:
    """Realised mean net return by EV quintile against the mean predicted EV (shown, not
    deciding)."""
    ev = np.asarray(ev_pred, dtype=float)
    real = np.asarray(net_real, dtype=float)
    order = np.argsort(ev, kind="stable")
    out = []
    for part in np.array_split(order, groups):
        if len(part):
            out.append(
                {
                    "trades": int(len(part)),
                    "predicted": float(ev[part].mean()),
                    "realised": float(real[part].mean()),
                }
            )
    return out


def label_rows(trades: Sequence[Trade], fee: float) -> Tuple[np.ndarray, np.ndarray]:
    """(gross, M) for each trade; forced trades get M = -1 (never a label)."""
    g = np.array([t.gross for t in trades], dtype=float)
    m = m_label(g, fee)
    forced = np.array([t.forced for t in trades], dtype=bool)
    return g, np.where(forced, -1, m)
