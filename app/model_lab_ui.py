"""
Settings > Training, "Compare models..." (FDS-MH-001 section 5.9, phase D): choose and
run a batch of the model lab's contestants, and read any saved batch's results.

* **Data.** Coins as ticks, the coin list first, with other coins typed in; the start
  date; and a read-only line saying where candles come from. Every batch's window ends
  on 2026-11-06 (``END``). Its last 18 months, 2025-05-06 to 2026-11-06, are then the
  held-back months that FDS-SR-001 shares (``strategy_lab.windows.LOCKBOX``), so the
  walk-forward stops at 2025-05-06, and no batch reads past 2026-11-06, which is kept
  for a forward check.
* **Models.** The catalogue (``model_lab.catalogue``), each in plain words, ticked as in
  the last batch. Two buttons tick a declared batch; when the ticks are exactly one, the
  batch is frozen as that declared batch. There are no parameter fields, so results
  cannot be tuned by trying values on screen.
* **Run / Stop.** Run freezes the batch (``batch.freeze``), then runs it (``batch.run``),
  off the Tk thread (``ui_jobs``), with progress. Stop, or closing the window, stops it:
  the batch keeps its frozen record and is marked as stopped.
* **Results.** One table per batch, for any saved batch (the newest first). Selecting a
  row shows its coins, rising and falling markets and fee lines. The trial count is
  shown, and the reference, "Enter whenever flat", is a row of its own.
* **Not here:** the final check. Nothing in this window reads the held-back months.

The words state facts only.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

import ui_table
from model_lab import batch as lab
from model_lab import catalogue, walkforward
from model_lab.series import epoch
from strategy_lab.windows import LOCKBOX
from ui_jobs import BackgroundJobs

WRAP = 1000
END = LOCKBOX[1]  # every batch's window ends here, so its last 18 months are LOCKBOX
DEFAULT_START = "2020-01-01"  # batch 1's
DECLARED_BUTTONS = (
    ("batch-1", "Tick batch 1"),
    ("pv-1", "Tick the price and volume batch"),
)
STAGES = {
    "series": "Reading candles",
    "trades": "Replaying trades",
    "fits": "Fitting models",
    "contestants": "Scoring models",
}
STATES = {
    "frozen": "frozen, not run",
    "running": "not finished",
    "stopped": "stopped",
    "done": "done",
    "refused": "refused",
    "failed": "failed",
}
CANDLES_TEXT = (
    "Hourly candles from your primary exchange, or, for a coin it cannot serve, from "
    "the next exchange in Settings > Exchanges that can. Fees: each coin's trading fee "
    "as that exchange states it, plus slippage."
)
COLUMNS = (
    "model",
    "result",
    "trades",
    "per_day",
    "profit",
    "drawdown",
    "in_trade",
    "r1",
    "r2",
    "edge",
)
HEADINGS = {
    "model": "Model",
    "trades": "Trades",
    "per_day": "Return per day held",
    "r1": "Above random: same waits",
    "r2": "Above random: other dates",
    "edge": "Smallest edge it could see",
    "result": "Result",
    "profit": "Total profit",
    "drawdown": "Worst drawdown",
    "in_trade": "Time in a trade",
}
NUMERIC = ("trades", "per_day", "r1", "r2", "edge", "profit", "drawdown", "in_trade")


# --- words ------------------------------------------------------------------------------


def _day(x: Optional[float]) -> str:
    return "" if x is None else f"{x * 100:+.3f}% a day"


def _pct(x: Optional[float], digits: int = 0) -> str:
    return "" if x is None else f"{x * 100:.{digits}f}%"


def _signed(x: Optional[float]) -> str:
    return "" if x is None else f"{x * 100:+.2f}%"


def _num(x: Optional[float], digits: int = 1) -> str:
    return "" if x is None else f"{x:.{digits}f}"


def _money(x: Optional[float]) -> str:
    return "" if x is None else f"{x:,.2f}"


def _date(text: Optional[str]) -> str:
    return (text or "")[:10]


def contestant_choices() -> List[Tuple[str, str]]:
    """Every contestant in the catalogue, in its order, with its words."""
    out = []
    for c in catalogue.catalogue():
        text = c.description
        if getattr(c, "forecast_only", False):
            text += " (its probabilities only, not tested)"
        elif not c.tested:
            text += " (shown for reference, not tested)"
        out.append((c.key, text))
    return out


def declared_for(keys: Sequence[str]) -> Optional[str]:
    """The declared batch whose contestants are exactly ``keys``, or None."""
    for name, (_version, members) in catalogue.DECLARED.items():
        if len(keys) == len(members) and set(keys) == set(members):
            return name
    return None


def batch_keys(ticked) -> Tuple[List[str], Optional[str]]:
    """The ticked contestants in catalogue order, and the declared batch they are (in
    that batch's own order), if any."""
    ticked = set(ticked)
    keys = [k for k, _text in contestant_choices() if k in ticked]
    declared = declared_for(keys)
    if declared is not None:
        keys = list(catalogue.DECLARED[declared][1])
    return keys, declared


def parse_coins(ticked: Sequence[str], typed: str) -> List[str]:
    """The ticked coins, then the typed ones (commas or spaces between), each once."""
    out = [str(c).upper() for c in ticked]
    for part in typed.replace(";", ",").replace(" ", ",").split(","):
        coin = part.strip().upper()
        if not coin:
            continue
        if not coin.isalnum() or len(coin) > 12:
            raise ValueError(f"{part.strip()} is not a coin symbol.")
        if coin not in out:
            out.append(coin)
    return out


def latest_start() -> pd.Timestamp:
    """The day after the latest start a batch ending on END can have: 12 months of bars
    before its first fold, which must start before the held-back months."""
    lock = walkforward.add_months(epoch(END), -walkforward.LOCKBOX_MONTHS)
    return pd.Timestamp(
        walkforward.add_months(lock, -walkforward.WARMUP_MONTHS), unit="s", tz="UTC"
    )


def parse_start(text: str) -> pd.Timestamp:
    try:
        ts = pd.Timestamp(str(text).strip())
    except (ValueError, TypeError):
        ts = None
    if ts is None or pd.isna(ts):
        raise ValueError("Give the start as a date, YYYY-MM-DD.")
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    if not ts < latest_start():
        raise ValueError(
            f"Start before {latest_start().date().isoformat()}: a batch needs 12 "
            f"months of bars before its first fold, and its folds end on "
            f"{LOCKBOX[0].date().isoformat()}."
        )
    return ts


def last_choices() -> Optional[Dict[str, Any]]:
    """The newest saved batch's contestants, coins and start, or None."""
    for batch_id in reversed(lab.batch_ids()):
        try:
            record = lab.read_batch(batch_id)
        except lab.BatchError:
            continue
        return {
            "contestants": [c["key"] for c in record.get("contestants", [])],
            "coins": list(record.get("coins", [])),
            "start": _date(record.get("calendar", {}).get("start")),
        }
    return None


def batch_label(batch_id: str) -> str:
    status = lab.read_status(batch_id) or {}
    return f"{batch_id} ({STATES.get(status.get('state'), 'no status')})"


def trials_text(counts: Mapping[str, int]) -> str:
    total = sum(counts.values())
    if not total:
        return "Trials logged so far: none."
    kinds = ", ".join(f"{kind} {n}" for kind, n in sorted(counts.items()))
    return f"Trials logged so far: {total} ({kinds})."


def summary_text(
    record: Mapping[str, Any], results: Optional[Mapping[str, Any]]
) -> str:
    cal = record["calendar"]
    folds = cal.get("folds") or []
    lines = [
        f"Coins: {', '.join(record['coins'])}. Window {_date(cal['start'])} to "
        f"{_date(cal['end'])}: models are scored from "
        f"{_date(folds[0][0]) if folds else ''} to {_date(cal['lockbox'][0])}, in "
        f"{len(folds)} folds of {cal['fold_months']} months; the last "
        f"{cal['lockbox_months']} months ({_date(cal['lockbox'][0])} to "
        f"{_date(cal['lockbox'][1])}) are held back and were not read.",
    ]
    fees = {
        f"{f['rate'] * 100:.2f}% plus {f['slippage'] * 100:.2f}% slippage"
        for f in record.get("fees", {}).values()
    }
    if len(fees) == 1:
        lines.append(f"Fee a side for every coin: {fees.pop()}.")
    elif fees:
        lines.append(
            "Fee a side: "
            + "; ".join(
                f"{coin} {f['rate'] * 100:.2f}% plus {f['slippage'] * 100:.2f}%"
                for coin, f in sorted(record["fees"].items())
            )
            + "."
        )
    if results is None:
        lines.append("No results: the batch did not finish.")
    else:
        pbo = results.get("pbo")
        lines.append(
            f"{results['k']} models tested, each against {record['draws']:,} draws of "
            "random entries with the same waits and on other dates"
            + (
                f"; probability of backtest overfitting {pbo:.2f}."
                if pbo is not None
                else "."
            )
        )
        late = [
            c
            for c, s in sorted((results.get("streams") or {}).items())
            if not s.get("hours")
        ]
        if late:
            lines.append(
                "No bars before the held-back months, so not scored: "
                + ", ".join(late)
                + "."
            )
    return "\n".join(lines)


def result_rows(results: Mapping[str, Any]) -> List[Tuple[str, tuple]]:
    """The results table's rows, as (contestant key, values), in the batch's order."""
    rows = []
    for key in results.get("order", []):
        r = results["contestants"][key]
        if r.get("verdict") == "forecast_only":
            rows.append(
                (
                    key,
                    (r["description"], r["verdict_text"]) + ("",) * 8,
                )
            )
            continue
        s = r["score"]
        r1, r2 = r.get("r1"), r.get("r2")
        rows.append(
            (
                key,
                (
                    r["description"],
                    r["verdict_text"],
                    s["trades"],
                    _day(s["per_day"]),
                    _money(s["profit"]),
                    _signed(s["drawdown"]),
                    _pct((r.get("time_in_trade") or {}).get("share")),
                    f"{_num(r1['rank'])}%" if r1 else "",
                    f"{_num(r2['rank'])}%" if r2 else "",
                    _day(r.get("smallest_edge")),
                ),
            )
        )
    return rows


def detail_text(r: Mapping[str, Any]) -> str:
    """One contestant's coins, markets and fee lines."""
    if r.get("verdict") == "forecast_only":
        return f"{r['description']}: fitted for its probabilities only; its trades are not scored."
    lines = [f"{r['description']}:"]
    for coin, c in sorted((r.get("coins") or {}).items()):
        joined = _date(c.get("joined")) or "never"
        lines.append(
            f"{coin}: scored from {joined}, {c['trades']} trades"
            + (f", {_day(c['per_day'])}" if c.get("per_day") is not None else "")
            + f", total profit {_money(c['profit'])}."
        )
    m = r.get("markets") or {}
    if m:
        lines.append(
            f"Rising markets (BTC above its close 90 days before): "
            f"{m['rising']['trades']} trades"
            + (
                f", {_day(m['rising']['per_day'])}"
                if m["rising"]["per_day"] is not None
                else ""
            )
            + f"; falling: {m['falling']['trades']} trades"
            + (
                f", {_day(m['falling']['per_day'])}"
                if m["falling"]["per_day"] is not None
                else ""
            )
            + "."
        )
    for name in ("half", "double"):
        f = (r.get("fees") or {}).get(name)
        if f:
            lines.append(
                f"At {name} the fee rate: {f['trades']} trades"
                + (f", {_day(f['per_day'])}" if f["per_day"] is not None else "")
                + f", total profit {_money(f['profit'])}."
            )
    if r.get("r2_left_out"):
        lines.append(
            "Too few bars to move its entries to other dates: "
            + ", ".join(r["r2_left_out"])
            + "."
        )
    best = r.get("best_rule")
    if best:
        try:
            rule = catalogue.get(best["key"]).description
        except KeyError:
            rule = best["key"]
        lines.append(
            f"On the hours both cover, against the best rule ({rule}): "
            f"{_day(best['own']['per_day'])} against {_day(best['rule']['per_day'])}."
        )
    dca = r.get("neural_dca")
    if dca:
        lines.append(
            f"With neural DCA on: {dca['score']['trades']} trades"
            + (
                f", {_day(dca['score']['per_day'])}"
                if dca["score"]["per_day"] is not None
                else ""
            )
            + "."
        )
    if r.get("lockbox_seen"):
        lines.append("Its results for the held-back months were looked at before.")
    return "\n".join(lines)


# --- the window ---------------------------------------------------------------------------


class CompareModelsWindow(tk.Toplevel):
    """Compare models... (see the module docstring). ``freeze_fn(coins, start,
    contestants, end=, declared=)`` and ``run_fn(batch_id, progress=, stop=)`` do the
    work (``batch.freeze`` and ``batch.run``; tests give fakes)."""

    def __init__(
        self,
        master: tk.Misc,
        coins: Sequence[str],
        freeze_fn: Optional[Callable[..., str]] = None,
        run_fn: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
    ) -> None:
        super().__init__(master)
        self.title("Compare models")
        self.geometry("1360x900")
        self._freeze_fn = freeze_fn or lab.freeze
        self._run_fn = run_fn or lab.run
        self.coins = [str(c).upper() for c in coins if c]
        self._stop = threading.Event()
        self._progress = ""
        self.running_id: Optional[str] = None
        self.shown_id: Optional[str] = None
        self.shown: Optional[Dict[str, Any]] = None
        last = last_choices() or {}
        chosen = set(last.get("contestants") or catalogue.BATCH_1)
        last_coins = set(last.get("coins") or self.coins)
        self.coin_on = {
            c: tk.BooleanVar(master=self, value=c in last_coins) for c in self.coins
        }
        self.other_var = tk.StringVar(
            master=self,
            value=", ".join(c for c in last.get("coins", []) if c not in self.coins),
        )
        self.start_var = tk.StringVar(
            master=self, value=last.get("start") or DEFAULT_START
        )
        self.model_on = {
            k: tk.BooleanVar(master=self, value=k in chosen)
            for k, _text in contestant_choices()
        }
        self.status_var = tk.StringVar(master=self, value="")
        self.trials_var = tk.StringVar(master=self, value="")
        self.batch_var = tk.StringVar(master=self, value="")
        self.summary_var = tk.StringVar(master=self, value="")
        self.detail_var = tk.StringVar(master=self, value="")
        self._labels: Dict[str, str] = {}
        self.jobs = BackgroundJobs(self, name="model-lab")
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._build()
        self.refresh_batches()

    # -- values ------------------------------------------------------------------------

    def choices(self) -> Tuple[List[str], pd.Timestamp, List[str], Optional[str]]:
        """The batch asked for; ValueError says, in plain words, what is wrong."""
        coins = parse_coins(
            [c for c in self.coins if self.coin_on[c].get()], self.other_var.get()
        )
        if not coins:
            raise ValueError("Choose at least one coin.")
        start = parse_start(self.start_var.get())
        keys, declared = batch_keys(k for k, v in self.model_on.items() if v.get())
        if not any(catalogue.get(k).tested for k in keys):
            raise ValueError("Choose at least one model that is tested.")
        return coins, start, keys, declared

    def tick_declared(self, name: str) -> None:
        members = set(catalogue.DECLARED[name][1])
        for key, var in self.model_on.items():
            var.set(key in members)

    # -- running -------------------------------------------------------------------------

    def start(self) -> bool:
        try:
            coins, start, keys, declared = self.choices()
        except ValueError as exc:
            self.status_var.set(str(exc))
            return False
        self._stop.clear()
        self.run_button.state(["disabled"])
        self.stop_button.state(["!disabled"])
        self.status_var.set("Reading candles and freezing the batch...")
        self._progress = ""
        self.running_id = None

        def progress(stage: str, n: int, total: int) -> None:
            self._progress = f"{STAGES.get(stage, stage)}: {n} of {total}"

        def job():
            batch_id = self._freeze_fn(coins, start, keys, end=END, declared=declared)
            self.running_id = batch_id
            return batch_id, self._run_fn(
                batch_id, progress=progress, stop=self._stop.is_set
            )

        self.jobs.submit(job, self._done, self._failed)
        self.after(200, self._tick)
        return True

    def stop(self) -> None:
        self._stop.set()
        self.status_var.set("Stopping...")

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            self._stop.set()  # a batch left running stops, marked as stopped

    def _tick(self) -> None:
        if not self.jobs.busy:
            return
        if self._progress and not self._stop.is_set():
            self.status_var.set(f"{self._progress}...")
        try:
            self.after(200, self._tick)
        except tk.TclError:
            pass

    def _finish(self) -> None:
        self.run_button.state(["!disabled"])
        self.stop_button.state(["disabled"])

    def _failed(self, exc: BaseException) -> None:
        self._finish()
        self.status_var.set(f"The batch could not run: {exc}")
        self.refresh_batches(self.running_id)

    def _done(self, outcome) -> None:
        self._finish()
        batch_id, results = outcome
        if results is None:
            self.status_var.set(
                "Stopped. The batch keeps its frozen record, marked as stopped."
            )
        else:
            self.status_var.set("Done.")
        self.refresh_batches(batch_id)

    # -- results ---------------------------------------------------------------------------

    def refresh_batches(self, select: Optional[str] = None) -> None:
        ids = list(reversed(lab.batch_ids()))  # the newest first
        self._labels = {batch_label(b): b for b in ids}
        self.batch_combo.configure(values=list(self._labels))
        self.trials_var.set(trials_text(lab.trial_counts()))
        target = select if select in ids else (ids[0] if ids else None)
        if target is None:
            self.batch_var.set("")
            self.show_batch(None)
            return
        self.batch_var.set(next(k for k, v in self._labels.items() if v == target))
        self.show_batch(target)

    def _on_batch(self, _event=None) -> None:
        self.show_batch(self._labels.get(self.batch_var.get()))

    def show_batch(self, batch_id: Optional[str]) -> None:
        tree = self.table.tree
        tree.delete(*tree.get_children())
        self.detail_var.set("")
        self.shown_id, self.shown = batch_id, None
        if batch_id is None:
            self.summary_var.set("No batch has been run yet.")
            self.table.settle()
            return
        try:
            record = lab.read_batch(batch_id)
        except lab.BatchError as exc:
            self.summary_var.set(str(exc))
            self.table.settle()
            return
        results = lab.read_results(batch_id)
        self.shown = results
        self.summary_var.set(summary_text(record, results))
        for key, values in result_rows(results or {}):
            tree.insert("", "end", iid=key, values=values)
        self.table.settle()

    def _on_select(self, _event=None) -> None:
        selected = self.table.tree.selection()
        if not selected or not self.shown:
            self.detail_var.set("")
            return
        r = self.shown["contestants"].get(selected[0])
        self.detail_var.set(detail_text(r) if r else "")

    # -- layout ----------------------------------------------------------------------------

    def _build(self) -> None:
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        r = 0

        def row(label: str, widget: tk.Widget, sticky: str = "w") -> None:
            nonlocal r
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="nw", pady=2)
            widget.grid(row=r, column=1, sticky=sticky, pady=2)
            r += 1

        coins = ttk.Frame(body)
        for c in self.coins:
            ttk.Checkbutton(coins, text=c, variable=self.coin_on[c]).pack(side="left")
        ttk.Label(coins, text="  Other coins:").pack(side="left")
        ttk.Entry(coins, textvariable=self.other_var, width=24).pack(side="left")
        row("Coins:", coins)
        start = ttk.Frame(body)
        ttk.Entry(start, textvariable=self.start_var, width=12).pack(side="left")
        ttk.Label(
            start,
            text=(
                f"  Every batch ends on {END.date().isoformat()}: models are scored to "
                f"{LOCKBOX[0].date().isoformat()}, and the 18 months after it are held "
                "back and not read."
            ),
            style="Muted.TLabel",
        ).pack(side="left")
        row("Start:", start)
        row(
            "Candles:",
            ttk.Label(body, text=CANDLES_TEXT, style="Muted.TLabel", wraplength=WRAP),
        )

        models = ttk.Frame(body)
        buttons = ttk.Frame(models)
        buttons.pack(fill="x")
        for name, text in DECLARED_BUTTONS:
            ttk.Button(
                buttons, text=text, command=lambda n=name: self.tick_declared(n)
            ).pack(side="left", padx=(0, 8))
        box = ttk.Frame(models)
        box.pack(fill="x", pady=(4, 0))
        background = ttk.Style(self).lookup("TFrame", "background") or None
        canvas = tk.Canvas(box, height=200, highlightthickness=0, borderwidth=0)
        if background:
            canvas.configure(background=background)
        bar = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind(
            "<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="x", expand=True)
        bar.pack(side="left", fill="y")

        def wheel(event) -> None:
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

        for key, text in contestant_choices():
            check = ttk.Checkbutton(inner, text=text, variable=self.model_on[key])
            check.pack(anchor="w")
            check.bind("<MouseWheel>", wheel)
        canvas.bind("<MouseWheel>", wheel)
        self.models_canvas = canvas
        row("Models:", models, sticky="ew")

        run = ttk.Frame(body)
        run.grid(row=r, column=0, columnspan=2, sticky="w", pady=(8, 4))
        r += 1
        self.run_button = ttk.Button(run, text="Run", command=self.start)
        self.run_button.pack(side="left")
        self.stop_button = ttk.Button(run, text="Stop", command=self.stop)
        self.stop_button.pack(side="left", padx=8)
        self.stop_button.state(["disabled"])
        ttk.Label(run, textvariable=self.trials_var, style="Muted.TLabel").pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(body, textvariable=self.status_var, wraplength=WRAP).grid(
            row=r, column=0, columnspan=2, sticky="w"
        )
        r += 1

        self.batch_combo = ttk.Combobox(
            body, textvariable=self.batch_var, state="readonly", width=40
        )
        self.batch_combo.bind("<<ComboboxSelected>>", self._on_batch)
        row("Batch:", self.batch_combo)
        ttk.Label(
            body, textvariable=self.summary_var, wraplength=WRAP, justify="left"
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(2, 4))
        r += 1
        self.table = ui_table.DataTable(
            body,
            COLUMNS,
            HEADINGS,
            empty_text="No results",
            numeric=NUMERIC,
            selectmode="browse",
            height=12,
        )
        self.table.grid(row=r, column=0, columnspan=2, sticky="nsew")
        self.table.tree.bind("<<TreeviewSelect>>", self._on_select, add="+")
        body.rowconfigure(r, weight=1)
        r += 1
        ttk.Label(
            body, textvariable=self.detail_var, wraplength=WRAP, justify="left"
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(6, 0))
