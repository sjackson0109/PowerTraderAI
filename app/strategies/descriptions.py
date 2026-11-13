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

# The strategy list's words (FDS-SR-001 section 5.8)
FAMILY_NAMES: Dict[str, str] = {
    "trend": "Trend",
    "breakout": "Breakout",
    "momentum": "Momentum",
    "regime": "Market regime",
    "mean_reversion": "Mean reversion",
    "relative_strength": "Relative strength",
    "model": "Trained model",
    "risk_overlay": "Stop or filter",
}
KIND_NAMES: Dict[str, str] = {"main": "Strategy", "risk_overlay": "Stop or filter"}
# what each authorisation allows, as the list shows it
USE_NAMES: Dict[str, str] = {
    "research": "Research only",
    "paper": "Paper",
    "live": "Paper and live",
}
USE_HELP: Dict[str, str] = {
    "research": "Can be used in backtests only, not for trading.",
    "paper": "Can be used for paper trading, not for live trading.",
    "live": "Can be used for paper and live trading.",
}


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
    "STRAT-003": Described(
        name="Trained pattern model",
        summary=(
            "Buys when enough of the trained pattern model's timeframes signal up "
            "and none signals down. Sells when its own timeframe signals down. It "
            "needs a trained model, so it cannot be chosen here."
        ),
        params={
            "model_id": Param("Model", "The trained model it uses."),
            "min_tf_agree": Param(
                "Timeframes that must agree",
                "How many of the counted timeframes must signal up before a buy.",
            ),
            "timeframes": Param(
                "Timeframes counted", "The model's timeframes that are counted."
            ),
        },
    ),
    "STRAT-004": Described(
        name="Donchian breakout",
        summary=(
            "Buys when a daily close is above every close of the previous breakout "
            "days: a new closing high. Sells when a close is below every close of the "
            "previous exit days: a new closing low. The days are calendar days."
        ),
        params={
            "entry_days": Param(
                "Breakout days", "Days of closes a new closing high must beat."
            ),
            "exit_days": Param(
                "Exit days",
                "Days of closes a new closing low must fall below. Must be fewer than "
                "the breakout days.",
            ),
        },
        rules=(
            (
                lambda p: p["exit_days"] < p["entry_days"],
                "The exit days must be fewer than the breakout days.",
            ),
        ),
    ),
    "STRAT-005": Described(
        name="Time-series momentum",
        summary=(
            "On each decision day, counts how many of three past returns are "
            "positive: over the short, middle and long lookback days. Buys when at "
            "least the required number are positive, and sells on a decision day "
            "when fewer are. Between decision days it neither buys nor sells; a stop "
            "can still sell."
        ),
        params={
            "lookback_1": Param("Short lookback days", "Days of the shortest return."),
            "lookback_2": Param(
                "Middle lookback days",
                "Days of the middle return. Must be more than the short lookback.",
            ),
            "lookback_3": Param(
                "Long lookback days",
                "Days of the longest return. Must be more than the middle lookback. "
                "A coin needs this many days of candles before its first decision.",
            ),
            "min_agree": Param(
                "Returns that must be positive",
                "How many of the three returns must be above 0 to hold the coin.",
            ),
            "rebalance_days": Param(
                "Days between decisions",
                "Decision days are counted from Monday 6 January 2020: one every "
                "this many days. 7 decides every Monday.",
            ),
        },
        rules=(
            (
                lambda p: p["lookback_1"] < p["lookback_2"] < p["lookback_3"],
                "Each lookback must be more than the one before.",
            ),
        ),
    ),
    "STRAT-006": Described(
        name="Price above its average",
        summary=(
            "Buys when a daily close is above the simple average of the last "
            "average days of closes, that close included. Sells when a close is "
            "below it. A close equal to the average changes nothing."
        ),
        params={
            "average_days": Param(
                "Average days",
                "How many days of closes the average takes. A coin needs this many "
                "days of candles before its first decision.",
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
    "OVL-REGIME": Described(
        name="Market regime filter",
        summary=(
            "Allows a buy only while the reference coin's last daily close is above "
            "its average over the average days. It never sells. With no daily "
            "candles for the reference, or only old ones, it allows no buy."
        ),
        params={
            "reference": Param(
                "Reference",
                "The coin whose trend is checked: Bitcoin, or the coin being bought.",
                choices={"BTC": "Bitcoin", "self": "The coin itself"},
            ),
            "sma_days": Param(
                "Average days", "Days of daily closes in the simple average."
            ),
        },
    ),
    "STRAT-007": Described(
        name="Breakout with a midline exit",
        summary=(
            "Buys when a daily close is above every close of the previous channel "
            "days. Sells when a close is below the midline of those closes, halfway "
            "between the highest and the lowest. With the midline stop ticked, the "
            "stop never moves down."
        ),
        params={
            "channel_days": Param(
                "Channel days",
                "How many days of closes the channel takes. A coin needs this many "
                "days of candles before its first decision.",
            ),
        },
    ),
    "OVL-MIDLINE": Described(
        name="Midline stop",
        summary=(
            "While a coin is held, sets the stop at the midline of the previous "
            "days' closes, halfway between the highest and the lowest. The stop "
            "never moves down. A close below it sells."
        ),
        params={
            "days": Param("Days", "How many days of closes the midline is taken from."),
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
