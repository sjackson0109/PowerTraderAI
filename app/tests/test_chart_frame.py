"""The coin chart is framed once (owner, 2026-11-04): its price range holds everything
it shows, is set before any layer is drawn, and stays put while the layers (candles,
lines, tags, trade dots, pattern labels) are drawn, until the coin, the timeframe,
the candles shown or the window size change, or something falls outside it.

Real CandleCharts on a hidden Tk root, fake candles and bars (no network), under the
isolation guard (app/conftest.py).
"""

import os
import sys

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_hub  # noqa: E402
from test_chart_settings_and_overlays import (  # noqa: E402,F401  (fixtures)
    as_candles,
    boxes,
    down_then_engulfing,
    make_chart,
    many_bars,
    refresh,
    rising_then_hikkake,
    tk_root,
    wide_and_short,
)


def frame_of(chart):
    """The plot's price range and its place in the figure."""
    pos = chart.ax.get_position()
    return tuple(chart.ax.get_ylim()), (pos.x0, pos.y0, pos.x1, pos.y1)


def every_price_shown(chart, candles, lines):
    prices = [c["low"] for c in candles] + [c["high"] for c in candles] + list(lines)
    return min(prices), max(prices)


def test_the_range_holds_every_candle_line_and_trade_dot(make_chart):
    candles = as_candles(down_then_engulfing())
    chart = make_chart(candles)
    wide_and_short(chart)
    refresh(chart)  # lines at 98.0 (DCA) .. 102.0 (SELL); the levels 100.2, 101.5
    lo, hi = chart.ax.get_ylim()
    low, high = every_price_shown(
        chart, candles, [98.0, 99.5, 100.8, 101.0, 102.0, 100.2, 101.5, 100.5]
    )
    assert lo < low and high < hi
    assert not chart.ax.get_autoscaley_on() and not chart.ax.get_autoscalex_on()


def test_no_layer_moves_the_frame(make_chart, monkeypatch):
    """Every limit the axes get during a refresh is the frame's: the layers are drawn
    after it is set, with autoscaling off."""
    candles = as_candles(rising_then_hikkake())
    chart = make_chart(candles, bars=rising_then_hikkake())
    wide_and_short(chart)
    refresh(chart)  # the first time: framed with the labels' room
    settled = frame_of(chart)
    seen = []
    real = chart.ax.set_ylim

    def spy(*args, **kwargs):
        seen.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(chart.ax, "set_ylim", spy)
    refresh(chart)  # the same coin, timeframe and candles
    assert frame_of(chart) == settled
    assert all(tuple(a) == settled[0] for a in seen)


def test_the_first_drawing_already_has_room_for_the_pattern_labels(make_chart):
    """The chart waits for the first pattern detection, so the labels never widen
    the range after the candles are on screen."""
    bars = rising_then_hikkake()
    chart = make_chart(as_candles(bars), bars=bars)
    wide_and_short(chart)
    chart.refresh({"BTC": chart.folder}, current_buy_price=101.0)
    assert len(chart.ax.patches) == 0  # nothing drawn yet: the patterns are coming
    chart.pattern_layer.wait()  # they arrive; the chart is drawn once, with them
    assert len(chart.ax.patches) and chart.pattern_layer.records
    drawn = frame_of(chart)
    chart.pattern_layer.redraw()  # the labels again: same frame
    assert frame_of(chart) == drawn
    ax, _ = boxes(chart)
    for rec in chart.pattern_layer.records:
        box = rec["artist"].get_window_extent()
        assert ax.y0 <= box.y0 and box.y1 <= ax.y1  # inside the plot


def test_labels_that_arrive_late_go_inside_the_frame(make_chart):
    """When the detection takes longer than the wait, the chart is drawn without
    them, and their labels later go inside the range it already has."""
    bars = rising_then_hikkake()
    chart = make_chart(as_candles(bars), bars=bars)
    wide_and_short(chart)
    chart.refresh({"BTC": chart.folder}, current_buy_price=101.0)
    chart._stop_waiting((chart.coin, "1hour"))  # the wait ran out
    assert len(chart.ax.patches) and chart.pattern_layer.records == []
    before = frame_of(chart)
    chart.pattern_layer.wait()
    assert chart.pattern_layer.records
    assert frame_of(chart) == before


def test_price_tags_appearing_later_do_not_resize_the_plot(make_chart):
    """The tag strip is kept for the tags the chart could show, so when the trader
    reports its prices the plot keeps its place."""
    candles = as_candles(many_bars())
    chart = make_chart(candles)
    wide_and_short(chart)
    refresh(
        chart,
        current_buy_price=None,
        current_sell_price=None,
        trail_line=None,
        dca_line_price=None,
        avg_cost_basis=None,
    )
    assert chart._price_tags == []
    bare = frame_of(chart)
    mid = (candles[-1]["low"] + candles[-1]["high"]) / 2
    refresh(
        chart,
        current_buy_price=mid,
        current_sell_price=mid,
        trail_line=None,
        dca_line_price=None,
        avg_cost_basis=None,
    )
    assert len(chart._price_tags) == 2
    assert frame_of(chart) == bare


def test_a_line_outside_the_frame_reframes_once(make_chart):
    candles = as_candles(down_then_engulfing())
    chart = make_chart(candles)
    wide_and_short(chart)
    refresh(chart)
    lo, hi = chart.ax.get_ylim()
    refresh(chart, dca_line_price=lo - 5.0)  # a DCA line well below: reframed
    assert chart.ax.get_ylim()[0] < lo - 5.0
    again = frame_of(chart)
    refresh(chart, dca_line_price=lo - 5.0)
    assert frame_of(chart) == again


def test_a_new_candle_or_another_window_size_reframes(make_chart):
    candles = as_candles(many_bars())
    chart = make_chart(candles)
    wide_and_short(chart)
    refresh(chart)
    first = chart._frame["key"]
    chart.fetcher.candles = as_candles(many_bars(), shift=1)  # one candle on
    refresh(chart)
    assert chart._frame["key"] != first  # the visible range moved
    framed_at = chart._frame["size"]
    wide_and_short(chart, w=900, h=500)
    chart._last_canvas_px = (900, 500)
    chart._fit_and_draw()
    assert chart._frame["size"] == (900, 500) != framed_at


def test_the_frame_key_is_the_coin_timeframe_and_candles_shown(make_chart):
    chart = make_chart(as_candles(down_then_engulfing()))
    refresh(chart)
    coin, tf, first_ts, n = chart._frame["key"]
    assert (coin, tf, n) == ("BTC", "1hour", len(down_then_engulfing()))
    assert first_ts == as_candles(down_then_engulfing())[0]["ts"]


def test_the_runners_placeholder_level_is_not_a_price(make_chart, monkeypatch):
    """The runner writes 0.01 for a timeframe with no prediction: it is not drawn
    into the range (the chart would otherwise reach down to a cent)."""
    candles = as_candles(down_then_engulfing())
    monkeypatch.setattr(
        pt_hub,
        "read_price_levels_from_html",
        lambda p: [pt_hub.NEURAL_PLACEHOLDER_LOW, 100.2],
    )
    chart = make_chart(candles)
    refresh(chart)
    assert chart.ax.get_ylim()[0] > 90
