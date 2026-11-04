#!/usr/bin/env python3
"""
Backtesting GUI for PowerTrader
Interactive interface for strategy backtesting, optimization, and Monte Carlo analysis.
"""

import json
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import ui_table
import ui_theme
import ui_tokens

try:
    from backtesting_engine import (
        BacktestEngine,
        MovingAverageCrossStrategy,
        PositionType,
        RSIStrategy,
        TradingStrategy,
    )

    BACKTESTING_AVAILABLE = True
except ImportError:
    BACKTESTING_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False


class BacktestingGUI:
    """
    Interactive GUI for backtesting trading strategies.
    """

    def __init__(self, parent=None):
        """Initialize the Backtesting GUI."""
        if parent is None:
            self.root = ui_theme.themed_root()
            self.root.title("Backtesting Framework")
            self.root.geometry("1400x900")
        else:
            self.root = parent

        # Initialize backtesting engine
        if BACKTESTING_AVAILABLE:
            self.engine = BacktestEngine()
        else:
            self.engine = None

        # GUI state
        self.current_data = None
        self.backtest_results = None
        self.monte_carlo_results = None
        self.optimization_results = None

        self.setup_gui()

    def setup_gui(self):
        """Setup the main GUI layout."""
        if not BACKTESTING_AVAILABLE:
            self.show_dependency_message()
            return

        # Create main notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Create tabs
        self.setup_data_strategy_tab()
        self.setup_results_tab()
        self.setup_optimization_tab()
        self.setup_monte_carlo_tab()

    def show_dependency_message(self):
        """Show message about missing dependencies."""
        p = ui_theme.active_palette()
        msg_frame = tk.Frame(self.root)
        msg_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            msg_frame,
            text="Backtesting Framework - Enhanced Features Available",
            font=ui_tokens.font("display", "bold"),
        ).pack(pady=20)

        tk.Label(
            msg_frame,
            text="For full backtesting capabilities, install optional dependencies:",
            font=ui_tokens.font("title"),
        ).pack(pady=10)

        tk.Label(
            msg_frame,
            text="python app/install_optional_deps.py",
            font=ui_tokens.mono("body"),
            background=p["PANEL"],
            foreground=p["FG"],
        ).pack(pady=5)

        features = [
            "• Historical strategy backtesting",
            "• Monte Carlo simulation analysis",
            "• Parameter optimization",
            "• Advanced performance metrics",
            "• Interactive charts and reports",
            "• Statistical analysis tools",
        ]

        tk.Label(
            msg_frame,
            text="Features available with enhanced dependencies:",
            font=ui_tokens.font("subtitle", "bold"),
        ).pack(pady=(20, 5))

        for feature in features:
            tk.Label(msg_frame, text=feature, font=ui_tokens.font("body")).pack(
                anchor="w", padx=100
            )

        return

    def setup_data_strategy_tab(self):
        """Setup the data input and strategy configuration tab."""
        data_frame = ttk.Frame(self.notebook)
        self.notebook.add(data_frame, text="Data & Strategy")

        # Create left and right panels
        left_panel = ttk.Frame(data_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        right_panel = ttk.Frame(data_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # Left Panel - Data Input
        self.setup_data_input_section(left_panel)

        # Right Panel - Strategy Configuration
        self.setup_strategy_section(right_panel)

        # Bottom Panel - Backtest Controls
        bottom_panel = ttk.Frame(data_frame)
        bottom_panel.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        self.setup_backtest_controls(bottom_panel)

    def setup_data_input_section(self, parent):
        """Setup data input section."""
        data_section = ttk.LabelFrame(parent, text="Historical Data")
        data_section.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # File input
        file_frame = tk.Frame(data_section)
        file_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(file_frame, text="Data File:").pack(side=tk.LEFT)
        self.data_file_var = tk.StringVar()
        tk.Entry(file_frame, textvariable=self.data_file_var, width=40).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(file_frame, text="Browse", command=self.browse_data_file).pack(
            side=tk.LEFT
        )
        ttk.Button(file_frame, text="Load Sample", command=self.load_sample_data).pack(
            side=tk.LEFT, padx=5
        )

        # Data info display
        info_frame = ttk.LabelFrame(data_section, text="Data Information")
        info_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.data_info_text = tk.Text(info_frame, height=8, wrap=tk.WORD)
        data_scrollbar = ttk.Scrollbar(info_frame, orient=tk.VERTICAL)
        ui_table.scroll_when_needed(self.data_info_text, data_scrollbar)

        # Backtest parameters
        params_frame = ttk.LabelFrame(data_section, text="Backtest Parameters")
        params_frame.pack(fill=tk.X, padx=5, pady=5)

        params_grid = tk.Frame(params_frame)
        params_grid.pack(padx=5, pady=5)

        tk.Label(params_grid, text="Initial Capital ($):").grid(
            row=0, column=0, sticky="w", padx=5
        )
        self.initial_capital_var = tk.StringVar(value="100000")
        tk.Entry(params_grid, textvariable=self.initial_capital_var, width=15).grid(
            row=0, column=1, padx=5
        )

        tk.Label(params_grid, text="Commission (%):").grid(
            row=0, column=2, sticky="w", padx=5
        )
        self.commission_var = tk.StringVar(value="0.1")
        tk.Entry(params_grid, textvariable=self.commission_var, width=15).grid(
            row=0, column=3, padx=5
        )

    def setup_strategy_section(self, parent):
        """Setup strategy configuration section."""
        strategy_section = ttk.LabelFrame(parent, text="Trading Strategy")
        strategy_section.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Strategy selection
        selection_frame = tk.Frame(strategy_section)
        selection_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(selection_frame, text="Strategy:").pack(side=tk.LEFT)
        self.strategy_var = tk.StringVar(value="MA Cross")
        strategy_combo = ttk.Combobox(
            selection_frame,
            textvariable=self.strategy_var,
            values=["MA Cross", "RSI Strategy"],
            state="readonly",
            width=15,
        )
        strategy_combo.pack(side=tk.LEFT, padx=5)
        strategy_combo.bind("<<ComboboxSelected>>", self.on_strategy_change)

        # Strategy parameters frame (dynamic content)
        self.strategy_params_frame = ttk.LabelFrame(
            strategy_section, text="Strategy Parameters"
        )
        self.strategy_params_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Initialize with MA Cross parameters
        self.setup_ma_cross_params()

        # Strategy description
        desc_frame = ttk.LabelFrame(strategy_section, text="Strategy Description")
        desc_frame.pack(fill=tk.X, padx=5, pady=5)

        self.strategy_desc_text = tk.Text(desc_frame, height=6, wrap=tk.WORD)
        desc_scrollbar = ttk.Scrollbar(desc_frame, orient=tk.VERTICAL)
        ui_table.scroll_when_needed(self.strategy_desc_text, desc_scrollbar)

        self.update_strategy_description()

    def setup_backtest_controls(self, parent):
        """Setup backtest control buttons."""
        controls_frame = ttk.LabelFrame(parent, text="Backtest Controls")
        controls_frame.pack(fill=tk.X, padx=5, pady=5)

        buttons_frame = tk.Frame(controls_frame)
        buttons_frame.pack(padx=5, pady=5)

        ttk.Button(buttons_frame, text="Run Backtest", command=self.run_backtest).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(buttons_frame, text="Quick Test", command=self.run_quick_test).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            buttons_frame, text="Clear Results", command=self.clear_results
        ).pack(side=tk.LEFT, padx=5)

        # Progress bar
        self.progress_var = tk.StringVar(value="Ready")
        tk.Label(controls_frame, textvariable=self.progress_var).pack(pady=5)

        self.progress_bar = ttk.Progressbar(controls_frame, mode="indeterminate")
        self.progress_bar.pack(fill=tk.X, padx=5, pady=5)

    def setup_results_tab(self):
        """Setup the results display tab."""
        results_frame = ttk.Frame(self.notebook)
        self.notebook.add(results_frame, text="Results")

        # Create left and right panels
        left_panel = ttk.Frame(results_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        right_panel = ttk.Frame(results_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # Performance metrics
        metrics_frame = ttk.LabelFrame(left_panel, text="Performance Metrics")
        metrics_frame.pack(fill=tk.X, padx=5, pady=5)

        self.metrics_table = ui_table.DataTable(
            metrics_frame,
            ("Value",),
            {"Value": "Value"},
            key="backtesting.metrics",
            numeric=("Value",),
            empty_text="No metrics yet",
            show="tree headings",
            sortable=False,  # metrics grouped under section rows, not to sort
            height=12,
        )
        self.metrics_table.pack(fill=tk.BOTH, expand=True)
        self.metrics_tree = self.metrics_table.tree
        self.metrics_tree.heading("#0", text="Metric")  # each row's own text

        # Trade list
        trades_frame = ttk.LabelFrame(left_panel, text="Trade History")
        trades_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.trades_table = ui_table.DataTable(
            trades_frame,
            ("Entry", "Exit", "PnL", "PnL%", "Duration"),
            {
                "Entry": "Entry",
                "Exit": "Exit",
                "PnL": "PnL",
                "PnL%": "PnL%",
                "Duration": "Duration",
            },
            key="backtesting.trades",
            numeric=("PnL", "PnL%", "Duration"),
            empty_text="No trades yet",
        )
        self.trades_table.pack(fill=tk.BOTH, expand=True)
        self.trades_tree = self.trades_table.tree

        # Charts section
        charts_frame = ttk.LabelFrame(right_panel, text="Performance Charts")
        charts_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Chart controls
        chart_controls = tk.Frame(charts_frame)
        chart_controls.pack(fill=tk.X, padx=5, pady=5)

        if PLOTTING_AVAILABLE:
            ttk.Button(
                chart_controls, text="Equity Curve", command=self.plot_equity_curve
            ).pack(side=tk.LEFT, padx=5)
            ttk.Button(
                chart_controls, text="Drawdown", command=self.plot_drawdown
            ).pack(side=tk.LEFT, padx=5)
            ttk.Button(
                chart_controls,
                text="Monthly Returns",
                command=self.plot_monthly_returns,
            ).pack(side=tk.LEFT, padx=5)
        else:
            tk.Label(chart_controls, text="Install matplotlib for charts").pack()

        # Chart display area
        self.chart_frame = tk.Frame(charts_frame)
        self.chart_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def setup_optimization_tab(self):
        """Setup the parameter optimization tab."""
        opt_frame = ttk.Frame(self.notebook)
        self.notebook.add(opt_frame, text="Optimization")

        # Parameter grid setup
        grid_frame = ttk.LabelFrame(opt_frame, text="Parameter Grid")
        grid_frame.pack(fill=tk.X, padx=10, pady=10)

        # Strategy selection for optimization
        strategy_frame = tk.Frame(grid_frame)
        strategy_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(strategy_frame, text="Strategy to Optimize:").pack(side=tk.LEFT)
        self.opt_strategy_var = tk.StringVar(value="MA Cross")
        ttk.Combobox(
            strategy_frame,
            textvariable=self.opt_strategy_var,
            values=["MA Cross", "RSI Strategy"],
            state="readonly",
        ).pack(side=tk.LEFT, padx=5)

        # Parameter ranges (dynamic based on strategy)
        self.param_grid_frame = tk.Frame(grid_frame)
        self.param_grid_frame.pack(fill=tk.X, padx=5, pady=5)

        self.setup_ma_optimization_params()

        # Optimization controls
        opt_controls = tk.Frame(opt_frame)
        opt_controls.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(
            opt_controls, text="Run Optimization", command=self.run_optimization
        ).pack(side=tk.LEFT, padx=5)

        tk.Label(opt_controls, text="Optimization Metric:").pack(side=tk.LEFT, padx=20)
        self.opt_metric_var = tk.StringVar(value="sharpe_ratio")
        ttk.Combobox(
            opt_controls,
            textvariable=self.opt_metric_var,
            values=["sharpe_ratio", "total_return", "calmar_ratio"],
            state="readonly",
        ).pack(side=tk.LEFT, padx=5)

        # Results display
        opt_results_frame = ttk.LabelFrame(opt_frame, text="Optimization Results")
        opt_results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.opt_results_table = ui_table.DataTable(
            opt_results_frame,
            ("Parameters", "Score", "Return", "Sharpe"),
            {
                "Parameters": "Parameters",
                "Score": "Score",
                "Return": "Return",
                "Sharpe": "Sharpe",
            },
            key="backtesting.optimization_results",
            numeric=("Score", "Return", "Sharpe"),
            empty_text="No results yet",
        )
        self.opt_results_table.pack(fill=tk.BOTH, expand=True)
        self.opt_results_tree = self.opt_results_table.tree

    def setup_monte_carlo_tab(self):
        """Setup the Monte Carlo simulation tab."""
        mc_frame = ttk.Frame(self.notebook)
        self.notebook.add(mc_frame, text="Monte Carlo")

        # Simulation parameters
        params_frame = ttk.LabelFrame(mc_frame, text="Simulation Parameters")
        params_frame.pack(fill=tk.X, padx=10, pady=10)

        params_grid = tk.Frame(params_frame)
        params_grid.pack(padx=5, pady=5)

        tk.Label(params_grid, text="Number of Simulations:").grid(
            row=0, column=0, sticky="w", padx=5
        )
        self.mc_simulations_var = tk.StringVar(value="1000")
        tk.Entry(params_grid, textvariable=self.mc_simulations_var, width=10).grid(
            row=0, column=1, padx=5
        )

        tk.Label(params_grid, text="Confidence Level (%):").grid(
            row=0, column=2, sticky="w", padx=5
        )
        self.mc_confidence_var = tk.StringVar(value="95")
        tk.Entry(params_grid, textvariable=self.mc_confidence_var, width=10).grid(
            row=0, column=3, padx=5
        )

        # Control buttons
        controls_frame = tk.Frame(mc_frame)
        controls_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(
            controls_frame, text="Run Monte Carlo", command=self.run_monte_carlo
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            controls_frame,
            text="Quick MC (100 runs)",
            command=self.run_quick_monte_carlo,
        ).pack(side=tk.LEFT, padx=5)

        # Results display
        mc_results_frame = ttk.LabelFrame(mc_frame, text="Monte Carlo Results")
        mc_results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Split into stats and distribution
        self.mc_stats_table = ui_table.DataTable(
            mc_results_frame,
            ("Value",),
            {"Value": "Value"},
            key="backtesting.monte_carlo_stats",
            numeric=("Value",),
            empty_text="No statistics yet",
            show="tree headings",
            sortable=False,  # a list of statistics, not rows to sort
        )
        self.mc_stats_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.mc_stats_tree = self.mc_stats_table.tree
        self.mc_stats_tree.heading("#0", text="Statistic")  # each row's own text

        # Distribution chart area
        self.mc_chart_frame = tk.Frame(mc_results_frame)
        self.mc_chart_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

    def setup_ma_cross_params(self):
        """Setup MA Cross strategy parameters."""
        # Clear existing widgets
        for widget in self.strategy_params_frame.winfo_children():
            widget.destroy()

        params_grid = tk.Frame(self.strategy_params_frame)
        params_grid.pack(padx=5, pady=5)

        tk.Label(params_grid, text="Short Window:").grid(
            row=0, column=0, sticky="w", padx=5
        )
        self.ma_short_var = tk.StringVar(value="20")
        tk.Entry(params_grid, textvariable=self.ma_short_var, width=10).grid(
            row=0, column=1, padx=5
        )

        tk.Label(params_grid, text="Long Window:").grid(
            row=0, column=2, sticky="w", padx=5
        )
        self.ma_long_var = tk.StringVar(value="50")
        tk.Entry(params_grid, textvariable=self.ma_long_var, width=10).grid(
            row=0, column=3, padx=5
        )

    def setup_rsi_params(self):
        """Setup RSI strategy parameters."""
        # Clear existing widgets
        for widget in self.strategy_params_frame.winfo_children():
            widget.destroy()

        params_grid = tk.Frame(self.strategy_params_frame)
        params_grid.pack(padx=5, pady=5)

        tk.Label(params_grid, text="RSI Period:").grid(
            row=0, column=0, sticky="w", padx=5
        )
        self.rsi_period_var = tk.StringVar(value="14")
        tk.Entry(params_grid, textvariable=self.rsi_period_var, width=10).grid(
            row=0, column=1, padx=5
        )

        tk.Label(params_grid, text="Oversold Level:").grid(
            row=0, column=2, sticky="w", padx=5
        )
        self.rsi_oversold_var = tk.StringVar(value="30")
        tk.Entry(params_grid, textvariable=self.rsi_oversold_var, width=10).grid(
            row=0, column=3, padx=5
        )

        tk.Label(params_grid, text="Overbought Level:").grid(
            row=1, column=0, sticky="w", padx=5
        )
        self.rsi_overbought_var = tk.StringVar(value="70")
        tk.Entry(params_grid, textvariable=self.rsi_overbought_var, width=10).grid(
            row=1, column=1, padx=5
        )

    def setup_ma_optimization_params(self):
        """Setup MA Cross optimization parameter ranges."""
        # Clear existing widgets
        for widget in self.param_grid_frame.winfo_children():
            widget.destroy()

        grid = tk.Frame(self.param_grid_frame)
        grid.pack(padx=5, pady=5)

        # Short window range
        tk.Label(grid, text="Short Window Range:").grid(
            row=0, column=0, sticky="w", padx=5
        )
        tk.Label(grid, text="Min:").grid(row=0, column=1, sticky="w", padx=5)
        self.opt_short_min_var = tk.StringVar(value="5")
        tk.Entry(grid, textvariable=self.opt_short_min_var, width=8).grid(
            row=0, column=2, padx=5
        )
        tk.Label(grid, text="Max:").grid(row=0, column=3, sticky="w", padx=5)
        self.opt_short_max_var = tk.StringVar(value="30")
        tk.Entry(grid, textvariable=self.opt_short_max_var, width=8).grid(
            row=0, column=4, padx=5
        )
        tk.Label(grid, text="Step:").grid(row=0, column=5, sticky="w", padx=5)
        self.opt_short_step_var = tk.StringVar(value="5")
        tk.Entry(grid, textvariable=self.opt_short_step_var, width=8).grid(
            row=0, column=6, padx=5
        )

        # Long window range
        tk.Label(grid, text="Long Window Range:").grid(
            row=1, column=0, sticky="w", padx=5
        )
        tk.Label(grid, text="Min:").grid(row=1, column=1, sticky="w", padx=5)
        self.opt_long_min_var = tk.StringVar(value="30")
        tk.Entry(grid, textvariable=self.opt_long_min_var, width=8).grid(
            row=1, column=2, padx=5
        )
        tk.Label(grid, text="Max:").grid(row=1, column=3, sticky="w", padx=5)
        self.opt_long_max_var = tk.StringVar(value="100")
        tk.Entry(grid, textvariable=self.opt_long_max_var, width=8).grid(
            row=1, column=4, padx=5
        )
        tk.Label(grid, text="Step:").grid(row=1, column=5, sticky="w", padx=5)
        self.opt_long_step_var = tk.StringVar(value="10")
        tk.Entry(grid, textvariable=self.opt_long_step_var, width=8).grid(
            row=1, column=6, padx=5
        )

    # Event handlers
    def on_strategy_change(self, event=None):
        """Handle strategy selection change."""
        strategy = self.strategy_var.get()

        if strategy == "MA Cross":
            self.setup_ma_cross_params()
        elif strategy == "RSI Strategy":
            self.setup_rsi_params()

        self.update_strategy_description()

    def update_strategy_description(self):
        """Update strategy description text."""
        strategy = self.strategy_var.get()

        descriptions = {
            "MA Cross": """Moving Average Crossover Strategy:

Generates buy signals when the short-period moving average crosses above the long-period moving average, and sell signals when it crosses below.

Parameters:
- Short Window: Period for fast moving average
- Long Window: Period for slow moving average

This is a trend-following strategy that works well in trending markets but may generate false signals in sideways markets.""",
            "RSI Strategy": """RSI Mean Reversion Strategy:

Uses the Relative Strength Index (RSI) to identify overbought and oversold conditions. Generates buy signals when RSI moves above the oversold level and sell signals when RSI moves below the overbought level.

Parameters:
- RSI Period: Period for RSI calculation (typically 14)
- Oversold Level: RSI level considered oversold (typically 30)
- Overbought Level: RSI level considered overbought (typically 70)

This is a mean-reversion strategy that works well in ranging markets.""",
        }

        self.strategy_desc_text.delete("1.0", tk.END)
        self.strategy_desc_text.insert(
            "1.0", descriptions.get(strategy, "Strategy description not available.")
        )

    def browse_data_file(self):
        """Browse for historical data file."""
        filename = filedialog.askopenfilename(
            title="Select Historical Data File",
            filetypes=[
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx"),
                ("All files", "*.*"),
            ],
        )
        if filename:
            self.data_file_var.set(filename)
            self.load_data_file(filename)

    def load_data_file(self, filename):
        """Load historical data from file."""
        try:
            if filename.endswith(".csv"):
                data = pd.read_csv(filename, index_col=0, parse_dates=True)
            elif filename.endswith(".xlsx"):
                data = pd.read_excel(filename, index_col=0, parse_dates=True)
            else:
                messagebox.showerror("Error", "Unsupported file format")
                return

            self.current_data = data
            self.display_data_info(data)
            messagebox.showinfo("Success", f"Data loaded successfully: {data.shape}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load data: {str(e)}")

    def load_sample_data(self):
        """Load sample data for testing."""
        try:
            # Generate sample data
            np.random.seed(42)
            dates = pd.date_range("2023-01-01", "2024-01-01", freq="D")
            n_days = len(dates)

            # Simulate realistic price data
            initial_price = 100
            returns = np.random.normal(0.0005, 0.02, n_days)
            prices = [initial_price]

            for ret in returns[1:]:
                new_price = prices[-1] * (1 + ret)
                prices.append(new_price)

            # Create OHLCV data
            data = pd.DataFrame(
                {
                    "open": [p * (1 + np.random.uniform(-0.01, 0.01)) for p in prices],
                    "high": [p * (1 + abs(np.random.uniform(0, 0.02))) for p in prices],
                    "low": [p * (1 - abs(np.random.uniform(0, 0.02))) for p in prices],
                    "close": prices,
                    "volume": np.random.randint(1000, 10000, n_days),
                },
                index=dates,
            )

            self.current_data = data
            self.display_data_info(data)
            messagebox.showinfo("Success", "Sample data loaded successfully")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate sample data: {str(e)}")

    def display_data_info(self, data):
        """Display data information in the text widget."""
        self.data_info_text.delete("1.0", tk.END)

        info_text = f"Data Information:\n"
        info_text += f"=" * 30 + "\n\n"
        info_text += f"Time Period: {data.index[0].strftime('%Y-%m-%d')} to {data.index[-1].strftime('%Y-%m-%d')}\n"
        info_text += f"Total Days: {len(data)}\n"
        info_text += f"Columns: {', '.join(data.columns)}\n\n"

        info_text += f"Price Summary:\n"
        info_text += f"Starting Price: ${data['close'].iloc[0]:.2f}\n"
        info_text += f"Ending Price: ${data['close'].iloc[-1]:.2f}\n"
        info_text += f"Minimum Price: ${data['close'].min():.2f}\n"
        info_text += f"Maximum Price: ${data['close'].max():.2f}\n"
        info_text += f"Average Price: ${data['close'].mean():.2f}\n\n"

        # Basic statistics
        returns = data["close"].pct_change().dropna()
        info_text += f"Return Statistics:\n"
        info_text += f"Total Return: {(data['close'].iloc[-1] / data['close'].iloc[0] - 1):.2%}\n"
        info_text += f"Daily Volatility: {returns.std():.4f}\n"
        info_text += f"Annualized Volatility: {returns.std() * np.sqrt(252):.2%}\n"

        self.data_info_text.insert("1.0", info_text)

    def get_selected_strategy(self):
        """Create strategy instance based on current selection."""
        strategy_name = self.strategy_var.get()

        if strategy_name == "MA Cross":
            short_window = int(self.ma_short_var.get())
            long_window = int(self.ma_long_var.get())
            return MovingAverageCrossStrategy(short_window, long_window)

        elif strategy_name == "RSI Strategy":
            rsi_period = int(self.rsi_period_var.get())
            oversold = float(self.rsi_oversold_var.get())
            overbought = float(self.rsi_overbought_var.get())
            return RSIStrategy(rsi_period, oversold, overbought)

        else:
            raise ValueError(f"Unknown strategy: {strategy_name}")

    def run_backtest(self):
        """Run full backtest with current settings."""
        if not self.current_data is None and BACKTESTING_AVAILABLE:
            try:
                self.progress_var.set("Running backtest...")
                self.progress_bar.start()

                # Update engine parameters
                initial_capital = float(self.initial_capital_var.get())
                commission = float(self.commission_var.get()) / 100

                self.engine = BacktestEngine(initial_capital, commission)

                # Get strategy
                strategy = self.get_selected_strategy()

                # Run backtest
                self.backtest_results = self.engine.run_backtest(
                    self.current_data, strategy
                )

                # Display results
                self.display_backtest_results()

                self.progress_bar.stop()
                self.progress_var.set("Backtest completed")

                messagebox.showinfo("Success", "Backtest completed successfully!")

            except Exception as e:
                self.progress_bar.stop()
                self.progress_var.set("Error")
                messagebox.showerror("Error", f"Backtest failed: {str(e)}")
        else:
            messagebox.showerror(
                "Error", "Please load data first or check dependencies"
            )

    def run_quick_test(self):
        """Run quick test with sample data."""
        if BACKTESTING_AVAILABLE:
            self.load_sample_data()
            # Give a moment for data to load, then run backtest
            self.root.after(100, self.run_backtest)
        else:
            messagebox.showerror("Error", "Backtesting engine not available")

    def clear_results(self):
        """Clear all results."""
        self.backtest_results = None
        self.monte_carlo_results = None
        self.optimization_results = None

        # Clear displays
        for item in self.metrics_tree.get_children():
            self.metrics_tree.delete(item)

        for item in self.trades_tree.get_children():
            self.trades_tree.delete(item)

        for widget in self.chart_frame.winfo_children():
            widget.destroy()

        self.progress_var.set("Ready")

    def display_backtest_results(self):
        """Display backtest results in the GUI."""
        if not self.backtest_results:
            return

        # Clear previous results
        for item in self.metrics_tree.get_children():
            self.metrics_tree.delete(item)

        for item in self.trades_tree.get_children():
            self.trades_tree.delete(item)

        # Display metrics
        metrics = self.backtest_results.metrics

        # Format metrics for display
        metric_items = [
            ("Returns", ""),
            ("  Total Return", f"{metrics.get('total_return', 0):.2%}"),
            ("  Annualized Return", f"{metrics.get('annualized_return', 0):.2%}"),
            ("Risk Metrics", ""),
            ("  Volatility", f"{metrics.get('volatility', 0):.2%}"),
            ("  Max Drawdown", f"{metrics.get('max_drawdown', 0):.2%}"),
            ("  Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.3f}"),
            ("  Calmar Ratio", f"{metrics.get('calmar_ratio', 0):.3f}"),
            ("Trade Metrics", ""),
            ("  Total Trades", f"{metrics.get('total_trades', 0)}"),
            ("  Win Rate", f"{metrics.get('win_rate', 0):.2%}"),
            ("  Profit Factor", f"{metrics.get('profit_factor', 0):.2f}"),
            ("  Best Trade", f"${metrics.get('best_trade', 0):.2f}"),
            ("  Worst Trade", f"${metrics.get('worst_trade', 0):.2f}"),
            ("Portfolio", ""),
            ("  Initial Capital", f"${self.backtest_results.initial_capital:,.2f}"),
            ("  Final Capital", f"${self.backtest_results.final_capital:,.2f}"),
        ]

        for metric, value in metric_items:
            if not value:  # Header row
                self.metrics_tree.insert("", "end", text=metric, values=("",))
            else:
                self.metrics_tree.insert("", "end", text=metric, values=(value,))

        # Display trades
        for trade in self.backtest_results.trades[-20:]:  # Show last 20 trades
            self.trades_tree.insert(
                "",
                "end",
                values=(
                    trade.entry_time.strftime("%Y-%m-%d"),
                    trade.exit_time.strftime("%Y-%m-%d"),
                    f"${trade.pnl:.2f}",
                    f"{trade.pnl_percent:.2%}",
                    f"{trade.holding_period.days}d",
                ),
            )

    def run_optimization(self):
        """Run parameter optimization."""
        if not self.current_data is None and BACKTESTING_AVAILABLE:
            try:
                self.progress_var.set("Running optimization...")
                self.progress_bar.start()

                # Get parameter grid based on strategy
                strategy_name = self.opt_strategy_var.get()

                if strategy_name == "MA Cross":
                    short_min = int(self.opt_short_min_var.get())
                    short_max = int(self.opt_short_max_var.get())
                    short_step = int(self.opt_short_step_var.get())

                    long_min = int(self.opt_long_min_var.get())
                    long_max = int(self.opt_long_max_var.get())
                    long_step = int(self.opt_long_step_var.get())

                    param_grid = {
                        "short_window": list(
                            range(short_min, short_max + 1, short_step)
                        ),
                        "long_window": list(range(long_min, long_max + 1, long_step)),
                    }
                    strategy_class = MovingAverageCrossStrategy

                else:
                    messagebox.showerror(
                        "Error", "Optimization not implemented for this strategy"
                    )
                    return

                # Run optimization
                optimization_metric = self.opt_metric_var.get()
                self.optimization_results = self.engine.parameter_optimization(
                    self.current_data, strategy_class, param_grid, optimization_metric
                )

                self.display_optimization_results()

                self.progress_bar.stop()
                self.progress_var.set("Optimization completed")

                best_params = self.optimization_results["best_parameters"]
                messagebox.showinfo(
                    "Success",
                    f"Optimization completed!\nBest parameters: {best_params}",
                )

            except Exception as e:
                self.progress_bar.stop()
                self.progress_var.set("Error")
                messagebox.showerror("Error", f"Optimization failed: {str(e)}")
        else:
            messagebox.showerror("Error", "Please load data first")

    def display_optimization_results(self):
        """Display optimization results."""
        if not self.optimization_results:
            return

        # Clear previous results
        for item in self.opt_results_tree.get_children():
            self.opt_results_tree.delete(item)

        # Display top 20 results
        for result in self.optimization_results["all_results"][:20]:
            params_str = ", ".join(
                [f"{k}={v}" for k, v in result["parameters"].items()]
            )

            self.opt_results_tree.insert(
                "",
                "end",
                values=(
                    params_str,
                    f"{result['score']:.3f}",
                    f"{result['metrics'].get('total_return', 0):.2%}",
                    f"{result['metrics'].get('sharpe_ratio', 0):.3f}",
                ),
            )

    def run_monte_carlo(self):
        """Run Monte Carlo simulation."""
        if not self.current_data is None and BACKTESTING_AVAILABLE:
            try:
                num_simulations = int(self.mc_simulations_var.get())
                confidence_level = float(self.mc_confidence_var.get()) / 100

                self.progress_var.set(f"Running {num_simulations} simulations...")
                self.progress_bar.start()

                strategy = self.get_selected_strategy()

                self.monte_carlo_results = self.engine.monte_carlo_simulation(
                    self.current_data, strategy, num_simulations, confidence_level
                )

                self.display_monte_carlo_results()

                self.progress_bar.stop()
                self.progress_var.set("Monte Carlo completed")

                messagebox.showinfo(
                    "Success",
                    f"Monte Carlo simulation completed with {num_simulations} runs!",
                )

            except Exception as e:
                self.progress_bar.stop()
                self.progress_var.set("Error")
                messagebox.showerror("Error", f"Monte Carlo failed: {str(e)}")
        else:
            messagebox.showerror("Error", "Please load data first")

    def run_quick_monte_carlo(self):
        """Run quick Monte Carlo with 100 simulations."""
        self.mc_simulations_var.set("100")
        self.run_monte_carlo()

    def display_monte_carlo_results(self):
        """Display Monte Carlo results."""
        if not self.monte_carlo_results:
            return

        # Clear previous results
        for item in self.mc_stats_tree.get_children():
            self.mc_stats_tree.delete(item)

        results = self.monte_carlo_results
        confidence = results.get("confidence_level", 0.95) * 100

        # Format statistics
        stats_items = [
            ("Simulation Summary", ""),
            ("  Successful Runs", f"{results.get('num_simulations', 0)}"),
            ("Return Statistics", ""),
            ("  Mean Return", f"{results.get('mean_return', 0):.2%}"),
            ("  Median Return", f"{results.get('median_return', 0):.2%}"),
            ("  Std Deviation", f"{results.get('std_return', 0):.2%}"),
            ("  Min Return", f"{results.get('min_return', 0):.2%}"),
            ("  Max Return", f"{results.get('max_return', 0):.2%}"),
            (
                f"  {confidence:.0f}% CI Lower",
                f"{results.get('return_ci_lower', 0):.2%}",
            ),
            (
                f"  {confidence:.0f}% CI Upper",
                f"{results.get('return_ci_upper', 0):.2%}",
            ),
            ("Risk Statistics", ""),
            ("  Mean Max Drawdown", f"{results.get('mean_max_drawdown', 0):.2%}"),
            ("  Worst Drawdown", f"{results.get('worst_drawdown', 0):.2%}"),
            ("Performance", ""),
            ("  Mean Sharpe Ratio", f"{results.get('mean_sharpe', 0):.3f}"),
            ("  Probability > 0", f"{results.get('probability_positive', 0):.2%}"),
            ("Capital Statistics", ""),
            ("  Mean Final Capital", f"${results.get('final_capital_mean', 0):,.0f}"),
            (
                f"  {confidence:.0f}% CI Lower",
                f"${results.get('final_capital_ci_lower', 0):,.0f}",
            ),
            (
                f"  {confidence:.0f}% CI Upper",
                f"${results.get('final_capital_ci_upper', 0):,.0f}",
            ),
        ]

        for stat, value in stats_items:
            if not value:  # Header row
                self.mc_stats_tree.insert("", "end", text=stat, values=("",))
            else:
                self.mc_stats_tree.insert("", "end", text=stat, values=(value,))

        # Plot distribution if plotting is available
        if PLOTTING_AVAILABLE:
            self.plot_monte_carlo_distribution()

    # Plotting functions
    def plot_equity_curve(self):
        """Plot equity curve."""
        if not self.backtest_results or not PLOTTING_AVAILABLE:
            return

        for widget in self.chart_frame.winfo_children():
            widget.destroy()

        fig, ax = plt.subplots(figsize=(10, 6))

        equity_curve = self.backtest_results.equity_curve
        ax.plot(
            equity_curve.index,
            equity_curve.values,
            color=ui_tokens.CHART["series"],
            linewidth=2,
            label="Strategy",
        )

        # Add benchmark if available
        if self.backtest_results.benchmark_curve is not None:
            ax.plot(
                self.backtest_results.benchmark_curve.index,
                self.backtest_results.benchmark_curve.values,
                color=ui_tokens.CHART["series2"],
                linewidth=2,
                label="Benchmark",
                alpha=0.7,
            )

        ax.set_title("Equity Curve")
        ax.set_xlabel("Date")
        ax.set_ylabel("Portfolio Value ($)")
        ax.legend()
        ax.grid(True, alpha=0.3)

        # Format y-axis as currency
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_drawdown(self):
        """Plot drawdown chart."""
        if not self.backtest_results or not PLOTTING_AVAILABLE:
            return

        for widget in self.chart_frame.winfo_children():
            widget.destroy()

        fig, ax = plt.subplots(figsize=(10, 6))

        drawdowns = self.backtest_results.drawdowns
        ax.fill_between(
            drawdowns.index,
            drawdowns.values * 100,
            0,
            alpha=0.3,
            color=ui_tokens.STATUS["bad"],
            label="Drawdown",
        )
        ax.plot(
            drawdowns.index,
            drawdowns.values * 100,
            color=ui_tokens.STATUS["bad"],
            linewidth=1,
        )

        ax.set_title("Drawdown Analysis")
        ax.set_xlabel("Date")
        ax.set_ylabel("Drawdown (%)")
        ax.grid(True, alpha=0.3)

        # Add max drawdown line
        max_dd = drawdowns.min() * 100
        ax.axhline(
            y=max_dd,
            color=ui_tokens.STATUS["bad"],
            linestyle="--",
            label=f"Max Drawdown: {max_dd:.2f}%",
        )
        ax.legend()
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_monthly_returns(self):
        """Plot monthly returns heatmap."""
        if not self.backtest_results or not PLOTTING_AVAILABLE:
            return

        for widget in self.chart_frame.winfo_children():
            widget.destroy()

        fig, ax = plt.subplots(figsize=(12, 8))

        # Calculate monthly returns
        equity_curve = self.backtest_results.equity_curve
        monthly_returns = equity_curve.resample("M").last().pct_change().dropna()

        # Create monthly returns matrix
        monthly_returns.index = pd.to_datetime(monthly_returns.index)
        returns_matrix = (
            monthly_returns.groupby(
                [monthly_returns.index.year, monthly_returns.index.month]
            )
            .first()
            .unstack()
        )

        # Plot heatmap
        sns.heatmap(
            returns_matrix * 100,
            annot=True,
            fmt=".1f",
            cmap="RdYlGn",
            center=0,
            ax=ax,
            cbar_kws={"label": "Monthly Return (%)"},
        )

        ax.set_title("Monthly Returns Heatmap")
        ax.set_xlabel("Month")
        ax.set_ylabel("Year")
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_monte_carlo_distribution(self):
        """Plot Monte Carlo return distribution."""
        if not self.monte_carlo_results or not PLOTTING_AVAILABLE:
            return

        for widget in self.mc_chart_frame.winfo_children():
            widget.destroy()

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 10))

        results = self.monte_carlo_results["raw_results"]
        returns = [r["total_return"] for r in results]
        final_capitals = [r["final_capital"] for r in results]

        # Returns distribution
        ax1.hist(
            np.array(returns) * 100,
            bins=50,
            alpha=0.7,
            density=True,
            color=ui_tokens.CHART["series"],
        )
        ax1.axvline(
            np.mean(returns) * 100,
            color=ui_tokens.CHART["text"],
            linestyle="--",
            label=f"Mean: {np.mean(returns)*100:.1f}%",
        )
        ax1.set_title("Distribution of Returns")
        ax1.set_xlabel("Total Return (%)")
        ax1.set_ylabel("Density")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Final capital distribution
        ax2.hist(
            final_capitals,
            bins=50,
            alpha=0.7,
            density=True,
            color=ui_tokens.CHART["series2"],
        )
        ax2.axvline(
            np.mean(final_capitals),
            color=ui_tokens.CHART["text"],
            linestyle="--",
            label=f"Mean: ${np.mean(final_capitals):,.0f}",
        )
        ax2.set_title("Distribution of Final Capital")
        ax2.set_xlabel("Final Capital ($)")
        ax2.set_ylabel("Density")
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.mc_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


def main():
    """Run the Backtesting GUI."""
    root = ui_theme.themed_root()
    app = BacktestingGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
