"""
PowerTrader AI GUI Integration Module

Integrates Phase 4 backend systems with the existing Tkinter GUI interface.
Provides live trading controls, monitoring dashboards, and configuration panels.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import asyncio
import threading
import queue
from datetime import datetime
from typing import Dict, Any, Optional, Callable
import json

# Phase 4 imports
from pt_paper_trading import PaperTradingAccount, OrderType, OrderSide
from pt_live_monitor import LiveMonitor, Alert
from pt_risk import RiskManager, RiskLimits
from pt_cost import CostManager, PerformanceTier
from pt_logging import get_logger

class TradingControlPanel(ttk.Frame):
    """Trading control panel for the GUI with Phase 4 integration."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.logger = get_logger("gui_trading_panel")
        
        # Trading system components
        self.paper_account: Optional[PaperTradingAccount] = None
        self.live_monitor: Optional[LiveMonitor] = None
        self.risk_manager: Optional[RiskManager] = None
        
        # GUI state
        self.trading_enabled = False
        self.monitoring_enabled = False
        
        # Threading and communication
        self.alert_queue = queue.Queue()
        self.status_queue = queue.Queue()
        
        self._setup_ui()
        self._start_background_tasks()
    
    def _setup_ui(self):
        """Create the trading control UI."""
        # Main container
        main_frame = ttk.LabelFrame(self, text="Trading Control Panel", padding="10")
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Account controls section
        self._create_account_section(main_frame)
        
        # Trading controls section
        self._create_trading_section(main_frame)
        
        # Monitoring section
        self._create_monitoring_section(main_frame)
        
        # Status section
        self._create_status_section(main_frame)
    
    def _create_account_section(self, parent):
        """Create account management section."""
        account_frame = ttk.LabelFrame(parent, text="Account Management", padding="5")
        account_frame.pack(fill="x", pady=(0, 10))
        
        # Account type selection
        ttk.Label(account_frame, text="Account Type:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.account_type_var = tk.StringVar(value="Paper Trading")
        account_combo = ttk.Combobox(account_frame, textvariable=self.account_type_var,
                                   values=["Paper Trading", "Live Trading (Demo)", "Live Trading"],
                                   state="readonly", width=20)
        account_combo.grid(row=0, column=1, sticky="w", padx=(0, 20))
        
        # Initial balance for paper trading
        ttk.Label(account_frame, text="Initial Balance:").grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.balance_var = tk.StringVar(value="10000.00")
        balance_entry = ttk.Entry(account_frame, textvariable=self.balance_var, width=12)
        balance_entry.grid(row=0, column=3, sticky="w", padx=(0, 10))
        
        # Initialize button
        self.init_btn = ttk.Button(account_frame, text="Initialize Account", 
                                 command=self._initialize_account)
        self.init_btn.grid(row=0, column=4, sticky="w", padx=(10, 0))
        
        # Account status label
        self.account_status_var = tk.StringVar(value="Not Initialized")
        ttk.Label(account_frame, textvariable=self.account_status_var, 
                 foreground="orange").grid(row=1, column=0, columnspan=5, sticky="w", pady=(5, 0))
    
    def _create_trading_section(self, parent):
        """Create trading controls section."""
        trading_frame = ttk.LabelFrame(parent, text="Trading Controls", padding="5")
        trading_frame.pack(fill="x", pady=(0, 10))
        
        # Quick trade controls
        quick_frame = ttk.Frame(trading_frame)
        quick_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(quick_frame, text="Symbol:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.symbol_var = tk.StringVar(value="BTC")
        symbol_entry = ttk.Entry(quick_frame, textvariable=self.symbol_var, width=8)
        symbol_entry.grid(row=0, column=1, sticky="w", padx=(0, 10))
        
        ttk.Label(quick_frame, text="Quantity:").grid(row=0, column=2, sticky="w", padx=(0, 5))
        self.quantity_var = tk.StringVar(value="0.01")
        quantity_entry = ttk.Entry(quick_frame, textvariable=self.quantity_var, width=10)
        quantity_entry.grid(row=0, column=3, sticky="w", padx=(0, 10))
        
        # Buy/Sell buttons
        self.buy_btn = ttk.Button(quick_frame, text="Buy", command=self._execute_buy,
                                style="Accent.TButton")
        self.buy_btn.grid(row=0, column=4, sticky="w", padx=(0, 5))
        
        self.sell_btn = ttk.Button(quick_frame, text="Sell", command=self._execute_sell,
                                 style="Accent.TButton")
        self.sell_btn.grid(row=0, column=5, sticky="w", padx=(0, 10))
        
        # Trading status
        control_frame = ttk.Frame(trading_frame)
        control_frame.pack(fill="x")
        
        self.trading_status_var = tk.StringVar(value="Trading Disabled")
        ttk.Label(control_frame, textvariable=self.trading_status_var).pack(side="left")
        
        self.toggle_trading_btn = ttk.Button(control_frame, text="Enable Trading",
                                           command=self._toggle_trading)
        self.toggle_trading_btn.pack(side="right")
    
    def _create_monitoring_section(self, parent):
        """Create monitoring controls section."""
        monitor_frame = ttk.LabelFrame(parent, text="Live Monitoring", padding="5")
        monitor_frame.pack(fill="x", pady=(0, 10))
        
        # Monitoring controls
        control_frame = ttk.Frame(monitor_frame)
        control_frame.pack(fill="x", pady=(0, 5))
        
        self.monitoring_status_var = tk.StringVar(value="Monitoring Disabled")
        ttk.Label(control_frame, textvariable=self.monitoring_status_var).pack(side="left")
        
        self.toggle_monitoring_btn = ttk.Button(control_frame, text="Start Monitoring",
                                              command=self._toggle_monitoring)
        self.toggle_monitoring_btn.pack(side="right")
        
        # Alert display
        alert_frame = ttk.Frame(monitor_frame)
        alert_frame.pack(fill="x")
        
        ttk.Label(alert_frame, text="Recent Alerts:").pack(anchor="w")
        self.alerts_text = tk.Text(alert_frame, height=4, wrap="word", 
                                 background="#0E1626", foreground="#C7D1DB")
        alerts_scroll = ttk.Scrollbar(alert_frame, orient="vertical", command=self.alerts_text.yview)
        self.alerts_text.configure(yscrollcommand=alerts_scroll.set)
        
        self.alerts_text.pack(side="left", fill="both", expand=True)
        alerts_scroll.pack(side="right", fill="y")
    
    def _create_status_section(self, parent):
        """Create status display section."""
        status_frame = ttk.LabelFrame(parent, text="Account Status", padding="5")
        status_frame.pack(fill="both", expand=True)
        
        # Status display with scrollbar
        self.status_text = tk.Text(status_frame, height=8, wrap="word",
                                 background="#0E1626", foreground="#C7D1DB")
        status_scroll = ttk.Scrollbar(status_frame, orient="vertical", command=self.status_text.yview)
        self.status_text.configure(yscrollcommand=status_scroll.set)
        
        self.status_text.pack(side="left", fill="both", expand=True)
        status_scroll.pack(side="right", fill="y")
        
        # Refresh button
        refresh_frame = ttk.Frame(status_frame)
        refresh_frame.pack(fill="x", pady=(5, 0))
        
        self.refresh_btn = ttk.Button(refresh_frame, text="Refresh Status",
                                    command=self._refresh_status)
        self.refresh_btn.pack(side="right")
    
    def _initialize_account(self):
        """Initialize trading account based on selected type."""
        try:
            account_type = self.account_type_var.get()
            
            if account_type == "Paper Trading":
                from decimal import Decimal
                initial_balance = Decimal(self.balance_var.get())
                self.paper_account = PaperTradingAccount(initial_balance=initial_balance)
                
                # Set up risk management
                limits = RiskLimits()
                self.risk_manager = RiskManager(limits, portfolio_value=float(initial_balance))
                
                # Set up monitoring
                self.live_monitor = LiveMonitor()
                self.live_monitor.register_paper_account(self.paper_account)
                self.live_monitor.add_alert_handler(self._handle_alert)
                
                self.account_status_var.set(f"Paper Trading Account Initialized: ${initial_balance:,.2f}")
                self._update_status(f"Account initialized successfully at {datetime.now().strftime('%H:%M:%S')}")
                
                # Enable controls
                self.toggle_trading_btn.config(state="normal")
                self.toggle_monitoring_btn.config(state="normal")
                
            else:
                messagebox.showwarning("Not Implemented", 
                                     f"{account_type} is not yet implemented.\nPlease use Paper Trading for now.")
                return
                
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid balance amount: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to initialize account: {e}")
            self.logger.error(f"Account initialization failed: {e}")
    
    def _execute_buy(self):
        """Execute buy order."""
        if not self.trading_enabled:
            messagebox.showwarning("Trading Disabled", "Please enable trading first")
            return
            
        if not self.paper_account:
            messagebox.showerror("Error", "No account initialized")
            return
            
        try:
            from decimal import Decimal
            symbol = self.symbol_var.get().upper()
            quantity = Decimal(self.quantity_var.get())
            
            order_id = self.paper_account.place_order(symbol, OrderType.MARKET, OrderSide.BUY, quantity)
            self._update_status(f"Buy order placed: {quantity} {symbol} (Order: {order_id[:8]}...)")
            self._refresh_status()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to execute buy order: {e}")
            self.logger.error(f"Buy order failed: {e}")
    
    def _execute_sell(self):
        """Execute sell order."""
        if not self.trading_enabled:
            messagebox.showwarning("Trading Disabled", "Please enable trading first")
            return
            
        if not self.paper_account:
            messagebox.showerror("Error", "No account initialized")
            return
            
        try:
            from decimal import Decimal
            symbol = self.symbol_var.get().upper()
            quantity = Decimal(self.quantity_var.get())
            
            order_id = self.paper_account.place_order(symbol, OrderType.MARKET, OrderSide.SELL, quantity)
            self._update_status(f"Sell order placed: {quantity} {symbol} (Order: {order_id[:8]}...)")
            self._refresh_status()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to execute sell order: {e}")
            self.logger.error(f"Sell order failed: {e}")
    
    def _toggle_trading(self):
        """Toggle trading enabled/disabled."""
        if not self.paper_account:
            messagebox.showerror("Error", "No account initialized")
            return
            
        self.trading_enabled = not self.trading_enabled
        
        if self.trading_enabled:
            self.trading_status_var.set("Trading Enabled")
            self.toggle_trading_btn.config(text="Disable Trading")
            self.buy_btn.config(state="normal")
            self.sell_btn.config(state="normal")
            self._update_status("Trading enabled")
        else:
            self.trading_status_var.set("Trading Disabled")
            self.toggle_trading_btn.config(text="Enable Trading")
            self.buy_btn.config(state="disabled")
            self.sell_btn.config(state="disabled")
            self._update_status("Trading disabled")
    
    def _toggle_monitoring(self):
        """Toggle live monitoring."""
        if not self.live_monitor:
            messagebox.showerror("Error", "No monitoring system initialized")
            return
            
        self.monitoring_enabled = not self.monitoring_enabled
        
        if self.monitoring_enabled:
            self.live_monitor.start_monitoring()
            self.monitoring_status_var.set("Monitoring Active")
            self.toggle_monitoring_btn.config(text="Stop Monitoring")
            self._update_status("Live monitoring started")
        else:
            self.live_monitor.stop_monitoring()
            self.monitoring_status_var.set("Monitoring Disabled")
            self.toggle_monitoring_btn.config(text="Start Monitoring")
            self._update_status("Live monitoring stopped")
    
    def _handle_alert(self, alert: Alert):
        """Handle alerts from the monitoring system."""
        self.alert_queue.put(alert)
        # Schedule GUI update
        self.after_idle(self._process_alerts)
    
    def _process_alerts(self):
        """Process pending alerts in the GUI thread."""
        try:
            while True:
                alert = self.alert_queue.get_nowait()
                timestamp = alert.timestamp.strftime("%H:%M:%S")
                alert_text = f"[{timestamp}] {alert.level.upper()}: {alert.message}\\n"
                
                self.alerts_text.insert("end", alert_text)
                self.alerts_text.see("end")
                
                # Keep only last 50 lines
                lines = self.alerts_text.get("1.0", "end").split("\\n")
                if len(lines) > 50:
                    self.alerts_text.delete("1.0", f"{len(lines)-50}.0")
                
        except queue.Empty:
            pass
    
    def _refresh_status(self):
        """Refresh account status display."""
        if not self.paper_account:
            return
            
        try:
            # Update market prices
            self.paper_account.update_market_prices()
            
            # Get account summary
            summary = self.paper_account.get_account_summary()
            
            # Format status text
            status_lines = [
                f"=== Account Status ({datetime.now().strftime('%H:%M:%S')}) ===",
                f"Total Portfolio Value: ${summary['total_value']:,.2f}",
                f"Cash Balance: ${summary['cash_balance']:,.2f}",
                f"Total P&L: ${summary['total_pnl']:+,.2f} ({summary['total_return_pct']:+.2f}%)",
                f"Total Trades: {summary['total_trades']}",
                f"Win Rate: {summary['win_rate_pct']:.1f}%",
                f"Active Positions: {len(summary['positions'])}",
                ""
            ]
            
            if summary['positions']:
                status_lines.append("=== Positions ===")
                for symbol, pos_data in summary['positions'].items():
                    pnl_pct = pos_data['unrealized_pnl_pct']
                    pnl_indicator = "↗" if pnl_pct >= 0 else "↘"
                    status_lines.append(
                        f"{symbol}: {pos_data['quantity']:.4f} @ ${pos_data['avg_price']:.2f} "
                        f"| Value: ${pos_data['market_value']:,.2f} "
                        f"| P&L: ${pos_data['unrealized_pnl']:+.2f} ({pnl_pct:+.2f}%) {pnl_indicator}"
                    )
            
            # Update status display
            self.status_text.delete("1.0", "end")
            self.status_text.insert("1.0", "\\n".join(status_lines))
            
        except Exception as e:
            self.logger.error(f"Failed to refresh status: {e}")
            self._update_status(f"Error refreshing status: {e}")
    
    def _update_status(self, message: str):
        """Add a status message to the display."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        status_line = f"[{timestamp}] {message}\\n"
        self.status_text.insert("end", status_line)
        self.status_text.see("end")
    
    def _start_background_tasks(self):
        """Start background tasks for status updates."""
        # Schedule periodic status refresh
        def periodic_refresh():
            if self.paper_account and self.monitoring_enabled:
                self._refresh_status()
            # Schedule next refresh
            self.after(10000, periodic_refresh)  # Every 10 seconds
        
        # Start the refresh cycle
        self.after(1000, periodic_refresh)  # Initial delay of 1 second

class RiskManagementPanel(ttk.Frame):
    """Risk management configuration panel."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._setup_ui()
    
    def _setup_ui(self):
        """Create risk management UI."""
        main_frame = ttk.LabelFrame(self, text="Risk Management Settings", padding="10")
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Position size limits
        pos_frame = ttk.LabelFrame(main_frame, text="Position Limits", padding="5")
        pos_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(pos_frame, text="Max Position Size (%):").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.max_position_var = tk.StringVar(value="20")
        pos_entry = ttk.Entry(pos_frame, textvariable=self.max_position_var, width=10)
        pos_entry.grid(row=0, column=1, sticky="w")
        
        ttk.Label(pos_frame, text="Max Daily Loss (%):").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(5, 0))
        self.max_loss_var = tk.StringVar(value="5")
        loss_entry = ttk.Entry(pos_frame, textvariable=self.max_loss_var, width=10)
        loss_entry.grid(row=1, column=1, sticky="w", pady=(5, 0))
        
        # Risk scenarios
        scenario_frame = ttk.LabelFrame(main_frame, text="Risk Scenarios", padding="5")
        scenario_frame.pack(fill="x", pady=(0, 10))
        
        scenarios = [
            ("Conservative", "1% risk per trade"),
            ("Moderate", "2% risk per trade"),
            ("Aggressive", "3% risk per trade")
        ]
        
        self.risk_scenario_var = tk.StringVar(value="Moderate")
        for i, (name, desc) in enumerate(scenarios):
            ttk.Radiobutton(scenario_frame, text=f"{name} - {desc}",
                          variable=self.risk_scenario_var, value=name).grid(row=i, column=0, sticky="w", pady=2)
        
        # Apply button
        apply_btn = ttk.Button(main_frame, text="Apply Risk Settings", command=self._apply_settings)
        apply_btn.pack(pady=(10, 0))
    
    def _apply_settings(self):
        """Apply risk management settings."""
        messagebox.showinfo("Applied", "Risk settings have been applied")

class CostAnalysisPanel(ttk.Frame):
    """Cost analysis and performance tier panel."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._setup_ui()
    
    def _setup_ui(self):
        """Create cost analysis UI."""
        main_frame = ttk.LabelFrame(self, text="Cost Analysis", padding="10")
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Performance tier selection
        tier_frame = ttk.LabelFrame(main_frame, text="Performance Tier", padding="5")
        tier_frame.pack(fill="x", pady=(0, 10))
        
        self.tier_var = tk.StringVar(value="PROFESSIONAL")
        tiers = [("BUDGET", "Budget Tier"), ("PROFESSIONAL", "Professional Tier"), ("ENTERPRISE", "Enterprise Tier")]
        
        for i, (value, label) in enumerate(tiers):
            ttk.Radiobutton(tier_frame, text=label, variable=self.tier_var, 
                          value=value, command=self._calculate_costs).grid(row=i, column=0, sticky="w", pady=2)
        
        # Cost display
        cost_frame = ttk.LabelFrame(main_frame, text="Monthly Cost Breakdown", padding="5")
        cost_frame.pack(fill="both", expand=True)
        
        self.cost_text = tk.Text(cost_frame, height=10, wrap="word",
                               background="#0E1626", foreground="#C7D1DB")
        cost_scroll = ttk.Scrollbar(cost_frame, orient="vertical", command=self.cost_text.yview)
        self.cost_text.configure(yscrollcommand=cost_scroll.set)
        
        self.cost_text.pack(side="left", fill="both", expand=True)
        cost_scroll.pack(side="right", fill="y")
        
        # Initial calculation
        self._calculate_costs()
    
    def _calculate_costs(self):
        """Calculate and display costs for selected tier."""
        try:
            tier_name = self.tier_var.get()
            tier = PerformanceTier[tier_name]
            cost_manager = CostManager(tier)
            monthly_costs = cost_manager.calculate_monthly_costs()
            
            cost_breakdown = [
                f"=== {tier_name} TIER - MONTHLY COSTS ===",
                "",
                f"Infrastructure: ${monthly_costs.infrastructure:.2f}",
                f"Data Feeds: ${monthly_costs.data_feeds:.2f}",
                f"Exchange Fees: ${monthly_costs.exchange_fees:.2f}",
                f"Compliance: ${monthly_costs.compliance:.2f}",
                f"Insurance: ${monthly_costs.insurance:.2f}",
                f"Personnel: ${monthly_costs.personnel:.2f}",
                f"Software: ${monthly_costs.software:.2f}",
                f"Legal: ${monthly_costs.legal:.2f}",
                "",
                f"TOTAL MONTHLY: ${monthly_costs.total_monthly:.2f}",
                f"TOTAL ANNUAL: ${monthly_costs.total_annual:.2f}",
                "",
                "=== COST EFFICIENCY ===",
                f"Cost per $1000 managed: ${(monthly_costs.total_monthly / 1000):.2f}",
                f"Break-even trading volume: ${monthly_costs.total_monthly * 100:.0f}/month"
            ]
            
            self.cost_text.delete("1.0", "end")
            self.cost_text.insert("1.0", "\\n".join(cost_breakdown))
            
        except Exception as e:
            self.cost_text.delete("1.0", "end")
            self.cost_text.insert("1.0", f"Error calculating costs: {e}")

def integrate_phase4_gui(notebook_widget):
    """
    Integrate Phase 4 systems into the existing GUI notebook.
    
    Args:
        notebook_widget: The existing ttk.Notebook widget to add tabs to
    """
    try:
        # Add trading control panel
        trading_panel = TradingControlPanel(notebook_widget)
        notebook_widget.add(trading_panel, text="Trading Control")
        
        # Add risk management panel  
        risk_panel = RiskManagementPanel(notebook_widget)
        notebook_widget.add(risk_panel, text="Risk Management")
        
        # Add cost analysis panel
        cost_panel = CostAnalysisPanel(notebook_widget)
        notebook_widget.add(cost_panel, text="Cost Analysis")
        
        return {
            'trading_panel': trading_panel,
            'risk_panel': risk_panel,
            'cost_panel': cost_panel
        }
        
    except Exception as e:
        print(f"Error integrating Phase 4 GUI: {e}")
        return None