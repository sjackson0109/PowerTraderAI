#!/usr/bin/env python3
"""
Performance Attribution GUI for PowerTrader
Interactive interface for portfolio performance attribution analysis.
"""

import json
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

import ui_table
import ui_theme
import ui_tokens

try:
    from performance_attribution import (
        AttributionMethod,
        AttributionResult,
        AttributionType,
        Holding,
        PerformanceAttributionEngine,
        create_sample_benchmark,
        create_sample_portfolio,
    )

    ATTRIBUTION_AVAILABLE = True
except ImportError:
    ATTRIBUTION_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False


class PerformanceAttributionGUI:
    """
    Interactive GUI for performance attribution analysis.
    """

    def __init__(self, parent=None):
        """Initialize the Performance Attribution GUI."""
        if parent is None:
            self.root = ui_theme.themed_root()
            self.root.title("Performance Attribution Analysis")
            self.root.geometry("1400x900")
        else:
            self.root = parent

        # Initialize attribution engine
        if ATTRIBUTION_AVAILABLE:
            self.engine = PerformanceAttributionEngine()
        else:
            self.engine = None

        # GUI state
        self.portfolio_holdings = []
        self.benchmark_holdings = []
        self.attribution_results = {}
        self.risk_attribution = None

        self.setup_gui()

    def setup_gui(self):
        """Setup the main GUI layout."""
        if not ATTRIBUTION_AVAILABLE:
            self.show_dependency_message()
            return

        # Create main notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Create tabs
        self.setup_data_input_tab()
        self.setup_sector_attribution_tab()
        self.setup_factor_attribution_tab()
        self.setup_risk_attribution_tab()
        self.setup_reports_tab()

    def show_dependency_message(self):
        """Show message about missing dependencies."""
        p = ui_theme.active_palette()
        msg_frame = tk.Frame(self.root)
        msg_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            msg_frame,
            text="Performance Attribution Engine - Enhanced Features Available",
            font=ui_tokens.font("display", "bold"),
        ).pack(pady=20)

        tk.Label(
            msg_frame,
            text="For full attribution analysis capabilities, install optional dependencies:",
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
            "• Brinson-Hood-Beebower attribution analysis",
            "• Multi-factor performance attribution",
            "• Style-based attribution analysis",
            "• Risk attribution and decomposition",
            "• Interactive charts and visualizations",
            "• Comprehensive attribution reports",
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

    def setup_data_input_tab(self):
        """Setup the data input and portfolio configuration tab."""
        data_frame = ttk.Frame(self.notebook)
        self.notebook.add(data_frame, text="Data Input")

        # Create left and right panels
        left_panel = ttk.Frame(data_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        right_panel = ttk.Frame(data_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # Left Panel - Portfolio Data
        self.setup_portfolio_section(left_panel)

        # Right Panel - Benchmark Data
        self.setup_benchmark_section(right_panel)

        # Bottom Panel - Controls
        bottom_panel = ttk.Frame(data_frame)
        bottom_panel.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        self.setup_data_controls(bottom_panel)

    def setup_portfolio_section(self, parent):
        """Setup portfolio data input section."""
        portfolio_section = ttk.LabelFrame(parent, text="Portfolio Holdings")
        portfolio_section.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # File input controls
        file_frame = tk.Frame(portfolio_section)
        file_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(file_frame, text="Portfolio File:").pack(side=tk.LEFT)
        self.portfolio_file_var = tk.StringVar()
        tk.Entry(file_frame, textvariable=self.portfolio_file_var, width=30).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(file_frame, text="Browse", command=self.browse_portfolio_file).pack(
            side=tk.LEFT
        )
        ttk.Button(
            file_frame, text="Load Sample", command=self.load_sample_portfolio
        ).pack(side=tk.LEFT, padx=5)

        # Portfolio holdings display
        holdings_frame = ttk.LabelFrame(portfolio_section, text="Current Holdings")
        holdings_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Portfolio holdings table
        self.portfolio_table = ui_table.DataTable(
            holdings_frame,
            ("Security", "Weight", "Return", "Sector"),
            {
                "Security": "Security",
                "Weight": "Weight",
                "Return": "Return",
                "Sector": "Sector",
            },
            key="performance_attribution.portfolio_holdings",
            numeric=("Weight", "Return"),
            empty_text="No holdings yet",
        )
        self.portfolio_table.pack(fill=tk.BOTH, expand=True)
        self.portfolio_tree = self.portfolio_table.tree

        # Add/Edit controls
        portfolio_controls = tk.Frame(portfolio_section)
        portfolio_controls.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(
            portfolio_controls, text="Add Holding", command=self.add_portfolio_holding
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            portfolio_controls,
            text="Edit Selected",
            command=self.edit_portfolio_holding,
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            portfolio_controls,
            text="Remove Selected",
            command=self.remove_portfolio_holding,
        ).pack(side=tk.LEFT, padx=5)

    def setup_benchmark_section(self, parent):
        """Setup benchmark data input section."""
        benchmark_section = ttk.LabelFrame(parent, text="Benchmark Holdings")
        benchmark_section.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # File input controls
        file_frame = tk.Frame(benchmark_section)
        file_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(file_frame, text="Benchmark File:").pack(side=tk.LEFT)
        self.benchmark_file_var = tk.StringVar()
        tk.Entry(file_frame, textvariable=self.benchmark_file_var, width=30).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(file_frame, text="Browse", command=self.browse_benchmark_file).pack(
            side=tk.LEFT
        )
        ttk.Button(
            file_frame, text="Load Sample", command=self.load_sample_benchmark
        ).pack(side=tk.LEFT, padx=5)

        # Benchmark holdings display
        holdings_frame = ttk.LabelFrame(benchmark_section, text="Current Holdings")
        holdings_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Benchmark holdings table
        self.benchmark_table = ui_table.DataTable(
            holdings_frame,
            ("Security", "Weight", "Return", "Sector"),
            {
                "Security": "Security",
                "Weight": "Weight",
                "Return": "Return",
                "Sector": "Sector",
            },
            key="performance_attribution.benchmark_holdings",
            numeric=("Weight", "Return"),
            empty_text="No holdings yet",
        )
        self.benchmark_table.pack(fill=tk.BOTH, expand=True)
        self.benchmark_tree = self.benchmark_table.tree

        # Add/Edit controls
        benchmark_controls = tk.Frame(benchmark_section)
        benchmark_controls.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(
            benchmark_controls, text="Add Holding", command=self.add_benchmark_holding
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            benchmark_controls,
            text="Edit Selected",
            command=self.edit_benchmark_holding,
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            benchmark_controls,
            text="Remove Selected",
            command=self.remove_benchmark_holding,
        ).pack(side=tk.LEFT, padx=5)

    def setup_data_controls(self, parent):
        """Setup data control buttons."""
        controls_frame = ttk.LabelFrame(parent, text="Attribution Controls")
        controls_frame.pack(fill=tk.X, padx=5, pady=5)

        buttons_frame = tk.Frame(controls_frame)
        buttons_frame.pack(padx=5, pady=5)

        ttk.Button(
            buttons_frame, text="Run All Attribution", command=self.run_all_attribution
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Quick Demo", command=self.run_quick_demo).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            buttons_frame, text="Clear Results", command=self.clear_results
        ).pack(side=tk.LEFT, padx=5)

        # Progress indicators
        self.progress_var = tk.StringVar(value="Ready")
        tk.Label(controls_frame, textvariable=self.progress_var).pack(pady=5)

    def setup_sector_attribution_tab(self):
        """Setup the sector attribution analysis tab."""
        sector_frame = ttk.Frame(self.notebook)
        self.notebook.add(sector_frame, text="Sector Attribution")

        # Create top and bottom panels
        top_panel = ttk.Frame(sector_frame)
        top_panel.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        bottom_panel = ttk.Frame(sector_frame)
        bottom_panel.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Attribution method selection
        method_frame = ttk.LabelFrame(top_panel, text="Attribution Method")
        method_frame.pack(fill=tk.X, padx=5, pady=5)

        method_controls = tk.Frame(method_frame)
        method_controls.pack(padx=5, pady=5)

        tk.Label(method_controls, text="Method:").pack(side=tk.LEFT)
        self.attribution_method_var = tk.StringVar(value="Brinson-Hood-Beebower")
        ttk.Combobox(
            method_controls,
            textvariable=self.attribution_method_var,
            values=["Brinson-Hood-Beebower", "Brinson-Fachler"],
            state="readonly",
            width=20,
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            method_controls,
            text="Run Sector Attribution",
            command=self.run_sector_attribution,
        ).pack(side=tk.LEFT, padx=10)

        # Results display
        results_frame = ttk.LabelFrame(bottom_panel, text="Sector Attribution Results")
        results_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Create left and right panels for results
        results_left = tk.Frame(results_frame)
        results_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        results_right = tk.Frame(results_frame)
        results_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Summary metrics
        summary_frame = ttk.LabelFrame(results_left, text="Summary")
        summary_frame.pack(fill=tk.X, padx=5, pady=5)

        self.sector_summary_table = ui_table.DataTable(
            summary_frame,
            ("Value",),
            {"Value": "Value"},
            key="performance_attribution.sector_summary",
            numeric=("Value",),
            empty_text="No metrics yet",
            show="tree headings",
            sortable=False,  # a list of metrics, not rows to sort
            height=6,
        )
        self.sector_summary_table.pack(fill=tk.BOTH, expand=True)
        self.sector_summary_tree = self.sector_summary_table.tree
        self.sector_summary_tree.heading("#0", text="Metric")  # each row's own text

        # Detailed breakdown
        breakdown_frame = ttk.LabelFrame(results_left, text="Sector Breakdown")
        breakdown_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.sector_breakdown_table = ui_table.DataTable(
            breakdown_frame,
            ("Allocation", "Selection", "Interaction", "Total"),
            {
                "Allocation": "Allocation",
                "Selection": "Selection",
                "Interaction": "Interaction",
                "Total": "Total",
            },
            key="performance_attribution.sector_breakdown",
            numeric=("Allocation", "Selection", "Interaction", "Total"),
            empty_text="No sectors yet",
            show="tree headings",  # each row's sector, inserted as its text
        )
        self.sector_breakdown_table.pack(fill=tk.BOTH, expand=True)
        self.sector_breakdown_tree = self.sector_breakdown_table.tree
        self.sector_breakdown_tree.heading("#0", text="Sector")

        # Chart area
        chart_frame = ttk.LabelFrame(results_right, text="Sector Attribution Chart")
        chart_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        if PLOTTING_AVAILABLE:
            chart_controls = tk.Frame(chart_frame)
            chart_controls.pack(fill=tk.X, padx=5, pady=5)

            ttk.Button(
                chart_controls,
                text="Attribution Chart",
                command=self.plot_sector_attribution,
            ).pack(side=tk.LEFT, padx=5)
            ttk.Button(
                chart_controls,
                text="Allocation vs Selection",
                command=self.plot_allocation_selection,
            ).pack(side=tk.LEFT, padx=5)

        self.sector_chart_frame = tk.Frame(chart_frame)
        self.sector_chart_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def setup_factor_attribution_tab(self):
        """Setup the factor attribution analysis tab."""
        factor_frame = ttk.Frame(self.notebook)
        self.notebook.add(factor_frame, text="Factor Attribution")

        # Factor selection and controls
        controls_frame = ttk.LabelFrame(factor_frame, text="Factor Analysis Controls")
        controls_frame.pack(fill=tk.X, padx=10, pady=5)

        factor_controls = tk.Frame(controls_frame)
        factor_controls.pack(padx=5, pady=5)

        tk.Label(factor_controls, text="Analysis Type:").pack(side=tk.LEFT)
        self.factor_type_var = tk.StringVar(value="Equity Factors")
        ttk.Combobox(
            factor_controls,
            textvariable=self.factor_type_var,
            values=["Equity Factors", "Style Factors", "Custom Factors"],
            state="readonly",
            width=15,
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            factor_controls,
            text="Run Factor Attribution",
            command=self.run_factor_attribution,
        ).pack(side=tk.LEFT, padx=10)
        ttk.Button(
            factor_controls,
            text="Run Style Attribution",
            command=self.run_style_attribution,
        ).pack(side=tk.LEFT, padx=5)

        # Results display
        results_frame = ttk.LabelFrame(factor_frame, text="Factor Attribution Results")
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Create left and right panels
        results_left = tk.Frame(results_frame)
        results_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        results_right = tk.Frame(results_frame)
        results_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Factor contributions
        factor_breakdown_frame = ttk.LabelFrame(
            results_left, text="Factor Contributions"
        )
        factor_breakdown_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.factor_table = ui_table.DataTable(
            factor_breakdown_frame,
            ("Exposure", "Return", "Contribution"),
            {
                "Exposure": "Exposure",
                "Return": "Return",
                "Contribution": "Contribution",
            },
            key="performance_attribution.factor_contributions",
            numeric=("Exposure", "Return", "Contribution"),
            empty_text="No factors yet",
            show="tree headings",  # each row's factor, inserted as its text
        )
        self.factor_table.pack(fill=tk.BOTH, expand=True)
        self.factor_tree = self.factor_table.tree
        self.factor_tree.heading("#0", text="Factor")

        # Factor chart area
        factor_chart_frame = ttk.LabelFrame(
            results_right, text="Factor Attribution Chart"
        )
        factor_chart_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        if PLOTTING_AVAILABLE:
            factor_chart_controls = tk.Frame(factor_chart_frame)
            factor_chart_controls.pack(fill=tk.X, padx=5, pady=5)

            ttk.Button(
                factor_chart_controls,
                text="Factor Contributions",
                command=self.plot_factor_attribution,
            ).pack(side=tk.LEFT, padx=5)

        self.factor_chart_frame = tk.Frame(factor_chart_frame)
        self.factor_chart_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def setup_risk_attribution_tab(self):
        """Setup the risk attribution analysis tab."""
        risk_frame = ttk.Frame(self.notebook)
        self.notebook.add(risk_frame, text="Risk Attribution")

        # Risk analysis controls
        controls_frame = ttk.LabelFrame(risk_frame, text="Risk Analysis Controls")
        controls_frame.pack(fill=tk.X, padx=10, pady=5)

        risk_controls = tk.Frame(controls_frame)
        risk_controls.pack(padx=5, pady=5)

        ttk.Button(
            risk_controls,
            text="Calculate Risk Attribution",
            command=self.calculate_risk_attribution,
        ).pack(side=tk.LEFT, padx=5)

        # Risk results display
        results_frame = ttk.LabelFrame(risk_frame, text="Risk Attribution Results")
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Create left and right panels
        results_left = tk.Frame(results_frame)
        results_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        results_right = tk.Frame(results_frame)
        results_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Portfolio risk metrics
        risk_metrics_frame = ttk.LabelFrame(results_left, text="Portfolio Risk Metrics")
        risk_metrics_frame.pack(fill=tk.X, padx=5, pady=5)

        self.risk_metrics_table = ui_table.DataTable(
            risk_metrics_frame,
            ("Value",),
            {"Value": "Value"},
            key="performance_attribution.risk_metrics",
            numeric=("Value",),
            empty_text="No metrics yet",
            show="tree headings",
            sortable=False,  # a list of metrics, not rows to sort
            height=6,
        )
        self.risk_metrics_table.pack(fill=tk.BOTH, expand=True)
        self.risk_metrics_tree = self.risk_metrics_table.tree
        self.risk_metrics_tree.heading("#0", text="Metric")  # each row's own text

        # Component risk contributions
        risk_breakdown_frame = ttk.LabelFrame(
            results_left, text="Component Risk Contributions"
        )
        risk_breakdown_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.risk_breakdown_table = ui_table.DataTable(
            risk_breakdown_frame,
            ("Weight", "Marginal", "Component", "Percentage"),
            {
                "Weight": "Weight",
                "Marginal": "Marginal",
                "Component": "Component",
                "Percentage": "Percentage",
            },
            key="performance_attribution.risk_contributions",
            numeric=("Weight", "Marginal", "Component", "Percentage"),
            empty_text="No contributions yet",
            show="tree headings",  # each row's security, inserted as its text
        )
        self.risk_breakdown_table.pack(fill=tk.BOTH, expand=True)
        self.risk_breakdown_tree = self.risk_breakdown_table.tree
        self.risk_breakdown_tree.heading("#0", text="Security")

        # Risk chart area
        risk_chart_frame = ttk.LabelFrame(results_right, text="Risk Attribution Charts")
        risk_chart_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        if PLOTTING_AVAILABLE:
            risk_chart_controls = tk.Frame(risk_chart_frame)
            risk_chart_controls.pack(fill=tk.X, padx=5, pady=5)

            ttk.Button(
                risk_chart_controls,
                text="Risk Contributions",
                command=self.plot_risk_attribution,
            ).pack(side=tk.LEFT, padx=5)

        self.risk_chart_frame = tk.Frame(risk_chart_frame)
        self.risk_chart_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def setup_reports_tab(self):
        """Setup the reports and export tab."""
        reports_frame = ttk.Frame(self.notebook)
        self.notebook.add(reports_frame, text="Reports")

        # Report generation controls
        controls_frame = ttk.LabelFrame(reports_frame, text="Report Generation")
        controls_frame.pack(fill=tk.X, padx=10, pady=5)

        report_controls = tk.Frame(controls_frame)
        report_controls.pack(padx=5, pady=5)

        tk.Label(report_controls, text="Report Type:").pack(side=tk.LEFT)
        self.report_type_var = tk.StringVar(value="Complete Attribution")
        ttk.Combobox(
            report_controls,
            textvariable=self.report_type_var,
            values=["Complete Attribution", "Sector Only", "Factor Only", "Risk Only"],
            state="readonly",
            width=18,
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            report_controls, text="Generate Report", command=self.generate_report
        ).pack(side=tk.LEFT, padx=10)
        ttk.Button(
            report_controls, text="Export to File", command=self.export_report
        ).pack(side=tk.LEFT, padx=5)

        # Report display
        report_display_frame = ttk.LabelFrame(reports_frame, text="Attribution Report")
        report_display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.report_text = tk.Text(
            report_display_frame, wrap=tk.WORD, font=ui_tokens.mono("small")
        )
        report_scrollbar = ttk.Scrollbar(report_display_frame, orient=tk.VERTICAL)
        ui_table.scroll_when_needed(self.report_text, report_scrollbar)

    # Event handlers and data management
    def browse_portfolio_file(self):
        """Browse for portfolio file."""
        filename = filedialog.askopenfilename(
            title="Select Portfolio File",
            filetypes=[
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx"),
                ("All files", "*.*"),
            ],
        )
        if filename:
            self.portfolio_file_var.set(filename)
            self.load_portfolio_file(filename)

    def browse_benchmark_file(self):
        """Browse for benchmark file."""
        filename = filedialog.askopenfilename(
            title="Select Benchmark File",
            filetypes=[
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx"),
                ("All files", "*.*"),
            ],
        )
        if filename:
            self.benchmark_file_var.set(filename)
            self.load_benchmark_file(filename)

    def load_portfolio_file(self, filename):
        """Load portfolio from file."""
        try:
            # Load data based on file extension
            if filename.endswith(".csv"):
                data = pd.read_csv(filename)
            elif filename.endswith(".xlsx"):
                data = pd.read_excel(filename)

            # Convert to holdings
            self.portfolio_holdings = self._dataframe_to_holdings(data)
            self.update_portfolio_display()

            messagebox.showinfo(
                "Success", f"Portfolio loaded: {len(self.portfolio_holdings)} holdings"
            )

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load portfolio: {str(e)}")

    def load_benchmark_file(self, filename):
        """Load benchmark from file."""
        try:
            # Load data based on file extension
            if filename.endswith(".csv"):
                data = pd.read_csv(filename)
            elif filename.endswith(".xlsx"):
                data = pd.read_excel(filename)

            # Convert to holdings
            self.benchmark_holdings = self._dataframe_to_holdings(data)
            self.update_benchmark_display()

            messagebox.showinfo(
                "Success", f"Benchmark loaded: {len(self.benchmark_holdings)} holdings"
            )

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load benchmark: {str(e)}")

    def load_sample_portfolio(self):
        """Load sample portfolio data."""
        if ATTRIBUTION_AVAILABLE:
            self.portfolio_holdings = create_sample_portfolio()
            self.update_portfolio_display()
            messagebox.showinfo("Success", "Sample portfolio loaded")

    def load_sample_benchmark(self):
        """Load sample benchmark data."""
        if ATTRIBUTION_AVAILABLE:
            self.benchmark_holdings = create_sample_benchmark()
            self.update_benchmark_display()
            messagebox.showinfo("Success", "Sample benchmark loaded")

    def update_portfolio_display(self):
        """Update portfolio holdings display."""
        # Clear existing items
        for item in self.portfolio_tree.get_children():
            self.portfolio_tree.delete(item)

        # Add holdings
        for holding in self.portfolio_holdings:
            self.portfolio_tree.insert(
                "",
                "end",
                values=(
                    holding.security,
                    f"{holding.weight:.3f}",
                    f"{holding.return_period:.3f}",
                    holding.sector or "N/A",
                ),
            )

    def update_benchmark_display(self):
        """Update benchmark holdings display."""
        # Clear existing items
        for item in self.benchmark_tree.get_children():
            self.benchmark_tree.delete(item)

        # Add holdings
        for holding in self.benchmark_holdings:
            self.benchmark_tree.insert(
                "",
                "end",
                values=(
                    holding.security,
                    f"{holding.weight:.3f}",
                    f"{holding.return_period:.3f}",
                    holding.sector or "N/A",
                ),
            )

    def run_all_attribution(self):
        """Run all attribution analyses."""
        if not self.portfolio_holdings or not self.benchmark_holdings:
            messagebox.showerror(
                "Error", "Please load both portfolio and benchmark data first"
            )
            return

        try:
            self.progress_var.set("Running attribution analyses...")

            # Run sector attribution
            self.run_sector_attribution()

            # Run factor attribution
            self.run_factor_attribution()

            # Run style attribution
            self.run_style_attribution()

            # Calculate risk attribution
            self.calculate_risk_attribution()

            self.progress_var.set("All attribution analyses completed")
            messagebox.showinfo(
                "Success", "All attribution analyses completed successfully!"
            )

        except Exception as e:
            self.progress_var.set("Error")
            messagebox.showerror("Error", f"Attribution analysis failed: {str(e)}")

    def run_quick_demo(self):
        """Run quick demo with sample data."""
        if ATTRIBUTION_AVAILABLE:
            self.load_sample_portfolio()
            self.load_sample_benchmark()
            # Give a moment for data to load, then run analyses
            self.root.after(100, self.run_all_attribution)

    def run_sector_attribution(self):
        """Run sector attribution analysis."""
        if not self.portfolio_holdings or not self.benchmark_holdings:
            messagebox.showerror(
                "Error", "Please load both portfolio and benchmark data first"
            )
            return

        try:
            # Determine method
            method = (
                AttributionMethod.BRINSON_HOOD_BEEBOWER
                if self.attribution_method_var.get() == "Brinson-Hood-Beebower"
                else AttributionMethod.BRINSON_FACHLER
            )

            # Run attribution
            result = self.engine.brinson_attribution(
                self.portfolio_holdings, self.benchmark_holdings, method
            )
            self.attribution_results["sector"] = result

            # Update display
            self.display_sector_results(result)

        except Exception as e:
            messagebox.showerror("Error", f"Sector attribution failed: {str(e)}")

    def run_factor_attribution(self):
        """Run factor attribution analysis."""
        if not self.portfolio_holdings:
            messagebox.showerror("Error", "Please load portfolio data first")
            return

        try:
            result = self.engine.factor_attribution(self.portfolio_holdings, {})
            self.attribution_results["factor"] = result

            # Update display
            self.display_factor_results(result)

        except Exception as e:
            messagebox.showerror("Error", f"Factor attribution failed: {str(e)}")

    def run_style_attribution(self):
        """Run style attribution analysis."""
        if not self.portfolio_holdings or not self.benchmark_holdings:
            messagebox.showerror(
                "Error", "Please load both portfolio and benchmark data first"
            )
            return

        try:
            result = self.engine.style_attribution(
                self.portfolio_holdings, self.benchmark_holdings
            )
            self.attribution_results["style"] = result

        except Exception as e:
            messagebox.showerror("Error", f"Style attribution failed: {str(e)}")

    def calculate_risk_attribution(self):
        """Calculate risk attribution."""
        if not self.portfolio_holdings:
            messagebox.showerror("Error", "Please load portfolio data first")
            return

        try:
            self.risk_attribution = self.engine.calculate_risk_attribution(
                self.portfolio_holdings
            )
            self.display_risk_results(self.risk_attribution)

        except Exception as e:
            messagebox.showerror("Error", f"Risk attribution failed: {str(e)}")

    def display_sector_results(self, result):
        """Display sector attribution results."""
        # Clear existing results
        for item in self.sector_summary_tree.get_children():
            self.sector_summary_tree.delete(item)

        for item in self.sector_breakdown_tree.get_children():
            self.sector_breakdown_tree.delete(item)

        # Display summary
        summary_items = [
            (
                "Total Attribution",
                f"{result.total_attribution:.4f} ({result.total_attribution*100:.2f}%)",
            ),
            (
                "Allocation Effect",
                f"{result.allocation_effect:.4f} ({result.allocation_effect*100:.2f}%)",
            ),
            (
                "Selection Effect",
                f"{result.selection_effect:.4f} ({result.selection_effect*100:.2f}%)",
            ),
            (
                "Interaction Effect",
                f"{result.interaction_effect:.4f} ({result.interaction_effect*100:.2f}%)",
            ),
        ]

        for metric, value in summary_items:
            self.sector_summary_tree.insert("", "end", text=metric, values=(value,))

        # Display breakdown
        for sector, attribution in result.attribution_breakdown.items():
            if isinstance(attribution, dict):
                self.sector_breakdown_tree.insert(
                    "",
                    "end",
                    text=sector,
                    values=(
                        f"{attribution.get('allocation', 0):.4f}",
                        f"{attribution.get('selection', 0):.4f}",
                        f"{attribution.get('interaction', 0):.4f}",
                        f"{attribution.get('total', 0):.4f}",
                    ),
                )

    def display_factor_results(self, result):
        """Display factor attribution results."""
        # Clear existing results
        for item in self.factor_tree.get_children():
            self.factor_tree.delete(item)

        # Display factor contributions
        for factor, contribution in result.attribution_breakdown.items():
            # For simplicity, show factor contribution
            self.factor_tree.insert(
                "",
                "end",
                text=factor,
                values=(
                    "1.0",  # Placeholder exposure
                    f"{self.engine.sample_factor_returns.get(factor, 0):.4f}",
                    f"{contribution:.4f}",
                ),
            )

    def display_risk_results(self, risk_attribution):
        """Display risk attribution results."""
        # Clear existing results
        for item in self.risk_metrics_tree.get_children():
            self.risk_metrics_tree.delete(item)

        for item in self.risk_breakdown_tree.get_children():
            self.risk_breakdown_tree.delete(item)

        # Display portfolio risk metrics
        metrics = [
            ("Portfolio Volatility", f"{risk_attribution['portfolio_volatility']:.4f}"),
            ("Portfolio Variance", f"{risk_attribution['portfolio_variance']:.6f}"),
            (
                "Diversification Ratio",
                f"{risk_attribution['diversification_ratio']:.3f}",
            ),
        ]

        for metric, value in metrics:
            self.risk_metrics_tree.insert("", "end", text=metric, values=(value,))

        # Display component contributions
        for i, (security, marginal) in enumerate(
            risk_attribution["marginal_contributions"].items()
        ):
            component = list(risk_attribution["component_contributions"].values())[i]
            percentage = list(risk_attribution["percentage_contributions"].values())[i]
            weight = (
                self.portfolio_holdings[i].weight
                if i < len(self.portfolio_holdings)
                else 0.0
            )

            self.risk_breakdown_tree.insert(
                "",
                "end",
                text=security,
                values=(
                    f"{weight:.3f}",
                    f"{marginal:.4f}",
                    f"{component:.4f}",
                    f"{percentage:.4f}",
                ),
            )

    def clear_results(self):
        """Clear all results."""
        self.attribution_results = {}
        self.risk_attribution = None

        # Clear displays
        for tree in [
            self.sector_summary_tree,
            self.sector_breakdown_tree,
            self.factor_tree,
            self.risk_metrics_tree,
            self.risk_breakdown_tree,
        ]:
            for item in tree.get_children():
                tree.delete(item)

        # Clear charts
        for chart_frame in [
            self.sector_chart_frame,
            self.factor_chart_frame,
            self.risk_chart_frame,
        ]:
            for widget in chart_frame.winfo_children():
                widget.destroy()

        self.report_text.delete("1.0", tk.END)
        self.progress_var.set("Ready")

    def generate_report(self):
        """Generate comprehensive attribution report."""
        if not self.attribution_results:
            messagebox.showwarning(
                "Warning", "No attribution results available. Run analyses first."
            )
            return

        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("PERFORMANCE ATTRIBUTION COMPREHENSIVE REPORT")
        report_lines.append("=" * 80)
        report_lines.append(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        report_lines.append("")

        # Add individual attribution reports
        for attribution_type, result in self.attribution_results.items():
            report_lines.append(self.engine.generate_attribution_report(result))
            report_lines.append("")

        # Add risk attribution if available
        if self.risk_attribution:
            report_lines.append("RISK ATTRIBUTION ANALYSIS")
            report_lines.append("-" * 40)
            report_lines.append(
                f"Portfolio Volatility: {self.risk_attribution['portfolio_volatility']:.4f}"
            )
            report_lines.append(
                f"Diversification Ratio: {self.risk_attribution['diversification_ratio']:.3f}"
            )
            report_lines.append("")

            report_lines.append("Component Risk Contributions:")
            for security, contribution in self.risk_attribution[
                "percentage_contributions"
            ].items():
                report_lines.append(f"  {security:15} {contribution:8.4f}")
            report_lines.append("")

        # Display report
        self.report_text.delete("1.0", tk.END)
        self.report_text.insert("1.0", "\n".join(report_lines))

    def export_report(self):
        """Export report to file."""
        if not self.report_text.get("1.0", tk.END).strip():
            messagebox.showwarning(
                "Warning", "No report to export. Generate a report first."
            )
            return

        filename = filedialog.asksaveasfilename(
            title="Export Attribution Report",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )

        if filename:
            try:
                with open(filename, "w") as f:
                    f.write(self.report_text.get("1.0", tk.END))
                messagebox.showinfo("Success", f"Report exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export report: {str(e)}")

    # Plotting functions
    def plot_sector_attribution(self):
        """Plot sector attribution chart."""
        if not PLOTTING_AVAILABLE or "sector" not in self.attribution_results:
            return

        for widget in self.sector_chart_frame.winfo_children():
            widget.destroy()

        result = self.attribution_results["sector"]

        fig, ax = plt.subplots(figsize=(10, 6))

        sectors = list(result.attribution_breakdown.keys())
        allocations = [
            result.attribution_breakdown[s].get("allocation", 0) * 100 for s in sectors
        ]
        selections = [
            result.attribution_breakdown[s].get("selection", 0) * 100 for s in sectors
        ]

        x = np.arange(len(sectors))
        width = 0.35

        ax.bar(
            x - width / 2,
            allocations,
            width,
            color=ui_tokens.CHART["series"],
            label="Allocation Effect",
            alpha=0.8,
        )
        ax.bar(
            x + width / 2,
            selections,
            width,
            color=ui_tokens.CHART["series2"],
            label="Selection Effect",
            alpha=0.8,
        )

        ax.set_xlabel("Sector")
        ax.set_ylabel("Attribution (%)")
        ax.set_title("Sector Attribution Analysis")
        ax.set_xticks(x)
        ax.set_xticklabels(sectors, rotation=45)
        ax.legend()
        ax.grid(True, alpha=0.3)
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.sector_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_allocation_selection(self):
        """Plot allocation vs selection scatter."""
        if not PLOTTING_AVAILABLE or "sector" not in self.attribution_results:
            return

        for widget in self.sector_chart_frame.winfo_children():
            widget.destroy()

        result = self.attribution_results["sector"]

        fig, ax = plt.subplots(figsize=(8, 6))

        allocations = [
            result.attribution_breakdown[s].get("allocation", 0) * 100
            for s in result.attribution_breakdown.keys()
        ]
        selections = [
            result.attribution_breakdown[s].get("selection", 0) * 100
            for s in result.attribution_breakdown.keys()
        ]
        sectors = list(result.attribution_breakdown.keys())

        scatter = ax.scatter(
            allocations, selections, alpha=0.7, s=100, color=ui_tokens.CHART["series"]
        )

        for i, sector in enumerate(sectors):
            ax.annotate(
                sector,
                (allocations[i], selections[i]),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=9,
            )

        ax.axhline(y=0, color=ui_tokens.CHART["text"], linestyle="--", alpha=0.5)
        ax.axvline(x=0, color=ui_tokens.CHART["text"], linestyle="--", alpha=0.5)
        ax.set_xlabel("Allocation Effect (%)")
        ax.set_ylabel("Selection Effect (%)")
        ax.set_title("Allocation vs Selection Effects")
        ax.grid(True, alpha=0.3)
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.sector_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_factor_attribution(self):
        """Plot factor attribution chart."""
        if not PLOTTING_AVAILABLE or "factor" not in self.attribution_results:
            return

        for widget in self.factor_chart_frame.winfo_children():
            widget.destroy()

        result = self.attribution_results["factor"]

        fig, ax = plt.subplots(figsize=(10, 6))

        factors = list(result.attribution_breakdown.keys())
        contributions = [result.attribution_breakdown[f] * 100 for f in factors]

        colors = [
            ui_tokens.STATUS["bad"] if c < 0 else ui_tokens.STATUS["good"]
            for c in contributions
        ]

        bars = ax.bar(factors, contributions, color=colors, alpha=0.7)

        ax.set_ylabel("Contribution (%)")
        ax.set_title("Factor Attribution Analysis")
        ax.tick_params(axis="x", rotation=45)
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color=ui_tokens.CHART["text"], linewidth=0.8)
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.factor_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def plot_risk_attribution(self):
        """Plot risk attribution chart."""
        if not PLOTTING_AVAILABLE or not self.risk_attribution:
            return

        for widget in self.risk_chart_frame.winfo_children():
            widget.destroy()

        fig, ax = plt.subplots(figsize=(10, 6))

        securities = list(self.risk_attribution["percentage_contributions"].keys())
        contributions = [
            self.risk_attribution["percentage_contributions"][s] for s in securities
        ]

        bars = ax.bar(
            securities, contributions, color=ui_tokens.CHART["series"], alpha=0.7
        )

        ax.set_ylabel("Risk Contribution")
        ax.set_title("Risk Attribution by Security")
        ax.tick_params(axis="x", rotation=45)
        ax.grid(True, alpha=0.3)
        ui_theme.theme_figure(fig)

        canvas = FigureCanvasTkAgg(fig, self.risk_chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # Helper methods
    def _dataframe_to_holdings(self, df):
        """Convert DataFrame to Holdings list."""
        holdings = []

        for _, row in df.iterrows():
            security = row.get("security", row.get("Security", ""))
            weight = float(row.get("weight", row.get("Weight", 0.0)))
            return_period = float(row.get("return", row.get("Return", 0.0)))
            sector = row.get("sector", row.get("Sector", None))

            holding = Holding(security, weight, return_period, sector)
            holdings.append(holding)

        return holdings

    # Placeholder methods for add/edit/remove functionality
    def add_portfolio_holding(self):
        """Add new portfolio holding."""
        # Placeholder - would open dialog for adding holdings
        messagebox.showinfo("Info", "Add holding functionality - to be implemented")

    def edit_portfolio_holding(self):
        """Edit selected portfolio holding."""
        messagebox.showinfo("Info", "Edit holding functionality - to be implemented")

    def remove_portfolio_holding(self):
        """Remove selected portfolio holding."""
        messagebox.showinfo("Info", "Remove holding functionality - to be implemented")

    def add_benchmark_holding(self):
        """Add new benchmark holding."""
        messagebox.showinfo("Info", "Add holding functionality - to be implemented")

    def edit_benchmark_holding(self):
        """Edit selected benchmark holding."""
        messagebox.showinfo("Info", "Edit holding functionality - to be implemented")

    def remove_benchmark_holding(self):
        """Remove selected benchmark holding."""
        messagebox.showinfo("Info", "Remove holding functionality - to be implemented")


def main():
    """Run the Performance Attribution GUI."""
    root = ui_theme.themed_root()
    app = PerformanceAttributionGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
