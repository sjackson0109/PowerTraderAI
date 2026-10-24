"""The Settings window: rows that must (not) be there.

Runs a real hub under the isolation guard (app/conftest.py) with a hidden window.
"""

import os
import sys
from tkinter import ttk

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_hub  # noqa: E402


@pytest.fixture
def hub(monkeypatch):
    import helpers_trainer as ht

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    yield hub
    ht.close_hub(hub)


def test_settings_has_no_robinhood_api_row(hub):
    from test_trainer_launch import open_settings, widgets

    win = open_settings(hub)
    texts = [
        str(w.cget("text"))
        for w in widgets(win)
        if isinstance(w, (ttk.Label, ttk.Button)) and "text" in w.keys()
    ]
    assert "Robinhood API:" not in texts
    assert "Setup Wizard" not in texts
    assert not any("no API key / private key saved" in t for t in texts)
    # the rows around it are still there
    assert "pt_trader.py path:" in texts and "Paper Account..." in texts
    win.destroy()


def label_texts(win):
    """Every label's text, a hint's from its variable."""
    texts = []
    for w in widgets_of(win):
        if isinstance(w, ttk.Label):
            var = str(w.cget("textvariable"))
            texts.append(str(w.getvar(var)) if var else str(w.cget("text")))
    return texts


def widgets_of(win):
    from test_trainer_launch import widgets

    return widgets(win)


def test_settings_sizes_a_new_trade_and_caps_a_coin(hub):
    """Start allocation % and Max per coin %, each shown in dollars at the last
    account value; Save writes both where the trader reads them."""
    from test_trainer_launch import open_settings, press, type_into

    hub._last_total_account_value = 10_000.0
    win = open_settings(hub)
    texts = label_texts(win)
    assert "Max per coin %:" in texts
    assert "≈ $100.00 per entry, at least the exchange minimum" in texts
    assert "≈ $1,000.00 per coin with DCA; no DCA buy past it" in texts

    type_into(win, "Start allocation %:", "2")
    type_into(win, "Max per coin %:", "15")
    assert "≈ $200.00 per entry, at least the exchange minimum" in label_texts(win)
    assert "≈ $1,500.00 per coin with DCA; no DCA buy past it" in label_texts(win)
    press(win, "Save")

    assert [d[1][0] for d in hub.test_dialogs if d[0] == "showinfo"] == ["Saved"]
    saved = hub._load_settings()
    assert (saved["start_allocation_pct"], saved["max_coin_allocation_pct"]) == (
        2.0,
        15.0,
    )
