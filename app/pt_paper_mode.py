"""
Paper trading mode helpers for the PowerTrader hub.

Provides:
- Palette that paints the hub blue (instead of black) when paper mode is on,
  so the user can instantly see they are not trading real money.
- "PAPER TRADING" banner label that gets injected into the trading section.
- A sample-trade runner that pulls a live BTC price from Binance's public
  ticker endpoint and routes a simulated BUY then SELL through
  PaperTradingAccount.
- Persistence helper so the File-menu toggle survives a restart.

This module is deliberately small and self-contained so pt_hub.py changes
remain surgical. All side effects on the hub happen through the helper
functions exported here; pt_hub.py never reaches into Tk internals from a
paper-mode branch directly.
"""

from __future__ import annotations

import json
import os
import tkinter as tk
import urllib.error
import urllib.request
from decimal import Decimal
from tkinter import ttk
from typing import Any, Callable, Dict, Optional

from pt_paper_trading import OrderSide, OrderType, PaperTradingAccount

# --- Palettes -----------------------------------------------------------------
# Owner spec (PR #90 comment): "paper mode changes the CSS of the background.
# Say BLUE instead of BLACK." Tk has no CSS, so we mirror the dark palette key
# names and let the hub apply whichever one matches the current mode.

DARK_PALETTE: Dict[str, str] = {
    "BG": "#070B10",
    "BG2": "#0B1220",
    "PANEL": "#0E1626",
    "PANEL2": "#121C2F",
    "BORDER": "#243044",
    "FG": "#C7D1DB",
    "MUTED": "#8B949E",
    "ACCENT": "#00FF66",
    "ACCENT2": "#00E5FF",
    "SELECT_BG": "#17324A",
    "SELECT_FG": "#00FF66",
}

# Blue family for paper mode. Same key names so the same style code paths work.
# ACCENT swapped to a warm gold so "PAPER TRADING" pops against the blue.
PAPER_PALETTE: Dict[str, str] = {
    "BG": "#0A1B3A",
    "BG2": "#11264D",
    "PANEL": "#152E5C",
    "PANEL2": "#1B3870",
    "BORDER": "#2E4A82",
    "FG": "#E6EEF8",
    "MUTED": "#9AB0CC",
    "ACCENT": "#FFC400",
    "ACCENT2": "#FFE082",
    "SELECT_BG": "#23488A",
    "SELECT_FG": "#FFC400",
}


def get_palette(paper_mode: bool) -> Dict[str, str]:
    return PAPER_PALETTE if paper_mode else DARK_PALETTE


# --- Settings persistence -----------------------------------------------------
PAPER_MODE_SETTING_KEY = "paper_mode_enabled"
PAPER_MODE_BALANCE_KEY = "paper_mode_balance"


def is_paper_mode(settings: Optional[Dict[str, Any]]) -> bool:
    if not settings:
        return False
    return bool(settings.get(PAPER_MODE_SETTING_KEY, False))


# --- Live BTC price (Binance public ticker, no auth) -------------------------
BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"


def fetch_binance_btc_price(
    timeout: float = 5.0,
    url: str = BINANCE_TICKER_URL,
    opener: Optional[Callable[[str, float], Any]] = None,
) -> Optional[Decimal]:
    """
    Pull the current BTC/USDT price from Binance's public REST endpoint.

    Returns None on any failure - the sample runner falls back to the
    PaperTradingAccount's own MarketDataSimulator so the demo still works
    when offline. `opener` is overridable for tests.
    """
    try:
        if opener is None:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        else:
            payload = json.loads(opener(url, timeout))
        price = payload.get("price")
        if price is None:
            return None
        return Decimal(str(price))
    except (urllib.error.URLError, ValueError, KeyError, OSError):
        return None


# --- Sample-scenario runner ---------------------------------------------------
def run_sample_scenario(
    account: PaperTradingAccount,
    quantity: Decimal = Decimal("0.001"),
    symbol: str = "BTC",
    price_fetcher: Callable[[], Optional[Decimal]] = fetch_binance_btc_price,
) -> Dict[str, Any]:
    """
    Place a simulated BUY then SELL through the paper account, using a live
    BTC price when available. Mirrors the demo flow from the now-retired
    standalone demo_paper_trading.py but lives behind the hub's "Run sample"
    button.

    Returns a dict the GUI can render directly. Keys:
      starting_balance, final_balance, buy_price, sell_price, source
    """
    starting = account.cash_balance
    live_price = price_fetcher()
    source = "binance_public" if live_price is not None else "simulated"

    # Seed the simulator so BUY/SELL fills land near the live spot price
    # instead of the simulator's default $45k anchor.
    if live_price is not None:
        account.market_simulator.current_prices[symbol] = live_price

    buy_id = account.place_order(
        symbol=symbol,
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=quantity,
    )
    buy_order = account.orders[buy_id]

    sell_id = account.place_order(
        symbol=symbol,
        order_type=OrderType.MARKET,
        side=OrderSide.SELL,
        quantity=quantity,
    )
    sell_order = account.orders[sell_id]

    return {
        "source": source,
        "starting_balance": float(starting),
        "final_balance": float(account.cash_balance),
        "buy_price": float(buy_order.filled_price),
        "sell_price": float(sell_order.filled_price),
        "buy_status": buy_order.status.value,
        "sell_status": sell_order.status.value,
        "live_price": float(live_price) if live_price is not None else None,
    }


# --- Tk widgets ---------------------------------------------------------------
class PaperBanner(tk.Frame):
    """
    Top-of-window banner that screams PAPER TRADING. Visible only when
    paper mode is on. Single tk.Frame so we can pack/forget cheaply on
    toggle without rebuilding the layout.
    """

    def __init__(
        self,
        parent: tk.Misc,
        palette: Dict[str, str],
        on_run_sample: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        super().__init__(
            parent,
            bg=palette["ACCENT"],
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self._palette = palette

        label = tk.Label(
            self,
            text="PAPER TRADING",
            bg=palette["ACCENT"],
            fg=palette["BG"],
            font=("Segoe UI", 14, "bold"),
            padx=14,
            pady=4,
        )
        label.pack(side="left")

        self.price_var = tk.StringVar(value="Live BTC: --")
        price_lbl = tk.Label(
            self,
            textvariable=self.price_var,
            bg=palette["ACCENT"],
            fg=palette["BG"],
            font=("Segoe UI", 10),
            padx=10,
        )
        price_lbl.pack(side="left")

        run_btn = tk.Button(
            self,
            text="Run sample trade",
            command=on_run_sample,
            bg=palette["BG2"],
            fg=palette["ACCENT"],
            activebackground=palette["PANEL2"],
            activeforeground=palette["ACCENT2"],
            relief="flat",
            padx=10,
            pady=2,
        )
        run_btn.pack(side="right", padx=6, pady=2)

        self.result_var = tk.StringVar(value="")
        result_lbl = tk.Label(
            self,
            textvariable=self.result_var,
            bg=palette["ACCENT"],
            fg=palette["BG"],
            font=("Segoe UI", 9, "italic"),
            padx=8,
        )
        result_lbl.pack(side="right")

    def set_price(self, price: Optional[Decimal]) -> None:
        if price is None:
            self.price_var.set("Live BTC: offline (using sim)")
        else:
            self.price_var.set(f"Live BTC: ${float(price):,.2f}")

    def set_result(self, text: str) -> None:
        self.result_var.set(text)


def attach_trading_section_label(parent: tk.Misc, palette: Dict[str, str]) -> tk.Label:
    """
    Owner spec: "in the trading section, add the words 'PAPER TRADING'.
    In a contrasting font colour." Returns a tk.Label the caller packs above
    the trades table. Caller is responsible for destroying it on toggle off.
    """
    return tk.Label(
        parent,
        text="PAPER TRADING",
        bg=palette["BG"],
        fg=palette["ACCENT"],
        font=("Segoe UI", 12, "bold"),
        pady=2,
    )


# --- Style application -------------------------------------------------------
def apply_palette_to_style(
    root: tk.Misc, style: ttk.Style, palette: Dict[str, str]
) -> None:
    """
    Re-runs the subset of pt_hub's `_apply_forced_dark_mode` styling that is
    palette-driven, but using whichever palette was passed. Kept in sync with
    pt_hub.py by hand - if you add a new ttk style there, mirror it here.
    """
    try:
        root.configure(bg=palette["BG"])
    except tk.TclError:
        pass

    style.configure(".", background=palette["BG"], foreground=palette["FG"])

    for name in ("TFrame", "TLabel", "TCheckbutton", "TRadiobutton"):
        style.configure(name, background=palette["BG"], foreground=palette["FG"])

    style.configure(
        "TLabelframe",
        background=palette["BG"],
        foreground=palette["FG"],
        bordercolor=palette["BORDER"],
    )
    style.configure(
        "TLabelframe.Label",
        background=palette["BG"],
        foreground=palette["ACCENT"],
    )

    style.configure("TSeparator", background=palette["BORDER"])

    style.configure(
        "TButton",
        background=palette["BG2"],
        foreground=palette["FG"],
        bordercolor=palette["BORDER"],
        focusthickness=1,
        focuscolor=palette["ACCENT"],
        padding=(3, 2),
    )
    style.map(
        "TButton",
        background=[
            ("active", palette["PANEL2"]),
            ("pressed", palette["PANEL"]),
            ("disabled", palette["BG2"]),
        ],
        foreground=[
            ("active", palette["ACCENT"]),
            ("disabled", palette["MUTED"]),
        ],
    )


def install_classic_widget_defaults(root: tk.Misc, palette: Dict[str, str]) -> None:
    """
    Tk classic widgets read their colors at creation time via option_add.
    We call this once before the layout is built so newly-created Text,
    Listbox and Menu widgets pick up paper-mode colors.
    """
    try:
        root.option_add("*Text.background", palette["PANEL"])
        root.option_add("*Text.foreground", palette["FG"])
        root.option_add("*Text.insertBackground", palette["FG"])
        root.option_add("*Text.selectBackground", palette["SELECT_BG"])
        root.option_add("*Text.selectForeground", palette["SELECT_FG"])

        root.option_add("*Listbox.background", palette["PANEL"])
        root.option_add("*Listbox.foreground", palette["FG"])
        root.option_add("*Listbox.selectBackground", palette["SELECT_BG"])
        root.option_add("*Listbox.selectForeground", palette["SELECT_FG"])

        root.option_add("*Menu.background", palette["BG2"])
        root.option_add("*Menu.foreground", palette["FG"])
        root.option_add("*Menu.activeBackground", palette["SELECT_BG"])
        root.option_add("*Menu.activeForeground", palette["SELECT_FG"])
    except tk.TclError:
        pass


# --- Read settings without instantiating the hub ----------------------------
def read_paper_mode_from_disk(settings_path: str) -> bool:
    """
    Used by pt_hub before settings are loaded into self so the very first
    `_apply_forced_dark_mode` call can paint the window the right color
    immediately - no flash of dark theme before paper mode kicks in.
    """
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    return bool(data.get(PAPER_MODE_SETTING_KEY, False))


def settings_path_for(app_dir: str, filename: str = "gui_settings.json") -> str:
    return os.path.join(app_dir, filename)
