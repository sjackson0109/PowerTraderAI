"""
Settings > Strategy, "Run a backtest..." and "Compare results..." (FDS-SR-001 section
5.8).

**Run a backtest...** One strategy that is enabled for research, with its parameters
(bounded as in the catalogue), stops and filters that are enabled for research, a
timeframe, coins from Settings, a period inside the development period (to 2025-05-06),
an account in pounds with the GBP-to-USD rate, the fee and the slippage. It runs off the
Tk thread (``ui_jobs``), can be stopped, and shows the strategy against buy-and-hold,
cash and random entries, per coin, with its equity line. Each run is logged as an
exploratory run and saved (``strategy_lab.runs``).

**Compare results...** Every saved run in one table, with a search box.

The words state facts only.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional, Sequence

import ui_table
from strategies import descriptions as words
from strategies.catalogue import CATALOGUE, ParamError, resolve_params
from strategies.settings import read_research_enabled
from strategy_lab import runs
from strategy_lab.simulate import ACCOUNTS_GBP
from strategy_lab.windows import DEVELOPMENT, ReservedPeriod, development_only
from ui_jobs import BackgroundJobs

WRAP = 560
SUMMARY_COLUMNS = ("what", "net", "rpcd", "drawdown", "trades", "in_market")
SUMMARY_HEADINGS = {
    "what": "",
    "net": "Net ($)",
    "rpcd": "Return per capital-day",
    "drawdown": "Max drawdown",
    "trades": "Trades",
    "in_market": "Time in market",
}
COMPARE_COLUMNS = (
    "when",
    "strategy",
    "candles",
    "coins",
    "period",
    "account",
    "net",
    "rpcd",
    "drawdown",
    "trades",
    "random",
)
COMPARE_HEADINGS = {
    "when": "Run",
    "strategy": "Strategy",
    "candles": "Candles",
    "coins": "Coins",
    "period": "Period",
    "account": "Account",
    "net": "Net ($)",
    "rpcd": "Return per capital-day",
    "drawdown": "Max drawdown",
    "trades": "Trades",
    "random": "Random draws at or above",
}


def research_strategies(settings: Any) -> List[str]:
    """The main strategies enabled for research, in catalogue order (not one that needs
    a trained model)."""
    enabled = set(read_research_enabled(settings))
    return [
        sid
        for sid, e in CATALOGUE.items()
        if e["class_type"] == "main" and e["family"] != "model" and sid in enabled
    ]


def research_overlays(settings: Any) -> List[str]:
    enabled = set(read_research_enabled(settings))
    return [
        sid
        for sid, e in CATALOGUE.items()
        if e["class_type"] == "risk_overlay" and sid in enabled
    ]


def _pct(x: Optional[float], digits: int = 2) -> str:
    return "" if x is None else f"{x * 100:.{digits}f}%"


def _money(x: Optional[float]) -> str:
    return "" if x is None else f"{x:,.2f}"


def summary_rows(record: Dict[str, Any]) -> List[tuple]:
    """The results table: the strategy, buy-and-hold, cash and random entries."""
    s, h = record["strategy_result"], record["buy_and_hold"]
    rows = [
        (
            "This strategy",
            _money(s["net_usd"]),
            _pct(s["return_per_capital_day"], 3),
            _pct(s["max_drawdown"]),
            s["trades"],
            _pct(s["time_in_market"], 1),
        ),
        (
            "Buy and hold",
            _money(h["net_usd"]),
            _pct(h["return_per_capital_day"], 3),
            _pct(h["max_drawdown"]),
            h["trades"],
            _pct(h["time_in_market"], 1),
        ),
        ("Cash", _money(0.0), _pct(0.0, 3), _pct(0.0), 0, _pct(0.0, 1)),
    ]
    r = record.get("random_entries")
    if r:
        rows.append(
            (
                f"Random entries (median of {r['draws']})",
                _money(r["median_net_usd"]),
                _pct(r["median_return_per_capital_day"], 3),
                "",
                "",
                "",
            )
        )
    return rows


def notes(record: Dict[str, Any]) -> str:
    """The facts under the table."""
    s = record["strategy_result"]
    lines = [
        f"Account: ${record['account_usd']:,.2f} "
        f"(£{record['config']['account_gbp']:,.2f} at {record['config']['gbp_usd']}).",
        f"Entries skipped for cash: {s['skipped_cash']}; below the minimum: "
        f"{s['skipped_minimum']}; in a cooldown: {s['skipped_cooldown']}.",
    ]
    if s["unsold_remainder_usd"]:
        lines.append(
            f"Unsold remainders of sells, held at the end: "
            f"${s['unsold_remainder_usd']:,.2f}."
        )
    if s["halt_reached"]:
        lines.append(
            f"The drawdown halt level was first reached on {s['halt_reached'][:10]}, "
            f"with ${s['halt_exposure_usd']:,.2f} in open positions. A halted trader "
            "manages nothing."
        )
    r = record.get("random_entries")
    if r:
        lines.append(
            f"Random draws with a return per capital-day at or above this strategy's: "
            f"{_pct(r['share_at_or_above'], 1)}."
        )
    unknown = record.get("venue", {}).get("unknown") or {}
    if unknown:
        lines.append(
            "Not known, so not applied: "
            + "; ".join(f"{c} {what}" for c, what in sorted(unknown.items()))
            + "."
        )
    lines.append("Logged as an exploratory run.")
    return "\n".join(lines)


def compare_row(record: Dict[str, Any]) -> tuple:
    c, s = record["config"], record["strategy_result"]
    r = record.get("random_entries") or {}
    return (
        record["ran_at"][:16].replace("T", " "),
        words.name_of(c["strategy_id"]),
        words.timeframe_name(c["timeframe"]),
        ", ".join(c["coins"]),
        f"{record['period'][0][:10]} to {record['period'][1][:10]}",
        f"£{c['account_gbp']:,.0f}",
        _money(s["net_usd"]),
        _pct(s["return_per_capital_day"], 3),
        _pct(s["max_drawdown"]),
        s["trades"],
        _pct(r.get("share_at_or_above"), 1) if r else "",
    )


class BacktestWindow(tk.Toplevel):
    """Run a backtest... (see the module docstring). ``run_fn(config, stop=,
    progress=)`` does the work (``strategy_lab.runs.run``; tests give a fake)."""

    def __init__(
        self,
        master: tk.Misc,
        settings: Any,
        coins: Sequence[str],
        run_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    ) -> None:
        super().__init__(master)
        self.title("Run a backtest")
        self.geometry("860x820")
        self._run_fn = run_fn or runs.run
        self.strategies = research_strategies(settings)
        self.overlays = research_overlays(settings)
        self.coins = list(coins)
        self.result: Optional[Dict[str, Any]] = None
        self._stop = threading.Event()
        self._progress = ""
        first = self.strategies[0] if self.strategies else None
        self.strategy_var = tk.StringVar(
            master=self, value=words.name_of(first) if first else ""
        )
        self.timeframe_var = tk.StringVar(
            master=self,
            value=(
                words.timeframe_name(CATALOGUE[first]["timeframe_primary"])
                if first
                else ""
            ),
        )
        self.start_var = tk.StringVar(
            master=self, value=DEVELOPMENT[0].date().isoformat()
        )
        self.end_var = tk.StringVar(
            master=self, value=DEVELOPMENT[1].date().isoformat()
        )
        self.account_var = tk.StringVar(master=self, value=f"{ACCOUNTS_GBP[-1]:,.0f}")
        self.rate_var = tk.StringVar(master=self, value="")
        self.fee_var = tk.StringVar(master=self, value="0.50")
        self.slippage_var = tk.StringVar(master=self, value="0.05")
        self.draws_var = tk.StringVar(master=self, value="200")
        self.status_var = tk.StringVar(master=self, value="")
        self.notes_var = tk.StringVar(master=self, value="")
        self.coin_on = {c: tk.BooleanVar(master=self, value=True) for c in self.coins}
        self.overlay_on = {
            o: tk.BooleanVar(master=self, value=False) for o in self.overlays
        }
        self.param_vars: Dict[str, tk.StringVar] = {}
        self.jobs = BackgroundJobs(self, name="strategy-backtest")
        self._build()
        self.strategy_var.trace_add("write", lambda *_: self._show_params())
        self._show_params()

    # -- values ------------------------------------------------------------------------

    def selected_strategy(self) -> Optional[str]:
        for sid in self.strategies:
            if words.name_of(sid) == self.strategy_var.get():
                return sid
        return None

    def selected_timeframe(self) -> Optional[str]:
        for tf in words.timeframes():
            if words.timeframe_name(tf) == self.timeframe_var.get():
                return tf
        return None

    def config(self) -> runs.RunConfig:
        """The run asked for; ValueError says, in plain words, what is wrong."""
        sid = self.selected_strategy()
        if sid is None:
            raise ValueError("Choose a strategy that is enabled for research.")
        tf = self.selected_timeframe()
        if tf is None:
            raise ValueError("Choose the candles.")
        params: Dict[str, Any] = {}
        entry = CATALOGUE[sid]
        for name, var in self.param_vars.items():
            spec = entry["param_bounds"][name]
            default = entry["default_params"][name]
            text = var.get().strip()
            if "values" in spec:
                params[name] = next(
                    (v for v in spec["values"] if str(v) == text), default
                )
                continue
            try:
                number = float(text)
            except ValueError:
                raise ValueError(
                    f"{words.DESCRIPTIONS[sid].params[name].label} must be a number."
                ) from None
            is_whole = isinstance(default, int) and not isinstance(default, bool)
            params[name] = int(number) if is_whole and number.is_integer() else number
        try:
            resolve_params(sid, params)
        except ParamError as exc:
            raise ValueError(str(exc)) from None
        problem = words.rule_problem(sid, {**entry["default_params"], **params})
        if problem:
            raise ValueError(problem)
        coins = [c for c in self.coins if self.coin_on[c].get()]
        if not coins:
            raise ValueError("Choose at least one coin.")
        try:
            development_only(self.start_var.get(), self.end_var.get())
        except ReservedPeriod:
            raise ValueError(
                f"Backtests here end by {DEVELOPMENT[1].date().isoformat()}: the "
                "months after it are kept for later checks."
            ) from None
        except (ValueError, TypeError):
            raise ValueError(
                "Give the period as two dates, YYYY-MM-DD, the first before the second."
            ) from None
        try:
            account = float(self.account_var.get().replace(",", "").replace("£", ""))
            rate = float(self.rate_var.get())
            fee = float(self.fee_var.get()) / 100.0
            slippage = float(self.slippage_var.get()) / 100.0
            draws = int(self.draws_var.get())
        except ValueError:
            raise ValueError(
                "The account, the GBP-to-USD rate, the fee, the slippage and the "
                "random draws must be numbers."
            ) from None
        if not rate > 0:
            raise ValueError("Give the GBP-to-USD rate to convert the account.")
        if account <= 0 or not 0 <= fee < 0.1 or not 0 <= slippage < 0.1:
            raise ValueError(
                "The account must be above 0, the fee and slippage below 10%."
            )
        if not 0 <= draws <= 10_000:
            raise ValueError("The random draws must be from 0 to 10,000.")
        return runs.RunConfig(
            strategy_id=sid,
            params=params,
            overlays=[{"id": o} for o in self.overlays if self.overlay_on[o].get()],
            timeframe=tf,
            coins=coins,
            start=self.start_var.get(),
            end=self.end_var.get(),
            account_gbp=account,
            gbp_usd=rate,
            fee=fee,
            allowance=slippage,
            draws=draws,
        )

    # -- running -------------------------------------------------------------------------

    def start(self) -> bool:
        try:
            config = self.config()
        except ValueError as exc:
            self.status_var.set(str(exc))
            return False
        self._stop.clear()
        self.run_button.state(["disabled"])
        self.stop_button.state(["!disabled"])
        self.status_var.set("Running...")
        self._progress = ""

        def progress(message: str) -> None:
            self._progress = message  # read by the Tk thread in _tick

        self.jobs.submit(
            lambda: self._run_fn(config, stop=self._stop, progress=progress),
            self._done,
            self._failed,
        )
        self.after(200, self._tick)
        return True

    def stop(self) -> None:
        self._stop.set()
        self.status_var.set("Stopping...")

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
        if isinstance(exc, runs.Stopped):
            self.status_var.set("Stopped. Nothing was saved.")
        else:
            self.status_var.set(f"The backtest could not run: {exc}")

    def _done(self, record: Dict[str, Any]) -> None:
        self._finish()
        self.result = record
        tree = self.summary.tree
        tree.delete(*tree.get_children())
        for row in summary_rows(record):
            tree.insert("", "end", values=row)
        tree = self.per_coin.tree
        tree.delete(*tree.get_children())
        for coin, row in sorted(record["per_coin"].items()):
            tree.insert("", "end", values=(coin, row["trades"], _money(row["net_usd"])))
        self.notes_var.set(notes(record))
        self._draw_curve(record.get("curve") or [])
        self.status_var.set("Done.")

    # -- layout ----------------------------------------------------------------------------

    def _build(self) -> None:
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        r = 0

        def row(label: str, widget: tk.Widget) -> None:
            nonlocal r
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=2)
            widget.grid(row=r, column=1, sticky="w", pady=2)
            r += 1

        if not self.strategies:
            ttk.Label(
                body,
                text="No strategy is enabled for research. Tick one in Settings > Strategy.",
                wraplength=WRAP,
            ).grid(row=r, column=0, columnspan=2, sticky="w")
            r += 1
        self.strategy_combo = ttk.Combobox(
            body,
            textvariable=self.strategy_var,
            values=[words.name_of(s) for s in self.strategies],
            state="readonly",
            width=36,
        )
        row("Strategy:", self.strategy_combo)
        self.params_frame = ttk.Frame(body)
        self.params_frame.grid(row=r, column=1, sticky="w")
        r += 1
        row(
            "Candles:",
            ttk.Combobox(
                body,
                textvariable=self.timeframe_var,
                values=[words.timeframe_name(tf) for tf in words.timeframes()],
                state="readonly",
                width=14,
            ),
        )
        stops = ttk.Frame(body)
        for o in self.overlays:
            ttk.Checkbutton(
                stops, text=words.name_of(o), variable=self.overlay_on[o]
            ).pack(side="left", padx=(0, 8))
        row("Stops and filters:", stops)
        coins = ttk.Frame(body)
        for c in self.coins:
            ttk.Checkbutton(coins, text=c, variable=self.coin_on[c]).pack(side="left")
        row("Coins:", coins)
        period = ttk.Frame(body)
        ttk.Entry(period, textvariable=self.start_var, width=12).pack(side="left")
        ttk.Label(period, text=" to ").pack(side="left")
        ttk.Entry(period, textvariable=self.end_var, width=12).pack(side="left")
        row("Period:", period)
        account = ttk.Frame(body)
        ttk.Combobox(
            account,
            textvariable=self.account_var,
            values=[f"{a:,.0f}" for a in ACCOUNTS_GBP],
            width=10,
        ).pack(side="left")
        ttk.Label(account, text="  GBP-to-USD rate:").pack(side="left")
        ttk.Entry(account, textvariable=self.rate_var, width=8).pack(side="left")
        row("Account (£):", account)
        costs = ttk.Frame(body)
        ttk.Entry(costs, textvariable=self.fee_var, width=6).pack(side="left")
        ttk.Label(costs, text=" % a side; slippage ").pack(side="left")
        ttk.Entry(costs, textvariable=self.slippage_var, width=6).pack(side="left")
        ttk.Label(costs, text=" %; random draws ").pack(side="left")
        ttk.Entry(costs, textvariable=self.draws_var, width=6).pack(side="left")
        row("Fee:", costs)

        buttons = ttk.Frame(body)
        buttons.grid(row=r, column=0, columnspan=2, sticky="w", pady=(8, 4))
        r += 1
        self.run_button = ttk.Button(buttons, text="Run", command=self.start)
        self.run_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop)
        self.stop_button.pack(side="left", padx=8)
        self.stop_button.state(["disabled"])
        if not self.strategies:
            self.run_button.state(["disabled"])
        ttk.Label(body, textvariable=self.status_var, wraplength=WRAP).grid(
            row=r, column=0, columnspan=2, sticky="w"
        )
        r += 1
        self.summary = ui_table.DataTable(
            body,
            SUMMARY_COLUMNS,
            SUMMARY_HEADINGS,
            empty_text="No result yet",
            sortable=False,
            height=4,
        )
        self.summary.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        r += 1
        self.per_coin = ui_table.DataTable(
            body,
            ("coin", "trades", "net"),
            {"coin": "Coin", "trades": "Trades", "net": "Net ($)"},
            empty_text="No result yet",
            numeric=("trades", "net"),
            height=4,
        )
        self.per_coin.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        r += 1
        ttk.Label(
            body, textvariable=self.notes_var, wraplength=WRAP, justify="left"
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(6, 0))
        r += 1
        self.canvas = tk.Canvas(body, height=140, highlightthickness=0)
        self.canvas.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    def _show_params(self) -> None:
        for child in self.params_frame.winfo_children():
            child.destroy()
        self.param_vars = {}
        sid = self.selected_strategy()
        if sid is None:
            return
        entry = CATALOGUE[sid]
        described = words.DESCRIPTIONS.get(sid)
        for i, (name, spec) in enumerate(entry["param_bounds"].items()):
            default = entry["default_params"][name]
            var = tk.StringVar(master=self, value=str(default))
            self.param_vars[name] = var
            label = described.params[name].label if described else name
            ttk.Label(self.params_frame, text=f"{label}:").grid(
                row=i, column=0, sticky="w", padx=(0, 6)
            )
            if "values" in spec:
                field = ttk.Combobox(
                    self.params_frame,
                    textvariable=var,
                    values=[str(v) for v in spec["values"]],
                    state="readonly",
                    width=10,
                )
                hint = f"default {default}"
            else:
                field = ttk.Spinbox(
                    self.params_frame,
                    textvariable=var,
                    from_=spec.get("min", 0),
                    to=spec.get("max", 1e9),
                    width=8,
                )
                hint = f"{spec.get('min')} to {spec.get('max')}, default {default}"
            field.grid(row=i, column=1, sticky="w")
            ttk.Label(self.params_frame, text=hint, style="Muted.TLabel").grid(
                row=i, column=2, sticky="w", padx=(6, 0)
            )
        self.timeframe_var.set(words.timeframe_name(entry["timeframe_primary"]))

    def _draw_curve(self, points: List[List[float]]) -> None:
        c = self.canvas
        c.delete("all")
        if len(points) < 2:
            return
        c.update_idletasks()
        width = max(c.winfo_width(), 400)
        height = int(c.cget("height"))
        values = [p[1] for p in points]
        lo, hi = min(values), max(values)
        span = (hi - lo) or 1.0
        xy = []
        for k, v in enumerate(values):
            xy += [
                4 + (width - 8) * k / (len(values) - 1),
                height - 4 - (height - 8) * (v - lo) / span,
            ]
        c.create_line(*xy, width=1.5)


class CompareWindow(tk.Toplevel):
    """Compare results...: every saved run, with a search box."""

    def __init__(
        self, master: tk.Misc, list_fn: Optional[Callable[[], List[dict]]] = None
    ):
        super().__init__(master)
        self.title("Compare results")
        self.geometry("1100x480")
        self._list_fn = list_fn or runs.list_runs
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        bar = ttk.Frame(body)
        bar.pack(fill="x")
        self.search = ui_table.SearchBox(bar, self.refresh)
        self.table = ui_table.DataTable(
            body,
            COMPARE_COLUMNS,
            COMPARE_HEADINGS,
            empty_text="No backtests yet",
            numeric=("net", "rpcd", "drawdown", "trades", "random"),
            height=14,
        )
        self.table.pack(fill="both", expand=True, pady=(8, 0))
        self.refresh()

    def refresh(self) -> None:
        tree = self.table.tree
        tree.delete(*tree.get_children())
        for record in self._list_fn():
            row = compare_row(record)
            if self.search.matches(row):
                tree.insert("", "end", values=row)
