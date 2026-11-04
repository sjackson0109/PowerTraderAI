"""
Settings > Risk: the limits that protect the account.

The window is built like Settings > Strategy (``strategy_settings_ui``): a
scrolling body, a status line, Save and Cancel.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox as _messagebox
from tkinter import ttk
from typing import Any, Callable, Optional

TITLE = "Risk"
HELP_WRAP = 520


class RiskSettingsWindow(tk.Toplevel):
    """The Risk window over ``parent``. ``manager_factory()`` returns the settings
    manager to read from and save through (a fresh one each time, so a change
    another window saved meanwhile is kept). ``on_saved()`` runs after a save (the
    hub refreshes its Settings line)."""

    def __init__(
        self,
        parent: tk.Misc,
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
        self._on_saved = on_saved
        self._box = messagebox or _messagebox
        self._palette = palette or {}
        if self._palette.get("BG"):
            self.configure(bg=self._palette["BG"])

        self.status_var = tk.StringVar(master=self, value="")
        try:
            self._build()
        except Exception:
            self.destroy()  # never leave a half-built window behind
            raise
        self.transient(parent)

    # -- saving ----------------------------------------------------------------------

    def save(self) -> bool:
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
        body.columnconfigure(1, weight=1)

        ttk.Label(
            self, textvariable=self.status_var, wraplength=HELP_WRAP, justify="left"
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(6, 0))
        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, sticky="ew", padx=12, pady=12)
        ttk.Button(buttons, text="Save", command=self.save).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side="left", padx=8
        )
