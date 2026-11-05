"""
Settings > Training, "Check the models in use...": the entry gate run again on each
coin's model in use (``pt_pattern_trainer.py COIN --check-gate``: its validation fit
is refitted from its manifest and its entries replayed on its own held-out bars;
nothing is trained, published or changed). One coin at a time, off the Tk thread
(ui_jobs); the window lists each coin's result as it arrives.

``run_check(coin)`` does the work and returns ``{"code": exit code, "record": the
coin's ``<coin>_gate_check.json`` (or None), "output": the last lines it printed}``;
the hub gives it (``PowerTraderHub.run_gate_check``), tests give a fake.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, Optional, Sequence

import ui_table
import ui_tokens
from ui_jobs import BackgroundJobs

COLUMNS = ("coin", "model", "vs_random", "gate", "hit_rate")
HEADINGS = {
    "coin": "Coin",
    "model": "Model in use",
    "vs_random": "Return after fees vs random",
    "gate": "Gate",
    "hit_rate": "Hit rate",
}


def row_values(coin: str, result: Dict[str, Any]) -> tuple:
    """A coin's table row from ``run_check``'s result."""
    import entry_gate

    record = result.get("record") or {}
    model = record.get("model_id") or ""
    gate = record.get("gate")
    if not gate:
        why = record.get("error") or _last_line(result.get("output", ""))
        return (coin, model, "", why or "could not be checked", "")
    decision = entry_gate.Decision.from_dict(gate)
    rate = decision.candidate.hit_rate
    return (
        coin,
        model,
        decision.short() or "no entries",
        "passed" if decision.passed else "not passed",
        "" if rate is None else f"{rate:.0%}",
    )


def detail_text(coin: str, result: Dict[str, Any]) -> str:
    """Everything the check printed about the gate, for the selected row."""
    import entry_gate

    record = result.get("record") or {}
    gate = record.get("gate")
    if not gate:
        return (
            record.get("error")
            or _last_line(result.get("output", ""))
            or f"{coin}: no result"
        )
    lines = entry_gate.Decision.from_dict(gate).lines()
    if record.get("refit_matches_record") is False:
        lines.append(
            "The refitted validation fit differs from the one its manifest records "
            "(the program or the candles changed since it was trained)."
        )
    return f"{coin}, {record.get('model_id')}:\n" + "\n".join(lines)


def _last_line(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


class GateCheckWindow(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        coins: Sequence[str],
        run_check: Callable[[str], Dict[str, Any]],
    ):
        super().__init__(master)
        self.title("Check the models in use")
        self.coins = list(coins)
        self.results: Dict[str, Dict[str, Any]] = {}
        gap = ui_tokens.SPACE["sm"]
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=(
                "Each coin's model in use, judged again by the entry gate: its "
                "validation fit is trained again and its entries replayed on the bars "
                "it never saw, against random entries with the same trade rules. "
                "Nothing is changed. A coin takes about as long as a training run."
            ),
            style="Muted.TLabel",
            wraplength=640,
            justify="left",
        ).pack(anchor="w")
        self.table = ui_table.DataTable(
            body,
            COLUMNS,
            HEADINGS,
            key="gate_check.results",
            empty_text="No coins",
            height=max(3, min(10, len(self.coins))),
            selectmode="browse",
        )
        self.table.pack(fill="both", expand=True, pady=(gap, 0))
        tree = self.table.tree
        for coin in self.coins:
            tree.insert("", "end", iid=coin, values=(coin, "", "", "waiting", ""))
        tree.bind("<<TreeviewSelect>>", lambda _e: self._show_detail())
        self.detail = tk.Text(body, height=8, wrap="word")
        self.detail.pack(fill="both", expand=True, pady=(gap, 0))
        self.detail.configure(state="disabled")
        self.status_var = tk.StringVar(master=self, value="")
        ttk.Label(body, textvariable=self.status_var).pack(anchor="w", pady=(gap, 0))
        ttk.Button(body, text="Close", command=self.destroy).pack(
            anchor="e", pady=(gap, 0)
        )
        self.jobs = BackgroundJobs(self, name="gate-check")
        self._next = 0
        self._run_check = run_check
        self._start_next()

    def _start_next(self) -> None:
        if self._next >= len(self.coins):
            self.status_var.set(
                f"Done: {len(self.results)} of {len(self.coins)} checked."
            )
            return
        coin = self.coins[self._next]
        self._next += 1
        self.status_var.set(f"Checking {coin} ({self._next} of {len(self.coins)})...")
        self._set_row(coin, (coin, "", "", "checking...", ""))
        self.jobs.submit(
            lambda c=coin: self._run_check(c),
            lambda result, c=coin: self._done(c, result),
            lambda exc, c=coin: self._done(
                c,
                {
                    "code": None,
                    "record": None,
                    "output": f"{type(exc).__name__}: {exc}",
                },
            ),
        )

    def _done(self, coin: str, result: Optional[Dict[str, Any]]) -> None:
        result = result or {}
        self.results[coin] = result
        self._set_row(coin, row_values(coin, result))
        if not self.table.tree.selection():
            self.table.tree.selection_set(coin)
        self._show_detail()
        self._start_next()

    def _set_row(self, coin: str, values: tuple) -> None:
        try:
            self.table.tree.item(coin, values=values)
        except tk.TclError:
            pass

    def _show_detail(self) -> None:
        selection = self.table.tree.selection()
        coin = selection[0] if selection else None
        text = detail_text(coin, self.results[coin]) if coin in self.results else ""
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")
