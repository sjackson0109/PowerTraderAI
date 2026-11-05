"""
The words Settings > Strategy shows: each strategy's and stop's name, what it buys
and sells on, and a label and a description for each of its parameters.

On screen text states facts and textbook definitions only. Every catalogue strategy
that the window offers (not one that needs a trained model) and every overlay has an
entry here, with every parameter: tests/test_strategy_settings_ui.py checks that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from market_data.timeframes import TIMEFRAME_SECONDS

TIMEFRAME_NAMES: Dict[str, str] = {
    "1m": "1 minute",
    "3m": "3 minutes",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "30m": "30 minutes",
    "1h": "1 hour",
    "2h": "2 hours",
    "4h": "4 hours",
    "6h": "6 hours",
    "8h": "8 hours",
    "12h": "12 hours",
    "1d": "1 day",
}

ENGINE_NAMES: Dict[str, str] = {
    "catalogue": "Rule-based strategy",
    "legacy_neural": "Neural levels, DCA and trailing profit margin",
}
ENGINE_HELP: Dict[str, str] = {
    "catalogue": (
        "The strategy below decides each buy and sale from closed candles. Each buy "
        "is the Start allocation % in Settings > Risk. The trade start level, DCA and "
        "trailing profit margin settings are not used."
    ),
    "legacy_neural": (
        "Buys when the thinker's long level reaches the trade start level and its "
        "short level is 0, then adds DCA buys and sells by the trailing profit "
        "margin. Those are set in Settings. The rule-based strategy's settings are "
        "not used."
    ),
}

STOPS_HELP = (
    "Stops are checked when each candle closes: a candle that closes below the "
    "stop sells the coin at the market price. With more than one stop ticked, the "
    "highest one applies. A stop never moves down."
)


@dataclass(frozen=True)
class Param:
    label: str
    help: str
    step: float = 1  # the arrows' step for a number
    choices: Mapping[Any, str] = field(default_factory=dict)  # value -> shown


Rule = Tuple[Callable[[Mapping[str, Any]], bool], str]  # (holds?, why not)


@dataclass(frozen=True)
class Described:
    name: str
    summary: str
    params: Mapping[str, Param]
    rules: Tuple[Rule, ...] = ()


def _slow_above_fast(what: str) -> Rule:
    return (
        lambda p: p["slow_len"] > p["fast_len"],
        f"The slow {what} length must be more than the fast {what} length.",
    )


DESCRIPTIONS: Dict[str, Described] = {
    "STRAT-000": Described(
        name="EMA crossover",
        summary=(
            "Buys when the fast EMA crosses above the slow EMA on a closed candle. "
            "Sells when a candle closes with the fast EMA below the slow EMA. An EMA "
            "(exponential moving average) averages the closes, weighting recent "
            "candles more."
        ),
        params={
            "fast_len": Param("Fast EMA length", "Candles in the fast average."),
            "slow_len": Param(
                "Slow EMA length",
                "Candles in the slow average. Must be more than the fast length.",
            ),
        },
        rules=(_slow_above_fast("EMA"),),
    ),
    "STRAT-001": Described(
        name="Trend crossover (DEMA/TEMA)",
        summary=(
            "Buys once per cross: when the fast average crosses above the slow "
            "average and is still above it after the confirmation candles. With the "
            "trend-strength filter on, the ADX on that candle must also be at least "
            "the minimum ADX. Sells when a candle closes with the fast average below "
            "the slow average."
        ),
        params={
            "ma_type": Param(
                "Moving average",
                "DEMA (double exponential) and TEMA (triple exponential) moving "
                "averages follow the price more closely than an EMA of the same "
                "length; TEMA the most.",
                choices={"DEMA": "DEMA", "TEMA": "TEMA"},
            ),
            "fast_len": Param("Fast average length", "Candles in the fast average."),
            "slow_len": Param(
                "Slow average length",
                "Candles in the slow average. Must be more than the fast length.",
            ),
            "persistence_bars": Param(
                "Confirmation candles",
                "Closed candles the fast average must stay above the slow average "
                "after the cross before the buy. 0 buys on the candle of the cross.",
            ),
            "regime_filter": Param(
                "Trend-strength filter",
                "ADX (average directional index) measures how strong a trend is, "
                "from 0 to 100, whichever way it runs.",
                choices={"none": "Off", "adx": "ADX"},
            ),
            "adx_len": Param("ADX length", "Candles the ADX is averaged over."),
            "adx_min": Param("Minimum ADX", "With the filter on, the ADX a buy needs."),
        },
        rules=(_slow_above_fast("average"),),
    ),
    "STRAT-002": Described(
        name="Supertrend",
        summary=(
            "The Supertrend line sits a multiple of the ATR below the price in an "
            "up-trend and above it in a down-trend. Buys once the trend turns up and "
            "stays up for the confirmation candles. Sells when a candle closes below "
            "the line. ATR (average true range) is the average size of a candle's "
            "range, gaps included."
        ),
        params={
            "atr_len": Param("ATR length", "Candles the ATR is averaged over."),
            "mult": Param(
                "ATR multiple",
                "How many ATRs the line sits from the price. A larger multiple "
                "leaves more room before a sale.",
                step=0.5,
            ),
            "confirm_bars": Param(
                "Confirmation candles",
                "Closed candles the up-trend must last after it turns up before "
                "the buy. 0 buys on the candle it turns up.",
            ),
        },
    ),
    "OVL-RATCHET": Described(
        name="Ratchet stop",
        summary=(
            "Once the gain reaches the start gain, sets a stop at the first stop % "
            "above the buy price. Each further step of gain raises the stop by one "
            "step. Gains are from the buy price to the highest close since."
        ),
        params={
            "trigger_pct": Param(
                "Start at gain %", "The gain at which the stop is set.", step=0.5
            ),
            "lock_pct": Param(
                "First stop %",
                "The first stop, as a gain on the buy price. Must be below the "
                "start gain.",
                step=0.5,
            ),
            "step_pct": Param(
                "Step %",
                "Each further step of gain raises the stop by this much.",
                step=0.5,
            ),
        },
        rules=(
            (
                lambda p: p["lock_pct"] < p["trigger_pct"],
                "The first stop % must be below the start gain %.",
            ),
        ),
    ),
    "OVL-ATR": Described(
        name="ATR trailing stop",
        summary="The stop is the highest close since the buy minus a multiple of the ATR.",
        params={
            "atr_len": Param("ATR length", "Candles the ATR is averaged over."),
            "mult": Param(
                "ATR multiple",
                "How many ATRs the stop sits below the highest close.",
                step=0.5,
            ),
        },
    ),
    "OVL-PLOCK": Described(
        name="Profit lock stages",
        summary=(
            "Each stage is a gain and a lock. When the gain reaches a stage's gain, "
            "the stop is at least the buy price plus its lock. Gains are from the "
            "buy price to the highest close since."
        ),
        params={
            "stages": Param(
                "Stages (gain %:lock %)",
                "For example 3:1, 6:3, 10:6: at a 3% gain the stop is 1% above the "
                "buy price, at 6% it is 3% above, at 10% it is 6% above.",
            ),
        },
    ),
    "OVL-COOLDOWN": Described(
        name="Pause after a sale",
        summary=(
            "After a sale, no new buy in that coin for a number of candles, or for "
            "longer after a sale at a loss."
        ),
        params={
            "bars_after_exit": Param(
                "Candles after a sale", "Candles with no new buy after any sale."
            ),
            "bars_after_loss": Param(
                "Candles after a loss",
                "Candles with no new buy after a sale below the buy price. The "
                "longer of the two applies.",
            ),
            "global": Param(
                "Pause every coin", "A sale in any coin pauses buys in every coin."
            ),
        },
    ),
}


def timeframe_name(tf: Any) -> str:
    """``"4h"`` -> ``"4 hours"``; an unknown one is shown as it is."""
    return TIMEFRAME_NAMES.get(tf, str(tf))


def candle_name(tf: Any) -> str:
    """``"4h"`` -> ``"4-hour"``, as in "4-hour candles"."""
    count, _, unit = timeframe_name(tf).partition(" ")
    return f"{count}-{unit[:-1] if unit.endswith('s') else unit}" if unit else count


def timeframes() -> Tuple[str, ...]:
    """The strategy timeframes, shortest first."""
    return tuple(sorted(TIMEFRAME_SECONDS, key=TIMEFRAME_SECONDS.__getitem__))


def name_of(strategy_id: Any) -> str:
    """A strategy's or stop's name; an unknown id is shown as it is."""
    entry = DESCRIPTIONS.get(strategy_id)
    return entry.name if entry is not None else str(strategy_id)


def rule_problem(strategy_id: str, params: Mapping[str, Any]) -> Optional[str]:
    """The first rule between two parameters that ``params`` breaks, in plain words."""
    entry = DESCRIPTIONS.get(strategy_id)
    for holds, why in entry.rules if entry is not None else ():
        if not holds(params):
            return why
    return None


def summary_line(settings: Any) -> str:
    """One line for Settings: what is trading, e.g. "Trend crossover (DEMA/TEMA)
    on 1-hour candles; stops and filters: Ratchet stop"."""
    if settings.problem:
        return "The saved strategy settings are refused: no orders are placed."
    if settings.is_legacy:
        return ENGINE_NAMES["legacy_neural"]
    extras = ", ".join(name_of(o["id"]) for o in settings.overlays) or "none"
    return (
        f"{name_of(settings.active_id)} on {candle_name(settings.timeframe)} "
        f"candles; stops and filters: {extras}"
    )
