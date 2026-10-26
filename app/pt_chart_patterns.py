"""
Candlestick patterns on the hub's coin charts, and the Chart settings pop-out
(FDS-CHART-001). Display only: nothing here reaches a strategy, the trainer, the
runner or the trader.

- PatternLayer: fetches closed bars for the displayed coin and timeframe from the
  exchanges in Settings, primary first, and runs detection in a background thread,
  never on the Tk thread. It then draws one
  label per candle, placed by open time, with hover brackets, a click-for-detail window
  and keyboard stepping.
- ChartSettingsWindow: the pop-out with a toggle for every overlay and pattern.
"""

from __future__ import annotations

import queue
import threading
import time
import webbrowser
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import ttk

import candlestick_patterns as cp
import chart_settings as cs
import ui_tokens
from market_data.listing import not_trading_reason

# Colours shared with the hub's dark theme (pt_hub.py); labels never use a candle or
# overlay colour (FDS-CHART-001 section 9).
LABEL_FG = ui_tokens.CHART["text"]
LABEL_BG = ui_tokens.CHART["label_bg"]
LABEL_EDGE = ui_tokens.CHART["grid"]
MIN_TARGET_PX = 24  # hover / click target (WCAG 2.5.8)
LABEL_OFFSET_PT = 12  # label distance from its candle
LABEL_STEP_PT = 16  # extra distance per stagger level
LABEL_LEVELS = 4  # stagger levels before labels may overlap again
LABEL_GAP_BARS = 10  # labels closer than this (in candles) on one side are staggered
LABEL_FONT_PT = ui_tokens.CHART_FONT_PT
LABEL_BOX_PAD = 0.3  # label box padding, as a fraction of the font size
MAX_LABEL_SHARE = 0.4  # most of the plot height one label may claim (tiny charts)
RETRY_SECONDS = 60.0


def _fmt_ts(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts)))


def room_for_labels(
    lo: float, hi: float, reach: Sequence[Tuple[float, bool, float]], height_px: float
) -> Tuple[float, float]:
    """The price range (lo, hi), widened only as far as every label needs to sit inside a
    plot ``height_px`` tall. ``reach``: (price, drawn above it, pixels from that price to
    the label's far edge)."""
    if height_px <= 0 or not reach:
        return lo, hi
    shares = [(y, up, min(px / height_px, MAX_LABEL_SHARE)) for y, up, px in reach]
    top, bottom = hi, lo
    for _ in range(8):  # each edge depends on the other; this settles in a few rounds
        top = max([hi] + [(y - r * bottom) / (1 - r) for y, up, r in shares if up])
        bottom = min([lo] + [(y - r * top) / (1 - r) for y, up, r in shares if not up])
    return bottom, top


def closed_bars(coin: str, interval: str, start_ts: int, end_ts: int):
    """Closed bars of the coin's market from the exchanges in Settings, primary first
    (``exchange_candles``; FDS-CHART-001 section 4, FDS-MX-001 phase E)."""
    import pandas as pd

    from market_data.candles import exchange_candles

    df = exchange_candles(
        coin,
        interval,
        pd.Timestamp(int(start_ts), unit="s", tz="UTC"),
        pd.Timestamp(int(end_ts), unit="s", tz="UTC"),
        closed_only=True,
    )
    return [
        cp.Bar(int(t.timestamp()), float(o), float(h), float(lo), float(c))
        for t, o, h, lo, c in zip(
            df["open_time"], df["open"], df["high"], df["low"], df["close"]
        )
    ]


class PatternResult:
    def __init__(self, key, bars=None, detections=None, error=None, start_ts=0):
        self.key = key
        self.bars = bars or []
        self.detections = detections or []
        self.error = error
        self.start_ts = start_ts
        self.finished_at = time.time()

    @property
    def last_bar_ts(self) -> Optional[int]:
        return int(self.bars[-1].ts) if self.bars else None


def _describe_error(exc: BaseException) -> str:
    from pt_exchange_abstraction import MarketNotFound

    if isinstance(exc, MarketNotFound):  # no exchange in Settings has the coin
        return "not available for this coin"
    return "unavailable right now"


class PatternLayer:
    """Candlestick-pattern labels on one CandleChart."""

    def __init__(
        self,
        chart,
        fetch_bars: Optional[Callable] = None,
        clock: Callable[[], float] = time.time,
        status_label: Optional[ttk.Label] = None,
    ):
        self.chart = chart
        self.ax = chart.ax
        self.canvas = chart.canvas
        self.fetch_bars = fetch_bars
        self.clock = clock
        self.status_label = status_label
        self.result: Optional[PatternResult] = None
        self._pending: Optional[queue.Queue] = None
        self._pending_key = None
        self._candles: List[dict] = []
        self._tf = ""
        self._cfg: Dict[str, Any] = cs.defaults()
        self._note = ""
        self.records: List[dict] = []  # drawn labels
        self.undrawn: List[cp.Detection] = []
        self.hidden_by_cap = 0
        self._overlay: List[Any] = []
        self._hover: Optional[dict] = None
        self._selected: Optional[int] = None
        # hover / keyboard selection survive a redraw: keyed by (pattern, last bar time)
        self._hover_key = None
        self._selected_key = None
        self.detail: Optional[tk.Toplevel] = None
        self.listing: Optional[tk.Toplevel] = None
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_press_event", self._on_click)
        self.canvas.mpl_connect("key_press_event", self._on_key)
        self.canvas.mpl_connect("figure_leave_event", lambda e: self._set_hover(None))
        if status_label is not None:
            status_label.bind("<Button-1>", lambda e: self.open_list())

    # --- data -------------------------------------------------------------------------

    def _step(self) -> Optional[int]:
        interval = cp.HUB_TO_CANDLE.get(self._tf)
        if interval is None:
            return None
        from market_data.timeframes import candle_timeframe_seconds

        return candle_timeframe_seconds(interval)

    def _needs_fetch(self, key, first_ts: int, step: int) -> bool:
        if self._pending is not None:
            return False
        r = self.result
        if r is None or r.key != key:
            return True
        now = self.clock()
        if r.error:
            return now - r.finished_at >= RETRY_SECONDS
        if r.start_ts > first_ts - cp.WARMUP_BARS * step:
            return True  # the visible window now starts earlier than the data
        last = r.last_bar_ts
        return last is None or now >= last + 2 * step  # a newer bar has closed

    def _start_fetch(self, key, coin: str, interval: str, start_ts: int, step: int):
        q: queue.Queue = queue.Queue(maxsize=1)
        self._pending, self._pending_key = q, key
        end_ts = int(self.clock())
        # looked up per call, so the test isolation guard can stub the network fetch
        fetch = self.fetch_bars or closed_bars

        def work():
            try:
                bars = fetch(coin, interval, start_ts, end_ts)
                used, dets = cp.detect(bars, step, now=end_ts)
                q.put(PatternResult(key, used, dets, None, start_ts))
            except Exception as exc:  # shown as a note, never raised into Tk
                q.put(PatternResult(key, error=_describe_error(exc), start_ts=start_ts))

        threading.Thread(target=work, name="chart-patterns", daemon=True).start()
        # first poll later, never inside update() (which is still drawing)
        try:
            self.chart.after(100, self._poll)
        except Exception:
            pass

    def _poll(self):
        q = self._pending
        if q is None:
            return
        try:
            result = q.get_nowait()
        except queue.Empty:
            try:
                self.chart.after(200, self._poll)
            except Exception:
                pass
            return
        self._pending = None
        if result.key == self._current_key():
            self.result = result
            self.redraw()

    def wait(self, timeout: float = 5.0) -> None:
        """Test helper: let a pending detection finish and apply it."""
        deadline = time.time() + timeout
        while self._pending is not None and time.time() < deadline:
            q = self._pending
            try:
                result = q.get(timeout=0.05)
            except queue.Empty:
                continue
            self._pending = None
            if result.key == self._current_key():
                self.result = result
                self.redraw()

    def _current_key(self):
        return (self.chart.coin, self._tf)

    # --- drawing ----------------------------------------------------------------------

    def update(
        self, candles: Sequence[dict], tf: str, coin_folder: str, cfg: Dict[str, Any]
    ):
        """Called by CandleChart.refresh after the candles and overlays are drawn."""
        self._candles, self._tf, self._cfg = list(candles), tf, cfg
        self.records, self.undrawn, self._overlay = [], [], []
        self._hover = None
        key = self._current_key()
        reason = not_trading_reason(coin_folder) if coin_folder else None
        step = self._step()
        if reason:
            self._note = "Candlestick patterns: not available for this coin"
        elif step is None:
            self._note = f"Candlestick patterns: timeframe {tf} not supported"
        elif not candles:
            self._note = ""
        else:
            first_ts = int(candles[0]["ts"])
            if self._needs_fetch(key, first_ts, step):
                start = first_ts - (cp.WARMUP_BARS + 2) * step
                self._start_fetch(
                    key, self.chart.coin, cp.HUB_TO_CANDLE[tf], start, step
                )
            self._draw_labels()
            self._restore_hover()
        self._set_status()

    def redraw(self):
        """Re-apply labels after a detection result arrives (no full chart refresh)."""
        for art in [r["artist"] for r in self.records] + self._overlay:
            try:
                art.remove()
            except Exception:
                pass
        self.records, self.undrawn, self._overlay = [], [], []
        self._hover = None
        self._draw_labels()
        self._restore_hover()
        self._set_status()
        fit = getattr(self.chart, "fit_layout", None)  # the labels may need more room
        try:
            if fit is not None:
                fit()
            self.canvas.draw_idle()
        except Exception:
            pass

    def label_artists(self) -> list:
        return [rec["artist"] for rec in self.records]

    def keep_labels_inside(self) -> None:
        """A label that would cross the left or right edge of the plot is aligned to
        that side of its candle instead of centred on it, so it never covers the price
        axis or the price tags."""
        try:
            renderer = self.canvas.get_renderer()
            plot = self.ax.get_window_extent(renderer)
        except Exception:
            return
        pad_px = LABEL_BOX_PAD * LABEL_FONT_PT * self.ax.figure.dpi / 72.0
        for rec in self.records:
            art = rec["artist"]
            art.set_horizontalalignment("center")
            try:
                box = art.get_window_extent(renderer)
            except Exception:
                continue
            if box.x1 + pad_px > plot.x1:
                art.set_horizontalalignment("right")
            elif box.x0 - pad_px < plot.x0:
                art.set_horizontalalignment("left")

    def label_reach(self) -> List[Tuple[float, bool, float]]:
        """(price, drawn above it, pixels from that price to the label's far edge) for
        every label, so the chart can widen its price range until each one is inside the
        plot."""
        px_per_pt = self.ax.figure.dpi / 72.0
        line_px = LABEL_FONT_PT * 1.2 * px_per_pt  # one line of text
        box_px = 2 * LABEL_BOX_PAD * LABEL_FONT_PT * px_per_pt
        try:
            renderer = self.canvas.get_renderer()
        except Exception:
            renderer = None
        out = []
        for rec in self.records:
            try:
                text_px = float(rec["artist"].get_window_extent(renderer).height)
            except Exception:
                text_px = 0.0
            if text_px < line_px / 2:  # not measurable yet
                text_px = line_px
            reach = rec["offset_pt"] * px_per_pt + text_px + box_px
            out.append((rec["y"], rec["up"], reach))
        return out

    @staticmethod
    def _key_of(rec_or_det):
        d = (
            rec_or_det["label"].detection
            if isinstance(rec_or_det, dict)
            else rec_or_det
        )
        return (d.pattern_id, d.last_ts)

    def _restore_hover(self):
        key = self._selected_key or self._hover_key
        if key is None:
            return
        for k, rec in enumerate(self.records):
            if self._key_of(rec) == key:
                if self._selected_key is not None:
                    self._selected = k
                self._set_hover(rec, force=True)
                return
        self._selected, self._selected_key, self._hover_key = None, None, None

    def _draw_labels(self):
        r = self.result
        candles = self._candles
        if not candles:
            return
        if self._pending is not None and (r is None or r.key != self._current_key()):
            self._note = "Candlestick patterns: detecting…"
            return
        if r is None or r.key != self._current_key():
            return
        if r.error:
            self._note = f"Candlestick patterns: {r.error}"
            return
        index = {int(c["ts"]): i for i, c in enumerate(candles)}
        first_ts, last_ts = int(candles[0]["ts"]), int(candles[-1]["ts"])
        in_window = [d for d in r.detections if first_ts <= d.last_ts <= last_ts]
        cfg = self._cfg
        lay = cp.layout(
            in_window,
            lambda p: cs.pattern_visible(cfg, p),
            cfg["patterns"]["max_labels"],
        )
        self.hidden_by_cap = lay.hidden_by_cap
        placed: List[tuple] = []  # (x, side, level) of labels already drawn
        for lb in lay.labels:
            d = lb.detection
            x_last = index.get(d.last_ts)
            if x_last is None:
                self.undrawn.append(d)
                continue
            # stagger labels on nearby candles so they never sit on top of each other
            side = "up" if lb.pattern.direction != "bearish" else "down"
            level = 0
            while level < LABEL_LEVELS - 1 and any(
                s_ == side and l_ == level and abs(x_ - x_last) < LABEL_GAP_BARS
                for x_, s_, l_ in placed
            ):
                level += 1
            placed.append((x_last, side, level))
            self._draw_one(lb, x_last, index, level)
        n = len(self.records)
        bits = [f"Patterns: {n} shown"]
        if self.hidden_by_cap:
            bits.append(f"{self.hidden_by_cap} hidden by the label cap")
        if self.undrawn:
            bits.append(f"{len(self.undrawn)} not on this chart")
        self._note = " · ".join(bits)

    def _draw_one(
        self, lb: cp.Label, x_last: int, index: Dict[int, int], level: int = 0
    ):
        d, p = lb.detection, lb.pattern
        c = self._candles[x_last]
        up = p.direction == "bullish" or p.direction == "none"
        y = float(c["high"]) if up else float(c["low"])
        text = f"{p.glyph} {p.name}" + (f" +{len(lb.others)}" if lb.others else "")
        offset = LABEL_OFFSET_PT + level * LABEL_STEP_PT
        art = self.ax.annotate(
            text,
            (x_last, y),
            xytext=(0, offset if up else -offset),
            textcoords="offset points",
            ha="center",
            va="bottom" if up else "top",
            fontsize=LABEL_FONT_PT,
            color=LABEL_FG,
            bbox=dict(
                boxstyle=f"round,pad={LABEL_BOX_PAD}",
                facecolor=LABEL_BG,
                edgecolor=LABEL_EDGE,
                alpha=0.92,
            ),
            zorder=25,
            annotation_clip=True,
        )
        self.records.append(
            {
                "label": lb,
                "artist": art,
                "x_last": x_last,
                "x_first": index.get(d.first_ts),
                "x_context": index.get(d.context_ts),
                "y": y,
                "up": up,
                "offset_pt": offset,
            }
        )

    def _set_status(self):
        if self.status_label is None:
            return
        try:
            self.status_label.config(text=self._note)
        except Exception:
            pass

    # --- hover, click, keyboard -------------------------------------------------------

    def _hit(self, event) -> Optional[dict]:
        if event.x is None or event.y is None:
            return None
        try:
            renderer = self.canvas.get_renderer()
        except Exception:
            renderer = None
        for rec in reversed(self.records):
            try:
                box = rec["artist"].get_window_extent(renderer)
            except Exception:
                continue
            x0, y0, x1, y1 = box.x0, box.y0, box.x1, box.y1
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            half_w = max((x1 - x0) / 2, MIN_TARGET_PX / 2)
            half_h = max((y1 - y0) / 2, MIN_TARGET_PX / 2)
            if abs(event.x - cx) <= half_w and abs(event.y - cy) <= half_h:
                return rec
        return None

    def _on_motion(self, event):
        if self._selected is not None:
            return  # keyboard selection holds the highlight
        self._set_hover(self._hit(event))

    def _on_click(self, event):
        try:
            self.canvas.get_tk_widget().focus_set()
        except Exception:
            pass
        rec = self._hit(event)
        if rec is not None and getattr(event, "button", 1) == 1:
            self._set_hover(rec)
            self.open_detail(rec)

    def _on_key(self, event):
        key = getattr(event, "key", "")
        if not self.records:
            return
        if key in ("right", "left"):
            order = sorted(
                range(len(self.records)), key=lambda k: self.records[k]["x_last"]
            )
            if self._selected not in order:
                pos = 0 if key == "right" else len(order) - 1
            else:
                pos = order.index(self._selected) + (1 if key == "right" else -1)
                pos = max(0, min(len(order) - 1, pos))
            self._selected = order[pos]
            self._selected_key = self._key_of(self.records[self._selected])
            self._set_hover(self.records[self._selected], force=True)
        elif key == "enter" and self._hover is not None:
            self.open_detail(self._hover)
        elif key == "escape":
            self._selected, self._selected_key = None, None
            self._set_hover(None)
            self.close_detail()

    def _set_hover(self, rec: Optional[dict], force: bool = False):
        if rec is self._hover and not force:
            return
        for art in self._overlay:
            try:
                art.remove()
            except Exception:
                pass
        self._overlay = []
        self._hover = rec
        self._hover_key = self._key_of(rec) if rec is not None else None
        if rec is not None:
            self._draw_hover(rec)
        for art in self._overlay:
            art.set_in_layout(False)  # hovering never moves the margins
        try:
            self.canvas.draw_idle()
        except Exception:
            pass

    def _draw_hover(self, rec: dict):
        from matplotlib.patches import Rectangle

        lb: cp.Label = rec["label"]
        d, p = lb.detection, lb.pattern
        x_last = rec["x_last"]
        x_first = rec["x_first"] if rec["x_first"] is not None else x_last
        span = self._candles[x_first : x_last + 1] or [self._candles[x_last]]
        lo = min(float(c["low"]) for c in span)
        hi = max(float(c["high"]) for c in span)
        pad = (hi - lo) * 0.05 or abs(hi) * 0.001
        box = Rectangle(
            (x_first - 0.45, lo - pad),
            (x_last - x_first) + 0.9,
            (hi - lo) + 2 * pad,
            fill=False,
            edgecolor=LABEL_FG,
            linestyle="--",
            linewidth=1.2,
            zorder=24,
        )
        self.ax.add_patch(box)
        self._overlay.append(box)
        if p.trend:
            x_ctx = rec["x_context"] if rec["x_context"] is not None else 0
            if x_ctx < x_first:
                ctx = self._candles[x_ctx:x_first]
                clo = min(float(c["low"]) for c in ctx)
                chi = max(float(c["high"]) for c in ctx)
                cbox = Rectangle(
                    (x_ctx - 0.45, clo),
                    (x_first - x_ctx) - 0.1,
                    chi - clo,
                    fill=False,
                    edgecolor=LABEL_FG,
                    linestyle=":",
                    linewidth=0.9,
                    zorder=24,
                )
                self.ax.add_patch(cbox)
                self._overlay.append(cbox)
        mid = (lo + hi) / 2
        into = {"down": "↘ into", "up": "↗ into"}.get(d.trend or "")
        if into:
            self._overlay.append(
                self.ax.text(
                    x_first - 0.6,
                    mid,
                    into,
                    ha="right",
                    va="center",
                    fontsize=8,
                    color=LABEL_FG,
                    zorder=26,
                )
            )
        nxt = {"up": "↗ next", "down": "↘ next", "flat": "→ next"}.get(
            d.next_move or ""
        )
        if nxt and self._cfg["patterns"]["next_arrows"]:
            self._overlay.append(
                self.ax.text(
                    x_last + 0.6,
                    mid,
                    nxt,
                    ha="left",
                    va="center",
                    fontsize=8,
                    color=LABEL_FG,
                    zorder=26,
                )
            )
        self._overlay.append(
            self.ax.text(
                0.01,
                0.98,
                self.hover_text(lb),
                transform=self.ax.transAxes,
                ha="left",
                va="top",
                fontsize=8,
                color=LABEL_FG,
                bbox=dict(
                    boxstyle="round,pad=0.4",
                    facecolor=LABEL_BG,
                    edgecolor=LABEL_EDGE,
                    alpha=0.95,
                ),
                zorder=30,
            )
        )

    def hover_text(self, lb: cp.Label) -> str:
        d, p = lb.detection, lb.pattern
        lines = [f"{p.glyph} {p.name}", p.explanation]
        if p.trend:
            lines.append(f"Trend into: {'falling' if d.trend == 'down' else 'rising'}")
        if self._cfg["patterns"]["next_arrows"]:
            if d.next_move:
                word = {"up": "higher", "down": "lower", "flat": "about level"}[
                    d.next_move
                ]
                lines.append(f"What happened next: {word} {d.next_after} bars later")
            else:
                lines.append("What happened next: not enough bars yet")
        if lb.others:
            lines.append(
                "Also on this candle: "
                + ", ".join(cp.BY_ID[o.pattern_id].name for o in lb.others)
            )
        lines.append("Click for details · ←/→ step · Esc clears")
        return "\n".join(lines)

    # --- windows ----------------------------------------------------------------------

    def detail_lines(self, lb: cp.Label) -> List[str]:
        d, p = lb.detection, lb.pattern
        r = self.result
        step = self._step() or 0
        bars = d.last_index - d.first_index + 1
        lines = [
            p.name,
            "",
            f"Bars: {bars}, {_fmt_ts(d.first_ts)} to {_fmt_ts(d.last_ts + step)}",
            f"Direction: {p.direction}   Type: {p.kind}   Family: "
            f"{'classical' if p.family == 'classical' else 'price action'}",
            "",
            p.explanation,
        ]
        if p.note:
            lines.append(p.note)
        if p.trend:
            lines.append(
                f"Trend into the pattern: {'falling' if d.trend == 'down' else 'rising'}."
            )
        if d.next_move:
            word = {"up": "higher", "down": "lower", "flat": "about level"}[d.next_move]
            lines.append(f"What happened next: {word} {d.next_after} bars later.")
        if lb.others:
            lines.append(
                "Also on this candle: "
                + ", ".join(cp.BY_ID[o.pattern_id].name for o in lb.others)
            )
        lines += [
            "",
            f"Reference: {p.reference}" + (f" ({p.url})" if p.url else ""),
        ]
        if r is not None and r.error:
            lines.append(f"(data: {r.error})")
        return lines

    def open_detail(self, rec_or_label):
        lb = rec_or_label["label"] if isinstance(rec_or_label, dict) else rec_or_label
        self.close_detail()
        win = tk.Toplevel(self.chart)
        win.title(f"{lb.pattern.name} — {self.chart.coin} {self._tf}")
        win.configure(bg=LABEL_BG)
        body = tk.Text(
            win,
            width=78,
            height=22,
            wrap="word",
            bg=LABEL_BG,
            fg=LABEL_FG,
            relief="flat",
        )
        body.insert("1.0", "\n".join(self.detail_lines(lb)))
        body.configure(state="disabled")
        body.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        row = ttk.Frame(win)
        row.pack(fill="x", padx=10, pady=(0, 10))
        if lb.pattern.url:
            ttk.Button(
                row,
                text="Open reference",
                command=lambda: webbrowser.open(lb.pattern.url),
            ).pack(side="left")
        ttk.Button(row, text="Close", command=self.close_detail).pack(side="right")
        win.bind("<Escape>", lambda e: self.close_detail())
        self.detail = win
        return win

    def close_detail(self):
        if self.detail is not None:
            try:
                self.detail.destroy()
            except Exception:
                pass
        self.detail = None

    def all_detections(self) -> List[cp.Detection]:
        """Every visible detection in the chart's window, drawn or not."""
        r = self.result
        if r is None or r.error or not self._candles:
            return []
        first_ts, last_ts = int(self._candles[0]["ts"]), int(self._candles[-1]["ts"])
        cfg = self._cfg
        return [
            d
            for d in cp.merge_runs(r.detections)
            if first_ts <= d.last_ts <= last_ts
            and cs.pattern_visible(cfg, cp.BY_ID[d.pattern_id])
        ]

    def open_list(self):
        dets = self.all_detections()
        if self.listing is not None:
            try:
                self.listing.destroy()
            except Exception:
                pass
        win = tk.Toplevel(self.chart)
        win.title(f"Candlestick patterns — {self.chart.coin} {self._tf}")
        win.configure(bg=LABEL_BG)
        drawn = {self._key_of(r) for r in self.records}
        box = tk.Listbox(
            win, width=70, height=min(24, max(6, len(dets))), bg=LABEL_BG, fg=LABEL_FG
        )
        for d in reversed(dets):
            p = cp.BY_ID[d.pattern_id]
            where = "" if self._key_of(d) in drawn else "  (not drawn)"
            box.insert("end", f"{_fmt_ts(d.last_ts)}  {p.glyph} {p.name}{where}")
        box.pack(fill="both", expand=True, padx=10, pady=10)
        ordered = list(reversed(dets))

        def _open(_e=None):
            sel = box.curselection()
            if sel:
                self.open_detail(cp.Label(ordered[sel[0]]))

        box.bind("<Double-Button-1>", _open)
        box.bind("<Return>", _open)
        self.listing = win
        return win


# --- the Chart settings pop-out (FDS-CHART-001 section 8) ---------------------------


class ChartSettingsWindow(tk.Toplevel):
    """Toggles for every chart overlay and candlestick pattern. Each change is passed to
    ``on_change(new_chart_settings)`` at once (the hub saves it and redraws)."""

    def __init__(
        self,
        master,
        current: Dict[str, Any],
        on_change: Callable[[Dict[str, Any]], None],
    ):
        super().__init__(master)
        self.title("Chart settings")
        self.geometry("620x640")
        self.minsize(520, 480)
        self.on_change = on_change
        self._raw = dict(current) if isinstance(current, dict) else {}
        self._building = True
        cfg = cs.normalize(current)
        self.overlay_vars = {
            k: tk.BooleanVar(value=cfg["overlays"][k]) for k, _, _ in cs.OVERLAYS
        }
        pats = cfg["patterns"]
        self.enabled_var = tk.BooleanVar(value=pats["enabled"])
        self.filter_vars = {
            k: tk.BooleanVar(value=pats["filters"][k]) for k in cs.FILTERS
        }
        self.item_vars = {
            p.id: tk.BooleanVar(value=pats["items"].get(p.id, cs.default_on(p)))
            for p in cp.PATTERNS
        }
        self.max_labels_var = tk.IntVar(value=pats["max_labels"])
        self.next_arrows_var = tk.BooleanVar(value=pats["next_arrows"])
        self.palette_var = tk.StringVar(value=cfg["palette"])
        self.style_var = tk.StringVar(value=cfg["candle_style"])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        self.notebook = nb
        nb.add(self._overlays_tab(nb), text="Overlays")
        nb.add(self._patterns_tab(nb), text="Candlestick patterns")
        nb.add(self._appearance_tab(nb), text="Appearance")

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(4, 10))
        ttk.Button(bottom, text="Reset to defaults", command=self.reset).pack(
            side="left"
        )
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side="right")
        for var in self._all_vars():
            var.trace_add("write", lambda *a: self._commit())
        self._building = False

    def _all_vars(self):
        return (
            list(self.overlay_vars.values())
            + [
                self.enabled_var,
                self.max_labels_var,
                self.next_arrows_var,
                self.palette_var,
                self.style_var,
            ]
            + list(self.filter_vars.values())
            + list(self.item_vars.values())
        )

    def _overlays_tab(self, nb):
        frm = ttk.Frame(nb)
        ttk.Label(frm, text="Show or hide each overlay on the coin charts.").pack(
            anchor="w", padx=8, pady=(8, 6)
        )
        for key, label, what in cs.OVERLAYS:
            row = ttk.Frame(frm)
            row.pack(fill="x", padx=8, pady=1)
            ttk.Checkbutton(row, text=label, variable=self.overlay_vars[key]).pack(
                side="left"
            )
            ttk.Label(row, text=f"  {what}").pack(side="left")
        self._all_on_off(frm, list(self.overlay_vars.values()))
        return frm

    def _patterns_tab(self, nb):
        outer = ttk.Frame(nb)
        top = ttk.Frame(outer)
        top.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Checkbutton(
            top, text="Show candlestick patterns", variable=self.enabled_var
        ).pack(anchor="w")
        filters = ttk.Frame(top)
        filters.pack(fill="x", pady=(6, 2))
        for row_i, (group, items) in enumerate(cs.FILTER_GROUPS):
            ttk.Label(filters, text=f"{group}:").grid(
                row=row_i, column=0, sticky="w", padx=(0, 8)
            )
            for col, (key, label) in enumerate(items, start=1):
                ttk.Checkbutton(
                    filters, text=label, variable=self.filter_vars[key]
                ).grid(row=row_i, column=col, sticky="w", padx=(0, 10))
        opts = ttk.Frame(top)
        opts.pack(fill="x", pady=(4, 2))
        ttk.Label(opts, text="Max labels per chart:").pack(side="left")
        lo, hi = cs.MAX_LABELS_RANGE
        ttk.Spinbox(
            opts, from_=lo, to=hi, width=4, textvariable=self.max_labels_var
        ).pack(side="left", padx=(4, 12))
        ttk.Checkbutton(
            opts, text="Show what happened next", variable=self.next_arrows_var
        ).pack(side="left")
        ttk.Label(
            top,
            text="A pattern shows only when its own box and every filter it belongs to are on.",
            wraplength=560,
        ).pack(anchor="w", pady=(4, 2))

        # scrollable pattern list
        holder = ttk.Frame(outer)
        holder.pack(fill="both", expand=True, padx=8, pady=4)
        # a plain Tk canvas ignores the ttk theme: give it the frame colour, and stretch
        # the list to the canvas width, so no unthemed strip shows beside the list
        canvas = tk.Canvas(holder, highlightthickness=0, bd=0)
        frame_bg = ttk.Style(self).lookup("TFrame", "background")
        if frame_bg:
            canvas.configure(bg=frame_bg)
        self.patterns_canvas = canvas
        bar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        list_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind(
            "<Configure>", lambda e: canvas.itemconfigure(list_id, width=e.width)
        )
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.pattern_checks: Dict[str, ttk.Checkbutton] = {}
        groups = (
            ("One bar", lambda p: p.family == "classical" and p.bars == 1),
            ("Two bars", lambda p: p.family == "classical" and p.bars == 2),
            ("Three bars", lambda p: p.family == "classical" and p.bars == 3),
            ("Four or more bars", lambda p: p.family == "classical" and p.bars >= 4),
            ("Price action", lambda p: p.family == "price_action"),
        )
        for title, test in groups:
            ttk.Label(inner, text=title).pack(anchor="w", pady=(6, 1))
            for p in cp.PATTERNS:
                if not test(p):
                    continue
                tags = ", ".join(t.replace("_", " ") for t in p.tags)
                text = f"{p.glyph} {p.name}   ({tags})"
                cb = ttk.Checkbutton(inner, text=text, variable=self.item_vars[p.id])
                cb.pack(anchor="w", padx=(12, 0))
                self.pattern_checks[p.id] = cb
        self._all_on_off(outer, list(self.item_vars.values()))
        return outer

    def _appearance_tab(self, nb):
        frm = ttk.Frame(nb)
        ttk.Label(frm, text="Palette").pack(anchor="w", padx=8, pady=(8, 2))
        for key, pal in cs.PALETTES.items():
            ttk.Radiobutton(
                frm, text=pal["label"], value=key, variable=self.palette_var
            ).pack(anchor="w", padx=20)
        ttk.Label(frm, text="Candle style").pack(anchor="w", padx=8, pady=(10, 2))
        for key, label in cs.CANDLE_STYLES.items():
            ttk.Radiobutton(frm, text=label, value=key, variable=self.style_var).pack(
                anchor="w", padx=20
            )
        ttk.Label(
            frm,
            text="Hollow up draws rising candles as outlines.",
            wraplength=560,
        ).pack(anchor="w", padx=8, pady=(8, 0))
        return frm

    def _all_on_off(self, parent, variables):
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=8, pady=(6, 8))

        def _set(value):
            self._building = True
            for v in variables:
                v.set(value)
            self._building = False
            self._commit()

        ttk.Button(row, text="All on", command=lambda: _set(True)).pack(side="left")
        ttk.Button(row, text="All off", command=lambda: _set(False)).pack(
            side="left", padx=6
        )

    def current(self) -> Dict[str, Any]:
        out = dict(self._raw)  # unknown keys are kept
        try:
            cap = int(self.max_labels_var.get())
        except (tk.TclError, ValueError):
            cap = 12
        out.update(
            {
                "overlays": {k: bool(v.get()) for k, v in self.overlay_vars.items()},
                "patterns": {
                    "enabled": bool(self.enabled_var.get()),
                    "filters": {k: bool(v.get()) for k, v in self.filter_vars.items()},
                    "items": {k: bool(v.get()) for k, v in self.item_vars.items()},
                    "max_labels": cap,
                    "next_arrows": bool(self.next_arrows_var.get()),
                },
                "palette": self.palette_var.get(),
                "candle_style": self.style_var.get(),
            }
        )
        return cs.normalize(out)

    def _commit(self):
        if self._building:
            return
        self.on_change(self.current())

    def reset(self):
        base = cs.defaults()
        self._building = True
        for k, v in self.overlay_vars.items():
            v.set(base["overlays"][k])
        self.enabled_var.set(base["patterns"]["enabled"])
        for k, v in self.filter_vars.items():
            v.set(base["patterns"]["filters"][k])
        for k, v in self.item_vars.items():
            v.set(base["patterns"]["items"][k])
        self.max_labels_var.set(base["patterns"]["max_labels"])
        self.next_arrows_var.set(base["patterns"]["next_arrows"])
        self.palette_var.set(base["palette"])
        self.style_var.set(base["candle_style"])
        self._building = False
        self._commit()
