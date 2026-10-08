"""
Honest backtester (FDS-121 section 6).

Honesty rules (each has a test):

1. A signal computed on bar *t*'s **close** fills at bar *t+1*'s **open**.
2. Costs on every fill: ``fee_bps`` per side + ``slippage_bps`` (a buy fills at
   ``open*(1+slip)``, a sell at ``open*(1-slip)``).
3. Position sizing is a fixed fraction of equity (``size_fraction``, default 100%).
4. Nothing is opened during warm-up: the strategy answers HOLD until it has
   ``warmup_bars`` bars of history.
5. Time split: the first 70% of bars are in-sample, the last 30% out-of-sample,
   reported separately. The OOS run starts flat at the split; the bars before it
   are used only as indicator history (they are never traded).
6. Benchmark: buy-and-hold over the same window with the same costs (one buy at
   the first tradable open, one sell at the final close).
7. No lookahead from a trained model (FDS-MDL 6.5): a strategy that carries a model
   (``model_train_end``) is refused, ``LOOKAHEAD_MODEL``, when the model's training
   window ends after the first bar being scored. This applies to every run: in a time
   split, an in-sample window it refuses is reported as refused, and the run fails if
   the out-of-sample window is refused.

A position still open on the final bar is closed at that bar's close (with costs),
so strategy and benchmark are measured on the same footing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from backtest.kpis import compute_kpis
from market_data.timeframes import timeframe_seconds
from strategies.base import Action
from strategies.runner import PositionState, StrategyRunner


@dataclass(frozen=True)
class CostModel:
    fee_bps: float = 10.0  # per side
    slippage_bps: float = 5.0  # per fill, adverse
    size_fraction: float = 1.0  # fraction of equity committed per entry

    def __post_init__(self):
        if self.fee_bps < 0 or self.slippage_bps < 0:
            raise ValueError("fee_bps and slippage_bps must be >= 0")
        if not 0 < self.size_fraction <= 1:
            raise ValueError("size_fraction must be in (0, 1]")


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float  # fill price (after slippage)
    exit_price: float
    qty: float
    pnl: float  # net of fees
    pnl_pct: float  # net, relative to cash spent on entry
    fees: float
    bars_held: int
    exit_rule: str
    forced_close: bool = False


@dataclass
class RunResult:
    equity: List[float]
    trades: List[Trade]
    bars_in_position: int
    fees_paid: float
    slippage_cost: float
    initial_equity: float
    first_bar: pd.Timestamp
    last_bar: pd.Timestamp
    bars: int
    kpis: Dict[str, Optional[float]] = field(default_factory=dict)
    # decisions held because the strategy lacked a bar it needs, by reason
    # ("BARS_MISSING:<timeframe>"): reported, never silently scored as "no signal"
    bars_missing: Dict[str, int] = field(default_factory=dict)


MISSING_BARS = "BARS_MISSING"  # the reason prefix of a HOLD for lack of data


class LookaheadError(ValueError):
    """LOOKAHEAD_MODEL: the strategy's model was trained on bars being scored."""


def check_lookahead(runner: StrategyRunner, first_scored: pd.Timestamp) -> None:
    """Refuse (``LOOKAHEAD_MODEL``) when the runner's strategy carries a model whose
    training window ends after ``first_scored``, the open of the first scored bar.
    (The trainer reads only bars closed by ``train_end``, so a bar that opens at
    ``train_end`` was not trained on.)"""
    train_end = getattr(runner.strategy, "model_train_end", None)
    if train_end is None:
        return
    try:
        train_end = pd.Timestamp(train_end)
    except (TypeError, ValueError):
        train_end = pd.NaT
    if pd.isna(train_end):  # unknown: nothing can be shown to be after it
        raise LookaheadError(
            "LOOKAHEAD_MODEL: the strategy's model has no readable end of training"
        )
    if train_end.tzinfo is None:  # naive times are UTC, as in the trainer
        train_end = train_end.tz_localize("UTC")
    if train_end > pd.Timestamp(first_scored):
        model = getattr(runner.strategy, "model_id", "?")
        raise LookaheadError(
            f"LOOKAHEAD_MODEL: model {model} was trained on bars up to {train_end}, "
            f"after the first scored bar ({pd.Timestamp(first_scored)}); score only bars "
            "that open at or after the end of the model's training window"
        )


def _fill_buy(price: float, slip_bps: float) -> float:
    return price * (1.0 + slip_bps / 1e4)


def _fill_sell(price: float, slip_bps: float) -> float:
    return price * (1.0 - slip_bps / 1e4)


def run_backtest(
    candles: pd.DataFrame,
    runner: StrategyRunner,
    symbol: str,
    tf: str,
    start_index: int = 0,
    end_index: Optional[int] = None,
    cost: CostModel = CostModel(),
    initial_equity: float = 10_000.0,
) -> RunResult:
    """
    Trade the bars ``[start_index, end_index)`` of ``candles``. Bars before
    ``start_index`` are history only. ``candles`` must be closed bars.
    """
    n = len(candles) if end_index is None else end_index
    if not 0 <= start_index < n <= len(candles):
        raise ValueError("invalid trading window")
    check_lookahead(runner, candles["open_time"].iloc[start_index])
    model_symbol = getattr(runner.strategy, "model_symbol", None)
    if model_symbol is not None and str(model_symbol).upper() != str(symbol).upper():
        raise ValueError(
            f"the strategy's model was trained on {model_symbol}; this run is {symbol}"
        )
    tf_seconds = timeframe_seconds(tf)
    runner.set_timeframe(
        tf_seconds
    )  # overlays that count bars (cooldowns) need the bar length
    fee_rate = cost.fee_bps / 1e4

    open_ = candles["open"].to_numpy(dtype=float)
    close = candles["close"].to_numpy(dtype=float)
    times = candles["open_time"]

    cash = float(initial_equity)
    qty = 0.0
    spent = 0.0  # cash paid for the open position (incl. entry fee)
    entry_fee = 0.0
    entry_fill = 0.0
    entry_i = 0
    pos: Optional[PositionState] = None
    pending: Optional[str] = None  # "ENTER" | "EXIT:<rule>"
    equity: List[float] = []
    trades: List[Trade] = []
    fees_paid = 0.0
    slippage_cost = 0.0
    bars_in_position = 0
    bars_missing: Dict[str, int] = {}

    def sell(i: int, price_raw: float, rule: str, forced: bool) -> None:
        nonlocal cash, qty, spent, fees_paid, slippage_cost, pos
        fill = _fill_sell(price_raw, cost.slippage_bps)
        gross = qty * fill
        fee = gross * fee_rate
        cash += gross - fee
        fees_paid += fee
        slippage_cost += qty * (price_raw - fill)
        pnl = gross - fee - spent
        trades.append(
            Trade(
                entry_time=times.iloc[entry_i],
                exit_time=times.iloc[i],
                entry_price=entry_fill,
                exit_price=fill,
                qty=qty,
                pnl=pnl,
                pnl_pct=pnl / spent * 100.0,
                fees=entry_fee + fee,
                bars_held=i - entry_i,
                exit_rule=rule,
                forced_close=forced,
            )
        )
        runner.close_position(pos, times.iloc[i], fill)
        qty, spent, pos = 0.0, 0.0, None

    last = n - 1
    for i in range(start_index, n):
        # 1) execute last bar's decision at this bar's open
        if pending == "ENTER" and pos is None:
            fill = _fill_buy(open_[i], cost.slippage_bps)
            spend = cash * cost.size_fraction
            entry_fee = spend * fee_rate
            qty = (spend - entry_fee) / fill
            cash -= spend
            spent = spend
            fees_paid += entry_fee
            slippage_cost += qty * (fill - open_[i])
            entry_i = i
            entry_fill = fill
            pos = runner.open_position(
                symbol, fill, times.iloc[i], runner.window(candles, i)
            )
        elif pending is not None and pending.startswith("EXIT") and pos is not None:
            sell(i, open_[i], pending.split(":", 1)[1], forced=False)
        pending = None

        # 2) mark to market at this bar's close
        if pos is not None:
            bars_in_position += 1
        equity.append(cash + qty * close[i])

        # 3) decide at this bar's close (executes at the next open)
        if i == last:
            break
        decision = runner.evaluate(runner.window(candles, i), pos, symbol)
        if decision.action is Action.HOLD and decision.reason.startswith(MISSING_BARS):
            bars_missing[decision.reason] = bars_missing.get(decision.reason, 0) + 1
        if decision.action is Action.ENTER_LONG and pos is None:
            pending = "ENTER"
        elif decision.action is Action.EXIT_LONG and pos is not None:
            pending = f"EXIT:{decision.exit_rule or 'strategy'}"

    if pos is not None:  # close at the final close so results are comparable
        sell(last, close[last], "end_of_data", forced=True)
        equity[-1] = cash

    result = RunResult(
        equity=equity,
        trades=trades,
        bars_in_position=bars_in_position,
        fees_paid=fees_paid,
        slippage_cost=slippage_cost,
        initial_equity=float(initial_equity),
        first_bar=times.iloc[start_index],
        last_bar=times.iloc[last],
        bars=n - start_index,
        bars_missing=bars_missing,
    )
    result.kpis = compute_kpis(
        equity,
        initial_equity,
        tf_seconds,
        [t.pnl_pct for t in trades],
        bars_in_position,
        fees_paid,
    )
    return result


def buy_and_hold(
    candles: pd.DataFrame,
    tf: str,
    start_index: int = 0,
    end_index: Optional[int] = None,
    cost: CostModel = CostModel(),
    initial_equity: float = 10_000.0,
) -> RunResult:
    """One buy at the first tradable open, one sell at the final close; same costs."""
    n = len(candles) if end_index is None else end_index
    if not 0 <= start_index < n <= len(candles):
        raise ValueError("invalid trading window")
    fee_rate = cost.fee_bps / 1e4
    open_ = candles["open"].to_numpy(dtype=float)
    close = candles["close"].to_numpy(dtype=float)
    times = candles["open_time"]

    fill = _fill_buy(open_[start_index], cost.slippage_bps)
    spend = initial_equity * cost.size_fraction
    entry_fee = spend * fee_rate
    qty = (spend - entry_fee) / fill
    cash = initial_equity - spend
    fees = entry_fee
    slip = qty * (fill - open_[start_index])

    equity = [cash + qty * close[i] for i in range(start_index, n)]
    last = n - 1
    sell_fill = _fill_sell(close[last], cost.slippage_bps)
    gross = qty * sell_fill
    exit_fee = gross * fee_rate
    fees += exit_fee
    slip += qty * (close[last] - sell_fill)
    final_cash = cash + gross - exit_fee
    equity[-1] = final_cash
    pnl = gross - exit_fee - spend
    trade = Trade(
        entry_time=times.iloc[start_index],
        exit_time=times.iloc[last],
        entry_price=fill,
        exit_price=sell_fill,
        qty=qty,
        pnl=pnl,
        pnl_pct=pnl / spend * 100.0,
        fees=fees,
        bars_held=last - start_index,
        exit_rule="end_of_data",
        forced_close=True,
    )
    bars = n - start_index
    result = RunResult(
        equity=equity,
        trades=[trade],
        bars_in_position=bars,
        fees_paid=fees,
        slippage_cost=slip,
        initial_equity=float(initial_equity),
        first_bar=times.iloc[start_index],
        last_bar=times.iloc[last],
        bars=bars,
    )
    result.kpis = compute_kpis(
        equity, initial_equity, timeframe_seconds(tf), [trade.pnl_pct], bars, fees
    )
    return result


def split_index(n_bars: int, in_sample_fraction: float = 0.7) -> int:
    """First out-of-sample bar index: the first 70% (by time) is in-sample."""
    if not 0 < in_sample_fraction < 1:
        raise ValueError("in_sample_fraction must be in (0, 1)")
    return int(n_bars * in_sample_fraction)


def evaluate_split(
    candles: pd.DataFrame,
    runner_factory,
    symbol: str,
    tf: str,
    cost: CostModel = CostModel(),
    in_sample_fraction: float = 0.7,
    initial_equity: float = 10_000.0,
) -> Dict[str, Any]:
    """
    Run the strategy and the buy-and-hold benchmark on the in-sample and
    out-of-sample windows. ``runner_factory()`` must return a *fresh* runner
    (overlays are stateful) for each window. An in-sample window refused with
    ``LOOKAHEAD_MODEL`` comes back as ``{"refused": reason, "buy_and_hold": ...}``;
    a refused out-of-sample window raises ``LookaheadError``.
    """
    n = len(candles)
    cut = split_index(n, in_sample_fraction)
    windows = {"in_sample": (0, cut), "out_of_sample": (cut, n)}
    out: Dict[str, Any] = {}
    for name, (a, b) in windows.items():
        if b - a < 2:
            raise ValueError(f"{name} window has fewer than 2 bars")
        bench = buy_and_hold(candles, tf, a, b, cost, initial_equity)
        try:
            strat = run_backtest(
                candles, runner_factory(), symbol, tf, a, b, cost, initial_equity
            )
        except LookaheadError as exc:
            if name == "out_of_sample":
                raise
            out[name] = {"refused": str(exc), "buy_and_hold": bench, "window": (a, b)}
            continue
        sk, bk = strat.kpis, bench.kpis
        if sk["total_return_pct"] is not None and bk["total_return_pct"] is not None:
            sk["vs_buy_hold_pct"] = sk["total_return_pct"] - bk["total_return_pct"]
        out[name] = {"strategy": strat, "buy_and_hold": bench, "window": (a, b)}
    return out
