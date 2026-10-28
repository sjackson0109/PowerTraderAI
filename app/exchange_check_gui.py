"""Settings > Check Exchanges: run the live exchange check (``exchange_check``) from
the hub and show each result as it arrives.

The user picks the exchanges (those enabled in Settings, primary first), the coins
(the hub's coins) and whether to include the read-only API key check. The checks
run on a worker thread; results reach the window through a queue it drains on the
Tk thread.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Iterable, List, Optional

import exchange_check
import ui_tokens

TITLE = "Check Exchanges"
MARKS = {True: "PASS", False: "FAIL", None: "n/a"}
_DONE = object()
COIN_COLUMNS = 6


class ExchangeCheckWindow(tk.Toplevel):
    """``exchanges``: the enabled exchanges, primary first (the first is labelled
    primary when ``primary`` names it). ``coins``: the hub's coins. ``runner`` has
    ``exchange_check.check``'s signature (tests pass a fake)."""

    def __init__(
        self,
        parent: tk.Misc,
        exchanges: Iterable[str],
        coins: Iterable[str],
        primary: Optional[str] = None,
        palette: Optional[dict] = None,
        runner: Callable = exchange_check.check,
    ) -> None:
        super().__init__(parent)
        self.title(TITLE)
        self._runner = runner
        self._queue: "queue.Queue" = queue.Queue()
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self.results: List[exchange_check.Result] = []
        self.exchange_vars: Dict[str, tk.BooleanVar] = {}
        self.coin_vars: Dict[str, tk.BooleanVar] = {}
        self.auth_var = tk.BooleanVar(master=self, value=False)
        self.status_var = tk.StringVar(master=self)
        if palette and palette.get("BG"):
            self.configure(bg=palette["BG"])
        try:
            self._build(list(exchanges), list(coins), primary)
        except Exception:
            self.destroy()  # never leave a half-built window behind
            raise
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.transient(parent)

    # -- layout --
    def _build(self, exchanges: List[str], coins: List[str], primary) -> None:
        body = ttk.Frame(self, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(5, weight=1)

        ttk.Label(body, text=TITLE, font=ui_tokens.font("body", "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            body,
            text="Reads each exchange's market status, prices, hourly candles and "
            "minimum order now. No order is placed.",
            wraplength=640,
        ).grid(row=1, column=0, sticky="w", pady=(4, 10))

        ex_frame = ttk.LabelFrame(body, text="Exchanges", padding=8)
        ex_frame.grid(row=2, column=0, sticky="ew")
        if not exchanges:
            ttk.Label(
                ex_frame,
                text="No exchange is enabled. Enable one in Configure Exchange APIs.",
            ).grid(row=0, column=0, sticky="w")
        for i, name in enumerate(exchanges):
            var = tk.BooleanVar(master=self, value=True)
            self.exchange_vars[name] = var
            label = f"{name} (primary)" if name == primary else name
            ttk.Checkbutton(ex_frame, text=label, variable=var).grid(
                row=0, column=i, sticky="w", padx=(0, 14)
            )

        coin_frame = ttk.LabelFrame(body, text="Coins", padding=8)
        coin_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        for i, coin in enumerate(coins):
            var = tk.BooleanVar(master=self, value=True)
            self.coin_vars[coin] = var
            ttk.Checkbutton(coin_frame, text=coin, variable=var).grid(
                row=i // COIN_COLUMNS, column=i % COIN_COLUMNS, sticky="w", padx=(0, 14)
            )

        controls = ttk.Frame(body)
        controls.grid(row=4, column=0, sticky="ew", pady=(8, 8))
        ttk.Checkbutton(
            controls,
            text="Also check the saved API keys (read-only)",
            variable=self.auth_var,
        ).grid(row=0, column=0, sticky="w")
        controls.columnconfigure(1, weight=1)
        self.run_button = ttk.Button(controls, text="Run check", command=self.run)
        self.run_button.grid(row=0, column=2, padx=(8, 0))
        self.stop_button = ttk.Button(
            controls, text="Stop", command=self.stop, state="disabled"
        )
        self.stop_button.grid(row=0, column=3, padx=(8, 0))
        ttk.Button(controls, text="Close", command=self.close).grid(
            row=0, column=4, padx=(8, 0)
        )

        table = ttk.Frame(body)
        table.grid(row=5, column=0, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            table,
            columns=("exchange", "check", "result", "detail"),
            show="headings",
            height=14,
        )
        for col, text, width, stretch in (
            ("exchange", "Exchange", 90, False),
            ("check", "Check", 110, False),
            ("result", "Result", 60, False),
            ("detail", "Detail", 360, True),
        ):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, stretch=stretch, anchor="w")
        self.tree.tag_configure("pass", foreground=ui_tokens.STATUS["good"])
        self.tree.tag_configure("fail", foreground=ui_tokens.STATUS["bad"])
        self.tree.tag_configure("na", foreground=ui_tokens.STATUS["warn"])
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        ttk.Label(body, textvariable=self.status_var).grid(
            row=6, column=0, sticky="w", pady=(8, 0)
        )

    # -- the run --
    def selected_exchanges(self) -> List[str]:
        return [name for name, var in self.exchange_vars.items() if var.get()]

    def selected_coins(self) -> List[str]:
        return [coin for coin, var in self.coin_vars.items() if var.get()]

    def run(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        names, coins = self.selected_exchanges(), self.selected_coins()
        if not names:
            self.status_var.set("Choose at least one exchange.")
            return
        self.tree.delete(*self.tree.get_children())
        self.results = []
        self._stop.clear()
        auth = bool(self.auth_var.get())
        self.status_var.set(f"Checking {', '.join(names)}...")
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

        def work() -> None:
            try:
                self._runner(
                    names,
                    coins,
                    auth=auth,
                    report=self._queue.put,
                    stopped=self._stop.is_set,
                )
            except Exception as exc:  # shown in the window, never lost on the thread
                self._queue.put(
                    exchange_check.Result("", "check", False, f"stopped: {exc}")
                )
            finally:
                self._queue.put(_DONE)

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()
        self.after(100, self._poll)

    def stop(self) -> None:
        """Stop after the exchange being checked."""
        self._stop.set()
        self.status_var.set("Stopping after the current exchange...")

    def close(self) -> None:
        self._stop.set()
        self.destroy()

    def _poll(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if not self.drain():
            self.after(100, self._poll)

    def drain(self) -> bool:
        """Show every result waiting in the queue; True once the run has ended."""
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return False
            if item is _DONE:
                self._finished()
                return True
            self._show(item)

    def _show(self, result: "exchange_check.Result") -> None:
        self.results.append(result)
        tag = {True: "pass", False: "fail", None: "na"}[result.ok]
        row = self.tree.insert(
            "",
            "end",
            values=(result.exchange, result.check, MARKS[result.ok], result.detail),
            tags=(tag,),
        )
        self.tree.see(row)

    def _finished(self) -> None:
        passed = sum(r.ok is True for r in self.results)
        failed = sum(r.ok is False for r in self.results)
        other = sum(r.ok is None for r in self.results)
        text = f"{passed} passed, {failed} failed"
        if other:
            text += f", {other} not applicable"
        if self._stop.is_set():
            text += " (stopped)"
        self.status_var.set(text)
        self.run_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
