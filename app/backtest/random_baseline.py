"""
Random-entry baseline (FDS-MDL section 7 Control; docs/dev/BACKTEST-REPORT-model-1.md).

A random strategy matched to a strategy's trade count *N* and average holding period *H*
(in bars) on the same window, with the same costs, sizing and overlays:

* ``match(trades)``: *N* is the trade count (a position closed on the last bar
  included), *H* the mean of the trades' ``bars_held``, rounded half up, at least 1.
* ``fit_hold(N, H, L)``: *H* reduced one bar at a time while *N* trades of *H* bars do
  not fit in a window of *L* bars (``N(H + 1) > L - 1``); ``None`` if they do not fit
  even at ``H = 1``.
* ``placement(seed, L, N, H)``: the entry bars, drawn uniformly among the placements of
  *N* non-overlapping trades of *H* bars that fit in the window. With
  ``S = L - 1 - N(H + 1)`` and ``c = sorted(random.Random(seed).sample(range(S + N), N))``
  the *k*-th trade (from 0) enters at the open of window bar ``1 + c[k] + k*H`` and exits
  at the open of the bar *H* bars later. The engine fills a decision at the next bar's
  open, one order per bar, so the strategy signals ENTER at the close of the bar before
  each entry and EXIT at the close of the bar before each exit; every exit fills by the
  window's last bar, so no position is force-closed.
* With overlays, an entry an overlay blocks is skipped, not deferred, and after an
  overlay exit the next entry is the next drawn one.

Python guarantees ``random()``'s sequence for a seed across versions, not
``sample()``'s, so the drawn entry bars are recorded with every result and a test pins
one placement on each of ``sample()``'s two code paths.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from strategies.base import Action, Signal, Strategy
from strategies.catalogue import CatalogueError, create, get_entry
from strategies.runner import StrategyRunner

RANDOM_ENTRY_ID = "RANDOM-ENTRY"  # not a catalogue strategy: a control only
# one placement pinned on each of random.sample's two code paths (the header's):
# (seed, L, N, H, SHA-256 of the JSON of the entry bars)
PINNED = (
    (
        0,
        9857,
        100,
        20,
        "6e1c38ca2d11f12a79d058752298d7c4daf078105ed717d455984e404fb6a13a",
    ),
    (
        100,
        2465,
        500,
        3,
        "7c4e0c320a343cb51715d0bba41d78660e27cae19fe8a47d04e30ea6a0b3fcb8",
    ),
)


def match(trades: Sequence[Any]) -> Tuple[int, Optional[int]]:
    """``(N, H)`` of a strategy's trades: ``H`` is ``None`` when ``N`` is 0."""
    n = len(trades)
    if n == 0:
        return 0, None
    mean = sum(int(t.bars_held) for t in trades) / n
    return n, max(1, int(math.floor(mean + 0.5)))  # halves up (round() would be even)


def fit_hold(n: int, h: int, length: int) -> Tuple[Optional[int], bool]:
    """``(H used, reduced?)``: ``H`` lowered one bar at a time while ``N`` trades of
    ``H`` bars do not fit in ``length`` bars; ``(None, True)`` if not even ``H = 1``."""
    if n < 1 or h < 1:
        raise ValueError("fit_hold needs N >= 1 and H >= 1")
    used = h
    while used >= 1 and n * (used + 1) > length - 1:
        used -= 1
    if used < 1:
        return None, True
    return used, used != h


def placement(seed: int, length: int, n: int, h: int) -> List[int]:
    """Window-relative entry bars (0 = the window's first bar) of ``n`` trades of ``h``
    bars, drawn with ``random.Random(seed)``."""
    if n < 1 or h < 1:
        raise ValueError("placement needs N >= 1 and H >= 1")
    slack = length - 1 - n * (h + 1)
    if slack < 0:
        raise ValueError(f"{n} trades of {h} bars do not fit in {length} bars")
    rng = random.Random(seed)
    chosen = sorted(rng.sample(range(slack + n), n))
    return [1 + c + k * h for k, c in enumerate(chosen)]


def check_pins() -> None:
    """``ValueError`` on a Python whose ``random`` draws differently from the pinned
    placements: the control is never drawn there (the recorded entry bars, not new
    draws, are the control)."""
    for seed, length, n, h, digest in PINNED:
        entries = placement(seed, length, n, h)
        if hashlib.sha256(json.dumps(entries).encode()).hexdigest() != digest:
            raise ValueError(
                f"seed {seed} with (L, N, H) = ({length}, {n}, {h}) no longer gives the "
                "pinned placement: this Python's random draws differently"
            )


class RandomEntryStrategy(Strategy):
    """ENTER at the closes before the drawn entry bars and EXIT at the closes before
    their exit bars; HOLD otherwise. Decides by the last bar's ``open_time``."""

    strategy_id = RANDOM_ENTRY_ID

    def __init__(self, enter_times: Iterable, exit_times: Iterable) -> None:
        # not in the catalogue: its only parameters are the drawn decision times
        self.params: Dict[str, Any] = {}
        self._enter = {pd.Timestamp(t) for t in enter_times}
        self._exit = {pd.Timestamp(t) for t in exit_times}
        if self._enter & self._exit:
            raise ValueError("an ENTER and an EXIT on the same bar")

    @property
    def warmup_bars(self) -> int:
        return 1

    @property
    def lookback_bars(self) -> int:
        return 1

    def compute(self, candles: pd.DataFrame) -> Signal:
        t = pd.Timestamp(candles["open_time"].iloc[-1])
        if t in self._enter:
            return Signal(Action.ENTER_LONG, "RANDOM_ENTRY")
        if t in self._exit:
            return Signal(Action.EXIT_LONG, "RANDOM_EXIT")
        return Signal.hold("RANDOM_WAIT")


def build_overlays(overlay_specs: Sequence[Mapping[str, Any]]) -> list:
    """Fresh overlay instances (cooldowns are stateful) from ``[{"id": ..., "params":
    {...}}, ...]``, checked against the catalogue as ``factory.build_runner`` does."""
    built = []
    for spec in overlay_specs:
        oid = spec.get("id")
        if not oid or get_entry(oid)["class_type"] != "risk_overlay":
            raise CatalogueError(f"not a risk overlay: {spec!r}")
        built.append(create(oid, **dict(spec.get("params") or {})))
    return built


def random_runner(
    candles: pd.DataFrame,
    start: int,
    entries: Sequence[int],
    h: int,
    overlay_specs: Sequence[Mapping[str, Any]] = (),
) -> StrategyRunner:
    """A fresh runner whose strategy enters at window-relative ``entries`` (window
    starting at ``candles`` index ``start``) and exits ``h`` bars later."""
    times = candles["open_time"]
    enter_times = [times.iloc[start + e - 1] for e in entries]
    exit_times = [times.iloc[start + e + h - 1] for e in entries]
    return StrategyRunner(
        RandomEntryStrategy(enter_times, exit_times), build_overlays(overlay_specs)
    )


def run_seed(
    candles: pd.DataFrame,
    start: int,
    end: int,
    symbol: str,
    tf: str,
    seed: int,
    n: int,
    h: int,
    overlay_specs: Sequence[Mapping[str, Any]] = (),
    cost=None,
    initial_equity: float = 10_000.0,
) -> Dict[str, Any]:
    """One seed's random strategy on ``candles[start:end]``, with a fresh runner."""
    from backtest.engine import CostModel, run_backtest

    length = end - start
    entries = placement(seed, length, n, h)
    runner = random_runner(candles, start, entries, h, overlay_specs)
    result = run_backtest(
        candles,
        runner,
        symbol,
        tf,
        start,
        end,
        cost if cost is not None else CostModel(),
        initial_equity,
    )
    times = candles["open_time"]
    entered = {pd.Timestamp(t.entry_time) for t in result.trades}
    skipped = [e for e in entries if pd.Timestamp(times.iloc[start + e]) not in entered]
    return {
        "seed": seed,
        "entries": entries,
        "skipped": skipped,
        "trade_count": result.kpis["trade_count"],
        "bars_held": sorted({int(t.bars_held) for t in result.trades}),
        "total_return_pct": result.kpis["total_return_pct"],
    }


def percentile_rank(value: float, sample: Sequence[float]) -> float:
    """100 x (values below ``value`` + half the values equal to it) / len(sample)."""
    if not sample:
        raise ValueError("percentile_rank needs a non-empty sample")
    below = sum(1 for x in sample if x < value)
    equal = sum(1 for x in sample if x == value)
    return 100.0 * (below + 0.5 * equal) / len(sample)
