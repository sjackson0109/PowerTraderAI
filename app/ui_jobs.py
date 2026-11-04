"""
Slow work (an LLM answer, a model list, a connection test) off the Tk thread.

``BackgroundJobs(widget)`` runs the callables given to ``submit`` one at a time on a
worker thread and calls their ``on_done(result)`` (or ``on_error(exc)``) back on the
Tk thread, from a queue the widget polls: no Tk call is ever made from the worker.
The thread starts with the first job and stops when ``widget`` is destroyed (or on
``stop()``): a job already running finishes, its result is dropped, and queued jobs
never start.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from typing import Any, Callable, Optional

POLL_MS = 100


class BackgroundJobs:
    def __init__(self, widget: tk.Misc, name: str = "ui-jobs", poll_ms: int = POLL_MS):
        self.widget = widget
        self.name = name
        self.poll_ms = poll_ms
        self.thread: Optional[threading.Thread] = None
        self._jobs: "queue.Queue[Any]" = queue.Queue()
        self._results: "queue.Queue[Any]" = queue.Queue()
        self._stopped = threading.Event()
        self._after: Optional[str] = None
        self._pending = 0
        widget.bind("<Destroy>", self._on_destroy, add="+")

    # ---- the Tk side ----

    def submit(
        self,
        job: Callable[[], Any],
        on_done: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[BaseException], None]] = None,
    ) -> bool:
        """Queue ``job``; False once stopped."""
        if self._stopped.is_set():
            return False
        if self.thread is None:
            self.thread = threading.Thread(
                target=self._work, name=self.name, daemon=True
            )
            self.thread.start()
        self._pending += 1
        self._jobs.put((job, on_done, on_error))
        self._schedule()
        return True

    @property
    def busy(self) -> bool:
        return self._pending > 0

    def _schedule(self) -> None:
        if self._after is None and not self._stopped.is_set():
            try:
                self._after = self.widget.after(self.poll_ms, self._poll)
            except tk.TclError:
                self._after = None

    def _poll(self) -> None:
        self._after = None
        if self._stopped.is_set():
            return
        while True:
            try:
                callback, value = self._results.get_nowait()
            except queue.Empty:
                break
            self._pending = max(0, self._pending - 1)
            if callback is not None:
                try:
                    callback(value)
                except tk.TclError:
                    pass  # the widget went while the job ran
        if self._pending:
            self._schedule()

    def drain(self, timeout: float = 5.0) -> None:
        """Wait for the queued jobs and run their callbacks now (tests)."""
        import time

        end = time.monotonic() + timeout
        while self._pending and time.monotonic() < end:
            try:
                callback, value = self._results.get(timeout=0.05)
            except queue.Empty:
                continue
            self._pending = max(0, self._pending - 1)
            if callback is not None:
                callback(value)

    def _on_destroy(self, event) -> None:
        if event.widget is self.widget:
            self.stop()

    def stop(self) -> None:
        """No more jobs: the worker ends after the one running (if any)."""
        if self._stopped.is_set():
            return
        self._stopped.set()
        self._jobs.put(None)
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    # ---- the worker ----

    def _work(self) -> None:
        while not self._stopped.is_set():
            item = self._jobs.get()
            if item is None or self._stopped.is_set():
                return
            job, on_done, on_error = item
            try:
                result = job()
            except Exception as exc:  # handed back to the Tk side
                self._results.put((on_error, exc))
            else:
                self._results.put((on_done, result))
