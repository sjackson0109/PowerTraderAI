"""The LLM Research tab (llm_research_gui): Market Analysis on the coins in Settings,
Detailed Analysis with the model's own text, auto-refresh with its cost, Trade
Signals with outcomes, scores and filters, Research Reports saved as Markdown, the
prompt editor, one border and no thread left running.

A real Tk window (alpha 0) under the isolation guard (app/conftest.py); the exchange
layer and every provider request are fakes (helpers_llm).
"""

import os
import re
import sys
import tkinter as tk
from tkinter import ttk

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import llm_research_gui as gui_mod  # noqa: E402
import pt_paths  # noqa: E402
import pt_secrets  # noqa: E402
import ui_table  # noqa: E402
from helpers_llm import (  # noqa: E402
    OPENAI,
    FakeHttp,
    FakeLayer,
    answer_for,
    chat_answer,
    make_engine,
    ollama_routes,
    openai_models,
)
from llm_store import LLMStore, SignalRecord  # noqa: E402

COINS = ["ZEC", "XRP", "BTC"]


@pytest.fixture
def layout_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_table, "LAYOUT_PATH", str(tmp_path / "table_layout.json"))
    ui_table.forget_layouts()
    yield
    ui_table.forget_layouts()


@pytest.fixture
def root(layout_file):
    import ui_theme
    import ui_tokens

    win, error = None, None
    for _ in range(10):  # Tk sometimes fails to read init.tcl on the first try
        try:
            win = tk.Tk()
            break
        except tk.TclError as exc:
            error = exc
    if win is None:
        pytest.skip(f"Tk not available: {error}")
    win.attributes("-alpha", 0.0)
    win.geometry("1300x760+0+0")
    ui_theme.apply_theme(win, ttk.Style(win), ui_tokens.DARK)
    yield win
    try:
        win.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def store(tmp_path):
    return LLMStore(str(tmp_path / "llm.db"))


class Box:
    def __init__(self, answer=True):
        self.answer = answer
        self.asked = []

    def askokcancel(self, title, message, **_):
        self.asked.append(message)
        return self.answer


def panel(root):
    """A notebook like the hub's bottom panel: what is built inside draws no border
    of its own."""
    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)
    ui_table.borderless_inside(nb)
    tab = ttk.Frame(nb)
    nb.add(tab, text="LLM\nResearch")
    return tab


def build(root, store, http, box=None, settings=None, layer=None, coins=COINS):
    engine = make_engine(store, http, settings=settings, layer=layer)
    gui = gui_mod.ResearchEngineGUI(
        panel(root),
        engine=engine,
        coins=lambda: list(coins),
        messagebox=box or Box(),
        refresh_ms=0,
        score_minutes=0,
    )
    gui.jobs.drain()  # the symbol lookup
    root.update()
    return gui


def rows(table):
    return [table.tree.item(i, "values") for i in table.tree.get_children()]


def test_the_tab_has_three_sub_tabs_and_no_settings(root, store):
    gui = build(root, store, FakeHttp(ollama_routes(answer_for)))
    names = [
        gui.notebook.tab(t, "text").replace("\n", " ") for t in gui.notebook.tabs()
    ]
    assert names == ["Market Analysis", "Trade Signals", "Research Reports"]


def test_market_analysis_runs_on_the_coins_in_settings_with_no_typing(root, store):
    http = FakeHttp(ollama_routes(answer_for))
    gui = build(root, store, http)
    # the Symbols box holds the coins in Settings, in the connected exchange's format
    assert gui.symbol_var.get() == "ZEC-USD, XRP-USD, BTC-USD"
    assert gui.run_market_analysis()
    gui.jobs.drain()
    shown = {r[0]: r for r in rows(gui.analysis_table)}
    assert set(shown) == set(COINS)
    coin, pair, price, change, rsi, signal, provider, model, prompt, _ = shown["XRP"]
    assert (pair, signal, provider, model, prompt) == (
        "XRP-USD",
        "BUY",
        "Ollama",
        "local:7b",
        "v1",
    )
    assert price and change.endswith("%") and rsi
    # each analysis asked for that coin's signal too
    assert sorted(s.coin for s in store.signals() if s.source == "analysis") == sorted(
        COINS
    )
    assert len(gui.signals) == 3
    assert gui.answered_var.get().startswith("Answered by Ollama (local:7b)")
    assert gui.warning_var.get() == ""


def test_detailed_analysis_shows_the_models_text_for_the_selected_coin(root, store):
    gui = build(root, store, FakeHttp(ollama_routes(answer_for)))
    gui.run_market_analysis()
    gui.jobs.drain()
    gui.analysis_tree.selection_set("BTC")
    gui.on_analysis_select()
    text = gui.analysis_details.get("1.0", "end-1c")
    assert "BTC is in a steady rise on the hourly chart." in text
    assert "##" not in text and "**" not in text  # rendered, not shown as typed
    first = gui.analysis_details.search("Summary", "1.0")
    assert "h2" in gui.analysis_details.tag_names(first)
    bold = gui.analysis_details.search("steady rise", "1.0")
    assert "bold" in gui.analysis_details.tag_names(bold)
    assert "• RSI is firm" in text
    meta = gui.details_meta.get()
    assert "BTC BTC-USD" in meta and "Ollama · local:7b · analysis prompt v1" in meta
    gui.analysis_tree.selection_set("ZEC")
    gui.on_analysis_select()
    assert "ZEC is in a steady rise" in gui.analysis_details.get("1.0", "end-1c")


def test_with_ollama_stopped_the_next_provider_answers_and_a_warning_shows(
    root, store, memory_keyring
):
    pt_secrets.set_secret("openai", "api_key", "sk")
    http = FakeHttp(
        {
            ("GET", OPENAI + "/models"): openai_models(("paid-model", 3)),
            ("POST", OPENAI + "/chat/completions"): lambda m, u, h, body, t: __import__(
                "llm_providers"
            ).HttpResponse(
                200, chat_answer(answer_for(body["messages"][-1]["content"]))[1]
            ),
        }
    )  # nothing answers on localhost
    gui = build(
        root,
        store,
        http,
        settings={"preferred": "ollama", "fallbacks": ["openai"]},
        coins=["BTC"],
    )
    gui.run_market_analysis()
    gui.jobs.drain()
    (row,) = rows(gui.analysis_table)
    assert (row[6], row[7]) == ("OpenAI", "paid-model")
    assert gui.warning_var.get().startswith(
        "Answered by OpenAI, a paid provider, in place of Ollama"
    )
    assert str(gui.warning_label.cget("style")) == "Warn.TLabel"
    gui.analysis_tree.selection_set("BTC")
    gui.on_analysis_select()
    assert "a paid provider" in gui.details_meta.get()


def test_the_symbols_box_is_an_override_with_a_reset(root, store):
    http = FakeHttp(ollama_routes(answer_for))
    gui = build(root, store, http)
    gui.symbol_var.set("btc-usd, ethusdt")
    assert gui.selected_coins() == ["BTC", "ETH"]
    gui.reset_symbols()
    gui.jobs.drain()
    assert gui.symbol_var.get() == "ZEC-USD, XRP-USD, BTC-USD"
    gui.symbol_var.set("")
    assert gui.selected_coins() == COINS  # empty: the coins in Settings


def test_auto_refresh_shows_its_cost_before_it_starts(root, store, memory_keyring):
    pt_secrets.set_secret("openai", "api_key", "sk")
    http = FakeHttp(
        {
            **ollama_routes(answer_for),
            ("GET", OPENAI + "/models"): openai_models(("m", 1)),
        }
    )
    settings = {
        "preferred": "ollama",
        "fallbacks": ["openai"],
        "providers": {"openai": {"model": "m"}},
        "prices": {"openai": {"m": {"input": 2.0, "output": 8.0}}},
    }
    box = Box(answer=False)
    gui = build(root, store, http, box=box, settings=settings)
    assert gui.cost_var.get() == "Ollama: free (runs on this computer)"
    gui.refresh_interval.set("30")
    gui.auto_refresh.set(True)
    assert not gui.toggle_auto_refresh()  # declined: stays off
    assert not gui.auto_refresh.get() and "auto" not in gui.timers()
    message = box.asked[-1]
    assert "Ollama: free (runs on this computer)" in message
    assert re.search(
        r"OpenAI \(m\), if it answers: \$\d+\.\d{4} per refresh, \$\d+\.\d\d a day",
        message,
    )
    box.answer = True
    gui.auto_refresh.set(True)
    assert gui.toggle_auto_refresh()
    assert "auto" in gui.timers()
    gui.auto_refresh.set(False)
    gui.toggle_auto_refresh()
    assert "auto" not in gui.timers()


def test_an_unknown_price_is_shown_as_not_known(root, store, memory_keyring):
    pt_secrets.set_secret("openai", "api_key", "sk")
    http = FakeHttp({("GET", OPENAI + "/models"): openai_models(("m", 1))})
    gui = build(
        root,
        store,
        http,
        settings={"preferred": "openai", "providers": {"openai": {"model": "m"}}},
    )
    assert (
        gui.cost_var.get() == "OpenAI (m): cost not known (no price set for the model)"
    )


def test_the_splitter_keeps_detailed_analysis_at_its_minimum_height(root, store):
    gui = build(root, store, FakeHttp(ollama_routes(answer_for)))
    gui.notebook.select(gui.analysis_tab)
    root.update()
    paned = gui.analysis_paned
    assert len(paned.panes()) == 2
    total = paned.winfo_height()
    assert total > gui_mod.MIN_TOP_PX + gui_mod.MIN_DETAIL_PX
    assert total - int(paned.sashpos(0)) >= gui_mod.MIN_DETAIL_PX
    paned.sashpos(0, total - 5)
    gui.clamp_sash()
    assert total - int(paned.sashpos(0)) >= gui_mod.MIN_DETAIL_PX
    paned.sashpos(0, 5)
    gui.clamp_sash()
    assert int(paned.sashpos(0)) >= gui_mod.MIN_TOP_PX


def test_signals_show_their_source_outcome_and_score_with_filters(root, store):
    gui = build(root, store, FakeHttp(ollama_routes(answer_for)))
    base = dict(
        coin="BTC", pair="BTC-USD", provider="ollama", prompt_version=1, price=100.0
    )
    a = store.add_signal(
        SignalRecord(
            ts=1.0, model="m1", direction="BUY", confidence=80, source="entry", **base
        )
    )
    store.set_outcome(a.id, "target", 0.031, True, 104.0)
    b = store.add_signal(
        SignalRecord(ts=2.0, model="m2", direction="SELL", confidence=40, **base)
    )
    store.set_outcome(b.id, "stop", -0.02, False, 102.0)
    store.add_signal(
        SignalRecord(
            ts=3.0, model="m2", direction="HOLD", **dict(base, prompt_version=2)
        )
    )
    gui.reload_signals()
    shown = {r[11]: r for r in rows(gui.signals_table)}
    assert shown["m1"][13:] == ("at an entry", "target reached", "+3.10%")
    assert shown["m2"][3] in ("SELL", "HOLD")
    assert gui.signal_summary.get().startswith(
        "3 signals shown, 2 scored, 1 won after fees (50%)"
    )
    gui.model_filter.set("m2")
    gui.apply_signal_filter()
    assert {r[11] for r in rows(gui.signals_table)} == {"m2"}
    gui.prompt_filter.set("v2")
    gui.apply_signal_filter()
    assert [r[3] for r in rows(gui.signals_table)] == ["HOLD"]
    gui.prompt_filter.set("All")
    gui.model_filter.set("All")
    gui.signal_filter.set(gui_mod.HIGH_CONFIDENCE)
    gui.apply_signal_filter()
    assert [r[11] for r in rows(gui.signals_table)] == ["m1"]
    gui.signal_filter.set("All")
    gui.signal_search_var.set("stop reached")
    gui.apply_signal_filter()
    assert [r[3] for r in rows(gui.signals_table)] == ["SELL"]
    scores = {(r[1], r[2]): r for r in rows(gui.scores_table)}
    assert scores[("m1", "v1")][3:8] == ("1", "1", "1", "100%", "+3.10%")
    assert scores[("m1", "v1")][8] == "not passed"  # 1 of 20 signals


def test_generate_signals_asks_for_each_coin_and_shows_the_reasoning(root, store):
    gui = build(root, store, FakeHttp(ollama_routes(answer_for)))
    assert gui.generate_trade_signals()
    gui.jobs.drain()
    assert sorted(s.coin for s in store.signals()) == sorted(COINS)
    first = gui.signals_tree.get_children()[0]
    gui.signals_tree.selection_set(first)
    gui.on_signal_select()
    assert "Momentum for" in gui.signal_details.get("1.0", "end-1c")
    assert "signal prompt v1" in gui.signal_meta.get()


def test_sorting_and_search_on_the_analysis_results(root, store):
    gui = build(root, store, FakeHttp(ollama_routes(answer_for)))
    gui.run_market_analysis()
    gui.jobs.drain()
    gui.analysis_table.sort_by("coin", descending=False)
    assert [r[0] for r in rows(gui.analysis_table)] == ["BTC", "XRP", "ZEC"]
    gui.analysis_table.sort_by("coin", descending=True)
    assert [r[0] for r in rows(gui.analysis_table)] == ["ZEC", "XRP", "BTC"]
    gui.analysis_search_var.set("xrp")
    assert [r[0] for r in rows(gui.analysis_table)] == ["XRP"]


def test_a_report_is_markdown_and_saved_with_its_source(root, store):
    gui = build(root, store, FakeHttp(ollama_routes(answer_for)))
    assert "disabled" in gui.save_report_btn.state()
    assert gui.save_report() is None
    assert gui.generate_report()
    gui.jobs.drain()
    assert "disabled" not in gui.save_report_btn.state()
    text = gui.report_display.get("1.0", "end-1c")
    assert text.startswith("Market Overview") and "#" not in text
    path = gui.save_report()
    assert path.startswith(pt_paths.data_dir()) and path.endswith(".md")
    with open(path, encoding="utf-8") as f:
        saved = f.read()
    for line in (
        "provider: Ollama",
        "model: local:7b",
        "prompt_version: report v1",
        "generated: ",
    ):
        assert line in saved
    assert saved.endswith("All coins rose.\n")


def test_the_prompt_editor_saves_versions_and_restores_one(root, store):
    gui = build(root, store, FakeHttp(ollama_routes(answer_for)))
    editor = gui.open_prompt("signal")
    sent = gui.engine.prompt("signal").template
    assert editor.editor.get("1.0", "end-1c") == sent  # the exact template sent
    editor.editor.insert("end", "\nKeep it short.")
    v2 = editor.save()
    assert (
        v2.version == 2
        and "logged only until this version passes the gate" in editor.status_var.get()
    )
    editor.versions.settle()
    assert [str(r[0]) for r in rows(editor.versions)] == ["2", "1"]  # newest first
    editor.versions.tree.selection_set("1")
    editor._show_selected()
    assert editor.use_selected().version == 1
    assert gui.engine.prompt("signal").version == 1
    editor.destroy()


def test_one_border_text_panes_and_tables(root, store):
    """No box round a table or a text pane: the panel's border is the only one."""
    gui = build(root, store, FakeHttp(ollama_routes(answer_for)))

    def walk(w):
        for c in w.winfo_children():
            yield c
            yield from walk(c)

    widgets = list(walk(gui.research_frame))
    assert not [w for w in widgets if w.winfo_class() in ("TLabelframe", "Labelframe")]
    for w in widgets:
        if w.winfo_class() == "Treeview":
            assert isinstance(w.master, ui_table.DataTable)
        if w.winfo_class() == "Text":
            assert (
                int(w.cget("borderwidth")) == 0
                and int(w.cget("highlightthickness")) == 0
            )
            # its own scrollbar, in the same holder, shown only when it overflows
            bars = [
                s for s in w.master.winfo_children() if s.winfo_class() == "TScrollbar"
            ]
            assert len(bars) == 1 and not bars[0].winfo_ismapped()
    assert str(gui.notebook.cget("style")) == "Inner.TNotebook"


def test_timers_and_the_worker_stop_when_the_tab_is_destroyed(root, store):
    engine = make_engine(store, FakeHttp(ollama_routes(answer_for)))
    gui = gui_mod.ResearchEngineGUI(
        panel(root),
        engine=engine,
        coins=lambda: COINS,
        messagebox=Box(),
        refresh_ms=50,
        score_minutes=1,
    )
    gui.jobs.drain()
    gui.auto_refresh.set(True)
    gui.toggle_auto_refresh()
    assert gui.timers() == ["auto", "score", "signals"]
    thread = gui.jobs.thread
    gui.research_frame.master.master.destroy()
    assert gui.timers() == [] and not gui.alive
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_no_model_name_or_symbol_is_written_in_the_llm_research_code():
    """The models come from each provider's list and the symbols from the exchange
    layer: neither is written in the code."""
    files = [
        "llm_research_gui.py",
        "llm_research_engine.py",
        "llm_providers.py",
        "llm_settings.py",
        "llm_settings_ui.py",
        "llm_signals.py",
        "llm_gate.py",
        "llm_store.py",
    ]
    model_names = re.compile(
        r"\b(?:gpt-|claude-|llama|mistral|gemma|qwen|phi-?\d|deepseek|nemotron|mixtral"
        r"|o1-|o3-)",
        re.IGNORECASE,
    )
    symbols = re.compile(
        r"\b(?:BTC|ETH|ADA|BNB|XRP|SOL|DOGE|ZEC|DASH|HYPE)(?:-?USDT?C?|/USD)?\b"
    )
    for name in files:
        with open(os.path.join(APP_DIR, name), encoding="utf-8") as f:
            source = f.read()
        assert not model_names.findall(source), name
        assert not symbols.findall(source), (name, symbols.findall(source))
        assert "USDT" not in source, name


def test_the_hub_builds_the_tab_on_its_coins_and_stops_it_on_close(monkeypatch, store):
    import helpers_trainer as ht
    import pt_hub

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    thread = None
    try:
        engine = make_engine(store, FakeHttp(ollama_routes(answer_for)))
        monkeypatch.setattr(gui_mod, "LLMResearchEngine", lambda: engine)
        monkeypatch.setattr(pt_hub, "LLM_RESEARCH_AVAILABLE", True)
        hub._create_llm_research_tab()
        gui = hub.research_gui
        assert gui.coins() == list(hub.coins)
        assert str(gui.notebook.cget("style")) == "Inner.TNotebook"
        gui.jobs.drain()
        assert gui.symbol_var.get() == ", ".join(f"{c}-USD" for c in hub.coins)
        thread = gui.jobs.thread
    finally:
        ht.close_hub(hub)
    assert thread is not None
    thread.join(timeout=5)
    assert not thread.is_alive()
