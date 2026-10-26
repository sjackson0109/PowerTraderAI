"""Chart settings, overlay toggles and candlestick labels on the coin chart
(FDS-CHART-001 sections 4, 7, 8, 9 and 13, items 3-7).

The chart is a real CandleChart in a hidden Tk root, fed by a fake KuCoin fetcher. Its
pattern layer uses a fake Binance fetch, so nothing touches the network.
"""

import json
import math
import os
import sys
import threading
import types

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import candlestick_patterns as cp  # noqa: E402
import chart_settings as cs  # noqa: E402
import ui_tokens  # noqa: E402
from helpers_colour import contrast as _contrast  # noqa: E402
from helpers_colour import linear as _lin  # noqa: E402
from helpers_colour import rgb as _rgb  # noqa: E402
from test_candlestick_patterns import NOT_ON_SCREEN  # noqa: E402
from market_data import listing  # noqa: E402

HOUR = 3600
T0 = 1_700_000_000 - 1_700_000_000 % HOUR


# --- settings: normalising and the visibility rule (section 8) ----------------------


STARTS_UNTICKED = {
    "doji",
    "four_price_doji",
    "long_legged_doji",
    "dragonfly_doji",
    "gravestone_doji",
    "spinning_top_white",
    "spinning_top_black",
    "high_wave",
    "inside_bar",
    "rising_three_methods",
    "falling_three_methods",
    "mat_hold",
}


def test_defaults_show_every_existing_overlay_and_the_owners_filters():
    cfg = cs.normalize(None)
    assert all(cfg["overlays"].values()) and len(cfg["overlays"]) == len(cs.OVERLAYS)
    filters = cfg["patterns"]["filters"]
    # owner decision 2026-10-13
    assert filters == {
        "bullish": True,
        "bearish": True,
        "none": False,
        "reversal": True,
        "continuation": False,
        "indecision": False,
        "classical": True,
        "price_action": True,
    }
    assert (cfg["patterns"]["max_labels"], cfg["palette"], cfg["candle_style"]) == (
        12,
        "default",
        "filled",
    )


def test_patterns_in_a_filter_that_starts_off_start_unticked():
    """Owner decisions 2026-10-13: every no-direction, continuation and indecision
    pattern is off by default; every other pattern, three white soldiers and three
    black crows included, is on."""
    items = cs.normalize(None)["patterns"]["items"]
    off = {k for k, v in items.items() if not v}
    assert off == STARTS_UNTICKED
    assert off == {
        p.id
        for p in cp.PATTERNS
        if p.kind in ("indecision", "continuation") or p.direction == "none"
    }
    assert {"rising_three_methods", "falling_three_methods", "mat_hold"} <= off
    shown = visible_ids(cs.normalize(None))
    assert {"three_white_soldiers", "three_black_crows"} <= shown
    assert not shown & STARTS_UNTICKED
    ticked = {"items": {"doji": True}}
    assert "doji" not in visible_ids(cs.normalize({"patterns": ticked}))
    ticked["filters"] = {"none": True, "indecision": True}
    assert "doji" in visible_ids(cs.normalize({"patterns": ticked}))


def test_missing_keys_take_defaults_and_unknown_keys_are_kept():
    raw = {
        "overlays": {"ask": False},
        "patterns": {"items": {"hammer": False}},
        "future": {"x": 1},
    }
    cfg = cs.normalize(raw)
    assert cfg["overlays"]["ask"] is False and cfg["overlays"]["bid"] is True
    assert cfg["patterns"]["items"]["hammer"] is False
    # not stored: a later pattern takes its own default
    assert cfg["patterns"]["items"]["morning_star_247"] is True
    assert cfg["patterns"]["items"]["doji"] is False
    assert cfg["future"] == {"x": 1}


def test_bad_values_fall_back_and_the_label_cap_is_clamped():
    cfg = cs.normalize(
        {
            "overlays": {"ask": "no"},
            "patterns": {"max_labels": 999},
            "palette": "neon",
            "candle_style": 3,
        }
    )
    assert cfg["overlays"]["ask"] is True
    assert cfg["patterns"]["max_labels"] == cs.MAX_LABELS_RANGE[1]
    assert (cfg["palette"], cfg["candle_style"]) == ("default", "filled")
    assert (
        cs.normalize({"patterns": {"max_labels": "x"}})["patterns"]["max_labels"] == 12
    )


def visible_ids(cfg):
    return {p.id for p in cp.PATTERNS if cs.pattern_visible(cfg, p)}


def test_only_bullish_patterns():
    """The owner's example: untick Bearish and No direction."""
    cfg = cs.normalize(
        {
            "patterns": {
                "filters": {"bearish": False, "none": False, "price_action": True}
            }
        }
    )
    shown = visible_ids(cfg)
    assert all(cp.BY_ID[i].direction == "bullish" for i in shown)
    assert (
        "hammer" in shown and "bearish_engulfing" not in shown and "doji" not in shown
    )
    assert "three_white_soldiers" in shown and "three_black_crows" not in shown


def test_no_doji_stars():
    """The owner's example: untick the doji stars, or Indecision for every doji."""
    cfg = cs.normalize(
        {
            "patterns": {
                "items": {
                    "morning_doji_star_247": False,
                    "evening_doji_star_247": False,
                }
            }
        }
    )
    shown = visible_ids(cfg)
    assert "morning_doji_star_247" not in shown and "evening_doji_star_247" not in shown
    assert "morning_star_247" in shown and "doji" not in shown  # doji starts off
    no_indecision = visible_ids(
        cs.normalize({"patterns": {"filters": {"indecision": False}}})
    )
    assert (
        not {"doji", "long_legged_doji", "dragonfly_doji", "gravestone_doji"}
        & no_indecision
    )


def test_the_master_toggle_hides_every_pattern():
    assert visible_ids(cs.normalize({"patterns": {"enabled": False}})) == set()


@pytest.mark.parametrize(
    "patterns",
    [
        {"items": {"three_white_soldiers": False, "three_black_crows": False}},
        {"filters": {"reversal": False}},
        {"filters": {"classical": False}},
    ],
)
def test_three_soldiers_and_crows_can_be_hidden(patterns):
    """Owner decision 2026-10-13: no longer always visible."""
    shown = visible_ids(cs.normalize({"patterns": patterns}))
    assert not {"three_white_soldiers", "three_black_crows"} & shown


# --- colour (section 9) --------------------------------------------------------------

PANEL = "#0E1626"
MACHADO = {  # Machado, Oliveira and Fernandes (2009), severity 1.0, on linear RGB
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
}


def _gamma(c):
    c = min(1.0, max(0.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _over(fg, bg, alpha=0.9):
    return tuple(alpha * f + (1 - alpha) * b for f, b in zip(fg, bg))


def _simulate(rgb, kind):
    if kind is None:
        return rgb
    lin = [_lin(c) for c in rgb]
    m = MACHADO[kind]
    return tuple(_gamma(sum(m[r][k] * lin[k] for k in range(3))) for r in range(3))


def _lab(rgb):
    r, g, b = (_lin(c) for c in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def _de2000(l1, l2):
    (L1, a1, b1), (L2, a2, b2) = l1, l2
    cb = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(cb**7 / (cb**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p, h2p = (
        math.degrees(math.atan2(b1, a1p)) % 360,
        math.degrees(math.atan2(b2, a2p)) % 360,
    )
    dh = 0 if c1p * c2p == 0 else (h2p - h1p + 180) % 360 - 180
    dHp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    lbp, cbp = (L1 + L2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    else:
        hbp = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(hbp - 30))
        + 0.24 * math.cos(math.radians(2 * hbp))
        + 0.32 * math.cos(math.radians(3 * hbp + 6))
        - 0.20 * math.cos(math.radians(4 * hbp - 63))
    )
    rc = 2 * math.sqrt(cbp**7 / (cbp**7 + 25**7))
    sl = 1 + 0.015 * (lbp - 50) ** 2 / math.sqrt(20 + (lbp - 50) ** 2)
    sc, sh = 1 + 0.045 * cbp, 1 + 0.015 * cbp * t
    rt = -math.sin(math.radians(60 * math.exp(-(((hbp - 275) / 25) ** 2)))) * rc
    dLs, dCs, dHs = (L2 - L1) / sl, (c2p - c1p) / sc, dHp / sh
    return math.sqrt(dLs**2 + dCs**2 + dHs**2 + rt * dCs * dHs)


def _measures(pal, kind):
    panel = _rgb(PANEL)
    up, down = _over(_rgb(pal["up"]), panel), _over(_rgb(pal["down"]), panel)
    u, d, p = _simulate(up, kind), _simulate(down, kind), _simulate(panel, kind)
    return _contrast(u, p), _contrast(d, p), _de2000(_lab(u), _lab(d))


@pytest.mark.parametrize("kind", [None, "protanopia", "deuteranopia"])
def test_the_alternate_palette_meets_every_colour_criterion(kind):
    up, down, de = _measures(cs.PALETTES["blue_vermilion"], kind)
    assert up >= 3.0 and down >= 3.0  # WCAG 1.4.11 against the panel
    assert de >= 20  # up and down stay distinct for dichromats


def test_the_default_palette_is_unchanged_and_relies_on_hollow_up_for_dichromats():
    """The owner kept today's colours. They meet 3:1 for typical vision only; under
    simulated dichromacy they do not, which is why 'hollow up' exists (section 9)."""
    assert (
        cs.PALETTES["default"]["up"] == "#008000"
        and cs.PALETTES["default"]["down"] == "#FF0000"
    )
    up, down, _ = _measures(cs.PALETTES["default"], None)
    assert up >= 3.0 and down >= 3.0
    assert _measures(cs.PALETTES["default"], "protanopia")[2] < 20
    assert "hollow_up" in cs.CANDLE_STYLES


# --- the chart (needs Tk) ------------------------------------------------------------


@pytest.fixture
def tk_root():
    import tkinter as tk

    # On Windows, Tk sometimes fails to read init.tcl on the first try (see
    # helpers_trainer.build_real_hub); retry before skipping.
    root, error = None, None
    for _ in range(10):
        try:
            root = tk.Tk()
            break
        except tk.TclError as exc:
            error = exc
    if root is None:
        pytest.skip(f"Tk not available: {error}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


def down_then_engulfing():
    rows = []
    for k in range(30):
        c = 100.0 + (29 - k)
        o = c + 1
        rows.append((o, o + 0.5, c - 0.5, c))
    rows += [(100.5, 100.7, 99.3, 99.5), (99.5, 100.9, 99.4, 100.8)]
    return [cp.Bar(T0 + k * HOUR, *r) for k, r in enumerate(rows)]


def as_candles(bars, shift=0):
    return [
        {
            "ts": b.ts + shift,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
        }
        for b in bars
    ]


class FakeCandles:
    def __init__(self, candles):
        self.candles = candles

    def get_klines(self, coin, tf, limit=120):
        return list(self.candles)


class FakeBars:
    def __init__(self, bars, error=None):
        self.bars, self.error, self.calls, self.threads = bars, error, [], []

    def __call__(self, coin, interval, start_ts, end_ts):
        self.calls.append((coin, interval, start_ts, end_ts))
        self.threads.append(threading.current_thread())
        if self.error:
            raise self.error
        return [b for b in self.bars if start_ts <= b.ts <= end_ts]


@pytest.fixture
def make_chart(tk_root, tmp_path, monkeypatch):
    import pt_hub

    folder = tmp_path / "BTC"
    folder.mkdir()
    for name, text in (
        ("low_bound_prices.html", "x"),
        ("high_bound_prices.html", "x"),
        ("long_dca_signal.txt", "3"),
        ("short_dca_signal.txt", "0"),
    ):
        (folder / name).write_text(text, encoding="utf-8")
    levels = {"low_bound_prices.html": [100.2], "high_bound_prices.html": [101.5]}
    monkeypatch.setattr(
        pt_hub, "read_price_levels_from_html", lambda p: levels[os.path.basename(p)]
    )
    history = tmp_path / "trade_history.jsonl"

    def build(candles, chart_cfg=None, bars=None, trade_ts=None):
        settings = {
            "default_timeframe": "1hour",
            "timeframes": ["1hour"],
            "candles_limit": 120,
        }
        if chart_cfg is not None:
            settings["chart"] = chart_cfg
        ts = trade_ts if trade_ts is not None else candles[len(candles) // 2]["ts"]
        history.write_text(
            json.dumps({"symbol": "BTC-USD", "side": "buy", "ts": ts, "price": 100.5})
            + "\n"
        )
        chart = pt_hub.CandleChart(
            tk_root, FakeCandles(candles), "BTC", lambda: settings, str(history)
        )
        fake = FakeBars(bars if bars is not None else [])
        chart.pattern_layer.fetch_bars = fake
        last = max(b.ts for b in bars) if bars else candles[-1]["ts"]
        chart.pattern_layer.clock = lambda: last + HOUR + 1
        chart.settings = settings
        chart.fake_bars = fake
        chart.folder = str(folder)
        return chart

    return build


def refresh(chart):
    chart.refresh(
        {"BTC": chart.folder},
        current_buy_price=101.0,
        current_sell_price=100.8,
        trail_line=102.0,
        dca_line_price=98.0,
        avg_cost_basis=99.5,
    )


LINES = ui_tokens.CHART_LINES
OVERLAY_MARKS = {  # key -> (line colour, right-edge label prefix)
    "neural_long": (LINES["neural_long"], None),
    "neural_short": (LINES["neural_short"], None),
    "ask": (LINES["ask"], "ASK"),
    "bid": (LINES["bid"], "BID"),
    "avg": (LINES["avg"], "AVG"),
    "dca": (LINES["dca"], "DCA"),
    "trail": (LINES["trail"], "SELL"),
}


def drawn(chart):
    # level lines are horizontal; candle wicks (one is the DCA line's red) are not
    lines = {
        line.get_color() for line in chart.ax.lines if len(set(line.get_ydata())) == 1
    }
    texts = [t.get_text() for t in chart.ax.texts]
    out = {}
    for key, (colour, prefix) in OVERLAY_MARKS.items():
        out[key] = colour in lines and (
            prefix is None or any(t.startswith(prefix) for t in texts)
        )
    out["trades"] = bool(chart.ax.collections) and any(t == "BUY" for t in texts)
    out["neural_readout"] = chart.neural_status_label.cget("text").startswith("Neural:")
    return out


def test_by_default_every_overlay_is_drawn_as_before(make_chart):
    chart = make_chart(as_candles(down_then_engulfing()))
    refresh(chart)
    assert drawn(chart) == {key: True for key, _, _ in cs.OVERLAYS}


@pytest.mark.parametrize("key", [k for k, _, _ in cs.OVERLAYS])
def test_each_overlay_toggle_hides_exactly_its_own_element(make_chart, key):
    chart = make_chart(
        as_candles(down_then_engulfing()), chart_cfg={"overlays": {key: False}}
    )
    refresh(chart)
    expected = {k: k != key for k, _, _ in cs.OVERLAYS}
    assert drawn(chart) == expected


def test_the_palette_and_hollow_up_change_the_candles(make_chart):
    chart = make_chart(
        as_candles(down_then_engulfing()),
        chart_cfg={"palette": "blue_vermilion", "candle_style": "hollow_up"},
    )
    refresh(chart)
    from matplotlib.colors import to_hex

    bodies = [
        p for p in chart.ax.patches if getattr(p, "get_width", lambda: 0)() == 0.7
    ]
    up = [p for p in bodies if to_hex(p.get_edgecolor()) == "#56b4e9"]
    down = [p for p in bodies if to_hex(p.get_edgecolor()) == "#d55e00"]
    assert up and down
    assert all(p.get_facecolor()[3] == 0 for p in up)  # hollow
    assert all(to_hex(p.get_facecolor()) == "#d55e00" for p in down)


# --- candlestick labels on the chart (sections 4, 5.4, 7) ---------------------------


def labels(chart):
    return {
        r["label"].detection.pattern_id: r["x_last"]
        for r in chart.pattern_layer.records
    }


def test_labels_come_from_binance_bars_off_the_tk_thread_and_sit_on_their_candle(
    make_chart,
):
    bars = down_then_engulfing()
    chart = make_chart(as_candles(bars), bars=bars)
    refresh(chart)
    chart.pattern_layer.wait()
    assert labels(chart).get("bullish_engulfing") == len(bars) - 1
    fake = chart.fake_bars
    assert fake.calls and fake.calls[0][:2] == ("BTC", "1h")
    assert all(t is not threading.main_thread() for t in fake.threads)


def test_a_label_follows_its_candle_when_the_window_shifts(make_chart):
    bars = down_then_engulfing()
    chart = make_chart(as_candles(bars), bars=bars)
    refresh(chart)
    chart.pattern_layer.wait()
    nxt = cp.Bar(bars[-1].ts + HOUR, 100.8, 101.0, 100.6, 100.9)
    chart.fetcher.candles = as_candles(bars[1:] + [nxt])
    refresh(chart)
    assert (
        labels(chart).get("bullish_engulfing") == len(bars) - 2
    )  # same open time, one place left


def test_a_detection_with_no_matching_chart_candle_is_listed_not_drawn(make_chart):
    bars = down_then_engulfing()
    chart = make_chart(
        as_candles(bars, shift=1800), bars=bars
    )  # chart bars open half an hour later
    refresh(chart)
    chart.pattern_layer.wait()
    layer = chart.pattern_layer
    assert "bullish_engulfing" not in labels(chart)
    assert any(d.pattern_id == "bullish_engulfing" for d in layer.undrawn)
    assert "not on this chart" in chart.patterns_status_label.cget("text")


def test_a_coin_recorded_not_trading_gets_a_note_and_no_fetch(make_chart):
    bars = down_then_engulfing()
    chart = make_chart(as_candles(bars), bars=bars)
    listing.write_market_status(chart.folder, "BTCUSDT", False, "delisted")
    refresh(chart)
    assert (
        chart.patterns_status_label.cget("text")
        == "Candlestick patterns: not available for this coin"
    )
    assert chart.fake_bars.calls == []


def test_a_coin_no_exchange_has_is_a_note_not_an_error(make_chart):
    from pt_exchange_abstraction import MarketNotFound

    bars = down_then_engulfing()
    chart = make_chart(as_candles(bars), bars=bars)
    chart.fake_bars.error = MarketNotFound("No exchange has a market for BTC-USD")
    refresh(chart)
    chart.pattern_layer.wait()
    assert (
        chart.patterns_status_label.cget("text")
        == "Candlestick patterns: not available for this coin"
    )


def test_the_label_cap_hides_the_rest_and_says_so(make_chart):
    rows = []
    for k in range(60):  # dojis and spinning tops on a flat base: many detections
        o = 100.0
        c = 100.05 if k % 3 else 100.4
        rows.append((o, 100.9, 99.5, c))
    bars = [cp.Bar(T0 + k * HOUR, *r) for k, r in enumerate(rows)]
    ticked = {  # off by default
        "items": {i: True for i in STARTS_UNTICKED},
        "filters": {"none": True, "indecision": True},
        "max_labels": 2,
    }
    chart = make_chart(as_candles(bars), chart_cfg={"patterns": ticked}, bars=bars)
    refresh(chart)
    chart.pattern_layer.wait()
    assert len(chart.pattern_layer.records) == 2
    assert "hidden by the label cap" in chart.patterns_status_label.cget("text")


def test_hover_brackets_click_explains_and_the_keyboard_steps(make_chart):
    bars = down_then_engulfing()
    chart = make_chart(as_candles(bars), bars=bars)
    refresh(chart)
    chart.pattern_layer.wait()
    layer = chart.pattern_layer
    rec = next(
        r
        for r in layer.records
        if r["label"].detection.pattern_id == "bullish_engulfing"
    )
    layer._set_hover(rec)
    assert any(
        getattr(a, "get_linestyle", lambda: "")() == "--" for a in layer._overlay
    )
    text = layer.hover_text(rec["label"])
    assert "Bullish engulfing" in text and "Trend into: falling" in text
    win = layer.open_detail(rec)
    body = "\n".join(layer.detail_lines(rec["label"]))
    assert "After a fall: a white body that covers" in body
    assert "Reference: TA-Lib (CDLENGULFING)" in body and "%" not in body
    shown = (text + body).lower()
    assert not [w for w in NOT_ON_SCREEN if w in shown]
    layer.close_detail()
    assert not win.winfo_exists()
    layer._on_key(types.SimpleNamespace(key="right"))
    assert layer._selected is not None and layer._hover is not None
    layer._on_key(types.SimpleNamespace(key="escape"))
    assert layer._selected is None and layer._hover is None


def test_a_hover_survives_the_next_refresh(make_chart):
    bars = down_then_engulfing()
    chart = make_chart(as_candles(bars), bars=bars)
    refresh(chart)
    chart.pattern_layer.wait()
    layer = chart.pattern_layer
    layer._set_hover(layer.records[-1])
    key = layer._hover_key
    refresh(chart)
    assert layer._hover is not None and layer._hover_key == key


def test_hidden_patterns_are_not_drawn(make_chart):
    bars = down_then_engulfing()
    chart = make_chart(
        as_candles(bars),
        chart_cfg={"patterns": {"filters": {"bullish": False}}},
        bars=bars,
    )
    refresh(chart)
    chart.pattern_layer.wait()
    assert "bullish_engulfing" not in labels(chart)


# --- the chart fills its area -------------------------------------------------------

NO_PRICE_TAGS = {key: False for key in ("ask", "bid", "avg", "dca", "trail")}


def rising_then_hikkake():
    """An uptrend whose last bar confirms a bullish Hikkake on the highest high, so its
    label sits above the top of the candle range, on the last candle."""
    rows = []
    for k in range(30):
        c = 100.0 + k
        rows.append((c - 1, c + 0.5, c - 1.5, c))
    rows += [
        (129, 135, 127, 133),
        (132, 134, 128.5, 130),
        (130, 133, 128, 129),
        (129, 137, 128.8, 136.5),
    ]
    return [cp.Bar(T0 + k * HOUR, *r) for k, r in enumerate(rows)]


def many_bars(n=120):
    """A full chart window: the last candle sits close to the plot's right edge, so a
    date label centred on it would hang past the plot."""
    rows = []
    for k in range(n):
        c = 100.0 + 5 * math.sin(k / 9)
        o = 100.0 + 5 * math.sin((k - 1) / 9)
        rows.append((o, max(o, c) + 0.4, min(o, c) - 0.4, c))
    return [cp.Bar(T0 + k * HOUR, *r) for k, r in enumerate(rows)]


def wide_and_short(chart, w=1200, h=335):
    """The size of the coin chart in the owner's screenshot of 2026-10-14."""
    chart.fig.set_size_inches(w / chart.fig.dpi, h / chart.fig.dpi)


def boxes(chart):
    chart.canvas.draw()
    return chart.ax.get_window_extent(), chart.fig.bbox


EDGE_PX = 10  # most empty space between the outermost text and the chart's edge


def edge_gaps(chart):
    """Empty pixels between the chart's outermost text and the top, bottom and left
    edges."""
    from matplotlib.transforms import Bbox

    fig = chart.fig.bbox
    renderer = chart.canvas.get_renderer()
    text = Bbox.union(
        [chart.ax.get_tightbbox(renderer)]
        + [t.get_window_extent(renderer) for t in chart.fig.texts]
    )
    return fig.y1 - text.y1, text.y0 - fig.y0, text.x0 - fig.x0


def test_room_for_labels_widens_the_range_only_as_far_as_the_labels_need():
    from pt_chart_patterns import room_for_labels

    assert room_for_labels(0, 100, [], 300) == (0, 100)
    assert room_for_labels(0, 100, [(50, True, 30)], 300) == (0, 100)  # room already
    lo, hi = room_for_labels(0, 100, [(100, True, 30), (0, False, 60)], 300)
    span = hi - lo
    assert (hi - 100) / span * 300 == pytest.approx(30, rel=1e-6)
    assert (0 - lo) / span * 300 == pytest.approx(60, rel=1e-6)


def test_the_coin_chart_fills_a_wide_short_area(make_chart):
    """Fixed margins left empty strips round the chart's text: 20% of the height above
    and below the plot, 12.5% of the width on the left and 13% on the right."""
    chart = make_chart(as_candles(many_bars()), chart_cfg={"overlays": NO_PRICE_TAGS})
    wide_and_short(chart)
    refresh(chart)
    ax, fig = boxes(chart)
    assert all(0 <= gap < EDGE_PX for gap in edge_gaps(chart))
    time_name = chart._time_name.get_window_extent()
    assert fig.x1 - time_name.x1 < EDGE_PX  # no price tags: only the time name's room
    assert chart.ax.get_xticklabels()[-1].get_window_extent().x1 <= ax.x1


def test_the_axis_names_sit_in_the_corners(make_chart):
    """Owner, 2026-10-14: the price name level at the top left, above the price labels,
    and "Time" at the bottom right, beside the last date, so neither holds a row or a
    column of its own."""
    chart = make_chart(as_candles(many_bars()), chart_cfg={"overlays": NO_PRICE_TAGS})
    wide_and_short(chart)
    refresh(chart)
    ax, fig = boxes(chart)
    assert chart.ax.get_xlabel() == "" and chart.ax.get_ylabel() == ""
    price = chart._price_name
    assert price.get_text() == "BTCUSD" and price.get_rotation() == 0
    box = price.get_window_extent()
    assert box.x0 - fig.x0 < EDGE_PX and ax.y1 <= box.y0 and fig.y1 - box.y1 < EDGE_PX
    lo, hi = chart.ax.get_ylim()
    for label in chart.ax.get_yticklabels():  # the drawn ones, top tick included
        if label.get_text() and lo <= label.get_position()[1] <= hi:
            assert not label.get_window_extent().overlaps(box)
    time_name = chart._time_name.get_window_extent()
    last_date = chart.ax.get_xticklabels()[-1].get_window_extent()
    assert ax.x1 < time_name.x0 and time_name.y1 <= ax.y0  # right of the plot, below it
    assert time_name.y0 >= last_date.y0  # inside the dates' row: no row of its own
    assert last_date.x1 < time_name.x0


def test_the_coin_chart_has_no_title_and_says_when_there_are_no_candles(make_chart):
    """The toolbar above the chart already names the coin and the timeframe."""
    chart = make_chart(as_candles(down_then_engulfing()))
    wide_and_short(chart)
    refresh(chart)
    ax, fig = boxes(chart)
    assert chart.ax.get_title() == ""
    name = chart._price_name.get_window_extent()
    assert ax.y1 <= name.y0 and fig.y1 - name.y1 < EDGE_PX  # only the price name above
    empty = make_chart([], trade_ts=T0, bars=down_then_engulfing())
    refresh(empty)
    assert empty.ax.get_title() == ""
    assert [t.get_text() for t in empty.ax.texts] == ["BTC (1hour): no candles"]


def test_price_tags_get_a_strip_and_a_price_off_the_plot_is_tagged_at_its_edge(
    make_chart,
):
    chart = make_chart(as_candles(down_then_engulfing()))
    wide_and_short(chart)
    refresh(chart)  # DCA 98.0 is below the lowest low, 99.3
    ax, fig = boxes(chart)
    tags = {t.get_text().split()[0]: t for t in chart._price_tags}
    assert set(tags) == {"ASK", "BID", "AVG", "DCA", "SELL"}
    ends = []
    for tag in tags.values():
        box = tag.get_bbox_patch().get_window_extent()
        assert ax.x1 < box.x0 and box.x1 <= fig.x1  # beside the plot, not cut off
        ends.append(box.x1)
    assert fig.x1 - max(ends) < EDGE_PX  # the strip is as wide as the widest tag
    # two lines each (name over price), stacked clear of one another in price order
    assert all(len(t.get_text().split("\n")) == 2 for t in tags.values())
    order = sorted(tags.values(), key=lambda t: t.get_position()[1])
    assert [t.get_text().split()[0] for t in order] == [
        "DCA",
        "AVG",
        "BID",
        "ASK",
        "SELL",
    ]
    for low, high in zip(order, order[1:]):
        assert (
            low.get_bbox_patch().get_window_extent().y1
            <= high.get_bbox_patch().get_window_extent().y0
        )
    lo, hi = chart.ax.get_ylim()
    assert tags["DCA"].get_text().endswith("▼")  # at the bottom of the plot
    assert lo <= tags["DCA"].get_position()[1] <= hi
    assert not tags["SELL"].get_text().endswith(("▲", "▼"))  # 102.0: on it
    time_name = chart._time_name.get_window_extent()
    for tag in tags.values():  # within the plot's height, clear of the time name
        box = tag.get_bbox_patch().get_window_extent()
        assert ax.y0 <= box.y0 and box.y1 <= ax.y1
        assert not box.overlaps(time_name)


def test_a_label_above_the_highest_candle_stays_inside_the_chart(make_chart):
    bars = rising_then_hikkake()
    chart = make_chart(
        as_candles(bars), chart_cfg={"overlays": NO_PRICE_TAGS}, bars=bars
    )
    wide_and_short(chart)
    refresh(chart)
    chart.pattern_layer.wait()  # the labels arrive after the refresh
    rec = next(
        r
        for r in chart.pattern_layer.records
        if r["label"].detection.pattern_id == "hikkake_bullish"
    )
    assert rec["x_last"] == len(bars) - 1 and rec["up"]
    ax, fig = boxes(chart)
    box = rec["artist"].get_window_extent()
    assert box.y1 <= ax.y1  # inside the plot, clear of the title
    assert ax.x0 <= box.x0 and box.x1 <= ax.x1  # the last candle's label is aligned in
    assert chart.ax.get_ylim()[1] > chart._base_ylim[1]  # the range grew to make room


def test_the_tag_strip_shares_the_space_the_last_date_label_holds(make_chart):
    """With a full window the last date label hangs right of the plot. The tags sit
    beside the plot and the label below it, so the strip is not added on top."""
    chart = make_chart(
        as_candles(many_bars()),
        chart_cfg={"overlays": {"avg": False, "dca": False, "trail": False}},
    )
    wide_and_short(chart)
    chart.refresh(
        {"BTC": chart.folder}, current_buy_price=100.6, current_sell_price=100.4
    )
    ax, fig = boxes(chart)
    ends = [t.get_bbox_patch().get_window_extent().x1 for t in chart._price_tags]
    assert len(ends) == 2 and fig.x1 - max(ends) < EDGE_PX


def test_labels_never_cover_the_price_tags_or_the_price_axis(make_chart):
    bars = rising_then_hikkake()
    chart = make_chart(as_candles(bars), bars=bars)  # every price tag on
    wide_and_short(chart)
    refresh(chart)
    chart.pattern_layer.wait()
    ax, fig = boxes(chart)
    tag_boxes = [t.get_window_extent() for t in chart._price_tags]
    assert tag_boxes and chart.pattern_layer.records
    for rec in chart.pattern_layer.records:
        box = rec["artist"].get_window_extent()
        assert ax.x0 <= box.x0 and box.x1 <= ax.x1
        assert not any(box.overlaps(tag) for tag in tag_boxes)


def test_hovering_never_moves_the_plot(make_chart):
    bars = rising_then_hikkake()
    chart = make_chart(
        as_candles(bars), chart_cfg={"overlays": NO_PRICE_TAGS}, bars=bars
    )
    wide_and_short(chart)
    refresh(chart)
    chart.pattern_layer.wait()
    before = chart.ax.get_position().bounds
    layer = chart.pattern_layer
    layer._set_hover(layer.records[-1])  # its "next" and "into" notes sit outside it
    refresh(chart)  # a refresh while hovering fits the layout again
    assert layer._hover is not None
    assert chart.ax.get_position().bounds == pytest.approx(before)


def test_the_account_chart_fills_a_wide_short_area(tk_root, tmp_path):
    import pt_hub

    history = tmp_path / "account_value_history.jsonl"
    history.write_text(
        "".join(
            json.dumps({"ts": T0 + k * 60, "total_account_value": 1000.0 + k}) + "\n"
            for k in range(50)
        )
    )
    chart = pt_hub.AccountValueChart(
        tk_root, str(history), str(tmp_path / "trade_history.jsonl")
    )
    wide_and_short(chart)
    chart.refresh()
    ax, fig = boxes(chart)
    assert all(0 <= gap < EDGE_PX for gap in edge_gaps(chart))
    assert fig.x1 - ax.x1 < EDGE_PX  # the last date label ends inside the plot


# --- the Chart settings pop-out (section 8) ------------------------------------------


def test_the_pop_out_applies_each_change_at_once_and_keeps_unknown_keys(tk_root):
    from pt_chart_patterns import ChartSettingsWindow

    seen = []
    win = ChartSettingsWindow(tk_root, {"future": 1}, seen.append)
    win.overlay_vars["ask"].set(False)
    assert seen[-1]["overlays"]["ask"] is False and seen[-1]["future"] == 1
    win.filter_vars["bearish"].set(False)
    assert seen[-1]["patterns"]["filters"]["bearish"] is False
    win.item_vars["hammer"].set(False)
    assert seen[-1]["patterns"]["items"]["hammer"] is False
    win.palette_var.set("blue_vermilion")
    assert seen[-1]["palette"] == "blue_vermilion"
    assert not win.pattern_checks["three_white_soldiers"].instate(["disabled"])
    win.item_vars["three_white_soldiers"].set(False)
    assert seen[-1]["patterns"]["items"]["three_white_soldiers"] is False
    assert win.item_vars["doji"].get() is False  # indecision starts unticked
    win.reset()
    reset = seen[-1]
    assert (
        reset["overlays"] == cs.defaults()["overlays"] and reset["palette"] == "default"
    )
    assert reset["patterns"]["items"] == cs.defaults()["patterns"]["items"]
    assert reset["future"] == 1
    win.destroy()


def test_the_pop_out_text_names_no_spec_provider_or_design_decision(tk_root):
    from pt_chart_patterns import ChartSettingsWindow

    win = ChartSettingsWindow(tk_root, {}, lambda cfg: None)

    def walk(w):
        yield w
        for child in w.winfo_children():
            yield from walk(child)

    texts = []
    for w in walk(win):
        try:
            texts.append(str(w.cget("text")).lower())
        except Exception:
            pass
    win.destroy()
    assert not [w for w in NOT_ON_SCREEN if w in " ".join(texts)]


def test_the_pattern_list_has_no_unthemed_strip(tk_root):
    """The list canvas takes the frame colour and the list fills its width."""
    import tkinter.ttk as ttk

    from pt_chart_patterns import ChartSettingsWindow

    win = ChartSettingsWindow(tk_root, {}, lambda cfg: None)
    canvas = win.patterns_canvas
    frame_bg = ttk.Style(win).lookup("TFrame", "background")
    assert str(canvas.cget("bg")) == str(frame_bg)
    list_id = canvas.find_withtag("all")[0]
    canvas.event_generate("<Configure>", width=480, height=300)
    win.update_idletasks()
    assert int(float(canvas.itemcget(list_id, "width"))) == 480
    win.destroy()


def test_ask_and_bid_lines_are_dotted_while_the_trader_is_stopped(make_chart):
    """Owner, 2026-10-14: ASK and BID come from the trader, so while it is stopped
    they are its last prices, drawn dotted. Every other line stays solid."""
    chart = make_chart(as_candles(down_then_engulfing()))

    def styles(running):
        chart.refresh(
            {"BTC": chart.folder},
            current_buy_price=101.0,
            current_sell_price=100.8,
            trail_line=102.0,
            dca_line_price=98.0,
            avg_cost_basis=99.5,
            trader_running=running,
        )
        levels = {LINES[k]: k for k in ("ask", "bid", "avg", "dca", "trail")}
        return {
            levels[line.get_color()]: line.get_linestyle()
            for line in chart.ax.lines
            if line.get_color() in levels
            and len(set(line.get_ydata())) == 1  # the level lines, not candle wicks
        }

    stopped = styles(False)
    assert stopped["ask"] == ":" and stopped["bid"] == ":"
    assert all(stopped[k] == "-" for k in ("avg", "dca", "trail"))
    running = styles(True)
    assert running["ask"] == "-" and running["bid"] == "-"


def test_the_coin_chart_shows_no_last_update_time(make_chart):
    """Owner, 2026-10-14: "Last:" was the neural level files' age, not the chart's,
    so it is gone from the chart. The cog moved to the hub's tab row
    (test_hub_layout)."""
    chart = make_chart(as_candles(down_then_engulfing()))
    refresh(chart)
    assert not any(t.get_text().startswith("Last:") for t in chart.ax.texts)
    assert not hasattr(chart, "last_update_text")
    assert not hasattr(chart, "chart_settings_button")
    assert not hasattr(chart, "last_update_label")
    assert chart.canvas.get_tk_widget().pack_info()["pady"] in (0, (0, 0))


def test_the_pop_out_opens_from_settings_and_the_toolbar_once(monkeypatch):
    import tkinter.ttk as ttk

    import helpers_trainer as ht
    import pt_paths

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    try:
        first = hub.open_chart_settings()
        assert hub.open_chart_settings() is first  # one at a time
        assert hub.bind_all("<<OpenChartSettings>>")
        hub._apply_chart_settings({"overlays": {"trades": False}})
        assert hub.settings["chart"]["overlays"]["trades"] is False
        with open(pt_paths.gui_settings_file(), encoding="utf-8") as f:
            assert json.load(f)["chart"]["overlays"]["trades"] is False
        first.destroy()
        before = set(hub.winfo_children())
        hub.open_settings_dialog()
        dialog = next(w for w in hub.winfo_children() if w not in before)

        def walk(w):
            yield w
            for child in w.winfo_children():
                yield from walk(child)

        buttons = [w for w in walk(dialog) if isinstance(w, ttk.Button)]
        assert any(str(b.cget("text")) == "Chart settings…" for b in buttons)
        dialog.destroy()
    finally:
        ht.close_hub(hub)
