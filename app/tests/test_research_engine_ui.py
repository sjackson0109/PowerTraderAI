"""PTAI-RD-001 M5: Settings > Training, "Research engine...".

* The window shows the computer as the inventory reports it, the mode's limits, and
  every job in the queue.
* The mode and the energy figures are saved beside the queue; without energy
  figures no energy is shown.
* Jobs can be paused, resumed, cancelled and retried from the window; a self-test
  runs end to end in worker processes.
* Closing the window asks running jobs to pause.
* The words state facts only.
"""

from __future__ import annotations

import time
from tkinter import ttk

import pytest
from test_research_engine import machine
from test_strategy_settings_ui import root  # noqa: F401

import research_engine_ui as ui
from research_engine import preferences
from research_engine.resources import GIB, EnergyModel
from research_engine.store import JobStore

BANNED = (
    "FDS",
    "PTAI",
    "STRAT-",
    "OVL-",
    "Binance",
    "KuCoin",
    "engine.selftest",
    "strategy_lab",
    "_",
)


def open_window(root, tmp_path, inv=None):  # noqa: F811
    win = ui.ResearchEngineWindow(
        root,
        str(tmp_path / "engine"),
        inventory_fn=lambda: inv or machine(),
        refresh_ms=0,
        available_memory=lambda: 64 * GIB,  # not this machine's free memory
    )
    win.withdraw()
    return win


def pump(win, condition, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        win.refresh()
        win.update()
        if condition():
            return True
        time.sleep(0.1)
    return False


def texts_of(win):
    out = []

    def walk(w):
        for child in w.winfo_children():
            if "text" in child.keys():
                out.append(str(child.cget("text")))
            walk(child)

    walk(win)
    return out


def test_the_computer_is_shown_as_the_inventory_reports_it(
    root, tmp_path
):  # noqa: F811
    win = open_window(root, tmp_path)
    shown = win.computer_label.cget("text")
    assert "AMD Ryzen 7 8845HS w/ Radeon 780M Graphics (8 cores, 16 threads)" in shown
    assert "Memory: 32.0 GiB, 12.0 GiB available" in shown
    assert "Graphics: AMD Radeon 780M Graphics" in shown
    assert "none found, so models run on the processor" in shown
    assert win.limits_label.cget("text") == (
        "4 jobs at once, 3 threads each; keeps 8.0 GiB of memory free; up to 6.0 GiB "
        "a job; below normal priority."
    )
    win.close()


def test_a_mode_is_applied_and_kept(root, tmp_path):  # noqa: F811
    win = open_window(root, tmp_path)
    win.mode_var.set("Low resource")
    win.set_mode()
    assert win.scheduler.limits.workers == 1
    assert win.limits_label.cget("text").startswith("1 job at once, 1 thread each")
    assert "idle priority" in win.limits_label.cget("text")
    win.close()
    again = open_window(root, tmp_path)
    assert again.mode_var.get() == "Low resource"
    assert again.scheduler.limits.mode == "low_resource"
    again.close()


def test_without_energy_figures_no_energy_is_shown(root, tmp_path):  # noqa: F811
    win = open_window(root, tmp_path)
    store = win.store
    job, _ = store.submit("engine.selftest", {"steps": 1}, seed=1)
    store.claim_next()
    store.finish(job.id, {}, {"cpu_seconds": 7200.0, "wall_seconds": 7300.0})
    win.refresh()
    row = win.rows()[0]
    assert row[ui.COLUMNS.index("energy")] == "—"
    assert row[ui.COLUMNS.index("cpu")] == "2.00 h"
    assert "Energy" not in win.status_var.get()
    win.watts_var.set("15")
    win.tariff_var.set("0.25")
    win.currency_var.set("GBP")
    assert win.save_energy()
    assert win.rows()[0][ui.COLUMNS.index("energy")] == "30.000"
    assert "Energy, estimated: 30.00 Wh, 0.0075 GBP." in win.status_var.get()
    assert preferences.load(store.root).watts_per_busy_core == 15.0
    win.close()


def test_a_wrong_energy_figure_is_refused(root, tmp_path):  # noqa: F811
    win = open_window(root, tmp_path)
    win.watts_var.set("lots")
    assert not win.save_energy()
    assert "number above 0" in win.message_var.get()
    assert preferences.load(win.store.root).watts_per_busy_core is None
    win.close()


def test_queued_jobs_are_paused_resumed_cancelled_and_retried(
    root, tmp_path
):  # noqa: F811
    win = open_window(root, tmp_path)
    ids = win.run_selftest()
    assert len(ids) == ui.SELFTEST_JOBS
    assert [r[2] for r in win.rows()] == ["Queued"] * ui.SELFTEST_JOBS
    win.table.tree.selection_set(str(ids[0]))
    for button, state in (
        ("Pause", "Paused"),
        ("Resume", "Queued"),
        ("Cancel", "Cancelled"),
        ("Retry", "Queued"),
    ):
        press(win, button)
        assert win.rows()[0][2] == state
    win.table.tree.selection_remove(win.table.tree.selection())
    press(win, "Pause")
    assert win.message_var.get() == "Select a job first."
    win.close()


def press(win, text):
    def walk(w):
        for child in w.winfo_children():
            if isinstance(child, ttk.Button) and child.cget("text") == text:
                return child
            found = walk(child)
            if found is not None:
                return found
        return None

    button = walk(win)
    assert button is not None, text
    button.invoke()


def test_a_self_test_runs_end_to_end(root, tmp_path):  # noqa: F811
    win = open_window(root, tmp_path)
    ids = win.run_selftest()
    win.start()
    assert "The engine is running." in win.status_var.get()
    done = pump(
        win,
        lambda: all(win.store.get(i).state == "done" for i in ids),
        timeout=120,
    )
    assert done, [win.store.get(i).error for i in ids]
    for row in win.rows():
        assert row[2] == "Done" and row[3] == "100%"
        assert row[ui.COLUMNS.index("memory")]  # peak memory recorded
    win.stop()
    assert "The engine is stopped." in win.status_var.get()
    win.close()


def test_closing_the_window_asks_running_jobs_to_pause(root, tmp_path):  # noqa: F811
    win = open_window(root, tmp_path)
    store = win.store
    job, _ = win.scheduler.submit(
        "engine.selftest", {"steps": 60, "sleep": 0.2}, seed=1
    )
    win.start()
    assert pump(win, lambda: (store.get(job.id).progress or 0) > 0, timeout=60)
    win.close()
    deadline = time.monotonic() + 30
    while store.get(job.id).state == "running" and time.monotonic() < deadline:
        time.sleep(0.2)
    assert store.get(job.id).state == "paused"
    assert store.get(job.id).checkpoint["step"] > 0


def test_the_words_state_facts_only(root, tmp_path):  # noqa: F811
    win = open_window(root, tmp_path)
    store = JobStore(win.store.root)
    bad, _ = store.submit("engine.selftest", {"x": 1}, seed=9)
    assert store.claim_next().id == bad.id
    store.fail(
        bad.id, "Traceback ...\nRuntimeError: the self-test was asked to fail", {}
    )
    win.run_selftest()
    texts = texts_of(win) + [win.status_var.get(), win.message_var.get()]
    texts += [str(v) for row in win.rows() for v in row]
    texts += list(ui.HEADINGS.values()) + list(ui.MODE_NAMES.values())
    texts += list(ui.STATE_NAMES.values()) + list(ui.KIND_NAMES.values())
    for text in texts:
        for banned in BANNED:
            assert banned not in text, (banned, text)
    assert "RuntimeError: the self-test was asked to fail" in [
        r[-1] for r in win.rows()
    ]
    win.close()


def test_the_formats():
    assert ui.duration(12.34) == "12.3 s"
    assert ui.duration(245) == "4 min 05 s"
    assert ui.duration(4500) == "1.25 h"
    assert ui.memory_text(0) == ""
    assert ui.memory_text(512 * ui.MIB) == "512 MiB"
    assert ui.memory_text(3 * GIB) == "3.0 GiB"
    assert ui.status_text(
        {
            "by_state": {s: 0 for s in ui.STATE_NAMES},
            "cpu_seconds": 0.0,
        },
        EnergyModel(),
        False,
        "",
    ).startswith("The engine is stopped.")


@pytest.fixture
def hub(monkeypatch):
    import helpers_trainer as ht
    import pt_hub

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    yield hub
    ht.close_hub(hub)


def test_settings_training_opens_the_research_engine(hub, monkeypatch, tmp_path):
    from test_trainer_launch import open_settings, press as press_hub, widgets

    monkeypatch.setattr(
        ui.resources,
        "inventory",
        lambda path=None, **_: machine(memory_total_bytes=16 * GIB),
    )
    win = open_settings(hub)
    texts = [
        str(w.cget("text"))
        for w in widgets(win)
        if isinstance(w, (ttk.Label, ttk.Button)) and "text" in w.keys()
    ]
    assert "Research engine..." in texts
    press_hub(win, "Research engine...")
    engine = hub._research_engine_window
    assert isinstance(engine, ui.ResearchEngineWindow)
    engine.withdraw()
    press_hub(win, "Research engine...")  # raises the open one
    assert hub._research_engine_window is engine
    engine.close()
    win.destroy()
