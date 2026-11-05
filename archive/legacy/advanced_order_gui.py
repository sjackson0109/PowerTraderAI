"""
Advanced Order Types GUI (Item 23)
User interface for creating and managing advanced order types
"""

import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Dict, List, Optional

import ui_table
import ui_theme
import ui_tokens

try:
    from advanced_order_automation import (
        AdvancedOrder,
        AdvancedOrderType,
        AutomationTrigger,
        BracketOrder,
        ConditionType,
        OCOOrder,
        OrderCondition,
        get_automation_engine,
    )
    from order_management_models import OrderSide, OrderStatus

    AUTOMATION_AVAILABLE = True
except ImportError:
    AUTOMATION_AVAILABLE = False
    print("Warning: Advanced order automation not available.")


class AdvancedOrderGUI:
    """GUI for advanced order types and automation"""

    def __init__(self, parent: tk.Widget):
        self.parent = parent
        self.automation_engine = None

        # Initialize automation engine if available
        if AUTOMATION_AVAILABLE:
            try:
                self.automation_engine = get_automation_engine()
                self.automation_engine.order_update_callback = self.on_order_update
                self.automation_engine.execution_callback = self.on_order_execution
                self.automation_engine.start()
            except Exception as e:
                print(f"Error initializing automation engine: {e}")

        self.setup_ui()
        self.refresh_orders()

    def setup_ui(self):
        """Setup the user interface"""
        self.main_frame = ttk.Frame(self.parent)
        self.main_frame.pack(fill="both", expand=True)

        if not AUTOMATION_AVAILABLE:
            self.setup_fallback_ui()
            return

        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill="both", expand=True)

        # Order Creation Tab
        self.creation_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.creation_tab, text="Create Orders")
        self.setup_creation_tab()

        # Active Orders Tab
        self.orders_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.orders_tab, text="Active Orders")
        self.setup_orders_tab()

        # Automation Rules Tab
        self.automation_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.automation_tab, text="Automation Rules")
        self.setup_automation_tab()

        # Order History Tab
        self.history_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.history_tab, text="Order History")
        self.setup_history_tab()

    def setup_fallback_ui(self):
        """Setup fallback UI when automation is not available"""
        frame = ttk.Frame(self.main_frame)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ttk.Label(
            frame,
            text="Advanced Order Types & Automation",
            font=ui_tokens.font("display", "bold"),
        ).pack(pady=20)

        ttk.Label(
            frame,
            text="⚠️ Advanced order automation not available",
            style="Warn.TLabel",
            font=ui_tokens.font("title"),
        ).pack(pady=10)

        ttk.Label(
            frame,
            text="Required for advanced order types:",
            font=ui_tokens.font("body", "bold"),
        ).pack(pady=5)

        deps = [
            "Advanced order automation module",
            "Order management models",
            "Threading support",
        ]
        for dep in deps:
            ttk.Label(frame, text=f"• {dep}", style="Bad.TLabel").pack()

        ttk.Label(
            frame,
            text="Install missing dependencies to enable advanced order features",
            style="Muted.TLabel",
            font=ui_tokens.font("body"),
        ).pack(pady=10)

    def setup_creation_tab(self):
        """Setup order creation tab"""
        p = ui_theme.active_palette()
        # Create scrollable frame
        canvas = tk.Canvas(self.creation_tab, bg=p["BG"])
        scrollbar = ttk.Scrollbar(
            self.creation_tab, orient="vertical", command=canvas.yview
        )
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        # Order type selection
        type_frame = ttk.LabelFrame(scrollable_frame, text="Order Type")
        type_frame.pack(fill="x", padx=10, pady=5)

        self.order_type_var = tk.StringVar(value=AdvancedOrderType.OCO.value)

        order_types = [
            ("One Cancels Other (OCO)", AdvancedOrderType.OCO.value),
            ("Trailing Stop", AdvancedOrderType.TRAILING_STOP.value),
            ("Iceberg Order", AdvancedOrderType.ICEBERG.value),
            ("Bracket Order", AdvancedOrderType.BRACKET.value),
            ("Conditional Order", AdvancedOrderType.CONDITIONAL.value),
            ("TWAP", AdvancedOrderType.TWAP.value),
            ("VWAP", AdvancedOrderType.VWAP.value),
        ]

        for i, (display_name, value) in enumerate(order_types):
            row = i // 2
            col = i % 2
            ttk.Radiobutton(
                type_frame,
                text=display_name,
                variable=self.order_type_var,
                value=value,
                command=self.on_order_type_changed,
            ).grid(row=row, column=col, sticky="w", padx=10, pady=2)

        # Dynamic configuration frame
        self.config_frame = ttk.LabelFrame(scrollable_frame, text="Order Configuration")
        self.config_frame.pack(fill="x", padx=10, pady=5)

        # Control buttons
        button_frame = ttk.Frame(scrollable_frame)
        button_frame.pack(fill="x", padx=10, pady=10)

        ttk.Button(button_frame, text="Create Order", command=self.create_order).pack(
            side="left", padx=5
        )
        ttk.Button(button_frame, text="Clear Form", command=self.clear_form).pack(
            side="left", padx=5
        )
        ttk.Button(button_frame, text="Save Template", command=self.save_template).pack(
            side="left", padx=5
        )
        ttk.Button(button_frame, text="Load Template", command=self.load_template).pack(
            side="left", padx=5
        )

        ui_table.scroll_when_needed(canvas, scrollbar)

        # Initialize with OCO configuration
        self.on_order_type_changed()

    def setup_orders_tab(self):
        """Setup active orders tab"""
        # Control frame
        control_frame = ttk.Frame(self.orders_tab)
        control_frame.pack(fill="x", padx=5, pady=5)

        ttk.Button(control_frame, text="Refresh", command=self.refresh_orders).pack(
            side="left", padx=5
        )
        ttk.Button(
            control_frame, text="Cancel Selected", command=self.cancel_selected_order
        ).pack(side="left", padx=5)
        ttk.Button(
            control_frame, text="Modify Order", command=self.modify_selected_order
        ).pack(side="left", padx=5)
        ttk.Button(
            control_frame, text="Force Execute", command=self.force_execute_order
        ).pack(side="left", padx=5)

        # Orders table (ui_table: fitted columns, its own scrollbars, sortable)
        self.orders_table = ui_table.DataTable(
            self.orders_tab,
            (
                "id",
                "type",
                "symbol",
                "side",
                "quantity",
                "price",
                "status",
                "created",
            ),
            {
                "id": "Id",
                "type": "Type",
                "symbol": "Symbol",
                "side": "Side",
                "quantity": "Quantity",
                "price": "Price",
                "status": "Status",
                "created": "Created",
            },
            key="advanced_orders.active_orders",
            numeric=("quantity", "price"),
            empty_text="No orders yet",
        )
        self.orders_table.pack(fill="both", expand=True)
        self.orders_tree = self.orders_table.tree

        # Bind selection
        self.orders_tree.bind("<<TreeviewSelect>>", self.on_order_select)

        # Order details frame
        details_frame = ttk.LabelFrame(self.orders_tab, text="Order Details")
        details_frame.pack(fill="x", padx=5, pady=5)

        self.details_text = tk.Text(details_frame, height=8, width=80)
        details_scrollbar = ttk.Scrollbar(details_frame, orient="vertical")
        ui_table.scroll_when_needed(self.details_text, details_scrollbar)

    def setup_automation_tab(self):
        """Setup automation rules tab"""
        # Rules management frame
        rules_frame = ttk.LabelFrame(self.automation_tab, text="Automation Rules")
        rules_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(
            rules_frame, text="Create Rule", command=self.create_automation_rule
        ).pack(side="left", padx=5)
        ttk.Button(
            rules_frame, text="Edit Rule", command=self.edit_automation_rule
        ).pack(side="left", padx=5)
        ttk.Button(
            rules_frame, text="Delete Rule", command=self.delete_automation_rule
        ).pack(side="left", padx=5)
        ttk.Button(
            rules_frame, text="Test Rule", command=self.test_automation_rule
        ).pack(side="left", padx=5)

        # Rules table
        self.rules_table = ui_table.DataTable(
            self.automation_tab,
            ("name", "trigger", "conditions", "status"),
            {
                "name": "Rule Name",
                "trigger": "Trigger Type",
                "conditions": "Conditions",
                "status": "Status",
            },
            key="advanced_orders.automation_rules",
            empty_text="No rules yet",
        )
        self.rules_table.pack(fill="both", expand=True)
        self.rules_tree = self.rules_table.tree

        # Rule details
        rule_details_frame = ttk.LabelFrame(self.automation_tab, text="Rule Details")
        rule_details_frame.pack(fill="x", padx=10, pady=5)

        self.rule_details_text = tk.Text(rule_details_frame, height=6, width=80)
        rule_details_scrollbar = ttk.Scrollbar(rule_details_frame, orient="vertical")
        ui_table.scroll_when_needed(self.rule_details_text, rule_details_scrollbar)

    def setup_history_tab(self):
        """Setup order history tab"""
        # Filter frame
        filter_frame = ttk.LabelFrame(self.history_tab, text="Filters")
        filter_frame.pack(fill="x", padx=10, pady=5)

        # Date range
        ttk.Label(filter_frame, text="From:").grid(row=0, column=0, padx=5, pady=2)
        self.from_date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(filter_frame, textvariable=self.from_date_var, width=12).grid(
            row=0, column=1, padx=5, pady=2
        )

        ttk.Label(filter_frame, text="To:").grid(row=0, column=2, padx=5, pady=2)
        self.to_date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(filter_frame, textvariable=self.to_date_var, width=12).grid(
            row=0, column=3, padx=5, pady=2
        )

        # Symbol filter
        ttk.Label(filter_frame, text="Symbol:").grid(row=0, column=4, padx=5, pady=2)
        self.symbol_filter_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.symbol_filter_var, width=10).grid(
            row=0, column=5, padx=5, pady=2
        )

        ttk.Button(
            filter_frame, text="Apply Filter", command=self.apply_history_filter
        ).grid(row=0, column=6, padx=10, pady=2)

        # History table
        self.history_table = ui_table.DataTable(
            self.history_tab,
            (
                "id",
                "type",
                "symbol",
                "side",
                "quantity",
                "price",
                "status",
                "created",
                "executed",
                "pnl",
            ),
            {
                "id": "Id",
                "type": "Type",
                "symbol": "Symbol",
                "side": "Side",
                "quantity": "Quantity",
                "price": "Price",
                "status": "Status",
                "created": "Created",
                "executed": "Executed",
                "pnl": "Pnl",
            },
            key="advanced_orders.order_history",
            numeric=("quantity", "price", "pnl"),
            empty_text="No order history yet",
        )
        self.history_table.pack(fill="both", expand=True)
        self.history_tree = self.history_table.tree

    def on_order_type_changed(self):
        """Handle order type selection change"""
        # Clear existing configuration
        for widget in self.config_frame.winfo_children():
            widget.destroy()

        order_type = self.order_type_var.get()

        if order_type == AdvancedOrderType.OCO.value:
            self.setup_oco_config()
        elif order_type == AdvancedOrderType.TRAILING_STOP.value:
            self.setup_trailing_stop_config()
        elif order_type == AdvancedOrderType.ICEBERG.value:
            self.setup_iceberg_config()
        elif order_type == AdvancedOrderType.BRACKET.value:
            self.setup_bracket_config()
        elif order_type == AdvancedOrderType.CONDITIONAL.value:
            self.setup_conditional_config()
        elif order_type in [AdvancedOrderType.TWAP.value, AdvancedOrderType.VWAP.value]:
            self.setup_algorithmic_config()

    def setup_oco_config(self):
        """Setup OCO order configuration"""
        # Primary order
        primary_frame = ttk.LabelFrame(self.config_frame, text="Primary Order")
        primary_frame.pack(fill="x", padx=5, pady=5)

        # Primary order fields
        row = 0
        ttk.Label(primary_frame, text="Symbol:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.primary_symbol_var = tk.StringVar(value="BTC/USD")
        ttk.Entry(primary_frame, textvariable=self.primary_symbol_var, width=12).grid(
            row=row, column=1, padx=5, pady=2
        )

        ttk.Label(primary_frame, text="Side:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.primary_side_var = tk.StringVar(value=OrderSide.BUY.value)
        ttk.Combobox(
            primary_frame,
            textvariable=self.primary_side_var,
            values=[OrderSide.BUY.value, OrderSide.SELL.value],
            width=8,
        ).grid(row=row, column=3, padx=5, pady=2)

        row += 1
        ttk.Label(primary_frame, text="Quantity:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.primary_quantity_var = tk.StringVar()
        ttk.Entry(primary_frame, textvariable=self.primary_quantity_var, width=12).grid(
            row=row, column=1, padx=5, pady=2
        )

        ttk.Label(primary_frame, text="Price:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.primary_price_var = tk.StringVar()
        ttk.Entry(primary_frame, textvariable=self.primary_price_var, width=12).grid(
            row=row, column=3, padx=5, pady=2
        )

        # Secondary order
        secondary_frame = ttk.LabelFrame(self.config_frame, text="Secondary Order")
        secondary_frame.pack(fill="x", padx=5, pady=5)

        # Secondary order fields
        row = 0
        ttk.Label(secondary_frame, text="Symbol:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.secondary_symbol_var = tk.StringVar(value="BTC/USD")
        ttk.Entry(
            secondary_frame, textvariable=self.secondary_symbol_var, width=12
        ).grid(row=row, column=1, padx=5, pady=2)

        ttk.Label(secondary_frame, text="Side:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.secondary_side_var = tk.StringVar(value=OrderSide.SELL.value)
        ttk.Combobox(
            secondary_frame,
            textvariable=self.secondary_side_var,
            values=[OrderSide.BUY.value, OrderSide.SELL.value],
            width=8,
        ).grid(row=row, column=3, padx=5, pady=2)

        row += 1
        ttk.Label(secondary_frame, text="Quantity:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.secondary_quantity_var = tk.StringVar()
        ttk.Entry(
            secondary_frame, textvariable=self.secondary_quantity_var, width=12
        ).grid(row=row, column=1, padx=5, pady=2)

        ttk.Label(secondary_frame, text="Price:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.secondary_price_var = tk.StringVar()
        ttk.Entry(
            secondary_frame, textvariable=self.secondary_price_var, width=12
        ).grid(row=row, column=3, padx=5, pady=2)

    def setup_trailing_stop_config(self):
        """Setup trailing stop configuration"""
        row = 0
        ttk.Label(self.config_frame, text="Symbol:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.trail_symbol_var = tk.StringVar(value="BTC/USD")
        ttk.Entry(self.config_frame, textvariable=self.trail_symbol_var, width=12).grid(
            row=row, column=1, padx=5, pady=2
        )

        ttk.Label(self.config_frame, text="Side:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.trail_side_var = tk.StringVar(value=OrderSide.SELL.value)
        ttk.Combobox(
            self.config_frame,
            textvariable=self.trail_side_var,
            values=[OrderSide.BUY.value, OrderSide.SELL.value],
            width=8,
        ).grid(row=row, column=3, padx=5, pady=2)

        row += 1
        ttk.Label(self.config_frame, text="Quantity:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.trail_quantity_var = tk.StringVar()
        ttk.Entry(
            self.config_frame, textvariable=self.trail_quantity_var, width=12
        ).grid(row=row, column=1, padx=5, pady=2)

        # Trail configuration
        row += 1
        self.trail_type_var = tk.StringVar(value="amount")
        ttk.Radiobutton(
            self.config_frame,
            text="Trail Amount:",
            variable=self.trail_type_var,
            value="amount",
        ).grid(row=row, column=0, sticky="w", padx=5, pady=2)
        self.trail_amount_var = tk.StringVar()
        ttk.Entry(self.config_frame, textvariable=self.trail_amount_var, width=12).grid(
            row=row, column=1, padx=5, pady=2
        )

        row += 1
        ttk.Radiobutton(
            self.config_frame,
            text="Trail Percent:",
            variable=self.trail_type_var,
            value="percent",
        ).grid(row=row, column=0, sticky="w", padx=5, pady=2)
        self.trail_percent_var = tk.StringVar()
        ttk.Entry(
            self.config_frame, textvariable=self.trail_percent_var, width=12
        ).grid(row=row, column=1, padx=5, pady=2)
        ttk.Label(self.config_frame, text="%").grid(
            row=row, column=2, sticky="w", padx=2, pady=2
        )

    def setup_iceberg_config(self):
        """Setup iceberg order configuration"""
        row = 0
        ttk.Label(self.config_frame, text="Symbol:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.iceberg_symbol_var = tk.StringVar(value="BTC/USD")
        ttk.Entry(
            self.config_frame, textvariable=self.iceberg_symbol_var, width=12
        ).grid(row=row, column=1, padx=5, pady=2)

        ttk.Label(self.config_frame, text="Side:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.iceberg_side_var = tk.StringVar(value=OrderSide.BUY.value)
        ttk.Combobox(
            self.config_frame,
            textvariable=self.iceberg_side_var,
            values=[OrderSide.BUY.value, OrderSide.SELL.value],
            width=8,
        ).grid(row=row, column=3, padx=5, pady=2)

        row += 1
        ttk.Label(self.config_frame, text="Total Quantity:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.iceberg_total_quantity_var = tk.StringVar()
        ttk.Entry(
            self.config_frame, textvariable=self.iceberg_total_quantity_var, width=12
        ).grid(row=row, column=1, padx=5, pady=2)

        ttk.Label(self.config_frame, text="Display Quantity:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.iceberg_display_quantity_var = tk.StringVar()
        ttk.Entry(
            self.config_frame, textvariable=self.iceberg_display_quantity_var, width=12
        ).grid(row=row, column=3, padx=5, pady=2)

        row += 1
        ttk.Label(self.config_frame, text="Limit Price:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.iceberg_price_var = tk.StringVar()
        ttk.Entry(
            self.config_frame, textvariable=self.iceberg_price_var, width=12
        ).grid(row=row, column=1, padx=5, pady=2)

    def setup_bracket_config(self):
        """Setup bracket order configuration"""
        # Entry order
        entry_frame = ttk.LabelFrame(self.config_frame, text="Entry Order")
        entry_frame.pack(fill="x", padx=5, pady=5)

        row = 0
        ttk.Label(entry_frame, text="Symbol:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.bracket_symbol_var = tk.StringVar(value="BTC/USD")
        ttk.Entry(entry_frame, textvariable=self.bracket_symbol_var, width=12).grid(
            row=row, column=1, padx=5, pady=2
        )

        ttk.Label(entry_frame, text="Side:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.bracket_side_var = tk.StringVar(value=OrderSide.BUY.value)
        ttk.Combobox(
            entry_frame,
            textvariable=self.bracket_side_var,
            values=[OrderSide.BUY.value, OrderSide.SELL.value],
            width=8,
        ).grid(row=row, column=3, padx=5, pady=2)

        row += 1
        ttk.Label(entry_frame, text="Quantity:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.bracket_quantity_var = tk.StringVar()
        ttk.Entry(entry_frame, textvariable=self.bracket_quantity_var, width=12).grid(
            row=row, column=1, padx=5, pady=2
        )

        ttk.Label(entry_frame, text="Entry Price:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.bracket_entry_price_var = tk.StringVar()
        ttk.Entry(
            entry_frame, textvariable=self.bracket_entry_price_var, width=12
        ).grid(row=row, column=3, padx=5, pady=2)

        # Profit/Stop levels
        levels_frame = ttk.LabelFrame(self.config_frame, text="Profit & Stop Levels")
        levels_frame.pack(fill="x", padx=5, pady=5)

        row = 0
        ttk.Label(levels_frame, text="Take Profit Price:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.bracket_profit_price_var = tk.StringVar()
        ttk.Entry(
            levels_frame, textvariable=self.bracket_profit_price_var, width=12
        ).grid(row=row, column=1, padx=5, pady=2)

        ttk.Label(levels_frame, text="Stop Loss Price:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.bracket_stop_price_var = tk.StringVar()
        ttk.Entry(
            levels_frame, textvariable=self.bracket_stop_price_var, width=12
        ).grid(row=row, column=3, padx=5, pady=2)

    def setup_conditional_config(self):
        """Setup conditional order configuration"""
        # Basic order details
        basic_frame = ttk.LabelFrame(self.config_frame, text="Order Details")
        basic_frame.pack(fill="x", padx=5, pady=5)

        row = 0
        ttk.Label(basic_frame, text="Symbol:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.conditional_symbol_var = tk.StringVar(value="BTC/USD")
        ttk.Entry(basic_frame, textvariable=self.conditional_symbol_var, width=12).grid(
            row=row, column=1, padx=5, pady=2
        )

        ttk.Label(basic_frame, text="Side:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.conditional_side_var = tk.StringVar(value=OrderSide.BUY.value)
        ttk.Combobox(
            basic_frame,
            textvariable=self.conditional_side_var,
            values=[OrderSide.BUY.value, OrderSide.SELL.value],
            width=8,
        ).grid(row=row, column=3, padx=5, pady=2)

        row += 1
        ttk.Label(basic_frame, text="Quantity:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.conditional_quantity_var = tk.StringVar()
        ttk.Entry(
            basic_frame, textvariable=self.conditional_quantity_var, width=12
        ).grid(row=row, column=1, padx=5, pady=2)

        ttk.Label(basic_frame, text="Limit Price:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.conditional_price_var = tk.StringVar()
        ttk.Entry(basic_frame, textvariable=self.conditional_price_var, width=12).grid(
            row=row, column=3, padx=5, pady=2
        )

        # Conditions
        conditions_frame = ttk.LabelFrame(self.config_frame, text="Conditions")
        conditions_frame.pack(fill="x", padx=5, pady=5)

        # Condition list
        self.conditions_table = ui_table.DataTable(
            conditions_frame,
            ("condition",),
            {"condition": "Condition"},
            key="advanced_orders.conditions",
            empty_text="No conditions yet",
            height=4,
        )
        self.conditions_table.pack(fill="both", expand=True)
        self.conditions_tree = self.conditions_table.tree

        # Condition controls
        condition_controls = ttk.Frame(conditions_frame)
        condition_controls.pack(fill="x", padx=5, pady=5)

        ttk.Button(
            condition_controls, text="Add Condition", command=self.add_condition
        ).pack(side="left", padx=5)
        ttk.Button(
            condition_controls, text="Edit Condition", command=self.edit_condition
        ).pack(side="left", padx=5)
        ttk.Button(
            condition_controls, text="Remove Condition", command=self.remove_condition
        ).pack(side="left", padx=5)

    def setup_algorithmic_config(self):
        """Setup algorithmic order configuration"""
        row = 0
        ttk.Label(self.config_frame, text="Symbol:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.algo_symbol_var = tk.StringVar(value="BTC/USD")
        ttk.Entry(self.config_frame, textvariable=self.algo_symbol_var, width=12).grid(
            row=row, column=1, padx=5, pady=2
        )

        ttk.Label(self.config_frame, text="Side:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.algo_side_var = tk.StringVar(value=OrderSide.BUY.value)
        ttk.Combobox(
            self.config_frame,
            textvariable=self.algo_side_var,
            values=[OrderSide.BUY.value, OrderSide.SELL.value],
            width=8,
        ).grid(row=row, column=3, padx=5, pady=2)

        row += 1
        ttk.Label(self.config_frame, text="Total Quantity:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.algo_quantity_var = tk.StringVar()
        ttk.Entry(
            self.config_frame, textvariable=self.algo_quantity_var, width=12
        ).grid(row=row, column=1, padx=5, pady=2)

        ttk.Label(self.config_frame, text="Duration (minutes):").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.algo_duration_var = tk.StringVar(value="30")
        ttk.Entry(
            self.config_frame, textvariable=self.algo_duration_var, width=12
        ).grid(row=row, column=3, padx=5, pady=2)

        row += 1
        ttk.Label(self.config_frame, text="Max Price Limit:").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        self.algo_max_price_var = tk.StringVar()
        ttk.Entry(
            self.config_frame, textvariable=self.algo_max_price_var, width=12
        ).grid(row=row, column=1, padx=5, pady=2)

        ttk.Label(self.config_frame, text="Participation Rate:").grid(
            row=row, column=2, sticky="w", padx=5, pady=2
        )
        self.algo_participation_var = tk.StringVar(value="20")
        ttk.Entry(
            self.config_frame, textvariable=self.algo_participation_var, width=12
        ).grid(row=row, column=3, padx=5, pady=2)
        ttk.Label(self.config_frame, text="%").grid(
            row=row, column=4, sticky="w", padx=2, pady=2
        )

    def create_order(self):
        """Create the configured order"""
        if not self.automation_engine:
            messagebox.showerror("Error", "Automation engine not available")
            return

        try:
            order_type = self.order_type_var.get()

            if order_type == AdvancedOrderType.OCO.value:
                self.create_oco_order()
            elif order_type == AdvancedOrderType.TRAILING_STOP.value:
                self.create_trailing_stop()
            elif order_type == AdvancedOrderType.ICEBERG.value:
                self.create_iceberg_order()
            elif order_type == AdvancedOrderType.BRACKET.value:
                self.create_bracket_order()
            elif order_type == AdvancedOrderType.CONDITIONAL.value:
                self.create_conditional_order()
            else:
                messagebox.showwarning(
                    "Warning", f"Order type {order_type} not yet implemented"
                )

        except Exception as e:
            messagebox.showerror("Error", f"Error creating order: {e}")

    def create_oco_order(self):
        """Create OCO order"""
        try:
            primary_order = AdvancedOrder(
                id="",  # Will be set by automation engine
                order_type=AdvancedOrderType.OCO,
                symbol=self.primary_symbol_var.get(),
                side=OrderSide(self.primary_side_var.get()),
                quantity=float(self.primary_quantity_var.get()),
                limit_price=(
                    float(self.primary_price_var.get())
                    if self.primary_price_var.get()
                    else None
                ),
            )

            secondary_order = AdvancedOrder(
                id="",  # Will be set by automation engine
                order_type=AdvancedOrderType.OCO,
                symbol=self.secondary_symbol_var.get(),
                side=OrderSide(self.secondary_side_var.get()),
                quantity=float(self.secondary_quantity_var.get()),
                limit_price=(
                    float(self.secondary_price_var.get())
                    if self.secondary_price_var.get()
                    else None
                ),
            )

            oco_id = self.automation_engine.create_oco_order(
                primary_order, secondary_order
            )
            messagebox.showinfo("Success", f"OCO order created with ID: {oco_id}")
            self.refresh_orders()

        except ValueError as e:
            messagebox.showerror("Error", f"Invalid input: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Error creating OCO order: {e}")

    def create_trailing_stop(self):
        """Create trailing stop order"""
        try:
            trail_amount = None
            trail_percent = None

            if self.trail_type_var.get() == "amount" and self.trail_amount_var.get():
                trail_amount = float(self.trail_amount_var.get())
            elif (
                self.trail_type_var.get() == "percent" and self.trail_percent_var.get()
            ):
                trail_percent = float(self.trail_percent_var.get())

            order_id = self.automation_engine.create_trailing_stop_order(
                symbol=self.trail_symbol_var.get(),
                side=OrderSide(self.trail_side_var.get()),
                quantity=float(self.trail_quantity_var.get()),
                trail_amount=trail_amount,
                trail_percent=trail_percent,
            )

            messagebox.showinfo(
                "Success", f"Trailing stop order created with ID: {order_id}"
            )
            self.refresh_orders()

        except ValueError as e:
            messagebox.showerror("Error", f"Invalid input: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Error creating trailing stop order: {e}")

    def create_iceberg_order(self):
        """Create iceberg order"""
        try:
            order_id = self.automation_engine.create_iceberg_order(
                symbol=self.iceberg_symbol_var.get(),
                side=OrderSide(self.iceberg_side_var.get()),
                total_quantity=float(self.iceberg_total_quantity_var.get()),
                display_quantity=float(self.iceberg_display_quantity_var.get()),
                limit_price=float(self.iceberg_price_var.get()),
            )

            messagebox.showinfo("Success", f"Iceberg order created with ID: {order_id}")
            self.refresh_orders()

        except ValueError as e:
            messagebox.showerror("Error", f"Invalid input: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Error creating iceberg order: {e}")

    def create_bracket_order(self):
        """Create bracket order"""
        try:
            entry_order = AdvancedOrder(
                id="",
                order_type=AdvancedOrderType.BRACKET,
                symbol=self.bracket_symbol_var.get(),
                side=OrderSide(self.bracket_side_var.get()),
                quantity=float(self.bracket_quantity_var.get()),
                limit_price=(
                    float(self.bracket_entry_price_var.get())
                    if self.bracket_entry_price_var.get()
                    else None
                ),
            )

            bracket_id = self.automation_engine.create_bracket_order(
                entry_order=entry_order,
                take_profit_price=float(self.bracket_profit_price_var.get()),
                stop_loss_price=float(self.bracket_stop_price_var.get()),
            )

            messagebox.showinfo(
                "Success", f"Bracket order created with ID: {bracket_id}"
            )
            self.refresh_orders()

        except ValueError as e:
            messagebox.showerror("Error", f"Invalid input: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Error creating bracket order: {e}")

    def create_conditional_order(self):
        """Create conditional order"""
        messagebox.showinfo("Info", "Conditional order creation dialog coming soon")

    def refresh_orders(self):
        """Refresh the active orders display"""
        if not self.automation_engine:
            return

        # Clear current items
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)

        # Add active orders
        for order in self.automation_engine.get_active_orders():
            values = (
                order.id[:8] + "...",  # Shortened ID
                order.order_type.value,
                order.symbol,
                order.side.value,
                f"{order.quantity:.4f}",
                f"{order.limit_price:.4f}" if order.limit_price else "Market",
                order.status.value,
                order.created_at.strftime("%m-%d %H:%M"),
            )

            tags = []
            if order.status == OrderStatus.PENDING:
                tags.append("pending")
            elif order.status == OrderStatus.FILLED:
                tags.append("filled")
            elif order.status == OrderStatus.CANCELLED:
                tags.append("cancelled")

            self.orders_tree.insert("", "end", values=values, tags=tags)

        # Configure tag colors
        p = ui_theme.active_palette()
        self.orders_tree.tag_configure("pending", foreground=ui_tokens.STATUS["warn"])
        self.orders_tree.tag_configure("filled", foreground=ui_tokens.STATUS["good"])
        self.orders_tree.tag_configure("cancelled", foreground=p["MUTED"])

    def on_order_select(self, event):
        """Handle order selection"""
        selection = self.orders_tree.selection()
        if not selection:
            return

        item = selection[0]
        values = self.orders_tree.item(item)["values"]
        if not values:
            return

        # Find the full order by ID prefix
        order_id_prefix = values[0].replace("...", "")
        order = None

        if self.automation_engine:
            for full_order in self.automation_engine.get_active_orders():
                if full_order.id.startswith(order_id_prefix):
                    order = full_order
                    break

        if order:
            self.display_order_details(order)

    def display_order_details(self, order: AdvancedOrder):
        """Display order details"""
        details = []
        details.append(f"Order ID: {order.id}")
        details.append(f"Type: {order.order_type.value}")
        details.append(f"Symbol: {order.symbol}")
        details.append(f"Side: {order.side.value}")
        details.append(f"Quantity: {order.quantity}")
        details.append(f"Limit Price: {order.limit_price or 'N/A'}")
        details.append(f"Stop Price: {order.stop_price or 'N/A'}")
        details.append(f"Status: {order.status.value}")
        details.append(f"Created: {order.created_at}")
        details.append(f"Updated: {order.updated_at}")
        details.append(f"Filled: {order.filled_quantity}")
        details.append(f"Avg Fill Price: {order.average_fill_price}")

        if order.conditions:
            details.append("\nConditions:")
            for condition in order.conditions:
                details.append(
                    f"  - {condition.condition_type.value}: {condition.target_value}"
                )

        if order.trail_amount:
            details.append(f"Trail Amount: {order.trail_amount}")
        if order.trail_percent:
            details.append(f"Trail Percent: {order.trail_percent}%")

        self.details_text.delete(1.0, tk.END)
        self.details_text.insert(1.0, "\n".join(details))

    def cancel_selected_order(self):
        """Cancel the selected order"""
        messagebox.showinfo("Info", "Cancel order feature coming soon")

    def modify_selected_order(self):
        """Modify the selected order"""
        messagebox.showinfo("Info", "Modify order feature coming soon")

    def force_execute_order(self):
        """Force execute the selected order"""
        messagebox.showinfo("Info", "Force execute feature coming soon")

    def clear_form(self):
        """Clear the order form"""
        # Clear all StringVars based on current order type
        messagebox.showinfo("Info", "Clear form feature coming soon")

    def save_template(self):
        """Save current configuration as template"""
        messagebox.showinfo("Info", "Save template feature coming soon")

    def load_template(self):
        """Load a saved template"""
        messagebox.showinfo("Info", "Load template feature coming soon")

    def add_condition(self):
        """Add a condition to conditional order"""
        messagebox.showinfo("Info", "Add condition dialog coming soon")

    def edit_condition(self):
        """Edit selected condition"""
        messagebox.showinfo("Info", "Edit condition dialog coming soon")

    def remove_condition(self):
        """Remove selected condition"""
        messagebox.showinfo("Info", "Remove condition feature coming soon")

    def create_automation_rule(self):
        """Create new automation rule"""
        messagebox.showinfo("Info", "Automation rule creation coming soon")

    def edit_automation_rule(self):
        """Edit selected automation rule"""
        messagebox.showinfo("Info", "Edit automation rule coming soon")

    def delete_automation_rule(self):
        """Delete selected automation rule"""
        messagebox.showinfo("Info", "Delete automation rule coming soon")

    def test_automation_rule(self):
        """Test selected automation rule"""
        messagebox.showinfo("Info", "Test automation rule coming soon")

    def apply_history_filter(self):
        """Apply history filter"""
        messagebox.showinfo("Info", "History filter coming soon")

    def on_order_update(self, order: AdvancedOrder):
        """Callback for order updates"""
        # Refresh orders in GUI thread
        self.parent.after_idle(self.refresh_orders)

    def on_order_execution(self, order: AdvancedOrder):
        """Callback for order execution"""
        # Show notification or update in GUI thread
        self.parent.after_idle(
            lambda: messagebox.showinfo(
                "Order Executed",
                f"Order {order.id[:8]}... executed: {order.side.value} {order.filled_quantity} {order.symbol}",
            )
        )


# Fallback class for when automation is not available
if not AUTOMATION_AVAILABLE:

    class AdvancedOrderGUI:
        def __init__(self, parent):
            self.parent = parent
            self.setup_fallback_ui()

        def setup_fallback_ui(self):
            frame = ttk.Frame(self.parent)
            frame.pack(fill="both", expand=True, padx=20, pady=20)

            ttk.Label(
                frame,
                text="Advanced Order Types & Automation",
                font=ui_tokens.font("display", "bold"),
            ).pack(pady=20)

            ttk.Label(
                frame,
                text="⚠️ Advanced order automation not available",
                style="Warn.TLabel",
                font=ui_tokens.font("title"),
            ).pack(pady=10)

            ttk.Label(
                frame,
                text="Missing dependencies:",
                font=ui_tokens.font("body", "bold"),
            ).pack(pady=5)

            deps = [
                "Advanced order automation module",
                "Order management models",
                "Threading support",
            ]
            for dep in deps:
                ttk.Label(frame, text=f"• {dep}", style="Bad.TLabel").pack()

            ttk.Label(
                frame,
                text="Install missing dependencies to enable advanced order features",
                style="Muted.TLabel",
                font=ui_tokens.font("body"),
            ).pack(pady=10)
