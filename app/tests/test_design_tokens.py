"""The hub's design tokens and theme (design-system audits, 2026-10-15 and -16).

Colours, fonts and the chart palette come from ui_tokens; ui_theme builds every ttk
style from one palette. These tests keep it that way: contrast meets WCAG 2.1 in
every widget state, paper mode re-themes every style, focus is visible, only
ui_theme configures ttk styles, and the UI modules repeat no colour, font or
off-scale spacing literal.
"""

import os
import re
import sys

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import ui_tokens  # noqa: E402
from helpers_colour import contrast  # noqa: E402

HUB_MODULES = (  # the main window and its dialogs
    "pt_hub.py",
    "pt_paper_mode.py",
    "trading_mode_ui.py",
    "pt_chart_patterns.py",
    "paper_account_ui.py",
    "ui_theme.py",
)
FEATURE_MODULES = (  # the bottom notebook's feature tabs and the exchange window
    "exchange_config_gui.py",
    "llm_research_gui.py",
    "long_term_holdings_gui.py",
    "portfolio_analytics_gui.py",
    "advanced_order_gui.py",
    "real_time_market_data_gui.py",
    "portfolio_optimizer_gui.py",
    "backtesting_gui.py",
    "performance_attribution_gui.py",
    "institutional_trading_gui.py",
)
UI_MODULES = HUB_MODULES + FEATURE_MODULES


def _source(module):
    with open(os.path.join(APP_DIR, module), encoding="utf-8") as f:
        return f.read()


# --- tokens ---------------------------------------------------------------------------


def test_the_contrast_helper_spans_1_to_21_for_strings_and_tuples():
    assert contrast("#000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)) == pytest.approx(21.0)
    assert contrast("#777777", (119 / 255,) * 3) == pytest.approx(1.0)
    assert contrast("#767676", "#FFFFFF") == pytest.approx(4.54, abs=0.01)


def test_both_palettes_define_the_same_tokens():
    assert set(ui_tokens.DARK) == set(ui_tokens.PAPER)
    assert ui_tokens.palette(False) is ui_tokens.DARK
    assert ui_tokens.palette(True) is ui_tokens.PAPER


@pytest.mark.parametrize("name", ["DARK", "PAPER"])
def test_text_meets_4_5_to_1_on_every_surface_it_sits_on(name):
    p = getattr(ui_tokens, name)
    for text in ("FG", "MUTED", "ACCENT", "ACCENT2"):
        for surface in ("BG", "BG2", "PANEL", "PANEL2"):
            assert contrast(p[text], p[surface]) >= 4.5, (name, text, surface)
    assert contrast(p["SELECT_FG"], p["SELECT_BG"]) >= 4.5
    for colour in ui_tokens.STATUS.values():  # log lines, training age
        assert contrast(colour, p["BG"]) >= 4.5, (name, colour)
        assert contrast(colour, p["PANEL"]) >= 4.5, (name, colour)


def test_chart_lines_and_tags_meet_their_contrast():
    """Lines and markers need 3:1 on the plot (WCAG 1.4.11); a price tag's text is
    its line colour on the tag box, so it needs 4.5:1 (WCAG 1.4.3)."""
    plot, tag_box = ui_tokens.CHART["plot"], ui_tokens.CHART["label_bg"]
    for key, colour in ui_tokens.CHART_LINES.items():
        assert contrast(colour, plot) >= 3.0, key
        assert contrast(colour, tag_box) >= 4.5, key
    for key, colour in ui_tokens.TRADE_MARKERS.items():
        assert contrast(colour, plot) >= 3.0, key
    assert contrast(ui_tokens.CHART["text"], plot) >= 4.5
    assert contrast(ui_tokens.CHART["text"], tag_box) >= 4.5


def test_the_audit_colours_were_replaced():
    """ASK was purple (1.9:1 on the plot), the neural long levels blue (2.1:1), BID
    teal and SELL green below 4.5:1 as tag text."""
    lines = ui_tokens.CHART_LINES
    assert (lines["ask"], lines["neural_long"], lines["bid"], lines["trail"]) == (
        "#B388FF",
        "#5C9DFF",
        "#26C6DA",
        "#4CAF50",
    )


def test_banner_text_is_readable():
    for bg, fg in ui_tokens.BANNER.values():
        assert contrast(fg, bg) >= 4.5, (bg, fg)


def test_the_type_scale_and_spacing_scale():
    names = {
        ui_tokens.font(role, *styles)
        for role in ui_tokens.FONT_SIZES
        for styles in ((), ("bold",), ("italic",), ("bold", "italic"))
    }
    assert len(names) == 4 * len(ui_tokens.FONT_SIZES)  # one font per role and style
    assert ui_tokens.font("body", "italic", "bold") == ui_tokens.font(
        "body", "bold", "italic"
    )
    with pytest.raises(KeyError):
        ui_tokens.font("huge")
    with pytest.raises(ValueError):
        ui_tokens.font("body", "underline")
    assert ui_tokens.mono("small") == (ui_tokens.MONO_FAMILY, 9)
    sizes = list(ui_tokens.FONT_SIZES.values())
    assert sizes == sorted(sizes)
    space = list(ui_tokens.SPACE.values())
    assert space == sorted(space) and ui_tokens.SPACE["edge"] == 5


def test_chart_series_colours_show_on_the_plot():
    for key in ("series", "series2"):
        assert contrast(ui_tokens.CHART[key], ui_tokens.CHART["plot"]) >= 3.0, key


COLOUR_OPTION = (
    r"\b(?:fg|bg|foreground|background|colou?r|facecolor|edgecolor|outline|fill"
    r"|insertbackground|selectbackground|selectforeground|selectcolor"
    r"|highlightbackground|highlightcolor|activebackground|activeforeground)"
)


@pytest.mark.parametrize("module", UI_MODULES)
def test_ui_modules_repeat_no_colour_or_font_literal(module):
    """Colours and fonts come from ui_tokens; the candle palettes in chart_settings
    are user-selectable data and stay there."""
    source = _source(module)
    assert not re.findall(r"[\"']#[0-9A-Fa-f]{3,8}[\"']", source)
    names = re.findall(COLOUR_OPTION + r"\s*=\s*[\"']([A-Za-z]+)[\"']", source)
    # "none" is no colour (a hollow candle); pack(fill="both") is not a colour
    assert not [n for n in names if n not in ("none", "both", "x", "y")]
    assert not re.findall(r"colou?rs\s*=\s*\[\s*[\"'][A-Za-z]", source)
    assert not re.findall(r"font\s*=\s*\(\s*[\"']", source)
    assert 'DARK_BG = "' not in source  # no copied palette


@pytest.mark.parametrize("module", [m for m in UI_MODULES if m != "ui_theme.py"])
def test_no_ui_module_keeps_a_second_name_for_a_palette(module):
    """pt_paper_mode re-exported DARK_PALETTE, PAPER_PALETTE and get_palette
    alongside ui_tokens: two names to keep in step for every palette. (ui_theme
    keeps the active palette, its own state.)"""
    source = _source(module)
    assert not re.findall(
        r"(?m)^\w+\s*(?::[^=\n]+)?=\s*ui_tokens\.(?:DARK|PAPER)\b", source
    )
    assert "def get_palette" not in source


@pytest.mark.parametrize("module", UI_MODULES)
def test_only_ui_theme_configures_ttk_styles(module):
    """ttk styles are shared by every window in the process: the exchange window
    used to rebuild them, turning a paper-mode hub half dark."""
    if module == "ui_theme.py":
        return
    source = _source(module)
    assert "theme_use(" not in source
    assert not re.findall(r"\.(?:configure|map)\(\s*[\"'][\w.]*T[A-Z]\w*[\"']", source)


def _pads(source):
    """Every number in a padx/pady/ipadx/ipady/padding argument."""
    for m in re.finditer(
        r"\b(?:padx|pady|ipadx|ipady|padding)\s*=\s*(\([^()]*\)|[^,()\n]+)", source
    ):
        for number in re.findall(r"(?<![\w\[\"'.])\d+(?![\w.])", m.group(1)):
            yield int(number), source.count("\n", 0, m.start()) + 1


@pytest.mark.parametrize("module", [m for m in HUB_MODULES if m != "ui_theme.py"])
def test_hub_spacing_is_on_the_scale(module):
    """Gaps are steps of ui_tokens.SPACE (or 0). A component's own padding is set in
    ui_theme, and an alignment offset gets a named constant."""
    scale = {0, *ui_tokens.SPACE.values()}
    off = [(n, line) for n, line in _pads(_source(module)) if n not in scale]
    assert not off, f"off-scale pads (value, line): {off}"


# --- the theme ------------------------------------------------------------------------


@pytest.fixture
def tk_root():
    import tkinter as tk

    root, error = None, None
    for _ in range(10):  # Tk sometimes fails to read init.tcl on the first try
        try:
            root = tk.Tk()
            break
        except tk.TclError as exc:
            error = exc
    if root is None:
        pytest.skip(f"Tk not available: {error}")
    root.withdraw()
    yield root
    import ui_theme

    ui_theme.apply_theme(
        root, __import__("tkinter.ttk").ttk.Style(root), ui_tokens.DARK
    )
    root.destroy()


EVERY_STYLE = (  # (style, option, palette key) across every style the hub uses
    (".", "background", "BG"),
    ("TFrame", "background", "BG"),
    ("TLabel", "foreground", "FG"),
    ("TLabelframe", "bordercolor", "FRAME_BORDER"),
    ("TLabelframe.Label", "foreground", "ACCENT"),
    ("TSeparator", "background", "BORDER"),
    ("TButton", "background", "BG2"),
    ("TEntry", "fieldbackground", "PANEL"),
    ("TCombobox", "fieldbackground", "PANEL"),
    ("TSpinbox", "fieldbackground", "PANEL"),
    ("TNotebook", "background", "BG"),
    ("TNotebook.Tab", "background", "BG2"),
    ("ChartTab.TButton", "background", "BG2"),
    ("ChartTabSelected.TButton", "background", "PANEL"),
    ("ChartTabSelected.TButton", "foreground", "ACCENT"),
    ("ChartCog.TButton", "background", "BG"),
    ("Treeview", "background", "PANEL"),
    ("Treeview.Heading", "background", "BG2"),
    ("TPanedwindow", "background", "BG"),
    ("Vertical.TScrollbar", "background", "BG2"),
    ("Horizontal.TScrollbar", "troughcolor", "BG"),
)


@pytest.mark.parametrize("name", ["PAPER", "DARK"])
def test_one_palette_styles_every_widget(tk_root, name):
    """Paper mode used to re-apply 10 of these styles, leaving tables, tabs, fields,
    scrollbars and the chart tabs dark on blue frames."""
    from tkinter import ttk

    import ui_theme

    p = getattr(ui_tokens, name)
    style = ttk.Style(tk_root)
    ui_theme.apply_theme(tk_root, style, p)  # the one entry, for either mode
    for widget_style, option, key in EVERY_STYLE:
        assert str(style.lookup(widget_style, option)).upper() == p[key].upper(), (
            widget_style,
            option,
        )
    assert str(tk_root.cget("bg")).upper() == p["BG"].upper()


def test_keyboard_focus_is_visible(tk_root):
    import ui_theme
    from tkinter import ttk

    p = ui_tokens.DARK
    style = ttk.Style(tk_root)
    ui_theme.apply_theme(tk_root, style, p)
    # the borderless cog lights up on focus, edges and all
    assert style.lookup("ChartCog.TButton", "background", ["focus"]) == p["PANEL2"]
    assert style.lookup("ChartCog.TButton", "background") == p["BG"]
    for edge in ("bordercolor", "lightcolor", "darkcolor", "focuscolor"):
        assert style.lookup("ChartCog.TButton", edge, ["focus"]) == p["PANEL2"]
    # the selected chart tab has its own states
    assert style.lookup("ChartTabSelected.TButton", "bordercolor", ["focus"]) == (
        p["ACCENT"]
    )
    assert style.lookup("ChartTabSelected.TButton", "background", ["active"]) == (
        p["PANEL2"]
    )
    # entries show focus too
    assert style.lookup("TEntry", "fieldbackground", ["focus"]) == p["PANEL2"]
    assert style.lookup("TEntry", "bordercolor", ["focus"]) == p["ACCENT2"]


@pytest.mark.parametrize("name", ["DARK", "PAPER"])
def test_every_focus_ring_shows_on_its_widget(tk_root, name):
    """The dotted focus ring is drawn in focuscolor; with none set, ttk draws it
    black, invisible on check boxes, radio buttons and notebook tabs (WCAG 2.4.7).
    A ring needs 3:1 against the widget it sits on (WCAG 1.4.11)."""
    import ui_theme
    from tkinter import ttk

    p = getattr(ui_tokens, name)
    style = ttk.Style(tk_root)
    ui_theme.apply_theme(tk_root, style, p)
    rings = (
        ("TButton", ["focus"]),
        ("Accent.TButton", ["focus"]),
        ("ChartTab.TButton", ["focus"]),
        ("ChartTabSelected.TButton", ["focus"]),
        ("TCheckbutton", ["focus"]),
        ("TRadiobutton", ["focus"]),
        ("TNotebook.Tab", ["focus", "selected"]),  # the focused tab is the selected one
    )
    faint = []
    for widget_style, state in rings:
        ring = style.lookup(widget_style, "focuscolor", state)
        under = style.lookup(widget_style, "background", state)
        if not ring or contrast(ring, under) < 3.0:
            faint.append((widget_style, ring, under))
    assert not faint


def test_fonts_use_the_system_family_and_tooltips_the_theme(tk_root):
    import tkinter.font as tkfont
    from tkinter import ttk

    import pt_hub
    import ui_theme

    p = ui_tokens.PAPER
    ui_theme.apply_theme(tk_root, ttk.Style(tk_root), p)
    family = tkfont.nametofont("TkDefaultFont", root=tk_root).actual("family")
    caption = tkfont.Font(
        root=tk_root, name=ui_tokens.font("caption", "bold"), exists=True
    )
    # not Arial, Tk's fallback for a tuple naming "TkDefaultFont" as its family
    assert caption.actual("family") == family
    assert caption.actual("weight") == "bold"
    assert caption.actual("size") == ui_tokens.FONT_SIZES["caption"]
    widget = ttk.Label(tk_root, text="x")
    widget.pack()
    tip = pt_hub.ToolTip(widget, "explained")
    tip.on_enter()
    label = tip.tooltip_window.winfo_children()[0]
    assert str(label.cget("background")).upper() == p["PANEL2"].upper()
    assert str(label.cget("foreground")).upper() == p["FG"].upper()
    assert tkfont.Font(root=tk_root, font=label.cget("font")).actual("family") == (
        family
    )
    tip.on_leave()


def test_applying_the_theme_leaves_the_tokens_unchanged(tk_root):
    """apply_theme used to write the system family into ui_tokens.FAMILY, so a font
    built before it (or in a window that never applied it) was Arial, and the value
    carried over from one test to the next."""
    import copy

    import ui_theme
    from tkinter import ttk

    before = {
        k: copy.deepcopy(v)
        for k, v in vars(ui_tokens).items()
        if not k.startswith("__") and not callable(v)
    }
    ui_theme.apply_theme(tk_root, ttk.Style(tk_root), ui_tokens.PAPER)
    after = {k: v for k, v in vars(ui_tokens).items() if k in before}
    assert after == before


# --- states: no light clam colour leaks in any state ---------------------------------

STATE_STYLES = (
    "TButton",
    "Accent.TButton",
    "ChartTab.TButton",
    "ChartTabSelected.TButton",
    "ChartCog.TButton",
    "TCheckbutton",
    "TRadiobutton",
    "TLabel",
    "TEntry",
    "TCombobox",
    "TSpinbox",
    "TNotebook.Tab",
    "Treeview",
    "Treeview.Heading",
    "Vertical.TScrollbar",
    "Horizontal.TScrollbar",
    "Horizontal.TProgressbar",
    "TNotebook",
    "TLabelframe",
)
STATES = (
    (),
    ("active",),
    ("pressed",),
    ("focus",),
    ("selected",),
    ("readonly",),
    ("readonly", "focus"),
    ("disabled",),
    ("disabled", "readonly"),
)
COLOURS = (
    "background",
    "foreground",
    "fieldbackground",
    "bordercolor",
    "indicatorbackground",
    "indicatorforeground",
    "arrowcolor",
    "selectbackground",
    "selectforeground",
    "troughcolor",
    "lightcolor",  # clam's inner outline: light greys, darker when pressed,
    "darkcolor",  # blue round a focused entry
)


@pytest.mark.parametrize("name", ["DARK", "PAPER"])
def test_every_state_takes_its_colours_from_the_palette(tk_root, name):
    """clam's own state colours are light greys and a blue: a hovered or disabled
    checkbox turned #EEEBE7 behind FG text (1.3:1), a disabled combo looked enabled,
    focused combos had a #4A6984 border, and the inner outline of buttons, fields,
    tabs and scrollbars stayed clam's greys (#6F9DC6 round a focused entry)."""
    import ui_theme
    from tkinter import ttk

    p = getattr(ui_tokens, name)
    style = ttk.Style(tk_root)
    ui_theme.apply_theme(tk_root, style, p)
    allowed = {c.upper() for c in (*p.values(), *ui_tokens.STATUS.values())}
    leaks = []
    for widget_style in STATE_STYLES:
        for state in STATES:
            for option in COLOURS:
                value = str(style.lookup(widget_style, option, list(state)))
                if value and value.upper() not in allowed:
                    leaks.append((widget_style, state, option, value))
    assert not leaks


@pytest.mark.parametrize("name", ["DARK", "PAPER"])
def test_text_is_readable_in_every_state(tk_root, name):
    import ui_theme
    from tkinter import ttk

    p = getattr(ui_tokens, name)
    style = ttk.Style(tk_root)
    ui_theme.apply_theme(tk_root, style, p)
    low = []
    for widget_style in STATE_STYLES:
        if widget_style.endswith(("Scrollbar", "Progressbar")):
            continue  # no text
        fields = widget_style in ("TEntry", "TCombobox", "TSpinbox", "Treeview")
        for state in STATES:
            fg = style.lookup(widget_style, "foreground", list(state))
            surface = "fieldbackground" if fields else "background"
            bg = style.lookup(widget_style, surface, list(state))
            if fg and bg and contrast(fg, bg) < 4.5:
                low.append((widget_style, state, fg, bg, round(contrast(fg, bg), 2)))
    assert not low


def test_a_pressed_button_shows_its_pressed_colours(tk_root):
    """ttk takes the first state in a map that matches, and a button under the mouse
    is both active and pressed: with "active" listed first, TButton and the chart
    tabs never showed their pressed colour."""
    import ui_theme
    from tkinter import ttk

    style = ttk.Style(tk_root)
    ui_theme.apply_theme(tk_root, style, ui_tokens.DARK)
    hidden = []
    for widget_style in STATE_STYLES:
        for option in COLOURS:
            pressed = style.lookup(widget_style, option, ["pressed"])
            if pressed == style.lookup(widget_style, option):
                continue  # no pressed colour of its own
            if style.lookup(widget_style, option, ["active", "pressed"]) != pressed:
                hidden.append((widget_style, option))
    assert not hidden
    assert style.lookup("TButton", "background", ["active", "pressed"]) == (
        ui_tokens.DARK["PANEL"]
    )


def test_disabled_fields_look_disabled(tk_root):
    import ui_theme
    from tkinter import ttk

    p = ui_tokens.DARK
    style = ttk.Style(tk_root)
    ui_theme.apply_theme(tk_root, style, p)
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        for state in (["disabled"], ["disabled", "readonly"]):
            assert style.lookup(name, "foreground", state) == p["MUTED"], name
            assert style.lookup(name, "fieldbackground", state) == p["BG2"], name
    for name in ("TCheckbutton", "TRadiobutton"):
        assert style.lookup(name, "foreground", ["disabled"]) == p["MUTED"]
        assert style.lookup(name, "background", ["active"]) == p["PANEL2"]
        assert style.lookup(name, "indicatorbackground") == p["PANEL"]


# --- named styles ---------------------------------------------------------------------


def test_every_named_style_in_use_is_defined(tk_root):
    """Accent.TButton was used and defined nowhere; Title/Header/Success/Warning/
    Error.TLabel were defined by one tab with light-theme colours (1.7:1)."""
    import ui_theme
    from tkinter import ttk

    p = ui_tokens.PAPER
    style = ttk.Style(tk_root)
    ui_theme.apply_theme(tk_root, style, p)
    used = set()
    pattern = r"style\s*=\s*[\"'](\w+\.[\w.]+)[\"']"
    for module in UI_MODULES:
        used |= set(re.findall(pattern, _source(module)))
    assert "Accent.TButton" in used
    assert not sorted(s for s in used if not style.configure(s))
    for name, key in (("Good", "good"), ("Warn", "warn"), ("Bad", "bad")):
        assert style.lookup(f"{name}.TLabel", "foreground") == ui_tokens.STATUS[key]
    assert style.lookup("Muted.TLabel", "foreground") == p["MUTED"]
    assert contrast(style.lookup("Accent.TButton", "foreground"), p["ACCENT"]) >= 4.5


# --- classic Tk widgets and charts ----------------------------------------------------


def test_classic_widgets_take_the_palette(tk_root):
    """The Portfolio Optimization, Backtesting and Performance Attribution tabs are
    built from classic Tk widgets: they showed Windows' light grey and white."""
    import tkinter as tk
    from tkinter import ttk

    import ui_theme

    p = ui_tokens.PAPER
    ui_theme.apply_theme(tk_root, ttk.Style(tk_root), p)
    frame = tk.Frame(tk_root)
    top = tk.Toplevel(frame)
    widgets = {
        "frame": (frame, "background", "BG"),
        "label": (tk.Label(frame, text="x"), "background", "BG"),
        "label text": (tk.Label(frame, text="x"), "foreground", "FG"),
        "labelframe": (tk.LabelFrame(frame, text="x"), "background", "BG"),
        "entry": (tk.Entry(frame), "background", "PANEL"),
        "entry text": (tk.Entry(frame), "foreground", "FG"),
        "button": (tk.Button(frame, text="x"), "background", "BG2"),
        "text": (tk.Text(frame), "background", "PANEL"),
        "canvas": (tk.Canvas(frame), "highlightbackground", "BG"),
        "toplevel": (top, "background", "BG"),
    }
    try:
        for name, (widget, option, key) in widgets.items():
            assert str(widget.cget(option)).upper() == p[key].upper(), name
        # a colour passed to the widget still wins
        assert tk.Label(frame, bg=p["ACCENT"]).cget("background") == p["ACCENT"]
    finally:
        top.destroy()
        frame.destroy()


CLASSIC_TEXT_WIDGETS = {"Label", "Button", "Text", "Entry", "Listbox", "Message"}


@pytest.mark.parametrize("module", UI_MODULES)
def test_a_classic_widget_that_sets_its_background_sets_its_text_colour(module):
    """The default text colour comes from the theme's option database, so a widget
    that paints its own background picks its text colour too: the dependency
    labels were black on PANEL (1.1:1) in a window run on its own."""
    import ast

    missing = []
    for node in ast.walk(ast.parse(_source(module))):
        func = getattr(node, "func", None)
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "tk"
            and func.attr in CLASSIC_TEXT_WIDGETS
        ):
            continue
        options = {k.arg for k in node.keywords}
        if options & {"bg", "background"} and not options & {"fg", "foreground"}:
            missing.append((func.attr, node.lineno))
    assert not missing


@pytest.mark.parametrize("module", FEATURE_MODULES)
def test_a_feature_window_run_on_its_own_builds_a_themed_root(module):
    """A bare tk.Tk() has no option database: the institutional event log was
    light text on white and its titles plain labels."""
    source = _source(module)
    assert "tk.Tk()" not in source
    if "__main__" in source:
        assert "ui_theme.themed_root()" in source


def test_a_themed_root_looks_like_the_hub():
    import tkinter as tk
    from tkinter import ttk

    import ui_theme

    root, error = None, None
    for _ in range(10):  # Tk sometimes fails to read init.tcl on the first try
        try:
            root = ui_theme.themed_root()
            break
        except tk.TclError as exc:
            error = exc
    if root is None:
        pytest.skip(f"Tk not available: {error}")
    root.withdraw()
    p = ui_tokens.DARK
    try:
        log = tk.Text(root)
        assert str(log.cget("background")).upper() == p["PANEL"].upper()
        assert str(log.cget("foreground")).upper() == p["FG"].upper()
        assert str(tk.Label(root).cget("foreground")).upper() == p["FG"].upper()
        style = ttk.Style(root)
        assert style.lookup("Title.TLabel", "font")
        assert style.lookup("Header.TLabel", "font")
    finally:
        root.destroy()


def test_theme_figure_gives_charts_the_chart_surfaces():
    from matplotlib.colors import to_hex
    from matplotlib.figure import Figure

    import ui_theme

    c = ui_tokens.CHART
    fig = Figure()
    ax = fig.add_subplot()
    ax.plot([1, 2], [3, 4], label="equity")
    ax.set_title("Returns")
    ax.legend()
    ax.text(0, 0, "plain")
    ax.text(0, 0, "own colour", color=ui_tokens.STATUS["bad"])
    ui_theme.theme_figure(fig)
    assert to_hex(fig.get_facecolor()) == c["figure"].lower()
    assert to_hex(ax.get_facecolor()) == c["plot"].lower()
    assert to_hex(ax.title.get_color()) == c["text"].lower()
    assert to_hex(ax.xaxis.get_ticklabels()[0].get_color()) == c["text"].lower()
    assert to_hex(ax.spines["left"].get_edgecolor()) == c["grid"].lower()
    plain, own = ax.texts
    assert to_hex(plain.get_color()) == c["text"].lower()
    assert to_hex(own.get_color()) == ui_tokens.STATUS["bad"].lower()
    assert to_hex(ax.get_legend().get_texts()[0].get_color()) == c["text"].lower()


def test_theme_figure_keeps_a_title_or_axis_label_given_its_own_colour():
    """It recoloured the title and axis labels whatever their colour."""
    from matplotlib.colors import to_hex
    from matplotlib.figure import Figure

    import ui_theme

    bad, good = ui_tokens.STATUS["bad"], ui_tokens.STATUS["good"]
    fig = Figure()
    ax = fig.add_subplot()
    ax.plot([1, 2], [3, 4])
    ax.set_title("Loss", color=bad)
    ax.set_ylabel("Equity", color=good)  # coloured like its series
    ax.set_xlabel("Date")
    ui_theme.theme_figure(fig)
    assert to_hex(ax.title.get_color()) == bad.lower()
    assert to_hex(ax.yaxis.label.get_color()) == good.lower()
    assert to_hex(ax.xaxis.label.get_color()) == ui_tokens.CHART["text"].lower()


# --- the hub --------------------------------------------------------------------------


@pytest.fixture
def hub(monkeypatch):
    import helpers_trainer as ht

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    yield hub
    ht.close_hub(hub)


def _classic_widgets(parent):
    from tkinter import ttk

    for child in parent.winfo_children():
        if not isinstance(child, ttk.Widget):
            yield child
        yield from _classic_widgets(child)


def test_classic_widgets_in_the_hub_have_readable_text_and_selections(hub):
    """Selected Trade History rows were light grey on cyan (DARK_FG on ACCENT2,
    1.0:1)."""
    low = []
    for widget in _classic_widgets(hub):
        if widget.winfo_class() not in CLASSIC_TEXT_WIDGETS:
            continue  # canvases and frames show no text
        keys = widget.keys()
        for fg, bg in (
            ("foreground", "background"),
            ("selectforeground", "selectbackground"),
        ):
            if fg in keys and bg in keys:
                # Tk resolves names such as SystemHighlightText
                a, b = (
                    "#%02X%02X%02X" % tuple(v // 257 for v in widget.winfo_rgb(c))
                    for c in (widget.cget(fg), widget.cget(bg))
                )
                if contrast(a, b) < 4.5:
                    low.append((widget.winfo_class(), str(widget), fg, a, b))
    assert not low


def test_the_hubs_classic_widgets_take_the_active_palette(hub):
    """pt_hub passed fixed DARK_* colours to its classic widgets, so in paper mode
    the Settings and Chart settings windows, the live logs, the menus and Trade
    History stayed dark navy inside the blue frames."""
    import tkinter as tk

    import ui_theme

    p = ui_tokens.PAPER
    assert hub._paper_mode and ui_theme.active_palette() is p  # tests run in paper

    def colour(widget, option):
        return str(widget.cget(option)).upper()

    menubar = hub.nametowidget(hub["menu"])
    assert colour(menubar, "background") == p["BG2"].upper()
    # Trade History is a table now (ui_table.DataTable): ttk, styled by the theme
    for text in (hub.trainer_text, hub.runner_text, hub.trader_text):
        assert colour(text, "background") == p["PANEL"].upper()
        assert colour(text, "selectbackground") == p["SELECT_BG"].upper()
        assert colour(text, "selectforeground") == p["SELECT_FG"].upper()
    hub.open_settings_dialog()
    settings = [
        w
        for w in hub.winfo_children()
        if isinstance(w, tk.Toplevel) and w.title() == "Settings"
    ][-1]
    assert colour(settings, "background") == p["BG"].upper()
    canvases = [w for w in _classic_widgets(settings) if w.winfo_class() == "Canvas"]
    assert canvases
    assert all(colour(c, "background") == p["BG"].upper() for c in canvases)
    assert colour(hub.open_chart_settings(), "background") == p["BG"].upper()


def test_the_hub_names_no_fixed_palette():
    """The palette is chosen at start-up (dark, or paper blue); a colour taken from
    ui_tokens.DARK directly stays dark in paper mode."""
    source = _source("pt_hub.py")
    assert not re.findall(r"\bDARK_[A-Z]", source)
    assert "ui_tokens.DARK" not in source


# --- the exchange window --------------------------------------------------------------


def test_opening_the_exchange_window_leaves_the_hub_theme_alone(
    tk_root, tmp_path, monkeypatch
):
    """It used to rebuild TFrame, TLabel, TButton, the notebook tabs and tables in
    the dark palette (and drop the button focus ring) for the whole process."""
    from tkinter import ttk

    import exchange_config_gui
    import ui_theme
    from pt_multi_exchange import ExchangeConfigManager

    manager = ExchangeConfigManager(str(tmp_path))
    monkeypatch.setattr(exchange_config_gui, "ExchangeConfigManager", lambda: manager)
    p = ui_tokens.PAPER
    style = ttk.Style(tk_root)
    ui_theme.apply_theme(tk_root, style, p)
    probes = [
        (name, option)
        for name in ("TFrame", "TLabel", "TButton", "TNotebook.Tab", "Treeview")
        for option in ("background", "foreground", "padding", "focuscolor")
    ]

    def looks():  # Tk returns a padding as (3, 2) or "3 2": compare the values
        return {k: re.findall(r"[^\s(),']+", str(style.lookup(*k))) for k in probes}

    before = looks()
    gui = exchange_config_gui.ExchangeConfigGUI(parent=tk_root)
    try:
        gui.window.withdraw()
        assert looks() == before
        assert str(gui.window.cget("bg")).upper() == p["BG"].upper()
    finally:
        gui.window.destroy()
