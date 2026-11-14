"""
Settings > Risk: the limits that protect the account.

* **Account drawdown** - how far the account value is below the highest value the
  trader has seen (the peak): the peak, the account value and the drawdown now;
  the warning and critical levels and the emergency stop, each with the account
  value it equals at the peak; and Reset peak, which sets the peak to the account
  value shown.
* **Trading halt** - after an emergency stop: since when, why, and Resume trading,
  the only way buying starts again (a restart does not). A halt refuses buys only:
  exits, stops and the trailing margin still sell.
* **Position and DCA limits** - Start allocation %, Minimum order margin %, Max per
  coin %, DCA multiplier and Max DCA buys per coin in 24 hours, with the dollar
  amounts at the last account value.

Save checks every field first and shows what is wrong beside the field: a refused
save changes nothing. It writes the ``risk`` keys of ``pt_config.json``
(``SettingsManager.set_risk``), which the trader reads before every drawdown check,
and the limits through ``save_limits`` (the hub's settings, which the trader re-reads
when they change). The window says when each change applies. Reset peak and Resume
trading
are requests the trader applies (``risk_state``). The window is built like Settings
> Strategy (``strategy_settings_ui``): a scrolling body, a status line, Save and
Cancel. ``HaltBanner`` is the hub's BUYING HALTED banner.
"""

from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import messagebox as _messagebox
from tkinter import ttk
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

import position_sizing
import risk_state
import ui_tokens
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
        "At this drawdown the trader halts buying, and stays halted, also after "
        "a restart, until Resume trading is pressed. Exits, stops and the trailing "
        "margin still sell.",
    ),
)


# The position and DCA limits: setting key (the hub's settings), label, range, default,
# whole number, help. The ranges are the trader's own (pt_validation): a value outside
# them makes the trader keep its last settings.
LIMITS = (
    (
        "start_allocation_pct",
        "Start allocation %:",
        (0.0001, 100.0),
        position_sizing.DEFAULT_START_ALLOCATION_PCT,
        False,
        "A new trade is this % of the account value, or the exchange's minimum "
        "order when that is more.",
    ),
    (
        "min_order_margin_pct",
        "Minimum order margin %:",
        position_sizing.MIN_ORDER_MARGIN_RANGE,
        position_sizing.DEFAULT_MIN_ORDER_MARGIN_PCT,
        False,
        "When an entry is raised to the exchange's minimum order, it is raised by "
        "this much more, so the position stays above the minimum when valued at the "
        "bid after fees.",
    ),
    (
        "max_coin_allocation_pct",
        "Max per coin %:",
        (0.1, 100.0),
        position_sizing.DEFAULT_MAX_COIN_ALLOCATION_PCT,
        False,
        "The most one coin may hold, at cost, as % of the account value.",
    ),
    (
        "dca_multiplier",
        "DCA multiplier:",
        (0.1, 10.0),
        2.0,
        False,
        "Each DCA buy is the position's current value times this.",
    ),
    (
        "max_dca_buys_per_24h",
        "Max DCA buys / coin (rolling 24h):",
        (0, 100),
        2,
        True,
        "The most DCA buys one coin may have in any 24 hours; 0: none.",
    ),
)


def limit_hint(key: str, pct: Optional[float], account: Optional[float]) -> str:
    """The dollar amount a limit is at the account value."""
    if pct is None or account is None or pct < 0.0:
        return ""
    if key == "start_allocation_pct":
        entry = position_sizing.entry_usd(account, pct)
        return f"\u2248 {money(entry)} per entry, at least the exchange minimum"
    if key == "max_coin_allocation_pct":
        budget = position_sizing.coin_budget_usd(account, pct)
        return f"\u2248 {money(budget)} per coin with DCA; no DCA buy past it"
    return ""


# When the trader uses a change (how pt_trader reads each one)
APPLY_TEXT = (
    "Saved levels and limits apply from the trader's next cycle: it reads them "
    "again every cycle, so a running trader needs no restart. Reset peak applies at "
    "the trader's next cycle, or when it next starts. After an emergency stop the "
    "trader keeps running but buys nothing; after Resume trading it buys again from "
    "its next pass, or when it is next started."
)
FIX_TEXT = "Nothing was saved: correct the values marked in red."


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


def when(ts: float) -> str:
    return time.strftime("%d %b %Y %H:%M", time.localtime(ts))


def halt_text(view: risk_state.RiskView) -> str:
    """Why and since when trading is halted ("" when it is not)."""
    if not view.halted:
        return ""
    parts = [view.halt_reason or "Emergency stop"]
    if view.halted_ts > 0.0:
        since = f"since {when(view.halted_ts)}"
        if view.halt_value is not None:
            since += f", account value {money(view.halt_value)}"
        parts.append(since)
    return " \u00b7 ".join(parts)


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
    last account value the trader reported (None before it has). ``limits`` are the
    position and DCA limits as saved, ``save_limits(values)`` saves them (without
    it the window shows no limits). ``on_saved()`` runs after a save,
    ``on_changed()`` after Reset peak or Resume trading (the hub refreshes its
    Settings line and banner)."""

    def __init__(
        self,
        parent: tk.Misc,
        books_dir: Optional[str] = None,
        account_value: Optional[Callable[[], Optional[float]]] = None,
        limits: Optional[Mapping[str, Any]] = None,
        save_limits: Optional[Callable[[Dict[str, Any]], None]] = None,
        manager_factory: Optional[Callable[[], Any]] = None,
        on_saved: Optional[Callable[[], None]] = None,
        on_changed: Optional[Callable[[], None]] = None,
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
        self._save_limits = save_limits
        self._on_saved = on_saved
        self._on_changed = on_changed
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
        self.halt_var = tk.StringVar(master=self)
        # per setting key: the field's text, its hint, and what is wrong with it
        self.vars: Dict[str, tk.StringVar] = {}
        self.hints: Dict[str, tk.StringVar] = {}
        self.errors: Dict[str, tk.StringVar] = {}
        self._error_labels: Dict[str, ttk.Label] = {}
        for key, _label, _bounds, default, _help in LEVELS:
            self.vars[key] = tk.StringVar(
                master=self, value=_number(saved.get(key, default))
            )
            self.hints[key] = tk.StringVar(master=self)
        limits = limits if isinstance(limits, Mapping) else {}
        self._limit_keys = [spec[0] for spec in LIMITS] if save_limits else []
        for key, _label, _bounds, default, _whole, _help in LIMITS:
            if key in self._limit_keys:
                self.vars[key] = tk.StringVar(
                    master=self, value=_number(limits.get(key, default))
                )
                self.hints[key] = tk.StringVar(master=self)
        self._peak = 0.0
        # the entry checks (entry_checks_ui): Off or Log only in this version
        import entry_checks_ui

        self.entry_check_vars = entry_checks_ui.make_vars(
            self, self._factory().get("signal_fusion") or {}, entry_checks_ui.RISK_KEYS
        )
        try:
            self._build()
        except Exception:
            self.destroy()  # never leave a half-built window behind
            raise
        for key in self.vars:
            self.vars[key].trace_add("write", lambda *_: self._show_hints())
            self.vars[key].trace_add("write", lambda *_, k=key: self._show_error(k, ""))
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
            seen = f", seen {when(view.peak_ts)}" if view.peak_ts > 0.0 else ""
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
        self.halt_var.set(
            f"Buying is halted: {halt_text(view)}. Sells still go through."
            if view.halted
            else "Trading is not halted."
        )
        self.resume_button.state(["!disabled"] if view.halted else ["disabled"])
        self._show_hints()

    def _show_hints(self) -> None:
        account = self.account_value()
        for key, var in self.vars.items():
            number = parse_number(var.get())
            if key in self._limit_keys:
                self.hints[key].set(limit_hint(key, number, account))
            else:
                self.hints[key].set(level_hint(self._peak, number))

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
        self._changed()
        return True

    def resume(self) -> bool:
        """Clear the halt, after a confirmation: the trader buys again from its
        next pass."""
        view = risk_state.current(self._books_dir)
        if not view.halted or not self._books_dir:
            self.refresh()
            return False
        message = (
            f"Buying was halted: {halt_text(view)}.\n\nThe trader buys again "
            "from its next pass."
        )
        try:
            from trading_mode import read_drawdown_levels

            stop = read_drawdown_levels(self._factory()).emergency_pct
        except Exception:
            stop = None
        dd = drawdown_pct(view.peak_value, self.account_value())
        if stop is not None and dd is not None and dd >= stop:
            message += (
                f"\n\nThe account is {dd:.2f}% below its peak, at or above the "
                f"{stop:g}% emergency stop: the trader halts buying again at its "
                "first check, unless the peak is reset or the stop is raised first."
            )
        if not self._box.askyesno("Resume trading?", message, parent=self):
            return False
        try:
            risk_state.request_resume(self._books_dir)
        except OSError as exc:
            text = f"Trading could not be resumed: {exc}"
            self.status_var.set(text)
            self._box.showerror(TITLE, text, parent=self)
            return False
        self.refresh()
        self.status_var.set(
            "Buying resumes at the trader's next pass, or when it is next started "
            "(the \u25ba button in the Trading section)."
        )
        self._changed()
        return True

    def _changed(self) -> None:
        if self._on_changed is not None:
            self._on_changed()

    # -- saving ----------------------------------------------------------------------

    def check(self) -> Tuple[Dict[str, float], Dict[str, Any], Dict[str, str]]:
        """Every field checked: the ``risk`` values, the limits, and what is wrong
        with each field that is (in plain words, by setting key)."""
        problems: Dict[str, str] = {}
        values: Dict[str, float] = {}
        for key, _label, (lo, hi), _default, _help in LEVELS:
            number = parse_number(self.vars[key].get())
            if number is None or not lo <= number <= hi:
                problems[key] = f"Must be a number from {lo:g} to {hi:g}."
            else:
                values[key] = number
        warning = values.get("drawdown_warning_pct")
        critical = values.get("drawdown_critical_pct")
        emergency = values.get("emergency_drawdown_pct")
        if warning is not None and critical is not None and not warning < critical:
            problems["drawdown_warning_pct"] = "Must be below Critical %."
        if critical is not None and emergency is not None and not critical < emergency:
            problems["drawdown_critical_pct"] = "Must be below Emergency stop %."
        limits: Dict[str, Any] = {}
        for key, _label, (lo, hi), _default, whole, _help in LIMITS:
            if key not in self._limit_keys:
                continue
            number = parse_number(self.vars[key].get())
            if (
                number is None
                or not lo <= number <= hi
                or (whole and not float(number).is_integer())
            ):
                kind = "a whole number" if whole else "a number"
                problems[key] = f"Must be {kind} from {lo:g} to {hi:g}."
            else:
                limits[key] = int(number) if whole else float(number)
        return values, limits, problems

    def _show_error(self, key: str, message: str) -> None:
        """``message`` beside the field (none: the field's error is hidden)."""
        self.errors[key].set(message)
        label = self._error_labels.get(key)
        if label is not None:
            if message:
                label.grid()
            else:
                label.grid_remove()

    def save(self) -> bool:
        values, limits, problems = self.check()
        for key in self.vars:
            self._show_error(key, problems.get(key, ""))
        if problems:
            self.status_var.set(FIX_TEXT)
            return False
        if not self._factory().set_risk(values):
            message = "The risk settings could not be saved."
            self.status_var.set(message)
            self._box.showerror(TITLE, message, parent=self)
            return False
        if self._save_limits is not None:
            try:
                self._save_limits(limits)
            except Exception as exc:
                message = f"The position and DCA limits could not be saved: {exc}"
                self.status_var.set(message)
                self._box.showerror(TITLE, message, parent=self)
                return False
        import entry_checks_ui

        if not entry_checks_ui.save_if_changed(self.entry_check_vars, self._factory):
            message = "The entry checks could not be saved."
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

        r = self._build_halt(body, 0)
        r = self._build_drawdown(body, r)
        if self._limit_keys:
            r = self._build_limits(body, r)
        import entry_checks_ui

        r = entry_checks_ui.build(
            body, r, "Entry checks", self.entry_check_vars, HELP_WRAP
        )
        ttk.Label(body, text="When changes apply", style="Header.TLabel").grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(14, 0)
        )
        self._help(body, r + 1, APPLY_TEXT)

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

    def _build_halt(self, frm: ttk.Frame, r: int) -> int:
        ttk.Label(frm, text="Trading halt", style="Header.TLabel").grid(
            row=r, column=0, columnspan=3, sticky="w"
        )
        r += 1
        ttk.Label(
            frm, textvariable=self.halt_var, wraplength=HELP_WRAP, justify="left"
        ).grid(row=r, column=0, columnspan=3, sticky="w", pady=(4, 0))
        r += 1
        self.resume_button = ttk.Button(
            frm, text="Resume trading...", command=self.resume
        )
        self.resume_button.grid(row=r, column=0, sticky="w", pady=(6, 0))
        r += 1
        self._help(
            frm,
            r,
            "After an emergency stop the trader places no new buys, also after a "
            "restart, until trading is resumed here. What it holds is still "
            "managed: exits, stops and the trailing margin still sell.",
        )
        return r + 1

    def _build_drawdown(self, frm: ttk.Frame, r: int) -> int:
        ttk.Label(frm, text="Account drawdown", style="Header.TLabel").grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(14, 0)
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
        ).grid(row=r, column=1, columnspan=2, sticky="w", pady=(6, 0))
        r += 1

        for key, label, bounds, default, help_text in LEVELS:
            r = self._field(frm, r, key, label, bounds, default, help_text)
        return r

    def _build_limits(self, frm: ttk.Frame, r: int) -> int:
        ttk.Label(frm, text="Position and DCA limits", style="Header.TLabel").grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(14, 0)
        )
        r += 1
        for key, label, bounds, default, _whole, help_text in LIMITS:
            r = self._field(frm, r, key, label, bounds, default, help_text)
        return r

    def _field(
        self,
        frm: ttk.Frame,
        r: int,
        key: str,
        label: str,
        bounds: tuple,
        default: Any,
        help_text: str,
    ) -> int:
        """A field's row: its label, entry and hint; its help, range and default
        under it. Returns the next free row."""
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
        self.errors[key] = tk.StringVar(master=self)
        error = ttk.Label(
            frm,
            textvariable=self.errors[key],
            style="Bad.TLabel",
            wraplength=HELP_WRAP,
            justify="left",
        )
        error.grid(row=r, column=1, columnspan=2, sticky="w")
        error.grid_remove()  # shown with a message only
        self._error_labels[key] = error
        r += 1
        lo, hi = bounds
        self._help(
            frm,
            r,
            f"{help_text} {lo:g} to {hi:g}, default {_number(default)}.",
            column=1,
        )
        return r + 1


class HaltBanner(tk.Frame):
    """Across the top of the hub while buying is halted: BUYING HALTED, why and
    since when, and a button that opens the Risk window (where Resume trading is)."""

    def __init__(self, parent: tk.Misc, on_open: Callable[[], None], **kwargs) -> None:
        bg, fg = ui_tokens.BANNER["halted"]
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0, **kwargs)
        tk.Label(
            self,
            text="BUYING HALTED",
            bg=bg,
            fg=fg,
            font=ui_tokens.font("display", "bold"),
            padx=12,
            pady=4,
        ).pack(side="left")
        tk.Button(
            self,
            text="Risk...",
            command=on_open,
            bg=fg,
            fg=bg,
            activebackground=fg,
            activeforeground=bg,
            relief="flat",
            padx=10,
            pady=2,
        ).pack(side="right", padx=6, pady=2)
        self.reason_var = tk.StringVar(master=self, value="")
        tk.Label(
            self,
            textvariable=self.reason_var,
            bg=bg,
            fg=fg,
            font=ui_tokens.font("subtitle"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

    def show(self, view: risk_state.RiskView) -> None:
        self.reason_var.set(halt_text(view))
