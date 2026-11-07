from __future__ import annotations

import bisect
import functools
import glob
import json
import logging
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import warnings
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Tuple

from matplotlib import rcParams
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter
from matplotlib.transforms import ScaledTranslation, blended_transform_factory

# The program folder is read-only at runtime (pt_paths): run as the hub, Python
# writes no bytecode cache next to the app modules imported from here on (#148).
# The processes the hub starts get the same through _child_env.
if __name__ == "__main__":
    sys.dont_write_bytecode = True

import chart_settings
import exchange_symbols
import order_management_execution
import order_management_view
import paper_coins
import position_sizing
import pt_paths
import risk_state
import trade_history_view
import training_settings
import ui_table
import ui_theme
import ui_tokens

try:
    import pt_migrate
except ImportError:  # the hub must start even without it
    pt_migrate = None
from pt_paper_mode import (
    PAPER_MODE_BALANCE_KEY,
    PaperBanner,
    attach_trading_section_label,
    run_sample_scenario,
)
import trainer_guard
import trainer_status
from strategies import descriptions as strategy_words
from strategies.settings import read_strategy_settings
from trading_mode import (
    MAX_QUOTE_AGE_RANGE,
    PaperBookError,
    PaperBookInvalid,
    TradingSettings,
    broker_places_orders,
    move_root_live_books,
    paper_book_path,
    read_drawdown_levels,
    read_paper_book,
    read_paper_settings,
    read_trading_settings,
    save_paper_settings,
)
from trading_mode_ui import TradingModeDialog, TradingModeIndicator, pack_at_top

from pt_exchange_abstraction import exchange_id, exchange_name

# Multi-exchange imports
try:
    from pt_exchange_abstraction import ExchangeFactory, ExchangeType
    from pt_multi_exchange import ExchangeConfigManager, MultiExchangeManager

    EXCHANGE_SUPPORT_AVAILABLE = True
except ImportError as exc:
    EXCHANGE_SUPPORT_AVAILABLE = False
    # A missing package is reported as such, not as a multi-exchange problem.
    if isinstance(exc, pt_paths.MissingDependency):
        print(f"Warning: {exc}")  # platformdirs: main() stops on it
    elif isinstance(exc, ModuleNotFoundError):
        print(
            f"Warning: Multi-exchange support not available: {exc}. Install the requirements "
            f"with: {pt_paths.REQUIREMENTS_COMMAND}. Exchange status will be disabled."
        )
    else:
        print(
            "Warning: Multi-exchange support not available. Exchange status will be disabled."
        )

# Order management imports
try:
    from order_management_integration import (
        get_global_order_manager,
        get_order_notifications_for_gui,
        initialize_order_management_for_powertrader,
    )
    from order_management_models import (
        ConditionOperator,
        ConditionType,
        OrderSide,
        OrderStatus,
        OrderType,
    )

    ORDER_MANAGEMENT_AVAILABLE = True
except ImportError:
    ORDER_MANAGEMENT_AVAILABLE = False
    print("Warning: Order management system not available.")

# LLM Research Engine imports
try:
    from llm_research_gui import ResearchEngineGUI

    LLM_RESEARCH_AVAILABLE = True
except ImportError:
    LLM_RESEARCH_AVAILABLE = False
    print("Warning: LLM Research Engine not available.")

# Dependency checker
try:
    from dependency_checker import get_dependency_checker, quick_check

    DEPENDENCY_CHECKER_AVAILABLE = True
except ImportError:
    DEPENDENCY_CHECKER_AVAILABLE = False
    print("Warning: Dependency checker not available.")

# Secrets never go into gui_settings.json (pt_secrets strips them on load/save)
try:
    import pt_secrets
except ImportError:
    pt_secrets = None  # type: ignore[assignment]

# API Server imports
try:
    from pt_api_server import create_api_server

    API_SERVER_AVAILABLE = True
except ImportError:
    API_SERVER_AVAILABLE = False
    print(
        "Warning: Public API Server not available. Install flask and flask-cors to enable."
    )

# Long-term Holdings imports
try:
    from long_term_holdings_gui import HoldingsManagementGUI

    HOLDINGS_MANAGEMENT_AVAILABLE = True
except ImportError:
    HOLDINGS_MANAGEMENT_AVAILABLE = False
    print("Warning: Long-term Holdings not available.")

# Real-time Market Data imports
try:
    from real_time_market_data_gui import MarketDataGUI

    MARKET_DATA_GUI_AVAILABLE = True
except ImportError:
    MARKET_DATA_GUI_AVAILABLE = False
    print("Warning: Real-time Market Data GUI not available.")

# Portfolio Optimization imports
try:
    from portfolio_optimizer_gui import PortfolioOptimizerGUI

    PORTFOLIO_OPTIMIZER_AVAILABLE = True
except ImportError:
    PORTFOLIO_OPTIMIZER_AVAILABLE = False
    print("Warning: Portfolio Optimization Engine not available.")

# Backtesting Framework imports
try:
    from backtesting_gui import BacktestingGUI

    BACKTESTING_FRAMEWORK_AVAILABLE = True
except ImportError:
    BACKTESTING_FRAMEWORK_AVAILABLE = False
    print("Warning: Backtesting Framework not available.")

# Performance Attribution imports
try:
    from performance_attribution_gui import PerformanceAttributionGUI

    PERFORMANCE_ATTRIBUTION_AVAILABLE = True
except ImportError:
    PERFORMANCE_ATTRIBUTION_AVAILABLE = False
    print("Warning: Performance Attribution Engine not available.")

# Institutional Trading imports
try:
    from institutional_trading_gui import InstitutionalTradingGUI

    INSTITUTIONAL_TRADING_AVAILABLE = True
except ImportError:
    INSTITUTIONAL_TRADING_AVAILABLE = False
    print("Warning: Institutional Trading System not available.")


class ToolTip:
    """Simple tooltip helper for widgets. ``text`` may be a string or a callable
    returning one, which is called each time the tooltip is shown."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.on_enter)
        self.widget.bind("<Leave>", self.on_leave)

    def on_enter(self, event=None):
        """Show tooltip on mouse enter."""
        if self.tooltip_window is not None:
            return

        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 5
        y = self.widget.winfo_rooty() + self.widget.winfo_height() // 2

        try:
            text = self.text() if callable(self.text) else self.text
        except Exception:
            return
        if not text:
            return

        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        p = ui_theme.active_palette()  # a dark tooltip, like the rest of the hub
        label = tk.Label(
            self.tooltip_window,
            text=text,
            background=p["PANEL2"],
            foreground=p["FG"],
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=p["BORDER"],
            highlightcolor=p["BORDER"],
            font=ui_tokens.font("caption"),
            padx=5,
            pady=2,
            justify="left",
            wraplength=420,
        )
        label.pack()

    def on_leave(self, event=None):
        """Hide tooltip on mouse leave."""
        if self.tooltip_window is not None:
            self.tooltip_window.destroy()
            self.tooltip_window = None


# Widgets take their colours from ui_theme.active_palette(): dark, or blue in paper
# mode (ui_tokens holds every colour; ui_theme builds the ttk styles).

# Status colours (training table, live output): busy amber, done green; idle is
# the palette's MUTED grey.
STATUS_AMBER = ui_tokens.STATUS["warn"]
STATUS_GREEN = ui_tokens.STATUS["good"]
STATUS_RED = ui_tokens.STATUS["bad"]
LOG_SHORT = ui_tokens.STATUS["short"]

# Chart colours: surfaces, level lines and price tags, trade markers
CHART = ui_tokens.CHART
LINES = ui_tokens.CHART_LINES
MARKERS = ui_tokens.TRADE_MARKERS
CHART_FONT_PT = ui_tokens.CHART_FONT_PT
SPACE = ui_tokens.SPACE  # spacing scale, in pixels
# The chart tab row (owner, 2026-10-14): the coin buttons sit TAB_BUTTON_GAP above
# the plot. Before, each coin chart had its status line in a row between them and
# the plot, CHART_STATUS_ROW_PADY above and below it (a chart on its own still
# has), and the gap under the buttons was FORMER_TAB_BUTTON_GAP.
TAB_BUTTON_GAP = SPACE["xs"]
FORMER_TAB_BUTTON_GAP = SPACE["sm"]
CHART_STATUS_ROW_PADY = SPACE["sm"]
# Short of room, the coin buttons narrow to this (and scroll) before the status line
MIN_TAB_BUTTONS_W = 60

# The bottom panel's module tabs, left to right (owner, 2026-11-04): change the
# order here. Holdings Management follows Long-term Holdings while it exists; a tab
# not built is skipped. Order Management has the order types Advanced Orders had
# (owner, 2026-11-05).
MODULE_TAB_ORDER = (
    "Current Trades",
    "Trade History",
    "Order Management",
    "Market Data",
    "Long-term Holdings",
    "Holdings Management",
    "Performance Attribution",
    "Backtesting Framework",
    "Portfolio Optimization",
    "LLM Research",
    "Institutional Trading",
)


def module_tab_name(text: str) -> str:
    """A bottom tab's name as MODULE_TAB_ORDER spells it (its label is on two lines)."""
    return " ".join(str(text).split())


# Live-output colouring: the first rule that matches a line picks its tag.
_LOG_LINE_RULES = (
    ("log_state", re.compile(r"stopped from the hub")),
    (
        "log_error",
        re.compile(
            r"\bERROR\b|EXCEPTION IN|Traceback|Error in main loop|\[FAILED\]"
            r"|EMERGENCY STOP|RISK HALT|Trading halted|ORDER (FAILED|REFUSED)"
            r"|^\[[^\]]+\] Error |\[process exited, code -?[1-9]|\[log reader stopped"
        ),
    ),
    (
        "log_warn",
        re.compile(
            r"\bWARNING\b|WAITING FOR PRICE DATA|SKIPPED|Skipping [A-Z0-9]+:"
            r"|NOT TRAINED|MODEL NOT VERIFIED|NO MODEL IN USE|TRAINING - "
            r"|did not pass the entry gate|skipped this pass"
            r"|RISK (BLOCK|WARNING)|ORDER REJECTED|log lost|training data issue"
            r"|refused|[Ff]ailed"
        ),
    ),
    ("log_long", re.compile(r"\bLONG\b")),
    ("log_short", re.compile(r"\bSHORT\b")),
    (
        "log_state",
        re.compile(
            r"\] \[(training |stopped|process exited)|Initialization complete"
            r"|Model for |\[SUCCESS\]|SUCCESS:|Training completed|Runner starting"
        ),
    ),
    (
        "log_dim",
        re.compile(
            r"Processing |Completed iteration|\bWITHIN\b|\bINACTIVE\b|Epoch \d"
            r"|^\[[A-Z0-9]+\] (=+|=== .* ===)\s*$"
        ),
    ),
)


def _log_line_tag(line: str) -> Optional[str]:
    """The colour tag for one live-output line, or None for the default colour."""
    for tag, rule in _LOG_LINE_RULES:
        if rule.search(line):
            return tag
    return None


def _atomic_write_text(path: str, content: str) -> None:
    """Atomic text writing to prevent corruption during concurrent operations."""
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)  # Atomic operation on Windows/Unix
    except Exception:
        pass


class ScrollingRow(ttk.Frame):
    """One row of widgets that asks for its content's full width and scrolls
    sideways when the layout gives it less; the scrollbar shows only then.
    Children go in ``inner``."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0, height=1)
        try:
            bg = ttk.Style(self).lookup("TFrame", "background")
            if bg:
                self._canvas.configure(bg=bg)
        except Exception:
            pass
        self._bar = ttk.Scrollbar(self, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(xscrollcommand=self._bar.set)
        self.inner = ttk.Frame(self._canvas)
        self._canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._canvas.pack(side="top", fill="x")
        self.inner.bind("<Configure>", self._fit, add="+")
        self._canvas.bind("<Configure>", self._fit, add="+")

    def add(self, widget: tk.Widget, padx=(0, 0), pady=(0, 0)) -> None:
        widget.pack(side="left", padx=padx, pady=pady)

    @property
    def scrolls(self) -> bool:
        return self._bar.winfo_manager() == "pack"

    def _fit(self, event=None) -> None:
        width, height = self.inner.winfo_reqwidth(), self.inner.winfo_reqheight()
        self._canvas.configure(height=height, scrollregion=(0, 0, width, height))
        if int(float(self._canvas.cget("width"))) != width:
            self._canvas.configure(width=width)
        need = width > self._canvas.winfo_width() > 1
        if need and not self.scrolls:
            self._bar.pack(side="top", fill="x", pady=(0, ui_tokens.SPACE["xs"]))
        elif not need and self.scrolls:
            self._bar.pack_forget()
            self._canvas.xview_moveto(0)


@dataclass
class _WrapItem:
    w: tk.Widget
    padx: Tuple[int, int] = (0, 0)
    pady: Tuple[int, int] = (0, 0)


class WrapFrame(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._items: List[_WrapItem] = []
        self._reflow_pending = False
        self._in_reflow = False
        self.bind("<Configure>", self._schedule_reflow)

    def add(self, widget: tk.Widget, padx=(0, 0), pady=(0, 0)) -> None:
        self._items.append(_WrapItem(widget, padx=padx, pady=pady))
        self._schedule_reflow()

    def clear(self, destroy_widgets: bool = True) -> None:
        for it in list(self._items):
            try:
                it.w.grid_forget()
            except Exception:
                pass
            if destroy_widgets:
                try:
                    it.w.destroy()
                except Exception:
                    pass
        self._items = []
        self._schedule_reflow()

    def _schedule_reflow(self, event=None) -> None:
        if self._reflow_pending:
            return
        self._reflow_pending = True
        self.after_idle(self._reflow)

    def _reflow(self) -> None:
        if self._in_reflow:
            self._reflow_pending = False
            return

        self._reflow_pending = False
        self._in_reflow = True
        try:
            width = self.winfo_width()
            if width <= 1:
                return
            usable_width = max(1, width - 6)

            for it in self._items:
                it.w.grid_forget()

            row = 0
            col = 0
            x = 0

            for it in self._items:
                reqw = max(it.w.winfo_reqwidth(), it.w.winfo_width())

                needed = 10 + reqw + it.padx[0] + it.padx[1]

                if col > 0 and (x + needed) > usable_width:
                    row += 1
                    col = 0
                    x = 0

                it.w.grid(row=row, column=col, sticky="w", padx=it.padx, pady=it.pady)
                x += needed
                col += 1
        finally:
            self._in_reflow = False


# -----------------------------
# Settings / Paths
# -----------------------------

# Settings > Risk's position and DCA limits (the hub's settings, read by the trader)
RISK_LIMIT_KEYS = (
    "start_allocation_pct",
    "min_order_margin_pct",
    "max_coin_allocation_pct",
    "dca_multiplier",
    "max_dca_buys_per_24h",
)

DEFAULT_SETTINGS = {
    "main_neural_dir": "",
    "coins": ["BTC", "ETH", "XRP", "BNB", "DOGE"],
    "trade_start_level": 3,  # trade starts when long signal >= this level (1..7)
    # A new trade: this % of the account value, at least the exchange's minimum order
    "start_allocation_pct": position_sizing.DEFAULT_START_ALLOCATION_PCT,
    # An entry raised to the exchange's minimum order is raised by this % more, so the
    # position stays above the minimum when valued at the bid after fees
    "min_order_margin_pct": position_sizing.DEFAULT_MIN_ORDER_MARGIN_PCT,
    # The most one coin may hold, at cost, as % of the account: DCA buys stop there
    "max_coin_allocation_pct": position_sizing.DEFAULT_MAX_COIN_ALLOCATION_PCT,
    position_sizing.DEFAULTS_VERSION_KEY: position_sizing.DEFAULTS_VERSION,
    "dca_multiplier": 2.0,  # DCA buy size = current value * this (2.0 => total scales ~3x per DCA)
    "dca_levels": [
        -2.5,
        -5.0,
        -10.0,
        -20.0,
        -30.0,
        -40.0,
        -50.0,
    ],  # Hard DCA triggers (percent PnL)
    "max_dca_buys_per_24h": 2,  # max DCA buys per coin in rolling 24h window (0 disables DCA buys)
    # --- Trailing Profit Margin settings (used by pt_trader.py; shown in GUI settings) ---
    "pm_start_pct_no_dca": 5.0,
    "pm_start_pct_with_dca": 2.5,
    "trailing_gap_pct": 0.5,
    # --- Multi-Exchange Settings ---
    "region": "us",  # us, eu, global
    "primary_exchange": "",  # No exchange configured by default
    "price_comparison_enabled": True,  # Compare prices across exchanges
    "auto_best_price": False,  # Automatically use best price exchange
    "default_timeframe": "1hour",
    "timeframes": [
        "1min",
        "5min",
        "15min",
        "30min",
        "1hour",
        "2hour",
        "4hour",
        "8hour",
        "12hour",
        "1day",
        "1week",
    ],
    "candles_limit": 120,
    "ui_refresh_seconds": 1.0,
    "chart_refresh_seconds": 10.0,
    "hub_data_dir": "",  # if blank, defaults to <this_dir>/hub_data
    "auto_start_scripts": False,  # start the runner, then the trader, at launch
    # --- Training Automation Settings ---
    "training_auto_interval_hours": 6,  # Auto re-train every 6 hours after manual training
    "training_stale_warning_hours": 3,  # Show warning when training is 3+ hours old
    "training_auto_enabled": True,  # Enable automatic re-training
    "training_age_indicators": True,  # Show color-coded training age indicators
    # --- Public API Server Settings ---
    "api_server_enabled": False,  # Enable public REST API server
    "api_server_host": "127.0.0.1",  # API server host (127.0.0.1 for localhost only)
    "api_server_port": 8080,  # API server port
    # --- Futures Trading Configuration ---
    "futures_trading": {
        "long_enabled": False,  # Enable long futures trading
        "short_enabled": False,  # Enable short futures trading
        "max_leverage": 10,  # Maximum leverage for futures trading
        "risk_per_trade": 2.0,  # Risk percentage per trade
    },
    # --- Alerts Configuration ---
    "alerts_config": {
        "version": "5/3/2022/9am",  # Alerts version timestamp
        "enabled": True,  # Enable alert system
        "notification_methods": ["gui"],  # Notification methods: gui, email, webhook
    },
    # --- Paper Trading Mode (issue #86) ---
    # The mode itself is `trading.mode` in pt_config.json (see trading_mode.py).
    # While paper, the hub paints blue (not black) and shows a PAPER TRADING
    # banner + label so the user cannot mistake it for live trading.
    PAPER_MODE_BALANCE_KEY: 10000.0,
    # Paper trading opens new trades in the coins above ("inherit") or in a chosen set
    # of them ("override"); see paper_coins.py. Live trading uses the coins above.
    paper_coins.MODE_KEY: paper_coins.INHERIT,
    paper_coins.COINS_KEY: [],
}


SETTINGS_FILE = pt_paths.GUI_SETTINGS_FILE  # in pt_paths.config_dir()


def _safe_read_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _safe_write_json(path: str, data: dict) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


# Long-term Holdings tab (owner, 2026-11-04)
LONG_TERM_HOLDINGS_SUBTITLE = (
    "Manual HODL positions, tracked separately from the trading account. "
    "Not included in Value, Buying Power or % in Trade."
)


def _read_trade_history_jsonl(path: str) -> List[dict]:
    """
    Reads hub_data/trade_history.jsonl written by pt_trader.py.
    Returns a list of dicts (only buy/sell rows).
    """
    out: List[dict] = []
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        obj = json.loads(ln)
                        side = str(obj.get("side", "")).lower().strip()
                        if side not in ("buy", "sell"):
                            continue
                        out.append(obj)
                    except Exception:
                        continue
    except Exception:
        pass
    return out


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _fmt_money(x: float) -> str:
    """Format a USD *amount* (account value, position value, etc.) as dollars with 2 decimals."""
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "N/A"


def _fmt_price(x: Any) -> str:
    """
    Format a USD *price/level* with dynamic decimals based on magnitude.
    Examples:
      50234.12   -> $50,234.12
      123.4567   -> $123.457
      1.234567   -> $1.2346
      0.06234567 -> $0.062346
      0.00012345 -> $0.00012345
    """
    try:
        if x is None:
            return "N/A"

        v = float(x)
        if not math.isfinite(v):
            return "N/A"

        sign = "-" if v < 0 else ""
        av = abs(v)

        # Choose decimals by magnitude (more detail for smaller prices).
        if av >= 1000:
            dec = 2
        elif av >= 100:
            dec = 3
        elif av >= 1:
            dec = 4
        elif av >= 0.1:
            dec = 5
        elif av >= 0.01:
            dec = 6
        elif av >= 0.001:
            dec = 7
        else:
            dec = 8

        s = f"{av:,.{dec}f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")

        return f"{sign}${s}"
    except Exception:
        return "N/A"


def _fmt_pct(x: float) -> str:
    try:
        return f"{float(x):+.2f}%"
    except Exception:
        return "N/A"


def _now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _clock(ts: float) -> str:
    """HH:MM:SS for a time later today, with the date for any other day."""
    at = time.localtime(ts)
    if time.strftime("%Y-%m-%d", at) == time.strftime("%Y-%m-%d"):
        return time.strftime("%H:%M:%S", at)
    return time.strftime("%d %b %H:%M:%S", at)


# The scripts the hub runs, in the program folder: part of the program, not settings
# (a value saved by an older release is dropped when the settings are read).
# FDS-MDL: the pattern-matching trainer (a port of upstream's); the old stub
# pt_trainer.py is marked MOCK and refused unless allow_mock_trainer is set.
SYSTEM_SCRIPTS = {
    "script_neural_trainer": "pt_pattern_trainer.py",
    "script_neural_runner2": "pt_thinker.py",
    "script_trader": "pt_trader.py",
}
# A coin folder's latest training run's entry gate decision (pt_pattern_trainer.GATE_FILE)
GATE_FILE = "model_gate.json"
# Settings > Training, "Check the models in use...": the longest one coin's check may take
GATE_CHECK_TIMEOUT_S = 3600

# Settings > System, Start ... when the hub opens: after the window is up
AUTO_START_DELAY_MS = 1500
# How long a notice (a training run ending, an auto start skipped) stays up
NOTICE_SECONDS = 8.0
# Settings > Paper trading, With no fresh price: the shown words for each policy
PAPER_PRICE_RULES = {
    "pause": "Don't fill; wait for a fresh price",
    "simulate_and_flag": "Fill on the last price and flag the trade",
}

# A retrain that fell due while the hub was closed waits this long after start-up,
# so the window is up before trainers start
OVERDUE_RETRAIN_DELAY_S = 60.0
# Settings > Training, Retrain every: a model counts as trained for 14 days
RETRAIN_HOURS_RANGE = (1.0, 336.0)


# -----------------------------
# Neural folder detection
# -----------------------------


def build_coin_folders(main_dir: str, coins: List[str]) -> Dict[str, str]:
    """
    Mirrors your convention:
      BTC uses main_dir directly
      other coins typically have subfolders inside main_dir (auto-detected)

    Returns { "BTC": "...", "ETH": "...", ... }
    """
    out: Dict[str, str] = {}
    main_dir = main_dir or pt_paths.neural_dir()

    # BTC folder
    out["BTC"] = main_dir

    # Auto-detect subfolders
    if os.path.isdir(main_dir):
        for name in os.listdir(main_dir):
            p = os.path.join(main_dir, name)
            if not os.path.isdir(p):
                continue
            sym = name.upper().strip()
            if sym in coins and sym != "BTC":
                out[sym] = p

    # Fallbacks for missing ones
    for c in coins:
        c = c.upper().strip()
        if c not in out:
            out[c] = os.path.join(main_dir, c)  # best-effort fallback

    return out


def read_price_levels_from_html(path: str) -> List[float]:
    """
    pt_thinker writes a python-list-like string into low_bound_prices.html / high_bound_prices.html.

    Example (commas often remain):
        "43210.1, 43100.0, 42950.5"

    So we normalize separators before parsing.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()

        if not raw:
            return []

        # Normalize common separators that pt_thinker can leave behind
        raw = (
            raw.replace(",", " ").replace("[", " ").replace("]", " ").replace("'", " ")
        )

        vals: List[float] = []
        for tok in raw.split():
            try:
                v = float(tok)

                # Filter obvious sentinel values used by pt_thinker for "inactive" slots
                if v <= 0:
                    continue
                if v >= 9e15:  # pt_thinker uses 99999999999999999
                    continue

                vals.append(v)
            except Exception:
                pass

        # De-dupe while preserving order (small rounding to avoid float-noise duplicates)
        out: List[float] = []
        seen = set()
        for v in vals:
            key = round(v, 12)
            if key in seen:
                continue
            seen.add(key)
            out.append(v)

        return out
    except Exception:
        return []


def read_int_from_file(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        return int(float(raw))
    except Exception:
        return 0


def read_short_signal(folder: str) -> int:
    txt = os.path.join(folder, "short_dca_signal.txt")
    if os.path.isfile(txt):
        return read_int_from_file(txt)
    else:
        return 0


# -----------------------------
# Candle fetching: the exchanges in Settings, primary first (FDS-MX-001 phase G)
# -----------------------------


class CandleFetcher:
    """
    The chart's candles from the exchanges in Settings: the primary exchange, else the
    next that serves the coin (``pt_multi_exchange.market_exchanges``). The bar still
    forming is included where the exchange serves that candle size itself.
    ``last_source`` names the exchange and market each chart's candles came from (for
    logs: the chart itself never names a data provider, FDS-CHART-001 section 7.1).
    """

    def __init__(self, manager=None):
        self._manager = manager  # None: the shared exchange layer
        self.last_source: Dict[Tuple[str, str], str] = {}

        # Enhanced in-memory cache with automatic cleanup
        # key: (symbol, timeframe, limit) -> (saved_time_epoch, candles, access_count)
        self._cache: Dict[Tuple[str, str, int], Tuple[float, List[dict], int]] = {}
        self._cache_ttl_seconds: float = 10.0
        self._cache_max_entries: int = 50  # Prevent unlimited memory growth
        self._cache_cleanup_threshold: int = 60  # Clean up when we exceed this

    def get_klines(self, symbol: str, timeframe: str, limit: int = 120) -> List[dict]:
        """
        Returns candles oldest->newest as:
          [{"ts": int, "open": float, "high": float, "low": float, "close": float}, ...]
        """
        from candlestick_patterns import HUB_TO_CANDLE
        from market_data.timeframes import candle_timeframe_seconds

        symbol = symbol.upper().strip()
        limit = int(limit or 0)
        tf = HUB_TO_CANDLE.get(timeframe, timeframe)
        try:
            step = candle_timeframe_seconds(tf)
        except ValueError:
            return []

        now = time.time()
        cache_key = (symbol, timeframe, limit)
        cached = self._cache.get(cache_key)
        if (
            cached
            and len(cached) >= 2
            and (now - float(cached[0])) <= float(self._cache_ttl_seconds)
        ):
            # Update access count for LRU cleanup
            access_count = cached[2] + 1 if len(cached) > 2 else 1
            self._cache[cache_key] = (cached[0], cached[1], access_count)
            return cached[1]

        # Clean up cache if it gets too large
        if len(self._cache) > self._cache_cleanup_threshold:
            self._cleanup_cache()

        # enough bars back for the window (and a little more), up to now
        now_ms = int(now * 1000)
        start_ms = now_ms - step * 1000 * (max(limit, 1) + 2)
        try:
            if self._manager is not None:
                manager = self._manager
            else:
                from pt_multi_exchange import market_exchanges

                manager = market_exchanges()
            answer = manager.candles(
                f"{symbol}-USD", tf, start_ms, now_ms, now_ms, closed_only=False
            )
        except Exception:
            return []

        candles: List[dict] = [
            {
                "ts": int(r[0]) // 1000,
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
            }
            for r in answer.value
        ]
        if limit and len(candles) > limit:
            candles = candles[-limit:]
        self.last_source[(symbol, timeframe)] = f"{answer.exchange} {answer.pair}"
        self._cache[cache_key] = (now, candles, 1)
        return candles

    def _cleanup_cache(self) -> None:
        """Clean up old cache entries to prevent unlimited memory growth."""
        try:
            now = time.time()
            # Remove expired entries first
            expired_keys = [
                k
                for k, v in self._cache.items()
                if len(v) >= 1 and (now - float(v[0])) > self._cache_ttl_seconds
            ]
            for k in expired_keys:
                del self._cache[k]

            # If still too many, remove least recently used entries
            if len(self._cache) > self._cache_max_entries:
                # Sort by access count (ascending) to remove least used
                sorted_items = sorted(
                    self._cache.items(), key=lambda x: x[1][2] if len(x[1]) > 2 else 0
                )
                # Keep only the most accessed entries
                keep_count = self._cache_max_entries
                self._cache = dict(sorted_items[-keep_count:])
        except Exception:
            # If cleanup fails, clear entire cache as fallback
            self._cache.clear()


# -----------------------------
# Chart widget
# -----------------------------

# Chart margins follow the text actually drawn (title, axis labels, tick labels, price
# tags). Fixed fractions left a wide, short chart a fifth of its height empty above and
# below and an eighth of its width at each side.
CHART_PAD = 0.4  # space round the chart's outer text, as a fraction of the font size
TAG_FONT_PT = CHART_FONT_PT  # right-hand price tags (ASK, BID, AVG, DCA, SELL)
TAG_BOX_PAD = 0.18  # their box padding, as a fraction of the font size
NAME_GAP_PT = 6  # price name above the plot: clear of a price label on the top tick


def _fit_axes(fig: Figure, right: float = 1.0, top: float = 1.0) -> None:
    """Fit the plot and its axis text into the figure, leaving the share of the width to
    the right of ``right`` and the share of the height above ``top`` free."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # too small to fit: keep the last layout
            fig.tight_layout(
                pad=CHART_PAD, rect=(0.0, 0.0, max(0.5, right), max(0.5, top))
            )
    except Exception:
        pass


def _fit_axes_beside(fig: Figure, tags: List[Any], top: float = 1.0) -> float:
    """Fit the axes, then take only as much width from the plot as the price tags need
    beyond the space the last date label already holds on the right. Returns the
    ``right`` to fit with again."""
    _fit_axes(fig, 1.0, top)
    if not tags:
        return 1.0
    try:
        renderer = fig.canvas.get_renderer()
        px_per_pt = fig.dpi / 72.0
        box_px = TAG_BOX_PAD * TAG_FONT_PT * px_per_pt
        edge_px = CHART_PAD * float(rcParams["font.size"]) * px_per_pt
        end = max(t.get_window_extent(renderer).x1 for t in tags) + box_px + edge_px
        over = end - float(fig.bbox.x1)
    except Exception:
        return 1.0
    if over <= 0:
        return 1.0
    right = max(0.6, 1.0 - over / float(fig.bbox.width))
    _fit_axes(fig, right, top)
    return right


def _top_below(fig: Figure, ax, reserve_px: float, top: float) -> float:
    """The ``top`` to fit with again so the plot starts ``reserve_px`` below the
    figure's top edge, where the hub puts the Timeframe box and the cog; ``top`` when
    it already does."""
    try:
        height = float(fig.bbox.height)
        over = float(ax.get_window_extent().y1) - (height - float(reserve_px))
    except Exception:
        return top
    if reserve_px <= 0 or over <= 0 or height <= 0:
        return top
    return top - over / height


def _corner_axis_names(fig: Figure, ax, price_name: str, time_name: str) -> List[Any]:
    """The axis names in two corners instead of a row and a column of their own: the
    price name level, above the price labels at the top left; the time name beside the
    last date at the bottom right. Figure text, so tight_layout leaves them out and
    the chart keeps room for them itself."""
    size = rcParams["axes.labelsize"]
    edge_pt = CHART_PAD * float(rcParams["font.size"])
    tick_pt = float(rcParams["xtick.major.size"]) + float(rcParams["xtick.major.pad"])
    above = blended_transform_factory(
        fig.transFigure, ax.transAxes
    ) + ScaledTranslation(edge_pt / 72.0, NAME_GAP_PT / 72.0, fig.dpi_scale_trans)
    beside = ax.transAxes + ScaledTranslation(
        4 / 72.0, -tick_pt / 72.0, fig.dpi_scale_trans
    )
    return [
        fig.text(
            0,
            1,
            price_name,
            transform=above,
            ha="left",
            va="bottom",
            color=CHART["text"],
            fontsize=size,
        ),
        fig.text(
            1,
            0,
            time_name,
            transform=beside,
            ha="left",
            va="top",
            color=CHART["text"],
            fontsize=size,
        ),
    ]


def _end_date_inside(ax) -> None:
    """The last date label ends at its candle instead of centring on it, so it does not
    hang past the plot and hold a strip of margin open."""
    try:
        labels = ax.get_xticklabels()
        if len(labels) > 1:
            labels[-1].set_horizontalalignment("right")
    except Exception:
        pass


# How long a coin's chart waits, the first time a coin and timeframe are shown, for
# its candlestick patterns: the chart is then drawn once, with room for their labels.
PATTERN_WAIT_MS = 1500
# The runner writes this low bound for a timeframe with no prediction: not a price.
NEURAL_PLACEHOLDER_LOW = 0.01
# A trade dot's label: 10 pt above the dot, one line of chart text, and the dot.
MARKER_REACH_PT = 10 + CHART_FONT_PT * 1.2 + 4


def padded_range(lo: float, hi: float) -> Tuple[float, float]:
    """``(lo, hi)`` with a 3% margin each side (a flat range gets a small one)."""
    pad = (hi - lo) * 0.03
    if not math.isfinite(pad) or pad <= 0:
        pad = max(abs(lo) * 0.001, 1e-6)
    return lo - pad, hi + pad


def _positive(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


class CandleChart(ttk.Frame):
    """One coin's candles with its lines, price tags, trade dots and pattern labels.

    The axes are framed once, before anything is drawn, from everything the chart
    will show: every candle's high and low, every line drawn (neural levels, bid,
    ask, average cost, DCA, sell), every trade dot, and room for the trade labels
    and the pattern labels; the price tags get their strip whether or not a tag is
    shown yet. Autoscaling is then off, so no layer drawn afterwards can move or
    resize the plot. The frame is worked out again only when the coin, the
    timeframe or the candles shown change, when something to show falls outside it,
    or when the window is resized (``_frame``)."""

    def __init__(
        self,
        parent: tk.Widget,
        fetcher: CandleFetcher,
        coin: str,
        settings_getter,
        trade_history_path: str,
        status_parent: Optional[tk.Widget] = None,
    ):
        super().__init__(parent)
        self.fetcher = fetcher
        self.coin = coin
        self.settings_getter = settings_getter
        self.trade_history_path = trade_history_path

        self.timeframe_var = tk.StringVar(
            value=self.settings_getter()["default_timeframe"]
        )
        # how far down the plot starts, for what the hub puts on its top right corner
        self.overlay_px: Callable[[], int] = lambda: 0

        # The status line (neural readout, pattern count). In the hub it sits in the
        # tab row, right of the coin buttons, and the hub shows the selected chart's
        # (owner, 2026-10-14); on its own the chart gives it a row above the plot.
        if status_parent is None:
            top = ttk.Frame(self)
            top.pack(fill="x", padx=SPACE["sm"], pady=CHART_STATUS_ROW_PADY)
        else:
            top = ttk.Frame(status_parent)  # packed by the hub while selected
        self.status_frame = top

        # No coin name and no timeframe box here (owner, 2026-10-14): the coin
        # buttons above name the chart, and the hub's Timeframe box at the end of
        # that row calls set_timeframe().
        self._tf_after_id = None

        # Two lines (owner, 2026-11-04): the neural readout, the pattern count below
        self.neural_status_label = ttk.Label(top, text="Neural: N/A")
        self.neural_status_label.pack(side="top", anchor="w")

        # Candlestick patterns (FDS-CHART-001): a status line (click: list of all
        # detections) and the Chart settings pop-out.
        self.patterns_status_label = ttk.Label(top, text="", cursor="hand2")
        self.patterns_status_label.pack(side="top", anchor="w")

        # The Chart settings cog sits on the chart's top right corner, placed by the
        # hub. No "Last:" time: it was the neural level files' age, which says
        # nothing about the chart, whose candles are fetched on every refresh
        # (owner, 2026-10-14).

        # Figure
        # IMPORTANT: keep a stable DPI and resize the figure to the widget's pixel size.
        # On Windows scaling, trying to "sync DPI" via winfo_fpixels("1i") can produce the
        # exact right-side blank/covered region you're seeing.
        self.fig = Figure(figsize=(6.5, 3.5), dpi=100)
        self.fig.patch.set_facecolor(CHART["figure"])
        # margins: fit_layout(), after every refresh and resize

        self.ax = self.fig.add_subplot(111)
        self._apply_dark_chart_style()
        # no title: the toolbar above already names the coin and the timeframe
        self._base_ylim: Optional[Tuple[float, float]] = None  # what is shown + pad
        self._price_tags: List[Any] = []
        # the price range the axes keep (see the class docstring): key, data range,
        # padded range, label reach, the range set and the canvas size it was set for
        self._frame: Optional[Dict[str, Any]] = None
        self._tag_probe: Optional[Any] = None  # an invisible tag: the strip's width
        # a refresh held back until this coin and timeframe's patterns are in
        self._pending_refresh: Optional[Dict[str, Any]] = None
        self._wait_after_id = None
        self._no_wait_key = None  # waited once already: draw without the labels

        # axis names in the corners (owner, 2026-10-14): fit_layout() keeps room. The
        # price name is the coin's pair as the connected exchange writes it, the one
        # format every pair in the app is shown in (exchange_symbols; with no exchange
        # connected, the exchange layer's BTC-USD)
        self._price_name, self._time_name = _corner_axis_names(
            self.fig, self.ax, exchange_symbols.market_pair(coin).pair, "Time"
        )

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        canvas_w = self.canvas.get_tk_widget()
        canvas_w.configure(bg=CHART["figure"])

        # Remove horizontal padding here so the chart widget truly fills the container.
        canvas_w.pack(fill="both", expand=True, padx=0, pady=0)

        # Keep the matplotlib figure EXACTLY the same pixel size as the Tk widget.
        # FigureCanvasTkAgg already sizes its backing PhotoImage to e.width/e.height.
        # Multiplying by tk scaling here makes the renderer larger than the PhotoImage,
        # which produces the "blank/covered strip" on the right.
        self._last_canvas_px = (0, 0)
        self._resize_after_id = None

        def _on_canvas_configure(e):
            try:
                w = int(e.width)
                h = int(e.height)
                if w <= 1 or h <= 1:
                    return

                if (w, h) == self._last_canvas_px:
                    return
                self._last_canvas_px = (w, h)

                dpi = float(self.fig.get_dpi() or 100.0)
                self.fig.set_size_inches(w / dpi, h / dpi, forward=True)

                # Debounce redraws during live resize
                if self._resize_after_id:
                    try:
                        self.after_cancel(self._resize_after_id)
                    except Exception:
                        pass
                self._resize_after_id = self.after_idle(self._fit_and_draw)
            except Exception:
                pass

        canvas_w.bind("<Configure>", _on_canvas_configure, add="+")

        self._last_refresh = 0.0

        from pt_chart_patterns import PatternLayer

        self.pattern_layer = PatternLayer(self, status_label=self.patterns_status_label)

    def destroy(self) -> None:
        """In the hub the status line is a child of the tab row, not of the chart:
        it goes with the chart, or it would stay in the row, its pattern label
        calling into a destroyed chart."""
        frame = getattr(self, "status_frame", None)
        if frame is not None and frame.master is not self:
            try:
                frame.destroy()
            except tk.TclError:
                pass
        super().destroy()

    def set_timeframe(self, tf: str) -> None:
        """Show ``tf``, chosen in the hub's Timeframe box. Rapid changes are debounced
        so redraws don't stack."""
        self.timeframe_var.set(tf)
        try:
            if self._tf_after_id:
                self.after_cancel(self._tf_after_id)
        except Exception:
            pass

        def _do():
            # Ask the hub to refresh charts on the next tick (single refresh)
            try:
                self.event_generate("<<TimeframeChanged>>", when="tail")
            except Exception:
                pass

        self._tf_after_id = self.after(120, _do)

    def fit_layout(self) -> None:
        """Size the margins to the text drawn: the price name above the plot, the tick
        labels, and on the right a strip as wide as the widest price tag could be
        (``_tag_probe``), kept whether or not a tag is shown. The price range is the
        frame's and is not changed here. A pattern label at either end of the plot is
        aligned inwards."""
        fig = self.fig
        layer = getattr(self, "pattern_layer", None)
        labels = layer.label_artists() if layer is not None else []
        probe = [self._tag_probe] if self._tag_probe is not None else []
        for art in labels + self._price_tags + probe:
            art.set_in_layout(False)
        top = 1.0  # a strip above the plot for the price name
        try:
            name_px = self._price_name.get_window_extent(fig.canvas.get_renderer())
            gap_px = NAME_GAP_PT * fig.dpi / 72.0
            top = 1.0 - (name_px.height + gap_px) / float(fig.bbox.height)
        except Exception:
            pass
        # the time name sits right of the plot, like the price tags
        _fit_axes_beside(fig, probe + [self._time_name], top)
        lower = _top_below(fig, self.ax, self.overlay_px(), top)
        if lower < top:  # clear of the hub's Timeframe box and cog
            _fit_axes_beside(fig, probe + [self._time_name], lower)
        if layer is not None and labels:
            layer.keep_labels_inside()

    def _set_frame(self, reach: List[Tuple[float, bool, float]]) -> None:
        """Set the price range: the padded range of what is shown, widened as far as
        the labels in ``reach`` need to sit inside the plot (the margins are fitted to
        it before and after), then recorded with the canvas size."""
        from pt_chart_patterns import room_for_labels

        frame = self._frame
        ax = self.ax
        ax.set_ylim(*frame["base"])
        self.fit_layout()
        if reach:
            try:
                height = float(ax.get_window_extent().height)
                ax.set_ylim(*room_for_labels(*frame["base"], reach, height))
            except Exception:
                pass
            self.fit_layout()  # the new range may change the price labels' width
        ax.set_autoscale_on(False)
        frame["ylim"] = tuple(ax.get_ylim())
        frame["reach"] = list(reach)
        frame["size"] = self._last_canvas_px

    def _fit_and_draw(self) -> None:
        """After a resize: the labels' room in price depends on the plot's height, so
        the frame is set again for the new size."""
        self._resize_after_id = None
        if self._frame is not None and self._frame.get("ylim") is not None:
            self._set_frame(self._frame.get("reach") or [])
        else:
            self.fit_layout()
        self.canvas.draw_idle()

    def patterns_ready(self) -> None:
        """A pattern detection finished. A refresh held back for it is drawn now (the
        whole chart, framed with its labels' room); otherwise the labels are redrawn
        inside the frame the chart already has."""
        if self._wait_after_id is not None:
            try:
                self.after_cancel(self._wait_after_id)
            except Exception:
                pass
            self._wait_after_id = None
        args, self._pending_refresh = self._pending_refresh, None
        if args is not None:
            self.refresh(**args)
        else:
            self.pattern_layer.redraw()

    def _stop_waiting(self, key) -> None:
        """The patterns took longer than PATTERN_WAIT_MS: draw the chart without them;
        their labels then go inside its frame when they arrive."""
        self._wait_after_id = None
        args, self._pending_refresh = self._pending_refresh, None
        if args is not None:
            self._no_wait_key = key
            self.refresh(**args)

    def _apply_dark_chart_style(self) -> None:
        """Apply dark styling (called on init and after every ax.clear())."""
        try:
            self.fig.patch.set_facecolor(CHART["figure"])
            self.ax.set_facecolor(CHART["plot"])
            self.ax.tick_params(colors=CHART["text"])
            for spine in self.ax.spines.values():
                spine.set_color(CHART["grid"])
            self.ax.grid(True, color=CHART["grid"], linewidth=0.6, alpha=0.35)
        except Exception:
            pass

    def refresh(
        self,
        coin_folders: Dict[str, str],
        current_buy_price: Optional[float] = None,
        current_sell_price: Optional[float] = None,
        trail_line: Optional[float] = None,
        dca_line_price: Optional[float] = None,
        avg_cost_basis: Optional[float] = None,
        trader_running: bool = True,
    ) -> None:
        cfg = self.settings_getter()
        chart_cfg = chart_settings.normalize(cfg.get("chart"))
        candle_colors = chart_settings.palette(chart_cfg)
        hollow_up = chart_cfg["candle_style"] == "hollow_up"

        def show(key: str) -> bool:
            # each overlay can be hidden from Chart settings (FDS-CHART-001 8.2)
            return chart_settings.overlay_on(chart_cfg, key)

        tf = self.timeframe_var.get().strip()
        limit = int(cfg.get("candles_limit", 120))

        candles = self.fetcher.get_klines(self.coin, tf, limit=limit)

        folder = coin_folders.get(self.coin, "")
        low_path = os.path.join(folder, "low_bound_prices.html")
        high_path = os.path.join(folder, "high_bound_prices.html")

        # --- Enhanced cached neural reads (per path, by mtime with corruption protection) ---
        if not hasattr(self, "_neural_cache"):
            self._neural_cache = {}  # path -> (mtime, value, error_count)
            self._neural_cache_max_errors = 3

        def _cached(path: str, loader, default):
            """Enhanced caching with corruption protection and error tracking."""
            try:
                mtime = os.path.getmtime(path)
                # Check for .tmp files indicating interrupted writes
                tmp_path = path + ".tmp"
                if os.path.exists(tmp_path):
                    # Clean up interrupted atomic write
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
            except Exception:
                return default

            hit = self._neural_cache.get(path)
            if hit and len(hit) >= 2 and hit[0] == mtime:
                # Reset error count on successful cache hit
                if len(hit) > 2 and hit[2] > 0:
                    self._neural_cache[path] = (hit[0], hit[1], 0)
                return hit[1]

            # Load with error tracking
            try:
                v = loader(path)
                self._neural_cache[path] = (mtime, v, 0)
                return v
            except Exception as e:
                # Track errors to avoid repeatedly trying corrupted files
                error_count = hit[2] + 1 if hit and len(hit) > 2 else 1
                if error_count < self._neural_cache_max_errors:
                    self._neural_cache[path] = (mtime, default, error_count)
                return default

        long_levels = (
            _cached(low_path, read_price_levels_from_html, []) if folder else []
        )
        short_levels = (
            _cached(high_path, read_price_levels_from_html, []) if folder else []
        )

        long_sig_path = os.path.join(folder, "long_dca_signal.txt")
        long_sig = _cached(long_sig_path, read_int_from_file, 0) if folder else 0
        short_sig = read_short_signal(folder) if folder else 0

        # The first time this coin and timeframe are shown, their patterns are still
        # being detected: the chart keeps what it shows and is drawn once they are in
        # (patterns_ready), so the frame has their labels' room from the start.
        wait_key = (self.coin, tf)
        if (
            candles
            and self._no_wait_key != wait_key
            and self.pattern_layer.waiting_for(candles, tf, folder, chart_cfg)
        ):
            self._pending_refresh = {
                "coin_folders": coin_folders,
                "current_buy_price": current_buy_price,
                "current_sell_price": current_sell_price,
                "trail_line": trail_line,
                "dca_line_price": dca_line_price,
                "avg_cost_basis": avg_cost_basis,
                "trader_running": trader_running,
            }
            if self._wait_after_id is None:
                self._wait_after_id = self.after(
                    PATTERN_WAIT_MS, lambda: self._stop_waiting(wait_key)
                )
            return
        self._pending_refresh = None

        # --- Avoid full ax.clear() (expensive). Just clear artists. ---
        try:
            self.ax.lines.clear()
            self.ax.patches.clear()
            self.ax.collections.clear()  # scatter dots live here
            self.ax.texts.clear()  # labels/annotations live here
        except Exception:
            # fallback if matplotlib version lacks .clear() on these lists
            self.ax.cla()
            self._apply_dark_chart_style()  # the axis names are figure text: kept
        self._price_tags = []
        self._tag_probe = None

        if not candles:
            self.ax.text(
                0.5,
                0.5,
                f"{self.coin} ({tf}): no candles",
                transform=self.ax.transAxes,
                ha="center",
                va="center",
                color=CHART["text"],
            )
            self.pattern_layer.update([], tf, folder, chart_cfg)
            self._frame = None
            self._base_ylim = None
            self.fit_layout()
            self.canvas.draw_idle()
            return

        # --- everything the chart will show, before anything is drawn -------------------
        neural = []
        for key, levels in (
            ("neural_long", long_levels),
            ("neural_short", short_levels),
        ):
            if show(key):
                neural += [
                    v
                    for v in map(_positive, levels)
                    if v is not None and v != NEURAL_PLACEHOLDER_LOW
                ]
        line_prices = {
            key: price
            for key, price in (
                ("trail", _positive(trail_line)),
                ("dca", _positive(dca_line_price)),
                ("avg", _positive(avg_cost_basis)),
                ("ask", _positive(current_buy_price)),
                ("bid", _positive(current_sell_price)),
            )
            if show(key) and price is not None
        }
        markers = self._trade_markers(candles) if show("trades") else []
        shown = (
            [float(c["low"]) for c in candles]
            + [float(c["high"]) for c in candles]
            + neural
            + list(line_prices.values())
            + [m[1] for m in markers]
        )
        lo, hi = min(shown), max(shown)
        frame_key = (self.coin, tf, int(candles[0]["ts"]), len(candles))
        frame = self._frame
        keep = (
            frame is not None
            and frame.get("ylim") is not None
            and frame["key"] == frame_key
            and frame["lo"] <= lo
            and hi <= frame["hi"]
            and frame["size"] == self._last_canvas_px
            and frame["markers"] == bool(markers)
        )
        if not keep:
            self._frame = frame = {
                "key": frame_key,
                "lo": lo,
                "hi": hi,
                "base": padded_range(lo, hi),
                "markers": bool(markers),
                "ylim": None,
            }
        self._base_ylim = frame["base"]
        # Set the frame first, then switch autoscaling off: no layer below moves it.
        self.ax.set_xlim(-0.5, (len(candles) - 0.5) + 0.6)
        self.ax.set_ylim(*(frame["ylim"] or frame["base"]))
        self.ax.set_autoscale_on(False)

        # Candlestick drawing (green up / red down) - batch rectangles
        xs = getattr(self, "_xs", None)
        if not xs or len(xs) != len(candles):
            xs = list(range(len(candles)))
            self._xs = xs

        rects = []
        for i, c in enumerate(candles):
            o = float(c["open"])
            cl = float(c["close"])
            h = float(c["high"])
            l = float(c["low"])

            up = cl >= o
            candle_color = candle_colors["up"] if up else candle_colors["down"]

            # wick
            self.ax.plot([i, i], [l, h], linewidth=1, color=candle_color)

            # body
            bottom = min(o, cl)
            height = abs(cl - o)
            if height < 1e-12:
                height = 1e-12

            rects.append(
                Rectangle(
                    (i - 0.35, bottom),
                    0.7,
                    height,
                    # "hollow up": rising candles as outlines, so direction never
                    # depends on colour alone (FDS-CHART-001 section 9)
                    facecolor="none" if (hollow_up and up) else candle_color,
                    edgecolor=candle_color,
                    linewidth=1.2 if (hollow_up and up) else 1,
                    alpha=0.9,
                )
            )

        for r in rects:
            self.ax.add_patch(r)

        # Overlay Neural levels (blue long, orange short)
        for lv in long_levels if show("neural_long") else []:
            try:
                self.ax.axhline(
                    y=float(lv), linewidth=1, color=LINES["neural_long"], alpha=0.8
                )
            except Exception:
                pass

        for lv in short_levels if show("neural_short") else []:
            try:
                self.ax.axhline(
                    y=float(lv), linewidth=1, color=LINES["neural_short"], alpha=0.8
                )
            except Exception:
                pass

        # Overlay Trailing PM line (sell) and next DCA line
        try:
            if show("trail") and trail_line is not None and float(trail_line) > 0:
                self.ax.axhline(
                    y=float(trail_line), linewidth=1.5, color=LINES["trail"], alpha=0.95
                )
        except Exception:
            pass

        try:
            if show("dca") and dca_line_price is not None and float(dca_line_price) > 0:
                self.ax.axhline(
                    y=float(dca_line_price),
                    linewidth=1.5,
                    color=LINES["dca"],
                    alpha=0.95,
                )
        except Exception:
            pass

        # Overlay avg cost basis (yellow)
        try:
            if show("avg") and avg_cost_basis is not None and float(avg_cost_basis) > 0:
                self.ax.axhline(
                    y=float(avg_cost_basis),
                    linewidth=1.5,
                    color=LINES["avg"],
                    alpha=0.95,
                )
        except Exception:
            pass

        # Overlay current ask/bid prices. They come from the trader, so while it is
        # stopped they are its last prices, drawn dotted (owner, 2026-10-14).
        quote_style = "-" if trader_running else ":"
        try:
            if (
                show("ask")
                and current_buy_price is not None
                and float(current_buy_price) > 0
            ):
                self.ax.axhline(
                    y=float(current_buy_price),
                    linewidth=1.5,
                    linestyle=quote_style,
                    color=LINES["ask"],
                    alpha=0.95,
                )
        except Exception:
            pass

        try:
            if (
                show("bid")
                and current_sell_price is not None
                and float(current_sell_price) > 0
            ):
                self.ax.axhline(
                    y=float(current_sell_price),
                    linewidth=1.5,
                    linestyle=quote_style,
                    color=LINES["bid"],
                    alpha=0.95,
                )
        except Exception:
            pass

        # --- Trade dots (BUY / DCA / SELL) for THIS coin only ---
        for x, y, label, color in markers:
            self.ax.scatter([x], [y], s=35, color=color, zorder=6)
            self.ax.annotate(
                label,
                (x, y),
                textcoords="offset points",
                xytext=(0, 10),
                ha="center",
                fontsize=CHART_FONT_PT,
                color=CHART["text"],
                zorder=7,
            )

        # x tick labels (date + time) - evenly spaced, never overlapping duplicates
        n = len(candles)
        want = 5  # keep it readable even when the window is narrow
        if n <= want:
            idxs = list(range(n))
        else:
            step = (n - 1) / float(want - 1)
            idxs = []
            last = -1
            for j in range(want):
                i = int(round(j * step))
                if i <= last:
                    i = last + 1
                if i >= n:
                    i = n - 1
                idxs.append(i)
                last = i

        tick_x = [xs[i] for i in idxs]
        tick_lbl = [
            time.strftime(
                "%Y-%m-%d\n%H:%M", time.localtime(int(candles[i].get("ts", 0)))
            )
            for i in idxs
        ]

        try:
            self.ax.minorticks_off()
            self.ax.set_xticks(tick_x)
            self.ax.set_xticklabels(tick_lbl)
            self.ax.tick_params(axis="x", labelsize=CHART_FONT_PT)
            _end_date_inside(self.ax)
        except Exception:
            pass

        # Candlestick pattern labels (FDS-CHART-001), placed by open time; a pattern
        # at one of this chart's trades ranks first (shown dots or not)
        trades = markers if show("trades") else self._trade_markers(candles)
        self.pattern_layer.trade_ts = [int(candles[x]["ts"]) for x, _, _, _ in trades]
        try:
            self.pattern_layer.update(candles, tf, folder, chart_cfg)
        except Exception:
            pass

        # the price tags' strip, as wide as the widest tag at these prices
        if any(show(k) for k in ("ask", "bid", "avg", "dca", "trail")):
            self._tag_probe = self._make_tag_probe(frame["lo"], frame["hi"])

        if frame.get("ylim") is None:
            # a new frame: room for the trade labels and the pattern labels drawn
            reach = [
                (y, True, MARKER_REACH_PT * self.fig.dpi / 72.0)
                for _, y, _, _ in markers
            ]
            try:
                reach += self.pattern_layer.label_reach()
            except Exception:
                pass
            self._set_frame(reach)
        else:
            self.ax.set_ylim(*frame["ylim"])
            self.fit_layout()

        # Right-side price tags (so you can read Bid/Ask/AVG/DCA/Sell at a glance).
        # Two lines each, name over price, so the strip they need stays narrow.
        try:
            trans = blended_transform_factory(self.ax.transAxes, self.ax.transData)
            y0, y1 = self.ax.get_ylim()
            # a tag's height in price units, so tags at close prices can be stacked
            px_per_pt = self.fig.dpi / 72.0
            tag_px = (2 * 1.2 + 2 * TAG_BOX_PAD) * TAG_FONT_PT * px_per_pt + 2
            plot_px = max(float(self.ax.get_window_extent().height), 1.0)
            y_pad = max((y1 - y0) * tag_px / plot_px, (y1 - y0) * 0.012, 1e-9)

            wanted = []
            # Map to your terminology: Ask=buy line, Bid=sell line
            for key, tag, color in (
                ("ask", "ASK", LINES["ask"]),
                ("bid", "BID", LINES["bid"]),
                ("avg", "AVG", LINES["avg"]),
                ("dca", "DCA", LINES["dca"]),
                ("trail", "SELL", LINES["trail"]),
            ):
                price = line_prices.get(key)
                if price is None:
                    continue
                # Every line is inside the frame; were one beyond the plot it would be
                # tagged at the nearest edge, with an arrow towards it.
                yy, arrow = price, ""
                if price > y1:
                    yy, arrow = y1, " ▲"
                elif price < y0:
                    yy, arrow = y0, " ▼"
                wanted.append((yy, price, arrow, tag, color))

            # Tags that would overlap are stacked in price order, and the stack
            # stays within the plot's height: a tag hanging below the plot would
            # meet the "Time" name beside the last date.
            wanted.sort(key=lambda w: w[0])
            low, high = y0 + y_pad / 2, y1 - y_pad / 2
            ys: List[float] = []
            for w in wanted:
                ys.append(max(w[0], low, ys[-1] + y_pad if ys else low))
            for k in range(len(ys) - 1, -1, -1):
                ys[k] = min(ys[k], high if k == len(ys) - 1 else ys[k + 1] - y_pad)
            for yy, (_, price, arrow, tag, color) in zip(ys, wanted):
                self._price_tags.append(
                    self.ax.text(
                        1.01,
                        yy,
                        f"{tag}\n{_fmt_price(price)}{arrow}",
                        transform=trans,
                        ha="left",
                        va="center",
                        multialignment="center",
                        fontsize=TAG_FONT_PT,
                        color=color,
                        bbox=dict(
                            facecolor=CHART["label_bg"],
                            edgecolor=color,
                            boxstyle=f"round,pad={TAG_BOX_PAD}",
                            alpha=0.85,
                        ),
                        zorder=20,
                        clip_on=False,
                    )
                )

        except Exception:
            pass

        self.canvas.draw_idle()

        self.neural_status_label.config(
            text=(
                f"Neural: long={long_sig} short={short_sig} | levels L={len(long_levels)} S={len(short_levels)}"
                if show("neural_readout")
                else ""
            )
        )

    def _make_tag_probe(self, lo: float, hi: float):
        """An invisible price tag as wide as the widest a tag can be at these prices
        (every line is inside the frame, so no tag carries an edge arrow): the strip
        the tags need, kept even before a tag is shown."""
        widest = max(
            (
                f"{name}\n{_fmt_price(price)}"
                for name in ("ASK", "BID", "AVG", "DCA", "SELL")
                for price in (lo, hi)
            ),
            key=len,
        )
        trans = blended_transform_factory(self.ax.transAxes, self.ax.transData)
        probe = self.ax.text(
            1.01,
            self.ax.get_ylim()[0],
            widest,
            transform=trans,
            ha="left",
            va="center",
            multialignment="center",
            fontsize=TAG_FONT_PT,
            color=(0, 0, 0, 0),
            bbox=dict(
                facecolor=(0, 0, 0, 0),
                edgecolor=(0, 0, 0, 0),
                boxstyle=f"round,pad={TAG_BOX_PAD}",
            ),
            clip_on=False,
        )
        probe.set_in_layout(False)
        return probe

    def _trade_markers(self, candles: List[dict]) -> List[Tuple[int, float, str, str]]:
        """``(x, price, label, colour)`` of this coin's trades within the candles shown:
        at the candle nearest each trade's time, at its price (or that candle's close).
        """
        out: List[Tuple[int, float, str, str]] = []
        try:
            trades = (
                _read_trade_history_jsonl(self.trade_history_path)
                if self.trade_history_path
                else []
            )
        except Exception:
            return out
        if not trades:
            return out
        candle_ts = [int(c["ts"]) for c in candles]  # oldest->newest
        t_min, t_max = float(candle_ts[0]), float(candle_ts[-1])
        coin = self.coin.upper().strip()
        for tr in trades:
            sym = str(tr.get("symbol", "")).upper()
            base = sym.split("-")[0].strip() if sym else ""
            if base != coin:
                continue
            side = str(tr.get("side", "")).lower().strip()
            tag = str(tr.get("tag") or "").upper().strip()
            if side == "buy":
                label = "DCA" if tag == "DCA" else "BUY"
                color = MARKERS["dca"] if tag == "DCA" else MARKERS["buy"]
            elif side == "sell":
                label = "SELL"
                color = MARKERS["sell"]
            else:
                continue
            try:
                tts = float(tr.get("ts", None))
            except (TypeError, ValueError):
                continue
            if tts < t_min or tts > t_max:
                continue
            i = bisect.bisect_left(candle_ts, tts)
            if i <= 0:
                idx = 0
            elif i >= len(candle_ts):
                idx = len(candle_ts) - 1
            else:
                idx = (
                    i
                    if abs(candle_ts[i] - tts) < abs(tts - candle_ts[i - 1])
                    else i - 1
                )
            # y = trade price if present, else candle close
            y = _positive(tr.get("price", None))
            if y is None:
                y = _positive(candles[idx].get("close", 0.0))
            if y is None:
                continue
            out.append((idx, y, label, color))
        return out


# -----------------------------
# Account panel: profit figures
# -----------------------------

REALIZED_TIP = (
    "Realized: profit or loss on coins already sold. For each sale, what it "
    "brought in minus what those coins cost. It changes only when a coin is sold."
)
UNREALIZED_TIP = (
    "Unrealized: profit or loss on coins still held. What they would sell for "
    "now, at the bid price, minus what they cost. It moves with the price, and "
    "becomes realized when the coin is sold."
)
SINCE_START_TIP = (
    "Since start: Value now minus the paper account's starting balance "
    "(Settings > Paper Account), in dollars and as a percentage of that balance. "
    "It includes realized and unrealized profit."
)


def _fmt_profit(value: Optional[float]) -> Tuple[str, str]:
    """A profit figure's text and label style: signed dollars, green for a profit,
    red for a loss, plain when it rounds to $0.00 (or N/A when not known)."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "N/A", "TLabel"
    if not math.isfinite(value):
        return "N/A", "TLabel"
    if abs(value) < 0.005:
        return "$0.00", "TLabel"
    style = "Good.TLabel" if value > 0 else "Bad.TLabel"
    return trade_history_view.signed_money(value), style


def unrealized_profit(positions: Any) -> Optional[float]:
    """What the coins held would sell for now (each position's bid) minus what they
    cost, from the trader's positions. None when a coin held has no bid or no cost."""
    if not isinstance(positions, dict):
        return None
    total = 0.0
    for pos in positions.values():
        try:
            qty = float(pos.get("quantity") or 0.0)
            if qty <= 0.0:
                continue
            bid = float(pos.get("current_sell_price") or 0.0)
            cost = float(pos.get("avg_cost_basis") or 0.0)
        except (AttributeError, TypeError, ValueError):
            return None
        if not (bid > 0.0 and cost > 0.0):
            return None
        total += qty * (bid - cost)
    return total


def paper_starting_balance(book_path: Optional[str]) -> Optional[float]:
    """The saved paper account's starting balance; None when there is no book or
    it does not keep the rules (Settings > Paper Account shows why)."""
    if not book_path:
        return None
    try:
        book = read_paper_book(book_path)
    except PaperBookError:
        return None
    return None if book is None else float(book.initial_balance)


# -----------------------------
# Account Value chart widget
# -----------------------------


class AccountValueChart(ttk.Frame):
    """The account's value over time, with a dot for each trade. The hub's Timeframe
    box sets the period shown: the last ``bars()`` bars of that timeframe, the
    period a coin chart on the same timeframe covers."""

    def __init__(
        self,
        parent: tk.Widget,
        history_path: str,
        trade_history_path: str,
        max_points: int = 250,
        timeframe: str = "1hour",
        bars: Callable[[], int] = lambda: 120,
    ):
        super().__init__(parent)
        self.history_path = history_path
        self.trade_history_path = trade_history_path
        # Hard-cap to 250 points max (account value chart only)
        self.max_points = min(int(max_points or 0) or 250, 250)
        self.timeframe_var = tk.StringVar(self, value=timeframe)
        self._bars = bars
        self._last_key: Optional[tuple] = None
        # how far down the plot starts, for what the hub puts on its top right corner
        self.overlay_px: Callable[[], int] = lambda: 0

        # No header row (owner, 2026-11-04): no "Account value" name and no "Last:"
        # time; the plot fills the page under the coin buttons, as a coin chart does.
        self.fig = Figure(figsize=(6.5, 3.5), dpi=100)
        self.fig.patch.set_facecolor(CHART["figure"])
        # margins: _fit_axes(), after every refresh and resize

        self.ax = self.fig.add_subplot(111)
        self._apply_dark_chart_style()
        self.ax.set_title("Account Value", color=CHART["text"])

        # Add axis labels
        self.ax.set_xlabel("Time", color=CHART["text"])
        self.ax.set_ylabel("Account Value ($USD)", color=CHART["text"])

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        canvas_w = self.canvas.get_tk_widget()
        canvas_w.configure(bg=CHART["figure"])

        # Remove horizontal padding here so the chart widget truly fills the container.
        canvas_w.pack(fill="both", expand=True, padx=0, pady=0)

        # Keep the matplotlib figure EXACTLY the same pixel size as the Tk widget.
        # FigureCanvasTkAgg already sizes its backing PhotoImage to e.width/e.height.
        # Multiplying by tk scaling here makes the renderer larger than the PhotoImage,
        # which produces the "blank/covered strip" on the right.
        self._last_canvas_px = (0, 0)
        self._resize_after_id = None

        def _on_canvas_configure(e):
            try:
                w = int(e.width)
                h = int(e.height)
                if w <= 1 or h <= 1:
                    return

                if (w, h) == self._last_canvas_px:
                    return
                self._last_canvas_px = (w, h)

                dpi = float(self.fig.get_dpi() or 100.0)
                self.fig.set_size_inches(w / dpi, h / dpi, forward=True)

                # Debounce redraws during live resize
                if self._resize_after_id:
                    try:
                        self.after_cancel(self._resize_after_id)
                    except Exception:
                        pass
                self._resize_after_id = self.after_idle(self._fit_and_draw)
            except Exception:
                pass

        canvas_w.bind("<Configure>", _on_canvas_configure, add="+")

    def _fit_and_draw(self) -> None:
        self._resize_after_id = None
        self._fit()
        self.canvas.draw_idle()

    def _fit(self) -> None:
        """Fit the margins to the text drawn, the plot clear of the hub's Timeframe
        box and cog on the top right corner."""
        _fit_axes(self.fig)
        top = _top_below(self.fig, self.ax, self.overlay_px(), 1.0)
        if top < 1.0:
            _fit_axes(self.fig, 1.0, top)

    def _apply_dark_chart_style(self) -> None:
        try:
            self.fig.patch.set_facecolor(CHART["figure"])
            self.ax.set_facecolor(CHART["plot"])
            self.ax.tick_params(colors=CHART["text"])
            for spine in self.ax.spines.values():
                spine.set_color(CHART["grid"])
            self.ax.grid(True, color=CHART["grid"], linewidth=0.6, alpha=0.35)
        except Exception:
            pass

    def set_timeframe(self, tf: str) -> None:
        """Show ``tf``, chosen in the hub's Timeframe box, and redraw at once."""
        self.timeframe_var.set(tf)
        self.refresh()

    def period_seconds(self) -> Optional[float]:
        """How far back the chart reaches from its newest point: ``bars()`` bars of
        the timeframe. None (the whole history) when the timeframe is not known."""
        try:
            from candlestick_patterns import HUB_TO_CANDLE
            from market_data.timeframes import candle_timeframe_seconds

            tf = self.timeframe_var.get().strip()
            bars = max(1, int(self._bars()))
            return float(candle_timeframe_seconds(HUB_TO_CANDLE.get(tf, tf)) * bars)
        except Exception:
            return None

    def refresh(self) -> None:
        path = self.history_path

        # mtime cache so we don't redraw if nothing changed (account history OR trade history)
        try:
            m_hist = os.path.getmtime(path)
        except Exception:
            m_hist = None

        try:
            m_trades = (
                os.path.getmtime(self.trade_history_path)
                if self.trade_history_path
                else None
            )
        except Exception:
            m_trades = None

        candidates = [m for m in (m_hist, m_trades) if m is not None]
        mtime = max(candidates) if candidates else None

        # ... or the period shown (timeframe, bars) changed
        span = self.period_seconds()
        key = (mtime, span)
        if mtime is not None and self._last_key == key:
            return
        self._last_key = key

        points: List[Tuple[float, float]] = []

        try:
            if os.path.isfile(path):
                # Read the FULL history so the chart shows from the very beginning
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()

                for ln in lines:
                    try:
                        obj = json.loads(ln)
                        ts = obj.get("ts", None)
                        v = obj.get("total_account_value", None)
                        if ts is None or v is None:
                            continue

                        tsf = float(ts)
                        vf = float(v)

                        # Drop obviously invalid points early
                        if (
                            (not math.isfinite(tsf))
                            or (not math.isfinite(vf))
                            or (vf <= 0.0)
                        ):
                            continue

                        points.append((tsf, vf))
                    except Exception:
                        continue
        except Exception:
            points = []

        # ---- Clean up history so single-tick bogus dips/spikes don't render ----
        if points:
            # Ensure chronological order
            points.sort(key=lambda x: x[0])

            # De-dupe identical timestamps (keep the latest occurrence)
            dedup: List[Tuple[float, float]] = []
            for tsf, vf in points:
                if dedup and tsf == dedup[-1][0]:
                    dedup[-1] = (tsf, vf)
                else:
                    dedup.append((tsf, vf))
            points = dedup

            # the period the timeframe covers, back from the newest point
            if span:
                start = points[-1][0] - span
                points = [pt for pt in points if pt[0] >= start]

        # Downsample to <= 250 points by AVERAGING buckets instead of skipping points.
        # IMPORTANT: never average the VERY FIRST or VERY LAST point.
        # - First point should remain the true first historical value.
        # - Last point should remain the true current/final account value (so the title and chart end match account info).
        max_keep = min(max(2, int(self.max_points or 250)), 250)
        n = len(points)

        if n > max_keep:
            first_pt = points[0]
            last_pt = points[-1]

            mid_points = points[1:-1]
            mid_n = len(mid_points)
            keep_mid = max_keep - 2

            if keep_mid <= 0 or mid_n <= 0:
                points = [first_pt, last_pt]
            elif mid_n <= keep_mid:
                points = [first_pt] + mid_points + [last_pt]
            else:
                bucket_size = mid_n / float(keep_mid)
                new_mid: List[Tuple[float, float]] = []

                for i in range(keep_mid):
                    start = int(i * bucket_size)
                    end = int((i + 1) * bucket_size)
                    if end <= start:
                        end = start + 1
                    if start >= mid_n:
                        break
                    if end > mid_n:
                        end = mid_n

                    bucket = mid_points[start:end]
                    if not bucket:
                        continue

                    # Average timestamp and account value within the bucket (MID ONLY)
                    avg_ts = sum(p[0] for p in bucket) / len(bucket)
                    avg_val = sum(p[1] for p in bucket) / len(bucket)
                    new_mid.append((avg_ts, avg_val))

                points = [first_pt] + new_mid + [last_pt]

        # clear artists (fast) / fallback to cla()
        try:
            self.ax.lines.clear()
            self.ax.patches.clear()
            self.ax.collections.clear()  # scatter dots live here
            self.ax.texts.clear()  # labels/annotations live here
        except Exception:
            self.ax.cla()
            self._apply_dark_chart_style()
            # Restore axis labels after clearing
            self.ax.set_xlabel("Time", color=CHART["text"])
            self.ax.set_ylabel("Account Value ($USD)", color=CHART["text"])

        if not points:
            self.ax.set_title("Account Value - no data", color=CHART["text"])
            self._fit()
            self.canvas.draw_idle()
            return

        xs = list(range(len(points)))
        # Only show cent-level changes (hide sub-cent noise)
        ys = [round(p[1], 2) for p in points]

        self.ax.plot(xs, ys, linewidth=1.5)

        # --- Trade dots (BUY / DCA / SELL) for ALL coins ---
        try:
            trades = (
                _read_trade_history_jsonl(self.trade_history_path)
                if self.trade_history_path
                else []
            )
            if trades:
                ts_list = [float(p[0]) for p in points]  # matches xs/ys indices
                t_min = ts_list[0]
                t_max = ts_list[-1]

                for tr in trades:
                    # Determine label/color
                    side = str(tr.get("side", "")).lower().strip()
                    tag = str(tr.get("tag", "")).upper().strip()

                    if side == "buy":
                        action_label = "DCA" if tag == "DCA" else "BUY"
                        color = MARKERS["dca"] if tag == "DCA" else MARKERS["buy"]
                    elif side == "sell":
                        action_label = "SELL"
                        color = MARKERS["sell"]
                    else:
                        continue

                    # Prefix with coin (so the dot says which coin it is)
                    sym = str(tr.get("symbol", "")).upper().strip()
                    coin_tag = (
                        sym.split("-")[0].split("/")[0].strip() if sym else ""
                    ) or (sym or "?")
                    label = f"{coin_tag} {action_label}"

                    tts = tr.get("ts")
                    try:
                        tts = float(tts)
                    except Exception:
                        continue
                    if tts < t_min or tts > t_max:
                        continue

                    # nearest account-value point
                    i = bisect.bisect_left(ts_list, tts)
                    if i <= 0:
                        idx = 0
                    elif i >= len(ts_list):
                        idx = len(ts_list) - 1
                    else:
                        idx = (
                            i
                            if abs(ts_list[i] - tts) < abs(tts - ts_list[i - 1])
                            else (i - 1)
                        )

                    x = idx
                    y = ys[idx]

                    self.ax.scatter([x], [y], s=30, color=color, zorder=6)
                    self.ax.annotate(
                        label,
                        (x, y),
                        textcoords="offset points",
                        xytext=(0, 10),
                        ha="center",
                        fontsize=CHART_FONT_PT,
                        color=CHART["text"],
                        zorder=7,
                    )

        except Exception:
            pass

        # Force 2 decimals on the y-axis labels (account value chart only)
        try:
            self.ax.yaxis.set_major_formatter(
                FuncFormatter(lambda y, _pos: f"${y:,.2f}")
            )
        except Exception:
            pass

        # x labels: show a few timestamps (date + time) - evenly spaced, never overlapping duplicates
        n = len(points)
        want = 5
        if n <= want:
            idxs = list(range(n))
        else:
            step = (n - 1) / float(want - 1)
            idxs = []
            last = -1
            for j in range(want):
                i = int(round(j * step))
                if i <= last:
                    i = last + 1
                if i >= n:
                    i = n - 1
                idxs.append(i)
                last = i

        tick_x = [xs[i] for i in idxs]
        tick_lbl = [
            time.strftime("%Y-%m-%d\n%H:%M:%S", time.localtime(points[i][0]))
            for i in idxs
        ]
        try:
            self.ax.minorticks_off()
            self.ax.set_xticks(tick_x)
            self.ax.set_xticklabels(tick_lbl)
            self.ax.tick_params(axis="x", labelsize=CHART_FONT_PT)
            _end_date_inside(self.ax)
        except Exception:
            pass

        self.ax.set_xlim(-0.5, (len(points) - 0.5) + 0.6)

        try:
            self.ax.set_title(
                f"Account Value ({_fmt_money(ys[-1])})", color=CHART["text"]
            )
        except Exception:
            self.ax.set_title("Account Value", color=CHART["text"])

        self._fit()
        self.canvas.draw_idle()


# -----------------------------
# Hub App
# -----------------------------


@dataclass
class ProcInfo:
    name: str
    path: str
    proc: Optional[subprocess.Popen] = None


def _child_env(hub_dir: str) -> Dict[str, str]:
    """The environment for a process the hub starts (runner, trader, trainer):
    the hub's own, plus where the hub reads their status, and no bytecode cache in
    the read-only program folder (#148)."""
    env = os.environ.copy()
    env["POWERTRADER_HUB_DIR"] = hub_dir
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


@dataclass
class LogProc:
    """
    A running process with a live log queue for stdout/stderr lines.
    """

    info: ProcInfo
    log_q: "queue.Queue[str]"
    thread: Optional[threading.Thread] = None
    is_trainer: bool = False
    coin: Optional[str] = None


def _left_split_target(requested: int, total: int) -> int:
    """Sash position for the Controls / Live Output split: what Controls asks
    for, at least 160 px, at most half the height (450 px when that is more)
    and never leaving Live Output less than 120 px."""
    upper = min(max(450, total // 2), total - 120)
    return int(max(160, min(requested + 2, upper)))


class PowerTraderHub(tk.Tk):
    def __init__(self):
        super().__init__()
        # set when the hub is destroyed: its background exchange check then ends
        self._stop_background = threading.Event()
        self.title("PowerTraderAI+ (https://github.com/sjackson0109/PowerTraderAI)")
        self.geometry("1400x820")

        # Hard minimum window size so the UI can't be shrunk to a point where panes vanish.
        # (Keeps things usable even if someone aggressively resizes.)
        self.minsize(1400, 820)

        # Debounce map for panedwindow clamp operations
        self._paned_clamp_after_ids: Dict[str, str] = {}

        # User config/data live outside the (read-only) program folder. Before
        # anything reads settings: move files left by older releases (copies
        # only; nothing is deleted or overwritten), then, on first run, copy
        # the shipped exchange template into the config folder.
        self._migration_report = (
            pt_migrate.run_startup_migration() if pt_migrate is not None else None
        )
        try:
            pt_paths.install_default("trading_config.example.json")
        except OSError as exc:
            print(f"Warning: could not install the default exchange config: {exc}")

        # Trading mode must be known BEFORE the first theme paint, otherwise
        # the window flashes dark for one frame before settling on blue. It is
        # `trading.mode` from pt_config.json (paper unless explicitly live).
        self._trading: TradingSettings = read_trading_settings()
        # the account's Buying Power as last shown (the order dialog checks buys
        # against it); None until the trader or the paper book gives one
        self._last_buying_power: Optional[float] = None
        self._paper_mode = not self._trading.is_live

        # Force one and only one theme: dark (or paper-blue when enabled).
        self._apply_forced_dark_mode()

        self.settings = self._load_settings()

        # Header strip + banner widgets; built after the layout exists.
        self._mode_indicator: Optional[TradingModeIndicator] = None
        self._paper_banner: Optional[PaperBanner] = None
        self._halt_banner = None  # TRADING HALTED (risk_settings_ui.HaltBanner)
        self._paper_section_label: Optional[tk.Label] = None
        self._paper_account = None  # lazy: only spun up when sample runs

        # Program folder (read-only): runner scripts are executed from here.
        self.project_dir = pt_paths.program_dir()

        # Neural folders (models + signals) and hub data live in the user data
        # folder; a setting pointing inside the program folder is ignored.
        self.settings["main_neural_dir"] = pt_paths.neural_dir(
            self.settings.get("main_neural_dir")
        )
        self.hub_dir = pt_paths.hub_dir_for(self.settings.get("hub_data_dir"))

        # file paths written by pt_trader.py. The trader keeps each trading mode's
        # books in its own sub-directory (paper / testnet / live/<broker>), so show
        # the ones for the mode this hub started in.
        if self._trading.is_live and not self._trading.uses_testnet:
            try:  # books from before each live broker had its own folder move once
                move_root_live_books(self.hub_dir, self._trading.active_broker)
            except (OSError, ValueError) as exc:
                print(f"Live books not moved: {exc}")
        trader_dir = os.path.join(self.hub_dir, self._trading.data_subdir)
        self._books_dir = trader_dir  # the public API serves the same books
        self.trader_status_path = os.path.join(trader_dir, "trader_status.json")
        self.trade_history_path = os.path.join(trader_dir, "trade_history.jsonl")
        self.pnl_ledger_path = os.path.join(trader_dir, "pnl_ledger.json")
        self.account_value_history_path = os.path.join(
            trader_dir, "account_value_history.jsonl"
        )

        # file written by pt_thinker.py (runner readiness gate used for Start All)
        self.runner_ready_path = os.path.join(self.hub_dir, "runner_ready.json")

        # internal: when Start All is pressed, we start the runner first and only start the trader once ready
        self._auto_start_trader_pending = False

        # cache latest trader status so charts can overlay buy/sell lines
        self._last_positions: Dict[str, dict] = {}

        # account value chart widget (created in _build_layout)
        self.account_chart = None

        # coin folders (neural outputs)
        self.coins = [c.upper().strip() for c in self.settings["coins"]]

        # On startup (like on Settings-save), create any missing alt coin neural
        # folders. Nothing is copied into them: the trainer runs from the
        # program folder with the coin folder as its working directory.
        self._ensure_alt_coin_folders_and_trainer_on_startup()

        # Rebuild folder map after potential folder creation
        self.coin_folders = build_coin_folders(
            self.settings["main_neural_dir"], self.coins
        )

        # Initialize last_training_times dictionary for training status tracking
        self.last_training_times = {}  # coin -> timestamp of last completed training

        # Initialize last_training_times from existing timestamp files (after coin_folders is built)
        self._load_existing_training_times()

        # scripts
        self.proc_neural = ProcInfo(
            name="Neural Runner",
            path=os.path.abspath(
                os.path.join(self.project_dir, SYSTEM_SCRIPTS["script_neural_runner2"])
            ),
        )
        self.proc_trader = ProcInfo(
            name="Trader",
            path=os.path.abspath(
                os.path.join(self.project_dir, SYSTEM_SCRIPTS["script_trader"])
            ),
        )

        self._refresh_trainer_path()

        # live log queues
        self.runner_log_q: "queue.Queue[str]" = queue.Queue()
        self.trader_log_q: "queue.Queue[str]" = queue.Queue()

        # trainers: coin -> LogProc
        self.trainers: Dict[str, LogProc] = {}

        self.fetcher = CandleFetcher()

        # Initialize multi-exchange system
        self._multi_exchange = None
        self._exchange_status = {"status": "Checking...", "details": ""}
        if EXCHANGE_SUPPORT_AVAILABLE:
            self._init_exchange_system()

        # Initialize Public API Server
        self._api_server = None
        self._api_server_enabled = bool(self.settings.get("api_server_enabled", False))
        self._api_server_port = int(self.settings.get("api_server_port", 8080))
        self._api_server_host = self.settings.get("api_server_host", "127.0.0.1")

        if self._api_server_enabled:
            self._init_api_server()

        # Run startup dependency check
        self._run_startup_dependency_check()

        self._build_menu()
        self._build_layout()

        # Paper-mode banner + trading-section label are packed AFTER the layout
        # exists. _build_layout assigns self.trades_frame for us.
        if self._paper_mode:
            self._build_paper_banner()
            self._attach_paper_section_label()

        # Always-visible MODE strip: in the banner in paper mode, else at the top
        self._mode_indicator = TradingModeIndicator(self, self._trading)
        self._place_mode_strip()

        # Refresh charts immediately when a timeframe is changed (don't wait for the 10s throttle).
        self.bind_all("<<TimeframeChanged>>", self._on_timeframe_changed)
        # the toolbar button on each coin chart (FDS-CHART-001 section 8.1)
        self.bind_all("<<OpenChartSettings>>", lambda e: self.open_chart_settings())

        self._last_chart_refresh = 0.0

        # Settings > System: the runner and trader start once the window is up
        self.after(AUTO_START_DELAY_MS, self._auto_start_on_launch)

        # NOTE: API server auto-start is handled inside _init_api_server() above.
        # No second toggle here — that would risk a double-bind on the same port.

        # the retrain timers live in memory: set them again from the saved times
        self._resume_auto_retrains()

        self.after(250, self._tick)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if self._migration_report is not None:
            self.after(800, self._show_migration_report)

    def _show_migration_report(self) -> None:
        """Summary of the FDS-108a migration with a 'Remove old files' button
        (which asks for confirmation before deleting anything)."""
        try:
            pt_migrate.show_migration_dialog(self, self._migration_report)
        except Exception as exc:
            print(f"Warning: could not show the migration report: {exc}")

    @staticmethod
    def _user_folder_rows(settings: Optional[dict] = None) -> List[Tuple[str, str]]:
        """(label, folder) for Settings > Working Directories: the folders in use.
        A Models or Hub data folder chosen in an older release is still used."""
        settings = settings or {}
        return [
            ("Config folder:", pt_paths.config_dir()),
            ("Data folder:", pt_paths.data_dir()),
            ("Models folder:", pt_paths.trainer_root(settings.get("main_neural_dir"))),
            (
                "Hub data folder:",
                pt_paths.user_dir_setting(
                    settings.get("hub_data_dir"),
                    pt_paths.hub_dir(create=False),
                    "hub_data_dir",
                    create=False,
                ),
            ),
            ("Cache folder:", pt_paths.cache_dir()),
            ("Log folder:", pt_paths.log_dir()),
        ]

    def _open_user_folder(self, folder: str) -> None:
        """Open ``folder`` in the system file manager."""
        try:
            pt_paths.make_private_dir(folder)
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror(
                "Couldn't open folder", f"Tried to open:\n{folder}\n\nError:\n{e}"
            )

    # ---- forced dark mode ----

    def _apply_forced_dark_mode(self) -> None:
        """Apply the hub's one ttk theme from the active palette: dark, or blue in
        paper mode. ui_theme builds every style from ui_tokens."""
        palette = ui_tokens.palette(bool(getattr(self, "_paper_mode", False)))
        try:
            ui_theme.apply_theme(self, ttk.Style(self), palette)
        except tk.TclError:
            pass

    # ---- paper mode ----

    def _build_paper_banner(self) -> None:
        """Pack the PAPER TRADING banner across the top of the window."""
        if self._paper_banner is not None:
            return
        palette = ui_tokens.palette(True)
        self._paper_banner = PaperBanner(
            self,
            palette=palette,
            on_run_sample=self._run_paper_sample,
        )
        pack_at_top(self._paper_banner, self)

    def _place_mode_strip(self) -> None:
        """The MODE strip. In paper mode it sits in the banner, right of PAPER
        TRADING, so the header is one row (owner, 2026-10-23); otherwise it is a
        strip of its own above everything else."""
        strip = getattr(self, "_mode_indicator", None)
        if strip is None:
            return
        strip.pack_forget()
        banner = self._paper_banner
        if banner is not None:
            strip.pack(in_=banner, side="left", fill="x", expand=True)
            strip.lift(banner)  # the banner may be newer: keep the strip above it
        else:
            pack_at_top(strip, self)
        if getattr(self, "_halt_banner", None) is not None:
            pack_at_top(self._halt_banner, self)  # a halt stays above everything

    def _attach_paper_section_label(self) -> None:
        """Drop a 'PAPER TRADING' label at the top of the trades panel."""
        frame = getattr(self, "trades_frame", None)
        if frame is None or self._paper_section_label is not None:
            return
        label = attach_trading_section_label(frame, ui_tokens.palette(True))
        pack_at_top(label, frame)
        self._paper_section_label = label

    def _remove_paper_widgets(self) -> None:
        if self._paper_banner is not None:
            try:
                self._paper_banner.destroy()
            except tk.TclError:
                pass
            self._paper_banner = None
        if self._paper_section_label is not None:
            try:
                self._paper_section_label.destroy()
            except tk.TclError:
                pass
            self._paper_section_label = None

    def _brokers_for_selector(self) -> List[str]:
        """Broker ids offered in the Trading Mode dialog: the exchanges this version
        can place live orders on (their connector's ``SUPPORTS_LIVE_ORDERS``)."""
        try:
            import pt_exchanges  # noqa: F401  (registers exchange classes)
            from pt_exchange_abstraction import ExchangeFactory

            return [
                e.value
                for e in ExchangeFactory.get_available_exchanges()
                if broker_places_orders(e.value)
            ]
        except Exception:
            return []

    def _open_trading_mode_dialog(self) -> None:
        """File > Trading Mode...: choose paper/live and the broker."""
        TradingModeDialog(
            self,
            current=read_trading_settings(),
            brokers=self._brokers_for_selector(),
            on_applied=self._on_trading_mode_applied,
        )

    def _on_trading_mode_applied(self, new_settings: TradingSettings) -> None:
        """The mode was persisted. Update the header immediately; the trader and
        the matching palette/books pick it up on restart (the running trader
        refuses orders until then, so nothing can trade in the wrong mode)."""
        self._trading = new_settings
        self._paper_mode = not new_settings.is_live
        if self._mode_indicator is not None:
            self._mode_indicator.update_settings(new_settings)

        # Immediate visible feedback - banner/label toggle without restart.
        if self._paper_mode:
            self._build_paper_banner()
            self._attach_paper_section_label()
        else:
            self._remove_paper_widgets()
            self._paper_account = None
        self._place_mode_strip()

        trader_running = bool(
            self.proc_trader.proc and self.proc_trader.proc.poll() is None
        )
        messagebox.showinfo(
            "Trading mode",
            f"{new_settings.label}\n\n"
            + (
                "The running trader keeps the mode it started in and will "
                "refuse orders until it is restarted.\n\n"
                if trader_running
                else ""
            )
            + "Restart PowerTrader to fully repaint charts and text panels in "
            "the matching palette and to show this mode's trade history.",
        )

    def _run_paper_sample(self) -> None:
        """Banner button handler. Runs the live-BTC buy/sell scenario."""
        if not self._paper_mode:
            return
        if self._paper_account is None:
            try:
                from pt_paper_trading import (  # local import: heavy module
                    PaperTradingAccount as _PaperAcct,
                )

                balance = Decimal(
                    str(self.settings.get(PAPER_MODE_BALANCE_KEY, 10000.0))
                )
                self._paper_account = _PaperAcct(initial_balance=balance)
            except Exception as exc:
                messagebox.showerror("Paper sample", f"Account init failed: {exc}")
                return
        try:
            result = run_sample_scenario(self._paper_account)
        except Exception as exc:
            messagebox.showerror("Paper sample", f"Sample run failed: {exc}")
            return
        if self._paper_banner is not None:
            delta = result["final_balance"] - result["starting_balance"]
            self._paper_banner.set_result(
                f"buy ${result['buy_price']:,.2f} -> sell ${result['sell_price']:,.2f} "
                f"({'+' if delta >= 0 else ''}${delta:,.4f})"
            )

    # ---- settings ----

    def _load_settings(self) -> dict:
        settings_path = pt_paths.gui_settings_file()
        data = _safe_read_json(settings_path)
        if not isinstance(data, dict):
            data = {}
        # A credential in the settings file is ignored and never written back.
        data = (
            pt_secrets.strip_secret_fields(data, SETTINGS_FILE) if pt_secrets else data
        )

        # A file saved before the new sizing defaults: its 0.005% entry is upstream's
        # default, replaced once (position_sizing.migrate_settings)
        if data and position_sizing.migrate_settings(data):
            try:
                pt_paths.write_private_text(settings_path, json.dumps(data, indent=2))
            except OSError:
                pass

        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        for key in SYSTEM_SCRIPTS:  # part of the program now; saved without them
            merged.pop(key, None)
        # normalize
        merged["coins"] = [c.upper().strip() for c in merged.get("coins", [])]
        return merged

    def _save_settings(self) -> None:
        data = self.settings
        if pt_secrets:
            data = pt_secrets.strip_secret_fields(data, SETTINGS_FILE)
        pt_paths.write_private_text(
            pt_paths.gui_settings_file(), json.dumps(data, indent=2)
        )

    def _apply_theme(self) -> None:
        """
        Apply the selected theme settings to the application.
        Currently implements a single dark theme, but could be extended
        for multiple theme support in the future.
        """
        # For now, the application uses a fixed dark theme regardless of settings
        # This function exists as a placeholder for future theme customization
        # when multiple themes might be implemented
        dark_theme_enabled = self.settings.get("dark_theme", True)

        # In the future, this could change color schemes, fonts, etc.
        # Currently, no action needed as the app uses a consistent dark theme
        pass

    def _settings_getter(self) -> dict:
        return self.settings

    def _ensure_alt_coin_folders_and_trainer_on_startup(self) -> None:
        """
        Startup behavior (mirrors Settings-save behavior): create the per-coin
        neural folder for every alt coin that does not have one yet. The trainer
        is run from the program folder with the coin folder as its working
        directory, so no code is copied into the data folders. (The name is
        historical: older versions also copied the trainer into each folder.)
        """
        try:
            main_dir = pt_paths.neural_dir(self.settings.get("main_neural_dir"))
            for coin in self.settings.get("coins") or []:
                coin = str(coin).strip().upper()
                if coin and coin != "BTC":  # BTC uses the main folder itself
                    os.makedirs(os.path.join(main_dir, coin), exist_ok=True)
        except Exception:
            pass

    def _refresh_trainer_path(self) -> str:
        """Set ``proc_trainer_path``: the system trainer script, resolved against the
        (read-only) program folder."""
        self.proc_trainer_path = os.path.abspath(
            os.path.join(self.project_dir, SYSTEM_SCRIPTS["script_neural_trainer"])
        )
        return self.proc_trainer_path

    # ---- menu / layout ----

    def _build_menu(self) -> None:
        p = ui_theme.active_palette()
        menubar = tk.Menu(
            self,
            bg=p["BG2"],
            fg=p["FG"],
            activebackground=p["SELECT_BG"],
            activeforeground=p["SELECT_FG"],
            bd=0,
            relief="flat",
        )

        m_file = tk.Menu(
            menubar,
            tearoff=0,
            bg=p["BG2"],
            fg=p["FG"],
            activebackground=p["SELECT_BG"],
            activeforeground=p["SELECT_FG"],
        )
        # Trading mode (owner spec: File menu so users don't need the CLI).
        # Paper is the default; Live needs a broker and an explicit confirmation.
        m_file.add_command(
            label="Trading Mode...", command=self._open_trading_mode_dialog
        )
        m_file.add_separator()
        m_file.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=m_file)

        m_settings = tk.Menu(
            menubar,
            tearoff=0,
            bg=p["BG2"],
            fg=p["FG"],
            activebackground=p["SELECT_BG"],
            activeforeground=p["SELECT_FG"],
        )
        m_settings.add_command(label="Settings...", command=self.open_settings_dialog)
        m_settings.add_command(
            label="Paper Account...", command=self.open_paper_account_dialog
        )
        menubar.add_cascade(label="Settings", menu=m_settings)

        # Help menu
        m_help = tk.Menu(
            menubar,
            tearoff=0,
            bg=p["BG2"],
            fg=p["FG"],
            activebackground=p["SELECT_BG"],
            activeforeground=p["SELECT_FG"],
        )
        m_help.add_command(
            label="Dependency Status", command=self.show_dependency_status
        )
        m_help.add_separator()
        m_help.add_command(label="About PowerTrader", command=self.show_about)
        menubar.add_cascade(label="Help", menu=m_help)

        self.config(menu=menubar)

    def _build_layout(self) -> None:
        p = ui_theme.active_palette()
        outer = ttk.Panedwindow(self, orient="horizontal")
        outer.pack(fill="both", expand=True)

        # LEFT + RIGHT panes
        left = ttk.Frame(outer)
        right = ttk.Frame(outer)

        outer.add(left, weight=0)  # Fixed width - doesn't expand
        outer.add(right, weight=1)  # Takes all expansion

        # Prevent the outer (left/right) panes from being collapsible to 0 width
        try:
            outer.paneconfigure(left, minsize=360)
            outer.paneconfigure(right, minsize=520)
        except Exception:
            pass

        # LEFT: vertical split (Controls on top, Live Output underneath)
        left_split = ttk.Panedwindow(left, orient="vertical")
        left_split.pack(fill="both", expand=True, padx=8, pady=8)

        # RIGHT: vertical split (Charts on top, Trades+History underneath)
        right_split = ttk.Panedwindow(right, orient="vertical")
        right_split.pack(fill="both", expand=True, padx=8, pady=8)

        # Keep references so we can clamp sash positions later
        self._pw_outer = outer
        self._pw_left_split = left_split
        self._pw_right_split = right_split

        # Clamp panes when the user releases a sash or the window resizes
        outer.bind("<Configure>", lambda e: self._schedule_paned_clamp(self._pw_outer))
        outer.bind(
            "<ButtonRelease-1>",
            lambda e: (
                setattr(self, "_user_moved_outer", True),
                self._schedule_paned_clamp(self._pw_outer),
            ),
        )

        left_split.bind(
            "<Configure>", lambda e: self._schedule_paned_clamp(self._pw_left_split)
        )
        left_split.bind(
            "<ButtonRelease-1>",
            lambda e: (
                setattr(self, "_user_moved_left_split", True),
                self._schedule_paned_clamp(self._pw_left_split),
            ),
        )

        right_split.bind(
            "<Configure>", lambda e: self._schedule_paned_clamp(self._pw_right_split)
        )
        right_split.bind(
            "<ButtonRelease-1>",
            lambda e: (
                setattr(self, "_user_moved_right_split", True),
                self._schedule_paned_clamp(self._pw_right_split),
            ),
        )

        # Set a startup default width that matches the screenshot (so left has room for Neural Levels).
        def _init_outer_sash_once():
            try:
                if getattr(self, "_did_init_outer_sash", False):
                    return

                # If the user already moved it, never override it.
                if getattr(self, "_user_moved_outer", False):
                    self._did_init_outer_sash = True
                    return

                total = outer.winfo_width()
                if total <= 2:
                    self.after(10, _init_outer_sash_once)
                    return

                min_left = 360
                min_right = 520
                # 394: the coin table's three columns with no spare strip right of
                # them (owner: 438 on 2026-10-14, 402 on 2026-11-02, 394 on
                # 2026-11-03)
                desired_left = 394
                target = max(min_left, min(total - min_right, desired_left))
                outer.sashpos(0, int(target))

                self._did_init_outer_sash = True
            except Exception:
                pass

        self.after_idle(_init_outer_sash_once)

        # Global safety: on some themes/platforms, the mouse events land on the sash element,
        # not the panedwindow widget, so the widget-level binds won't always fire.
        self.bind_all(
            "<ButtonRelease-1>",
            lambda e: (
                self._schedule_paned_clamp(getattr(self, "_pw_outer", None)),
                self._schedule_paned_clamp(getattr(self, "_pw_left_split", None)),
                self._schedule_paned_clamp(getattr(self, "_pw_right_split", None)),
            ),
        )

        # ----------------------------
        # LEFT: 1) Controls / Health (pane)
        # ----------------------------
        top_controls = ttk.LabelFrame(left_split, text="Controls / Health")

        # Create a main container for organized sections
        main_container = ttk.Frame(top_controls)
        main_container.pack(fill="both", expand=True, padx=6, pady=6)

        # One column: Account, then Coins (training and thinking per coin); both
        # take their natural height and the rest goes to Live Output.
        main_container.grid_rowconfigure(0, weight=0, minsize=0)  # Account
        main_container.grid_rowconfigure(1, weight=0, minsize=0)  # Coins
        main_container.grid_columnconfigure(0, weight=1)

        # Button width and height constants
        BTN_W = 10  # Standard button width
        BTN_H = 1  # Standard button height
        MINI_BTN_W = 1  # Ultra-small width for icon buttons
        MINI_BTN_H = 1  # Much smaller height for icon buttons

        # Account: a status row (trader, exchange, start/stop), then the figures
        # as a two-column key/value grid.
        acct_box = ttk.LabelFrame(main_container, text="Account")
        acct_box.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        acct_box.grid_columnconfigure(1, weight=1)
        acct_box.grid_columnconfigure(3, weight=1)

        trader_row = ttk.Frame(acct_box)
        trader_row.grid(row=0, column=0, columnspan=4, sticky="ew", padx=4, pady=(1, 2))
        # Exchange on the left; Trader on the right, next to its start/stop buttons.
        # Packed buttons first, then Trader, then Exchange: a narrow pane clips the
        # exchange text, never the trader or its buttons.
        self.btn_stop_trader = ttk.Button(
            trader_row,
            text="■",
            width=MINI_BTN_W,
            command=self.stop_trader,
        )
        self.btn_stop_trader.pack(side="right", padx=(0, 2), pady=0, ipady=0)
        ToolTip(self.btn_stop_trader, "Stop trader")

        self.btn_start_trader = ttk.Button(
            trader_row,
            text="►",
            width=MINI_BTN_W,
            command=self.start_trader,
        )
        self.btn_start_trader.pack(side="right", padx=(0, 0), pady=0, ipady=0)
        ToolTip(self.btn_start_trader, "Start trader")
        self.lbl_trader = ttk.Label(
            trader_row,
            text="stopped",
            font=ui_tokens.font("caption"),
            foreground=p["ACCENT2"],
        )
        self.lbl_trader.pack(side="right", padx=(2, 6))
        ttk.Label(
            trader_row,
            text="Trading:",
            font=ui_tokens.font("caption"),
            foreground=p["MUTED"],
        ).pack(side="right")

        # Exchange status (click for details)
        self.lbl_exchange_key = ttk.Label(
            trader_row,
            text="Exchange:",
            font=ui_tokens.font("caption"),
            foreground=p["MUTED"],
        )
        self.lbl_exchange_key.pack(side="left")
        self.lbl_exchange = ttk.Label(
            trader_row,
            text="Checking...",
            font=ui_tokens.font("caption"),
            foreground=p["MUTED"],
            cursor="hand2",
        )
        self.lbl_exchange.pack(side="left", padx=(2, 0))

        def _figure(
            row: int, col: int, key: str, attr: str, tip: str = "", span: int = 1
        ) -> ttk.Label:
            name = ttk.Label(
                acct_box,
                text=key,
                font=ui_tokens.font("caption"),
                foreground=p["MUTED"],
            )
            name.grid(row=row, column=col, sticky="w", padx=(4, 6))
            value = ttk.Label(acct_box, text="N/A", font=ui_tokens.font("caption"))
            value.grid(
                row=row, column=col + 1, columnspan=span, sticky="w", padx=(0, 8)
            )
            setattr(self, attr, value)
            if tip:
                ToolTip(name, tip)
                ToolTip(value, tip)
            return name

        _figure(1, 0, "Value", "lbl_acct_total_value")
        _figure(1, 2, "Buying Power", "lbl_acct_buying_power")
        _figure(2, 0, "Holdings", "lbl_acct_holdings_value")
        _figure(2, 2, "% in Trade", "lbl_acct_percent_in_trade")
        _figure(3, 0, "DCA Single", "lbl_acct_dca_single")
        _figure(3, 2, "DCA Spread", "lbl_acct_dca_spread")
        _figure(4, 0, "Realized", "lbl_pnl", REALIZED_TIP)
        _figure(4, 2, "Unrealized", "lbl_acct_unrealized", UNREALIZED_TIP)
        # paper only: shown by _show_profit_figures when the paper book is in use
        self.lbl_acct_since_start_key = _figure(
            5, 0, "Since start", "lbl_acct_since_start", SINCE_START_TIP, span=3
        )
        ttk.Frame(acct_box, height=2).grid(row=6, column=0, columnspan=4)

        # Coins: one cell per coin (training status, trained-for, long/short
        # signal counts), with the Training and Thinking controls in its header.
        training_section = ttk.LabelFrame(main_container, text="Coins")
        training_section.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        training_title_row = ttk.Frame(training_section)
        training_title_row.pack(fill="x", padx=6, pady=(1, 0))

        # Training: counter and Train all / Stop all
        ttk.Label(
            training_title_row,
            text="Training:",
            font=ui_tokens.font("caption"),
            foreground=p["MUTED"],
        ).pack(side="left")
        total_coins = len(self.coins) if self.coins else 0
        self.training_status_label = ttk.Label(
            training_title_row,
            text=f"0/{total_coins} running",
            font=ui_tokens.font("caption"),
            foreground=p["ACCENT2"],
        )
        self.training_status_label.pack(side="left", padx=(2, 4))
        # Note: TTK buttons don't support 'height' parameter, so we only use 'width'
        train_all_btn = ttk.Button(
            training_title_row,
            text="►",
            width=MINI_BTN_W,
            command=self.train_all_coins,
        )
        train_all_btn.pack(side="left", pady=0, ipady=0)
        ToolTip(train_all_btn, "Train all coins")
        stop_all_btn = ttk.Button(
            training_title_row,
            text="■",
            width=MINI_BTN_W,
            command=self.stop_all_trainers,
        )
        stop_all_btn.pack(side="left", padx=(2, 0), pady=0, ipady=0)
        ToolTip(stop_all_btn, "Stop all trainers")

        # Thinking (the neural runner): status and Start / Stop
        self.btn_stop_neural = ttk.Button(
            training_title_row,
            text="■",
            width=MINI_BTN_W,
            command=self.stop_neural,
        )
        self.btn_stop_neural.pack(side="right", padx=(2, 0), pady=0, ipady=0)
        ToolTip(self.btn_stop_neural, "Stop neural runner")
        self.btn_start_neural = ttk.Button(
            training_title_row,
            text="►",
            width=MINI_BTN_W,
            command=self.start_neural,
        )
        self.btn_start_neural.pack(side="right", pady=0, ipady=0)
        ToolTip(self.btn_start_neural, "Start neural runner")
        self.lbl_neural = ttk.Label(
            training_title_row,
            text="stopped",
            font=ui_tokens.font("caption"),
            foreground=p["ACCENT2"],
        )
        self.lbl_neural.pack(side="right", padx=(2, 4))
        ttk.Label(
            training_title_row,
            text="Thinking:",
            font=ui_tokens.font("caption"),
            foreground=p["MUTED"],
        ).pack(side="right")

        # Keep train_coin_var for click handlers but remove dropdown UI
        self.train_coin_var = tk.StringVar(value=(self.coins[0] if self.coins else ""))

        # One cell per coin, built once per coin list and updated in place
        self.training_status_frame = ttk.Frame(training_section)
        self.training_status_frame.pack(fill="x", padx=4, pady=(1, 2))
        self._training_cells: Dict[str, Tuple[Any, ...]] = {}
        # signal counts' mtime cache: path -> (mtime, value)
        self._neural_overview_cache: Dict[str, Tuple[float, Any]] = {}
        self._build_training_table()
        self.training_status_frame.bind(
            "<Configure>", lambda e: self._layout_training_table(), add="+"
        )

        # Training automation: auto-retrain timers
        self.auto_retrain_timers = {}  # coin -> timer for auto retraining
        self.auto_retrain_due = {}  # coin -> when its timer fires (epoch seconds)

        # (Duplicate Account section removed - using the one in top_sections_row)

        # (Duplicate Neural Levels overview removed - using compact version in Neural section only)

        # ----------------------------
        # LEFT: 3) Live Output (pane)
        # ----------------------------

        # Half-size fixed-width font for live logs (Runner/Trader/Trainers)
        _base = tkfont.nametofont("TkFixedFont")
        _half = max(6, int(round(abs(int(_base.cget("size"))) / 2.0)))
        self._live_log_font = _base.copy()
        self._live_log_font.configure(size=8)

        logs_frame = ttk.LabelFrame(left_split, text="Live Output")
        self.logs_nb = ttk.Notebook(logs_frame)
        self.logs_nb.pack(fill="both", expand=True, padx=6, pady=6)

        # Trainers tab (multi-coin) - FIRST
        trainer_tab = ttk.Frame(self.logs_nb)
        self.logs_nb.add(trainer_tab, text="Training")

        # Create trainer coin selection frame at the top
        trainer_controls = ttk.Frame(trainer_tab)
        trainer_controls.pack(fill="x", padx=4, pady=2)

        ttk.Label(trainer_controls, text="Coin:").pack(side="left", padx=(0, 5))

        # Create trainer_coin_var for compatibility with other code that references it
        self.trainer_coin_var = tk.StringVar(
            value=(self.coins[0] if self.coins else "BTC")
        )

        self.trainer_coin_combo = ttk.Combobox(
            trainer_controls,
            textvariable=self.trainer_coin_var,
            values=self.coins,
            state="readonly",
            width=10,
        )
        self.trainer_coin_combo.pack(side="left", padx=(0, 10))

        # Add training status label
        self.trainer_status_lbl = ttk.Label(
            trainer_controls, text="(no trainers running)"
        )
        self.trainer_status_lbl.pack(side="left", padx=(10, 0))

        # Create text frame for the output display
        trainer_text_frame = ttk.Frame(trainer_tab)
        trainer_text_frame.pack(fill="both", expand=True, padx=4, pady=2)

        self.trainer_text = tk.Text(
            trainer_text_frame,
            height=8,
            wrap="none",
            font=self._live_log_font,
            bg=p["PANEL"],
            fg=p["FG"],
            insertbackground=p["FG"],
            selectbackground=p["SELECT_BG"],
            selectforeground=p["SELECT_FG"],
            highlightbackground=p["BORDER"],
            highlightcolor=p["ACCENT"],
        )

        trainer_scroll = ttk.Scrollbar(
            trainer_text_frame, orient="vertical", command=self.trainer_text.yview
        )
        self.trainer_text.configure(yscrollcommand=trainer_scroll.set)
        self.trainer_text.pack(side="left", fill="both", expand=True)
        trainer_scroll.pack(side="right", fill="y")

        # Runner tab - SECOND
        runner_tab = ttk.Frame(self.logs_nb)
        self.logs_nb.add(runner_tab, text="Thinking")
        self.runner_text = tk.Text(
            runner_tab,
            height=8,
            wrap="none",
            font=self._live_log_font,
            bg=p["PANEL"],
            fg=p["FG"],
            insertbackground=p["FG"],
            selectbackground=p["SELECT_BG"],
            selectforeground=p["SELECT_FG"],
            highlightbackground=p["BORDER"],
            highlightcolor=p["ACCENT"],
        )

        runner_scroll = ttk.Scrollbar(
            runner_tab, orient="vertical", command=self.runner_text.yview
        )
        self.runner_text.configure(yscrollcommand=runner_scroll.set)
        self.runner_text.pack(side="left", fill="both", expand=True)
        runner_scroll.pack(side="right", fill="y")

        # Trader tab - THIRD
        trader_tab = ttk.Frame(self.logs_nb)
        self.logs_nb.add(trader_tab, text="Trading")
        self.trader_text = tk.Text(
            trader_tab,
            height=8,
            wrap="none",
            font=self._live_log_font,
            bg=p["PANEL"],
            fg=p["FG"],
            insertbackground=p["FG"],
            selectbackground=p["SELECT_BG"],
            selectforeground=p["SELECT_FG"],
            highlightbackground=p["BORDER"],
            highlightcolor=p["ACCENT"],
        )

        trader_scroll = ttk.Scrollbar(
            trader_tab, orient="vertical", command=self.trader_text.yview
        )
        self.trader_text.configure(yscrollcommand=trader_scroll.set)
        self.trader_text.pack(side="left", fill="both", expand=True)
        trader_scroll.pack(side="right", fill="y")

        # Colour lines by kind (see _log_line_tag)
        self._live_log_bold = self._live_log_font.copy()
        self._live_log_bold.configure(weight="bold")
        for log_text in (self.trainer_text, self.runner_text, self.trader_text):
            log_text.tag_configure("log_error", foreground=STATUS_RED)
            log_text.tag_configure("log_warn", foreground=STATUS_AMBER)
            log_text.tag_configure("log_long", foreground=STATUS_GREEN)
            log_text.tag_configure("log_short", foreground=LOG_SHORT)
            log_text.tag_configure(
                "log_state", foreground=p["ACCENT2"], font=self._live_log_bold
            )
            log_text.tag_configure("log_dim", foreground=p["MUTED"])
            log_text.tag_raise("sel")
        # Add left panes to vertical PanedWindow (enables drag sash between Controls and Live Output)
        left_split.add(top_controls, weight=0)
        left_split.add(logs_frame, weight=1)
        try:
            left_split.paneconfigure(top_controls, minsize=280)
            left_split.paneconfigure(logs_frame, minsize=80)
        except Exception:
            pass

        def _fit_left_split() -> None:
            """Give the Controls pane the height its content asks for (within
            limits) and the rest to Live Output; not after the user moved the sash."""
            if getattr(self, "_user_moved_left_split", False):
                return
            if getattr(self, "_fit_left_split_pending", False):
                return
            self._fit_left_split_pending = True

            def _apply() -> None:
                self._fit_left_split_pending = False
                try:
                    total = left_split.winfo_height()
                    if total <= 2:
                        self.after(50, _fit_left_split)
                        return
                    target = _left_split_target(top_controls.winfo_reqheight(), total)
                    if abs(left_split.sashpos(0) - target) > 2:
                        left_split.sashpos(0, target)
                except Exception:
                    pass

            self.after_idle(_apply)

        self._fit_left_split = _fit_left_split
        self.after_idle(_fit_left_split)

        # ----------------------------
        # RIGHT TOP: Charts (tabs)
        # ----------------------------
        charts_frame = ttk.LabelFrame(right_split, text="Charts")
        self._charts_frame = charts_frame

        self._build_chart_tab_row(charts_frame)

        # Page container (no ttk.Notebook, so there are NO native tabs to show)
        self.chart_pages_container = ttk.Frame(charts_frame)
        # Keep left padding, remove right padding so charts fill to the edge
        self.chart_pages_container.pack(  # 5 px to the panel's edges
            fill="both",
            expand=True,
            padx=(SPACE["edge"], SPACE["edge"]),
            pady=(0, SPACE["edge"]),
        )

        self._chart_tab_buttons: Dict[str, ttk.Button] = {}
        self.chart_pages: Dict[str, ttk.Frame] = {}
        self._current_chart_page: str = "ACCOUNT"

        def _show_page(name: str) -> None:
            self._current_chart_page = name
            # hide all pages
            for f in self.chart_pages.values():
                try:
                    f.pack_forget()
                except Exception:
                    pass
            # show selected
            f = self.chart_pages.get(name)
            if f is not None:
                f.pack(fill="both", expand=True)

            # style selected tab
            for txt, b in self._chart_tab_buttons.items():
                try:
                    b.configure(
                        style=(
                            "ChartTabSelected.TButton"
                            if txt == name
                            else "ChartTab.TButton"
                        )
                    )
                except Exception:
                    pass
            self._show_chart_timeframe(name)
            self._show_chart_status(name)

            # Immediately refresh the newly shown coin chart so candles appear right away
            # (even if trader/neural scripts are not running yet).
            try:
                tab = str(name or "").strip().upper()
                if tab and tab != "ACCOUNT":
                    coin = tab
                    chart = self.charts.get(coin)
                    if chart:

                        def _do_refresh_visible():
                            try:
                                # Ensure coin folders exist (best-effort; fast)
                                try:
                                    cf_sig = (
                                        self.settings.get("main_neural_dir"),
                                        tuple(self.coins),
                                    )
                                    if (
                                        getattr(self, "_coin_folders_sig", None)
                                        != cf_sig
                                    ):
                                        self._coin_folders_sig = cf_sig
                                        self.coin_folders = build_coin_folders(
                                            self.settings["main_neural_dir"], self.coins
                                        )
                                except Exception:
                                    pass

                                pos = (
                                    self._last_positions.get(coin, {})
                                    if isinstance(self._last_positions, dict)
                                    else {}
                                )
                                buy_px = pos.get("current_buy_price", None)
                                sell_px = pos.get("current_sell_price", None)
                                trail_line = pos.get("trail_line", None)
                                dca_line_price = pos.get("dca_line_price", None)
                                avg_cost_basis = pos.get("avg_cost_basis", None)

                                chart.refresh(
                                    self.coin_folders,
                                    current_buy_price=buy_px,
                                    current_sell_price=sell_px,
                                    trail_line=trail_line,
                                    dca_line_price=dca_line_price,
                                    avg_cost_basis=avg_cost_basis,
                                    trader_running=self._trader_is_running(),
                                )

                            except Exception:
                                pass

                        self.after(1, _do_refresh_visible)
            except Exception:
                pass

        self._show_chart_page = _show_page  # used by _rebuild_coin_chart_tabs()

        # ACCOUNT page
        acct_page = ttk.Frame(self.chart_pages_container)
        self.chart_pages["ACCOUNT"] = acct_page

        acct_btn = ttk.Button(
            self.chart_tabs_bar.inner,
            text="ACCOUNT",
            style="ChartTab.TButton",
            command=lambda: self._show_chart_page("ACCOUNT"),
        )
        self.chart_tabs_bar.add(
            acct_btn, padx=(0, SPACE["sm"]), pady=(0, TAB_BUTTON_GAP)
        )
        self._chart_tab_buttons["ACCOUNT"] = acct_btn

        self.account_chart = self._new_account_chart(acct_page)

        # Coin pages
        self.charts: Dict[str, CandleChart] = {}
        for coin in self.coins:
            page = ttk.Frame(self.chart_pages_container)
            self.chart_pages[coin] = page

            btn = ttk.Button(
                self.chart_tabs_bar.inner,
                text=coin,
                style="ChartTab.TButton",
                command=lambda c=coin: self._show_chart_page(c),
            )
            self.chart_tabs_bar.add(
                btn, padx=(0, SPACE["sm"]), pady=(0, TAB_BUTTON_GAP)
            )
            self._chart_tab_buttons[coin] = btn

            chart = CandleChart(
                page,
                self.fetcher,
                coin,
                self._settings_getter,
                self.trade_history_path,
                status_parent=self._chart_status_slot,
            )
            chart.pack(fill="both", expand=True)
            self.charts[coin] = chart

        # show initial page
        self._show_chart_page("ACCOUNT")

        # ----------------------------
        # RIGHT BOTTOM: Tabbed Interface (Current Trades + Long-term Holdings + Trade History)
        # ----------------------------
        self.bottom_notebook = ttk.Notebook(right_split)
        # the panel's border is the only one round each tab: the notebooks and
        # titled groups the module windows build inside it draw none
        ui_table.borderless_inside(self.bottom_notebook)

        # Every tab's table is a ui_table.DataTable filling its tab (owner,
        # 2026-11-04): no inner title or border, scrollbars on the table itself.

        # ----------------------------
        # TAB 1: Current Trades
        # ----------------------------
        trades_tab = ttk.Frame(self.bottom_notebook)
        self.bottom_notebook.add(trades_tab, text="Current\nTrades")
        # Exposed so the paper-mode hook can pack a "PAPER TRADING" label
        # at the top of the trading section without re-walking the widget tree.
        self.trades_frame = trades_tab

        cols = (
            "coin",
            "qty",
            "value",  # <-- right after qty
            "avg_cost",
            "buy_price",
            "buy_pnl",
            "sell_price",
            "sell_pnl",
            "dca_stages",
            "dca_24h",
            "next_dca",
            "trail_line",  # keep trail line column
        )

        header_labels = {
            "coin": "Coin",
            "qty": "Qty",
            "value": "Value",
            "avg_cost": "Avg Cost",
            "buy_price": "Ask Price",
            "buy_pnl": "DCA PnL",
            "sell_price": "Bid Price",
            "sell_pnl": "Sell PnL",
            "dca_stages": "DCA Stage",
            "dca_24h": "DCA 24h",
            "next_dca": "Next DCA",
            "trail_line": "Trail Line",
        }

        self.trades_table = ui_table.DataTable(
            trades_tab,
            cols,
            header_labels,
            key="current_trades",
            numeric=[c for c in cols if c != "coin"],
        )
        self.trades_table.pack(fill="both", expand=True)
        self.trades_tree = self.trades_table.tree

        # ----------------------------
        # TAB 2: Long-term Holdings: the holdings window (Holdings, Portfolio
        # Overview, Rebalancing, Analytics) under one subtitle (owner, 2026-11-04)
        # ----------------------------
        lth_tab = ttk.Frame(self.bottom_notebook)
        self.bottom_notebook.add(lth_tab, text="Long-term\nHoldings")
        self._create_long_term_holdings_tab(lth_tab)

        # ----------------------------
        # TAB 3: Trade History: the history as a table, with filters and a summary
        # ----------------------------
        hist_tab = ttk.Frame(self.bottom_notebook)
        self.bottom_notebook.add(hist_tab, text="Trade\nHistory")
        self.trade_history_view = trade_history_view.TradeHistoryView(
            hist_tab, money=_fmt_money, price=_fmt_price, pct=_fmt_pct
        )
        self.trade_history_view.pack(fill="both", expand=True)
        self.hist_filter_var = self.trade_history_view.search_var

        # ----------------------------
        # Entry Assessments: what the entry assessment recorded for each entry
        # (Settings > Strategy and Risk; Off by default, Log only at most)
        # ----------------------------
        assessments_tab = ttk.Frame(self.bottom_notebook)
        self.bottom_notebook.add(assessments_tab, text="Entry\nAssessments")
        try:
            import entry_assessment_view

            self.entry_assessment_view = entry_assessment_view.EntryAssessmentView(
                assessments_tab
            )
            self.entry_assessment_view.pack(fill="both", expand=True)
        except Exception as e:
            ttk.Label(
                assessments_tab, text=f"The entry assessments cannot be shown: {e}"
            ).pack(padx=10, pady=10, anchor="w")

        # ----------------------------
        # TAB 4: Order Management
        # ----------------------------
        if ORDER_MANAGEMENT_AVAILABLE:
            self._create_order_management_tab()

        # ----------------------------
        # TAB 5: LLM Research Engine
        # ----------------------------
        self._create_llm_research_tab()

        # ----------------------------
        # TAB 6: Real-time Market Data
        # ----------------------------
        self._create_market_data_tab()

        # ----------------------------
        # TAB 7: Portfolio Optimization
        # ----------------------------
        self._create_portfolio_optimization_tab()

        # ----------------------------
        # TAB 8: Backtesting Framework
        # ----------------------------
        self._create_backtesting_tab()

        # ----------------------------
        # TAB 9: Performance Attribution
        # ----------------------------
        self._create_performance_attribution_tab()

        # ----------------------------
        # TAB 10: Institutional Trading
        # ----------------------------
        self._create_institutional_trading_tab()

        # Left to right as MODULE_TAB_ORDER says, whatever order they were built in;
        # Current Trades is the one shown at start-up
        self._order_module_tabs()
        self.bottom_notebook.select(trades_tab)

        # Assemble right side
        right_split.add(charts_frame, weight=3)
        right_split.add(self.bottom_notebook, weight=2)

        try:
            # Screenshot-style sizing: don't force Charts to be enormous by default.
            right_split.paneconfigure(charts_frame, minsize=360)
            right_split.paneconfigure(self.bottom_notebook, minsize=220)
        except Exception:
            pass

        # Startup defaults to match the screenshot (but never override if user already dragged).
        def _init_right_split_sash_once():
            try:
                if getattr(self, "_did_init_right_split_sash", False):
                    return

                if getattr(self, "_user_moved_right_split", False):
                    self._did_init_right_split_sash = True
                    return

                total = right_split.winfo_height()
                if total <= 2:
                    self.after(10, _init_right_split_sash_once)
                    return

                min_top = 360
                min_bottom = 220
                # Charts at half the window height, less the status row that moved
                # into the tab row (owner, 2026-10-14): the chart keeps its height
                # and the panel below gains the row's
                target = total // 2 - self._moved_status_row_px()
                target = max(min_top, min(total - min_bottom, target))

                right_split.sashpos(0, int(target))
                self._did_init_right_split_sash = True
            except Exception:
                pass
                pass

        self.after_idle(_init_right_split_sash_once)

        # Initial clamp once everything is laid out
        self.after_idle(
            lambda: (
                self._schedule_paned_clamp(getattr(self, "_pw_outer", None)),
                self._schedule_paned_clamp(getattr(self, "_pw_left_split", None)),
                self._schedule_paned_clamp(getattr(self, "_pw_right_split", None)),
            )
        )

        # status bar
        self.status = ttk.Label(self, text="Ready", anchor="w")
        self.status.pack(fill="x", side="bottom")

    # ---- panedwindow anti-collapse helpers ----

    def _schedule_paned_clamp(self, pw: ttk.Panedwindow) -> None:
        """
        Debounced clamp so we don't fight the geometry manager mid-resize.

        IMPORTANT: use `after(1, ...)` instead of `after_idle(...)` so it still runs
        while the mouse is held during sash dragging (Tk often doesn't go "idle"
        until after the drag ends, which is exactly when panes can vanish).
        """
        try:
            if not pw or not int(pw.winfo_exists()):
                return
        except Exception:
            return

        key = str(pw)
        if key in self._paned_clamp_after_ids:
            return

        def _run():
            try:
                self._paned_clamp_after_ids.pop(key, None)
            except Exception:
                pass
            self._clamp_panedwindow_sashes(pw)

        try:
            self._paned_clamp_after_ids[key] = self.after(1, _run)
        except Exception:
            pass

    def _clamp_panedwindow_sashes(self, pw: ttk.Panedwindow) -> None:
        """
        Enforces each pane's configured 'minsize' by clamping sash positions.

        NOTE:
        ttk.Panedwindow.paneconfigure(pane) typically returns dict values like:
            {"minsize": ("minsize", "minsize", "Minsize", "140"), ...}
        so we MUST pull the last element when it's a tuple/list.
        """
        try:
            if not pw or not int(pw.winfo_exists()):
                return

            panes = list(pw.panes())
            if len(panes) < 2:
                return

            orient = str(pw.cget("orient"))
            total = pw.winfo_height() if orient == "vertical" else pw.winfo_width()
            if total <= 2:
                return

            def _get_minsize(pane_id) -> int:
                try:
                    cfg = pw.paneconfigure(pane_id)
                    ms = cfg.get("minsize", 0)

                    # ttk returns tuples like ('minsize','minsize','Minsize','140')
                    if isinstance(ms, (tuple, list)) and ms:
                        ms = ms[-1]

                    # sometimes it's already int/float-like, sometimes it's a string
                    return max(0, int(float(ms)))
                except Exception:
                    return 0

            mins: List[int] = [_get_minsize(p) for p in panes]

            # If total space is smaller than sum(mins), we still clamp as best-effort
            # by scaling mins down proportionally but never letting a pane hit 0.
            if sum(mins) >= total:
                # best-effort: keep every pane at least 24px so it can’t disappear
                floor = 24
                mins = [max(floor, m) for m in mins]

                # if even floors don't fit, just stop here (window minsize should prevent this)
                if sum(mins) >= total:
                    return

            # Two-pass clamp so constraints settle even with multiple sashes
            for _ in range(2):
                for i in range(len(panes) - 1):
                    min_pos = sum(mins[: i + 1])
                    max_pos = total - sum(mins[i + 1 :])

                    try:
                        cur = int(pw.sashpos(i))
                    except Exception:
                        continue

                    new = max(min_pos, min(max_pos, cur))
                    if new != cur:
                        try:
                            pw.sashpos(i, new)
                        except Exception:
                            pass

        except Exception:
            pass

    # ---- process control ----

    def _reader_thread(
        self, proc: subprocess.Popen, q: "queue.Queue[str]", prefix: str
    ) -> None:
        try:
            # line-buffered text mode
            while True:
                line = proc.stdout.readline() if proc.stdout else ""
                if not line:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue
                q.put(f"{prefix}{line.rstrip()}")
        except Exception as exc:
            q.put(f"{prefix}[log reader stopped: {exc}]")
        finally:
            note = self._exit_note(proc)
            requested = getattr(self, "_stop_requested_pids", None)
            if requested is not None and proc.pid in requested:
                requested.discard(proc.pid)
                note += " - stopped from the hub"
            q.put(f"{prefix}[process exited{note}]")

    def _note_stop_requested(self, proc) -> None:
        """Remember that the hub asked ``proc`` to stop, so its exit line (code 1
        from a terminate) says so instead of looking like a crash."""
        try:
            if not hasattr(self, "_stop_requested_pids"):
                self._stop_requested_pids = set()
            self._stop_requested_pids.add(proc.pid)
        except Exception:
            pass

    @staticmethod
    def _exit_note(proc: subprocess.Popen) -> str:
        """', code N' once the process has ended, else a note that it still runs."""
        try:
            code = proc.wait(timeout=2)
        except Exception:
            return " - log lost, the process may still be running"
        return f", code {code}"

    def _start_process(
        self, p: ProcInfo, log_q: Optional["queue.Queue[str]"] = None, prefix: str = ""
    ) -> None:
        if p.proc and p.proc.poll() is None:
            return
        if not os.path.isfile(p.path):
            messagebox.showerror("Missing script", f"Cannot find: {p.path}")
            return

        env = _child_env(self.hub_dir)  # so rhcb writes where GUI reads

        try:
            p.proc = subprocess.Popen(
                [sys.executable, "-u", p.path],  # -u for unbuffered prints
                # never the program folder: any relative write lands in user data
                cwd=pt_paths.data_dir(),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if log_q is not None:
                t = threading.Thread(
                    target=self._reader_thread,
                    args=(p.proc, log_q, prefix),
                    daemon=True,
                )
                t.start()
        except Exception as e:
            messagebox.showerror("Failed to start", f"{p.name} failed to start:\n{e}")

    def _stop_process(self, p: ProcInfo) -> None:
        if not p.proc or p.proc.poll() is not None:
            return
        self._note_stop_requested(p.proc)
        try:
            p.proc.terminate()
        except Exception:
            pass

    def _order_module_tabs(self) -> None:
        """Put the bottom panel's tabs in MODULE_TAB_ORDER. A tab that is not built
        is skipped; one the list does not name keeps its place after the rest."""
        nb = self.bottom_notebook
        by_name = {module_tab_name(nb.tab(t, "text")): t for t in nb.tabs()}
        position = 0
        for name in MODULE_TAB_ORDER:
            tab = by_name.get(name)
            if tab is not None:
                nb.insert(position, tab)
                position += 1

    def _create_order_management_tab(self):
        """The Order Management tab: a toolbar over the orders, and the Order
        Notifications under them (order_management_view)."""
        try:
            # Initialize order manager
            self.order_manager = get_global_order_manager()

            # Create tab even if order manager isn't fully available
            order_tab = ttk.Frame(self.bottom_notebook)
            self.bottom_notebook.add(order_tab, text="Order\nManagement")

            if not self.order_manager.is_available:
                # Show a message about limited functionality
                ttk.Label(
                    order_tab,
                    text="Order Management System Not Available\n\nSQLAlchemy dependency required for full functionality.\nInstall with: pip install sqlalchemy",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
                return

            # Toolbar and Active Orders over the Order Notifications (owner,
            # 2026-11-04). Every 5 s the view reads both from the order management
            # database and its executor carries the open orders on, for the account
            # trading now (order_management_execution; owner, 2026-11-05)
            self.order_view = order_management_view.OrderManagementView(
                order_tab,
                self.order_manager,
                coins=lambda: list(self.coins),
                chart_coin=lambda: getattr(self, "_current_chart_page", ""),
                trading=lambda: self._trading,
                buying_power=lambda: self._last_buying_power,
                executor=order_management_execution.OrderExecutor(
                    self.order_manager.db,
                    hub_dir=lambda: self.hub_dir,
                    trading=lambda: self._trading,
                ),
                money=_fmt_money,
                price=_fmt_price,
            )
            self.order_view.pack(fill="both", expand=True)
            self.orders_table = self.order_view.orders_table
            self.orders_tree = self.order_view.orders_tree

        except Exception as e:
            print(f"Error creating order management tab: {e}")

    def _create_llm_research_tab(self):
        """Create the LLM Research Engine tab for AI-powered market analysis."""
        try:
            # Always create the tab first
            research_tab = ttk.Frame(self.bottom_notebook)
            self.bottom_notebook.add(research_tab, text="LLM\nResearch")

            if not LLM_RESEARCH_AVAILABLE:
                # Show a message about unavailability
                ttk.Label(
                    research_tab,
                    text="LLM Research Engine Not Available\n\nRequired dependencies missing.\nPlease check imports and dependencies.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
                print("LLM Research Engine not available")
                return

            # The research tab: the coins in Settings; every LLM setting is in
            # Settings > LLM Providers
            self.research_gui = ResearchEngineGUI(
                research_tab,
                coins=lambda: list(getattr(self, "coins", []) or []),
                open_settings=self.open_llm_settings,
            )

            print("LLM Research Engine tab created successfully")

        except Exception as e:
            # If there's an error after tab creation, show error message in the tab
            try:
                for widget in research_tab.winfo_children():
                    widget.destroy()
                ttk.Label(
                    research_tab,
                    text=f"LLM Research Engine Error\n\n{str(e)}\n\nPlease check console for details.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
            except Exception:
                pass
            print(f"Error creating LLM Research tab: {e}")
            import traceback

            traceback.print_exc()

    def _create_long_term_holdings_tab(self, tab) -> None:
        """Long-term Holdings: a subtitle over the holdings window
        (long_term_holdings_gui: Holdings, Portfolio Overview, Rebalancing,
        Analytics), all from holdings.db. Separate from the trading account: the
        account's figures do not include the holdings, and nothing links them. The
        Add Holding dialog offers the coins in Settings."""
        ui_table.subtitle(tab, LONG_TERM_HOLDINGS_SUBTITLE)
        self.holdings_gui = None
        body = ttk.Frame(tab)
        body.pack(fill="both", expand=True)
        if not HOLDINGS_MANAGEMENT_AVAILABLE:
            ttk.Label(
                body,
                text="The holdings could not be loaded.",
                style="Muted.TLabel",
                anchor="center",
            ).pack(expand=True, fill="both", padx=20, pady=20)
            print("Long-term Holdings not available")
            return
        try:
            self.holdings_gui = HoldingsManagementGUI(
                body,
                coins=lambda: list(self.coins),
                money=_fmt_money,
                price=_fmt_price,
            )
        except Exception as e:
            self.holdings_gui = None
            for widget in body.winfo_children():
                widget.destroy()
            ttk.Label(
                body,
                text=f"The holdings could not be loaded:\n{e}",
                style="Muted.TLabel",
                anchor="center",
            ).pack(expand=True, fill="both", padx=20, pady=20)
            print(f"Error creating the Long-term Holdings tab: {e}")
            import traceback

            traceback.print_exc()

    def _create_market_data_tab(self):
        """Create the Real-time Market Data tab for live market monitoring."""
        try:
            # Always create the tab first
            market_data_tab = ttk.Frame(self.bottom_notebook)
            self.bottom_notebook.add(market_data_tab, text="Market\nData")

            if not MARKET_DATA_GUI_AVAILABLE:
                # Show a message about unavailability
                ttk.Label(
                    market_data_tab,
                    text="Real-time Market Data Not Available\n\nRequired dependencies missing.\nPlease install real-time market data module.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
                print("Real-time Market Data not available")
                return

            # Initialize the market data GUI: the coins in Settings by default
            self.market_data_gui = MarketDataGUI(
                market_data_tab, coins=lambda: list(getattr(self, "coins", []) or [])
            )

            print("Real-time Market Data tab created successfully")

        except Exception as e:
            # If there's an error after tab creation, show error message in the tab
            try:
                for widget in market_data_tab.winfo_children():
                    widget.destroy()
                ttk.Label(
                    market_data_tab,
                    text=f"Market Data Error\n\n{str(e)}\n\nPlease check console for details.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
            except Exception:
                pass
            print(f"Error creating Real-time Market Data tab: {e}")
            import traceback

            traceback.print_exc()

    def _create_portfolio_optimization_tab(self):
        """The Portfolio Optimization tab (portfolio_optimizer_gui): the coins in
        Settings, their daily candles from the candle cache, and the current
        portfolio from Long-term Holdings (its tag filter), built before it."""
        self.portfolio_optimizer_gui = None
        try:
            # Always create the tab first
            portfolio_opt_tab = ttk.Frame(self.bottom_notebook)
            self.bottom_notebook.add(portfolio_opt_tab, text="Portfolio\nOptimization")

            if not PORTFOLIO_OPTIMIZER_AVAILABLE:
                ttk.Label(
                    portfolio_opt_tab,
                    text="Portfolio Optimization could not be loaded.",
                    style="Muted.TLabel",
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
                print("Portfolio Optimization not available")
                return

            self.portfolio_optimizer_gui = PortfolioOptimizerGUI(
                portfolio_opt_tab,
                coins=lambda: list(self.coins),
                holdings=getattr(self, "holdings_gui", None),
                money=_fmt_money,
                price=_fmt_price,
            )

            print("Portfolio Optimization tab created successfully")

        except Exception as e:
            # If there's an error after tab creation, show error message in the tab
            try:
                for widget in portfolio_opt_tab.winfo_children():
                    widget.destroy()
                ttk.Label(
                    portfolio_opt_tab,
                    text=f"Portfolio Optimization Error\n\n{str(e)}\n\nPlease check console for details.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
            except Exception:
                pass
            print(f"Error creating Portfolio Optimization tab: {e}")
            import traceback

            traceback.print_exc()

    def _create_backtesting_tab(self):
        """Create the Backtesting Framework tab for strategy testing and optimization."""
        try:
            # Create tab
            backtest_tab = ttk.Frame(self.bottom_notebook)
            self.bottom_notebook.add(backtest_tab, text="Backtesting\nFramework")

            if not BACKTESTING_FRAMEWORK_AVAILABLE:
                # Show dependency message
                ttk.Label(
                    backtest_tab,
                    text="Backtesting Framework\n\nFor enhanced backtesting features, install optional dependencies:\n\npython app/install_optional_deps.py\n\nCore features available without optional packages.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
                print("Backtesting Framework available with limited functionality")
                return

            # Initialize the backtesting GUI
            self.backtesting_gui = BacktestingGUI(backtest_tab)

            print("Backtesting Framework tab created successfully")

        except Exception as e:
            # If there's an error after tab creation, show error message in the tab
            try:
                for widget in backtest_tab.winfo_children():
                    widget.destroy()
                ttk.Label(
                    backtest_tab,
                    text=f"Backtesting Framework Error\n\n{str(e)}\n\nPlease check console for details.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
            except Exception:
                pass
            print(f"Error creating Backtesting Framework tab: {e}")
            import traceback

            traceback.print_exc()

    def _create_performance_attribution_tab(self):
        """Create the Performance Attribution tab for portfolio analysis."""
        try:
            # Create tab
            attribution_tab = ttk.Frame(self.bottom_notebook)
            self.bottom_notebook.add(attribution_tab, text="Performance\nAttribution")

            if not PERFORMANCE_ATTRIBUTION_AVAILABLE:
                # Show dependency message
                ttk.Label(
                    attribution_tab,
                    text="Performance Attribution Engine\n\nFor enhanced attribution analysis features, install optional dependencies:\n\npython app/install_optional_deps.py\n\nCore features available without optional packages.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
                print(
                    "Performance Attribution Engine available with limited functionality"
                )
                return

            # Initialize the performance attribution GUI
            self.performance_attribution_gui = PerformanceAttributionGUI(
                attribution_tab
            )

            print("Performance Attribution tab created successfully")

        except Exception as e:
            # If there's an error after tab creation, show error message in the tab
            try:
                for widget in attribution_tab.winfo_children():
                    widget.destroy()
                ttk.Label(
                    attribution_tab,
                    text=f"Performance Attribution Error\n\n{str(e)}\n\nPlease check console for details.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
            except Exception:
                pass
            print(f"Error creating Performance Attribution tab: {e}")
            import traceback

            traceback.print_exc()

    def _create_institutional_trading_tab(self):
        """Create the Institutional Trading tab for enterprise-grade trading."""
        try:
            # Create tab
            institutional_tab = ttk.Frame(self.bottom_notebook)
            self.bottom_notebook.add(institutional_tab, text="Institutional\nTrading")

            if not INSTITUTIONAL_TRADING_AVAILABLE:
                # Show dependency message
                ttk.Label(
                    institutional_tab,
                    text="Institutional Trading System\n\nEnterprise-grade trading infrastructure with:\n• High-volume order processing\n• Advanced algorithmic execution (TWAP, VWAP, Iceberg)\n• Institutional risk management\n• Batch order processing\n• Performance monitoring\n• Compliance reporting\n\nSystem is initializing...",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
                print("Institutional Trading System loading...")
                return

            # Initialize the institutional trading GUI
            self.institutional_trading_gui = InstitutionalTradingGUI(institutional_tab)

            print("Institutional Trading tab created successfully")

        except Exception as e:
            # If there's an error after tab creation, show error message in the tab
            try:
                for widget in institutional_tab.winfo_children():
                    widget.destroy()
                ttk.Label(
                    institutional_tab,
                    text=f"Institutional Trading Error\n\n{str(e)}\n\nPlease check console for details.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
            except Exception:
                pass
            print(f"Error creating Institutional Trading tab: {e}")
            import traceback

            traceback.print_exc()

    def _run_startup_dependency_check(self):
        """Run dependency check at startup and show results."""
        try:
            if not DEPENDENCY_CHECKER_AVAILABLE:
                print("Dependency checker not available - skipping check")
                return

            # Run quick check for immediate feedback
            quick_results = quick_check()
            missing_critical = [
                name for name, available in quick_results.items() if not available
            ]

            if missing_critical:
                print(
                    f"\n⚠️  WARNING: Missing critical dependencies: {', '.join(missing_critical)}"
                )
                print("PowerTrader functionality will be limited.")
                print("Run full dependency check from Help menu for details.\n")
            else:
                print("✅ All critical dependencies available")

            # Store checker for later use
            self.dependency_checker = get_dependency_checker()

        except Exception as e:
            print(f"Error during dependency check: {e}")

    def show_dependency_status(self):
        """Show comprehensive dependency status window."""
        p = ui_theme.active_palette()
        try:
            if not DEPENDENCY_CHECKER_AVAILABLE:
                messagebox.showinfo(
                    "Dependency Check", "Dependency checker not available"
                )
                return

            # Run full check
            results = self.dependency_checker.check_all_dependencies()

            # Create status window
            status_window = tk.Toplevel(self)
            status_window.title("PowerTrader - Dependency Status")
            status_window.geometry("800x600")
            status_window.configure(bg=p["BG"])

            # Create notebook for different views
            notebook = ttk.Notebook(status_window)
            notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            # Overview tab
            self._create_dependency_overview_tab(notebook, results)

            # Detailed tab
            self._create_dependency_details_tab(notebook, results)

            # Install instructions tab
            self._create_install_instructions_tab(notebook)

            # Make window modal and center it
            status_window.transient(self)
            status_window.grab_set()

            # Center the window
            status_window.geometry(f"+{self.winfo_x() + 50}+{self.winfo_y() + 50}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to show dependency status: {str(e)}")

    def _create_dependency_overview_tab(self, notebook, results):
        """Create overview tab for dependency status."""
        p = ui_theme.active_palette()
        overview_frame = ttk.Frame(notebook)
        notebook.add(overview_frame, text="Overview")

        # Summary statistics
        available_count = sum(1 for dep in results.values() if dep.available)
        total_count = len(results)
        required_missing = [
            dep for dep in results.values() if dep.required and not dep.available
        ]

        # Header
        header_frame = ttk.Frame(overview_frame)
        header_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(
            header_frame,
            text="PowerTrader Dependency Status",
            font=ui_tokens.font("display", "bold"),
        ).pack()

        ttk.Label(
            header_frame,
            text=f"Dependencies: {available_count}/{total_count} available",
            font=ui_tokens.font("body"),
        ).pack()

        # Status indicators
        status_frame = ttk.LabelFrame(overview_frame, text="Feature Status")
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Create scrolled text for status
        status_text = tk.Text(
            status_frame,
            height=15,
            bg=p["PANEL"],
            fg=p["FG"],
            font=ui_tokens.mono("body"),
        )
        status_scrollbar = ttk.Scrollbar(
            status_frame, orient=tk.VERTICAL, command=status_text.yview
        )
        status_text.configure(yscrollcommand=status_scrollbar.set)

        status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        status_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Generate status text
        status_content = f"PowerTrader Feature Status Report\n"
        status_content += "=" * 50 + "\n\n"

        # Get functionality status
        functionality_status = self.dependency_checker._get_functionality_status()
        for feature, status in functionality_status.items():
            status_content += f"{status['icon']} {feature}: {status['status']}\n"

        status_content += "\n" + "=" * 50 + "\n"
        status_content += "Dependency Summary:\n"
        status_content += f"Available: {available_count}\n"
        status_content += f"Missing: {total_count - available_count}\n"

        if required_missing:
            status_content += f"\n⚠️ CRITICAL: {len(required_missing)} required dependencies missing!\n"
            for dep in required_missing:
                status_content += f"  - {dep.name}\n"
        else:
            status_content += "\n✅ All required dependencies available\n"

        status_text.insert(tk.END, status_content)
        status_text.config(state=tk.DISABLED)

    def _create_dependency_details_tab(self, notebook, results):
        """Create detailed tab for dependency status."""
        details_frame = ttk.Frame(notebook)
        notebook.add(details_frame, text="Details")

        # Create tree view for dependencies
        tree_frame = ttk.Frame(details_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        columns = ("Name", "Status", "Version", "Type", "Description")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=20)

        # Configure columns
        tree.heading("Name", text="Dependency")
        tree.heading("Status", text="Status")
        tree.heading("Version", text="Version")
        tree.heading("Type", text="Type")
        tree.heading("Description", text="Description")

        tree.column("Name", width=120, anchor=tk.W)
        tree.column("Status", width=80, anchor=tk.CENTER)
        tree.column("Version", width=100, anchor=tk.W)
        tree.column("Type", width=80, anchor=tk.CENTER)
        tree.column("Description", width=300, anchor=tk.W)

        # Add scrollbar
        tree_scrollbar = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=tree.yview
        )
        tree.configure(yscrollcommand=tree_scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Populate tree
        for dep in sorted(
            results.values(), key=lambda x: (not x.available, x.required, x.name)
        ):
            status = "✅ Available" if dep.available else "❌ Missing"
            dep_type = "Required" if dep.required else "Optional"
            version = dep.version or "N/A"

            tree.insert(
                "",
                tk.END,
                values=(
                    dep.name,
                    status,
                    version,
                    dep_type,
                    (
                        dep.description[:50] + "..."
                        if len(dep.description) > 50
                        else dep.description
                    ),
                ),
            )

    def _create_install_instructions_tab(self, notebook):
        """Create install instructions tab."""
        p = ui_theme.active_palette()
        install_frame = ttk.Frame(notebook)
        notebook.add(install_frame, text="Install Instructions")

        # Instructions header
        header_frame = ttk.Frame(install_frame)
        header_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(
            header_frame,
            text="Installation Instructions",
            font=ui_tokens.font("title", "bold"),
        ).pack()

        # Install script text area
        script_frame = ttk.LabelFrame(install_frame, text="Copy and run this script:")
        script_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        script_text = tk.Text(
            script_frame,
            height=15,
            bg=p["PANEL"],
            fg=p["FG"],
            font=ui_tokens.mono("small"),
            wrap=tk.WORD,
        )
        script_scrollbar = ttk.Scrollbar(
            script_frame, orient=tk.VERTICAL, command=script_text.yview
        )
        script_text.configure(yscrollcommand=script_scrollbar.set)

        script_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        script_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Generate install script
        install_script = self.dependency_checker.generate_install_script()
        script_text.insert(tk.END, install_script)
        script_text.config(state=tk.DISABLED)

        # Copy button
        button_frame = ttk.Frame(install_frame)
        button_frame.pack(fill=tk.X, padx=10, pady=5)

        def copy_script():
            self.clipboard_clear()
            self.clipboard_append(install_script)
            messagebox.showinfo("Copied", "Install script copied to clipboard!")

        ttk.Button(
            button_frame, text="Copy Script to Clipboard", command=copy_script
        ).pack(side=tk.LEFT)

        def save_script():
            from tkinter import filedialog

            filename = filedialog.asksaveasfilename(
                defaultextension=".bat",
                filetypes=[
                    ("Batch files", "*.bat"),
                    ("Shell scripts", "*.sh"),
                    ("Text files", "*.txt"),
                ],
                title="Save Install Script",
            )
            if filename:
                try:
                    with open(filename, "w", encoding="utf-8") as f:
                        if filename.endswith(".bat"):
                            f.write("@echo off\\n")
                            f.write("echo Installing PowerTrader dependencies...\\n")
                        f.write(install_script)
                    messagebox.showinfo("Saved", f"Install script saved to: {filename}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to save script: {str(e)}")

        ttk.Button(button_frame, text="Save Script to File", command=save_script).pack(
            side=tk.LEFT, padx=(10, 0)
        )

    def show_about(self):
        """Show about dialog."""
        about_text = f"""PowerTrader AI Hub

An advanced cryptocurrency trading platform with AI-powered features.

Features:
• Multi-exchange support (66+ exchanges)
• Advanced order management with stop-loss and take-profit
• Dollar-cost averaging (DCA) automation
• LLM-powered market research and analysis
• Real-time portfolio tracking
• Dark mode interface

Version: 2026.02.23
Python: {sys.version.split()[0]}
Platform: {sys.platform}

© 2026 PowerTrader Development Team"""

        messagebox.showinfo("About PowerTrader", about_text)

    def start_neural(self) -> None:
        # Reset runner-ready gate file (prevents stale "ready" from a prior run)
        try:
            with open(self.runner_ready_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"timestamp": time.time(), "ready": False, "stage": "starting"}, f
                )
        except Exception:
            pass

        self._start_process(
            self.proc_neural, log_q=self.runner_log_q, prefix="[RUNNER] "
        )

    def start_trader(self) -> None:
        self._start_process(
            self.proc_trader, log_q=self.trader_log_q, prefix="[TRADER] "
        )

    def stop_neural(self, reason: str = "stopped with the ■ button") -> None:
        if self.proc_neural.proc and self.proc_neural.proc.poll() is None:
            try:
                self.runner_log_q.put(f"[RUNNER] [{reason}]")
            except Exception:
                pass
        self._stop_process(self.proc_neural)

    def stop_trader(self, reason: str = "stopped with the \u25a0 button") -> None:
        if self.proc_trader.proc and self.proc_trader.proc.poll() is None:
            try:
                self.trader_log_q.put(f"[TRADER] [{reason}]")
            except Exception:
                pass
        self._stop_process(self.proc_trader)

    def toggle_neural_runner(self) -> None:
        """Toggle the neural runner (thinking) process only."""
        neural_running = bool(
            self.proc_neural.proc and self.proc_neural.proc.poll() is None
        )

        if neural_running:
            self.stop_neural()
        else:
            self.start_neural()

    def toggle_all_scripts(self) -> None:
        neural_running = bool(
            self.proc_neural.proc and self.proc_neural.proc.poll() is None
        )
        trader_running = bool(
            self.proc_trader.proc and self.proc_trader.proc.poll() is None
        )

        # If anything is running (or we're waiting on runner readiness), toggle means "stop"
        if (
            neural_running
            or trader_running
            or bool(getattr(self, "_auto_start_trader_pending", False))
        ):
            self.stop_all_scripts()
            return

        # Otherwise, toggle means "start"
        self.start_all_scripts()

    def _read_runner_ready(self) -> Dict[str, Any]:
        try:
            if os.path.isfile(self.runner_ready_path):
                with open(self.runner_ready_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {"ready": False}

    def _poll_runner_ready_then_start_trader(self) -> None:
        # Cancelled or already started
        if not bool(getattr(self, "_auto_start_trader_pending", False)):
            return

        # If runner died, stop waiting
        if not (self.proc_neural.proc and self.proc_neural.proc.poll() is None):
            self._auto_start_trader_pending = False
            return

        st = self._read_runner_ready()
        if bool(st.get("ready", False)):
            self._auto_start_trader_pending = False

            # Start trader if not already running
            if not (self.proc_trader.proc and self.proc_trader.proc.poll() is None):
                self.start_trader()
            return

        # Not ready yet — keep polling
        try:
            self.after(250, self._poll_runner_ready_then_start_trader)
        except Exception:
            pass

    def start_all_scripts(self) -> None:
        # Enforce training requirement ONLY for "Start All" flow (which auto-starts trader)
        # Individual Neural Runner can be started anytime
        all_trained = (
            all(self._coin_is_trained(c) for c in self.coins) if self.coins else False
        )
        if not all_trained:
            messagebox.showwarning(
                "Training required",
                "All coins must be trained before starting the full automated flow.\n\nUse Train All first, or start Neural Runner individually.",
            )
            return

        self._auto_start_trader_pending = True
        self.start_neural()

        # Wait for runner to signal readiness before starting trader
        try:
            self.after(250, self._poll_runner_ready_then_start_trader)
        except Exception:
            pass

    def _auto_start_on_launch(self) -> None:
        """Settings > System: start the Neural Runner, then the Trader once the runner
        is ready. Like Start All it needs every coin trained; without that, a notice
        says which are not and nothing starts."""
        if not self.settings.get("auto_start_scripts", False):
            return
        untrained = [c for c in self.coins if not self._coin_is_trained(c)]
        if not self.coins or untrained:
            self._show_notice(
                "Auto start skipped: "
                + (
                    f"{', '.join(untrained)} not trained yet."
                    if untrained
                    else "no coins in Settings."
                )
            )
            return
        self.start_all_scripts()

    def _show_notice(self, text: str, seconds: float = NOTICE_SECONDS) -> None:
        """A small window at the hub's bottom-right corner that closes itself after
        ``seconds``; a click closes it at once. Newer notices stack above older ones.
        Every notice is kept in ``self.notices``; a hidden hub shows none."""
        print(f"NOTICE: {text}")
        if not hasattr(self, "notices"):
            self.notices = []
        self.notices.append(text)
        try:
            if not self.winfo_viewable():
                return
            p = ui_theme.active_palette()
            note = tk.Toplevel(self)
            note.wm_overrideredirect(True)
            note.attributes("-topmost", True)
            label = tk.Label(
                note,
                text=text,
                background=p["PANEL2"],
                foreground=p["FG"],
                highlightthickness=1,
                highlightbackground=p["BORDER"],
                highlightcolor=p["BORDER"],
                font=ui_tokens.font("body"),
                padx=12,
                pady=8,
                justify="left",
                wraplength=380,
            )
            label.pack()
            shown = [
                n for n in getattr(self, "_notice_windows", []) if n.winfo_exists()
            ]
            note.update_idletasks()
            x = self.winfo_rootx() + self.winfo_width() - note.winfo_reqwidth() - 16
            y = (
                self.winfo_rooty()
                + self.winfo_height()
                - 16
                - sum(n.winfo_height() + 8 for n in shown)
                - note.winfo_reqheight()
            )
            note.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
            self._notice_windows = shown + [note]
            for widget in (note, label):
                widget.bind("<Button-1>", lambda _e: note.destroy())
            note.after(int(seconds * 1000), note.destroy)
        except tk.TclError:
            pass

    @staticmethod
    def _training_ended_text(coin: str, code, gate: Optional[dict] = None) -> str:
        """The notice for a training run that ended with exit code ``code``; ``gate``
        is its model_gate.json record, when it wrote one."""
        if code == 0:
            if not gate or not isinstance(gate.get("gate"), dict):
                return f"{coin}: training finished; its new model is saved."
            import entry_gate

            decision = entry_gate.Decision.from_dict(gate["gate"])
            figures = f"{decision.figure_name()} vs random: " + (
                decision.short() or "no entries"
            )
            if gate.get("published"):
                return (
                    f"{coin}: training finished; its new model passed the entry gate "
                    f"({figures}) and is in use."
                )
            kept = (
                "the model in use is kept."
                if gate.get("kept_model_id")
                else f"{coin} has no model in use until one passes."
            )
            return (
                f"{coin}: training finished, but the new model did not pass the entry "
                f"gate ({figures}); {kept}"
            )
        return (
            f"{coin}: training ended without a model (exit code {code}); the "
            f"Neural Runner gives {coin} no signals until it is trained."
        )

    def _coin_is_trained(self, coin: str) -> bool:
        coin = coin.upper().strip()

        # First check in-memory training times (updated when training completes)
        if coin in self.last_training_times:
            ts = self.last_training_times[coin]
            if ts > 0 and (time.time() - ts) <= (14 * 24 * 60 * 60):
                return True

        # Fall back to checking timestamp files
        folder = self.coin_folders.get(coin, "")
        if not folder or not os.path.isdir(folder):
            return False

        # A coin whose trainer is still running is not "trained" yet (a killed
        # trainer's TRAINING does not count: trainer_status).
        if trainer_status.training_in(folder):
            return False

        stamp_path = os.path.join(folder, "trainer_last_training_time.txt")
        try:
            if not os.path.isfile(stamp_path):
                return False
            with open(stamp_path, "r", encoding="utf-8") as f:
                raw = (f.read() or "").strip()
            ts = float(raw) if raw else 0.0
            if ts <= 0:
                return False

            # Update last_training_times for future checks
            if (time.time() - ts) <= (14 * 24 * 60 * 60):
                self.last_training_times[coin] = ts
                return True
            return False
        except Exception:
            return False

    def _running_trainers(self) -> List[str]:
        running: List[str] = []

        # Trainers launched by this GUI instance
        for c, lp in self.trainers.items():
            try:
                if lp.info.proc and lp.info.proc.poll() is None:
                    running.append(c)
            except Exception:
                pass

        # Trainers launched elsewhere: look at per-coin status file
        for c in self.coins:
            try:
                coin = (c or "").strip().upper()
                folder = self.coin_folders.get(coin, "")
                if not folder or not os.path.isdir(folder):
                    continue

                status_path = os.path.join(folder, trainer_status.FILE_NAME)
                st = _safe_read_json(status_path)

                if trainer_status.is_training(st):
                    stamp_path = os.path.join(folder, "trainer_last_training_time.txt")

                    try:
                        if os.path.isfile(stamp_path) and os.path.isfile(status_path):
                            if os.path.getmtime(stamp_path) >= os.path.getmtime(
                                status_path
                            ):
                                continue
                    except Exception:
                        pass

                    running.append(coin)
            except Exception:
                pass

        # de-dupe while preserving order
        out: List[str] = []
        seen = set()
        for c in running:
            cc = (c or "").strip().upper()
            if cc and cc not in seen:
                seen.add(cc)
                out.append(cc)
        return out

    def _training_status_map(self) -> Dict[str, str]:
        """
        Returns {coin: "✅" | "●" (blinking) | "❌"}.
        """
        import time

        running = set(self._running_trainers())
        out: Dict[str, str] = {}

        # Blinking effect for training status (alternates every 0.8 seconds)
        blink_state = int(time.time() / 0.8) % 2
        training_symbol = "●" if blink_state else "○"

        for c in self.coins:
            if c in running:
                out[c] = training_symbol
            elif self._coin_is_trained(c):
                out[c] = "✅"
            else:
                out[c] = "❌"
        return out

    # ---- the entry gate (pt_pattern_trainer deviation 13, entry_gate) ----

    def _gate_record(self, coin: str) -> Optional[dict]:
        """The coin's latest training run's gate decision (``model_gate.json`` in its
        folder), or None."""
        folder = self.coin_folders.get(coin, "")
        if not folder:
            return None
        data = _safe_read_json(os.path.join(folder, GATE_FILE))
        return data if isinstance(data, dict) and data.get("coin") == coin else None

    def run_gate_check(self, coin: str) -> dict:
        """``pt_pattern_trainer.py COIN --check-gate`` (off the Tk thread): the entry
        gate on the coin's model in use. Returns its exit code, its record
        (``<coin>_gate_check.json``, None when it wrote none) and its last lines."""
        record_path = pt_paths.data_file(
            "training_results", f"{coin.lower()}_gate_check.json"
        )
        started = time.time()
        folder = (
            self.coin_folders.get(coin)
            or build_coin_folders(self.settings["main_neural_dir"], [coin])[coin]
        )
        os.makedirs(folder, exist_ok=True)
        env = _child_env(self.hub_dir)
        env["PYTHONIOENCODING"] = "utf-8"
        done = subprocess.run(
            [
                sys.executable,
                "-u",
                "-W",
                "ignore",
                self.proc_trainer_path,
                coin,
                "--check-gate",
            ],
            cwd=folder,
            env=env,
            capture_output=True,
            text=True,
            timeout=GATE_CHECK_TIMEOUT_S,
        )
        record = _safe_read_json(record_path)
        if not isinstance(record, dict) or record.get("checked_at", 0) < int(started):
            record = None
        output = (done.stdout or "") + (done.stderr or "")
        return {
            "code": done.returncode,
            "record": record,
            "output": "\n".join(output.splitlines()[-20:]),
        }

    def check_models_against_gate(self, parent=None) -> None:
        """Settings > Training, "Check the models in use...": gate_check_ui's window,
        one at a time."""
        from gate_check_ui import GateCheckWindow

        win = getattr(self, "_gate_check_window", None)
        try:
            if win is not None and win.winfo_exists():
                win.lift()
                return
        except tk.TclError:
            pass
        coins = [c for c in (self.coins or []) if c]
        if not coins:
            messagebox.showinfo(
                "Check the models in use",
                "There are no coins in Settings.",
                parent=parent,
            )
            return
        self._gate_check_window = GateCheckWindow(self, coins, self.run_gate_check)

    def train_selected_coin(self) -> None:
        print(f"DEBUG: train_selected_coin() called")
        coin = (
            (getattr(self, "train_coin_var", self.trainer_coin_var).get() or "")
            .strip()
            .upper()
        )
        print(f"DEBUG: Selected coin for training: '{coin}'")

        if not coin:
            print(f"DEBUG: No coin selected, returning")
            return

        # Synchronize trainer_coin_var with the selected coin to ensure consistency
        self.trainer_coin_var.set(coin)
        print(
            f"DEBUG: trainer_coin_var synchronized to: '{self.trainer_coin_var.get()}'"
        )

        # Reuse the trainers pane runner — start trainer for selected coin
        print(f"DEBUG: About to call start_trainer_for_selected_coin()")
        self.start_trainer_for_selected_coin()
        print(f"DEBUG: start_trainer_for_selected_coin() completed")

    def train_all_coins(self) -> None:
        if not self._trainer_launch_allowed("all coins"):
            return  # one refusal message, not one per coin
        trained = [c for c in self.coins if self._coin_is_trained(c)]
        if trained and not messagebox.askyesno(
            "Train all coins?",
            f"Train all {len(self.coins)} coins now?\n\n"
            f"This deletes the current models of {', '.join(trained)}. The runner "
            "skips each coin until its new model is saved.",
            parent=self,
        ):
            return
        # Start trainers for every coin (in parallel)
        print(f"DEBUG: Starting training for coins: {self.coins}")
        for c in self.coins:
            print(f"DEBUG: Training coin: {c}")
            self.trainer_coin_var.set(c)
            self.start_trainer_for_selected_coin()

    def stop_all_trainers(self) -> None:
        """Stop all running trainer processes."""
        print(f"DEBUG: Stopping all trainer processes")
        stopped_count = 0

        for coin, lp in list(self.trainers.items()):
            try:
                if lp and lp.info.proc and lp.info.proc.poll() is None:
                    print(
                        f"DEBUG: Stopping trainer for {coin} (PID: {lp.info.proc.pid})"
                    )
                    self._note_stop_requested(lp.info.proc)
                    lp.info.proc.terminate()
                    stopped_count += 1
                    # Give it a moment to terminate gracefully
                    try:
                        lp.info.proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate gracefully
                        print(f"DEBUG: Force killing trainer for {coin}")
                        lp.info.proc.kill()
                else:
                    print(f"DEBUG: Trainer for {coin} already stopped")
            except Exception as e:
                print(f"DEBUG: Error stopping trainer for {coin}: {e}")
            self._mark_training_ended(coin, self._exit_code(lp))

        # Clear the trainers dictionary
        self.trainers.clear()

        if stopped_count > 0:
            print(f"DEBUG: Stopped {stopped_count} trainer processes")
            try:
                self.status.config(text=f"Stopped {stopped_count} trainer(s)")
            except Exception:
                pass
        else:
            print(f"DEBUG: No trainers were running")
            try:
                self.status.config(text="No trainers were running")
            except Exception:
                pass

    def stop_selected_trainer(self) -> None:
        """Stop the currently selected trainer process."""
        coin = (self.trainer_coin_var.get() or "").strip().upper()
        print(f"DEBUG: Stopping selected trainer: {coin}")

        if not coin:
            print(f"DEBUG: No coin selected for stopping")
            try:
                self.status.config(text="No coin selected")
            except Exception:
                pass
            return

        if coin not in self.trainers:
            print(f"DEBUG: No trainer running for {coin}")
            try:
                self.status.config(text=f"No trainer running for {coin}")
            except Exception:
                pass
            return

        lp = self.trainers[coin]
        try:
            if lp and lp.info.proc and lp.info.proc.poll() is None:
                print(f"DEBUG: Stopping trainer for {coin} (PID: {lp.info.proc.pid})")
                self._note_stop_requested(lp.info.proc)
                lp.info.proc.terminate()
                # Give it a moment to terminate gracefully
                try:
                    lp.info.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    print(f"DEBUG: Force killing trainer for {coin}")
                    lp.info.proc.kill()

                self._mark_training_ended(coin, self._exit_code(lp))
                # Remove from trainers dictionary
                del self.trainers[coin]

                print(f"DEBUG: Stopped trainer for {coin}")
                try:
                    self.status.config(text=f"Stopped trainer for {coin}")
                except Exception:
                    pass
            else:
                print(f"DEBUG: Trainer for {coin} not running")
                try:
                    self.status.config(text=f"Trainer for {coin} not running")
                except Exception:
                    pass
        except Exception as e:
            print(f"DEBUG: Error stopping trainer for {coin}: {e}")
            try:
                self.status.config(text=f"Error stopping {coin}: {e}")
            except Exception:
                pass

    def _mock_trainer_refused(self) -> bool:
        """True if the configured trainer script is marked MOCK and pt_config.json
        does not set ``allow_mock_trainer`` to true (read again on every call)."""
        return (
            trainer_guard.is_mock_trainer(self.proc_trainer_path)
            and not trainer_guard.read_allow_mock_trainer()
        )

    def _trainer_launch_allowed(self, coin: str) -> bool:
        """False (after telling the user) if the configured trainer is a refused mock."""
        if not self._mock_trainer_refused():
            return True
        messagebox.showerror(
            "Mock trainer refused",
            trainer_guard.refusal_message(self.proc_trainer_path),
        )
        try:
            self.status.config(text=f"Training refused for {coin}: mock trainer")
        except Exception:
            pass
        return False

    def start_trainer_for_selected_coin(self) -> None:
        print(f"DEBUG: start_trainer_for_selected_coin() called")
        coin = (self.trainer_coin_var.get() or "").strip().upper()
        print(f"DEBUG: trainer_coin_var contains: '{coin}'")
        if not coin:
            print(f"DEBUG: No coin in trainer_coin_var, returning")
            return

        # Only a coin in the coin list trains. Any other has no folder of its own and
        # would fall back to the root, which is BTC's folder: its files would be
        # deleted and BTC's model replaced (#146).
        if coin not in (self.coins or []):
            print(f"DEBUG: {coin} is not in the coin list: not trained")
            try:
                self.status.config(
                    text=f"Training refused for {coin}: it is not in Coins in Settings"
                )
            except Exception:
                pass
            return

        # A mock trainer is refused before anything is deleted (FDS-MDL).
        if not self._trainer_launch_allowed(coin):
            return

        # The Neural Runner keeps running: removing the coin's training stamp
        # (below) makes it skip this coin until the new model is complete.

        # --- IMPORTANT ---
        # Match the trader's folder convention:
        #   BTC runs from the main neural folder
        #   Alts run from their own coin subfolder
        coin_cwd = (
            self.coin_folders.get(coin)
            or build_coin_folders(self.settings["main_neural_dir"], [coin])[coin]
        )
        os.makedirs(coin_cwd, exist_ok=True)

        # The trainer runs from the (read-only) program folder with the coin's
        # neural folder as its working directory, so its outputs land there.
        # proc_trainer_path follows the Settings (see _refresh_trainer_path).
        trainer_path = self.proc_trainer_path
        print(f"DEBUG: Looking for trainer at: {trainer_path}")

        if not os.path.isfile(trainer_path):
            print(f"DEBUG: Trainer not found at {trainer_path}")
            messagebox.showerror(
                "Missing trainer", f"Cannot find trainer for {coin} at:\n{trainer_path}"
            )
            return

        print(f"DEBUG: Trainer found, proceeding with launch")

        if (
            coin in self.trainers
            and self.trainers[coin].info.proc
            and self.trainers[coin].info.proc.poll() is None
        ):
            return

        try:
            patterns = [
                "trainer_last_training_time.txt",
                "trainer_status.json",
                "trainer_last_start_time.txt",
                GATE_FILE,
                "killer.txt",
                "memories_*.txt",
                "memory_weights_*.txt",
                "neural_perfect_threshold_*.txt",
            ]

            deleted = 0
            deadline = time.time() + 1.0
            for pat in patterns:
                for fp in glob.glob(os.path.join(coin_cwd, pat)):
                    while True:
                        try:
                            os.remove(fp)
                            deleted += 1
                            break
                        except FileNotFoundError:
                            break
                        except OSError as exc:
                            # 32: open in another process (e.g. the runner reading it)
                            if getattr(exc, "winerror", None) != 32:
                                break
                            if time.time() >= deadline:
                                break
                            time.sleep(0.05)
            # the coin is untrained until the new run finishes, here as in the runner
            getattr(self, "last_training_times", {}).pop(coin, None)

            if deleted:
                try:
                    self.status.config(
                        text=f"Deleted {deleted} training file(s) for {coin} before training"
                    )
                except Exception:
                    pass
        except Exception:
            pass

        q: "queue.Queue[str]" = queue.Queue()
        info = ProcInfo(name=f"Trainer-{coin}", path=trainer_path)

        env = _child_env(self.hub_dir)
        # Force unbuffered output for Python subprocess
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            # IMPORTANT: pass `coin` so neural_trainer trains the correct market instead of defaulting to BTC
            # Add -u flag to force unbuffered output and -W ignore to suppress warnings
            cmd_args = [sys.executable, "-u", "-W", "ignore", info.path, coin]
            print(f"DEBUG: Command args: {cmd_args}")
            print(f"DEBUG: Working directory: {coin_cwd}")
            print(
                f"DEBUG: Environment POWERTRADER_HUB_DIR: {env.get('POWERTRADER_HUB_DIR')}"
            )
            info.proc = subprocess.Popen(
                cmd_args,
                cwd=coin_cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            print(f"DEBUG: Process started with PID: {info.proc.pid}")
            # A trainer that stops at once (e.g. exit 2: its folder still holds
            # model files) is kept too, so its output and exit code reach the log.

            t = threading.Thread(
                target=self._reader_thread,
                args=(info.proc, q, f"[{coin}] "),
                daemon=True,
            )
            t.start()

            self.trainers[coin] = LogProc(
                info=info, log_q=q, thread=t, is_trainer=True, coin=coin
            )
            if self.proc_neural.proc and self.proc_neural.proc.poll() is None:
                self.runner_log_q.put(
                    f"[RUNNER] [training {coin}: the runner skips {coin} until "
                    "its new model is saved]"
                )

            # Add periodic monitoring to see when process exits
            self.after(1000, lambda c=coin: self._monitor_trainer_process(c))
        except Exception as e:
            messagebox.showerror(
                "Failed to start", f"Trainer for {coin} failed to start:\n{e}"
            )

    @staticmethod
    def _exit_code(lp):
        """A stopped trainer's exit code, once it has ended (None if unknown)."""
        try:
            return lp.info.proc.wait(timeout=2)
        except Exception:
            return None

    def _mark_training_ended(self, coin: str, code) -> None:
        """A stopped or crashed trainer can leave trainer_status.json at TRAINING;
        record how it ended so neither the hub nor the runner waits on it."""
        path = os.path.join(self.coin_folders.get(coin, ""), "trainer_status.json")
        try:
            st = _safe_read_json(path)
            if isinstance(st, dict) and str(st.get("state", "")).upper() == "TRAINING":
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "state": "STOPPED",
                            "exit_code": code,
                            "timestamp": time.time(),
                        },
                        f,
                    )
        except Exception:
            pass

    def _monitor_trainer_process(self, coin: str) -> None:
        """Monitor a specific trainer process and log when it exits"""
        try:
            if coin in self.trainers:
                proc = self.trainers[coin].info.proc
                if proc and proc.poll() is not None:
                    print(
                        f"DEBUG: Trainer process for {coin} exited with code: {proc.returncode}"
                    )

                    # Save training completion time for auto-retrain tracking
                    if proc.returncode == 0:  # Successful completion
                        current_time = time.time()
                        self.last_training_times[coin] = current_time
                        print(
                            f"DEBUG: Training completed successfully for {coin}, scheduling auto-retrain"
                        )
                        # Schedule auto-retrain if enabled
                        self._schedule_auto_retrain(coin)
                    else:
                        self._mark_training_ended(coin, proc.returncode)
                    if self.settings.get("training_notifications", True):
                        self._show_notice(
                            self._training_ended_text(
                                coin, proc.returncode, self._gate_record(coin)
                            )
                        )

                    # Try to get any remaining output
                    try:
                        remaining_output = proc.stdout.read() if proc.stdout else ""
                        if remaining_output:
                            print(
                                f"DEBUG: Final output from {coin}: {remaining_output}"
                            )
                    except (OSError, AttributeError):
                        pass
                else:
                    # Process still running, check again in 2 seconds
                    print(
                        f"DEBUG: Trainer {coin} still running (PID: {proc.pid if proc else 'None'})"
                    )
                    self.after(2000, lambda: self._monitor_trainer_process(coin))
        except Exception as e:
            print(f"DEBUG: Error monitoring {coin}: {e}")

    def _auto_retrain_hours(self) -> float:
        """Hours between a coin's successful training and its retrain; 0 means off."""
        if not self.settings.get("training_auto_enabled", True):
            return 0.0
        try:
            hours = float(self.settings.get("training_auto_interval_hours", 6))
        except (TypeError, ValueError):
            return 0.0
        return hours if math.isfinite(hours) and hours > 0 else 0.0

    def _schedule_auto_retrain(self, coin: str, due: Optional[float] = None) -> None:
        """Schedule automatic re-training for a coin after the configured interval,
        or at ``due`` (epoch seconds; one already past fires in a minute)."""
        interval_hours = self._auto_retrain_hours()
        if not interval_hours:
            return

        # Get the Tk root widget for scheduling
        try:
            root_widget = self.master or self.winfo_toplevel()
            if not root_widget:
                print(f"DEBUG: Cannot schedule auto-retrain for {coin}: no root widget")
                return
        except Exception:
            print(f"DEBUG: Cannot schedule auto-retrain for {coin}: widget error")
            return

        self._cancel_auto_retrain(coin)  # an earlier timer for this coin

        now = time.time()
        if due is None:
            due = now + interval_hours * 3600
        due = max(float(due), now + OVERDUE_RETRAIN_DELAY_S)
        interval_ms = int((due - now) * 1000)

        def auto_retrain():
            try:
                if coin not in (self.coins or []):  # removed from the coin list
                    print(
                        f"DEBUG: Auto-retrain for {coin} skipped: not in the coin list"
                    )
                    return
                print(f"DEBUG: Auto-retraining {coin} after {interval_hours} hours")
                if self._mock_trainer_refused():
                    # Unattended: no dialog (the next manual launch shows it).
                    print(
                        f"DEBUG: Auto-retrain for {coin} skipped: mock trainer refused"
                    )
                    try:
                        self.status.config(
                            text=f"Auto-retrain skipped for {coin}: mock trainer refused"
                        )
                    except Exception:
                        pass
                    return
                previous = self.trainers.get(coin)
                self.trainer_coin_var.set(coin)
                self.start_trainer_for_selected_coin()
                lp = self.trainers.get(coin)
                if lp is None or lp is previous:
                    # nothing new was started (missing script, a process that died at
                    # once, or a trainer already running): keep the status it left
                    return
                # Update status to show it's an automatic retrain
                try:
                    self.status.config(text=f"Auto-retraining {coin} (stale data)")
                except Exception:
                    pass
            except Exception as e:
                print(f"ERROR: Auto-retrain failed for {coin}: {e}")
            finally:
                # Remove from timers dict when done
                if coin in self.auto_retrain_timers:
                    del self.auto_retrain_timers[coin]
                self.auto_retrain_due.pop(coin, None)

        timer_id = root_widget.after(interval_ms, auto_retrain)
        self.auto_retrain_timers[coin] = timer_id
        self.auto_retrain_due[coin] = due

        print(f"DEBUG: Scheduled auto-retrain for {coin} at {_clock(due)}")

    def _resume_auto_retrains(self) -> None:
        """Each trained coin's retrain falls due its interval after its model was
        saved, so the schedule survives a restart; an overdue coin retrains in a
        minute. Run at start-up and after Settings change the interval."""
        hours = self._auto_retrain_hours()
        if not hours:
            self.cancel_all_auto_retrains()
            return
        for coin in list(self.coins or []):
            ts = (self.last_training_times or {}).get(coin)
            if ts and not self._is_trainer_running(coin):
                self._schedule_auto_retrain(coin, due=float(ts) + hours * 3600)

    def _trainer_status_text(self, running: List[str]) -> str:
        """The Training tab's line: the trainers running, then the next retrain."""
        waiting = sorted(
            (due, coin)
            for coin, due in (getattr(self, "auto_retrain_due", None) or {}).items()
            if coin not in running
        )
        parts = []
        if running:
            parts.append(f"running: {', '.join(running)}")
        if waiting:
            due, coin = waiting[0]
            more = f", +{len(waiting) - 1} more" if len(waiting) > 1 else ""
            if running:
                parts.append(f"next: {coin} at {_clock(due)}{more}")
            else:
                parts.append(f"idle until {_clock(due)} (next: {coin}{more})")
        if parts:
            return " · ".join(parts)
        if not self._auto_retrain_hours():
            return "(no trainers running; auto-retrain off)"
        return "(no trainers running)"

    def _build_training_table(self) -> None:
        """One cell per coin: status dot, symbol and trained-for. Clicking a cell
        trains the coin, or stops it while it trains (both ask first)."""
        p = ui_theme.active_palette()
        frame = self.training_status_frame
        for widget in frame.winfo_children():
            widget.destroy()
        bg = p["BG"]  # the frames' colour
        self._training_cells = {}
        self._training_cell_state: Dict[str, Tuple[str, str, str]] = {}
        for coin in self.coins or []:
            cell = tk.Frame(frame, bg=bg, cursor="hand2")
            tight = {"bg": bg, "bd": 0, "padx": 0, "pady": 0}
            dot = tk.Label(
                cell, text="●", fg=p["MUTED"], font=ui_tokens.font("small"), **tight
            )
            sym = tk.Label(
                cell,
                text=coin,
                fg=p["FG"],
                font=ui_tokens.font("caption", "bold"),
                width=5,
                anchor="w",
                **tight,
            )
            age = tk.Label(
                cell,
                text="",
                fg=p["MUTED"],
                font=ui_tokens.font("micro"),
                width=7,
                anchor="w",
                **tight,
            )
            sig = tk.Label(
                cell,
                text="–",
                fg=p["MUTED"],
                font=ui_tokens.font("micro", "bold"),
                width=6,
                anchor="w",
                **tight,
            )
            dot.pack(side="left")
            sym.pack(side="left", padx=2)
            age.pack(side="left")
            sig.pack(side="left")
            handler = self._make_coin_click_handler(coin)

            def _open_chart(_e=None, c=coin):
                fn = getattr(self, "_show_chart_page", None)
                if callable(fn):
                    fn(c)

            for widget in (cell, dot, sym, age, sig):
                widget.bind("<Button-1>", handler)
                widget.bind("<Button-3>", _open_chart)
            ToolTip(dot, lambda c=coin: self._coin_tooltip(c, "status"))
            ToolTip(sym, lambda c=coin: self._coin_tooltip(c, "coin"))
            ToolTip(age, lambda c=coin: self._coin_tooltip(c, "age"))
            ToolTip(sig, lambda c=coin: self._coin_tooltip(c, "signal"))
            self._training_cells[coin] = (cell, dot, sym, age, sig)
        self._training_signal_state: Dict[str, Tuple[str, str]] = {}
        self._training_status: Dict[str, str] = {}
        self._training_signal_info: Dict[str, Tuple[Any, ...]] = {}
        self._training_table_coins = tuple(self.coins or [])
        self._training_table_cols = 0
        self._layout_training_table()

    def _layout_training_table(self) -> None:
        """Arrange the cells in as many columns as fit, filled top to bottom."""
        cells = getattr(self, "_training_cells", None) or {}
        if not cells:
            return
        width = self.training_status_frame.winfo_width()
        if width <= 1:
            width = 300
        gap = 8  # between columns; none after the last, so three fit at 394 px
        try:
            cell_w = max(c[0].winfo_reqwidth() for c in cells.values())
        except Exception:
            cell_w = 0
        if cell_w <= 1:  # not measured yet
            cell_w = 140
        cols = max(1, min(len(cells), (width + gap) // (cell_w + gap)))
        if cols != getattr(self, "_training_table_cols", 0):
            self._training_table_cols = cols
            rows = -(-len(cells) // cols)
            last = (len(cells) - 1) // rows
            for i, coin in enumerate(self._training_table_coins):
                cells[coin][0].grid(
                    row=i % rows,
                    column=i // rows,
                    sticky="w",
                    padx=(0, gap if i // rows < last else 0),
                    pady=1,
                )
        # the table's final height is known once its width is: fit the split again
        fit = getattr(self, "_fit_left_split", None)
        if fit:
            fit()

    def _update_training_table(self, status_map: Dict[str, str]) -> None:
        """Refresh each cell's dot colour and trained-for text; only changed
        widgets are touched."""
        if tuple(self.coins or []) != getattr(self, "_training_table_coins", None):
            self._build_training_table()
        statuses = getattr(self, "_training_status", None)
        if statuses is None:
            statuses = self._training_status = {}
        for coin, (cell, dot, sym, age, sig) in self._training_cells.items():
            status = status_map.get(coin, "❌")
            training = status in ("●", "○")
            state = (
                status if training else "●",
                self._get_status_border_color(status, coin),
                "training" if training else self._get_training_hours(coin),
            )
            statuses[coin] = status  # for the cell's tooltips
            if self._training_cell_state.get(coin) == state:
                continue
            self._training_cell_state[coin] = state
            dot.configure(text=state[0], fg=state[1])
            age.configure(text=state[2])

    def _get_status_border_color(self, status: str, coin: str = None) -> str:
        """Status colour of a coin: trained green, training amber, untrained grey."""
        p = ui_theme.active_palette()
        if status in ("✅", "✓"):  # _training_status_map marks trained coins ✅
            return STATUS_GREEN
        if status in ("●", "○"):
            return STATUS_AMBER
        return p["MUTED"]

    def _is_recently_trained(self, coin: str, hours_threshold: float = 2.0) -> bool:
        """Check if coin was trained within the threshold hours"""
        try:
            if coin in self.last_training_times:
                hours_elapsed = (time.time() - self.last_training_times[coin]) / 3600
                return hours_elapsed <= hours_threshold
            return False
        except Exception:
            return False

    def _get_training_hours(self, coin: str) -> str:
        """Get training age in hours for display"""
        try:
            if self.settings.get("training_age_indicators", True):
                _, age_text = self._get_training_age_status(coin)
                return age_text
            else:
                # Get hours since last training
                if coin in self.last_training_times:
                    hours = (time.time() - self.last_training_times[coin]) / 3600
                    if hours < 1:
                        return "<1h"
                    elif hours < 24:
                        return f"{int(hours)}h"
                    else:
                        days = int(hours / 24)
                        return f"{days}d"
                return "N/A"
        except Exception:
            return "N/A"

    def _make_coin_click_handler(self, coin_name: str):
        """Create click handler for coin training"""

        def on_coin_click(event=None):
            try:
                print(f"DEBUG: Coin clicked: {coin_name}")

                # Check if trainer is currently running for this coin
                is_running = self._is_trainer_running(coin_name)

                if is_running:
                    if not messagebox.askyesno(
                        f"Stop training {coin_name}?",
                        f"{coin_name} is training. Stop it now?\n\n"
                        f"{coin_name} stays untrained until it is trained again.",
                        parent=self,
                    ):
                        return
                    # Stop training if running
                    print(f"DEBUG: Stopping training for {coin_name}")
                    self.trainer_coin_var.set(coin_name)
                    self.stop_trainer_for_selected_coin()
                    print(f"DEBUG: Training stopped for {coin_name}")
                else:
                    if not self._trainer_launch_allowed(coin_name):
                        return
                    if self._coin_is_trained(coin_name) and not messagebox.askyesno(
                        f"Retrain {coin_name}?",
                        f"{coin_name} is already trained "
                        f"({self._get_training_hours(coin_name)} ago).\n\n"
                        f"Retraining deletes its current model files. The runner "
                        f"skips {coin_name} until the new model is saved.\n\n"
                        "Retrain now?",
                        parent=self,
                    ):
                        return
                    # Start training if not running
                    print(f"DEBUG: Starting training for {coin_name}")
                    # Set the dropdown to this coin
                    self.train_coin_var.set(coin_name)
                    print(f"DEBUG: train_coin_var set to: {self.train_coin_var.get()}")
                    # Start training for this coin
                    print(f"DEBUG: About to call train_selected_coin()")
                    self.train_selected_coin()
                    print(f"DEBUG: train_selected_coin() completed")
            except Exception as e:
                print(f"ERROR: Exception handling coin click for {coin_name}: {e}")
                import traceback

                traceback.print_exc()
                # Also show error to user
                try:
                    action = (
                        "stopping"
                        if self._is_trainer_running(coin_name)
                        else "starting"
                    )
                    messagebox.showerror(
                        "Training Error",
                        f"Failed {action} training for {coin_name}: {e}",
                    )
                except Exception:
                    pass

        return on_coin_click

    def _is_trainer_running(self, coin: str) -> bool:
        """Check if trainer is currently running for the specified coin"""
        try:
            lp = self.trainers.get(coin)
            return lp and lp.info.proc and lp.info.proc.poll() is None
        except Exception:
            return False

    def _get_training_age_status(self, coin: str) -> tuple:
        """Get training age status (color, text) for a coin."""
        if coin not in self.last_training_times:
            return STATUS_RED, "Never"

        last_time = self.last_training_times[coin]
        current_time = time.time()
        age_hours = (current_time - last_time) / 3600

        stale_warning_hours = self.settings.get("training_stale_warning_hours", 3)
        auto_interval_hours = self.settings.get("training_auto_interval_hours", 6)

        if age_hours < stale_warning_hours:
            return STATUS_GREEN, f"{age_hours:.1f}h"  # fresh
        elif age_hours < auto_interval_hours:
            return STATUS_AMBER, f"{age_hours:.1f}h"  # ageing
        else:
            return STATUS_RED, f"{age_hours:.1f}h"  # stale

    def _load_existing_training_times(self) -> None:
        """Load existing training completion times from timestamp files."""
        import time

        for coin in self.coins:
            folder = self.coin_folders.get(coin, "")
            if not folder or not os.path.isdir(folder):
                continue

            stamp_path = os.path.join(folder, "trainer_last_training_time.txt")
            try:
                if os.path.isfile(stamp_path):
                    with open(stamp_path, "r", encoding="utf-8") as f:
                        raw = (f.read() or "").strip()
                    ts = float(raw) if raw else 0.0
                    if ts > 0 and (time.time() - ts) <= (14 * 24 * 60 * 60):
                        self.last_training_times[coin] = ts
                        print(f"DEBUG: Loaded training time for {coin}: {ts}")
            except Exception as e:
                print(f"DEBUG: Error loading training time for {coin}: {e}")

    def _cancel_auto_retrain(self, coin: str) -> None:
        """Cancel ``coin``'s scheduled auto-retrain, if it has one."""
        self.auto_retrain_due.pop(coin, None)
        timer_id = self.auto_retrain_timers.pop(coin, None)
        if timer_id is None:
            return
        try:
            self.after_cancel(timer_id)  # the hub is the Tk root: no .master
            print(f"DEBUG: Cancelled auto-retrain timer for {coin}")
        except Exception:
            pass

    def cancel_all_auto_retrains(self) -> None:
        """Cancel all scheduled auto-retraining timers."""
        for coin in list(self.auto_retrain_timers):
            self._cancel_auto_retrain(coin)

    def stop_trainer_for_selected_coin(self) -> None:
        coin = (self.trainer_coin_var.get() or "").strip().upper()
        lp = self.trainers.get(coin)
        if not lp or not lp.info.proc or lp.info.proc.poll() is not None:
            return
        try:
            self._note_stop_requested(lp.info.proc)
            lp.info.proc.terminate()
        except Exception:
            pass

    def stop_all_scripts(self) -> None:
        # Cancel any pending "wait for runner then start trader"
        self._auto_start_trader_pending = False

        # Cancel all auto-retrain timers
        self.cancel_all_auto_retrains()

        self.stop_neural(reason="stopped: the hub is closing")
        self.stop_trader(reason="stopped: the hub is closing")

        # Also reset the runner-ready gate file (best-effort)
        try:
            with open(self.runner_ready_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"timestamp": time.time(), "ready": False, "stage": "stopped"}, f
                )
        except Exception:
            pass

    def _on_timeframe_changed(self, event) -> None:
        """
        Immediate redraw when the user changes a timeframe in any CandleChart.
        Avoids waiting for the chart_refresh_seconds throttle in _tick().
        """
        try:
            chart = getattr(event, "widget", None)
            if not isinstance(chart, CandleChart):
                return

            coin = getattr(chart, "coin", None)
            if not coin:
                return

            self.coin_folders = build_coin_folders(
                self.settings["main_neural_dir"], self.coins
            )

            pos = (
                self._last_positions.get(coin, {})
                if isinstance(self._last_positions, dict)
                else {}
            )
            buy_px = pos.get("current_buy_price", None)
            sell_px = pos.get("current_sell_price", None)
            trail_line = pos.get("trail_line", None)
            dca_line_price = pos.get("dca_line_price", None)
            avg_cost_basis = pos.get("avg_cost_basis", None)

            chart.refresh(
                self.coin_folders,
                current_buy_price=buy_px,
                current_sell_price=sell_px,
                trail_line=trail_line,
                dca_line_price=dca_line_price,
                avg_cost_basis=avg_cost_basis,
                trader_running=self._trader_is_running(),
            )

            # Keep the periodic refresh behavior consistent (prevents an immediate full refresh right after this).
            self._last_chart_refresh = time.time()
        except Exception:
            pass

    # ---- refresh loop ----
    def _drain_queue_to_text(
        self, q: "queue.Queue[str]", txt: tk.Text, max_lines: int = 2500
    ) -> None:
        try:
            # follow new lines only at the bottom; a tab never opened is 1 px tall
            # and its yview is meaningless, so it follows too
            follow = txt.winfo_height() <= 1 or txt.yview()[1] >= 0.999
        except Exception:
            follow = True
        try:
            changed = False
            while True:
                line = q.get_nowait()
                tag = _log_line_tag(line)
                txt.insert("end", line + "\n", (tag,) if tag else ())
                changed = True
        except queue.Empty:
            pass
        except Exception:
            pass

        if changed:
            # trim very old lines
            try:
                current = int(txt.index("end-1c").split(".")[0])
                if current > max_lines:
                    txt.delete("1.0", f"{current - max_lines}.0")
            except Exception:
                pass
            if follow:
                txt.see("end")

    def _trader_is_running(self) -> bool:
        """The trader this hub started is alive (the "Trading:" label's rule)."""
        proc = getattr(getattr(self, "proc_trader", None), "proc", None)
        return bool(proc and proc.poll() is None)

    def _tick(self) -> None:
        # process labels
        neural_running = bool(
            self.proc_neural.proc and self.proc_neural.proc.poll() is None
        )
        trader_running = self._trader_is_running()

        self.lbl_neural.config(text=f"{'running' if neural_running else 'stopped'}")
        self.lbl_trader.config(text=f"{'running' if trader_running else 'stopped'}")

        # Update exchange status display (non-blocking check)
        self._update_exchange_status_display()

        # Update trader button states
        try:
            # Show/hide buttons based on trader state
            if trader_running or bool(
                getattr(self, "_auto_start_trader_pending", False)
            ):
                # Trader is running, enable stop button and disable start button
                if hasattr(self, "btn_start_trader"):
                    self.btn_start_trader.config(state="disabled")
                if hasattr(self, "btn_stop_trader"):
                    self.btn_stop_trader.config(state="normal")
            else:
                # Trader is not running, enable start button and disable stop button
                if hasattr(self, "btn_start_trader"):
                    self.btn_start_trader.config(state="normal")
                if hasattr(self, "btn_stop_trader"):
                    self.btn_stop_trader.config(state="disabled")
        except Exception:
            pass

        # Update neural button states
        try:
            # Neural Runner can always be started - remove training gate
            # Show/hide buttons based on neural state only
            if neural_running:
                # Neural is running, enable stop button and disable start button
                if hasattr(self, "btn_start_neural"):
                    self.btn_start_neural.config(state="disabled")
                if hasattr(self, "btn_stop_neural"):
                    self.btn_stop_neural.config(state="normal")
            else:
                # Neural is not running, always enable start button
                if hasattr(self, "btn_start_neural"):
                    self.btn_start_neural.config(state="normal")
                if hasattr(self, "btn_stop_neural"):
                    self.btn_stop_neural.config(state="disabled")
        except Exception:
            pass

        # --- flow gating: Train -> Start All ---
        status_map = self._training_status_map()
        all_trained = (
            all(v == "✅" for v in status_map.values()) if status_map else False
        )

        # Disable Start All until training is done (but always allow it if something is already running/pending,
        # so the user can still stop everything).
        can_toggle_all = True
        if (
            (not all_trained)
            and (not neural_running)
            and (not trader_running)
            and (not self._auto_start_trader_pending)
        ):
            can_toggle_all = False

        try:
            # Apply training gate to trader start button only
            if hasattr(self, "btn_start_trader"):
                if can_toggle_all:
                    # Regular state logic (handled above) applies
                    pass
                else:
                    # Force disabled due to training requirement
                    self.btn_start_trader.configure(state="disabled")
        except Exception:
            pass

        # Training overview + per-coin grid
        try:
            training_running = [c for c, s in status_map.items() if s in ["●", "○"]]
            not_trained = [c for c, s in status_map.items() if s == "❌"]

            # Update training status counter
            try:
                total_coins = len(self.coins) if self.coins else 0
                running_count = len(training_running)
                self.training_status_label.config(
                    text=f"{running_count}/{total_coins} running"
                )
            except Exception:
                pass

            # each coin's status dot and trained-for text (updated in place)
            self._update_training_table(status_map)
        except Exception as e:
            print(f"Error updating training status: {e}")
            pass

        # neural overview bars (mtime-cached inside)
        self._refresh_neural_overview()

        # trader status -> current trades table (now mtime-cached inside)
        self._refresh_trader_status()
        self._refresh_price_note()
        self._refresh_signals_note()
        self._refresh_halt_banner()

        # pnl ledger -> realized profit (now mtime-cached inside)
        self._refresh_pnl()

        # trade history (now mtime-cached inside)
        self._refresh_trade_history()

        # charts (throttle)
        now = time.time()
        if (now - self._last_chart_refresh) >= float(
            self.settings.get("chart_refresh_seconds", 10.0)
        ):
            # account value chart (internally mtime-cached already)
            try:
                if self.account_chart:
                    self.account_chart.refresh()
            except Exception:
                pass

            # Only rebuild coin_folders when inputs change (avoids directory scans every refresh)
            try:
                cf_sig = (self.settings.get("main_neural_dir"), tuple(self.coins))
                if getattr(self, "_coin_folders_sig", None) != cf_sig:
                    self._coin_folders_sig = cf_sig
                    self.coin_folders = build_coin_folders(
                        self.settings["main_neural_dir"], self.coins
                    )
            except Exception:
                try:
                    self.coin_folders = build_coin_folders(
                        self.settings["main_neural_dir"], self.coins
                    )
                except Exception:
                    pass

            # Refresh ONLY the currently visible coin tab (prevents O(N_coins) network/plot stalls)
            selected_tab = None

            # Primary: our custom chart pages (multi-row tab buttons)
            try:
                selected_tab = getattr(self, "_current_chart_page", None)
            except Exception:
                selected_tab = None

            # Fallback: old notebook-based UI (if it exists)
            if not selected_tab:
                try:
                    if hasattr(self, "nb") and self.nb:
                        selected_tab = self.nb.tab(self.nb.select(), "text")
                except Exception:
                    selected_tab = None

            if selected_tab and str(selected_tab).strip().upper() != "ACCOUNT":
                coin = str(selected_tab).strip().upper()
                chart = self.charts.get(coin)
                if chart:
                    pos = (
                        self._last_positions.get(coin, {})
                        if isinstance(self._last_positions, dict)
                        else {}
                    )
                    buy_px = pos.get("current_buy_price", None)
                    sell_px = pos.get("current_sell_price", None)
                    trail_line = pos.get("trail_line", None)
                    dca_line_price = pos.get("dca_line_price", None)
                    avg_cost_basis = pos.get("avg_cost_basis", None)

                    try:
                        chart.refresh(
                            self.coin_folders,
                            current_buy_price=buy_px,
                            current_sell_price=sell_px,
                            trail_line=trail_line,
                            dca_line_price=dca_line_price,
                            avg_cost_basis=avg_cost_basis,
                            trader_running=self._trader_is_running(),
                        )
                    except Exception:
                        pass

            self._last_chart_refresh = now

        # drain logs into panes
        self._drain_queue_to_text(self.runner_log_q, self.runner_text)
        self._drain_queue_to_text(self.trader_log_q, self.trader_text)

        # trainer logs: show selected trainer output
        try:
            sel = (self.trainer_coin_var.get() or "").strip().upper()
            running = [
                c
                for c, lp in self.trainers.items()
                if lp.info.proc and lp.info.proc.poll() is None
            ]
            self.trainer_status_lbl.config(text=self._trainer_status_text(running))

            lp = self.trainers.get(sel)
            if lp:
                self._drain_queue_to_text(lp.log_q, self.trainer_text)
        except Exception:
            pass

        self.status.config(text=f"{_now_str()} | hub_dir={self.hub_dir}")
        self.after(
            int(float(self.settings.get("ui_refresh_seconds", 1.0)) * 1000), self._tick
        )

    def _refresh_signals_note(self) -> None:
        """Strip text for the signal source: the legacy neural trainer is a mock, so it
        must never look like a real model. Re-read only when pt_config.json changes."""
        indicator = getattr(self, "_mode_indicator", None)
        if indicator is None:
            return
        try:
            path = pt_paths.settings_file()
            mtime = os.path.getmtime(path) if os.path.exists(path) else None
        except OSError:
            mtime = None
        if mtime != getattr(self, "_signals_note_mtime", object()):
            self._signals_note_mtime = mtime
            try:
                strategy = read_strategy_settings()
                self._signals_note_text = strategy.note
                self._signals_engine = str(strategy.engine or "")
            except Exception:
                self._signals_note_text = "SIGNALS: BLOCKED"
        indicator.update_signals_note(self._signals_note_text)

    def _refresh_price_note(self) -> None:
        """Paper mode: show PRICES: LIVE / DEGRADED on the mode strip, from the
        trader's price_integrity status. Only a fresh status counts, so a stopped
        trader never leaves a stale "LIVE" claim on screen."""
        indicator = getattr(self, "_mode_indicator", None)
        if indicator is None or self._trading.is_live:
            return
        try:
            mtime = os.path.getmtime(self.trader_status_path)
        except Exception:
            mtime = None
        if mtime != getattr(self, "_price_note_mtime", object()):
            self._price_note_mtime = mtime
            data = _safe_read_json(self.trader_status_path) if mtime else None
            if not isinstance(data, dict):
                data = {}
            self._price_note_data = data.get("price_integrity")
            self._price_note_ts = data.get("timestamp")
        try:
            fresh = time.time() - float(self._price_note_ts) <= 120.0
        except (TypeError, ValueError):
            fresh = False
        indicator.update_price_integrity(self._price_note_data if fresh else None)

    def _shown_paper_book_path(self) -> Optional[str]:
        """The paper book, when this hub shows the paper trader's books (paper
        mode at start-up); else None."""
        status_dir = os.path.dirname(getattr(self, "trader_status_path", "") or "")
        hub_dir = getattr(self, "hub_dir", None)
        if not hub_dir:
            return None
        paper_dir = os.path.join(hub_dir, "paper")
        if os.path.normcase(os.path.abspath(status_dir)) != os.path.normcase(
            os.path.abspath(paper_dir)
        ):
            return None
        return paper_book_path(hub_dir)

    @staticmethod
    def _paper_book_status(book_path: str) -> Optional[dict]:
        """The Account panel's figures from the saved paper book: cash as buying
        power, positions at cost (the book holds no live prices). None when the
        book is missing or unreadable."""
        try:
            book = read_paper_book(book_path)
            if book is None:
                return None
            cash = book.cash_balance
            held = sum(
                (qty * price for qty, price in book.positions.values()), Decimal(0)
            )
        except PaperBookInvalid:
            # the trader loads an invalid-but-parsable book as written
            try:
                with open(book_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                cash = Decimal(state["cash_balance"])
                held = sum(
                    (
                        Decimal(p["quantity"]) * Decimal(p["average_price"])
                        for p in (state.get("positions") or {}).values()
                    ),
                    Decimal(0),
                )
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                AttributeError,
                ArithmeticError,
            ):
                return None
        except PaperBookError:  # unreadable: the trader starts a fresh book
            return None
        total = cash + held
        return {
            "source": "paper_book",
            "account": {
                "total_account_value": float(total),
                "buying_power": float(cash),
                "holdings_sell_value": float(held),
                "holdings_buy_value": float(held),
                "percent_in_trade": float(held / total * 100) if total > 0 else 0.0,
            },
            "positions": {},
        }

    def _refresh_trader_status(self) -> None:
        # mtime cache: rebuilding the whole tree every tick is expensive with many rows
        try:
            mtime = os.path.getmtime(self.trader_status_path)
        except Exception:
            mtime = None
        # The saved paper book counts too: after it is edited (Settings > Paper
        # Account) and until the trader reports again, the panel shows the book.
        book_path = self._shown_paper_book_path()
        try:
            book_mtime = os.path.getmtime(book_path) if book_path else None
        except OSError:
            book_mtime = None

        key = (mtime, book_mtime)
        if getattr(self, "_last_trader_status_mtime", object()) == key:
            return
        self._last_trader_status_mtime = key

        data = _safe_read_json(self.trader_status_path)
        if book_mtime is not None and (mtime is None or book_mtime > mtime):
            book_data = self._paper_book_status(book_path)
            if book_data is not None:
                data = book_data
        if not data:
            self._last_buying_power = None
            # account summary (right-side status area)
            try:
                self.lbl_acct_total_value.config(text="N/A")
                self.lbl_acct_holdings_value.config(text="N/A")
                self.lbl_acct_buying_power.config(text="N/A")
                self.lbl_acct_percent_in_trade.config(text="N/A")

                # DCA affordability
                self.lbl_acct_dca_spread.config(text="N/A")
                self.lbl_acct_dca_single.config(text="N/A")
            except Exception:
                pass
            self._show_profit_figures({})

            # clear tree (once; subsequent ticks are mtime-short-circuited)
            for iid in self.trades_tree.get_children():
                self.trades_tree.delete(iid)
            return

        ts = data.get("timestamp")
        # Note: Timestamp display removed - using main neural status only

        # --- account summary (same info the trader prints above current trades) ---
        acct = data.get("account", {}) or {}
        try:
            total_val = float(acct.get("total_account_value", 0.0) or 0.0)

            self._last_total_account_value = total_val

            from_book = data.get("source") == "paper_book"
            self.lbl_acct_total_value.config(
                text=_fmt_money(acct.get("total_account_value", None))
                + (" (saved paper account)" if from_book else "")
            )
            self.lbl_acct_holdings_value.config(
                text=_fmt_money(acct.get("holdings_sell_value", None))
            )
            self.lbl_acct_buying_power.config(
                text=_fmt_money(acct.get("buying_power", None))
            )
            try:
                self._last_buying_power = float(acct["buying_power"])
            except (KeyError, TypeError, ValueError):
                self._last_buying_power = None

            pit = acct.get("percent_in_trade", None)
            try:
                pit_txt = f"{float(pit):.2f}%"
            except Exception:
                pit_txt = "N/A"
            self.lbl_acct_percent_in_trade.config(text=pit_txt)

            # -------------------------
            # DCA affordability: how many DCA buys fit in a coin's budget and the
            # account, for one coin and for every coin at once (position_sizing)
            # -------------------------
            coins = getattr(self, "coins", None) or []
            n = len(coins)
            spread_levels = 0
            single_levels = 0

            if total_val > 0.0:
                levels = functools.partial(
                    position_sizing.dca_levels_affordable,
                    total_val,
                    float(self.settings.get("start_allocation_pct") or 0.0),
                    float(
                        self.settings.get("max_coin_allocation_pct")
                        or position_sizing.DEFAULT_MAX_COIN_ALLOCATION_PCT
                    ),
                    float(self.settings.get("dca_multiplier", 2.0) or 0.0),
                )
                single_levels = levels(coins=1)
                spread_levels = levels(coins=max(1, n))

            # Show labels + number (one line each)
            self.lbl_acct_dca_spread.config(text=str(spread_levels))
            self.lbl_acct_dca_single.config(text=str(single_levels))

        except Exception:
            pass

        positions = data.get("positions", {}) or {}
        # Defensive type checking - positions should be a dict, not a list
        if isinstance(positions, list):
            positions = {}
        self._last_positions = positions
        self._show_profit_figures(data)

        # --- precompute per-coin DCA count in rolling 24h (and after last SELL for that coin) ---
        dca_24h_by_coin: Dict[str, int] = {}
        try:
            now = time.time()
            window_floor = now - (24 * 3600)

            trades = (
                _read_trade_history_jsonl(self.trade_history_path)
                if self.trade_history_path
                else []
            )

            last_sell_ts: Dict[str, float] = {}
            for tr in trades:
                sym = str(tr.get("symbol", "")).upper().strip()
                base = sym.split("-")[0].strip() if sym else ""
                if not base:
                    continue

                side = str(tr.get("side", "")).lower().strip()
                if side != "sell":
                    continue

                try:
                    tsf = float(tr.get("ts", 0))
                except Exception:
                    continue

                prev = float(last_sell_ts.get(base, 0.0))
                if tsf > prev:
                    last_sell_ts[base] = tsf

            for tr in trades:
                sym = str(tr.get("symbol", "")).upper().strip()
                base = sym.split("-")[0].strip() if sym else ""
                if not base:
                    continue

                side = str(tr.get("side", "")).lower().strip()
                if side != "buy":
                    continue

                tag = str(tr.get("tag") or "").upper().strip()
                if tag != "DCA":
                    continue

                try:
                    tsf = float(tr.get("ts", 0))
                except Exception:
                    continue

                start_ts = max(window_floor, float(last_sell_ts.get(base, 0.0)))
                if tsf >= start_ts:
                    dca_24h_by_coin[base] = int(dca_24h_by_coin.get(base, 0)) + 1
        except Exception:
            dca_24h_by_coin = {}

        # rebuild tree (only when file changes)
        for iid in self.trades_tree.get_children():
            self.trades_tree.delete(iid)

        for sym, pos in positions.items():
            coin = sym
            qty = pos.get("quantity", 0.0)

            # Hide "not in trade" rows (0 qty), but keep them in _last_positions for chart overlays
            try:
                if float(qty) <= 0.0:
                    continue
            except Exception:
                continue

            value = pos.get("value_usd", 0.0)
            avg_cost = pos.get("avg_cost_basis", 0.0)

            buy_price = pos.get("current_buy_price", 0.0)
            buy_pnl = pos.get("gain_loss_pct_buy", 0.0)

            sell_price = pos.get("current_sell_price", 0.0)
            sell_pnl = pos.get("gain_loss_pct_sell", 0.0)

            dca_stages = pos.get("dca_triggered_stages", 0)
            dca_24h = int(dca_24h_by_coin.get(str(coin).upper().strip(), 0))

            # Display + heading reflect the current max DCA setting (hot-reload friendly)
            try:
                max_dca_24h = int(
                    float(
                        self.settings.get(
                            "max_dca_buys_per_24h",
                            DEFAULT_SETTINGS.get("max_dca_buys_per_24h", 2),
                        )
                        or 2
                    )
                )
            except Exception:
                max_dca_24h = int(DEFAULT_SETTINGS.get("max_dca_buys_per_24h", 2) or 2)
            if max_dca_24h < 0:
                max_dca_24h = 0
            try:
                self.trades_tree.heading("dca_24h", text=f"DCA 24h (max {max_dca_24h})")
            except Exception:
                pass
            dca_24h_display = f"{dca_24h}/{max_dca_24h}"

            # Display + heading reflect trailing PM settings (hot-reload friendly)
            try:
                pm0 = float(
                    self.settings.get(
                        "pm_start_pct_no_dca",
                        DEFAULT_SETTINGS.get("pm_start_pct_no_dca", 5.0),
                    )
                    or 5.0
                )
                pm1 = float(
                    self.settings.get(
                        "pm_start_pct_with_dca",
                        DEFAULT_SETTINGS.get("pm_start_pct_with_dca", 2.5),
                    )
                    or 2.5
                )
                tg = float(
                    self.settings.get(
                        "trailing_gap_pct",
                        DEFAULT_SETTINGS.get("trailing_gap_pct", 0.5),
                    )
                    or 0.5
                )
                self.trades_tree.heading(
                    "trail_line",
                    text=f"Trail Line (start {pm0:g}/{pm1:g}%, gap {tg:g}%)",
                )
            except Exception:
                pass

            next_dca = pos.get("next_dca_display", "")

            trail_line = pos.get("trail_line", 0.0)
            trail_cell = _fmt_price(trail_line)  # trail line is a price level

            # Catalogue engine: this column shows the strategy's effective stop (the
            # tightest overlay stop) and which overlay owns it; the heading lists the
            # active overlays. Text only.
            overlay_ids = pos.get("overlays")
            if overlay_ids is not None:
                stop = pos.get("effective_stop")
                owner = pos.get("stop_owner")
                trail_cell = f"{_fmt_price(stop)} ({owner})" if stop else "no stop yet"
                try:
                    self.trades_tree.heading(
                        "trail_line",
                        text="Stop (" + (", ".join(overlay_ids) or "no overlays") + ")",
                    )
                except Exception:
                    pass

            self.trades_tree.insert(
                "",
                "end",
                values=(
                    coin,
                    f"{qty:.8f}".rstrip("0").rstrip("."),
                    _fmt_money(value),  # position value (USD)
                    _fmt_price(avg_cost),  # per-unit price (USD) -> dynamic decimals
                    _fmt_price(buy_price),
                    _fmt_pct(buy_pnl),
                    _fmt_price(sell_price),
                    _fmt_pct(sell_pnl),
                    dca_stages,
                    dca_24h_display,
                    next_dca,
                    trail_cell,
                ),
            )

    def _refresh_pnl(self) -> None:
        # mtime cache: avoid reading/parsing every tick
        try:
            mtime = os.path.getmtime(self.pnl_ledger_path)
        except Exception:
            mtime = None

        if getattr(self, "_last_pnl_mtime", object()) == mtime:
            return
        self._last_pnl_mtime = mtime

        data = _safe_read_json(self.pnl_ledger_path)
        total = data.get("total_realized_profit_usd", 0.0) if data else None
        text, style = _fmt_profit(total)
        self.lbl_pnl.config(text=text, style=style)

    def _show_profit_figures(self, data: dict) -> None:
        """Unrealized and Since start, from the status the Account panel shows
        (Realized comes from the P&L ledger: _refresh_pnl). Since start is shown
        for the paper account only: it is measured from its starting balance."""
        unrealized = getattr(self, "lbl_acct_unrealized", None)
        since = getattr(self, "lbl_acct_since_start", None)
        if unrealized is None or since is None:
            return
        from_book = data.get("source") == "paper_book"
        # the saved book holds no prices: positions at cost, nothing to compare
        profit = (
            None
            if (from_book or not data)
            else unrealized_profit(data.get("positions") or {})
        )
        text, style = _fmt_profit(profit)
        unrealized.config(text=text, style=style)

        book_path = self._shown_paper_book_path()
        key = getattr(self, "lbl_acct_since_start_key", None)
        for widget in (key, since):
            if widget is None:
                continue
            if book_path is None:
                widget.grid_remove()
            elif widget.winfo_manager() != "grid":
                widget.grid()  # back where grid_remove() took it from
        if book_path is None:
            return
        start = paper_starting_balance(book_path)
        try:
            value = float((data.get("account") or {})["total_account_value"])
        except (KeyError, TypeError, ValueError):
            value = None
        if start is None or start <= 0 or value is None:
            since.config(text="N/A", style="TLabel")
            return
        text, style = _fmt_profit(value - start)
        pct = (value - start) / start * 100.0
        pct_text = "0.00%" if text == "$0.00" else f"{pct:+.2f}%"
        since.config(text=f"{text} ({pct_text})", style=style)

    def _refresh_trade_history(self) -> None:
        # mtime cache: avoid reading/parsing/rebuilding the table every tick
        try:
            mtime = os.path.getmtime(self.trade_history_path)
        except Exception:
            mtime = None

        if getattr(self, "_last_trade_history_mtime", object()) == mtime:
            return
        self._last_trade_history_mtime = mtime

        # every buy and sell: the filters and the summary need the whole history
        rows = (
            _read_trade_history_jsonl(self.trade_history_path)
            if mtime is not None
            else []
        )
        self.trade_history_view.load(rows)

    def _refresh_coin_dependent_ui(self, prev_coins: List[str]) -> None:
        """
        After settings change: refresh every coin-driven UI element:
          - Training dropdown (Train coin)
          - Trainers tab dropdown (Coin)
          - Chart tabs (Notebook): add/remove tabs to match current coin list
          - Neural overview tiles (new): add/remove tiles to match current coin list
        """
        # Rebuild dependent pieces
        self.coins = [
            c.upper().strip() for c in (self.settings.get("coins") or []) if c.strip()
        ]
        self.coin_folders = build_coin_folders(
            pt_paths.neural_dir(self.settings.get("main_neural_dir")), self.coins
        )
        # A removed coin's auto-retrain would still fire, in a folder that is no
        # longer its own (#146)
        for coin in [c for c in self.auto_retrain_timers if c not in self.coins]:
            self._cancel_auto_retrain(coin)

        # Refresh coin dropdowns (they don't auto-update)
        try:
            # Training pane dropdown
            if (
                hasattr(self, "train_coin_combo")
                and self.train_coin_combo.winfo_exists()
            ):
                self.train_coin_combo["values"] = self.coins
                cur = (
                    (self.train_coin_var.get() or "").strip().upper()
                    if hasattr(self, "train_coin_var")
                    else ""
                )
                if self.coins and cur not in self.coins:
                    self.train_coin_var.set(self.coins[0])

            # Trainers tab dropdown
            if (
                hasattr(self, "trainer_coin_combo")
                and self.trainer_coin_combo.winfo_exists()
            ):
                self.trainer_coin_combo["values"] = self.coins
                cur = (
                    (self.trainer_coin_var.get() or "").strip().upper()
                    if hasattr(self, "trainer_coin_var")
                    else ""
                )
                if self.coins and cur not in self.coins:
                    self.trainer_coin_var.set(self.coins[0])

            # Keep both selectors aligned if both exist
            if hasattr(self, "train_coin_var") and hasattr(self, "trainer_coin_var"):
                if self.train_coin_var.get():
                    self.trainer_coin_var.set(self.train_coin_var.get())
        except Exception:
            pass

        # Rebuild the coin table and its signal counts for the new coin list
        try:
            if getattr(self, "_training_cells", None) is not None:
                self._build_training_table()
                self._refresh_neural_overview()
        except Exception:
            pass

        # Rebuild chart tabs if the coin list changed
        try:
            prev_set = set(
                [str(c).strip().upper() for c in (prev_coins or []) if str(c).strip()]
            )
            if prev_set != set(self.coins):
                self._rebuild_coin_chart_tabs()
        except Exception:
            pass

    def _refresh_neural_overview(self) -> None:
        """
        Show each coin's long/short signal counts in its coin-table cell.
        Uses mtime caching so it's cheap to call every UI tick.
        """
        if not getattr(self, "_training_cells", None):
            return

        # Keep coin_folders aligned with current settings/coins
        try:
            sig = (
                str(self.settings.get("main_neural_dir") or ""),
                tuple(self.coins or []),
            )
            if getattr(self, "_coin_folders_sig", None) != sig:
                self._coin_folders_sig = sig
                self.coin_folders = build_coin_folders(
                    pt_paths.neural_dir(self.settings.get("main_neural_dir")),
                    self.coins,
                )
        except Exception:
            pass

        if not hasattr(self, "_neural_overview_cache"):
            self._neural_overview_cache = {}  # path -> (mtime, value)

        def _cached(path: str, loader, default: Any):
            try:
                mtime = os.path.getmtime(path)
            except Exception:
                return default, None

            hit = self._neural_overview_cache.get(path)
            if hit and hit[0] == mtime:
                return hit[1], mtime

            v = loader(path)
            self._neural_overview_cache[path] = (mtime, v)
            return v, mtime

        def _load_short_from_memory_json(path: str) -> int:
            try:
                obj = _safe_read_json(path) or {}
                return int(float(obj.get("short_dca_signal", 0)))
            except Exception:
                return 0

        try:  # the trader's start gate: long >= this level and no short
            level = max(
                1, min(int(float(self.settings.get("trade_start_level", 3) or 3)), 7)
            )
        except Exception:
            level = 3

        for coin, cell in list(self._training_cells.items()):
            folder = ""
            try:
                folder = (self.coin_folders or {}).get(coin, "")
            except Exception:
                folder = ""

            if not folder or not os.path.isdir(folder):
                self._show_signal_counts(coin, cell[4], None, None, None, level)
                continue

            long_sig = 0
            short_sig = 0
            mt_candidates: List[float] = []

            # Long signal
            long_path = os.path.join(folder, "long_dca_signal.txt")
            if os.path.isfile(long_path):
                long_sig, mt = _cached(long_path, read_int_from_file, 0)
                if mt:
                    mt_candidates.append(float(mt))

            # Short signal (prefer txt; fallback to memory.json)
            short_txt = os.path.join(folder, "short_dca_signal.txt")
            if os.path.isfile(short_txt):
                short_sig, mt = _cached(short_txt, read_int_from_file, 0)
                if mt:
                    mt_candidates.append(float(mt))
            else:
                mem = os.path.join(folder, "memory.json")
                if os.path.isfile(mem):
                    short_sig, mt = _cached(mem, _load_short_from_memory_json, 0)
                    if mt:
                        mt_candidates.append(float(mt))

            self._show_signal_counts(
                coin,
                cell[4],
                long_sig if mt_candidates else None,
                short_sig,
                min(mt_candidates) if mt_candidates else None,
                level,
            )

    def _gate_tooltip_line(self, coin: str) -> str:
        """The last training run's entry gate result, as tooltip lines ("" when the
        run wrote none)."""
        record = self._gate_record(coin)
        if not record or not isinstance(record.get("gate"), dict):
            return ""
        try:
            import entry_gate

            decision = entry_gate.Decision.from_dict(record["gate"])
        except Exception:
            return ""
        name = decision.figure_name()
        figures = decision.short() or "no entries"
        if record.get("published"):
            return (
                f"{name[0].upper()}{name[1:]} vs random: {figures}; passed the entry "
                "gate.\n"
            )
        kept = (
            f"the model in use ({record['kept_model_id']}) is kept"
            if record.get("kept_model_id")
            else "no model is in use"
        )
        return (
            f"Last training: {name} vs random {figures}; the new model did not "
            f"pass the entry gate, so {kept}.\n"
        )

    def _coin_tooltip(self, coin: str, field: str) -> str:
        """What a coin cell's field means, with this coin's current values."""
        status = (getattr(self, "_training_status", None) or {}).get(coin, "❌")
        training = status in ("●", "○")
        trained = status in ("✅", "✓")
        if field == "coin":
            return (
                f"{coin}\n"
                "Click: train it (or stop its training); both ask first.\n"
                "Right-click: open its price chart."
            )
        if field == "status":
            if training:
                return (
                    f"{coin}: training now (amber dot).\n"
                    f"The neural runner skips {coin} until the new model is saved.\n"
                    "Click to stop the training run."
                )
            if trained:
                record = self._gate_record(coin) or {}
                unused = "gate" in record and not (
                    record.get("published") or record.get("kept_model_id")
                )
                return (
                    f"{coin}: trained (green dot).\n"
                    + (
                        "Its model did not pass the entry gate and none did before, so "
                        f"the neural runner gives {coin} no signals.\n"
                        if unused
                        else "Its model is less than 14 days old, so the neural "
                        "runner uses it.\n"
                    )
                    + self._gate_tooltip_line(coin)
                    + "Click to retrain (this replaces the model if the new one "
                    "passes the entry gate)."
                )
            return (
                f"{coin}: not trained (grey dot).\n"
                "No model yet, or its model is older than 14 days, so the neural "
                f"runner gives {coin} no signals.\n"
                "Click to train it (about 2 minutes)."
            )
        if field == "age":
            if training:
                return (
                    f"Trained-for: {coin} is training now; this resets when its new "
                    "model is saved."
                )
            ts = (getattr(self, "last_training_times", None) or {}).get(coin)
            if not trained or not ts:
                return (
                    f"Trained-for: {coin} has never been trained, or its model was "
                    "removed or is older than 14 days."
                )
            hours = max(0.0, (time.time() - float(ts)) / 3600.0)
            when = time.strftime("%d %b %H:%M", time.localtime(float(ts)))
            auto = ""
            try:
                if self.settings.get("training_auto_enabled", True):
                    every = float(self.settings.get("training_auto_interval_hours", 6))
                    if every > 0:
                        auto = (
                            f"\nAuto-retrain: about every {every:g} h after a "
                            "successful run (Settings)."
                        )
                due = (getattr(self, "auto_retrain_due", None) or {}).get(coin)
                if due:
                    auto += f"\nNext auto-retrain: {_clock(due)}."
            except Exception:
                pass
            return (
                f"Trained-for: time since {coin}'s model was last saved.\n"
                f"{hours:.1f} h ago, at {when}. A model counts as trained for 14 days."
                + auto
            )
        if field == "signal":
            longs, shorts, mtime, level = (
                getattr(self, "_training_signal_info", None) or {}
            ).get(coin, (None, None, None, 3))
            engine = str(getattr(self, "_signals_engine", "") or "")
            if engine == "legacy_neural":
                used = (
                    "Your trader's engine is legacy_neural, so these counts decide "
                    "its new trades and neural DCA."
                )
            else:
                used = (
                    f"Your trader's engine is {engine or 'catalogue'}, which does not "
                    "use these counts; they are shown for information."
                )
            if longs is None:
                return (
                    f"Neural runner signal for {coin}: none yet.\n"
                    "The runner has not written one: it is stopped, the coin is "
                    "untrained or skipped, or it is still warming up (the first counts "
                    "appear after two full sweeps).\n" + used
                )
            age_txt = ""
            if mtime is not None:
                secs = max(0, int(time.time() - float(mtime)))
                age_txt = (
                    f"\nUpdated {secs} s ago."
                    if secs < 120
                    else f"\nUpdated {secs // 60} min ago."
                )
                if secs > 15 * 60:
                    age_txt += " Older than 15 minutes: the trader ignores it (dimmed)."
            return (
                f"Neural runner signal for {coin}: L{int(longs)} S{int(shorts or 0)}.\n"
                f"L = how many of the 7 timeframes (1h, 2h, 4h, 8h, 12h, 1d, 1w) have "
                f"the price below their predicted low (long); S = how many have it "
                f"above their predicted high (short).\n"
                f"Green: long is at least the trade start level ({level}, Settings) "
                f"and there is no short, so a new trade could start. Orange: a short "
                f"is present (no new trade). White: below the start level."
                + age_txt
                + "\n"
                + used
            )
        return ""

    def _show_signal_counts(
        self, coin, label, longs, shorts, mtime, level: int = 3
    ) -> None:
        """One cell's "L<n> S<n>": green when the trader would start a trade
        (long >= the trade start level and no short), orange while short, dimmed
        when the runner has not rewritten it for 15 minutes; "–" when there is no
        signal file. Only touches the label when the text or colour changes."""
        p = ui_theme.active_palette()
        info = getattr(self, "_training_signal_info", None)
        if info is not None:
            info[coin] = (longs, shorts, mtime, level)
        if longs is None:
            state = ("–", p["MUTED"])
        else:
            text = f"L{int(longs)} S{int(shorts or 0)}"
            if mtime is not None and time.time() - float(mtime) > 15 * 60:
                colour = p["MUTED"]
            elif shorts:
                colour = LOG_SHORT
            elif longs >= level:
                colour = STATUS_GREEN
            else:
                colour = p["FG"]
            state = (text, colour)
        cache = getattr(self, "_training_signal_state", None)
        if cache is None:
            cache = self._training_signal_state = {}
        if cache.get(coin) == state:
            return
        cache[coin] = state
        try:
            label.configure(text=state[0], fg=state[1])
        except Exception:
            pass

    def _build_chart_tab_row(self, charts_frame) -> None:
        """The chart tab row (owner, 2026-10-14): the coin buttons in one row that
        scrolls sideways when the panel is too narrow for it, then the selected
        chart's status lines out to the right edge (owner, 2026-11-04). The
        Timeframe box and the Chart settings cog sit on the chart itself
        (_build_chart_overlay)."""
        row = ttk.Frame(charts_frame)
        row.pack(fill="x", padx=(SPACE["edge"], SPACE["edge"]), pady=(SPACE["sm"], 0))
        self._chart_tabs_row = row
        self._build_chart_overlay(charts_frame)
        # The buttons, then the status lines straight after them, in a strip as wide
        # as the row. With room to spare the status column takes it, out to the
        # right edge; short of room the buttons' column narrows first, down to
        # MIN_TAB_BUTTONS_W, and they scroll, while the status keeps its width
        # (_balance_chart_tab_strip).
        strip = ttk.Frame(row)
        strip.pack(side="left", anchor="n", fill="x", expand=True)
        strip.columnconfigure(0, minsize=MIN_TAB_BUTTONS_W)
        self._chart_tabs_strip = strip
        self.chart_tabs_bar = ScrollingRow(strip)
        self.chart_tabs_bar.grid(row=0, column=0, sticky="new")
        self._chart_status_slot = ttk.Frame(strip)
        self._chart_status_slot.grid(
            row=0,
            column=1,
            sticky="new",
            padx=(SPACE["sm"], 0),
            pady=(0, TAB_BUTTON_GAP),
        )
        for widget in (strip, self._chart_status_slot, self.chart_tabs_bar.inner):
            widget.bind("<Configure>", self._balance_chart_tab_strip, add="+")
        self._balance_chart_tab_strip()

    def _balance_chart_tab_strip(self, event=None) -> None:
        """Give the tab strip's spare width to the status column, or take a
        shortfall from the buttons' column, whichever applies at this width."""
        strip = getattr(self, "_chart_tabs_strip", None)
        try:
            need = (
                self.chart_tabs_bar.inner.winfo_reqwidth()
                + self._chart_status_slot.winfo_reqwidth()
                + SPACE["sm"]
            )
            roomy = strip.winfo_width() >= need
            strip.columnconfigure(0, weight=0 if roomy else 1)
            strip.columnconfigure(1, weight=1 if roomy else 0)
        except (AttributeError, tk.TclError):
            pass

    def _build_chart_overlay(self, parent: tk.Widget) -> None:
        """The Timeframe box with the Chart settings cog butted up to its right, on
        the shown chart's top right corner (owner, 2026-11-04), above the plot.
        A child of the charts panel, placed on the chart's canvas by
        _place_chart_overlay; it is rebuilt with the tab row."""
        old = getattr(self, "_chart_overlay", None)
        try:
            if old is not None and old.winfo_exists():
                old.destroy()
        except tk.TclError:
            pass
        overlay = ttk.Frame(parent, style="ChartOverlay.TFrame")
        self._chart_overlay = overlay
        box = ttk.Frame(overlay, style="ChartOverlay.TFrame")
        ttk.Label(box, text="Timeframe:", style="ChartOverlay.TLabel").pack(
            side="left", padx=(0, 4)
        )
        combo = ttk.Combobox(
            box,
            values=self._settings_getter()["timeframes"],
            state="readonly",
            width=10,
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", self._on_chart_timeframe_selected)
        self._chart_tf_box, self.chart_tf_combo = box, combo
        box.pack(side="left")
        cog = ttk.Button(
            overlay,
            text="\u2699",
            style="ChartCog.TButton",
            command=self.open_chart_settings,
        )
        cog.pack(side="left")
        ToolTip(cog, "Chart settings")
        self.chart_settings_button = cog

    def _place_chart_overlay(self, chart: Any) -> None:
        """Put the Timeframe box and the cog on ``chart``'s top right corner, or take
        them away when there is no chart. Raised each time: the page container is
        created after it, so it would draw over it."""
        overlay = getattr(self, "_chart_overlay", None)
        if overlay is None:
            return
        try:
            if chart is None:
                overlay.place_forget()
                return
            overlay.place(
                in_=chart.canvas.get_tk_widget(),
                relx=1.0,
                rely=0.0,
                x=0,
                y=0,
                anchor="ne",
            )
            overlay.lift()
            if chart.overlay_px != self._chart_overlay_px:
                chart.overlay_px = self._chart_overlay_px  # the plot starts below it
                chart.after_idle(chart._fit_and_draw)
        except (AttributeError, tk.TclError):
            pass

    def _chart_overlay_px(self) -> int:
        """The Timeframe box and cog's height on the chart."""
        try:
            return int(self._chart_overlay.winfo_reqheight())
        except (AttributeError, tk.TclError):
            return 0

    def _show_chart_status(self, name: str) -> None:
        """The selected coin chart's status lines, in the tab row out to its right
        edge. The account chart has none."""
        for coin, chart in getattr(self, "charts", {}).items():
            frame = getattr(chart, "status_frame", None)
            if frame is None or frame.master is not getattr(
                self, "_chart_status_slot", None
            ):
                continue
            try:
                if coin == name:
                    if frame.winfo_manager() != "pack":
                        frame.pack(fill="x")
                elif frame.winfo_manager():
                    frame.pack_forget()
            except Exception:
                pass

    def _moved_status_row_px(self) -> int:
        """How much higher the plot starts than when each coin chart had a status
        row above it: that row (a label with CHART_STATUS_ROW_PADY above and below),
        plus what the gap under the tab buttons shrank by. The divider under the
        charts moves up as much, so the chart keeps its height."""
        try:
            label = next(iter(self.charts.values())).neural_status_label
        except (AttributeError, StopIteration):
            return 0
        row = int(label.winfo_reqheight()) + 2 * CHART_STATUS_ROW_PADY
        return row + FORMER_TAB_BUTTON_GAP - TAB_BUTTON_GAP

    def _new_account_chart(self, parent: tk.Widget) -> "AccountValueChart":
        """The ACCOUNT page's chart, packed, on the timeframe the one it replaces
        showed (the default timeframe the first time)."""
        try:
            tf = self.account_chart.timeframe_var.get()
        except Exception:
            tf = ""
        chart = AccountValueChart(
            parent,
            self.account_value_history_path,
            self.trade_history_path,
            timeframe=tf or self.settings["default_timeframe"],
            bars=lambda: int(self.settings.get("candles_limit", 120)),
        )
        chart.pack(fill="both", expand=True)
        return chart

    def _chart_named(self, name: str) -> Any:
        """The chart of page ``name``: a coin's CandleChart or, for ACCOUNT, the
        account chart. Both have a timeframe_var and set_timeframe()."""
        if name == "ACCOUNT":
            return getattr(self, "account_chart", None)
        return getattr(self, "charts", {}).get(name)

    def _show_chart_timeframe(self, name: str) -> None:
        """The Timeframe box shows the selected chart's timeframe (the account
        chart's too), on that chart with the cog."""
        if getattr(self, "_chart_overlay", None) is None:
            return
        chart = self._chart_named(name)
        try:
            if chart is not None:
                self.chart_tf_combo.set(chart.timeframe_var.get())
        except Exception:
            pass
        self._place_chart_overlay(chart)

    def _on_chart_timeframe_selected(self, event=None) -> None:
        chart = self._chart_named(getattr(self, "_current_chart_page", ""))
        if chart is not None:
            chart.set_timeframe(self.chart_tf_combo.get())

    def _rebuild_coin_chart_tabs(self) -> None:
        """
        Ensure the Charts multi-row tab bar + pages match self.coins.
        Keeps the ACCOUNT page intact and preserves the currently selected page when possible.
        """
        charts_frame = getattr(self, "_charts_frame", None)
        if charts_frame is None or (
            hasattr(charts_frame, "winfo_exists") and not charts_frame.winfo_exists()
        ):
            return

        # Remember selected page (coin or ACCOUNT)
        selected = getattr(self, "_current_chart_page", "ACCOUNT")
        if selected not in (["ACCOUNT"] + list(self.coins)):
            selected = "ACCOUNT"

        # Destroy existing tab row + pages container (clean rebuild)
        try:
            row = getattr(self, "_chart_tabs_row", None)
            if row is not None and row.winfo_exists():
                row.destroy()
        except Exception:
            pass

        try:
            if (
                hasattr(self, "chart_pages_container")
                and self.chart_pages_container.winfo_exists()
            ):
                self.chart_pages_container.destroy()
        except Exception:
            pass

        # Recreate
        self._build_chart_tab_row(charts_frame)

        self.chart_pages_container = ttk.Frame(charts_frame)
        self.chart_pages_container.pack(  # 5 px to the panel's edges
            fill="both",
            expand=True,
            padx=(SPACE["edge"], SPACE["edge"]),
            pady=(0, SPACE["edge"]),
        )

        self._chart_tab_buttons = {}
        self.chart_pages = {}
        self._current_chart_page = selected

        def _show_page(name: str) -> None:
            self._current_chart_page = name
            for f in self.chart_pages.values():
                try:
                    f.pack_forget()
                except Exception:
                    pass
            f = self.chart_pages.get(name)
            if f is not None:
                f.pack(fill="both", expand=True)

            for txt, b in self._chart_tab_buttons.items():
                try:
                    b.configure(
                        style=(
                            "ChartTabSelected.TButton"
                            if txt == name
                            else "ChartTab.TButton"
                        )
                    )
                except Exception:
                    pass
            self._show_chart_timeframe(name)
            self._show_chart_status(name)

        self._show_chart_page = _show_page

        # ACCOUNT page
        acct_page = ttk.Frame(self.chart_pages_container)
        self.chart_pages["ACCOUNT"] = acct_page

        acct_btn = ttk.Button(
            self.chart_tabs_bar.inner,
            text="ACCOUNT",
            style="ChartTab.TButton",
            command=lambda: self._show_chart_page("ACCOUNT"),
        )
        self.chart_tabs_bar.add(
            acct_btn, padx=(0, SPACE["sm"]), pady=(0, TAB_BUTTON_GAP)
        )
        self._chart_tab_buttons["ACCOUNT"] = acct_btn

        self.account_chart = self._new_account_chart(acct_page)

        # Coin pages
        self.charts = {}
        for coin in self.coins:
            page = ttk.Frame(self.chart_pages_container)
            self.chart_pages[coin] = page

            btn = ttk.Button(
                self.chart_tabs_bar.inner,
                text=coin,
                style="ChartTab.TButton",
                command=lambda c=coin: self._show_chart_page(c),
            )
            self.chart_tabs_bar.add(
                btn, padx=(0, SPACE["sm"]), pady=(0, TAB_BUTTON_GAP)
            )
            self._chart_tab_buttons[coin] = btn

            chart = CandleChart(
                page,
                self.fetcher,
                coin,
                self._settings_getter,
                self.trade_history_path,
                status_parent=self._chart_status_slot,
            )
            chart.pack(fill="both", expand=True)
            self.charts[coin] = chart

        # Restore selection
        self._show_chart_page(selected)

    # ---- paper account (the paper trader's book) ----

    def _paper_trader_running_reason(self) -> Optional[str]:
        """Why the paper book must not be saved now, or None.

        A running trader never reloads the book and saves over it after every
        order, so an edit made while it runs would be lost. Checked at the moment
        of saving."""
        proc = getattr(getattr(self, "proc_trader", None), "proc", None)
        if (proc is not None and proc.poll() is None) or getattr(
            self, "_auto_start_trader_pending", False
        ):
            return (
                "The trader is running (or about to start), and it would overwrite "
                "these values. Stop it with the ■ (Stop trader) button in the "
                "Trading section, then save here; this window can stay open."
            )
        if proc is None:
            # Not started by this hub: a trader started elsewhere is seen only by a
            # fresh paper status file (the hub's 2-minute freshness rule).
            status = _safe_read_json(
                os.path.join(
                    getattr(self, "hub_dir", ""), "paper", "trader_status.json"
                )
            )
            if not isinstance(status, dict):
                status = {}
            try:
                age = time.time() - float(status.get("timestamp"))
            except (TypeError, ValueError):
                age = None
            if age is not None and 0 <= age <= 120.0:
                return (
                    "A paper trader updated its status less than 2 minutes ago, so "
                    "it may still be running outside this window. Stop it (or wait "
                    "2 minutes if it has stopped), then save."
                )
        return None

    def open_paper_account_dialog(self, parent=None):
        """Settings > Paper Account: the starting balance, cash and positions the
        paper trader starts from (``<hub>/paper/paper_account.json``)."""
        try:
            from paper_account_ui import PaperAccountDialog

            paper_mode = bool(getattr(self, "_paper_mode", True))
            return PaperAccountDialog(
                parent or self,
                hub_dir=self.hub_dir,
                trader_running=self._paper_trader_running_reason,
                known_coins=getattr(self, "coins", ()) or (),
                palette=ui_tokens.palette(paper_mode),
                live=not paper_mode,
                on_saved=self._on_paper_account_saved,
            )
        except Exception as e:
            messagebox.showerror(
                "Paper Account", f"Could not open the paper account: {e}"
            )
            return None

    def open_exchange_check(self, parent=None):
        """Settings > Check Exchanges: the live exchange check for the exchanges
        enabled in Settings (primary first) and the hub's coins."""
        win = getattr(self, "_exchange_check_win", None)
        try:
            if win is not None and win.winfo_exists():
                win.deiconify()
                win.lift()
                win.focus_set()
                return win
        except tk.TclError:
            pass
        try:
            import exchange_check
            from exchange_check_gui import ExchangeCheckWindow

            exchanges, primary = exchange_check.enabled_exchanges()
            win = ExchangeCheckWindow(
                parent or self,
                exchanges=exchanges,
                coins=getattr(self, "coins", ()) or exchange_check.settings_coins(),
                primary=primary,
                palette=ui_theme.active_palette(),
            )
        except Exception as e:
            messagebox.showerror(
                "Check Exchanges", f"Could not open the exchange check: {e}"
            )
            return None
        self._exchange_check_win = win
        return win

    def open_strategy_settings(self, parent=None, on_saved=None):
        """Settings > Strategy: the signal source, the strategy, its candles and
        parameters, and the stops and filters (``strategy_settings_ui``). Saved to
        pt_config.json, which the trader reads before every decision."""
        win = getattr(self, "_strategy_settings_win", None)
        try:
            if win is not None and win.winfo_exists():
                win.deiconify()
                win.lift()
                win.focus_set()
                return win
        except tk.TclError:
            pass

        def saved() -> None:
            self._signals_note_mtime = object()  # re-read the strip's SIGNALS note
            self._refresh_signals_note()
            if on_saved is not None:
                on_saved()

        try:
            from strategy_settings_ui import StrategySettingsWindow

            win = StrategySettingsWindow(
                parent or self, on_saved=saved, palette=ui_theme.active_palette()
            )
        except Exception as e:
            messagebox.showerror(
                "Strategy", f"Could not open the strategy settings: {e}"
            )
            return None
        self._strategy_settings_win = win
        return win

    def _shown_account_value(self) -> Optional[float]:
        """The account value on the Account panel (from trader_status.json), or
        None before the trader has reported one."""
        try:
            value = float(getattr(self, "_last_total_account_value", 0.0) or 0.0)
        except (TypeError, ValueError):
            return None
        return value if value > 0.0 else None

    def open_risk_settings(self, parent=None, on_saved=None):
        """Settings > Risk: the account drawdown levels, the peak they are
        measured from, and Resume trading after an emergency stop
        (``risk_settings_ui``). The levels are saved to pt_config.json, which the
        trader reads before every drawdown check; the peak and the halt are kept in
        the books folder this hub shows; the position and DCA limits in
        gui_settings.json. ``on_saved()`` also runs after Reset peak and Resume
        trading."""
        win = getattr(self, "_risk_settings_win", None)
        try:
            if win is not None and win.winfo_exists():
                win.deiconify()
                win.lift()
                win.focus_set()
                return win
        except tk.TclError:
            pass

        def changed() -> None:
            self._refresh_halt_banner()
            if on_saved is not None:
                on_saved()

        try:
            from risk_settings_ui import RiskSettingsWindow

            win = RiskSettingsWindow(
                parent or self,
                books_dir=getattr(self, "_books_dir", None),
                account_value=self._shown_account_value,
                limits={
                    key: self.settings.get(key, DEFAULT_SETTINGS[key])
                    for key in RISK_LIMIT_KEYS
                },
                save_limits=self._save_risk_limits,
                on_saved=changed,
                on_changed=changed,
                palette=ui_theme.active_palette(),
            )
        except Exception as e:
            messagebox.showerror("Risk", f"Could not open the risk settings: {e}")
            return None
        self._risk_settings_win = win
        return win

    def _save_risk_limits(self, values: Dict[str, Any]) -> None:
        """Settings > Risk's position and DCA limits, saved in gui_settings.json
        with the rest of the hub's settings (the trader re-reads that file when it
        changes)."""
        self.settings.update({k: values[k] for k in RISK_LIMIT_KEYS if k in values})
        self._save_settings()

    def _risk_summary(self) -> str:
        """Settings' Risk line: a halt, and the drawdown levels the trader uses."""
        try:
            levels = read_drawdown_levels()
            halted = risk_state.current(getattr(self, "_books_dir", None)).halted
        except Exception as e:
            return f"Could not read the risk settings: {e}"
        return ("Trading is halted. " if halted else "") + (
            f"Trading stops at a {levels.emergency_pct:g}% drawdown from the peak; "
            f"warnings at {levels.warning_pct:g}% and {levels.critical_pct:g}%"
        )

    def _refresh_halt_banner(self) -> None:
        """TRADING HALTED across the top while an emergency stop has halted
        trading for the books this hub shows; the files are read again only when
        one of them changes."""
        folder = getattr(self, "_books_dir", None)
        key = risk_state.files_signature(folder)
        if key == getattr(self, "_halt_banner_key", None):
            return
        self._halt_banner_key = key
        view = risk_state.current(folder)
        banner = self._halt_banner
        if not view.halted:
            if banner is not None:
                try:
                    banner.destroy()
                except tk.TclError:
                    pass
                self._halt_banner = None
            return
        if banner is None:
            from risk_settings_ui import HaltBanner

            banner = HaltBanner(self, on_open=lambda: self.open_risk_settings())
            self._halt_banner = banner
            pack_at_top(banner, self)
        banner.show(view)

    def _on_paper_account_saved(self) -> None:
        """Settings > Paper Account saved a new book: the Account panel shows it,
        and the paper peak is cleared, so drawdown is measured from the book's
        first account value when the trader starts (a halt stays)."""
        self._refresh_trader_status()
        try:
            risk_state.request_peak_reset(
                os.path.dirname(paper_book_path(self.hub_dir)), None
            )
        except OSError as exc:
            print(f"Paper peak not cleared: {exc}")

    @staticmethod
    def _strategy_summary() -> str:
        """Settings' Strategy line: what decides each buy and sale."""
        try:
            return strategy_words.summary_line(read_strategy_settings())
        except Exception as e:
            return f"Could not read the strategy settings: {e}"

    def open_llm_settings(self, parent=None, on_saved=None):
        """Settings > LLM Providers: the LLM providers, their order and the LLM
        signals in trading (``llm_settings_ui``), saved to pt_config.json."""
        win = getattr(self, "_llm_settings_win", None)
        try:
            if win is not None and win.winfo_exists():
                win.deiconify()
                win.lift()
                win.focus_set()
                return win
        except tk.TclError:
            pass
        try:
            from llm_settings_ui import LLMProvidersWindow

            win = LLMProvidersWindow(
                parent or self, on_saved=on_saved, palette=ui_theme.active_palette()
            )
        except Exception as e:
            messagebox.showerror(
                "LLM Providers", f"Could not open the LLM provider settings: {e}"
            )
            return None
        self._llm_settings_win = win
        return win

    @staticmethod
    def _llm_summary() -> str:
        """Settings' LLM Providers line: the provider order and the signal mode."""
        try:
            from llm_settings_ui import summary_line

            return summary_line()
        except Exception as e:
            return f"Could not read the LLM settings: {e}"

    # ---- settings dialog ----

    # ---- Chart settings pop-out (FDS-CHART-001 section 8) ----

    def open_chart_settings(self, parent=None):
        """Open (or raise) the Chart settings pop-out: a toggle for every chart overlay
        and candlestick pattern. Each change is saved and redrawn at once."""
        p = ui_theme.active_palette()
        from pt_chart_patterns import ChartSettingsWindow

        win = getattr(self, "_chart_settings_win", None)
        try:
            if win is not None and win.winfo_exists():
                win.deiconify()
                win.lift()
                win.focus_set()
                return win
        except tk.TclError:
            pass
        win = ChartSettingsWindow(
            parent or self, self.settings.get("chart"), self._apply_chart_settings
        )
        win.configure(bg=p["BG"])
        self._chart_settings_win = win
        return win

    def _apply_chart_settings(self, chart_cfg: dict) -> None:
        """Save new chart settings and redraw the visible coin chart; the others pick
        them up when they are next shown."""
        self.settings["chart"] = chart_settings.normalize(chart_cfg)
        try:
            self._save_settings()
        except Exception as exc:
            print(f"Chart settings not saved: {exc}")
        try:
            page = getattr(self, "_current_chart_page", "ACCOUNT")
            if page and page != "ACCOUNT" and hasattr(self, "_show_chart_page"):
                self._show_chart_page(page)
        except Exception:
            pass

    def open_settings_dialog(self) -> None:
        """One tab per section; Save writes every tab. Strategy, Risk, LLM
        Providers, the paper account and the chart overlays keep their own windows,
        opened from their tab."""
        p = ui_theme.active_palette()
        win = tk.Toplevel(self)
        win.title("Settings")
        win.geometry("900x640")
        win.minsize(780, 560)
        win.configure(bg=p["BG"])

        outer = ttk.Frame(win)
        outer.pack(fill="both", expand=True, padx=12, pady=12)
        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        btns = ttk.Frame(outer)
        btns.pack(fill="x", pady=(12, 0))

        def new_page(title: str) -> ttk.Frame:
            page = ttk.Frame(notebook, padding=12)
            page.columnconfigure(0, weight=0)  # labels
            page.columnconfigure(1, weight=1)  # entries
            page.columnconfigure(2, weight=0)  # buttons and hints
            notebook.add(page, text=title)
            return page

        def add_row(
            page: ttk.Frame, r: int, label: str, var: tk.Variable, wide: bool = False
        ) -> None:
            ttk.Label(page, text=label).grid(
                row=r, column=0, sticky="w", padx=(0, 10), pady=6
            )
            entry = ttk.Entry(page, textvariable=var, width=24)
            if wide:  # a list: as wide as the page
                entry.grid(row=r, column=1, columnspan=2, sticky="ew", pady=6)
            else:
                entry.grid(row=r, column=1, sticky="w", pady=6)

        def add_heading(page: ttk.Frame, r: int, text: str) -> None:
            ttk.Label(page, text=text, font=ui_tokens.font("body", "bold")).grid(
                row=r, column=0, columnspan=3, sticky="w", pady=(12, 4)
            )

        def add_check(page: ttk.Frame, r: int, text: str, var: tk.Variable) -> None:
            ttk.Checkbutton(page, text=text, variable=var).grid(
                row=r, column=0, columnspan=3, sticky="w", pady=6
            )

        def add_window_row(
            page: ttk.Frame, r: int, text: str, command, summary: tk.Variable
        ) -> None:
            """A button opening a section's own window, with a line saying what it
            holds now."""
            ttk.Button(page, text=text, command=command).grid(
                row=r, column=0, sticky="w", pady=6
            )
            ttk.Label(page, textvariable=summary, wraplength=560).grid(
                row=r, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=6
            )

        def add_choice(
            page: ttk.Frame,
            r: int,
            label: str,
            var: tk.Variable,
            values,
            width: int = 22,
        ) -> ttk.Combobox:
            ttk.Label(page, text=label).grid(
                row=r, column=0, sticky="w", padx=(0, 10), pady=6
            )
            box = ttk.Combobox(
                page,
                textvariable=var,
                values=list(values),
                state="readonly",
                width=width,
            )
            box.grid(row=r, column=1, sticky="w", pady=6)
            return box

        def setting_text(key: str, default) -> str:
            value = self.settings.get(key, DEFAULT_SETTINGS.get(key, default))
            return str(default if value is None else value)

        # --- Trading: the coins, the entry level, DCA and the trailing exit --------
        page = new_page("Trading")
        coins_var = tk.StringVar(master=win, value=",".join(self.settings["coins"]))
        trade_start_level_var = tk.StringVar(
            master=win, value=setting_text("trade_start_level", 3)
        )
        _dca_levels = self.settings.get(
            "dca_levels", DEFAULT_SETTINGS.get("dca_levels", [])
        )
        if not isinstance(_dca_levels, list):
            _dca_levels = DEFAULT_SETTINGS.get("dca_levels", [])
        dca_levels_var = tk.StringVar(
            master=win, value=",".join(str(x) for x in _dca_levels)
        )
        pm_no_dca_var = tk.StringVar(
            master=win, value=setting_text("pm_start_pct_no_dca", 5.0)
        )
        pm_with_dca_var = tk.StringVar(
            master=win, value=setting_text("pm_start_pct_with_dca", 2.5)
        )
        trailing_gap_var = tk.StringVar(
            master=win, value=setting_text("trailing_gap_pct", 0.5)
        )
        r = 0
        add_row(page, r, "Coins (comma):", coins_var, wide=True)
        r += 1
        add_row(page, r, "Trade start level (1-7):", trade_start_level_var)
        r += 1
        # Start allocation %, Max per coin %, DCA multiplier and Max DCA buys are in
        # Settings > Risk (Position and DCA limits)
        add_row(page, r, "DCA levels (% list):", dca_levels_var, wide=True)
        r += 1
        add_row(page, r, "Trailing PM start % (no DCA):", pm_no_dca_var)
        r += 1
        add_row(page, r, "Trailing PM start % (with DCA):", pm_with_dca_var)
        r += 1
        add_row(page, r, "Trailing gap % (behind peak):", trailing_gap_var)
        r += 1
        # Strategy: what decides each buy and sale (its own window, saved there)
        add_heading(page, r, "Strategy")
        r += 1
        strategy_summary_var = tk.StringVar(master=win, value=self._strategy_summary())
        add_window_row(
            page,
            r,
            "Strategy...",
            lambda: self.open_strategy_settings(
                win,
                on_saved=lambda: strategy_summary_var.set(self._strategy_summary()),
            ),
            strategy_summary_var,
        )
        r += 1
        # Risk: the limits that protect the account (its own window, saved there)
        add_heading(page, r, "Risk")
        r += 1
        risk_summary_var = tk.StringVar(master=win, value=self._risk_summary())
        add_window_row(
            page,
            r,
            "Risk...",
            lambda: self.open_risk_settings(
                win, on_saved=lambda: risk_summary_var.set(self._risk_summary())
            ),
            risk_summary_var,
        )

        # --- Training: when a model may be used, and when coins retrain -----------
        # (training_settings: the entry gate the trainer and the LLM signal gate use)
        page = new_page("Training")
        _training = training_settings.read_training_settings()
        min_signals_var = tk.StringVar(
            master=win, value=str(_training["holdout_min_signals"])
        )
        min_return_var = tk.StringVar(
            master=win, value=f"{_training['gate_min_return_per_day'] * 100:g}"
        )
        llm_min_return_var = tk.StringVar(
            master=win, value=f"{_training['gate_min_return_after_fees'] * 100:g}"
        )
        baseline_runs_var = tk.StringVar(
            master=win, value=str(_training["gate_baseline_runs"])
        )
        baseline_percentile_var = tk.StringVar(
            master=win, value=f"{_training['gate_baseline_percentile']:g}"
        )
        auto_retrain_var = tk.BooleanVar(
            master=win, value=bool(self.settings.get("training_auto_enabled", True))
        )
        try:
            retrain_hours = float(self.settings.get("training_auto_interval_hours", 6))
        except (TypeError, ValueError):
            retrain_hours = 6.0
        retrain_hours_var = tk.StringVar(master=win, value=f"{retrain_hours:g}")
        notifications_var = tk.BooleanVar(
            master=win, value=bool(self.settings.get("training_notifications", True))
        )
        r = 0
        add_row(page, r, "Minimum scored signals:", min_signals_var)
        r += 1
        add_row(page, r, "Minimum return per day held after fees %:", min_return_var)
        r += 1
        add_row(
            page,
            r,
            "Minimum mean return per LLM signal after fees %:",
            llm_min_return_var,
        )
        r += 1
        add_row(page, r, "Random-entry baselines:", baseline_runs_var)
        r += 1
        add_row(
            page, r, "Beat this percentile of random entries:", baseline_percentile_var
        )
        r += 1
        ttk.Label(
            page,
            text=(
                "A new model is used only when, on bars it never saw, its entries' "
                "return per day held after fees is above the minimum and above this "
                "percentile of random entries made with the same waits, its return "
                "over all the capital it committed is above 0%, its worst drawdown is "
                "no worse than the random entries' median, and it does at least as "
                "well per day held as the model in use. An LLM model may confirm or "
                "veto entries only when its signals' mean return after fees is above "
                "the minimum per LLM signal and above this percentile of random "
                "signals, on the same terms. "
                "The hit rate is shown only."
            ),
            style="Muted.TLabel",
            wraplength=560,
            justify="left",
        ).grid(row=r, column=0, columnspan=3, sticky="w", pady=(2, 6))
        r += 1
        ttk.Button(
            page,
            text="Check the models in use...",
            command=lambda: self.check_models_against_gate(win),
        ).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1
        add_check(page, r, "Retrain each trained coin automatically", auto_retrain_var)
        r += 1
        add_row(page, r, "Retrain every (hours):", retrain_hours_var)
        r += 1
        add_check(page, r, "Show a notice when a training run ends", notifications_var)

        # --- Exchanges: where prices come from and orders go ----------------------
        page = new_page("Exchanges")
        region_var = tk.StringVar(master=win, value=self.settings.get("region", "us"))
        # The user's choice is shown and kept as it is: the window never fills one
        # in. It lists each exchange by name ("KuCoin") and saves its id ("kucoin").
        primary_exchange = self._primary_exchange()
        primary_exchange_var = tk.StringVar(
            master=win, value=exchange_name(primary_exchange)
        )
        price_comparison_var = tk.BooleanVar(
            master=win, value=self.settings.get("price_comparison_enabled", True)
        )
        auto_best_price_var = tk.BooleanVar(
            master=win, value=self.settings.get("auto_best_price", False)
        )
        r = 0
        add_choice(page, r, "Your region:", region_var, ["us", "eu", "global"])
        r += 1
        add_choice(
            page,
            r,
            "Primary exchange:",
            primary_exchange_var,
            sorted(
                (
                    exchange_name(e)
                    for e in self._primary_exchange_choices(primary_exchange)
                ),
                key=str.lower,
            ),
        )
        r += 1
        add_check(
            page, r, "Enable price comparison across exchanges", price_comparison_var
        )
        r += 1
        add_check(page, r, "Automatically use best price exchange", auto_best_price_var)
        r += 1

        def open_exchange_setup():
            try:
                from exchange_config_gui import ExchangeConfigGUI

                ExchangeConfigGUI(parent=self)
                messagebox.showinfo(
                    "Exchange Setup",
                    "Exchange configuration tool opened in separate window.",
                )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open exchange setup: {e}")

        ttk.Button(
            page, text="Configure Exchange APIs...", command=open_exchange_setup
        ).grid(row=r, column=0, sticky="w", pady=(12, 6))
        ttk.Label(page, text="API keys and which exchanges are enabled").grid(
            row=r, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=(12, 6)
        )
        r += 1
        ttk.Button(
            page,
            text="Check Exchanges...",
            command=lambda: self.open_exchange_check(win),
        ).grid(row=r, column=0, sticky="w", pady=6)
        ttk.Label(
            page, text="prices, candles and minimum orders from each enabled exchange"
        ).grid(row=r, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=6)

        # --- Paper trading ---------------------------------------------------------
        page = new_page("Paper trading")
        # The coins paper trading opens new trades in: the coins on the Trading tab,
        # or a chosen set of them (paper_coins.py)
        paper_mode_var = tk.StringVar(master=win, value=paper_coins.mode(self.settings))
        saved_paper_coins = paper_coins.chosen(self.settings)
        paper_coin_vars: Dict[str, tk.BooleanVar] = {}
        _paper = read_paper_settings()
        quote_age_var = tk.StringVar(master=win, value=f"{_paper.max_quote_age_s:g}")
        price_rule_var = tk.StringVar(
            master=win, value=PAPER_PRICE_RULES[_paper.price_fallback_policy]
        )
        r = 0
        ttk.Label(page, text="Paper-trading coins:").grid(
            row=r, column=0, sticky="nw", padx=(0, 10), pady=6
        )
        paper_box = ttk.Frame(page)
        paper_box.grid(row=r, column=1, columnspan=2, sticky="ew", pady=6)
        ttk.Radiobutton(
            paper_box,
            text="Inherit coins from main settings",
            value=paper_coins.INHERIT,
            variable=paper_mode_var,
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            paper_box,
            text="Override paper-trading coins:",
            value=paper_coins.OVERRIDE,
            variable=paper_mode_var,
        ).grid(row=1, column=0, sticky="w")
        paper_coin_frame = ttk.Frame(paper_box)
        paper_coin_frame.grid(
            row=2, column=0, sticky="w", padx=(ui_tokens.SPACE["xxl"], 0), pady=(2, 0)
        )
        ttk.Label(
            paper_box,
            wraplength=560,
            text=(
                "New paper trades open only in these coins. A position already held "
                "is still sold by its exit rules. Live trading uses the coins on the "
                "Trading tab."
            ),
        ).grid(row=3, column=0, sticky="w", pady=(4, 0))

        def _typed_coins() -> List[str]:
            return paper_coins.normalise(coins_var.get().split(","))

        def _show_paper_coins(*_) -> None:
            """One tick box per coin on the Trading tab, usable when overriding. A
            coin keeps its tick while that list is edited."""
            for child in paper_coin_frame.winfo_children():
                child.destroy()
            override = paper_mode_var.get() == paper_coins.OVERRIDE
            for i, coin in enumerate(_typed_coins()):
                var = paper_coin_vars.get(coin)
                if var is None:
                    # nothing chosen yet: start from every coin
                    ticked = coin in saved_paper_coins if saved_paper_coins else True
                    var = paper_coin_vars[coin] = tk.BooleanVar(
                        master=win, value=ticked
                    )
                box = ttk.Checkbutton(paper_coin_frame, text=coin, variable=var)
                box.grid(row=i // 8, column=i % 8, sticky="w", padx=(0, 10))
                box.state(["!disabled"] if override else ["disabled"])

        def _ticked_paper_coins() -> List[str]:
            return [
                c
                for c in _typed_coins()
                if c in paper_coin_vars and paper_coin_vars[c].get()
            ]

        _show_paper_coins()
        coins_var.trace_add("write", _show_paper_coins)
        paper_mode_var.trace_add("write", _show_paper_coins)
        r += 1
        # Paper fills: how old a price may be, and what happens without a fresh one
        add_row(page, r, "Oldest price a paper fill uses (s):", quote_age_var)
        r += 1
        add_choice(
            page,
            r,
            "With no fresh price:",
            price_rule_var,
            PAPER_PRICE_RULES.values(),
            width=40,
        )
        r += 1
        # Paper account: the paper trader's book (balances and positions)
        ttk.Button(
            page,
            text="Paper Account...",
            command=lambda: self.open_paper_account_dialog(win),
        ).grid(row=r, column=0, sticky="w", pady=(12, 6))
        ttk.Label(
            page, text="starting balance, cash and positions for paper trading"
        ).grid(row=r, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=(12, 6))

        # --- LLM: providers, their order and LLM signals (its own window) ----------
        page = new_page("LLM")
        llm_summary_var = tk.StringVar(master=win, value=self._llm_summary())
        add_window_row(
            page,
            0,
            "LLM Providers...",
            lambda: self.open_llm_settings(
                win, on_saved=lambda: llm_summary_var.set(self._llm_summary())
            ),
            llm_summary_var,
        )

        # --- Display: refresh rates and charts --------------------------------------
        page = new_page("Display")
        ui_refresh_var = tk.StringVar(
            master=win, value=str(self.settings["ui_refresh_seconds"])
        )
        chart_refresh_var = tk.StringVar(
            master=win, value=str(self.settings["chart_refresh_seconds"])
        )
        candles_limit_var = tk.StringVar(
            master=win, value=str(self.settings["candles_limit"])
        )
        timeframes = list(
            self.settings.get("timeframes") or DEFAULT_SETTINGS["timeframes"]
        )
        default_tf_var = tk.StringVar(
            master=win,
            value=self.settings.get("default_timeframe")
            or DEFAULT_SETTINGS["default_timeframe"],
        )
        dark_theme_var = tk.BooleanVar(
            master=win, value=bool(self.settings.get("dark_theme", True))
        )
        r = 0
        add_row(page, r, "UI refresh seconds:", ui_refresh_var)
        r += 1
        add_row(page, r, "Chart refresh seconds:", chart_refresh_var)
        r += 1
        add_row(page, r, "Candles limit:", candles_limit_var)
        r += 1
        add_choice(page, r, "Chart timeframe at start-up:", default_tf_var, timeframes)
        r += 1
        # Chart overlays and candlestick patterns: their own pop-out (FDS-CHART-001)
        ttk.Label(page, text="Chart overlays:").grid(
            row=r, column=0, sticky="w", padx=(0, 10), pady=6
        )
        ttk.Button(
            page,
            text="Chart settings…",
            command=lambda: self.open_chart_settings(parent=win),
        ).grid(row=r, column=1, sticky="w", pady=6)
        r += 1
        add_check(page, r, "Use dark theme (default: enabled)", dark_theme_var)

        # --- Working Directories: where settings, data and logs live (read-only) ---
        page = new_page("Working Directories")
        ttk.Label(
            page,
            wraplength=760,
            text=(
                "Where PowerTrader keeps your settings, models, data and logs. The "
                "program folder itself is read-only and holds none of your files."
            ),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        for r, (label, folder) in enumerate(
            self._user_folder_rows(self.settings), start=1
        ):
            ttk.Label(page, text=label).grid(
                row=r, column=0, sticky="w", padx=(0, 10), pady=4
            )
            path_entry = ttk.Entry(page)
            path_entry.insert(0, folder)
            path_entry.configure(state="readonly")
            path_entry.grid(row=r, column=1, sticky="ew", pady=4)
            ttk.Button(
                page,
                text="Open folder",
                command=lambda f=folder: self._open_user_folder(f),
            ).grid(row=r, column=2, sticky="e", padx=(10, 0), pady=4)

        # --- System: start-up and the public API server -----------------------------
        page = new_page("System")
        auto_start_var = tk.BooleanVar(
            master=win, value=bool(self.settings.get("auto_start_scripts", False))
        )
        api_enabled_var = tk.BooleanVar(
            master=win, value=bool(self.settings.get("api_server_enabled", False))
        )
        api_host_var = tk.StringVar(
            master=win, value=self.settings.get("api_server_host", "127.0.0.1")
        )
        api_port_var = tk.StringVar(
            master=win, value=str(self.settings.get("api_server_port", 8080))
        )
        r = 0
        add_check(
            page,
            r,
            "Start the Neural Runner and Trader when the hub opens",
            auto_start_var,
        )
        r += 1
        ttk.Label(
            page,
            wraplength=760,
            text=(
                "Every coin must be trained. The Trader starts once the Neural Runner "
                "is ready, in the trading mode that is set (paper or live)."
            ),
        ).grid(row=r, column=0, columnspan=3, sticky="w", padx=(20, 0))
        r += 1
        add_heading(page, r, "Public API server")
        r += 1
        add_check(page, r, "Enable Public API Server", api_enabled_var)
        r += 1
        add_row(page, r, "API Host:", api_host_var)
        r += 1
        add_row(page, r, "API Port:", api_port_var)
        r += 1
        api_status_frame = ttk.Frame(page)
        api_status_frame.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(5, 10))
        api_status_frame.columnconfigure(1, weight=1)
        ttk.Label(api_status_frame, text="Status:").grid(row=0, column=0, sticky="w")
        api_status_lbl = ttk.Label(api_status_frame, text="Unknown")
        api_status_lbl.grid(row=0, column=1, sticky="w", padx=(10, 0))

        def test_api():
            if API_SERVER_AVAILABLE:
                status = self.get_api_server_status()
                api_status_lbl.config(text=status.get("message", "Unknown"))
            else:
                api_status_lbl.config(text="Flask not installed")

        ttk.Button(api_status_frame, text="Test API", command=test_api).grid(
            row=0, column=2, sticky="e"
        )
        test_api()  # Initial status check

        def save():
            # checked before anything changes, so a refused save changes nothing
            paper_mode = paper_mode_var.get()
            paper_ticked = _ticked_paper_coins()
            if paper_mode == paper_coins.OVERRIDE and not paper_ticked:
                messagebox.showerror(
                    "Paper trading",
                    "Tick at least one paper-trading coin, or choose "
                    "Inherit coins from main settings.",
                    parent=win,
                )
                return
            try:
                # Training: read first, so a value that is not allowed saves nothing
                gate_values = {}
                for name, label, var, scale in (
                    (
                        "holdout_min_signals",
                        "Minimum scored signals",
                        min_signals_var,
                        1,
                    ),
                    (
                        "gate_min_return_per_day",
                        "Minimum return per day held after fees %",
                        min_return_var,
                        100,
                    ),
                    (
                        "gate_min_return_after_fees",
                        "Minimum mean return per LLM signal after fees %",
                        llm_min_return_var,
                        100,
                    ),
                    (
                        "gate_baseline_runs",
                        "Random-entry baselines",
                        baseline_runs_var,
                        1,
                    ),
                    (
                        "gate_baseline_percentile",
                        "Beat this percentile of random entries",
                        baseline_percentile_var,
                        1,
                    ),
                ):
                    text = var.get().strip().replace("%", "")
                    try:
                        value = float(text) / scale
                    except ValueError:
                        value = text
                    problem = training_settings.problem(name, value)
                    if problem:
                        low, high = training_settings.BOUNDS[name]
                        raise ValueError(
                            f"{label} must be from {low * scale:g} to {high * scale:g}"
                            + (
                                " (a whole number)"
                                if name in training_settings.WHOLE
                                else ""
                            )
                        )
                    gate_values[name] = (
                        int(value) if name in training_settings.WHOLE else value
                    )
                retrain_hours = float(retrain_hours_var.get().strip())
                if (
                    not RETRAIN_HOURS_RANGE[0]
                    <= retrain_hours
                    <= RETRAIN_HOURS_RANGE[1]
                ):
                    raise ValueError(
                        "Retrain every is between {:g} and {:g} hours (a model counts "
                        "as trained for 14 days)".format(*RETRAIN_HOURS_RANGE)
                    )
                quote_age = float(quote_age_var.get().strip())
                if not MAX_QUOTE_AGE_RANGE[0] <= quote_age <= MAX_QUOTE_AGE_RANGE[1]:
                    raise ValueError(
                        "The oldest price a paper fill uses is between {:g} and {:g} "
                        "seconds".format(*MAX_QUOTE_AGE_RANGE)
                    )
                price_rule = next(
                    k for k, v in PAPER_PRICE_RULES.items() if v == price_rule_var.get()
                )

                # Track coins before changes so we can detect newly added coins
                prev_coins = set(
                    [
                        str(c).strip().upper()
                        for c in (self.settings.get("coins") or [])
                        if str(c).strip()
                    ]
                )

                self.settings["coins"] = [
                    c.strip().upper() for c in coins_var.get().split(",") if c.strip()
                ]
                self.settings["trade_start_level"] = max(
                    1, min(int(float(trade_start_level_var.get().strip())), 7)
                )

                raw_dca = (dca_levels_var.get() or "").replace(",", " ").split()
                dca_levels = []
                for tok in raw_dca:
                    try:
                        dca_levels.append(float(tok))
                    except Exception:
                        pass
                if not dca_levels:
                    dca_levels = list(DEFAULT_SETTINGS.get("dca_levels", []))
                self.settings["dca_levels"] = dca_levels

                # --- Trailing PM settings ---
                for key, var, default in (
                    ("pm_start_pct_no_dca", pm_no_dca_var, 5.0),
                    ("pm_start_pct_with_dca", pm_with_dca_var, 2.5),
                    ("trailing_gap_pct", trailing_gap_var, 0.5),
                ):
                    try:
                        value = float((var.get() or "").strip().replace("%", "") or 0.0)
                    except Exception:
                        value = float(
                            self.settings.get(key, DEFAULT_SETTINGS.get(key, default))
                            or default
                        )
                    self.settings[key] = max(0.0, value)

                # --- Paper trading coins (an inherit keeps the chosen coins for later)
                self.settings[paper_coins.MODE_KEY] = paper_mode
                if paper_mode == paper_coins.OVERRIDE:
                    self.settings[paper_coins.COINS_KEY] = paper_ticked

                # --- Exchanges ---
                self.settings["region"] = region_var.get().strip()
                self.settings["primary_exchange"] = exchange_id(
                    primary_exchange_var.get()
                )
                self.settings["price_comparison_enabled"] = bool(
                    price_comparison_var.get()
                )
                self.settings["auto_best_price"] = bool(auto_best_price_var.get())

                # --- Display ---
                self.settings["ui_refresh_seconds"] = float(
                    ui_refresh_var.get().strip()
                )
                self.settings["chart_refresh_seconds"] = float(
                    chart_refresh_var.get().strip()
                )
                self.settings["candles_limit"] = int(
                    float(candles_limit_var.get().strip())
                )
                if default_tf_var.get() in timeframes:
                    self.settings["default_timeframe"] = default_tf_var.get()
                self.settings["dark_theme"] = dark_theme_var.get()

                # --- System ---
                self.settings["auto_start_scripts"] = bool(auto_start_var.get())
                self.settings["api_server_enabled"] = api_enabled_var.get()
                self.settings["api_server_host"] = api_host_var.get()
                try:
                    port = int(api_port_var.get())
                    self.settings["api_server_port"] = max(1, min(port, 65535))
                except ValueError:
                    self.settings["api_server_port"] = 8080

                # --- Training ---
                self.settings["training_notifications"] = notifications_var.get()
                retrain_was = (
                    self.settings.get("training_auto_enabled", True),
                    self.settings.get("training_auto_interval_hours", 6),
                )
                self.settings["training_auto_enabled"] = bool(auto_retrain_var.get())
                self.settings["training_auto_interval_hours"] = retrain_hours

                # pt_config.json first: a refusal there leaves gui_settings.json as
                # it was
                if not save_paper_settings(price_rule, quote_age):
                    raise ValueError("the paper-trading price rules were not saved")
                self._save_settings()
                training_settings.save_training_settings(gate_values)
                # the runner, trainers and trader read the exchange choice from
                # trading_config.json, not from gui_settings.json
                self._sync_exchange_choice()

                # Apply theme changes
                self._apply_theme()

                # Restart API server if settings changed
                if API_SERVER_AVAILABLE:
                    # Sync instance fields from newly-saved settings before toggling
                    _old_host = self._api_server_host
                    _old_port = self._api_server_port
                    self._api_server_enabled = bool(
                        self.settings.get("api_server_enabled", False)
                    )
                    self._api_server_host = self.settings.get(
                        "api_server_host", "127.0.0.1"
                    )
                    self._api_server_port = int(
                        self.settings.get("api_server_port", 8080)
                    )
                    # If host/port changed, tear down the old server so _init_api_server
                    # will recreate it with the correct address on the next toggle.
                    if (
                        _old_host != self._api_server_host
                        or _old_port != self._api_server_port
                    ) and getattr(self, "_api_server", None):
                        try:
                            self._api_server.stop_server()
                        except Exception:
                            pass
                        self._api_server = None
                    self.toggle_api_server(self._api_server_enabled)

                # If new coin(s) were added, create their neural folders right away
                # (the trainer itself stays in the program folder).
                self._ensure_alt_coin_folders_and_trainer_on_startup()

                # Refresh all coin-driven UI (dropdowns + chart tabs)
                self._refresh_coin_dependent_ui(prev_coins)
                if retrain_was != (
                    self.settings["training_auto_enabled"],
                    self.settings["training_auto_interval_hours"],
                ):
                    self._resume_auto_retrains()

                # Refresh exchange system with new settings
                self.refresh_exchange_settings()

                messagebox.showinfo("Saved", "Settings saved.")
                win.destroy()

            except Exception as e:
                messagebox.showerror("Error", f"Failed to save settings:\n{e}")

        ttk.Button(btns, text="Save", command=save).pack(side="left")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="left", padx=8)

    # ---- Exchange System Management ----

    def _init_exchange_system(self):
        """Initialize the multi-exchange system"""
        try:
            # Initialize exchange configuration
            config_manager = ExchangeConfigManager()

            # Create multi-exchange manager
            self._multi_exchange = MultiExchangeManager(config_manager)

            # Start checking exchange status in background
            threading.Thread(
                target=self._check_exchange_status_worker, daemon=True
            ).start()

        except Exception as e:
            self._exchange_status = {
                "status": "check failed",
                "details": f"Failed to initialize: {str(e)}",
                "tone": "bad",
            }
            print(f"Exchange system initialization error: {e}")

    def _init_api_server(self):
        """Initialize the public API server"""
        if not API_SERVER_AVAILABLE:
            print("API Server not available - install flask and flask-cors")
            return

        try:
            self._api_server = create_api_server(
                hub_data_dir=self.hub_dir,
                port=self._api_server_port,
                host=self._api_server_host,
                books_dir=self._books_dir,
            )

            if self._api_server_enabled:
                self._api_server.start_server()
                print(
                    f"Public API server started at http://{self._api_server_host}:{self._api_server_port}"
                )

        except Exception as e:
            print(f"Failed to initialize API server: {e}")
            self._api_server = None

    def toggle_api_server(self, enabled: bool):
        """Toggle API server on/off"""
        if not API_SERVER_AVAILABLE:
            return False

        if enabled and not self._api_server:
            self._init_api_server()
            return self._api_server is not None
        elif enabled and self._api_server and not self._api_server.is_running():
            self._api_server.start_server()
            return True
        elif not enabled and self._api_server and self._api_server.is_running():
            self._api_server.stop_server()
            return True
        return False

    def get_api_server_status(self) -> dict:
        """Get current API server status"""
        if not API_SERVER_AVAILABLE:
            return {"status": "unavailable", "message": "Flask not installed"}

        if not self._api_server:
            return {"status": "disabled", "message": "API server not initialized"}

        if self._api_server.is_running():
            return {
                "status": "running",
                "url": f"http://{self._api_server_host}:{self._api_server_port}",
                "message": "API server is operational",
            }
        else:
            return {"status": "stopped", "message": "API server is stopped"}

    def _exchange_status_once(
        self, primary_exchange: str, trading: Optional[TradingSettings] = None
    ) -> Tuple[str, str, str]:
        """One status check for the Exchange line: ``(status, details, tone)``.

        In live mode it names the live broker, "(live orders)", "(preview orders)"
        or "(testnet orders)"; in paper mode the primary exchange's name alone. It
        asks the exchange's own connector for a public BTC price (no key needed).
        ``tone`` colours the line: "ok", "warn" (no price) or "bad"."""
        live = trading is not None and trading.is_live and trading.active_broker
        if live:
            primary_exchange = trading.active_broker
        name = exchange_name(primary_exchange)
        try:
            import pt_exchanges  # noqa: F401  (registers the connectors)
            from pt_exchange_abstraction import ExchangeFactory, ExchangeType

            cache = getattr(self, "_status_exchanges", None)
            if cache is None:
                cache = self._status_exchanges = {}
            exchange = cache.get(primary_exchange)
            if exchange is None:
                # empty credentials: given none, the factory would read the saved ones
                exchange = ExchangeFactory.get_exchange(
                    ExchangeType(primary_exchange), api_key="", api_secret=""
                )
                cache[primary_exchange] = exchange
            price = float(exchange.get_current_price("BTC-USD"))
        except Exception as exc:
            return (
                f"{name} (no prices)",
                f"No price from {name}: {str(exc)[:160]}",
                "bad",
            )
        if price <= 0:
            return (
                f"{name} (no prices)",
                f"{name} answered but gave no price",
                "warn",
            )
        if not live:
            return (
                name,
                f"Prices OK | BTC ${price:,.2f} | the primary exchange for market data",
                "ok",
            )
        if not getattr(exchange, "SUPPORTS_LIVE_ORDERS", False):
            return (
                f"{name} (no live orders)",
                f"Prices OK | BTC ${price:,.2f} | this version cannot place orders on "
                f"{name}",
                "bad",
            )
        orders = (
            "testnet orders"
            if trading.uses_testnet
            else "preview orders" if trading.uses_preview else "live orders"
        )
        return f"{name} ({orders})", f"Prices OK | BTC ${price:,.2f} | {orders}", "ok"

    def _check_exchange_status_worker(self):
        """Background worker to check exchange connectivity. It only sets
        ``_exchange_status``: Tk may be touched from the main thread alone, and
        ``_tick`` shows the status there on every tick. It ends when the hub is
        destroyed."""
        stop = self._stop_background
        while not stop.is_set():
            try:
                if not self._multi_exchange:
                    stop.wait(5)
                    continue

                primary_exchange = self._primary_exchange()
                region = self.settings.get("region", "us")
                trading = getattr(self, "_trading", None)
                live_broker = (
                    trading.active_broker if trading and trading.is_live else None
                )

                # Skip if no primary exchange (or, live, no broker) is configured
                if not primary_exchange and not live_broker:
                    self._exchange_status = {
                        "status": "none configured",
                        "details": "Configure API credentials in Settings to enable trading",
                        "tone": "warn",
                    }
                    stop.wait(30)
                    continue

                status, details, tone = self._exchange_status_once(
                    primary_exchange or live_broker, trading
                )

                # Update status
                self._exchange_status = {
                    "status": status,
                    "details": details,
                    "tone": tone,
                }

            except Exception as e:
                self._exchange_status = {
                    "status": "check failed",
                    "details": f"Status check failed: {str(e)}",
                    "tone": "bad",
                }

            # Check every 30 seconds
            stop.wait(30)

    def _update_exchange_status_display(self):
        """Update the exchange status label in the GUI"""
        try:
            if hasattr(self, "lbl_exchange"):
                # the colour says the state ("Exchange:" is the grey key beside it)
                tone = self._exchange_status.get("tone", "wait")
                p = ui_theme.active_palette()
                colour = {
                    "ok": p["ACCENT2"],
                    "warn": ui_tokens.STATUS["warn"],
                    "bad": ui_tokens.STATUS["bad"],
                }.get(tone, p["MUTED"])
                self.lbl_exchange.config(
                    text=self._exchange_status["status"], foreground=colour
                )

                # Set tooltip with details if available
                if self._exchange_status.get("details"):
                    # Simple tooltip approach - could be enhanced with proper tooltip widget
                    self.lbl_exchange.bind(
                        "<Button-1>",
                        lambda e: messagebox.showinfo(
                            "Exchange Status", self._exchange_status["details"]
                        ),
                    )
        except Exception:
            pass

    def _sync_exchange_choice(self) -> None:
        """Write the Settings window's region and primary exchange into the shared
        exchange config (``trading_config.json``), which the neural runner, the
        trainers and the trader read. ``gui_settings.json`` is the hub's own copy;
        without this the processes kept an old primary (e.g. binance)."""
        if not EXCHANGE_SUPPORT_AVAILABLE:
            return
        region = str(self.settings.get("region", "") or "").strip().upper()
        primary = str(self.settings.get("primary_exchange", "") or "").strip().lower()
        if not region and not primary:
            return
        try:
            manager = ExchangeConfigManager()
            config = manager.load_config() or manager.create_default_config(
                region or "GLOBAL"
            )
            changed = False
            if region and config.user_region != region:
                config.user_region = region
                changed = True
            # the chosen primary is also enabled there, or it would not be connected
            if primary and manager.set_primary_exchange(primary):
                changed = True
            if changed:
                manager.save_config(config)
        except Exception as e:
            print(f"Could not save the exchange choice for the runner and trader: {e}")

    def _primary_exchange(self) -> str:
        """The primary exchange: the one chosen in Settings, else the one the runner,
        trainers and trader use (``trading_config.json``: a new install's default),
        else ""."""
        chosen = str(self.settings.get("primary_exchange", "") or "").strip().lower()
        if chosen or not EXCHANGE_SUPPORT_AVAILABLE:
            return chosen
        try:
            config = ExchangeConfigManager().load_config()
        except Exception:
            return ""
        return str(config.primary_exchange or "").strip().lower() if config else ""

    @staticmethod
    def _primary_exchange_choices(current: str) -> List[str]:
        """The exchanges Settings offers as the primary: every exchange that serves
        prices, alphabetically, and the current choice even when it does not."""
        names = (
            ExchangeFactory.market_data_exchanges()
            if EXCHANGE_SUPPORT_AVAILABLE
            else []
        )
        if current and current not in names:
            names.append(current)
        return names

    def refresh_exchange_settings(self):
        """Refresh exchange system with new settings - called when settings are saved"""
        if EXCHANGE_SUPPORT_AVAILABLE and self._multi_exchange:
            try:
                # Reinitialize with new settings
                self._init_exchange_system()
            except Exception as e:
                print(f"Error refreshing exchange settings: {e}")

    # ---- close ----

    def destroy(self) -> None:
        """Closing the hub also ends its background exchange status check."""
        stop = getattr(self, "_stop_background", None)
        if stop is not None:
            stop.set()
        super().destroy()

    def _on_close(self) -> None:
        # Don’t force kill; just stop if running (you can change this later)
        try:
            self.stop_all_scripts()
        except Exception:
            pass
        self.destroy()


def _show_startup_error(message: str) -> None:
    """Print ``message`` and, when Tk can open a window, show it in an error box."""
    print(f"PowerTraderAI cannot start. {message}", file=sys.stderr)
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("PowerTraderAI cannot start", message, parent=root)
        root.destroy()
    except Exception:  # no display, or Tcl/Tk not usable: the printed message is enough
        pass


def main():
    """Entry point for console script installation."""
    # Before the window opens: without platformdirs the hub cannot find its
    # folders and would stop later with a traceback.
    try:
        pt_paths.check_dependencies()
    except pt_paths.MissingDependency as exc:
        _show_startup_error(str(exc))
        sys.exit(1)
    app = PowerTraderHub()
    app.mainloop()


if __name__ == "__main__":
    main()
