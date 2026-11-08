"""
Settings > Strategy: what decides each buy and sale, and every value it uses.

* **Strategies and stops** - every catalogue entry, with what it may be used for
  (research only, paper, or paper and live), whether it is enabled for research,
  and whether it is in use (FDS-SR-001 section 5.8). Highlighting one shows its
  description, its research tick and "Use for trading", offered only where its
  authorisation covers the trading mode.
* **Signals from** - a rule-based strategy, or the legacy neural levels with DCA and
  the trailing profit margin.
* **Strategy** - the strategies this trading mode may use (not one that needs a
  trained model), what each buys and sells on, and each parameter with its range,
  default and description.
* **Candles** - the timeframe the strategy decides on.
* **Stops and filters** - the risk overlays, each ticked on or off, with theirs.

Save writes the ``strategy`` keys of ``pt_config.json``
(``SettingsManager.set_strategy``); the trader reads them before every decision, so
no restart is needed. ``research_enabled`` is written only when a research tick
changed, so a settings file nobody changed stays as it was. Every value is checked first (bounds, whole numbers, the rules
between two parameters): a refused save changes nothing. A strategy's parameters are
saved only where they differ from its defaults, so "Reset to defaults" saves none.

The words come from ``strategies.descriptions``; the checks from the catalogue.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox as _messagebox
from tkinter import ttk
from typing import Any, Callable, Dict, List, Mapping, Optional

import ui_table
import ui_tokens
from market_data.timeframes import TIMEFRAME_SECONDS
from strategies import descriptions as words
from strategies.catalogue import CATALOGUE, allowed_in_mode
from strategies.settings import (
    DEFAULT_ACTIVE_ID,
    DEFAULT_ENGINE,
    DEFAULT_TIMEFRAME,
    ENGINES,
    params_problem,
    read_research_enabled,
)

TITLE = "Strategy"
HELP_WRAP = 520


def offered_strategies(mode: str = "paper") -> List[str]:
    """The strategies the window offers for trading in ``mode``, in catalogue order:
    every main strategy authorised for it, except one that needs a trained model."""
    return [
        sid
        for sid, e in CATALOGUE.items()
        if e["class_type"] == "main"
        and e["family"] != "model"
        and allowed_in_mode(sid, mode)
    ]


def overlay_ids() -> List[str]:
    """The stops and filters, in catalogue order."""
    return [sid for sid, e in CATALOGUE.items() if e["class_type"] == "risk_overlay"]


def listed_ids() -> List[str]:
    """Every entry the strategy list shows: the strategies, then the stops."""
    main = [sid for sid, e in CATALOGUE.items() if e["class_type"] == "main"]
    return main + overlay_ids()


def settings_coins() -> List[str]:
    """The coins in Settings (``gui_settings.json``), as the trader reads them."""
    import json

    import paper_coins
    import pt_paths

    try:
        with open(pt_paths.gui_settings_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    coins = data.get("coins") if isinstance(data, dict) else None
    return paper_coins.normalise(coins if isinstance(coins, list) else ())


def trading_mode_of(manager: Any) -> str:
    """The trading mode the settings name: "live" only when it is exactly that, as
    the trader reads it (trading_mode.py); anything else is paper."""
    try:
        trading = manager.get("trading") or {}
    except Exception:
        return "paper"
    mode = trading.get("mode") if isinstance(trading, Mapping) else None
    return "live" if mode == "live" else "paper"


def _number(value: Any) -> str:
    """``12`` -> ``"12"``, ``2.0`` -> ``"2"``, ``0.5`` -> ``"0.5"``."""
    return f"{value:g}" if isinstance(value, float) else str(value)


def stages_text(stages: Any) -> str:
    """``[[3, 1], [6, 3]]`` -> ``"3:1, 6:3"``."""
    try:
        return ", ".join(f"{_number(g)}:{_number(lk)}" for g, lk in stages)
    except (TypeError, ValueError):
        return str(stages)


def _kind(spec: Mapping[str, Any]) -> str:
    if spec.get("type") == "bool":
        return "bool"
    if spec.get("type") == "stages":
        return "stages"
    if "values" in spec:
        return "choice"
    return "number"


class StrategySettingsWindow(tk.Toplevel):
    """The Strategy window over ``parent``. ``manager_factory()`` returns the
    settings manager to read from and save through (a fresh one each time, so a
    change another window saved meanwhile is kept). ``on_saved()`` runs after a
    save (the hub refreshes its Settings line and mode strip)."""

    def __init__(
        self,
        parent: tk.Misc,
        manager_factory: Optional[Callable[[], Any]] = None,
        on_saved: Optional[Callable[[], None]] = None,
        messagebox=None,
        palette: Optional[dict] = None,
        coins_factory: Optional[Callable[[], List[str]]] = None,
    ) -> None:
        super().__init__(parent)
        self._coins = coins_factory or settings_coins
        self.title(TITLE)
        self.geometry("760x780")
        self.minsize(640, 480)
        if manager_factory is None:
            from pt_settings_manager import SettingsManager

            manager_factory = SettingsManager
        self._factory = manager_factory
        self._on_saved = on_saved
        self._box = messagebox or _messagebox
        self._palette = palette or {}
        if self._palette.get("BG"):
            self.configure(bg=self._palette["BG"])

        saved = self._factory().get("strategy") or {}
        self._saved = saved if isinstance(saved, Mapping) else {}
        self._mode = trading_mode_of(self._factory())
        raw_params = self._saved.get("params")
        self._saved_params: Dict[str, dict] = (
            {k: dict(v) for k, v in raw_params.items() if isinstance(v, Mapping)}
            if isinstance(raw_params, Mapping)
            else {}
        )
        notes: List[str] = []

        engine = self._saved.get("engine", DEFAULT_ENGINE)
        if engine not in ENGINES:
            notes.append(f"The saved signal source {engine!r} is not one of these.")
            engine = DEFAULT_ENGINE
        active = self._saved.get("active_id", DEFAULT_ACTIVE_ID)
        if active not in offered_strategies(self._mode):
            notes.append(f"The saved strategy {active!r} is not one of these.")
            active = DEFAULT_ACTIVE_ID
        timeframe = self._saved.get("timeframe", DEFAULT_TIMEFRAME)
        if timeframe not in TIMEFRAME_SECONDS:
            notes.append(f"The saved candles {timeframe!r} are not one of these.")
            timeframe = DEFAULT_TIMEFRAME
        saved_overlays: Dict[str, dict] = {}
        raw_overlays = self._saved.get("overlays")
        for spec in raw_overlays if isinstance(raw_overlays, list) else ():
            if isinstance(spec, Mapping) and spec.get("id") in overlay_ids():
                if not allowed_in_mode(spec["id"], self._mode):
                    notes.append(
                        f"The saved stop {words.name_of(spec['id'])} cannot be used "
                        f"for {self._mode} trading."
                    )
                    continue
                params = spec.get("params")
                saved_overlays[spec["id"]] = (
                    dict(params) if isinstance(params, Mapping) else {}
                )

        self.engine_var = tk.StringVar(master=self, value=engine)
        self.strategy_var = tk.StringVar(master=self, value=words.name_of(active))
        self.timeframe_var = tk.StringVar(
            master=self, value=words.timeframe_name(timeframe)
        )
        self.status_var = tk.StringVar(master=self, value=" ".join(notes))
        # the strategy list: what is enabled for research, and what is highlighted
        self._research_saved = set(read_research_enabled({"strategy": self._saved}))
        self.research_on: Dict[str, tk.BooleanVar] = {
            sid: tk.BooleanVar(master=self, value=sid in self._research_saved)
            for sid in listed_ids()
        }
        self.highlight_var = tk.StringVar(master=self, value=active)
        self.highlight_help_var = tk.StringVar(master=self)
        self.highlight_use_var = tk.StringVar(master=self)
        self.strategy_help_var = tk.StringVar(master=self)
        self.timeframe_help_var = tk.StringVar(master=self)
        # per strategy / overlay id: {parameter: variable}, made when first shown
        self._param_vars: Dict[str, Dict[str, tk.Variable]] = {}
        self.overlay_on: Dict[str, tk.BooleanVar] = {}
        for oid in overlay_ids():
            self.overlay_on[oid] = tk.BooleanVar(
                master=self, value=oid in saved_overlays
            )
            self._make_vars(oid, saved_overlays.get(oid, {}))
        # the entry assessment (entry_checks_ui): Off or Log only in this version
        import entry_checks_ui

        self.entry_check_vars = entry_checks_ui.make_vars(
            self,
            self._factory().get("signal_fusion") or {},
            entry_checks_ui.STRATEGY_KEYS,
        )

        try:
            self._build()
        except Exception:
            self.destroy()  # never leave a half-built window behind
            raise
        self.engine_var.trace_add("write", lambda *_: self._show_engine())
        self.strategy_var.trace_add("write", lambda *_: self._show_strategy())
        self.timeframe_var.trace_add("write", lambda *_: self._show_timeframe())
        for var in list(self.research_on.values()) + list(self.overlay_on.values()):
            var.trace_add("write", lambda *_: self._refresh_list())
        self._show_engine()
        self._show_strategy()
        self._show_highlight()
        self.transient(parent)

    # -- values ----------------------------------------------------------------------

    def selected_strategy(self) -> str:
        name = self.strategy_var.get()
        for sid in offered_strategies(self._mode):
            if words.name_of(sid) == name:
                return sid
        return DEFAULT_ACTIVE_ID

    def research_enabled(self) -> List[str]:
        """The entries ticked for research, in the list's order."""
        return [sid for sid in listed_ids() if self.research_on[sid].get()]

    def can_use(self, sid: str) -> bool:
        """Whether "Use for trading" is offered for ``sid`` in this trading mode."""
        if CATALOGUE[sid]["class_type"] == "main":
            return sid in offered_strategies(self._mode)
        return allowed_in_mode(sid, self._mode)

    def use_highlighted(self) -> None:
        """ "Use for trading": the highlighted strategy becomes the one Save trades,
        or the highlighted stop is ticked. Nothing happens where it is not allowed."""
        sid = self.highlight_var.get()
        if sid not in CATALOGUE or not self.can_use(sid):
            return
        if CATALOGUE[sid]["class_type"] == "main":
            self.engine_var.set("catalogue")
            self.strategy_var.set(words.name_of(sid))
        else:
            self.overlay_on[sid].set(True)
            self._show_overlay(sid)

    def selected_timeframe(self) -> str:
        name = self.timeframe_var.get()
        for tf in words.timeframes():
            if words.timeframe_name(tf) == name:
                return tf
        return DEFAULT_TIMEFRAME

    def param_vars(self, sid: str) -> Dict[str, tk.Variable]:
        """The variables behind ``sid``'s parameter fields (made from its saved
        parameters the first time)."""
        if sid not in self._param_vars:
            self._make_vars(sid, self._saved_params.get(sid, {}))
        return self._param_vars[sid]

    def _make_vars(self, sid: str, saved: Mapping[str, Any]) -> None:
        entry = CATALOGUE[sid]
        described = words.DESCRIPTIONS[sid]
        made: Dict[str, tk.Variable] = {}
        for name, spec in entry["param_bounds"].items():
            value = saved.get(name, entry["default_params"][name])
            kind = _kind(spec)
            if kind == "bool":
                made[name] = tk.BooleanVar(master=self, value=bool(value))
            elif kind == "choice":
                shown = described.params[name].choices.get(value, str(value))
                made[name] = tk.StringVar(master=self, value=shown)
            elif kind == "stages":
                made[name] = tk.StringVar(master=self, value=stages_text(value))
            else:
                made[name] = tk.StringVar(master=self, value=_number(value))
        self._param_vars[sid] = made

    def reset_strategy_params(self) -> None:
        """Show the selected strategy's defaults (saved by Save)."""
        sid = self.selected_strategy()
        self._make_vars(sid, {})
        self._show_strategy()

    def _parse(self, sid: str) -> Dict[str, Any]:
        """``sid``'s parameters from its fields; ValueError says, in plain words,
        which one is wrong."""
        entry = CATALOGUE[sid]
        described = words.DESCRIPTIONS[sid]
        values: Dict[str, Any] = {}
        for name, var in self.param_vars(sid).items():
            spec = entry["param_bounds"][name]
            default = entry["default_params"][name]
            label = f"{described.name}: {described.params[name].label}"
            kind = _kind(spec)
            if kind == "bool":
                values[name] = bool(var.get())
            elif kind == "choice":
                by_shown = {
                    described.params[name].choices.get(v, str(v)): v
                    for v in spec["values"]
                }
                if var.get() not in by_shown:
                    raise ValueError(f"{label}: choose one of the list.")
                values[name] = by_shown[var.get()]
            elif kind == "stages":
                values[name] = _parse_stages(label, var.get())
            else:
                values[name] = _parse_number(label, var.get(), spec, default)
        problem = words.rule_problem(sid, values) or params_problem(sid, values)
        if problem:
            raise ValueError(
                problem
                if problem.startswith(described.name)
                else f"{described.name}: {problem}"
            )
        return values

    def collect(self) -> Dict[str, Any]:
        """What Save writes: the ``strategy`` keys. With the neural levels chosen,
        only the signal source (the strategy's own values are kept as saved)."""
        engine = self.engine_var.get()
        research = self.research_enabled()
        extra = (
            {"research_enabled": research}
            if set(research) != self._research_saved
            else {}
        )
        if engine != "catalogue":
            return {"engine": engine, **extra}
        sid = self.selected_strategy()
        params = dict(self._saved_params)
        changed = _changed(sid, self._parse(sid))
        if changed:
            params[sid] = changed
        else:
            params.pop(sid, None)
        overlays = [
            {"id": oid, "params": _changed(oid, self._parse(oid))}
            for oid in overlay_ids()
            if self.overlay_on[oid].get()
        ]
        return {
            "engine": engine,
            "active_id": sid,
            "timeframe": self.selected_timeframe(),
            "params": params,
            "overlays": overlays,
            **extra,
        }

    def save(self) -> bool:
        try:
            values = self.collect()
        except ValueError as exc:
            self.status_var.set(str(exc))
            self._box.showerror(TITLE, str(exc), parent=self)
            return False
        if not self._factory().set_strategy(values):
            message = "The strategy settings could not be saved."
            self.status_var.set(message)
            self._box.showerror(TITLE, message, parent=self)
            return False
        import entry_checks_ui

        if not entry_checks_ui.save_if_changed(self.entry_check_vars, self._factory):
            message = "The entry assessment could not be saved."
            self.status_var.set(message)
            self._box.showerror(TITLE, message, parent=self)
            return False
        if self._on_saved is not None:
            self._on_saved()
        self.destroy()
        return True

    # -- layout ----------------------------------------------------------------------

    def _build(self) -> None:
        bg = self._palette.get("BG")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        viewport = ttk.Frame(self)
        viewport.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 0))
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)
        canvas = tk.Canvas(viewport, highlightthickness=0, bd=0)
        if bg:
            canvas.configure(bg=bg)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scroll.set)
        body = ttk.Frame(canvas, padding=(0, 0, 8, 0))
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def fit(_event=None) -> None:
            """The scroll region follows the content; the scrollbar shows only when
            the content is taller than the window."""
            bbox = canvas.bbox("all")
            canvas.configure(scrollregion=bbox)
            if bbox and bbox[3] - bbox[1] > canvas.winfo_height() + 1:
                scroll.grid()
            else:
                scroll.grid_remove()
                canvas.yview_moveto(0)

        def resize(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)
            fit()

        body.bind("<Configure>", fit, add="+")
        canvas.bind("<Configure>", resize, add="+")

        def wheel(event) -> None:
            if scroll.winfo_ismapped():
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _e: canvas.focus_set(), add="+")
        canvas.bind("<MouseWheel>", wheel, add="+")
        self._canvas = canvas
        body.columnconfigure(0, weight=1)

        r = 0
        listing = ttk.Frame(body)
        listing.grid(row=r, column=0, sticky="ew", pady=(0, 12))
        listing.columnconfigure(0, weight=1)
        r += 1
        self._build_list(listing)

        ttk.Label(body, text="Signals from", style="Header.TLabel").grid(
            row=r, column=0, sticky="w"
        )
        r += 1
        for engine in ENGINES:
            ttk.Radiobutton(
                body,
                text=words.ENGINE_NAMES[engine],
                value=engine,
                variable=self.engine_var,
            ).grid(row=r, column=0, sticky="w", pady=(4, 0))
            r += 1
            ttk.Label(
                body,
                text=words.ENGINE_HELP[engine],
                style="Muted.TLabel",
                wraplength=HELP_WRAP,
                justify="left",
            ).grid(row=r, column=0, sticky="w", padx=(ui_tokens.SPACE["xxl"], 0))
            r += 1

        self._catalogue_frame = ttk.Frame(body)
        self._catalogue_frame.grid(row=r, column=0, sticky="ew", pady=(10, 0))
        self._catalogue_frame.columnconfigure(1, weight=1)
        r += 1
        self._build_catalogue(self._catalogue_frame)

        import entry_checks_ui

        checks = ttk.Frame(body)
        checks.grid(row=r, column=0, sticky="ew", pady=(10, 0))
        checks.columnconfigure(1, weight=1)
        r += 1
        entry_checks_ui.build(
            checks, 0, "Entry assessment", self.entry_check_vars, HELP_WRAP, columns=2
        )

        ttk.Label(
            self, textvariable=self.status_var, wraplength=HELP_WRAP, justify="left"
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(6, 0))
        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=12)
        ttk.Button(buttons, text="Save", command=self.save).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side="left", padx=8
        )

    def _build_list(self, frm: ttk.Frame) -> None:
        """The strategy list, and the highlighted entry's details under it."""
        ttk.Label(frm, text="Strategies and stops", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        columns = ("name", "kind", "family", "candles", "use", "research", "in_use")
        headings = {
            "name": "Name",
            "kind": "Kind",
            "family": "Family",
            "candles": "Candles",
            "use": "Use",
            "research": "Research",
            "in_use": "In use",
        }
        self.list_table = ui_table.DataTable(
            frm,
            columns,
            headings,
            empty_text="No strategies",
            sortable=False,
            height=min(len(listed_ids()), 10),
            selectmode="browse",
        )
        self.list_table.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        tree = self.list_table.tree
        for sid in listed_ids():
            tree.insert("", "end", iid=sid, values=self._row(sid))
        tree.bind("<<TreeviewSelect>>", self._on_list_select, add="+")

        detail = ttk.Frame(frm)
        detail.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        detail.columnconfigure(0, weight=1)
        ttk.Label(
            detail,
            textvariable=self.highlight_help_var,
            wraplength=HELP_WRAP,
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            detail,
            textvariable=self.highlight_use_var,
            style="Muted.TLabel",
            wraplength=HELP_WRAP,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))
        actions = ttk.Frame(detail)
        actions.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.research_tick = ttk.Checkbutton(actions, text="Enabled for research")
        self.research_tick.pack(side="left")
        self.use_button = ttk.Button(
            actions, text="Use for trading", command=self.use_highlighted
        )
        self.use_button.pack(side="left", padx=(12, 0))
        ttk.Button(actions, text="Run a backtest...", command=self.open_backtest).pack(
            side="left", padx=(24, 0)
        )
        ttk.Button(actions, text="Compare results...", command=self.open_compare).pack(
            side="left", padx=(8, 0)
        )
        self.evidence_button = ttk.Button(
            actions, text="Model evidence...", command=self.open_evidence
        )
        self.evidence_button.pack(side="left", padx=(8, 0))

    def open_backtest(self):
        """Run a backtest... with the research ticks as they are now."""
        import strategy_lab_ui

        settings = {"strategy": {"research_enabled": self.research_enabled()}}
        return strategy_lab_ui.BacktestWindow(self, settings, self._coins())

    def open_compare(self):
        import strategy_lab_ui

        return strategy_lab_ui.CompareWindow(self)

    def open_evidence(self):
        """Model evidence... for the highlighted strategy (a stop has none)."""
        import strategy_lab_ui

        sid = self.highlight_var.get()
        if CATALOGUE.get(sid, {}).get("class_type") != "main":
            return None
        return strategy_lab_ui.EvidenceWindow(self, sid)

    def _row(self, sid: str) -> tuple:
        entry = CATALOGUE[sid]
        if entry["class_type"] == "main":
            in_use = (
                self.engine_var.get() == "catalogue" and self.selected_strategy() == sid
            )
            candles = words.timeframe_name(entry["timeframe_primary"])
        else:
            in_use = bool(self.overlay_on[sid].get())
            candles = "Any"
        return (
            words.name_of(sid),
            words.KIND_NAMES[entry["class_type"]],
            words.FAMILY_NAMES.get(entry["family"], entry["family"]),
            candles,
            words.USE_NAMES[entry["authorisation"]],
            "Yes" if self.research_on[sid].get() else "No",
            "Yes" if in_use else "",
        )

    def _refresh_list(self) -> None:
        table = getattr(self, "list_table", None)
        if table is None:
            return
        for sid in listed_ids():
            table.tree.item(sid, values=self._row(sid))
        self._show_highlight()

    def _on_list_select(self, _event=None) -> None:
        chosen = self.list_table.tree.selection()
        if chosen:
            self.highlight_var.set(chosen[0])
            self._show_highlight()

    def _show_highlight(self) -> None:
        sid = self.highlight_var.get()
        if sid not in CATALOGUE or not hasattr(self, "research_tick"):
            return
        described = words.DESCRIPTIONS.get(sid)
        summary = described.summary if described is not None else ""
        self.highlight_help_var.set(f"{words.name_of(sid)}: {summary}".strip())
        use = words.USE_HELP[CATALOGUE[sid]["authorisation"]]
        if not self.can_use(sid) and allowed_in_mode(sid, "paper"):
            use += f" Trading is set to {self._mode}."
        self.highlight_use_var.set(use)
        self.research_tick.configure(variable=self.research_on[sid])
        self.use_button.state(["!disabled"] if self.can_use(sid) else ["disabled"])
        main = CATALOGUE[sid]["class_type"] == "main"
        if hasattr(self, "evidence_button"):
            self.evidence_button.state(["!disabled"] if main else ["disabled"])

    def _build_catalogue(self, frm: ttk.Frame) -> None:
        r = 0
        ttk.Label(frm, text="Strategy:").grid(
            row=r, column=0, sticky="w", padx=(0, 10), pady=4
        )
        self.strategy_combo = ttk.Combobox(
            frm,
            textvariable=self.strategy_var,
            values=[words.name_of(sid) for sid in offered_strategies(self._mode)],
            state="readonly",
        )
        self.strategy_combo.grid(row=r, column=1, sticky="ew", pady=4)
        r += 1
        ttk.Label(
            frm,
            textvariable=self.strategy_help_var,
            style="Muted.TLabel",
            wraplength=HELP_WRAP,
            justify="left",
        ).grid(row=r, column=1, sticky="w")
        r += 1

        ttk.Label(frm, text="Candles:").grid(
            row=r, column=0, sticky="w", padx=(0, 10), pady=(10, 4)
        )
        self.timeframe_combo = ttk.Combobox(
            frm,
            textvariable=self.timeframe_var,
            values=[words.timeframe_name(tf) for tf in words.timeframes()],
            state="readonly",
        )
        self.timeframe_combo.grid(row=r, column=1, sticky="ew", pady=(10, 4))
        r += 1
        ttk.Label(
            frm,
            textvariable=self.timeframe_help_var,
            style="Muted.TLabel",
            wraplength=HELP_WRAP,
            justify="left",
        ).grid(row=r, column=1, sticky="w")
        r += 1

        head = ttk.Frame(frm)
        head.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(14, 4))
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="Parameters", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(
            head, text="Reset to defaults", command=self.reset_strategy_params
        ).grid(row=0, column=1, sticky="e")
        r += 1
        self._params_frame = ttk.Frame(frm)
        self._params_frame.grid(row=r, column=0, columnspan=2, sticky="ew")
        self._params_frame.columnconfigure(2, weight=1)
        r += 1

        ttk.Label(frm, text="Stops and filters", style="Header.TLabel").grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(14, 0)
        )
        r += 1
        ttk.Label(
            frm,
            text=words.STOPS_HELP,
            style="Muted.TLabel",
            wraplength=HELP_WRAP,
            justify="left",
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(0, 4))
        r += 1
        self._overlay_frames: Dict[str, ttk.Frame] = {}
        for oid in overlay_ids():
            described = words.DESCRIPTIONS[oid]
            tick = ttk.Checkbutton(
                frm,
                text=described.name,
                variable=self.overlay_on[oid],
                command=lambda o=oid: self._show_overlay(o),
            )
            tick.grid(row=r, column=0, columnspan=2, sticky="w", pady=(8, 0))
            if not allowed_in_mode(oid, self._mode):
                tick.state(["disabled"])  # this trading mode may not use it
            r += 1
            ttk.Label(
                frm,
                text=described.summary,
                style="Muted.TLabel",
                wraplength=HELP_WRAP,
                justify="left",
            ).grid(
                row=r,
                column=0,
                columnspan=2,
                sticky="w",
                padx=(ui_tokens.SPACE["xxl"], 0),
            )
            r += 1
            box = ttk.Frame(frm)
            box.grid(
                row=r,
                column=0,
                columnspan=2,
                sticky="ew",
                padx=(ui_tokens.SPACE["xxl"], 0),
            )
            box.columnconfigure(2, weight=1)
            self._overlay_frames[oid] = box
            self._param_rows(box, oid)
            self._show_overlay(oid)
            r += 1

    def _param_rows(self, frm: ttk.Frame, sid: str) -> None:
        """One row per parameter: its label, field and range; its description under."""
        for child in frm.winfo_children():
            child.destroy()
        entry = CATALOGUE[sid]
        described = words.DESCRIPTIONS[sid]
        for i, (name, var) in enumerate(self.param_vars(sid).items()):
            spec = entry["param_bounds"][name]
            default = entry["default_params"][name]
            p = described.params[name]
            kind = _kind(spec)
            ttk.Label(frm, text=p.label + ":").grid(
                row=2 * i, column=0, sticky="w", padx=(0, 10), pady=(6, 0)
            )
            if kind == "bool":
                field = ttk.Checkbutton(frm, variable=var)
                hint = f"default {'on' if default else 'off'}"
            elif kind == "choice":
                field = ttk.Combobox(
                    frm,
                    textvariable=var,
                    values=[p.choices.get(v, str(v)) for v in spec["values"]],
                    state="readonly",
                    width=10,
                )
                hint = f"default {p.choices.get(default, str(default))}"
            elif kind == "stages":
                field = ttk.Entry(frm, textvariable=var, width=24)
                hint = f"default {stages_text(default)}"
            else:
                field = ttk.Spinbox(
                    frm,
                    textvariable=var,
                    from_=spec["min"],
                    to=spec["max"],
                    increment=p.step,
                    width=8,
                )
                hint = (
                    f"{_number(spec['min'])} to {_number(spec['max'])}, "
                    f"default {_number(default)}"
                )
            field.grid(row=2 * i, column=1, sticky="w", pady=(6, 0))
            ttk.Label(frm, text=hint, style="Muted.TLabel").grid(
                row=2 * i, column=2, sticky="w", padx=(10, 0), pady=(6, 0)
            )
            ttk.Label(
                frm,
                text=p.help,
                style="Muted.TLabel",
                wraplength=HELP_WRAP - 40,
                justify="left",
            ).grid(row=2 * i + 1, column=1, columnspan=2, sticky="w")

    # -- showing -------------------------------------------------------------------

    def _show_engine(self) -> None:
        if self.engine_var.get() == "catalogue":
            self._catalogue_frame.grid()
        else:
            self._catalogue_frame.grid_remove()
        self._refresh_list()

    def _show_strategy(self) -> None:
        sid = self.selected_strategy()
        self.strategy_help_var.set(words.DESCRIPTIONS[sid].summary)
        self._param_rows(self._params_frame, sid)
        permitted = CATALOGUE[sid]["timeframes_permitted"]
        offered = [tf for tf in words.timeframes() if tf in permitted]
        self.timeframe_combo.configure(
            values=[words.timeframe_name(tf) for tf in offered]
        )
        if self.selected_timeframe() not in permitted:
            self.timeframe_var.set(
                words.timeframe_name(CATALOGUE[sid]["timeframe_primary"])
            )
        self._show_timeframe()
        self._refresh_list()

    def _show_timeframe(self) -> None:
        tf = self.selected_timeframe()
        text = (
            "The strategy decides when each candle closes: for each coin, once "
            f"every {words.timeframe_name(tf)}."
        )
        primary = CATALOGUE[self.selected_strategy()]["timeframe_primary"]
        if primary != tf:
            text += f" Default for this strategy: {words.timeframe_name(primary)}."
        self.timeframe_help_var.set(text)

    def _show_overlay(self, oid: str) -> None:
        state = ["!disabled"] if self.overlay_on[oid].get() else ["disabled"]
        for child in self._overlay_frames[oid].winfo_children():
            try:
                child.state(state)
            except (AttributeError, tk.TclError):
                pass


def _changed(sid: str, values: Mapping[str, Any]) -> Dict[str, Any]:
    """The parameters in ``values`` that differ from ``sid``'s defaults."""
    defaults = CATALOGUE[sid]["default_params"]
    return {k: v for k, v in values.items() if v != defaults[k]}


def _parse_number(label: str, text: str, spec: Mapping[str, Any], default: Any) -> Any:
    text = (text or "").strip().replace("%", "").strip()
    whole = isinstance(default, int) and not isinstance(default, bool)
    lo, hi = spec.get("min"), spec.get("max")
    span = f"from {_number(lo)} to {_number(hi)}"
    try:
        number = float(text)
    except ValueError:
        raise ValueError(
            f"{label} must be a {'whole ' if whole else ''}number {span}."
        ) from None
    if number != number:  # NaN
        raise ValueError(f"{label} must be a number {span}.")
    if whole:
        if not number.is_integer():
            raise ValueError(f"{label} must be a whole number {span}.")
        number = int(number)
    if (lo is not None and number < lo) or (hi is not None and number > hi):
        raise ValueError(f"{label} must be {span}.")
    return number


def _parse_stages(label: str, text: str) -> List[List[float]]:
    """``"3:1, 6:3"`` -> ``[[3, 1], [6, 3]]``, checked as the catalogue checks them."""
    stages: List[List[Any]] = []
    for part in (text or "").replace(";", ",").split(","):
        if not part.strip():
            continue
        gain_text, sep, lock_text = part.partition(":")
        try:
            if not sep:
                raise ValueError
            pair = [float(gain_text), float(lock_text)]
        except ValueError:
            raise ValueError(
                f"{label}: write each stage as gain %:lock %, e.g. 3:1."
            ) from None
        stages.append([int(x) if x.is_integer() else x for x in pair])
    if not stages:
        raise ValueError(f"{label}: give at least one stage, e.g. 3:1.")
    last_gain = 0.0
    for gain, lock in stages:
        if gain <= last_gain:
            raise ValueError(
                f"{label}: each stage's gain must be above 0 and above the one before."
            )
        if lock < 0 or lock >= gain:
            raise ValueError(
                f"{label}: each stage's lock must be at least 0 and below its gain."
            )
        last_gain = gain
    return stages
