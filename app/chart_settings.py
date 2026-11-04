"""
Chart settings for the coin charts (FDS-CHART-001 section 8): which overlays are drawn,
which candlestick patterns are shown, and the palette. Pure: no Tk.

The settings live under one ``gui_settings`` key, ``chart``. ``normalize`` turns
whatever is stored there into a complete settings dict: missing keys take their
defaults (an older settings file still works), unknown keys are kept but ignored, and
a pattern added later takes its own default (``default_on``).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Tuple

from candlestick_patterns import (
    DEFAULT_RANK,
    DEFAULT_RECENT_CANDLES,
    PATTERNS,
    RANK_RANGE,
    RECENT_CANDLES_RANGE,
    PatternDef,
)

# (key, label, what it controls) for the Overlays tab, in display order
OVERLAYS: Tuple[Tuple[str, str, str], ...] = (
    (
        "neural_long",
        "Neural long levels",
        "the blue full-width lines, one per long level",
    ),
    (
        "neural_short",
        "Neural short levels",
        "the orange full-width lines, one per short level",
    ),
    (
        "neural_readout",
        "Neural readout",
        'the toolbar text "Neural: long=... short=..."',
    ),
    ("ask", "Ask price", "the purple ASK line and its right-edge label"),
    ("bid", "Bid price", "the teal BID line and its right-edge label"),
    ("avg", "Average cost", "the yellow AVG line and its right-edge label"),
    ("dca", "Next DCA level", "the red DCA line and its right-edge label"),
    ("trail", "Trailing sell line", "the green SELL line and its right-edge label"),
    ("trades", "Trade markers", "the BUY, DCA and SELL dots and their labels"),
)

# (filter key, label) for the Candlestick patterns tab, grouped
FILTER_GROUPS: Tuple[Tuple[str, Tuple[Tuple[str, str], ...]], ...] = (
    (
        "Direction",
        (("bullish", "Bullish"), ("bearish", "Bearish"), ("none", "No direction")),
    ),
    (
        "Type",
        (
            ("reversal", "Reversal"),
            ("continuation", "Continuation"),
            ("indecision", "Indecision"),
        ),
    ),
    ("Family", (("classical", "Classical"), ("price_action", "Price action"))),
)
FILTERS = tuple(key for _, group in FILTER_GROUPS for key, _ in group)
# owner decision 2026-10-13 (FDS-CHART-001 section 12.2): these filters start off
FILTERS_OFF_BY_DEFAULT = ("none", "continuation", "indecision")

MAX_LABELS_RANGE = (1, 30)

# Palettes (FDS-CHART-001 section 9): candle up / down colours
PALETTES: Dict[str, Dict[str, str]] = {
    "default": {"label": "Default", "up": "#008000", "down": "#FF0000"},
    "blue_vermilion": {"label": "Blue / vermilion", "up": "#56B4E9", "down": "#D55E00"},
}
CANDLE_STYLES: Dict[str, str] = {"filled": "Filled", "hollow_up": "Hollow up"}


def default_on(pattern: PatternDef) -> bool:
    """Owner decisions 2026-10-13 (FDS-CHART-001 section 12.2): a pattern starts
    unticked when it belongs to a filter that starts off (no direction, continuation,
    indecision); every other pattern starts ticked."""
    return not set(pattern.tags) & set(FILTERS_OFF_BY_DEFAULT)


def defaults() -> Dict[str, Any]:
    return {
        "overlays": {key: True for key, _, _ in OVERLAYS},
        "patterns": {
            "enabled": True,
            "filters": {key: key not in FILTERS_OFF_BY_DEFAULT for key in FILTERS},
            "items": {p.id: default_on(p) for p in PATTERNS},
            "max_labels": 12,
            "next_arrows": True,
            "rank": dict(DEFAULT_RANK),
            "recent_candles": DEFAULT_RECENT_CANDLES,
        },
        "palette": "default",
        "candle_style": "filled",
    }


def _as_bool(value, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def normalize(raw: Any) -> Dict[str, Any]:
    """A complete chart-settings dict from whatever ``gui_settings["chart"]`` holds."""
    base = defaults()
    if not isinstance(raw, dict):
        return base
    out = copy.deepcopy(raw)  # unknown keys are kept
    for key in ("overlays",):
        given = raw.get(key) if isinstance(raw.get(key), dict) else {}
        merged = dict(given)
        for name, value in base[key].items():
            merged[name] = _as_bool(given.get(name), value)
        out[key] = merged
    pats_raw = raw.get("patterns") if isinstance(raw.get("patterns"), dict) else {}
    pats = dict(pats_raw)
    pats["enabled"] = _as_bool(pats_raw.get("enabled"), True)
    for sub in ("filters", "items"):
        given = pats_raw.get(sub) if isinstance(pats_raw.get(sub), dict) else {}
        merged = dict(given)
        for name, value in base["patterns"][sub].items():
            merged[name] = _as_bool(given.get(name), value)
        pats[sub] = merged
    try:
        cap = int(pats_raw.get("max_labels", 12))
    except (TypeError, ValueError):
        cap = 12
    lo, hi = MAX_LABELS_RANGE
    pats["max_labels"] = min(hi, max(lo, cap))
    pats["next_arrows"] = _as_bool(pats_raw.get("next_arrows"), True)
    given = pats_raw.get("rank") if isinstance(pats_raw.get("rank"), dict) else {}
    low, high = RANK_RANGE
    rank = {}
    for key, value in DEFAULT_RANK.items():
        weight = given.get(key, value)
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            weight = value
        rank[key] = int(min(high, max(low, int(weight))))
    pats["rank"] = rank
    try:
        within = int(pats_raw.get("recent_candles", DEFAULT_RECENT_CANDLES))
    except (TypeError, ValueError):
        within = DEFAULT_RECENT_CANDLES
    low, high = RECENT_CANDLES_RANGE
    pats["recent_candles"] = min(high, max(low, within))
    out["patterns"] = pats
    if out.get("palette") not in PALETTES:
        out["palette"] = "default"
    if out.get("candle_style") not in CANDLE_STYLES:
        out["candle_style"] = "filled"
    return out


def overlay_on(cfg: Dict[str, Any], key: str) -> bool:
    return bool(cfg["overlays"].get(key, True))


def pattern_visible(cfg: Dict[str, Any], pattern: PatternDef) -> bool:
    """FDS-CHART-001 section 8.3: shown when the master toggle, the pattern's own
    checkbox and every filter it belongs to are on."""
    pats = cfg["patterns"]
    if not pats["enabled"] or not pats["items"].get(pattern.id, default_on(pattern)):
        return False
    return all(pats["filters"].get(tag, True) for tag in pattern.tags)


def palette(cfg: Dict[str, Any]) -> Dict[str, str]:
    return PALETTES.get(cfg.get("palette"), PALETTES["default"])
