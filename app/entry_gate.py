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

Candidates
----------
A trained model of one coin (model_gate: its entries on its held-out bars), the paper
signals of one LLM provider/model/prompt version (llm_gate), or any entry filter. A
candidate gives its trades (``Trade``), and for the random baseline the trade a random
entry would have made at each moment it could have entered (``Slots``), in groups: the
same coin, and for an LLM signal also the same direction, horizon, target and stop.
Every slot's trade is replayed with exactly the rules the candidate's trades were: the
same sizing, exits, DCA, trailing, stops and the same treatment of a trade still open
when the held-out bars end.

The random baseline
-------------------
``gate_baseline_runs`` runs (1000). Run k draws, with ``random.Random(seed + k)``, as
many distinct slots from each group as the candidate made entries in that group (all of
them when the group has fewer). Draws use only ``random()``, whose sequence Python keeps
for a seed across versions, so a recorded seed repeats a run exactly.

The pass rule (all must hold)
-----------------------------
a. at least ``holdout_min_signals`` entries;
b. mean return after fees per trade above ``gate_min_return_after_fees`` (0%);
c. capital-weighted return after fees (profit over all capital committed, DCA buys
   included) above 0%;
d. mean return after fees above the ``gate_baseline_percentile`` (95th) percentile of the
   random runs' mean returns;
e. worst drawdown no worse than the median of the random runs' worst drawdowns;
f. where a current model has a recorded score, a mean return after fees not below the
   current model's own (each on its own held-out bars).

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
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

DEFAULT_SEED = 0  # run k of a baseline uses random.Random(DEFAULT_SEED + k)
ORDER_TYPE = "market"  # the trader's entry, DCA and exit orders (pt_trader.py)


# --- trades and their score -----------------------------------------------------------


@dataclass(frozen=True)
class Trade:
    """One trade, replayed. ``net`` is its profit after fees and slippage, in the
    account's money; ``committed`` the capital put in (the entry and every DCA buy,
    fees included); ``drawdown`` its worst fall below its average cost while it was
    open, a fraction (0 or less); ``hit`` whether it counts as a win (the hit rate is
    shown, never decides); ``end`` the index it ended at (replays that hold one trade
    at a time read it)."""

    net: float
    committed: float
    drawdown: float
    hit: bool
    end: int = -1

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entries": self.entries,
            "mean_return": self.mean_return,
            "capital_return": self.capital_return,
            "drawdown": self.drawdown,
            "hit_rate": self.hit_rate,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Score":
        return cls(
            int(data.get("entries") or 0),
            data.get("mean_return"),
            data.get("capital_return"),
            data.get("drawdown"),
            data.get("hit_rate"),
        )


def score(trades: Sequence[Trade]) -> Score:
    if not trades:
        return Score(0, None, None, None, None)
    committed = sum(t.committed for t in trades)
    return Score(
        entries=len(trades),
        mean_return=sum(t.ret for t in trades) / len(trades),
        capital_return=(sum(t.net for t in trades) / committed) if committed else None,
        drawdown=min(t.drawdown for t in trades),
        hit_rate=sum(1 for t in trades if t.hit) / len(trades),
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
    means: Tuple[float, ...]  # each run's mean return after fees
    drawdowns: Tuple[float, ...]  # each run's worst drawdown
    entries: int  # entries drawn in each run
    short: Tuple[str, ...] = ()  # groups with fewer slots than the candidate's entries

    def median(self) -> float:
        return percentile(self.means, 50.0)

    def at(self, p: float) -> float:
        return percentile(self.means, p)

    def median_drawdown(self) -> float:
        return percentile(self.drawdowns, 50.0)

    def rank(self, mean_return: float) -> float:
        return percentile_rank(mean_return, self.means)


def run_baseline(
    slots: Mapping[str, Slots],
    counts: Mapping[str, int],
    runs: int,
    seed: int = DEFAULT_SEED,
) -> Optional[Baseline]:
    """``runs`` random baselines: run k draws ``counts[group]`` slots of each group
    (groups in sorted order) with ``random.Random(seed + k)``. A slot's trade is
    replayed once and reused. None when no run gets a trade."""
    cache: Dict[Tuple[str, int], Optional[Trade]] = {}
    groups = sorted(g for g in slots if counts.get(g, 0) > 0)
    short = tuple(g for g in groups if slots[g].size < counts[g])
    means: List[float] = []
    drawdowns: List[float] = []
    entries = sum(min(counts[g], slots[g].size) for g in groups)
    for k in range(int(runs)):
        rng = random.Random(int(seed) + k)
        trades: List[Trade] = []
        for g in groups:
            for i in draw(rng, slots[g].size, counts[g]):
                key = (g, i)
                if key not in cache:
                    cache[key] = slots[g].trade(i)
                if cache[key] is not None:
                    trades.append(cache[key])
        if trades:
            means.append(sum(t.ret for t in trades) / len(trades))
            drawdowns.append(min(t.drawdown for t in trades))
    if not means:
        return None
    return Baseline(
        len(means), int(seed), tuple(means), tuple(drawdowns), entries, short
    )


# --- settings and fees ----------------------------------------------------------------


@dataclass(frozen=True)
class GateSettings:
    min_entries: int = 20
    min_return: float = 0.0  # a fraction
    runs: int = 1000
    percentile: float = 95.0

    @classmethod
    def from_training(cls, training: Mapping[str, Any]) -> "GateSettings":
        """From the ``training`` section (training_settings.normalise)."""
        return cls(
            int(training["holdout_min_signals"]),
            float(training["gate_min_return_after_fees"]),
            int(training["gate_baseline_runs"]),
            float(training["gate_baseline_percentile"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "holdout_min_signals": self.min_entries,
            "gate_min_return_after_fees": self.min_return,
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


@dataclass
class Decision:
    passed: bool
    failed: List[str]  # why it did not pass (empty when it did)
    candidate: Score
    fees: Optional[Fees]
    settings: GateSettings
    baseline: Dict[str, Any] = field(default_factory=dict)  # see summary_of
    current: Optional[float] = None  # the current model's own mean return (rule f)
    note: str = ""  # anything else the reader should know

    def headline(self) -> str:
        """ "Return after fees vs random", in one line."""
        c = self.candidate
        if c.mean_return is None:
            return "no entries to score"
        text = f"{c.mean_return:+.2%} after fees"
        b = self.baseline
        if b:
            text += (
                f" vs random {b['median']:+.2%} (median; "
                f"{ordinal(b['percentile'])} percentile {b['at_percentile']:+.2%}): "
                f"{ordinal(b['rank'], whole=True)} percentile"
            )
        return text

    def short(self) -> str:
        """ "Return after fees vs random" for a table cell."""
        c, b = self.candidate, self.baseline
        if c.mean_return is None:
            return ""
        if not b:
            return f"{c.mean_return:+.2%}"
        return (
            f"{c.mean_return:+.2%} vs {b['median']:+.2%} "
            f"({ordinal(b['rank'], whole=True)} percentile)"
        )

    def lines(self) -> List[str]:
        """Everything a decision is logged and shown with."""
        c = self.candidate
        out = [("PASSED" if self.passed else "NOT PASSED") + ": " + self.headline()]
        if c.entries:
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
            out.append(
                f"random entries ({b['runs']} runs of {b['entries']} entries, {seeds}): "
                f"mean return median {b['median']:+.2%}, "
                f"{ordinal(b['percentile'])} percentile {b['at_percentile']:+.2%}; "
                f"worst drawdown median {b['median_drawdown']:+.2%}; the candidate is "
                f"at the {ordinal(b['rank'], whole=True)} percentile"
                + (
                    f"; fewer moments than entries in {', '.join(b['short'])}"
                    if b.get("short")
                    else ""
                )
            )
        if self.current is not None:
            out.append(
                f"current model's own mean return after fees {self.current:+.2%}"
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
            "headline": self.headline(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Decision":
        s = data.get("settings") or {}
        return cls(
            passed=bool(data.get("passed")),
            failed=list(data.get("failed") or []),
            candidate=Score.from_dict(data.get("candidate") or {}),
            fees=Fees.from_dict(data["fees"]) if data.get("fees") else None,
            settings=GateSettings(
                int(s.get("holdout_min_signals", 20)),
                float(s.get("gate_min_return_after_fees", 0.0)),
                int(s.get("gate_baseline_runs", 1000)),
                float(s.get("gate_baseline_percentile", 95.0)),
            ),
            baseline=dict(data.get("baseline") or {}),
            current=data.get("current"),
            note=str(data.get("note") or ""),
        )


def _pct(value: Optional[float], sign: bool = True) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2%}" if sign else f"{value:.1%}"


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


def summary_of(
    baseline: Baseline, settings: GateSettings, mean: float
) -> Dict[str, Any]:
    return {
        "runs": baseline.runs,
        "seed": baseline.seed,
        "entries": baseline.entries,
        "median": baseline.median(),
        "percentile": settings.percentile,
        "at_percentile": baseline.at(settings.percentile),
        "rank": baseline.rank(mean),
        "median_drawdown": baseline.median_drawdown(),
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
) -> Decision:
    """The gate's decision on a candidate's ``trades`` (``counts``: its entries per
    group of ``slots``). ``current`` is the current model's own mean return after
    fees, when one is recorded (rule f)."""
    cand = score(trades)
    failed: List[str] = []
    if fees is None:
        failed.append("no fee rate: no exchange states one")
    if cand.entries < settings.min_entries:
        failed.append(f"{cand.entries} entries, {settings.min_entries} needed")
    summary: Dict[str, Any] = {}
    if cand.entries:
        if not cand.mean_return > settings.min_return:
            failed.append(
                f"mean return after fees {cand.mean_return:+.2%} is not above "
                f"{settings.min_return:+.2%}"
            )
        if cand.capital_return is None or not cand.capital_return > 0.0:
            failed.append(
                f"capital-weighted return after fees {_pct(cand.capital_return)} is "
                "not above 0%"
            )
        baseline = run_baseline(slots, counts, settings.runs, seed)
        if baseline is None:
            failed.append("no random baseline: no moment a random entry could be made")
        else:
            summary = summary_of(baseline, settings, cand.mean_return)
            if not cand.mean_return > summary["at_percentile"]:
                failed.append(
                    f"mean return after fees {cand.mean_return:+.2%} is not above the "
                    f"random entries' {ordinal(settings.percentile)} percentile "
                    f"{summary['at_percentile']:+.2%}"
                )
            if not cand.drawdown >= summary["median_drawdown"]:
                failed.append(
                    f"worst drawdown {cand.drawdown:+.2%} is worse than the random "
                    f"entries' median {summary['median_drawdown']:+.2%}"
                )
        if current is not None and not cand.mean_return >= current:
            failed.append(
                f"mean return after fees {cand.mean_return:+.2%} is below the current "
                f"model's {current:+.2%}"
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
    )
