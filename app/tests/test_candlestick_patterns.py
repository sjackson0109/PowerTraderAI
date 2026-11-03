"""Candlestick pattern detection (FDS-CHART-001 sections 5, 6 and 13, items 1, 2, 8 and
9). Each rule has a hand-built fixture that matches and a near-miss that does not.

The fixtures sit on a 30-bar base whose bars all have body 1 and range 2, so the
shared measures are B(10) = 1, R(10) = R(5) = 2. That gives: doji means a body of at
most 0.2; a very short shadow is under 0.2; "equal" means within 0.1; "near" means
within 0.4. A "down" base falls into the pattern (a downtrend by the section 5.3
rule), an "up" base rises into it, and a "flat" base has no trend. The last base bar
closes at 100.

No network; the recorded fixtures are Binance 1h candles committed to the repo.
"""

import ast
import os
import re
import sys

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import candlestick_patterns as cp  # noqa: E402

HOUR = 3600
T0 = 1_700_000_000 - 1_700_000_000 % HOUR


def base(trend, n=30):
    out = []
    for k in range(n):
        if trend == "down":
            c = 100.0 + (n - 1 - k)
            o = c + 1
        elif trend == "up":
            c = 100.0 - (n - 1 - k)
            o = c - 1
        else:  # flat: alternating white / black around 100
            o, c = (99.5, 100.5) if k % 2 == 0 else (100.5, 99.5)
        out.append((o, max(o, c) + 0.5, min(o, c) - 0.5, c))
    return out


def bars_of(rows, start=T0, gap_at=None):
    out, ts = [], start
    for k, (o, h, lo, c) in enumerate(rows):
        if gap_at is not None and k == gap_at:
            ts += HOUR  # one missing bar
        out.append(cp.Bar(ts, o, h, lo, c))
        ts += HOUR
    return out


def detected(trend, pattern_rows, pattern_id, **kw):
    rows = base(trend) + list(pattern_rows)
    bars = bars_of(rows, **kw)
    _, dets = cp.detect(bars, HOUR)
    last = len(bars) - 1
    return any(d.pattern_id == pattern_id and d.last_index == last for d in dets)


# (pattern, base trend, matching bars, near-miss bars); bars are (open, high, low, close)
CASES = [
    # --- one bar
    ("doji", "flat", [(100, 101, 99, 100.1)], [(100, 101, 99, 100.5)]),
    ("four_price_doji", "flat", [(100, 100, 100, 100)], [(100, 100.01, 100, 100)]),
    (
        "long_legged_doji",
        "flat",
        [(100, 101.2, 98.8, 100.05)],
        [(100, 100.5, 98.8, 100.05)],
    ),
    (
        "dragonfly_doji",
        "flat",
        [(100, 100.05, 98.5, 100.05)],
        [(100, 100.55, 98.5, 100.05)],
    ),
    (
        "gravestone_doji",
        "flat",
        [(100, 101.5, 99.95, 99.95)],
        [(100, 101.5, 99.45, 99.95)],
    ),
    (
        "spinning_top_white",
        "flat",
        [(100, 100.9, 99.5, 100.4)],
        [(100, 100.7, 99.5, 100.4)],
    ),
    (
        "spinning_top_black",
        "flat",
        [(100.4, 100.9, 99.5, 100)],
        [(100.4, 100.9, 99.7, 100)],
    ),
    ("high_wave", "flat", [(100, 101.3, 99.1, 100.4)], [(100, 101.1, 99.1, 100.4)]),
    ("hammer", "down", [(100, 100.5, 98.8, 100.45)], [(100, 100.75, 98.8, 100.45)]),
    ("hanging_man", "up", [(100, 100.5, 98.8, 100.45)], [(100, 100.75, 98.8, 100.45)]),
    (
        "inverted_hammer",
        "down",
        [(100, 101.5, 99.95, 100.45)],
        [(100, 101.5, 99.7, 100.45)],
    ),
    (
        "shooting_star",
        "up",
        [(100, 101.5, 99.95, 100.45)],
        [(100, 101.5, 99.7, 100.45)],
    ),
    (
        "belt_hold_bullish",
        "down",
        [(100, 102.6, 99.95, 102.5)],
        [(100, 102.6, 99.5, 102.5)],
    ),
    (
        "belt_hold_bearish",
        "up",
        [(100, 100.05, 97.4, 97.5)],
        [(100, 100.5, 97.4, 97.5)],
    ),
    # --- two bars
    (
        "bullish_engulfing",
        "down",
        [(100.5, 100.7, 99.3, 99.5), (99.5, 100.9, 99.4, 100.8)],
        [(100.5, 100.7, 99.3, 99.5), (99.5, 100.4, 99.4, 100.3)],
    ),
    (
        "bearish_engulfing",
        "up",
        [(99.5, 100.7, 99.3, 100.5), (100.5, 100.6, 99.1, 99.2)],
        [(99.5, 100.7, 99.3, 100.5), (100.5, 100.6, 99.7, 99.8)],
    ),
    (
        "bullish_harami",
        "down",
        [(102, 102.2, 98.8, 99), (99.5, 100.2, 99.3, 100.0)],
        [(102, 102.2, 98.6, 99), (98.8, 99.7, 98.7, 99.5)],
    ),
    (
        "bearish_harami",
        "up",
        [(98, 101.2, 97.8, 101), (100.5, 100.8, 99.9, 100.0)],
        [(98, 101.2, 97.8, 101), (100.5, 101.5, 100.3, 101.4)],
    ),
    (
        "tweezer_bottom",
        "down",
        [(100.5, 100.7, 99.0, 99.5), (99.5, 100.6, 99.05, 100.4)],
        [(100.5, 100.7, 99.0, 99.5), (99.5, 100.6, 99.3, 100.4)],
    ),
    (
        "tweezer_top",
        "up",
        [(99.5, 101.0, 99.3, 100.5), (100.5, 101.05, 99.5, 99.6)],
        [(99.5, 101.0, 99.3, 100.5), (100.5, 101.4, 99.5, 99.6)],
    ),
    (
        "piercing_line_247",
        "down",
        [(102, 102.2, 98.8, 99), (99.1, 101.2, 98.9, 101)],
        [(102, 102.2, 98.8, 99), (99.1, 100.4, 98.9, 100.2)],
    ),
    (
        "dark_cloud_cover_247",
        "up",
        [(98, 101.2, 97.8, 101), (100.9, 101.1, 98.8, 99)],
        [(98, 101.2, 97.8, 101), (100.9, 101.1, 99.6, 99.8)],
    ),
    (
        "matching_low",
        "down",
        [(102, 102.2, 98.8, 99), (99.4, 99.6, 98.9, 99.05)],
        [(102, 102.2, 98.8, 99), (99.4, 99.6, 98.5, 98.7)],
    ),
    (
        "matching_high",
        "up",
        [(98, 101.2, 97.8, 101), (100.6, 101.1, 100.4, 100.95)],
        [(98, 101.2, 97.8, 101), (100.6, 101.5, 100.4, 101.3)],
    ),
    # --- three bars
    (
        "morning_star_247",
        "down",
        [(102, 102.2, 98.8, 99), (99.2, 99.8, 98.8, 99.6), (99.6, 101.2, 99.5, 101)],
        [(102, 102.2, 98.8, 99), (99.2, 99.8, 98.8, 99.6), (99.6, 100.4, 99.5, 100.2)],
    ),
    (
        "morning_doji_star_247",
        "down",
        [(102, 102.2, 98.8, 99), (99.3, 99.6, 99.0, 99.35), (99.4, 101.2, 99.3, 101)],
        [
            (102, 102.2, 98.8, 99),
            (100.6, 100.9, 100.4, 100.65),
            (99.4, 101.2, 99.3, 101),
        ],
    ),
    (
        "evening_star_247",
        "up",
        [
            (98, 101.2, 97.8, 101),
            (100.3, 100.9, 100.0, 100.7),
            (100.7, 100.8, 98.8, 99),
        ],
        [
            (98, 101.2, 97.8, 101),
            (100.3, 100.9, 100.0, 100.7),
            (100.7, 100.8, 99.6, 99.8),
        ],
    ),
    (
        "evening_doji_star_247",
        "up",
        [
            (98, 101.2, 97.8, 101),
            (100.6, 100.9, 100.4, 100.65),
            (100.6, 100.7, 98.8, 99),
        ],
        [
            (98, 101.2, 97.8, 101),
            (100.6, 100.9, 100.4, 100.65),
            (100.6, 100.7, 99.6, 99.8),
        ],
    ),
    (
        "three_white_soldiers",
        "down",
        [
            (100, 102.1, 99.9, 102),
            (101, 103.6, 100.9, 103.5),
            (102.5, 105.1, 102.4, 105),
        ],
        [
            (100, 102.1, 99.9, 102),
            (101, 103.6, 100.9, 103.5),
            (102.5, 106.0, 102.4, 105),
        ],
    ),
    (
        "three_black_crows",
        "up",
        [(100, 100.1, 97.9, 98), (99, 99.1, 96.4, 96.5), (97.5, 97.6, 94.9, 95)],
        [(100, 100.1, 97.9, 98), (99, 99.1, 96.4, 96.5), (97.5, 97.6, 94.0, 95)],
    ),
    (
        "three_outside_up",
        "down",
        [
            (100.5, 100.7, 99.3, 99.5),
            (99.5, 100.9, 99.4, 100.8),
            (100.8, 101.6, 100.7, 101.5),
        ],
        [
            (100.5, 100.7, 99.3, 99.5),
            (99.5, 100.9, 99.4, 100.8),
            (100.8, 100.9, 100.5, 100.6),
        ],
    ),
    (
        "three_outside_down",
        "up",
        [
            (99.5, 100.7, 99.3, 100.5),
            (100.5, 100.6, 99.1, 99.2),
            (99.2, 99.3, 98.5, 98.6),
        ],
        [
            (99.5, 100.7, 99.3, 100.5),
            (100.5, 100.6, 99.1, 99.2),
            (99.2, 99.5, 99.1, 99.4),
        ],
    ),
    (
        "three_inside_up",
        "down",
        [(102, 102.2, 98.8, 99), (99.5, 100.2, 99.3, 100.0), (100, 102.4, 99.9, 102.3)],
        [(102, 102.2, 98.8, 99), (99.5, 100.2, 99.3, 100.0), (100, 101.6, 99.9, 101.5)],
    ),
    (
        "three_inside_down",
        "up",
        [(98, 101.2, 97.8, 101), (100.5, 100.8, 99.9, 100.0), (100, 100.1, 97.6, 97.7)],
        [(98, 101.2, 97.8, 101), (100.5, 100.8, 99.9, 100.0), (100, 100.1, 98.4, 98.5)],
    ),
    # --- four and five bars
    (
        "rising_three_methods",
        "up",
        [
            (100, 103.2, 99.8, 103),
            (102.8, 102.9, 102.3, 102.4),
            (102.4, 102.5, 101.9, 102.0),
            (102.0, 102.1, 101.5, 101.6),
            (101.6, 104.1, 101.5, 104),
        ],
        [
            (100, 103.2, 99.8, 103),
            (102.8, 102.9, 102.3, 102.4),
            (102.4, 102.5, 101.9, 102.0),
            (102.0, 102.1, 101.5, 101.6),
            (101.6, 102.9, 101.5, 102.8),
        ],
    ),
    (
        "falling_three_methods",
        "down",
        [
            (100, 100.2, 96.8, 97),
            (97.2, 97.7, 97.1, 97.6),
            (97.6, 98.1, 97.5, 98.0),
            (98.0, 98.5, 97.9, 98.4),
            (98.4, 98.5, 95.9, 96),
        ],
        [
            (100, 100.2, 96.8, 97),
            (97.2, 97.7, 97.1, 97.6),
            (97.6, 98.1, 97.5, 98.0),
            (98.0, 98.5, 97.9, 98.4),
            (98.4, 98.5, 97.3, 97.4),
        ],
    ),
    (
        "mat_hold",
        "up",
        [
            (100, 103.2, 99.8, 103),
            (103.4, 103.5, 102.9, 103.0),
            (103.0, 103.1, 102.5, 102.6),
            (102.6, 102.7, 102.1, 102.2),
            (102.2, 104.6, 102.1, 104.5),
        ],
        [
            (100, 103.2, 99.8, 103),
            (103.4, 103.5, 102.9, 103.0),
            (103.0, 103.1, 102.5, 102.6),
            (102.6, 102.7, 102.1, 102.2),
            (102.2, 103.45, 102.1, 103.4),
        ],
    ),
    (
        "three_line_strike_white",
        "down",
        [
            (100.5, 100.6, 99.4, 99.5),
            (99.6, 99.7, 98.5, 98.6),
            (98.7, 98.8, 97.6, 97.7),
            (97.7, 100.9, 97.6, 100.8),
        ],
        [
            (100.5, 100.6, 99.4, 99.5),
            (99.6, 99.7, 98.5, 98.6),
            (98.7, 98.8, 97.6, 97.7),
            (97.7, 100.3, 97.6, 100.2),
        ],
    ),
    (
        "three_line_strike_black",
        "up",
        [
            (99.5, 100.6, 99.4, 100.5),
            (100.4, 101.5, 100.3, 101.4),
            (101.3, 102.4, 101.2, 102.3),
            (102.3, 102.4, 99.1, 99.2),
        ],
        [
            (99.5, 100.6, 99.4, 100.5),
            (100.4, 101.5, 100.3, 101.4),
            (101.3, 102.4, 101.2, 102.3),
            (102.3, 102.4, 99.7, 99.8),
        ],
    ),
    (
        "hikkake_bullish",
        "flat",
        [
            (99, 101, 98, 100.5),
            (99.5, 100.5, 98.5, 100),
            (99.8, 100.2, 98.2, 98.6),
            (98.6, 101.0, 98.5, 100.8),
        ],
        [
            (99, 101, 98, 100.5),
            (99.5, 100.5, 98.5, 100),
            (99.8, 100.2, 98.2, 98.6),
            (98.6, 100.4, 98.5, 100.3),
        ],
    ),
    (
        "hikkake_bearish",
        "flat",
        [
            (99, 101, 98, 100.5),
            (99.5, 100.5, 98.5, 100),
            (99, 100.8, 98.8, 100.4),
            (100.4, 100.5, 97.9, 98.1),
        ],
        [
            (99, 101, 98, 100.5),
            (99.5, 100.5, 98.5, 100),
            (99, 100.8, 98.8, 100.4),
            (100.4, 100.5, 98.6, 98.7),
        ],
    ),
    # --- price action
    (
        "pin_bar_bullish",
        "flat",
        [(100.6, 100.7, 98.7, 100.65)],
        [(100.6, 100.95, 98.7, 100.65)],
    ),
    (
        "pin_bar_bearish",
        "flat",
        [(99.4, 101.3, 99.35, 99.35)],
        [(99.4, 101.3, 99.05, 99.35)],
    ),
    ("inside_bar", "flat", [(99.8, 100.6, 99.4, 100.2)], [(99.8, 101.2, 99.4, 100.2)]),
    (
        "long_lower_wick",
        "flat",
        [(100.2, 100.5, 98.8, 100.4)],
        [(100.0, 100.6, 99.4, 100.5)],
    ),
    (
        "long_upper_wick",
        "flat",
        [(100.0, 101.6, 99.95, 100.2)],
        [(100.0, 101.0, 99.95, 100.5)],
    ),
]


def test_every_pattern_in_the_library_has_a_fixture():
    assert sorted(c[0] for c in CASES) == sorted(p.id for p in cp.PATTERNS)


@pytest.mark.parametrize(
    "pattern_id,trend,match,miss", CASES, ids=[c[0] for c in CASES]
)
def test_each_rule_matches_its_fixture_and_not_its_near_miss(
    pattern_id, trend, match, miss
):
    assert detected(trend, match, pattern_id), f"{pattern_id} not detected"
    assert not detected(trend, miss, pattern_id), f"{pattern_id} matched its near miss"


# --- definitions, trend, contiguity, forming bar (section 5) ------------------------


def test_a_flat_bar_is_a_four_price_doji_and_never_divides_by_zero():
    assert detected("flat", [(100, 100, 100, 100)], "four_price_doji")
    assert not detected(
        "flat", [(100, 100, 100, 100)], "doji"
    )  # the flat bar has its own name


def test_body_edges_are_inclusive():
    # the engulfing bar opens exactly at the previous close, as most 24/7 bars do
    assert detected(
        "down",
        [(100.5, 100.7, 99.3, 99.5), (99.5, 100.9, 99.4, 100.8)],
        "bullish_engulfing",
    )


def test_the_trend_decides_hammer_against_hanging_man():
    bar = [(100, 100.5, 98.8, 100.45)]
    assert detected("down", bar, "hammer") and not detected("down", bar, "hanging_man")
    assert detected("up", bar, "hanging_man") and not detected("up", bar, "hammer")
    assert not detected("flat", bar, "hammer") and not detected(
        "flat", bar, "hanging_man"
    )


def test_a_missing_bar_inside_the_window_gives_no_match():
    rows = [(100.5, 100.7, 99.3, 99.5), (99.5, 100.9, 99.4, 100.8)]
    assert not detected("down", rows, "bullish_engulfing", gap_at=31)


def test_the_forming_bar_is_never_used():
    rows = base("down") + [(100.5, 100.7, 99.3, 99.5), (99.5, 100.9, 99.4, 100.8)]
    bars = bars_of(rows)
    still_forming = bars[-1].ts + HOUR - 1  # the last bar has not closed yet
    used, dets = cp.detect(bars, HOUR, now=still_forming)
    assert len(used) == len(bars) - 1
    assert not any(d.pattern_id == "bullish_engulfing" for d in dets)
    used, dets = cp.detect(bars, HOUR, now=bars[-1].ts + HOUR)  # now it has closed
    assert any(
        d.pattern_id == "bullish_engulfing" and d.last_index == len(bars) - 1
        for d in dets
    )


def test_a_detection_records_its_trend_context_and_what_happened_next():
    rows = (
        base("down")
        + [(100, 100.5, 98.8, 100.45)]
        + [(100.45, 101.2, 100.3, 101.0)] * 3
    )
    _, dets = cp.detect(bars_of(rows), HOUR)
    hammer = next(d for d in dets if d.pattern_id == "hammer")
    assert hammer.trend == "down"
    assert hammer.context_index == hammer.first_index - cp.TREND_BARS
    assert (hammer.next_move, hammer.next_after) == ("up", 3)


# --- layout: merging, precedence, cap (section 5.4) ---------------------------------


def det(pid, first, last):
    return cp.Detection(
        pid, first, last, first, first * HOUR, last * HOUR, first * HOUR, None
    )


def every(_p):
    return True


def test_consecutive_detections_of_one_pattern_merge():
    merged = cp.merge_runs([det("doji", 5, 5), det("doji", 6, 6), det("doji", 9, 9)])
    assert [(d.first_index, d.last_index) for d in merged] == [(5, 6), (9, 9)]


def test_one_label_per_candle_with_the_longest_classical_pattern_winning():
    lay = cp.layout(
        [
            det("doji", 9, 9),
            det("three_outside_up", 7, 9),
            det("long_lower_wick", 9, 9),
        ],
        every,
        12,
    )
    assert len(lay.labels) == 1
    label = lay.labels[0]
    assert label.detection.pattern_id == "three_outside_up"
    # the doji is a "+1"; the price-action wick is dropped next to a classical pattern
    assert [o.pattern_id for o in label.others] == ["doji"]


def test_price_action_shows_where_no_classical_pattern_matched():
    lay = cp.layout([det("pin_bar_bullish", 4, 4)], every, 12)
    assert [lb.detection.pattern_id for lb in lay.labels] == ["pin_bar_bullish"]


def ids_of(labels):
    return [lb.detection.pattern_id for lb in labels]


def dojis_and_soldiers():
    """Dojis on every other candle to 28, and three white soldiers on candles 0-2."""
    return [det("doji", k, k) for k in range(0, 30, 2)] + [
        det("three_white_soldiers", 0, 2)
    ]


def test_the_cap_keeps_the_newest_patterns_by_default():
    """Owner, 2026-11-04: rank, then cap. With no trade, the newest come first: the
    soldiers, three candles long but 26 candles back, are hidden."""
    dets = dojis_and_soldiers()
    lay = cp.layout(dets, every, 4)
    assert [lb.detection.last_index for lb in lay.labels] == [22, 24, 26, 28]
    assert lay.hidden_by_cap == len(dets) - 4 - 1  # the doji at index 2 is a "+1"
    # the hidden ones stay, ranked: the next newest first, the oldest last; candles
    # 2 and 4 are equally recent (within 3 candles), so the soldiers go before the doji
    assert [lb.detection.last_index for lb in lay.hidden][:3] == [20, 18, 16]
    tail = [(lb.detection.pattern_id, lb.detection.last_index) for lb in lay.hidden]
    assert tail[-3:] == [("three_white_soldiers", 2), ("doji", 4), ("doji", 0)]


def test_a_pattern_at_a_trade_ranks_first():
    """A trade on a pattern's candles, or the candle after its last, puts it first,
    however old it is."""
    lay = cp.layout(dojis_and_soldiers(), every, 4, trade_ts=[3 * HOUR], step=HOUR)
    assert "three_white_soldiers" in ids_of(lay.labels)
    later = cp.layout(dojis_and_soldiers(), every, 4, trade_ts=[4 * HOUR], step=HOUR)
    assert "three_white_soldiers" not in ids_of(later.labels)  # two candles after


def test_equally_recent_patterns_go_longest_first():
    """Within the same recency (by default, ending within 3 candles of each other)
    three candles before two before one."""
    dets = [
        det("doji", 28, 28),
        det("bullish_engulfing", 25, 26),
        det("three_white_soldiers", 25, 27),
    ]
    assert ids_of(cp.layout(dets, every, 1).labels) == ["three_white_soldiers"]
    assert ids_of(cp.layout(dets, every, 2).labels) == [
        "bullish_engulfing",
        "three_white_soldiers",
    ]
    # recency counted in single candles: the newest wins
    single = cp.layout(dets, every, 1, recent_candles=1)
    assert ids_of(single.labels) == ["doji"]


def test_with_the_trend_before_against_it():
    dets = [det("hammer", 28, 28), det("shooting_star", 27, 27)]
    falling = cp.layout(dets, every, 1, trend="down")
    rising = cp.layout(dets, every, 1, trend="up")
    assert ids_of(falling.labels) == ["shooting_star"]  # bearish, with the trend
    assert ids_of(rising.labels) == ["hammer"]
    assert ids_of(cp.layout(dets, every, 1).labels) == ["hammer"]  # no trend: newest


def test_the_weights_set_the_order_and_0_leaves_a_criterion_out():
    dets = dojis_and_soldiers()
    longest = cp.layout(
        dets, every, 1, rank={"trade": 0, "recent": 1, "bars": 9, "trend": 0}
    )
    assert ids_of(longest.labels) == ["three_white_soldiers"]
    assert cp.ranked_criteria({"trade": 0, "recent": 1, "bars": 9, "trend": 0}) == [
        "bars",
        "recent",
    ]
    assert cp.ranked_criteria(cp.DEFAULT_RANK) == ["trade", "recent", "bars", "trend"]
    none = cp.layout(dets, every, 1, rank={k: 0 for k in cp.RANK_CRITERIA})
    assert [lb.detection.last_index for lb in none.labels] == [28]  # then the newest


def test_the_current_trend_uses_the_patterns_trend_rule():
    rising = [cp.Bar(k * HOUR, 100 + k, 101 + k, 99 + k, 100.5 + k) for k in range(20)]
    falling = [
        cp.Bar(k * HOUR, 120 - k, 121 - k, 119 - k, 119.5 - k) for k in range(20)
    ]
    assert cp.trend_now(rising, HOUR) == "up"
    assert cp.trend_now(falling, HOUR) == "down"
    assert cp.trend_now(rising[:5], HOUR) is None  # too few bars to say


def test_hidden_patterns_take_no_label_slot():
    lay = cp.layout(
        [det("doji", 3, 3), det("hammer", 5, 5)], lambda p: p.id != "doji", 1
    )
    assert [lb.detection.pattern_id for lb in lay.labels] == ["hammer"]
    assert lay.hidden_by_cap == 0


# --- the recorded fixtures (section 13 item 2) ---------------------------------------


def load_fixture(name):
    from market_data.candles import load_candles_csv

    df = load_candles_csv(
        os.path.join(APP_DIR, "tests", "fixtures", f"{name}.csv"), "1h"
    )
    return [
        cp.Bar(int(t.timestamp()), o, h, lo, c)
        for t, o, h, lo, c in zip(df.open_time, df.open, df.high, df.low, df.close)
    ]


@pytest.mark.parametrize("name,soldiers", [("BTCUSDT_1h", 0), ("ETHUSDT_1h", 1)])
def test_three_soldiers_and_crows_are_rare_on_recorded_binance_data(
    name, soldiers, capsys
):
    bars = load_fixture(name)
    used, dets = cp.detect(bars, HOUR)
    counts = {}
    for d in dets:
        counts[d.pattern_id] = counts.get(d.pattern_id, 0) + 1
    with capsys.disabled():
        print(
            f"\n{name}: {len(used)} bars; "
            + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        )
    assert (
        counts.get("three_white_soldiers", 0) == soldiers
    )  # FDS-CHART-001 section 6.3
    assert counts.get("three_black_crows", 0) == 0


def test_no_dropped_pattern_has_a_rule():
    # FDS-CHART-001 section 6.7; the 2-bar doji star survives only inside the 3-bar
    # morning / evening doji stars
    dropped = (
        "window",
        "tasuki",
        "kicker",
        "abandoned",
        "tri_star",
        "separating",
        "counterattack",
        "meeting",
        "on_neck",
        "thrusting",
        "in_neck",
        "ladder",
        "concealing",
        "tower",
        "upthrust",
        "upside_thrust",
    )
    ids = [p.id for p in cp.PATTERNS]
    assert not [i for i in ids if any(word in i for word in dropped)]
    assert "doji_star" not in ids and "bullish_doji_star" not in ids


# --- no published numbers; display only (section 13 items 8 and 9) -------------------


# Owner rule 2026-10-13: displayed text states facts about the coin and textbook
# definitions only. It never names the spec or its sections, the data provider,
# or a design decision.
NOT_ON_SCREEN = (
    "fds",
    "section",
    "\u00a7",
    "binance",
    "kucoin",
    "measured",
    "forecast",
    "statistic",
    "reliab",
    "variant",
    "24/7 bars",
    "not required here",
    "shown instead",
    "owner",
)


def test_pattern_text_states_only_textbook_definitions():
    for p in cp.PATTERNS:
        text = " ".join([p.name, p.explanation, p.reference, p.note]).lower()
        assert not [w for w in NOT_ON_SCREEN if w in text], p.id


def test_no_pattern_text_carries_a_percentage_or_hit_rate():
    texts = []
    for p in cp.PATTERNS:
        texts += [p.name, p.explanation, p.reference, p.note]
    bad = [
        t
        for t in texts
        if re.search(r"\d\s*%|percent|hit rate|success rate|accuracy", t, re.I)
    ]
    assert not bad


def _imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_the_detection_and_settings_modules_are_pure():
    for name in ("candlestick_patterns.py", "chart_settings.py"):
        assert not _imports(os.path.join(APP_DIR, name)) & {
            "tkinter",
            "matplotlib",
            "pt_hub",
        }


def test_nothing_that_trades_or_trains_imports_the_chart_pattern_code():
    chart_modules = {"candlestick_patterns", "chart_settings", "pt_chart_patterns"}
    files = [
        os.path.join(APP_DIR, f)
        for f in (
            "signal_engine.py",
            "pt_trader.py",
            "pt_thinker.py",
            "pt_pattern_trainer.py",
        )
    ]
    strategies = os.path.join(APP_DIR, "strategies")
    files += [
        os.path.join(strategies, f) for f in os.listdir(strategies) if f.endswith(".py")
    ]
    offenders = [f for f in files if _imports(f) & chart_modules]
    assert not offenders
