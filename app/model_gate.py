"""
The entry gate for a trained model (entry_gate): the trades its entries make on its
held-out bars, replayed with the trader's rules, against random entries replayed with
exactly the same rules. pt_pattern_trainer publishes a model only when it passes.

Signals
-------
At the close of each held-out hour every timeframe predicts from its last bar that
closed before then, and ``pattern_model.thinker_decision`` gives each timeframe's side,
as the neural runner does in steady state (STRAT-003 uses the same rule). The long and
short counts are the ones the runner writes for the trader. An hour where a timeframe's
bar is missing, or the bounds do not settle, is undecided: no entry is made there.

The trade rules (pt_trader.py, the neural signals' trade logic)
---------------------------------------------------------------
Read from the trader's settings (gui_settings.json) the way the trader reads them
(``trade_rules``):

* entry: at an hour whose long count is at least ``trade_start_level`` and short count
  0, when no trade in the coin is open; ``start_allocation_pct`` of the account;
* at each hourly close from the entry on, first the trailing profit margin: its line
  starts ``pm_start_pct_no_dca`` (``pm_start_pct_with_dca`` after a DCA) above the
  average cost; once the price is at or above it the line follows the peak
  ``trailing_gap_pct`` behind, never below the start line, and a close that falls from
  above it to below it sells everything;
* then DCA: the stage's hard level (``dca_levels``, the last one repeated) or, for the
  first four stages and below cost, a long count of at least stage + 4. The buy is
  ``dca_multiplier`` times the position's value, skipped when ``max_dca_buys_per_24h``
  were made in the last 24 h or when it would take the coin past
  ``max_coin_allocation_pct`` of the account. A DCA restarts the trailing line;
* every fill pays the fee (entry_gate.trading_fees: the taker rate, since the trader
  places market orders) and the slippage; the average cost includes the fees, as the
  trader's ledger does;
* a trade still open when the held-out bars end is sold at the last close, its exit fee
  included; open longer than ``OPEN_TOO_LONG_S`` it counts as a loss in the hit rate.

The account is ``ACCOUNT`` units and is not compounded: every trade is sized from it.
Prices are the hourly closes (the trader watches the live price and buys at the ask,
sells at the bid), and an entry is not raised to the exchange's minimum order; both are
the same for the model's entries and the random ones.

The score
---------
Return per day held after fees (entry_gate.PER_DAY): the trades' profit over their
capital-days. A trade's capital-days add, for each hour after its entry up to its exit,
the capital committed at the start of that hour times the hour's length in days (by
the close times, so an hour missing from the candles still counts its time).

Random entries: same waits, random order
----------------------------------------
The model holds one trade at a time, and so do the random entries (``same_waits``).
The model's waits are the hours (held-out hour positions) from being free to entering:
from the first held-out hour to its first entry, then from each trade's end to its
next entry; the time after its last trade is not a wait, as it never ended in an entry.
A random run starts free at the first hour; it draws one of those waits with
replacement, enters at the first decided hour at least that far on, holds the trade
exactly as the model would (its neural DCA read from the same long counts), and from
the trade's end draws again, until the held-out hours run out. Only the order of the
waits is random, so the run keeps the model's patience, and its entry count varies
around the model's. (An earlier version drew distinct hours and replayed each as a
trade of its own, so random trades overlapped; buys made part-way down a drawdown, while
a real trade would still be open, recover well, so that baseline favoured random
entries: docs/dev/GATE-DIAGNOSTIC-2026-11-05.md, finding 1.)
"""

from __future__ import annotations

import bisect
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import entry_gate
import position_sizing

ACCOUNT = 100.0
HOUR_S = 3600
DAY_S = 24 * HOUR_S
OPEN_TOO_LONG_S = 7 * DAY_S  # the gate design's max_open_bars (7 days)
NEURAL_DCA_STAGES = 4  # pt_trader: neural DCA for the first four stages only

# the trader's defaults (pt_trader._gui_settings_cache)
TRADER_DEFAULTS: Dict[str, Any] = {
    "trade_start_level": 3,
    "start_allocation_pct": position_sizing.DEFAULT_START_ALLOCATION_PCT,
    "max_coin_allocation_pct": position_sizing.DEFAULT_MAX_COIN_ALLOCATION_PCT,
    "dca_multiplier": 2.0,
    "dca_levels": [-2.5, -5.0, -10.0, -20.0, -30.0, -40.0, -50.0],
    "max_dca_buys_per_24h": 2,
    "pm_start_pct_no_dca": 5.0,
    "pm_start_pct_with_dca": 2.5,
    "trailing_gap_pct": 0.5,
}


@dataclass(frozen=True)
class TradeRules:
    trade_start_level: int
    start_allocation_pct: float
    max_coin_allocation_pct: float
    dca_multiplier: float
    dca_levels: Tuple[float, ...]
    max_dca_buys_per_24h: int
    pm_start_pct_no_dca: float
    pm_start_pct_with_dca: float
    trailing_gap_pct: float

    def to_dict(self) -> Dict[str, Any]:
        out = dict(self.__dict__)
        out["dca_levels"] = list(self.dca_levels)
        return out


def _number(value: Any, default: float) -> float:
    """``float(value or default)``, as pt_trader._refresh_paths_and_symbols reads it."""
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return float(default)


def trade_rules(settings: Mapping[str, Any]) -> TradeRules:
    """The rules from gui_settings.json's values, read and bounded as
    pt_trader._refresh_paths_and_symbols does (a missing or zero value is the
    default)."""
    s = {**TRADER_DEFAULTS, **{k: v for k, v in settings.items() if v is not None}}
    try:
        level = int(s["trade_start_level"] or 3)
    except (TypeError, ValueError):
        level = 3
    try:
        per_day = int(float(s["max_dca_buys_per_24h"] or 2))
    except (TypeError, ValueError):
        per_day = 2
    try:
        levels = tuple(
            float(x) for x in (s["dca_levels"] or TRADER_DEFAULTS["dca_levels"])
        )
    except (TypeError, ValueError):
        levels = tuple(TRADER_DEFAULTS["dca_levels"])
    return TradeRules(
        trade_start_level=max(1, min(level, 7)),
        start_allocation_pct=max(
            0.0,
            _number(s["start_allocation_pct"], TRADER_DEFAULTS["start_allocation_pct"]),
        ),
        max_coin_allocation_pct=_number(
            s["max_coin_allocation_pct"], TRADER_DEFAULTS["max_coin_allocation_pct"]
        ),
        dca_multiplier=max(0.0, _number(s["dca_multiplier"], 2.0)),
        dca_levels=levels,
        max_dca_buys_per_24h=max(0, per_day),
        pm_start_pct_no_dca=max(0.0, _number(s["pm_start_pct_no_dca"], 5.0)),
        pm_start_pct_with_dca=max(0.0, _number(s["pm_start_pct_with_dca"], 2.5)),
        trailing_gap_pct=max(0.0, _number(s["trailing_gap_pct"], 0.5)),
    )


def read_trade_rules(path: Optional[str] = None) -> TradeRules:
    """The rules from the trader's settings file, checked as the trader checks it
    (``InputValidator.validate_config_data``): a file it refuses, or none, gives the
    trader's defaults, as a trader starting now would use."""
    import pt_paths
    from pt_validation import InputValidator, ValidationError

    path = (
        path
        or os.environ.get("POWERTRADER_GUI_SETTINGS")
        or pt_paths.gui_settings_file()
    )
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        data = InputValidator.validate_config_data(data)
    except (OSError, ValueError, ValidationError):
        data = {}
    return trade_rules(data if isinstance(data, dict) else {})


# --- the held-out hours ---------------------------------------------------------------


@dataclass(frozen=True)
class Hours:
    """The held-out hours, oldest first: each hour's close time (s), its close price,
    and the long and short counts decided at its close (None: undecided)."""

    close_s: Tuple[int, ...]
    price: Tuple[float, ...]
    longs: Tuple[Optional[int], ...]
    shorts: Tuple[Optional[int], ...]

    def decided(self) -> List[int]:
        return [i for i, n in enumerate(self.longs) if n is not None]


class _Bars:
    def __init__(self, frame, step: int):
        self.open_s = [int(t.timestamp()) for t in frame["open_time"]]
        self.open = frame["open"].astype(float).tolist()
        self.close = frame["close"].astype(float).tolist()
        self.step = step


def hourly_signals(model, frames: Mapping[str, Any], start_s: int, end_s: int) -> Hours:
    """The runner's counts at the close of every 1-hour bar that opens at or after
    ``start_s`` and closes by ``end_s``. ``frames`` are ``{candle timeframe: frame}``
    (open_time, open, close) reaching back far enough for each timeframe's last bar
    before the first hour."""
    from market_data.timeframes import bar_open_floor, candle_timeframe_seconds
    from pattern_model import CANDLE_TF, TIMEFRAMES, GapPassStuck, thinker_decision

    bars = {
        tf: _Bars(frames[CANDLE_TF[tf]], candle_timeframe_seconds(CANDLE_TF[tf]))
        for tf in TIMEFRAMES
    }
    hourly = bars["1hour"]
    predictions: Dict[Tuple[str, int], Any] = {}
    close_s, price, longs, shorts = [], [], [], []
    for k, opened in enumerate(hourly.open_s):
        t = opened + HOUR_S
        if opened < start_s or t > end_s:
            continue
        preds = []
        for tf in TIMEFRAMES:
            b = bars[tf]
            expected = bar_open_floor(t - 1, CANDLE_TF[tf]) - b.step
            j = bisect.bisect_left(b.open_s, expected)
            if j >= len(b.open_s) or b.open_s[j] != expected:
                preds = None
                break
            if (tf, j) not in predictions:
                predictions[(tf, j)] = model.timeframes[tf].predict(
                    b.open[j], b.close[j]
                )
            preds.append(predictions[(tf, j)])
        counts: Tuple[Optional[int], Optional[int]] = (None, None)
        if preds is not None:
            try:
                sides, _lows, _highs = thinker_decision(preds, hourly.close[k])
                counts = (sides.count("long"), sides.count("short"))
            except GapPassStuck:
                pass
        close_s.append(t)
        price.append(hourly.close[k])
        longs.append(counts[0])
        shorts.append(counts[1])
    return Hours(tuple(close_s), tuple(price), tuple(longs), tuple(shorts))


# --- one trade --------------------------------------------------------------------------


def replay(
    i: int, hours: Hours, rules: TradeRules, fees: entry_gate.Fees
) -> entry_gate.Trade:
    """The trade an entry at the close of hour ``i`` makes (see the module docstring)."""
    f, s = fees.rate, fees.slippage
    prices, times, longs = hours.price, hours.close_s, hours.longs
    budget = position_sizing.coin_budget_usd(ACCOUNT, rules.max_coin_allocation_pct)
    spent = ACCOUNT * rules.start_allocation_pct / 100.0
    if spent <= 0.0:
        return entry_gate.Trade(0.0, 0.0, 0.0, False, i)
    committed = spent
    qty = spent * (1.0 - f) / (prices[i] * (1.0 + s))
    stage = 0
    dca_times: List[int] = []
    trail: Optional[Dict[str, Any]] = None
    worst = 0.0
    held = 0.0  # capital-days
    levels = rules.dca_levels
    gap = rules.trailing_gap_pct / 100.0
    last = len(prices) - 1
    for j in range(i, last + 1):
        price, now = prices[j], times[j]
        if j > i:
            held += committed * (now - times[j - 1]) / DAY_S
        avg = committed / qty
        gain_pct = (price - avg) / avg * 100.0
        worst = min(worst, gain_pct / 100.0)
        # trailing profit margin (pt_trader.manage_trades)
        pm = rules.pm_start_pct_no_dca if stage == 0 else rules.pm_start_pct_with_dca
        base = avg * (1.0 + pm / 100.0)
        if trail is None:
            trail = {"active": False, "line": base, "peak": 0.0, "was_above": False}
        elif not trail["active"]:
            trail["line"] = base
        elif trail["line"] < base:
            trail["line"] = base
        above = price >= trail["line"]
        if not trail["active"] and above:
            trail["active"], trail["peak"] = True, price
        if trail["active"]:
            if price > trail["peak"]:
                trail["peak"] = price
            line = max(trail["peak"] * (1.0 - gap), base)
            if line > trail["line"]:
                trail["line"] = line
            if trail["was_above"] and price < trail["line"]:
                proceeds = qty * price * (1.0 - s) * (1.0 - f)
                net = proceeds - committed
                return entry_gate.Trade(net, committed, worst, net > 0.0, j, held)
        trail["was_above"] = above
        # DCA: the stage's hard level, or the neural level below cost
        hard = (
            (levels[stage] if stage < len(levels) else levels[-1]) if levels else None
        )
        hard_hit = hard is not None and gain_pct <= hard
        neural_hit = False
        if stage < NEURAL_DCA_STAGES:
            neural_hit = gain_pct < 0 and (longs[j] or 0) >= stage + 4
        if hard_hit or neural_hit:
            dca_times = [t for t in dca_times if now - t < DAY_S]
            amount = qty * price * rules.dca_multiplier
            if (
                len(dca_times) < rules.max_dca_buys_per_24h
                and amount > 0.0
                and committed + amount <= budget + 1e-9
            ):
                committed += amount
                qty += amount * (1.0 - f) / (price * (1.0 + s))
                stage += 1
                dca_times.append(now)
                trail = None
    proceeds = qty * prices[last] * (1.0 - s) * (1.0 - f)
    net = proceeds - committed
    too_long = times[last] - times[i] > OPEN_TOO_LONG_S
    return entry_gate.Trade(
        net, committed, worst, net > 0.0 and not too_long, last, held
    )


def model_entries(
    hours: Hours, rules: TradeRules, trade
) -> List[Tuple[int, entry_gate.Trade]]:
    """The model's trades: an entry at each qualifying hour while no trade is open (a
    trade that ends at an hour's close leaves that hour free for the next entry)."""
    out = []
    free_from = 0
    for i, (n_long, n_short) in enumerate(zip(hours.longs, hours.shorts)):
        if i < free_from or n_long is None:
            continue
        if n_long >= rules.trade_start_level and n_short == 0:
            t = trade(i)
            out.append((i, t))
            free_from = max(t.end, i + 1)
    return out


def waits_of(
    entries: Sequence[Tuple[int, entry_gate.Trade]], start: int = 0
) -> List[int]:
    """The waits of ``model_entries``'s trades (the module docstring): hours from being
    free (the first hour, ``start``, then a trade's end) to the next entry."""
    waits, free = [], start
    for i, t in entries:
        waits.append(i - free)
        free = max(t.end, i + 1)
    return waits


def same_waits(
    decided: Sequence[int], waits: Sequence[int], trade, rng, start: int = 0
) -> List[entry_gate.Trade]:
    """One run of random entries made with the same waits, in random order (the module
    docstring): ``decided`` are the decided hours, ascending, ``trade(i)`` the trade an
    entry at hour ``i`` makes, and ``start`` the first hour. Draws use
    ``rng.random()`` alone."""
    out: List[entry_gate.Trade] = []
    free = start
    if not waits:
        return out
    while True:
        wait = waits[int(rng.random() * len(waits))]
        p = bisect.bisect_left(decided, free + wait)
        if p >= len(decided):
            return out
        i = decided[p]
        t = trade(i)
        out.append(t)
        free = max(t.end, i + 1)


@dataclass
class ModelGateResult:
    decision: entry_gate.Decision
    hours: int
    decided: int
    signal_hours: int
    rules: TradeRules

    def lines(self) -> List[str]:
        return self.decision.lines() + [
            f"held-out hours {self.hours} ({self.decided} decided, "
            f"{self.signal_hours} with an entry signal); trade rules "
            + json.dumps(self.rules.to_dict(), sort_keys=True)
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            **self.decision.to_dict(),
            "hours": self.hours,
            "decided_hours": self.decided,
            "signal_hours": self.signal_hours,
            "rules": self.rules.to_dict(),
        }


def evaluate(
    hours: Hours,
    rules: TradeRules,
    fees: Optional[entry_gate.Fees],
    settings: entry_gate.GateSettings,
    coin: str,
    current: Optional[float] = None,
    seed: int = entry_gate.DEFAULT_SEED,
    note: str = "",
) -> ModelGateResult:
    """The gate's decision on a model whose held-out hours are ``hours``: its return
    per day held after fees against random entries made with the same waits.
    ``current`` is the model in use's own return per day held, when recorded."""
    decided = hours.decided()
    signal_hours = sum(
        1
        for i in decided
        if hours.longs[i] >= rules.trade_start_level and hours.shorts[i] == 0
    )
    if fees is None:
        decision = entry_gate.decide(
            [], {}, {}, settings, None, seed, current, note, entry_gate.PER_DAY
        )
        return ModelGateResult(
            decision, len(hours.price), len(decided), signal_hours, rules
        )
    cache: Dict[int, entry_gate.Trade] = {}

    def trade(i: int) -> entry_gate.Trade:
        if i not in cache:
            cache[i] = replay(i, hours, rules, fees)
        return cache[i]

    entries = model_entries(hours, rules, trade)
    waits = waits_of(entries)
    decision = entry_gate.decide(
        [t for _i, t in entries],
        {},
        {},
        settings,
        fees,
        seed,
        current,
        note,
        entry_gate.PER_DAY,
        draw_run=lambda rng: same_waits(decided, waits, trade, rng),
    )
    return ModelGateResult(
        decision, len(hours.price), len(decided), signal_hours, rules
    )
