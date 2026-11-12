"""
Settings > Paper trading, "Observation..." (FDS-SR-001 section 5.11).

"Start an observation" freezes the settings that decide a paper trade and the SHA-256 of
each trading-path program file; changing any of them ends the observation (checked
whenever this window opens or reconciles). "End the observation" ends it by hand.
"Reconcile..." replays the observation's closed candles through the same strategy and
compares each trade with the paper trades: matched, timing (within 3 candles), missed or
extra, with the paper fill against the replay's open and the fee paper charged. It runs
off the Tk thread (``ui_jobs``).

``read_current()`` gives ``(pt_config, gui_settings, last written, exchanges)``: the
exchanges are the enabled ones in the order the exchange layer asks them. The hub gives
the real files, tests give their own; a reader that gives only the first three freezes
no exchanges. The words state facts only.
"""

from __future__ import annotations

import json
import os
import tkinter as tk
from datetime import datetime, timezone
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional, Tuple

import ui_table
from strategy_lab import observation as obs
from ui_jobs import BackgroundJobs

COLUMNS = (
    "coin",
    "result",
    "replay_entry",
    "paper_entry",
    "replay_exit",
    "paper_exit",
    "fill",
    "fee",
)
HEADINGS = {
    "coin": "Coin",
    "result": "Result",
    "replay_entry": "Replay entry",
    "paper_entry": "Paper entry",
    "replay_exit": "Replay exit",
    "paper_exit": "Paper exit",
    "fill": "Paper fill vs replay open",
    "fee": "Paper fee a side",
}
RESULTS = {
    "matched": "Matched",
    "timing": "Different candle",
    "missed": "Not placed",
    "extra": "Extra",
}


def read_current() -> Tuple[Dict[str, Any], Dict[str, Any], float, Optional[List[str]]]:
    """The settings files as they are now, when any of them was last written, and the
    enabled exchanges in the order the exchange layer asks them (None when they cannot
    be read)."""
    import pt_paths
    from exchange_check import settings_exchanges
    from trading_mode import settings_mapping

    config = settings_mapping(None) or {}
    path = pt_paths.gui_settings_file()
    try:
        with open(path, encoding="utf-8") as f:
            gui = json.load(f)
    except (OSError, ValueError):
        gui = {}
    try:
        exchanges: Optional[List[str]] = list(settings_exchanges())
    except (OSError, ValueError):
        exchanges = None
    written = 0.0
    for p in (pt_paths.settings_file(), path, pt_paths.trading_config_file()):
        try:
            written = max(written, os.path.getmtime(p))
        except OSError:
            pass
    return dict(config), gui if isinstance(gui, dict) else {}, written, exchanges


def _when(s: Optional[int]) -> str:
    if s is None:
        return ""
    return datetime.fromtimestamp(int(s), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def row_values(row: obs.Row) -> tuple:
    return (
        row.coin,
        RESULTS.get(row.result, row.result),
        _when(row.replay_entry_s),
        _when(row.paper_entry_s),
        _when(row.replay_exit_s),
        _when(row.paper_exit_s),
        "" if row.fill_vs_open is None else f"{row.fill_vs_open * 100:+.3f}%",
        "" if row.fee_rate_paid is None else f"{row.fee_rate_paid * 100:.3f}%",
    )


def paper_rows(hub_dir: str) -> List[dict]:
    path = os.path.join(hub_dir, "paper", "trade_history.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def default_reconcile(hub_dir: str, segment: dict) -> List[obs.Row]:
    spec = obs.spec_of(segment["snapshot"])
    coins = list((segment["snapshot"].get("gui") or {}).get("coins") or [])
    end_s = int(segment.get("ended_s") or datetime.now(tz=timezone.utc).timestamp())
    candles, context = obs.load_candles(spec, coins, int(segment["started_s"]), end_s)
    return obs.reconcile(segment, paper_rows(hub_dir), candles, end_s, context)


class ObservationWindow(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        hub_dir: str,
        read: Callable[[], tuple] = read_current,
        reconcile_fn: Optional[Callable[[str, dict], List[obs.Row]]] = None,
    ) -> None:
        super().__init__(master)
        self.title("Observation")
        self.geometry("1000x480")
        self.hub_dir = hub_dir
        self._read = read
        self._reconcile = reconcile_fn or default_reconcile
        self.status_var = tk.StringVar(master=self, value="")
        self.summary_var = tk.StringVar(master=self, value="")
        self.rows: List[obs.Row] = []
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=(
                "An observation keeps the settings that decide a paper trade: the "
                "strategy, its parameters, stops and candles, the coins, sizing and risk, "
                "the entry checks, the LLM signal mode and the exchange order. It also "
                "keeps the SHA-256 of each program file that decides, sizes or places a "
                "paper order. Changing any of them ends it. Reconcile replays its candles "
                "through the same strategy and compares each trade with the paper trades."
            ),
            wraplength=900,
            justify="left",
            style="Muted.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            body, textvariable=self.status_var, wraplength=900, justify="left"
        ).pack(anchor="w", pady=(8, 0))
        bar = ttk.Frame(body)
        bar.pack(anchor="w", pady=(8, 0))
        self.start_button = ttk.Button(
            bar, text="Start an observation", command=self.start
        )
        self.start_button.pack(side="left")
        self.end_button = ttk.Button(bar, text="End the observation", command=self.end)
        self.end_button.pack(side="left", padx=8)
        self.reconcile_button = ttk.Button(
            bar, text="Reconcile...", command=self.reconcile
        )
        self.reconcile_button.pack(side="left")
        self.table = ui_table.DataTable(
            body, COLUMNS, HEADINGS, empty_text="Not reconciled yet", height=10
        )
        self.table.pack(fill="both", expand=True, pady=(8, 0))
        ttk.Label(body, textvariable=self.summary_var).pack(anchor="w", pady=(6, 0))
        self.jobs = BackgroundJobs(self, name="observation")
        self.refresh()

    def _current(self) -> Tuple[dict, dict, float, Optional[List[str]]]:
        got = tuple(self._read())
        return got[0], got[1], got[2], got[3] if len(got) > 3 else None

    def _segment(self) -> Optional[dict]:
        config, gui, written, exchanges = self._current()
        obs.check(self.hub_dir, config, gui, written, exchanges)
        live = obs.open_segment(self.hub_dir)
        if live is not None:
            return live
        done = obs.segments(self.hub_dir)
        return done[-1] if done else None

    def refresh(self) -> None:
        segment = self._segment()
        live = segment is not None and not segment.get("ended_at")
        if segment is None:
            self.status_var.set("No observation yet.")
        elif live:
            self.status_var.set(f"Observing since {_when(segment['started_s'])} UTC.")
        else:
            self.status_var.set(
                f"The last observation ran from {_when(segment['started_s'])} to "
                f"{_when(segment.get('ended_s'))} UTC; it ended: {segment['end_reason']}."
            )
        self.start_button.state(["disabled"] if live else ["!disabled"])
        self.end_button.state(["!disabled"] if live else ["disabled"])
        self.reconcile_button.state(["!disabled"] if segment else ["disabled"])

    def start(self) -> None:
        config, gui, _written, exchanges = self._current()
        try:
            obs.start(self.hub_dir, config, gui, exchanges=exchanges)
        except obs.ObservationError as exc:
            self.status_var.set(str(exc))
            return
        self.refresh()

    def end(self) -> None:
        try:
            obs.end(self.hub_dir, "ended by hand")
        except obs.ObservationError as exc:
            self.status_var.set(str(exc))
            return
        self.refresh()

    def reconcile(self) -> None:
        segment = self._segment()
        if segment is None:
            return
        self.refresh()
        self.summary_var.set("Reconciling...")
        self.reconcile_button.state(["disabled"])
        self.jobs.submit(
            lambda: self._reconcile(self.hub_dir, segment), self._shown, self._failed
        )

    def _failed(self, exc: BaseException) -> None:
        self.reconcile_button.state(["!disabled"])
        self.summary_var.set(f"It could not be reconciled: {exc}")

    def _shown(self, rows: List[obs.Row]) -> None:
        self.reconcile_button.state(["!disabled"])
        self.rows = list(rows)
        tree = self.table.tree
        tree.delete(*tree.get_children())
        for row in self.rows:
            tree.insert("", "end", values=row_values(row))
        counts = obs.summary(self.rows)
        self.summary_var.set(
            f"Matched {counts['matched']}, on a different candle {counts['timing']}, "
            f"not placed {counts['missed']}, extra {counts['extra']}."
        )
