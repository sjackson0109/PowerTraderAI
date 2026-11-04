"""The table every tab of the hub's bottom panel shows (owner, 2026-11-04).

One widget, so every tab's table looks and behaves the same:

* it fills its tab and draws no border of its own: the panel's is the only one;
* its scrollbars are its own: the vertical one runs its full height on its right
  edge, the horizontal one its full width directly under it, and each shows only
  while the rows or the columns overflow that way;
* columns fit their content; dragging a heading's edge resizes a column and a
  double-click on the edge fits it again; a click on a heading sorts by it (again
  to reverse). Widths and sort order are kept per table between sessions
  (``table_layout.json`` in the config folder);
* numbers are right-aligned, text left-aligned; the headings, row height and
  colours come from one style (``Table.Treeview``, ui_theme);
* with no rows it says so (``empty_text``, "No trades yet" by default).

``DataTable.tree`` is a ttk.Treeview: callers fill it as before (insert, delete,
item, selection, tag_configure ...). Once their changes are done (at idle) the
table sorts the rows, fits the columns and shows or hides the empty message;
``settle()`` does it at once.

``section(parent, title)`` is the plain frame with one short title line that
replaces a bordered LabelFrame around a table. ``borderless_inside(panel)`` makes
every notebook and titled group created inside ``panel`` draw no border of its own,
so ``panel``'s border is the only one (the module windows of the bottom panel).
``scroll_when_needed(text, bar)`` gives a text pane in a tab the same scrollbar
rule as the tables: shown only while its content overflows. ``SearchBox`` is a
toolbar's free-text search through every column of a table's rows.
"""

import json
import os
import re
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

STYLE = "Table.Treeview"
EMPTY_STYLE = "TableEmpty.TLabel"
SECTION_STYLE = "Header.TLabel"
LAYOUT_FILE = "table_layout.json"

CELL_PAD = 18  # pixels round a column's widest text
TREE = "#0"  # the tree column: a row's own name (show="tree headings")
TREE_INDENT = 24  # the tree column's indicator and indent, ahead of the name
MIN_WIDTH = 40
MAX_FIT = 420  # a fitted column is at most this wide: drag its edge for more
FIT_SAMPLE = 30  # the longest values of a column are the ones measured
SORT_MARKS = {False: " ▲", True: " ▼"}  # ascending, descending
SEARCH_DELAY_MS = 150  # a SearchBox searches this long after the last key

# a number inside a cell: "$1,234.56", "-$5.00", "+2.50%", "3/4", "0.0012 (stop)"
_NUMBER = re.compile(r"[-+]?(?:\d[\d,]*(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_CURRENCY = str.maketrans("", "", "$€£ ")

# where the layouts are kept; None: table_layout.json in pt_paths' config folder
LAYOUT_PATH: Optional[str] = None
_layouts: Optional[Dict[str, dict]] = None


def _layout_path() -> str:
    if LAYOUT_PATH:
        return LAYOUT_PATH
    import pt_paths

    return pt_paths.config_file(LAYOUT_FILE)


def _all_layouts() -> Dict[str, dict]:
    global _layouts
    if _layouts is None:
        try:
            with open(_layout_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            _layouts = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            _layouts = {}
    return _layouts


def saved_layout(key: str) -> dict:
    """The widths and sort order kept for table ``key`` ({} when none)."""
    entry = _all_layouts().get(key)
    return entry if isinstance(entry, dict) else {}


def save_layout(key: str, entry: dict) -> None:
    layouts = _all_layouts()
    layouts[key] = entry
    path = _layout_path()
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(layouts, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except OSError:
        pass  # a layout that can't be kept is only a convenience lost


def forget_layouts() -> None:
    """Read the layout file again on next use (tests, a new config folder)."""
    global _layouts
    _layouts = None


def number_in(text) -> Optional[float]:
    """The first number in a cell's text, or None ("N/A", "", "no stop yet")."""
    m = _NUMBER.search(str(text).translate(_CURRENCY))
    if not m:
        return None
    try:
        return float(m.group().replace(",", ""))
    except ValueError:
        return None


def section(
    parent: tk.Misc, title: Optional[str] = None, *, packed: bool = True, **pack
) -> ttk.Frame:
    """A plain frame for a table and its controls, with one short title line on top
    when ``title`` is given; no border, unlike the LabelFrame it replaces. Packed
    to fill the parent (``pack`` options override that) unless ``packed`` is
    False."""
    frame = ttk.Frame(parent)
    if title:
        ttk.Label(frame, text=title, style=SECTION_STYLE).pack(
            side="top", anchor="w", pady=(0, 2)
        )
    if packed:
        frame.pack(**{"fill": "both", "expand": True, **pack})
    return frame


def borderless_inside(panel: tk.Misc) -> None:
    """Every notebook and titled group (LabelFrame) created inside ``panel`` from now
    on draws no border of its own: the option database gives them Inner.TNotebook
    and Flat.TLabelframe (ui_theme), unless they name a style themselves. A dialog
    opened from inside keeps the usual look."""
    inside = "*" + str(panel).lstrip(".")
    panel.option_add(inside + "*TNotebook.Style", "Inner.TNotebook", "userDefault")
    panel.option_add(inside + "*TLabelframe.Style", "Flat.TLabelframe", "userDefault")
    panel.option_add("*Toplevel*TNotebook.Style", "TNotebook", "interactive")
    panel.option_add("*Toplevel*TLabelframe.Style", "TLabelframe", "interactive")


def scroll_when_needed(view: tk.Misc, bar: Optional[tk.Misc] = None) -> None:
    """Lay out ``view`` (a Text or Canvas) and its vertical scrollbar ``bar`` in
    their parent, which holds only the two of them: the bar on the view's right
    edge, its full height, shown only while the content overflows. A ScrolledText
    is given without ``bar``: its own bar is replaced by one in the theme's
    style."""
    if bar is None:  # a ScrolledText: its text and bar sit in its own frame
        view.vbar.destroy()
        bar = view.vbar = ttk.Scrollbar(view.master, orient="vertical")
    for widget in (view, bar):  # tk's own calls: a ScrolledText's are its frame's
        manager = widget.tk.call("winfo", "manager", widget._w)
        if manager in ("pack", "grid", "place"):
            widget.tk.call(manager, "forget", widget._w)
    parent = view.master
    tk.Grid.grid_configure(view, row=0, column=0, sticky="nsew")
    parent.rowconfigure(0, weight=1)
    parent.columnconfigure(0, weight=1)
    bar.configure(command=view.yview)
    shown = [False]

    def set_bar(first, last) -> None:
        bar.set(first, last)
        needed = float(first) > 0.0 or float(last) < 1.0
        if needed != shown[0]:
            shown[0] = needed
            if needed:
                bar.grid(row=0, column=1, sticky="ns")
            else:
                bar.grid_remove()

    view.configure(yscrollcommand=set_bar)


def subtitle(parent: tk.Misc, text: str) -> ttk.Label:
    """One short line of context above a tab's table (it wraps when the panel is
    narrower than the line)."""
    label = ttk.Label(parent, text=text, style="Muted.TLabel", anchor="w")
    label.pack(side="top", fill="x", padx=6, pady=(4, 4))

    def wrap(event) -> None:
        width = max(120, int(event.width) - 4)
        if int(label.cget("wraplength") or 0) != width:
            label.configure(wraplength=width)

    label.bind("<Configure>", wrap, add="+")
    return label


class SearchBox:
    """A toolbar's "Search" label and entry, packed left in ``bar`` (the entry takes
    the room left). ``on_change()`` runs SEARCH_DELAY_MS after the last key, or at
    once with ``now()``; ``matches(cells)`` says whether a row holds every word
    typed, each in any of its cells, in any case. The caller shows the rows that
    match and the table sorts them as before."""

    def __init__(self, bar: tk.Misc, on_change: Callable[[], None], *, width: int = 16):
        self._on_change = on_change
        self._after: Optional[str] = None
        self.var = tk.StringVar(master=bar)
        ttk.Label(bar, text="Search").pack(side="left", padx=(0, 4))
        self.entry = ttk.Entry(bar, textvariable=self.var, width=width)
        self.entry.pack(side="left", fill="x", expand=True)
        self.var.trace_add("write", lambda *_: self._changed())

    def _changed(self) -> None:
        self._cancel()
        try:
            self._after = self.entry.after(SEARCH_DELAY_MS, self.now)
        except tk.TclError:
            self._after = None  # the entry is gone

    def _cancel(self) -> None:
        if self._after is not None:
            try:
                self.entry.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def now(self) -> None:
        """Search at once."""
        self._cancel()
        self._on_change()

    def words(self) -> List[str]:
        return self.var.get().casefold().split()

    def matches(self, cells: Iterable) -> bool:
        words = self.words()
        if not words:
            return True
        text = " ".join(str(c) for c in cells).casefold()
        return all(w in text for w in words)


class _Tree(ttk.Treeview):
    """A Treeview that tells its table when rows or headings change."""

    def __init__(self, table: "DataTable", master: tk.Misc, **kw):
        self._table = table
        super().__init__(master, **kw)

    def insert(self, parent, index, iid=None, **kw):
        item = super().insert(parent, index, iid, **kw)
        self._table._changed()
        return item

    def delete(self, *items):
        super().delete(*items)
        self._table._changed()

    def item(self, item, option=None, **kw):
        result = super().item(item, option, **kw)
        if kw:
            self._table._changed()
        return result

    def set(self, item, column=None, value=None):
        result = super().set(item, column, value)
        if value is not None:
            self._table._changed()
        return result

    def heading(self, column, option=None, **kw):
        if "text" in kw and column in self._table.laid_out():
            self._table._titles[column] = str(kw["text"])
            kw["text"] = self._table._title(column)
            self._table._changed()
        return super().heading(column, option, **kw)


class DataTable(ttk.Frame):
    """A table filling its parent; see the module docstring.

    ``columns`` are the column ids; ``headings`` their titles (the id by default);
    ``numeric`` the ids of number columns (right-aligned, sorted as numbers);
    ``key`` names the table for its saved widths and sort order (None: not kept);
    ``sort`` is the order before the user picks one: (column, descending);
    ``sort_keys`` maps a column to its own sort key, from the cell's text;
    ``empty_text`` is shown while there are no rows.
    With ``show="tree headings"`` the tree column ("#0") holds each row's name (its
    ``text``); it is fitted and kept like the others, and its heading is set with
    ``tree.heading("#0", text=...)``.
    """

    def __init__(
        self,
        parent: tk.Misc,
        columns: Sequence[str],
        headings: Optional[Dict[str, str]] = None,
        *,
        key: Optional[str] = None,
        numeric: Iterable[str] = (),
        empty_text: str = "No trades yet",
        sort: Optional[Tuple[str, bool]] = None,
        sort_keys: Optional[Dict[str, Callable[[str], object]]] = None,
        sortable: bool = True,
        height: int = 10,
        show: str = "headings",
        selectmode: str = "extended",
        anchors: Optional[Dict[str, str]] = None,
        min_widths: Optional[Dict[str, int]] = None,
    ):
        super().__init__(parent)
        self.columns: List[str] = list(columns)
        self.tree_column = "tree" in show
        self.key = key
        self.numeric = set(numeric)
        self.sortable = sortable
        self.sort_keys = dict(sort_keys or {})
        self.min_widths = dict(min_widths or {})
        self._titles: Dict[str, str] = {
            c: str((headings or {}).get(c, c)) for c in self.columns
        }
        self._fit: Dict[str, int] = {}
        self._user: Dict[str, int] = {}
        self._applied: Dict[str, int] = {}
        self._sort: Optional[Tuple[str, bool]] = None
        self._pending: Optional[str] = None
        self._dragging = False
        self._shown = {"y": False, "x": False}
        self._toggles = 0

        saved = saved_layout(key) if key else {}
        for c, w in (saved.get("widths") or {}).items():
            if c in self.laid_out() and isinstance(w, (int, float)) and w > 0:
                self._user[c] = max(MIN_WIDTH, int(w))
        s = saved.get("sort")
        if isinstance(s, (list, tuple)) and len(s) == 2 and s[0] in self.columns:
            self._sort = (str(s[0]), bool(s[1]))
        elif sort and sort[0] in self.columns:
            self._sort = (sort[0], bool(sort[1]))

        self.tree = _Tree(
            self,
            self,
            columns=self.columns,
            show=show,
            height=height,
            style=STYLE,
            selectmode=selectmode,
        )
        self.ysb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.xsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self._yset, xscrollcommand=self._xset)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        if self.tree_column:
            self._titles[TREE] = ""
            ttk.Treeview.column(self.tree, TREE, stretch=False)
        else:
            ttk.Treeview.column(self.tree, TREE, width=0, minwidth=0, stretch=False)
        for c in self.columns:
            anchor = (anchors or {}).get(c) or ("e" if c in self.numeric else "w")
            ttk.Treeview.column(self.tree, c, anchor=anchor, stretch=False)
            ttk.Treeview.heading(self.tree, c, text=self._title(c), anchor=anchor)
            if sortable:
                ttk.Treeview.heading(
                    self.tree, c, command=lambda col=c: self.sort_by(col)
                )

        self.empty = ttk.Label(self, text=empty_text, style=EMPTY_STYLE)
        self.tree.bind("<Configure>", lambda _e: self._layout(), add="+")
        self.tree.bind("<ButtonPress-1>", self._on_press, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.tree.bind("<Double-Button-1>", self._on_double, add="+")
        self._changed()

    # ---- the rows ----

    def _changed(self) -> None:
        if self._pending is None:
            try:
                self._pending = self.after_idle(self.settle)
            except tk.TclError:
                self._pending = None

    def settle(self) -> None:
        """Sort the rows, fit the columns and show or hide the empty message now."""
        if self._pending is not None:
            try:
                self.after_cancel(self._pending)
            except tk.TclError:
                pass
            self._pending = None
        try:
            rows = list(ttk.Treeview.get_children(self.tree, ""))
        except tk.TclError:
            return  # destroyed
        values = {iid: self._cells(iid) for iid in rows}
        if self._sort is not None:
            self._apply_sort(rows, values)
        names = (
            [str(ttk.Treeview.item(self.tree, iid, "text")) for iid in rows]
            if self.tree_column
            else []
        )
        self._fit_columns(values, names)
        self._show_empty(not rows)
        self._layout()

    def _cells(self, iid) -> List[str]:
        vals = ttk.Treeview.item(self.tree, iid, "values")
        cells = [str(v) for v in (vals or ())]
        return cells + [""] * (len(self.columns) - len(cells))

    def _show_empty(self, empty: bool) -> None:
        if empty:
            self.empty.place(in_=self.tree, relx=0.5, rely=0.5, anchor="center")
            self.empty.lift()
        else:
            self.empty.place_forget()

    def is_empty_shown(self) -> bool:
        return bool(self.empty.place_info())

    # ---- sorting ----

    @property
    def sort_order(self) -> Optional[Tuple[str, bool]]:
        """(column, descending), or None while the rows keep their own order."""
        return self._sort

    def sort_by(self, column: str, descending: Optional[bool] = None) -> None:
        """Sort by ``column``; without ``descending``, a second click on the same
        column reverses the order."""
        if column not in self.columns:
            return
        if descending is None:
            same = self._sort is not None and self._sort[0] == column
            descending = (not self._sort[1]) if same else False
        old = self._sort[0] if self._sort else None
        self._sort = (column, bool(descending))
        for c in {old, column} - {None}:
            ttk.Treeview.heading(self.tree, c, text=self._title(c))
        self._save()
        self.settle()

    def _sort_key(self, column: str, text: str):
        own = self.sort_keys.get(column)
        if own is not None:
            return own(text)
        if column in self.numeric:
            return number_in(text)
        return text.casefold() if text else None

    def _apply_sort(self, rows: List[str], values: Dict[str, List[str]]) -> None:
        column, descending = self._sort
        idx = self.columns.index(column)
        keyed = [(self._sort_key(column, values[iid][idx]), iid) for iid in rows]
        known = [k for k in keyed if k[0] is not None]
        # a cell with no value ("", "N/A") goes last whichever way the sort runs
        try:
            known.sort(key=lambda k: k[0], reverse=descending)
        except TypeError:
            known.sort(key=lambda k: str(k[0]), reverse=descending)
        order = [iid for _k, iid in known] + [iid for key, iid in keyed if key is None]
        if order != rows:
            for pos, iid in enumerate(order):
                self.tree.move(iid, "", pos)

    def _title(self, column: str) -> str:
        text = self._titles.get(column, column)
        if self._sort is not None and self._sort[0] == column:
            return text + SORT_MARKS[self._sort[1]]
        return text

    # ---- column widths ----

    def _fonts(self):
        style = ttk.Style(self)
        body = style.lookup(STYLE, "font") or "TkDefaultFont"
        head = style.lookup(STYLE + ".Heading", "font") or "TkHeadingFont"
        return _font(self, body), _font(self, head)

    def laid_out(self) -> List[str]:
        """The columns this table sizes: the tree column first, when shown."""
        return ([TREE] if self.tree_column else []) + self.columns

    def _fit_columns(
        self, values: Dict[str, List[str]], names: Sequence[str] = ()
    ) -> None:
        body, head = self._fonts()
        mark = max(head.measure(m) for m in SORT_MARKS.values())

        def widest(texts) -> int:
            longest = sorted({t for t in texts if t}, key=len, reverse=True)
            return max((body.measure(t) for t in longest[:FIT_SAMPLE]), default=0)

        for i, c in enumerate(self.columns):
            content = widest(v[i] for v in values.values())
            heading = head.measure(self._titles.get(c, c)) + mark
            width = max(content, heading) + CELL_PAD
            floor = max(MIN_WIDTH, int(self.min_widths.get(c, 0)))
            self._fit[c] = max(floor, min(MAX_FIT, width))
        if self.tree_column:
            heading = head.measure(self._titles.get(TREE, ""))
            width = max(widest(names) + TREE_INDENT, heading) + CELL_PAD
            self._fit[TREE] = max(MIN_WIDTH, min(MAX_FIT, width))

    def _base_width(self, column: str) -> int:
        return self._user.get(column) or self._fit.get(column, MIN_WIDTH)

    def _layout(self) -> None:
        """Columns at their fitted (or dragged) widths; when they leave room, the
        columns not dragged share it, so the table runs the panel's full width (the
        tree column keeps its own width)."""
        try:
            avail = int(self.tree.winfo_width())
        except tk.TclError:
            return
        base = {c: self._base_width(c) for c in self.laid_out()}
        widths = dict(base)
        extra = avail - sum(base.values()) if avail > 1 else 0
        if extra > 0 and self.columns:
            free = [c for c in self.columns if c not in self._user] or [
                self.columns[-1]
            ]
            total = sum(base[c] for c in free) or 1
            given = 0
            for n, c in enumerate(free):
                add = extra - given if n == len(free) - 1 else extra * base[c] // total
                widths[c] += add
                given += add
        for c, w in widths.items():
            if self._applied.get(c) != w:
                ttk.Treeview.column(self.tree, c, width=w)
        self._applied = widths

    def column_widths(self) -> Dict[str, int]:
        return {
            c: int(ttk.Treeview.column(self.tree, c, "width")) for c in self.laid_out()
        }

    def _on_press(self, event) -> None:
        self._dragging = self.tree.identify_region(event.x, event.y) == "separator"

    def _on_release(self, _event) -> None:
        if not self._dragging:
            return
        self._dragging = False
        changed = False
        for c, w in self.column_widths().items():
            if w != self._applied.get(c):
                self._user[c] = max(MIN_WIDTH, w)
                changed = True
        if changed:
            self._save()
            self._layout()

    def _on_double(self, event) -> Optional[str]:
        """A double-click on a heading's edge fits that column to its content."""
        if self.tree.identify_region(event.x, event.y) != "separator":
            return None
        column = self._separator_column(event.x)
        if column is not None:
            self._user.pop(column, None)
            self._save()
            self._layout()
        return "break"

    def _separator_column(self, x: int) -> Optional[str]:
        """The column whose right edge is at ``x`` (a heading's edge belongs to the
        column on its left, as Tk's drag does)."""
        ident = self.tree.identify_column(max(0, x - 2))
        try:
            n = int(str(ident).lstrip("#"))
        except ValueError:
            return None
        if n == 0:
            return TREE if self.tree_column else None
        shown = list(self.tree["displaycolumns"])
        names = self.columns if not shown or shown == ["#all"] else shown
        return names[n - 1] if n <= len(names) else None

    def reset_widths(self) -> None:
        """Every column back to its fitted width."""
        self._user.clear()
        self._save()
        self._layout()

    def _save(self) -> None:
        if not self.key:
            return
        entry = {"widths": dict(self._user)}
        if self._sort is not None:
            entry["sort"] = [self._sort[0], self._sort[1]]
        save_layout(self.key, entry)

    # ---- scrollbars ----

    def _yset(self, first, last) -> None:
        self.ysb.set(first, last)
        self._bar("y", float(first) > 0.0 or float(last) < 1.0)

    def _xset(self, first, last) -> None:
        self.xsb.set(first, last)
        self._bar("x", float(first) > 0.0 or float(last) < 1.0)

    def _bar(self, axis: str, needed: bool) -> None:
        if needed == self._shown[axis]:
            return
        # Showing one bar can make the other one needed, and hiding it unneeded;
        # past a few changes in one go, the bars stay shown.
        self._toggles += 1
        if self._toggles == 1:
            self.after_idle(self._reset_toggles)
        if not needed and self._toggles > 6:
            return
        self._shown[axis] = needed
        bar = self.ysb if axis == "y" else self.xsb
        if needed:
            if axis == "y":
                bar.grid(row=0, column=1, sticky="ns")
            else:
                bar.grid(row=1, column=0, sticky="ew")
        else:
            bar.grid_remove()

    def _reset_toggles(self) -> None:
        self._toggles = 0

    def scrollbars_shown(self) -> Dict[str, bool]:
        return dict(self._shown)


def _font(widget: tk.Misc, spec) -> tkfont.Font:
    try:
        return tkfont.nametofont(str(spec), root=widget)
    except (tk.TclError, TypeError):
        return tkfont.Font(root=widget, font=spec)
