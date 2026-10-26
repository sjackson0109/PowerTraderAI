"""
Candlestick pattern detection for the hub chart (FDS-CHART-001). Display only.

Pure: no Tk, no matplotlib, no network. The input is closed OHLC bars with open
timestamps; the output is detections, plus the label layout (merging, precedence,
cap). The rules follow FDS-CHART-001 sections 5 and 6. Where the spec names a TA-Lib
function, TA-Lib's logic and default candle settings are the reference. Every
threshold used is written out below, next to the rule that uses it.

Nothing here feeds a strategy, the trainer, the runner or the trader, and no
pattern carries a published hit rate (FDS-CHART-001 section 10).
"""

from __future__ import annotations

from collections import namedtuple
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple

Bar = namedtuple("Bar", "ts open high low close")  # ts: bar open time, epoch seconds

# --- shared definitions (FDS-CHART-001 section 5.2; TA-Lib default candle settings)
DOJI_FACTOR = 0.10  # doji: body <= 0.10 x R(10)
VERY_SHORT_SHADOW = 0.10  # very short shadow: < 0.10 x R(10)
EQUAL_FACTOR = 0.05  # equal: within 0.05 x R(5)
NEAR_FACTOR = 0.20  # near: within 0.20 x R(5)
# trend rule (section 5.3)
TREND_SMA = 10
TREND_SLOPE = 3
TREND_BARS = TREND_SMA + TREND_SLOPE  # bars of history the trend rule needs
AVG_BARS = 10  # bars of history the averages need
# three white soldiers / three black crows (section 6.3)
SOLDIER_SHADOW = 0.25  # closing-side shadow at most 0.25 x body


class _Ctx:
    """Bar arrays and the shared measurements for one detection run."""

    def __init__(self, bars: Sequence[Bar], step: int):
        self.n = len(bars)
        self.ts = [int(b.ts) for b in bars]
        self.o = [float(b.open) for b in bars]
        self.h = [float(b.high) for b in bars]
        self.l = [float(b.low) for b in bars]
        self.c = [float(b.close) for b in bars]
        self.body = [abs(c - o) for o, c in zip(self.o, self.c)]
        self.rng = [h - l for h, l in zip(self.h, self.l)]
        self.upper = [h - max(o, c) for o, h, c in zip(self.o, self.h, self.c)]
        self.lower = [min(o, c) - l for o, l, c in zip(self.o, self.l, self.c)]
        # run_start[i]: first bar of the contiguous run holding bar i
        self.run_start = []
        for i in range(self.n):
            if i and self.ts[i] - self.ts[i - 1] == step:
                self.run_start.append(self.run_start[i - 1])
            else:
                self.run_start.append(i)

    # -- measurements over the previous n bars (None when there is not enough history)
    def _mean(self, values, i, n):
        if i - n < self.run_start[i]:
            return None
        return sum(values[i - n : i]) / n

    def R(self, i, n):
        return self._mean(self.rng, i, n)

    def B10(self, i):
        return self._mean(self.body, i, 10)

    def contiguous(self, a, b):
        return a >= 0 and b < self.n and self.run_start[b] <= a

    # -- candle predicates
    def white(self, i):
        return self.c[i] > self.o[i]

    def black(self, i):
        return self.c[i] < self.o[i]

    def mid(self, i):
        return (self.o[i] + self.c[i]) / 2.0

    def top(self, i):
        return max(self.o[i], self.c[i])

    def bottom(self, i):
        return min(self.o[i], self.c[i])

    def doji(self, i):
        r10 = self.R(i, 10)
        return r10 is not None and self.body[i] <= DOJI_FACTOR * r10

    def long_body(self, i):
        b10 = self.B10(i)
        return b10 is not None and self.body[i] > b10

    def short_body(self, i):
        b10 = self.B10(i)
        return b10 is not None and self.body[i] < b10

    def very_short(self, shadow, i):
        r10 = self.R(i, 10)
        return r10 is not None and shadow < VERY_SHORT_SHADOW * r10

    def equal(self, x, y, i):
        r5 = self.R(i, 5)
        return r5 is not None and abs(x - y) <= EQUAL_FACTOR * r5

    def near_below(self, x, ref, i):
        """x is at or below ref, or above it by at most 'near'."""
        r5 = self.R(i, 5)
        return r5 is not None and x <= ref + NEAR_FACTOR * r5

    def near_above(self, x, ref, i):
        r5 = self.R(i, 5)
        return r5 is not None and x >= ref - NEAR_FACTOR * r5

    def within_body(self, x, j):
        """x lies inside bar j's body, edges included."""
        return self.bottom(j) <= x <= self.top(j)

    # -- trend before bar s (section 5.3)
    def sma(self, j):
        return sum(self.c[j - TREND_SMA + 1 : j + 1]) / TREND_SMA

    def trend(self, s) -> Optional[str]:
        first = s - TREND_BARS
        if not self.contiguous(first, s - 1):
            return None
        now_sma, then_sma = self.sma(s - 1), self.sma(s - 1 - TREND_SLOPE)
        if self.c[s - 1] < now_sma and now_sma < then_sma:
            return "down"
        if self.c[s - 1] > now_sma and now_sma > then_sma:
            return "up"
        return None


# --- the pattern library (FDS-CHART-001 section 6) ----------------------------------

BULKOWSKI = "Bulkowski, thepatternsite.com"
TALIB = "TA-Lib"


@dataclass(frozen=True)
class PatternDef:
    id: str
    name: str
    bars: int  # bars in the pattern window (Hikkake: its maximum)
    direction: str  # "bullish", "bearish" or "none"
    kind: str  # "reversal", "continuation", "indecision" or "none"
    family: str  # "classical" or "price_action"
    trend: Optional[str]  # trend needed before the first bar: "down", "up" or None
    explanation: str
    reference: str
    url: str = ""
    note: str = ""  # "24/7 variant", "non-canonical", source disagreement, ...
    rule: Optional[Callable] = field(default=None, compare=False, repr=False)

    @property
    def glyph(self) -> str:
        return {"bullish": "▲", "bearish": "▼"}.get(self.direction, "◆")

    @property
    def tags(self) -> Tuple[str, ...]:
        """The filter groups a pattern belongs to (FDS-CHART-001 section 8.3)."""
        direction = self.direction if self.direction != "none" else "none"
        tags = [direction, self.family]
        if self.kind in ("reversal", "continuation", "indecision"):
            tags.append(self.kind)
        return tuple(tags)


def _p(id, name, bars, direction, kind, trend, explanation, reference, **kw):
    family = kw.pop("family", "classical")
    return PatternDef(
        id, name, bars, direction, kind, family, trend, explanation, reference, **kw
    )


# Each rule takes (ctx, i) with i the pattern's last bar and returns True when it
# matches. Bars are i - bars + 1 .. i. The trend is checked by the caller.


def _doji(x, i):
    return x.rng[i] > 0 and x.doji(i)


def _four_price(x, i):
    return x.rng[i] == 0 and x.R(i, 10) is not None


def _long_legged(x, i):
    r10 = x.R(i, 10)
    return _doji(x, i) and x.upper[i] >= 0.5 * r10 and x.lower[i] >= 0.5 * r10


def _dragonfly(x, i):
    return (
        _doji(x, i) and x.very_short(x.upper[i], i) and not x.very_short(x.lower[i], i)
    )


def _gravestone(x, i):
    return (
        _doji(x, i) and x.very_short(x.lower[i], i) and not x.very_short(x.upper[i], i)
    )


def _spinning(x, i):
    return x.short_body(i) and x.upper[i] > x.body[i] and x.lower[i] > x.body[i]


def _spinning_white(x, i):
    return _spinning(x, i) and x.c[i] >= x.o[i] and not _doji(x, i)


def _spinning_black(x, i):
    return _spinning(x, i) and x.c[i] < x.o[i] and not _doji(x, i)


def _high_wave(x, i):
    return (
        x.short_body(i)
        and x.upper[i] > 2 * x.body[i]
        and x.lower[i] > 2 * x.body[i]
        and not _doji(x, i)
    )


def _hammer_shape(x, i):
    return (
        x.short_body(i)
        and x.body[i] > 0
        and x.lower[i] > 2 * x.body[i]
        and x.very_short(x.upper[i], i)
    )


def _inverted_shape(x, i):
    return (
        x.short_body(i)
        and x.body[i] > 0
        and x.upper[i] > 2 * x.body[i]
        and x.very_short(x.lower[i], i)
    )


def _belt_bull(x, i):
    return x.white(i) and x.long_body(i) and x.very_short(x.lower[i], i)


def _belt_bear(x, i):
    return x.black(i) and x.long_body(i) and x.very_short(x.upper[i], i)


def _engulf_bull(x, i):
    a = i - 1
    if not (x.black(a) and x.white(i)):
        return False
    return (x.c[i] >= x.o[a] and x.o[i] < x.c[a]) or (
        x.c[i] > x.o[a] and x.o[i] <= x.c[a]
    )


def _engulf_bear(x, i):
    a = i - 1
    if not (x.white(a) and x.black(i)):
        return False
    return (x.c[i] <= x.o[a] and x.o[i] > x.c[a]) or (
        x.c[i] < x.o[a] and x.o[i] >= x.c[a]
    )


def _harami(x, i):
    a = i - 1
    return (
        x.long_body(a)
        and x.short_body(i)
        and x.top(i) <= x.top(a)
        and x.bottom(i) >= x.bottom(a)
    )


def _harami_bull(x, i):
    return x.black(i - 1) and _harami(x, i)


def _harami_bear(x, i):
    return x.white(i - 1) and _harami(x, i)


def _tweezer_bottom(x, i):
    a = i - 1
    return x.black(a) and x.white(i) and x.equal(x.l[a], x.l[i], i)


def _tweezer_top(x, i):
    a = i - 1
    return x.white(a) and x.black(i) and x.equal(x.h[a], x.h[i], i)


def _piercing(x, i):
    a = i - 1
    return (
        x.black(a)
        and x.long_body(a)
        and x.white(i)
        and x.near_below(x.o[i], x.c[a], i)
        and x.c[i] > x.mid(a)
        and x.c[i] < x.o[a]
    )


def _dark_cloud(x, i):
    a = i - 1
    return (
        x.white(a)
        and x.long_body(a)
        and x.black(i)
        and x.near_above(x.o[i], x.c[a], i)
        and x.c[i] < x.mid(a)
        and x.c[i] > x.o[a]
    )


def _matching_low(x, i):
    a = i - 1
    return x.black(a) and x.long_body(a) and x.black(i) and x.equal(x.c[a], x.c[i], i)


def _matching_high(x, i):
    a = i - 1
    return x.white(a) and x.long_body(a) and x.white(i) and x.equal(x.c[a], x.c[i], i)


def _star_down(x, i, doji):
    a, b = i - 2, i - 1
    star = _doji(x, b) if doji else (x.short_body(b) and not _doji(x, b))
    return (
        x.black(a)
        and x.long_body(a)
        and star
        and x.top(b) <= x.mid(a)
        and x.white(i)
        and x.c[i] > x.mid(a)
    )


def _star_up(x, i, doji):
    a, b = i - 2, i - 1
    star = _doji(x, b) if doji else (x.short_body(b) and not _doji(x, b))
    return (
        x.white(a)
        and x.long_body(a)
        and star
        and x.bottom(b) >= x.mid(a)
        and x.black(i)
        and x.c[i] < x.mid(a)
    )


def _soldiers(x, i):
    for k, j in enumerate((i - 2, i - 1, i)):
        if not (x.white(j) and x.long_body(j)):
            return False
        if x.upper[j] > SOLDIER_SHADOW * x.body[j]:
            return False
        if k:
            if not x.c[j] > x.c[j - 1]:
                return False
            if not x.within_body(x.o[j], j - 1):
                return False
    return True


def _crows(x, i):
    for k, j in enumerate((i - 2, i - 1, i)):
        if not (x.black(j) and x.long_body(j)):
            return False
        if x.lower[j] > SOLDIER_SHADOW * x.body[j]:
            return False
        if k:
            if not x.c[j] < x.c[j - 1]:
                return False
            if not x.within_body(x.o[j], j - 1):
                return False
    return True


def _outside_up(x, i):
    return _engulf_bull(x, i - 1) and x.c[i] > x.c[i - 1]


def _outside_down(x, i):
    return _engulf_bear(x, i - 1) and x.c[i] < x.c[i - 1]


def _inside_up(x, i):
    return _harami_bull(x, i - 1) and x.white(i) and x.c[i] > x.o[i - 2]


def _inside_down(x, i):
    return _harami_bear(x, i - 1) and x.black(i) and x.c[i] < x.o[i - 2]


def _methods(x, i, rising):
    first, last = i - 4, i
    if rising:
        if not (x.white(first) and x.long_body(first)):
            return False
    elif not (x.black(first) and x.long_body(first)):
        return False
    for j in (i - 3, i - 2, i - 1):
        if not x.short_body(j):
            return False
        if not (x.top(j) <= x.h[first] and x.bottom(j) >= x.l[first]):
            return False
    if rising:
        return (
            x.white(last)
            and x.long_body(last)
            and x.near_above(x.o[last], x.c[i - 1], last)
            and x.c[last] > x.c[first]
        )
    return (
        x.black(last)
        and x.long_body(last)
        and x.near_below(x.o[last], x.c[i - 1], last)
        and x.c[last] < x.c[first]
    )


def _mat_hold(x, i):
    first, last = i - 4, i
    if not (x.white(first) and x.long_body(first)):
        return False
    for j in (i - 3, i - 2, i - 1):
        if not (x.short_body(j) and x.bottom(j) > x.l[first]):
            return False
    return x.white(last) and x.long_body(last) and x.c[last] > max(x.h[first:last])


def _strike(x, i, white_strike):
    run = (i - 3, i - 2, i - 1)
    for k, j in enumerate(run):
        if white_strike and not x.black(j):
            return False
        if not white_strike and not x.white(j):
            return False
        if k:
            prev = j - 1
            if white_strike and not x.c[j] < x.c[prev]:
                return False
            if not white_strike and not x.c[j] > x.c[prev]:
                return False
            if not (
                x.near_below(x.o[j], x.top(prev), j)
                and x.near_above(x.o[j], x.bottom(prev), j)
            ):
                return False
    if white_strike:
        return (
            x.white(i) and x.near_below(x.o[i], x.c[i - 1], i) and x.c[i] > x.o[i - 3]
        )
    return x.black(i) and x.near_above(x.o[i], x.c[i - 1], i) and x.c[i] < x.o[i - 3]


def _pin_bull(x, i):
    return (
        x.rng[i] > 0
        and x.bottom(i) >= x.l[i] + (2.0 / 3.0) * x.rng[i]
        and x.lower[i] >= 2 * x.body[i]
        and x.very_short(x.upper[i], i)
    )


def _pin_bear(x, i):
    return (
        x.rng[i] > 0
        and x.top(i) <= x.l[i] + (1.0 / 3.0) * x.rng[i]
        and x.upper[i] >= 2 * x.body[i]
        and x.very_short(x.lower[i], i)
    )


def _inside_bar(x, i):
    return x.h[i] <= x.h[i - 1] and x.l[i] >= x.l[i - 1] and x.rng[i] < x.rng[i - 1]


def _long_lower(x, i):
    return x.rng[i] > 0 and x.lower[i] >= 2 * x.body[i] and x.lower[i] >= 0.5 * x.rng[i]


def _long_upper(x, i):
    return x.rng[i] > 0 and x.upper[i] >= 2 * x.body[i] and x.upper[i] >= 0.5 * x.rng[i]


PATTERNS: Tuple[PatternDef, ...] = (
    # --- one bar (section 6.1)
    _p(
        "doji",
        "Doji",
        1,
        "none",
        "indecision",
        None,
        "Open and close almost equal: buyers and sellers ended the bar level.",
        TALIB + " (CDLDOJI)",
        rule=_doji,
    ),
    _p(
        "four_price_doji",
        "Four-price doji",
        1,
        "none",
        "indecision",
        None,
        "A flat bar: open, high, low and close all equal. Usually no trading at all.",
        "Nison, Japanese Candlestick Charting Techniques",
        rule=_four_price,
    ),
    _p(
        "long_legged_doji",
        "Long-legged doji",
        1,
        "none",
        "indecision",
        None,
        "A doji with long shadows on both sides: a wide fight that ended level.",
        TALIB + " (CDLLONGLEGGEDDOJI)",
        rule=_long_legged,
    ),
    _p(
        "dragonfly_doji",
        "Dragonfly doji",
        1,
        "bullish",
        "indecision",
        None,
        "A doji with a long lower shadow and almost no upper one: a sell-off that was bought back.",
        TALIB + " (CDLDRAGONFLYDOJI)",
        rule=_dragonfly,
    ),
    _p(
        "gravestone_doji",
        "Gravestone doji",
        1,
        "bearish",
        "indecision",
        None,
        "A doji with a long upper shadow and almost no lower one: a rally that was sold back.",
        TALIB + " (CDLGRAVESTONEDOJI)",
        rule=_gravestone,
    ),
    _p(
        "spinning_top_white",
        "Spinning top (white body)",
        1,
        "none",
        "indecision",
        None,
        "A small body with shadows longer than the body on both sides.",
        TALIB + " (CDLSPINNINGTOP)",
        rule=_spinning_white,
    ),
    _p(
        "spinning_top_black",
        "Spinning top (black body)",
        1,
        "none",
        "indecision",
        None,
        "A small body with shadows longer than the body on both sides.",
        TALIB + " (CDLSPINNINGTOP)",
        rule=_spinning_black,
    ),
    _p(
        "high_wave",
        "High wave",
        1,
        "none",
        "indecision",
        None,
        "A small body with very long shadows on both sides.",
        TALIB + " (CDLHIGHWAVE)",
        rule=_high_wave,
    ),
    _p(
        "hammer",
        "Hammer",
        1,
        "bullish",
        "reversal",
        "down",
        "After a fall: a small body near the top and a long lower shadow.",
        TALIB + " (CDLHAMMER)",
        rule=_hammer_shape,
        note="Same shape as the hanging man; the prior trend tells them apart.",
    ),
    _p(
        "hanging_man",
        "Hanging man",
        1,
        "bearish",
        "reversal",
        "up",
        "After a rise: a small body near the top and a long lower shadow.",
        BULKOWSKI,
        url="https://www.thepatternsite.com/HangingMan.html",
        rule=_hammer_shape,
        note="Same shape as the hammer; the prior trend tells them apart.",
    ),
    _p(
        "inverted_hammer",
        "Inverted hammer",
        1,
        "bullish",
        "reversal",
        "down",
        "After a fall: a small body near the bottom and a long upper shadow.",
        BULKOWSKI,
        url="https://thepatternsite.com/HammerInv.html",
        rule=_inverted_shape,
        note="Textbook form: gaps down from the previous bar.",
    ),
    _p(
        "shooting_star",
        "Shooting star",
        1,
        "bearish",
        "reversal",
        "up",
        "After a rise: a small body near the bottom and a long upper shadow.",
        TALIB + " (CDLSHOOTINGSTAR)",
        rule=_inverted_shape,
        note="Textbook form: gaps up from the previous bar.",
    ),
    _p(
        "belt_hold_bullish",
        "Belt hold, bullish",
        1,
        "bullish",
        "reversal",
        "down",
        "After a fall: a long white body opening at (or very near) its low.",
        BULKOWSKI,
        url="https://www.thepatternsite.com/BeltHoldBull.html",
        rule=_belt_bull,
    ),
    _p(
        "belt_hold_bearish",
        "Belt hold, bearish",
        1,
        "bearish",
        "reversal",
        "up",
        "After a rise: a long black body opening at (or very near) its high.",
        TALIB + " (CDLBELTHOLD)",
        rule=_belt_bear,
    ),
    # --- two bars (section 6.2)
    _p(
        "bullish_engulfing",
        "Bullish engulfing",
        2,
        "bullish",
        "reversal",
        "down",
        "After a fall: a white body that covers the previous black body.",
        TALIB + " (CDLENGULFING)",
        rule=_engulf_bull,
    ),
    _p(
        "bearish_engulfing",
        "Bearish engulfing",
        2,
        "bearish",
        "reversal",
        "up",
        "After a rise: a black body that covers the previous white body.",
        TALIB + " (CDLENGULFING)",
        rule=_engulf_bear,
    ),
    _p(
        "bullish_harami",
        "Bullish harami",
        2,
        "bullish",
        "reversal",
        "down",
        "After a fall: a small body inside the previous long black body.",
        TALIB + " (CDLHARAMI)",
        rule=_harami_bull,
    ),
    _p(
        "bearish_harami",
        "Bearish harami",
        2,
        "bearish",
        "reversal",
        "up",
        "After a rise: a small body inside the previous long white body.",
        TALIB + " (CDLHARAMI)",
        rule=_harami_bear,
    ),
    _p(
        "tweezer_bottom",
        "Tweezer bottom",
        2,
        "bullish",
        "reversal",
        "down",
        "After a fall: a black bar then a white bar with matching lows.",
        BULKOWSKI,
        rule=_tweezer_bottom,
    ),
    _p(
        "tweezer_top",
        "Tweezer top",
        2,
        "bearish",
        "reversal",
        "up",
        "After a rise: a white bar then a black bar with matching highs.",
        BULKOWSKI,
        url="https://www.thepatternsite.com/TweezersTop.html",
        rule=_tweezer_top,
    ),
    _p(
        "piercing_line_247",
        "Piercing line (24/7)",
        2,
        "bullish",
        "reversal",
        "down",
        "After a fall: a long black bar, then a white bar closing above its midpoint.",
        BULKOWSKI,
        url="https://www.thepatternsite.com/Piercing.html",
        rule=_piercing,
        note="Textbook form: the white bar opens below the black bar's low.",
    ),
    _p(
        "dark_cloud_cover_247",
        "Dark cloud cover (24/7)",
        2,
        "bearish",
        "reversal",
        "up",
        "After a rise: a long white bar, then a black bar closing below its midpoint.",
        BULKOWSKI,
        url="https://www.thepatternsite.com/DarkCloudCover.html",
        rule=_dark_cloud,
        note="Textbook form: the black bar opens above the white bar's high.",
    ),
    _p(
        "matching_low",
        "Matching low",
        2,
        "bullish",
        "reversal",
        "down",
        "After a fall: two black bars closing at the same price.",
        BULKOWSKI,
        url="https://www.thepatternsite.com/MatchingLow.html",
        rule=_matching_low,
    ),
    _p(
        "matching_high",
        "Matching high",
        2,
        "bearish",
        "reversal",
        "up",
        "After a rise: two white bars closing at the same price.",
        "Secondary sources: the mirror image of the matching low",
        rule=_matching_high,
        note="Not in Bulkowski or TA-Lib.",
    ),
    # --- three bars (section 6.3)
    _p(
        "morning_star_247",
        "Morning star (24/7)",
        3,
        "bullish",
        "reversal",
        "down",
        "After a fall: a long black bar, a small body below its midpoint, then a white bar closing above it.",
        BULKOWSKI,
        url="https://www.thepatternsite.com/MorningStar.html",
        rule=lambda x, i: _star_down(x, i, doji=False),
        note="Textbook form: the star gaps below the first body.",
    ),
    _p(
        "morning_doji_star_247",
        "Morning doji star (24/7)",
        3,
        "bullish",
        "reversal",
        "down",
        "As the morning star, with a doji in the middle.",
        BULKOWSKI,
        rule=lambda x, i: _star_down(x, i, doji=True),
        note="Textbook form: the star gaps below the first body.",
    ),
    _p(
        "evening_star_247",
        "Evening star (24/7)",
        3,
        "bearish",
        "reversal",
        "up",
        "After a rise: a long white bar, a small body above its midpoint, then a black bar closing below it.",
        BULKOWSKI,
        rule=lambda x, i: _star_up(x, i, doji=False),
        note="Textbook form: the star gaps above the first body.",
    ),
    _p(
        "evening_doji_star_247",
        "Evening doji star (24/7)",
        3,
        "bearish",
        "reversal",
        "up",
        "As the evening star, with a doji in the middle.",
        BULKOWSKI,
        rule=lambda x, i: _star_up(x, i, doji=True),
        note="Textbook form: the star gaps above the first body.",
    ),
    _p(
        "three_white_soldiers",
        "Three white soldiers",
        3,
        "bullish",
        "reversal",
        "down",
        "After a fall: three long white bars, each closing higher and opening inside the previous body.",
        TALIB + " (CDL3WHITESOLDIERS)",
        rule=_soldiers,
    ),
    _p(
        "three_black_crows",
        "Three black crows",
        3,
        "bearish",
        "reversal",
        "up",
        "After a rise: three long black bars, each closing lower and opening inside the previous body.",
        TALIB + " (CDL3BLACKCROWS)",
        rule=_crows,
    ),
    _p(
        "three_outside_up",
        "Three outside up",
        3,
        "bullish",
        "reversal",
        "down",
        "A bullish engulfing pair, then a bar closing higher still.",
        TALIB + " (CDL3OUTSIDE)",
        rule=_outside_up,
    ),
    _p(
        "three_outside_down",
        "Three outside down",
        3,
        "bearish",
        "reversal",
        "up",
        "A bearish engulfing pair, then a bar closing lower still.",
        TALIB + " (CDL3OUTSIDE)",
        rule=_outside_down,
    ),
    _p(
        "three_inside_up",
        "Three inside up",
        3,
        "bullish",
        "reversal",
        "down",
        "A bullish harami, then a white bar closing above the first bar's open.",
        TALIB + " (CDL3INSIDE)",
        rule=_inside_up,
    ),
    _p(
        "three_inside_down",
        "Three inside down",
        3,
        "bearish",
        "reversal",
        "up",
        "A bearish harami, then a black bar closing below the first bar's open.",
        TALIB + " (CDL3INSIDE)",
        rule=_inside_down,
    ),
    # --- four, five and variable bars (section 6.4)
    _p(
        "rising_three_methods",
        "Rising three methods",
        5,
        "bullish",
        "continuation",
        "up",
        "A long white bar, three small bodies inside its range, then a long white bar closing above it.",
        BULKOWSKI,
        url="https://www.thepatternsite.com/Rising3Methods.html",
        rule=lambda x, i: _methods(x, i, rising=True),
    ),
    _p(
        "falling_three_methods",
        "Falling three methods",
        5,
        "bearish",
        "continuation",
        "down",
        "A long black bar, three small bodies inside its range, then a long black bar closing below it.",
        TALIB + " (CDLRISEFALL3METHODS)",
        rule=lambda x, i: _methods(x, i, rising=False),
    ),
    _p(
        "mat_hold",
        "Mat hold",
        5,
        "bullish",
        "continuation",
        "up",
        "A long white bar, three small bodies holding above its low, then a white bar closing above all four.",
        BULKOWSKI,
        url="https://www.thepatternsite.com/MatHold.html",
        rule=_mat_hold,
    ),
    _p(
        "three_line_strike_white",
        "Three line strike, white strike",
        4,
        "bullish",
        "reversal",
        "down",
        "Three falling black bars, then a white bar that closes above the first one's open.",
        BULKOWSKI,
        url="https://www.thepatternsite.com/ThreeLineStrikeBull.html",
        rule=lambda x, i: _strike(x, i, white_strike=True),
        note="Sources disagree on naming and meaning: Farley reads this as a reversal; "
        "Bulkowski's 'bullish' three line strike is the opposite colour order.",
    ),
    _p(
        "three_line_strike_black",
        "Three line strike, black strike",
        4,
        "bearish",
        "reversal",
        "up",
        "Three rising white bars, then a black bar that closes below the first one's open.",
        TALIB + " (CDL3LINESTRIKE)",
        rule=lambda x, i: _strike(x, i, white_strike=False),
        note="Sources disagree on naming and meaning: Farley reads this as a reversal; "
        "Bulkowski reads the white-candle form as a continuation.",
    ),
    _p(
        "hikkake_bullish",
        "Hikkake, bullish",
        6,
        "bullish",
        "reversal",
        None,
        "An inside bar, a false break below it, then a close back above its high within three bars.",
        TALIB + " (CDLHIKKAKE)",
        family="price_action",
    ),
    _p(
        "hikkake_bearish",
        "Hikkake, bearish",
        6,
        "bearish",
        "reversal",
        None,
        "An inside bar, a false break above it, then a close back below its low within three bars.",
        TALIB + " (CDLHIKKAKE)",
        family="price_action",
    ),
    # --- price action (section 6.6)
    _p(
        "pin_bar_bullish",
        "Pin bar, bullish",
        1,
        "bullish",
        "reversal",
        None,
        "A body in the top third and a long lower tail, with almost no upper shadow.",
        "Price action (Western)",
        family="price_action",
        rule=_pin_bull,
    ),
    _p(
        "pin_bar_bearish",
        "Pin bar, bearish",
        1,
        "bearish",
        "reversal",
        None,
        "A body in the bottom third and a long upper tail, with almost no lower shadow.",
        "Price action (Western)",
        family="price_action",
        rule=_pin_bear,
    ),
    _p(
        "inside_bar",
        "Inside bar",
        2,
        "none",
        "indecision",
        None,
        "The bar's whole range sits inside the previous bar's range.",
        "Price action (Western)",
        family="price_action",
        rule=_inside_bar,
    ),
    _p(
        "long_lower_wick",
        "Long lower wick",
        1,
        "bullish",
        "none",
        None,
        "A lower shadow at least twice the body and half the bar: a sell-off rejected.",
        "Price action (Western)",
        family="price_action",
        rule=_long_lower,
    ),
    _p(
        "long_upper_wick",
        "Long upper wick",
        1,
        "bearish",
        "none",
        None,
        "An upper shadow at least twice the body and half the bar: a rally rejected.",
        "Price action (Western)",
        family="price_action",
        rule=_long_upper,
    ),
)

BY_ID: Dict[str, PatternDef] = {p.id: p for p in PATTERNS}
ORDER: Dict[str, int] = {p.id: k for k, p in enumerate(PATTERNS)}


@dataclass(frozen=True)
class Detection:
    pattern_id: str
    first_index: int  # index into the (closed, cleaned) bars passed to detect()
    last_index: int
    context_index: int  # first trend-context bar (== first_index when none)
    first_ts: int
    last_ts: int
    context_ts: int
    trend: Optional[str]  # trend verdict into the pattern
    next_move: Optional[str] = None  # "up", "down", "flat", or None (not enough bars)
    next_after: int = 0  # bars after the pattern that next_move compares


def closed_bars(bars: Sequence[Bar], step: int, now: Optional[float]) -> List[Bar]:
    """Bars in time order with the still-forming bar (and any later) removed."""
    out = sorted(bars, key=lambda b: int(b.ts))
    if now is None:
        return out
    return [b for b in out if int(b.ts) + step <= now]


def _next_move(x: _Ctx, last: int, k: int) -> Optional[str]:
    j = last + k
    if not x.contiguous(last, j):
        return None
    if x.equal(x.c[j], x.c[last], j):
        return "flat"
    return "up" if x.c[j] > x.c[last] else "down"


def _hikkake(x: _Ctx, i: int) -> List[Tuple[str, int, int]]:
    """(pattern_id, first, last) for a Hikkake whose confirmation lands on bar i."""
    out = []
    for wait in range(1, 4):  # confirmed on one of the break bar's next three bars
        c3 = i - wait  # the false-break bar
        c1, c2 = c3 - 2, c3 - 1
        if c1 < 0 or not x.contiguous(c1, i):
            continue
        inside = x.h[c2] < x.h[c1] and x.l[c2] > x.l[c1]
        if not inside:
            continue
        if x.h[c3] < x.h[c2] and x.l[c3] < x.l[c2]:  # false break down
            if x.c[i] > x.h[c2] and all(x.c[j] <= x.h[c2] for j in range(c3, i)):
                out.append(("hikkake_bullish", c1, i))
        if x.h[c3] > x.h[c2] and x.l[c3] > x.l[c2]:  # false break up
            if x.c[i] < x.l[c2] and all(x.c[j] >= x.l[c2] for j in range(c3, i)):
                out.append(("hikkake_bearish", c1, i))
    return out


def detect(
    bars: Sequence[Bar], step: int, now: Optional[float] = None
) -> Tuple[List[Bar], List[Detection]]:
    """Detect every pattern on closed bars. Returns (the closed bars used, detections).

    ``now`` (epoch seconds) drops the still-forming bar; pass None only when the bars
    are already closed. A pattern needs its whole window, its trend-context bars and
    the bars its averages need to be one contiguous run of ``step``-spaced bars."""
    used = closed_bars(bars, step, now)
    x = _Ctx(used, step)
    found: List[Detection] = []

    def add(pid, first, last):
        d = BY_ID[pid]
        trend = x.trend(first) if d.trend else None
        if d.trend and trend != d.trend:
            return
        context = first - TREND_BARS if d.trend else first
        k = max(3, last - first + 1)
        found.append(
            Detection(
                pid,
                first,
                last,
                context,
                x.ts[first],
                x.ts[last],
                x.ts[context],
                trend,
                _next_move(x, last, k),
                k,
            )
        )

    for i in range(x.n):
        for d in PATTERNS:
            if d.rule is None:
                continue
            first = i - d.bars + 1
            history = first - max(TREND_BARS if d.trend else 0, AVG_BARS)
            if history < 0 or not x.contiguous(history, i):
                continue
            try:
                hit = d.rule(x, i)
            except (TypeError, ZeroDivisionError):
                hit = False  # an average without enough history
            if hit:
                add(d.id, first, i)
        for pid, first, last in _hikkake(x, i):
            add(pid, first, last)
    return used, found


# --- label layout (FDS-CHART-001 section 5.4) ---------------------------------------


@dataclass
class Label:
    detection: Detection
    others: List[Detection] = field(default_factory=list)  # the "+n" detections

    @property
    def pattern(self) -> PatternDef:
        return BY_ID[self.detection.pattern_id]


@dataclass
class Layout:
    labels: List[Label]
    hidden_by_cap: int
    shown_detections: int


def merge_runs(detections: Sequence[Detection]) -> List[Detection]:
    """Consecutive detections of one pattern become one, covering the whole run."""
    out: List[Detection] = []
    last_by_pattern: Dict[str, int] = {}
    for d in sorted(detections, key=lambda d: (d.last_index, ORDER[d.pattern_id])):
        k = last_by_pattern.get(d.pattern_id)
        if k is not None and d.first_index <= out[k].last_index + 1:
            prev = out[k]
            out[k] = replace(
                d,
                first_index=prev.first_index,
                first_ts=prev.first_ts,
                context_index=prev.context_index,
                context_ts=prev.context_ts,
                trend=prev.trend,
            )
            continue
        last_by_pattern[d.pattern_id] = len(out)
        out.append(d)
    return out


def _precedence(d: Detection) -> Tuple[int, int, int]:
    p = BY_ID[d.pattern_id]
    return (-(d.last_index - d.first_index + 1), p.family != "classical", ORDER[p.id])


def layout(
    detections: Sequence[Detection],
    visible: Callable[[PatternDef], bool],
    max_labels: int,
) -> Layout:
    """One label per candle: merge runs, keep the visible patterns, pick a winner per
    last candle (most bars, then classical, then library order; price action only
    where no classical pattern ends on that candle), then cap the label count
    (by bar count, then the most recent)."""
    kept = [d for d in merge_runs(detections) if visible(BY_ID[d.pattern_id])]
    by_candle: Dict[int, List[Detection]] = {}
    for d in kept:
        by_candle.setdefault(d.last_index, []).append(d)
    labels: List[Label] = []
    for candle, group in by_candle.items():
        if any(BY_ID[d.pattern_id].family == "classical" for d in group):
            group = [d for d in group if BY_ID[d.pattern_id].family == "classical"]
        group.sort(key=_precedence)
        labels.append(Label(group[0], group[1:]))

    def priority(lb: Label):
        d = lb.detection
        return (-(d.last_index - d.first_index + 1), -d.last_index)

    labels.sort(key=priority)
    cap = max(1, int(max_labels))
    shown, hidden = labels[:cap], labels[cap:]
    shown.sort(key=lambda lb: lb.detection.last_index)
    return Layout(shown, len(hidden), sum(1 + len(lb.others) for lb in shown))


# --- the hub's timeframe names -> candle sizes -------------------------------------

HUB_TO_CANDLE = {
    "1min": "1m",
    "5min": "5m",
    "15min": "15m",
    "30min": "30m",
    "1hour": "1h",
    "2hour": "2h",
    "4hour": "4h",
    "8hour": "8h",
    "12hour": "12h",
    "1day": "1d",
    "1week": "1w",
}

# Bars before the first visible candle that detection needs (window + trend + averages)
WARMUP_BARS = max(p.bars for p in PATTERNS) + max(TREND_BARS, AVG_BARS)
