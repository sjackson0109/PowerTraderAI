"""
The Entry Assessments tab: each entry the strategy or the thinker wanted, and what the entry
assessment recorded for it (signal_fusion.live). In this version every part is Off or Log
only, so the effect is always none. The table shows each assessment's facts and no outcome:
no trade's result and no score (the trade's own result is in Trade History). Text states
facts only.
"""

from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, Iterable, List, Optional, Tuple

import ui_table

COLUMNS = (
    "time",
    "coin",
    "source",
    "amount",
    "fee",
    "spread",
    "hourly",
    "share",
    "chance",
    "scale",
    "effect",
    "note",
)
HEADINGS = {
    "time": "Time",
    "coin": "Coin",
    "source": "From",
    "amount": "Entry",
    "fee": "Fee",
    "spread": "Spread",
    "hourly": "Hourly trading",
    "share": "Share of hourly",
    "chance": "Chance of profit",
    "scale": "Size scale",
    "effect": "Effect",
    "note": "Note",
}
NUMERIC = ("amount", "fee", "spread", "hourly", "share")
TIME_FORMAT = "%Y-%m-%d %H:%M"
POLL_MS = 5000
SOURCE_WORDS = {"strategy": "Strategy", "thinker": "Neural levels"}
PART_WORDS = {
    "entry_assessment": "Expected value",
    "volatility_shrink": "Size reduction",
    "spread_cap": "Spread",
    "participation_cap": "Share of hourly trading",
    "minimum": "Minimum entry",
}


def _pct(x: Optional[float], digits: int = 2) -> str:
    return "" if x is None else f"{x:.{digits}%}"


def _money(x: Optional[float]) -> str:
    return "" if x is None else f"${x:,.2f}"


def cells(r: Dict[str, Any]) -> Tuple[str, ...]:
    """One record's row."""
    parts = {p.get("name"): p for p in r.get("parts") or []}
    when = r.get("when_s")
    stamp = time.strftime(TIME_FORMAT, time.localtime(when)) if when else ""
    chance = parts.get("entry_assessment", {})
    scale = parts.get("volatility_shrink", {})
    notes: List[str] = []
    for name, p in parts.items():
        if p.get("mode") == "off":
            continue
        word = PART_WORDS.get(name, name)
        if not p.get("available"):
            notes.append(f"{word}: {p.get('reason') or 'not available'}")
        elif p.get("would") == "skip":
            notes.append(f"{word}: would have skipped the entry")
    if r.get("error"):
        notes.append(r["error"])
    effect = r.get("effect", "allow")
    return (
        stamp,
        r.get("coin", ""),
        SOURCE_WORDS.get(r.get("source"), r.get("source") or ""),
        _money(r.get("amount_usd")),
        _pct(r.get("fee")),
        _pct(r.get("spread"), 3),
        _money(r.get("hourly_median_usd")),
        _pct(r.get("participation"), 3),
        _pct(chance.get("value"), 1) if chance.get("available") else "not available",
        f"{scale['value']:.2f}" if scale.get("available") else "not available",
        "None" if effect == "allow" else effect.capitalize(),
        "; ".join(notes),
    )


class EntryAssessmentView(ttk.Frame):
    """The tab's table, refreshed when the records file changes."""

    def __init__(self, parent: tk.Misc, read=None, path=None, poll: bool = True):
        super().__init__(parent)
        from signal_fusion import live

        self._read = read or live.read_records
        self._path = path or live.records_path
        self._mtime: Optional[float] = None
        self.table = ui_table.DataTable(
            self,
            COLUMNS,
            HEADINGS,
            key="entry_assessments",
            numeric=NUMERIC,
            empty_text="No entry assessed yet",
        )
        self.table.pack(fill="both", expand=True)
        self.tree = self.table.tree
        if poll:
            self.after(POLL_MS, self._poll)

    def load(self, records: Iterable[Dict[str, Any]]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in records:
            if isinstance(r, dict):
                self.tree.insert("", "end", values=cells(r))
        self.table.settle()

    def refresh(self) -> None:
        self.load(self._read())

    def _poll(self) -> None:
        try:
            path = self._path()
            mtime = os.path.getmtime(path) if os.path.exists(path) else None
            if mtime != self._mtime:
                self._mtime = mtime
                self.refresh()
        except Exception:
            pass
        try:
            self.after(POLL_MS, self._poll)
        except tk.TclError:
            pass
