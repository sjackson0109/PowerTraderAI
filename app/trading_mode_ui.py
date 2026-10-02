"""
Tk widgets for the trading-mode gate (issue #96):

* ``TradingModeIndicator`` - the always-visible "MODE: PAPER" /
  "MODE: LIVE - <broker>" header strip.
* ``TradingModeDialog``    - choose paper/live and the broker; switching to live
  is only possible after ticking "Yes, I understand real money is at risk".

All decisions (is this change allowed? persist it) live in ``trading_mode``;
this module is only the presentation.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, List, Optional

from trading_mode import (
    LIVE_CONFIRM_TEXT,
    TESTNET_BROKERS,
    TradingModeError,
    TradingSettings,
    apply_trading_mode,
    can_apply,
)

PAPER_BG, PAPER_FG = "#FFC400", "#0A1B3A"
LIVE_BG, LIVE_FG = "#B00020", "#FFFFFF"
TESTNET_BG, TESTNET_FG = "#E67E00", "#FFFFFF"


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
    """Always-visible strip showing the current trading mode and broker."""

    def __init__(self, parent: tk.Misc, settings: TradingSettings) -> None:
        super().__init__(
            parent,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
            padx=14,
            pady=3,
        )
        self.update_settings(settings)

    def update_settings(self, settings: TradingSettings) -> None:
        if not settings.is_live:
            bg, fg = PAPER_BG, PAPER_FG
        elif settings.uses_testnet:
            bg, fg = TESTNET_BG, TESTNET_FG
        else:
            bg, fg = LIVE_BG, LIVE_FG
        self.configure(text=settings.label, bg=bg, fg=fg)


class TradingModeDialog(tk.Toplevel):
    """Pick paper/live + broker. Live is gated behind an explicit confirmation."""

    def __init__(
        self,
        parent: tk.Misc,
        current: TradingSettings,
        brokers: List[str],
        on_applied: Callable[[TradingSettings], None],
        apply_fn: Callable[..., TradingSettings] = apply_trading_mode,
    ) -> None:
        super().__init__(parent)
        self.title("Trading Mode")
        self.resizable(False, False)
        self.transient(parent)
        self._on_applied = on_applied
        self._apply_fn = apply_fn

        self.mode_var = tk.StringVar(value="live" if current.is_live else "paper")
        self.broker_var = tk.StringVar(value=current.active_broker or "")
        self.testnet_var = tk.BooleanVar(value=current.testnet)
        self.confirm_var = tk.BooleanVar(value=False)

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Radiobutton(
            body,
            text="Paper trading (simulated, no credentials, no real money)",
            variable=self.mode_var,
            value="paper",
            command=self._refresh,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(
            body,
            text="Live trading (real orders on the selected broker)",
            variable=self.mode_var,
            value="live",
            command=self._refresh,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 10))

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

        self.confirm_cb = ttk.Checkbutton(
            body,
            text=LIVE_CONFIRM_TEXT,
            variable=self.confirm_var,
            command=self._refresh,
        )
        self.confirm_cb.grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self.note_var = tk.StringVar()
        ttk.Label(body, textvariable=self.note_var, wraplength=380).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(14, 0))
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
        if not live:
            self.confirm_var.set(False)
        self.confirm_cb.configure(state="normal" if live else "disabled")

        allowed = can_apply(self.mode_var.get(), broker, self.confirm_var.get())
        self.apply_btn.configure(state="normal" if allowed else "disabled")

        if not live:
            self.note_var.set("Orders go to the simulated paper account only.")
        elif broker is None:
            self.note_var.set("Choose the broker to trade with.")
        elif not self.confirm_var.get():
            self.note_var.set("Tick the confirmation box to enable Apply.")
        else:
            self.note_var.set(
                "Restart the trader after applying. Orders will use real funds "
                "unless testnet is selected."
            )

    def _apply(self) -> None:
        try:
            new_settings = self._apply_fn(
                self.mode_var.get(),
                broker=self._selected_broker(),
                testnet=self.testnet_var.get(),
                live_confirmed=self.confirm_var.get(),
            )
        except TradingModeError as exc:
            messagebox.showerror("Trading mode", str(exc), parent=self)
            return
        self._on_applied(new_settings)
        self.destroy()
