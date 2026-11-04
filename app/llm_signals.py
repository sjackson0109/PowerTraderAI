"""
LLM trade signals: reading one from a model's answer, and scoring it after fees
against what the price did.

Reading
-------
``parse_signal(text)`` takes the first JSON object in the answer: ``direction``
(BUY, SELL or HOLD; LONG and SHORT are read as BUY and SELL), ``strength``
(very_bearish ... very_bullish), ``confidence`` (0-100), ``price_target``,
``stop_loss``, ``time_horizon`` (SHORT, MEDIUM or LONG) and ``reasoning``. An answer
with no direction is kept with ``direction`` None: it is never used in trading.

Scoring (the backtester's fee-adjusted rules)
----------------------------------------------
A BUY is a long from the price when the signal was made; a SELL the mirror (a gain
when the price falls). The trade fills like the backtester's (backtest.engine): a
buy at ``price * (1 + slippage)``, a sell at ``price * (1 - slippage)``, and a fee
on each side. It ends at the first hourly bar that reaches the stop loss (the stop
is taken first when one bar reaches both) or the price target, else at the close of
the last bar within the time horizon (SHORT 1 day, MEDIUM 7 days, LONG 30 days). A
signal wins when its return after fees and slippage is above zero, as in the model
gate design ("a win means the net gain beats the fees"). HOLD signals are not
scored: they say nothing to win or lose on.

Fees: the taker rate of the connected exchange (primary first) from its connector's
``trading_fees()`` when it has one; no connector has one yet, so the backtester's
cost model is used (``backtest.engine.CostModel``: 0.10% a side, 0.05% slippage a
fill).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

DIRECTIONS = ("BUY", "SELL", "HOLD")
STRENGTHS = ("very_bearish", "bearish", "neutral", "bullish", "very_bullish")
HORIZONS = ("SHORT", "MEDIUM", "LONG")
HORIZON_HOURS = {"SHORT": 24, "MEDIUM": 24 * 7, "LONG": 24 * 30}
_ALIASES = {"LONG": "BUY", "SHORT": "SELL", "NEUTRAL": "HOLD", "WAIT": "HOLD"}
_DEFAULT_STRENGTH = {"BUY": "bullish", "SELL": "bearish", "HOLD": "neutral"}


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        value = value.replace(",", "").replace("$", "").strip()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first_json_object(text: str) -> Optional[dict]:
    """The first JSON object in ``text`` (a fenced block or bare braces)."""
    for match in re.finditer(r"\{", text or ""):
        depth = 0
        for end in range(match.start(), len(text)):
            ch = text[end]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[match.start() : end + 1])
                    except ValueError:
                        break
                    if isinstance(data, dict):
                        return data
                    break
    return None


def parse_signal(text: str) -> Dict[str, Any]:
    """The signal in a model's answer (see the module docstring)."""
    data = _first_json_object(text) or {}
    raw = str(
        data.get("direction") or data.get("signal_type") or data.get("signal") or ""
    )
    word = raw.strip().upper()
    direction = _ALIASES.get(word, word) if word else None
    if direction not in DIRECTIONS:
        direction = None
    strength = str(data.get("strength") or "").strip().lower().replace(" ", "_")
    if strength not in STRENGTHS:
        strength = _DEFAULT_STRENGTH.get(direction or "HOLD", "neutral")
    confidence = _number(data.get("confidence"))
    if confidence is not None:
        if 0 < confidence <= 1:
            confidence *= 100.0  # a fraction
        confidence = max(0.0, min(100.0, confidence))
    horizon = str(data.get("time_horizon") or "").strip().upper()
    if horizon not in HORIZONS:
        horizon = "MEDIUM"
    target = _number(data.get("price_target"))
    stop = _number(data.get("stop_loss"))
    reasoning = str(data.get("reasoning") or "").strip()
    if not data:
        reasoning = (text or "").strip()[:2000]
    return {
        "direction": direction,
        "strength": strength,
        "confidence": confidence,
        "price_target": target if target and target > 0 else None,
        "stop_loss": stop if stop and stop > 0 else None,
        "time_horizon": horizon,
        "reasoning": reasoning,
    }


def analysis_signal(text: str) -> Optional[str]:
    """The ``SIGNAL: BUY|SELL|HOLD`` line an analysis ends with, or None."""
    found = re.findall(r"SIGNAL\s*[:=]\s*\**\s*([A-Za-z]+)", text or "", re.IGNORECASE)
    if not found:
        return None
    word = found[-1].upper()
    word = _ALIASES.get(word, word)
    return word if word in DIRECTIONS else None


# --- costs -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Costs:
    fee_rate: float  # a fraction, per side
    slippage_rate: float  # a fraction, per fill
    source: str  # where the fee came from

    def text(self) -> str:
        return (
            f"{self.fee_rate:.2%} fee a side and {self.slippage_rate:.2%} slippage "
            f"a fill ({self.source})"
        )


def backtest_costs() -> Costs:
    from backtest.engine import CostModel

    model = CostModel()
    return Costs(
        model.fee_bps / 1e4, model.slippage_bps / 1e4, "the backtester's costs"
    )


def trade_costs(layer: Optional[Callable[[], Any]] = None) -> Costs:
    """The taker fee of the connected exchange (primary first) when a connector
    states one, else the backtester's costs; slippage is the backtester's."""
    base = backtest_costs()
    try:
        from pt_exchange_abstraction import ExchangeType

        if layer is None:
            from pt_multi_exchange import market_exchanges as layer
        connected = layer().exchange_manager
        ordered = [
            (name, connected.exchanges[ExchangeType(name)])
            for name in connected.exchange_names()
        ]
    except Exception:
        return base
    for exchange_type, connector in ordered:
        fees = getattr(connector, "trading_fees", None)
        if not callable(fees):
            continue
        try:
            answer = fees()
        except Exception:
            continue
        taker = _number(answer.get("taker")) if isinstance(answer, dict) else None
        if taker is not None and 0.0 <= taker < 1.0:
            from pt_exchange_abstraction import exchange_name

            return Costs(
                taker, base.slippage_rate, f"{exchange_name(exchange_type)} taker fee"
            )
    return base


# --- scoring -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    outcome: str  # "target", "stop", "horizon"
    exit_price: float
    net_return: float  # after fees and slippage, a fraction
    hit: bool
    ended_ms: int


def net_return(direction: str, entry: float, exit_price: float, costs: Costs) -> float:
    """The return after fees and slippage of a long (BUY) or its mirror (SELL)."""
    f, s = costs.fee_rate, costs.slippage_rate
    if direction == "BUY":
        bought = entry * (1 + s)
        sold = exit_price * (1 - s)
        return (1 - f) * (sold / bought) * (1 - f) - 1.0
    sold = entry * (1 - s)
    bought = exit_price * (1 + s)
    return (1 - f) * (sold / bought) * (1 - f) - 1.0


def score_signal(
    direction: Optional[str],
    entry: Optional[float],
    signal_ms: int,
    horizon: str,
    target: Optional[float],
    stop: Optional[float],
    bars: Sequence[Sequence[float]],
    costs: Costs,
    now_ms: int,
) -> Optional[Outcome]:
    """The outcome of a BUY or SELL signal made at ``signal_ms`` at ``entry``, from
    the hourly ``bars`` ([open_ms, open, high, low, close, volume], oldest first) that
    opened after it; None while it is still open (or cannot be scored)."""
    if direction not in ("BUY", "SELL") or not entry or entry <= 0:
        return None
    hours = HORIZON_HOURS.get(horizon, HORIZON_HOURS["MEDIUM"])
    end_ms = signal_ms + hours * 3600 * 1000
    if direction == "BUY":
        target = target if target and target > entry else None
        stop = stop if stop and stop < entry else None
    else:
        target = target if target and target < entry else None
        stop = stop if stop and stop > entry else None
    last = None
    for bar in bars:
        opened = int(bar[0])
        if opened < signal_ms:
            continue
        if opened + 3600 * 1000 > end_ms:
            break
        high, low = float(bar[2]), float(bar[3])
        last = bar
        if direction == "BUY":
            if stop is not None and low <= stop:
                return _outcome("stop", direction, entry, stop, costs, opened)
            if target is not None and high >= target:
                return _outcome("target", direction, entry, target, costs, opened)
        else:
            if stop is not None and high >= stop:
                return _outcome("stop", direction, entry, stop, costs, opened)
            if target is not None and low <= target:
                return _outcome("target", direction, entry, target, costs, opened)
    if now_ms < end_ms or last is None:
        return None  # the horizon has not passed, or no bar covers it
    return _outcome("horizon", direction, entry, float(last[4]), costs, int(last[0]))


def _outcome(kind, direction, entry, exit_price, costs, ended_ms) -> Outcome:
    net = net_return(direction, entry, exit_price, costs)
    return Outcome(kind, float(exit_price), net, net > 0.0, int(ended_ms))


OUTCOME_WORDS = {
    "target": "target reached",
    "stop": "stop reached",
    "horizon": "horizon ended",
}


def outcome_text(outcome: Optional[str]) -> str:
    return OUTCOME_WORDS.get(outcome or "", outcome or "")


def signal_summary(signals: Sequence[Any]) -> Dict[str, Any]:
    """Counts for a set of signal records: shown, scored, won, hit rate and the mean
    return after fees of the scored ones."""
    scored = [s for s in signals if s.hit is not None]
    won = sum(1 for s in scored if s.hit)
    returns: List[float] = [s.net_return for s in scored if s.net_return is not None]
    return {
        "signals": len(signals),
        "scored": len(scored),
        "won": won,
        "hit_rate": (won / len(scored)) if scored else None,
        "mean_return": (sum(returns) / len(returns)) if returns else None,
    }
