"""The pattern model the trainer writes, and the neural runner's use of it (FDS-MDL).

A model is the five files per timeframe that ``pt_pattern_trainer.py`` writes (memories,
the three weight lists and the match threshold). ``TimeframeModel.predict`` is
``pt_thinker.step_coin``'s per-timeframe computation, reproduced operation for
operation: the body % of the last closed bar is matched against every memory with the
thinker's difference formula and threshold, the matched memories' moves are averaged
(skipping zero weights, summed in memory order) and the predicted high and low prices
follow from the bar's close. Any parse problem the thinker would hit makes the timeframe
inactive with a "training data issue", as in the thinker.

``validation_metrics`` scores a frozen model on bars it was not trained on (FDS-MDL
Phase 2: the last 20% of the training window).

``thinker_decision`` is the runner's signal rule at the end of a sweep (FDS-MDL Phase 3,
STRAT-003): the bounds rebuilt from the predictions, the gap pass, the remap back to
timeframe order and the LONG/SHORT comparison with the current price, statement for
statement, quirks included.
"""

import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

TIMEFRAMES = ("1hour", "2hour", "4hour", "8hour", "12hour", "1day", "1week")
# the candle timeframe each model timeframe is trained on and predicts from
CANDLE_TF = {
    "1hour": "1h",
    "2hour": "2h",
    "4hour": "4h",
    "8hour": "8h",
    "12hour": "12h",
    "1day": "1d",
    "1week": "1w",
}
FILE_KINDS = (
    "neural_perfect_threshold",
    "memories",
    "memory_weights",
    "memory_weights_high",
    "memory_weights_low",
)


def model_file_names() -> List[str]:
    return sorted(f"{kind}_{tf}.txt" for kind in FILE_KINDS for tf in TIMEFRAMES)


def _strip(text: str) -> str:
    """The thinker's clean-up chain (and the trainer's)."""
    return (
        text.replace("'", "")
        .replace(",", "")
        .replace('"', "")
        .replace("]", "")
        .replace("[", "")
    )


def _number(text: str):
    """``(float(text), True)``, or ``(nan, False)`` where the thinker's ``float()``
    raises. A "nan" in the file parses (the thinker does not raise on it)."""
    try:
        return float(text), True
    except (TypeError, ValueError):
        return math.nan, False


def _numbers(texts):
    values, ok = zip(*(_number(t) for t in texts)) if texts else ((), ())
    return np.array(values, dtype=float), np.array(ok, dtype=bool)


class ModelFormatError(ValueError):
    """A threshold file the thinker cannot read (it stops the thinker)."""


@dataclass
class Prediction:
    active: bool
    training_issue: bool
    move_pct: float  # predicted close move, % (the thinker's final_moves)
    high_frac: float  # predicted high move as a fraction (high_final_moves)
    low_frac: float  # predicted low move as a fraction (low_final_moves)
    start_price: float  # the bar's close
    high_price: float  # the thinker's high_tf_prices entry
    low_price: float  # the thinker's low_tf_prices entry
    matched: int


class TimeframeModel:
    """One timeframe's files, parsed once the way the thinker parses them every step."""

    def __init__(
        self, threshold_text, memories_text, weights, high_weights, low_weights
    ):
        try:
            self.threshold = float(threshold_text)
        except (TypeError, ValueError) as exc:
            raise ModelFormatError(f"threshold {threshold_text!r}: {exc}") from None
        self.memory_list = _strip(memories_text).split("~")
        weight_list = _strip(weights).split(" ")
        high_list = _strip(high_weights).split(" ")
        low_list = _strip(low_weights).split(" ")
        n = len(self.memory_list)
        patterns = [_strip(m.split("{}")[0]).split(" ") for m in self.memory_list]
        parts = [m.split("{}") for m in self.memory_list]
        # each field's value and whether the thinker's float() accepts it (a missing
        # field raises IndexError there: not ok)
        self.candle, candle_ok = _numbers([p[0] for p in patterns])
        self.move, self.move_ok = _numbers([p[len(p) - 1] for p in patterns])

        def field(index):
            texts = [p[index] if len(p) > index else None for p in parts]
            values, ok = _numbers(
                [None if t is None else _strip(t).replace(" ", "") for t in texts]
            )
            return values / 100, ok

        self.high, self.high_ok = field(1)
        self.low, self.low_ok = field(2)

        def weights_of(texts):
            values, ok = _numbers(texts[:n])
            pad = n - len(values)  # weights missing for the last memories: IndexError
            return (
                np.concatenate([values, np.full(pad, math.nan)]),
                np.concatenate([ok, np.zeros(pad, dtype=bool)]),
            )

        self.weight, self.weight_ok = weights_of(weight_list)
        self.high_weight, self.high_weight_ok = weights_of(high_list)
        self.low_weight, self.low_weight_ok = weights_of(low_list)
        # an unparsable first field anywhere raises in the thinker's loop
        self.candle_error = not bool(candle_ok.all())

    @classmethod
    def from_folder(cls, folder: str, tf: str) -> "TimeframeModel":
        def read(kind):
            with open(os.path.join(folder, f"{kind}_{tf}.txt"), "r") as f:
                return f.read()

        return cls(
            read("neural_perfect_threshold"),
            read("memories"),
            read("memory_weights"),
            read("memory_weights_high"),
            read("memory_weights_low"),
        )

    def predict(self, open_price: float, close_price: float) -> Prediction:
        """``pt_thinker.step_coin`` for this timeframe, given the last closed bar."""
        current = 100 * ((close_price - open_price) / open_price)
        start = close_price
        if self.candle_error:
            return self._inactive(start, issue=True)
        m = self.candle
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            denom = (current + m) / 2
            diff = np.abs((np.abs(current - m) / denom) * 100)
        # the thinker: both zero -> 0.0; a zero denominator raises and is caught -> 0.0;
        # a NaN difference (a "nan" memory) never passes the threshold
        diff = np.where((denom == 0.0) | ((current == 0.0) & (m == 0.0)), 0.0, diff)
        hit = diff <= self.threshold
        idx = np.flatnonzero(hit)
        if idx.size == 0:
            return self._inactive(start, issue=False)
        # fields read only for matched memories: any unparsable one raises in the thinker
        parsed = (
            self.high_ok[idx]
            & self.low_ok[idx]
            & self.move_ok[idx]
            & self.weight_ok[idx]
            & self.high_weight_ok[idx]
            & self.low_weight_ok[idx]
        )
        if not parsed.all():
            return self._inactive(start, issue=True)
        # a NaN weight is not 0.0, so its NaN product is averaged in, as in the thinker
        w, hw, lw = self.weight[idx], self.high_weight[idx], self.low_weight[idx]
        moves = [float(x) for x in (self.move[idx] * w)[w != 0.0]]
        high_moves = [float(x) for x in (self.high[idx] * hw)[hw != 0.0]]
        low_moves = [float(x) for x in (self.low[idx] * lw)[lw != 0.0]]
        if not moves or not high_moves or not low_moves:
            # sum/len of an empty list raises in the thinker: inactive, no issue flag
            return self._inactive(start, issue=False)
        final = sum(moves) / len(moves)
        high_final = sum(high_moves) / len(high_moves)
        low_final = sum(low_moves) / len(low_moves)
        return Prediction(
            active=True,
            training_issue=False,
            move_pct=final,
            high_frac=high_final,
            low_frac=low_final,
            start_price=start,
            high_price=start + (start * high_final),
            low_price=start + (start * low_final),
            matched=int(idx.size),
        )

    @staticmethod
    def _inactive(start: float, issue: bool) -> Prediction:
        return Prediction(
            active=False,
            training_issue=issue,
            move_pct=0.0,
            high_frac=0.0,
            low_frac=0.0,
            start_price=start,
            high_price=start,
            low_price=start,
            matched=0,
        )


class PatternModel:
    """All seven timeframes of one model folder."""

    def __init__(self, timeframes: Dict[str, TimeframeModel]):
        self.timeframes = timeframes

    @classmethod
    def from_folder(cls, folder: str) -> "PatternModel":
        return cls({tf: TimeframeModel.from_folder(folder, tf) for tf in TIMEFRAMES})


# --- the runner's signal rule (pt_thinker.step_coin, end of a sweep; FDS-MDL Phase 3) -----

DISTANCE_PCT = 0.5  # pt_thinker.distance
LOW_PLACEHOLDER = 0.01  # the bound of an inactive timeframe
HIGH_PLACEHOLDER = (
    99999999999999999  # an int, as in the thinker (1e17 compares differently)
)
GAP_PASS_LIMIT = 100_000


class GapPassStuck(RuntimeError):
    """The gap pass would never end (the thinker loops for ever on a zero bound)."""


def thinker_bounds(predictions: Sequence[Prediction]):
    """The low and high bounds the runner keeps in its state after a sweep whose
    predictions (one per timeframe, in timeframe order) are ``predictions``: each
    timeframe's predicted low and high moved 0.5% outwards (placeholders where it is
    inactive), spread by the gap pass, then mapped back to timeframe order with
    ``list.index``. Where values repeat (two or more inactive timeframes) the remap drops
    the repeats, so the lists come back shorter and later entries shift left."""
    low_bound_prices: List = []
    high_bound_prices: List = []
    for p in predictions:
        new_low_price = p.low_price - (p.low_price * (DISTANCE_PCT / 100))
        new_high_price = p.high_price + (p.high_price * (DISTANCE_PCT / 100))
        if p.active:
            low_bound_prices.append(new_low_price)
            high_bound_prices.append(new_high_price)
        else:
            low_bound_prices.append(LOW_PLACEHOLDER)
            high_bound_prices.append(HIGH_PLACEHOLDER)

    new_low = sorted(low_bound_prices)
    new_low.reverse()
    new_high = sorted(high_bound_prices)
    og_low_index_list = [low_bound_prices.index(v) for v in new_low]
    og_high_index_list = [high_bound_prices.index(v) for v in new_high]

    og_index = 0
    gap_modifier = 0.0
    steps = 0
    while True:
        steps += 1
        if steps > GAP_PASS_LIMIT:
            raise GapPassStuck("the gap pass does not end on these bounds")
        if (
            new_low[og_index] == LOW_PLACEHOLDER
            or new_low[og_index + 1] == LOW_PLACEHOLDER
            or new_high[og_index] == HIGH_PLACEHOLDER
            or new_high[og_index + 1] == HIGH_PLACEHOLDER
        ):
            pass
        else:
            try:
                low_perc_diff = (
                    abs(new_low[og_index] - new_low[og_index + 1])
                    / ((new_low[og_index] + new_low[og_index + 1]) / 2)
                ) * 100
            except Exception:
                low_perc_diff = 0.0
            try:
                high_perc_diff = (
                    abs(new_high[og_index] - new_high[og_index + 1])
                    / ((new_high[og_index] + new_high[og_index + 1]) / 2)
                ) * 100
            except Exception:
                high_perc_diff = 0.0
            if (
                low_perc_diff < 0.25 + gap_modifier
                or new_low[og_index + 1] > new_low[og_index]
            ):
                new_low[og_index + 1] = new_low[og_index + 1] - (
                    new_low[og_index + 1] * 0.0005
                )
                continue
            if (
                high_perc_diff < 0.25 + gap_modifier
                or new_high[og_index + 1] < new_high[og_index]
            ):
                new_high[og_index + 1] = new_high[og_index + 1] + (
                    new_high[og_index + 1] * 0.0005
                )
                continue
        og_index += 1
        gap_modifier += 0.25
        if og_index >= len(new_low) - 1:
            break

    lows: List = []
    highs: List = []
    for og_index in range(len(new_low)):
        if og_index in og_low_index_list:
            lows.append(new_low[og_low_index_list.index(og_index)])
        if og_index in og_high_index_list:
            highs.append(new_high[og_high_index_list.index(og_index)])
    return lows, highs


def _pad(values, n, fill):
    """The runner's ``_pad_to_len``: missing entries filled at the end, extras cut."""
    out = list(values[:n])
    out.extend([fill] * (n - len(out)))
    return out


def thinker_sides(predictions: Sequence[Prediction], low_bounds, high_bounds, current):
    """Each timeframe's side for price ``current`` against bounds kept from a sweep
    (padded as the runner pads them): "short" above the high bound, "long" below the low
    bound (SHORT is checked first), "none" otherwise or when the timeframe's predicted
    high equals its low (an inactive timeframe)."""
    n = len(predictions)
    lows = _pad(low_bounds, n, LOW_PLACEHOLDER)
    highs = _pad(high_bounds, n, HIGH_PLACEHOLDER)
    sides = []
    for i, p in enumerate(predictions):
        if current > highs[i] and p.high_price != p.low_price:
            sides.append("short")
        elif current < lows[i] and p.high_price != p.low_price:
            sides.append("long")
        else:
            sides.append("none")
    return sides, lows, highs


def thinker_decision(predictions: Sequence[Prediction], current):
    """The runner's sides in steady state, as after two sweeps on the same closed bars:
    the bounds come from the same predictions the sides are checked with. Returns
    (sides, low bounds, high bounds) in timeframe order, bounds padded."""
    lows, highs = thinker_bounds(predictions)
    return thinker_sides(predictions, lows, highs, current)


# --- validation (FDS-MDL Phase 2) ---------------------------------------------------------


def _mean(values: Sequence[float]) -> Optional[float]:
    return (sum(values) / len(values)) if values else None


def score_timeframe(model: TimeframeModel, bars, step_seconds: int) -> dict:
    """Score a frozen timeframe model on consecutive bar pairs (j, j+1) of ``bars``
    (a frame with open_time, open, high, low, close): the prediction made from bar j
    against what bar j+1 did. Pairs across a gap are skipped."""
    times = [int(t.timestamp()) for t in bars["open_time"]]
    o, c = bars["open"].tolist(), bars["close"].tolist()
    h, lo = bars["high"].tolist(), bars["low"].tolist()
    scored = active = 0
    move_err, high_err, low_err = [], [], []
    hits = considered = ups = predicted_ups = within = 0
    for j in range(len(times) - 1):
        if times[j + 1] - times[j] != step_seconds:
            continue
        scored += 1
        p = model.predict(o[j], c[j])
        if not p.active:
            continue
        active += 1
        base = c[j]
        actual_move = ((c[j + 1] - base) / abs(base)) * 100
        actual_high = ((h[j + 1] - base) / abs(base)) * 100
        actual_low = ((lo[j + 1] - base) / abs(base)) * 100
        move_err.append(abs(p.move_pct - actual_move))
        high_err.append(abs(p.high_frac * 100 - actual_high))
        low_err.append(abs(p.low_frac * 100 - actual_low))
        if p.low_price <= c[j + 1] <= p.high_price:
            within += 1
        if p.move_pct != 0.0 and actual_move != 0.0:
            considered += 1
            hits += (p.move_pct > 0) == (actual_move > 0)
            ups += actual_move > 0
            predicted_ups += p.move_pct > 0
    return {
        "scored_pairs": scored,
        "active_pairs": active,
        "active_share": (active / scored) if scored else None,
        "direction_considered": considered,
        "direction_hit_rate": (hits / considered) if considered else None,
        "up_share_of_considered": (ups / considered) if considered else None,
        "predicted_up_share_of_considered": (
            (predicted_ups / considered) if considered else None
        ),
        "close_move_mae_pct": _mean(move_err),
        "high_move_mae_pct": _mean(high_err),
        "low_move_mae_pct": _mean(low_err),
        "next_close_within_band_share": (within / active) if active else None,
    }


METRIC_DEFINITIONS = {
    "scored_pairs": "consecutive held-out bar pairs (j, j+1) of the timeframe",
    "active_pairs": "pairs where bar j matched at least one memory",
    "active_share": "active_pairs / scored_pairs",
    "direction_considered": "active pairs with a non-zero predicted and actual close move",
    "direction_hit_rate": "share of those where the predicted close move has the right sign",
    "up_share_of_considered": "share of those where the close rose (the 'always up' rate)",
    "predicted_up_share_of_considered": "share of those where the predicted close move is "
    "up (1.0: the model always predicts a rise, so its hit rate is the up share)",
    "close_move_mae_pct": "mean |predicted - actual| close move from bar j's close, %",
    "high_move_mae_pct": "mean |predicted - actual| high move from bar j's close, %",
    "low_move_mae_pct": "mean |predicted - actual| low move from bar j's close, %",
    "next_close_within_band_share": "share of active pairs whose next close lies in the "
    "predicted [low, high] band",
}
