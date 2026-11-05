"""Every tab of the hub's bottom panel: one border, the panel's own, no inner title
that repeats the tab's name, and every table built by ui_table.DataTable (owner,
2026-11-04).

A real hub (hidden window) under the isolation guard (app/conftest.py); the module
windows' files are read as source, since building them starts their services.
"""

import os
import re
import sys

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import ui_table  # noqa: E402

# the module windows the bottom panel shows (pt_hub's _create_*_tab)
MODULE_WINDOWS = (
    "llm_research_gui.py",
    "long_term_holdings_gui.py",
    "advanced_order_gui.py",
    "real_time_market_data_gui.py",
    "portfolio_optimizer_gui.py",
    "backtesting_gui.py",
    "performance_attribution_gui.py",
    "institutional_trading_gui.py",
)


@pytest.fixture
def hub(monkeypatch, tmp_path):
    """The real hub, with its Long-term Holdings window (on the guard's temporary
    holdings.db); the other module windows are off."""
    import helpers_trainer as ht
    import long_term_holdings

    monkeypatch.setattr(ui_table, "LAYOUT_PATH", str(tmp_path / "table_layout.json"))
    ui_table.forget_layouts()
    monkeypatch.setattr(long_term_holdings, "_holdings_manager", None)
    monkeypatch.setattr(
        ht,
        "HEAVY_FLAGS",
        tuple(f for f in ht.HEAVY_FLAGS if f != "HOLDINGS_MANAGEMENT_AVAILABLE"),
    )
    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    yield hub
    ht.close_hub(hub)
    ui_table.forget_layouts()


def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)


def test_no_tab_repeats_its_name_and_every_table_is_a_data_table(hub):
    nb = hub.bottom_notebook
    names = [nb.tab(t, "text").replace("\n", " ") for t in nb.tabs()]
    # in the order pt_hub.MODULE_TAB_ORDER sets (test_hub_layout)
    assert {"Current Trades", "Long-term Holdings", "Trade History"} <= set(names)
    tables = 0
    for tab, name in zip(nb.tabs(), names):
        for w in walk(hub.nametowidget(tab)):
            cls = w.winfo_class()
            assert cls != "Listbox", f"{name}: a list, not a table"
            if cls in ("TLabel", "TLabelframe", "Label"):
                text = str(w.cget("text")).strip().lower()
                assert text != name.lower(), f"{name}: an inner title repeats it"
                assert "(scroll" not in text
            if cls == "TLabelframe":  # a titled group draws no box of its own
                assert str(w.cget("style")) == "Flat.TLabelframe"
            if cls == "Treeview":
                assert isinstance(w.master, ui_table.DataTable), name
                assert str(w.cget("style")) == ui_table.STYLE
                tables += 1
    # Current Trades, Long-term Holdings (Holdings, Rebalancing), Trade History
    assert tables >= 4
    assert [n for n in names if "Holdings" in n] == ["Long-term Holdings"]


def test_a_tab_has_one_border_the_panels_own(hub):
    from tkinter import ttk

    import ui_theme

    p = ui_theme.active_palette()
    style = ttk.Style(hub)
    # the table: no border element at all
    assert [e for e, _ in style.layout(ui_table.STYLE)] == ["Treeview.treearea"]
    # the module windows' own notebooks and titled groups: borders in the
    # background colour
    for name in ("Inner.TNotebook", "Flat.TLabelframe"):
        for edge in ("bordercolor", "lightcolor", "darkcolor"):
            assert str(style.lookup(name, edge)).upper() == p["BG"].upper()
    # and the module windows get them without asking: whatever a tab builds
    tab = hub.nametowidget(hub.bottom_notebook.tabs()[-1])
    inner = ttk.Notebook(tab)
    group = ttk.LabelFrame(ttk.Frame(tab), text="Group")
    assert str(inner.cget("style")) == "Inner.TNotebook"
    assert str(group.cget("style")) == "Flat.TLabelframe"
    # a dialog opened from a tab keeps the usual look
    import tkinter as tk

    dialog = tk.Toplevel(tab)
    try:
        assert str(ttk.LabelFrame(dialog, text="x").cget("style")) == "TLabelframe"
    finally:
        dialog.destroy()
    # the hub's own tabs, and Long-term Holdings' sub-tabs: the table straight in
    # the tab, no frame round it
    holdings = hub.holdings_gui
    assert str(holdings.notebook.cget("style")) == "Inner.TNotebook"
    for table in (
        hub.trades_table,
        holdings.holdings_table,
        holdings.suggestions_table,
        hub.trade_history_view.table,
    ):
        assert str(table.cget("style")) in ("", "TFrame")
        assert str(table.pack_info()["fill"]) == "both"
        assert str(table.pack_info()["expand"]) in ("1", "True")
    assert holdings.holdings_table.master is holdings.holdings_tab
    assert holdings.suggestions_table.master is holdings.rebalancing_tab


@pytest.mark.parametrize("module", MODULE_WINDOWS)
def test_every_module_window_builds_its_tables_with_data_table(module):
    with open(os.path.join(APP_DIR, module), encoding="utf-8") as f:
        source = f.read()
    assert not re.findall(r"\bttk\.Treeview\(", source)
    assert not re.findall(r"\bListbox\(", source)
    if "DataTable(" in source:
        assert "import ui_table" in source
