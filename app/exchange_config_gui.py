#!/usr/bin/env python3
"""
PowerTraderAI+ Exchange Configuration GUI
GUI-based tool for setting up and managing cryptocurrency exchanges
"""

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import font, messagebox, ttk
from typing import Dict, Optional

import coinbase_auth
import pt_secrets
from pt_exchange_abstraction import (
    ConnectionStatus,
    ConnectionTestResult,
    ExchangeType,
)
from pt_multi_exchange import ExchangeConfigManager, MultiExchangeManager


# Exchanges whose credentials are not a plain "API key + secret" pair. Anything not
# listed uses the default labels and a single-line secret.
DEFAULT_FIELDS = {"key_label": "API Key:", "secret_label": "API Secret:", "multiline": False}
EXCHANGE_FIELDS = {
    # CDP API key: key *name* + EC *private key* (PEM, several lines).
    "coinbase": {
        "key_label": "Key name:",
        "secret_label": "Private key (PEM):",
        "multiline": True,
    },
}
SAVED_SECRET_HINT = "A private key is already saved. Leave this box empty to keep it."
ENV_CREDENTIALS_HINT = (
    "Credentials for this exchange come from environment variables ({names}); "
    "they take precedence over anything saved here."
)


def exchange_fields(exchange_name: str) -> dict:
    return EXCHANGE_FIELDS.get(exchange_name, DEFAULT_FIELDS)


def saved_secret_hint(exchange_name: str, source: str) -> str:
    """Shown instead of a saved secret, which is never echoed into the form."""
    if source == pt_secrets.SOURCE_ENV:
        return ENV_CREDENTIALS_HINT.format(names=", ".join(pt_secrets.env_var_names(exchange_name)))
    fields = exchange_fields(exchange_name)
    if fields["multiline"]:
        return SAVED_SECRET_HINT
    label = fields["secret_label"].rstrip(":")
    return f"{label} is already saved. Leave the box empty to keep it."


STATUS_HEADLINES = {
    ConnectionStatus.OK: "connection successful",
    ConnectionStatus.INVALID_CREDENTIALS: "credentials not valid",
    ConnectionStatus.AUTH_FAILED: "authentication failed",
    ConnectionStatus.PERMISSION_DENIED: "permission denied",
    ConnectionStatus.NETWORK_ERROR: "network error",
    ConnectionStatus.ENDPOINT_ERROR: "unexpected response",
    ConnectionStatus.UNSUPPORTED: "not tested",
}
_STATUS_ICONS = {
    ConnectionStatus.OK: "✅",
    ConnectionStatus.INVALID_CREDENTIALS: "❌",
    ConnectionStatus.AUTH_FAILED: "🔑❌",
    ConnectionStatus.PERMISSION_DENIED: "🚫",
    ConnectionStatus.NETWORK_ERROR: "🌐❌",
    ConnectionStatus.ENDPOINT_ERROR: "⚠️",
    ConnectionStatus.UNSUPPORTED: "ℹ️",
}


def format_test_result(exchange_name: str, result: ConnectionTestResult) -> str:
    """One readable block for the Test Results pane (no credentials in it)."""
    return (
        f"{_STATUS_ICONS[result.status]} {exchange_name.title()}: "
        f"{STATUS_HEADLINES[result.status]}\n   {result.message}"
    )


class ExchangeConfigGUI:
    def __init__(self, parent=None):
        """Initialize the Exchange Configuration GUI"""
        if parent:
            self.window = tk.Toplevel(parent)
        else:
            self.window = tk.Tk()

        self.window.title("PowerTrader AI - Exchange Configuration")
        self.window.geometry("1000x800")
        self.window.minsize(900, 700)

        # Configure dark theme colors (matching main hub)
        self.DARK_BG = "#070B10"
        self.DARK_BG2 = "#0B1220"
        self.DARK_PANEL = "#0E1626"
        self.DARK_PANEL2 = "#121C2F"
        self.DARK_BORDER = "#243044"
        self.DARK_FG = "#C7D1DB"
        self.DARK_MUTED = "#8B949E"
        self.DARK_ACCENT = "#00FF66"
        self.DARK_ACCENT2 = "#00E5FF"
        self.DARK_SELECT_BG = "#17324A"
        self.DARK_SELECT_FG = "#00FF66"

        self.window.configure(bg=self.DARK_BG)

        # Initialize exchange configuration
        self.config_manager = ExchangeConfigManager()
        self.multi_exchange = MultiExchangeManager(self.config_manager)

        # Load comprehensive exchange list
        self.all_exchanges = self.load_all_supported_exchanges()

        # Apply dark theme styling first
        self.apply_dark_theme()

        self.setup_gui()
        self.refresh_exchange_list()

    def load_all_supported_exchanges(self):
        """Load all supported exchanges from data_provider_config.json"""
        config_path = os.path.join(
            os.path.dirname(__file__), "data_provider_config.json"
        )
        exchanges_list = []

        try:
            with open(config_path, "r") as f:
                config = json.load(f)

            exchanges = config.get("exchanges", {})

            # Process centralized exchanges
            centralized = exchanges.get("centralized", {})
            for tier, tier_exchanges in centralized.items():
                for exchange_id, exchange_info in tier_exchanges.items():
                    regions = ", ".join(exchange_info.get("regions", ["Global"]))
                    exchanges_list.append(
                        (
                            exchange_id,
                            regions,
                            "CEX",
                            exchange_info.get("name", exchange_id.title()),
                            tier.upper(),
                        )
                    )

            # Process DeFi exchanges
            defi = exchanges.get("defi", {})
            for tier, tier_exchanges in defi.items():
                for exchange_id, exchange_info in tier_exchanges.items():
                    regions = ", ".join(exchange_info.get("regions", ["Global"]))
                    exchanges_list.append(
                        (
                            exchange_id,
                            regions,
                            "DeFi",
                            exchange_info.get("name", exchange_id.title()),
                            tier.upper(),
                        )
                    )

            # Process derivatives exchanges
            derivatives = exchanges.get("derivatives", {})
            for tier, tier_exchanges in derivatives.items():
                for exchange_id, exchange_info in tier_exchanges.items():
                    regions = ", ".join(exchange_info.get("regions", ["Global"]))
                    exchanges_list.append(
                        (
                            exchange_id,
                            regions,
                            "Derivatives",
                            exchange_info.get("name", exchange_id.title()),
                            tier.upper(),
                        )
                    )

            # Process specialized exchanges
            specialized = exchanges.get("specialized", {})
            for tier, tier_exchanges in specialized.items():
                for exchange_id, exchange_info in tier_exchanges.items():
                    regions = ", ".join(exchange_info.get("regions", ["Global"]))
                    exchanges_list.append(
                        (
                            exchange_id,
                            regions,
                            "Specialized",
                            exchange_info.get("name", exchange_id.title()),
                            tier.upper(),
                        )
                    )

            # Process cross-chain
            cross_chain = exchanges.get("cross_chain", {})
            for tier, tier_exchanges in cross_chain.items():
                for exchange_id, exchange_info in tier_exchanges.items():
                    regions = ", ".join(exchange_info.get("regions", ["Global"]))
                    exchanges_list.append(
                        (
                            exchange_id,
                            regions,
                            "Cross-Chain",
                            exchange_info.get("name", exchange_id.title()),
                            tier.upper(),
                        )
                    )

        except Exception as e:
            print(f"Error loading exchange config: {e}")
            # Fallback to basic list
            exchanges_list = [
                ("binance", "Global", "CEX", "Binance", "TIER1"),
                ("kraken", "Global", "CEX", "Kraken", "TIER1"),
                ("kucoin", "Global", "CEX", "KuCoin", "TIER1"),
                ("coinbase", "US/EU", "CEX", "Coinbase", "TIER1"),
            ]

        return exchanges_list

    def apply_dark_theme(self):
        """Apply consistent dark theme to all widgets"""
        # Configure ttk styles to match main hub
        style = ttk.Style()
        style.theme_use("clam")

        # Configure notebook
        style.configure(
            "TNotebook", background=self.DARK_BG, borderwidth=0, tabmargins=[2, 5, 2, 0]
        )
        style.configure(
            "TNotebook.Tab",
            background=self.DARK_PANEL,
            foreground=self.DARK_FG,
            padding=[12, 8],
            borderwidth=1,
            focuscolor="none",
        )
        style.map(
            "TNotebook.Tab",
            background=[
                ("selected", self.DARK_PANEL2),
                ("active", self.DARK_SELECT_BG),
            ],
            foreground=[("selected", self.DARK_ACCENT)],
        )

        # Configure frames and labels
        style.configure("TFrame", background=self.DARK_BG)
        style.configure(
            "TLabelFrame",
            background=self.DARK_BG,
            foreground=self.DARK_ACCENT,
            borderwidth=1,
            relief="solid",
            bordercolor=self.DARK_BORDER,
        )
        style.configure("TLabel", background=self.DARK_BG, foreground=self.DARK_FG)

        # Configure treeview
        style.configure(
            "Treeview",
            background=self.DARK_PANEL,
            foreground=self.DARK_FG,
            fieldbackground=self.DARK_PANEL,
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "Treeview.Heading",
            background=self.DARK_PANEL2,
            foreground=self.DARK_ACCENT,
            borderwidth=1,
            relief="solid",
        )
        style.map(
            "Treeview",
            background=[("selected", self.DARK_SELECT_BG)],
            foreground=[("selected", self.DARK_SELECT_FG)],
        )
        style.map("Treeview.Heading", background=[("active", self.DARK_SELECT_BG)])

        # Configure buttons
        style.configure(
            "TButton",
            background=self.DARK_PANEL,
            foreground=self.DARK_FG,
            borderwidth=1,
            focuscolor="none",
            relief="solid",
        )
        style.map(
            "TButton",
            background=[("active", self.DARK_SELECT_BG), ("pressed", self.DARK_ACCENT)],
            foreground=[("active", self.DARK_ACCENT), ("pressed", self.DARK_BG)],
        )

        # Configure entry and combobox
        style.configure(
            "TEntry",
            fieldbackground=self.DARK_PANEL,
            foreground=self.DARK_FG,
            borderwidth=1,
            insertcolor=self.DARK_FG,
            relief="solid",
        )
        style.map(
            "TEntry",
            focuscolor=[("!focus", self.DARK_BORDER)],
            bordercolor=[("focus", self.DARK_ACCENT)],
        )

        style.configure(
            "TCombobox",
            fieldbackground=self.DARK_PANEL,
            foreground=self.DARK_FG,
            borderwidth=1,
            selectbackground=self.DARK_SELECT_BG,
            selectforeground=self.DARK_SELECT_FG,
            relief="solid",
        )
        style.map(
            "TCombobox",
            focuscolor=[("!focus", self.DARK_BORDER)],
            bordercolor=[("focus", self.DARK_ACCENT)],
        )

        # Configure scrollbars
        style.configure(
            "TScrollbar",
            background=self.DARK_PANEL,
            troughcolor=self.DARK_BG,
            borderwidth=1,
            arrowcolor=self.DARK_FG,
            relief="solid",
        )
        style.map("TScrollbar", background=[("active", self.DARK_SELECT_BG)])

        # Configure separator
        style.configure("TSeparator", background=self.DARK_BORDER)

        # Configure checkboxes and radiobuttons
        style.configure(
            "TCheckbutton",
            background=self.DARK_BG,
            foreground=self.DARK_FG,
            focuscolor="none",
            borderwidth=0,
        )
        style.map(
            "TCheckbutton",
            background=[("active", self.DARK_BG)],
            foreground=[("active", self.DARK_ACCENT)],
        )

        style.configure(
            "TRadiobutton",
            background=self.DARK_BG,
            foreground=self.DARK_FG,
            focuscolor="none",
            borderwidth=0,
        )
        style.map(
            "TRadiobutton",
            background=[("active", self.DARK_BG)],
            foreground=[("active", self.DARK_ACCENT)],
        )

    def setup_gui(self):
        """Set up the main GUI layout"""
        # Main container
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Title
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))

        title_label = ttk.Label(
            title_frame,
            text="🚀 Exchange Configuration Manager",
            font=("Arial", 16, "bold"),
            foreground=self.DARK_ACCENT,
        )
        title_label.pack(side=tk.LEFT)

        # Create notebook for different sections
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Exchange List Tab
        self.setup_exchange_list_tab()

        # Exchange Setup Tab
        self.setup_exchange_setup_tab()

        # Testing Tab
        self.setup_testing_tab()

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(
            main_frame,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            bg=self.DARK_PANEL,
            fg=self.DARK_FG,
            borderwidth=1,
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

    def setup_exchange_list_tab(self):
        """Set up the exchange list and status tab"""
        list_frame = ttk.Frame(self.notebook)
        self.notebook.add(list_frame, text="📊 Exchange Status")

        # Header
        header_frame = ttk.Frame(list_frame)
        header_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(
            header_frame, text="Available Exchanges", font=("Arial", 12, "bold")
        ).pack(side=tk.LEFT)

        refresh_btn = ttk.Button(
            header_frame, text="🔄 Refresh", command=self.refresh_exchange_list
        )
        refresh_btn.pack(side=tk.RIGHT)

        # Exchange list with treeview
        tree_frame = ttk.Frame(list_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Create treeview with scrollbar
        self.exchange_tree = ttk.Treeview(
            tree_frame,
            columns=("status", "credentials", "type", "region", "tier"),
            show="tree headings",
        )

        # Configure columns
        self.exchange_tree.heading("#0", text="Exchange")
        self.exchange_tree.heading("status", text="Status")
        self.exchange_tree.heading("credentials", text="Credentials")
        self.exchange_tree.heading("type", text="Type")
        self.exchange_tree.heading("region", text="Region")
        self.exchange_tree.heading("tier", text="Tier")

        self.exchange_tree.column("#0", width=150)
        self.exchange_tree.column("status", width=80)
        self.exchange_tree.column("credentials", width=90)
        self.exchange_tree.column("type", width=90)
        self.exchange_tree.column("region", width=150)
        self.exchange_tree.column("tier", width=80)

        scrollbar = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=self.exchange_tree.yview
        )
        self.exchange_tree.configure(yscrollcommand=scrollbar.set)

        self.exchange_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Control buttons
        button_frame = tk.Frame(list_frame, bg=self.DARK_BG)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Button(
            button_frame,
            text="➕ Configure Selected",
            command=self.configure_selected_exchange,
        ).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(
            button_frame, text="✅ Enable", command=self.enable_selected_exchange
        ).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(
            button_frame, text="❌ Disable", command=self.disable_selected_exchange
        ).pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(
            button_frame,
            text="🗑️ Remove Credentials",
            command=self.remove_selected_credentials,
        ).pack(side=tk.LEFT)

    def setup_exchange_setup_tab(self):
        """Set up the exchange configuration tab"""
        setup_frame = tk.Frame(self.notebook, bg=self.DARK_BG)
        self.notebook.add(setup_frame, text="⚙️ Setup Exchange")

        # Exchange selection
        select_frame = tk.LabelFrame(
            setup_frame,
            text="Select Exchange",
            bg=self.DARK_BG,
            fg=self.DARK_ACCENT,
            bd=1,
            relief="solid",
            highlightbackground=self.DARK_BORDER,
        )
        select_frame.pack(fill=tk.X, padx=10, pady=10)

        self.exchange_var = tk.StringVar()
        self.exchange_combo = ttk.Combobox(
            select_frame, textvariable=self.exchange_var, state="readonly", width=20
        )
        self.exchange_combo.pack(side=tk.LEFT, padx=10, pady=10)
        self.exchange_combo.bind("<<ComboboxSelected>>", self.on_exchange_selected)

        # Update exchange list from comprehensive configuration
        exchange_ids = [exchange_id for exchange_id, _, _, _, _ in self.all_exchanges]
        self.exchange_combo["values"] = sorted(set(exchange_ids))

        # Configuration frame
        self.config_frame = tk.LabelFrame(
            setup_frame,
            text="Configuration",
            bg=self.DARK_BG,
            fg=self.DARK_ACCENT,
            bd=1,
            relief="solid",
            highlightbackground=self.DARK_BORDER,
        )
        self.config_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Instructions text
        self.instructions_text = tk.Text(
            self.config_frame,
            height=8,
            wrap=tk.WORD,
            bg=self.DARK_PANEL,
            fg=self.DARK_FG,
            font=("Consolas", 10),
            insertbackground=self.DARK_ACCENT,
            selectbackground=self.DARK_SELECT_BG,
            selectforeground=self.DARK_SELECT_FG,
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
        )
        self.instructions_text.pack(fill=tk.X, padx=10, pady=(10, 0))

        # Credentials input frame
        creds_frame = tk.Frame(self.config_frame, bg=self.DARK_BG)
        creds_frame.pack(fill=tk.X, padx=10, pady=10)

        # API Key
        self.api_key_label = ttk.Label(creds_frame, text=DEFAULT_FIELDS["key_label"])
        self.api_key_label.grid(row=0, column=0, sticky="w", pady=2)
        self.api_key_var = tk.StringVar()
        self.api_key_entry = ttk.Entry(
            creds_frame, textvariable=self.api_key_var, width=50
        )
        self.api_key_entry.grid(row=0, column=1, padx=(10, 0), pady=2)

        # API Secret
        self.api_secret_label = ttk.Label(
            creds_frame, text=DEFAULT_FIELDS["secret_label"]
        )
        self.api_secret_label.grid(row=1, column=0, sticky="nw", pady=2)
        self.api_secret_var = tk.StringVar()
        self.api_secret_entry = ttk.Entry(
            creds_frame, textvariable=self.api_secret_var, width=50, show="*"
        )
        self.api_secret_entry.grid(row=1, column=1, padx=(10, 0), pady=2)

        # Multi-line secret (Coinbase private key). Shown instead of the entry above.
        self.api_secret_text = tk.Text(
            creds_frame,
            width=50,
            height=7,
            wrap=tk.NONE,
            bg=self.DARK_PANEL,
            fg=self.DARK_FG,
            font=("Consolas", 9),
            insertbackground=self.DARK_ACCENT,
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
        )
        self.secret_hint_var = tk.StringVar()
        self.secret_hint_label = ttk.Label(
            creds_frame, textvariable=self.secret_hint_var, wraplength=480
        )

        # Passphrase (for KuCoin)
        self.passphrase_label = ttk.Label(creds_frame, text="Passphrase:")
        self.passphrase_var = tk.StringVar()
        self.passphrase_entry = ttk.Entry(
            creds_frame, textvariable=self.passphrase_var, width=50
        )

        creds_frame.columnconfigure(1, weight=1)

        # Save button
        save_button_frame = tk.Frame(self.config_frame, bg=self.DARK_BG)
        save_button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Button(
            save_button_frame,
            text="💾 Save Configuration",
            command=self.save_exchange_config,
        ).pack(side=tk.RIGHT)

        ttk.Button(
            save_button_frame,
            text="📋 Test Connection",
            command=self.test_exchange_connection,
        ).pack(side=tk.RIGHT, padx=(0, 10))

    def setup_testing_tab(self):
        """Set up the connection testing tab"""
        test_frame = tk.Frame(self.notebook, bg=self.DARK_BG)
        self.notebook.add(test_frame, text="🧪 Test Connections")

        # Test all button
        test_all_frame = tk.Frame(test_frame, bg=self.DARK_BG)
        test_all_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(
            test_all_frame,
            text="🧪 Test All Configured Exchanges",
            command=self.test_all_exchanges,
        ).pack(side=tk.LEFT)

        # Results area
        results_frame = tk.LabelFrame(
            test_frame,
            text="Test Results",
            bg=self.DARK_BG,
            fg=self.DARK_ACCENT,
            bd=1,
            relief="solid",
            highlightbackground=self.DARK_BORDER,
        )
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.results_text = tk.Text(
            results_frame,
            bg=self.DARK_PANEL,
            fg=self.DARK_FG,
            font=("Consolas", 10),
            insertbackground=self.DARK_ACCENT,
            selectbackground=self.DARK_SELECT_BG,
            selectforeground=self.DARK_SELECT_FG,
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
        )

        results_scrollbar = ttk.Scrollbar(
            results_frame, orient=tk.VERTICAL, command=self.results_text.yview
        )
        self.results_text.configure(yscrollcommand=results_scrollbar.set)

        self.results_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        results_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh_exchange_list(self):
        """Refresh the exchange list display"""
        # Clear existing items
        for item in self.exchange_tree.get_children():
            self.exchange_tree.delete(item)

        config = self.config_manager.load_config()

        # Add all exchanges from comprehensive list
        for exchange_id, region, ex_type, display_name, tier in self.all_exchanges:
            # Check status - handle both dict and dataclass configurations
            enabled = False
            has_creds = False

            if config:
                if hasattr(config, "exchanges"):
                    # Dataclass structure
                    for ex_config in config.exchanges:
                        if (
                            hasattr(ex_config, "exchange_type")
                            and ex_config.exchange_type.lower() == exchange_id
                        ):
                            enabled = ex_config.enabled
                            has_creds = bool(ex_config.api_key)
                            break
                elif isinstance(config, dict):
                    # Dictionary structure
                    exchange_config = config.get("exchanges", {}).get(exchange_id, {})
                    enabled = exchange_config.get("enabled", False)
                    has_creds = bool(exchange_config.get("api_key"))

            status = "✅ Enabled" if enabled else "❌ Disabled"
            creds = "✅ Set" if has_creds else "❌ None"

            self.exchange_tree.insert(
                "",
                "end",
                text=display_name,
                values=(status, creds, ex_type, region, tier),
            )

        self.status_var.set(f"Loaded {len(self.all_exchanges)} exchanges")

    def configure_selected_exchange(self):
        """Configure the selected exchange"""
        selection = self.exchange_tree.selection()
        if not selection:
            messagebox.showwarning(
                "No Selection", "Please select an exchange to configure"
            )
            return

        item = self.exchange_tree.item(selection[0])
        display_name = item["text"]

        # Find the exchange ID from display name
        exchange_id = None
        for ex_id, _, _, ex_display, _ in self.all_exchanges:
            if ex_display == display_name:
                exchange_id = ex_id
                break

        if not exchange_id:
            messagebox.showerror(
                "Error", f"Could not find exchange ID for {display_name}"
            )
            return

        # Switch to setup tab and select exchange
        self.notebook.select(1)  # Switch to setup tab
        self.exchange_var.set(exchange_id)
        self.on_exchange_selected()

    def enable_selected_exchange(self):
        """Enable the selected exchange"""
        selection = self.exchange_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an exchange")
            return

        item = self.exchange_tree.item(selection[0])
        display_name = item["text"]

        # Find the exchange ID from display name
        exchange_name = None
        for ex_id, _, _, ex_display, _ in self.all_exchanges:
            if ex_display == display_name:
                exchange_name = ex_id
                break

        if not exchange_name:
            messagebox.showerror(
                "Error", f"Could not find exchange ID for {display_name}"
            )
            return

        self.config_manager.enable_exchange(exchange_name, True)
        self.refresh_exchange_list()
        self.status_var.set(f"{exchange_name.title()} enabled")

    def disable_selected_exchange(self):
        """Disable the selected exchange"""
        selection = self.exchange_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an exchange")
            return

        item = self.exchange_tree.item(selection[0])
        display_name = item["text"]

        # Find the exchange ID from display name
        exchange_name = None
        for ex_id, _, _, ex_display, _ in self.all_exchanges:
            if ex_display == display_name:
                exchange_name = ex_id
                break

        if not exchange_name:
            messagebox.showerror(
                "Error", f"Could not find exchange ID for {display_name}"
            )
            return

        self.config_manager.enable_exchange(exchange_name, False)
        self.refresh_exchange_list()
        self.status_var.set(f"{exchange_name.title()} disabled")

    def remove_selected_credentials(self):
        """Remove credentials for selected exchange"""
        selection = self.exchange_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an exchange")
            return

        item = self.exchange_tree.item(selection[0])
        display_name = item["text"]

        # Find the exchange ID from display name
        exchange_name = None
        for ex_id, _, _, ex_display, _ in self.all_exchanges:
            if ex_display == display_name:
                exchange_name = ex_id
                break

        if not exchange_name:
            messagebox.showerror(
                "Error", f"Could not find exchange ID for {display_name}"
            )
            return

        if messagebox.askyesno(
            "Confirm", f"Remove credentials for {exchange_name.title()}?"
        ):
            self.config_manager.update_exchange_credentials(exchange_name, "", "", "")
            self.refresh_exchange_list()
            self.status_var.set(f"Credentials removed for {exchange_name.title()}")

    def on_exchange_selected(self, event=None):
        """Handle exchange selection in setup tab"""
        exchange_name = self.exchange_var.get()
        if not exchange_name:
            return

        # Update instructions
        instructions = self.get_exchange_instructions(exchange_name)
        self.instructions_text.delete(1.0, tk.END)
        self.instructions_text.insert(1.0, instructions)

        # Show/hide passphrase field for KuCoin
        if exchange_name == "kucoin":
            self.passphrase_label.grid(row=2, column=0, sticky="w", pady=2)
            self.passphrase_entry.grid(row=2, column=1, padx=(10, 0), pady=2)
        else:
            self.passphrase_label.grid_remove()
            self.passphrase_entry.grid_remove()

        # Load existing credentials (pt_secrets: environment, then OS keyring)
        config = self.config_manager.load_config()
        api_key = ""
        api_secret = ""
        source = ""

        if config and hasattr(config, "exchanges"):
            # Dataclass structure
            for ex_config in config.exchanges:
                if (
                    hasattr(ex_config, "exchange_type")
                    and ex_config.exchange_type.lower() == exchange_name
                ):
                    api_key = ex_config.api_key or ""
                    api_secret = ex_config.api_secret or ""
                    source = ex_config.credential_source
                    break

        # The key name / API key identifies the key and is shown; a saved secret,
        # private key or passphrase is never echoed back into the form.
        self.api_key_var.set(api_key)
        self.passphrase_var.set("")
        self.api_secret_var.set("")
        self.api_secret_text.delete("1.0", tk.END)
        self._apply_field_layout(exchange_name, has_saved_secret=bool(api_secret), source=source)

    def get_exchange_instructions(self, exchange_name: str) -> str:
        """Get setup instructions for an exchange"""
        instructions = {
            # Tier 1 Centralized Exchanges
            "binance": """
Binance API Setup:
1. Go to: https://www.binance.com/en/my/settings/api-management
2. Create new API key with a descriptive label
3. Enable Spot & Margin Trading permissions
4. Enable Reading, Spot Trading permissions
5. Copy API Key and Secret Key
⚠️ Check local regulations before using Binance
            """,
            "kraken": """
Kraken API Setup:
1. Go to: https://www.kraken.com/u/security/api
2. Create new API key
3. Enable Query Funds, Query Open Orders & Trades
4. Enable Trade permissions if you want live trading
5. Copy API Key and Private Key
            """,
            "kucoin": """
KuCoin API Setup:
1. Go to: https://www.kucoin.com/account/api
2. Create new API key
3. Enable General and Trade permissions
4. Set API restrictions (IP whitelist recommended)
5. Copy API Key, Secret, and Passphrase
Note: All three fields are required for KuCoin
            """,
            "coinbase": """
Coinbase (Advanced Trade) API setup:
1. Sign in to the Coinbase Developer Platform: https://portal.cdp.coinbase.com
   -> API Keys -> Secret API Keys -> Create API key
2. Under Advanced Settings choose signature algorithm ECDSA
   (Ed25519 keys are not supported)
3. Permissions: View is enough to test and for paper mode. Add Trade only if
   you will trade live. Leave Transfer OFF. An IP allowlist is recommended.
4. Paste the two values Coinbase gives you:
   - Key name:    organizations/<org-id>/apiKeys/<key-id>
   - Private key: the whole block, including the -----BEGIN EC PRIVATE KEY-----
     and -----END EC PRIVATE KEY----- lines (several lines)
5. Press Test Connection (read-only, never places an order), then Save.
Old Coinbase Pro keys and key + secret + passphrase keys no longer work.
            """,
            "bybit": """
Bybit API Setup:
1. Go to: https://www.bybit.com/app/user/api-management
2. Create new API key
3. Enable Contract Trading & Spot Trading
4. Set IP restrictions for security
5. Copy API Key and Secret
            """,
            # Tier 2 Centralized Exchanges
            "okx": """
OKX API Setup:
1. Go to: https://www.okx.com/account/users/myApi
2. Create new API key
3. Enable Trading permissions
4. Set passphrase and IP whitelist
5. Copy API Key, Secret Key, and Passphrase
            """,
            "bitstamp": """
Bitstamp API Setup:
1. Go to: https://www.bitstamp.net/account/security/api/
2. Create new API key
3. Enable Trading permissions
4. Set IP restrictions
5. Copy API Key and Secret
            """,
            "bitfinex": """
Bitfinex API Setup:
1. Go to: https://setting.bitfinex.com/api
2. Create new API key
3. Enable Orders permissions for trading
4. Copy API Key and Secret Key
            """,
            "huobi": """
Huobi API Setup:
1. Go to: https://www.huobi.com/en-us/apikey/
2. Create new API key
3. Enable Trading permissions
4. Set IP whitelist for security
5. Copy Access Key and Secret Key
            """,
            "gate": """
Gate.io API Setup:
1. Go to: https://www.gate.io/myaccount/apiv4keys
2. Create new API key
3. Enable Spot Trading permissions
4. Set IP restrictions
5. Copy API Key and Secret
            """,
            "mexc": """
MEXC API Setup:
1. Go to: https://www.mexc.com/user/openapi
2. Create new API key
3. Enable Spot Trading permissions
4. Copy API Key and Secret Key
            """,
            "bitget": """
Bitget API Setup:
1. Go to: https://www.bitget.com/api-doc
2. Create new API key in account settings
3. Enable Trading permissions
4. Copy API Key, Secret Key, and Passphrase
            """,
            "crypto_com": """
Crypto.com API Setup:
1. Go to: https://crypto.com/exchange/document/api
2. Contact support for API access
3. Enable trading permissions once approved
4. Copy API Key and Secret
            """,
            "gemini": """
Gemini API Setup:
1. Go to: https://exchange.gemini.com/settings/api
2. Create new API key
3. Enable Trading scope
4. Copy API Key and Secret
            """,
            "bitpanda": """
Bitpanda Pro API Setup:
1. Go to: https://web.bitpanda.com/apikey
2. Create new API key
3. Enable Trading permissions
4. Copy API Token
            """,
            "upbit": """
Upbit API Setup:
1. Go to: https://upbit.com/mypage/open_api_management
2. Create new API key
3. Enable trading permissions if available
4. Copy Access Key and Secret Key
Note: Trading may be restricted for non-KR residents
            """,
            "coincheck": """
Coincheck API Setup:
1. Go to: https://coincheck.com/api_settings
2. Create new API key
3. Enable trading permissions
4. Copy API Key and Secret
Note: Primarily for Japanese users
            """,
            "phemex": """
Phemex API Setup:
1. Go to: https://phemex.com/account/api-manage
2. Create new API key
3. Enable trading permissions
4. Copy API Key and Secret
            """,
            "robinhood": """
Robinhood Setup:
1. Enable Robinhood Crypto in your mobile app
2. Contact Robinhood support for API access
3. API access may be limited to certain users
Note: Robinhood has limited API availability
            """,
            "etoro": """
eToro Setup:
1. eToro has limited API access
2. Contact eToro support for institutional API
3. Most retail users use web interface
Note: API primarily for institutional clients
            """,
            "deribit": """
Deribit API Setup:
1. Go to: https://www.deribit.com/main#/account?scrollTo=api
2. Create new API key
3. Enable Trading permissions for derivatives
4. Copy Client ID and Client Secret
            """,
            # DeFi Platforms
            "uniswap": """
Uniswap Integration:
1. Use Web3 wallet (MetaMask, WalletConnect, etc.)
2. Connect wallet to PowerTrader
3. Approve token spending contracts
4. Set slippage tolerance
Note: Gas fees apply for all transactions
            """,
            "sushiswap": """
SushiSwap Integration:
1. Connect Web3 wallet (MetaMask recommended)
2. Approve SUSHI token contracts
3. Set transaction parameters
4. Monitor gas fees
            """,
            "aave": """
Aave Protocol Integration:
1. Connect Web3 wallet
2. Approve lending pool contracts
3. Set up health factor monitoring
4. Configure liquidation protection
            """,
            "compound": """
Compound Protocol Integration:
1. Connect Web3 wallet
2. Enable cToken minting
3. Set up interest rate monitoring
4. Configure supply/borrow limits
            """,
            "yearn": """
Yearn Finance Integration:
1. Connect Web3 wallet
2. Approve vault deposits
3. Monitor strategy performance
4. Set up automatic harvesting
            """,
            "lido": """
Lido Finance Setup:
1. Connect Web3 wallet
2. Approve stETH contracts
3. Monitor staking rewards
4. Set up liquid staking
            """,
            # Regional Exchanges
            "quidax": """
Quidax API Setup (Nigeria):
1. Go to: https://www.quidax.com/settings/api
2. Create new API key
3. Verify identity (KYC required)
4. Enable trading permissions
5. Copy API Key and Secret
            """,
            "luno": """
Luno API Setup (Africa):
1. Go to: https://www.luno.com/wallet/security/api_keys
2. Create new API key
3. Enable trading permissions
4. Copy API Key ID and Secret
            """,
            "rain": """
Rain API Setup (Middle East):
1. Contact Rain support for API access
2. Complete KYC verification
3. Request trading permissions
4. Copy provided credentials
            """,
            "bitoasis": """
BitOasis API Setup (MENA):
1. Contact BitOasis for API documentation
2. Complete institutional verification
3. Request API access
4. Follow provided integration guide
            """,
        }

        # Default instruction for unlisted exchanges
        default_instruction = f"""
{exchange_name.title()} API Setup:
1. Visit the official {exchange_name.title()} website
2. Navigate to Account Settings > API Management
3. Create a new API key with appropriate permissions
4. Enable trading permissions if you plan to trade
5. Copy the API Key and Secret Key
6. Set up IP whitelist for security (recommended)

Note: Specific instructions may vary. Check the exchange's official API documentation.
Official docs usually found at: https://{exchange_name}.com/api-docs
        """

        return instructions.get(exchange_name, default_instruction)

    def save_exchange_config(self):
        """Save exchange configuration"""
        exchange_name = self.exchange_var.get()
        if not exchange_name:
            messagebox.showwarning("No Exchange", "Please select an exchange first")
            return

        api_key, api_secret, passphrase = self._form_credentials()

        if not api_key or not api_secret:
            fields = exchange_fields(exchange_name)
            messagebox.showerror(
                "Missing Fields",
                f"{fields['key_label'].rstrip(':')} and "
                f"{fields['secret_label'].rstrip(':')} are required",
            )
            return

        if exchange_name == "coinbase":
            # Refuse to save something that could never authenticate.
            try:
                api_key = coinbase_auth.validate_key_name(api_key)
                coinbase_auth.load_private_key(api_secret)
                api_secret = coinbase_auth.normalise_private_key(api_secret)
            except coinbase_auth.CoinbaseCredentialError as exc:
                messagebox.showerror("Invalid Coinbase credentials", str(exc))
                return

        if exchange_name == "kucoin" and not passphrase:
            messagebox.showerror("Missing Field", "Passphrase is required for KuCoin")
            return

        try:
            # Save credentials (OS keyring via pt_secrets; never to a file)
            self.config_manager.update_exchange_credentials(
                exchange_name, api_key, api_secret, passphrase
            )

            # Enable the exchange
            self.config_manager.enable_exchange(exchange_name, True)

            messagebox.showinfo(
                "Success",
                f"{exchange_name.title()} configuration saved!\n\n"
                "The credentials are in your operating system's credential store.",
            )
            # Don't leave a secret sitting in the form.
            self.api_secret_text.delete("1.0", tk.END)
            self.api_secret_var.set("")
            self.passphrase_var.set("")
            saved = self._saved_credentials(exchange_name)
            self.secret_hint_var.set(
                saved_secret_hint(exchange_name, saved.credential_source if saved else "")
            )
            self.refresh_exchange_list()
            self.status_var.set(f"Saved configuration for {exchange_name.title()}")

        except pt_secrets.KeyringUnavailable as e:
            messagebox.showerror("No secure credential store", str(e))
        except pt_secrets.SecretsError as e:
            messagebox.showerror("Credentials not saved", str(e))
        except Exception as e:
            messagebox.showerror(
                "Error", f"Failed to save configuration ({type(e).__name__})."
            )

    def _typed_secret(self, exchange_name: str) -> str:
        if exchange_fields(exchange_name)["multiline"]:
            return self.api_secret_text.get("1.0", tk.END).strip()
        return self.api_secret_var.get().strip()

    def _saved_credentials(self, exchange_name: str):
        """The saved ExchangeConfig for ``exchange_name``, or None."""
        if self.config_manager.config is None:
            self.config_manager.load_config()
        return self.config_manager.get_exchange_config(exchange_name)

    def _form_credentials(self):
        """What is currently typed in the setup form: (api_key, api_secret, passphrase).
        Blank key AND secret mean "use the saved credentials". A saved secret or
        passphrase is never shown, so a blank box next to a typed key means
        "keep the saved one"."""
        exchange_name = self.exchange_var.get()
        api_key = self.api_key_var.get().strip()
        api_secret = self._typed_secret(exchange_name)
        passphrase = self.passphrase_var.get().strip()
        if api_key and (not api_secret or not passphrase):
            saved = self._saved_credentials(exchange_name)
            if saved is not None:
                api_secret = api_secret or saved.api_secret or ""
                passphrase = passphrase or saved.passphrase or ""
        return api_key, api_secret, passphrase

    def _apply_field_layout(self, exchange_name: str, has_saved_secret: bool, source: str = ""):
        """Labels and input widget for this exchange's credential shape."""
        fields = exchange_fields(exchange_name)
        self.api_key_label.configure(text=fields["key_label"])
        self.api_secret_label.configure(text=fields["secret_label"])
        if fields["multiline"]:
            self.api_secret_entry.grid_remove()
            self.api_secret_text.grid(row=1, column=1, padx=(10, 0), pady=2, sticky="we")
        else:
            self.api_secret_text.grid_remove()
            self.api_secret_entry.grid(row=1, column=1, padx=(10, 0), pady=2)
        self.secret_hint_label.grid(row=3, column=1, padx=(10, 0), sticky="w")
        self.secret_hint_var.set(
            saved_secret_hint(exchange_name, source) if has_saved_secret else ""
        )

    def _append_result(self, text: str):
        self.results_text.insert(tk.END, text)
        self.results_text.see(tk.END)

    def _run_in_background(self, job, on_item, on_done=None):
        """Run ``job(emit)`` on a worker thread. Tk is only ever touched from the UI
        thread: the worker puts results on a queue and the UI polls it."""
        results: queue.Queue = queue.Queue()

        def worker():
            try:
                job(lambda item: results.put(("item", item)))
            except Exception as exc:  # never leave the user without an answer
                results.put(("error", exc))
            results.put(("done", None))

        def poll():
            finished = False
            try:
                while True:
                    kind, value = results.get_nowait()
                    if kind == "item":
                        on_item(value)
                    elif kind == "error":
                        on_item(None)
                    else:
                        finished = True
                        break
            except queue.Empty:
                pass
            if finished:
                if on_done:
                    on_done()
            else:
                self.window.after(50, poll)

        threading.Thread(target=worker, daemon=True).start()
        self.window.after(50, poll)

    def _test_one(self, exchange_name, *credentials):
        """One connection test as a ConnectionTestResult; a connector bug becomes a
        result, not an exception."""
        try:
            return self.multi_exchange.test_exchange_connection(
                exchange_name, *credentials
            )
        except Exception as exc:
            return ConnectionTestResult(
                exchange_name,
                ConnectionStatus.ENDPOINT_ERROR,
                f"The test failed unexpectedly ({type(exc).__name__}).",
            )

    def test_exchange_connection(self):
        """Test the credentials typed in the form (or the saved ones if the form is
        blank) with one read-only call. Runs off the UI thread."""
        exchange_name = self.exchange_var.get()
        if not exchange_name:
            messagebox.showwarning("No Exchange", "Please select an exchange first")
            return

        credentials = self._form_credentials()
        if not credentials[0] and not credentials[1]:
            credentials = (None, None, None)  # fall back to saved credentials

        self.notebook.select(2)
        self._append_result(f"\n🧪 Testing {exchange_name.title()} connection...\n")
        self.status_var.set(f"Testing {exchange_name.title()}...")

        def job(emit):
            emit(self._test_one(exchange_name, *credentials))

        def on_item(result):
            if result is None:  # job itself failed
                result = ConnectionTestResult(
                    exchange_name, ConnectionStatus.ENDPOINT_ERROR, "The test failed unexpectedly."
                )
            self._append_result(format_test_result(exchange_name, result) + "\n")
            self.status_var.set(
                f"{exchange_name.title()} connection successful"
                if result.ok
                else f"{exchange_name.title()} test: {STATUS_HEADLINES[result.status]}"
            )

        self._run_in_background(job, on_item)

    def test_all_exchanges(self):
        """Test every enabled exchange that has saved credentials (read-only)."""
        self.results_text.delete(1.0, tk.END)
        self._append_result("🧪 Testing all configured exchanges...\n\n")

        config = self.config_manager.load_config()
        targets = [
            ex.exchange_type
            for ex in (config.exchanges if config else [])
            if ex.enabled and ex.api_key
        ]
        tally = {"ok": 0}

        def job(emit):
            for name in targets:
                emit((name, self._test_one(name)))

        def on_item(item):
            if item is None:
                return
            name, result = item
            tally["ok"] += 1 if result.ok else 0
            self._append_result(format_test_result(name, result) + "\n")

        def on_done():
            self._append_result(
                f"\n📊 Summary: {tally['ok']}/{len(targets)} exchanges tested successfully\n"
            )
            self.status_var.set(f"Tested {len(targets)} exchanges, {tally['ok']} successful")

        self._run_in_background(job, on_item, on_done)

    def run(self):
        """Start the GUI"""
        self.window.mainloop()


if __name__ == "__main__":
    app = ExchangeConfigGUI()
    app.run()
