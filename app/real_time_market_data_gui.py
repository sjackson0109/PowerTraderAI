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

import ui_table
import ui_tokens

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
        self.symbol_entry = ttk.Entry(symbol_frame, width=15)
        self.symbol_entry.pack(side="left", padx=5)
        self.symbol_entry.insert(0, "BTCUSDT")

        ttk.Label(symbol_frame, text="Exchange:").pack(side="left", padx=(10, 0))
        names = self.exchange_names()
        self.exchange_var = tk.StringVar(value=names[0] if names else "")
        exchange_combo = ttk.Combobox(
            symbol_frame,
            textvariable=self.exchange_var,
            width=15,
            values=names,
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
        chart = ui_tokens.CHART
        self.figure = Figure(figsize=(12, 8), dpi=100)
        self.figure.patch.set_facecolor(chart["figure"])

        # Price subplot
        self.price_ax = self.figure.add_subplot(211)
        self.price_ax.set_facecolor(chart["plot"])
        self.price_ax.tick_params(colors=chart["text"])
        self.price_ax.set_title("Price Chart", color=chart["text"])
        self.price_ax.set_ylabel("Price", color=chart["text"])

        # Volume subplot
        self.volume_ax = self.figure.add_subplot(212)
        self.volume_ax.set_facecolor(chart["plot"])
        self.volume_ax.tick_params(colors=chart["text"])
        self.volume_ax.set_title("Volume", color=chart["text"])
        self.volume_ax.set_ylabel("Volume", color=chart["text"])
        self.volume_ax.set_xlabel("Time", color=chart["text"])

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
        names = self.exchange_names()
        self.ob_exchange_var = tk.StringVar(value=names[0] if names else "")
        ttk.Combobox(
            ob_controls,
            textvariable=self.ob_exchange_var,
            width=15,
            values=names,
        ).pack(side="left", padx=5)

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
        """Subscribe to a symbol"""
        symbol = self.symbol_entry.get().strip().upper()
        exchange = self.exchange_var.get()

        if not symbol:
            messagebox.showerror("Error", "Please enter a symbol")
            return

        if not self.market_manager:
            messagebox.showerror(
                "Error",
                "Market data manager not available.",
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
                "Market data manager not available.",
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
        names = self.exchange_names()
        if not names:
            return
        primary = names[0]
        for symbol in ("BTC", "ETH", "ADA"):
            try:
                self.market_manager.subscribe_symbol(symbol, [primary])
                self.subscriptions[f"{symbol}_{primary}"] = {
                    "symbol": symbol,
                    "exchange": primary,
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
            self.feed_status_label.config(text="Connected", style="Good.TLabel")
        else:
            self.feed_status_label.config(text="Disconnected", style="Bad.TLabel")

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

        # A value the exchange does not give shows as n/a, never as 0
        values = (
            ticker.symbol,
            ticker.exchange,
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
        self.data_tree.tag_configure("positive", foreground=ui_tokens.STATUS["good"])
        self.data_tree.tag_configure("negative", foreground=ui_tokens.STATUS["bad"])

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
        chart = ui_tokens.CHART
        self.price_ax.plot(timestamps, prices, color=chart["series"], linewidth=1.5)
        self.price_ax.set_facecolor(chart["plot"])
        self.price_ax.tick_params(colors=chart["text"])
        self.price_ax.set_title(f"{symbol} Price Chart", color=chart["text"])
        self.price_ax.set_ylabel("Price", color=chart["text"])
        self.price_ax.grid(True, alpha=0.3)

        # Plot volume
        self.volume_ax.bar(
            timestamps, volumes, color=chart["series2"], alpha=0.7, width=0.0001
        )
        self.volume_ax.set_facecolor(chart["plot"])
        self.volume_ax.tick_params(colors=chart["text"])
        self.volume_ax.set_title("Volume", color=chart["text"])
        self.volume_ax.set_ylabel("Volume", color=chart["text"])
        self.volume_ax.set_xlabel("Time", color=chart["text"])
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
        self.arb_tree.tag_configure("opportunity", foreground=ui_tokens.STATUS["good"])

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
