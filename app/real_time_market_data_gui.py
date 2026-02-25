"""
Real-time Market Data GUI (Item 24)
User interface for monitoring real-time market data feeds
"""

import queue
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

try:
    from real_time_market_data import (
        DataSource,
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

# Dark theme colors
DARK_BG = "#070B10"
DARK_BG2 = "#0B1220"
DARK_PANEL = "#0E1626"
DARK_PANEL2 = "#121C2F"
DARK_BORDER = "#243044"
DARK_FG = "#C7D1DB"
DARK_MUTED = "#8B949E"
DARK_ACCENT = "#00FF66"
DARK_ACCENT2 = "#00E5FF"
DARK_SELECT_BG = "#17324A"
DARK_SELECT_FG = "#00FF66"
DARK_ERROR = "#FF4757"
DARK_WARNING = "#FFA502"
DARK_SUCCESS = "#2ED573"


class MarketDataGUI:
    """GUI for real-time market data monitoring"""

    def __init__(self, parent: tk.Widget):
        self.parent = parent
        self.market_manager = None
        self.update_queue = queue.Queue()
        self.subscriptions: Dict[str, Dict] = {}
        self.price_data: Dict[str, List] = {}
        self.is_updating = True

        # Initialize market data manager if available
        if MARKET_DATA_AVAILABLE:
            try:
                self.market_manager = get_market_data_manager()
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
        self.start_update_thread()

        # Start with some default subscriptions
        if self.market_manager:
            self.add_default_subscriptions()

    def setup_ui(self):
        """Setup the user interface"""
        if not MARKET_DATA_AVAILABLE:
            self.setup_fallback_ui()
            return

        self.main_frame = ttk.Frame(self.parent)
        self.main_frame.pack(fill="both", expand=True, padx=5, pady=5)

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

        ttk.Label(frame, text="Real-time Market Data", font=("Arial", 16, "bold")).pack(
            pady=20
        )

        if not MARKET_DATA_AVAILABLE:
            ttk.Label(
                frame,
                text="⚠️ Real-time market data module not available",
                foreground=DARK_WARNING,
                font=("Arial", 12),
            ).pack(pady=10)
        else:
            ttk.Label(
                frame,
                text="⚠️ Market data dependencies missing",
                foreground=DARK_WARNING,
                font=("Arial", 12),
            ).pack(pady=10)

        ttk.Label(
            frame,
            text="Required for real-time market data:",
            font=("Arial", 10, "bold"),
        ).pack(pady=5)

        deps = [
            "pip install websocket-client",
            "pip install ccxt",
            "pip install pandas numpy",
        ]
        for dep in deps:
            ttk.Label(frame, text=f"• {dep}", foreground=DARK_MUTED).pack()

        ttk.Label(
            frame,
            text="Install missing dependencies to enable real-time market data",
            foreground=DARK_MUTED,
            font=("Arial", 10),
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
        self.symbol_entry = ttk.Entry(symbol_frame, width=15)
        self.symbol_entry.pack(side="left", padx=5)
        self.symbol_entry.insert(0, "BTCUSDT")

        ttk.Label(symbol_frame, text="Exchange:").pack(side="left", padx=(10, 0))
        self.exchange_var = tk.StringVar(value="binance")
        exchange_combo = ttk.Combobox(
            symbol_frame,
            textvariable=self.exchange_var,
            width=15,
            values=["binance", "binance_futures", "coinbase_pro", "kraken"],
        )
        exchange_combo.pack(side="left", padx=5)

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
            status_frame, text="Disconnected", foreground=DARK_ERROR
        )
        self.feed_status_label.pack(side="left", padx=5)

        ttk.Label(status_frame, text="Active Subscriptions:").pack(
            side="left", padx=(20, 0)
        )
        self.subscriptions_count_label = ttk.Label(status_frame, text="0")
        self.subscriptions_count_label.pack(side="left", padx=5)

        # Market data table
        data_frame = ttk.LabelFrame(self.overview_tab, text="Market Data")
        data_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Treeview for market data
        columns = (
            "symbol",
            "exchange",
            "price",
            "change",
            "change_pct",
            "volume",
            "bid",
            "ask",
            "spread",
            "updated",
        )
        self.data_tree = ttk.Treeview(data_frame, columns=columns, show="headings")

        # Configure columns
        column_widths = {
            "symbol": 80,
            "exchange": 90,
            "price": 100,
            "change": 80,
            "change_pct": 70,
            "volume": 120,
            "bid": 90,
            "ask": 90,
            "spread": 70,
            "updated": 120,
        }

        for col in columns:
            self.data_tree.heading(col, text=col.replace("_", " ").title())
            self.data_tree.column(
                col, width=column_widths.get(col, 80), anchor="center"
            )

        # Scrollbars
        data_v_scrollbar = ttk.Scrollbar(
            data_frame, orient="vertical", command=self.data_tree.yview
        )
        data_h_scrollbar = ttk.Scrollbar(
            data_frame, orient="horizontal", command=self.data_tree.xview
        )
        self.data_tree.configure(
            yscrollcommand=data_v_scrollbar.set, xscrollcommand=data_h_scrollbar.set
        )

        self.data_tree.pack(side="left", fill="both", expand=True)
        data_v_scrollbar.pack(side="right", fill="y")
        data_h_scrollbar.pack(side="bottom", fill="x")

    def setup_charts_tab(self):
        """Setup price charts tab"""
        # Chart controls
        chart_controls = ttk.LabelFrame(self.charts_tab, text="Chart Controls")
        chart_controls.pack(fill="x", padx=5, pady=5)

        ttk.Label(chart_controls, text="Symbol:").pack(side="left")
        self.chart_symbol_var = tk.StringVar(value="BTCUSDT")
        symbol_entry = ttk.Entry(
            chart_controls, textvariable=self.chart_symbol_var, width=15
        )
        symbol_entry.pack(side="left", padx=5)

        ttk.Label(chart_controls, text="Timeframe:").pack(side="left", padx=(10, 0))
        self.timeframe_var = tk.StringVar(value="1h")
        timeframe_combo = ttk.Combobox(
            chart_controls,
            textvariable=self.timeframe_var,
            width=10,
            values=["5m", "15m", "30m", "1h", "4h", "1d"],
        )
        timeframe_combo.pack(side="left", padx=5)

        ttk.Button(chart_controls, text="Update Chart", command=self.update_chart).pack(
            side="left", padx=5
        )

        # Chart frame
        chart_frame = ttk.Frame(self.charts_tab)
        chart_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Create matplotlib figure
        self.figure = Figure(figsize=(12, 8), dpi=100)
        self.figure.patch.set_facecolor(DARK_BG)

        # Price subplot
        self.price_ax = self.figure.add_subplot(211)
        self.price_ax.set_facecolor(DARK_PANEL)
        self.price_ax.tick_params(colors=DARK_FG)
        self.price_ax.set_title("Price Chart", color=DARK_FG)
        self.price_ax.set_ylabel("Price", color=DARK_FG)

        # Volume subplot
        self.volume_ax = self.figure.add_subplot(212)
        self.volume_ax.set_facecolor(DARK_PANEL)
        self.volume_ax.tick_params(colors=DARK_FG)
        self.volume_ax.set_title("Volume", color=DARK_FG)
        self.volume_ax.set_ylabel("Volume", color=DARK_FG)
        self.volume_ax.set_xlabel("Time", color=DARK_FG)

        self.figure.tight_layout()

        # Canvas
        self.canvas = FigureCanvasTkAgg(self.figure, chart_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def setup_orderbook_tab(self):
        """Setup order book tab"""
        # Symbol selection
        ob_controls = ttk.LabelFrame(self.orderbook_tab, text="Order Book Controls")
        ob_controls.pack(fill="x", padx=5, pady=5)

        ttk.Label(ob_controls, text="Symbol:").pack(side="left")
        self.ob_symbol_var = tk.StringVar(value="BTCUSDT")
        ttk.Entry(ob_controls, textvariable=self.ob_symbol_var, width=15).pack(
            side="left", padx=5
        )

        ttk.Label(ob_controls, text="Exchange:").pack(side="left", padx=(10, 0))
        self.ob_exchange_var = tk.StringVar(value="binance")
        ttk.Combobox(
            ob_controls,
            textvariable=self.ob_exchange_var,
            width=15,
            values=["binance", "coinbase_pro", "kraken"],
        ).pack(side="left", padx=5)

        ttk.Button(
            ob_controls, text="Load Order Book", command=self.load_orderbook
        ).pack(side="left", padx=5)

        # Order book display
        ob_frame = ttk.LabelFrame(self.orderbook_tab, text="Order Book")
        ob_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Split into bids and asks
        ob_paned = ttk.PanedWindow(ob_frame, orient="horizontal")
        ob_paned.pack(fill="both", expand=True)

        # Asks (sells)
        asks_frame = ttk.LabelFrame(ob_paned, text="Asks (Sellers)")
        ob_paned.add(asks_frame)

        asks_columns = ("price", "quantity", "total")
        self.asks_tree = ttk.Treeview(
            asks_frame, columns=asks_columns, show="headings", height=15
        )

        for col in asks_columns:
            self.asks_tree.heading(col, text=col.title())
            self.asks_tree.column(col, width=120, anchor="center")

        asks_scrollbar = ttk.Scrollbar(
            asks_frame, orient="vertical", command=self.asks_tree.yview
        )
        self.asks_tree.configure(yscrollcommand=asks_scrollbar.set)
        self.asks_tree.pack(side="left", fill="both", expand=True)
        asks_scrollbar.pack(side="right", fill="y")

        # Bids (buys)
        bids_frame = ttk.LabelFrame(ob_paned, text="Bids (Buyers)")
        ob_paned.add(bids_frame)

        bids_columns = ("price", "quantity", "total")
        self.bids_tree = ttk.Treeview(
            bids_frame, columns=bids_columns, show="headings", height=15
        )

        for col in bids_columns:
            self.bids_tree.heading(col, text=col.title())
            self.bids_tree.column(col, width=120, anchor="center")

        bids_scrollbar = ttk.Scrollbar(
            bids_frame, orient="vertical", command=self.bids_tree.yview
        )
        self.bids_tree.configure(yscrollcommand=bids_scrollbar.set)
        self.bids_tree.pack(side="left", fill="both", expand=True)
        bids_scrollbar.pack(side="right", fill="y")

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

        arb_columns = (
            "symbol",
            "buy_exchange",
            "sell_exchange",
            "buy_price",
            "sell_price",
            "profit",
            "profit_pct",
            "updated",
        )
        self.arb_tree = ttk.Treeview(arb_frame, columns=arb_columns, show="headings")

        arb_column_widths = {
            "symbol": 80,
            "buy_exchange": 100,
            "sell_exchange": 100,
            "buy_price": 100,
            "sell_price": 100,
            "profit": 90,
            "profit_pct": 80,
            "updated": 120,
        }

        for col in arb_columns:
            self.arb_tree.heading(col, text=col.replace("_", " ").title())
            self.arb_tree.column(
                col, width=arb_column_widths.get(col, 80), anchor="center"
            )

        arb_v_scrollbar = ttk.Scrollbar(
            arb_frame, orient="vertical", command=self.arb_tree.yview
        )
        arb_h_scrollbar = ttk.Scrollbar(
            arb_frame, orient="horizontal", command=self.arb_tree.xview
        )
        self.arb_tree.configure(
            yscrollcommand=arb_v_scrollbar.set, xscrollcommand=arb_h_scrollbar.set
        )

        self.arb_tree.pack(side="left", fill="both", expand=True)
        arb_v_scrollbar.pack(side="right", fill="y")
        arb_h_scrollbar.pack(side="bottom", fill="x")

    def setup_feeds_tab(self):
        """Setup data feeds monitoring tab"""
        # Feed status
        feed_status_frame = ttk.LabelFrame(self.feeds_tab, text="Feed Status")
        feed_status_frame.pack(fill="x", padx=5, pady=5)

        feeds = ["Binance", "Coinbase Pro", "Kraken", "Bitfinex"]
        self.feed_indicators = {}

        for i, feed in enumerate(feeds):
            row = i // 2
            col = i % 2

            frame = ttk.Frame(feed_status_frame)
            frame.grid(row=row, column=col, sticky="w", padx=10, pady=5)

            self.feed_indicators[feed] = tk.Label(
                frame, text="●", foreground=DARK_ERROR, font=("Arial", 16)
            )
            self.feed_indicators[feed].pack(side="left")

            ttk.Label(frame, text=feed).pack(side="left", padx=5)

        # Feed statistics
        stats_frame = ttk.LabelFrame(self.feeds_tab, text="Feed Statistics")
        stats_frame.pack(fill="both", expand=True, padx=5, pady=5)

        stats_columns = (
            "exchange",
            "status",
            "messages_received",
            "last_message",
            "uptime",
            "errors",
        )
        self.stats_tree = ttk.Treeview(
            stats_frame, columns=stats_columns, show="headings"
        )

        for col in stats_columns:
            self.stats_tree.heading(col, text=col.replace("_", " ").title())
            self.stats_tree.column(col, width=120, anchor="center")

        stats_scrollbar = ttk.Scrollbar(
            stats_frame, orient="vertical", command=self.stats_tree.yview
        )
        self.stats_tree.configure(yscrollcommand=stats_scrollbar.set)
        self.stats_tree.pack(side="left", fill="both", expand=True)
        stats_scrollbar.pack(side="right", fill="y")

    def subscribe_symbol(self):
        """Subscribe to a symbol"""
        symbol = self.symbol_entry.get().strip().upper()
        exchange = self.exchange_var.get()

        if not symbol:
            messagebox.showerror("Error", "Please enter a symbol")
            return

        if not self.market_manager:
            messagebox.showerror(
                "Error",
                "Market data manager not available.\nPlease install dependencies: websocket-client, ccxt",
            )
            return

        try:
            self.market_manager.subscribe_symbol(symbol, [exchange])
            self.subscriptions[f"{symbol}_{exchange}"] = {
                "symbol": symbol,
                "exchange": exchange,
                "subscribed_at": datetime.now(),
            }
            self.update_subscriptions_count()
            messagebox.showinfo("Success", f"Subscribed to {symbol} on {exchange}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to subscribe: {e}")

    def unsubscribe_symbol(self):
        """Unsubscribe from a symbol"""
        symbol = self.symbol_entry.get().strip().upper()

        if not symbol:
            messagebox.showerror("Error", "Please enter a symbol")
            return

        if not self.market_manager:
            messagebox.showerror(
                "Error",
                "Market data manager not available.\nPlease install dependencies: websocket-client, ccxt",
            )
            return

        try:
            self.market_manager.unsubscribe_symbol(symbol)

            # Remove from local tracking
            keys_to_remove = [
                k for k in self.subscriptions.keys() if k.startswith(f"{symbol}_")
            ]
            for key in keys_to_remove:
                del self.subscriptions[key]

            self.update_subscriptions_count()
            messagebox.showinfo("Success", f"Unsubscribed from {symbol}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to unsubscribe: {e}")

    def add_default_subscriptions(self):
        """Add some default symbol subscriptions"""
        default_symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
        for symbol in default_symbols:
            try:
                self.market_manager.subscribe_symbol(symbol, ["binance"])
                self.subscriptions[f"{symbol}_binance"] = {
                    "symbol": symbol,
                    "exchange": "binance",
                    "subscribed_at": datetime.now(),
                }
            except Exception as e:
                print(f"Failed to subscribe to {symbol}: {e}")

        self.update_subscriptions_count()

    def update_subscriptions_count(self):
        """Update subscriptions count display"""
        count = len(self.subscriptions)
        self.subscriptions_count_label.config(text=str(count))

        if count > 0:
            self.feed_status_label.config(text="Connected", foreground=DARK_SUCCESS)
        else:
            self.feed_status_label.config(text="Disconnected", foreground=DARK_ERROR)

    def on_market_update(self, data_type: str, data: Any):
        """Handle market data updates"""
        # Queue updates to be processed in GUI thread
        self.update_queue.put((data_type, data))

    def start_update_thread(self):
        """Start the GUI update thread"""

        def update_worker():
            while self.is_updating:
                try:
                    # Process queued updates
                    while not self.update_queue.empty():
                        data_type, data = self.update_queue.get_nowait()

                        if data_type == "ticker":
                            self.parent.after_idle(
                                lambda d=data: self.update_ticker_display(d)
                            )

                    time.sleep(0.1)  # Small delay to prevent CPU overload

                except queue.Empty:
                    pass
                except Exception as e:
                    print(f"Error in update worker: {e}")

        self.update_thread = threading.Thread(target=update_worker, daemon=True)
        self.update_thread.start()

    def update_ticker_display(self, ticker):
        """Update ticker display in the data tree"""
        if not MARKET_DATA_AVAILABLE or MarketTicker is None:
            return

        key = f"{ticker.symbol}_{ticker.exchange}"

        # Store price data for charts
        if ticker.symbol not in self.price_data:
            self.price_data[ticker.symbol] = []

        self.price_data[ticker.symbol].append(
            {
                "timestamp": ticker.timestamp,
                "price": ticker.last,
                "volume": ticker.volume,
            }
        )

        # Keep only last 1000 data points
        if len(self.price_data[ticker.symbol]) > 1000:
            self.price_data[ticker.symbol] = self.price_data[ticker.symbol][-1000:]

        # Format display values
        price_str = f"{ticker.last:.6f}"
        change_str = f"{ticker.change_24h:.6f}" if ticker.change_24h else "0.000000"
        change_pct_str = (
            f"{ticker.change_24h_pct:.2f}%" if ticker.change_24h_pct else "0.00%"
        )
        volume_str = f"{ticker.volume:.2f}" if ticker.volume else "0.00"
        bid_str = f"{ticker.bid:.6f}" if ticker.bid else "N/A"
        ask_str = f"{ticker.ask:.6f}" if ticker.ask else "N/A"
        spread_str = f"{ticker.spread_pct:.3f}%" if ticker.spread_pct else "N/A"
        updated_str = ticker.timestamp.strftime("%H:%M:%S")

        values = (
            ticker.symbol,
            ticker.exchange,
            price_str,
            change_str,
            change_pct_str,
            volume_str,
            bid_str,
            ask_str,
            spread_str,
            updated_str,
        )

        # Find existing item or create new one
        existing_item = None
        for item in self.data_tree.get_children():
            item_values = self.data_tree.item(item)["values"]
            if (
                len(item_values) >= 2
                and item_values[0] == ticker.symbol
                and item_values[1] == ticker.exchange
            ):
                existing_item = item
                break

        if existing_item:
            self.data_tree.item(existing_item, values=values)
        else:
            self.data_tree.insert("", "end", values=values)

        # Color coding based on change
        tags = []
        if ticker.change_24h_pct and ticker.change_24h_pct > 0:
            tags.append("positive")
        elif ticker.change_24h_pct and ticker.change_24h_pct < 0:
            tags.append("negative")

        if existing_item:
            self.data_tree.item(existing_item, tags=tags)

        # Configure tag colors
        self.data_tree.tag_configure("positive", foreground=DARK_SUCCESS)
        self.data_tree.tag_configure("negative", foreground=DARK_ERROR)

    def update_chart(self):
        """Update price chart"""
        if not MATPLOTLIB_AVAILABLE:
            messagebox.showwarning(
                "Warning", "Charts not available - matplotlib not installed"
            )
            return

        symbol = self.chart_symbol_var.get().upper()

        if symbol not in self.price_data or not self.price_data[symbol]:
            messagebox.showwarning("Warning", f"No data available for {symbol}")
            return

        # Get data for chart
        data = self.price_data[symbol][-100:]  # Last 100 data points

        if len(data) < 2:
            messagebox.showwarning("Warning", "Not enough data for chart")
            return

        timestamps = [d["timestamp"] for d in data]
        prices = [d["price"] for d in data]
        volumes = [d["volume"] for d in data]

        # Clear previous plots
        self.price_ax.clear()
        self.volume_ax.clear()

        # Plot price
        self.price_ax.plot(timestamps, prices, color=DARK_ACCENT, linewidth=1.5)
        self.price_ax.set_facecolor(DARK_PANEL)
        self.price_ax.tick_params(colors=DARK_FG)
        self.price_ax.set_title(f"{symbol} Price Chart", color=DARK_FG)
        self.price_ax.set_ylabel("Price", color=DARK_FG)
        self.price_ax.grid(True, alpha=0.3)

        # Plot volume
        self.volume_ax.bar(
            timestamps, volumes, color=DARK_ACCENT2, alpha=0.7, width=0.0001
        )
        self.volume_ax.set_facecolor(DARK_PANEL)
        self.volume_ax.tick_params(colors=DARK_FG)
        self.volume_ax.set_title("Volume", color=DARK_FG)
        self.volume_ax.set_ylabel("Volume", color=DARK_FG)
        self.volume_ax.set_xlabel("Time", color=DARK_FG)
        self.volume_ax.grid(True, alpha=0.3)

        # Format x-axis
        self.volume_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        self.volume_ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=5))

        self.figure.tight_layout()
        self.canvas.draw()

    def load_orderbook(self):
        """Load order book data"""
        messagebox.showinfo("Info", "Order book loading not yet implemented")

    def scan_arbitrage(self):
        """Scan for arbitrage opportunities"""
        if not self.market_manager:
            messagebox.showerror("Error", "Market data manager not available")
            return

        min_profit = float(self.min_profit_var.get() or 0.1)

        # Clear existing opportunities
        for item in self.arb_tree.get_children():
            self.arb_tree.delete(item)

        # Check each subscribed symbol
        opportunities_found = 0
        for key, subscription in self.subscriptions.items():
            symbol = subscription["symbol"]

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
            messagebox.showinfo(
                "Info", f"No arbitrage opportunities found above {min_profit}% profit"
            )
        else:
            messagebox.showinfo(
                "Success", f"Found {opportunities_found} arbitrage opportunities"
            )

        # Configure tag colors
        self.arb_tree.tag_configure("opportunity", foreground=DARK_SUCCESS)

    def cleanup(self):
        """Cleanup when closing"""
        self.is_updating = False
        if self.market_manager:
            try:
                self.market_manager.stop()
            except:
                pass


# Fallback class for when market data is not available
if not MARKET_DATA_AVAILABLE:

    class MarketTicker:
        """Fallback MarketTicker class"""

        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    class MarketDataGUI:
        def __init__(self, parent):
            self.parent = parent
            self.setup_fallback_ui()

        def setup_fallback_ui(self):
            frame = ttk.Frame(self.parent)
            frame.pack(fill="both", expand=True, padx=20, pady=20)

            ttk.Label(
                frame, text="Real-time Market Data", font=("Arial", 16, "bold")
            ).pack(pady=20)

            ttk.Label(
                frame,
                text="⚠️ Real-time market data not available",
                foreground=DARK_WARNING,
                font=("Arial", 12),
            ).pack(pady=10)

            ttk.Label(
                frame, text="Missing dependencies:", font=("Arial", 10, "bold")
            ).pack(pady=5)

            deps = ["Real-time market data module", "WebSocket support", "CCXT library"]
            for dep in deps:
                ttk.Label(frame, text=f"• {dep}", foreground=DARK_ERROR).pack()

            ttk.Label(
                frame,
                text="Install missing dependencies to enable real-time market data",
                foreground=DARK_MUTED,
                font=("Arial", 10),
            ).pack(pady=10)

        def cleanup(self):
            pass
