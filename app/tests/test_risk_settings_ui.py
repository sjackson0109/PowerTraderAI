"""Settings > Risk: the window, and its row in Settings.

The window runs under the isolation guard (app/conftest.py) with a hidden root, and
saves to a pt_config.json in a temporary folder.
"""

from __future__ import annotations

import tkinter as tk

import pytest

import risk_settings_ui as ui

# --- the window ------------------------------------------------------------------------


@pytest.fixture
def root():
    last = None
    for _ in range(5):  # Tk on Windows sometimes fails to read init.tcl at first
        try:
            r = tk.Tk()
            break
        except tk.TclError as exc:
            last = exc
    else:
        pytest.skip(f"Tk cannot start: {last}")
    r.withdraw()
    yield r
    r.destroy()


# --- the window in the hub ----------------------------------------------------------


@pytest.fixture
def hub(monkeypatch):
    import helpers_trainer as ht
    import pt_hub

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    yield hub
    ht.close_hub(hub)


def test_settings_opens_the_risk_window_next_to_strategy(hub):
    from test_settings_window import widgets_of
    from test_trainer_launch import open_settings, press

    win = open_settings(hub)
    buttons = [
        str(w.cget("text")) for w in widgets_of(win) if isinstance(w, tk.ttk.Button)
    ]
    assert buttons.index("Risk...") == buttons.index("Strategy...") + 1
    press(win, "Risk...")
    risk_win = hub._risk_settings_win
    assert isinstance(risk_win, ui.RiskSettingsWindow)
    assert risk_win.title() == "Risk"
    risk_win.withdraw()
    press(win, "Risk...")  # raises the open one rather than opening another
    assert hub._risk_settings_win is risk_win
    risk_win.withdraw()
    risk_win.destroy()
    win.destroy()
