"""
Tk widgets for the trading-mode gate (issue #96):

* ``TradingModeIndicator`` - the always-visible "MODE: PAPER" /
  "MODE: LIVE - <broker>" header strip.
* ``TradingModeDialog``    - choose paper/live and the broker; switching to live
  is only possible after ticking "Yes, I understand real money is at risk", and
  is refused when the broker's key check refuses the saved API key.

All decisions (is this change allowed? persist it) live in ``trading_mode``;
this module is only the presentation.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

import ui_tokens
from trading_mode import (
    LIVE_CONFIRM_TEXT,
    TESTNET_BROKERS,
    KeyCheck,
    TradingModeError,
    TradingSettings,
    apply_trading_mode,
    broker_previews_orders,
    can_apply,
    check_broker_key,
)

# How often the Trading Mode window looks for the key check's answer (ms)
KEY_CHECK_POLL_MS = 50

PAPER_BG, PAPER_FG = ui_tokens.BANNER["paper"]
LIVE_BG, LIVE_FG = ui_tokens.BANNER["live"]
TESTNET_BG, TESTNET_FG = ui_tokens.BANNER["testnet"]


def pack_at_top(widget: tk.Misc, parent: tk.Misc) -> None:
    """Pack ``widget`` above everything already packed in ``parent``.

    ``winfo_children()[0]`` can't be used for this: the menu bar is a child
    widget that is never packed, and ``pack(before=<it>)`` raises TclError.
    """
    slaves = [w for w in parent.pack_slaves() if w is not widget]
    if slaves:
        widget.pack(side="top", fill="x", before=slaves[0])
    else:
        widget.pack(side="top", fill="x")


class TradingModeIndicator(tk.Label):
    """Always-visible strip: the trading mode and broker, the price and signal notes.

    Live and testnet: a strip of its own at the top ("MODE: LIVE — kraken · ...").
    Paper: the hub packs it into the PAPER TRADING banner, right of that title, so
    the header is one row and the strip does not repeat the mode ("PRICES: LIVE ·
    SIGNALS: STRAT-001 1h")."""

    def __init__(self, parent: tk.Misc, settings: TradingSettings) -> None:
        super().__init__(
            parent,
            font=ui_tokens.font("subtitle", "bold"),
            anchor="w",
            padx=12,
            pady=4,
        )
        self._settings = settings
        self._price_integrity: Optional[dict] = None
        self._signals_note: str = ""
        self._render()

    def update_settings(self, settings: TradingSettings) -> None:
        self._settings = settings
        self._price_integrity = None  # belongs to the previous mode's trader
        self._render()

    def update_signals_note(self, note: Optional[str]) -> None:
        """e.g. "SIGNALS: LEGACY (UNTRAINED)" / "SIGNALS: STRAT-001 1h"."""
        note = note or ""
        if note != self._signals_note:
            self._signals_note = note
            self._render()

    def update_price_integrity(self, price_integrity: Optional[dict]) -> None:
        """Latest ``price_integrity`` block from trader_status.json (paper only)."""
        if price_integrity != self._price_integrity:
            self._price_integrity = price_integrity
            self._render()

    def _render(self) -> None:
        settings = self._settings
        if not settings.is_live:
            bg, fg = PAPER_BG, PAPER_FG
        elif settings.uses_testnet:
            bg, fg = TESTNET_BG, TESTNET_FG
        else:
            bg, fg = LIVE_BG, LIVE_FG
        if settings.is_live:
            parts = [settings.label]
        else:  # the banner's PAPER TRADING title stands before it
            parts = [price_note(self._price_integrity)]
        parts.append(self._signals_note)
        text = " · ".join(p for p in parts if p)
        self.configure(text=text, bg=bg, fg=fg)


def price_note(price_integrity: Optional[dict]) -> str:
    """ "PRICES: LIVE" / "PRICES: DEGRADED (n in last hour)" for the paper strip;
    empty until the trader has reported (no claim without data)."""
    if not isinstance(price_integrity, dict):
        return ""
    try:
        degraded = int(price_integrity.get("degraded_last_hour", 0) or 0)
    except (TypeError, ValueError):
        return ""
    if degraded > 0 or price_integrity.get("state") == "degraded":
        return f"PRICES: DEGRADED ({degraded} in last hour)"
    return "PRICES: LIVE"


class TradingModeDialog(tk.Toplevel):
    """Pick paper/live + broker. Live is gated behind an explicit confirmation and
    the broker's key check (``key_check_fn(broker, preview)``)."""

    def __init__(
        self,
        parent: tk.Misc,
        current: TradingSettings,
        brokers: List[str],
        on_applied: Callable[[TradingSettings], None],
        apply_fn: Callable[..., TradingSettings] = apply_trading_mode,
        key_check_fn: Callable[[str, bool], KeyCheck] = check_broker_key,
        previews_fn: Callable[[Optional[str]], bool] = broker_previews_orders,
    ) -> None:
        super().__init__(parent)
        self.title("Trading Mode")
        self.resizable(False, False)
        self.transient(parent)
        self._on_applied = on_applied
        self._apply_fn = apply_fn
        self._key_check_fn = key_check_fn
        self._previews_fn = previews_fn

        self.mode_var = tk.StringVar(value="live" if current.is_live else "paper")
        self.broker_var = tk.StringVar(value=current.active_broker or "")
        self.testnet_var = tk.BooleanVar(value=current.testnet)
        # on unless the saved setting for this broker is off (the safe choice)
        self.preview_var = tk.BooleanVar(
            value=current.preview or not previews_fn(current.active_broker)
        )
        self.confirm_var = tk.BooleanVar(value=False)
        self.key_var = tk.StringVar()
        # the key check runs on a worker thread (it calls the broker); while it
        # runs, Check API key and Apply are disabled
        self._checking = False
        self._key_after: Optional[str] = None

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        self.paper_rb = ttk.Radiobutton(
            body,
            text="Paper trading (simulated, no credentials, no real money)",
            variable=self.mode_var,
            value="paper",
            command=self._refresh,
        )
        self.paper_rb.grid(row=0, column=0, columnspan=2, sticky="w")
        self.live_rb = ttk.Radiobutton(
            body,
            text="Live trading (real orders on the selected broker)",
            variable=self.mode_var,
            value="live",
            command=self._refresh,
        )
        self.live_rb.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 10))

        ttk.Label(body, text="Broker:").grid(row=2, column=0, sticky="w")
        self.broker_cb = ttk.Combobox(
            body,
            textvariable=self.broker_var,
            values=sorted(brokers),
            state="readonly",
            width=24,
        )
        self.broker_cb.grid(row=2, column=1, sticky="w", padx=(8, 0))
        self.broker_cb.bind("<<ComboboxSelected>>", lambda _e: self._refresh())

        self.testnet_cb = ttk.Checkbutton(
            body,
            text="Use testnet / sandbox (where the broker supports it)",
            variable=self.testnet_var,
        )
        self.testnet_cb.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.preview_cb = ttk.Checkbutton(
            body,
            text="Preview orders only (the broker shows each order; nothing is bought "
            "or sold)",
            variable=self.preview_var,
            command=self._refresh,
        )
        self.preview_cb.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        key_row = ttk.Frame(body)
        key_row.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.key_btn = ttk.Button(key_row, text="Check API key", command=self.check_key)
        self.key_btn.pack(side="left")
        ttk.Label(body, textvariable=self.key_var, wraplength=380).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )

        self.confirm_cb = ttk.Checkbutton(
            body,
            text=LIVE_CONFIRM_TEXT,
            variable=self.confirm_var,
            command=self._refresh,
        )
        self.confirm_cb.grid(row=7, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self.note_var = tk.StringVar()
        ttk.Label(body, textvariable=self.note_var, wraplength=380).grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )

        buttons = ttk.Frame(body)
        buttons.grid(row=9, column=0, columnspan=2, sticky="e", pady=(12, 0))
        self.apply_btn = ttk.Button(buttons, text="Apply", command=self._apply)
        self.apply_btn.pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side="right", padx=(0, 8)
        )

        self._refresh()
        self.grab_set()

    def _selected_broker(self) -> Optional[str]:
        return self.broker_var.get().strip() or None

    def _refresh(self) -> None:
        live = self.mode_var.get() == "live"
        broker = self._selected_broker()

        self.broker_cb.configure(state="readonly" if live else "disabled")
        self.testnet_cb.configure(
            state="normal" if (live and broker in TESTNET_BROKERS) else "disabled"
        )
        previews = bool(broker) and self._previews_fn(broker)
        self.preview_cb.configure(state="normal" if (live and previews) else "disabled")
        checkable = live and bool(broker) and not self._checking
        self.key_btn.configure(state="normal" if checkable else "disabled")
        if not live:
            self.confirm_var.set(False)
        self.confirm_cb.configure(state="normal" if live else "disabled")

        allowed = can_apply(self.mode_var.get(), broker, self.confirm_var.get())
        allowed = allowed and not self._checking
        self.apply_btn.configure(state="normal" if allowed else "disabled")

        # While a key is checked the choice is fixed, so what Apply saves is the
        # choice whose key was checked.
        for radio in (self.paper_rb, self.live_rb):
            radio.configure(state="disabled" if self._checking else "normal")
        if self._checking:
            for widget in (
                self.broker_cb,
                self.testnet_cb,
                self.preview_cb,
                self.confirm_cb,
            ):
                widget.configure(state="disabled")

        if not live:
            self.note_var.set("Orders go to the simulated paper account only.")
        elif broker is None:
            self.note_var.set("Choose the broker to trade with.")
        elif not self.confirm_var.get():
            self.note_var.set("Tick the confirmation box to enable Apply.")
        elif previews and self.preview_var.get():
            self.note_var.set(
                f"Restart the trader after applying. {broker.title()} shows each "
                "order the trader would place; nothing is bought or sold."
            )
        elif broker not in TESTNET_BROKERS:
            self.note_var.set(
                f"{broker.title()} has no test network: live orders use real money. "
                "Restart the trader after applying."
            )
        else:
            self.note_var.set(
                "Restart the trader after applying. Orders will use real funds "
                "unless testnet is selected."
            )

    def _previewing(self) -> bool:
        broker = self._selected_broker()
        return bool(broker) and self._previews_fn(broker) and self.preview_var.get()

    def check_key(self, then: Optional[Callable[[KeyCheck], None]] = None) -> None:
        """Run the broker's read-only key check on a worker thread (it calls the
        broker, which can take seconds) and show what it found. ``then`` gets the
        result on the Tk thread. Check API key and Apply are disabled meanwhile."""
        broker = self._selected_broker()
        if not broker or self._checking:
            return
        previewing = self._previewing()
        answers: "queue.Queue[KeyCheck]" = queue.Queue()

        def work() -> None:
            try:
                answers.put(self._key_check_fn(broker, previewing))
            except Exception as exc:  # the check reports failures itself
                answers.put(KeyCheck(False, f"The API key check failed: {exc}"))

        self._checking = True
        self.key_var.set("Checking the API key...")
        self._refresh()
        threading.Thread(target=work, name="key-check", daemon=True).start()
        self._key_after = self.after(
            KEY_CHECK_POLL_MS, self._poll_key_check, answers, then
        )

    def _poll_key_check(
        self,
        answers: "queue.Queue[KeyCheck]",
        then: Optional[Callable[[KeyCheck], None]],
    ) -> None:
        try:
            result = answers.get_nowait()
        except queue.Empty:
            self._key_after = self.after(
                KEY_CHECK_POLL_MS, self._poll_key_check, answers, then
            )
            return
        self._key_after = None
        self._checking = False
        text = result.message
        if result.warning:
            text += f" {result.warning}"
        self.key_var.set(text)
        self._refresh()
        if then is not None:
            then(result)

    def destroy(self) -> None:
        if self._key_after is not None:
            try:
                self.after_cancel(self._key_after)
            except tk.TclError:
                pass
            self._key_after = None
        super().destroy()

    def _apply(self) -> None:
        # the choice as it is now: changing it while the key is checked cannot
        # apply a broker whose key was not checked
        broker = self._selected_broker()
        choice: Dict[str, Any] = {
            "broker": broker,
            "testnet": self.testnet_var.get(),
            "live_confirmed": self.confirm_var.get(),
        }
        if broker and self._previews_fn(broker):
            choice["preview"] = self.preview_var.get()
        mode = self.mode_var.get()
        if mode == "live" and broker:
            self.check_key(
                then=lambda result: self._apply_checked(mode, choice, result)
            )
        else:
            self._apply_checked(mode, choice, None)

    def _apply_checked(
        self, mode: str, choice: Dict[str, Any], result: Optional[KeyCheck]
    ) -> None:
        if result is not None and not result.ok:
            messagebox.showerror("Trading mode", result.message, parent=self)
            return
        if result is not None and result.warning:
            messagebox.showwarning("Trading mode", result.warning, parent=self)
        try:
            new_settings = self._apply_fn(mode, **choice)
        except TradingModeError as exc:
            messagebox.showerror("Trading mode", str(exc), parent=self)
            return
        self._on_applied(new_settings)
        self.destroy()
