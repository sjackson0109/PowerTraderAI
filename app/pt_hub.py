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
import urllib.error
import urllib.request
import warnings
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple

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
import position_sizing
import pt_paths
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
from strategies.settings import read_strategy_settings
from trading_mode import (
    PaperBookError,
    PaperBookInvalid,
    TradingSettings,
    paper_book_path,
    read_paper_book,
    read_trading_settings,
)
from trading_mode_ui import TradingModeDialog, TradingModeIndicator, pack_at_top

# Multi-exchange imports
try:
    from pt_exchange_abstraction import ExchangeType
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
    print("Warning: Holdings Management not available.")

# Portfolio Analytics imports
try:
    from portfolio_analytics_gui import PortfolioAnalyticsGUI

    # Temporarily disable portfolio analytics due to memory allocation issues
    PORTFOLIO_ANALYTICS_AVAILABLE = (
        False  # Set to False to avoid matplotlib memory errors
    )
except ImportError:
    PORTFOLIO_ANALYTICS_AVAILABLE = False
    print("Warning: Portfolio Analytics not available.")

# Advanced Order Types imports
try:
    from advanced_order_gui import AdvancedOrderGUI

    ADVANCED_ORDER_AVAILABLE = True
except ImportError:
    ADVANCED_ORDER_AVAILABLE = False
    print("Warning: Advanced Order Types not available.")

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
# Not a gap: how far down the chart status text sits to centre it on the tab buttons
STATUS_TEXT_DROP = 9
# The chart tab row (owner, 2026-10-14): the coin buttons sit TAB_BUTTON_GAP above
# the plot. Before, each coin chart had its status line in a row between them and
# the plot, CHART_STATUS_ROW_PADY above and below it (a chart on its own still
# has), and the gap under the buttons was FORMER_TAB_BUTTON_GAP.
TAB_BUTTON_GAP = SPACE["xs"]
FORMER_TAB_BUTTON_GAP = SPACE["sm"]
CHART_STATUS_ROW_PADY = SPACE["sm"]
# Short of room, the coin buttons narrow to this (and scroll) before the status line
MIN_TAB_BUTTONS_W = 60

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
            r"|NOT TRAINED|MODEL NOT VERIFIED|TRAINING - |skipped this pass"
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

DEFAULT_SETTINGS = {
    "main_neural_dir": "",
    "coins": ["BTC", "ETH", "XRP", "BNB", "DOGE"],
    "trade_start_level": 3,  # trade starts when long signal >= this level (1..7)
    # A new trade: this % of the account value, at least the exchange's minimum order
    "start_allocation_pct": position_sizing.DEFAULT_START_ALLOCATION_PCT,
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
    # FDS-MDL: the pattern-matching trainer (a port of upstream's); the old stub
    # pt_trainer.py is marked MOCK and refused unless allow_mock_trainer is set.
    "script_neural_trainer": "pt_pattern_trainer.py",
    "script_neural_runner2": "pt_thinker.py",
    "script_trader": "pt_trader.py",
    "auto_start_scripts": False,  # Disabled to prevent auto-triggering
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


class CandleChart(ttk.Frame):
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

        self.neural_status_label = ttk.Label(top, text="Neural: N/A")
        self.neural_status_label.pack(side="left")

        # Candlestick patterns (FDS-CHART-001): a status line (click: list of all
        # detections) and the Chart settings pop-out.
        self.patterns_status_label = ttk.Label(top, text="", cursor="hand2")
        self.patterns_status_label.pack(side="left", padx=(12, 0))

        # The Chart settings cog sits at the right end of the hub's tab row. No "Last:"
        # time: it was the neural level files' age, which says nothing about the
        # chart, whose candles are fetched on every refresh (owner, 2026-10-14).

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
        self._base_ylim: Optional[Tuple[float, float]] = None  # candle range + pad
        self._price_tags: List[Any] = []

        # axis names in the corners (owner, 2026-10-14): fit_layout() keeps room
        self._price_name, self._time_name = _corner_axis_names(
            self.fig, self.ax, f"{coin}USD", "Time"
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
        """Size the margins to the text actually drawn: the title, axis labels and tick
        labels, plus a strip on the right while price tags are shown. The pattern labels
        then go inside the plot, since the margins no longer leave room for them: the
        price range widens only as far as they need, and a label at either end is
        aligned inwards."""
        fig, ax = self.fig, self.ax
        layer = getattr(self, "pattern_layer", None)
        labels = layer.label_artists() if layer is not None else []
        for art in labels + self._price_tags:
            art.set_in_layout(False)
        if self._base_ylim:
            ax.set_ylim(*self._base_ylim)
        top = 1.0  # a strip above the plot for the price name
        try:
            name_px = self._price_name.get_window_extent(fig.canvas.get_renderer())
            gap_px = NAME_GAP_PT * fig.dpi / 72.0
            top = 1.0 - (name_px.height + gap_px) / float(fig.bbox.height)
        except Exception:
            pass
        # the time name sits right of the plot, like the price tags
        right = _fit_axes_beside(fig, self._price_tags + [self._time_name], top)
        if not (self._base_ylim and labels):
            return
        try:
            from pt_chart_patterns import room_for_labels

            height = float(ax.get_window_extent().height)
            ax.set_ylim(*room_for_labels(*self._base_ylim, layer.label_reach(), height))
        except Exception:
            pass
        _fit_axes(fig, right, top)  # the new range may change the price labels' width
        layer.keep_labels_inside()

    def _fit_and_draw(self) -> None:
        self._resize_after_id = None
        self.fit_layout()
        self.canvas.draw_idle()

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
        self._base_ylim = None

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
            self.fit_layout()
            self.canvas.draw_idle()
            return

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

        # Lock y-limits to candle range so overlay lines can go offscreen without expanding the chart.
        try:
            y_low = min(float(c["low"]) for c in candles)
            y_high = max(float(c["high"]) for c in candles)
            pad = (y_high - y_low) * 0.03
            if not math.isfinite(pad) or pad <= 0:
                pad = max(abs(y_low) * 0.001, 1e-6)
            self.ax.set_ylim(y_low - pad, y_high + pad)
            self._base_ylim = (y_low - pad, y_high + pad)
        except Exception:
            pass

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
            for key, y_val, tag, color in (
                ("ask", current_buy_price, "ASK", LINES["ask"]),
                ("bid", current_sell_price, "BID", LINES["bid"]),
                ("avg", avg_cost_basis, "AVG", LINES["avg"]),
                ("dca", dca_line_price, "DCA", LINES["dca"]),
                ("trail", trail_line, "SELL", LINES["trail"]),
            ):
                if not show(key) or y_val is None:
                    continue
                try:
                    price = float(y_val)
                except Exception:
                    continue
                if (not math.isfinite(price)) or price <= 0:
                    continue
                # A price beyond the plot is tagged at the nearest edge, with an arrow
                # towards it: its line is off the chart, and the margins are too
                # narrow to hold the tag where the price would be.
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

        # --- Trade dots (BUY / DCA / SELL) for THIS coin only ---
        try:
            trades = (
                _read_trade_history_jsonl(self.trade_history_path)
                if self.trade_history_path and show("trades")
                else []
            )
            if trades:
                candle_ts = [int(c["ts"]) for c in candles]  # oldest->newest
                t_min = float(candle_ts[0])
                t_max = float(candle_ts[-1])

                for tr in trades:
                    sym = str(tr.get("symbol", "")).upper()
                    base = sym.split("-")[0].strip() if sym else ""
                    if base != self.coin.upper().strip():
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

                    tts = tr.get("ts", None)
                    if tts is None:
                        continue
                    try:
                        tts = float(tts)
                    except Exception:
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
                            else (i - 1)
                        )

                    # y = trade price if present, else candle close
                    y = None
                    try:
                        p = tr.get("price", None)
                        if p is not None and float(p) > 0:
                            y = float(p)
                    except Exception:
                        y = None
                    if y is None:
                        try:
                            y = float(candles[idx].get("close", 0.0))
                        except Exception:
                            y = None
                    if y is None:
                        continue

                    x = idx
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
        except Exception:
            pass

        self.ax.set_xlim(-0.5, (len(candles) - 0.5) + 0.6)

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

        # Candlestick pattern labels (FDS-CHART-001): drawn last, placed by open time
        try:
            self.pattern_layer.update(candles, tf, folder, chart_cfg)
        except Exception:
            pass

        self.fit_layout()
        self.canvas.draw_idle()

        self.neural_status_label.config(
            text=(
                f"Neural: long={long_sig} short={short_sig} | levels L={len(long_levels)} S={len(short_levels)}"
                if show("neural_readout")
                else ""
            )
        )


# -----------------------------
# Account Value chart widget
# -----------------------------


class AccountValueChart(ttk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        history_path: str,
        trade_history_path: str,
        max_points: int = 250,
    ):
        super().__init__(parent)
        self.history_path = history_path
        self.trade_history_path = trade_history_path
        # Hard-cap to 250 points max (account value chart only)
        self.max_points = min(int(max_points or 0) or 250, 250)
        self._last_mtime: Optional[float] = None

        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=6)

        ttk.Label(top, text="Account value").pack(side="left")
        self.last_update_label = ttk.Label(top, text="Last: N/A")
        self.last_update_label.pack(side="right")

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
        _fit_axes(self.fig)
        self.canvas.draw_idle()

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

        if mtime is not None and self._last_mtime == mtime:
            return
        self._last_mtime = mtime

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
            self.last_update_label.config(text="Last: N/A")
            _fit_axes(self.fig)
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

        try:
            self.last_update_label.config(
                text=f"Last: {time.strftime('%H:%M:%S', time.localtime(points[-1][0]))}"
            )
        except Exception:
            self.last_update_label.config(text="Last: N/A")

        _fit_axes(self.fig)
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
        self._paper_mode = not self._trading.is_live

        # Force one and only one theme: dark (or paper-blue when enabled).
        self._apply_forced_dark_mode()

        self.settings = self._load_settings()

        # Header strip + banner widgets; built after the layout exists.
        self._mode_indicator: Optional[TradingModeIndicator] = None
        self._paper_banner: Optional[PaperBanner] = None
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
        # books in its own sub-directory (paper / testnet / live), so show the ones
        # for the mode this hub started in.
        trader_dir = os.path.join(self.hub_dir, self._trading.data_subdir)
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
                os.path.join(self.project_dir, self.settings["script_neural_runner2"])
            ),
        )
        self.proc_trader = ProcInfo(
            name="Trader",
            path=os.path.abspath(
                os.path.join(self.project_dir, self.settings["script_trader"])
            ),
        )

        # Resolved again on every Settings save (see _refresh_trainer_path).
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

        # Disabled auto-start to prevent accidental triggering
        # if bool(self.settings.get("auto_start_scripts", False)):
        #     self.start_all_scripts()

        # NOTE: API server auto-start is handled inside _init_api_server() above.
        # No second toggle here — that would risk a double-bind on the same port.

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
    def _user_folder_rows() -> List[Tuple[str, str]]:
        """(label, folder) for the Settings window's Paths section."""
        return [
            ("Config folder:", pt_paths.config_dir()),
            ("Data folder:", pt_paths.data_dir()),
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
        """Broker ids offered in the Trading Mode dialog: the exchanges that have
        an implementation registered, else every known exchange id."""
        try:
            import pt_exchanges  # noqa: F401  (registers exchange classes)
            from pt_exchange_abstraction import ExchangeFactory, ExchangeType

            registered = [e.value for e in ExchangeFactory.get_available_exchanges()]
            if registered:
                return registered
            return [e.value for e in ExchangeType]
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
        """
        Set ``proc_trainer_path`` from the ``script_neural_trainer`` setting,
        resolved against the (read-only) program folder. Called at start-up and
        on every Settings save, so a changed trainer script is used by the next
        training run without restarting the hub.
        """
        self.proc_trainer_path = os.path.abspath(
            os.path.join(self.project_dir, self.settings["script_neural_trainer"])
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
                # 438: the coin table's three columns with no spare strip (owner, 2026-10-14)
                desired_left = 438
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
        # buttons first: a narrow pane then clips the exchange text, not them
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
        ttk.Label(
            trader_row,
            text="Trader:",
            font=ui_tokens.font("caption"),
            foreground=p["MUTED"],
        ).pack(side="left")
        self.lbl_trader = ttk.Label(
            trader_row,
            text="stopped",
            font=ui_tokens.font("caption"),
            foreground=p["ACCENT2"],
        )
        self.lbl_trader.pack(side="left", padx=(2, 12))

        # Exchange status (click for details)
        self.lbl_exchange = ttk.Label(
            trader_row,
            text="Exchange: Checking...",
            font=ui_tokens.font("caption"),
            foreground=p["ACCENT2"],
            cursor="hand2",
        )
        self.lbl_exchange.pack(side="left")

        def _figure(row: int, col: int, key: str, attr: str) -> None:
            ttk.Label(
                acct_box,
                text=key,
                font=ui_tokens.font("caption"),
                foreground=p["MUTED"],
            ).grid(row=row, column=col, sticky="w", padx=(4, 6))
            value = ttk.Label(acct_box, text="N/A", font=ui_tokens.font("caption"))
            value.grid(row=row, column=col + 1, sticky="w", padx=(0, 8))
            setattr(self, attr, value)

        _figure(1, 0, "Value", "lbl_acct_total_value")
        _figure(1, 2, "Buying Power", "lbl_acct_buying_power")
        _figure(2, 0, "Holdings", "lbl_acct_holdings_value")
        _figure(2, 2, "% in Trade", "lbl_acct_percent_in_trade")
        _figure(3, 0, "DCA Single", "lbl_acct_dca_single")
        _figure(3, 2, "DCA Spread", "lbl_acct_dca_spread")
        _figure(4, 0, "Realized", "lbl_pnl")
        ttk.Frame(acct_box, height=2).grid(row=5, column=0, columnspan=4)

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
        charts_frame = ttk.LabelFrame(
            right_split, text="Charts (Signal lines overlaid)"
        )
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

        self.account_chart = AccountValueChart(
            acct_page,
            self.account_value_history_path,
            self.trade_history_path,
        )
        self.account_chart.pack(fill="both", expand=True)

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

        # ----------------------------
        # TAB 1: Current Trades
        # ----------------------------
        trades_tab = ttk.Frame(self.bottom_notebook)
        self.bottom_notebook.add(trades_tab, text="Current\nTrades")

        trades_frame = ttk.LabelFrame(trades_tab, text="Current Trades")
        trades_frame.pack(fill="both", expand=True, padx=6, pady=6)
        # Exposed so the paper-mode hook can pack a "PAPER TRADING" label
        # at the top of the trading section without re-walking the widget tree.
        self.trades_frame = trades_frame

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

        trades_table_wrap = ttk.Frame(trades_frame)
        trades_table_wrap.pack(fill="both", expand=True, padx=6, pady=6)

        self.trades_tree = ttk.Treeview(
            trades_table_wrap, columns=cols, show="headings", height=10
        )
        for c in cols:
            self.trades_tree.heading(c, text=header_labels.get(c, c))
            self.trades_tree.column(c, width=110, anchor="center", stretch=True)

        # Reasonable starting widths (they will be dynamically scaled on resize)
        self.trades_tree.column("coin", width=70)
        self.trades_tree.column("qty", width=95)
        self.trades_tree.column("value", width=110)
        self.trades_tree.column("next_dca", width=160)
        self.trades_tree.column("dca_stages", width=90)
        self.trades_tree.column("dca_24h", width=80)

        ysb = ttk.Scrollbar(
            trades_table_wrap, orient="vertical", command=self.trades_tree.yview
        )
        xsb = ttk.Scrollbar(
            trades_table_wrap, orient="horizontal", command=self.trades_tree.xview
        )
        self.trades_tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)

        self.trades_tree.pack(side="top", fill="both", expand=True)
        xsb.pack(side="bottom", fill="x")
        ysb.pack(side="right", fill="y")

        def _resize_trades_columns(*_):
            # Scale the initial column widths proportionally so the table always fits the current window.
            try:
                total_w = int(self.trades_tree.winfo_width())
            except Exception:
                return
            if total_w <= 1:
                return

            try:
                sb_w = int(ysb.winfo_width() or 0)
            except Exception:
                sb_w = 0

            avail = max(200, total_w - sb_w - 8)

            base = {
                "coin": 70,
                "qty": 95,
                "value": 110,
                "avg_cost": 110,
                "buy_price": 110,
                "buy_pnl": 110,
                "sell_price": 110,
                "sell_pnl": 110,
                "dca_stages": 90,
                "dca_24h": 80,
                "next_dca": 160,
                "trail_line": 110,
            }
            base_total = sum(base.get(c, 110) for c in cols) or 1
            scale = avail / base_total

            for c in cols:
                w = int(base.get(c, 110) * scale)
                self.trades_tree.column(c, width=max(60, min(420, w)))

        self.trades_tree.bind(
            "<Configure>", lambda e: self.after_idle(_resize_trades_columns)
        )
        self.after_idle(_resize_trades_columns)

        # ----------------------------
        # TAB 2: Long-term Holdings
        # ----------------------------
        lth_tab = ttk.Frame(self.bottom_notebook)
        self.bottom_notebook.add(lth_tab, text="Long-term\nHoldings")

        lth_frame = ttk.LabelFrame(
            lth_tab, text="Long-term Holdings (Manual/HODL Positions)"
        )
        lth_frame.pack(fill="both", expand=True, padx=6, pady=6)

        lth_cols = (
            "coin",
            "qty",
            "value",
            "avg_cost",
            "current_price",
            "total_pnl",
            "pnl_pct",
            "allocation",
        )

        lth_headers = {
            "coin": "Coin",
            "qty": "Quantity",
            "value": "Current Value",
            "avg_cost": "Avg Cost",
            "current_price": "Current Price",
            "total_pnl": "Total P&L",
            "pnl_pct": "P&L %",
            "allocation": "% of Portfolio",
        }

        lth_table_wrap = ttk.Frame(lth_frame)
        lth_table_wrap.pack(fill="both", expand=True, padx=6, pady=6)

        self.lth_tree = ttk.Treeview(
            lth_table_wrap, columns=lth_cols, show="headings", height=10
        )
        for c in lth_cols:
            self.lth_tree.heading(c, text=lth_headers.get(c, c))
            self.lth_tree.column(c, width=110, anchor="center", stretch=True)

        # Set reasonable column widths for LTH table
        self.lth_tree.column("coin", width=70)
        self.lth_tree.column("qty", width=100)
        self.lth_tree.column("value", width=110)
        self.lth_tree.column("avg_cost", width=90)
        self.lth_tree.column("current_price", width=90)
        self.lth_tree.column("total_pnl", width=100)
        self.lth_tree.column("pnl_pct", width=80)
        self.lth_tree.column("allocation", width=90)

        lth_ysb = ttk.Scrollbar(
            lth_table_wrap, orient="vertical", command=self.lth_tree.yview
        )
        lth_xsb = ttk.Scrollbar(
            lth_table_wrap, orient="horizontal", command=self.lth_tree.xview
        )
        self.lth_tree.configure(yscrollcommand=lth_ysb.set, xscrollcommand=lth_xsb.set)

        self.lth_tree.pack(side="top", fill="both", expand=True)
        lth_xsb.pack(side="bottom", fill="x")
        lth_ysb.pack(side="right", fill="y")

        # Trade history (now in its own tab)
        hist_tab = ttk.Frame(self.bottom_notebook)
        self.bottom_notebook.add(hist_tab, text="Trade\nHistory")

        hist_frame = ttk.LabelFrame(hist_tab, text="Trade History (Scroll)")
        hist_frame.pack(fill="both", expand=True, padx=6, pady=6)

        # Add filter/search controls for trade history
        hist_controls = ttk.Frame(hist_frame)
        hist_controls.pack(fill="x", padx=6, pady=(6, 0))

        ttk.Label(hist_controls, text="Filter:").pack(side="left")
        self.hist_filter_var = tk.StringVar()
        hist_filter_entry = ttk.Entry(
            hist_controls, textvariable=self.hist_filter_var, width=20
        )
        hist_filter_entry.pack(side="left", padx=(4, 8))

        ttk.Button(
            hist_controls, text="Clear", command=lambda: self.hist_filter_var.set("")
        ).pack(side="left")

        hist_wrap = ttk.Frame(hist_frame)
        hist_wrap.pack(fill="both", expand=True, padx=6, pady=6)

        self.hist_list = tk.Listbox(
            hist_wrap,
            height=10,
            bg=p["PANEL"],
            fg=p["FG"],
            selectbackground=p["SELECT_BG"],
            selectforeground=p["SELECT_FG"],
            font=ui_tokens.mono("small"),
        )

        # Add scrollbars for hist_list
        ysb2 = ttk.Scrollbar(hist_wrap, orient="vertical", command=self.hist_list.yview)
        xsb2 = ttk.Scrollbar(
            hist_wrap, orient="horizontal", command=self.hist_list.xview
        )
        self.hist_list.configure(yscrollcommand=ysb2.set, xscrollcommand=xsb2.set)

        self.hist_list.pack(side="left", fill="both", expand=True)
        ysb2.pack(side="right", fill="y")
        xsb2.pack(side="bottom", fill="x")

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
        # TAB 6: Holdings Management
        # ----------------------------
        self._create_holdings_management_tab()

        # ----------------------------
        # TAB 7: Portfolio Analytics
        # ----------------------------
        self._create_portfolio_analytics_tab()

        # ----------------------------
        # TAB 8: Advanced Order Types
        # ----------------------------
        self._create_advanced_order_tab()

        # ----------------------------
        # TAB 9: Real-time Market Data
        # ----------------------------
        self._create_market_data_tab()

        # ----------------------------
        # TAB 10: Portfolio Optimization
        # ----------------------------
        self._create_portfolio_optimization_tab()

        # ----------------------------
        # TAB 11: Backtesting Framework
        # ----------------------------
        self._create_backtesting_tab()

        # ----------------------------
        # TAB 12: Performance Attribution
        # ----------------------------
        self._create_performance_attribution_tab()

        # ----------------------------
        # TAB 13: Institutional Trading
        # ----------------------------
        self._create_institutional_trading_tab()

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

        # Create a placeholder LTH refresh method (will be implemented in Phase 3)
        self._refresh_lth_status = lambda: None

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

    def _create_order_management_tab(self):
        """Create the Order Management tab with order creation forms and monitoring."""
        p = ui_theme.active_palette()
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

            # Start monitoring if not already started
            self.order_manager.start_monitoring()

            # Main container with splitter
            order_paned = ttk.PanedWindow(order_tab, orient="horizontal")
            order_paned.pack(fill="both", expand=True, padx=6, pady=6)

            # Left panel: Order creation forms
            left_frame = ttk.LabelFrame(order_paned, text="Create Orders")
            order_paned.add(left_frame, weight=1)

            # Order type selection
            type_frame = ttk.Frame(left_frame)
            type_frame.pack(fill="x", padx=6, pady=6)

            ttk.Label(type_frame, text="Order Type:").pack(side="left")
            self.order_type_var = tk.StringVar(value="Stop Loss")
            order_type_combo = ttk.Combobox(
                type_frame,
                textvariable=self.order_type_var,
                values=["Stop Loss", "Take Profit", "DCA Order", "Conditional"],
                state="readonly",
                width=15,
            )
            order_type_combo.pack(side="left", padx=(6, 0))
            order_type_combo.bind("<<ComboboxSelected>>", self._on_order_type_changed)

            # Symbol input
            symbol_frame = ttk.Frame(left_frame)
            symbol_frame.pack(fill="x", padx=6, pady=(0, 6))

            ttk.Label(symbol_frame, text="Symbol:").pack(side="left")
            self.symbol_var = tk.StringVar(value="BTCUSDT")
            symbol_entry = ttk.Entry(
                symbol_frame, textvariable=self.symbol_var, width=12
            )
            symbol_entry.pack(side="left", padx=(6, 0))

            # Quantity input
            qty_frame = ttk.Frame(left_frame)
            qty_frame.pack(fill="x", padx=6, pady=(0, 6))

            ttk.Label(qty_frame, text="Quantity:").pack(side="left")
            self.quantity_var = tk.StringVar(value="0.001")
            qty_entry = ttk.Entry(qty_frame, textvariable=self.quantity_var, width=12)
            qty_entry.pack(side="left", padx=(6, 0))

            # Price input frame (dynamic content based on order type)
            self.price_frame = ttk.Frame(left_frame)
            self.price_frame.pack(fill="x", padx=6, pady=(0, 6))

            # Condition frame (for conditional orders)
            self.condition_frame = ttk.Frame(left_frame)
            self.condition_frame.pack(fill="x", padx=6, pady=(0, 6))

            # Initialize price controls for default order type
            self._update_order_form()

            # Create order button
            create_btn = ttk.Button(
                left_frame, text="Create Order", command=self._create_order_from_form
            )
            create_btn.pack(pady=10)

            # Right panel: Active orders and monitoring
            right_frame = ttk.LabelFrame(order_paned, text="Active Orders")
            order_paned.add(right_frame, weight=2)

            # Orders table
            orders_frame = ttk.Frame(right_frame)
            orders_frame.pack(fill="both", expand=True, padx=6, pady=6)

            order_cols = (
                "id",
                "symbol",
                "type",
                "side",
                "quantity",
                "price",
                "status",
                "conditions",
                "created",
            )

            order_headers = {
                "id": "Order ID",
                "symbol": "Symbol",
                "type": "Type",
                "side": "Side",
                "quantity": "Quantity",
                "price": "Price",
                "status": "Status",
                "conditions": "Conditions",
                "created": "Created",
            }

            self.orders_tree = ttk.Treeview(
                orders_frame, columns=order_cols, show="headings", height=10
            )
            for c in order_cols:
                self.orders_tree.heading(c, text=order_headers.get(c, c))
                self.orders_tree.column(c, width=80, anchor="center", stretch=True)

            # Set specific column widths
            self.orders_tree.column("id", width=100)
            self.orders_tree.column("symbol", width=80)
            self.orders_tree.column("type", width=90)
            self.orders_tree.column("side", width=50)
            self.orders_tree.column("quantity", width=80)
            self.orders_tree.column("price", width=80)
            self.orders_tree.column("status", width=70)
            self.orders_tree.column("conditions", width=120)
            self.orders_tree.column("created", width=120)

            # Scrollbars for orders table
            orders_ysb = ttk.Scrollbar(
                orders_frame, orient="vertical", command=self.orders_tree.yview
            )
            orders_xsb = ttk.Scrollbar(
                orders_frame, orient="horizontal", command=self.orders_tree.xview
            )
            self.orders_tree.configure(
                yscrollcommand=orders_ysb.set, xscrollcommand=orders_xsb.set
            )

            self.orders_tree.pack(side="top", fill="both", expand=True)
            orders_xsb.pack(side="bottom", fill="x")
            orders_ysb.pack(side="right", fill="y")

            # Order control buttons
            control_frame = ttk.Frame(right_frame)
            control_frame.pack(fill="x", padx=6, pady=(0, 6))

            ttk.Button(
                control_frame, text="Refresh", command=self._refresh_orders
            ).pack(side="left", padx=(0, 6))
            ttk.Button(
                control_frame,
                text="Cancel Selected",
                command=self._cancel_selected_order,
            ).pack(side="left", padx=(0, 6))

            # Notifications area
            notif_frame = ttk.LabelFrame(right_frame, text="Recent Notifications")
            notif_frame.pack(fill="x", padx=6, pady=(6, 0))

            # Create notification text widget with scrollbar
            notif_text_frame = ttk.Frame(notif_frame)
            notif_text_frame.pack(fill="x", padx=6, pady=6)

            self.notifications_text = tk.Text(
                notif_text_frame,
                height=4,
                wrap="word",
                bg=p["BG2"],
                fg=p["FG"],
                insertbackground=p["FG"],
            )
            notif_scroll = ttk.Scrollbar(
                notif_text_frame,
                orient="vertical",
                command=self.notifications_text.yview,
            )
            self.notifications_text.configure(yscrollcommand=notif_scroll.set)

            self.notifications_text.pack(side="left", fill="x", expand=True)
            notif_scroll.pack(side="right", fill="y")

            # Set initial pane sizes
            try:
                order_paned.pane(left_frame, minsize=300)
                order_paned.pane(right_frame, minsize=400)
            except Exception:
                # Fallback for different tkinter versions
                pass

            # Initial data load
            self._refresh_orders()
            self._refresh_notifications()

            # Schedule periodic updates
            self._schedule_order_updates()

        except Exception as e:
            print(f"Error creating order management tab: {e}")

    def _on_order_type_changed(self, event=None):
        """Handle order type selection change."""
        self._update_order_form()

    def _update_order_form(self):
        """Update the order form based on selected order type."""
        try:
            # Clear existing widgets
            for widget in self.price_frame.winfo_children():
                widget.destroy()
            for widget in self.condition_frame.winfo_children():
                widget.destroy()

            order_type = self.order_type_var.get()

            if order_type == "Stop Loss":
                # Stop price input
                ttk.Label(self.price_frame, text="Stop Price:").pack(side="left")
                self.stop_price_var = tk.StringVar(value="45000")
                ttk.Entry(
                    self.price_frame, textvariable=self.stop_price_var, width=12
                ).pack(side="left", padx=(6, 0))

                # Optional limit price
                ttk.Label(self.price_frame, text="Limit Price (optional):").pack(
                    side="left", padx=(12, 0)
                )
                self.limit_price_var = tk.StringVar()
                ttk.Entry(
                    self.price_frame, textvariable=self.limit_price_var, width=12
                ).pack(side="left", padx=(6, 0))

            elif order_type == "Take Profit":
                # Target price input
                ttk.Label(self.price_frame, text="Target Price:").pack(side="left")
                self.target_price_var = tk.StringVar(value="50000")
                ttk.Entry(
                    self.price_frame, textvariable=self.target_price_var, width=12
                ).pack(side="left", padx=(6, 0))

            elif order_type == "DCA Order":
                # DCA specific fields
                ttk.Label(self.price_frame, text="DCA Stage:").pack(side="left")
                self.dca_stage_var = tk.StringVar(value="1")
                ttk.Entry(
                    self.price_frame, textvariable=self.dca_stage_var, width=6
                ).pack(side="left", padx=(6, 0))

                ttk.Label(self.condition_frame, text="Neural Level:").pack(side="left")
                self.neural_level_var = tk.StringVar(value="7")
                ttk.Entry(
                    self.condition_frame, textvariable=self.neural_level_var, width=6
                ).pack(side="left", padx=(6, 0))

            elif order_type == "Conditional":
                # Condition type selection
                ttk.Label(self.condition_frame, text="Condition:").pack(side="left")
                self.condition_type_var = tk.StringVar(value="Price")
                condition_combo = ttk.Combobox(
                    self.condition_frame,
                    textvariable=self.condition_type_var,
                    values=["Price", "Neural Level", "Volume"],
                    state="readonly",
                    width=10,
                )
                condition_combo.pack(side="left", padx=(6, 0))

                # Operator selection
                ttk.Label(self.condition_frame, text="Operator:").pack(
                    side="left", padx=(12, 0)
                )
                self.condition_operator_var = tk.StringVar(value=">=")
                op_combo = ttk.Combobox(
                    self.condition_frame,
                    textvariable=self.condition_operator_var,
                    values=[">=", "<=", "==", ">", "<"],
                    state="readonly",
                    width=6,
                )
                op_combo.pack(side="left", padx=(6, 0))

                # Target value
                ttk.Label(self.condition_frame, text="Value:").pack(
                    side="left", padx=(12, 0)
                )
                self.condition_value_var = tk.StringVar(value="50000")
                ttk.Entry(
                    self.condition_frame,
                    textvariable=self.condition_value_var,
                    width=12,
                ).pack(side="left", padx=(6, 0))

        except Exception as e:
            print(f"Error updating order form: {e}")

    def _create_order_from_form(self):
        """Create an order based on form inputs."""
        try:
            if (
                not hasattr(self, "order_manager")
                or not self.order_manager.is_available
            ):
                messagebox.showerror("Error", "Order management system not available")
                return

            symbol = self.symbol_var.get().strip().upper()
            quantity = float(self.quantity_var.get())
            order_type = self.order_type_var.get()

            if not symbol or quantity <= 0:
                messagebox.showerror("Error", "Please enter valid symbol and quantity")
                return

            order_id = None

            if order_type == "Stop Loss":
                stop_price = float(self.stop_price_var.get())
                limit_price = None
                if (
                    hasattr(self, "limit_price_var")
                    and self.limit_price_var.get().strip()
                ):
                    limit_price = float(self.limit_price_var.get())

                from decimal import Decimal

                order_id = self.order_manager.create_stop_loss_order(
                    symbol,
                    Decimal(str(quantity)),
                    Decimal(str(stop_price)),
                    Decimal(str(limit_price)) if limit_price else None,
                )

            elif order_type == "Take Profit":
                target_price = float(self.target_price_var.get())
                from decimal import Decimal

                order_id = self.order_manager.create_take_profit_order(
                    symbol, Decimal(str(quantity)), Decimal(str(target_price))
                )

            elif order_type == "DCA Order":
                dca_stage = int(self.dca_stage_var.get())
                neural_level = int(self.neural_level_var.get())
                from decimal import Decimal

                order_id = self.order_manager.create_dca_order(
                    symbol, Decimal(str(quantity)), dca_stage, neural_level
                )

            elif order_type == "Conditional":
                # Create conditional order with specified conditions
                from decimal import Decimal

                from order_management_models import (
                    ConditionOperator,
                    ConditionType,
                    OrderSide,
                )
                from order_management_models import OrderType as OMOrderType

                order = self.order_manager.db.create_order(
                    symbol=symbol,
                    order_type=OMOrderType.CONDITIONAL,
                    side=OrderSide.BUY,  # Default to BUY for now
                    quantity=Decimal(str(quantity)),
                )
                order_id = order.id

                # Add condition
                condition_type_str = self.condition_type_var.get()
                condition_type = {
                    "Price": ConditionType.PRICE,
                    "Neural Level": ConditionType.NEURAL_LEVEL,
                    "Volume": ConditionType.VOLUME,
                }.get(condition_type_str, ConditionType.PRICE)

                operator_str = self.condition_operator_var.get()
                operator = {
                    ">=": ConditionOperator.GTE,
                    "<=": ConditionOperator.LTE,
                    "==": ConditionOperator.EQ,
                    ">": ConditionOperator.GT,
                    "<": ConditionOperator.LT,
                }.get(operator_str, ConditionOperator.GTE)

                target_value = Decimal(str(float(self.condition_value_var.get())))

                self.order_manager.db.add_condition_to_order(
                    order_id, condition_type, operator, target_value, symbol=symbol
                )

            if order_id:
                messagebox.showinfo(
                    "Success", f"Order created successfully: {order_id}"
                )
                self._refresh_orders()

                # Clear form
                self.symbol_var.set("BTCUSDT")
                self.quantity_var.set("0.001")
            else:
                messagebox.showerror("Error", "Failed to create order")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to create order: {str(e)}")

    def _refresh_orders(self):
        """Refresh the active orders table."""
        try:
            if (
                not hasattr(self, "order_manager")
                or not self.order_manager.is_available
            ):
                return

            # Clear existing items
            for item in self.orders_tree.get_children():
                self.orders_tree.delete(item)

            # Get active orders
            active_orders = self.order_manager.get_active_orders()

            for order in active_orders:
                # Format conditions text
                conditions_text = ""
                if order.get("conditions"):
                    cond_parts = []
                    for cond in order["conditions"]:
                        cond_parts.append(
                            f"{cond['condition_type'].value} {cond['operator'].value} {cond['target_value']}"
                        )
                    conditions_text = "; ".join(cond_parts)

                # Format created time
                created_at = order.get("created_at")
                created_str = created_at.strftime("%m/%d %H:%M") if created_at else ""

                # Insert into tree
                order_id_str = str(order["id"])
                self.orders_tree.insert(
                    "",
                    "end",
                    values=(
                        order_id_str[:8] + "...",  # Truncated ID
                        order["symbol"],
                        order["order_type"].value,
                        order["side"].value,
                        f"{order['quantity']}",
                        f"{order.get('price') or order.get('stop_price') or 'N/A'}",
                        order["status"].value,
                        (
                            conditions_text[:20] + "..."
                            if len(conditions_text) > 20
                            else conditions_text
                        ),
                        created_str,
                    ),
                )

        except Exception as e:
            print(f"Error refreshing orders: {e}")
            import traceback

            traceback.print_exc()

    def _cancel_selected_order(self):
        """Cancel the selected order."""
        try:
            selection = self.orders_tree.selection()
            if not selection:
                messagebox.showwarning(
                    "No Selection", "Please select an order to cancel"
                )
                return

            # Get the order ID from the selected item
            item_values = self.orders_tree.item(selection[0])["values"]
            truncated_id = item_values[0]

            # Find full order ID (this is a simplified approach)
            active_orders = self.order_manager.get_active_orders()
            full_order_id = None

            for order in active_orders:
                if str(order["id"]).startswith(truncated_id.replace("...", "")):
                    full_order_id = str(order["id"])
                    break

            if not full_order_id:
                messagebox.showerror("Error", "Could not find order to cancel")
                return

            # Confirm cancellation
            if messagebox.askyesno("Confirm", f"Cancel order {truncated_id}?"):
                if self.order_manager.cancel_order(full_order_id):
                    messagebox.showinfo("Success", "Order cancelled successfully")
                    self._refresh_orders()
                else:
                    messagebox.showerror("Error", "Failed to cancel order")

        except Exception as e:
            messagebox.showerror("Error", f"Error cancelling order: {str(e)}")
            import traceback

            traceback.print_exc()

    def _refresh_notifications(self):
        """Refresh the notifications display."""
        try:
            if (
                not hasattr(self, "order_manager")
                or not self.order_manager.is_available
            ):
                return

            notifications = self.order_manager.get_unread_notifications(limit=10)

            # Clear existing text
            self.notifications_text.delete(1.0, tk.END)

            if not notifications:
                self.notifications_text.insert(tk.END, "No new notifications")
                return

            # Add notifications to text widget
            for notif in notifications:
                created_at = notif.get("created_at")
                time_str = created_at.strftime("%H:%M:%S") if created_at else ""
                notification_line = (
                    f"[{time_str}] {notif['title']}: {notif['message']}\n"
                )
                self.notifications_text.insert(tk.END, notification_line)

            # Scroll to bottom
            self.notifications_text.see(tk.END)

        except Exception as e:
            print(f"Error refreshing notifications: {e}")
            import traceback

            traceback.print_exc()

    def _schedule_order_updates(self):
        """Schedule periodic updates for orders and notifications."""
        try:
            self._refresh_orders()
            self._refresh_notifications()

            # Schedule next update in 5 seconds
            self.after(5000, self._schedule_order_updates)

        except Exception as e:
            print(f"Error in scheduled order updates: {e}")

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

            # Initialize the research GUI
            config = {
                "llm": {
                    "api_key": "",  # Users will need to add their API key in settings
                    "model": "gpt-4",
                },
                "news": {
                    "sources": ["alpaca_news", "polygon_news"],
                    "update_interval": 300,
                },
                "auto_analysis_interval": 600,
            }

            self.research_gui = ResearchEngineGUI(research_tab, config)

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

    def _create_holdings_management_tab(self):
        """Create the Holdings Management tab for long-term portfolio management."""
        try:
            # Always create the tab first
            holdings_tab = ttk.Frame(self.bottom_notebook)
            self.bottom_notebook.add(holdings_tab, text="Holdings\nManagement")

            if not HOLDINGS_MANAGEMENT_AVAILABLE:
                # Show a message about unavailability
                ttk.Label(
                    holdings_tab,
                    text="Holdings Management Not Available\n\nRequired dependencies missing.\nPlease install: pip install sqlite3",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
                print("Holdings Management not available")
                return

            # Initialize the holdings GUI
            self.holdings_gui = HoldingsManagementGUI(holdings_tab)

            print("Holdings Management tab created successfully")

        except Exception as e:
            # If there's an error after tab creation, show error message in the tab
            try:
                for widget in holdings_tab.winfo_children():
                    widget.destroy()
                ttk.Label(
                    holdings_tab,
                    text=f"Holdings Management Error\n\n{str(e)}\n\nPlease check console for details.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
            except Exception:
                pass
            print(f"Error creating Holdings Management tab: {e}")
            import traceback

            traceback.print_exc()

    def _create_portfolio_analytics_tab(self):
        """Create the Portfolio Analytics tab for advanced portfolio analysis."""
        try:
            # Always create the tab first
            analytics_tab = ttk.Frame(self.bottom_notebook)
            self.bottom_notebook.add(analytics_tab, text="Portfolio\nAnalytics")

            if not PORTFOLIO_ANALYTICS_AVAILABLE:
                # Show a message about unavailability
                ttk.Label(
                    analytics_tab,
                    text="Portfolio Analytics Not Available\n\nRequired dependencies missing.\nPlease install: pip install pandas numpy matplotlib seaborn",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
                print("Portfolio Analytics not available")
                return

            # Initialize the analytics GUI
            self.analytics_gui = PortfolioAnalyticsGUI(analytics_tab)

            print("Portfolio Analytics tab created successfully")

        except Exception as e:
            # If there's an error after tab creation, show error message in the tab
            try:
                for widget in analytics_tab.winfo_children():
                    widget.destroy()
                ttk.Label(
                    analytics_tab,
                    text=f"Portfolio Analytics Error\n\n{str(e)}\n\nPlease check console for details.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
            except Exception:
                pass
            print(f"Error creating Portfolio Analytics tab: {e}")
            import traceback

            traceback.print_exc()

    def _create_advanced_order_tab(self):
        """Create the Advanced Order Types tab for sophisticated order management."""
        try:
            # Always create the tab first
            advanced_order_tab = ttk.Frame(self.bottom_notebook)
            self.bottom_notebook.add(advanced_order_tab, text="Advanced\nOrders")

            if not ADVANCED_ORDER_AVAILABLE:
                # Show a message about unavailability
                ttk.Label(
                    advanced_order_tab,
                    text="Advanced Order Types Not Available\n\nRequired dependencies missing.\nPlease install advanced order automation module.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
                print("Advanced Order Types not available")
                return

            # Initialize the advanced order GUI
            self.advanced_order_gui = AdvancedOrderGUI(advanced_order_tab)

            print("Advanced Order Types tab created successfully")

        except Exception as e:
            # If there's an error after tab creation, show error message in the tab
            try:
                for widget in advanced_order_tab.winfo_children():
                    widget.destroy()
                ttk.Label(
                    advanced_order_tab,
                    text=f"Advanced Orders Error\n\n{str(e)}\n\nPlease check console for details.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
            except Exception:
                pass
            print(f"Error creating Advanced Order Types tab: {e}")
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

            # Initialize the market data GUI
            self.market_data_gui = MarketDataGUI(market_data_tab)

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
        """Create the Portfolio Optimization tab for advanced portfolio management."""
        try:
            # Always create the tab first
            portfolio_opt_tab = ttk.Frame(self.bottom_notebook)
            self.bottom_notebook.add(portfolio_opt_tab, text="Portfolio\nOptimization")

            if not PORTFOLIO_OPTIMIZER_AVAILABLE:
                # Show a message about unavailability
                ttk.Label(
                    portfolio_opt_tab,
                    text="Portfolio Optimization Engine\n\nFor enhanced optimization features, install optional dependencies:\n\npython app/install_optional_deps.py\n\nCore features available without optional packages.",
                    font=ui_tokens.font("body"),
                    anchor="center",
                    justify="center",
                ).pack(expand=True, fill="both", padx=20, pady=20)
                print(
                    "Portfolio Optimization Engine available with limited functionality"
                )
                return

            # Initialize the portfolio optimization GUI
            self.portfolio_optimizer_gui = PortfolioOptimizerGUI(portfolio_opt_tab)

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

    def _schedule_auto_retrain(self, coin: str) -> None:
        """Schedule automatic re-training for a coin after the configured interval."""
        if not self.settings.get("training_auto_enabled", True):
            return

        interval_hours = self.settings.get("training_auto_interval_hours", 6)
        if interval_hours <= 0:
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

        # Schedule new auto-retrain
        interval_ms = int(
            interval_hours * 60 * 60 * 1000
        )  # Convert hours to milliseconds

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

        timer_id = root_widget.after(interval_ms, auto_retrain)
        self.auto_retrain_timers[coin] = timer_id

        print(f"DEBUG: Scheduled auto-retrain for {coin} in {interval_hours} hours")

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
        gap = 8  # between columns; none after the last, so three fit at 438 px
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

    def _fetch_binance_icon(self, coin_symbol: str) -> Optional[str]:
        """Fetch SVG icon from Binance CDN"""
        try:
            url = f"https://cdn.jsdelivr.net/gh/vadimmalykhin/binance-icons/crypto/{coin_symbol.lower()}.svg"
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    return response.read().decode("utf-8")
        except Exception as e:
            print(f"Failed to fetch icon for {coin_symbol}: {e}")
        return None

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
        """The trader this hub started is alive (the "Trader:" label's rule)."""
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
            self.trainer_status_lbl.config(
                text=(
                    f"running: {', '.join(running)}"
                    if running
                    else "(no trainers running)"
                )
            )

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
        if not data:
            self.lbl_pnl.config(text="N/A")
            return
        total = float(data.get("total_realized_profit_usd", 0.0))
        self.lbl_pnl.config(text=_fmt_money(total))

    def _refresh_trade_history(self) -> None:
        # mtime cache: avoid reading/parsing/rebuilding the list every tick
        try:
            mtime = os.path.getmtime(self.trade_history_path)
        except Exception:
            mtime = None

        if getattr(self, "_last_trade_history_mtime", object()) == mtime:
            return
        self._last_trade_history_mtime = mtime

        if not os.path.isfile(self.trade_history_path):
            self.hist_list.delete(0, "end")
            self.hist_list.insert("end", "(no trade_history.jsonl yet)")
            return

        # show last N lines
        try:
            with open(self.trade_history_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return

        lines = lines[-250:]  # cap for UI
        self.hist_list.delete(0, "end")
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                ts = obj.get("ts", None)
                tss = (
                    time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                    if isinstance(ts, (int, float))
                    else "?"
                )
                side = str(obj.get("side", "")).upper()
                tag = str(obj.get("tag", "") or "").upper()

                sym = obj.get("symbol", "")
                qty = obj.get("qty", "")
                px = obj.get("price", None)
                pnl = obj.get("realized_profit_usd", None)

                pnl_pct = obj.get("pnl_pct", None)

                px_txt = _fmt_price(px) if px is not None else "N/A"

                action = side
                if tag:
                    action = f"{side}/{tag}"

                txt = f"{tss} | {action:10s} {sym:5s} | qty={qty} | px={px_txt}"

                # Show the exact trade-time PnL%:
                # - DCA buys: show the BUY-side PnL (how far below avg cost it was when it bought)
                # - sells: show the SELL-side PnL (how far above/below avg cost it sold)
                show_trade_pnl_pct = None
                if side == "SELL":
                    show_trade_pnl_pct = pnl_pct
                elif side == "BUY" and tag == "DCA":
                    show_trade_pnl_pct = pnl_pct

                if show_trade_pnl_pct is not None:
                    try:
                        txt += f" | pnl@trade={_fmt_pct(float(show_trade_pnl_pct))}"
                    except Exception:
                        txt += f" | pnl@trade={show_trade_pnl_pct}"

                if pnl is not None:
                    try:
                        txt += f" | realized={float(pnl):+.2f}"
                    except Exception:
                        txt += f" | realized={pnl}"

                self.hist_list.insert("end", txt)
            except Exception:
                self.hist_list.insert("end", line)

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
                return (
                    f"{coin}: trained (green dot).\n"
                    "Its model is less than 14 days old, so the neural runner uses it.\n"
                    "Click to retrain (this replaces the model)."
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
        scrolls sideways when the panel is too narrow for it, and the Timeframe box
        anchored at the right end, never overlapping the buttons."""
        row = ttk.Frame(charts_frame)
        row.pack(fill="x", padx=(SPACE["edge"], SPACE["edge"]), pady=(SPACE["sm"], 0))
        self._chart_tabs_row = row
        # the Chart settings cog at the far right, the Timeframe box to its left
        cog = ttk.Button(
            row,
            text="\u2699",
            style="ChartCog.TButton",
            command=self.open_chart_settings,
        )
        cog.pack(side="right", anchor="n", pady=(0, TAB_BUTTON_GAP))
        ToolTip(cog, "Chart settings")
        self.chart_settings_button = cog
        box = ttk.Frame(row)
        ttk.Label(box, text="Timeframe:").pack(side="left", padx=(0, 4))
        combo = ttk.Combobox(
            box,
            values=self._settings_getter()["timeframes"],
            state="readonly",
            width=10,
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", self._on_chart_timeframe_selected)
        self._chart_tf_box, self.chart_tf_combo = box, combo
        self._pack_chart_tf_box()  # packed first, so the buttons get what is left
        # The buttons, then the selected chart's status line straight after them
        # (owner, 2026-10-14), in a strip only as wide as both. With less room the
        # buttons' column narrows first (it has the weight), down to
        # MIN_TAB_BUTTONS_W, and they scroll; the status line keeps its width.
        strip = ttk.Frame(row)
        strip.pack(side="left", anchor="n")
        strip.columnconfigure(0, weight=1, minsize=MIN_TAB_BUTTONS_W)
        self._chart_tabs_strip = strip
        self.chart_tabs_bar = ScrollingRow(strip)
        self.chart_tabs_bar.grid(row=0, column=0, sticky="new")
        self._chart_status_slot = ttk.Frame(strip)
        self._chart_status_slot.grid(
            row=0,
            column=1,
            sticky="nw",
            padx=(SPACE["sm"], 0),
            pady=(STATUS_TEXT_DROP, TAB_BUTTON_GAP),
        )

    def _show_chart_status(self, name: str) -> None:
        """The selected coin chart's status line, in the tab row. The account chart
        has none."""
        for coin, chart in getattr(self, "charts", {}).items():
            frame = getattr(chart, "status_frame", None)
            if frame is None or frame.master is not getattr(
                self, "_chart_status_slot", None
            ):
                continue
            try:
                if coin == name:
                    if frame.winfo_manager() != "pack":
                        frame.pack(side="left")
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

    def _pack_chart_tf_box(self) -> None:
        strip = getattr(self, "_chart_tabs_strip", None)
        before = {"before": strip} if strip is not None and strip.winfo_exists() else {}
        self._chart_tf_box.pack(
            side="right",
            anchor="n",
            padx=(SPACE["md"], SPACE["sm"]),
            pady=(SPACE["sm"], TAB_BUTTON_GAP),
            **before,
        )  # level with the buttons, also while the scrollbar shows

    def _show_chart_timeframe(self, name: str) -> None:
        """The Timeframe box shows the selected coin chart's timeframe. The account
        chart has none, so the box is hidden there."""
        box = getattr(self, "_chart_tf_box", None)
        if box is None:
            return
        chart = getattr(self, "charts", {}).get(name)
        try:
            if chart is None:
                box.pack_forget()
                return
            self.chart_tf_combo.set(chart.timeframe_var.get())
            if box.winfo_manager() != "pack":
                self._pack_chart_tf_box()
        except Exception:
            pass

    def _on_chart_timeframe_selected(self, event=None) -> None:
        chart = getattr(self, "charts", {}).get(
            getattr(self, "_current_chart_page", "")
        )
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

        self.account_chart = AccountValueChart(
            acct_page,
            self.account_value_history_path,
            self.trade_history_path,
        )
        self.account_chart.pack(fill="both", expand=True)

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
                on_saved=self._refresh_trader_status,
            )
        except Exception as e:
            messagebox.showerror(
                "Paper Account", f"Could not open the paper account: {e}"
            )
            return None

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
        p = ui_theme.active_palette()
        win = tk.Toplevel(self)
        win.title("Settings")
        # Big enough for the bottom buttons on most screens + still scrolls if someone resizes smaller.
        win.geometry("860x680")
        win.minsize(760, 560)
        win.configure(bg=p["BG"])

        # Scrollable settings content (auto-hides the scrollbar if everything fits),
        # using the same pattern as the Neural Levels scrollbar.
        viewport = ttk.Frame(win)
        viewport.pack(fill="both", expand=True, padx=12, pady=12)
        viewport.grid_rowconfigure(0, weight=1)
        viewport.grid_columnconfigure(0, weight=1)

        settings_canvas = tk.Canvas(
            viewport,
            bg=p["BG"],
            highlightthickness=1,
            highlightbackground=p["BORDER"],
            bd=0,
        )
        settings_canvas.grid(row=0, column=0, sticky="nsew")

        settings_scroll = ttk.Scrollbar(
            viewport,
            orient="vertical",
            command=settings_canvas.yview,
        )
        settings_scroll.grid(row=0, column=1, sticky="ns")

        settings_canvas.configure(yscrollcommand=settings_scroll.set)

        frm = ttk.Frame(settings_canvas)
        settings_window = settings_canvas.create_window((0, 0), window=frm, anchor="nw")

        def _update_settings_scrollbars(event=None) -> None:
            """Update scrollregion + hide/show the scrollbar depending on overflow."""
            try:
                c = settings_canvas
                win_id = settings_window

                c.update_idletasks()
                bbox = c.bbox(win_id)
                if not bbox:
                    settings_scroll.grid_remove()
                    return

                c.configure(scrollregion=bbox)
                content_h = int(bbox[3] - bbox[1])
                view_h = int(c.winfo_height())

                if content_h > (view_h + 1):
                    settings_scroll.grid()
                else:
                    settings_scroll.grid_remove()
                    try:
                        c.yview_moveto(0)
                    except Exception:
                        pass
            except Exception:
                pass

        def _on_settings_canvas_configure(e) -> None:
            # Keep the inner frame exactly the canvas width so wrapping is correct.
            try:
                settings_canvas.itemconfigure(settings_window, width=int(e.width))
            except Exception:
                pass
            _update_settings_scrollbars()

        settings_canvas.bind("<Configure>", _on_settings_canvas_configure, add="+")
        frm.bind("<Configure>", _update_settings_scrollbars, add="+")

        # Mousewheel scrolling when the mouse is over the settings window.
        def _wheel(e):
            try:
                if settings_scroll.winfo_ismapped():
                    settings_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass

        settings_canvas.bind("<Enter>", lambda _e: settings_canvas.focus_set(), add="+")
        settings_canvas.bind("<MouseWheel>", _wheel, add="+")  # Windows / Mac
        settings_canvas.bind(
            "<Button-4>", lambda _e: settings_canvas.yview_scroll(-3, "units"), add="+"
        )  # Linux
        settings_canvas.bind(
            "<Button-5>", lambda _e: settings_canvas.yview_scroll(3, "units"), add="+"
        )  # Linux

        # Make the entry column expand
        frm.columnconfigure(0, weight=0)  # labels
        frm.columnconfigure(1, weight=1)  # entries
        frm.columnconfigure(2, weight=0)  # browse buttons

        def add_row(r: int, label: str, var: tk.Variable, browse: Optional[str] = None):
            """
            browse: "dir" to attach a directory chooser, else None.
            """
            ttk.Label(frm, text=label).grid(
                row=r, column=0, sticky="w", padx=(0, 10), pady=6
            )

            ent = ttk.Entry(frm, textvariable=var)
            ent.grid(row=r, column=1, sticky="ew", pady=6)

            if browse == "dir":

                def do_browse():
                    picked = filedialog.askdirectory()
                    if picked:
                        var.set(picked)

                ttk.Button(frm, text="Browse", command=do_browse).grid(
                    row=r, column=2, sticky="e", padx=(10, 0), pady=6
                )
            else:
                # keep column alignment consistent
                ttk.Label(frm, text="").grid(
                    row=r, column=2, sticky="e", padx=(10, 0), pady=6
                )

        main_dir_var = tk.StringVar(value=self.settings["main_neural_dir"])
        coins_var = tk.StringVar(value=",".join(self.settings["coins"]))
        trade_start_level_var = tk.StringVar(
            value=str(self.settings.get("trade_start_level", 3))
        )
        start_alloc_pct_var = tk.StringVar(
            value=str(
                self.settings.get(
                    "start_allocation_pct", position_sizing.DEFAULT_START_ALLOCATION_PCT
                )
            )
        )
        max_coin_pct_var = tk.StringVar(
            value=str(
                self.settings.get(
                    "max_coin_allocation_pct",
                    position_sizing.DEFAULT_MAX_COIN_ALLOCATION_PCT,
                )
            )
        )
        dca_mult_var = tk.StringVar(value=str(self.settings.get("dca_multiplier", 2.0)))
        _dca_levels = self.settings.get(
            "dca_levels", DEFAULT_SETTINGS.get("dca_levels", [])
        )
        if not isinstance(_dca_levels, list):
            _dca_levels = DEFAULT_SETTINGS.get("dca_levels", [])
        dca_levels_var = tk.StringVar(value=",".join(str(x) for x in _dca_levels))
        max_dca_var = tk.StringVar(
            value=str(
                self.settings.get(
                    "max_dca_buys_per_24h",
                    DEFAULT_SETTINGS.get("max_dca_buys_per_24h", 2),
                )
            )
        )

        # --- Trailing PM settings (editable; hot-reload friendly) ---
        pm_no_dca_var = tk.StringVar(
            value=str(
                self.settings.get(
                    "pm_start_pct_no_dca",
                    DEFAULT_SETTINGS.get("pm_start_pct_no_dca", 5.0),
                )
            )
        )
        pm_with_dca_var = tk.StringVar(
            value=str(
                self.settings.get(
                    "pm_start_pct_with_dca",
                    DEFAULT_SETTINGS.get("pm_start_pct_with_dca", 2.5),
                )
            )
        )
        trailing_gap_var = tk.StringVar(
            value=str(
                self.settings.get(
                    "trailing_gap_pct", DEFAULT_SETTINGS.get("trailing_gap_pct", 0.5)
                )
            )
        )

        hub_dir_var = tk.StringVar(value=self.settings.get("hub_data_dir", ""))

        neural_script_var = tk.StringVar(value=self.settings["script_neural_runner2"])
        trainer_script_var = tk.StringVar(
            value=self.settings.get(
                "script_neural_trainer", DEFAULT_SETTINGS["script_neural_trainer"]
            )
        )
        trader_script_var = tk.StringVar(value=self.settings["script_trader"])

        ui_refresh_var = tk.StringVar(value=str(self.settings["ui_refresh_seconds"]))
        chart_refresh_var = tk.StringVar(
            value=str(self.settings["chart_refresh_seconds"])
        )
        candles_limit_var = tk.StringVar(value=str(self.settings["candles_limit"]))
        auto_start_var = tk.BooleanVar(
            value=bool(self.settings.get("auto_start_scripts", False))
        )

        r = 0
        add_row(r, "Main neural folder:", main_dir_var, browse="dir")
        r += 1
        add_row(r, "Coins (comma):", coins_var)
        r += 1
        add_row(r, "Trade start level (1-7):", trade_start_level_var)
        r += 1

        # Start allocation % and Max per coin %, each with its amount in dollars at the
        # last account value the trader reported
        ttk.Label(frm, text="Start allocation %:").grid(
            row=r, column=0, sticky="w", padx=(0, 10), pady=6
        )
        ttk.Entry(frm, textvariable=start_alloc_pct_var).grid(
            row=r, column=1, sticky="ew", pady=6
        )

        start_alloc_hint_var = tk.StringVar(value="")
        ttk.Label(frm, textvariable=start_alloc_hint_var).grid(
            row=r, column=2, sticky="w", padx=(10, 0), pady=6
        )

        def _pct(var):
            """A percentage typed as "1" or "1%" (None if it is not a number)."""
            try:
                return max(0.0, float((var.get() or "").strip().replace("%", "")))
            except ValueError:
                return None

        def _account_value() -> float:
            # the last account value in trader_status.json (no extra API calls)
            try:
                return float(getattr(self, "_last_total_account_value", 0.0) or 0.0)
            except (TypeError, ValueError):
                return 0.0

        def _update_start_alloc_hint(*_):
            pct, total_val = _pct(start_alloc_pct_var), _account_value()
            if pct is None or total_val <= 0.0:
                start_alloc_hint_var.set("")
                return
            entry = position_sizing.entry_usd(total_val, pct)
            start_alloc_hint_var.set(
                f"≈ {_fmt_money(entry)} per entry, at least the exchange minimum"
            )

        _update_start_alloc_hint()
        start_alloc_pct_var.trace_add("write", _update_start_alloc_hint)

        r += 1

        ttk.Label(frm, text="Max per coin %:").grid(
            row=r, column=0, sticky="w", padx=(0, 10), pady=6
        )
        ttk.Entry(frm, textvariable=max_coin_pct_var).grid(
            row=r, column=1, sticky="ew", pady=6
        )
        max_coin_hint_var = tk.StringVar(value="")
        ttk.Label(frm, textvariable=max_coin_hint_var).grid(
            row=r, column=2, sticky="w", padx=(10, 0), pady=6
        )

        def _update_max_coin_hint(*_):
            pct, total_val = _pct(max_coin_pct_var), _account_value()
            if pct is None or total_val <= 0.0:
                max_coin_hint_var.set("")
                return
            budget = position_sizing.coin_budget_usd(total_val, pct)
            max_coin_hint_var.set(
                f"≈ {_fmt_money(budget)} per coin with DCA; no DCA buy past it"
            )

        _update_max_coin_hint()
        max_coin_pct_var.trace_add("write", _update_max_coin_hint)

        r += 1

        add_row(r, "DCA levels (% list):", dca_levels_var)
        r += 1

        add_row(r, "DCA multiplier:", dca_mult_var)
        r += 1

        add_row(r, "Max DCA buys / coin (rolling 24h):", max_dca_var)
        r += 1

        add_row(r, "Trailing PM start % (no DCA):", pm_no_dca_var)
        r += 1
        add_row(r, "Trailing PM start % (with DCA):", pm_with_dca_var)
        r += 1
        add_row(r, "Trailing gap % (behind peak):", trailing_gap_var)
        r += 1

        add_row(r, "Hub data dir (optional):", hub_dir_var, browse="dir")
        r += 1

        ttk.Separator(frm, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=10
        )
        r += 1

        # --- Exchange Provider Settings ---
        ttk.Label(
            frm,
            text="🌍 Exchange Provider Settings",
            font=ui_tokens.font("body", "bold"),
        ).grid(row=r, column=0, columnspan=3, sticky="w", pady=(10, 5))
        r += 1

        # User region selection
        ttk.Label(frm, text="Your region:").grid(
            row=r, column=0, sticky="w", padx=(0, 10), pady=6
        )
        region_var = tk.StringVar(value=self.settings.get("region", "us"))
        region_combo = ttk.Combobox(
            frm,
            textvariable=region_var,
            values=["us", "eu", "global"],
            state="readonly",
        )
        region_combo.grid(row=r, column=1, sticky="ew", pady=6)
        ttk.Label(frm, text="").grid(row=r, column=2, sticky="e", padx=(10, 0), pady=6)
        r += 1

        # Primary exchange selection
        ttk.Label(frm, text="Primary exchange:").grid(
            row=r, column=0, sticky="w", padx=(0, 10), pady=6
        )
        primary_exchange_var = tk.StringVar(
            value=self.settings.get("primary_exchange", "")
        )

        # Exchange options based on region
        def update_exchange_options(*args):
            region = region_var.get()
            if region == "US":
                exchanges = ["binance", "coinbase", "kraken", "robinhood", "kucoin"]
            elif region in ["EU", "UK"]:
                exchanges = ["kraken", "coinbase", "binance", "bitstamp", "kucoin"]
            else:  # GLOBAL
                exchanges = [
                    "binance",
                    "kraken",
                    "kucoin",
                    "coinbase",
                    "robinhood",
                    "bybit",
                    "okx",
                ]

            exchange_combo.configure(values=exchanges)
            # Set default if current selection not in new list
            if primary_exchange_var.get() not in exchanges:
                primary_exchange_var.set(exchanges[0])

        exchange_combo = ttk.Combobox(
            frm, textvariable=primary_exchange_var, state="readonly"
        )
        exchange_combo.grid(row=r, column=1, sticky="ew", pady=6)
        region_var.trace("w", update_exchange_options)
        update_exchange_options()  # Initialize
        ttk.Label(frm, text="").grid(row=r, column=2, sticky="e", padx=(10, 0), pady=6)
        r += 1

        # Price comparison options
        price_comparison_var = tk.BooleanVar(
            value=self.settings.get("price_comparison_enabled", True)
        )
        ttk.Checkbutton(
            frm,
            text="Enable price comparison across exchanges",
            variable=price_comparison_var,
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(frm, text="").grid(row=r, column=2, sticky="e", padx=(10, 0), pady=6)
        r += 1

        auto_best_price_var = tk.BooleanVar(
            value=self.settings.get("auto_best_price", False)
        )
        ttk.Checkbutton(
            frm,
            text="Automatically use best price exchange",
            variable=auto_best_price_var,
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(frm, text="").grid(row=r, column=2, sticky="e", padx=(10, 0), pady=6)
        r += 1

        # Exchange setup button
        def open_exchange_setup():
            try:
                from exchange_config_gui import ExchangeConfigGUI

                exchange_gui = ExchangeConfigGUI(parent=self)
                messagebox.showinfo(
                    "Exchange Setup",
                    "Exchange configuration tool opened in separate window.",
                )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open exchange setup: {e}")

        ttk.Button(
            frm, text="Configure Exchange APIs...", command=open_exchange_setup
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(frm, text="").grid(row=r, column=2, sticky="e", padx=(10, 0), pady=6)
        r += 1

        # Paper account: the paper trader's book (balances and positions)
        ttk.Button(
            frm,
            text="Paper Account...",
            command=lambda: self.open_paper_account_dialog(win),
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(
            frm, text="starting balance, cash and positions for paper trading"
        ).grid(row=r, column=2, sticky="e", padx=(10, 0), pady=6)
        r += 1

        ttk.Separator(frm, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=10
        )
        r += 1

        add_row(r, "pt_thinker.py path:", neural_script_var)
        r += 1
        add_row(r, "pt_trainer.py path:", trainer_script_var)
        r += 1
        add_row(r, "pt_trader.py path:", trader_script_var)
        r += 1

        ttk.Separator(frm, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=10
        )
        r += 1

        # --- Paths (FDS-108a): where settings, data and logs live ---
        ttk.Label(
            frm, text="Paths (read-only program folder is not used for your files):"
        ).grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 4))
        r += 1
        for label, folder in self._user_folder_rows():
            ttk.Label(frm, text=label).grid(
                row=r, column=0, sticky="w", padx=(0, 10), pady=4
            )
            path_row = ttk.Frame(frm)
            path_row.grid(row=r, column=1, columnspan=2, sticky="ew", pady=4)
            path_row.columnconfigure(0, weight=1)
            path_entry = ttk.Entry(path_row)
            path_entry.insert(0, folder)
            path_entry.configure(state="readonly")
            path_entry.grid(row=0, column=0, sticky="ew")
            ttk.Button(
                path_row,
                text="Open folder",
                command=lambda f=folder: self._open_user_folder(f),
            ).grid(row=0, column=1, sticky="e", padx=(10, 0))
            r += 1

        ttk.Separator(frm, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=10
        )
        r += 1

        add_row(r, "UI refresh seconds:", ui_refresh_var)
        r += 1
        add_row(r, "Chart refresh seconds:", chart_refresh_var)
        r += 1
        add_row(r, "Candles limit:", candles_limit_var)
        r += 1

        # Chart overlays and candlestick patterns: their own pop-out (FDS-CHART-001)
        ttk.Label(frm, text="Chart overlays:").grid(row=r, column=0, sticky="w", pady=6)
        ttk.Button(
            frm,
            text="Chart settings\u2026",
            command=lambda: self.open_chart_settings(parent=win),
        ).grid(row=r, column=1, sticky="w", pady=6)
        r += 1

        # --- Public API Server Section ---
        ttk.Separator(frm, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=10
        )
        r += 1

        api_enabled_var = tk.BooleanVar(
            value=bool(self.settings.get("api_server_enabled", False))
        )
        api_host_var = tk.StringVar(
            value=self.settings.get("api_server_host", "127.0.0.1")
        )
        api_port_var = tk.StringVar(
            value=str(self.settings.get("api_server_port", 8080))
        )

        chk_api = ttk.Checkbutton(
            frm, text="Enable Public API Server", variable=api_enabled_var
        )
        chk_api.grid(row=r, column=0, columnspan=3, sticky="w", pady=(0, 5))
        r += 1

        add_row(r, "API Host:", api_host_var)
        r += 1
        add_row(r, "API Port:", api_port_var)
        r += 1

        # API Status and test button
        api_status_frame = ttk.Frame(frm)
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
        r += 1

        chk = ttk.Checkbutton(
            frm, text="Auto start scripts on GUI launch", variable=auto_start_var
        )
        chk.grid(row=r, column=0, columnspan=3, sticky="w", pady=(10, 0))
        r += 1

        # --- UI Theme and Notification Settings ---
        dark_theme_var = tk.BooleanVar(
            value=bool(self.settings.get("dark_theme", True))
        )
        notifications_var = tk.BooleanVar(
            value=bool(self.settings.get("training_notifications", True))
        )

        dark_theme_chk = ttk.Checkbutton(
            frm, text="Use dark theme (default: enabled)", variable=dark_theme_var
        )
        dark_theme_chk.grid(row=r, column=0, columnspan=3, sticky="w", pady=(10, 0))
        r += 1

        notif_chk = ttk.Checkbutton(
            frm, text="Enable training notifications", variable=notifications_var
        )
        notif_chk.grid(row=r, column=0, columnspan=3, sticky="w", pady=(5, 0))
        r += 1

        btns = ttk.Frame(frm)
        btns.grid(row=r, column=0, columnspan=3, sticky="ew", pady=12)
        btns.columnconfigure(0, weight=1)

        def save():
            try:
                # Track coins before changes so we can detect newly added coins
                prev_coins = set(
                    [
                        str(c).strip().upper()
                        for c in (self.settings.get("coins") or [])
                        if str(c).strip()
                    ]
                )

                self.settings["main_neural_dir"] = pt_paths.neural_dir(
                    main_dir_var.get().strip()
                )
                self.settings["coins"] = [
                    c.strip().upper() for c in coins_var.get().split(",") if c.strip()
                ]
                self.settings["trade_start_level"] = max(
                    1, min(int(float(trade_start_level_var.get().strip())), 7)
                )

                sap = (start_alloc_pct_var.get() or "").strip().replace("%", "")
                self.settings["start_allocation_pct"] = min(
                    100.0, max(0.0001, float(sap or 0.0))
                )
                mcp = (max_coin_pct_var.get() or "").strip().replace("%", "")
                self.settings["max_coin_allocation_pct"] = min(
                    100.0, max(0.1, float(mcp or 0.0))
                )

                dm = (dca_mult_var.get() or "").strip()
                try:
                    dm_f = float(dm)
                except Exception:
                    dm_f = float(
                        self.settings.get(
                            "dca_multiplier",
                            DEFAULT_SETTINGS.get("dca_multiplier", 2.0),
                        )
                        or 2.0
                    )
                if dm_f < 0.0:
                    dm_f = 0.0
                self.settings["dca_multiplier"] = dm_f

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

                md = (max_dca_var.get() or "").strip()
                try:
                    md_i = int(float(md))
                except Exception:
                    md_i = int(
                        self.settings.get(
                            "max_dca_buys_per_24h",
                            DEFAULT_SETTINGS.get("max_dca_buys_per_24h", 2),
                        )
                        or 2
                    )
                if md_i < 0:
                    md_i = 0
                self.settings["max_dca_buys_per_24h"] = md_i

                # --- Trailing PM settings ---
                try:
                    pm0 = float(
                        (pm_no_dca_var.get() or "").strip().replace("%", "") or 0.0
                    )
                except Exception:
                    pm0 = float(
                        self.settings.get(
                            "pm_start_pct_no_dca",
                            DEFAULT_SETTINGS.get("pm_start_pct_no_dca", 5.0),
                        )
                        or 5.0
                    )
                if pm0 < 0.0:
                    pm0 = 0.0
                self.settings["pm_start_pct_no_dca"] = pm0

                try:
                    pm1 = float(
                        (pm_with_dca_var.get() or "").strip().replace("%", "") or 0.0
                    )
                except Exception:
                    pm1 = float(
                        self.settings.get(
                            "pm_start_pct_with_dca",
                            DEFAULT_SETTINGS.get("pm_start_pct_with_dca", 2.5),
                        )
                        or 2.5
                    )
                if pm1 < 0.0:
                    pm1 = 0.0
                self.settings["pm_start_pct_with_dca"] = pm1

                try:
                    tg = float(
                        (trailing_gap_var.get() or "").strip().replace("%", "") or 0.0
                    )
                except Exception:
                    tg = float(
                        self.settings.get(
                            "trailing_gap_pct",
                            DEFAULT_SETTINGS.get("trailing_gap_pct", 0.5),
                        )
                        or 0.5
                    )
                if tg < 0.0:
                    tg = 0.0
                self.settings["trailing_gap_pct"] = tg

                self.settings["hub_data_dir"] = hub_dir_var.get().strip()

                # --- Exchange Provider Settings ---
                self.settings["region"] = region_var.get().strip()
                self.settings["primary_exchange"] = primary_exchange_var.get().strip()
                self.settings["price_comparison_enabled"] = bool(
                    price_comparison_var.get()
                )
                self.settings["auto_best_price"] = bool(auto_best_price_var.get())

                self.settings["script_neural_runner2"] = neural_script_var.get().strip()
                self.settings["script_neural_trainer"] = (
                    trainer_script_var.get().strip()
                )
                self.settings["script_trader"] = trader_script_var.get().strip()
                # The next training run uses the new trainer script (no restart).
                self._refresh_trainer_path()

                self.settings["ui_refresh_seconds"] = float(
                    ui_refresh_var.get().strip()
                )
                self.settings["chart_refresh_seconds"] = float(
                    chart_refresh_var.get().strip()
                )
                self.settings["candles_limit"] = int(
                    float(candles_limit_var.get().strip())
                )
                self.settings["auto_start_scripts"] = bool(auto_start_var.get())

                # --- API Server Settings ---
                self.settings["api_server_enabled"] = api_enabled_var.get()
                self.settings["api_server_host"] = api_host_var.get()
                try:
                    port = int(api_port_var.get())
                    self.settings["api_server_port"] = max(1, min(port, 65535))
                except ValueError:
                    self.settings["api_server_port"] = 8080

                # --- Dark Theme and Notifications ---
                self.settings["dark_theme"] = dark_theme_var.get()
                self.settings["training_notifications"] = notifications_var.get()

                self._save_settings()
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
                "status": "Error",
                "details": f"Failed to initialize: {str(e)}",
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

    def _exchange_status_once(self, primary_exchange: str) -> Tuple[str, str]:
        """One status check of the primary exchange: ``(status, details)``.

        It asks the exchange's own connector for a public BTC price (no key
        needed). The hub's MultiExchangeManager is never connected, so the old
        check always reported "Exchange not available". The details also say
        whether this version can trade live on that exchange: most connectors
        serve prices only (no balances or orders)."""
        name = primary_exchange.upper()
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
            return f"❌ {name}", f"No price from {primary_exchange}: {str(exc)[:160]}"
        if price <= 0:
            return f"⚠️ {name}", f"{primary_exchange} answered but gave no price"
        if getattr(exchange, "SUPPORTS_LIVE_ORDERS", False):
            return (
                f"✅ {name}",
                f"Prices OK | BTC ${price:,.2f} | live orders supported",
            )
        return (
            f"✅ {name} (prices only)",
            f"Prices OK | BTC ${price:,.2f} | this version cannot read balances or "
            f"place live orders on {primary_exchange}; paper trading works",
        )

    def _check_exchange_status_worker(self):
        """Background worker to check exchange connectivity. It only sets
        ``_exchange_status``: Tk may be touched from the main thread alone, and
        ``_tick`` shows the status there on every tick."""
        while True:
            try:
                if not self._multi_exchange:
                    time.sleep(5)
                    continue

                primary_exchange = self.settings.get("primary_exchange", "")
                region = self.settings.get("region", "us")

                # Skip if no primary exchange is configured
                if not primary_exchange:
                    self._exchange_status = {
                        "status": "No exchange configured",
                        "details": "Configure API credentials in Settings to enable trading",
                    }
                    time.sleep(30)
                    continue

                status, details = self._exchange_status_once(primary_exchange)

                # Update status
                self._exchange_status = {"status": status, "details": details}

            except Exception as e:
                self._exchange_status = {
                    "status": "Error",
                    "details": f"Status check failed: {str(e)}",
                }

            # Check every 30 seconds
            time.sleep(30)

    def _update_exchange_status_display(self):
        """Update the exchange status label in the GUI"""
        try:
            if hasattr(self, "lbl_exchange"):
                status_text = f"Exchange: {self._exchange_status['status']}"
                self.lbl_exchange.config(text=status_text)

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
            if primary and config.primary_exchange != primary:
                config.primary_exchange = primary
                changed = True
            if changed:
                manager.save_config(config)
        except Exception as e:
            print(f"Could not save the exchange choice for the runner and trader: {e}")

    def refresh_exchange_settings(self):
        """Refresh exchange system with new settings - called when settings are saved"""
        if EXCHANGE_SUPPORT_AVAILABLE and self._multi_exchange:
            try:
                # Reinitialize with new settings
                self._init_exchange_system()
            except Exception as e:
                print(f"Error refreshing exchange settings: {e}")

    # ---- close ----

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
