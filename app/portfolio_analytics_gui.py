"""
Enhanced Portfolio Analytics GUI (Item 21)
Graphical interface for advanced portfolio analytics
"""

import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

import ui_table
import ui_theme
import ui_tokens

try:
    from portfolio_analytics import PortfolioAnalytics, get_portfolio_analytics

    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False
    print("Warning: Portfolio analytics system not available.")

try:
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import seaborn as sns
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

try:
    import numpy as np
    import pandas as pd

    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


class PortfolioAnalyticsGUI:
    """GUI for enhanced portfolio analytics"""

    def __init__(self, parent: tk.Widget):
        self.parent = parent
        self.analytics = None

        # Initialize analytics if available
        if ANALYTICS_AVAILABLE:
            try:
                self.analytics = get_portfolio_analytics()
            except Exception as e:
                print(f"Error initializing portfolio analytics: {e}")

        self.setup_ui()
        self.refresh_analytics()

    def setup_ui(self):
        """Setup the user interface"""
        self.main_frame = ttk.Frame(self.parent)
        self.main_frame.pack(fill="both", expand=True)

        # Create notebook for analytics tabs
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill="both", expand=True)

        # Performance Analytics Tab
        self.performance_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.performance_tab, text="Performance")
        self.setup_performance_tab()

        # Risk Analytics Tab
        self.risk_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.risk_tab, text="Risk Analysis")
        self.setup_risk_tab()

        # Asset Allocation Tab
        self.allocation_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.allocation_tab, text="Asset Allocation")
        self.setup_allocation_tab()

        # Advanced Analytics Tab
        self.advanced_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.advanced_tab, text="Advanced")
        self.setup_advanced_tab()

        # Reports Tab
        self.reports_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.reports_tab, text="Reports")
        self.setup_reports_tab()

    def setup_performance_tab(self):
        """Setup performance analytics tab"""
        # Control frame
        control_frame = ttk.Frame(self.performance_tab)
        control_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(control_frame, text="Analysis Period:").pack(side="left", padx=5)

        self.period_var = tk.StringVar(value="30")
        period_combo = ttk.Combobox(
            control_frame,
            textvariable=self.period_var,
            values=["7", "14", "30", "60", "90", "180", "365"],
            width=10,
        )
        period_combo.pack(side="left", padx=5)

        ttk.Label(control_frame, text="days").pack(side="left", padx=5)

        ttk.Button(
            control_frame, text="Update", command=self.update_performance_analysis
        ).pack(side="left", padx=20)
        ttk.Button(
            control_frame, text="Export Data", command=self.export_performance_data
        ).pack(side="left", padx=5)

        # Metrics frame
        metrics_frame = ttk.LabelFrame(self.performance_tab, text="Performance Metrics")
        metrics_frame.pack(fill="x", padx=10, pady=5)

        # Create metrics display
        self.performance_metrics = {}
        metrics_data = [
            ("Total Return:", "total_return", "$"),
            ("Total Return %:", "total_return_pct", "%"),
            ("Sharpe Ratio:", "sharpe_ratio", ""),
            ("Max Drawdown:", "max_drawdown", "%"),
            ("Volatility (Annualized):", "volatility", "%"),
            ("Alpha:", "alpha", ""),
            ("Beta:", "beta", ""),
        ]

        for i, (label_text, key, suffix) in enumerate(metrics_data):
            row = i // 3
            col = (i % 3) * 2

            ttk.Label(metrics_frame, text=label_text).grid(
                row=row, column=col, sticky="w", padx=5, pady=2
            )
            label_widget = ttk.Label(metrics_frame, text="N/A")
            label_widget.grid(row=row, column=col + 1, sticky="e", padx=5, pady=2)
            self.performance_metrics[key] = (label_widget, suffix)

        # Performance charts
        if MATPLOTLIB_AVAILABLE:
            chart_frame = ttk.LabelFrame(
                self.performance_tab, text="Performance Charts"
            )
            chart_frame.pack(fill="both", expand=True, padx=10, pady=5)

            self.performance_fig = Figure(
                figsize=(12, 8), facecolor=ui_tokens.CHART["figure"]
            )
            self.performance_canvas = FigureCanvasTkAgg(
                self.performance_fig, chart_frame
            )
            self.performance_canvas.get_tk_widget().pack(fill="both", expand=True)
        else:
            ttk.Label(
                self.performance_tab,
                text="Charts not available - matplotlib not installed",
            ).pack(pady=20)

    def setup_risk_tab(self):
        """Setup risk analysis tab"""
        # Control frame
        control_frame = ttk.Frame(self.risk_tab)
        control_frame.pack(fill="x", padx=5, pady=5)

        ttk.Button(
            control_frame,
            text="Calculate Risk Metrics",
            command=self.calculate_risk_metrics,
        ).pack(side="left", padx=5)
        ttk.Button(
            control_frame, text="Export Risk Report", command=self.export_risk_report
        ).pack(side="left", padx=5)

        # Risk metrics frame
        risk_metrics_frame = ttk.LabelFrame(self.risk_tab, text="Risk Metrics")
        risk_metrics_frame.pack(fill="x", padx=10, pady=5)

        self.risk_metrics = {}
        risk_data = [
            ("Value at Risk (95%):", "var_95", "$"),
            ("Value at Risk (99%):", "var_99", "$"),
            ("Expected Shortfall (95%):", "expected_shortfall_95", "$"),
            ("Expected Shortfall (99%):", "expected_shortfall_99", "$"),
            ("Portfolio Volatility:", "portfolio_volatility", "%"),
            ("Concentration Risk:", "concentration_risk", ""),
        ]

        for i, (label_text, key, suffix) in enumerate(risk_data):
            row = i // 2
            col = (i % 2) * 2

            ttk.Label(risk_metrics_frame, text=label_text).grid(
                row=row, column=col, sticky="w", padx=5, pady=2
            )
            label_widget = ttk.Label(risk_metrics_frame, text="N/A")
            label_widget.grid(row=row, column=col + 1, sticky="e", padx=5, pady=2)
            self.risk_metrics[key] = (label_widget, suffix)

        # Risk visualization
        if MATPLOTLIB_AVAILABLE:
            risk_chart_frame = ttk.LabelFrame(self.risk_tab, text="Risk Visualization")
            risk_chart_frame.pack(fill="both", expand=True, padx=10, pady=5)

            self.risk_fig = Figure(figsize=(12, 6), facecolor=ui_tokens.CHART["figure"])
            self.risk_canvas = FigureCanvasTkAgg(self.risk_fig, risk_chart_frame)
            self.risk_canvas.get_tk_widget().pack(fill="both", expand=True)

    def setup_allocation_tab(self):
        """Setup asset allocation tab"""
        # Control frame
        allocation_control = ttk.Frame(self.allocation_tab)
        allocation_control.pack(fill="x", padx=5, pady=5)

        ttk.Label(allocation_control, text="Historical Period:").pack(
            side="left", padx=5
        )

        self.allocation_period_var = tk.StringVar(value="30")
        allocation_combo = ttk.Combobox(
            allocation_control,
            textvariable=self.allocation_period_var,
            values=["7", "14", "30", "60", "90"],
            width=10,
        )
        allocation_combo.pack(side="left", padx=5)

        ttk.Label(allocation_control, text="days").pack(side="left", padx=5)

        ttk.Button(
            allocation_control,
            text="Update Allocation Analysis",
            command=self.update_allocation_analysis,
        ).pack(side="left", padx=20)

        # Current allocation frame
        current_frame = ttk.LabelFrame(self.allocation_tab, text="Current Allocation")
        current_frame.pack(fill="x", padx=10, pady=5)

        # Allocation table: each row's text (the tree column) is its asset
        self.allocation_table = ui_table.DataTable(
            current_frame,
            ("percentage", "value"),
            {"percentage": "Percentage", "value": "Value"},
            key="portfolio_analytics.allocation",
            numeric=("percentage", "value"),
            empty_text="No assets yet",
            height=6,
            show="tree headings",
        )
        self.allocation_table.pack(fill="both", expand=True)
        self.allocation_tree = self.allocation_table.tree
        # the table titles and sizes its own columns, not the tree column
        self.allocation_tree.heading("#0", text="Asset")  # each row's own text

        # Allocation history charts
        if MATPLOTLIB_AVAILABLE:
            allocation_chart_frame = ttk.LabelFrame(
                self.allocation_tab, text="Allocation History"
            )
            allocation_chart_frame.pack(fill="both", expand=True, padx=10, pady=5)

            self.allocation_fig = Figure(
                figsize=(12, 6), facecolor=ui_tokens.CHART["figure"]
            )
            self.allocation_canvas = FigureCanvasTkAgg(
                self.allocation_fig, allocation_chart_frame
            )
            self.allocation_canvas.get_tk_widget().pack(fill="both", expand=True)

    def setup_advanced_tab(self):
        """Setup advanced analytics tab"""
        # Monte Carlo Simulation
        monte_carlo_frame = ttk.LabelFrame(
            self.advanced_tab, text="Monte Carlo Simulation"
        )
        monte_carlo_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(monte_carlo_frame, text="Simulation Parameters:").pack(
            anchor="w", padx=5, pady=2
        )

        params_frame = ttk.Frame(monte_carlo_frame)
        params_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(params_frame, text="Days:").grid(row=0, column=0, sticky="w", padx=5)
        self.sim_days_var = tk.StringVar(value="30")
        ttk.Entry(params_frame, textvariable=self.sim_days_var, width=10).grid(
            row=0, column=1, padx=5
        )

        ttk.Label(params_frame, text="Simulations:").grid(
            row=0, column=2, sticky="w", padx=5
        )
        self.sim_runs_var = tk.StringVar(value="1000")
        ttk.Entry(params_frame, textvariable=self.sim_runs_var, width=10).grid(
            row=0, column=3, padx=5
        )

        ttk.Button(
            params_frame, text="Run Simulation", command=self.run_monte_carlo
        ).grid(row=0, column=4, padx=20)

        # Correlation Analysis
        correlation_frame = ttk.LabelFrame(
            self.advanced_tab, text="Correlation Analysis"
        )
        correlation_frame.pack(fill="both", expand=True, padx=10, pady=5)

        if MATPLOTLIB_AVAILABLE:
            self.advanced_fig = Figure(
                figsize=(12, 8), facecolor=ui_tokens.CHART["figure"]
            )
            self.advanced_canvas = FigureCanvasTkAgg(
                self.advanced_fig, correlation_frame
            )
            self.advanced_canvas.get_tk_widget().pack(fill="both", expand=True)
        else:
            ttk.Label(
                correlation_frame, text="Advanced analytics require matplotlib"
            ).pack(pady=20)

    def setup_reports_tab(self):
        """Setup reports generation tab"""
        # Report options frame
        options_frame = ttk.LabelFrame(self.reports_tab, text="Report Options")
        options_frame.pack(fill="x", padx=10, pady=10)

        # Report type
        ttk.Label(options_frame, text="Report Type:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        self.report_type_var = tk.StringVar(value="comprehensive")
        report_combo = ttk.Combobox(
            options_frame,
            textvariable=self.report_type_var,
            values=["comprehensive", "performance", "risk", "allocation"],
            width=15,
        )
        report_combo.grid(row=0, column=1, padx=5, pady=5)

        # Report period
        ttk.Label(options_frame, text="Period (days):").grid(
            row=1, column=0, sticky="w", padx=5, pady=5
        )
        self.report_period_var = tk.StringVar(value="30")
        ttk.Entry(options_frame, textvariable=self.report_period_var, width=15).grid(
            row=1, column=1, padx=5, pady=5
        )

        # Include charts option
        self.include_charts_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame, text="Include Charts", variable=self.include_charts_var
        ).grid(row=2, column=0, sticky="w", padx=5, pady=5)

        # Generate buttons
        buttons_frame = ttk.Frame(self.reports_tab)
        buttons_frame.pack(fill="x", padx=10, pady=20)

        ttk.Button(
            buttons_frame, text="Generate Report", command=self.generate_report
        ).pack(side="left", padx=10)
        ttk.Button(
            buttons_frame, text="Export to PDF", command=self.export_pdf_report
        ).pack(side="left", padx=10)
        ttk.Button(
            buttons_frame, text="Export to Excel", command=self.export_excel_report
        ).pack(side="left", padx=10)

        # Report preview
        preview_frame = ttk.LabelFrame(self.reports_tab, text="Report Preview")
        preview_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.report_text = tk.Text(preview_frame, height=15, width=80)
        report_scrollbar = ttk.Scrollbar(preview_frame, orient="vertical")
        ui_table.scroll_when_needed(self.report_text, report_scrollbar)

    def refresh_analytics(self):
        """Refresh all analytics displays"""
        if not ANALYTICS_AVAILABLE:
            return

        self.update_performance_analysis()
        self.calculate_risk_metrics()
        self.update_allocation_analysis()

    def update_performance_analysis(self):
        """Update performance analytics"""
        if not ANALYTICS_AVAILABLE or not self.analytics:
            return

        try:
            days = int(self.period_var.get())
            performance = self.analytics.calculate_performance_metrics(days)

            if performance:
                # Update metrics display
                for key, (label_widget, suffix) in self.performance_metrics.items():
                    value = getattr(performance, key, 0)

                    if key in ["total_return"]:
                        formatted_value = f"${value:.2f}"
                    elif key in ["total_return_pct", "max_drawdown", "volatility"]:
                        formatted_value = f"{value:.2f}{suffix}"
                    else:
                        formatted_value = f"{value:.3f}{suffix}"

                    label_widget.config(text=formatted_value)

                    # Color code based on value
                    if key in ["total_return", "total_return_pct"]:
                        style = "Good.TLabel" if value >= 0 else "Bad.TLabel"
                        label_widget.config(style=style)

                # Update performance charts
                if MATPLOTLIB_AVAILABLE and hasattr(self, "performance_canvas"):
                    self.update_performance_charts(performance)

        except Exception as e:
            print(f"Error updating performance analysis: {e}")
            messagebox.showerror("Error", f"Error updating performance analysis: {e}")

    def update_performance_charts(self, performance):
        """Update performance visualization charts"""
        if not MATPLOTLIB_AVAILABLE:
            return

        try:
            chart = ui_tokens.CHART
            self.performance_fig.clear()

            # Create subplots
            gs = self.performance_fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)

            # Cumulative returns chart
            ax1 = self.performance_fig.add_subplot(gs[0, :])
            if performance.timestamps and performance.cumulative_returns:
                dates = [
                    (
                        datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if "Z" in ts
                        else datetime.fromisoformat(ts)
                    )
                    for ts in performance.timestamps
                ]
                ax1.plot(
                    dates,
                    [r * 100 for r in performance.cumulative_returns],
                    color=chart["series"],
                    linewidth=2,
                )
                ax1.set_title("Cumulative Returns (%)", color=chart["text"])
                ax1.set_ylabel("Return (%)", color=chart["text"])
                ax1.tick_params(colors=chart["text"])
                ax1.grid(True, alpha=0.3)

                # Format x-axis
                ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
                ax1.xaxis.set_major_locator(
                    mdates.DayLocator(interval=max(1, len(dates) // 10))
                )
                self.performance_fig.autofmt_xdate()

            # Daily returns distribution
            ax2 = self.performance_fig.add_subplot(gs[1, 0])
            if performance.daily_returns:
                returns_pct = [r * 100 for r in performance.daily_returns]
                ax2.hist(
                    returns_pct,
                    bins=20,
                    color=chart["series"],
                    alpha=0.7,
                    edgecolor=chart["text"],
                )
                ax2.set_title("Daily Returns Distribution", color=chart["text"])
                ax2.set_xlabel("Return (%)", color=chart["text"])
                ax2.set_ylabel("Frequency", color=chart["text"])
                ax2.tick_params(colors=chart["text"])

            # Performance metrics bar chart
            ax3 = self.performance_fig.add_subplot(gs[1, 1])
            metrics = ["Return %", "Sharpe", "Max DD %"]
            values = [
                performance.total_return_pct,
                performance.sharpe_ratio,
                -performance.max_drawdown,
            ]
            status = ui_tokens.STATUS
            colors = [status["good"] if v >= 0 else status["bad"] for v in values]

            bars = ax3.bar(metrics, values, color=colors, alpha=0.7)
            ax3.set_title("Key Metrics", color=chart["text"])
            ax3.tick_params(colors=chart["text"])
            ax3.axhline(y=0, color=chart["text"], linestyle="-", alpha=0.5)

            ui_theme.theme_figure(self.performance_fig)
            self.performance_canvas.draw()

        except Exception as e:
            print(f"Error updating performance charts: {e}")

    def calculate_risk_metrics(self):
        """Calculate and display risk metrics"""
        if not ANALYTICS_AVAILABLE or not self.analytics:
            return

        try:
            risk_metrics = self.analytics.calculate_risk_metrics()

            if risk_metrics:
                # Update risk metrics display
                for key, (label_widget, suffix) in self.risk_metrics.items():
                    value = getattr(risk_metrics, key, 0)

                    if key in [
                        "var_95",
                        "var_99",
                        "expected_shortfall_95",
                        "expected_shortfall_99",
                    ]:
                        formatted_value = f"${value:.2f}"
                        label_widget.config(style="Bad.TLabel")
                    elif key == "portfolio_volatility":
                        formatted_value = f"{value * 100:.2f}{suffix}"
                        style = "Warn.TLabel" if value > 0.5 else "TLabel"
                        label_widget.config(style=style)
                    else:
                        formatted_value = f"{value:.3f}{suffix}"
                        label_widget.config(style="TLabel")

                    label_widget.config(text=formatted_value)

                # Update risk visualization
                if MATPLOTLIB_AVAILABLE and hasattr(self, "risk_canvas"):
                    self.update_risk_charts(risk_metrics)

        except Exception as e:
            print(f"Error calculating risk metrics: {e}")
            messagebox.showerror("Error", f"Error calculating risk metrics: {e}")

    def update_risk_charts(self, risk_metrics):
        """Update risk visualization charts"""
        if not MATPLOTLIB_AVAILABLE:
            return

        try:
            chart = ui_tokens.CHART
            status = ui_tokens.STATUS
            self.risk_fig.clear()

            # VaR and ES comparison
            ax1 = self.risk_fig.add_subplot(1, 2, 1)
            categories = ["VaR 95%", "VaR 99%", "ES 95%", "ES 99%"]
            values = [
                risk_metrics.var_95,
                risk_metrics.var_99,
                risk_metrics.expected_shortfall_95,
                risk_metrics.expected_shortfall_99,
            ]

            bars = ax1.bar(
                categories,
                values,
                color=[status["warn"], status["bad"], status["warn"], status["bad"]],
                alpha=0.7,
            )
            ax1.set_title("Risk Measures", color=chart["text"])
            ax1.set_ylabel("Value ($)", color=chart["text"])
            ax1.tick_params(colors=chart["text"])

            # Rotate labels for better readability
            plt.setp(ax1.get_xticklabels(), rotation=45)

            # Risk profile gauge
            ax2 = self.risk_fig.add_subplot(1, 2, 2)

            # Simple risk level indicator
            volatility = risk_metrics.portfolio_volatility
            if volatility < 0.2:
                risk_level = "Low"
                color = status["good"]
            elif volatility < 0.5:
                risk_level = "Medium"
                color = status["warn"]
            else:
                risk_level = "High"
                color = status["bad"]

            ax2.text(
                0.5,
                0.6,
                "Risk Level",
                ha="center",
                va="center",
                fontsize=14,
                color=chart["text"],
            )
            ax2.text(
                0.5,
                0.4,
                risk_level,
                ha="center",
                va="center",
                fontsize=20,
                color=color,
                weight="bold",
            )
            ax2.text(
                0.5,
                0.2,
                f"Volatility: {volatility * 100:.1f}%",
                ha="center",
                va="center",
                fontsize=12,
                color=chart["text"],
            )

            ax2.set_xlim(0, 1)
            ax2.set_ylim(0, 1)
            ax2.axis("off")

            ui_theme.theme_figure(self.risk_fig)
            self.risk_canvas.draw()

        except Exception as e:
            print(f"Error updating risk charts: {e}")

    def update_allocation_analysis(self):
        """Update asset allocation analysis"""
        if not ANALYTICS_AVAILABLE or not self.analytics:
            return

        try:
            days = int(self.allocation_period_var.get())
            allocation_history = self.analytics.get_asset_allocation_history(days)

            # Clear current allocation tree
            for item in self.allocation_tree.get_children():
                self.allocation_tree.delete(item)

            # Get latest allocation data
            if allocation_history:
                latest_allocations = {}
                for symbol, history in allocation_history.items():
                    if history:
                        latest_allocations[symbol] = history[-1][1]  # Latest percentage

                # Add to tree
                total_value = 10000  # Placeholder - would come from actual portfolio
                for symbol, percentage in sorted(latest_allocations.items()):
                    value = total_value * (percentage / 100)
                    self.allocation_tree.insert(
                        "",
                        "end",
                        text=symbol,
                        values=(f"{percentage:.2f}%", f"${value:.2f}"),
                    )

            # Update allocation charts
            if MATPLOTLIB_AVAILABLE and hasattr(self, "allocation_canvas"):
                self.update_allocation_charts(allocation_history)

        except Exception as e:
            print(f"Error updating allocation analysis: {e}")
            messagebox.showerror("Error", f"Error updating allocation analysis: {e}")

    def update_allocation_charts(self, allocation_history):
        """Update allocation history charts"""
        if not MATPLOTLIB_AVAILABLE or not allocation_history:
            return

        try:
            chart = ui_tokens.CHART
            self.allocation_fig.clear()
            ax = self.allocation_fig.add_subplot(1, 1, 1)

            for symbol, history in allocation_history.items():
                if history:
                    dates = [
                        (
                            datetime.fromisoformat(item[0].replace("Z", "+00:00"))
                            if "Z" in item[0]
                            else datetime.fromisoformat(item[0])
                        )
                        for item, _ in history
                    ]
                    percentages = [item[1] for _, item in history]

                    ax.plot(
                        dates,
                        percentages,
                        label=symbol,
                        linewidth=2,
                        marker="o",
                        markersize=4,
                    )

            ax.set_title("Asset Allocation History", color=chart["text"])
            ax.set_xlabel("Date", color=chart["text"])
            ax.set_ylabel("Allocation (%)", color=chart["text"])
            ax.tick_params(colors=chart["text"])
            ax.legend()
            ax.grid(True, alpha=0.3)

            # Format x-axis
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
            self.allocation_fig.autofmt_xdate()

            ui_theme.theme_figure(self.allocation_fig)  # the legend too
            self.allocation_canvas.draw()

        except Exception as e:
            print(f"Error updating allocation charts: {e}")

    def run_monte_carlo(self):
        """Run Monte Carlo simulation"""
        messagebox.showinfo("Info", "Monte Carlo simulation feature coming soon")

    def generate_report(self):
        """Generate analytics report"""
        if not ANALYTICS_AVAILABLE or not self.analytics:
            messagebox.showerror("Error", "Analytics system not available")
            return

        try:
            report_type = self.report_type_var.get()
            period = int(self.report_period_var.get())

            # Generate report text
            report_lines = []
            report_lines.append(f"=== {report_type.title()} Analytics Report ===")
            report_lines.append(
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            report_lines.append(f"Analysis Period: {period} days")
            report_lines.append("")

            if report_type in ["comprehensive", "performance"]:
                performance = self.analytics.calculate_performance_metrics(period)
                if performance:
                    report_lines.append("PERFORMANCE METRICS:")
                    report_lines.append(
                        f"  Total Return: ${performance.total_return:.2f}"
                    )
                    report_lines.append(
                        f"  Total Return %: {performance.total_return_pct:.2f}%"
                    )
                    report_lines.append(
                        f"  Sharpe Ratio: {performance.sharpe_ratio:.3f}"
                    )
                    report_lines.append(
                        f"  Max Drawdown: {performance.max_drawdown:.2f}%"
                    )
                    report_lines.append(
                        f"  Volatility: {performance.volatility * 100:.2f}%"
                    )
                    report_lines.append("")

            if report_type in ["comprehensive", "risk"]:
                risk_metrics = self.analytics.calculate_risk_metrics()
                if risk_metrics:
                    report_lines.append("RISK METRICS:")
                    report_lines.append(
                        f"  Value at Risk (95%): ${risk_metrics.var_95:.2f}"
                    )
                    report_lines.append(
                        f"  Value at Risk (99%): ${risk_metrics.var_99:.2f}"
                    )
                    report_lines.append(
                        f"  Expected Shortfall (95%): ${risk_metrics.expected_shortfall_95:.2f}"
                    )
                    report_lines.append(
                        f"  Expected Shortfall (99%): ${risk_metrics.expected_shortfall_99:.2f}"
                    )
                    report_lines.append(
                        f"  Portfolio Volatility: {risk_metrics.portfolio_volatility * 100:.2f}%"
                    )
                    report_lines.append(
                        f"  Concentration Risk: {risk_metrics.concentration_risk:.3f}"
                    )
                    report_lines.append("")

            if report_type in ["comprehensive", "allocation"]:
                allocation_history = self.analytics.get_asset_allocation_history(period)
                if allocation_history:
                    report_lines.append("CURRENT ALLOCATION:")
                    for symbol, history in allocation_history.items():
                        if history:
                            latest_pct = history[-1][1]
                            report_lines.append(f"  {symbol}: {latest_pct:.2f}%")
                    report_lines.append("")

            # Display report
            self.report_text.delete(1.0, tk.END)
            self.report_text.insert(1.0, "\n".join(report_lines))

        except Exception as e:
            print(f"Error generating report: {e}")
            messagebox.showerror("Error", f"Error generating report: {e}")

    def export_performance_data(self):
        """Export performance data to CSV"""
        if not ANALYTICS_AVAILABLE:
            messagebox.showerror("Error", "Analytics system not available")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Performance Data",
        )

        if file_path:
            messagebox.showinfo("Info", "Performance data export feature coming soon")

    def export_risk_report(self):
        """Export risk analysis report"""
        messagebox.showinfo("Info", "Risk report export feature coming soon")

    def export_pdf_report(self):
        """Export report to PDF"""
        messagebox.showinfo("Info", "PDF export feature coming soon")

    def export_excel_report(self):
        """Export report to Excel"""
        messagebox.showinfo("Info", "Excel export feature coming soon")


# Fallback class for when analytics is not available
if not ANALYTICS_AVAILABLE:

    class PortfolioAnalyticsGUI:
        def __init__(self, parent):
            self.parent = parent
            self.setup_fallback_ui()

        def setup_fallback_ui(self):
            frame = ttk.Frame(self.parent)
            frame.pack(fill="both", expand=True, padx=20, pady=20)

            ttk.Label(
                frame,
                text="Enhanced Portfolio Analytics",
                font=ui_tokens.font("display", "bold"),
            ).pack(pady=20)

            ttk.Label(
                frame,
                text="⚠️ Portfolio analytics system not available",
                style="Warn.TLabel",
                font=ui_tokens.font("title"),
            ).pack(pady=10)

            ttk.Label(
                frame, text="Missing dependencies:", font=ui_tokens.font("body", "bold")
            ).pack(pady=5)

            missing_deps = []
            if not PANDAS_AVAILABLE:
                missing_deps.append("pandas, numpy")
            if not MATPLOTLIB_AVAILABLE:
                missing_deps.append("matplotlib, seaborn")

            if missing_deps:
                for dep in missing_deps:
                    ttk.Label(frame, text=f"• {dep}", style="Bad.TLabel").pack()
            else:
                ttk.Label(
                    frame, text="• portfolio_analytics module", style="Bad.TLabel"
                ).pack()

            ttk.Label(
                frame,
                text="Install missing dependencies to enable advanced analytics",
                style="Muted.TLabel",
                font=ui_tokens.font("body"),
            ).pack(pady=10)
