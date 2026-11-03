"""Which pattern labels a coin chart shows when more are found than the label cap
(owner, 2026-11-04): the filters first, then the ranking, then the cap; the hidden
ones are counted and shown when the pointer is on their candle; the ranking's
weights are set in Chart settings.

Real CandleCharts on a hidden Tk root, fake candles and bars (no network), under the
isolation guard (app/conftest.py).
"""

import os
import sys
from types import SimpleNamespace

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import candlestick_patterns as cp  # noqa: E402
import chart_settings as cs  # noqa: E402
from test_chart_settings_and_overlays import (  # noqa: E402,F401  (fixtures)
    HOUR,
    STARTS_UNTICKED,
    T0,
    as_candles,
    make_chart,
    refresh,
    tk_root,
)


def many_small_patterns(n=60):
    """Dojis and spinning tops on a flat base: many detections."""
    rows = []
    for k in range(n):
        c = 100.05 if k % 3 else 100.4
        rows.append((100.0, 100.9, 99.5, c))
    return [cp.Bar(T0 + k * HOUR, *r) for k, r in enumerate(rows)]


TICKED = {  # the patterns that start unticked, on: many labels
    "items": {i: True for i in STARTS_UNTICKED},
    "filters": {"none": True, "indecision": True},
    "max_labels": 3,
}


def test_the_weights_default_to_the_owners_order_and_are_checked():
    pats = cs.defaults()["patterns"]
    assert pats["rank"] == {"trade": 4, "recent": 3, "bars": 2, "trend": 1}
    assert pats["recent_candles"] == 3
    cfg = cs.normalize(
        {
            "patterns": {
                "rank": {"trade": 99, "recent": -3, "bars": "x", "trend": True},
                "recent_candles": 500,
            }
        }
    )
    assert cfg["patterns"]["rank"] == {"trade": 9, "recent": 0, "bars": 2, "trend": 1}
    assert cfg["patterns"]["recent_candles"] == cp.RECENT_CANDLES_RANGE[1]


def test_the_chart_ranks_its_own_trades_candles_first(make_chart):
    bars = many_small_patterns()
    candles = as_candles(bars)
    trade_ts = candles[10]["ts"]  # an old candle: without the trade it would be hidden
    chart = make_chart(
        candles, chart_cfg={"patterns": TICKED}, bars=bars, trade_ts=trade_ts
    )
    refresh(chart)
    layer = chart.pattern_layer
    assert layer.trade_ts == [trade_ts]
    shown = [rec["label"].detection for rec in layer.records]
    assert any(d.first_ts <= trade_ts <= d.last_ts + HOUR for d in shown)
    assert len(shown) == 3 and layer.hidden_by_cap == len(layer.hidden) > 0


def test_a_hidden_label_shows_while_the_pointer_is_on_its_candle(make_chart):
    bars = many_small_patterns()
    candles = as_candles(bars)
    chart = make_chart(candles, chart_cfg={"patterns": TICKED}, bars=bars)
    refresh(chart)
    layer = chart.pattern_layer
    assert (
        "hidden by the label cap (point at a candle"
        in chart.patterns_status_label.cget("text")
    )
    hidden = layer.hidden[0]
    x = next(i for i, c in enumerate(candles) if c["ts"] == hidden.detection.last_ts)
    before = chart.ax.get_ylim()
    layer._on_motion(SimpleNamespace(x=None, y=None, inaxes=chart.ax, xdata=float(x)))
    texts = [a.get_text() for a in layer._overlay if hasattr(a, "get_text")]
    assert any(hidden.pattern.name in t for t in texts)
    assert chart.ax.get_ylim() == before  # inside the frame: nothing moves
    # off its candle the label goes again
    layer._on_motion(SimpleNamespace(x=None, y=None, inaxes=None, xdata=None))
    assert layer._overlay == []


def test_the_ranking_weights_are_set_in_chart_settings(tk_root):
    from pt_chart_patterns import ChartSettingsWindow

    seen = []
    win = ChartSettingsWindow(tk_root, {}, seen.append)
    try:
        win.rank_vars["bars"].set(9)
        assert seen[-1]["patterns"]["rank"]["bars"] == 9
        win.recent_candles_var.set(5)
        assert seen[-1]["patterns"]["recent_candles"] == 5
        win.reset()
        assert seen[-1]["patterns"]["rank"] == cp.DEFAULT_RANK
        assert seen[-1]["patterns"]["recent_candles"] == cp.DEFAULT_RECENT_CANDLES
    finally:
        win.destroy()
