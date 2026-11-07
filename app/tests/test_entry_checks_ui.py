"""The entry assessment in Settings and its table (FDS-SIG-004 sections 5.10 and 6.6).

* Settings > Strategy has the entry assessment; Settings > Risk the volatility size
  reduction and the two entry limits. Each offers Off and Log only, Off by default; a
  saved value this version does not offer shows as Off.
* Saving writes the section only when a value changed.
* The Entry Assessments table shows each assessment's facts and no outcome.
* All their text states facts: no spec names.

The windows run under the isolation guard (app/conftest.py) with a hidden root, saving to
a pt_config.json in a temporary folder."""

from __future__ import annotations

import json
import os
import re
import tkinter as tk

import pytest

import entry_assessment_view as view
import entry_checks_ui as checks
import risk_settings_ui
import strategy_settings_ui
from pt_settings_manager import SettingsManager


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


class Box:
    def __init__(self):
        self.errors = []

    def showerror(self, title, message, **_):
        self.errors.append(message)

    def askyesno(self, *_a, **_k):
        return True


def manager(folder):
    return SettingsManager("pt_config.json", folder)


def on_disk(folder):
    path = os.path.join(folder, "pt_config.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def strategy_window(root, folder):
    win = strategy_settings_ui.StrategySettingsWindow(
        root, manager_factory=lambda: manager(folder), messagebox=Box()
    )
    win.withdraw()
    return win


def risk_window(root, folder):
    win = risk_settings_ui.RiskSettingsWindow(
        root, manager_factory=lambda: manager(folder), messagebox=Box()
    )
    win.withdraw()
    return win


def combos(win):
    out = []
    stack = [win]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        if w.winfo_class() == "TCombobox":
            out.append(w)
    return out


def test_each_setting_offers_off_and_log_only_and_is_off_by_default(root, tmp_path):
    folder = str(tmp_path / "config")
    s = strategy_window(root, folder)
    r = risk_window(root, folder)
    assert {k: v.get() for k, v in s.entry_check_vars.items()} == {
        "entry_assessment": "Off"
    }
    assert {k: v.get() for k, v in r.entry_check_vars.items()} == {
        "volatility_shrink": "Off",
        "participation_cap": "Off",
        "spread_cap": "Off",
    }
    for win, n in ((s, 1), (r, 3)):
        offered = [
            tuple(c.cget("values"))
            for c in combos(win)
            if tuple(c.cget("values")) == ("Off", "Log only")
        ]
        assert len(offered) == n
    s.destroy()
    r.destroy()


def test_saving_writes_the_section_only_when_a_value_changed(root, tmp_path):
    folder = str(tmp_path / "config")
    r = risk_window(root, folder)
    assert r.save()
    assert "signal_fusion" not in on_disk(folder)  # nothing changed: nothing written
    r = risk_window(root, folder)
    r.entry_check_vars["spread_cap"].set("Log only")
    assert r.save()
    saved = on_disk(folder)["signal_fusion"]
    assert saved["spread_cap"] == "log_only"
    assert saved["entry_assessment"] == "off"
    s = strategy_window(root, folder)
    assert s.entry_check_vars["entry_assessment"].get() == "Off"
    s.entry_check_vars["entry_assessment"].set("Log only")
    assert s.save()
    saved = on_disk(folder)["signal_fusion"]
    assert saved["entry_assessment"] == "log_only"
    assert saved["spread_cap"] == "log_only"  # the Risk window's value is kept


def test_a_saved_value_this_version_does_not_offer_shows_as_off(root, tmp_path):
    folder = str(tmp_path / "config")
    m = manager(folder)
    assert m.set_section(
        "signal_fusion", {"entry_assessment": "veto", "spread_cap": "on"}
    )
    s = strategy_window(root, folder)
    r = risk_window(root, folder)
    assert s.entry_check_vars["entry_assessment"].get() == "Off"
    assert r.entry_check_vars["spread_cap"].get() == "Off"
    s.destroy()
    r.destroy()


def test_the_text_states_facts_only():
    spec = re.compile(r"FDS|SIG-|spec|section|§|D1[0-9]|phase", re.IGNORECASE)
    texts = list(checks.LABELS.values()) + list(checks.HELP.values())
    texts += list(view.HEADINGS.values())
    for text in texts:
        assert not spec.search(text), text


def test_the_table_shows_facts_and_no_outcome(root):
    headings = " ".join(view.HEADINGS.values()).lower()
    for word in ("result", "p&l", "pnl", "net", "return", "score"):
        assert word not in headings
    record = {
        "when_s": 1_762_500_000,
        "coin": "ETH",
        "source": "strategy",
        "amount_usd": 100.0,
        "fee": 0.005,
        "spread": 0.0012,
        "hourly_median_usd": 20_000.0,
        "participation": 0.005,
        "effect": "allow",
        "parts": [
            {
                "name": "entry_assessment",
                "mode": "log_only",
                "available": False,
                "reason": "no registered model",
                "would": "allow",
            },
            {
                "name": "spread_cap",
                "mode": "log_only",
                "available": True,
                "reason": "",
                "would": "allow",
                "value": 0.0012,
            },
        ],
    }
    row = view.cells(record)
    assert row[1] == "ETH" and row[2] == "Strategy"
    assert row[8] == "not available" and row[10] == "None"
    assert "Expected value: no registered model" in row[11]
    v = view.EntryAssessmentView(root, read=lambda: [record, record], poll=False)
    v.refresh()
    assert len(v.tree.get_children()) == 2
    v.destroy()
