"""
Real-time Market Data GUI (Item 24)
User interface for monitoring real-time market data feeds

Coins are the ones in Settings (subscribed by default, on the primary exchange) and
any typed into a symbol box; every pair is shown in the connected exchange's own
format (``exchange_symbols``), every exchange by its proper name. What the feed
threads bring is shown from the Tk thread (a timer polls their queue); the timers
stop, and the feeds with them, when the tab is destroyed.
"""

import queue
import tkinter as tk
from datetime import datetime
from tkinter import messagebox as _messagebox
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional, Sequence

import exchange_symbols
import ui_table
import ui_tokens
from pt_exchange_abstraction import exchange_id, exchange_name
from ui_jobs import BackgroundJobs

try:
    from real_time_market_data import (
        MarketTicker,
        get_market_data_manager,
        initialize_market_data,
    )

    MARKET_DATA_AVAILABLE = True
except ImportError:
    MARKET_DATA_AVAILABLE = False
    MarketTicker = None  # Define fallback
    print("Warning: Real-time market data not available.")

try:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: Matplotlib not available. Charts disabled.")

# A value the exchange does not give (never shown as 0)
NA = "n/a"

# Price Charts: this many candles of the chosen timeframe, so the timeframe sets the
# time span (120 hours of 1h candles, 120 days of 1d candles)
CHART_BARS = 120
CHART_TIMEFRAMES = ("5m", "15m", "30m", "1h", "4h", "1d")


def _candle_style():
    """The candle colours and style chosen in Chart settings (gui_settings.json, read
    only): ({"up": colour, "down": colour}, hollow up candles)."""
    import json

    import chart_settings
    import pt_paths

    try:
        with open(pt_paths.gui_settings_file(), encoding="utf-8") as f:
            raw = json.load(f).get("chart")
    except (OSError, ValueError, AttributeError):
        raw = None
    cfg = chart_settings.normalize(raw)
    return chart_settings.palette(cfg), cfg["candle_style"] == "hollow_up"


def _price(value: Optional[float], signed: bool = False) -> str:
    """A price (or a change in price): more decimals the smaller it is."""
    if value is None:
        return NA
    size = abs(float(value))
    digits = 2 if size >= 100 else 4 if size >= 1 else 8
    return f"{float(value):{'+' if signed else ''},.{digits}f}"


def _percent(value: Optional[float], signed: bool = False, digits: int = 2) -> str:
    if value is None:
        return NA
    return f"{float(value):{'+' if signed else ''}.{digits}f}%"


def _amount(value: Optional[float]) -> str:
    """A quantity of a coin."""
    if value is None:
        return NA
    amount = float(value)
    return f"{amount:,.2f}" if abs(amount) >= 1000 else f"{amount:,.4f}"


REFRESH_MS = 500  # how often the tab shows what the feeds brought
COINS_MS = 5000  # how often the coins in Settings are compared with the subscriptions


class MarketDataGUI:
    """GUI for real-time market data monitoring.

    ``coins`` gives the coins in Settings (default: ``exchange_symbols.
    settings_coins``); ``manager`` is the MarketDataManager (default: the process's
    own); ``messagebox`` stands in for tkinter's in tests."""

    def __init__(
        self,
        parent: tk.Widget,
        coins: Optional[Callable[[], Sequence[str]]] = None,
        manager=None,
        messagebox=None,
        refresh_ms: int = REFRESH_MS,
    ):
        self.parent = parent
        self.market_manager = None
        self.update_queue = queue.Queue()
        self._coins = coins or exchange_symbols.settings_coins
        self._box = messagebox or _messagebox
        self._refresh_ms = refresh_ms
        self._afters: Dict[str, str] = {}
        self._pairs: Dict[str, str] = {}  # coin -> its pair as shown
        self._known: Dict[str, str] = {}  # a pair shown (upper case) -> its coin
        self._default_coins: List[str] = []  # subscribed because they are in Settings
        self.alive = True

        # Initialize market data manager if available
        if MARKET_DATA_AVAILABLE:
            try:
                self.market_manager = manager or get_market_data_manager()
                self.market_manager.add_update_callback(self.on_market_update)
                self.market_manager.start()
                print("Market data manager initialized successfully")
            except Exception as e:
                print(f"Error initializing market data manager: {e}")
                self.market_manager = None
                # Don't set MARKET_DATA_AVAILABLE to False globally,
                # just disable for this instance
        else:
            print("Market data module not available")

        self.setup_ui()
        if not MARKET_DATA_AVAILABLE:
            return
        self.main_frame.bind("<Destroy>", self._on_destroy, add="+")

        # The coins in Settings, subscribed on the primary exchange
        if self.market_manager:
            self.add_default_subscriptions()
        if refresh_ms:
            self._after("refresh", refresh_ms, self._refresh)
            self._after("coins", COINS_MS, self._follow_settings_coins)

    # ---- timers and shutdown ----

    def _after(self, name: str, ms: int, fn: Callable[[], None]) -> None:
        self._cancel(name)
        if not self.alive:
            return
        try:
            self._afters[name] = self.main_frame.after(
                int(ms), lambda: self._fire(name, fn)
            )
        except tk.TclError:
            self._afters.pop(name, None)

    def _fire(self, name: str, fn: Callable[[], None]) -> None:
        self._afters.pop(name, None)
        if self.alive:
            fn()

    def _cancel(self, name: str) -> None:
        after_id = self._afters.pop(name, None)
        if after_id is not None:
            try:
                self.main_frame.after_cancel(after_id)
            except tk.TclError:
                pass

    def _on_destroy(self, event) -> None:
        if event.widget is self.main_frame:
            self.cleanup()

    def _refresh(self) -> None:
        """Show what the feeds brought, then again in ``refresh_ms``."""
        self.process_updates()
        self._after("refresh", self._refresh_ms, self._refresh)

    def _follow_settings_coins(self) -> None:
        """Subscribe the coins added in Settings, unsubscribe the ones removed."""
        try:
            coins = self.coins()
            if coins != self._default_coins:
                for coin in [c for c in self._default_coins if c not in coins]:
                    self.market_manager.unsubscribe_symbol(coin)
                    self._remove_rows(coin)
                self._subscribe_defaults(
                    [c for c in coins if c not in self._default_coins]
                )
                self._default_coins = coins
                self.update_subscriptions_count()
        except Exception as e:
            print(f"Market data could not follow the coins in Settings: {e}")
        self._after("coins", COINS_MS, self._follow_settings_coins)

    # ---- coins, pairs and exchanges ----

    def coins(self) -> List[str]:
        """The coins in Settings, each once."""
        out: List[str] = []
        try:
            given = list(self._coins() or [])
        except Exception:
            given = []
        for raw in given:
            coin = exchange_symbols.coin_of(raw)
            if coin and coin not in out:
                out.append(coin)
        return out

    def _learn_pairs(self, coins: Sequence[str]) -> None:
        if self.market_manager:
            pairs = self.market_manager.market_pairs(coins)
        else:
            pairs = exchange_symbols.market_pairs(coins)
        for p in pairs:
            self._pairs[p.coin] = p.pair
            self._known[p.pair.upper()] = p.coin

    def pair_of(self, coin: str) -> str:
        """The coin's market as the connected exchange writes it (``BTC-USD`` on
        Coinbase): one format for every pair the tab shows."""
        coin = exchange_symbols.coin_of(coin)
        if coin and coin not in self._pairs:
            self._learn_pairs([coin])
        return self._pairs.get(coin, coin)

    def symbol_choices(self) -> List[str]:
        """The pairs of the coins in Settings, for the symbol boxes."""
        coins = self.coins()
        self._learn_pairs(coins)
        return [self._pairs[c] for c in coins if c in self._pairs]

    def coin_from(self, text: str) -> str:
        """The coin in a symbol box: a pair the tab showed, a coin, or any pair."""
        found = exchange_symbols.parse_symbols(text, self._known)
        return found[0] if found else ""

    def _symbol_box(self, parent: tk.Widget, var: tk.StringVar) -> ttk.Combobox:
        """A symbol box: the coins in Settings to choose from, any other typed in."""
        box = ttk.Combobox(parent, textvariable=var, width=15)
        box.configure(
            values=self.symbol_choices(),
            postcommand=lambda: box.configure(values=self.symbol_choices()),
        )
        if not var.get() and box.cget("values"):
            var.set(box.cget("values")[0])
        return box

    def exchange_choices(self) -> List[str]:
        """The exchanges in Settings by their proper names, primary first."""
        return [exchange_name(n) for n in self.exchange_names()]

    def _exchange_box(self, parent: tk.Widget, var: tk.StringVar) -> ttk.Combobox:
        names = self.exchange_choices()
        var.set(names[0] if names else "")
        return ttk.Combobox(
            parent, textvariable=var, width=15, values=names, state="readonly"
        )

    def setup_ui(self):
        """Setup the user interface"""
        if not MARKET_DATA_AVAILABLE:
            self.setup_fallback_ui()
            return

        self.main_frame = ttk.Frame(self.parent)
        self.main_frame.pack(fill="both", expand=True)

        # Create notebook for different views
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill="both", expand=True)

        # Market Overview Tab
        self.overview_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.overview_tab, text="Market\nOverview")
        self.setup_overview_tab()

        # Price Charts Tab
        if MATPLOTLIB_AVAILABLE:
            self.charts_tab = ttk.Frame(self.notebook)
            self.notebook.add(self.charts_tab, text="Price\nCharts")
            self.setup_charts_tab()

        # Order Books Tab
        self.orderbook_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.orderbook_tab, text="Order\nBooks")
        self.setup_orderbook_tab()

        # Arbitrage Tab
        self.arbitrage_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.arbitrage_tab, text="Arbitrage\nMonitor")
        self.setup_arbitrage_tab()

        # Data Feeds Tab
        self.feeds_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.feeds_tab, text="Data\nFeeds")
        self.setup_feeds_tab()

    def setup_fallback_ui(self):
        """Setup fallback UI when market data is not available"""
        frame = ttk.Frame(self.parent)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ttk.Label(
            frame, text="Real-time Market Data", font=ui_tokens.font("display", "bold")
        ).pack(pady=20)

        if not MARKET_DATA_AVAILABLE:
            ttk.Label(
                frame,
                text="⚠️ Real-time market data module not available",
                style="Warn.TLabel",
                font=ui_tokens.font("title"),
            ).pack(pady=10)
        else:
            ttk.Label(
                frame,
                text="⚠️ Market data dependencies missing",
                style="Warn.TLabel",
                font=ui_tokens.font("title"),
            ).pack(pady=10)

        ttk.Label(
            frame,
            text="Required for real-time market data:",
            font=ui_tokens.font("body", "bold"),
        ).pack(pady=5)

        deps = ["pip install pandas numpy"]
        for dep in deps:
            ttk.Label(frame, text=f"• {dep}", style="Muted.TLabel").pack()

        ttk.Label(
            frame,
            text="Install missing dependencies to enable real-time market data",
            style="Muted.TLabel",
            font=ui_tokens.font("body"),
        ).pack(pady=10)

    def setup_overview_tab(self):
        """Setup market overview tab"""
        # Control panel
        control_frame = ttk.LabelFrame(self.overview_tab, text="Controls")
        control_frame.pack(fill="x", padx=5, pady=5)

        # Symbol management
        symbol_frame = ttk.Frame(control_frame)
        symbol_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(symbol_frame, text="Symbol:").pack(side="left")
        self.symbol_var = tk.StringVar(master=self.overview_tab)
        self.symbol_box = self._symbol_box(symbol_frame, self.symbol_var)
        self.symbol_box.pack(side="left", padx=5)

        ttk.Label(symbol_frame, text="Exchange:").pack(side="left", padx=(10, 0))
        self.exchange_var = tk.StringVar(master=self.overview_tab)
        self._exchange_box(symbol_frame, self.exchange_var).pack(side="left", padx=5)

        ttk.Button(symbol_frame, text="Subscribe", command=self.subscribe_symbol).pack(
            side="left", padx=5
        )
        ttk.Button(
            symbol_frame, text="Unsubscribe", command=self.unsubscribe_symbol
        ).pack(side="left", padx=5)

        # Status indicators
        status_frame = ttk.Frame(control_frame)
        status_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(status_frame, text="Data Feeds:").pack(side="left")
        self.feed_status_label = ttk.Label(
            status_frame, text="Disconnected", style="Bad.TLabel"
        )
        self.feed_status_label.pack(side="left", padx=5)

        ttk.Label(status_frame, text="Active Subscriptions:").pack(
            side="left", padx=(20, 0)
        )
        self.subscriptions_count_label = ttk.Label(status_frame, text="0")
        self.subscriptions_count_label.pack(side="left", padx=5)

        # Market data table (ui_table: fitted columns, its own scrollbars, sortable)
        self.data_table = ui_table.DataTable(
            self.overview_tab,
            (
                "symbol",
                "exchange",
                "price",
                "change",
                "change_pct",
                "volume",
                "high",
                "low",
                "bid",
                "ask",
                "spread",
                "updated",
            ),
            {
                "symbol": "Symbol",
                "exchange": "Exchange",
                "price": "Price",
                "change": "Change 24h",
                "change_pct": "Change Pct 24h",
                "volume": "Volume 24h",
                "high": "High 24h",
                "low": "Low 24h",
                "bid": "Bid",
                "ask": "Ask",
                "spread": "Spread",
                "updated": "Updated",
            },
            key="market_data.overview",
            numeric=(
                "price",
                "change",
                "change_pct",
                "volume",
                "high",
                "low",
                "bid",
                "ask",
                "spread",
            ),
            empty_text="No market data yet",
        )
        self.data_table.pack(fill="both", expand=True)
        self.data_tree = self.data_table.tree

    def setup_charts_tab(self):
        """Setup price charts tab: candles of the chosen timeframe from the candle
        cache (the exchanges in Settings, primary first), with their volume."""
        # Chart controls
        chart_controls = ttk.LabelFrame(self.charts_tab, text="Chart Controls")
        chart_controls.pack(fill="x", padx=5, pady=5)

        ttk.Label(chart_controls, text="Symbol:").pack(side="left")
        self.chart_symbol_var = tk.StringVar(master=self.charts_tab)
        symbol_box = self._symbol_box(chart_controls, self.chart_symbol_var)
        symbol_box.pack(side="left", padx=5)
        symbol_box.bind("<<ComboboxSelected>>", lambda e: self.update_chart(), add="+")
        symbol_box.bind("<Return>", lambda e: self.update_chart(), add="+")

        ttk.Label(chart_controls, text="Timeframe:").pack(side="left", padx=(10, 0))
        self.timeframe_var = tk.StringVar(master=self.charts_tab, value="1h")
        timeframe_combo = ttk.Combobox(
            chart_controls,
            textvariable=self.timeframe_var,
            width=10,
            values=CHART_TIMEFRAMES,
            state="readonly",
        )
        timeframe_combo.pack(side="left", padx=5)
        timeframe_combo.bind(
            "<<ComboboxSelected>>", lambda e: self.update_chart(), add="+"
        )

        ttk.Button(chart_controls, text="Update Chart", command=self.update_chart).pack(
            side="left", padx=5
        )

        # Chart frame
        chart_frame = ttk.Frame(self.charts_tab)
        chart_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Create matplotlib figure: the axes are made for each chart (the volume
        # panel only when the candles have volume)
        self.figure = Figure(figsize=(12, 8), dpi=100)
        self.figure.patch.set_facecolor(ui_tokens.CHART["figure"])
        self.price_ax = None
        self.volume_ax = None
        self.chart_source: Optional[str] = None  # the exchange the candles came from
        self._chart_request: Optional[tuple] = None
        self._chart_message("")

        # Canvas
        self.canvas = FigureCanvasTkAgg(self.figure, chart_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # the candles are read off the Tk thread; drawn the first time the tab shows
        self.chart_jobs = BackgroundJobs(self.charts_tab, name="market-data-chart")
        self._chart_shown = False
        self.notebook.bind("<<NotebookTabChanged>>", self._on_subtab, add="+")

    def _on_subtab(self, _event=None) -> None:
        try:
            selected = self.notebook.select()
        except tk.TclError:
            return
        if (
            not self._chart_shown
            and getattr(self, "charts_tab", None) is not None
            and selected == str(self.charts_tab)
        ):
            self._chart_shown = True
            self.update_chart()

    def setup_orderbook_tab(self):
        """Setup order book tab"""
        # Symbol selection
        ob_controls = ttk.LabelFrame(self.orderbook_tab, text="Order Book Controls")
        ob_controls.pack(fill="x", padx=5, pady=5)

        ttk.Label(ob_controls, text="Symbol:").pack(side="left")
        self.ob_symbol_var = tk.StringVar(master=self.orderbook_tab)
        self._symbol_box(ob_controls, self.ob_symbol_var).pack(side="left", padx=5)

        ttk.Label(ob_controls, text="Exchange:").pack(side="left", padx=(10, 0))
        self.ob_exchange_var = tk.StringVar(master=self.orderbook_tab)
        self._exchange_box(ob_controls, self.ob_exchange_var).pack(side="left", padx=5)

        ttk.Button(
            ob_controls, text="Load Order Book", command=self.load_orderbook
        ).pack(side="left", padx=5)

        # Order book display, split into asks and bids
        ob_paned = ttk.PanedWindow(self.orderbook_tab, orient="horizontal")
        ob_paned.pack(fill="both", expand=True)

        # Asks (sells)
        asks_frame = ttk.LabelFrame(ob_paned, text="Asks (Sellers)")
        ob_paned.add(asks_frame, weight=1)

        self.asks_table = ui_table.DataTable(
            asks_frame,
            ("price", "quantity", "total"),
            {"price": "Price", "quantity": "Quantity", "total": "Total"},
            key="market_data.asks",
            numeric=("price", "quantity", "total"),
            empty_text="No asks yet",
        )
        self.asks_table.pack(fill="both", expand=True)
        self.asks_tree = self.asks_table.tree

        # Bids (buys)
        bids_frame = ttk.LabelFrame(ob_paned, text="Bids (Buyers)")
        ob_paned.add(bids_frame, weight=1)

        self.bids_table = ui_table.DataTable(
            bids_frame,
            ("price", "quantity", "total"),
            {"price": "Price", "quantity": "Quantity", "total": "Total"},
            key="market_data.bids",
            numeric=("price", "quantity", "total"),
            empty_text="No bids yet",
        )
        self.bids_table.pack(fill="both", expand=True)
        self.bids_tree = self.bids_table.tree

    def setup_arbitrage_tab(self):
        """Setup arbitrage monitoring tab"""
        # Arbitrage controls
        arb_controls = ttk.LabelFrame(self.arbitrage_tab, text="Arbitrage Monitor")
        arb_controls.pack(fill="x", padx=5, pady=5)

        ttk.Label(arb_controls, text="Min Profit %:").pack(side="left")
        self.min_profit_var = tk.StringVar(value="0.1")
        ttk.Entry(arb_controls, textvariable=self.min_profit_var, width=10).pack(
            side="left", padx=5
        )

        ttk.Button(
            arb_controls, text="Scan for Opportunities", command=self.scan_arbitrage
        ).pack(side="left", padx=10)

        self.auto_scan_var = tk.BooleanVar()
        ttk.Checkbutton(
            arb_controls, text="Auto Scan", variable=self.auto_scan_var
        ).pack(side="left", padx=5)

        # Arbitrage opportunities table
        arb_frame = ttk.LabelFrame(self.arbitrage_tab, text="Arbitrage Opportunities")
        arb_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.arb_table = ui_table.DataTable(
            arb_frame,
            (
                "symbol",
                "buy_exchange",
                "sell_exchange",
                "buy_price",
                "sell_price",
                "profit",
                "profit_pct",
                "updated",
            ),
            {
                "symbol": "Symbol",
                "buy_exchange": "Buy Exchange",
                "sell_exchange": "Sell Exchange",
                "buy_price": "Buy Price",
                "sell_price": "Sell Price",
                "profit": "Profit",
                "profit_pct": "Profit Pct",
                "updated": "Updated",
            },
            key="market_data.arbitrage",
            numeric=("buy_price", "sell_price", "profit", "profit_pct"),
            empty_text="No opportunities yet",
        )
        self.arb_table.pack(fill="both", expand=True)
        self.arb_tree = self.arb_table.tree

    def setup_feeds_tab(self):
        """Setup data feeds monitoring tab"""
        # Feed status
        feed_status_frame = ttk.LabelFrame(self.feeds_tab, text="Feed Status")
        feed_status_frame.pack(fill="x", padx=5, pady=5)

        feeds = self.exchange_names()  # the exchanges in Settings, primary first
        self.feed_indicators = {}

        for i, feed in enumerate(feeds):
            row = i // 2
            col = i % 2

            frame = ttk.Frame(feed_status_frame)
            frame.grid(row=row, column=col, sticky="w", padx=10, pady=5)

            self.feed_indicators[feed] = tk.Label(
                frame,
                text="●",
                foreground=ui_tokens.STATUS["bad"],
                font=ui_tokens.font("display"),
            )
            self.feed_indicators[feed].pack(side="left")

            ttk.Label(frame, text=feed).pack(side="left", padx=5)

        # Feed statistics
        stats_frame = ttk.LabelFrame(self.feeds_tab, text="Feed Statistics")
        stats_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.stats_table = ui_table.DataTable(
            stats_frame,
            (
                "exchange",
                "status",
                "messages_received",
                "last_message",
                "uptime",
                "errors",
            ),
            {
                "exchange": "Exchange",
                "status": "Status",
                "messages_received": "Messages Received",
                "last_message": "Last Message",
                "uptime": "Uptime",
                "errors": "Errors",
            },
            key="market_data.feed_statistics",
            numeric=("messages_received", "errors"),
            empty_text="No feed statistics yet",
        )
        self.stats_table.pack(fill="both", expand=True)
        self.stats_tree = self.stats_table.tree

    def exchange_names(self) -> List[str]:
        """The exchanges in Settings, primary first ([] without a market manager)."""
        try:
            return self.market_manager.exchange_names() if self.market_manager else []
        except Exception:
            return []

    def subscribe_symbol(self):
        """Subscribe to the coin in the symbol box on the chosen exchange."""
        coin = self.coin_from(self.symbol_var.get())
        exchange = exchange_id(self.exchange_var.get())

        if not coin:
            self._box.showerror("Error", "Please enter a symbol")
            return

        if not self.market_manager:
            self._box.showerror(
                "Error",
                "Market data manager not available.",
            )
            return

        try:
            self.market_manager.subscribe_symbol(coin, [exchange])
            self.update_subscriptions_count()
            self._box.showinfo(
                "Success",
                f"Subscribed to {self.pair_of(coin)} on {exchange_name(exchange)}",
            )
        except Exception as e:
            self._box.showerror("Error", f"Failed to subscribe: {e}")

    def unsubscribe_symbol(self):
        """Unsubscribe from the coin in the symbol box, on every exchange."""
        coin = self.coin_from(self.symbol_var.get())

        if not coin:
            self._box.showerror("Error", "Please enter a symbol")
            return

        if not self.market_manager:
            self._box.showerror(
                "Error",
                "Market data manager not available.",
            )
            return

        try:
            self.market_manager.unsubscribe_symbol(coin)
            self._remove_rows(coin)
            self.update_subscriptions_count()
            self._box.showinfo("Success", f"Unsubscribed from {self.pair_of(coin)}")
        except Exception as e:
            self._box.showerror("Error", f"Failed to unsubscribe: {e}")

    def add_default_subscriptions(self):
        """Subscribe the coins in Settings, each on the primary exchange (the next
        exchange in Settings order where the primary has no market for it)."""
        self._default_coins = self.coins()
        self._subscribe_defaults(self._default_coins)
        self.update_subscriptions_count()

    def _subscribe_defaults(self, coins: Sequence[str]) -> None:
        if not self.exchange_names():
            return
        for coin in coins:
            try:
                self.market_manager.subscribe_symbol(coin)
            except Exception as e:
                print(f"Failed to subscribe to {coin}: {e}")

    def subscribed(self) -> Dict[str, List[str]]:
        """Each subscribed coin and the exchanges asked for it."""
        if not self.market_manager:
            return {}
        return {
            exchange_symbols.coin_of(market): names
            for market, names in self.market_manager.aggregator.subscribed().items()
        }

    def update_subscriptions_count(self):
        """Update subscriptions count display"""
        count = len(self.subscribed())
        self.subscriptions_count_label.config(text=str(count))

        if count > 0:
            self.feed_status_label.config(text="Connected", style="Good.TLabel")
        else:
            self.feed_status_label.config(text="Disconnected", style="Bad.TLabel")

    def on_market_update(self, data_type: str, data: Any):
        """Handle market data updates (on a feed thread: queued for the Tk thread)"""
        self.update_queue.put((data_type, data))

    def process_updates(self) -> int:
        """Show the queued updates (on the Tk thread); returns how many there were."""
        shown = 0
        while True:
            try:
                data_type, data = self.update_queue.get_nowait()
            except queue.Empty:
                return shown
            try:
                if data_type == "ticker":
                    self.update_ticker_display(data)
                    shown += 1
            except tk.TclError:
                return shown  # the tab went
            except Exception as e:
                print(f"Error showing market data: {e}")

    def _remove_rows(self, coin: str) -> None:
        for iid in self.data_tree.get_children():
            if str(iid).split("|", 1)[0] == coin:
                self.data_tree.delete(iid)

    def update_ticker_display(self, ticker):
        """Update ticker display in the data tree: one row per coin and exchange,
        the pair in the connected exchange's format, the exchange by its name."""
        if not MARKET_DATA_AVAILABLE or MarketTicker is None:
            return

        coin = exchange_symbols.coin_of(ticker.symbol)
        iid = f"{coin}|{ticker.exchange}"

        # A value the exchange does not give shows as n/a, never as 0
        values = (
            self.pair_of(coin),
            exchange_name(ticker.exchange),
            _price(ticker.last),
            _price(ticker.change_24h, signed=True),
            _percent(ticker.change_24h_pct, signed=True),
            _amount(ticker.volume),
            _price(ticker.high_24h),
            _price(ticker.low_24h),
            _price(ticker.bid),
            _price(ticker.ask),
            _percent(ticker.spread_pct, digits=3),
            ticker.timestamp.strftime("%H:%M:%S"),
        )

        # Color coding based on change
        tags = []
        if ticker.change_24h_pct and ticker.change_24h_pct > 0:
            tags.append("positive")
        elif ticker.change_24h_pct and ticker.change_24h_pct < 0:
            tags.append("negative")

        if self.data_tree.exists(iid):
            self.data_tree.item(iid, values=values, tags=tags)
        else:
            self.data_tree.insert("", "end", iid=iid, values=values, tags=tags)

        # Configure tag colors
        self.data_tree.tag_configure("positive", foreground=ui_tokens.STATUS["good"])
        self.data_tree.tag_configure("negative", foreground=ui_tokens.STATUS["bad"])

    def update_chart(self):
        """Draw the chosen coin's candles of the chosen timeframe: the last
        ``CHART_BARS`` closed bars from the candle cache, topped up from the
        exchanges in Settings (primary first), read off the Tk thread."""
        if not MATPLOTLIB_AVAILABLE:
            self._box.showwarning(
                "Warning", "Charts not available - matplotlib not installed"
            )
            return

        coin = self.coin_from(self.chart_symbol_var.get())
        tf = self.timeframe_var.get()
        if not coin:
            self._chart_message("Choose a symbol")
            return
        request = (coin, tf)
        self._chart_request = request
        self._chart_message(f"{self.pair_of(coin)} ({tf}): loading candles")
        self.chart_jobs.submit(
            lambda: self._read_candles(coin, tf),
            on_done=lambda df: self._draw_candles(request, df),
            on_error=lambda exc: self._chart_failed(request, exc),
        )

    def _read_candles(self, coin: str, tf: str):
        """The last ``CHART_BARS`` closed ``tf`` bars of ``coin`` (worker thread)."""
        import pandas as pd
        from market_data.candles import exchange_candles
        from market_data.timeframes import candle_timeframe_seconds

        step = candle_timeframe_seconds(tf)
        end = pd.Timestamp.now(tz="UTC")
        start = end - pd.Timedelta(seconds=step * (CHART_BARS + 1))
        layer = self.market_manager.aggregator.layer() if self.market_manager else None
        df = exchange_candles(coin, tf, start, end, manager=layer)
        return df.tail(CHART_BARS)

    def _chart_failed(self, request: tuple, exc: BaseException) -> None:
        if request != self._chart_request or not self.alive:
            return
        coin, tf = request
        print(f"Market data chart {coin} {tf}: {exc}")
        self._chart_message(f"{self.pair_of(coin)} ({tf}): no candles")

    def _new_axes(self, volume: bool):
        """The price axes, and the volume axes below them when ``volume``."""
        self.figure.clear()
        if volume:
            price_ax, volume_ax = self.figure.subplots(
                2, 1, sharex=True, gridspec_kw={"height_ratios": [3, 1]}
            )
        else:
            price_ax, volume_ax = self.figure.add_subplot(111), None
        chart = ui_tokens.CHART
        for ax in (price_ax, volume_ax):
            if ax is None:
                continue
            ax.set_facecolor(chart["plot"])
            ax.tick_params(colors=chart["text"])
            ax.grid(True, color=chart["grid"], alpha=0.3)
            for spine in ax.spines.values():
                spine.set_color(chart["grid"])
        price_ax.set_ylabel("Price", color=chart["text"])
        if volume_ax is not None:
            volume_ax.set_ylabel("Volume", color=chart["text"])
            price_ax.tick_params(labelbottom=False)
        self.price_ax, self.volume_ax = price_ax, volume_ax
        return price_ax, volume_ax

    def _chart_message(self, text: str) -> None:
        """An empty chart saying ``text``."""
        ax, _ = self._new_axes(volume=False)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_ylabel("")
        ax.grid(False)
        if text:
            ax.text(
                0.5,
                0.5,
                text,
                transform=ax.transAxes,
                ha="center",
                va="center",
                color=ui_tokens.CHART["text"],
            )
        canvas = getattr(self, "canvas", None)
        if canvas is not None:
            canvas.draw_idle()

    def _draw_candles(self, request: tuple, df) -> None:
        """Candles, and their volume where the exchange gives it (Tk thread)."""
        if request != self._chart_request or not self.alive:
            return  # another symbol or timeframe was asked for since
        from market_data.timeframes import candle_timeframe_seconds

        coin, tf = request
        pair = self.pair_of(coin)
        if df is None or len(df) == 0:
            self._chart_message(f"{pair} ({tf}): no candles")
            return
        colours, hollow_up = _candle_style()
        x = mdates.date2num(
            [datetime.fromtimestamp(t.timestamp()) for t in df["open_time"]]
        )
        width = candle_timeframe_seconds(tf) / 86400.0 * 0.7
        opens, closes = list(df["open"]), list(df["close"])
        up = [c >= o for o, c in zip(opens, closes)]
        edge = [colours["up"] if u else colours["down"] for u in up]
        face = ["none" if (u and hollow_up) else e for u, e in zip(up, edge)]
        volumes = [float(v) for v in df["volume"]]
        has_volume = any(v > 0 for v in volumes)  # none at all: the exchange gives none

        price_ax, volume_ax = self._new_axes(volume=has_volume)
        price_ax.vlines(x, df["low"], df["high"], colors=edge, linewidth=1)
        price_ax.bar(
            x,
            [max(abs(c - o), 1e-12) for o, c in zip(opens, closes)],
            width,
            bottom=[min(o, c) for o, c in zip(opens, closes)],
            color=face,
            edgecolor=edge,
            linewidth=1,
        )
        if volume_ax is not None:
            volume_ax.bar(x, volumes, width, color=edge, alpha=0.6)
        self.chart_source = str(df.attrs.get("exchange") or "")
        source = exchange_name(self.chart_source) if self.chart_source else ""
        title = " · ".join(t for t in (pair, tf, source) if t)
        price_ax.set_title(title, color=ui_tokens.CHART["text"])
        locator = mdates.AutoDateLocator()
        axis = (volume_ax or price_ax).xaxis
        axis.set_major_locator(locator)
        axis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        price_ax.set_xlim(x[0] - width, x[-1] + width)
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def load_orderbook(self):
        """Load order book data"""
        self._box.showinfo("Info", "Order book loading not yet implemented")

    def scan_arbitrage(self):
        """Scan for arbitrage opportunities"""
        if not self.market_manager:
            self._box.showerror("Error", "Market data manager not available")
            return

        min_profit = float(self.min_profit_var.get() or 0.1)

        # Clear existing opportunities
        for item in self.arb_tree.get_children():
            self.arb_tree.delete(item)

        # Check each subscribed symbol
        opportunities_found = 0
        for symbol in self.subscribed():
            try:
                # Get spread analysis
                if hasattr(self.market_manager.aggregator, "get_spread_analysis"):
                    analysis = self.market_manager.aggregator.get_spread_analysis(
                        symbol
                    )

                    if "arbitrage_opportunities" in analysis:
                        for opportunity in analysis["arbitrage_opportunities"]:
                            if opportunity["profit_pct"] >= min_profit:
                                values = (
                                    symbol,
                                    opportunity["buy_exchange"],
                                    opportunity["sell_exchange"],
                                    f"{opportunity['buy_price']:.6f}",
                                    f"{opportunity['sell_price']:.6f}",
                                    f"{opportunity['profit_per_unit']:.6f}",
                                    f"{opportunity['profit_pct']:.2f}%",
                                    datetime.now().strftime("%H:%M:%S"),
                                )

                                self.arb_tree.insert(
                                    "", "end", values=values, tags=["opportunity"]
                                )
                                opportunities_found += 1

            except Exception as e:
                print(f"Error checking arbitrage for {symbol}: {e}")

        if opportunities_found == 0:
            self._box.showinfo(
                "Info", f"No arbitrage opportunities found above {min_profit}% profit"
            )
        else:
            self._box.showinfo(
                "Success", f"Found {opportunities_found} arbitrage opportunities"
            )

        # Configure tag colors
        self.arb_tree.tag_configure("opportunity", foreground=ui_tokens.STATUS["good"])

    def cleanup(self):
        """Cleanup when closing (and when the tab is destroyed): the timers stop,
        and the feeds."""
        if not self.alive:
            return
        self.alive = False
        for name in list(self._afters):
            self._cancel(name)
        for jobs in (getattr(self, "chart_jobs", None),):
            if jobs is not None:
                jobs.stop()
        if self.market_manager:
            try:
                self.market_manager.remove_update_callback(self.on_market_update)
                self.market_manager.stop()
            except Exception:
                pass


# Fallback class for when market data is not available
if not MARKET_DATA_AVAILABLE:

    class MarketTicker:
        """Fallback MarketTicker class"""

        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    class MarketDataGUI:
        def __init__(self, parent, **kwargs):
            self.parent = parent
            self.setup_fallback_ui()

        def setup_fallback_ui(self):
            frame = ttk.Frame(self.parent)
            frame.pack(fill="both", expand=True, padx=20, pady=20)

            ttk.Label(
                frame,
                text="Real-time Market Data",
                font=ui_tokens.font("display", "bold"),
            ).pack(pady=20)

            ttk.Label(
                frame,
                text="⚠️ Real-time market data not available",
                style="Warn.TLabel",
                font=ui_tokens.font("title"),
            ).pack(pady=10)

            ttk.Label(
                frame, text="Missing dependencies:", font=ui_tokens.font("body", "bold")
            ).pack(pady=5)

            deps = ["Real-time market data module"]
            for dep in deps:
                ttk.Label(frame, text=f"• {dep}", style="Bad.TLabel").pack()

            ttk.Label(
                frame,
                text="Install missing dependencies to enable real-time market data",
                style="Muted.TLabel",
                font=ui_tokens.font("body"),
            ).pack(pady=10)

        def cleanup(self):
            pass
