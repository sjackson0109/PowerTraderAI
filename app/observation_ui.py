"""
Settings > Paper trading, "Observation..." (FDS-SR-001 section 5.11).

"Start an observation" freezes the settings that decide a paper trade and the SHA-256 of
each trading-path program file; changing any of them ends the observation (checked
whenever this window opens or reconciles). The window shows the observation's SHA-256
and every frozen value; what an older observation did not record says so. "End the
observation" ends it by hand.

"Reconcile..." replays the observation's closed candles, for the paper trading coins,
through the same strategy and compares each trade with the paper trades: matched,
timing (within 3 candles), open, exit not placed, missed, extra, pending, a second entry,
or a row from other strategy settings (``strategy_lab.observation``), with each side's
paper fill against the replay's open, its delay and the fee paper charged. It runs off
the Tk thread (``ui_jobs``).

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
    "entry_delay",
    "fill",
    "fee",
    "replay_exit",
    "paper_exit",
    "exit_delay",
    "exit_fill",
    "exit_fee",
    "differs",
)
HEADINGS = {
    "coin": "Coin",
    "result": "Result",
    "replay_entry": "Replay entry",
    "paper_entry": "Paper entry",
    "entry_delay": "Entry delay",
    "fill": "Paper entry fill vs replay open",
    "fee": "Paper entry fee",
    "replay_exit": "Replay exit",
    "paper_exit": "Paper exit",
    "exit_delay": "Exit delay",
    "exit_fill": "Paper exit fill vs replay open",
    "exit_fee": "Paper exit fee",
    "differs": "Strategy fields that differ",
}
RESULTS = {
    "matched": "Matched",
    "timing": "Different candle",
    "missed": "Not placed",
    "extra": "Extra",
    "open": "Open",
    "exit_missed": "Exit not placed",
    "pending": "Pending",
    "duplicate": "Second entry",
    "different": "Other strategy settings",
}
# The trade rows' strategy fields, as Settings > Strategy names them
FIELDS = {
    "strategy_id": "strategy",
    "strategy_version": "version",
    "strategy_params_sha256": "parameters",
    "strategy_timeframe": "timeframe",
    "strategy_overlays": "stops and gates",
}
FROZEN_COLUMNS = ("name", "value")
FROZEN_HEADINGS = {
    "name": "Frozen setting or program file",
    "value": "Value or SHA-256",
}
NOT_RECORDED = "Not recorded for this observation"
# The summary's words for the results after the first four, shown when there are any
MORE = (
    ("open", "open"),
    ("exit_missed", "exit not placed"),
    ("pending", "pending"),
    ("duplicate", "second entries"),
    ("different", "other strategy settings"),
)


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


def delay_text(s: Optional[int]) -> str:
    """A fill's delay after the replay's: seconds under a minute, else hours and
    minutes."""
    if s is None:
        return ""
    sign = "-" if s < 0 else "+"
    if abs(s) < 60:
        return f"{sign}{abs(s)} s"
    hours, minutes = divmod(int(round(abs(s) / 60)), 60)
    return f"{sign}{hours} h {minutes:02d} min" if hours else f"{sign}{minutes} min"


def _pct(x: Optional[float], signed: bool = False) -> str:
    if x is None:
        return ""
    return f"{x * 100:+.3f}%" if signed else f"{x * 100:.3f}%"


def row_values(row: obs.Row) -> tuple:
    return (
        row.coin,
        RESULTS.get(row.result, row.result),
        _when(row.replay_entry_s),
        _when(row.paper_entry_s),
        delay_text(row.entry_delay_s),
        _pct(row.fill_vs_open, signed=True),
        _pct(row.fee_rate_paid),
        _when(row.replay_exit_s),
        _when(row.paper_exit_s),
        delay_text(row.exit_delay_s),
        _pct(row.exit_fill_vs_open, signed=True),
        _pct(row.exit_fee_rate_paid),
        ", ".join(FIELDS.get(f, f) for f in row.differs),
    )


def summary_text(rows: List[obs.Row]) -> str:
    """The counts by result, and the largest delays of the matched trades."""
    counts = obs.summary(rows)
    text = (
        f"Matched {counts['matched']}, on a different candle {counts['timing']}, "
        f"not placed {counts['missed']}, extra {counts['extra']}"
    )
    for kind, words in MORE:
        if counts.get(kind):
            text += f", {words} {counts[kind]}"
    text += "."
    matched = [r for r in rows if r.result == "matched"]
    if matched:
        entry = max(r.entry_delay_s or 0 for r in matched)
        exit_ = max(r.exit_delay_s or 0 for r in matched)
        text += (
            " The matched trades filled in the replay's candles: entries up to "
            f"{delay_text(entry)} and exits up to {delay_text(exit_)} after the "
            "replay's fills."
        )
    return text


def shown_value(value: Any) -> str:
    """A frozen value as the window shows it."""
    if value is None:
        return "Not set"
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and all(
        isinstance(v, (str, int, float)) and not isinstance(v, bool) for v in value
    ):
        return ", ".join(str(v) for v in value) if value else "Empty"
    return json.dumps(value, sort_keys=True)


def frozen_rows(segment: dict) -> List[Tuple[str, str]]:
    """The segment's frozen settings, then its program files with their SHA-256s, as
    (name, value). What it did not record (it started before that was frozen) says
    so."""
    snap = segment.get("snapshot") or {}
    scheme = obs.snapshot({}, {}, [])
    out = []
    for part in ("config", "gui"):
        frozen = snap.get(part) or {}
        for key in scheme[part]:
            out.append(
                (key, shown_value(frozen[key]) if key in frozen else NOT_RECORDED)
            )
    if "exchanges" in snap:
        out.append(("exchanges", shown_value(snap["exchanges"])))
    else:
        out.append(("exchanges", NOT_RECORDED))
    code = segment.get("code")
    if isinstance(code, dict):
        out += [(name, sha or "Missing") for name, sha in sorted(code.items())]
    else:
        out.append(("Program files", NOT_RECORDED))
    return out


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
    coins = obs.replay_coins(segment["snapshot"])
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
        self.geometry("1200x680")
        self.hub_dir = hub_dir
        self._read = read
        self._reconcile = reconcile_fn or default_reconcile
        self.status_var = tk.StringVar(master=self, value="")
        self.hash_var = tk.StringVar(master=self, value="")
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
                "for the paper trading coins through the same strategy and compares each "
                "trade with the paper trades."
            ),
            wraplength=900,
            justify="left",
            style="Muted.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            body, textvariable=self.status_var, wraplength=1100, justify="left"
        ).pack(anchor="w", pady=(8, 0))
        sha = ttk.Frame(body)
        sha.pack(anchor="w", fill="x", pady=(6, 0))
        ttk.Label(sha, text="SHA-256 of the frozen settings:").pack(side="left")
        ttk.Entry(sha, textvariable=self.hash_var, state="readonly", width=70).pack(
            side="left", padx=(6, 0)
        )
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
        self.frozen_table = ui_table.DataTable(
            body,
            FROZEN_COLUMNS,
            FROZEN_HEADINGS,
            empty_text="No observation yet",
            sortable=False,
            height=7,
        )
        self.frozen_table.pack(fill="both", expand=True, pady=(8, 0))
        self.table = ui_table.DataTable(
            body, COLUMNS, HEADINGS, empty_text="Not reconciled yet", height=10
        )
        self.table.pack(fill="both", expand=True, pady=(8, 0))
        ttk.Label(
            body, textvariable=self.summary_var, wraplength=1100, justify="left"
        ).pack(anchor="w", pady=(6, 0))
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
        self.hash_var.set((segment or {}).get("sha256") or "")
        tree = self.frozen_table.tree
        tree.delete(*tree.get_children())
        for name, value in frozen_rows(segment) if segment else []:
            tree.insert("", "end", values=(name, value))
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
        self.summary_var.set(summary_text(self.rows))
