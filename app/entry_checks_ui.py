"""
The entry assessment's rows in Settings (signal_fusion.settings): Settings > Strategy has
the entry assessment, Settings > Risk the volatility size reduction and the two entry
limits. Each is Off or Log only in this version; Log only records what it would have done
for every entry and changes none. The text states facts only.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, Mapping, Sequence

from signal_fusion import settings as fs

NAMES = {"off": "Off", "log_only": "Log only"}
CODES = {v: k for k, v in NAMES.items()}
STRATEGY_KEYS = ("entry_assessment",)
RISK_KEYS = ("volatility_shrink", "participation_cap", "spread_cap")
LABELS = {
    "entry_assessment": "Entry assessment:",
    "volatility_shrink": "Volatility size reduction:",
    "participation_cap": "Largest entry as a share of hourly trading:",
    "spread_cap": "Widest spread for an entry:",
}
HELP = {
    "entry_assessment": (
        "Log only records, for every entry the strategy wants, whether its expected "
        "value after fees would have stopped it. It never changes an entry. Veto is not "
        "offered yet: it needs a model whose results have been confirmed."
    ),
    "volatility_shrink": (
        "Log only records the smaller size each entry would have when its coin is more "
        "volatile than usual. It never changes an entry. On is not offered yet."
    ),
    "participation_cap": (
        "Log only records each entry's share of its coin's median hourly trading over "
        "the 20 previous days, against 1%. It never changes an entry. On is not offered "
        "yet."
    ),
    "spread_cap": (
        "Log only records the spread of each entry's quote, against 0.50%. It never "
        "changes an entry. On is not offered yet."
    ),
}


def make_vars(
    master: tk.Misc, saved: Mapping, keys: Sequence[str]
) -> Dict[str, tk.StringVar]:
    values = fs.normalise(saved)
    return {key: tk.StringVar(master=master, value=NAMES[values[key]]) for key in keys}


def build(
    frm: ttk.Frame,
    r: int,
    title: str,
    variables: Mapping[str, tk.StringVar],
    wrap: int,
    columns: int = 3,
) -> int:
    """A heading and one row per setting, its help under it; the next free row."""
    ttk.Label(frm, text=title, style="Header.TLabel").grid(
        row=r, column=0, columnspan=columns, sticky="w", pady=(14, 0)
    )
    r += 1
    for key, var in variables.items():
        ttk.Label(frm, text=LABELS[key]).grid(
            row=r, column=0, sticky="w", padx=(0, 10), pady=(10, 0)
        )
        ttk.Combobox(
            frm,
            textvariable=var,
            values=[NAMES[code] for code in fs.AVAILABLE[key]],
            state="readonly",
            width=10,
        ).grid(row=r, column=1, sticky="w", pady=(10, 0))
        r += 1
        ttk.Label(
            frm, text=HELP[key], style="Muted.TLabel", wraplength=wrap, justify="left"
        ).grid(row=r, column=1, columnspan=max(1, columns - 1), sticky="w")
        r += 1
    return r


def values(variables: Mapping[str, tk.StringVar]) -> Dict[str, str]:
    return {key: CODES.get(var.get(), "off") for key, var in variables.items()}


def save_if_changed(variables: Mapping[str, tk.StringVar], factory) -> bool:
    """Save the rows' values when they differ from what is saved (nothing is written
    otherwise, so the file keeps its other sections as they are). True when nothing had
    to be saved or the save worked."""
    chosen = values(variables)
    manager = factory()
    saved = fs.normalise(manager.get(fs.SECTION) or {})
    if all(saved[k] == v for k, v in chosen.items()):
        return True
    return fs.save(chosen, manager)
