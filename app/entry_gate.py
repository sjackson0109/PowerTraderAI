"""
The entry gate: whether a source of trade entries has earned a place in trading, judged
by what its entries earn after fees against random entries, never by its hit rate.

Why not the hit rate
--------------------
The trader's exits make most trades win whatever the entry: a trade is held, and added
to as it falls (DCA), until the trailing profit margin sells it above its average cost.
On the same held-out months, random entries with those exits won about 91% of the time
and the trained model's entries 90.5% (docs/research/volume-module.md, research/volume
branch). So the hit rate is calculated and shown, and decides nothing.

Candidates and their score
--------------------------
A trained model of one coin (model_gate: its entries on its held-out bars), the paper
signals of one LLM provider/model/prompt version (llm_gate), or any entry filter. A
candidate gives its trades (``Trade``) and how a run of random entries is drawn. Every
random entry's trade is replayed with exactly the rules the candidate's trades were:
the same sizing, exits, DCA, trailing, stops and the same treatment of a trade still
open when the held-out bars end. Each kind of candidate is judged by one score:

* a trained model (``PER_DAY``): its return per day held after fees, the profit over
  every unit of capital times the days it was committed. Its trades hold one at a time
  and last from hours to weeks, and a long trade with DCA buys can look good per trade
  while tying capital up for weeks, so time held counts
  (docs/dev/GATE-DIAGNOSTIC-2026-11-05.md, finding 3);
* an LLM signal (``MEAN_RETURN``): its mean return after fees per trade. Each signal is
  scored as a trade of its own, with no capital held between them.

The random baseline
-------------------
``gate_baseline_runs`` runs (1000); run k uses ``random.Random(seed + k)``. Draws use
only ``random()``, whose sequence Python keeps for a seed across versions, so a
recorded seed repeats a run exactly. Two kinds:

* same waits, random order (``draw_run``: a trained model, model_gate.same_waits): one
  trade at a time, as the model and the trader hold them. From the first held-out hour,
  and after each exit, a random entry waits one of the model's own waits (hours from
  being free to entering), drawn with replacement, then enters. Only the timing is
  random, so the run keeps the model's patience, and its entry count varies around the
  model's;
* distinct moments (``Slots``: an LLM signal): as many distinct moments from each group
  (the same coin, direction, horizon, target and stop) as the candidate made entries in
  it (all of them when the group has fewer), each replayed as a trade of its own, so
  random trades can overlap, as signals do.

The smallest detectable edge is the gain over the random median that the candidate
would have needed to pass rule d four times in five: (z at the percentile + z at 0.8) x
the spread (standard deviation) of the runs' scores. When it is more than half the size
of the random median, the result is "too few trades to tell"; that is shown, and
decides nothing.

The pass rule (all must hold)
-----------------------------
a. at least ``holdout_min_signals`` entries;
b. the score above its minimum: for a trained model ``gate_min_return_per_day`` (0%
   a day), for an LLM signal ``gate_min_return_after_fees`` (0%);
c. capital-weighted return after fees (profit over all capital committed, DCA buys
   included) above 0%;
d. the score above the ``gate_baseline_percentile`` (95th) percentile of the random
   runs' scores;
e. worst drawdown no worse than the median of the random runs' worst drawdowns;
f. where a current model has a recorded score, a score not below the current model's
   own (each on its own held-out bars).

Fees
----
``trading_fees(coin)``: the rate the trader pays. Its orders are market orders, so the
taker rate, of the primary exchange first: read from the account with the API key saved
for it where the exchange can say (``TradingFees.source`` "exchange"), else the
exchange's published standard rate ("default", DEFAULT_TRADING_FEES). Every fill also
pays the backtester's slippage (``backtest.engine.CostModel``, 0.05%). Every decision
records the rate, its order type, exchange and source.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

DEFAULT_SEED = 0  # run k of a baseline uses random.Random(DEFAULT_SEED + k)
ORDER_TYPE = "market"  # the trader's entry, DCA and exit orders (pt_trader.py)

MEAN_RETURN = "mean_return"  # mean return after fees per trade (an LLM signal)
PER_DAY = "per_day"  # return per day held after fees (a trained model)
POWER = 0.8  # the smallest detectable edge is the one rule d catches 4 times in 5
TOO_FEW = 0.5  # ...and above this share of the random median: too few trades to tell
SAME_WAITS = "same waits"  # the kinds of random baseline (module docstring)
DISTINCT = "distinct moments"


# --- trades and their score -----------------------------------------------------------


@dataclass(frozen=True)
class Trade:
    """One trade, replayed. ``net`` is its profit after fees and slippage, in the
    account's money; ``committed`` the capital put in (the entry and every DCA buy,
    fees included); ``drawdown`` its worst fall below its average cost while it was
    open, a fraction (0 or less); ``hit`` whether it counts as a win (the hit rate is
    shown, never decides); ``end`` the index it ended at (replays that hold one trade
    at a time read it); ``capital_days`` the capital it had committed times the days
    it was held, summed hour by hour (a DCA buy counts from the next hour on)."""

    net: float
    committed: float
    drawdown: float
    hit: bool
    end: int = -1
    capital_days: float = 0.0

    @property
    def ret(self) -> float:
        """The return after fees: profit over the capital it committed."""
        return self.net / self.committed if self.committed > 0 else 0.0


@dataclass(frozen=True)
class Score:
    entries: int
    mean_return: Optional[float]  # mean of the trades' returns after fees
    capital_return: Optional[float]  # total profit / total capital committed
    drawdown: Optional[float]  # the worst trade's drawdown
    hit_rate: Optional[float]  # shown only
    per_day: Optional[float] = None  # total profit / total capital-days held

    def value(self, measure: str) -> Optional[float]:
        """The score ``measure`` (PER_DAY or MEAN_RETURN) names."""
        return self.per_day if measure == PER_DAY else self.mean_return

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entries": self.entries,
            "mean_return": self.mean_return,
            "capital_return": self.capital_return,
            "drawdown": self.drawdown,
            "hit_rate": self.hit_rate,
            "per_day": self.per_day,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Score":
        return cls(
            int(data.get("entries") or 0),
            data.get("mean_return"),
            data.get("capital_return"),
            data.get("drawdown"),
            data.get("hit_rate"),
            data.get("per_day"),
        )


def score(trades: Sequence[Trade]) -> Score:
    if not trades:
        return Score(0, None, None, None, None, None)
    committed = sum(t.committed for t in trades)
    net = sum(t.net for t in trades)
    capital_days = sum(t.capital_days for t in trades)
    return Score(
        entries=len(trades),
        mean_return=sum(t.ret for t in trades) / len(trades),
        capital_return=(net / committed) if committed else None,
        drawdown=min(t.drawdown for t in trades),
        hit_rate=sum(1 for t in trades if t.hit) / len(trades),
        per_day=(net / capital_days) if capital_days > 0 else None,
    )


# --- the random baseline --------------------------------------------------------------


@dataclass(frozen=True)
class Slots:
    """``size`` moments a random entry could be made at, and ``trade(i)``: the trade an
    entry at moment ``i`` (0 .. size-1) makes, or None when none can be replayed there.
    """

    size: int
    trade: Callable[[int], Optional[Trade]]


def draw(rng: random.Random, size: int, n: int) -> List[int]:
    """``n`` distinct numbers from ``range(size)`` (all of them, shuffled, when ``n`` is
    ``size`` or more): a partial Fisher-Yates shuffle that keeps only the swapped
    places, driven by ``rng.random()`` alone."""
    n = max(0, min(int(n), int(size)))
    swapped: Dict[int, int] = {}
    out: List[int] = []
    for i in range(n):
        j = i + int(rng.random() * (size - i))
        at_i, at_j = swapped.get(i, i), swapped.get(j, j)
        swapped[j] = at_i
        out.append(at_j)
    return out


def percentile(values: Sequence[float], p: float) -> float:
    """The ``p``-th percentile of ``values``, interpolated between the two nearest
    ranks (numpy's default)."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile of nothing")
    h = (len(ordered) - 1) * max(0.0, min(100.0, float(p))) / 100.0
    lo = int(math.floor(h))
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (h - lo) * (ordered[hi] - ordered[lo])


def percentile_rank(value: float, values: Sequence[float]) -> float:
    """100 x (values below ``value`` + half the values equal to it) / their number (the
    backtester's control uses the same: backtest.random_baseline.percentile_rank)."""
    below = sum(1 for x in values if x < value)
    equal = sum(1 for x in values if x == value)
    return 100.0 * (below + 0.5 * equal) / len(values)


@dataclass(frozen=True)
class Baseline:
    runs: int
    seed: int  # run k used random.Random(seed + k)
    values: Tuple[float, ...]  # each run's score (``measure``)
    drawdowns: Tuple[float, ...]  # each run's worst drawdown
    entries: Tuple[int, ...]  # each run's entry count
    short: Tuple[str, ...] = ()  # groups with fewer slots than the candidate's entries
    measure: str = MEAN_RETURN
    kind: str = DISTINCT

    def median(self) -> float:
        return percentile(self.values, 50.0)

    def at(self, p: float) -> float:
        return percentile(self.values, p)

    def median_drawdown(self) -> float:
        return percentile(self.drawdowns, 50.0)

    def rank(self, value: float) -> float:
        return percentile_rank(value, self.values)

    def spread(self) -> float:
        """The standard deviation of the runs' scores (0 for a single run)."""
        return statistics.pstdev(self.values) if len(self.values) > 1 else 0.0


def run_draws(
    draw_run: Callable[[random.Random], Sequence[Optional[Trade]]],
    runs: int,
    seed: int = DEFAULT_SEED,
    measure: str = MEAN_RETURN,
    kind: str = SAME_WAITS,
    short: Tuple[str, ...] = (),
) -> Optional[Baseline]:
    """``runs`` random baselines: run k is ``draw_run(random.Random(seed + k))``'s
    entries, each a trade or None (a moment where none could be replayed: it counts as
    an entry drawn, and is not scored), scored by ``measure``. A run with no score is
    left out. None when no run is left."""
    values: List[float] = []
    drawdowns: List[float] = []
    entries: List[int] = []
    for k in range(int(runs)):
        drawn = list(draw_run(random.Random(int(seed) + k)))
        s = score([t for t in drawn if t is not None])
        value = s.value(measure)
        if value is None:
            continue
        values.append(value)
        drawdowns.append(s.drawdown)
        entries.append(len(drawn))
    if not values:
        return None
    return Baseline(
        len(values),
        int(seed),
        tuple(values),
        tuple(drawdowns),
        tuple(entries),
        short,
        measure,
        kind,
    )


def run_baseline(
    slots: Mapping[str, Slots],
    counts: Mapping[str, int],
    runs: int,
    seed: int = DEFAULT_SEED,
    measure: str = MEAN_RETURN,
) -> Optional[Baseline]:
    """``runs`` random baselines of distinct moments: run k draws ``counts[group]``
    slots of each group (groups in sorted order) with ``random.Random(seed + k)``. A
    slot's trade is replayed once and reused. None when no run gets a trade."""
    cache: Dict[Tuple[str, int], Optional[Trade]] = {}
    groups = sorted(g for g in slots if counts.get(g, 0) > 0)

    def draw_run(rng: random.Random) -> List[Optional[Trade]]:
        out: List[Optional[Trade]] = []
        for g in groups:
            for i in draw(rng, slots[g].size, counts[g]):
                key = (g, i)
                if key not in cache:
                    cache[key] = slots[g].trade(i)
                out.append(cache[key])
        return out

    short = tuple(g for g in groups if slots[g].size < counts[g])
    return run_draws(draw_run, runs, seed, measure, DISTINCT, short)


# --- settings and fees ----------------------------------------------------------------


@dataclass(frozen=True)
class GateSettings:
    min_entries: int = 20
    min_return_per_day: float = 0.0  # a fraction a day (rule b for PER_DAY)
    runs: int = 1000
    percentile: float = 95.0
    min_mean_return: float = 0.0  # a fraction (rule b for MEAN_RETURN: LLM signals)

    @classmethod
    def from_training(cls, training: Mapping[str, Any]) -> "GateSettings":
        """From the ``training`` section (training_settings.normalise)."""
        return cls(
            int(training["holdout_min_signals"]),
            float(training["gate_min_return_per_day"]),
            int(training["gate_baseline_runs"]),
            float(training["gate_baseline_percentile"]),
            float(training["gate_min_return_after_fees"]),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "GateSettings":
        """From ``to_dict``'s keys (a record an earlier version wrote has no per-day
        minimum: its default)."""
        return cls(
            int(data.get("holdout_min_signals", 20)),
            float(data.get("gate_min_return_per_day", 0.0)),
            int(data.get("gate_baseline_runs", 1000)),
            float(data.get("gate_baseline_percentile", 95.0)),
            float(data.get("gate_min_return_after_fees", 0.0)),
        )

    def minimum(self, measure: str) -> float:
        """Rule b's minimum for ``measure``."""
        return self.min_return_per_day if measure == PER_DAY else self.min_mean_return

    def to_dict(self) -> Dict[str, Any]:
        return {
            "holdout_min_signals": self.min_entries,
            "gate_min_return_per_day": self.min_return_per_day,
            "gate_min_return_after_fees": self.min_mean_return,
            "gate_baseline_runs": self.runs,
            "gate_baseline_percentile": self.percentile,
        }


SOURCE_WORDS = {
    "exchange": "read from the account",
    "default": "the exchange's published standard rate; the account's own could "
    "not be read",
    "paper": "the paper account's rate",
}


@dataclass(frozen=True)
class Fees:
    rate: float  # a fraction, per side
    order_type: str  # "taker" or "maker"
    exchange: str  # an ExchangeType value, "" when none is known
    source: str  # TradingFees.source, or "none"
    slippage: float = 0.0  # a fraction, per fill

    def text(self) -> str:
        from pt_exchange_abstraction import exchange_name

        who = exchange_name(self.exchange) if self.exchange else "no exchange"
        why = SOURCE_WORDS.get(self.source, self.source)
        return (
            f"{self.rate:.2%} a side ({who} {self.order_type} rate, {why}) and "
            f"{self.slippage:.2%} slippage a fill"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rate": self.rate,
            "order_type": self.order_type,
            "exchange": self.exchange,
            "source": self.source,
            "slippage": self.slippage,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Fees":
        return cls(
            float(data.get("rate") or 0.0),
            str(data.get("order_type") or "taker"),
            str(data.get("exchange") or ""),
            str(data.get("source") or "none"),
            float(data.get("slippage") or 0.0),
        )


def slippage_rate() -> float:
    """The backtester's slippage a fill (backtest.engine.CostModel), a fraction."""
    from backtest.engine import CostModel

    return CostModel().slippage_bps / 1e4


def _account_fees(symbol: str, names: Sequence[str]):
    """The first usable TradingFees of ``names`` (primary first), each read through a
    connector built with the API key saved for it (none saved: its standard rates)."""
    from pt_exchange_abstraction import ExchangeFactory, ExchangeType, usable_fees

    for name in names:
        try:
            connector = ExchangeFactory.get_exchange(ExchangeType(name))
            fees = usable_fees(connector.trading_fees(symbol)) if connector else None
        except Exception:
            fees = None
        if fees is not None:
            return fees
    return None


def _settings_exchanges() -> List[str]:
    from exchange_check import settings_exchanges

    return settings_exchanges()


def trading_fees(
    coin: str,
    exchanges: Optional[Sequence[str]] = None,
    account: Optional[Callable[[str, Sequence[str]], Any]] = None,
    public: Optional[Callable[[str], Any]] = None,
) -> Optional[Fees]:
    """What the trader's orders on ``coin`` pay (see the module docstring), or None
    when no exchange states a rate. ``exchanges`` are the exchanges in Settings,
    primary first (read when None); ``account`` and ``public`` stand in for the
    connectors with saved keys and the public exchange layer (tests)."""
    from pt_exchange_abstraction import TradingFees, dollar_symbol

    symbol = dollar_symbol(coin)
    fees = None
    try:
        names = list(exchanges) if exchanges is not None else _settings_exchanges()
    except Exception:
        names = []
    try:
        fees = (account or _account_fees)(symbol, names) if names else None
    except Exception:
        fees = None
    if fees is None:
        try:
            if public is None:
                from trading_mode import fetch_trading_fees as public
            fees = public(coin)
        except Exception:
            fees = None
    if not isinstance(fees, TradingFees):
        return None
    order_type, rate = fees.for_order(ORDER_TYPE)
    try:
        slip = slippage_rate()
    except Exception:
        slip = 0.0005
    return Fees(float(rate), order_type, fees.exchange, fees.source, slip)


# --- the decision ---------------------------------------------------------------------

MEASURE_NAMES = {
    MEAN_RETURN: "mean return after fees",
    PER_DAY: "return per day held after fees",
}


def _fmt(value: float, measure: str, sign: bool = True) -> str:
    """A score as shown: a return per trade to 0.01%, a return per day to 0.001%."""
    if measure == PER_DAY:
        return (f"{value:+.3%}" if sign else f"{value:.3%}") + " a day"
    return f"{value:+.2%}" if sign else f"{value:.2%}"


@dataclass
class Decision:
    passed: bool
    failed: List[str]  # why it did not pass (empty when it did)
    candidate: Score
    fees: Optional[Fees]
    settings: GateSettings
    baseline: Dict[str, Any] = field(default_factory=dict)  # see summary_of
    current: Optional[float] = None  # the current model's own score (rule f)
    note: str = ""  # anything else the reader should know
    measure: str = (
        MEAN_RETURN  # the score it was judged by (a record before: per trade)
    )

    def value(self) -> Optional[float]:
        return self.candidate.value(self.measure)

    def figure_name(self) -> str:
        """What ``short`` shows, for a sentence: "return after fees" (per trade) or
        "return per day held after fees"."""
        return (
            MEASURE_NAMES[PER_DAY] if self.measure == PER_DAY else "return after fees"
        )

    def headline(self) -> str:
        """ "Return after fees vs random", in one line."""
        value = self.value()
        if value is None:
            return (
                "no entries to score"
                if not self.candidate.entries
                else ("no time held to score")
            )
        m = self.measure
        if m == PER_DAY:
            text = f"{_fmt(value, m)} held after fees"
        else:
            text = f"{value:+.2%} after fees"
        b = self.baseline
        if b:
            text += (
                f" vs random {_fmt(b['median'], m)} (median; "
                f"{ordinal(b['percentile'])} percentile {_fmt(b['at_percentile'], m)}): "
                f"{ordinal(b['rank'], whole=True)} percentile"
            )
        return text

    def short(self) -> str:
        """ "Return after fees vs random" for a table cell."""
        value, b, m = self.value(), self.baseline, self.measure
        if value is None:
            return ""
        if not b:
            return _fmt(value, m)
        if m == PER_DAY:
            return (
                f"{value:+.3%} vs {b['median']:+.3%} a day "
                f"({ordinal(b['rank'], whole=True)} percentile)"
            )
        return (
            f"{value:+.2%} vs {b['median']:+.2%} "
            f"({ordinal(b['rank'], whole=True)} percentile)"
        )

    def entries_text(self) -> str:
        """The candidate's entries and the random runs' ("" with no baseline)."""
        b = self.baseline
        if not b:
            return str(self.candidate.entries) if self.candidate.entries else ""
        return f"{self.candidate.entries} (random {b['entries']:g})"

    def edge_text(self) -> str:
        """The smallest detectable edge, for a table cell ("" when none is recorded)."""
        b = self.baseline
        if not b or b.get("smallest_edge") is None:
            return ""
        text = _fmt(b["smallest_edge"], self.measure, sign=False)
        return f"{text}: too few trades to tell" if b.get("too_few") else text

    def lines(self) -> List[str]:
        """Everything a decision is logged and shown with."""
        c, m = self.candidate, self.measure
        out = [("PASSED" if self.passed else "NOT PASSED") + ": " + self.headline()]
        if c.entries and m == PER_DAY:
            out.append(
                f"entries {c.entries}; return per day held after fees "
                f"{_pct(c.per_day, digits=3)}; mean return after fees per trade "
                f"{_pct(c.mean_return)}; capital-weighted {_pct(c.capital_return)}; "
                f"worst drawdown {_pct(c.drawdown)}; hit rate "
                f"{_pct(c.hit_rate, sign=False)} (shown only, it decides nothing)"
            )
        elif c.entries:
            out.append(
                f"entries {c.entries}; mean return after fees {c.mean_return:+.2%}; "
                f"capital-weighted {_pct(c.capital_return)}; worst drawdown "
                f"{_pct(c.drawdown)}; hit rate {_pct(c.hit_rate, sign=False)} (shown "
                "only, it decides nothing)"
            )
        else:
            out.append("entries 0")
        b = self.baseline
        if b:
            seeds = f"seeds {b['seed']}..{b['seed'] + b['runs'] - 1}"
            if b.get("kind") == SAME_WAITS:
                low, high = b.get("entries_low"), b.get("entries_high")
                counts = (
                    f"{b['runs']} runs of {low} to {high} entries, median "
                    f"{b['entries']:g}"
                    if low != high
                    else f"{b['runs']} runs of {b['entries']:g} entries"
                )
                out.append(
                    "random entries made with the same waits as the candidate's, in "
                    f"random order ({counts}; {seeds}): {MEASURE_NAMES[m]} median "
                    f"{_fmt(b['median'], m)}, {ordinal(b['percentile'])} percentile "
                    f"{_fmt(b['at_percentile'], m)}; worst drawdown median "
                    f"{b['median_drawdown']:+.2%}; the candidate is at the "
                    f"{ordinal(b['rank'], whole=True)} percentile"
                )
            else:
                out.append(
                    f"random entries ({b['runs']} runs of {b['entries']} entries, "
                    f"{seeds}): mean return median {b['median']:+.2%}, "
                    f"{ordinal(b['percentile'])} percentile {b['at_percentile']:+.2%}; "
                    f"worst drawdown median {b['median_drawdown']:+.2%}; the candidate "
                    f"is at the {ordinal(b['rank'], whole=True)} percentile"
                    + (
                        f"; fewer moments than entries in {', '.join(b['short'])}"
                        if b.get("short")
                        else ""
                    )
                )
            if b.get("smallest_edge") is not None:
                out.append(
                    "smallest detectable edge "
                    f"{_fmt(b['smallest_edge'], m, sign=False)}: the gain over the "
                    "random median that would put it above the random entries' "
                    f"{ordinal(b['percentile'])} percentile 4 times in 5"
                    + (
                        "; that is more than half the size of the random median, so "
                        "there are too few trades to tell"
                        if b.get("too_few")
                        else ""
                    )
                )
        if self.current is not None:
            out.append(
                f"current model's own {MEASURE_NAMES[m]} {_fmt(self.current, m)}"
            )
        out.append(
            "fees: "
            + (self.fees.text() if self.fees else "none: no exchange states a rate")
        )
        if self.failed:
            out.append("failed: " + "; ".join(self.failed))
        if self.note:
            out.append(self.note)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "failed": list(self.failed),
            "candidate": self.candidate.to_dict(),
            "fees": self.fees.to_dict() if self.fees else None,
            "settings": self.settings.to_dict(),
            "baseline": dict(self.baseline),
            "current": self.current,
            "note": self.note,
            "measure": self.measure,
            "headline": self.headline(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Decision":
        measure = data.get("measure")
        return cls(
            passed=bool(data.get("passed")),
            failed=list(data.get("failed") or []),
            candidate=Score.from_dict(data.get("candidate") or {}),
            fees=Fees.from_dict(data["fees"]) if data.get("fees") else None,
            settings=GateSettings.from_dict(data.get("settings") or {}),
            baseline=dict(data.get("baseline") or {}),
            current=data.get("current"),
            note=str(data.get("note") or ""),
            measure=measure if measure in MEASURE_NAMES else MEAN_RETURN,
        )


def _pct(value: Optional[float], sign: bool = True, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if sign:
        return f"{value:+.{digits}%}"
    return f"{value:.1%}"


def ordinal(value: float, whole: bool = False) -> str:
    number = int(round(value)) if whole else value
    if not whole and float(number).is_integer():
        number = int(number)
    if isinstance(number, float):
        return f"{number:g}th"
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"


def smallest_edge(spread: float, percentile_: float, power: float = POWER) -> float:
    """The gain over the random median a candidate needs to be above the random runs'
    ``percentile_`` with probability ``power``: (z at the percentile + z at the power)
    x the runs' spread (a normal approximation of their scores)."""
    z = statistics.NormalDist()
    p = min(max(float(percentile_) / 100.0, 1e-6), 1.0 - 1e-6)
    return (z.inv_cdf(p) + z.inv_cdf(power)) * spread


def _whole(value: float):
    return int(value) if float(value).is_integer() else value


def summary_of(
    baseline: Baseline, settings: GateSettings, value: float
) -> Dict[str, Any]:
    median = baseline.median()
    spread = baseline.spread()
    edge = smallest_edge(spread, settings.percentile)
    return {
        "runs": baseline.runs,
        "seed": baseline.seed,
        "kind": baseline.kind,
        "measure": baseline.measure,
        "entries": _whole(percentile(baseline.entries, 50.0)),
        "entries_low": min(baseline.entries),
        "entries_high": max(baseline.entries),
        "median": median,
        "percentile": settings.percentile,
        "at_percentile": baseline.at(settings.percentile),
        "rank": baseline.rank(value),
        "median_drawdown": baseline.median_drawdown(),
        "spread": spread,
        "smallest_edge": edge,
        "too_few": edge > TOO_FEW * abs(median),
        "short": list(baseline.short),
    }


def decide(
    trades: Sequence[Trade],
    slots: Mapping[str, Slots],
    counts: Mapping[str, int],
    settings: GateSettings,
    fees: Optional[Fees],
    seed: int = DEFAULT_SEED,
    current: Optional[float] = None,
    note: str = "",
    measure: str = MEAN_RETURN,
    draw_run: Optional[Callable[[random.Random], Sequence[Optional[Trade]]]] = None,
) -> Decision:
    """The gate's decision on a candidate's ``trades``, by the score ``measure``
    names. The random baseline is ``draw_run``'s runs (same waits) when given, else
    distinct moments: ``counts`` of each group of ``slots`` (the candidate's entries
    per group). ``current`` is the current model's own score, when one is recorded
    (rule f)."""
    cand = score(trades)
    name = MEASURE_NAMES[measure]
    failed: List[str] = []
    if fees is None:
        failed.append("no fee rate: no exchange states one")
    if cand.entries < settings.min_entries:
        failed.append(f"{cand.entries} entries, {settings.min_entries} needed")
    summary: Dict[str, Any] = {}
    if cand.entries:
        value = cand.value(measure)
        minimum = settings.minimum(measure)
        if value is None:
            failed.append(f"{name} cannot be scored: its trades held no time")
        elif not value > minimum:
            failed.append(
                f"{name} {_fmt(value, measure)} is not above {_fmt(minimum, measure)}"
            )
        if cand.capital_return is None or not cand.capital_return > 0.0:
            failed.append(
                f"capital-weighted return after fees {_pct(cand.capital_return)} is "
                "not above 0%"
            )
        if draw_run is not None:
            baseline = run_draws(draw_run, settings.runs, seed, measure, SAME_WAITS)
        else:
            baseline = run_baseline(slots, counts, settings.runs, seed, measure)
        if baseline is None:
            failed.append("no random baseline: no moment a random entry could be made")
        elif value is not None:
            summary = summary_of(baseline, settings, value)
            if not value > summary["at_percentile"]:
                failed.append(
                    f"{name} {_fmt(value, measure)} is not above the random entries' "
                    f"{ordinal(settings.percentile)} percentile "
                    f"{_fmt(summary['at_percentile'], measure)}"
                )
            if not cand.drawdown >= summary["median_drawdown"]:
                failed.append(
                    f"worst drawdown {cand.drawdown:+.2%} is worse than the random "
                    f"entries' median {summary['median_drawdown']:+.2%}"
                )
        if current is not None and value is not None and not value >= current:
            failed.append(
                f"{name} {_fmt(value, measure)} is below the current model's "
                f"{_fmt(current, measure)}"
            )
    return Decision(
        passed=not failed,
        failed=failed,
        candidate=cand,
        fees=fees,
        settings=settings,
        baseline=summary,
        current=current,
        note=note,
        measure=measure,
    )
