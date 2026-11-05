"""Design tokens for the hub: colour palettes, status, chart and banner colours, the
type scale and the spacing scale.

Every ttk style (ui_theme.apply_theme), chart colour and font in the hub takes its
value from here, so a colour or size is defined once. Pure data: no Tk.

Contrast (WCAG 2.1), checked by app/tests/test_design_tokens.py:
- text colours are at least 4.5:1 on the backgrounds they sit on;
- chart lines and candles are at least 3:1 on the plot, and the price tags' text
  (the line colour on the tag box) at least 4.5:1.
"""

from typing import Dict, Tuple

# --- palettes: the frames, buttons, tables and fields take one of these ---------------

DARK: Dict[str, str] = {
    "BG": "#070B10",
    "BG2": "#0B1220",
    "PANEL": "#0E1626",
    "PANEL2": "#121C2F",
    "BORDER": "#243044",
    "FRAME_BORDER": "#FFFFFF",  # LabelFrame outlines
    "FG": "#C7D1DB",
    "MUTED": "#8B949E",
    "ACCENT": "#00FF66",
    "ACCENT2": "#00E5FF",
    "SELECT_BG": "#17324A",
    "SELECT_FG": "#00FF66",
}

# Paper mode: the same keys in a blue family, with a warm gold accent so "PAPER
# TRADING" stands out.
PAPER: Dict[str, str] = {
    "BG": "#0A1B3A",
    "BG2": "#11264D",
    "PANEL": "#152E5C",
    "PANEL2": "#1B3870",
    "BORDER": "#2E4A82",
    "FRAME_BORDER": "#2E4A82",
    "FG": "#E6EEF8",
    "MUTED": "#9AB0CC",
    "ACCENT": "#FFC400",
    "ACCENT2": "#FFE082",
    "SELECT_BG": "#23488A",
    "SELECT_FG": "#FFC400",
}


def palette(paper_mode: bool) -> Dict[str, str]:
    return PAPER if paper_mode else DARK


# --- status colours (log lines, training age, signal counts) ---------------------------

STATUS: Dict[str, str] = {
    "good": "#4CAF50",
    "warn": "#FFA726",
    "bad": "#FF6B6B",
    "short": "#FF8A65",  # a short signal in the log
}

# --- charts -----------------------------------------------------------------------------

# The chart surfaces stay dark in both modes: the candle and line colours below are
# chosen for this plot colour, and a paper-blue plot would lower their contrast.
CHART: Dict[str, str] = {
    "figure": DARK["BG"],
    "plot": DARK["PANEL"],
    "text": DARK["FG"],
    "grid": DARK["BORDER"],
    "label_bg": DARK["BG2"],  # price tags, pattern labels, hover notes
    "series": DARK["ACCENT"],  # the feature tabs' data series: prices, returns
    "series2": DARK["ACCENT2"],  # a second series, e.g. volume
}

# Level lines and the price tags beside them.
CHART_LINES: Dict[str, str] = {
    "neural_long": "#5C9DFF",
    "neural_short": "#FFA500",
    "ask": "#B388FF",
    "bid": "#26C6DA",
    "avg": "#FFFF00",
    "dca": "#FF0000",
    "trail": "#4CAF50",
}

# Trade markers on the coin and account charts.
TRADE_MARKERS: Dict[str, str] = {
    "buy": "#FF0000",
    "dca": CHART_LINES["ask"],
    "sell": CHART_LINES["trail"],
}

CHART_FONT_PT = 8  # chart labels, tags and notes (matplotlib points)

# --- the trading-mode banner ---------------------------------------------------------

BANNER: Dict[str, Tuple[str, str]] = {  # (background, text)
    "paper": ("#FFC400", "#0A1B3A"),
    "live": ("#B00020", "#FFFFFF"),
    "testnet": ("#E67E00", "#1A1A1A"),  # dark text: white on this orange is 2.9:1
    "halted": ("#C62828", "#FFFFFF"),  # TRADING HALTED, over any mode's header
}

# --- type scale ---------------------------------------------------------------------

FONT_SIZES: Dict[str, int] = {
    "micro": 7,
    "caption": 8,
    "small": 9,
    "body": 10,
    "subtitle": 11,
    "title": 12,
    "display": 14,
}
FONT_STYLES = ("bold", "italic")
MONO_FAMILY = "Consolas"


def font(role: str, *styles: str) -> str:
    """The Tk named font for a role in the type scale, e.g. font("caption", "bold").

    ui_theme.apply_theme creates the named fonts in each Tk interpreter, in the
    system UI family (Segoe UI on Windows), the one widgets without a font of their
    own use. A font tuple can't name that family: Tk reads "TkDefaultFont" in a
    tuple as a family it doesn't have, and falls back to Arial."""
    FONT_SIZES[role]  # an unknown role is a KeyError
    unknown = set(styles) - set(FONT_STYLES)
    if unknown:
        raise ValueError(f"font styles are {FONT_STYLES}, not {sorted(unknown)}")
    return "-".join(("pt", role, *sorted(set(styles))))


def mono(role: str) -> Tuple:
    return (MONO_FAMILY, FONT_SIZES[role])


# --- spacing scale (pixels) ---------------------------------------------------------

SPACE: Dict[str, int] = {
    "px": 1,  # a one-pixel nudge in the dense Controls / Health pane
    "hair": 2,
    "xs": 4,
    "edge": 5,  # the chart panel's outer margin (owner, 2026-10-14)
    "sm": 6,
    "md": 8,
    "lg": 10,
    "xl": 12,
    "xxl": 20,
}
