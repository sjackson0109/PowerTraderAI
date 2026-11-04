#!/usr/bin/env python3
"""
Portfolio Optimization GUI for PowerTrader
Interactive interface for portfolio optimization, efficient frontier, and rebalancing.
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
    from portfolio_optimizer import PortfolioOptimizer

    OPTIMIZER_AVAILABLE = True
except ImportError:
    OPTIMIZER_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False


class PortfolioOptimizerGUI:
    """
    Interactive GUI for portfolio optimization using Modern Portfolio Theory.
    """

    def __init__(self, parent=None):
        """Initialize the Portfolio Optimizer GUI."""
        if parent is None:
            self.root = ui_theme.themed_root()
            self.root.title("Portfolio Optimization Engine")
            self.root.geometry("1200x800")
        else:
            self.root = parent

        # Initialize optimizer
        if OPTIMIZER_AVAILABLE:
            self.optimizer = PortfolioOptimizer()
        else:
            self.optimizer = None

        # GUI state
        self.current_data = None
        self.optimization_result = None
        self.frontier_data = None

        self.setup_gui()

    def setup_gui(self):
        """Setup the main GUI layout."""
        # Create main notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Create tabs
        self.setup_data_tab()
        self.setup_optimization_tab()
        self.setup_rebalancing_tab()
        self.setup_analysis_tab()

        if not OPTIMIZER_AVAILABLE:
            self.show_dependency_message()

    def show_dependency_message(self):
        """Show message about missing dependencies."""
        p = ui_theme.active_palette()
        msg_frame = tk.Frame(self.root)
        msg_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            msg_frame,
            text="Portfolio Optimization Engine - Enhanced Features Available",
            font=ui_tokens.font("display", "bold"),
        ).pack(pady=20)

        tk.Label(
            msg_frame,
            text="For full portfolio optimization capabilities, install optional dependencies:",
            font=ui_tokens.font("title"),
        ).pack(pady=10)

        tk.Label(
            msg_frame,
            text="python app/install_optional_deps.py",
            font=ui_tokens.mono("body"),
            background=p["PANEL"],
            foreground=p["FG"],
        ).pack(pady=5)

        tk.Label(
            msg_frame,
            text="Features available with enhanced dependencies:",
            font=ui_tokens.font("subtitle", "bold"),
        ).pack(pady=(20, 5))

        features = [
            "• Modern Portfolio Theory optimization",
            "• Efficient frontier calculations",
            "• Sharpe ratio maximization",
            "• Risk-adjusted portfolio construction",
            "• Advanced statistical analysis",
            "• Interactive charts and visualizations",
        ]

        for feature in features:
            tk.Label(msg_frame, text=feature, font=ui_tokens.font("body")).pack(
                anchor="w", padx=100
            )

        return

    def setup_data_tab(self):
        """Setup the data input tab."""
        data_frame = ttk.Frame(self.notebook)
        self.notebook.add(data_frame, text="Data Input")

        # Data input section
        input_frame = ttk.LabelFrame(data_frame, text="Portfolio Data Input")
        input_frame.pack(fill=tk.X, padx=10, pady=10)

        # File input
        file_frame = tk.Frame(input_frame)
        file_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(file_frame, text="Price Data File:").pack(side=tk.LEFT)
        self.file_path_var = tk.StringVar()
        tk.Entry(file_frame, textvariable=self.file_path_var, width=50).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(file_frame, text="Browse", command=self.browse_file).pack(
            side=tk.LEFT
        )
        ttk.Button(file_frame, text="Load", command=self.load_data).pack(
            side=tk.LEFT, padx=5
        )

        # Manual input
        manual_frame = ttk.LabelFrame(data_frame, text="Manual Asset Input")
        manual_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Asset list
        list_frame = tk.Frame(manual_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Asset input controls
        controls_frame = tk.Frame(list_frame)
        controls_frame.pack(fill=tk.X, pady=(0, 5))

        tk.Label(controls_frame, text="Symbol:").pack(side=tk.LEFT)
        self.symbol_entry = tk.Entry(controls_frame, width=10)
        self.symbol_entry.pack(side=tk.LEFT, padx=5)

        tk.Label(controls_frame, text="Expected Return (%):").pack(
            side=tk.LEFT, padx=(20, 0)
        )
        self.return_entry = tk.Entry(controls_frame, width=10)
        self.return_entry.pack(side=tk.LEFT, padx=5)

        tk.Label(controls_frame, text="Volatility (%):").pack(
            side=tk.LEFT, padx=(20, 0)
        )
        self.volatility_entry = tk.Entry(controls_frame, width=10)
        self.volatility_entry.pack(side=tk.LEFT, padx=5)

        ttk.Button(controls_frame, text="Add Asset", command=self.add_asset).pack(
            side=tk.LEFT, padx=10
        )
        ttk.Button(controls_frame, text="Remove", command=self.remove_asset).pack(
            side=tk.LEFT
        )
        ttk.Button(
            controls_frame, text="Load Sample", command=self.load_sample_data
        ).pack(side=tk.LEFT, padx=5)

        # Asset list display (ui_table: fitted columns, its own scrollbars, sortable);
        # eight rows high, so the Data Summary below stays in a short panel
        self.asset_table = ui_table.DataTable(
            list_frame,
            ("Symbol", "Return", "Volatility"),
            {
                "Symbol": "Symbol",
                "Return": "Expected Return (%)",
                "Volatility": "Volatility (%)",
            },
            key="portfolio_optimization.assets",
            numeric=("Return", "Volatility"),
            empty_text="No assets yet",
            height=8,
        )
        self.asset_table.pack(fill="both", expand=True)
        self.asset_tree = self.asset_table.tree

        # Data summary
        summary_frame = ttk.LabelFrame(data_frame, text="Data Summary")
        summary_frame.pack(fill=tk.X, padx=10, pady=10)

        self.data_summary_label = tk.Label(
            summary_frame, text="No data loaded", font=ui_tokens.font("body")
        )
        self.data_summary_label.pack(pady=5)

    def setup_optimization_tab(self):
        """Setup the optimization tab."""
        opt_frame = ttk.Frame(self.notebook)
        self.notebook.add(opt_frame, text="Optimization")

        # Optimization parameters
        params_frame = ttk.LabelFrame(opt_frame, text="Optimization Parameters")
        params_frame.pack(fill=tk.X, padx=10, pady=10)

        # Optimization type
        type_frame = tk.Frame(params_frame)
        type_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(type_frame, text="Optimization Type:").pack(side=tk.LEFT)
        self.opt_type_var = tk.StringVar(value="max_sharpe")
        opt_combo = ttk.Combobox(
            type_frame,
            textvariable=self.opt_type_var,
            values=["max_sharpe", "min_variance", "target_return"],
            state="readonly",
            width=15,
        )
        opt_combo.pack(side=tk.LEFT, padx=5)
        opt_combo.bind("<<ComboboxSelected>>", self.on_opt_type_change)

        # Target return (for target_return optimization)
        self.target_frame = tk.Frame(type_frame)
        self.target_frame.pack(side=tk.LEFT, padx=20)
        tk.Label(self.target_frame, text="Target Return (%):").pack(side=tk.LEFT)
        self.target_return_entry = tk.Entry(self.target_frame, width=10)
        self.target_return_entry.pack(side=tk.LEFT, padx=5)
        self.target_frame.pack_forget()  # Initially hidden

        # Risk-free rate
        rate_frame = tk.Frame(params_frame)
        rate_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(rate_frame, text="Risk-free Rate (%):").pack(side=tk.LEFT)
        self.risk_free_var = tk.StringVar(value="2.0")
        tk.Entry(rate_frame, textvariable=self.risk_free_var, width=10).pack(
            side=tk.LEFT, padx=5
        )

        # Constraints
        constraints_frame = ttk.LabelFrame(opt_frame, text="Constraints")
        constraints_frame.pack(fill=tk.X, padx=10, pady=10)

        constraint_grid = tk.Frame(constraints_frame)
        constraint_grid.pack(padx=5, pady=5)

        tk.Label(constraint_grid, text="Max Weight per Asset (%):").grid(
            row=0, column=0, sticky="w", padx=5
        )
        self.max_weight_var = tk.StringVar(value="40")
        tk.Entry(constraint_grid, textvariable=self.max_weight_var, width=10).grid(
            row=0, column=1, padx=5
        )

        tk.Label(constraint_grid, text="Min Weight per Asset (%):").grid(
            row=0, column=2, sticky="w", padx=5
        )
        self.min_weight_var = tk.StringVar(value="1")
        tk.Entry(constraint_grid, textvariable=self.min_weight_var, width=10).grid(
            row=0, column=3, padx=5
        )

        tk.Label(constraint_grid, text="Max Portfolio Volatility (%):").grid(
            row=1, column=0, sticky="w", padx=5, pady=5
        )
        self.max_vol_var = tk.StringVar(value="25")
        tk.Entry(constraint_grid, textvariable=self.max_vol_var, width=10).grid(
            row=1, column=1, padx=5, pady=5
        )

        # Optimization button and results
        opt_button_frame = tk.Frame(opt_frame)
        opt_button_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(
            opt_button_frame, text="Optimize Portfolio", command=self.optimize_portfolio
        ).pack(side=tk.LEFT)
        ttk.Button(
            opt_button_frame,
            text="Calculate Efficient Frontier",
            command=self.calculate_frontier,
        ).pack(side=tk.LEFT, padx=10)
        ttk.Button(
            opt_button_frame, text="Save Portfolio", command=self.save_portfolio
        ).pack(side=tk.LEFT)

        # Results display
        results_frame = ttk.LabelFrame(opt_frame, text="Optimization Results")
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.results_text = tk.Text(results_frame, height=10, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL)
        ui_table.scroll_when_needed(self.results_text, scrollbar)

    def setup_rebalancing_tab(self):
        """Setup the rebalancing tab."""
        rebal_frame = ttk.Frame(self.notebook)
        self.notebook.add(rebal_frame, text="Rebalancing")

        # Current portfolio input
        current_frame = ttk.LabelFrame(rebal_frame, text="Current Portfolio")
        current_frame.pack(fill=tk.X, padx=10, pady=10)

        # Current weights input
        current_input_frame = tk.Frame(current_frame)
        current_input_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(
            current_input_frame,
            text="Enter current weights (Symbol:Weight%, comma separated):",
        ).pack(anchor="w")
        self.current_weights_entry = tk.Text(current_input_frame, height=3, width=80)
        self.current_weights_entry.pack(fill=tk.X, pady=5)
        self.current_weights_entry.insert(
            "1.0", "BTC:35, ETH:25, ADA:15, DOT:15, LINK:10"
        )

        # Target portfolio
        target_frame = ttk.LabelFrame(rebal_frame, text="Target Portfolio")
        target_frame.pack(fill=tk.X, padx=10, pady=10)

        target_controls = tk.Frame(target_frame)
        target_controls.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(
            target_controls,
            text="Use Last Optimization",
            command=self.use_last_optimization,
        ).pack(side=tk.LEFT)
        ttk.Button(
            target_controls,
            text="Load Saved Portfolio",
            command=self.load_saved_portfolio,
        ).pack(side=tk.LEFT, padx=10)

        # Manual target weights
        tk.Label(target_frame, text="Or enter target weights manually:").pack(
            anchor="w", padx=5
        )
        self.target_weights_entry = tk.Text(target_frame, height=3, width=80)
        self.target_weights_entry.pack(fill=tk.X, padx=5, pady=5)

        # Rebalancing parameters
        rebal_params_frame = ttk.LabelFrame(rebal_frame, text="Rebalancing Parameters")
        rebal_params_frame.pack(fill=tk.X, padx=10, pady=10)

        params_grid = tk.Frame(rebal_params_frame)
        params_grid.pack(padx=5, pady=5)

        tk.Label(params_grid, text="Drift Threshold (%):").grid(
            row=0, column=0, sticky="w", padx=5
        )
        self.drift_threshold_var = tk.StringVar(value="5")
        tk.Entry(params_grid, textvariable=self.drift_threshold_var, width=10).grid(
            row=0, column=1, padx=5
        )

        tk.Label(params_grid, text="Transaction Cost (%):").grid(
            row=0, column=2, sticky="w", padx=5
        )
        self.transaction_cost_var = tk.StringVar(value="0.1")
        tk.Entry(params_grid, textvariable=self.transaction_cost_var, width=10).grid(
            row=0, column=3, padx=5
        )

        # Analyze button
        ttk.Button(
            rebal_frame,
            text="Analyze Rebalancing Need",
            command=self.analyze_rebalancing,
        ).pack(pady=10)

        # Rebalancing results
        rebal_results_frame = ttk.LabelFrame(rebal_frame, text="Rebalancing Analysis")
        rebal_results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.rebal_results_text = tk.Text(rebal_results_frame, wrap=tk.WORD)
        rebal_scrollbar = ttk.Scrollbar(rebal_results_frame, orient=tk.VERTICAL)
        ui_table.scroll_when_needed(self.rebal_results_text, rebal_scrollbar)

    def setup_analysis_tab(self):
        """Setup the analysis and visualization tab."""
        analysis_frame = ttk.Frame(self.notebook)
        self.notebook.add(analysis_frame, text="Analysis")

        if not PLOTTING_AVAILABLE:
            tk.Label(
                analysis_frame,
                text="Install matplotlib and seaborn for visualization features",
                font=ui_tokens.font("title"),
            ).pack(pady=50)
            return

        # Visualization controls
        viz_frame = ttk.LabelFrame(analysis_frame, text="Visualization")
        viz_frame.pack(fill=tk.X, padx=10, pady=10)

        viz_buttons = tk.Frame(viz_frame)
        viz_buttons.pack(padx=5, pady=5)

        ttk.Button(
            viz_buttons,
            text="Plot Efficient Frontier",
            command=self.plot_efficient_frontier,
        ).pack(side=tk.LEFT)
        ttk.Button(
            viz_buttons,
            text="Portfolio Composition",
            command=self.plot_portfolio_composition,
        ).pack(side=tk.LEFT, padx=10)
        ttk.Button(
            viz_buttons, text="Risk-Return Scatter", command=self.plot_risk_return
        ).pack(side=tk.LEFT)

        # Chart area
        self.chart_frame = tk.Frame(analysis_frame)
        self.chart_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # Event handlers
    def on_opt_type_change(self, event=None):
        """Handle optimization type change."""
        if self.opt_type_var.get() == "target_return":
            self.target_frame.pack(side=tk.LEFT, padx=20)
        else:
            self.target_frame.pack_forget()

    def browse_file(self):
        """Browse for data file."""
        filename = filedialog.askopenfilename(
            title="Select Price Data File",
            filetypes=[
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx"),
                ("All files", "*.*"),
            ],
        )
        if filename:
            self.file_path_var.set(filename)

    def load_data(self):
        """Load data from file."""
        if not self.file_path_var.get():
            messagebox.showerror("Error", "Please select a data file")
            return

        try:
            file_path = self.file_path_var.get()
            if file_path.endswith(".csv"):
                data = pd.read_csv(file_path, index_col=0, parse_dates=True)
            elif file_path.endswith(".xlsx"):
                data = pd.read_excel(file_path, index_col=0, parse_dates=True)
            else:
                messagebox.showerror("Error", "Unsupported file format")
                return

            self.current_data = data
            self.update_data_summary(
                f"Loaded data: {len(data)} rows, {len(data.columns)} assets"
            )
            messagebox.showinfo("Success", f"Data loaded successfully: {data.shape}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load data: {str(e)}")

    def add_asset(self):
        """Add asset manually."""
        try:
            symbol = self.symbol_entry.get().strip().upper()
            expected_return = float(self.return_entry.get())
            volatility = float(self.volatility_entry.get())

            if not symbol:
                messagebox.showerror("Error", "Please enter a symbol")
                return

            # Check if asset already exists
            for item in self.asset_tree.get_children():
                if self.asset_tree.item(item, "values")[0] == symbol:
                    messagebox.showerror("Error", f"Asset {symbol} already exists")
                    return

            self.asset_tree.insert(
                "",
                "end",
                values=(symbol, f"{expected_return:.2f}", f"{volatility:.2f}"),
            )

            # Clear entries
            self.symbol_entry.delete(0, tk.END)
            self.return_entry.delete(0, tk.END)
            self.volatility_entry.delete(0, tk.END)

            self.update_manual_data()

        except ValueError:
            messagebox.showerror(
                "Error", "Please enter valid numbers for return and volatility"
            )

    def remove_asset(self):
        """Remove selected asset."""
        selection = self.asset_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select an asset to remove")
            return

        for item in selection:
            self.asset_tree.delete(item)

        self.update_manual_data()

    def load_sample_data(self):
        """Load sample portfolio data."""
        # Clear existing data
        for item in self.asset_tree.get_children():
            self.asset_tree.delete(item)

        # Sample crypto portfolio
        sample_assets = [
            ("BTC", 8.5, 45.2),
            ("ETH", 12.1, 58.7),
            ("ADA", 15.3, 67.8),
            ("DOT", 18.7, 72.1),
            ("LINK", 22.4, 68.9),
        ]

        for symbol, ret, vol in sample_assets:
            self.asset_tree.insert(
                "", "end", values=(symbol, f"{ret:.1f}", f"{vol:.1f}")
            )

        self.update_manual_data()

    def update_manual_data(self):
        """Update data from manual input."""
        assets = []
        returns = []
        volatilities = []

        for item in self.asset_tree.get_children():
            values = self.asset_tree.item(item, "values")
            assets.append(values[0])
            returns.append(float(values[1]) / 100)  # Convert percentage to decimal
            volatilities.append(float(values[2]) / 100)

        if assets:
            self.current_data = {
                "assets": assets,
                "expected_returns": pd.Series(returns, index=assets),
                "volatilities": pd.Series(volatilities, index=assets),
            }

            # Create covariance matrix (simplified - assumes correlations)
            correlations = np.random.rand(len(assets), len(assets)) * 0.3 + 0.5
            np.fill_diagonal(correlations, 1.0)
            correlations = (correlations + correlations.T) / 2  # Make symmetric

            vol_matrix = np.outer(volatilities, volatilities)
            cov_matrix = correlations * vol_matrix

            self.current_data["covariance_matrix"] = pd.DataFrame(
                cov_matrix, index=assets, columns=assets
            )

            self.update_data_summary(f"Manual data: {len(assets)} assets")
        else:
            self.current_data = None
            self.update_data_summary("No data loaded")

    def update_data_summary(self, text):
        """Update data summary display."""
        self.data_summary_label.config(text=text)

    def optimize_portfolio(self):
        """Perform portfolio optimization."""
        if not OPTIMIZER_AVAILABLE:
            messagebox.showerror(
                "Error",
                "Portfolio optimizer not available. Install scipy for optimization.",
            )
            return

        if not self.current_data:
            messagebox.showerror("Error", "Please load data first")
            return

        try:
            # Get optimization parameters
            opt_type = self.opt_type_var.get()
            risk_free_rate = float(self.risk_free_var.get()) / 100

            # Update optimizer risk-free rate
            self.optimizer.risk_free_rate = risk_free_rate

            # Get constraints
            constraints = {
                "max_weight": float(self.max_weight_var.get()) / 100,
                "min_weight": float(self.min_weight_var.get()) / 100,
                "max_volatility": float(self.max_vol_var.get()) / 100,
            }

            # Get data
            if isinstance(self.current_data, dict):
                expected_returns = self.current_data["expected_returns"]
                cov_matrix = self.current_data["covariance_matrix"]
            else:
                (
                    expected_returns,
                    cov_matrix,
                ) = self.optimizer.calculate_returns_covariance(self.current_data)

            # Target return for target_return optimization
            target_return = None
            if opt_type == "target_return":
                target_return = float(self.target_return_entry.get()) / 100

            # Perform optimization
            result = self.optimizer.optimize_portfolio(
                expected_returns, cov_matrix, opt_type, target_return, constraints
            )

            self.optimization_result = result
            self.display_optimization_results(result)

        except Exception as e:
            messagebox.showerror("Error", f"Optimization failed: {str(e)}")

    def display_optimization_results(self, result):
        """Display optimization results."""
        self.results_text.delete("1.0", tk.END)

        text = f"Optimization Results ({result['method']})\n"
        text += "=" * 50 + "\n\n"

        text += f"Expected Return: {result['expected_return']:.2%}\n"
        text += f"Volatility: {result['volatility']:.2%}\n"
        text += f"Sharpe Ratio: {result['sharpe_ratio']:.3f}\n"
        text += f"Success: {result['success']}\n\n"

        text += "Optimal Weights:\n"
        text += "-" * 20 + "\n"

        for asset, weight in sorted(
            result["weights"].items(), key=lambda x: x[1], reverse=True
        ):
            text += f"{asset}: {weight:.1%}\n"

        if not result["success"] and "error" in result:
            text += f"\nNote: {result['error']}\n"

        self.results_text.insert("1.0", text)

    def calculate_frontier(self):
        """Calculate and display efficient frontier."""
        if not OPTIMIZER_AVAILABLE:
            messagebox.showerror(
                "Error",
                "Portfolio optimizer not available. Install scipy for optimization.",
            )
            return

        if not self.current_data:
            messagebox.showerror("Error", "Please load data first")
            return

        try:
            # Get data
            if isinstance(self.current_data, dict):
                expected_returns = self.current_data["expected_returns"]
                cov_matrix = self.current_data["covariance_matrix"]
            else:
                (
                    expected_returns,
                    cov_matrix,
                ) = self.optimizer.calculate_returns_covariance(self.current_data)

            # Calculate efficient frontier
            frontier = self.optimizer.calculate_efficient_frontier(
                expected_returns, cov_matrix, 30
            )
            self.frontier_data = frontier

            # Display summary
            text = f"\nEfficient Frontier calculated with {len(frontier)} points\n"
            text += f"Return range: {frontier['Return'].min():.2%} to {frontier['Return'].max():.2%}\n"
            text += f"Risk range: {frontier['Volatility'].min():.2%} to {frontier['Volatility'].max():.2%}\n"
            text += f"Max Sharpe ratio: {frontier['Sharpe_Ratio'].max():.3f}\n"

            self.results_text.insert(tk.END, text)

            messagebox.showinfo(
                "Success", f"Efficient frontier calculated with {len(frontier)} points"
            )

        except Exception as e:
            messagebox.showerror("Error", f"Frontier calculation failed: {str(e)}")

    def save_portfolio(self):
        """Save optimized portfolio."""
        if not self.optimization_result:
            messagebox.showerror("Error", "No optimization result to save")
            return

        # Simple dialog for portfolio name
        name = tk.simpledialog.askstring("Save Portfolio", "Enter portfolio name:")
        if name and OPTIMIZER_AVAILABLE:
            try:
                portfolio_id = self.optimizer.save_optimized_portfolio(
                    name, self.optimization_result, self.opt_type_var.get()
                )
                messagebox.showinfo(
                    "Success", f"Portfolio saved with ID {portfolio_id}"
                )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save portfolio: {str(e)}")

    def use_last_optimization(self):
        """Use last optimization result for rebalancing."""
        if not self.optimization_result:
            messagebox.showerror("Error", "No optimization result available")
            return

        # Format weights for target entry
        weights_text = ", ".join(
            [
                f"{asset}:{weight*100:.1f}"
                for asset, weight in self.optimization_result["weights"].items()
            ]
        )

        self.target_weights_entry.delete("1.0", tk.END)
        self.target_weights_entry.insert("1.0", weights_text)

    def load_saved_portfolio(self):
        """Load saved portfolio for rebalancing."""
        # This would open a dialog to select from saved portfolios
        messagebox.showinfo("Info", "Feature coming soon: Load from saved portfolios")

    def parse_weights(self, text):
        """Parse weights from text input."""
        weights = {}
        try:
            for item in text.split(","):
                if ":" in item:
                    symbol, weight = item.split(":")
                    weights[symbol.strip().upper()] = float(weight.strip()) / 100
            return weights
        except:
            raise ValueError(
                "Invalid weights format. Use 'Symbol:Weight%, Symbol:Weight%'"
            )

    def analyze_rebalancing(self):
        """Analyze rebalancing needs."""
        if not OPTIMIZER_AVAILABLE:
            messagebox.showerror("Error", "Portfolio optimizer not available")
            return

        try:
            # Parse current and target weights
            current_text = self.current_weights_entry.get("1.0", tk.END).strip()
            target_text = self.target_weights_entry.get("1.0", tk.END).strip()

            if not current_text or not target_text:
                messagebox.showerror(
                    "Error", "Please enter both current and target weights"
                )
                return

            current_weights = self.parse_weights(current_text)
            target_weights = self.parse_weights(target_text)

            # Get parameters
            threshold = float(self.drift_threshold_var.get()) / 100
            transaction_cost = float(self.transaction_cost_var.get()) / 100

            # Analyze rebalancing
            analysis = self.optimizer.suggest_rebalancing(
                current_weights, target_weights, threshold, transaction_cost
            )

            self.display_rebalancing_analysis(analysis)

        except Exception as e:
            messagebox.showerror("Error", f"Rebalancing analysis failed: {str(e)}")

    def display_rebalancing_analysis(self, analysis):
        """Display rebalancing analysis results."""
        self.rebal_results_text.delete("1.0", tk.END)

        text = "Rebalancing Analysis\n"
        text += "=" * 30 + "\n\n"

        text += (
            f"Rebalancing Needed: {'Yes' if analysis['rebalancing_needed'] else 'No'}\n"
        )
        text += f"Total Portfolio Drift: {analysis['total_drift']:.2%}\n"
        text += f"Estimated Transaction Cost: {analysis['estimated_transaction_cost']:.2%}\n"
        text += f"Cost-Benefit Ratio: {analysis['cost_benefit_ratio']:.2f}\n\n"

        if analysis["recommendations"]:
            text += "Recommendations:\n"
            text += "-" * 20 + "\n"

            for rec in analysis["recommendations"]:
                text += f"{rec['symbol']}: {rec['action']} "
                text += f"({rec['current_weight']:.1%} → {rec['target_weight']:.1%}, "
                text += f"Drift: {rec['drift']:.2%}, Urgency: {rec['urgency']})\n"
        else:
            text += "No rebalancing recommendations.\n"

        self.rebal_results_text.insert("1.0", text)

    def plot_efficient_frontier(self):
        """Plot efficient frontier."""
        if not PLOTTING_AVAILABLE:
            messagebox.showerror("Error", "Matplotlib not available for plotting")
            return

        if self.frontier_data is None or self.frontier_data.empty:
            messagebox.showerror("Error", "Please calculate efficient frontier first")
            return

        # Clear previous charts
        for widget in self.chart_frame.winfo_children():
            widget.destroy()

        fig, ax = plt.subplots(figsize=(10, 6))

        # Plot efficient frontier
        ax.plot(
            self.frontier_data["Volatility"],
            self.frontier_data["Return"],
            "-",
            color=ui_tokens.CHART["series"],
            linewidth=2,
            label="Efficient Frontier",
        )

        # Highlight max Sharpe ratio portfolio
        max_sharpe_idx = self.frontier_data["Sharpe_Ratio"].idxmax()
        ax.plot(
            self.frontier_data.loc[max_sharpe_idx, "Volatility"],
            self.frontier_data.loc[max_sharpe_idx, "Return"],
            "o",
            color=ui_tokens.CHART["text"],
            markersize=10,
            label="Max Sharpe Ratio",
        )

        # Mark current optimization if available
        if self.optimization_result:
            ax.plot(
                self.optimization_result["volatility"],
                self.optimization_result["expected_return"],
                "o",
                color=ui_tokens.CHART["series2"],
                markersize=10,
                label="Current Optimization",
            )

        ax.set_xlabel("Volatility (Risk)")
        ax.set_ylabel("Expected Return")
        ax.set_title("Efficient Frontier")
        ax.legend()
        ax.grid(True, alpha=0.3)
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_portfolio_composition(self):
        """Plot portfolio composition pie chart."""
        if not PLOTTING_AVAILABLE:
            messagebox.showerror("Error", "Matplotlib not available for plotting")
            return

        if not self.optimization_result:
            messagebox.showerror("Error", "Please optimize portfolio first")
            return

        # Clear previous charts
        for widget in self.chart_frame.winfo_children():
            widget.destroy()

        fig, ax = plt.subplots(figsize=(8, 8))

        weights = self.optimization_result["weights"]
        assets = list(weights.keys())
        values = list(weights.values())

        colors = plt.cm.Set3(np.arange(len(assets)))
        wedges, texts, autotexts = ax.pie(
            values, labels=assets, autopct="%1.1f%%", colors=colors, startangle=90
        )
        for autotext in autotexts:  # dark on the pale wedges
            autotext.set_color(ui_tokens.CHART["figure"])

        ax.set_title(
            f"Portfolio Composition\n"
            f'Expected Return: {self.optimization_result["expected_return"]:.2%}, '
            f'Volatility: {self.optimization_result["volatility"]:.2%}'
        )
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_risk_return(self):
        """Plot risk-return scatter of individual assets."""
        if not PLOTTING_AVAILABLE:
            messagebox.showerror("Error", "Matplotlib not available for plotting")
            return

        if not self.current_data:
            messagebox.showerror("Error", "Please load data first")
            return

        # Clear previous charts
        for widget in self.chart_frame.winfo_children():
            widget.destroy()

        fig, ax = plt.subplots(figsize=(10, 6))

        if isinstance(self.current_data, dict):
            returns = self.current_data["expected_returns"]
            volatilities = self.current_data["volatilities"]
        else:
            returns, cov_matrix = self.optimizer.calculate_returns_covariance(
                self.current_data
            )
            volatilities = np.sqrt(np.diag(cov_matrix))

        # Plot individual assets
        ax.scatter(volatilities, returns, s=100, alpha=0.7, c=ui_tokens.CHART["series"])

        # Add labels
        for i, asset in enumerate(returns.index):
            ax.annotate(
                asset,
                (volatilities.iloc[i], returns.iloc[i]),
                xytext=(5, 5),
                textcoords="offset points",
            )

        # Add portfolio if optimized
        if self.optimization_result:
            ax.scatter(
                self.optimization_result["volatility"],
                self.optimization_result["expected_return"],
                s=200,
                c=ui_tokens.CHART["series2"],
                marker="*",
                label="Optimized Portfolio",
            )

        ax.set_xlabel("Volatility (Risk)")
        ax.set_ylabel("Expected Return")
        ax.set_title("Risk-Return Profile of Assets")
        ax.grid(True, alpha=0.3)
        if self.optimization_result:
            ax.legend()
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


def main():
    """Run the Portfolio Optimizer GUI."""
    root = ui_theme.themed_root()
    app = PortfolioOptimizerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
