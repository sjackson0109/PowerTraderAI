"""
The LLM Research tab of the hub's bottom panel: Market Analysis, Trade Signals and
Research Reports, for the coins in Settings, answered through the LLM provider layer
(llm_research_engine, llm_providers). Every LLM setting is in Settings > LLM
Providers; this tab has none of its own.

* **Market Analysis** - the coins (the Symbols box shows them in the connected
  exchange's format and can be overridden; Reset to my coins puts them back), Analyze
  Market, auto-refresh every N minutes (its cost per refresh and per day is shown
  before it is turned on), the results table and, under a splitter, the selected
  coin's analysis as the model wrote it (Markdown), with the provider, model and
  prompt version that produced it. Each analysis also asks for that coin's signal.
* **Trade Signals** - every signal (on demand, with an analysis, or from the trader
  at an entry), with its outcome and score after fees once known, filters by
  direction, provider, model and prompt version, a search, the selected signal's
  reasoning and the scores of each provider, model and prompt version.
* **Research Reports** - a Markdown report, saved as a .md file in the user data
  folder with its source in the file's header.

Each prompt has View / edit prompt: the exact template sent, saved as a new version
on every edit; earlier versions can be viewed and used again. LLM requests run on a
worker thread (ui_jobs); timers and the worker stop when the tab is destroyed.
"""

from __future__ import annotations

import os
import re
import time
import tkinter as tk
from tkinter import messagebox as _messagebox
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional, Sequence

import exchange_symbols
import llm_gate
import llm_settings
import llm_signals
import ui_markdown
import ui_table
import ui_tokens
from llm_research_engine import (
    DEFAULT_PROMPTS,
    PROMPT_FIELDS,
    REPORT_TYPES,
    LLMResearchEngine,
)
from llm_settings import provider_name
from ui_jobs import BackgroundJobs

ANALYSIS_COLUMNS = (
    "coin",
    "pair",
    "price",
    "change",
    "rsi",
    "signal",
    "provider",
    "model",
    "prompt",
    "updated",
)
ANALYSIS_HEADINGS = {
    "coin": "Coin",
    "pair": "Symbol",
    "price": "Price",
    "change": "24h %",
    "rsi": "RSI",
    "signal": "Signal",
    "provider": "Provider",
    "model": "Model",
    "prompt": "Prompt",
    "updated": "Updated",
}
SIGNAL_COLUMNS = (
    "time",
    "coin",
    "pair",
    "direction",
    "strength",
    "confidence",
    "price",
    "target",
    "stop",
    "horizon",
    "provider",
    "model",
    "prompt",
    "source",
    "outcome",
    "score",
)
SIGNAL_HEADINGS = {
    "time": "Time",
    "coin": "Coin",
    "pair": "Symbol",
    "direction": "Direction",
    "strength": "Strength",
    "confidence": "Confidence",
    "price": "Price",
    "target": "Target",
    "stop": "Stop Loss",
    "horizon": "Horizon",
    "provider": "Provider",
    "model": "Model",
    "prompt": "Prompt",
    "source": "Source",
    "outcome": "Outcome",
    "score": "After fees",
}
SCORE_COLUMNS = (
    "provider",
    "model",
    "prompt",
    "signals",
    "scored",
    "won",
    "hit_rate",
    "mean",
    "gate",
)
SCORE_HEADINGS = {
    "provider": "Provider",
    "model": "Model",
    "prompt": "Prompt",
    "signals": "Signals",
    "scored": "Scored",
    "won": "Won",
    "hit_rate": "Hit rate",
    "mean": "Mean after fees",
    "gate": "Gate",
}
DECISION_COLUMNS = ("time", "coin", "mode", "decision", "order", "reason")
DECISION_HEADINGS = {
    "time": "Time",
    "coin": "Coin",
    "mode": "LLM signals",
    "decision": "Decision",
    "order": "Order",
    "reason": "Reason",
}
ALL = "All"
HIGH_CONFIDENCE = "High confidence (70% or more)"
DIRECTION_FILTERS = (ALL, "BUY", "SELL", "HOLD", HIGH_CONFIDENCE)
SOURCE_WORDS = {
    "manual": "on demand",
    "analysis": "with an analysis",
    "entry": "at an entry",
}
HORIZON_WORDS = {
    "SHORT": "up to 1 day",
    "MEDIUM": "up to 1 week",
    "LONG": "up to 1 month",
}
PROMPT_TITLES = {
    "analysis": "Analysis prompt",
    "signal": "Signal prompt",
    "report": "Report prompt",
}
MIN_TOP_PX = 110  # the results table: its toolbar and a few rows
MIN_DETAIL_PX = 160  # Detailed Analysis: its title and several lines
TIME_FORMAT = "%Y-%m-%d %H:%M"
REFRESH_MS = 60_000  # the signals table is read again this often
SCORE_MINUTES = 10  # signals whose outcome may be known are scored this often


def _fmt_price(value: Optional[float]) -> str:
    if value is None:
        return ""
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}"
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _when(ts: Optional[float]) -> str:
    return time.strftime(TIME_FORMAT, time.localtime(ts)) if ts else ""


def _text_pane(parent: tk.Misc, mono: bool = False) -> tk.Text:
    """A read-only text pane with no border of its own, its scrollbar shown only
    while its content overflows (ui_table.scroll_when_needed)."""
    holder = ttk.Frame(parent)
    holder.pack(side="top", fill="both", expand=True)
    text = tk.Text(
        holder,
        wrap="word",
        borderwidth=0,
        highlightthickness=0,
        relief="flat",
        padx=ui_tokens.SPACE["md"],
        pady=ui_tokens.SPACE["sm"],
        font=ui_tokens.mono("small") if mono else ui_tokens.font("body"),
        height=6,
    )
    ui_table.scroll_when_needed(text, ttk.Scrollbar(holder, orient="vertical"))
    text.configure(state="disabled")
    return text


def estimate_lines(estimates: Sequence[Any]) -> List[str]:
    """One line per provider in the order: free, a cost per refresh and per day,
    or not known."""
    lines = []
    for n, e in enumerate(estimates):
        who = provider_name(e.provider) + (f" ({e.model})" if e.model else "")
        if n:
            who += ", if it answers"
        if e.per_refresh is None:
            lines.append(f"{who}: cost not known (no price set for the model)")
        elif e.free:
            lines.append(f"{who}: free (runs on this computer)")
        else:
            lines.append(
                f"{who}: ${e.per_refresh:,.4f} per refresh, ${e.per_day:,.2f} a day"
            )
    return lines


class PromptEditor(tk.Toplevel):
    """View / edit prompt: the template sent for ``kind``, its versions, and saving
    an edit as a new version or using an earlier one again."""

    def __init__(
        self,
        parent: tk.Misc,
        store: Any,
        kind: str,
        on_changed: Optional[Callable[[], None]] = None,
        messagebox=None,
    ):
        super().__init__(parent)
        self.store = store
        self.kind = kind
        self._on_changed = on_changed
        self._box = messagebox or _messagebox
        self.title(PROMPT_TITLES[kind])
        self.geometry("900x560")
        self.minsize(640, 380)
        store.ensure_prompt(kind, DEFAULT_PROMPTS[kind])
        gap = ui_tokens.SPACE["sm"]
        body = ttk.Frame(self, padding=ui_tokens.SPACE["lg"])
        body.pack(fill="both", expand=True)
        paned = ttk.Panedwindow(body, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned)
        self.versions = ui_table.DataTable(
            left,
            ("version", "saved", "use"),
            {"version": "Version", "saved": "Saved", "use": "In use"},
            numeric=("version",),
            sort=("version", True),
            empty_text="No versions yet",
            selectmode="browse",
        )
        self.versions.pack(fill="both", expand=True)
        self.versions.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_selected())
        right = ttk.Frame(paned)
        fields = ", ".join("${" + f + "}" for f in PROMPT_FIELDS[kind])
        ttk.Label(
            right,
            text=f"Filled in when the prompt is sent: {fields}",
            style="Muted.TLabel",
            wraplength=560,
            justify="left",
        ).pack(side="top", anchor="w", pady=(0, gap))
        holder = ttk.Frame(right)
        holder.pack(side="top", fill="both", expand=True)
        self.editor = tk.Text(
            holder,
            wrap="word",
            undo=True,
            borderwidth=0,
            highlightthickness=0,
            font=ui_tokens.mono("small"),
            padx=ui_tokens.SPACE["md"],
            pady=ui_tokens.SPACE["sm"],
        )
        ui_table.scroll_when_needed(
            self.editor, ttk.Scrollbar(holder, orient="vertical")
        )
        paned.add(left, weight=1)
        paned.add(right, weight=3)
        self.status_var = tk.StringVar(master=self)
        ttk.Label(
            body, textvariable=self.status_var, wraplength=760, justify="left"
        ).pack(side="top", anchor="w", pady=(gap, 0))
        buttons = ttk.Frame(body)
        buttons.pack(side="top", fill="x", pady=(gap, 0))
        ttk.Button(buttons, text="Save as new version", command=self.save).pack(
            side="left"
        )
        ttk.Button(buttons, text="Use this version", command=self.use_selected).pack(
            side="left", padx=gap
        )
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="left")
        self.load()

    def load(self, select: Optional[int] = None) -> None:
        tree = self.versions.tree
        tree.delete(*tree.get_children())
        versions = self.store.prompt_versions(self.kind)
        for v in versions:
            tree.insert(
                "",
                "end",
                iid=str(v.version),
                values=(v.version, _when(v.created_at), "yes" if v.active else ""),
            )
        active = next(
            (v for v in versions if v.active), versions[-1] if versions else None
        )
        chosen = select if select is not None else (active.version if active else None)
        if chosen is not None and tree.exists(str(chosen)):
            tree.selection_set(str(chosen))
            self._show_selected()

    def selected_version(self):
        selection = self.versions.tree.selection()
        if not selection:
            return None
        number = int(selection[0])
        return next(
            (v for v in self.store.prompt_versions(self.kind) if v.version == number),
            None,
        )

    def _show_selected(self) -> None:
        v = self.selected_version()
        if v is None:
            return
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", v.template)
        self.editor.edit_reset()
        state = "in use" if v.active else "not in use"
        self.status_var.set(
            f"Version {v.version}, saved {_when(v.created_at)}, {state}."
        )

    def save(self):
        text = self.editor.get("1.0", "end-1c")
        try:
            version = self.store.save_prompt(self.kind, text)
        except ValueError as exc:
            self.status_var.set(str(exc))
            return None
        self.load(version.version)
        note = (
            " Its signals are logged only until this version passes the gate."
            if self.kind == "signal"
            else ""
        )
        self.status_var.set(f"Saved as version {version.version}, now in use.{note}")
        if self._on_changed:
            self._on_changed()
        return version

    def use_selected(self):
        v = self.selected_version()
        if v is None:
            self.status_var.set("Select a version first.")
            return None
        version = self.store.restore_prompt(self.kind, v.version)
        self.load(version.version)
        self.status_var.set(f"Version {version.version} is in use again.")
        if self._on_changed:
            self._on_changed()
        return version


class ResearchEngineGUI:
    """The tab; see the module docstring. ``coins`` returns the coins in Settings;
    ``engine`` an LLMResearchEngine (built with its defaults when not given);
    ``open_settings`` opens Settings > LLM Providers."""

    def __init__(
        self,
        parent: tk.Misc,
        config: Optional[dict] = None,
        *,
        engine: Optional[LLMResearchEngine] = None,
        coins: Optional[Callable[[], Sequence[str]]] = None,
        open_settings: Optional[Callable[[], Any]] = None,
        messagebox=None,
        refresh_ms: int = REFRESH_MS,
        score_minutes: float = SCORE_MINUTES,
    ):
        self.parent = parent
        self.config = config or {}
        self.engine = engine if engine is not None else LLMResearchEngine()
        self.store = self.engine.store
        self.router = self.engine.router
        self._coins = coins or exchange_symbols.settings_coins
        self._open_settings = open_settings
        self._box = messagebox or _messagebox
        self._refresh_ms = refresh_ms
        self._score_ms = int(score_minutes * 60_000)
        self._afters: Dict[str, str] = {}
        self._known: Dict[str, str] = {}  # a symbol shown -> its coin
        self._default_symbols = ""
        self._default_for: tuple = ()
        self._running = 0  # analyses still to answer
        self.analyses: Dict[str, Any] = {}
        self.signals: List[Any] = []
        self.shown_signals: List[Any] = []
        self.report = None
        self.alive = True

        self.research_frame = ttk.Frame(parent)
        self.research_frame.pack(fill="both", expand=True)
        self.research_frame.bind("<Destroy>", self._on_destroy, add="+")
        self.jobs = BackgroundJobs(self.research_frame, name="llm-research")

        # the status bar is packed first, so the sub-tabs never squeeze it out
        bar = ttk.Frame(self.research_frame)
        bar.pack(side="bottom", fill="x", padx=ui_tokens.SPACE["sm"], pady=(2, 2))
        self.status_var = tk.StringVar(master=self.research_frame, value="Ready")
        self.answered_var = tk.StringVar(master=self.research_frame)
        self.warning_var = tk.StringVar(master=self.research_frame)
        ttk.Label(bar, textvariable=self.status_var).pack(side="left")
        self.warning_label = ttk.Label(
            bar, textvariable=self.warning_var, style="Warn.TLabel"
        )
        self.warning_label.pack(side="left", padx=(ui_tokens.SPACE["lg"], 0))
        if open_settings is not None:
            ttk.Button(bar, text="LLM Providers...", command=open_settings).pack(
                side="right", padx=(ui_tokens.SPACE["sm"], 0)
            )
        ttk.Label(bar, textvariable=self.answered_var, style="Muted.TLabel").pack(
            side="right"
        )

        self.notebook = ttk.Notebook(self.research_frame)
        self.notebook.pack(fill="both", expand=True)
        self._build_analysis_tab()
        self._build_signals_tab()
        self._build_reports_tab()

        self.reset_symbols(lookup=False)
        self._load_symbols()
        self.reload_analyses()
        self.reload_signals()
        self._show_cost()
        if refresh_ms:
            self._after("signals", refresh_ms, self._tick_signals)
        if self._score_ms:
            self._after("score", min(self._score_ms, 5_000), self._tick_score)

    # ---- timers and shutdown ----

    def _after(self, name: str, ms: int, fn: Callable[[], None]) -> None:
        self._cancel(name)
        if not self.alive:
            return
        try:
            self._afters[name] = self.research_frame.after(
                int(ms), lambda: self._fire(name, fn)
            )
        except tk.TclError:
            pass

    def _fire(self, name: str, fn: Callable[[], None]) -> None:
        self._afters.pop(name, None)
        if self.alive:
            fn()

    def _cancel(self, name: str) -> None:
        after = self._afters.pop(name, None)
        if after is not None:
            try:
                self.research_frame.after_cancel(after)
            except tk.TclError:
                pass

    def _on_destroy(self, event) -> None:
        if event.widget is not self.research_frame:
            return
        self.alive = False
        for name in list(self._afters):
            self._cancel(name)
        self.jobs.stop()

    def timers(self) -> List[str]:
        return sorted(self._afters)

    def _submit(self, job, done=None, failed=None) -> bool:
        return self.jobs.submit(job, done, failed or self._failed)

    def _failed(self, exc: BaseException) -> None:
        self.status_var.set(str(exc)[:300])

    def _answered(self, routed: Any, what: str, version: int) -> None:
        """The status bar: which provider and model answered, and a warning when a
        paid provider stood in for the preferred one."""
        self.answered_var.set(
            f"Answered by {provider_name(routed.provider)} ({routed.model}), {what} prompt v{version}"
        )
        self.warning_var.set(routed.warning())

    # ---- the coins ----

    def coins(self) -> List[str]:
        try:
            return [
                exchange_symbols.coin_of(c)
                for c in self._coins()
                if exchange_symbols.coin_of(c)
            ]
        except Exception:
            return []

    def reset_symbols(self, lookup: bool = True) -> None:
        """Reset to my coins: the coins in Settings, as the connected exchange names
        them."""
        coins = self.coins()
        shown = ", ".join(self._known_pair(c) for c in coins)
        self._default_symbols = shown
        self._default_for = tuple(coins)
        self.symbol_var.set(shown)
        if lookup:
            self._load_symbols()

    def _known_pair(self, coin: str) -> str:
        for pair, known in self._known.items():
            if known == coin:
                return pair
        return coin

    def _load_symbols(self) -> None:
        coins = self.coins()

        def look():
            return exchange_symbols.market_pairs(coins, self.engine.market.layer)

        def done(pairs) -> None:
            untouched = self.symbol_var.get() == self._default_symbols
            self._known = {p.pair: p.coin for p in pairs}
            self._default_symbols = ", ".join(p.pair for p in pairs)
            self._default_for = tuple(coins)
            if untouched:
                self.symbol_var.set(self._default_symbols)

        self._submit(look, done, lambda _exc: None)

    def selected_coins(self) -> List[str]:
        """The coins in the Symbols box, or the coins in Settings when it is
        empty."""
        current = self.coins()
        untouched = self.symbol_var.get() == self._default_symbols
        if untouched and tuple(current) != self._default_for:
            self.coins_changed()  # an untouched box follows the coins in Settings
            return current
        return (
            exchange_symbols.parse_symbols(self.symbol_var.get(), self._known)
            or current
        )

    def coins_changed(self) -> None:
        """The coins in Settings changed: an untouched Symbols box follows them."""
        if self.symbol_var.get() == self._default_symbols:
            self.reset_symbols()
        self.report_coin_box.configure(values=self.coins())

    # ---- Market Analysis ----

    def _build_analysis_tab(self) -> None:
        gap = ui_tokens.SPACE["sm"]
        tab = ttk.Frame(self.notebook)
        self.analysis_tab = tab
        self.notebook.add(tab, text="Market\nAnalysis")

        bar = ttk.Frame(tab)
        bar.pack(side="top", fill="x", padx=gap, pady=(gap, 0))
        ttk.Label(bar, text="Symbols").pack(side="left", padx=(0, 4))
        self.symbol_var = tk.StringVar(master=tab)
        self.symbol_entry = ttk.Entry(
            bar, textvariable=self.symbol_var, font=ui_tokens.mono("small")
        )
        self.symbol_entry.pack(side="left", fill="x", expand=True, padx=(0, gap))
        ttk.Button(bar, text="Reset to my coins", command=self.reset_symbols).pack(
            side="left", padx=(0, gap)
        )
        self.analyze_btn = ttk.Button(
            bar,
            text="Analyze Market",
            command=self.run_market_analysis,
            style="Accent.TButton",
        )
        self.analyze_btn.pack(side="left", padx=(0, gap))
        ttk.Button(bar, text="Clear", command=self.clear_analysis).pack(side="left")

        bar2 = ttk.Frame(tab)
        bar2.pack(side="top", fill="x", padx=gap, pady=(gap, gap))
        self.auto_refresh = tk.BooleanVar(master=tab, value=False)
        minutes = llm_settings.read_llm_settings().get("auto_refresh_minutes", 10)
        self.refresh_interval = tk.StringVar(master=tab, value=str(minutes))
        self.auto_refresh_check = ttk.Checkbutton(
            bar2,
            text="Auto-refresh every",
            variable=self.auto_refresh,
            command=self.toggle_auto_refresh,
        )
        self.auto_refresh_check.pack(side="left")
        ttk.Spinbox(
            bar2, from_=1, to=1440, width=5, textvariable=self.refresh_interval
        ).pack(side="left", padx=(4, 4))
        ttk.Label(bar2, text="min").pack(side="left", padx=(0, gap))
        self.cost_var = tk.StringVar(master=tab)
        ttk.Label(bar2, textvariable=self.cost_var, style="Muted.TLabel").pack(
            side="left"
        )
        self.refresh_interval.trace_add("write", lambda *_: self._interval_changed())
        self.analysis_search_var = tk.StringVar(master=tab)
        self.analysis_search_var.trace_add(
            "write", lambda *_: self.apply_analysis_filter()
        )
        ttk.Entry(bar2, textvariable=self.analysis_search_var, width=16).pack(
            side="right"
        )
        ttk.Label(bar2, text="Search").pack(side="right", padx=(gap, 4))
        ttk.Button(
            bar2,
            text="View / edit prompt",
            command=lambda: self.open_prompt("analysis"),
        ).pack(side="right", padx=(gap, 0))

        self.analysis_paned = ttk.Panedwindow(tab, orient="vertical")
        self.analysis_paned.pack(fill="both", expand=True)
        top = ttk.Frame(self.analysis_paned)
        self.analysis_table = ui_table.DataTable(
            top,
            ANALYSIS_COLUMNS,
            ANALYSIS_HEADINGS,
            key="llm_research.analysis_results",
            numeric=("price", "change", "rsi"),
            empty_text="No analyses yet",
            selectmode="browse",
        )
        self.analysis_table.pack(fill="both", expand=True)
        self.analysis_tree = self.analysis_table.tree
        self.analysis_tree.bind("<<TreeviewSelect>>", self.on_analysis_select)

        bottom = ttk.Frame(self.analysis_paned)
        head = ttk.Frame(bottom)
        head.pack(side="top", fill="x", padx=gap, pady=(gap, 0))
        ttk.Label(head, text="Detailed Analysis", style=ui_table.SECTION_STYLE).pack(
            side="left"
        )
        self.details_meta = tk.StringVar(master=tab)
        ttk.Label(bottom, textvariable=self.details_meta, style="Muted.TLabel").pack(
            side="top", anchor="w", padx=gap
        )
        self.analysis_details = _text_pane(bottom)
        ui_markdown.show(self.analysis_details, "Select a coin to see its analysis.")
        self.analysis_paned.add(top, weight=3)
        self.analysis_paned.add(bottom, weight=2)
        self._sash_placed = False
        self.analysis_paned.bind("<Configure>", lambda _e: self._place_sash(), add="+")
        self.analysis_paned.bind("<B1-Motion>", lambda _e: self.clamp_sash(), add="+")
        self.analysis_paned.bind(
            "<ButtonRelease-1>", lambda _e: self.clamp_sash(), add="+"
        )

    def _place_sash(self) -> None:
        if not self._sash_placed:
            total = self.analysis_paned.winfo_height()
            if total <= 1:
                return
            self._sash_placed = True
            detail = max(MIN_DETAIL_PX, (total * 2) // 5)
            try:
                self.analysis_paned.sashpos(0, max(MIN_TOP_PX, total - detail))
            except tk.TclError:
                return
        self.clamp_sash()

    def clamp_sash(self) -> None:
        """Keep both panes at least their minimum height (ttk panes have none)."""
        try:
            total = self.analysis_paned.winfo_height()
            pos = int(self.analysis_paned.sashpos(0))
        except (tk.TclError, ValueError):
            return
        if total <= MIN_TOP_PX + MIN_DETAIL_PX:
            return
        clamped = max(MIN_TOP_PX, min(total - MIN_DETAIL_PX, pos))
        if clamped != pos:
            self.analysis_paned.sashpos(0, clamped)

    def reload_analyses(self) -> None:
        try:
            self.analyses = self.store.latest_analyses()
        except Exception as exc:
            self.status_var.set(f"Could not read the analyses: {exc}")
            return
        self.apply_analysis_filter()

    def analysis_cells(self, a: Any) -> tuple:
        f = a.facts or {}
        change = f.get("change_24h_pct")
        rsi = f.get("rsi_14")
        return (
            a.coin,
            a.pair or f.get("pair", ""),
            _fmt_price(f.get("price")),
            "" if change is None else f"{change:+.2f}%",
            "" if rsi is None else f"{rsi:.1f}",
            f.get("signal") or "",
            provider_name(a.provider),
            a.model,
            f"v{a.prompt_version}",
            _when(a.ts),
        )

    def apply_analysis_filter(self) -> None:
        tree = self.analysis_tree
        selected = tree.selection()
        tree.delete(*tree.get_children())
        words = self.analysis_search_var.get().casefold().split()
        for coin, a in self.analyses.items():
            cells = self.analysis_cells(a)
            if words:
                text = " ".join(str(c) for c in cells).casefold()
                if not all(w in text for w in words):
                    continue
            tags = (
                ("buy",)
                if cells[5] == "BUY"
                else ("sell",) if cells[5] == "SELL" else ()
            )
            tree.insert("", "end", iid=coin, values=cells, tags=tags)
        tree.tag_configure("buy", foreground=ui_tokens.STATUS["good"])
        tree.tag_configure("sell", foreground=ui_tokens.STATUS["short"])
        self.analysis_table.empty.configure(
            text="No analyses match the search" if self.analyses else "No analyses yet"
        )
        keep = [i for i in selected if tree.exists(i)]
        if keep:
            tree.selection_set(keep)

    def run_market_analysis(self, auto: bool = False) -> bool:
        """Analyze Market: an analysis, then a signal, for each selected coin."""
        if self._running:
            return False
        coins = self.selected_coins()
        if not coins:
            self.status_var.set("No coins: add coins in Settings, or type symbols.")
            return False
        self._running = len(coins)
        self._analysis_errors: List[str] = []
        self.analyze_btn.state(["disabled"])
        self.status_var.set(f"Analysing {', '.join(coins)}...")
        for coin in coins:
            self._submit(
                lambda c=coin: self.engine.analyze(c),
                self._analysis_done,
                lambda exc, c=coin: self._analysis_failed(c, exc),
            )
        return True

    def _analysis_finished_one(self) -> None:
        self._running = max(0, self._running - 1)
        if not self._running:
            self.analyze_btn.state(["!disabled"])
            errors = getattr(self, "_analysis_errors", [])
            if errors:
                self.status_var.set("; ".join(errors)[:400])
            else:
                self.status_var.set("Analysis complete")

    def _analysis_done(self, result: Any) -> None:
        record = result.record
        self.analyses[record.coin] = record
        self.apply_analysis_filter()
        self._answered(result.routed, "analysis", record.prompt_version)
        selection = self.analysis_tree.selection()
        if not selection or selection[0] == record.coin:
            if self.analysis_tree.exists(record.coin):
                self.analysis_tree.selection_set(record.coin)
            self.show_details(record.coin)
        self._analysis_finished_one()
        # the coin's trade signal is refreshed with its analysis
        self._submit(
            lambda: self.engine.signal(
                record.coin, source="analysis", snapshot=result.snapshot
            ),
            self._signal_done,
            lambda exc: self.status_var.set(f"{record.coin} signal: {exc}"[:300]),
        )

    def _analysis_failed(self, coin: str, exc: BaseException) -> None:
        self._analysis_errors.append(f"{coin}: {exc}")
        self._analysis_finished_one()

    def on_analysis_select(self, _event=None) -> None:
        selection = self.analysis_tree.selection()
        if selection:
            self.show_details(selection[0])

    def show_details(self, coin: str) -> None:
        """The model's own analysis of ``coin``, and what produced it."""
        a = self.analyses.get(coin)
        if a is None:
            return
        meta = (
            f"{a.coin} {a.pair} · {provider_name(a.provider)} · {a.model} · "
            f"analysis prompt v{a.prompt_version} · {_when(a.ts)}"
        )
        warning = (a.facts or {}).get("warning")
        self.details_meta.set(meta + (f" · {warning}" if warning else ""))
        ui_markdown.show(self.analysis_details, a.text or "(the model gave no text)")

    def clear_analysis(self) -> None:
        """Clear: empty the results (the analyses stay in the store)."""
        self.analyses = {}
        self.apply_analysis_filter()
        self.details_meta.set("")
        ui_markdown.show(self.analysis_details, "Select a coin to see its analysis.")
        self.status_var.set("Analysis cleared")

    # ---- auto-refresh ----

    def minutes(self) -> Optional[int]:
        try:
            value = int(float(self.refresh_interval.get()))
        except ValueError:
            return None
        return value if 1 <= value <= 1440 else None

    def estimates(self):
        return self.engine.estimate(self.selected_coins(), self.minutes() or 10)

    def _show_cost(self) -> None:
        try:
            lines = estimate_lines(self.estimates())
        except Exception:
            lines = []
        self.cost_var.set(lines[0] if lines else "no LLM provider set up")

    def _interval_changed(self) -> None:
        self._show_cost()
        if self.auto_refresh.get() and self.minutes():
            self._after("auto", self.minutes() * 60_000, self._tick_auto)

    def toggle_auto_refresh(self) -> bool:
        """Turning auto-refresh on shows what it costs first; it starts only once
        that is accepted."""
        if not self.auto_refresh.get():
            self._cancel("auto")
            self.status_var.set("Auto-refresh off")
            return False
        minutes = self.minutes()
        if minutes is None:
            self.auto_refresh.set(False)
            self.status_var.set(
                "Auto-refresh: enter a number of minutes from 1 to 1440"
            )
            return False
        try:
            lines = estimate_lines(self.estimates())
        except Exception as exc:
            lines = [f"The cost could not be estimated: {exc}"]
        coins = self.selected_coins()
        message = (
            f"Each refresh asks for an analysis and a signal for {len(coins)} coins, "
            f"every {minutes} minutes. Estimated cost:\n\n"
            + "\n".join(lines or ["no LLM provider set up"])
            + "\n\nTurn on auto-refresh?"
        )
        if not self._box.askokcancel(
            "Auto-refresh", message, parent=self.research_frame
        ):
            self.auto_refresh.set(False)
            return False
        self._after("auto", minutes * 60_000, self._tick_auto)
        self.status_var.set(f"Auto-refresh every {minutes} minutes")
        return True

    def _tick_auto(self) -> None:
        if not self.auto_refresh.get():
            return
        self.run_market_analysis(auto=True)
        self._after("auto", (self.minutes() or 10) * 60_000, self._tick_auto)

    # ---- Trade Signals ----

    def _build_signals_tab(self) -> None:
        gap = ui_tokens.SPACE["sm"]
        tab = ttk.Frame(self.notebook)
        self.signals_tab = tab
        self.notebook.add(tab, text="Trade\nSignals")
        bar = ttk.Frame(tab)
        bar.pack(side="top", fill="x", padx=gap, pady=(gap, 0))
        self.generate_signals_btn = ttk.Button(
            bar,
            text="Generate Signals",
            command=self.generate_trade_signals,
            style="Accent.TButton",
        )
        self.generate_signals_btn.pack(side="left", padx=(0, gap))
        ttk.Button(
            bar, text="View / edit prompt", command=lambda: self.open_prompt("signal")
        ).pack(side="left", padx=(0, gap + 4))

        def combo(label: str, values, width: int) -> ttk.Combobox:
            ttk.Label(bar, text=label).pack(side="left", padx=(0, 4))
            box = ttk.Combobox(bar, values=list(values), state="readonly", width=width)
            box.set(ALL)
            box.pack(side="left", padx=(0, gap + 4))
            box.bind("<<ComboboxSelected>>", lambda _e: self.apply_signal_filter())
            return box

        self.signal_filter = combo("Show", DIRECTION_FILTERS, 16)
        self.provider_filter = combo("Provider", (ALL,), 10)
        self.model_filter = combo("Model", (ALL,), 18)
        self.prompt_filter = combo("Prompt", (ALL,), 5)
        ttk.Label(bar, text="Search").pack(side="left", padx=(0, 4))
        self.signal_search_var = tk.StringVar(master=tab)
        self.signal_search_var.trace_add("write", lambda *_: self.apply_signal_filter())
        ttk.Entry(bar, textvariable=self.signal_search_var, width=14).pack(
            side="left", fill="x", expand=True
        )
        self.signal_summary = tk.StringVar(master=tab)
        ttk.Label(tab, textvariable=self.signal_summary, anchor="w").pack(
            side="top", fill="x", padx=gap, pady=(4, 4)
        )

        self.signals_paned = ttk.Panedwindow(tab, orient="vertical")
        self.signals_paned.pack(fill="both", expand=True)
        top = ttk.Frame(self.signals_paned)
        self.signals_table = ui_table.DataTable(
            top,
            SIGNAL_COLUMNS,
            SIGNAL_HEADINGS,
            key="llm_research.trade_signals",
            numeric=("confidence", "price", "target", "stop", "score", "prompt"),
            sort=("time", True),
            empty_text="No signals yet",
            selectmode="browse",
        )
        self.signals_table.pack(fill="both", expand=True)
        self.signals_tree = self.signals_table.tree
        self.signals_tree.bind("<<TreeviewSelect>>", self.on_signal_select)

        bottom = ttk.Panedwindow(self.signals_paned, orient="horizontal")
        reasons = ttk.Frame(bottom)
        ttk.Label(reasons, text="Signal Reasoning", style=ui_table.SECTION_STYLE).pack(
            side="top", anchor="w", padx=gap, pady=(gap, 0)
        )
        self.signal_meta = tk.StringVar(master=tab)
        ttk.Label(reasons, textvariable=self.signal_meta, style="Muted.TLabel").pack(
            side="top", anchor="w", padx=gap
        )
        self.signal_details = _text_pane(reasons)
        ui_markdown.show(self.signal_details, "Select a signal to see its reasoning.")
        scores = ttk.Frame(bottom)
        ttk.Label(
            scores,
            text="Scores by provider, model and prompt",
            style=ui_table.SECTION_STYLE,
        ).pack(side="top", anchor="w", padx=gap, pady=(gap, 2))
        self.scores_table = ui_table.DataTable(
            scores,
            SCORE_COLUMNS,
            SCORE_HEADINGS,
            key="llm_research.signal_scores",
            numeric=("signals", "scored", "won", "hit_rate", "mean"),
            empty_text="No signals yet",
            height=4,
        )
        self.scores_table.pack(fill="both", expand=True)
        decisions = ttk.Frame(bottom)
        ttk.Label(decisions, text="Entry decisions", style=ui_table.SECTION_STYLE).pack(
            side="top", anchor="w", padx=gap, pady=(gap, 2)
        )
        self.decisions_table = ui_table.DataTable(
            decisions,
            DECISION_COLUMNS,
            DECISION_HEADINGS,
            key="llm_research.entry_decisions",
            sort=("time", True),
            empty_text="No entry decisions yet",
            height=4,
        )
        self.decisions_table.pack(fill="both", expand=True)
        bottom.add(reasons, weight=2)
        bottom.add(scores, weight=2)
        bottom.add(decisions, weight=2)
        self.signals_paned.add(top, weight=3)
        self.signals_paned.add(bottom, weight=2)

    def reload_signals(self) -> None:
        try:
            self.signals = self.store.signals(limit=2000)
        except Exception as exc:
            self.status_var.set(f"Could not read the signals: {exc}")
            return
        for box, values in (
            (
                self.provider_filter,
                sorted({provider_name(s.provider) for s in self.signals if s.provider}),
            ),
            (self.model_filter, sorted({s.model for s in self.signals if s.model})),
            (
                self.prompt_filter,
                [f"v{v}" for v in sorted({s.prompt_version for s in self.signals})],
            ),
        ):
            box.configure(values=[ALL] + list(values))
            if box.get() not in [ALL] + list(values):
                box.set(ALL)
        self.apply_signal_filter()
        self._show_scores()
        self._show_decisions()

    def signal_cells(self, s: Any) -> tuple:
        return (
            _when(s.ts),
            s.coin,
            s.pair,
            s.direction or "none",
            (s.strength or "").replace("_", " "),
            "" if s.confidence is None else f"{s.confidence:.0f}%",
            _fmt_price(s.price),
            _fmt_price(s.price_target),
            _fmt_price(s.stop_loss),
            HORIZON_WORDS.get(s.time_horizon, s.time_horizon),
            provider_name(s.provider),
            s.model,
            f"v{s.prompt_version}",
            SOURCE_WORDS.get(s.source, s.source),
            llm_signals.outcome_text(s.outcome)
            or ("pending" if s.direction in ("BUY", "SELL") else ""),
            "" if s.net_return is None else f"{s.net_return * 100:+.2f}%",
        )

    def signal_matches(self, s: Any) -> bool:
        shown = self.signal_filter.get()
        if shown == HIGH_CONFIDENCE:
            if s.confidence is None or s.confidence < 70:
                return False
        elif shown != ALL and s.direction != shown:
            return False
        for box, value in (
            (self.provider_filter, provider_name(s.provider)),
            (self.model_filter, s.model),
            (self.prompt_filter, f"v{s.prompt_version}"),
        ):
            if box.get() != ALL and box.get() != value:
                return False
        words = self.signal_search_var.get().casefold().split()
        if words:
            text = " ".join(str(c) for c in self.signal_cells(s)).casefold()
            if not all(w in text for w in words):
                return False
        return True

    def apply_signal_filter(self, event=None) -> None:
        tree = self.signals_tree
        selected = tree.selection()
        tree.delete(*tree.get_children())
        self.shown_signals = [s for s in self.signals if self.signal_matches(s)]
        for s in self.shown_signals:
            tags = []
            if s.direction == "BUY":
                tags.append("buy")
            elif s.direction == "SELL":
                tags.append("sell")
            tree.insert(
                "", "end", iid=str(s.id), values=self.signal_cells(s), tags=tags
            )
        tree.tag_configure("buy", foreground=ui_tokens.STATUS["good"])
        tree.tag_configure("sell", foreground=ui_tokens.STATUS["short"])
        self.signals_table.empty.configure(
            text="No signals match these filters" if self.signals else "No signals yet"
        )
        keep = [i for i in selected if tree.exists(i)]
        if keep:
            tree.selection_set(keep)
        summary = llm_signals.signal_summary(self.shown_signals)
        text = f"{summary['signals']} signals shown, {summary['scored']} scored"
        if summary["scored"]:
            text += (
                f", {summary['won']} won after fees ({summary['hit_rate']:.0%}), mean "
                f"{summary['mean_return'] * 100:+.2f}%"
            )
        self.signal_summary.set(text)

    filter_signals = apply_signal_filter

    def _show_decisions(self) -> None:
        """What the trader's entry hook decided, newest first, with the order."""
        try:
            rows = self.store.decisions(limit=500)
        except Exception:
            rows = []
        tree = self.decisions_table.tree
        tree.delete(*tree.get_children())
        for d in rows:
            tree.insert(
                "",
                "end",
                values=(
                    _when(d.get("ts")),
                    d.get("coin") or "",
                    llm_settings.SIGNAL_MODE_NAMES.get(
                        d.get("mode"), d.get("mode") or ""
                    ),
                    llm_gate.DECISION_WORDS.get(
                        d.get("decision"), d.get("decision") or ""
                    ),
                    d.get("order_id") or d.get("trade_ref") or "",
                    d.get("reason") or "",
                ),
            )

    def _show_scores(self) -> None:
        tree = self.scores_table.tree
        tree.delete(*tree.get_children())
        groups: Dict[tuple, List[Any]] = {}
        for s in self.signals:
            groups.setdefault((s.provider, s.model, s.prompt_version), []).append(s)
        for (p, model, version), group in sorted(groups.items()):
            summary = llm_signals.signal_summary(group)
            try:
                gate = (
                    "passed"
                    if llm_gate.gate_status(self.store, p, model, version).passed
                    else "not passed"
                )
            except Exception:
                gate = ""
            tree.insert(
                "",
                "end",
                values=(
                    provider_name(p),
                    model,
                    f"v{version}",
                    summary["signals"],
                    summary["scored"],
                    summary["won"],
                    "" if summary["hit_rate"] is None else f"{summary['hit_rate']:.0%}",
                    (
                        ""
                        if summary["mean_return"] is None
                        else f"{summary['mean_return'] * 100:+.2f}%"
                    ),
                    gate,
                ),
            )

    def generate_trade_signals(self) -> bool:
        """Generate Signals: a signal now for each selected coin."""
        coins = self.selected_coins()
        if not coins:
            self.status_var.set("No coins: add coins in Settings, or type symbols.")
            return False
        self.generate_signals_btn.state(["disabled"])
        self._signals_left = len(coins)
        self.status_var.set(f"Asking for signals: {', '.join(coins)}...")
        for coin in coins:
            self._submit(
                lambda c=coin: self.engine.signal(c, source="manual"),
                self._signal_done,
                lambda exc, c=coin: self._signal_failed(c, exc),
            )
        return True

    def _signal_finished_one(self) -> None:
        left = getattr(self, "_signals_left", 0)
        if left:
            self._signals_left = left - 1
            if not self._signals_left:
                self.generate_signals_btn.state(["!disabled"])

    def _signal_done(self, result: Any) -> None:
        self._answered(result.routed, "signal", result.record.prompt_version)
        self.reload_signals()
        self._signal_finished_one()
        self.status_var.set(
            f"{result.record.coin}: {result.record.direction or 'no signal'}"
        )

    def _signal_failed(self, coin: str, exc: BaseException) -> None:
        self.status_var.set(f"{coin} signal: {exc}"[:300])
        self._signal_finished_one()

    def on_signal_select(self, _event=None) -> None:
        selection = self.signals_tree.selection()
        if not selection:
            return
        s = next((x for x in self.shown_signals if str(x.id) == selection[0]), None)
        if s is None:
            return
        self.signal_meta.set(
            f"{s.coin} {s.pair} · {provider_name(s.provider)} · {s.model} · "
            f"signal prompt v{s.prompt_version} · {_when(s.ts)}"
        )
        ui_markdown.show(self.signal_details, s.reasoning or "(no reasoning given)")

    def _tick_signals(self) -> None:
        self.reload_signals()
        self._after("signals", self._refresh_ms, self._tick_signals)

    def _tick_score(self) -> None:
        def scored(count) -> None:
            if count:
                self.reload_signals()

        self._submit(self.engine.score_pending, scored, lambda _exc: None)
        if self._score_ms:
            self._after("score", self._score_ms, self._tick_score)

    # ---- Research Reports ----

    def _build_reports_tab(self) -> None:
        gap = ui_tokens.SPACE["sm"]
        tab = ttk.Frame(self.notebook)
        self.reports_tab = tab
        self.notebook.add(tab, text="Research\nReports")
        bar = ttk.Frame(tab)
        bar.pack(side="top", fill="x", padx=gap, pady=(gap, 0))
        ttk.Label(bar, text="Report").pack(side="left", padx=(0, 4))
        self.report_type = ttk.Combobox(
            bar, values=list(REPORT_TYPES), state="readonly", width=16
        )
        self.report_type.set(REPORT_TYPES[0])
        self.report_type.pack(side="left", padx=(0, gap + 4))
        self.report_type.bind(
            "<<ComboboxSelected>>", lambda _e: self._report_type_changed()
        )
        ttk.Label(bar, text="Coin").pack(side="left", padx=(0, 4))
        self.report_coin_box = ttk.Combobox(
            bar, values=self.coins(), state="readonly", width=8
        )
        self.report_coin_box.pack(side="left", padx=(0, gap + 4))
        self.generate_report_btn = ttk.Button(
            bar,
            text="Generate Report",
            command=self.generate_report,
            style="Accent.TButton",
        )
        self.generate_report_btn.pack(side="left", padx=(0, gap))
        self.save_report_btn = ttk.Button(
            bar, text="Save Report", command=self.save_report
        )
        self.save_report_btn.pack(side="left", padx=(0, gap))
        self.save_report_btn.state(["disabled"])
        ttk.Button(
            bar, text="View / edit prompt", command=lambda: self.open_prompt("report")
        ).pack(side="left")
        self.report_meta = tk.StringVar(master=tab)
        ttk.Label(tab, textvariable=self.report_meta, style="Muted.TLabel").pack(
            side="top", anchor="w", padx=gap, pady=(4, 2)
        )
        self.report_display = _text_pane(tab)
        ui_markdown.show(self.report_display, "No report yet.")
        self._report_type_changed()

    def _report_type_changed(self) -> None:
        single = self.report_type.get() == "Coin Report"
        self.report_coin_box.state(["!disabled"] if single else ["disabled"])
        if single and not self.report_coin_box.get():
            coins = self.selected_coins()
            if coins:
                self.report_coin_box.set(coins[0])

    def generate_report(self) -> bool:
        kind = self.report_type.get()
        coins = (
            [self.report_coin_box.get()]
            if kind == "Coin Report"
            else self.selected_coins()
        )
        coins = [c for c in coins if c]
        if not coins:
            self.status_var.set("No coins for the report.")
            return False
        self.generate_report_btn.state(["disabled"])
        self.status_var.set(f"Writing the {kind}...")
        self._submit(
            lambda: self.engine.report(kind, coins),
            self._report_done,
            self._report_failed,
        )
        return True

    def _report_done(self, result: Any) -> None:
        self.report = result
        self.generate_report_btn.state(["!disabled"])
        self.report_meta.set(
            f"{result.report_type}: {', '.join(result.coins)} · {provider_name(result.provider)} "
            f"· {result.model} · report prompt v{result.prompt_version} · {_when(result.ts)}"
        )
        ui_markdown.show(self.report_display, result.text or "(the model gave no text)")
        self.save_report_btn.state(["!disabled"])
        self._answered(result.routed, "report", result.prompt_version)
        self.status_var.set("Report written")

    def _report_failed(self, exc: BaseException) -> None:
        self.generate_report_btn.state(["!disabled"])
        self.status_var.set(f"No report: {exc}"[:300])

    def report_path(self, result: Any) -> str:
        import pt_paths

        slug = re.sub(r"[^a-z0-9]+", "-", result.report_type.lower()).strip("-")
        if len(result.coins) == 1:
            slug += "-" + result.coins[0].lower()
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(result.ts))
        return pt_paths.data_file("reports", f"{slug}-{stamp}.md")

    def save_report(self) -> Optional[str]:
        """Save Report: the report as a .md file in the user data folder."""
        if self.report is None:
            return None
        path = self.report_path(self.report)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.report.markdown_file())
        except OSError as exc:
            self.status_var.set(f"The report was not saved: {exc}")
            return None
        self.status_var.set(f"Saved to {path}")
        return path

    # ---- prompts ----

    def open_prompt(self, kind: str) -> PromptEditor:
        return PromptEditor(
            self.research_frame,
            self.store,
            kind,
            on_changed=self._show_cost,
            messagebox=self._box,
        )


def create_research_engine_tab(parent, config: Dict = None):
    """The tab in ``parent`` (kept for callers of the old module)."""
    return ResearchEngineGUI(parent, config).research_frame
