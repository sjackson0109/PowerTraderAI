"""Settings > Strategy: the words it shows, the window, and its row in Settings.

The window runs under the isolation guard (app/conftest.py) with a hidden root, and
saves to a pt_config.json in a temporary folder.
"""

from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import ttk

import pytest

import strategy_settings_ui as ui
from pt_settings_manager import SettingsManager
from strategies import descriptions as words
from strategies.catalogue import CATALOGUE
from strategies.factory import build_runner
from strategies.settings import read_strategy_settings

# --- the words -------------------------------------------------------------------------


def all_text():
    texts = list(words.ENGINE_NAMES.values()) + list(words.ENGINE_HELP.values())
    texts.append(words.STOPS_HELP)
    for d in words.DESCRIPTIONS.values():
        texts += [d.name, d.summary] + [why for _, why in d.rules]
        for p in d.params.values():
            texts += [p.label, p.help] + list(p.choices.values())
    return texts


def test_the_window_offers_every_strategy_but_one_that_needs_a_model():
    """For trading: the strategies the mode may use (FDS-SR-001 5.3), never a model."""
    offered = ui.offered_strategies()
    assert "STRAT-001" in offered and "STRAT-003" not in offered
    for mode in ("paper", "live"):
        assert ui.offered_strategies(mode) == [
            sid
            for sid, e in CATALOGUE.items()
            if e["class_type"] == "main"
            and e["family"] != "model"
            and e["authorisation"]
            in ({"paper", "live"} if mode == "paper" else {"live"})
        ]
    assert ui.overlay_ids() == [
        "OVL-RATCHET",
        "OVL-ATR",
        "OVL-PLOCK",
        "OVL-COOLDOWN",
        "OVL-REGIME",  # listed; research only, so its tick is disabled
    ]


def test_every_offered_strategy_and_stop_and_parameter_is_described():
    for sid in ui.offered_strategies() + ui.overlay_ids():
        described = words.DESCRIPTIONS[sid]
        entry = CATALOGUE[sid]
        assert described.name and described.summary, sid
        assert set(described.params) == set(entry["default_params"]), sid
        for name, p in described.params.items():
            assert p.label and p.help, (sid, name)
            values = entry["param_bounds"][name].get("values")
            if values:
                assert set(p.choices) == set(values), (sid, name)
    names = [words.name_of(sid) for sid in ui.offered_strategies()]
    assert len(set(names)) == len(names)
    assert set(words.TIMEFRAME_NAMES) == set(words.timeframes())


def test_the_words_name_no_spec_id_parameter_or_data_provider():
    for text in all_text():
        for banned in ("FDS", "STRAT-", "OVL-", "Binance", "KuCoin", "_len", "_pct"):
            assert banned not in text, (banned, text)
        assert "catalogue" not in text.lower(), text


def test_the_rules_between_two_parameters_match_the_strategies_own():
    """Every pair the window refuses is one the strategy refuses, and the reverse."""
    for sid, params in (
        ("STRAT-000", {"fast_len": 30, "slow_len": 30}),
        ("STRAT-001", {"fast_len": 30, "slow_len": 25}),
        ("OVL-RATCHET", {"trigger_pct": 1.0, "lock_pct": 1.0}),
    ):
        full = dict(CATALOGUE[sid]["default_params"], **params)
        assert words.rule_problem(sid, full)
        assert words.rule_problem(sid, CATALOGUE[sid]["default_params"]) is None
        from strategies.settings import params_problem

        assert params_problem(sid, params)


def test_the_settings_line_says_what_is_trading():
    s = read_strategy_settings(
        {"strategy": {"timeframe": "4h", "overlays": [{"id": "OVL-RATCHET"}]}}
    )
    assert words.summary_line(s) == (
        "Trend crossover (DEMA/TEMA) on 4-hour candles; stops and filters: "
        "Ratchet stop"
    )
    assert words.summary_line(read_strategy_settings({})).endswith(
        "on 1-hour candles; stops and filters: none"
    )
    legacy = read_strategy_settings({"strategy": {"engine": "legacy_neural"}})
    assert words.summary_line(legacy) == words.ENGINE_NAMES["legacy_neural"]
    bad = read_strategy_settings({"strategy": {"active_id": "nope"}})
    assert "no orders are placed" in words.summary_line(bad)


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


class Box:
    def __init__(self, answer=False):
        self.errors = []
        self.questions = []
        self.answer = answer  # what askyesno answers

    def showerror(self, title, message, **_):
        self.errors.append(message)

    def askyesno(self, title, message, **_):
        self.questions.append(message)
        return self.answer


@pytest.fixture
def folder(tmp_path):
    return str(tmp_path)


def manager(folder):
    return SettingsManager("pt_config.json", folder)


def on_disk(folder):
    path = os.path.join(folder, "pt_config.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("strategy", {})


def open_window(root, folder, saved=None, box=None):
    if saved is not None:
        assert manager(folder).set_strategy(saved)
    calls = []
    win = ui.StrategySettingsWindow(
        root,
        manager_factory=lambda: manager(folder),
        on_saved=lambda: calls.append("saved"),
        messagebox=box or Box(),
    )
    win.withdraw()
    win.saved_calls = calls
    return win


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


def shown_labels(frame):
    return [
        str(w.cget("text"))
        for w in frame.winfo_children()
        if isinstance(w, ttk.Label) and str(w.cget("text")).endswith(":")
    ]


def test_a_new_install_shows_the_default_strategy(root, folder):
    win = open_window(root, folder)
    assert win.engine_var.get() == "catalogue"
    assert win.strategy_var.get() == "Trend crossover (DEMA/TEMA)"
    assert win.timeframe_var.get() == "1 hour"
    assert {k: v.get() for k, v in win.param_vars("STRAT-001").items()} == {
        "ma_type": "TEMA",
        "fast_len": "12",
        "slow_len": "48",
        "persistence_bars": "2",
        "regime_filter": "ADX",
        "adx_len": "14",
        "adx_min": "20",
    }
    assert not any(v.get() for v in win.overlay_on.values())
    assert win.status_var.get() == ""
    assert win.strategy_help_var.get() == words.DESCRIPTIONS["STRAT-001"].summary
    assert win.timeframe_help_var.get() == (
        "The strategy decides when each candle closes: for each coin, once every "
        "1 hour."
    )
    assert shown_labels(win._params_frame) == [
        "Moving average:",
        "Fast average length:",
        "Slow average length:",
        "Confirmation candles:",
        "Trend-strength filter:",
        "ADX length:",
        "Minimum ADX:",
    ]
    hints = [
        str(w.cget("text"))
        for w in win._params_frame.winfo_children()
        if isinstance(w, ttk.Label)
    ]
    assert "5 to 50, default 12" in hints and "default TEMA" in hints
    win.destroy()


def test_choosing_another_strategy_shows_its_own_parameters(root, folder):
    win = open_window(root, folder)
    win.strategy_var.set("Supertrend")
    assert shown_labels(win._params_frame) == [
        "ATR length:",
        "ATR multiple:",
        "Confirmation candles:",
    ]
    assert win.strategy_help_var.get() == words.DESCRIPTIONS["STRAT-002"].summary
    assert win.timeframe_help_var.get().endswith(" Default for this strategy: 4 hours.")
    win.timeframe_var.set("4 hours")
    assert "Default for this strategy" not in win.timeframe_help_var.get()
    win.destroy()


def test_save_writes_what_the_trader_reads(root, folder):
    win = open_window(root, folder)
    win.strategy_var.set("Supertrend")
    win.timeframe_var.set("4 hours")
    win.param_vars("STRAT-002")["mult"].set("2.5")
    win.overlay_on["OVL-RATCHET"].set(True)
    win.param_vars("OVL-RATCHET")["trigger_pct"].set("3")
    win.overlay_on["OVL-COOLDOWN"].set(True)
    win.param_vars("OVL-COOLDOWN")["global"].set(True)
    assert win.save()
    assert win.saved_calls == ["saved"]
    assert on_disk(folder) == {
        "engine": "catalogue",
        "active_id": "STRAT-002",
        "timeframe": "4h",
        "params": {"STRAT-002": {"mult": 2.5}},
        "overlays": [
            {"id": "OVL-RATCHET", "params": {"trigger_pct": 3.0}},
            {"id": "OVL-COOLDOWN", "params": {"global": True}},
        ],
    }
    s = read_strategy_settings(manager(folder))
    assert s.problem is None
    runner = build_runner(s.active_id, s.params, list(s.overlays))
    assert runner.strategy.params["mult"] == 2.5
    assert [o.overlay_id for o in runner.overlays] == ["OVL-RATCHET", "OVL-COOLDOWN"]


def test_the_window_shows_what_was_saved(root, folder):
    win = open_window(
        root,
        folder,
        saved={
            "active_id": "STRAT-002",
            "timeframe": "15m",
            "params": {"STRAT-002": {"atr_len": 7}},
            "overlays": [{"id": "OVL-PLOCK", "params": {"stages": [[2, 0.5], [5, 2]]}}],
        },
    )
    assert win.strategy_var.get() == "Supertrend"
    assert win.timeframe_var.get() == "15 minutes"
    assert win.param_vars("STRAT-002")["atr_len"].get() == "7"
    assert win.overlay_on["OVL-PLOCK"].get()
    assert win.param_vars("OVL-PLOCK")["stages"].get() == "2:0.5, 5:2"
    win.destroy()


@pytest.mark.parametrize(
    "sid, name, value, message",
    [
        (
            "STRAT-001",
            "fast_len",
            "60",
            "Trend crossover (DEMA/TEMA): Fast average length must be from 5 to 50.",
        ),
        (
            "STRAT-001",
            "fast_len",
            "12.5",
            "Trend crossover (DEMA/TEMA): Fast average length must be a whole number "
            "from 5 to 50.",
        ),
        (
            "STRAT-001",
            "fast_len",
            "",
            "Trend crossover (DEMA/TEMA): Fast average length must be a whole number "
            "from 5 to 50.",
        ),
        (
            "STRAT-001",
            "slow_len",
            "20",
            "Trend crossover (DEMA/TEMA): The slow average length must be more than "
            "the fast average length.",
        ),
        (
            "OVL-RATCHET",
            "lock_pct",
            "2",
            "Ratchet stop: The first stop % must be below the start gain %.",
        ),
        (
            "OVL-PLOCK",
            "stages",
            "3:1, 2:0.5",
            "Profit lock stages: Stages (gain %:lock %): each stage's gain must be "
            "above 0 and above the one before.",
        ),
        (
            "OVL-PLOCK",
            "stages",
            "3-1",
            "Profit lock stages: Stages (gain %:lock %): write each stage as gain "
            "%:lock %, e.g. 3:1.",
        ),
        (
            "OVL-PLOCK",
            "stages",
            "3:3",
            "Profit lock stages: Stages (gain %:lock %): each stage's lock must be at "
            "least 0 and below its gain.",
        ),
    ],
)
def test_a_wrong_value_is_refused_and_nothing_is_saved(
    root, folder, sid, name, value, message
):
    box = Box()
    win = open_window(root, folder, box=box)
    if sid.startswith("OVL-"):
        win.overlay_on[sid].set(True)
    if sid == "STRAT-001" and name == "slow_len":
        win.param_vars(sid)["fast_len"].set("25")
    win.param_vars(sid)[name].set(value)
    assert not win.save()
    assert box.errors == [message]
    assert win.status_var.get() == message
    assert win.winfo_exists() and win.saved_calls == []
    assert on_disk(folder) == {}
    win.destroy()


def test_an_unticked_stop_is_not_checked_or_saved(root, folder):
    win = open_window(root, folder)
    win.param_vars("OVL-RATCHET")["lock_pct"].set("99")
    assert win.save()
    assert on_disk(folder)["overlays"] == []


def test_reset_to_defaults_saves_no_parameters(root, folder):
    win = open_window(
        root,
        folder,
        saved={"params": {"STRAT-001": {"fast_len": 10}, "STRAT-002": {"mult": 2.0}}},
    )
    assert win.param_vars("STRAT-001")["fast_len"].get() == "10"
    next(
        w
        for w in widgets(win)
        if isinstance(w, ttk.Button) and str(w.cget("text")) == "Reset to defaults"
    ).invoke()
    assert win.param_vars("STRAT-001")["fast_len"].get() == "12"
    assert win.save()
    # another strategy's saved parameters are kept
    assert on_disk(folder)["params"] == {"STRAT-002": {"mult": 2.0}}


def test_neural_levels_save_only_the_signal_source(root, folder):
    saved = {
        "active_id": "STRAT-002",
        "params": {"STRAT-002": {"mult": 2.0}},
        "overlays": [{"id": "OVL-ATR", "params": {}}],
    }
    win = open_window(root, folder, saved=saved)
    assert win._catalogue_frame.winfo_manager() == "grid"
    win.engine_var.set("legacy_neural")
    assert win._catalogue_frame.winfo_manager() == ""
    assert win.save()
    after = on_disk(folder)
    assert after["engine"] == "legacy_neural"
    assert {k: after[k] for k in saved} == saved
    assert read_strategy_settings(manager(folder)).is_legacy


def test_a_saved_value_the_window_does_not_offer_is_reported(root, folder):
    path = os.path.join(folder, "pt_config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"strategy": {"active_id": "STRAT-003", "overlays": [{"id": "OVL-X"}]}}, f
        )
    win = open_window(root, folder)
    assert win.status_var.get() == "The saved strategy 'STRAT-003' is not one of these."
    assert win.strategy_var.get() == "Trend crossover (DEMA/TEMA)"
    assert win.save()
    assert on_disk(folder)["active_id"] == "STRAT-001"
    assert on_disk(folder)["overlays"] == []


def test_a_stops_fields_follow_its_tick(root, folder):
    win = open_window(root, folder)
    box = win._overlay_frames["OVL-ATR"]
    fields = [w for w in box.winfo_children() if isinstance(w, ttk.Spinbox)]
    assert fields and all(w.instate(["disabled"]) for w in fields)
    tick = next(
        w
        for w in widgets(win)
        if isinstance(w, ttk.Checkbutton) and str(w.cget("text")) == "ATR trailing stop"
    )
    tick.invoke()
    assert win.overlay_on["OVL-ATR"].get()
    assert all(not w.instate(["disabled"]) for w in fields)
    win.destroy()


# --- its row in Settings --------------------------------------------------------------


@pytest.fixture
def hub(monkeypatch):
    import helpers_trainer as ht
    import pt_hub

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    yield hub
    ht.close_hub(hub)


def test_settings_shows_the_strategy_and_opens_its_window(hub):
    from test_settings_window import label_texts
    from test_trainer_launch import open_settings, press

    win = open_settings(hub)
    line = "Trend crossover (DEMA/TEMA) on 1-hour candles; stops and filters: none"
    assert line in label_texts(win)
    press(win, "Strategy...")
    strategy_win = hub._strategy_settings_win
    assert isinstance(strategy_win, ui.StrategySettingsWindow)
    strategy_win.withdraw()
    press(win, "Strategy...")  # raises the open one rather than opening another
    assert hub._strategy_settings_win is strategy_win
    strategy_win.withdraw()

    strategy_win.timeframe_var.set("4 hours")
    strategy_win.overlay_on["OVL-ATR"].set(True)
    assert strategy_win.save()
    assert (
        "Trend crossover (DEMA/TEMA) on 4-hour candles; stops and filters: "
        "ATR trailing stop"
    ) in label_texts(win)
    s = read_strategy_settings()  # pt_config.json, where the trader reads it
    assert (s.timeframe, [o["id"] for o in s.overlays]) == ("4h", ["OVL-ATR"])
    win.destroy()
