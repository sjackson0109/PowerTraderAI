"""The table every tab of the bottom panel shows (ui_table.DataTable; owner,
2026-11-04): it says when it has no rows, its scrollbars are its own and show only
while the rows or columns overflow, columns fit their content, a heading click
sorts, and widths and sort order are kept per table.

A real Tk window, shown fully transparent (sizes exist only once a window is
mapped), under the isolation guard (app/conftest.py).
"""

import os
import sys
from types import SimpleNamespace

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import ui_table  # noqa: E402

COLUMNS = ("coin", "qty", "value")
HEADINGS = {"coin": "Coin", "qty": "Qty", "value": "Value"}


@pytest.fixture
def layout_file(tmp_path, monkeypatch):
    path = str(tmp_path / "table_layout.json")
    monkeypatch.setattr(ui_table, "LAYOUT_PATH", path)
    ui_table.forget_layouts()
    yield path
    ui_table.forget_layouts()


@pytest.fixture
def root(layout_file):
    import tkinter as tk
    from tkinter import ttk

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
    win.geometry("600x300+0+0")
    ui_theme.apply_theme(win, ttk.Style(win), ui_tokens.DARK)
    yield win
    try:
        win.destroy()
    except tk.TclError:
        pass


def table(root, key=None, **kw):
    t = ui_table.DataTable(
        root, COLUMNS, HEADINGS, key=key, numeric=("qty", "value"), **kw
    )
    t.pack(fill="both", expand=True)
    settle(root, t)
    return t


def settle(root, t):
    for _ in range(3):
        root.update()
        t.settle()
    root.update()


def cells(t, column):
    i = t.columns.index(column)
    return [str(t.tree.item(iid, "values")[i]) for iid in t.tree.get_children()]


def test_an_empty_table_says_so_and_shows_no_scrollbar(root):
    t = table(root)
    assert t.is_empty_shown()
    assert t.empty.cget("text") == "No trades yet"
    assert t.scrollbars_shown() == {"y": False, "x": False}
    t.tree.insert("", "end", values=("BTC", "1", "$5.00"))
    settle(root, t)
    assert not t.is_empty_shown()
    t.tree.delete(*t.tree.get_children())
    settle(root, t)
    assert t.is_empty_shown()


def test_a_few_rows_show_no_scrollbar(root):
    t = table(root)
    for n in range(3):
        t.tree.insert("", "end", values=(f"C{n}", n, f"${n:,.2f}"))
    settle(root, t)
    assert t.scrollbars_shown() == {"y": False, "x": False}
    assert not t.ysb.winfo_ismapped() and not t.xsb.winfo_ismapped()


def test_many_rows_and_wide_columns_scroll_along_the_whole_table(root):
    t = table(root)
    for n in range(200):
        t.tree.insert("", "end", values=("X" * 70 + str(n), n, f"${n * 1000:,.2f}"))
    t.min_widths = {"qty": 300, "value": 300}  # wider than the window together
    settle(root, t)
    assert t.scrollbars_shown() == {"y": True, "x": True}
    tree, ysb, xsb = t.tree, t.ysb, t.xsb
    # the vertical bar runs the table's full height on its right edge, the
    # horizontal one its full width directly under it
    assert ysb.winfo_height() == tree.winfo_height() > 100
    assert ysb.winfo_x() == tree.winfo_x() + tree.winfo_width()
    assert ysb.winfo_y() == tree.winfo_y()
    assert xsb.winfo_width() == tree.winfo_width() > 100
    assert xsb.winfo_y() == tree.winfo_y() + tree.winfo_height()
    assert xsb.winfo_x() == tree.winfo_x()
    # and they go again when the rows and columns fit
    t.tree.delete(*t.tree.get_children()[3:])
    t.min_widths = {}
    settle(root, t)
    assert t.scrollbars_shown() == {"y": False, "x": False}


def test_columns_fit_their_content_and_numbers_sit_right(root):
    t = table(root)
    t.tree.insert("", "end", values=("BTC", "1", "$5.00"))
    settle(root, t)
    short = t._fit["coin"]
    t.tree.insert("", "end", values=("A much longer coin name", "1", "$5.00"))
    settle(root, t)
    assert t._fit["coin"] > short
    # the table runs the panel's full width
    assert sum(t.column_widths().values()) == t.tree.winfo_width()
    assert str(t.tree.column("coin", "anchor")) == "w"
    assert str(t.tree.column("qty", "anchor")) == "e"
    assert str(t.tree.column("value", "anchor")) == "e"


def test_a_heading_click_sorts_numbers_as_numbers_and_again_reverses(root):
    t = table(root)
    for value in ("$999.00", "N/A", "$1,000.00", "$5.00", "-$20.00"):
        t.tree.insert("", "end", values=("C", "1", value))
    settle(root, t)
    assert cells(t, "value")[0] == "$999.00"  # insertion order until a click
    root.tk.call(t.tree.heading("value", "command"))
    settle(root, t)
    # a cell with no number goes last, whichever way
    assert cells(t, "value") == ["-$20.00", "$5.00", "$999.00", "$1,000.00", "N/A"]
    assert t.tree.heading("value", "text") == "Value ▲"
    root.tk.call(t.tree.heading("value", "command"))
    settle(root, t)
    assert cells(t, "value") == ["$1,000.00", "$999.00", "$5.00", "-$20.00", "N/A"]
    assert t.tree.heading("value", "text") == "Value ▼"
    assert t.sort_order == ("value", True)


def test_rows_added_later_take_the_sort_and_a_new_heading_keeps_its_mark(root):
    t = table(root, sort=("coin", False))
    for coin in ("SOL", "BTC"):
        t.tree.insert("", "end", values=(coin, "1", "$1.00"))
    settle(root, t)
    t.tree.insert("", "end", values=("ADA", "1", "$1.00"))
    settle(root, t)
    assert cells(t, "coin") == ["ADA", "BTC", "SOL"]
    t.tree.heading("coin", text="Coin (3)")
    assert t.tree.heading("coin", "text") == "Coin (3) ▲"


def test_widths_and_sort_order_are_kept_per_table(root, layout_file):
    t = table(root, key="probe")
    t.tree.insert("", "end", values=("BTC", "1", "$5.00"))
    settle(root, t)
    # a drag on a heading's edge: Tk resizes the column, the release keeps it
    t._dragging = True
    t.tree.column("coin", width=233)
    t._on_release(None)
    t.sort_by("qty", descending=True)
    assert os.path.isfile(layout_file)

    ui_table.forget_layouts()  # as after a restart
    again = table(root, key="probe")
    assert again.sort_order == ("qty", True)
    assert again.column_widths()["coin"] == 233
    other = table(root, key="another")
    assert other.sort_order is None and "coin" not in other._user


def test_a_double_click_on_a_heading_edge_fits_the_column_again(root):
    t = table(root, key="probe")
    t.tree.insert("", "end", values=("BTC", "1", "$5.00"))
    settle(root, t)
    t._dragging = True
    t.tree.column("coin", width=233)
    t._on_release(None)
    edge = t.column_widths()["coin"]
    assert t.tree.identify_region(edge, 5) == "separator"
    assert t._on_double(SimpleNamespace(x=edge, y=5)) == "break"
    settle(root, t)
    assert "coin" not in t._user


def test_a_cell_number_is_read_from_its_text():
    assert ui_table.number_in("$1,234.50") == 1234.5
    assert ui_table.number_in("-$5.00") == -5.0
    assert ui_table.number_in("+2.50%") == 2.5
    assert ui_table.number_in("1/2") == 1.0
    assert ui_table.number_in("N/A") is None
    assert ui_table.number_in("") is None


def test_the_table_draws_no_border_of_its_own(root):
    from tkinter import ttk

    layout = ttk.Style(root).layout(ui_table.STYLE)
    assert [element for element, _opts in layout] == ["Treeview.treearea"]


@pytest.mark.parametrize("scrolled", [False, True])
def test_a_text_pane_shows_its_scrollbar_only_while_the_text_overflows(root, scrolled):
    import tkinter as tk
    from tkinter import scrolledtext, ttk

    holder = ttk.Frame(root)
    holder.pack(fill="both", expand=True)
    if scrolled:  # a ScrolledText's own bar is replaced by a themed one
        text = scrolledtext.ScrolledText(holder, height=5)
        text.pack(fill="both", expand=True)
        ui_table.scroll_when_needed(text)
        bar = text.vbar
        assert isinstance(bar, ttk.Scrollbar)
    else:
        text = tk.Text(holder, height=5)
        bar = ttk.Scrollbar(holder, orient="vertical")
        ui_table.scroll_when_needed(text, bar)
    text.insert("end", "one line")
    root.update()
    assert not bar.winfo_ismapped()
    text.insert("end", "\n".join(str(n) for n in range(200)))
    for _ in range(3):
        root.update()
    assert bar.winfo_ismapped()
    assert bar.winfo_height() == text.winfo_height()
    assert bar.winfo_x() == text.winfo_x() + text.winfo_width()
    text.delete("1.0", "end")
    for _ in range(3):
        root.update()
    assert not bar.winfo_ismapped()
