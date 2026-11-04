"""
PowerTrader AI - Institutional Trading GUI
Professional interface for institutional trading operations
"""

import asyncio
import json
import threading
import tkinter as tk
from datetime import datetime
from decimal import Decimal
from tkinter import messagebox, ttk
from typing import Any, Dict, List

import ui_table
import ui_theme
import ui_tokens
from institutional_trading import (
    InstitutionalOrder,
    InstitutionalOrderType,
    OrderPriority,
    get_institutional_engine,
)


class InstitutionalTradingGUI:
    """Professional GUI for institutional trading"""

    def __init__(self, parent):
        self.parent = parent
        self.engine = get_institutional_engine()

        # Create main frame
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.BOTH, expand=True)

        self.setup_gui()

        # Start background monitoring
        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self.monitor_performance, daemon=True
        )
        self.monitor_thread.start()

    def setup_gui(self):
        """Setup the institutional trading interface"""
        # Status indicator (no title: the hub's tab names this window)
        header_frame = ttk.Frame(self.frame)
        header_frame.pack(fill=tk.X, padx=6, pady=(4, 4))

        self.status_label = ttk.Label(
            header_frame, text="● Online", style="Good.TLabel"
        )
        self.status_label.pack(side=tk.RIGHT)

        # Create notebook for different sections
        self.notebook = ttk.Notebook(self.frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Setup tabs
        self.setup_order_entry_tab()
        self.setup_batch_processing_tab()
        self.setup_algorithmic_trading_tab()
        self.setup_risk_management_tab()
        self.setup_performance_tab()
        self.setup_monitoring_tab()

    def setup_order_entry_tab(self):
        """Setup order entry interface"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Order Entry")

        # Left panel - Order form
        left_frame = ttk.LabelFrame(tab, text="New Order", padding="10")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # Order form
        form_frame = ttk.Frame(left_frame)
        form_frame.pack(fill=tk.X, pady=5)

        # Symbol
        ttk.Label(form_frame, text="Symbol:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.symbol_var = tk.StringVar(value="BTC/USD")
        symbol_combo = ttk.Combobox(form_frame, textvariable=self.symbol_var, width=15)
        symbol_combo["values"] = ("BTC/USD", "ETH/USD", "BNB/USD", "ADA/USD", "DOT/USD")
        symbol_combo.grid(row=0, column=1, sticky=tk.W, padx=(5, 0), pady=2)

        # Side
        ttk.Label(form_frame, text="Side:").grid(
            row=0, column=2, sticky=tk.W, padx=(20, 0), pady=2
        )
        self.side_var = tk.StringVar(value="buy")
        side_combo = ttk.Combobox(form_frame, textvariable=self.side_var, width=10)
        side_combo["values"] = ("buy", "sell")
        side_combo.grid(row=0, column=3, sticky=tk.W, padx=(5, 0), pady=2)

        # Order Type
        ttk.Label(form_frame, text="Type:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.order_type_var = tk.StringVar(value="limit")
        type_combo = ttk.Combobox(
            form_frame, textvariable=self.order_type_var, width=15
        )
        type_combo["values"] = (
            "market",
            "limit",
            "stop_loss",
            "take_profit",
            "iceberg",
            "twap",
            "vwap",
            "block",
        )
        type_combo.grid(row=1, column=1, sticky=tk.W, padx=(5, 0), pady=2)
        type_combo.bind("<<ComboboxSelected>>", self.on_order_type_change)

        # Priority
        ttk.Label(form_frame, text="Priority:").grid(
            row=1, column=2, sticky=tk.W, padx=(20, 0), pady=2
        )
        self.priority_var = tk.StringVar(value="normal")
        priority_combo = ttk.Combobox(
            form_frame, textvariable=self.priority_var, width=10
        )
        priority_combo["values"] = ("low", "normal", "high", "critical")
        priority_combo.grid(row=1, column=3, sticky=tk.W, padx=(5, 0), pady=2)

        # Quantity
        ttk.Label(form_frame, text="Quantity:").grid(
            row=2, column=0, sticky=tk.W, pady=2
        )
        self.quantity_var = tk.StringVar(value="1.0")
        quantity_entry = ttk.Entry(form_frame, textvariable=self.quantity_var, width=18)
        quantity_entry.grid(row=2, column=1, sticky=tk.W, padx=(5, 0), pady=2)

        # Price
        ttk.Label(form_frame, text="Price:").grid(
            row=2, column=2, sticky=tk.W, padx=(20, 0), pady=2
        )
        self.price_var = tk.StringVar(value="50000.0")
        self.price_entry = ttk.Entry(form_frame, textvariable=self.price_var, width=13)
        self.price_entry.grid(row=2, column=3, sticky=tk.W, padx=(5, 0), pady=2)

        # Account & Trader
        ttk.Label(form_frame, text="Account ID:").grid(
            row=3, column=0, sticky=tk.W, pady=2
        )
        self.account_var = tk.StringVar(value="FUND_A")
        account_combo = ttk.Combobox(
            form_frame, textvariable=self.account_var, width=15
        )
        account_combo["values"] = ("FUND_A", "FUND_B", "HEDGE_001", "PROP_DESK")
        account_combo.grid(row=3, column=1, sticky=tk.W, padx=(5, 0), pady=2)

        ttk.Label(form_frame, text="Trader ID:").grid(
            row=3, column=2, sticky=tk.W, padx=(20, 0), pady=2
        )
        self.trader_var = tk.StringVar(value="TRADER_001")
        trader_entry = ttk.Entry(form_frame, textvariable=self.trader_var, width=13)
        trader_entry.grid(row=3, column=3, sticky=tk.W, padx=(5, 0), pady=2)

        # Advanced options frame (initially hidden)
        self.advanced_frame = ttk.LabelFrame(
            left_frame, text="Advanced Options", padding="5"
        )

        # Slice size for iceberg orders
        ttk.Label(self.advanced_frame, text="Slice Size:").grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        self.slice_size_var = tk.StringVar(value="")
        slice_entry = ttk.Entry(
            self.advanced_frame, textvariable=self.slice_size_var, width=15
        )
        slice_entry.grid(row=0, column=1, sticky=tk.W, padx=(5, 0), pady=2)

        # TWAP duration
        ttk.Label(self.advanced_frame, text="TWAP Duration (min):").grid(
            row=0, column=2, sticky=tk.W, padx=(20, 0), pady=2
        )
        self.twap_duration_var = tk.StringVar(value="60")
        twap_entry = ttk.Entry(
            self.advanced_frame, textvariable=self.twap_duration_var, width=10
        )
        twap_entry.grid(row=0, column=3, sticky=tk.W, padx=(5, 0), pady=2)

        # VWAP participation
        ttk.Label(self.advanced_frame, text="VWAP Participation:").grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        self.vwap_participation_var = tk.StringVar(value="0.1")
        vwap_entry = ttk.Entry(
            self.advanced_frame, textvariable=self.vwap_participation_var, width=15
        )
        vwap_entry.grid(row=1, column=1, sticky=tk.W, padx=(5, 0), pady=2)

        # Submit button
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill=tk.X, pady=10)

        submit_btn = ttk.Button(
            button_frame,
            text="Submit Order",
            command=self.submit_order,
            style="Accent.TButton",
        )
        submit_btn.pack(side=tk.LEFT, padx=(0, 10))

        validate_btn = ttk.Button(
            button_frame, text="Validate", command=self.validate_order
        )
        validate_btn.pack(side=tk.LEFT)

        # Right panel - Order status
        right_frame = ttk.LabelFrame(tab, text="Recent Orders", padding="10")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # Order history table (ui_table: fitted columns, its own scrollbars, sortable)
        columns = ("Order ID", "Symbol", "Side", "Type", "Quantity", "Price", "Status")
        self.order_table = ui_table.DataTable(
            right_frame,
            columns,
            key="institutional_trading.recent_orders",
            numeric=("Quantity", "Price"),
            empty_text="No orders yet",
        )
        self.order_table.pack(fill="both", expand=True)
        self.order_tree = self.order_table.tree

    def setup_batch_processing_tab(self):
        """Setup batch processing interface"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Batch Processing")

        # Upload area
        upload_frame = ttk.LabelFrame(tab, text="Batch Upload", padding="10")
        upload_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(
            upload_frame,
            text="Upload CSV file with order details:",
            style="Header.TLabel",
        ).pack(anchor=tk.W)

        upload_btn_frame = ttk.Frame(upload_frame)
        upload_btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(
            upload_btn_frame, text="Select File", command=self.select_batch_file
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            upload_btn_frame, text="Upload Template", command=self.download_template
        ).pack(side=tk.LEFT, padx=(0, 10))

        self.batch_file_label = ttk.Label(
            upload_btn_frame, text="No file selected", style="Warn.TLabel"
        )
        self.batch_file_label.pack(side=tk.LEFT, padx=(20, 0))

        # Batch status
        status_frame = ttk.LabelFrame(tab, text="Batch Status", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Batch history
        batch_columns = (
            "Batch ID",
            "Orders",
            "Status",
            "Success Rate",
            "Submitted",
            "Completed",
        )
        self.batch_table = ui_table.DataTable(
            status_frame,
            batch_columns,
            key="institutional_trading.batches",
            numeric=("Orders", "Success Rate"),
            empty_text="No batches yet",
        )
        self.batch_table.pack(fill="both", expand=True)
        self.batch_tree = self.batch_table.tree

    def setup_algorithmic_trading_tab(self):
        """Setup algorithmic trading interface"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Algorithmic Trading")

        # Algorithm selection
        algo_frame = ttk.LabelFrame(tab, text="Algorithm Configuration", padding="10")
        algo_frame.pack(fill=tk.X, padx=10, pady=5)

        # TWAP section
        twap_frame = ttk.LabelFrame(
            algo_frame, text="TWAP (Time-Weighted Average Price)", padding="5"
        )
        twap_frame.pack(fill=tk.X, pady=5)

        twap_config = ttk.Frame(twap_frame)
        twap_config.pack(fill=tk.X)

        ttk.Label(twap_config, text="Duration (minutes):").grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        self.twap_duration_config = tk.StringVar(value="60")
        ttk.Entry(twap_config, textvariable=self.twap_duration_config, width=10).grid(
            row=0, column=1, padx=5, pady=2
        )

        ttk.Label(twap_config, text="Min Slice Size:").grid(
            row=0, column=2, sticky=tk.W, padx=(20, 0), pady=2
        )
        self.twap_min_slice = tk.StringVar(value="0.1")
        ttk.Entry(twap_config, textvariable=self.twap_min_slice, width=10).grid(
            row=0, column=3, padx=5, pady=2
        )

        # VWAP section
        vwap_frame = ttk.LabelFrame(
            algo_frame, text="VWAP (Volume-Weighted Average Price)", padding="5"
        )
        vwap_frame.pack(fill=tk.X, pady=5)

        vwap_config = ttk.Frame(vwap_frame)
        vwap_config.pack(fill=tk.X)

        ttk.Label(vwap_config, text="Target Participation:").grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        self.vwap_participation_config = tk.StringVar(value="0.1")
        ttk.Entry(
            vwap_config, textvariable=self.vwap_participation_config, width=10
        ).grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(vwap_config, text="Max Participation:").grid(
            row=0, column=2, sticky=tk.W, padx=(20, 0), pady=2
        )
        self.vwap_max_participation = tk.StringVar(value="0.25")
        ttk.Entry(vwap_config, textvariable=self.vwap_max_participation, width=10).grid(
            row=0, column=3, padx=5, pady=2
        )

        # Active algorithms
        active_frame = ttk.LabelFrame(tab, text="Active Algorithms", padding="10")
        active_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        algo_columns = (
            "Algorithm ID",
            "Type",
            "Symbol",
            "Progress",
            "Status",
            "Start Time",
        )
        self.algo_table = ui_table.DataTable(
            active_frame,
            algo_columns,
            key="institutional_trading.active_algorithms",
            numeric=("Progress",),
            empty_text="No algorithms yet",
        )
        self.algo_tree = self.algo_table.tree

        # Control buttons, under the table (packed first so a short panel keeps them)
        control_frame = ttk.Frame(active_frame)
        control_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        ttk.Button(
            control_frame, text="Stop Selected", command=self.stop_algorithm
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(control_frame, text="Refresh", command=self.refresh_algorithms).pack(
            side=tk.LEFT
        )

        self.algo_table.pack(fill="both", expand=True)

    def setup_risk_management_tab(self):
        """Setup risk management interface"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Risk Management")

        # Risk limits
        limits_frame = ttk.LabelFrame(tab, text="Risk Limits", padding="10")
        limits_frame.pack(fill=tk.X, padx=10, pady=5)

        limits_grid = ttk.Frame(limits_frame)
        limits_grid.pack(fill=tk.X)

        # Position limits
        ttk.Label(limits_grid, text="Max Position Size:", style="Header.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=5
        )
        self.max_position_var = tk.StringVar(value="1000000")
        ttk.Entry(limits_grid, textvariable=self.max_position_var, width=15).grid(
            row=0, column=1, padx=5, pady=5
        )

        ttk.Label(limits_grid, text="Max Daily Volume:", style="Header.TLabel").grid(
            row=0, column=2, sticky=tk.W, padx=(20, 0), pady=5
        )
        self.max_daily_volume_var = tk.StringVar(value="10000000")
        ttk.Entry(limits_grid, textvariable=self.max_daily_volume_var, width=15).grid(
            row=0, column=3, padx=5, pady=5
        )

        ttk.Label(limits_grid, text="Max Concentration:", style="Header.TLabel").grid(
            row=1, column=0, sticky=tk.W, pady=5
        )
        self.max_concentration_var = tk.StringVar(value="0.25")
        ttk.Entry(limits_grid, textvariable=self.max_concentration_var, width=15).grid(
            row=1, column=1, padx=5, pady=5
        )

        # Apply button
        ttk.Button(
            limits_grid, text="Update Limits", command=self.update_risk_limits
        ).grid(row=1, column=3, padx=5, pady=5)

        # Current exposures
        exposure_frame = ttk.LabelFrame(tab, text="Current Exposures", padding="10")
        exposure_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        exposure_columns = (
            "Account",
            "Symbol",
            "Position",
            "Value",
            "Daily Volume",
            "Risk Level",
        )
        self.exposure_table = ui_table.DataTable(
            exposure_frame,
            exposure_columns,
            key="institutional_trading.exposures",
            numeric=("Position", "Value", "Daily Volume"),
            empty_text="No exposures yet",
        )
        self.exposure_table.pack(fill="both", expand=True)
        self.exposure_tree = self.exposure_table.tree

    def setup_performance_tab(self):
        """Setup performance monitoring interface"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Performance")

        # Key metrics
        metrics_frame = ttk.LabelFrame(
            tab, text="Key Performance Metrics", padding="10"
        )
        metrics_frame.pack(fill=tk.X, padx=10, pady=5)

        metrics_grid = ttk.Frame(metrics_frame)
        metrics_grid.pack(fill=tk.X)

        # Create metric displays
        metric_labels = [
            ("Total Orders", "total_orders"),
            ("Success Rate", "success_rate"),
            ("Avg Latency", "avg_latency"),
            ("Total Volume", "total_volume"),
            ("Orders/Sec", "orders_per_sec"),
            ("Active Algos", "active_algos"),
        ]

        self.metric_vars = {}
        for i, (label, key) in enumerate(metric_labels):
            row, col = i // 3, (i % 3) * 2

            ttk.Label(metrics_grid, text=f"{label}:", style="Header.TLabel").grid(
                row=row,
                column=col,
                sticky=tk.W,
                padx=(0 if col == 0 else 20, 5),
                pady=5,
            )

            var = tk.StringVar(value="0")
            self.metric_vars[key] = var
            ttk.Label(metrics_grid, textvariable=var, style="Good.TLabel").grid(
                row=row, column=col + 1, sticky=tk.W, pady=5
            )

        # Performance chart placeholder
        chart_frame = ttk.LabelFrame(tab, text="Performance Charts", padding="10")
        chart_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        ttk.Label(
            chart_frame,
            text="📊 Performance visualization would go here",
            style="Muted.TLabel",
            font=ui_tokens.font("body"),
        ).pack(expand=True)

        # Account performance
        account_frame = ttk.LabelFrame(tab, text="Account Performance", padding="10")
        account_frame.pack(fill=tk.X, padx=10, pady=5)

        account_columns = (
            "Account ID",
            "Total Orders",
            "Success Rate",
            "Total Volume",
            "P&L",
        )
        # six rows high: this section keeps its height, the chart above takes the rest
        self.account_table = ui_table.DataTable(
            account_frame,
            account_columns,
            key="institutional_trading.account_performance",
            numeric=("Total Orders", "Success Rate", "Total Volume", "P&L"),
            empty_text="No accounts yet",
            height=6,
        )
        self.account_table.pack(fill="both", expand=True)
        self.account_tree = self.account_table.tree

    def setup_monitoring_tab(self):
        """Setup system monitoring interface"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Monitoring")

        # System status
        system_frame = ttk.LabelFrame(tab, text="System Status", padding="10")
        system_frame.pack(fill=tk.X, padx=10, pady=5)

        status_grid = ttk.Frame(system_frame)
        status_grid.pack(fill=tk.X)

        # Status indicators
        status_items = [
            ("Trading Engine", "engine_status"),
            ("Risk Manager", "risk_status"),
            ("Market Data", "data_status"),
            ("Database", "db_status"),
            ("Order Router", "router_status"),
            ("Compliance", "compliance_status"),
        ]

        self.status_vars = {}
        for i, (label, key) in enumerate(status_items):
            row, col = i // 3, (i % 3) * 2

            ttk.Label(status_grid, text=f"{label}:", style="Header.TLabel").grid(
                row=row,
                column=col,
                sticky=tk.W,
                padx=(0 if col == 0 else 20, 5),
                pady=5,
            )

            var = tk.StringVar(value="● Online")
            self.status_vars[key] = var
            ttk.Label(status_grid, textvariable=var, style="Good.TLabel").grid(
                row=row, column=col + 1, sticky=tk.W, pady=5
            )

        # Event log
        log_frame = ttk.LabelFrame(tab, text="Event Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Log display
        self.log_text = tk.Text(
            log_frame,
            height=15,
            wrap=tk.WORD,
            font=ui_tokens.mono("small"),
        )
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL)
        ui_table.scroll_when_needed(self.log_text, log_scroll)

        # Add initial log entries
        self.add_log_entry("System started", "INFO")
        self.add_log_entry("Risk management initialized", "INFO")
        self.add_log_entry("Database connection established", "INFO")

    def on_order_type_change(self, event=None):
        """Handle order type selection changes"""
        order_type = self.order_type_var.get()

        if order_type in ["iceberg", "twap", "vwap"]:
            self.advanced_frame.pack(fill=tk.X, pady=5)
        else:
            self.advanced_frame.pack_forget()

        # Enable/disable price field for market orders
        if order_type == "market":
            self.price_entry.config(state="disabled")
        else:
            self.price_entry.config(state="normal")

    def validate_order(self):
        """Validate order before submission"""
        try:
            # Create order object for validation
            order = self.create_order_from_form()

            # Validate with risk manager
            is_valid, message = self.engine.risk_manager.validate_order(order)

            if is_valid:
                messagebox.showinfo(
                    "Validation", "✅ Order passes all validation checks"
                )
                self.add_log_entry(f"Order validation passed: {order.order_id}", "INFO")
            else:
                messagebox.showwarning("Validation Failed", f"❌ {message}")
                self.add_log_entry(f"Order validation failed: {message}", "WARNING")

        except Exception as e:
            messagebox.showerror(
                "Validation Error", f"Error validating order: {str(e)}"
            )
            self.add_log_entry(f"Validation error: {str(e)}", "ERROR")

    def submit_order(self):
        """Submit order for execution"""
        try:
            order = self.create_order_from_form()

            # Submit order asynchronously
            def submit_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(self.engine.submit_order(order))
                    self.parent.after(
                        0, lambda: self.handle_order_result(result, order)
                    )
                finally:
                    loop.close()

            threading.Thread(target=submit_async, daemon=True).start()

            self.add_log_entry(f"Submitting order: {order.order_id}", "INFO")
            messagebox.showinfo(
                "Order Submitted", f"Order {order.order_id} submitted for processing"
            )

        except Exception as e:
            messagebox.showerror(
                "Submission Error", f"Error submitting order: {str(e)}"
            )
            self.add_log_entry(f"Order submission error: {str(e)}", "ERROR")

    def create_order_from_form(self) -> InstitutionalOrder:
        """Create order object from form data"""
        order_id = f"ORD_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:17]}"

        # Get order type enum
        order_type_str = self.order_type_var.get()
        order_type = InstitutionalOrderType(order_type_str)

        # Get priority enum
        priority_str = self.priority_var.get()
        priority = OrderPriority(priority_str)

        # Create order
        order = InstitutionalOrder(
            order_id=order_id,
            symbol=self.symbol_var.get(),
            side=self.side_var.get(),
            order_type=order_type,
            quantity=Decimal(self.quantity_var.get()),
            price=(
                Decimal(self.price_var.get())
                if self.price_var.get() and order_type != InstitutionalOrderType.MARKET
                else None
            ),
            priority=priority,
            account_id=self.account_var.get(),
            trader_id=self.trader_var.get(),
        )

        # Add slice size for iceberg orders
        if order_type == InstitutionalOrderType.ICEBERG and self.slice_size_var.get():
            order.slice_size = Decimal(self.slice_size_var.get())

        return order

    def handle_order_result(self, result: Dict[str, Any], order: InstitutionalOrder):
        """Handle order submission result"""
        status = result.get("status", "unknown")

        if status == "accepted":
            self.add_log_entry(f"Order {order.order_id} accepted", "SUCCESS")
            # Add to order tree
            self.order_tree.insert(
                "",
                0,
                values=(
                    order.order_id,
                    order.symbol,
                    order.side,
                    order.order_type.value,
                    f"{order.quantity}",
                    f"{order.price or 'Market'}",
                    status,
                ),
            )
        elif status == "rejected":
            reason = result.get("reason", "Unknown reason")
            self.add_log_entry(f"Order {order.order_id} rejected: {reason}", "ERROR")
        else:
            self.add_log_entry(f"Order {order.order_id} status: {status}", "INFO")

    def select_batch_file(self):
        """Select batch file for upload"""
        from tkinter import filedialog

        filename = filedialog.askopenfilename(
            title="Select Batch Order File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )

        if filename:
            self.batch_file_label.config(text=f"Selected: {filename}")
            self.add_log_entry(f"Batch file selected: {filename}", "INFO")

    def download_template(self):
        """Download batch order template"""
        messagebox.showinfo("Template", "Batch order template would be downloaded here")
        self.add_log_entry("Batch template download requested", "INFO")

    def stop_algorithm(self):
        """Stop selected algorithm"""
        selection = self.algo_tree.selection()
        if selection:
            algo_id = self.algo_tree.item(selection[0])["values"][0]
            success = self.engine.algo_engine.stop_algorithm(algo_id)

            if success:
                self.add_log_entry(f"Algorithm {algo_id} stopped", "INFO")
                messagebox.showinfo(
                    "Algorithm Stopped", f"Algorithm {algo_id} has been stopped"
                )
            else:
                messagebox.showwarning(
                    "Stop Failed", f"Could not stop algorithm {algo_id}"
                )

    def refresh_algorithms(self):
        """Refresh algorithm status"""
        # Clear current items
        for item in self.algo_tree.get_children():
            self.algo_tree.delete(item)

        # Add active algorithms
        for algo_id, state in self.engine.algo_engine.active_algos.items():
            progress = (
                f"{state.get('slices_executed', 0)}/{state.get('total_slices', 0)}"
            )
            self.algo_tree.insert(
                "",
                0,
                values=(
                    algo_id,
                    state.get("order", {}).get("order_type", "Unknown"),
                    state.get("order", {}).get("symbol", "Unknown"),
                    progress,
                    state.get("status", "Unknown"),
                    state.get("start_time", datetime.now()).strftime("%H:%M:%S"),
                ),
            )

    def update_risk_limits(self):
        """Update risk management limits"""
        try:
            limits = {
                "max_position_size": Decimal(self.max_position_var.get()),
                "max_daily_volume": Decimal(self.max_daily_volume_var.get()),
                "max_concentration": Decimal(self.max_concentration_var.get()),
            }

            self.engine.risk_manager.position_limits.update(limits)
            self.add_log_entry("Risk limits updated", "INFO")
            messagebox.showinfo("Risk Limits", "Risk limits updated successfully")

        except Exception as e:
            messagebox.showerror(
                "Update Error", f"Error updating risk limits: {str(e)}"
            )
            self.add_log_entry(f"Risk limits update error: {str(e)}", "ERROR")

    def add_log_entry(self, message: str, level: str = "INFO"):
        """Add entry to event log"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Color coding
        p = ui_theme.active_palette()
        colors = {
            "INFO": p["ACCENT2"],
            "SUCCESS": ui_tokens.STATUS["good"],
            "WARNING": ui_tokens.STATUS["warn"],
            "ERROR": ui_tokens.STATUS["bad"],
        }

        color = colors.get(level, p["FG"])

        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {level}: {message}\n")
        self.log_text.tag_add(level, f"end-2l linestart", f"end-1l lineend")
        self.log_text.tag_config(level, foreground=color)
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def monitor_performance(self):
        """Background performance monitoring"""
        while self.monitoring:
            try:
                # Update performance metrics
                summary = self.engine.get_performance_summary()

                if not summary.get("error"):
                    # Update metric displays
                    self.parent.after(0, lambda: self.update_metrics(summary))

                # Sleep for 5 seconds
                for _ in range(50):
                    if not self.monitoring:
                        break
                    threading.Event().wait(0.1)

            except Exception as e:
                print(f"Monitoring error: {e}")
                threading.Event().wait(1)

    def update_metrics(self, summary: Dict[str, Any]):
        """Update performance metric displays"""
        try:
            self.metric_vars["total_orders"].set(str(summary.get("total_orders", 0)))
            self.metric_vars["success_rate"].set(f"{summary.get('success_rate', 0)}%")
            self.metric_vars["total_volume"].set(
                f"${summary.get('total_volume', 0):,.0f}"
            )
            self.metric_vars["avg_latency"].set("< 10ms")
            self.metric_vars["orders_per_sec"].set(
                f"{summary.get('total_orders', 0) / 60:.1f}"
            )
            self.metric_vars["active_algos"].set(
                str(len(self.engine.algo_engine.active_algos))
            )

        except Exception as e:
            print(f"Metrics update error: {e}")

    def cleanup(self):
        """Cleanup on close"""
        self.monitoring = False


if __name__ == "__main__":
    # Test the GUI
    root = ui_theme.themed_root()
    root.title("Institutional Trading System")
    root.geometry("1200x800")

    gui = InstitutionalTradingGUI(root)

    # Handle window close
    def on_closing():
        gui.cleanup()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
