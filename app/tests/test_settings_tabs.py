"""The Settings window as one tab per section; Working Directories read-only; the
scripts part of the program; the paper-fill rules, start-up timeframe, auto start
and training notices reachable from Settings and doing what they say.

Runs a real hub under the isolation guard (app/conftest.py) with a hidden window.
"""

import json
import os
import sys
import tkinter as tk
import types
from tkinter import ttk
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_hub  # noqa: E402
import pt_paths  # noqa: E402
import trading_mode  # noqa: E402
import training_settings  # noqa: E402

Hub = pt_hub.PowerTraderHub

TABS = [
    "Trading",
    "Training",
    "Exchanges",
    "Paper trading",
    "LLM",
    "Display",
    "Working Directories",
    "System",
]


@pytest.fixture
def hub(monkeypatch):
    import helpers_trainer as ht

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    yield hub
    ht.close_hub(hub)


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


def open_settings(hub):
    from test_trainer_launch import open_settings as opener

    return opener(hub)


def tab_pages(win):
    (notebook,) = [w for w in widgets(win) if isinstance(w, ttk.Notebook)]
    return {notebook.tab(t, "text"): notebook.nametowidget(t) for t in notebook.tabs()}


def texts_in(parent):
    return [
        str(w.cget("text"))
        for w in widgets(parent)
        if isinstance(w, (ttk.Label, ttk.Button, ttk.Checkbutton))
        and "text" in w.keys()
    ]


def entry_on_row(win, label):
    (lbl,) = [
        w
        for w in widgets(win)
        if isinstance(w, ttk.Label) and str(w.cget("text")) == label
    ]
    row = int(lbl.grid_info()["row"])
    (field,) = [
        w
        for w in lbl.master.winfo_children()
        if isinstance(w, (ttk.Entry, ttk.Combobox))
        and int(w.grid_info().get("row", -1)) == row
    ]
    return field


# --- the tabs ---------------------------------------------------------------------


def test_settings_has_one_tab_per_section_in_order(hub):
    win = open_settings(hub)
    pages = tab_pages(win)
    assert list(pages) == TABS
    assert {
        "Coins (comma):",
        "Trade start level (1-7):",
        "Strategy...",
        "Risk...",
    } <= set(texts_in(pages["Trading"]))
    assert {
        "Minimum scored signals:",
        "Retrain every (hours):",
        "Show a notice when a training run ends",
    } <= set(texts_in(pages["Training"]))
    assert {
        "Primary exchange:",
        "Configure Exchange APIs...",
        "Check Exchanges...",
    } <= set(texts_in(pages["Exchanges"]))
    assert {
        "Paper-trading coins:",
        "Oldest price a paper fill uses (s):",
        "With no fresh price:",
        "Paper Account...",
    } <= set(texts_in(pages["Paper trading"]))
    assert "LLM Providers..." in texts_in(pages["LLM"])
    assert {
        "Candles limit:",
        "Chart timeframe at start-up:",
        "Chart settings…",
    } <= set(texts_in(pages["Display"]))
    assert {
        "Start the Neural Runner and Trader when the hub opens",
        "Enable Public API Server",
        "Test API",
    } <= set(texts_in(pages["System"]))
    win.destroy()


def test_the_scripts_and_the_editable_folders_are_gone(hub):
    win = open_settings(hub)
    texts = texts_in(win)
    for gone in (
        "pt_thinker.py path:",
        "pt_trainer.py path:",
        "pt_trader.py path:",
        "Main neural folder:",
        "Hub data dir (optional):",
        "Browse",
        "Auto start scripts on GUI launch",
    ):
        assert gone not in texts
    win.destroy()


def test_working_directories_lists_every_folder_read_only(hub):
    win = open_settings(hub)
    page = tab_pages(win)["Working Directories"]
    rows = Hub._user_folder_rows(hub.settings)
    assert [label for label, _ in rows] == [
        "Config folder:",
        "Data folder:",
        "Models folder:",
        "Hub data folder:",
        "Cache folder:",
        "Log folder:",
    ]
    for label, folder in rows:
        entry = entry_on_row(page, label)
        assert entry.get() == folder
        assert str(entry.cget("state")) == "readonly"
    assert texts_in(page).count("Open folder") == len(rows)
    # the folders in use are the hub's own
    assert dict(rows)["Hub data folder:"] == hub.hub_dir
    win.destroy()


def test_save_keeps_the_folders_chosen_in_an_older_release(hub):
    from test_trainer_launch import press

    chosen = os.path.join(pt_paths.data_dir(), "my_models")
    hub.settings["main_neural_dir"] = chosen
    hub.settings["hub_data_dir"] = "my_hub"
    win = open_settings(hub)
    assert entry_on_row(win, "Models folder:").get() == chosen
    press(win, "Save")
    saved = hub._load_settings()
    assert (saved["main_neural_dir"], saved["hub_data_dir"]) == (chosen, "my_hub")


# --- the scripts are part of the program -------------------------------------------


def test_the_scripts_are_system_values_not_settings(hub):
    assert pt_hub.SYSTEM_SCRIPTS == {
        "script_neural_trainer": "pt_pattern_trainer.py",
        "script_neural_runner2": "pt_thinker.py",
        "script_trader": "pt_trader.py",
    }
    for key in pt_hub.SYSTEM_SCRIPTS:
        assert key not in pt_hub.DEFAULT_SETTINGS
        assert key not in hub.settings
    program = pt_paths.program_dir()
    assert hub.proc_neural.path == os.path.join(program, "pt_thinker.py")
    assert hub.proc_trader.path == os.path.join(program, "pt_trader.py")
    assert hub.proc_trainer_path == os.path.join(program, "pt_pattern_trainer.py")


def test_scripts_saved_by_an_older_release_are_dropped_when_read(hub):
    path = pt_paths.gui_settings_file()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"script_trader": "x.py", "script_neural_runner2": "y.py"}, f)
    settings = hub._load_settings()
    assert "script_trader" not in settings
    assert "script_neural_runner2" not in settings


# --- paper trading, display -----------------------------------------------------------


def test_paper_trading_saves_its_price_rules(hub):
    from test_trainer_launch import press, type_into

    win = open_settings(hub)
    assert entry_on_row(win, "Oldest price a paper fill uses (s):").get() == "30"
    assert entry_on_row(win, "With no fresh price:").get() == (
        pt_hub.PAPER_PRICE_RULES["pause"]
    )
    type_into(win, "Oldest price a paper fill uses (s):", "45")
    entry_on_row(win, "With no fresh price:").set(
        pt_hub.PAPER_PRICE_RULES["simulate_and_flag"]
    )
    press(win, "Save")
    assert [d for d in hub.test_dialogs if d[0] == "showerror"] == []
    paper = trading_mode.read_paper_settings()
    assert paper.max_quote_age_s == 45.0
    assert paper.price_fallback_policy == "simulate_and_flag"


@pytest.mark.parametrize("age", ["0", "4000", "soon"])
def test_paper_trading_refuses_a_price_age_out_of_range(hub, age):
    from test_trainer_launch import press, type_into

    win = open_settings(hub)
    type_into(win, "Oldest price a paper fill uses (s):", age)
    type_into(win, "Trade start level (1-7):", "5")
    press(win, "Save")
    assert any(d[0] == "showerror" for d in hub.test_dialogs)
    assert trading_mode.read_paper_settings().max_quote_age_s == 30.0
    assert hub._load_settings().get("trade_start_level", 3) != 5  # nothing saved
    win.destroy()


@pytest.mark.parametrize(
    "label, value",
    [
        ("Random-entry baselines:", "50"),
        ("Random-entry baselines:", "1500.5"),
        ("Beat this percentile of random entries:", "100"),
        ("Minimum return per day held after fees %:", "lots"),
        ("Minimum scored signals:", "0"),
    ],
)
def test_the_entry_gate_settings_refuse_a_value_out_of_range(hub, label, value):
    from test_trainer_launch import press, type_into

    win = open_settings(hub)
    type_into(win, label, value)
    type_into(win, "Trade start level (1-7):", "5")
    press(win, "Save")
    assert any(d[0] == "showerror" for d in hub.test_dialogs)
    assert training_settings.read_training_settings() == training_settings.normalise({})
    assert hub._load_settings().get("trade_start_level", 3) != 5  # nothing saved
    win.destroy()


def test_save_paper_settings_checks_both_rules():
    manager = mock.Mock()
    assert trading_mode.save_paper_settings("never", 30) is False
    assert trading_mode.save_paper_settings("pause", 0.5, manager) is False
    manager.set.assert_not_called()


def test_display_saves_the_chart_timeframe_at_start_up(hub):
    from test_trainer_launch import press

    win = open_settings(hub)
    box = entry_on_row(win, "Chart timeframe at start-up:")
    assert box.get() == "1hour"
    assert "4hour" in box.cget("values")
    box.set("4hour")
    press(win, "Save")
    assert hub._load_settings()["default_timeframe"] == "4hour"


# --- auto start -------------------------------------------------------------------------


def auto_start_hub(enabled=True, coins=("BTC", "ETH"), trained=("BTC", "ETH")):
    hub = types.SimpleNamespace(
        settings={"auto_start_scripts": enabled},
        coins=list(coins),
        start_all_scripts=mock.Mock(),
        _show_notice=mock.Mock(),
    )
    hub._coin_is_trained = lambda coin: coin in trained
    return hub


def test_auto_start_starts_the_runner_and_trader_when_every_coin_is_trained():
    hub = auto_start_hub()
    Hub._auto_start_on_launch(hub)
    hub.start_all_scripts.assert_called_once_with()
    hub._show_notice.assert_not_called()


def test_auto_start_with_an_untrained_coin_starts_nothing_and_says_which():
    hub = auto_start_hub(trained=("BTC",))
    Hub._auto_start_on_launch(hub)
    hub.start_all_scripts.assert_not_called()
    hub._show_notice.assert_called_once_with("Auto start skipped: ETH not trained yet.")


def test_auto_start_off_does_nothing():
    hub = auto_start_hub(enabled=False)
    Hub._auto_start_on_launch(hub)
    hub.start_all_scripts.assert_not_called()
    hub._show_notice.assert_not_called()


def test_the_hub_queues_the_auto_start_when_it_opens(hub):
    scripts = [
        str(hub.tk.call("after", "info", timer)[0])
        for timer in hub.tk.splitlist(hub.tk.call("after", "info"))
    ]
    assert any(s.endswith("_auto_start_on_launch") for s in scripts)


# --- training notices ---------------------------------------------------------------------


class EndedProc:
    def __init__(self, code):
        self.returncode = code
        self.stdout = None
        self.pid = 4242

    def poll(self):
        return self.returncode


def notice_hub(code, notify=True, gate=None):
    hub = types.SimpleNamespace(
        settings={"training_notifications": notify},
        trainers={
            "ETH": types.SimpleNamespace(
                info=types.SimpleNamespace(proc=EndedProc(code))
            )
        },
        last_training_times={},
        _schedule_auto_retrain=mock.Mock(),
        _mark_training_ended=mock.Mock(),
        _show_notice=mock.Mock(),
        _training_ended_text=Hub._training_ended_text,
        _gate_record=lambda coin: gate,
    )
    return hub


def gate_record(published, kept=None):
    """A model_gate.json record, as the trainer writes it."""
    import entry_gate

    decision = entry_gate.Decision(
        published,
        [] if published else ["forced"],
        entry_gate.Score(25, 0.02 if published else -0.01, 0.02, -0.05, 0.9),
        entry_gate.Fees(0.012, "taker", "coinbase", "default", 0.0005),
        entry_gate.GateSettings(),
        baseline={
            "runs": 1000,
            "seed": 0,
            "entries": 25,
            "median": -0.02,
            "percentile": 95.0,
            "at_percentile": 0.01,
            "rank": 99.0 if published else 40.0,
            "median_drawdown": -0.1,
            "short": [],
        },
    )
    return {
        "coin": "ETH",
        "published": published,
        "model_id": "ETH-20260101T0000Z-0123456789ab" if published else None,
        "kept_model_id": kept,
        "gate": decision.to_dict(),
    }


def per_day_record(published, kept=None):
    """A model_gate.json record judged by the return per day held (FDS-MH-001 §6)."""
    import entry_gate

    record = gate_record(published, kept)
    decision = entry_gate.Decision.from_dict(record["gate"])
    decision.measure = entry_gate.PER_DAY
    decision.candidate = entry_gate.Score(25, 0.02, 0.02, -0.05, 0.9, 0.0004)
    decision.baseline = dict(decision.baseline, median=0.0001)
    record["gate"] = decision.to_dict()
    return record


def test_a_notice_names_the_return_per_day_held():
    hub = notice_hub(0, gate=per_day_record(True))
    Hub._monitor_trainer_process(hub, "ETH")
    hub._show_notice.assert_called_once_with(
        "ETH: training finished; its new model passed the entry gate (return per day "
        "held after fees vs random: +0.040% vs +0.010% a day (99th percentile)) and "
        "is in use."
    )


def test_a_notice_says_whether_the_new_model_passed_the_entry_gate():
    hub = notice_hub(0, gate=gate_record(True))
    Hub._monitor_trainer_process(hub, "ETH")
    hub._show_notice.assert_called_once_with(
        "ETH: training finished; its new model passed the entry gate (return after "
        "fees vs random: +2.00% vs -2.00% (99th percentile)) and is in use."
    )
    hub = notice_hub(0, gate=gate_record(False, kept="ETH-20251201T0000Z-aaaaaaaaaaaa"))
    Hub._monitor_trainer_process(hub, "ETH")
    hub._show_notice.assert_called_once_with(
        "ETH: training finished, but the new model did not pass the entry gate "
        "(return after fees vs random: -1.00% vs -2.00% (40th percentile)); the model "
        "in use is kept."
    )
    hub = notice_hub(0, gate=gate_record(False))
    Hub._monitor_trainer_process(hub, "ETH")
    (text,), _ = hub._show_notice.call_args
    assert text.endswith("ETH has no model in use until one passes.")


def test_a_finished_training_run_shows_a_notice():
    hub = notice_hub(0)
    Hub._monitor_trainer_process(hub, "ETH")
    hub._show_notice.assert_called_once_with(
        "ETH: training finished; its new model is saved."
    )


def test_a_failed_training_run_shows_a_notice_with_its_code():
    hub = notice_hub(3)
    Hub._monitor_trainer_process(hub, "ETH")
    (text,), _ = hub._show_notice.call_args
    assert text.startswith("ETH: training ended without a model (exit code 3)")


def test_training_notices_off_show_nothing():
    hub = notice_hub(0, notify=False)
    Hub._monitor_trainer_process(hub, "ETH")
    hub._show_notice.assert_not_called()


def test_a_hidden_hub_keeps_the_notice_but_opens_no_window(hub):
    before = set(hub.winfo_children())
    hub._show_notice("BTC: training finished; its new model is saved.")
    assert hub.notices[-1] == "BTC: training finished; its new model is saved."
    assert set(hub.winfo_children()) == before


def test_a_shown_hub_puts_the_notice_in_a_small_window(hub, monkeypatch):
    class Invisible(tk.Toplevel):  # never seen on the screen during the tests
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.attributes("-alpha", 0.0)

    monkeypatch.setattr(pt_hub.tk, "Toplevel", Invisible)
    monkeypatch.setattr(hub, "winfo_viewable", lambda: True)
    hub._show_notice("Auto start skipped: ETH not trained yet.")
    (note,) = [w for w in hub.winfo_children() if isinstance(w, Invisible)]
    assert note.wm_overrideredirect()
    (label,) = note.winfo_children()
    assert label.cget("text") == "Auto start skipped: ETH not trained yet."
    note.destroy()
