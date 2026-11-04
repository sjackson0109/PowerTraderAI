"""Settings > LLM Providers (llm_settings_ui) and its rows in the hub's Settings.

A hidden Tk root under the isolation guard (app/conftest.py): pt_config.json is in a
temporary folder, keys go to the in-memory keyring, and every provider request goes
to a fake transport.
"""

import json
import os
import sys
import tkinter as tk
from tkinter import ttk

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import llm_providers as lp  # noqa: E402
import llm_settings  # noqa: E402
import pt_paths  # noqa: E402
import pt_secrets  # noqa: E402
from helpers_llm import OLLAMA, OPENAI, FakeHttp, openai_models  # noqa: E402
from llm_settings_ui import LLMProvidersWindow, summary_line  # noqa: E402
from llm_store import LLMStore, SignalRecord  # noqa: E402
from pt_settings_manager import SettingsManager  # noqa: E402


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


@pytest.fixture
def http():
    return FakeHttp(
        {
            ("GET", OLLAMA + "/api/version"): (200, {}),
            ("GET", OLLAMA + "/api/tags"): (200, {"models": [{"name": "local:7b"}]}),
            ("GET", OPENAI + "/models"): openai_models(("old", 1), ("new", 9)),
        }
    )


@pytest.fixture
def store(tmp_path):
    return LLMStore(str(tmp_path / "llm.db"))


def open_window(root, http, store, box=None):
    holder = {}
    router = lp.LLMRouter(
        settings=lambda: holder["win"].working, store=store, transport=http
    )
    win = LLMProvidersWindow(root, router=router, store=store, messagebox=box or Box())
    holder["win"] = win
    win.withdraw()
    return win


def saved_llm():
    with open(pt_paths.settings_file(), encoding="utf-8") as f:
        return json.load(f)["llm"]


def test_every_provider_has_a_row_with_its_status(root, http, store, memory_keyring):
    win = open_window(root, http, store)
    states = {
        p: str(win.rows[p]["status"].cget("text")) for p in llm_settings.PROVIDERS
    }
    assert states == {
        "ollama": "not tested",
        "openai": "not configured",
        "anthropic": "not configured",
        "nvidia": "not configured",
    }
    assert "free: runs on this computer" in str(
        win.rows["ollama"]["detail"].cget("text")
    )
    assert "no API key" in str(win.rows["openai"]["detail"].cget("text"))
    win.destroy()


def test_a_key_set_up_goes_to_the_credential_store_never_the_file(
    root, http, store, memory_keyring
):
    win = open_window(root, http, store)
    setup = win.open_setup("openai")
    setup.withdraw()
    setup.key_var.set("sk-secret-1")
    setup.cap_var.set("5")
    assert setup.save()
    assert pt_secrets.get_secret("openai", "api_key").reveal() == "sk-secret-1"
    assert str(win.rows["openai"]["status"].cget("text")) == "not tested"
    assert "key in the OS credential store" in str(
        win.rows["openai"]["detail"].cget("text")
    )
    assert win.save()
    with open(pt_paths.settings_file(), encoding="utf-8") as f:
        text = f.read()
    assert "sk-secret-1" not in text
    assert json.loads(text)["llm"]["providers"]["openai"]["monthly_cap_usd"] == 5.0


def test_refresh_models_fills_the_picker_with_the_recommended_model_first(
    root, http, store, memory_keyring
):
    pt_secrets.set_secret("openai", "api_key", "sk")
    win = open_window(root, http, store)
    win.refresh_models("openai")
    win.jobs.drain()
    values = list(win.rows["openai"]["model_box"].cget("values"))
    assert values == ["Recommended: new", "old", "new"]
    win.rows["openai"]["model_var"].set("old")
    win._model_picked("openai")
    # with a model chosen, its price can be set
    setup = win.open_setup("openai")
    setup.withdraw()
    setup.in_var.set("2.5")
    setup.out_var.set("10")
    assert setup.save()
    assert win.save()
    saved = saved_llm()
    assert saved["providers"]["openai"]["model"] == "old"
    assert saved["prices"]["openai"]["old"] == {"input": 2.5, "output": 10.0}


def test_test_connection_shows_connected_or_error(root, http, store, memory_keyring):
    pt_secrets.set_secret("nvidia", "api_key", "nv")
    win = open_window(root, http, store)
    win.test_connection("ollama")
    win.test_connection("nvidia")  # nothing answers there
    win.jobs.drain()
    assert str(win.rows["ollama"]["status"].cget("text")) == "connected"
    assert str(win.rows["nvidia"]["status"].cget("text")).startswith("error: ")
    assert str(win.rows["nvidia"]["status"].cget("style")) == "Bad.TLabel"
    win.destroy()


def test_the_preferred_provider_and_the_fallback_order_are_saved(
    root, http, store, memory_keyring
):
    win = open_window(root, http, store)
    win.preferred_var.set("Anthropic")
    win._preferred_picked()
    for name in ("Ollama", "OpenAI"):
        win.add_var.set(name)
        win.add_fallback()
    win.fallback_table.tree.selection_set("openai")
    win.move_fallback(-1)
    assert [v for v in win.fallback_table.tree.get_children()] == ["openai", "ollama"]
    win.health_var.set("2")
    assert win.save()
    saved = saved_llm()
    assert (saved["preferred"], saved["fallbacks"]) == (
        "anthropic",
        ["openai", "ollama"],
    )
    assert saved["health_timeout_s"] == 2.0
    assert summary_line() == "Anthropic, then OpenAI, Ollama. LLM signals: log only."


def test_the_signal_settings_and_the_gate_are_shown_and_saved(
    root, http, store, memory_keyring
):
    for i in range(3):
        s = store.add_signal(
            SignalRecord(
                ts=1000 + i,
                coin="BTC",
                provider="ollama",
                model="local:7b",
                prompt_version=1,
                direction="BUY",
                trading_mode="paper",
            )
        )
        store.set_outcome(s.id, "target", 0.01, i < 2, 101.0)
    win = open_window(root, http, store)
    rows = {
        win.signal_table.tree.item(i, "values")[1]: win.signal_table.tree.item(
            i, "values"
        )
        for i in win.signal_table.tree.get_children()
    }
    assert rows["local:7b"][3:] == ("3", "67%", "not passed", "no")
    win.mode_var.set(llm_settings.SIGNAL_MODE_NAMES["veto"])
    win._show_mode_help()
    assert "does not open when the signal says sell" in str(win.mode_help.cget("text"))
    win.signal_table.tree.selection_set("ollama|local:7b|1")
    win.toggle_use()
    win.wait_var.set("4")
    assert win.save()
    saved = saved_llm()
    assert saved["signal_mode"] == "veto" and saved["signal_timeout_s"] == 4.0
    assert saved["signal_use"] == {"ollama|local:7b": True}


def test_a_value_that_is_not_a_number_saves_nothing(root, http, store):
    box = Box()
    win = open_window(root, http, store, box)
    win.answer_var.set("soon")
    assert not win.save()
    assert box.errors == ["Answer timeout: 'soon' is not a number"]
    assert not os.path.exists(pt_paths.settings_file()) or "llm" not in json.load(
        open(pt_paths.settings_file(), encoding="utf-8")
    )
    win.destroy()


def test_the_windows_worker_stops_when_it_closes(root, http, store, memory_keyring):
    win = open_window(root, http, store)
    win.test_connection("ollama")
    win.jobs.drain()
    thread = win.jobs.thread
    assert thread is not None and thread.is_alive()
    win.destroy()
    thread.join(timeout=5)
    assert not thread.is_alive()


# --- the hub's Settings ------------------------------------------------------------------


@pytest.fixture
def hub(monkeypatch):
    import helpers_trainer as ht
    import pt_hub

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    yield hub
    ht.close_hub(hub)


def test_settings_has_llm_providers_and_the_training_gate(hub):
    from test_trainer_launch import open_settings, press, type_into, widgets

    win = open_settings(hub)
    texts = [
        str(w.cget("text"))
        for w in widgets(win)
        if isinstance(w, (ttk.Label, ttk.Button)) and "text" in w.keys()
    ]
    for text in (
        "LLM Providers...",
        "Training",
        "Minimum scored signals:",
        "Minimum hit rate after fees %:",
    ):
        assert text in texts
    type_into(win, "Minimum scored signals:", "40")
    type_into(win, "Minimum hit rate after fees %:", "60")
    press(win, "Save")
    with open(pt_paths.settings_file(), encoding="utf-8") as f:
        training = json.load(f)["training"]
    assert training == {"holdout_min_signals": 40, "holdout_min_hit_rate": 0.6}
    llm_win = hub.open_llm_settings()
    try:
        assert isinstance(llm_win, LLMProvidersWindow)
        assert hub.open_llm_settings() is llm_win  # one window, raised again
    finally:
        llm_win.destroy()


def test_llm_research_has_no_settings_tab_of_its_own():
    with open(os.path.join(APP_DIR, "llm_research_gui.py"), encoding="utf-8") as f:
        source = f.read()
    for gone in ("create_settings_tab", "OpenAI API Key", "api_key_entry", "gpt-"):
        assert gone not in source
