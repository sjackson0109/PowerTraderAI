"""
PowerTrader AI+ Chart Components Module
Extracted chart-related classes from main pt_hub.py for better modularity
"""

import json
import math
import os
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter
from matplotlib.transforms import blended_transform_factory

# Set matplotlib to non-interactive backend
plt.ioff()


class CandleFetcher:
    """
    Handles fetching and caching of candlestick data for chart display.
    Provides efficient data management with automatic caching.
    """

    def __init__(self, cache_timeout: int = 300):  # 5 minutes default
        self.cache = {}
        self.cache_timeout = cache_timeout
        self.last_fetch_times = {}

    def get_candle_data(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> List[Dict]:
        """
        Get candlestick data with caching support.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            timeframe: Chart timeframe (e.g., "1h", "4h", "1d")
            limit: Number of candles to fetch

        Returns:
            List of candle data dictionaries
        """
        cache_key = f"{symbol}_{timeframe}_{limit}"
        current_time = time.time()

        # Check if we have cached data that's still fresh
        if (
            cache_key in self.cache
            and cache_key in self.last_fetch_times
            and current_time - self.last_fetch_times[cache_key] < self.cache_timeout
        ):
            return self.cache[cache_key]

        try:
            # Try to get data from the data provider
            from pt_data_provider import get_data_provider

            data_provider = get_data_provider()
            if not data_provider or not data_provider.is_available():
                return self._generate_mock_data(symbol, limit)

            # Fetch real data
            kline_data = data_provider.get_kline_data(symbol, timeframe, limit=limit)

            if not kline_data:
                return self._generate_mock_data(symbol, limit)

            # Parse the data
            if isinstance(kline_data, str):
                kline_data = json.loads(kline_data)

            # Convert to standard format
            candles = []
            if isinstance(kline_data, list):
                for kline in kline_data:
                    if len(kline) >= 6:
                        candles.append(
                            {
                                "timestamp": int(kline[0]),
                                "open": float(kline[1]),
                                "high": float(kline[2]),
                                "low": float(kline[3]),
                                "close": float(kline[4]),
                                "volume": float(kline[5]),
                            }
                        )

            # Cache the data
            self.cache[cache_key] = candles
            self.last_fetch_times[cache_key] = current_time

            return candles

        except Exception as e:
            print(f"Error fetching candle data for {symbol}: {e}")
            return self._generate_mock_data(symbol, limit)

    def _generate_mock_data(self, symbol: str, limit: int) -> List[Dict]:
        """Generate mock candlestick data for testing/fallback."""
        candles = []
        base_price = (
            50000.0
            if "BTC" in symbol.upper()
            else 3000.0 if "ETH" in symbol.upper() else 1.0
        )
        current_time = int(time.time()) * 1000

        for i in range(limit):
            # Simple random walk for price simulation
            price_change = (np.random.random() - 0.5) * 0.02  # ±1% change
            if i == 0:
                open_price = base_price
            else:
                open_price = candles[-1]["close"]

            high = open_price * (1 + abs(price_change) + np.random.random() * 0.01)
            low = open_price * (1 - abs(price_change) - np.random.random() * 0.01)
            close = open_price * (1 + price_change)

            # Ensure OHLC relationships are valid
            high = max(high, open_price, close)
            low = min(low, open_price, close)

            candles.append(
                {
                    "timestamp": current_time
                    - (limit - i - 1) * 3600000,  # 1-hour intervals
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "volume": round(np.random.uniform(100, 10000), 2),
                }
            )

        return candles

    def clear_cache(self):
        """Clear all cached data."""
        self.cache.clear()
        self.last_fetch_times.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "cached_symbols": len(self.cache),
            "total_cache_size": sum(len(data) for data in self.cache.values()),
        }


class CandleChart(ttk.Frame):
    """
    Advanced candlestick chart widget with technical indicators and interactivity.
    """

    def __init__(self, parent, symbol: str = "BTCUSDT", **kwargs):
        super().__init__(parent, **kwargs)
        self.symbol = symbol
        self.timeframe = "1h"
        self.limit = 100

        self.fetcher = CandleFetcher()
        self.candle_data = []

        self._setup_ui()
        self._setup_chart()

        # Auto-refresh timer
        self.auto_refresh = True
        self.refresh_interval = 30000  # 30 seconds
        self.after_id = None

        # Start auto-refresh
        self._schedule_refresh()

    def _setup_ui(self):
        """Setup the chart UI components."""
        # Control frame
        control_frame = ttk.Frame(self)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        # Symbol selector
        ttk.Label(control_frame, text="Symbol:").pack(side=tk.LEFT)
        self.symbol_var = tk.StringVar(value=self.symbol)
        symbol_combo = ttk.Combobox(
            control_frame,
            textvariable=self.symbol_var,
            values=["BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT"],
            width=10,
        )
        symbol_combo.pack(side=tk.LEFT, padx=(5, 10))
        symbol_combo.bind("<<ComboboxSelected>>", self._on_symbol_change)

        # Timeframe selector
        ttk.Label(control_frame, text="Timeframe:").pack(side=tk.LEFT)
        self.timeframe_var = tk.StringVar(value=self.timeframe)
        timeframe_combo = ttk.Combobox(
            control_frame,
            textvariable=self.timeframe_var,
            values=["1m", "5m", "15m", "1h", "4h", "1d"],
            width=8,
        )
        timeframe_combo.pack(side=tk.LEFT, padx=(5, 10))
        timeframe_combo.bind("<<ComboboxSelected>>", self._on_timeframe_change)

        # Refresh button
        refresh_btn = ttk.Button(
            control_frame, text="Refresh", command=self.refresh_chart
        )
        refresh_btn.pack(side=tk.LEFT, padx=(5, 0))

        # Auto-refresh checkbox
        self.auto_refresh_var = tk.BooleanVar(value=self.auto_refresh)
        auto_check = ttk.Checkbutton(
            control_frame,
            text="Auto-refresh",
            variable=self.auto_refresh_var,
            command=self._on_auto_refresh_change,
        )
        auto_check.pack(side=tk.LEFT, padx=(10, 0))

        # Chart frame
        self.chart_frame = ttk.Frame(self)
        self.chart_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def _setup_chart(self):
        """Setup the matplotlib chart."""
        # Create figure and subplot
        self.fig = Figure(figsize=(12, 8), dpi=100, facecolor="white")
        self.ax = self.fig.add_subplot(111)

        # Create canvas
        self.canvas = FigureCanvasTkAgg(self.fig, self.chart_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Add toolbar
        from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

        toolbar = NavigationToolbar2Tk(self.canvas, self.chart_frame)
        toolbar.update()

        # Configure chart appearance
        self.fig.subplots_adjust(left=0.1, right=0.95, top=0.95, bottom=0.1)

    def _plot_candlesticks(self):
        """Plot candlestick data on the chart."""
        if not self.candle_data:
            return

        self.ax.clear()

        # Extract OHLCV data
        opens = [c["open"] for c in self.candle_data]
        highs = [c["high"] for c in self.candle_data]
        lows = [c["low"] for c in self.candle_data]
        closes = [c["close"] for c in self.candle_data]
        times = [c["timestamp"] for c in self.candle_data]

        # Convert timestamps to matplotlib dates
        from matplotlib.dates import DateFormatter
        import datetime

        dates = [datetime.datetime.fromtimestamp(t / 1000) for t in times]

        # Plot candlesticks
        for i, (open_price, high, low, close, date) in enumerate(
            zip(opens, highs, lows, closes, dates)
        ):
            color = "green" if close > open_price else "red"
            alpha = 0.8

            # Draw the high-low line
            self.ax.plot([i, i], [low, high], color="black", linewidth=1, alpha=alpha)

            # Draw the open-close rectangle
            height = abs(close - open_price)
            bottom = min(open_price, close)

            rect = Rectangle(
                (i - 0.3, bottom),
                0.6,
                height,
                facecolor=color,
                edgecolor="black",
                alpha=alpha,
            )
            self.ax.add_patch(rect)

        # Customize chart
        self.ax.set_title(
            f"{self.symbol} - {self.timeframe}", fontsize=14, fontweight="bold"
        )
        self.ax.set_ylabel("Price", fontsize=12)
        self.ax.grid(True, alpha=0.3)

        # Format x-axis labels (show only some timestamps to avoid crowding)
        if len(dates) > 0:
            step = max(1, len(dates) // 10)
            tick_positions = list(range(0, len(dates), step))
            tick_labels = [dates[i].strftime("%m/%d %H:%M") for i in tick_positions]
            self.ax.set_xticks(tick_positions)
            self.ax.set_xticklabels(tick_labels, rotation=45, ha="right")

        # Add simple moving averages
        if len(closes) >= 20:
            sma_20 = self._calculate_sma(closes, 20)
            self.ax.plot(
                range(19, len(closes)), sma_20, label="SMA 20", color="blue", alpha=0.7
            )

        if len(closes) >= 50:
            sma_50 = self._calculate_sma(closes, 50)
            self.ax.plot(
                range(49, len(closes)),
                sma_50,
                label="SMA 50",
                color="orange",
                alpha=0.7,
            )

        # Add legend if we have indicators
        if len(closes) >= 20:
            self.ax.legend()

        # Refresh canvas
        self.canvas.draw()

    def _calculate_sma(self, prices: List[float], period: int) -> List[float]:
        """Calculate Simple Moving Average."""
        sma = []
        for i in range(period - 1, len(prices)):
            avg = sum(prices[i - period + 1 : i + 1]) / period
            sma.append(avg)
        return sma

    def refresh_chart(self):
        """Refresh chart data and redraw."""
        self.symbol = self.symbol_var.get()
        self.timeframe = self.timeframe_var.get()

        # Fetch new data
        self.candle_data = self.fetcher.get_candle_data(
            self.symbol, self.timeframe, self.limit
        )

        # Redraw chart
        self._plot_candlesticks()

    def _on_symbol_change(self, event=None):
        """Handle symbol change."""
        self.refresh_chart()

    def _on_timeframe_change(self, event=None):
        """Handle timeframe change."""
        self.refresh_chart()

    def _on_auto_refresh_change(self):
        """Handle auto-refresh toggle."""
        self.auto_refresh = self.auto_refresh_var.get()
        if self.auto_refresh:
            self._schedule_refresh()
        elif self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None

    def _schedule_refresh(self):
        """Schedule the next auto-refresh."""
        if self.auto_refresh:
            self.after_id = self.after(self.refresh_interval, self._auto_refresh)

    def _auto_refresh(self):
        """Perform automatic refresh."""
        if self.auto_refresh:
            self.refresh_chart()
            self._schedule_refresh()

    def destroy(self):
        """Clean up when destroying the widget."""
        if self.after_id:
            self.after_cancel(self.after_id)
        super().destroy()


class AccountValueChart(ttk.Frame):
    """
    Enhanced account value chart with performance metrics and portfolio analysis.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.account_history = []
        self.pnl_history = []
        self._setup_ui()
        self._setup_chart()

        # Load initial data
        self.load_account_data()

        # Auto-refresh
        self.auto_refresh = True
        self.refresh_interval = 60000  # 1 minute
        self._schedule_refresh()

    def _setup_ui(self):
        """Setup the chart UI components."""
        # Control frame
        control_frame = ttk.Frame(self)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        # Time range selector
        ttk.Label(control_frame, text="Time Range:").pack(side=tk.LEFT)
        self.time_range_var = tk.StringVar(value="7d")
        time_combo = ttk.Combobox(
            control_frame,
            textvariable=self.time_range_var,
            values=["1d", "7d", "30d", "90d", "1y", "All"],
            width=8,
        )
        time_combo.pack(side=tk.LEFT, padx=(5, 10))
        time_combo.bind("<<ComboboxSelected>>", self._on_time_range_change)

        # Refresh button
        refresh_btn = ttk.Button(
            control_frame, text="Refresh", command=self.refresh_chart
        )
        refresh_btn.pack(side=tk.LEFT, padx=(5, 0))

        # Auto-refresh checkbox
        self.auto_refresh_var = tk.BooleanVar(value=self.auto_refresh)
        auto_check = ttk.Checkbutton(
            control_frame,
            text="Auto-refresh",
            variable=self.auto_refresh_var,
            command=self._on_auto_refresh_change,
        )
        auto_check.pack(side=tk.LEFT, padx=(10, 0))

        # Performance metrics frame
        metrics_frame = ttk.LabelFrame(
            control_frame, text="Performance Metrics", padding=5
        )
        metrics_frame.pack(side=tk.RIGHT, padx=(10, 0))

        self.total_return_label = ttk.Label(metrics_frame, text="Total Return: --")
        self.total_return_label.grid(row=0, column=0, sticky="w")

        self.daily_return_label = ttk.Label(metrics_frame, text="Daily Return: --")
        self.daily_return_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.max_drawdown_label = ttk.Label(metrics_frame, text="Max Drawdown: --")
        self.max_drawdown_label.grid(row=1, column=0, sticky="w")

        self.sharpe_ratio_label = ttk.Label(metrics_frame, text="Sharpe Ratio: --")
        self.sharpe_ratio_label.grid(row=1, column=1, sticky="w", padx=(10, 0))

        # Chart frame
        self.chart_frame = ttk.Frame(self)
        self.chart_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def _setup_chart(self):
        """Setup the matplotlib chart."""
        self.fig = Figure(figsize=(12, 8), dpi=100, facecolor="white")

        # Create subplots
        gs = self.fig.add_gridspec(3, 1, height_ratios=[2, 1, 1], hspace=0.3)
        self.ax_value = self.fig.add_subplot(gs[0])
        self.ax_pnl = self.fig.add_subplot(gs[1])
        self.ax_drawdown = self.fig.add_subplot(gs[2])

        # Create canvas
        self.canvas = FigureCanvasTkAgg(self.fig, self.chart_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Add toolbar
        from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

        toolbar = NavigationToolbar2Tk(self.canvas, self.chart_frame)
        toolbar.update()

        self.fig.subplots_adjust(left=0.1, right=0.95, top=0.95, bottom=0.1)

    def load_account_data(self):
        """Load account value history from file."""
        try:
            # Try to load from hub data directory
            import pt_paths

            hub_data_dir = os.environ.get("POWERTRADER_HUB_DIR") or pt_paths.hub_dir()

            # Load account value history
            account_file = os.path.join(hub_data_dir, "account_value_history.jsonl")
            if os.path.exists(account_file):
                with open(account_file, "r") as f:
                    lines = f.readlines()
                    self.account_history = [
                        json.loads(line.strip()) for line in lines if line.strip()
                    ]

            # Load PnL data
            pnl_file = os.path.join(hub_data_dir, "pnl_ledger.json")
            if os.path.exists(pnl_file):
                with open(pnl_file, "r") as f:
                    pnl_data = json.load(f)
                    self.pnl_history = pnl_data.get("entries", [])

            # If no real data, generate mock data for demonstration
            if not self.account_history:
                self._generate_mock_account_data()

        except Exception as e:
            print(f"Error loading account data: {e}")
            self._generate_mock_account_data()

    def _generate_mock_account_data(self):
        """Generate mock account data for demonstration."""
        import datetime

        self.account_history = []
        self.pnl_history = []

        base_value = 10000.0
        current_time = time.time()

        for i in range(30):  # Last 30 days
            timestamp = current_time - (29 - i) * 24 * 3600

            # Simulate account value changes
            if i == 0:
                value = base_value
            else:
                change = (np.random.random() - 0.5) * 0.02 * base_value  # ±2% change
                value = self.account_history[-1]["total_value"] + change

            self.account_history.append(
                {
                    "timestamp": int(timestamp),
                    "total_value": max(
                        value, base_value * 0.5
                    ),  # Don't go below 50% of base
                    "cash": value * 0.3,
                    "positions": value * 0.7,
                }
            )

            # Simulate PnL entries
            if i > 0:
                pnl = value - self.account_history[-2]["total_value"]
                self.pnl_history.append(
                    {
                        "timestamp": int(timestamp),
                        "amount": pnl,
                        "type": "unrealized" if abs(pnl) < 100 else "realized",
                    }
                )

    def _plot_account_charts(self):
        """Plot account value, PnL, and drawdown charts."""
        if not self.account_history:
            return

        # Clear all subplots
        self.ax_value.clear()
        self.ax_pnl.clear()
        self.ax_drawdown.clear()

        # Filter data by time range
        filtered_data = self._filter_data_by_time_range()

        if not filtered_data:
            return

        # Extract data
        timestamps = [d["timestamp"] for d in filtered_data]
        values = [d["total_value"] for d in filtered_data]

        # Convert timestamps to datetime
        import datetime

        dates = [datetime.datetime.fromtimestamp(ts) for ts in timestamps]

        # Plot account value
        self.ax_value.plot(dates, values, linewidth=2, color="blue", alpha=0.8)
        self.ax_value.set_title("Account Value Over Time", fontweight="bold")
        self.ax_value.set_ylabel("Value ($)")
        self.ax_value.grid(True, alpha=0.3)
        self.ax_value.tick_params(axis="x", labelbottom=False)

        # Fill area under curve
        self.ax_value.fill_between(dates, values, alpha=0.2, color="blue")

        # Plot daily PnL
        if len(values) > 1:
            daily_pnl = [values[i] - values[i - 1] for i in range(1, len(values))]
            pnl_dates = dates[1:]

            colors = ["green" if pnl >= 0 else "red" for pnl in daily_pnl]
            self.ax_pnl.bar(pnl_dates, daily_pnl, color=colors, alpha=0.7, width=0.8)
            self.ax_pnl.axhline(y=0, color="black", linestyle="-", alpha=0.3)
            self.ax_pnl.set_title("Daily PnL", fontweight="bold")
            self.ax_pnl.set_ylabel("PnL ($)")
            self.ax_pnl.grid(True, alpha=0.3)
            self.ax_pnl.tick_params(axis="x", labelbottom=False)

            # Calculate and plot drawdown
            peak = np.maximum.accumulate(values)
            drawdown = (np.array(values) - peak) / peak * 100

            self.ax_drawdown.fill_between(dates, drawdown, 0, color="red", alpha=0.3)
            self.ax_drawdown.plot(dates, drawdown, color="red", alpha=0.7)
            self.ax_drawdown.axhline(y=0, color="black", linestyle="-", alpha=0.3)
            self.ax_drawdown.set_title("Drawdown (%)", fontweight="bold")
            self.ax_drawdown.set_ylabel("Drawdown (%)")
            self.ax_drawdown.set_xlabel("Date")
            self.ax_drawdown.grid(True, alpha=0.3)

            # Format x-axis
            from matplotlib.dates import DateFormatter

            date_formatter = DateFormatter("%m/%d")
            self.ax_drawdown.xaxis.set_major_formatter(date_formatter)
            self.ax_drawdown.tick_params(axis="x", rotation=45)

            # Update performance metrics
            self._update_performance_metrics(values, peak, drawdown)

        # Refresh canvas
        self.canvas.draw()

    def _filter_data_by_time_range(self) -> List[Dict]:
        """Filter account history by selected time range."""
        if not self.account_history:
            return []

        time_range = self.time_range_var.get()
        current_time = time.time()

        if time_range == "All":
            return self.account_history

        # Calculate cutoff time
        time_deltas = {
            "1d": 24 * 3600,
            "7d": 7 * 24 * 3600,
            "30d": 30 * 24 * 3600,
            "90d": 90 * 24 * 3600,
            "1y": 365 * 24 * 3600,
        }

        cutoff_time = current_time - time_deltas.get(time_range, 7 * 24 * 3600)

        return [d for d in self.account_history if d["timestamp"] >= cutoff_time]

    def _update_performance_metrics(
        self, values: List[float], peak: np.ndarray, drawdown: np.ndarray
    ):
        """Update performance metrics display."""
        if len(values) < 2:
            return

        # Calculate metrics
        initial_value = values[0]
        final_value = values[-1]
        total_return = (final_value - initial_value) / initial_value * 100

        if len(values) > 1:
            daily_returns = [
                (values[i] - values[i - 1]) / values[i - 1]
                for i in range(1, len(values))
            ]
            avg_daily_return = np.mean(daily_returns) * 100

            # Max drawdown
            max_drawdown = np.min(drawdown)

            # Simple Sharpe ratio calculation (assuming 0% risk-free rate)
            if np.std(daily_returns) > 0:
                sharpe_ratio = (
                    np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
                )  # Annualized
            else:
                sharpe_ratio = 0
        else:
            avg_daily_return = 0
            max_drawdown = 0
            sharpe_ratio = 0

        # Update labels
        self.total_return_label.configure(
            text=f"Total Return: {total_return:+.2f}%",
            foreground="green" if total_return >= 0 else "red",
        )

        self.daily_return_label.configure(
            text=f"Avg Daily: {avg_daily_return:+.2f}%",
            foreground="green" if avg_daily_return >= 0 else "red",
        )

        self.max_drawdown_label.configure(
            text=f"Max Drawdown: {max_drawdown:.2f}%",
            foreground=(
                "red"
                if max_drawdown < -5
                else "orange" if max_drawdown < -2 else "black"
            ),
        )

        self.sharpe_ratio_label.configure(
            text=f"Sharpe Ratio: {sharpe_ratio:.2f}",
            foreground=(
                "green" if sharpe_ratio > 1 else "orange" if sharpe_ratio > 0 else "red"
            ),
        )

    def refresh_chart(self):
        """Refresh chart data and redraw."""
        self.load_account_data()
        self._plot_account_charts()

    def _on_time_range_change(self, event=None):
        """Handle time range change."""
        self._plot_account_charts()

    def _on_auto_refresh_change(self):
        """Handle auto-refresh toggle."""
        self.auto_refresh = self.auto_refresh_var.get()
        if self.auto_refresh:
            self._schedule_refresh()
        elif hasattr(self, "after_id") and self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None

    def _schedule_refresh(self):
        """Schedule the next auto-refresh."""
        if self.auto_refresh:
            self.after_id = self.after(self.refresh_interval, self._auto_refresh)

    def _auto_refresh(self):
        """Perform automatic refresh."""
        if self.auto_refresh:
            self.refresh_chart()
            self._schedule_refresh()

    def destroy(self):
        """Clean up when destroying the widget."""
        if hasattr(self, "after_id") and self.after_id:
            self.after_cancel(self.after_id)
        super().destroy()


class TechnicalIndicatorChart(ttk.Frame):
    """
    Specialized chart for displaying technical indicators and signals.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.indicators = {}
        self.signals = {}

        self._setup_ui()
        self._setup_chart()

    def _setup_ui(self):
        """Setup the indicator chart UI."""
        # Control frame
        control_frame = ttk.Frame(self)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        # Indicator selection
        ttk.Label(control_frame, text="Indicators:").pack(side=tk.LEFT)

        self.rsi_var = tk.BooleanVar(value=True)
        self.macd_var = tk.BooleanVar(value=True)
        self.bollinger_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(
            control_frame, text="RSI", variable=self.rsi_var, command=self.update_chart
        ).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(
            control_frame,
            text="MACD",
            variable=self.macd_var,
            command=self.update_chart,
        ).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(
            control_frame,
            text="Bollinger Bands",
            variable=self.bollinger_var,
            command=self.update_chart,
        ).pack(side=tk.LEFT, padx=5)

        # Chart frame
        self.chart_frame = ttk.Frame(self)
        self.chart_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def _setup_chart(self):
        """Setup the matplotlib chart."""
        self.fig = Figure(figsize=(12, 8), dpi=100, facecolor="white")

        # Create dynamic subplot layout based on selected indicators
        self.axes = {}

        # Create canvas
        self.canvas = FigureCanvasTkAgg(self.fig, self.chart_frame)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def update_chart(self, price_data: Optional[List[Dict]] = None):
        """Update the chart with current indicators."""
        if price_data:
            self._calculate_indicators(price_data)

        self.fig.clear()
        self.axes.clear()

        # Determine subplot layout
        subplot_count = sum(
            [self.rsi_var.get(), self.macd_var.get(), 1]  # Always have price chart
        )

        if subplot_count == 1:
            gs = self.fig.add_gridspec(1, 1)
        elif subplot_count == 2:
            gs = self.fig.add_gridspec(2, 1, height_ratios=[2, 1], hspace=0.3)
        else:
            gs = self.fig.add_gridspec(3, 1, height_ratios=[2, 1, 1], hspace=0.3)

        # Price chart (always first)
        self.axes["price"] = self.fig.add_subplot(gs[0])
        self._plot_price_chart()

        # Add indicator subplots
        subplot_idx = 1

        if self.rsi_var.get() and "rsi" in self.indicators:
            self.axes["rsi"] = self.fig.add_subplot(gs[subplot_idx])
            self._plot_rsi()
            subplot_idx += 1

        if self.macd_var.get() and "macd" in self.indicators:
            self.axes["macd"] = self.fig.add_subplot(gs[subplot_idx])
            self._plot_macd()
            subplot_idx += 1

        self.canvas.draw()

    def _calculate_indicators(self, price_data: List[Dict]):
        """Calculate technical indicators from price data."""
        if len(price_data) < 14:
            return

        closes = [float(d["close"]) for d in price_data]
        highs = [float(d["high"]) for d in price_data]
        lows = [float(d["low"]) for d in price_data]

        # RSI calculation
        if len(closes) >= 14:
            self.indicators["rsi"] = self._calculate_rsi(closes)

        # MACD calculation
        if len(closes) >= 26:
            self.indicators["macd"] = self._calculate_macd(closes)

        # Bollinger Bands
        if len(closes) >= 20:
            self.indicators["bollinger"] = self._calculate_bollinger_bands(closes)

    def _calculate_rsi(self, closes: List[float], period: int = 14) -> List[float]:
        """Calculate Relative Strength Index."""
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        rsi = []
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        for i in range(period, len(gains)):
            if avg_loss == 0:
                rsi.append(100)
            else:
                rs = avg_gain / avg_loss
                rsi_value = 100 - (100 / (1 + rs))
                rsi.append(rsi_value)

            # Update averages
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        return rsi

    def _calculate_macd(self, closes: List[float]) -> Dict[str, List[float]]:
        """Calculate MACD indicator."""

        def ema(data, period):
            multiplier = 2 / (period + 1)
            ema_values = [sum(data[:period]) / period]  # SMA for first value

            for i in range(period, len(data)):
                ema_values.append(
                    (data[i] * multiplier) + (ema_values[-1] * (1 - multiplier))
                )

            return ema_values

        if len(closes) >= 26:
            ema_12 = ema(closes, 12)
            ema_26 = ema(closes, 26)

            # MACD line
            macd_line = [ema_12[i] - ema_26[i] for i in range(len(ema_26))]

            # Signal line (9-period EMA of MACD)
            signal_line = ema(macd_line, 9)

            # Histogram
            histogram = [
                macd_line[len(macd_line) - len(signal_line) + i] - signal_line[i]
                for i in range(len(signal_line))
            ]

            return {"macd": macd_line, "signal": signal_line, "histogram": histogram}

        return {}

    def _calculate_bollinger_bands(
        self, closes: List[float], period: int = 20, std_dev: float = 2
    ) -> Dict[str, List[float]]:
        """Calculate Bollinger Bands."""
        sma = []
        upper = []
        lower = []

        for i in range(period - 1, len(closes)):
            window = closes[i - period + 1 : i + 1]
            mean = sum(window) / period
            variance = sum((x - mean) ** 2 for x in window) / period
            std = variance**0.5

            sma.append(mean)
            upper.append(mean + (std_dev * std))
            lower.append(mean - (std_dev * std))

        return {"middle": sma, "upper": upper, "lower": lower}

    def _plot_price_chart(self):
        """Plot price chart with Bollinger Bands if enabled."""
        ax = self.axes["price"]
        ax.set_title("Price Chart with Technical Indicators", fontweight="bold")
        ax.grid(True, alpha=0.3)

        # Plot Bollinger Bands if enabled and available
        if self.bollinger_var.get() and "bollinger" in self.indicators:
            bb = self.indicators["bollinger"]
            x_bb = range(len(bb["middle"]))

            ax.plot(x_bb, bb["upper"], color="gray", alpha=0.5, label="BB Upper")
            ax.plot(x_bb, bb["middle"], color="blue", alpha=0.7, label="BB Middle")
            ax.plot(x_bb, bb["lower"], color="gray", alpha=0.5, label="BB Lower")
            ax.fill_between(x_bb, bb["upper"], bb["lower"], alpha=0.1, color="gray")
            ax.legend()

    def _plot_rsi(self):
        """Plot RSI indicator."""
        ax = self.axes["rsi"]
        rsi_data = self.indicators["rsi"]

        x = range(len(rsi_data))
        ax.plot(x, rsi_data, color="purple", linewidth=2)
        ax.axhline(70, color="red", linestyle="--", alpha=0.7, label="Overbought (70)")
        ax.axhline(30, color="green", linestyle="--", alpha=0.7, label="Oversold (30)")
        ax.axhline(50, color="gray", linestyle="-", alpha=0.5)

        ax.set_title("RSI (14)", fontweight="bold")
        ax.set_ylabel("RSI")
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3)
        ax.legend()

    def _plot_macd(self):
        """Plot MACD indicator."""
        ax = self.axes["macd"]
        macd_data = self.indicators["macd"]

        if "macd" in macd_data and "signal" in macd_data:
            x_macd = range(len(macd_data["macd"]))
            x_signal = range(
                len(macd_data["macd"]) - len(macd_data["signal"]),
                len(macd_data["macd"]),
            )

            ax.plot(x_macd, macd_data["macd"], color="blue", linewidth=2, label="MACD")
            ax.plot(
                x_signal, macd_data["signal"], color="red", linewidth=2, label="Signal"
            )

            if "histogram" in macd_data:
                x_hist = range(
                    len(macd_data["macd"]) - len(macd_data["histogram"]),
                    len(macd_data["macd"]),
                )
                colors = ["green" if h > 0 else "red" for h in macd_data["histogram"]]
                ax.bar(
                    x_hist, macd_data["histogram"], color=colors, alpha=0.7, width=0.8
                )

            ax.axhline(0, color="gray", linestyle="-", alpha=0.5)
            ax.set_title("MACD", fontweight="bold")
            ax.set_ylabel("MACD")
            ax.grid(True, alpha=0.3)
            ax.legend()

    def add_signal(self, signal_type: str, x: int, y: float, direction: str):
        """Add a trading signal to the chart."""
        if "price" in self.axes:
            ax = self.axes["price"]
            color = "green" if direction == "buy" else "red"
            marker = "^" if direction == "buy" else "v"
            ax.scatter(
                x,
                y,
                color=color,
                marker=marker,
                s=100,
                alpha=0.8,
                label=(
                    f"{signal_type.upper()} Signal"
                    if signal_type not in self.signals
                    else ""
                ),
            )
            self.signals[signal_type] = True
            ax.legend()
            self.canvas.draw()
