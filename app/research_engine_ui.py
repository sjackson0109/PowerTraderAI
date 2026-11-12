"""
Settings > Training, "Research engine...": research jobs run on this computer.

The window shows:
* what the computer has: processor, memory, graphics, model accelerators, free disk;
* the operating mode and its limits;
* the owner's optional energy figures;
* every job in the queue, with its state, progress, attempts, time, memory and
  energy.

Jobs can be paused, resumed, cancelled and retried. A self-test checks the engine
without reading market data.

The engine runs only while this window is open and started. Closing the window asks
running jobs to pause. They go on from their last checkpoint when the engine starts
again.

The words state facts only.
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

import ui_table
from research_engine import preferences, resources
from research_engine.resources import GIB, EnergyModel, Inventory, Limits, limits_for
from research_engine.scheduler import Scheduler
from research_engine.store import Job, JobStore

MIB = 1024**2
WRAP = 620
MODE_NAMES = {
    "max_throughput": "Maximum throughput",
    "balanced": "Balanced",
    "low_resource": "Low resource",
}
KIND_NAMES = {"engine.selftest": "Self-test", "strategy_lab.run": "Strategy backtest"}
STATE_NAMES = {
    "queued": "Queued",
    "running": "Running",
    "paused": "Paused",
    "done": "Done",
    "failed": "Failed",
    "cancelled": "Cancelled",
}
REQUEST_NAMES = {"pause": "Pause asked", "cancel": "Cancel asked"}
PRIORITY_NAMES = {"below_normal": "below normal priority", "idle": "idle priority"}
ACCELERATOR_NAMES = {"cuda": "CUDA", "mps": "Metal (MPS)", "directml": "DirectML"}
COLUMNS = (
    "id",
    "job",
    "state",
    "progress",
    "tries",
    "cpu",
    "wall",
    "memory",
    "energy",
    "note",
)
HEADINGS = {
    "id": "No.",
    "job": "Job",
    "state": "State",
    "progress": "Progress",
    "tries": "Attempts",
    "cpu": "Processor time",
    "wall": "Elapsed",
    "memory": "Peak memory",
    "energy": "Energy (Wh)",
    "note": "Note",
}
SELFTEST_JOBS = 4
ENERGY_TEXT = (
    "Energy is not measured: Windows does not give programs the processor's power. "
    "With the watts one busy core draws, each job's energy is estimated as its "
    "processor time times those watts, and its cost from the price per kWh. Leave "
    "them blank to estimate nothing."
)


def gib(n: int) -> str:
    return f"{n / GIB:.1f} GiB"


def duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f} s"
    if seconds < 3600:
        m, s = divmod(int(round(seconds)), 60)
        return f"{m} min {s:02d} s"
    return f"{seconds / 3600:.2f} h"


def memory_text(n: int) -> str:
    if not n:
        return ""
    return f"{n / MIB:.0f} MiB" if n < GIB else gib(n)


def computer_lines(inv: Inventory) -> List[str]:
    accel = ", ".join(ACCELERATOR_NAMES.get(a, a) for a in inv.accelerators)
    return [
        f"Processor: {inv.cpu_name} ({inv.physical_cores} cores, "
        f"{inv.logical_cores} threads)",
        f"Memory: {gib(inv.memory_total_bytes)}, "
        f"{gib(inv.memory_available_bytes)} available",
        f"Graphics: {', '.join(inv.gpus) or 'none reported'}",
        "Model accelerators: "
        + (accel or "none found, so models run on the processor"),
        f"Free disk: {inv.disk_free_bytes / GIB:,.0f} GiB",
    ]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def limits_text(lim: Limits) -> str:
    return (
        f"{_plural(lim.workers, 'job')} at once, "
        f"{_plural(lim.threads_per_worker, 'thread')} each; keeps "
        f"{gib(lim.memory_reserve_bytes)} of memory free; up to "
        f"{gib(lim.memory_per_job_bytes)} a job; {PRIORITY_NAMES[lim.priority]}."
    )


def _note(job: Job) -> str:
    if job.request:
        return REQUEST_NAMES.get(job.request, job.request)
    if job.state == "failed" and job.error:
        lines = [x.strip() for x in job.error.strip().splitlines() if x.strip()]
        return lines[-1] if lines else ""
    if job.state == "running":
        return job.progress_note or ""
    return ""


def job_row(job: Job, energy: EnergyModel) -> tuple:
    wh = energy.energy_wh(job.cpu_seconds) if job.cpu_seconds else None
    name = KIND_NAMES.get(job.kind, job.kind)
    return (
        job.id,
        f"{name}: {job.label}" if job.label else name,
        STATE_NAMES.get(job.state, job.state),
        f"{round(100 * job.progress)}%" if job.progress is not None else "",
        job.attempts,
        duration(job.cpu_seconds) if job.cpu_seconds else "",
        duration(job.wall_seconds) if job.wall_seconds else "",
        memory_text(job.peak_rss_bytes),
        f"{wh:.3f}" if wh is not None else "—",
        _note(job),
    )


def status_text(summary: dict, energy: EnergyModel, running: bool, note: str) -> str:
    n = summary["by_state"]
    parts = [
        "The engine is running." if running else "The engine is stopped.",
        f"{n['running']} running, {n['queued']} queued, {n['paused']} paused, "
        f"{n['done']} done, {n['failed']} failed, {n['cancelled']} cancelled.",
        f"Processor time: {duration(summary['cpu_seconds'])}.",
    ]
    wh = energy.energy_wh(summary["cpu_seconds"])
    if wh is not None:
        cost = energy.cost(summary["cpu_seconds"])
        parts.append(
            f"Energy, estimated: {wh:.2f} Wh"
            + (f", {cost:.4f} {energy.currency}".rstrip() if cost is not None else "")
            + "."
        )
    if note and running:
        parts.append(note[0].upper() + note[1:] + ".")
    return " ".join(parts)


class ResearchEngineWindow(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        root_dir: Optional[str] = None,
        inventory_fn: Optional[Callable[[], Inventory]] = None,
        refresh_ms: int = 1000,
        available_memory: Optional[Callable[[], int]] = None,
    ):
        super().__init__(master)
        # the kinds the engine can run, registered before any job is started
        from research_engine import selftest, strategy_runs  # noqa: F401

        self.title("Research engine")
        self.geometry("1100x640")
        self.store = JobStore(root_dir)
        self.prefs = preferences.load(self.store.root)
        self.inv = (inventory_fn or (lambda: resources.inventory(self.store.root)))()
        lim = limits_for(self.prefs.mode, self.inv)
        self.scheduler = (
            Scheduler(self.store, lim, available_memory=available_memory)
            if available_memory is not None
            else Scheduler(self.store, lim)
        )
        self.engine_running = False
        self.refresh_ms = int(refresh_ms)
        self._after: Optional[str] = None
        self.message_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    # -- layout --------------------------------------------------------------------------

    def _build(self) -> None:
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="This computer", style="Title.TLabel").pack(anchor="w")
        self.computer_label = ttk.Label(
            body, text="\n".join(computer_lines(self.inv)), justify="left"
        )
        self.computer_label.pack(anchor="w", pady=(2, 8))

        mode_row = ttk.Frame(body)
        mode_row.pack(fill="x")
        ttk.Label(mode_row, text="Mode:").pack(side="left")
        self.mode_var = tk.StringVar(value=MODE_NAMES[self.prefs.mode])
        self.mode_combo = ttk.Combobox(
            mode_row,
            textvariable=self.mode_var,
            values=[MODE_NAMES[m] for m in resources.MODES],
            state="readonly",
            width=20,
        )
        self.mode_combo.pack(side="left", padx=(6, 10))
        self.mode_combo.bind("<<ComboboxSelected>>", self.set_mode)
        self.limits_label = ttk.Label(
            mode_row, text=limits_text(self.scheduler.limits), style="Muted.TLabel"
        )
        self.limits_label.pack(side="left")

        energy_row = ttk.Frame(body)
        energy_row.pack(fill="x", pady=(8, 0))
        self.watts_var = tk.StringVar(value=_shown(self.prefs.watts_per_busy_core))
        self.tariff_var = tk.StringVar(value=_shown(self.prefs.tariff_per_kwh))
        self.currency_var = tk.StringVar(value=self.prefs.currency)
        for text, var, width in (
            ("Watts per busy core:", self.watts_var, 8),
            ("Price per kWh:", self.tariff_var, 8),
            ("Currency:", self.currency_var, 6),
        ):
            ttk.Label(energy_row, text=text).pack(side="left")
            ttk.Entry(energy_row, textvariable=var, width=width).pack(
                side="left", padx=(4, 12)
            )
        ttk.Button(energy_row, text="Save", command=self.save_energy).pack(side="left")
        ttk.Label(
            body,
            text=ENERGY_TEXT,
            style="Muted.TLabel",
            wraplength=WRAP,
            justify="left",
        ).pack(anchor="w", pady=(2, 8))

        buttons = ttk.Frame(body)
        buttons.pack(fill="x")
        self.start_button = ttk.Button(buttons, text="Start", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop)
        self.stop_button.pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Run a self-test", command=self.run_selftest).pack(
            side="left", padx=(18, 0)
        )

        self.table = ui_table.DataTable(
            body,
            COLUMNS,
            HEADINGS,
            empty_text="No jobs yet",
            numeric=("id", "tries"),
            height=12,
            selectmode="browse",
        )
        self.table.pack(fill="both", expand=True, pady=(8, 0))

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(6, 0))
        for text, fn in (
            ("Pause", self.store.pause),
            ("Resume", self.store.resume),
            ("Cancel", self.store.cancel),
            ("Retry", self.store.retry),
        ):
            ttk.Button(
                actions, text=text, command=lambda fn=fn: self._on_selected(fn)
            ).pack(side="left", padx=(0, 6))
        ttk.Label(actions, textvariable=self.message_var, style="Muted.TLabel").pack(
            side="left", padx=(12, 0)
        )
        ttk.Label(
            body, textvariable=self.status_var, wraplength=1000, justify="left"
        ).pack(anchor="w", pady=(6, 0))

    # -- the engine ----------------------------------------------------------------------

    def start(self) -> None:
        self.scheduler.start()
        self.engine_running = True
        self.refresh()

    def stop(self) -> None:
        """Ask running jobs to pause, off the Tk thread (it can take a few seconds)."""
        self.engine_running = False
        threading.Thread(
            target=self.scheduler.stop, name="research-engine-stop", daemon=True
        ).start()
        self.refresh()

    def run_selftest(self) -> List[int]:
        """Queue a few self-test jobs (new ones each time: they carry the time)."""
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        ids = []
        for n in range(SELFTEST_JOBS):
            job, _ = self.scheduler.submit(
                "engine.selftest",
                {"steps": 5, "sleep": 0.2, "queued_at": stamp, "n": n},
                seed=n,
                label=f"{n + 1} of {SELFTEST_JOBS}",
            )
            ids.append(job.id)
        self.message_var.set(f"{SELFTEST_JOBS} self-test jobs queued.")
        self.refresh()
        return ids

    def set_mode(self, _event=None) -> None:
        mode = next(m for m, name in MODE_NAMES.items() if name == self.mode_var.get())
        self.prefs = preferences.checked(
            mode,
            self.prefs.watts_per_busy_core,
            self.prefs.tariff_per_kwh,
            self.prefs.currency,
        )
        preferences.save(self.store.root, self.prefs)
        self.scheduler.limits = limits_for(mode, self.inv)
        self.limits_label.configure(text=limits_text(self.scheduler.limits))

    def save_energy(self) -> bool:
        bad = [
            name
            for name, var in (
                ("watts per busy core", self.watts_var),
                ("price per kWh", self.tariff_var),
            )
            if var.get().strip() and preferences._figure(var.get()) is None
        ]
        if bad:
            self.message_var.set(f"Enter the {' and '.join(bad)} as a number above 0.")
            return False
        self.prefs = preferences.checked(
            self.prefs.mode,
            self.watts_var.get(),
            self.tariff_var.get(),
            self.currency_var.get(),
        )
        preferences.save(self.store.root, self.prefs)
        self.message_var.set("Energy figures saved.")
        self.refresh()
        return True

    def selected_job(self) -> Optional[int]:
        sel = self.table.tree.selection()
        return int(sel[0]) if sel else None

    def _on_selected(self, fn: Callable[[int], str]) -> None:
        job_id = self.selected_job()
        if job_id is None:
            self.message_var.set("Select a job first.")
            return
        state = fn(job_id)
        self.message_var.set(f"Job {job_id}: {STATE_NAMES.get(state, state).lower()}.")
        self.refresh()

    # -- showing -------------------------------------------------------------------------

    def rows(self) -> List[tuple]:
        energy = self.prefs.energy()
        return [job_row(j, energy) for j in self.store.jobs()]

    def refresh(self) -> None:
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        tree = self.table.tree
        rows = self.rows()
        keep = {str(r[0]) for r in rows}
        for iid in tree.get_children():
            if iid not in keep:
                tree.delete(iid)
        for row in rows:
            iid = str(row[0])
            if tree.exists(iid):
                tree.item(iid, values=row)
            else:
                tree.insert("", "end", iid=iid, values=row)
        note = self.scheduler.notes[-1] if self.scheduler.notes else ""
        self.status_var.set(
            status_text(
                self.store.summary(), self.prefs.energy(), self.engine_running, note
            )
        )
        self.start_button.state(["disabled"] if self.engine_running else ["!disabled"])
        self.stop_button.state(["!disabled"] if self.engine_running else ["disabled"])
        if self.refresh_ms > 0:
            self._after = self.after(self.refresh_ms, self.refresh)

    def close(self) -> None:
        """Close the window; running jobs are asked to pause (off the Tk thread)."""
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        if self.engine_running:
            self.engine_running = False
            threading.Thread(
                target=self.scheduler.stop, name="research-engine-stop", daemon=True
            ).start()
        self.destroy()


def _shown(value: Optional[float]) -> str:
    return "" if value is None else f"{value:g}"
