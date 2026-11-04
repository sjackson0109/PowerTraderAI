"""
Long-term Holdings Management GUI (Item 20)
Graphical interface for managing cryptocurrency long-term holdings
"""

import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

import ui_table
import ui_theme
import ui_tokens

try:
    from long_term_holdings import Holding, HoldingsManager, get_holdings_manager

    HOLDINGS_AVAILABLE = True
except ImportError:
    HOLDINGS_AVAILABLE = False
    print("Warning: Long-term holdings system not available.")

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class HoldingsManagementGUI:
    """GUI for managing long-term cryptocurrency holdings"""

    def __init__(self, parent: tk.Widget):
        self.parent = parent
        self.holdings_manager = None
        self.selected_holding = None

        # Initialize holdings manager if available
        if HOLDINGS_AVAILABLE:
            try:
                self.holdings_manager = get_holdings_manager()
            except Exception as e:
                print(f"Error initializing holdings manager: {e}")

        self.setup_ui()
        self.refresh_holdings_display()

    def setup_ui(self):
        """Setup the user interface"""
        self.main_frame = ttk.Frame(self.parent)
        self.main_frame.pack(fill="both", expand=True)

        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill="both", expand=True)

        # Holdings Management Tab
        self.holdings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.holdings_tab, text="Holdings")
        self.setup_holdings_tab()

        # Portfolio Overview Tab
        self.portfolio_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.portfolio_tab, text="Portfolio Overview")
        self.setup_portfolio_tab()

        # Rebalancing Tab
        self.rebalancing_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.rebalancing_tab, text="Rebalancing")
        self.setup_rebalancing_tab()

        # Analytics Tab
        self.analytics_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.analytics_tab, text="Analytics")
        self.setup_analytics_tab()

    def setup_holdings_tab(self):
        """Setup the holdings management tab"""
        # Top frame for controls
        control_frame = ttk.Frame(self.holdings_tab)
        control_frame.pack(fill="x", padx=5, pady=5)

        ttk.Button(
            control_frame, text="Add Holding", command=self.add_holding_dialog
        ).pack(side="left", padx=5)
        ttk.Button(
            control_frame, text="Edit Holding", command=self.edit_holding_dialog
        ).pack(side="left", padx=5)
        ttk.Button(
            control_frame, text="Delete Holding", command=self.delete_holding
        ).pack(side="left", padx=5)
        ttk.Button(
            control_frame, text="Update Prices", command=self.update_prices_dialog
        ).pack(side="left", padx=5)
        ttk.Button(control_frame, text="Export CSV", command=self.export_holdings).pack(
            side="left", padx=5
        )
        ttk.Button(
            control_frame, text="Refresh", command=self.refresh_holdings_display
        ).pack(side="right", padx=5)

        # Holdings table (ui_table: fitted columns, its own scrollbars, sortable)
        self.holdings_table = ui_table.DataTable(
            self.holdings_tab,
            (
                "symbol",
                "quantity",
                "avg_cost",
                "current_price",
                "total_cost",
                "current_value",
                "pnl",
                "pnl_pct",
                "exchange",
                "target_pct",
            ),
            {
                "symbol": "Symbol",
                "quantity": "Quantity",
                "avg_cost": "Avg Cost",
                "current_price": "Current Price",
                "total_cost": "Total Cost",
                "current_value": "Current Value",
                "pnl": "P&L",
                "pnl_pct": "P&L %",
                "exchange": "Exchange",
                "target_pct": "Target %",
            },
            key="holdings_management.holdings",
            numeric=(
                "quantity",
                "avg_cost",
                "current_price",
                "total_cost",
                "current_value",
                "pnl",
                "pnl_pct",
                "target_pct",
            ),
            empty_text="No holdings yet",
        )
        self.holdings_table.pack(fill="both", expand=True)
        self.holdings_tree = self.holdings_table.tree

        # Bind selection
        self.holdings_tree.bind("<<TreeviewSelect>>", self.on_holding_select)

    def setup_portfolio_tab(self):
        """Setup portfolio overview tab"""
        # Summary frame
        summary_frame = ttk.LabelFrame(self.portfolio_tab, text="Portfolio Summary")
        summary_frame.pack(fill="x", padx=10, pady=10)

        self.summary_labels = {}
        summary_data = [
            ("Total Holdings:", "holdings_count"),
            ("Total Cost:", "total_cost"),
            ("Current Value:", "total_value"),
            ("Total P&L:", "total_pnl"),
            ("Total P&L %:", "total_pnl_pct"),
        ]

        for i, (label_text, key) in enumerate(summary_data):
            ttk.Label(summary_frame, text=label_text).grid(
                row=i, column=0, sticky="w", padx=5, pady=2
            )
            label_widget = ttk.Label(summary_frame, text="$0.00")
            label_widget.grid(row=i, column=1, sticky="e", padx=5, pady=2)
            self.summary_labels[key] = label_widget

        # Chart frame
        if MATPLOTLIB_AVAILABLE:
            chart_frame = ttk.LabelFrame(
                self.portfolio_tab, text="Portfolio Allocation"
            )
            chart_frame.pack(fill="both", expand=True, padx=10, pady=10)

            self.portfolio_fig = Figure(
                figsize=(8, 6), facecolor=ui_tokens.CHART["figure"]
            )
            self.portfolio_canvas = FigureCanvasTkAgg(self.portfolio_fig, chart_frame)
            self.portfolio_canvas.get_tk_widget().pack(fill="both", expand=True)
        else:
            ttk.Label(
                self.portfolio_tab,
                text="Charts not available - matplotlib not installed",
            ).pack(pady=20)

    def setup_rebalancing_tab(self):
        """Setup rebalancing suggestions tab"""
        # Control frame
        control_frame = ttk.Frame(self.rebalancing_tab)
        control_frame.pack(fill="x", padx=5, pady=5)

        ttk.Button(
            control_frame,
            text="Generate Suggestions",
            command=self.generate_rebalancing_suggestions,
        ).pack(side="left", padx=5)
        ttk.Button(
            control_frame, text="Export Suggestions", command=self.export_suggestions
        ).pack(side="left", padx=5)

        # Suggestions table
        self.suggestions_table = ui_table.DataTable(
            self.rebalancing_tab,
            (
                "symbol",
                "action",
                "current_pct",
                "target_pct",
                "deviation",
                "amount_diff",
            ),
            {
                "symbol": "Symbol",
                "action": "Action",
                "current_pct": "Current %",
                "target_pct": "Target %",
                "deviation": "Deviation %",
                "amount_diff": "Amount Diff",
            },
            key="holdings_management.rebalancing",
            numeric=("current_pct", "target_pct", "deviation", "amount_diff"),
            empty_text="No suggestions yet",
        )
        self.suggestions_table.pack(fill="both", expand=True)
        self.suggestions_tree = self.suggestions_table.tree

    def setup_analytics_tab(self):
        """Setup analytics and charts tab"""
        if MATPLOTLIB_AVAILABLE:
            # Performance chart
            perf_frame = ttk.LabelFrame(
                self.analytics_tab, text="Performance Analytics"
            )
            perf_frame.pack(fill="both", expand=True, padx=10, pady=5)

            self.analytics_fig = Figure(
                figsize=(10, 6), facecolor=ui_tokens.CHART["figure"]
            )
            self.analytics_canvas = FigureCanvasTkAgg(self.analytics_fig, perf_frame)
            self.analytics_canvas.get_tk_widget().pack(fill="both", expand=True)

            # Control frame for analytics
            analytics_control = ttk.Frame(self.analytics_tab)
            analytics_control.pack(fill="x", padx=10, pady=5)

            ttk.Button(
                analytics_control,
                text="Update Charts",
                command=self.update_analytics_charts,
            ).pack(side="left", padx=5)
        else:
            ttk.Label(
                self.analytics_tab,
                text="Analytics not available - matplotlib not installed",
            ).pack(pady=20)

    def refresh_holdings_display(self):
        """Refresh the holdings display"""
        if not HOLDINGS_AVAILABLE or not self.holdings_manager:
            return

        # Clear current items
        for item in self.holdings_tree.get_children():
            self.holdings_tree.delete(item)

        # Add holdings
        try:
            self.holdings_manager.refresh_holdings()
            for holding in self.holdings_manager.holdings:
                values = (
                    holding.symbol,
                    f"{holding.quantity:.8f}",
                    f"${holding.average_cost:.4f}",
                    f"${holding.current_price:.4f}",
                    f"${holding.total_cost:.2f}",
                    f"${holding.current_value:.2f}",
                    f"${holding.unrealized_pnl:.2f}",
                    f"{holding.unrealized_pnl_percentage:.2f}%",
                    holding.exchange,
                    f"{holding.target_percentage:.1f}%",
                )

                # Add color coding for P&L
                tags = []
                if holding.unrealized_pnl > 0:
                    tags.append("profit")
                elif holding.unrealized_pnl < 0:
                    tags.append("loss")

                # a selection finds its holding by symbol (on_holding_select)
                self.holdings_tree.insert("", "end", values=values, tags=tags)

            # Configure tags for colors
            status = ui_tokens.STATUS
            self.holdings_tree.tag_configure("profit", foreground=status["good"])
            self.holdings_tree.tag_configure("loss", foreground=status["bad"])

            # Update portfolio summary
            self.update_portfolio_summary()

        except Exception as e:
            print(f"Error refreshing holdings: {e}")
            messagebox.showerror("Error", f"Error refreshing holdings: {e}")

    def update_portfolio_summary(self):
        """Update portfolio summary display"""
        if not HOLDINGS_AVAILABLE or not self.holdings_manager:
            return

        try:
            summary = self.holdings_manager.get_portfolio_summary()

            self.summary_labels["holdings_count"].config(
                text=f"{summary['holdings_count']}"
            )
            self.summary_labels["total_cost"].config(
                text=f"${summary['total_cost']:.2f}"
            )
            self.summary_labels["total_value"].config(
                text=f"${summary['total_value']:.2f}"
            )
            self.summary_labels["total_pnl"].config(text=f"${summary['total_pnl']:.2f}")
            self.summary_labels["total_pnl_pct"].config(
                text=f"{summary['total_pnl_percentage']:.2f}%"
            )

            # Color code P&L
            pnl_style = "Good.TLabel" if summary["total_pnl"] >= 0 else "Bad.TLabel"
            self.summary_labels["total_pnl"].config(style=pnl_style)
            self.summary_labels["total_pnl_pct"].config(style=pnl_style)

            # Update portfolio chart
            if MATPLOTLIB_AVAILABLE and hasattr(self, "portfolio_canvas"):
                self.update_portfolio_chart()

        except Exception as e:
            print(f"Error updating portfolio summary: {e}")

    def update_portfolio_chart(self):
        """Update the portfolio allocation pie chart"""
        if not MATPLOTLIB_AVAILABLE or not self.holdings_manager:
            return

        try:
            chart = ui_tokens.CHART
            self.portfolio_fig.clear()
            ax = self.portfolio_fig.add_subplot(111)

            holdings = self.holdings_manager.holdings
            if not holdings:
                ax.text(
                    0.5,
                    0.5,
                    "No holdings to display",
                    ha="center",
                    va="center",
                    color=chart["text"],
                )
                ui_theme.theme_figure(self.portfolio_fig)
                self.portfolio_canvas.draw()
                return

            # Prepare data for pie chart
            symbols = []
            values = []
            colors = []

            for holding in holdings:
                if holding.current_value > 0:
                    symbols.append(holding.symbol)
                    values.append(holding.current_value)
                    colors.append(plt.cm.Set3(len(symbols) - 1))

            if values:
                wedges, texts, autotexts = ax.pie(
                    values,
                    labels=symbols,
                    autopct="%1.1f%%",
                    colors=colors,
                    textprops={"color": chart["text"]},
                )
                for autotext in autotexts:  # dark on the pale wedges
                    autotext.set_color(chart["figure"])
                ax.set_title("Portfolio Allocation", color=chart["text"], fontsize=14)

            ui_theme.theme_figure(self.portfolio_fig)
            self.portfolio_canvas.draw()

        except Exception as e:
            print(f"Error updating portfolio chart: {e}")

    def on_holding_select(self, event):
        """Handle holding selection"""
        selection = self.holdings_tree.selection()
        if selection and HOLDINGS_AVAILABLE and self.holdings_manager:
            item = selection[0]
            symbol = self.holdings_tree.item(item)["values"][0]

            # Find the holding
            for holding in self.holdings_manager.holdings:
                if holding.symbol == symbol:
                    self.selected_holding = holding
                    break

    def add_holding_dialog(self):
        """Show dialog to add a new holding"""
        if not HOLDINGS_AVAILABLE:
            messagebox.showerror("Error", "Holdings system not available")
            return

        dialog = HoldingDialog(self.parent, title="Add Holding")
        if dialog.result:
            holding = dialog.result
            holding.last_updated = datetime.now().isoformat()

            if self.holdings_manager.add_holding(holding):
                self.refresh_holdings_display()
                messagebox.showinfo("Success", "Holding added successfully!")
            else:
                messagebox.showerror("Error", "Failed to add holding")

    def edit_holding_dialog(self):
        """Show dialog to edit selected holding"""
        if not self.selected_holding:
            messagebox.showwarning("Warning", "Please select a holding to edit")
            return

        dialog = HoldingDialog(
            self.parent, title="Edit Holding", holding=self.selected_holding
        )
        if dialog.result:
            holding = dialog.result
            holding.last_updated = datetime.now().isoformat()

            if self.holdings_manager.update_holding(holding):
                self.refresh_holdings_display()
                messagebox.showinfo("Success", "Holding updated successfully!")
            else:
                messagebox.showerror("Error", "Failed to update holding")

    def delete_holding(self):
        """Delete the selected holding"""
        if not self.selected_holding:
            messagebox.showwarning("Warning", "Please select a holding to delete")
            return

        if messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete {self.selected_holding.symbol}?",
        ):
            if self.holdings_manager.delete_holding(self.selected_holding.id):
                self.refresh_holdings_display()
                self.selected_holding = None
                messagebox.showinfo("Success", "Holding deleted successfully!")
            else:
                messagebox.showerror("Error", "Failed to delete holding")

    def update_prices_dialog(self):
        """Show dialog to update prices"""
        if not HOLDINGS_AVAILABLE or not self.holdings_manager:
            return

        dialog = PriceUpdateDialog(self.parent, self.holdings_manager)
        if dialog.updated:
            self.refresh_holdings_display()

    def generate_rebalancing_suggestions(self):
        """Generate and display rebalancing suggestions"""
        if not HOLDINGS_AVAILABLE or not self.holdings_manager:
            return

        # Clear current suggestions
        for item in self.suggestions_tree.get_children():
            self.suggestions_tree.delete(item)

        try:
            suggestions = self.holdings_manager.get_rebalancing_suggestions()

            for suggestion in suggestions:
                values = (
                    suggestion["symbol"],
                    suggestion["action"],
                    f"{suggestion['current_percentage']:.2f}%",
                    f"{suggestion['target_percentage']:.2f}%",
                    f"{suggestion['deviation']:.2f}%",
                    f"${suggestion['amount_difference']:.2f}",
                )

                tags = ["buy"] if suggestion["action"] == "BUY" else ["sell"]
                self.suggestions_tree.insert("", "end", values=values, tags=tags)

            # Configure tag colors
            status = ui_tokens.STATUS
            self.suggestions_tree.tag_configure("buy", foreground=status["good"])
            self.suggestions_tree.tag_configure("sell", foreground=status["warn"])

        except Exception as e:
            print(f"Error generating suggestions: {e}")
            messagebox.showerror("Error", f"Error generating suggestions: {e}")

    def export_holdings(self):
        """Export holdings to CSV"""
        if not HOLDINGS_AVAILABLE or not self.holdings_manager:
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Holdings",
        )

        if file_path:
            if self.holdings_manager.export_holdings_csv(file_path):
                messagebox.showinfo("Success", f"Holdings exported to {file_path}")
            else:
                messagebox.showerror("Error", "Failed to export holdings")

    def export_suggestions(self):
        """Export rebalancing suggestions"""
        # Implementation for exporting suggestions
        messagebox.showinfo("Info", "Suggestion export not implemented yet")

    def update_analytics_charts(self):
        """Update analytics charts"""
        if MATPLOTLIB_AVAILABLE and hasattr(self, "analytics_canvas"):
            messagebox.showinfo("Info", "Advanced analytics coming soon")


class HoldingDialog:
    """Dialog for adding/editing holdings"""

    def __init__(self, parent, title="Add Holding", holding=None):
        self.parent = parent
        self.result = None
        self.holding = holding

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("400x600")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center the dialog
        self.center_window()

        self.setup_dialog()

        # Wait for dialog to close
        self.dialog.wait_window()

    def center_window(self):
        """Center the dialog on the parent window"""
        self.dialog.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() // 2) - (400 // 2)
        y = self.parent.winfo_y() + (self.parent.winfo_height() // 2) - (600 // 2)
        self.dialog.geometry(f"400x600+{x}+{y}")

    def setup_dialog(self):
        """Setup the dialog interface"""
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Create entry fields
        fields = [
            ("Symbol:", "symbol", "text"),
            ("Quantity:", "quantity", "float"),
            ("Average Cost ($):", "average_cost", "float"),
            ("Current Price ($):", "current_price", "float"),
            ("Exchange:", "exchange", "text"),
            ("Purchase Date:", "purchase_date", "text"),
            ("Target Percentage (%):", "target_percentage", "float"),
            ("Rebalance Threshold (%):", "rebalance_threshold", "float"),
            ("Notes:", "notes", "text"),
        ]

        self.entries = {}

        for i, (label, field, field_type) in enumerate(fields):
            ttk.Label(main_frame, text=label).grid(row=i, column=0, sticky="w", pady=5)

            if field == "notes":
                entry = tk.Text(main_frame, height=4, width=30)
            else:
                entry = ttk.Entry(main_frame, width=30)

            entry.grid(row=i, column=1, sticky="ew", pady=5, padx=(10, 0))
            self.entries[field] = entry

            # Populate if editing
            if self.holding:
                value = getattr(self.holding, field, "")
                if field == "notes":
                    entry.insert("1.0", value)
                else:
                    entry.insert(0, str(value))

        # Configure grid weights
        main_frame.grid_columnconfigure(1, weight=1)

        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=len(fields), column=0, columnspan=2, pady=20)

        ttk.Button(button_frame, text="Save", command=self.save_holding).pack(
            side="left", padx=10
        )
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(
            side="left", padx=10
        )

    def save_holding(self):
        """Save the holding data"""
        try:
            if HOLDINGS_AVAILABLE:
                # Get values from entries
                symbol = self.entries["symbol"].get().strip().upper()
                quantity = float(self.entries["quantity"].get() or 0)
                average_cost = float(self.entries["average_cost"].get() or 0)
                current_price = float(self.entries["current_price"].get() or 0)
                exchange = self.entries["exchange"].get().strip()
                purchase_date = self.entries["purchase_date"].get().strip()
                target_percentage = float(self.entries["target_percentage"].get() or 0)
                rebalance_threshold = float(
                    self.entries["rebalance_threshold"].get() or 5.0
                )

                if isinstance(self.entries["notes"], tk.Text):
                    notes = self.entries["notes"].get("1.0", tk.END).strip()
                else:
                    notes = self.entries["notes"].get().strip()

                # Validation
                if not symbol:
                    messagebox.showerror("Error", "Symbol is required")
                    return

                if quantity <= 0:
                    messagebox.showerror("Error", "Quantity must be greater than 0")
                    return

                if average_cost <= 0:
                    messagebox.showerror("Error", "Average cost must be greater than 0")
                    return

                # Create holding
                from long_term_holdings import Holding

                self.result = Holding(
                    id=self.holding.id if self.holding else None,
                    symbol=symbol,
                    quantity=quantity,
                    average_cost=average_cost,
                    current_price=current_price,
                    exchange=exchange,
                    purchase_date=purchase_date,
                    target_percentage=target_percentage,
                    rebalance_threshold=rebalance_threshold,
                    notes=notes,
                )

                self.dialog.destroy()

        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid numeric values")
        except Exception as e:
            messagebox.showerror("Error", f"Error saving holding: {e}")

    def cancel(self):
        """Cancel the dialog"""
        self.dialog.destroy()


class PriceUpdateDialog:
    """Dialog for updating prices"""

    def __init__(self, parent, holdings_manager):
        self.parent = parent
        self.holdings_manager = holdings_manager
        self.updated = False

        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Update Prices")
        self.dialog.geometry("500x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self.setup_dialog()
        self.dialog.wait_window()

    def setup_dialog(self):
        """Setup price update dialog"""
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        ttk.Label(
            main_frame,
            text="Update Current Prices",
            font=ui_tokens.font("title", "bold"),
        ).pack(pady=10)

        # Price entries frame
        entries_frame = ttk.Frame(main_frame)
        entries_frame.pack(fill="both", expand=True)

        self.price_entries = {}

        for i, holding in enumerate(self.holdings_manager.holdings):
            frame = ttk.Frame(entries_frame)
            frame.pack(fill="x", pady=5)

            ttk.Label(frame, text=f"{holding.symbol}:", width=10).pack(side="left")

            entry = ttk.Entry(frame, width=15)
            entry.pack(side="left", padx=10)
            entry.insert(0, str(holding.current_price))

            ttk.Label(frame, text="$").pack(side="left")

            self.price_entries[holding.symbol] = entry

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=20)

        ttk.Button(
            button_frame, text="Update All", command=self.update_all_prices
        ).pack(side="left", padx=10)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(
            side="left", padx=10
        )

    def update_all_prices(self):
        """Update all prices"""
        try:
            for symbol, entry in self.price_entries.items():
                price = float(entry.get())
                self.holdings_manager.db.update_price(symbol, price, "manual")

            self.updated = True
            messagebox.showinfo("Success", "Prices updated successfully!")
            self.dialog.destroy()

        except ValueError:
            messagebox.showerror("Error", "Please enter valid numeric prices")
        except Exception as e:
            messagebox.showerror("Error", f"Error updating prices: {e}")


# Fallback classes for when holdings system is not available
if not HOLDINGS_AVAILABLE:

    class HoldingsManagementGUI:
        def __init__(self, parent):
            self.parent = parent
            self.setup_fallback_ui()

        def setup_fallback_ui(self):
            frame = ttk.Frame(self.parent)
            frame.pack(fill="both", expand=True, padx=20, pady=20)

            ttk.Label(
                frame,
                text="Long-term Holdings Management",
                font=ui_tokens.font("display", "bold"),
            ).pack(pady=20)

            ttk.Label(
                frame,
                text="⚠️ Holdings system not available",
                style="Warn.TLabel",
                font=ui_tokens.font("title"),
            ).pack(pady=10)

            ttk.Label(
                frame, text="Missing dependencies:", font=ui_tokens.font("body", "bold")
            ).pack(pady=5)

            missing_deps = []
            try:
                import sqlite3
            except ImportError:
                missing_deps.append("sqlite3")

            if missing_deps:
                for dep in missing_deps:
                    ttk.Label(frame, text=f"• {dep}", style="Bad.TLabel").pack()
            else:
                ttk.Label(
                    frame, text="• long_term_holdings module", style="Bad.TLabel"
                ).pack()

            ttk.Label(
                frame,
                text="Install missing dependencies to enable holdings management",
                style="Muted.TLabel",
                font=ui_tokens.font("body"),
            ).pack(pady=10)
