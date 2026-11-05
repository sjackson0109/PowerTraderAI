"""
Settings > Risk: the limits that protect the account.

* **Account drawdown** - how far the account value is below the highest value the
  trader has seen (the peak): the peak, the account value and the drawdown now;
  the warning and critical levels and the emergency stop, each with the account
  value it equals at the peak; and Reset peak, which sets the peak to the account
  value shown.

Save writes the ``risk`` keys of ``pt_config.json`` (``SettingsManager.set_risk``),
which the trader reads before every drawdown check. Reset peak is a request the
trader applies (``risk_state``). The window is built like Settings > Strategy
(``strategy_settings_ui``): a scrolling body, a status line, Save and Cancel.
"""

from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import messagebox as _messagebox
from tkinter import ttk
from typing import Any, Callable, Dict, Mapping, Optional

import risk_state
from pt_settings_manager import (
    DEFAULT_DRAWDOWN_CRITICAL_PCT,
    DEFAULT_DRAWDOWN_WARNING_PCT,
    DEFAULT_EMERGENCY_DRAWDOWN_PCT,
    DRAWDOWN_LEVEL_RANGE,
    EMERGENCY_DRAWDOWN_RANGE,
)

TITLE = "Risk"
HELP_WRAP = 520

# The drawdown levels: setting key (in the risk section), label, range, default, help
LEVELS = (
    (
        "drawdown_warning_pct",
        "Warning %:",
        DRAWDOWN_LEVEL_RANGE,
        DEFAULT_DRAWDOWN_WARNING_PCT,
        "The trader's log shows a risk warning while the drawdown is at or above "
        "this level.",
    ),
    (
        "drawdown_critical_pct",
        "Critical %:",
        DRAWDOWN_LEVEL_RANGE,
        DEFAULT_DRAWDOWN_CRITICAL_PCT,
        "The trader's log shows a critical risk warning while the drawdown is at "
        "or above this level.",
    ),
    (
        "emergency_drawdown_pct",
        "Emergency stop %:",
        EMERGENCY_DRAWDOWN_RANGE,
        DEFAULT_EMERGENCY_DRAWDOWN_PCT,
        "At this drawdown the trader stops trading.",
    ),
)


def money(value: float) -> str:
    return f"${value:,.2f}"


def _number(value: Any) -> str:
    """``8.0`` -> ``"8"``, ``2.5`` -> ``"2.5"``."""
    return f"{value:g}" if isinstance(value, float) else str(value)


def parse_number(text: str) -> Optional[float]:
    """A number typed as "3" or "3%" (None if it is not a finite number)."""
    try:
        number = float((text or "").strip().replace("%", "").strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def drawdown_pct(peak: float, value: Optional[float]) -> Optional[float]:
    """How far ``value`` is below ``peak``, in percent (0 at or above it)."""
    if not peak > 0.0 or value is None:
        return None
    return max(0.0, (peak - float(value)) / peak * 100.0)


def level_hint(peak: float, pct: Optional[float]) -> str:
    """The account value a level equals at the peak."""
    if not peak > 0.0 or pct is None:
        return ""
    below = peak * pct / 100.0
    return f"at {money(peak - below)} ({money(below)} below the peak)"


class RiskSettingsWindow(tk.Toplevel):
    """The Risk window over ``parent``. ``manager_factory()`` returns the settings
    manager to read from and save through (a fresh one each time, so a change
    another window saved meanwhile is kept). ``books_dir`` is the trader's books
    folder for the trading mode (where the peak is kept); ``account_value()`` the
    last account value the trader reported (None before it has). ``on_saved()``
    runs after a save (the hub refreshes its Settings line)."""

    def __init__(
        self,
        parent: tk.Misc,
        books_dir: Optional[str] = None,
        account_value: Optional[Callable[[], Optional[float]]] = None,
        manager_factory: Optional[Callable[[], Any]] = None,
        on_saved: Optional[Callable[[], None]] = None,
        messagebox=None,
        palette: Optional[dict] = None,
    ) -> None:
        super().__init__(parent)
        self.title(TITLE)
        self.geometry("760x680")
        self.minsize(640, 480)
        if manager_factory is None:
            from pt_settings_manager import SettingsManager

            manager_factory = SettingsManager
        self._factory = manager_factory
        self._books_dir = books_dir
        self._account_value = account_value or (lambda: None)
        self._on_saved = on_saved
        self._box = messagebox or _messagebox
        self._palette = palette or {}
        if self._palette.get("BG"):
            self.configure(bg=self._palette["BG"])

        saved = self._factory().get("risk") or {}
        saved = saved if isinstance(saved, Mapping) else {}
        self.status_var = tk.StringVar(master=self, value="")
        self.peak_var = tk.StringVar(master=self)
        self.account_var = tk.StringVar(master=self)
        self.drawdown_var = tk.StringVar(master=self)
        # per setting key: the field's text and its hint
        self.vars: Dict[str, tk.StringVar] = {}
        self.hints: Dict[str, tk.StringVar] = {}
        for key, _label, _bounds, default, _help in LEVELS:
            self.vars[key] = tk.StringVar(
                master=self, value=_number(saved.get(key, default))
            )
            self.hints[key] = tk.StringVar(master=self)
        self._peak = 0.0
        try:
            self._build()
        except Exception:
            self.destroy()  # never leave a half-built window behind
            raise
        for key in self.vars:
            self.vars[key].trace_add("write", lambda *_: self._show_hints())
        self.refresh()
        self.transient(parent)

    # -- what the trader has seen -----------------------------------------------------

    def account_value(self) -> Optional[float]:
        try:
            value = self._account_value()
        except Exception:
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return value if value > 0.0 and math.isfinite(value) else None

    def refresh(self) -> None:
        """Show the peak, the account value and the drawdown now."""
        view = risk_state.current(self._books_dir)
        self._peak = view.peak_value
        value = self.account_value()
        if self._peak > 0.0:
            seen = (
                time.strftime(", seen %d %b %Y %H:%M", time.localtime(view.peak_ts))
                if view.peak_ts > 0.0
                else ""
            )
            self.peak_var.set(money(self._peak) + seen)
        else:
            self.peak_var.set("none recorded yet")
        self.account_var.set(
            "not reported yet"
            if value is None
            else f"{money(value)}, as last reported by the trader"
        )
        dd = drawdown_pct(self._peak, value)
        self.drawdown_var.set("" if dd is None else f"{dd:.2f}%")
        self._show_hints()

    def _show_hints(self) -> None:
        for key, var in self.vars.items():
            self.hints[key].set(level_hint(self._peak, parse_number(var.get())))

    # -- actions ---------------------------------------------------------------------

    def reset_peak(self) -> bool:
        """Set the peak to the account value shown, after a confirmation."""
        value = self.account_value()
        if value is None or not self._books_dir:
            message = "There is no account value from the trader to set the peak to."
            self.status_var.set(message)
            self._box.showerror(TITLE, message, parent=self)
            return False
        if not self._box.askyesno(
            "Reset peak?",
            f"Set the peak account value to {money(value)}, the account value "
            "last reported by the trader?\n\nDrawdown is then measured from "
            f"{money(value)}.",
            parent=self,
        ):
            return False
        try:
            risk_state.request_peak_reset(self._books_dir, value)
        except (OSError, ValueError) as exc:
            message = f"The peak could not be reset: {exc}"
            self.status_var.set(message)
            self._box.showerror(TITLE, message, parent=self)
            return False
        self.refresh()
        self.status_var.set(f"Peak set to {money(value)}.")
        return True

    # -- saving ----------------------------------------------------------------------

    def collect(self) -> Dict[str, float]:
        """What Save writes to the ``risk`` section; ValueError says, in plain
        words, which value is wrong."""
        values: Dict[str, float] = {}
        for key, label, (lo, hi), _default, _help in LEVELS:
            number = parse_number(self.vars[key].get())
            name = label.rstrip(":")
            if number is None or not lo <= number <= hi:
                raise ValueError(f"{name} must be a number from {lo:g} to {hi:g}.")
            values[key] = number
        if not values["drawdown_warning_pct"] < values["drawdown_critical_pct"]:
            raise ValueError("Warning % must be below Critical %.")
        if not values["drawdown_critical_pct"] < values["emergency_drawdown_pct"]:
            raise ValueError("Critical % must be below Emergency stop %.")
        return values

    def save(self) -> bool:
        try:
            values = self.collect()
        except ValueError as exc:
            self.status_var.set(str(exc))
            self._box.showerror(TITLE, str(exc), parent=self)
            return False
        if not self._factory().set_risk(values):
            message = "The risk settings could not be saved."
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
        self._body = body
        body.columnconfigure(2, weight=1)

        self._build_drawdown(body, 0)

        ttk.Label(
            self, textvariable=self.status_var, wraplength=HELP_WRAP, justify="left"
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(6, 0))
        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=12)
        ttk.Button(buttons, text="Save", command=self.save).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side="left", padx=8
        )

    def _help(self, frm: ttk.Frame, r: int, text: str, column: int = 0) -> None:
        ttk.Label(
            frm,
            text=text,
            style="Muted.TLabel",
            wraplength=HELP_WRAP,
            justify="left",
        ).grid(row=r, column=column, columnspan=3 - column, sticky="w")

    def _build_drawdown(self, frm: ttk.Frame, r: int) -> int:
        ttk.Label(frm, text="Account drawdown", style="Header.TLabel").grid(
            row=r, column=0, columnspan=3, sticky="w"
        )
        r += 1
        self._help(
            frm,
            r,
            "Drawdown is how far the account value is below the highest account "
            "value the trader has seen (the peak).",
        )
        r += 1
        for label, var in (
            ("Peak account value:", self.peak_var),
            ("Account value:", self.account_var),
            ("Drawdown:", self.drawdown_var),
        ):
            ttk.Label(frm, text=label).grid(
                row=r, column=0, sticky="w", padx=(0, 10), pady=(4, 0)
            )
            ttk.Label(frm, textvariable=var).grid(
                row=r, column=1, columnspan=2, sticky="w", pady=(4, 0)
            )
            r += 1
        ttk.Button(frm, text="Reset peak...", command=self.reset_peak).grid(
            row=r, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Label(
            frm,
            text="sets the peak to the account value above",
            style="Muted.TLabel",
        ).grid(row=r, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=(6, 0))
        r += 1

        for key, label, (lo, hi), default, help_text in LEVELS:
            ttk.Label(frm, text=label).grid(
                row=r, column=0, sticky="w", padx=(0, 10), pady=(10, 0)
            )
            ttk.Entry(frm, textvariable=self.vars[key], width=10).grid(
                row=r, column=1, sticky="w", pady=(10, 0)
            )
            ttk.Label(frm, textvariable=self.hints[key]).grid(
                row=r, column=2, sticky="w", padx=(10, 0), pady=(10, 0)
            )
            r += 1
            self._help(
                frm,
                r,
                f"{help_text} {lo:g} to {hi:g}, default {default:g}.",
                column=1,
            )
            r += 1
        return r
